"""Integration tests for FileOperations class."""

import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pytest

from mergy.models import (
    ComputerFolder,
    FolderMatch,
    MatchReason,
    MergeSelection,
)
from mergy.operations import FileOperations
from mergy.scanning import FileHasher


class TestFileOperationsMergeWorkflows:
    """Integration tests for complete merge workflows."""

    def test_merge_simple_scenario(
        self, merge_scenario_simple: Dict[str, Path]
    ) -> None:
        """Complete merge with new files, duplicates, conflicts."""
        ops = FileOperations()

        selection = _create_selection(
            merge_scenario_simple["primary"],
            [merge_scenario_simple["source"]],
        )

        result = ops.merge_folders(selection, dry_run=False)

        # file3.txt and file4.txt are new
        assert result.files_copied == 2
        # file2.txt is duplicate (same content)
        assert result.files_skipped == 1
        # shared.txt is conflict
        assert result.conflicts_resolved == 1

        # Verify new files exist in primary
        primary = merge_scenario_simple["primary"]
        assert (primary / "file3.txt").exists()
        assert (primary / "file4.txt").exists()

        # Verify .merged directory exists for conflict
        assert (primary / ".merged").exists()

    def test_merge_multiple_sources(self, temp_dir: Path) -> None:
        """Merge from 3+ folders into primary."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "base.txt").write_text("base")

        # Create 3 source folders
        sources = []
        for i in range(1, 4):
            source = temp_dir / f"source{i}"
            source.mkdir()
            (source / f"from_source{i}.txt").write_text(f"content{i}")
            sources.append(source)

        selection = _create_selection(primary, sources)
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == 3
        assert (primary / "from_source1.txt").exists()
        assert (primary / "from_source2.txt").exists()
        assert (primary / "from_source3.txt").exists()

    def test_merge_nested_conflicts(self, temp_dir: Path) -> None:
        """Conflicts in deeply nested directory structures."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        nested_primary = primary / "logs" / "app" / "2024"
        nested_primary.mkdir(parents=True)
        (nested_primary / "system.log").write_text("primary log content")

        source = temp_dir / "source"
        nested_source = source / "logs" / "app" / "2024"
        nested_source.mkdir(parents=True)
        (nested_source / "system.log").write_text("source log content")

        # Make primary file newer
        _set_ctime(nested_primary / "system.log", datetime(2024, 6, 1))
        _set_ctime(nested_source / "system.log", datetime(2024, 1, 1))

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.conflicts_resolved == 1

        # .merged should be at logs/app/2024/.merged
        merged_dir = nested_primary / ".merged"
        assert merged_dir.exists()
        merged_files = list(merged_dir.iterdir())
        assert len(merged_files) == 1

    def test_merge_preserves_primary_newer(self, temp_dir: Path) -> None:
        """Verify newer primary files not overwritten."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        primary_file = primary / "file.txt"
        primary_file.write_text("primary content - newer")

        source = temp_dir / "source"
        source.mkdir()
        source_file = source / "file.txt"
        source_file.write_text("source content - older")

        # Primary is newer
        _set_ctime(primary_file, datetime(2024, 6, 1))
        _set_ctime(source_file, datetime(2024, 1, 1))

        selection = _create_selection(primary, [source])
        ops.merge_folders(selection, dry_run=False)

        # Primary file should still have its content
        assert primary_file.read_text() == "primary content - newer"

    def test_merge_updates_primary_with_newer(self, temp_dir: Path) -> None:
        """Verify newer source files replace primary."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        primary_file = primary / "file.txt"
        primary_file.write_text("primary content - older")

        source = temp_dir / "source"
        source.mkdir()
        source_file = source / "file.txt"
        source_file.write_text("source content - newer")

        # Source is newer
        _set_ctime(primary_file, datetime(2024, 1, 1))
        _set_ctime(source_file, datetime(2024, 6, 1))

        selection = _create_selection(primary, [source])
        ops.merge_folders(selection, dry_run=False)

        # Primary file should now have source content
        assert primary_file.read_text() == "source content - newer"

    def test_merge_statistics_accurate(self, temp_dir: Path) -> None:
        """Verify MergeOperation counts match actual operations."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing")
        (primary / "duplicate.txt").write_text("same content")

        source = temp_dir / "source"
        source.mkdir()
        (source / "new1.txt").write_text("new file 1")
        (source / "new2.txt").write_text("new file 2")
        (source / "duplicate.txt").write_text("same content")  # Duplicate
        (source / "existing.txt").write_text("different")  # Conflict

        _set_ctime(primary / "existing.txt", datetime(2024, 1, 1))
        _set_ctime(source / "existing.txt", datetime(2024, 6, 1))

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == 2  # new1.txt, new2.txt
        assert result.files_skipped == 1  # duplicate.txt
        assert result.conflicts_resolved == 1  # existing.txt

        # Verify actual filesystem matches
        assert (primary / "new1.txt").exists()
        assert (primary / "new2.txt").exists()
        assert (primary / ".merged").exists()

    def test_merge_dry_run_no_changes(self, temp_dir: Path) -> None:
        """Verify dry-run leaves filesystem unchanged."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "existing.txt").write_text("original")

        source = temp_dir / "source"
        source.mkdir()
        (source / "new.txt").write_text("new content")
        (source / "existing.txt").write_text("different content")

        # Record filesystem state
        primary_files_before = set(primary.iterdir())

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=True)

        # Stats should show what would happen
        assert result.files_copied == 1
        assert result.conflicts_resolved == 1

        # But filesystem should be unchanged
        primary_files_after = set(primary.iterdir())
        assert primary_files_before == primary_files_after
        assert not (primary / ".merged").exists()

    def test_merge_dry_run_validates_permissions(self, temp_dir: Path) -> None:
        """Verify dry-run validates read/write permissions."""
        if platform.system() == "Windows":
            pytest.skip("Permission tests not reliable on Windows")

        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()
        unreadable = source / "unreadable.txt"
        unreadable.write_text("content")
        os.chmod(unreadable, 0o000)

        try:
            selection = _create_selection(primary, [source])
            result = ops.merge_folders(selection, dry_run=True)

            # Should detect the permission issue
            assert result.files_copied == 0
            assert len(result.errors) > 0
            assert "Permission denied" in result.errors[0]
        finally:
            os.chmod(unreadable, 0o644)

    def test_merge_empty_source_folder(self, temp_dir: Path) -> None:
        """Handle empty source folders gracefully."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "file.txt").write_text("content")

        source = temp_dir / "source"
        source.mkdir()
        # Source is empty

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == 0
        assert result.files_skipped == 0
        assert result.conflicts_resolved == 0


class TestFileOperationsRealWorldScenarios:
    """Tests for real-world edge cases."""

    @pytest.mark.skipif(
        not hasattr(os, "symlink") or platform.system() == "Windows",
        reason="Symlinks not supported on this platform",
    )
    def test_merge_with_symlinks(self, temp_dir: Path) -> None:
        """Handle symlinks in source folders (follow them)."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()

        # Create target file and symlink
        target = temp_dir / "target.txt"
        target.write_text("target content")
        symlink = source / "link.txt"
        symlink.symlink_to(target)

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == 1
        # Should have copied the content, not the symlink
        copied_file = primary / "link.txt"
        assert copied_file.exists()
        assert copied_file.read_text() == "target content"

    def test_merge_large_files(self, temp_dir: Path, sample_files: Dict[str, Path]) -> None:
        """Test with files >10MB."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()

        # Copy large file to source
        large_file = sample_files["large"]
        import shutil
        shutil.copy2(large_file, source / "large.txt")

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == 1
        assert (primary / "large.txt").exists()
        # Verify content preserved
        assert (primary / "large.txt").stat().st_size == large_file.stat().st_size

    def test_merge_special_characters_in_names(self, temp_dir: Path) -> None:
        """Files with spaces, unicode, special chars."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()

        # Create files with special characters
        special_files = [
            "file with spaces.txt",
            "file-with-dashes.txt",
            "file_with_underscores.txt",
            "file.multiple.dots.txt",
        ]

        for name in special_files:
            (source / name).write_text(f"content of {name}")

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        assert result.files_copied == len(special_files)
        for name in special_files:
            assert (primary / name).exists()

    def test_merge_partial_failure_continues(self, temp_dir: Path) -> None:
        """Some files fail, others succeed."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()
        (source / "file1.txt").write_text("content1")
        (source / "file2.txt").write_text("content2")
        (source / "file3.txt").write_text("content3")

        # Simulate partial failure by removing a file after walking
        # We'll test the error handling by creating an unreadable file
        if platform.system() != "Windows":
            bad_file = source / "file2.txt"
            os.chmod(bad_file, 0o000)

            try:
                selection = _create_selection(primary, [source])
                result = ops.merge_folders(selection, dry_run=False)

                # file1 and file3 should succeed, file2 should fail
                assert result.files_copied == 2
                assert len(result.errors) > 0
            finally:
                os.chmod(bad_file, 0o644)
        else:
            # On Windows, just verify normal operation
            selection = _create_selection(primary, [source])
            result = ops.merge_folders(selection, dry_run=False)
            assert result.files_copied == 3

    def test_merge_creates_merge_operation_object(self, temp_dir: Path) -> None:
        """Verify return value structure."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        source.mkdir()
        (source / "file.txt").write_text("content")

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        # Verify MergeOperation fields
        assert result.selection == selection
        assert result.dry_run is False
        assert isinstance(result.timestamp, datetime)
        assert isinstance(result.files_copied, int)
        assert isinstance(result.files_skipped, int)
        assert isinstance(result.conflicts_resolved, int)
        assert isinstance(result.folders_removed, int)
        assert isinstance(result.errors, list)


class TestFileOperationsCleanupIntegration:
    """Integration tests for empty directory cleanup."""

    def test_cleanup_after_merge(self, temp_dir: Path) -> None:
        """Empty directories cleaned up after files moved."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "source"
        subdir = source / "subdir"
        subdir.mkdir(parents=True)
        (subdir / "file.txt").write_text("content")

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        # File copied to primary
        assert (primary / "subdir" / "file.txt").exists()

        # Source directory structure cleaned up (subdir now empty)
        # Note: the source folder itself is not removed
        assert result.folders_removed >= 1

    def test_cleanup_preserves_non_empty(self, temp_dir: Path) -> None:
        """Directories with remaining files not removed."""
        ops = FileOperations()

        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "existing.txt").write_text("primary content")

        source = temp_dir / "source"
        source.mkdir()
        # File that will become duplicate (not removed from source)
        (source / "existing.txt").write_text("primary content")
        # Another file that stays
        (source / "other.txt").write_text("other")

        selection = _create_selection(primary, [source])
        result = ops.merge_folders(selection, dry_run=False)

        # Source files still exist (duplicates skipped, other file copied)
        # Source directory not removed because it still has files
        assert source.exists()


# Helper functions


def _create_selection(
    primary_path: Path, source_paths: List[Path]
) -> MergeSelection:
    """Create a MergeSelection for testing."""
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


def _set_ctime(path: Path, dt: datetime) -> None:
    """Set file creation/modification time.

    Note: On most systems, ctime cannot be set directly. We use mtime
    as a proxy since the actual implementation may use either.
    """
    timestamp = dt.timestamp()
    os.utime(path, (timestamp, timestamp))
