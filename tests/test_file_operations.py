"""Unit tests for FileOperations class."""

import errno
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest

from mergy.models import (
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MatchReason,
    MergeSelection,
)
from mergy.operations import FileOperations
from mergy.scanning import FileHasher


class TestFileOperationsBasic:
    """Tests for basic file copying operations."""

    def test_copy_file_normal(self, temp_dir: Path) -> None:
        """Copy regular file, verify content and metadata preserved."""
        ops = FileOperations()

        # Create source file
        source = temp_dir / "source" / "file.txt"
        source.parent.mkdir(parents=True)
        source.write_text("test content")

        dest = temp_dir / "dest" / "file.txt"

        # Copy file
        result = ops._copy_file(source, dest, dry_run=False)

        assert result is True
        assert dest.exists()
        assert dest.read_text() == "test content"

    def test_copy_file_creates_parent_dirs(self, temp_dir: Path) -> None:
        """Copy to non-existent directory structure."""
        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")

        # Nested destination
        dest = temp_dir / "a" / "b" / "c" / "dest.txt"

        result = ops._copy_file(source, dest, dry_run=False)

        assert result is True
        assert dest.exists()
        assert dest.read_text() == "content"

    def test_copy_file_dry_run(self, temp_dir: Path) -> None:
        """Verify no actual copy in dry-run mode."""
        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")

        dest = temp_dir / "dest.txt"

        result = ops._copy_file(source, dest, dry_run=True)

        assert result is True
        assert not dest.exists()

    def test_copy_file_dry_run_validates_source_readable(self, temp_dir: Path) -> None:
        """Verify dry-run checks source readability."""
        if platform.system() == "Windows":
            pytest.skip("Permission tests not reliable on Windows")

        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")
        os.chmod(source, 0o000)

        try:
            dest = temp_dir / "dest.txt"
            result = ops._copy_file(source, dest, dry_run=True)

            assert result is False
            errors = ops.get_errors()
            assert len(errors) > 0
            assert "Permission denied" in errors[0]
        finally:
            os.chmod(source, 0o644)

    def test_copy_file_dry_run_validates_dest_writable(self, temp_dir: Path) -> None:
        """Verify dry-run checks destination parent writability."""
        if platform.system() == "Windows":
            pytest.skip("Permission tests not reliable on Windows")

        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")

        # Create a read-only directory
        readonly_dir = temp_dir / "readonly"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, 0o555)

        try:
            dest = readonly_dir / "dest.txt"
            result = ops._copy_file(source, dest, dry_run=True)

            assert result is False
            errors = ops.get_errors()
            assert len(errors) > 0
            assert "Cannot write to destination directory" in errors[0]
        finally:
            os.chmod(readonly_dir, 0o755)

    def test_copy_file_preserves_metadata(self, temp_dir: Path) -> None:
        """Test that copy preserves file metadata."""
        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")

        # Set specific modification time
        os.utime(source, (1000000, 1000000))
        source_stat = source.stat()

        dest = temp_dir / "dest.txt"
        ops._copy_file(source, dest, dry_run=False)

        dest_stat = dest.stat()
        assert dest_stat.st_mtime == source_stat.st_mtime


class TestFileOperationsConflictDetection:
    """Tests for conflict detection."""

    def test_detect_conflict_different_hashes(self, temp_dir: Path) -> None:
        """Files with different content return FileConflict."""
        ops = FileOperations()

        primary = temp_dir / "primary.txt"
        primary.write_text("primary content")

        source = temp_dir / "source.txt"
        source.write_text("different content")

        conflict = ops._detect_conflict(primary, source, Path("source.txt"))

        assert conflict is not None
        assert conflict.primary_file == primary
        assert conflict.conflicting_file == source
        assert conflict.primary_hash != conflict.conflict_hash

    def test_detect_conflict_same_hash_returns_none(self, temp_dir: Path) -> None:
        """Duplicate files return None."""
        ops = FileOperations()

        primary = temp_dir / "primary.txt"
        primary.write_text("same content")

        source = temp_dir / "source.txt"
        source.write_text("same content")

        conflict = ops._detect_conflict(primary, source, Path("source.txt"))

        assert conflict is None

    def test_detect_conflict_missing_file(self, temp_dir: Path) -> None:
        """Handle file not found gracefully."""
        ops = FileOperations()

        primary = temp_dir / "primary.txt"
        primary.write_text("content")

        source = temp_dir / "nonexistent.txt"

        conflict = ops._detect_conflict(primary, source, Path("nonexistent.txt"))

        assert conflict is None
        errors = ops.get_errors()
        assert len(errors) > 0
        assert "Failed to compute hash" in errors[0]

    def test_detect_conflict_hash_failure(self, temp_dir: Path) -> None:
        """Handle hash computation errors."""
        hasher = FileHasher()
        ops = FileOperations(hasher=hasher)

        primary = temp_dir / "primary.txt"
        primary.write_text("content")

        source = temp_dir / "source.txt"
        source.write_text("other content")

        # Mock hash_file to return None for source
        original_hash_file = hasher.hash_file

        def mock_hash_file(path: Path):
            if path == source:
                return None
            return original_hash_file(path)

        with patch.object(hasher, "hash_file", side_effect=mock_hash_file):
            conflict = ops._detect_conflict(primary, source, Path("source.txt"))

        assert conflict is None
        errors = ops.get_errors()
        assert len(errors) > 0

    def test_detect_conflict_preserves_nested_relative_path(self, temp_dir: Path) -> None:
        """Verify FileConflict.relative_path preserves full nested path."""
        ops = FileOperations()

        # Create nested primary file
        primary_dir = temp_dir / "primary"
        nested_primary = primary_dir / "logs" / "app" / "2024"
        nested_primary.mkdir(parents=True)
        primary_file = nested_primary / "system.log"
        primary_file.write_text("primary log content")

        # Create nested source file
        source_dir = temp_dir / "source"
        nested_source = source_dir / "logs" / "app" / "2024"
        nested_source.mkdir(parents=True)
        source_file = nested_source / "system.log"
        source_file.write_text("different source log content")

        # The relative path should preserve the full nested structure
        nested_rel_path = Path("logs/app/2024/system.log")
        conflict = ops._detect_conflict(primary_file, source_file, nested_rel_path)

        assert conflict is not None
        assert conflict.relative_path == nested_rel_path
        assert str(conflict.relative_path) == "logs/app/2024/system.log"


class TestFileOperationsConflictResolution:
    """Tests for conflict resolution."""

    def test_resolve_conflict_primary_newer(self, temp_dir: Path) -> None:
        """Keep primary, move source to .merged/."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source" / "file.txt"
        source_file.parent.mkdir()
        source_file.write_text("source content")

        # Set times: primary is newer
        now = datetime.now()
        older = datetime(2020, 1, 1)

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=now,
            conflict_ctime=older,
        )

        result = ops._resolve_conflict(conflict, primary_dir, dry_run=False)

        assert result is True
        assert primary_file.exists()
        merged_dir = primary_dir / ".merged"
        assert merged_dir.exists()
        # Source file should be moved to .merged with hash suffix
        merged_files = list(merged_dir.iterdir())
        assert len(merged_files) == 1
        assert "def456" in merged_files[0].name

    def test_resolve_conflict_source_newer(self, temp_dir: Path) -> None:
        """Move primary to .merged/, copy source to primary location."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source" / "file.txt"
        source_file.parent.mkdir()
        source_file.write_text("source content")

        # Set times: source is newer
        now = datetime.now()
        older = datetime(2020, 1, 1)

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=older,
            conflict_ctime=now,
        )

        result = ops._resolve_conflict(conflict, primary_dir, dry_run=False)

        assert result is True
        # Primary location should now have source content
        assert primary_file.read_text() == "source content"
        # Old primary should be in .merged
        merged_dir = primary_dir / ".merged"
        merged_files = list(merged_dir.iterdir())
        assert len(merged_files) == 1
        assert "abc123" in merged_files[0].name

    def test_resolve_conflict_creates_merged_dir(self, temp_dir: Path) -> None:
        """Verify .merged/ directory creation."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source.txt"
        source_file.write_text("source content")

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=datetime.now(),
            conflict_ctime=datetime(2020, 1, 1),
        )

        merged_dir = primary_dir / ".merged"
        assert not merged_dir.exists()

        ops._resolve_conflict(conflict, primary_dir, dry_run=False)

        assert merged_dir.exists()
        assert merged_dir.is_dir()

    def test_resolve_conflict_hash_suffix(self, temp_dir: Path) -> None:
        """Verify filename format name_hash16chars.ext."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "document.pdf"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source.pdf"
        source_file.write_text("source content")

        full_hash = "abcdef1234567890abcdef1234567890"

        conflict = FileConflict(
            relative_path=Path("document.pdf"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="primary_hash",
            conflict_hash=full_hash,
            primary_ctime=datetime.now(),
            conflict_ctime=datetime(2020, 1, 1),
        )

        ops._resolve_conflict(conflict, primary_dir, dry_run=False)

        merged_files = list((primary_dir / ".merged").iterdir())
        assert len(merged_files) == 1
        merged_name = merged_files[0].name
        # Should be document_abcdef1234567890.pdf (16 char hash)
        assert merged_name == "document_abcdef1234567890.pdf"

    def test_resolve_conflict_nested_path(self, temp_dir: Path) -> None:
        """Test with nested directory structure (e.g., logs/app/system.log)."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        nested_dir = primary_dir / "logs" / "app"
        nested_dir.mkdir(parents=True)
        primary_file = nested_dir / "system.log"
        primary_file.write_text("primary log")

        source_file = temp_dir / "source" / "logs" / "app" / "system.log"
        source_file.parent.mkdir(parents=True)
        source_file.write_text("source log")

        conflict = FileConflict(
            relative_path=Path("logs/app/system.log"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=datetime.now(),
            conflict_ctime=datetime(2020, 1, 1),
        )

        result = ops._resolve_conflict(conflict, primary_dir, dry_run=False)

        assert result is True
        # .merged/ should be at logs/app/.merged/
        merged_dir = nested_dir / ".merged"
        assert merged_dir.exists()
        merged_files = list(merged_dir.iterdir())
        assert len(merged_files) == 1

    def test_resolve_conflict_dry_run(self, temp_dir: Path) -> None:
        """Verify no file operations in dry-run mode."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source.txt"
        source_file.write_text("source content")

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=datetime.now(),
            conflict_ctime=datetime(2020, 1, 1),
        )

        result = ops._resolve_conflict(conflict, primary_dir, dry_run=True)

        assert result is True
        # No .merged/ directory should be created
        merged_dir = primary_dir / ".merged"
        assert not merged_dir.exists()
        # Primary file unchanged
        assert primary_file.read_text() == "primary content"

    def test_resolve_conflict_dry_run_validates_files_exist(
        self, temp_dir: Path
    ) -> None:
        """Verify dry-run checks that both conflict files exist."""
        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        # Source file does not exist
        source_file = temp_dir / "nonexistent.txt"

        conflict = FileConflict(
            relative_path=Path("file.txt"),
            primary_file=primary_file,
            conflicting_file=source_file,
            primary_hash="abc123",
            conflict_hash="def456",
            primary_ctime=datetime.now(),
            conflict_ctime=datetime(2020, 1, 1),
        )

        result = ops._resolve_conflict(conflict, primary_dir, dry_run=True)

        assert result is False
        errors = ops.get_errors()
        assert len(errors) > 0
        assert "Conflicting file not found" in errors[0]

    def test_resolve_conflict_dry_run_validates_merged_dir_writable(
        self, temp_dir: Path
    ) -> None:
        """Verify dry-run checks .merged directory can be created."""
        if platform.system() == "Windows":
            pytest.skip("Permission tests not reliable on Windows")

        ops = FileOperations()

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()
        primary_file = primary_dir / "file.txt"
        primary_file.write_text("primary content")

        source_file = temp_dir / "source.txt"
        source_file.write_text("source content")

        # Make primary_dir read-only so .merged cannot be created
        os.chmod(primary_dir, 0o555)

        try:
            conflict = FileConflict(
                relative_path=Path("file.txt"),
                primary_file=primary_file,
                conflicting_file=source_file,
                primary_hash="abc123",
                conflict_hash="def456",
                primary_ctime=datetime.now(),
                conflict_ctime=datetime(2020, 1, 1),
            )

            result = ops._resolve_conflict(conflict, primary_dir, dry_run=True)

            assert result is False
            errors = ops.get_errors()
            assert len(errors) > 0
            assert "Cannot create .merged directory" in errors[0]
        finally:
            os.chmod(primary_dir, 0o755)


class TestFileOperationsEmptyDirCleanup:
    """Tests for empty directory cleanup."""

    def test_cleanup_empty_dirs_removes_empty(self, temp_dir: Path) -> None:
        """Remove empty directories."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        empty_subdir = folder / "empty"
        empty_subdir.mkdir()

        result = ops._cleanup_empty_dirs(folder, dry_run=False)

        assert result == 1
        assert not empty_subdir.exists()

    def test_cleanup_empty_dirs_preserves_nonempty(self, temp_dir: Path) -> None:
        """Keep directories with files."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        subdir = folder / "nonempty"
        subdir.mkdir()
        (subdir / "file.txt").write_text("content")

        result = ops._cleanup_empty_dirs(folder, dry_run=False)

        assert result == 0
        assert subdir.exists()
        assert (subdir / "file.txt").exists()

    def test_cleanup_empty_dirs_skips_merged(self, temp_dir: Path) -> None:
        """Never remove .merged/ directories."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        merged_dir = folder / ".merged"
        merged_dir.mkdir()

        result = ops._cleanup_empty_dirs(folder, dry_run=False)

        assert result == 0
        assert merged_dir.exists()

    def test_cleanup_empty_dirs_recursive(self, temp_dir: Path) -> None:
        """Handle nested empty directories."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        nested = folder / "a" / "b" / "c"
        nested.mkdir(parents=True)

        result = ops._cleanup_empty_dirs(folder, dry_run=False)

        # Should remove c, b, a (3 directories)
        assert result == 3
        assert not (folder / "a").exists()

    def test_cleanup_empty_dirs_dry_run(self, temp_dir: Path) -> None:
        """Count but don't remove in dry-run mode."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        empty_subdir = folder / "empty"
        empty_subdir.mkdir()

        result = ops._cleanup_empty_dirs(folder, dry_run=True)

        assert result == 1
        assert empty_subdir.exists()  # Still exists


class TestFileOperationsErrorHandling:
    """Tests for error handling."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Permission tests not reliable on Windows",
    )
    def test_permission_denied_continues(self, temp_dir: Path) -> None:
        """Skip file, log error, continue operation."""
        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")

        # Make file unreadable
        os.chmod(source, 0o000)

        try:
            dest = temp_dir / "dest.txt"
            result = ops._copy_file(source, dest, dry_run=False)

            assert result is False
            errors = ops.get_errors()
            assert len(errors) > 0
            assert "Permission denied" in errors[0]
        finally:
            os.chmod(source, 0o644)

    def test_file_not_found_continues(self, temp_dir: Path) -> None:
        """Log error, continue operation."""
        ops = FileOperations()

        source = temp_dir / "nonexistent.txt"
        dest = temp_dir / "dest.txt"

        result = ops._copy_file(source, dest, dry_run=False)

        assert result is False
        errors = ops.get_errors()
        assert len(errors) > 0
        assert "File not found" in errors[0] or "not found" in errors[0].lower()

    def test_disk_full_aborts(self, temp_dir: Path) -> None:
        """Raise exception on disk full."""
        ops = FileOperations()

        source = temp_dir / "source.txt"
        source.write_text("content")
        dest = temp_dir / "dest.txt"

        # Mock shutil.copy2 to raise disk full error
        with patch("shutil.copy2") as mock_copy:
            mock_copy.side_effect = OSError(errno.ENOSPC, "No space left on device")

            with pytest.raises(OSError) as exc_info:
                ops._copy_file(source, dest, dry_run=False)

            assert exc_info.value.errno == errno.ENOSPC

        errors = ops.get_errors()
        assert len(errors) > 0
        assert "Disk full" in errors[0]

    def test_errors_accumulated(self, temp_dir: Path) -> None:
        """Verify get_errors() returns all errors."""
        ops = FileOperations()

        # Generate multiple errors
        ops._copy_file(temp_dir / "nonexistent1.txt", temp_dir / "dest1.txt", False)
        ops._copy_file(temp_dir / "nonexistent2.txt", temp_dir / "dest2.txt", False)
        ops._copy_file(temp_dir / "nonexistent3.txt", temp_dir / "dest3.txt", False)

        errors = ops.get_errors()
        assert len(errors) == 3

    def test_clear_errors(self, temp_dir: Path) -> None:
        """Verify error list can be cleared."""
        ops = FileOperations()

        ops._copy_file(temp_dir / "nonexistent.txt", temp_dir / "dest.txt", False)
        assert len(ops.get_errors()) > 0

        ops.clear_errors()
        assert len(ops.get_errors()) == 0

    def test_merge_folders_clears_errors_between_calls(self, temp_dir: Path) -> None:
        """Verify errors from first merge_folders call don't appear in second call."""
        ops = FileOperations()

        # First merge: create scenario that generates an error
        primary1 = temp_dir / "primary1"
        primary1.mkdir()
        source1 = temp_dir / "source1"
        source1.mkdir()
        bad_file = source1 / "bad.txt"
        bad_file.write_text("content")

        # Create merge selection for first call
        selection1 = _create_selection(primary1, [source1])

        # Simulate an error by removing the file after scanning but before copying
        # We'll use a simpler approach: create a scenario with a hash error
        # Instead, let's just verify via the errors list
        # First, manually add an error to simulate previous run
        ops._errors.append("Error from previous run")

        # Second merge: successful merge that should clear old errors
        primary2 = temp_dir / "primary2"
        primary2.mkdir()
        source2 = temp_dir / "source2"
        source2.mkdir()
        (source2 / "good.txt").write_text("good content")

        selection2 = _create_selection(primary2, [source2])
        result2 = ops.merge_folders(selection2, dry_run=False)

        # The second merge result should NOT contain errors from the first run
        assert "Error from previous run" not in result2.errors
        assert result2.files_copied == 1


class TestFileOperationsProgressTracking:
    """Tests for progress callback functionality."""

    def test_progress_callback_invoked(self, temp_dir: Path) -> None:
        """Verify callback called for each file."""
        callback_calls: List[tuple] = []

        def callback(idx: int, total: int, filename: str) -> None:
            callback_calls.append((idx, total, filename))

        ops = FileOperations(progress_callback=callback)

        # Create source folder with files
        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()

        source_dir = temp_dir / "source"
        source_dir.mkdir()
        (source_dir / "file1.txt").write_text("content1")
        (source_dir / "file2.txt").write_text("content2")
        (source_dir / "file3.txt").write_text("content3")

        selection = _create_selection(primary_dir, [source_dir])
        ops.merge_folders(selection, dry_run=True)

        assert len(callback_calls) == 3

    def test_progress_callback_parameters(self, temp_dir: Path) -> None:
        """Verify correct index, total, filename passed."""
        callback_calls: List[tuple] = []

        def callback(idx: int, total: int, filename: str) -> None:
            callback_calls.append((idx, total, filename))

        ops = FileOperations(progress_callback=callback)

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()

        source_dir = temp_dir / "source"
        source_dir.mkdir()
        (source_dir / "test.txt").write_text("content")

        selection = _create_selection(primary_dir, [source_dir])
        ops.merge_folders(selection, dry_run=True)

        assert len(callback_calls) == 1
        idx, total, filename = callback_calls[0]
        assert idx == 0
        assert total == 1
        assert "test.txt" in filename

    def test_progress_callback_optional(self, temp_dir: Path) -> None:
        """Verify operation works without callback."""
        ops = FileOperations()  # No callback

        primary_dir = temp_dir / "primary"
        primary_dir.mkdir()

        source_dir = temp_dir / "source"
        source_dir.mkdir()
        (source_dir / "file.txt").write_text("content")

        selection = _create_selection(primary_dir, [source_dir])

        # Should not raise
        result = ops.merge_folders(selection, dry_run=True)
        assert result.files_copied == 1


class TestFileOperationsWalkFiles:
    """Tests for _walk_files method."""

    def test_walk_files_returns_all_files(self, temp_dir: Path) -> None:
        """Walk folder and return all files."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        (folder / "file1.txt").write_text("content1")
        (folder / "file2.txt").write_text("content2")

        files = ops._walk_files(folder)

        assert len(files) == 2
        filenames = [rel.name for _, rel in files]
        assert "file1.txt" in filenames
        assert "file2.txt" in filenames

    def test_walk_files_skips_merged_dir(self, temp_dir: Path) -> None:
        """Skip .merged/ directories during traversal."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        (folder / "file.txt").write_text("content")

        merged = folder / ".merged"
        merged.mkdir()
        (merged / "old_file.txt").write_text("old content")

        files = ops._walk_files(folder)

        assert len(files) == 1
        filenames = [rel.name for _, rel in files]
        assert "file.txt" in filenames
        assert "old_file.txt" not in filenames

    def test_walk_files_handles_nested(self, temp_dir: Path) -> None:
        """Handle nested directory structures."""
        ops = FileOperations()

        folder = temp_dir / "folder"
        folder.mkdir()
        (folder / "root.txt").write_text("root")

        nested = folder / "a" / "b"
        nested.mkdir(parents=True)
        (nested / "deep.txt").write_text("deep")

        files = ops._walk_files(folder)

        assert len(files) == 2
        rel_paths = [str(rel) for _, rel in files]
        assert any("root.txt" in p for p in rel_paths)
        assert any("deep.txt" in p for p in rel_paths)


def _create_selection(
    primary_path: Path, source_paths: List[Path]
) -> MergeSelection:
    """Helper to create a MergeSelection for testing."""
    now = datetime.now()

    primary = ComputerFolder(
        path=primary_path,
        name=primary_path.name,
        file_count=0,
        total_size=0,
        oldest_file_date=now,
        newest_file_date=now,
    )

    sources = [
        ComputerFolder(
            path=p,
            name=p.name,
            file_count=0,
            total_size=0,
            oldest_file_date=now,
            newest_file_date=now,
        )
        for p in source_paths
    ]

    match = FolderMatch(
        folders=[primary] + sources,
        confidence=1.0,
        match_reason=MatchReason.EXACT_PREFIX,
        base_name="test",
    )

    return MergeSelection(
        primary=primary,
        merge_from=sources,
        match_group=match,
    )
