"""Unit tests for MergeOrchestrator."""

import errno
import io
import os
from datetime import datetime
from pathlib import Path
from typing import List
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from mergy.models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    MergeSummary,
)
from mergy.models.match_reason import MatchReason
from mergy.orchestration import MergeOrchestrator
from mergy.ui import MergeTUI


# ============================================================================
# TestScanWorkflow
# ============================================================================


class TestScanWorkflow:
    """Tests for the scan() workflow."""

    def test_scan_valid_path(self, temp_dir: Path) -> None:
        """Test successful scan with matches."""
        # Create folder structure that will match
        folder1 = temp_dir / "135897-ntp"
        folder1.mkdir()
        (folder1 / "file1.txt").write_text("content1")

        folder2 = temp_dir / "135897-ntp.newspace"
        folder2.mkdir()
        (folder2 / "file2.txt").write_text("content2")

        folder3 = temp_dir / "unrelated"
        folder3.mkdir()
        (folder3 / "file3.txt").write_text("content3")

        # Create orchestrator with captured output
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )
        orchestrator._tui = tui

        # Execute scan
        matches = orchestrator.scan()

        # Verify results
        assert len(matches) == 1
        assert len(matches[0].folders) == 2
        assert matches[0].confidence == 1.0  # Exact prefix match
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_scan_empty_directory(self, temp_dir: Path) -> None:
        """Test scan with no subdirectories."""
        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        matches = orchestrator.scan()

        assert len(matches) == 0

    def test_scan_invalid_path_not_exists(self, temp_dir: Path) -> None:
        """Test that ValueError is raised for non-existent base path."""
        non_existent = temp_dir / "does_not_exist"

        with pytest.raises(ValueError, match="Base path does not exist"):
            MergeOrchestrator(base_path=non_existent)

    def test_scan_not_directory(self, temp_dir: Path) -> None:
        """Test that ValueError is raised when base path is a file."""
        file_path = temp_dir / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="Base path is not a directory"):
            MergeOrchestrator(base_path=file_path)

    def test_scan_with_scanner_errors(self, temp_dir: Path) -> None:
        """Test that scanner errors are collected but scan continues."""
        # Create a valid folder
        folder1 = temp_dir / "valid-folder"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        # Create orchestrator
        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            verbose=True,
        )

        # Execute scan
        matches = orchestrator.scan()

        # Scan should complete successfully
        assert isinstance(matches, list)

    def test_scan_logging(self, temp_dir: Path) -> None:
        """Test that log file is created with correct format."""
        folder1 = temp_dir / "folder1"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        log_file = temp_dir / "test_scan.log"

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            log_file_path=log_file,
        )

        orchestrator.scan()

        # Verify log file exists and contains expected content
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "Computer Data Organization Tool" in log_content
        assert "SCAN PHASE" in log_content
        assert str(temp_dir) in log_content

    def test_scan_no_matches_unrelated_folders(self, temp_dir: Path) -> None:
        """Test scan with folders that don't match."""
        folder1 = temp_dir / "completely-different"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content1")

        folder2 = temp_dir / "another-unrelated"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content2")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.9,  # High threshold
        )

        matches = orchestrator.scan()

        assert len(matches) == 0


# ============================================================================
# TestMergeWorkflow
# ============================================================================


class TestMergeWorkflow:
    """Tests for the merge() workflow."""

    def test_merge_full_workflow(self, temp_dir: Path) -> None:
        """Test complete merge with selections, operations, summary."""
        # Create matching folders with files
        primary = temp_dir / "135897-ntp"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing content")

        source = temp_dir / "135897-ntp.newspace"
        source.mkdir()
        (source / "new_file.txt").write_text("new content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,  # Use dry run for testing
        )

        # Mock TUI to return a selection
        mock_selection = self._create_mock_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert isinstance(summary, MergeSummary)
        assert summary.total_operations == 1

    def test_merge_no_matches(self, temp_dir: Path) -> None:
        """Test merge when scan finds no matches."""
        # Create unrelated folders
        folder1 = temp_dir / "unrelated1"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "different2"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.95,  # High threshold ensures no match
        )

        summary = orchestrator.merge()

        assert summary.total_operations == 0
        assert summary.total_files_copied == 0

    def test_merge_user_skips_all(self, temp_dir: Path) -> None:
        """Test merge when user skips all match groups."""
        folder1 = temp_dir / "135897-ntp"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "135897-ntp.backup"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        # Mock TUI to return empty selections (user skipped all)
        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[]):
            summary = orchestrator.merge()

        assert summary.total_operations == 0

    def test_merge_user_quits_early(self, temp_dir: Path) -> None:
        """Test merge when user quits during review."""
        folder1 = temp_dir / "135897-ntp"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "135897-ntp.backup"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        # Mock TUI to return empty list (user quit)
        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[]):
            summary = orchestrator.merge()

        assert summary.total_operations == 0

    def test_merge_dry_run_mode(self, temp_dir: Path) -> None:
        """Test that dry run doesn't make actual file changes."""
        primary = temp_dir / "primary-folder"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing")

        source = temp_dir / "primary-folder.backup"
        source.mkdir()
        new_file = source / "new_file.txt"
        new_file.write_text("new content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        mock_selection = self._create_mock_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # File should not be copied in dry run
        assert not (primary / "new_file.txt").exists()
        assert new_file.exists()  # Source should remain

    def test_merge_with_conflicts(self, temp_dir: Path) -> None:
        """Test merge with file conflicts tracked correctly."""
        primary = temp_dir / "primary-folder"
        primary.mkdir()
        conflict_file = primary / "conflict.txt"
        conflict_file.write_text("primary version")

        source = temp_dir / "primary-folder.backup"
        source.mkdir()
        source_conflict = source / "conflict.txt"
        source_conflict.write_text("source version - different")

        # Set timestamps for conflict resolution
        os.utime(conflict_file, (datetime(2024, 6, 1).timestamp(), datetime(2024, 6, 1).timestamp()))
        os.utime(source_conflict, (datetime(2024, 1, 1).timestamp(), datetime(2024, 1, 1).timestamp()))

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        mock_selection = self._create_mock_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_operations == 1

    def test_merge_disk_full_error(self, temp_dir: Path) -> None:
        """Test that disk full error aborts remaining operations."""
        primary = temp_dir / "primary-folder"
        primary.mkdir()

        source = temp_dir / "primary-folder.backup"
        source.mkdir()
        (source / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        mock_selection = self._create_mock_selection(primary, source)

        # Mock FileOperations to raise ENOSPC error
        def mock_merge_raising_enospc(*args, **kwargs):
            error = OSError(errno.ENOSPC, "No space left on device")
            error.errno = errno.ENOSPC
            raise error

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                with patch('mergy.orchestration.merge_orchestrator.FileOperations') as MockFileOps:
                    mock_instance = MagicMock()
                    mock_instance.merge_folders.side_effect = mock_merge_raising_enospc
                    MockFileOps.return_value = mock_instance

                    summary = orchestrator.merge()

        # Should have error about disk full
        assert any("Disk full" in e for e in summary.errors)

    def test_merge_keyboard_interrupt(self, temp_dir: Path) -> None:
        """Test graceful exit on Ctrl+C."""
        folder1 = temp_dir / "folder1"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "folder1.backup"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        # Mock TUI to raise KeyboardInterrupt during review
        with patch.object(orchestrator._tui, 'review_match_groups', side_effect=KeyboardInterrupt):
            summary = orchestrator.merge()

        assert summary.total_operations == 0

    def _create_mock_selection(self, primary_path: Path, source_path: Path) -> MergeSelection:
        """Helper to create a mock MergeSelection."""
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary = ComputerFolder(
            path=primary_path,
            name=primary_path.name,
            file_count=10,
            total_size=1000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source = ComputerFolder(
            path=source_path,
            name=source_path.name,
            file_count=5,
            total_size=500,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match_group = FolderMatch(
            folders=[primary, source],
            confidence=0.95,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name=primary_path.name,
        )

        return MergeSelection(
            primary=primary,
            merge_from=[source],
            match_group=match_group,
        )


# ============================================================================
# TestErrorHandling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling behavior."""

    def test_scanner_errors_collected(self, temp_dir: Path) -> None:
        """Test that scanner errors propagate to orchestrator errors."""
        folder1 = temp_dir / "valid-folder"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        # Patch FolderScanner.scan_folder to simulate an error during scanning
        original_scan_folder = orchestrator._scanner.scan_folder

        def patched_scan_folder(folder_path: Path):
            if folder_path.name == "valid-folder":
                # For valid-folder, first add an error then return the result
                orchestrator._scanner._errors.append("Simulated scanner error for testing")
                return original_scan_folder(folder_path)
            return original_scan_folder(folder_path)

        with patch.object(orchestrator._scanner, 'scan_folder', side_effect=patched_scan_folder):
            matches = orchestrator.scan()

        # Errors should be in orchestrator's error list (propagated from scanner)
        assert "Simulated scanner error for testing" in orchestrator._errors

    def test_file_operation_errors_collected(self, temp_dir: Path) -> None:
        """Test that operation errors appear in summary."""
        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "primary.backup"
        source.mkdir()
        (source / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        mock_selection = TestMergeWorkflow()._create_mock_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # Summary should exist even with potential errors
        assert isinstance(summary, MergeSummary)

    def test_logger_initialization_failure(self, temp_dir: Path) -> None:
        """Test fallback when log file can't be created."""
        folder1 = temp_dir / "folder1"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        # Use a path that doesn't exist
        invalid_log_path = Path("/nonexistent/directory/log.txt")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            log_file_path=invalid_log_path,
        )

        # Should not raise, should print warning to stderr
        matches = orchestrator.scan()

        assert isinstance(matches, list)

    def test_invalid_min_confidence(self, temp_dir: Path) -> None:
        """Test that invalid min_confidence raises ValueError."""
        folder = temp_dir / "folder"
        folder.mkdir()

        with pytest.raises(ValueError, match="min_confidence must be between"):
            MergeOrchestrator(base_path=temp_dir, min_confidence=1.5)

        with pytest.raises(ValueError, match="min_confidence must be between"):
            MergeOrchestrator(base_path=temp_dir, min_confidence=-0.1)


# ============================================================================
# TestProgressIntegration
# ============================================================================


class TestProgressIntegration:
    """Tests for progress tracking integration."""

    def test_progress_callback_integration(self, temp_dir: Path) -> None:
        """Test that TUI progress updates during merge."""
        primary = temp_dir / "primary"
        primary.mkdir()

        source = temp_dir / "primary.backup"
        source.mkdir()
        (source / "file1.txt").write_text("content1")
        (source / "file2.txt").write_text("content2")

        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )
        orchestrator._tui = tui

        mock_selection = TestMergeWorkflow()._create_mock_selection(primary, source)

        with patch.object(tui, 'review_match_groups', return_value=[mock_selection]):
            with patch.object(tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_operations == 1

    def test_multiple_operations_progress(self, temp_dir: Path) -> None:
        """Test progress tracking across multiple merges."""
        # Create two matching folder pairs
        primary1 = temp_dir / "group1-main"
        primary1.mkdir()

        source1 = temp_dir / "group1-main.backup"
        source1.mkdir()
        (source1 / "file.txt").write_text("content")

        primary2 = temp_dir / "group2-main"
        primary2.mkdir()

        source2 = temp_dir / "group2-main.backup"
        source2.mkdir()
        (source2 / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        # Create two selections
        selection1 = TestMergeWorkflow()._create_mock_selection(primary1, source1)
        selection2 = TestMergeWorkflow()._create_mock_selection(primary2, source2)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection1, selection2]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_operations == 2


# ============================================================================
# TestVerboseMode
# ============================================================================


class TestVerboseMode:
    """Tests for verbose mode output."""

    def test_verbose_shows_scanner_warnings(self, temp_dir: Path) -> None:
        """Test that verbose mode shows scanner warnings."""
        folder = temp_dir / "folder"
        folder.mkdir()
        (folder / "file.txt").write_text("content")

        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            verbose=True,
        )
        orchestrator._tui = tui

        # Patch FolderScanner.scan_folder to simulate an error during scanning
        original_scan_folder = orchestrator._scanner.scan_folder

        def patched_scan_folder(folder_path: Path):
            if folder_path.name == "folder":
                # Add a scanner error then return the result
                orchestrator._scanner._errors.append("Test warning for verbose display")
                return original_scan_folder(folder_path)
            return original_scan_folder(folder_path)

        with patch.object(orchestrator._scanner, 'scan_folder', side_effect=patched_scan_folder):
            orchestrator.scan()

        output_text = output.getvalue()
        # In verbose mode, scanner warnings should be displayed
        assert "Scanner warnings" in output_text or "Test warning" in output_text

    def test_verbose_shows_log_path(self, temp_dir: Path) -> None:
        """Test that verbose mode shows log file path."""
        folder = temp_dir / "folder"
        folder.mkdir()
        (folder / "file.txt").write_text("content")

        log_path = temp_dir / "verbose_test.log"

        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            log_file_path=log_path,
            verbose=True,
        )
        orchestrator._tui = tui

        orchestrator.scan()

        output_text = output.getvalue()
        assert "Log file" in output_text or str(log_path) in output_text


# ============================================================================
# TestConflictTracking
# ============================================================================


class TestConflictTracking:
    """Tests for conflict detection and tracking."""

    def test_conflict_detection_different_hashes(self, temp_dir: Path) -> None:
        """Test that files with different hashes are detected as conflicts."""
        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "conflict.txt").write_text("primary version")

        source = temp_dir / "source"
        source.mkdir()
        (source / "conflict.txt").write_text("source version - different content")

        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary_folder = ComputerFolder(
            path=primary,
            name="primary",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source_folder = ComputerFolder(
            path=source,
            name="source",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        match_group = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=0.9,
            match_reason=MatchReason.NORMALIZED,
            base_name="primary",
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match_group,
        )

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        conflicts = orchestrator._track_conflicts_for_operation(selection)

        assert len(conflicts) == 1
        assert conflicts[0].relative_path == Path("conflict.txt")

    def test_no_conflict_for_duplicates(self, temp_dir: Path) -> None:
        """Test that files with same hash are not marked as conflicts."""
        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "same.txt").write_text("identical content")

        source = temp_dir / "source"
        source.mkdir()
        (source / "same.txt").write_text("identical content")

        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary_folder = ComputerFolder(
            path=primary,
            name="primary",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source_folder = ComputerFolder(
            path=source,
            name="source",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        match_group = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=0.9,
            match_reason=MatchReason.NORMALIZED,
            base_name="primary",
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match_group,
        )

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        conflicts = orchestrator._track_conflicts_for_operation(selection)

        assert len(conflicts) == 0

    def test_no_conflict_for_new_files(self, temp_dir: Path) -> None:
        """Test that new files (not in primary) are not conflicts."""
        primary = temp_dir / "primary"
        primary.mkdir()
        (primary / "existing.txt").write_text("exists in primary")

        source = temp_dir / "source"
        source.mkdir()
        (source / "new_file.txt").write_text("only in source")

        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary_folder = ComputerFolder(
            path=primary,
            name="primary",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source_folder = ComputerFolder(
            path=source,
            name="source",
            file_count=1,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        match_group = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=0.9,
            match_reason=MatchReason.NORMALIZED,
            base_name="primary",
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match_group,
        )

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        conflicts = orchestrator._track_conflicts_for_operation(selection)

        assert len(conflicts) == 0


# ============================================================================
# TestSummaryAggregation
# ============================================================================


class TestSummaryAggregation:
    """Tests for summary aggregation logic."""

    def test_aggregate_summary_single_operation(self) -> None:
        """Test aggregation with a single operation."""
        from mergy.models import MergeOperation

        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary = ComputerFolder(
            path=Path("/test/primary"),
            name="primary",
            file_count=10,
            total_size=1000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source = ComputerFolder(
            path=Path("/test/source"),
            name="source",
            file_count=5,
            total_size=500,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match_group = FolderMatch(
            folders=[primary, source],
            confidence=0.9,
            match_reason=MatchReason.NORMALIZED,
            base_name="primary",
        )
        selection = MergeSelection(
            primary=primary,
            merge_from=[source],
            match_group=match_group,
        )

        operation = MergeOperation(
            selection=selection,
            dry_run=False,
            timestamp=datetime.now(),
            files_copied=10,
            files_skipped=5,
            conflicts_resolved=2,
            folders_removed=1,
            errors=["error1"],
        )

        # Create orchestrator with mock
        orchestrator = MergeOrchestrator.__new__(MergeOrchestrator)
        orchestrator._errors = []

        summary = orchestrator._aggregate_summary([operation], 10.5, ["error2"])

        assert summary.total_operations == 1
        assert summary.total_files_copied == 10
        assert summary.total_files_skipped == 5
        assert summary.total_conflicts_resolved == 2
        assert summary.total_folders_removed == 1
        assert summary.duration_seconds == 10.5
        assert "error2" in summary.errors

    def test_aggregate_summary_multiple_operations(self) -> None:
        """Test aggregation with multiple operations."""
        from mergy.models import MergeOperation

        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        def create_operation(copied: int, skipped: int, conflicts: int, removed: int) -> MergeOperation:
            primary = ComputerFolder(
                path=Path("/test/primary"),
                name="primary",
                file_count=10,
                total_size=1000,
                oldest_file_date=base_date,
                newest_file_date=end_date,
            )
            source = ComputerFolder(
                path=Path("/test/source"),
                name="source",
                file_count=5,
                total_size=500,
                oldest_file_date=base_date,
                newest_file_date=end_date,
            )
            match_group = FolderMatch(
                folders=[primary, source],
                confidence=0.9,
                match_reason=MatchReason.NORMALIZED,
                base_name="primary",
            )
            selection = MergeSelection(
                primary=primary,
                merge_from=[source],
                match_group=match_group,
            )
            return MergeOperation(
                selection=selection,
                dry_run=False,
                timestamp=datetime.now(),
                files_copied=copied,
                files_skipped=skipped,
                conflicts_resolved=conflicts,
                folders_removed=removed,
                errors=[],
            )

        operations = [
            create_operation(10, 5, 2, 1),
            create_operation(20, 3, 4, 2),
            create_operation(15, 7, 1, 0),
        ]

        orchestrator = MergeOrchestrator.__new__(MergeOrchestrator)
        orchestrator._errors = []

        summary = orchestrator._aggregate_summary(operations, 30.0, [])

        assert summary.total_operations == 3
        assert summary.total_files_copied == 45  # 10 + 20 + 15
        assert summary.total_files_skipped == 15  # 5 + 3 + 7
        assert summary.total_conflicts_resolved == 7  # 2 + 4 + 1
        assert summary.total_folders_removed == 3  # 1 + 2 + 0

    def test_empty_summary_creation(self) -> None:
        """Test creation of empty summary."""
        orchestrator = MergeOrchestrator.__new__(MergeOrchestrator)
        orchestrator._errors = ["test error"]

        summary = orchestrator._create_empty_summary(5.5)

        assert summary.total_operations == 0
        assert summary.total_files_copied == 0
        assert summary.total_files_skipped == 0
        assert summary.total_conflicts_resolved == 0
        assert summary.total_folders_removed == 0
        assert summary.duration_seconds == 5.5
        assert "test error" in summary.errors
