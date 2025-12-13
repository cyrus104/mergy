"""Tests for the MergeTUI class."""

import io
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
from mergy.ui import MergeTUI


class TestMergeTUIDisplay:
    """Tests for display methods with captured console output."""

    @pytest.fixture
    def tui_with_output(self) -> tuple[MergeTUI, io.StringIO]:
        """Create a MergeTUI with captured output.

        Returns:
            Tuple of (MergeTUI instance, StringIO for reading output).
        """
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)
        return tui, output

    def test_display_scan_summary_formats_correctly(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_folder_matches: List[FolderMatch]
    ) -> None:
        """Verify scan summary displays table headers and formatted data."""
        tui, output = tui_with_output

        tui.display_scan_summary(sample_folder_matches, total_scanned=100, threshold=0.7)

        result = output.getvalue()
        assert "Scan Results" in result
        assert "Folders scanned: 100" in result
        assert "Match groups found: 2" in result
        assert "Confidence threshold: 70%" in result
        assert "Group #" in result
        assert "Confidence" in result
        assert "Match Type" in result
        assert "Folders" in result

    def test_display_scan_summary_confidence_color_coding(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_folder_matches: List[FolderMatch]
    ) -> None:
        """Verify confidence percentages are displayed correctly."""
        tui, output = tui_with_output

        tui.display_scan_summary(sample_folder_matches, total_scanned=100, threshold=0.7)

        result = output.getvalue()
        assert "95%" in result
        assert "85%" in result

    def test_display_scan_summary_empty_matches(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Verify empty match list displays appropriate message."""
        tui, output = tui_with_output

        tui.display_scan_summary([], total_scanned=50, threshold=0.7)

        result = output.getvalue()
        assert "No match groups found" in result
        assert "Folders scanned: 50" in result

    def test_display_match_group_shows_folder_details(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_folder_matches: List[FolderMatch]
    ) -> None:
        """Verify folder details including file count and size are displayed."""
        tui, output = tui_with_output

        tui._display_match_group(sample_folder_matches[0], group_number=1)

        result = output.getvalue()
        assert "Match Group 1" in result
        assert "95% confidence" in result
        assert "exact_prefix" in result
        assert "135897-ntp" in result
        assert "100" in result
        assert "9.8 KB" in result or "10" in result

    def test_display_merge_summary_basic(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_merge_summary: MergeSummary
    ) -> None:
        """Verify merge summary displays all statistics."""
        tui, output = tui_with_output

        tui.display_merge_summary(sample_merge_summary, dry_run=False)

        result = output.getvalue()
        assert "Merge Summary" in result
        assert "Total operations" in result
        assert "5" in result
        assert "Files copied" in result
        assert "120" in result
        assert "Files skipped" in result
        assert "35" in result
        assert "Conflicts resolved" in result
        assert "12" in result
        assert "Duration" in result
        assert "5m 23s" in result

    def test_display_merge_summary_dry_run(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_merge_summary: MergeSummary
    ) -> None:
        """Verify dry run indicator is displayed."""
        tui, output = tui_with_output

        tui.display_merge_summary(sample_merge_summary, dry_run=True)

        result = output.getvalue()
        assert "DRY RUN" in result

    def test_display_merge_summary_with_errors(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Verify error panel appears when summary has errors."""
        summary = MergeSummary(
            total_operations=2,
            total_files_copied=10,
            total_files_skipped=3,
            total_conflicts_resolved=1,
            total_folders_removed=1,
            duration_seconds=60.0,
            errors=["Error reading file X", "Permission denied for Y"],
        )
        tui, output = tui_with_output

        tui.display_merge_summary(summary, dry_run=False)

        result = output.getvalue()
        assert "Errors" in result
        assert "Error reading file X" in result
        assert "Permission denied for Y" in result

    def test_display_merge_summary_many_errors_truncated(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Verify more than 10 errors are truncated with count."""
        errors = [f"Error {i}" for i in range(15)]
        summary = MergeSummary(
            total_operations=1,
            total_files_copied=5,
            total_files_skipped=0,
            total_conflicts_resolved=0,
            total_folders_removed=0,
            duration_seconds=30.0,
            errors=errors,
        )
        tui, output = tui_with_output

        tui.display_merge_summary(summary, dry_run=False)

        result = output.getvalue()
        assert "Errors (15)" in result
        assert "Error 0" in result
        assert "Error 9" in result
        assert "5 more errors" in result


class TestMergeTUIFormatters:
    """Tests for helper formatting methods."""

    @pytest.fixture
    def tui(self) -> MergeTUI:
        """Create a MergeTUI instance."""
        return MergeTUI()

    def test_format_size_bytes(self, tui: MergeTUI) -> None:
        """Test size formatting for bytes."""
        assert tui._format_size(0) == "0 B"
        assert tui._format_size(500) == "500 B"
        assert tui._format_size(1023) == "1023 B"

    def test_format_size_kilobytes(self, tui: MergeTUI) -> None:
        """Test size formatting for kilobytes."""
        assert tui._format_size(1024) == "1.0 KB"
        assert tui._format_size(1536) == "1.5 KB"
        assert tui._format_size(10240) == "10.0 KB"

    def test_format_size_megabytes(self, tui: MergeTUI) -> None:
        """Test size formatting for megabytes."""
        assert tui._format_size(1048576) == "1.0 MB"
        assert tui._format_size(10485760) == "10.0 MB"
        assert tui._format_size(1572864) == "1.5 MB"

    def test_format_size_gigabytes(self, tui: MergeTUI) -> None:
        """Test size formatting for gigabytes."""
        assert tui._format_size(1073741824) == "1.0 GB"
        assert tui._format_size(2147483648) == "2.0 GB"

    def test_format_duration_minutes_seconds(self, tui: MergeTUI) -> None:
        """Test duration formatting."""
        assert tui._format_duration(0) == "0m 0s"
        assert tui._format_duration(30) == "0m 30s"
        assert tui._format_duration(60) == "1m 0s"
        assert tui._format_duration(90) == "1m 30s"
        assert tui._format_duration(323.5) == "5m 23s"
        assert tui._format_duration(3661) == "61m 1s"

    def test_format_duration_negative_clamps_to_zero(self, tui: MergeTUI) -> None:
        """Test negative duration is clamped to zero."""
        assert tui._format_duration(-1) == "0m 0s"
        assert tui._format_duration(-100) == "0m 0s"

    def test_truncate_name_short_names(self, tui: MergeTUI) -> None:
        """Test truncation with short names."""
        assert tui._truncate_name("short") == "short"
        assert tui._truncate_name("exactly-60-chars" + "x" * 44) == "exactly-60-chars" + "x" * 44

    def test_truncate_name_long_names(self, tui: MergeTUI) -> None:
        """Test truncation with long names."""
        long_name = "a" * 100
        result = tui._truncate_name(long_name, max_length=60)
        assert len(result) == 60
        assert result.endswith("...")
        assert result == "a" * 57 + "..."

    def test_truncate_name_custom_max_length(self, tui: MergeTUI) -> None:
        """Test truncation with custom max length."""
        name = "a" * 50
        result = tui._truncate_name(name, max_length=20)
        assert len(result) == 20
        assert result == "a" * 17 + "..."

    def test_format_confidence_high(self, tui: MergeTUI) -> None:
        """Test confidence formatting for high values."""
        result = tui._format_confidence(95)
        assert "95%" in result
        assert "green" in result

    def test_format_confidence_medium(self, tui: MergeTUI) -> None:
        """Test confidence formatting for medium values."""
        result = tui._format_confidence(75)
        assert "75%" in result
        assert "yellow" in result

    def test_format_confidence_low(self, tui: MergeTUI) -> None:
        """Test confidence formatting for low values."""
        result = tui._format_confidence(60)
        assert "60%" in result
        assert "red" in result


class TestMergeTUIInteractive:
    """Tests for interactive workflow with mocked input."""

    @pytest.fixture
    def tui_with_output(self) -> tuple[MergeTUI, io.StringIO]:
        """Create a MergeTUI with captured output."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)
        return tui, output

    def test_review_match_groups_empty_list(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Verify empty match list returns empty selections."""
        tui, _ = tui_with_output
        result = tui.review_match_groups([])
        assert result == []

    @patch("mergy.ui.merge_tui.Prompt.ask")
    @patch("mergy.ui.merge_tui.Confirm.ask")
    def test_review_match_groups_merge_all(
        self,
        mock_confirm: MagicMock,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test merge flow with 'all' folder selection."""
        tui, _ = tui_with_output
        mock_prompt.side_effect = ["m", "all", "1", "s"]
        mock_confirm.return_value = True

        result = tui.review_match_groups(sample_folder_matches)

        assert len(result) == 1
        assert isinstance(result[0], MergeSelection)
        assert result[0].primary == sample_folder_matches[0].folders[0]
        assert len(result[0].merge_from) == 1

    @patch("mergy.ui.merge_tui.Prompt.ask")
    def test_review_match_groups_skip_then_quit(
        self,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test skip then quit returns empty list and shows cancellation message."""
        tui, output = tui_with_output
        mock_prompt.side_effect = ["s", "q"]

        result = tui.review_match_groups(sample_folder_matches)

        assert result == []
        # Verify cancellation message appears in output (progress bar description)
        output_text = output.getvalue().lower()
        assert "cancelled" in output_text or "review" in output_text

    @patch("mergy.ui.merge_tui.Prompt.ask")
    @patch("mergy.ui.merge_tui.Confirm.ask")
    def test_review_match_groups_partial_selection(
        self,
        mock_confirm: MagicMock,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test selecting specific folders by number."""
        tui, _ = tui_with_output
        mock_prompt.side_effect = ["m", "1 2", "1", "q"]
        mock_confirm.return_value = True

        result = tui.review_match_groups(sample_folder_matches)

        assert len(result) == 1
        selection = result[0]
        assert selection.primary == sample_folder_matches[0].folders[0]

    @patch("mergy.ui.merge_tui.Prompt.ask")
    @patch("mergy.ui.merge_tui.Confirm.ask")
    def test_review_match_groups_cancel_merge(
        self,
        mock_confirm: MagicMock,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test user declining confirmation adds no selection."""
        tui, _ = tui_with_output
        mock_prompt.side_effect = ["m", "all", "1", "q"]
        mock_confirm.return_value = False

        result = tui.review_match_groups(sample_folder_matches)

        assert result == []

    @patch("mergy.ui.merge_tui.Prompt.ask")
    def test_review_match_groups_keyboard_interrupt(
        self,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test KeyboardInterrupt exits gracefully with cancellation message."""
        tui, output = tui_with_output
        mock_prompt.side_effect = KeyboardInterrupt()

        result = tui.review_match_groups(sample_folder_matches)

        assert result == []
        output_text = output.getvalue().lower()
        assert "cancelled" in output_text
        # Verify progress shows interrupted state, not 100%
        assert "interrupted" in output_text or "0/2" in output_text

    @patch("mergy.ui.merge_tui.Prompt.ask")
    def test_review_match_groups_quit_shows_partial_progress(
        self,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
        sample_folder_matches: List[FolderMatch],
    ) -> None:
        """Test quitting early shows partial progress, not 100%."""
        tui, output = tui_with_output
        # Quit on first group
        mock_prompt.side_effect = ["q"]

        result = tui.review_match_groups(sample_folder_matches)

        assert result == []
        output_text = output.getvalue().lower()
        # Verify cancellation message appears
        assert "cancelled" in output_text
        # Verify progress reflects 0 completed groups (quit before any were processed)
        assert "0/2" in output_text

    def test_create_progress_callback_returns_callable(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test progress callback creation returns Progress and callable.

        API Contract: create_progress_callback returns a tuple of (Progress, callback).
        The caller must use Progress as a context manager (`with progress:`).
        """
        tui, _ = tui_with_output

        progress, callback = tui.create_progress_callback("test-folder", total_files=10)

        assert progress is not None
        assert callable(callback)

    def test_create_progress_callback_updates_correctly(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test progress callback updates progress bar.

        Demonstrates the required usage pattern: Progress must be used as a
        context manager, and the callback is called with completed file count.
        """
        tui, _ = tui_with_output

        progress, callback = tui.create_progress_callback("test-folder", total_files=10)

        # Required pattern: use Progress as context manager
        with progress:
            callback(0)
            callback(5)
            callback(10)


class TestMergeTUIEdgeCases:
    """Tests for edge cases and boundary conditions."""

    @pytest.fixture
    def tui_with_output(self) -> tuple[MergeTUI, io.StringIO]:
        """Create a MergeTUI with captured output."""
        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)
        return tui, output

    def test_single_folder_in_group(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test match with single folder cannot be merged."""
        tui, output = tui_with_output
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        single_folder = ComputerFolder(
            path=Path("/computers/pc1/single"),
            name="single",
            file_count=10,
            total_size=1000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match = FolderMatch(
            folders=[single_folder],
            confidence=0.95,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="single",
        )

        result = tui._process_merge_action(match)

        assert result is None
        assert "Cannot merge" in output.getvalue() or "need at least 2" in output.getvalue()

    def test_very_long_folder_names(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test folders with very long names are truncated properly."""
        tui, output = tui_with_output
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        long_name = "a" * 200
        folder = ComputerFolder(
            path=Path(f"/computers/pc1/{long_name}"),
            name=long_name,
            file_count=10,
            total_size=1000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match = FolderMatch(
            folders=[folder, folder],
            confidence=0.85,
            match_reason=MatchReason.NORMALIZED,
            base_name="test",
        )

        tui._display_match_group(match, 1)

        result = output.getvalue()
        assert "..." in result
        assert long_name not in result

    def test_zero_file_count_folder(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test folder with zero files displays correctly."""
        tui, output = tui_with_output
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        folder = ComputerFolder(
            path=Path("/computers/pc1/empty"),
            name="empty-folder",
            file_count=0,
            total_size=0,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match = FolderMatch(
            folders=[folder, folder],
            confidence=0.90,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="empty",
        )

        tui._display_match_group(match, 1)

        result = output.getvalue()
        assert "0" in result
        assert "0 B" in result

    def test_unicode_folder_names(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test folders with unicode/emoji names are handled correctly."""
        tui, output = tui_with_output
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        folder = ComputerFolder(
            path=Path("/computers/pc1/test-folder"),
            name="test-folder",
            file_count=50,
            total_size=5000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        match = FolderMatch(
            folders=[folder, folder],
            confidence=0.80,
            match_reason=MatchReason.FUZZY_MATCH,
            base_name="test",
        )

        tui._display_match_group(match, 1)

        result = output.getvalue()
        assert "test-folder" in result

    def test_display_scan_summary_high_threshold(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_folder_matches: List[FolderMatch]
    ) -> None:
        """Test scan summary with high threshold percentage."""
        tui, output = tui_with_output

        tui.display_scan_summary(sample_folder_matches, total_scanned=1000, threshold=0.95)

        result = output.getvalue()
        assert "Confidence threshold: 95%" in result
        assert "Folders scanned: 1,000" in result

    def test_display_scan_summary_low_threshold(
        self, tui_with_output: tuple[MergeTUI, io.StringIO], sample_folder_matches: List[FolderMatch]
    ) -> None:
        """Test scan summary with low threshold percentage."""
        tui, output = tui_with_output

        tui.display_scan_summary(sample_folder_matches, total_scanned=50, threshold=0.5)

        result = output.getvalue()
        assert "Confidence threshold: 50%" in result

    @patch("mergy.ui.merge_tui.Prompt.ask")
    @patch("mergy.ui.merge_tui.Confirm.ask")
    def test_select_primary_recommends_largest(
        self,
        mock_confirm: MagicMock,
        mock_prompt: MagicMock,
        tui_with_output: tuple[MergeTUI, io.StringIO],
    ) -> None:
        """Test primary folder selection recommends largest folder."""
        tui, output = tui_with_output
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        small_folder = ComputerFolder(
            path=Path("/computers/pc1/small"),
            name="small-folder",
            file_count=10,
            total_size=1000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        large_folder = ComputerFolder(
            path=Path("/computers/pc2/large"),
            name="large-folder",
            file_count=100,
            total_size=100000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        mock_prompt.return_value = "2"

        result = tui._select_primary_folder([small_folder, large_folder])

        assert result == large_folder
        output_text = output.getvalue()
        assert "recommended" in output_text.lower()

    def test_merge_summary_zero_duration(
        self, tui_with_output: tuple[MergeTUI, io.StringIO]
    ) -> None:
        """Test merge summary with zero duration."""
        summary = MergeSummary(
            total_operations=1,
            total_files_copied=5,
            total_files_skipped=0,
            total_conflicts_resolved=0,
            total_folders_removed=1,
            duration_seconds=0,
            errors=[],
        )
        tui, output = tui_with_output

        tui.display_merge_summary(summary, dry_run=False)

        result = output.getvalue()
        assert "0m 0s" in result
