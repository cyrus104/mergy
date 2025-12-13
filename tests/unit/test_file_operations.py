"""
Unit tests for FileOperations conflict logic in merger_ops.py.

Tests cover:
- Conflict detection (different hashes)
- No conflict for identical files
- Conflict resolution (newer wins)
- .merged/ directory handling
- File copying for new files
- Duplicate file skipping
- Metadata preservation
- Empty directory removal
- Dry-run mode behavior
"""

import os
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mergy.models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    FileConflict,
    MergeOperation,
    MatchReason,
)
from mergy.scanning import FileHasher
from mergy.operations import FileOperations

# Import from conftest through tests package
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import create_computer_folder


def create_merge_selection(
    primary_name: str,
    merge_from_names: list,
    base_dir: Path
) -> MergeSelection:
    """Create a MergeSelection for testing."""
    primary = create_computer_folder(primary_name, base_dir)
    merge_from = [create_computer_folder(name, base_dir) for name in merge_from_names]

    match = FolderMatch(
        folders=[primary] + merge_from,
        confidence=100.0,
        match_reason=MatchReason.EXACT_PREFIX,
        base_name=primary_name
    )

    return MergeSelection(
        primary=primary,
        merge_from=merge_from,
        match_group=match
    )


@pytest.mark.unit
class TestConflictDetection:
    """Tests for file conflict detection."""

    def test_detect_conflict_different_hashes(self, temp_base_dir: Path):
        """Two files at same path with different content creates conflict."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create two files with different content
        primary_dir = temp_base_dir / "primary"
        merge_dir = temp_base_dir / "merge"
        primary_dir.mkdir()
        merge_dir.mkdir()

        primary_file = primary_dir / "data.txt"
        merge_file = merge_dir / "data.txt"
        primary_file.write_text("primary content")
        merge_file.write_text("different content")

        # Compare files
        conflict = ops._compare_files(
            primary_file,
            merge_file,
            Path("data.txt")
        )

        assert conflict is not None
        assert conflict.relative_path == Path("data.txt")
        assert conflict.primary_hash != conflict.conflict_hash

    def test_detect_conflict_same_hash_no_conflict(self, temp_base_dir: Path):
        """Identical files should not create conflict."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create two files with same content
        primary_dir = temp_base_dir / "primary"
        merge_dir = temp_base_dir / "merge"
        primary_dir.mkdir()
        merge_dir.mkdir()

        same_content = "identical content"
        primary_file = primary_dir / "same.txt"
        merge_file = merge_dir / "same.txt"
        primary_file.write_text(same_content)
        merge_file.write_text(same_content)

        # Compare files
        conflict = ops._compare_files(
            primary_file,
            merge_file,
            Path("same.txt")
        )

        # No conflict for identical files
        assert conflict is None


@pytest.mark.unit
class TestConflictResolution:
    """Tests for conflict resolution logic."""

    def test_resolve_conflict_newer_wins(self, temp_base_dir: Path):
        """File with newer ctime kept in primary location."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create primary folder structure
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "conflict.txt"
        primary_file.write_text("primary version - newer")

        # Create merge folder structure
        merge_dir = temp_base_dir / "merge"
        merge_dir.mkdir()
        merge_file = merge_dir / "conflict.txt"
        merge_file.write_text("merge version - older")

        # Get actual file stats
        primary_stat = primary_file.stat()
        merge_stat = merge_file.stat()

        # Create conflict with primary as newer
        conflict = FileConflict(
            relative_path=Path("conflict.txt"),
            primary_file=primary_file,
            conflicting_file=merge_file,
            primary_hash=hasher.get_hash(primary_file),
            conflict_hash=hasher.get_hash(merge_file),
            primary_ctime=datetime.fromtimestamp(primary_stat.st_ctime),
            conflict_ctime=datetime.fromtimestamp(merge_stat.st_ctime) - timedelta(hours=1)
        )

        # Resolve conflict
        ops._resolve_conflict(conflict, primary_dir)

        # Primary file should remain unchanged
        assert primary_file.read_text() == "primary version - newer"

        # Older file should be in .merged/
        merged_dir = primary_dir / ".merged"
        assert merged_dir.exists()
        merged_files = list(merged_dir.glob("conflict_*.txt"))
        assert len(merged_files) == 1

    def test_resolve_conflict_older_to_merged(self, temp_base_dir: Path):
        """Older file moved to .merged/ with hash suffix."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("older primary")

        merge_dir = temp_base_dir / "merge"
        merge_dir.mkdir()
        merge_file = merge_dir / "file.txt"
        merge_file.write_text("newer merge")

        # Create conflict with merge file as newer
        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=merge_file,
            primary_hash=hasher.get_hash(primary_file),
            conflict_hash=hasher.get_hash(merge_file),
            primary_ctime=datetime.now() - timedelta(hours=2),  # Older
            conflict_ctime=datetime.now()  # Newer
        )

        # Resolve conflict
        ops._resolve_conflict(conflict, primary_dir)

        # Newer file should now be in primary location
        assert primary_file.read_text() == "newer merge"

        # Older file should be in .merged/
        merged_dir = primary_dir / ".merged"
        assert merged_dir.exists()


@pytest.mark.unit
class TestMergedDirectory:
    """Tests for .merged/ directory handling."""

    def test_merged_directory_creation(self, temp_base_dir: Path):
        """Verify .merged/ created at correct level."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create nested structure
        primary_dir = temp_base_dir / "primary"
        nested_dir = primary_dir / "subdir" / "nested"
        nested_dir.mkdir(parents=True)
        primary_file = nested_dir / "file.txt"
        primary_file.write_text("primary")

        merge_dir = temp_base_dir / "merge"
        merge_nested = merge_dir / "subdir" / "nested"
        merge_nested.mkdir(parents=True)
        merge_file = merge_nested / "file.txt"
        merge_file.write_text("merge")

        conflict = FileConflict(
            relative_path=Path("subdir/nested/file.txt"),
            primary_file=primary_file,
            conflicting_file=merge_file,
            primary_hash=hasher.get_hash(primary_file),
            conflict_hash=hasher.get_hash(merge_file),
            primary_ctime=datetime.now(),
            conflict_ctime=datetime.now() - timedelta(hours=1)
        )

        ops._resolve_conflict(conflict, primary_dir)

        # .merged/ should be created in subdir/nested/
        expected_merged = primary_dir / "subdir" / "nested" / ".merged"
        assert expected_merged.exists()

    def test_merged_filename_format(self, temp_base_dir: Path):
        """Verify filename_hash16chars.ext format."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "document.pdf"
        primary_file.write_bytes(b"primary pdf content")

        merge_dir = temp_base_dir / "merge"
        merge_dir.mkdir()
        merge_file = merge_dir / "document.pdf"
        merge_file.write_bytes(b"merge pdf content")

        conflict = FileConflict(
            relative_path=Path("document.pdf"),
            primary_file=primary_file,
            conflicting_file=merge_file,
            primary_hash=hasher.get_hash(primary_file),
            conflict_hash=hasher.get_hash(merge_file),
            primary_ctime=datetime.now(),
            conflict_ctime=datetime.now() - timedelta(hours=1)
        )

        ops._resolve_conflict(conflict, primary_dir)

        merged_dir = primary_dir / ".merged"
        merged_files = list(merged_dir.glob("document_*.pdf"))
        assert len(merged_files) == 1

        # Check filename format: document_<16char_hash>.pdf
        filename = merged_files[0].name
        assert filename.startswith("document_")
        assert filename.endswith(".pdf")
        # Extract hash part
        hash_part = filename[len("document_"):-len(".pdf")]
        assert len(hash_part) == 16
        assert all(c in '0123456789abcdef' for c in hash_part)


@pytest.mark.unit
class TestFileCopying:
    """Tests for file copy operations."""

    def test_copy_new_file(self, temp_base_dir: Path):
        """Copy file that doesn't exist in primary."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create primary folder (empty)
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()

        # Create source file
        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        source_file = source_dir / "new_file.txt"
        source_file.write_text("new content")

        # Destination
        dest_file = primary_dir / "new_file.txt"

        # Copy file
        ops._copy_file(source_file, dest_file)

        assert dest_file.exists()
        assert dest_file.read_text() == "new content"

    def test_copy_creates_parent_directories(self, temp_base_dir: Path):
        """Copy file creates parent directories as needed."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()

        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        source_file = source_dir / "file.txt"
        source_file.write_text("content")

        # Destination in nested path that doesn't exist
        dest_file = primary_dir / "deep" / "nested" / "path" / "file.txt"

        ops._copy_file(source_file, dest_file)

        assert dest_file.exists()
        assert dest_file.read_text() == "content"

    def test_skip_duplicate_file(self, temp_base_dir: Path):
        """Skip file with identical hash in full merge operation."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create primary folder with file
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "duplicate.txt"
        primary_file.write_text("same content")

        # Create source folder with identical file
        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        source_file = source_dir / "duplicate.txt"
        source_file.write_text("same content")

        # Create merge selection
        selection = create_merge_selection("primary", ["source"], temp_base_dir)

        # Execute merge
        operation = ops.merge_folders(selection)

        # File should be skipped (duplicate)
        assert operation.files_skipped >= 1
        assert operation.files_copied == 0

    def test_preserve_file_metadata(self, temp_base_dir: Path):
        """Verify shutil.copy2() preserves timestamps."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()

        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        source_file = source_dir / "metadata.txt"
        source_file.write_text("content")

        # Set specific modification time
        old_mtime = time.time() - 86400  # 1 day ago
        os.utime(source_file, (old_mtime, old_mtime))

        original_mtime = source_file.stat().st_mtime

        dest_file = primary_dir / "metadata.txt"
        ops._copy_file(source_file, dest_file)

        # Check that modification time is preserved
        dest_mtime = dest_file.stat().st_mtime
        assert abs(dest_mtime - original_mtime) < 1  # Within 1 second


@pytest.mark.unit
class TestEmptyDirectoryRemoval:
    """Tests for empty directory cleanup."""

    def test_remove_empty_directories(self, temp_base_dir: Path):
        """Verify recursive empty dir cleanup."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create a folder with an empty subdirectory
        folder = temp_base_dir / "to_clean"
        folder.mkdir()
        empty_subdir = folder / "empty_child"
        empty_subdir.mkdir()

        # Verify structure exists
        assert folder.exists()
        assert empty_subdir.exists()

        # Remove empty directories
        removed = ops._remove_empty_dirs(folder)

        # At least the empty child and root should be removed
        assert removed >= 1
        # The folder should be removed since it's now empty
        assert not folder.exists()

    def test_remove_empty_directories_with_merged(self, temp_base_dir: Path):
        """Don't remove dirs containing .merged/."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        folder = temp_base_dir / "with_merged"
        folder.mkdir()

        # Create .merged directory with content
        merged = folder / ".merged"
        merged.mkdir()
        (merged / "preserved.txt").write_text("keep this")

        # Try to remove
        removed = ops._remove_empty_dirs(folder)

        # Folder should NOT be removed (has .merged with content)
        assert folder.exists()
        assert merged.exists()

    def test_remove_empty_dirs_preserves_files(self, temp_base_dir: Path):
        """Directories with files are not removed."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        folder = temp_base_dir / "has_files"
        nested = folder / "nested"
        nested.mkdir(parents=True)
        (nested / "important.txt").write_text("keep")

        removed = ops._remove_empty_dirs(folder)

        # No directories should be removed
        assert folder.exists()
        assert nested.exists()
        assert removed == 0


@pytest.mark.unit
class TestDryRunMode:
    """Tests for dry-run mode behavior."""

    def test_dry_run_no_modifications(self, temp_base_dir: Path):
        """Verify dry_run=True prevents file operations."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        # Create primary folder (empty)
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()

        # Create source file
        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        source_file = source_dir / "file.txt"
        source_file.write_text("content")

        dest_file = primary_dir / "file.txt"

        # Try to copy in dry-run mode
        ops._copy_file(source_file, dest_file)

        # File should NOT be created
        assert not dest_file.exists()

    def test_dry_run_no_directory_creation(self, temp_base_dir: Path):
        """Verify no .merged/ dirs created in dry-run."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary")

        merge_dir = temp_base_dir / "merge"
        merge_dir.mkdir()
        merge_file = merge_dir / "file.txt"
        merge_file.write_text("merge")

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=merge_file,
            primary_hash=hasher.get_hash(primary_file),
            conflict_hash=hasher.get_hash(merge_file),
            primary_ctime=datetime.now(),
            conflict_ctime=datetime.now() - timedelta(hours=1)
        )

        ops._resolve_conflict(conflict, primary_dir)

        # .merged directory should NOT be created
        merged_dir = primary_dir / ".merged"
        assert not merged_dir.exists()

    def test_dry_run_no_empty_dir_removal(self, temp_base_dir: Path):
        """Verify no directories removed in dry-run."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        folder = temp_base_dir / "empty_folder"
        folder.mkdir()

        removed = ops._remove_empty_dirs(folder)

        # Nothing should be removed
        assert removed == 0
        assert folder.exists()

    def test_dry_run_full_merge_no_changes(self, temp_base_dir: Path):
        """Full merge in dry-run mode makes no file system changes."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        # Create folders with files
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        (primary_dir / "existing.txt").write_text("primary")

        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        (source_dir / "new_file.txt").write_text("new")
        (source_dir / "existing.txt").write_text("different")  # Conflict

        # Snapshot of file system before merge
        primary_files_before = set(p.name for p in primary_dir.iterdir())
        source_files_before = set(p.name for p in source_dir.iterdir())

        # Create selection and merge
        selection = create_merge_selection("primary", ["source"], temp_base_dir)
        operation = ops.merge_folders(selection)

        # File system should be unchanged
        primary_files_after = set(p.name for p in primary_dir.iterdir())
        source_files_after = set(p.name for p in source_dir.iterdir())

        assert primary_files_before == primary_files_after
        assert source_files_before == source_files_after

        # But operation should have statistics
        assert operation.dry_run is True


@pytest.mark.unit
class TestMergeFolders:
    """Tests for the complete merge_folders operation."""

    def test_merge_folders_basic(self, temp_base_dir: Path):
        """Basic merge operation with new files."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create primary folder
        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        (primary_dir / "file1.txt").write_text("primary file 1")

        # Create source folder with new file
        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        (source_dir / "file2.txt").write_text("source file 2")

        selection = create_merge_selection("primary", ["source"], temp_base_dir)
        operation = ops.merge_folders(selection)

        # New file should be copied
        assert operation.files_copied >= 1
        assert (primary_dir / "file2.txt").exists()

    def test_merge_folders_with_conflicts(self, temp_base_dir: Path):
        """Merge with file conflicts."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        (primary_dir / "conflict.txt").write_text("primary version")

        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        (source_dir / "conflict.txt").write_text("source version")

        selection = create_merge_selection("primary", ["source"], temp_base_dir)
        operation = ops.merge_folders(selection)

        # Conflict should be resolved
        assert operation.conflicts_resolved >= 1
        # .merged directory should exist
        assert (primary_dir / ".merged").exists()

    def test_merge_folders_statistics(self, temp_base_dir: Path):
        """Verify MergeOperation counters accuracy."""
        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_dir = temp_base_dir / "primary"
        primary_dir.mkdir()
        (primary_dir / "existing.txt").write_text("existing content")
        (primary_dir / "duplicate.txt").write_text("same content")

        source_dir = temp_base_dir / "source"
        source_dir.mkdir()
        (source_dir / "new.txt").write_text("new file")
        (source_dir / "duplicate.txt").write_text("same content")  # Duplicate
        (source_dir / "existing.txt").write_text("different content")  # Conflict

        selection = create_merge_selection("primary", ["source"], temp_base_dir)
        operation = ops.merge_folders(selection)

        assert operation.files_copied == 1  # new.txt
        assert operation.files_skipped == 1  # duplicate.txt
        assert operation.conflicts_resolved == 1  # existing.txt
