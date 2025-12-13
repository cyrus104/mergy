"""
Unit tests for data models in merger_models.py.

Tests cover:
- ComputerFolder instantiation and field validation
- FolderMatch creation with multiple folders
- MergeSelection structure
- FileConflict with hash/timestamp data
- MergeOperation default values and error tracking
- MergeSummary aggregation
- MatchReason enum values
"""

from datetime import datetime, timedelta
from pathlib import Path

import pytest

from mergy.models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    FileConflict,
    MergeOperation,
    MergeSummary,
    MatchReason,
)


@pytest.mark.unit
class TestComputerFolder:
    """Tests for ComputerFolder dataclass."""

    def test_computer_folder_creation(self, temp_base_dir: Path):
        """Validate ComputerFolder instantiation with all fields."""
        now = datetime.now()
        earlier = now - timedelta(days=30)

        folder = ComputerFolder(
            path=temp_base_dir / "test-folder",
            name="test-folder",
            file_count=42,
            total_size=1024000,
            oldest_file_date=earlier,
            newest_file_date=now
        )

        assert folder.path == temp_base_dir / "test-folder"
        assert folder.name == "test-folder"
        assert folder.file_count == 42
        assert folder.total_size == 1024000
        assert folder.oldest_file_date == earlier
        assert folder.newest_file_date == now

    def test_computer_folder_with_none_dates(self, temp_base_dir: Path):
        """Test empty folder scenario with None dates."""
        folder = ComputerFolder(
            path=temp_base_dir / "empty-folder",
            name="empty-folder",
            file_count=0,
            total_size=0,
            oldest_file_date=None,
            newest_file_date=None
        )

        assert folder.file_count == 0
        assert folder.total_size == 0
        assert folder.oldest_file_date is None
        assert folder.newest_file_date is None


@pytest.mark.unit
class TestFolderMatch:
    """Tests for FolderMatch dataclass."""

    def test_folder_match_creation(self, sample_folders):
        """Validate FolderMatch with multiple folders."""
        # Use first 3 folders from sample (computer-01 family)
        folders_to_match = sample_folders[:3]

        match = FolderMatch(
            folders=folders_to_match,
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="computer-01"
        )

        assert len(match.folders) == 3
        assert match.confidence == 100.0
        assert match.match_reason == MatchReason.EXACT_PREFIX
        assert match.base_name == "computer-01"

    def test_folder_match_two_folders(self, temp_base_dir: Path):
        """Validate FolderMatch with exactly two folders."""
        folder1 = ComputerFolder(
            path=temp_base_dir / "folder1",
            name="folder1",
            file_count=5,
            total_size=500,
            oldest_file_date=datetime.now(),
            newest_file_date=datetime.now()
        )
        folder2 = ComputerFolder(
            path=temp_base_dir / "folder2",
            name="folder2",
            file_count=3,
            total_size=300,
            oldest_file_date=datetime.now(),
            newest_file_date=datetime.now()
        )

        match = FolderMatch(
            folders=[folder1, folder2],
            confidence=90.0,
            match_reason=MatchReason.NORMALIZED,
            base_name="folder"
        )

        assert len(match.folders) == 2
        assert match.folders[0] == folder1
        assert match.folders[1] == folder2


@pytest.mark.unit
class TestMergeSelection:
    """Tests for MergeSelection dataclass."""

    def test_merge_selection_creation(self, sample_folders):
        """Validate MergeSelection structure."""
        # Create a match first
        folders_to_match = sample_folders[:3]
        match = FolderMatch(
            folders=folders_to_match,
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="computer-01"
        )

        # Create selection with first folder as primary
        selection = MergeSelection(
            primary=folders_to_match[0],
            merge_from=folders_to_match[1:],
            match_group=match
        )

        assert selection.primary == folders_to_match[0]
        assert len(selection.merge_from) == 2
        assert selection.merge_from[0] == folders_to_match[1]
        assert selection.merge_from[1] == folders_to_match[2]
        assert selection.match_group == match


@pytest.mark.unit
class TestFileConflict:
    """Tests for FileConflict dataclass."""

    def test_file_conflict_creation(self, temp_base_dir: Path):
        """Validate FileConflict with hash/timestamp data."""
        now = datetime.now()
        earlier = now - timedelta(hours=2)

        conflict = FileConflict(
            relative_path=Path("data/file.txt"),
            primary_file=temp_base_dir / "primary" / "data" / "file.txt",
            conflicting_file=temp_base_dir / "other" / "data" / "file.txt",
            primary_hash="abc123def456abc123def456abc123def456abc123def456abc123def456abc1",
            conflict_hash="xyz789xyz789xyz789xyz789xyz789xyz789xyz789xyz789xyz789xyz789xyz7",
            primary_ctime=now,
            conflict_ctime=earlier
        )

        assert conflict.relative_path == Path("data/file.txt")
        assert conflict.primary_file == temp_base_dir / "primary" / "data" / "file.txt"
        assert conflict.conflicting_file == temp_base_dir / "other" / "data" / "file.txt"
        assert len(conflict.primary_hash) == 64
        assert len(conflict.conflict_hash) == 64
        assert conflict.primary_ctime == now
        assert conflict.conflict_ctime == earlier
        # Primary is newer
        assert conflict.primary_ctime > conflict.conflict_ctime


@pytest.mark.unit
class TestMergeOperation:
    """Tests for MergeOperation dataclass."""

    def test_merge_operation_defaults(self, sample_folders):
        """Verify default values for counters."""
        match = FolderMatch(
            folders=sample_folders[:2],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="computer-01"
        )
        selection = MergeSelection(
            primary=sample_folders[0],
            merge_from=[sample_folders[1]],
            match_group=match
        )

        operation = MergeOperation(
            selection=selection,
            dry_run=False,
            timestamp=datetime.now()
        )

        # Verify all counters default to 0
        assert operation.files_copied == 0
        assert operation.files_skipped == 0
        assert operation.conflicts_resolved == 0
        assert operation.folders_removed == 0
        assert operation.errors == []

    def test_merge_operation_error_tracking(self, sample_folders):
        """Test error list accumulation."""
        match = FolderMatch(
            folders=sample_folders[:2],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="computer-01"
        )
        selection = MergeSelection(
            primary=sample_folders[0],
            merge_from=[sample_folders[1]],
            match_group=match
        )

        operation = MergeOperation(
            selection=selection,
            dry_run=True,
            timestamp=datetime.now()
        )

        # Add errors
        operation.errors.append("Error 1: File not found")
        operation.errors.append("Error 2: Permission denied")
        operation.errors.append("Error 3: Disk full")

        assert len(operation.errors) == 3
        assert "Error 1: File not found" in operation.errors
        assert "Error 2: Permission denied" in operation.errors
        assert "Error 3: Disk full" in operation.errors

    def test_merge_operation_counter_updates(self, sample_folders):
        """Test counter increments."""
        match = FolderMatch(
            folders=sample_folders[:2],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="computer-01"
        )
        selection = MergeSelection(
            primary=sample_folders[0],
            merge_from=[sample_folders[1]],
            match_group=match
        )

        operation = MergeOperation(
            selection=selection,
            dry_run=False,
            timestamp=datetime.now()
        )

        # Simulate counter updates during merge
        operation.files_copied += 10
        operation.files_skipped += 5
        operation.conflicts_resolved += 2
        operation.folders_removed += 3

        assert operation.files_copied == 10
        assert operation.files_skipped == 5
        assert operation.conflicts_resolved == 2
        assert operation.folders_removed == 3


@pytest.mark.unit
class TestMergeSummary:
    """Tests for MergeSummary dataclass."""

    def test_merge_summary_aggregation(self):
        """Validate MergeSummary statistics."""
        summary = MergeSummary(
            total_operations=3,
            files_copied=100,
            files_skipped=50,
            conflicts_resolved=10,
            folders_removed=5,
            errors=["Error 1", "Error 2"],
            duration=120.5,
            interrupted=False
        )

        assert summary.total_operations == 3
        assert summary.files_copied == 100
        assert summary.files_skipped == 50
        assert summary.conflicts_resolved == 10
        assert summary.folders_removed == 5
        assert len(summary.errors) == 2
        assert summary.duration == 120.5
        assert summary.interrupted is False

    def test_merge_summary_defaults(self):
        """Test MergeSummary default values."""
        summary = MergeSummary()

        assert summary.total_operations == 0
        assert summary.files_copied == 0
        assert summary.files_skipped == 0
        assert summary.conflicts_resolved == 0
        assert summary.folders_removed == 0
        assert summary.errors == []
        assert summary.duration == 0.0
        assert summary.interrupted is False

    def test_merge_summary_interrupted_state(self):
        """Test MergeSummary with interrupted flag."""
        summary = MergeSummary(
            total_operations=1,
            files_copied=25,
            interrupted=True
        )

        assert summary.interrupted is True
        assert summary.files_copied == 25


@pytest.mark.unit
class TestMatchReason:
    """Tests for MatchReason enum."""

    def test_match_reason_enum_values(self):
        """Verify all MatchReason enum members."""
        # Check all four tiers exist
        assert MatchReason.EXACT_PREFIX.value == "exact_prefix"
        assert MatchReason.NORMALIZED.value == "normalized"
        assert MatchReason.TOKEN_MATCH.value == "token_match"
        assert MatchReason.FUZZY_MATCH.value == "fuzzy_match"

        # Verify exactly 4 members
        assert len(MatchReason) == 4

    def test_match_reason_comparison(self):
        """Test enum comparison."""
        assert MatchReason.EXACT_PREFIX == MatchReason.EXACT_PREFIX
        assert MatchReason.EXACT_PREFIX != MatchReason.NORMALIZED

    def test_match_reason_iteration(self):
        """Test that all enum values are accessible via iteration."""
        reasons = list(MatchReason)
        assert len(reasons) == 4
        assert MatchReason.EXACT_PREFIX in reasons
        assert MatchReason.NORMALIZED in reasons
        assert MatchReason.TOKEN_MATCH in reasons
        assert MatchReason.FUZZY_MATCH in reasons
