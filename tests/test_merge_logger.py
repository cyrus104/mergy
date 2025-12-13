"""Comprehensive unit tests for MergeLogger."""

import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List

import pytest

from mergy.models import (
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)
from mergy.models.match_reason import MatchReason
from mergy.orchestration import MergeLogger


class TestMergeLoggerBasic:
    """Test basic MergeLogger functionality."""

    def test_log_file_creation_with_auto_generated_filename(self, temp_dir: Path):
        """Test that log file is created with auto-generated timestamped filename."""
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            with MergeLogger() as logger:
                log_path = logger.get_log_path()
                assert log_path.parent == temp_dir
                assert log_path.name.startswith("merge_log_")
                assert log_path.name.endswith(".log")
                # Verify timestamp format in filename: YYYY-MM-DD_HH-MM-SS
                pattern = r"merge_log_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2}\.log"
                assert re.match(pattern, log_path.name)
        finally:
            os.chdir(original_cwd)

    def test_custom_log_file_path(self, temp_dir: Path):
        """Test that custom log file path is used correctly."""
        custom_path = temp_dir / "custom_merge.log"
        with MergeLogger(log_file_path=custom_path) as logger:
            assert logger.get_log_path() == custom_path
            logger.log_header()

        assert custom_path.exists()
        content = custom_path.read_text()
        assert "Computer Data Organization Tool" in content

    def test_context_manager_opens_and_closes_file(self, temp_dir: Path):
        """Test that context manager properly opens and closes the file."""
        log_path = temp_dir / "test.log"
        logger = MergeLogger(log_file_path=log_path)

        # Before entering context, file should not exist
        assert not log_path.exists()

        with logger:
            # Inside context, file should exist
            assert log_path.exists()
            logger.log_header()

        # After exiting, should be able to read the file
        content = log_path.read_text()
        assert len(content) > 0

    def test_dry_run_mode_in_header(self, temp_dir: Path):
        """Test that DRY RUN mode is displayed correctly in header."""
        log_path = temp_dir / "dry_run.log"
        with MergeLogger(log_file_path=log_path, dry_run=True) as logger:
            logger.log_header()

        content = log_path.read_text()
        assert "Mode: DRY RUN" in content
        assert "Mode: LIVE MERGE" not in content

    def test_live_merge_mode_in_header(self, temp_dir: Path):
        """Test that LIVE MERGE mode is displayed correctly in header."""
        log_path = temp_dir / "live_merge.log"
        with MergeLogger(log_file_path=log_path, dry_run=False) as logger:
            logger.log_header()

        content = log_path.read_text()
        assert "Mode: LIVE MERGE" in content
        assert "Mode: DRY RUN" not in content


class TestMergeLoggerHeaderSection:
    """Test header section formatting."""

    def test_header_format_matches_specification(self, temp_dir: Path):
        """Test that header format matches AGENTS.md specification exactly."""
        log_path = temp_dir / "header_test.log"
        with MergeLogger(log_file_path=log_path, dry_run=False) as logger:
            logger.log_header()

        content = log_path.read_text()
        lines = content.split("\n")

        # First line should be separator
        assert lines[0] == "=" * 65
        # Second line should be title
        assert lines[1] == "Computer Data Organization Tool - Merge Log"
        # Third line should be separator
        assert lines[2] == "=" * 65
        # Fourth line should be timestamp
        assert lines[3].startswith("Timestamp: ")
        # Fifth line should be mode
        assert lines[4].startswith("Mode: ")
        # Sixth line should be blank
        assert lines[5] == ""

    def test_timestamp_formatting(self, temp_dir: Path):
        """Test that timestamp is in correct YYYY-MM-DD HH:MM:SS format."""
        log_path = temp_dir / "timestamp_test.log"
        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_header()

        content = log_path.read_text()
        # Extract timestamp
        match = re.search(r"Timestamp: (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", content)
        assert match is not None
        timestamp_str = match.group(1)

        # Verify it parses correctly
        parsed = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        assert parsed is not None


class TestMergeLoggerScanPhase:
    """Test scan phase section formatting."""

    def test_scan_phase_section_with_match_groups(
        self, temp_dir: Path, sample_folder_matches: List[FolderMatch]
    ):
        """Test scan phase section with match groups."""
        log_path = temp_dir / "scan_phase.log"
        base_path = Path("/computers")

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_scan_phase(
                base_path=base_path,
                min_confidence=0.7,
                total_folders=50,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )

        content = log_path.read_text()

        # Check section structure
        assert "SCAN PHASE" in content
        assert f"Base Path: {base_path}" in content
        assert "Minimum Confidence Threshold: 70%" in content
        assert "Total folders scanned: 50" in content
        assert f"Match groups found: {len(sample_folder_matches)}" in content
        assert f"Match groups above threshold: {len(sample_folder_matches)}" in content
        # Check that Match Groups: heading is present
        assert "Match Groups:" in content

    def test_confidence_threshold_formatting(self, temp_dir: Path):
        """Test that confidence threshold is formatted as percentage."""
        log_path = temp_dir / "confidence_test.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.85,
                total_folders=10,
                match_groups=[],
                threshold_filtered_count=0,
            )

        content = log_path.read_text()
        assert "Minimum Confidence Threshold: 85%" in content

    def test_match_group_formatting_with_folder_names(
        self, temp_dir: Path, sample_folder_matches: List[FolderMatch]
    ):
        """Test that match groups are formatted with folder names."""
        log_path = temp_dir / "match_groups.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.7,
                total_folders=20,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )

        content = log_path.read_text()

        # Check that Match Groups: heading is present
        assert "Match Groups:" in content

        # Check group formatting
        assert "Group 1:" in content

        # Check folder names are listed with indentation
        for match_group in sample_folder_matches:
            for folder in match_group.folders:
                assert f"- {folder.name}" in content

    def test_empty_match_groups_list(self, temp_dir: Path):
        """Test scan phase with no match groups."""
        log_path = temp_dir / "empty_groups.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.7,
                total_folders=5,
                match_groups=[],
                threshold_filtered_count=0,
            )

        content = log_path.read_text()
        assert "Match groups found: 0" in content
        assert "Match groups above threshold: 0" in content
        # Match Groups: heading should NOT be present when there are no groups
        assert "Match Groups:" not in content


class TestMergeLoggerMergePhase:
    """Test merge phase section formatting."""

    def test_merge_selection_logging(
        self, temp_dir: Path, sample_merge_selection: MergeSelection
    ):
        """Test merge selection logging with primary and source folders."""
        log_path = temp_dir / "merge_selection.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_selection)

        content = log_path.read_text()

        # Check merge phase header is written
        assert "MERGE PHASE" in content
        # Selection header should not have confidence/match_reason embedded
        assert "Selection 1:" in content
        # Verify no extra formatting in Selection header (no parentheses with %)
        lines = content.split("\n")
        selection_lines = [l for l in lines if l.strip().startswith("Selection 1:")]
        assert len(selection_lines) == 1
        assert "(" not in selection_lines[0]  # No parentheses in Selection header
        # Confidence should be on its own indented line directly under Selection
        confidence_pct = int(sample_merge_selection.match_group.confidence * 100)
        assert f"Confidence: {confidence_pct}%" in content
        assert f"Primary: {sample_merge_selection.primary.name}" in content
        assert "Merging from:" in content

        for folder in sample_merge_selection.merge_from:
            assert f"- {folder.name}" in content

    def test_merge_operation_logging_with_statistics(
        self, temp_dir: Path, sample_merge_operation: MergeOperation
    ):
        """Test merge operation logging with statistics."""
        log_path = temp_dir / "merge_operation.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_operation.selection)
            logger.log_merge_operation(sample_merge_operation)

        content = log_path.read_text()

        # Check operation details
        assert "Starting merge into:" in content
        assert "Files copied:" in content
        assert "Files skipped (duplicates):" in content
        assert "Conflicts resolved:" in content
        assert "Empty folders removed:" in content
        assert "Completed merge" in content

    def test_conflict_detail_formatting(
        self,
        temp_dir: Path,
        sample_merge_operation: MergeOperation,
        sample_file_conflicts: List[FileConflict],
    ):
        """Test conflict detail formatting with hash suffixes.

        Verifies that logged .merged paths follow the same naming convention
        as verify_merged_file_format() in conftest.py: base_hash16.ext
        """
        log_path = temp_dir / "conflicts.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_operation.selection)
            logger.log_merge_operation(sample_merge_operation, conflicts=sample_file_conflicts)

        content = log_path.read_text()

        # Check conflict formatting with proper .merged path convention
        for conflict in sample_file_conflicts:
            assert f"! Conflict: {conflict.relative_path}" in content
            assert "kept newer" in content

            # Verify .merged/ path follows the naming convention: base_hash16chars.ext
            original_name = conflict.relative_path.name
            # Determine which hash was used for the moved file (older file's hash)
            if conflict.primary_ctime >= conflict.conflict_ctime:
                moved_hash = conflict.conflict_hash[:16]
            else:
                moved_hash = conflict.primary_hash[:16]

            # Build expected merged filename following verify_merged_file_format() convention
            if "." in original_name:
                name_part, ext = original_name.rsplit(".", 1)
                expected_merged_filename = f"{name_part}_{moved_hash}.{ext}"
            else:
                expected_merged_filename = f"{original_name}_{moved_hash}"

            # The .merged directory should be at the same level as the conflict
            merged_dir = conflict.relative_path.parent / ".merged"
            expected_path = f"{merged_dir}/{expected_merged_filename}"
            assert expected_path in content

    def test_multiple_merge_operations_in_sequence(
        self, temp_dir: Path, sample_merge_selection: MergeSelection
    ):
        """Test multiple merge operations are logged correctly."""
        log_path = temp_dir / "multiple_ops.log"

        operation1 = MergeOperation(
            selection=sample_merge_selection,
            dry_run=False,
            timestamp=datetime.now(),
            files_copied=10,
            files_skipped=2,
            conflicts_resolved=1,
            folders_removed=1,
            errors=[],
        )

        # Create a second selection
        base_date = datetime(2020, 1, 1)
        second_primary = ComputerFolder(
            path=Path("/test/folder3"),
            name="folder3",
            file_count=30,
            total_size=3000,
            oldest_file_date=base_date,
            newest_file_date=datetime.now(),
        )
        second_source = ComputerFolder(
            path=Path("/test/folder4"),
            name="folder4",
            file_count=25,
            total_size=2500,
            oldest_file_date=base_date,
            newest_file_date=datetime.now(),
        )
        second_match = FolderMatch(
            folders=[second_primary, second_source],
            confidence=0.85,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="folder",
        )
        second_selection = MergeSelection(
            primary=second_primary,
            merge_from=[second_source],
            match_group=second_match,
        )
        operation2 = MergeOperation(
            selection=second_selection,
            dry_run=False,
            timestamp=datetime.now(),
            files_copied=15,
            files_skipped=3,
            conflicts_resolved=0,
            folders_removed=1,
            errors=[],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_selection)
            logger.log_merge_operation(operation1)
            logger.log_merge_selection(second_selection)
            logger.log_merge_operation(operation2)

        content = log_path.read_text()

        # Both selections should be numbered
        assert "Selection 1:" in content
        assert "Selection 2:" in content

    def test_timestamped_start_completion_lines(
        self, temp_dir: Path, sample_merge_operation: MergeOperation
    ):
        """Test that start and completion lines have timestamps."""
        log_path = temp_dir / "timestamps.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_operation.selection)
            logger.log_merge_operation(sample_merge_operation)

        content = log_path.read_text()

        # Check timestamp format in start and completion lines
        timestamp_pattern = r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]"
        assert re.search(f"{timestamp_pattern} Starting merge into:", content)
        assert re.search(f"{timestamp_pattern} Completed merge", content)


class TestMergeLoggerSummary:
    """Test summary section formatting."""

    def test_summary_section_with_aggregated_statistics(
        self, temp_dir: Path, sample_merge_summary: MergeSummary
    ):
        """Test summary section with aggregated statistics."""
        log_path = temp_dir / "summary.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(sample_merge_summary)

        content = log_path.read_text()

        assert "SUMMARY" in content
        # Check exact label text to enforce alignment with AGENTS.md §7.1
        assert f"Total merge operations: {sample_merge_summary.total_operations}" in content
        assert f"Files copied: {sample_merge_summary.total_files_copied:,}" in content
        assert f"Files skipped (duplicates): {sample_merge_summary.total_files_skipped:,}" in content
        assert f"Conflicts resolved: {sample_merge_summary.total_conflicts_resolved}" in content
        assert f"Empty folders removed: {sample_merge_summary.total_folders_removed}" in content
        assert "Duration:" in content
        assert "Log file:" in content

    def test_duration_formatting_seconds(self, temp_dir: Path):
        """Test duration formatting for durations under 60 seconds."""
        log_path = temp_dir / "duration_seconds.log"
        summary = MergeSummary(
            total_operations=1,
            total_files_copied=10,
            total_files_skipped=2,
            total_conflicts_resolved=1,
            total_folders_removed=1,
            duration_seconds=45.7,
            errors=[],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(summary)

        content = log_path.read_text()
        assert "Duration: 45s" in content

    def test_duration_formatting_minutes(self, temp_dir: Path):
        """Test duration formatting for minutes."""
        log_path = temp_dir / "duration_minutes.log"
        summary = MergeSummary(
            total_operations=1,
            total_files_copied=10,
            total_files_skipped=2,
            total_conflicts_resolved=1,
            total_folders_removed=1,
            duration_seconds=323.0,  # 5m 23s
            errors=[],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(summary)

        content = log_path.read_text()
        assert "Duration: 5m 23s" in content

    def test_duration_formatting_hours(self, temp_dir: Path):
        """Test duration formatting for hours."""
        log_path = temp_dir / "duration_hours.log"
        summary = MergeSummary(
            total_operations=1,
            total_files_copied=10,
            total_files_skipped=2,
            total_conflicts_resolved=1,
            total_folders_removed=1,
            duration_seconds=3930.0,  # 1h 5m 30s
            errors=[],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(summary)

        content = log_path.read_text()
        assert "Duration: 1h 5m 30s" in content

    def test_log_file_path_in_summary(self, temp_dir: Path, sample_merge_summary: MergeSummary):
        """Test that log file path is included in summary."""
        log_path = temp_dir / "path_test.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(sample_merge_summary)

        content = log_path.read_text()
        assert f"Log file: {log_path}" in content


class TestMergeLoggerFormatting:
    """Test formatting consistency."""

    def test_separator_line_length(self, temp_dir: Path):
        """Test that separator lines are exactly 65 characters."""
        log_path = temp_dir / "separator.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_header()

        content = log_path.read_text()
        lines = content.split("\n")

        # Check separator lines
        separator_lines = [line for line in lines if line and all(c == "=" for c in line)]
        for sep in separator_lines:
            assert len(sep) == 65

    def test_indentation_consistency(
        self, temp_dir: Path, sample_folder_matches: List[FolderMatch]
    ):
        """Test that indentation uses consistent spacing."""
        log_path = temp_dir / "indentation.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.7,
                total_folders=20,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )

        content = log_path.read_text()
        lines = content.split("\n")

        # Find indented lines (folder names in groups)
        for line in lines:
            if line.startswith("  - "):
                # 2-space indent for folder names
                assert line.startswith("  ")

    def test_blank_line_placement_between_sections(
        self, temp_dir: Path, sample_merge_summary: MergeSummary
    ):
        """Test that blank lines are placed correctly between sections."""
        log_path = temp_dir / "blank_lines.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_header()
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.7,
                total_folders=10,
                match_groups=[],
                threshold_filtered_count=0,
            )
            logger.log_summary(sample_merge_summary)

        content = log_path.read_text()

        # After header (after Mode line), there should be a blank line
        assert "Mode: LIVE MERGE\n\n" in content or "Mode: DRY RUN\n\n" in content

    def test_conflict_detail_indentation_and_prefix(
        self,
        temp_dir: Path,
        sample_merge_operation: MergeOperation,
        sample_file_conflicts: List[FileConflict],
    ):
        """Test conflict details have proper indentation and ! prefix."""
        log_path = temp_dir / "conflict_format.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_operation.selection)
            logger.log_merge_operation(sample_merge_operation, conflicts=sample_file_conflicts)

        content = log_path.read_text()
        lines = content.split("\n")

        # Find conflict lines
        conflict_lines = [line for line in lines if "! Conflict:" in line]
        for line in conflict_lines:
            # Should have 4-space indentation and ! prefix
            assert line.startswith("    ! Conflict:")


class TestMergeLoggerIntegration:
    """Integration tests for complete workflows."""

    def test_complete_scan_only_workflow(
        self, temp_dir: Path, sample_folder_matches: List[FolderMatch]
    ):
        """Test complete scan-only workflow (header + scan + summary)."""
        log_path = temp_dir / "scan_only.log"
        summary = MergeSummary(
            total_operations=0,
            total_files_copied=0,
            total_files_skipped=0,
            total_conflicts_resolved=0,
            total_folders_removed=0,
            duration_seconds=5.2,
            errors=[],
        )

        with MergeLogger(log_file_path=log_path, dry_run=True) as logger:
            logger.log_header()
            logger.log_scan_phase(
                base_path=Path("/computers"),
                min_confidence=0.7,
                total_folders=100,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )
            logger.log_summary(summary)

        content = log_path.read_text()

        # Verify section order
        header_pos = content.find("Computer Data Organization Tool")
        scan_pos = content.find("SCAN PHASE")
        summary_pos = content.find("SUMMARY")

        assert header_pos < scan_pos < summary_pos

    def test_complete_merge_workflow(
        self,
        temp_dir: Path,
        sample_folder_matches: List[FolderMatch],
        sample_merge_selection: MergeSelection,
        sample_merge_operation: MergeOperation,
        sample_merge_summary: MergeSummary,
    ):
        """Test complete merge workflow (all sections)."""
        log_path = temp_dir / "full_merge.log"

        with MergeLogger(log_file_path=log_path, dry_run=False) as logger:
            logger.log_header()
            logger.log_scan_phase(
                base_path=Path("/computers"),
                min_confidence=0.7,
                total_folders=50,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )
            logger.log_merge_selection(sample_merge_selection)
            logger.log_merge_operation(sample_merge_operation)
            logger.log_summary(sample_merge_summary)

        content = log_path.read_text()

        # Verify all sections present in order
        header_pos = content.find("Computer Data Organization Tool")
        scan_pos = content.find("SCAN PHASE")
        merge_pos = content.find("MERGE PHASE")
        summary_pos = content.find("SUMMARY")

        assert header_pos < scan_pos < merge_pos < summary_pos

    def test_multiple_selections_and_operations(
        self, temp_dir: Path, sample_merge_selection: MergeSelection
    ):
        """Test multiple selections and operations in sequence."""
        log_path = temp_dir / "multiple_all.log"

        base_date = datetime(2020, 1, 1)

        # Create multiple operations
        operations = []
        for i in range(3):
            folder_primary = ComputerFolder(
                path=Path(f"/test/primary{i}"),
                name=f"primary{i}",
                file_count=20 + i * 10,
                total_size=2000 + i * 1000,
                oldest_file_date=base_date,
                newest_file_date=datetime.now(),
            )
            folder_source = ComputerFolder(
                path=Path(f"/test/source{i}"),
                name=f"source{i}",
                file_count=15 + i * 5,
                total_size=1500 + i * 500,
                oldest_file_date=base_date,
                newest_file_date=datetime.now(),
            )
            match = FolderMatch(
                folders=[folder_primary, folder_source],
                confidence=0.8 + i * 0.05,
                match_reason=MatchReason.EXACT_PREFIX,
                base_name=f"folder{i}",
            )
            selection = MergeSelection(
                primary=folder_primary,
                merge_from=[folder_source],
                match_group=match,
            )
            operation = MergeOperation(
                selection=selection,
                dry_run=False,
                timestamp=datetime.now(),
                files_copied=10 + i * 5,
                files_skipped=2 + i,
                conflicts_resolved=i,
                folders_removed=1,
                errors=[],
            )
            operations.append((selection, operation))

        summary = MergeSummary(
            total_operations=3,
            total_files_copied=45,
            total_files_skipped=9,
            total_conflicts_resolved=3,
            total_folders_removed=3,
            duration_seconds=120.5,
            errors=[],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_header()
            logger.log_scan_phase(
                base_path=Path("/test"),
                min_confidence=0.7,
                total_folders=30,
                match_groups=[],
                threshold_filtered_count=0,
            )
            for selection, operation in operations:
                logger.log_merge_selection(selection)
                logger.log_merge_operation(operation)
            logger.log_summary(summary)

        content = log_path.read_text()

        # Verify all selections numbered correctly
        assert "Selection 1:" in content
        assert "Selection 2:" in content
        assert "Selection 3:" in content


class TestMergeLoggerErrors:
    """Test error handling scenarios."""

    def test_invalid_log_file_path_permission_denied(self, temp_dir: Path):
        """Test that invalid log file path raises appropriate error."""
        # Try to create log in non-existent directory
        invalid_path = temp_dir / "nonexistent" / "subdir" / "test.log"

        with pytest.raises(OSError) as exc_info:
            MergeLogger(log_file_path=invalid_path)

        assert "Parent directory does not exist" in str(exc_info.value)

    def test_context_manager_cleanup_on_exception(self, temp_dir: Path):
        """Test that context manager closes file even on exception."""
        log_path = temp_dir / "cleanup_test.log"

        try:
            with MergeLogger(log_file_path=log_path) as logger:
                logger.log_header()
                raise ValueError("Test exception")
        except ValueError:
            pass

        # File should be closed and readable
        content = log_path.read_text()
        assert "Computer Data Organization Tool" in content

    def test_get_log_path_returns_correct_path(self, temp_dir: Path):
        """Test that get_log_path returns the correct path."""
        custom_path = temp_dir / "get_path_test.log"
        logger = MergeLogger(log_file_path=custom_path)
        assert logger.get_log_path() == custom_path


class TestMergeLoggerErrorTracking:
    """Test error tracking and logging in MergeLogger."""

    def test_merge_operation_with_errors(
        self, temp_dir: Path, sample_merge_selection: MergeSelection
    ):
        """Test that errors in MergeOperation are logged."""
        log_path = temp_dir / "operation_errors.log"

        operation_with_errors = MergeOperation(
            selection=sample_merge_selection,
            dry_run=False,
            timestamp=datetime.now(),
            files_copied=10,
            files_skipped=2,
            conflicts_resolved=1,
            folders_removed=0,
            errors=[
                "Permission denied: /path/to/file.txt",
                "File not found: /another/path/missing.txt",
            ],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_selection)
            logger.log_merge_operation(operation_with_errors)

        content = log_path.read_text()

        # Check that errors section is present
        assert "Errors:" in content
        assert "Permission denied: /path/to/file.txt" in content
        assert "File not found: /another/path/missing.txt" in content

    def test_merge_operation_without_errors(
        self, temp_dir: Path, sample_merge_operation: MergeOperation
    ):
        """Test that no Errors section appears when errors list is empty."""
        log_path = temp_dir / "no_errors.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_merge_selection(sample_merge_operation.selection)
            logger.log_merge_operation(sample_merge_operation)

        content = log_path.read_text()

        # Should not have an Errors: section in the merge operation output
        # (only looking for the errors subsection pattern, not the class name)
        lines = content.split("\n")
        errors_lines = [l for l in lines if l.strip() == "Errors:"]
        assert len(errors_lines) == 0

    def test_merge_summary_with_errors(self, temp_dir: Path):
        """Test that errors in MergeSummary are logged with count and list."""
        log_path = temp_dir / "summary_errors.log"

        summary_with_errors = MergeSummary(
            total_operations=3,
            total_files_copied=50,
            total_files_skipped=10,
            total_conflicts_resolved=5,
            total_folders_removed=2,
            duration_seconds=120.0,
            errors=[
                "Failed to remove empty folder: /path/folder1",
                "Hash calculation failed: /path/corrupted.bin",
                "Disk full during copy: /path/large_file.zip",
            ],
        )

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(summary_with_errors)

        content = log_path.read_text()

        # Check error count and list are present
        assert "Total errors: 3" in content
        assert "Errors:" in content
        assert "Failed to remove empty folder: /path/folder1" in content
        assert "Hash calculation failed: /path/corrupted.bin" in content
        assert "Disk full during copy: /path/large_file.zip" in content

    def test_merge_summary_without_errors(
        self, temp_dir: Path, sample_merge_summary: MergeSummary
    ):
        """Test that no error section appears when errors list is empty."""
        log_path = temp_dir / "summary_no_errors.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_summary(sample_merge_summary)

        content = log_path.read_text()

        # Should not have Total errors line
        assert "Total errors:" not in content


class TestVerifyLogFormat:
    """Test helper for verifying log format compliance."""

    def verify_log_format(self, log_path: Path) -> dict:
        """Verify log format compliance and return analysis.

        Args:
            log_path: Path to the log file to verify.

        Returns:
            Dictionary with verification results.
        """
        content = log_path.read_text()
        lines = content.split("\n")

        results = {
            "separator_lines_correct": True,
            "timestamp_formats_valid": True,
            "section_order_valid": True,
            "indentation_consistent": True,
        }

        # Check separator lines are 65 characters
        for line in lines:
            if line and all(c == "=" for c in line):
                if len(line) != 65:
                    results["separator_lines_correct"] = False
                    break

        # Check timestamp formats
        timestamp_pattern = r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"
        timestamps = re.findall(timestamp_pattern, content)
        for ts in timestamps:
            try:
                datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                results["timestamp_formats_valid"] = False
                break

        return results

    def test_format_verification_on_complete_log(
        self,
        temp_dir: Path,
        sample_folder_matches: List[FolderMatch],
        sample_merge_selection: MergeSelection,
        sample_merge_operation: MergeOperation,
        sample_merge_summary: MergeSummary,
    ):
        """Test format verification on a complete log file."""
        log_path = temp_dir / "verification_test.log"

        with MergeLogger(log_file_path=log_path) as logger:
            logger.log_header()
            logger.log_scan_phase(
                base_path=Path("/computers"),
                min_confidence=0.7,
                total_folders=50,
                match_groups=sample_folder_matches,
                threshold_filtered_count=len(sample_folder_matches),
            )
            logger.log_merge_selection(sample_merge_selection)
            logger.log_merge_operation(sample_merge_operation)
            logger.log_summary(sample_merge_summary)

        results = self.verify_log_format(log_path)

        assert results["separator_lines_correct"]
        assert results["timestamp_formats_valid"]
        assert results["indentation_consistent"]
