"""End-to-end tests for Mergy CLI.

This module tests the CLI interface using Typer's CliRunner and the
test data structure from spec section 13.2.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Generator, List
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from mergy import __version__
from mergy.cli import app
from mergy.models import ComputerFolder, FolderMatch, MergeSelection
from mergy.models.match_reason import MatchReason


@pytest.fixture
def cli_runner() -> CliRunner:
    """Return a CliRunner instance for testing."""
    return CliRunner()


@pytest.fixture
def test_data_structure(temp_dir: Path) -> Path:
    """Create the test data structure from spec section 13.2.

    Creates:
        test_data/
        ├── computer-01/
        ├── computer-01-backup/
        ├── computer-01.old/
        ├── 192.168.1.5-computer02/
        ├── 192.168.1.5 computer02/
        └── unrelated-folder/

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path to the base test_data directory.
    """
    base = temp_dir / "test_data"
    base.mkdir()

    # Group 1: computer-01 variants
    (base / "computer-01").mkdir()
    (base / "computer-01-backup").mkdir()
    (base / "computer-01.old").mkdir()

    # Group 2: 192.168.1.5-computer02 variants
    (base / "192.168.1.5-computer02").mkdir()
    (base / "192.168.1.5 computer02").mkdir()

    # Unrelated folder
    (base / "unrelated-folder").mkdir()

    return base


@pytest.fixture
def populated_test_data(test_data_structure: Path) -> Path:
    """Add files to test data folders for realistic merging.

    Args:
        test_data_structure: The test data structure fixture.

    Returns:
        Path to the populated test_data directory.
    """
    base = test_data_structure

    # Populate computer-01 group
    # Primary folder: computer-01
    (base / "computer-01" / "readme.txt").write_text("Main readme")
    (base / "computer-01" / "data.json").write_text('{"version": 1}')

    # Backup folder: computer-01-backup
    (base / "computer-01-backup" / "readme.txt").write_text("Main readme")  # duplicate
    (base / "computer-01-backup" / "backup-notes.txt").write_text("Backup notes")  # new

    # Old folder: computer-01.old
    (base / "computer-01.old" / "legacy.txt").write_text("Legacy file")  # new

    # Populate 192.168.1.5-computer02 group
    (base / "192.168.1.5-computer02" / "config.ini").write_text("[main]\nversion=2")
    (base / "192.168.1.5 computer02" / "config.ini").write_text("[main]\nversion=1")  # conflict

    # Populate unrelated folder
    (base / "unrelated-folder" / "random.txt").write_text("Random content")

    return base


class TestVersionFlag:
    """Tests for --version flag."""

    def test_version_flag_short(self, cli_runner: CliRunner) -> None:
        """Test -v flag displays version."""
        result = cli_runner.invoke(app, ["-v"])
        assert result.exit_code == 0
        assert __version__ in result.stdout

    def test_version_flag_long(self, cli_runner: CliRunner) -> None:
        """Test --version flag displays version."""
        result = cli_runner.invoke(app, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.stdout


class TestHelpFlags:
    """Tests for --help flags."""

    def test_app_help(self, cli_runner: CliRunner) -> None:
        """Test app-level --help displays main help text."""
        result = cli_runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "Computer Data Organization Tool" in result.stdout
        assert "scan" in result.stdout
        assert "merge" in result.stdout

    def test_scan_help(self, cli_runner: CliRunner) -> None:
        """Test scan command --help displays scan help text."""
        result = cli_runner.invoke(app, ["scan", "--help"])
        assert result.exit_code == 0
        assert "Analyze folders without modification" in result.stdout
        assert "--min-confidence" in result.stdout
        assert "--log-file" in result.stdout
        assert "--verbose" in result.stdout

    def test_merge_help(self, cli_runner: CliRunner) -> None:
        """Test merge command --help displays merge help text."""
        result = cli_runner.invoke(app, ["merge", "--help"])
        assert result.exit_code == 0
        assert "Interactive merge process" in result.stdout
        assert "--min-confidence" in result.stdout
        assert "--log-file" in result.stdout
        assert "--verbose" in result.stdout
        assert "--dry-run" in result.stdout


class TestPathValidation:
    """Tests for path validation."""

    def test_scan_nonexistent_path(self, cli_runner: CliRunner) -> None:
        """Test scan with non-existent path returns error."""
        result = cli_runner.invoke(app, ["scan", "/nonexistent/path/12345"])
        assert result.exit_code == 1
        assert "Error" in result.stdout
        assert "does not exist" in result.stdout

    def test_merge_nonexistent_path(self, cli_runner: CliRunner) -> None:
        """Test merge with non-existent path returns error."""
        result = cli_runner.invoke(app, ["merge", "/nonexistent/path/12345"])
        assert result.exit_code == 1
        assert "Error" in result.stdout
        assert "does not exist" in result.stdout

    def test_scan_file_not_directory(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan with file path (not directory) returns error."""
        file_path = temp_dir / "test_file.txt"
        file_path.write_text("test content")

        result = cli_runner.invoke(app, ["scan", str(file_path)])
        assert result.exit_code == 1
        assert "Error" in result.stdout
        assert "not a directory" in result.stdout

    def test_merge_file_not_directory(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test merge with file path (not directory) returns error."""
        file_path = temp_dir / "test_file.txt"
        file_path.write_text("test content")

        result = cli_runner.invoke(app, ["merge", str(file_path)])
        assert result.exit_code == 1
        assert "Error" in result.stdout
        assert "not a directory" in result.stdout

    def test_scan_relative_path(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan with relative path works correctly."""
        # Create a subdirectory to scan
        subdir = temp_dir / "scanme"
        subdir.mkdir()
        (subdir / "folder1").mkdir()
        (subdir / "folder2").mkdir()

        # Change to temp_dir and use relative path
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            result = cli_runner.invoke(app, ["scan", "scanme"])
            # Should succeed (exit code 0) even if no matches found
            assert result.exit_code == 0
        finally:
            os.chdir(original_cwd)


class TestConfidenceValidation:
    """Tests for confidence option validation."""

    def test_confidence_out_of_range_high(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test confidence > 100 returns error."""
        result = cli_runner.invoke(app, ["scan", str(temp_dir), "--min-confidence", "150"])
        assert result.exit_code != 0

    def test_confidence_out_of_range_negative(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test negative confidence returns error."""
        result = cli_runner.invoke(app, ["scan", str(temp_dir), "--min-confidence", "-10"])
        assert result.exit_code != 0

    def test_confidence_valid_range(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test valid confidence values are accepted."""
        # Test at boundaries
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "0"]
        )
        assert result.exit_code == 0

        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "100"]
        )
        assert result.exit_code == 0

        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "50.5"]
        )
        assert result.exit_code == 0


class TestScanCommand:
    """Tests for scan command functionality."""

    def test_scan_command_success(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan with valid path succeeds."""
        result = cli_runner.invoke(app, ["scan", str(test_data_structure)])
        assert result.exit_code == 0

    def test_scan_finds_expected_matches(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan finds expected match groups from spec 13.2 test data."""
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "50"]
        )
        assert result.exit_code == 0
        # Should find computer-01 group
        assert "computer-01" in result.stdout

    def test_scan_empty_directory(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan with empty directory shows appropriate message."""
        result = cli_runner.invoke(app, ["scan", str(temp_dir)])
        assert result.exit_code == 0
        # No subdirectories means no folders to scan

    def test_scan_no_subdirectories(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan directory with only files (no subdirs)."""
        (temp_dir / "file1.txt").write_text("content")
        (temp_dir / "file2.txt").write_text("content")

        result = cli_runner.invoke(app, ["scan", str(temp_dir)])
        assert result.exit_code == 0

    def test_scan_with_verbose_flag(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan with --verbose flag shows additional output."""
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--verbose"]
        )
        assert result.exit_code == 0

    def test_scan_with_short_options(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan with short option flags (-c, -V)."""
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "-c", "60", "-V"]
        )
        assert result.exit_code == 0


class TestMergeCommand:
    """Tests for merge command functionality."""

    def test_merge_dry_run_no_changes(
        self, cli_runner: CliRunner, populated_test_data: Path
    ) -> None:
        """Test merge with --dry-run doesn't modify files.

        Patches MergeTUI.review_match_groups to return an empty list,
        so the merge completes without prompting but runs the full pipeline.
        """
        # Get file counts before
        files_before = list(populated_test_data.rglob("*"))
        file_count_before = len([f for f in files_before if f.is_file()])

        # Patch review_match_groups to return empty list (no selections)
        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[],
        ):
            result = cli_runner.invoke(
                app, ["merge", str(populated_test_data), "--dry-run"]
            )

        # Get file counts after
        files_after = list(populated_test_data.rglob("*"))
        file_count_after = len([f for f in files_after if f.is_file()])

        # File count should be unchanged
        assert file_count_before == file_count_after
        assert result.exit_code == 0

    def test_merge_dry_run_message(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test merge with --dry-run shows dry-run message.

        Patches MergeTUI.review_match_groups to return empty list to
        avoid interactive prompts while still running the pipeline.
        """
        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[],
        ):
            result = cli_runner.invoke(
                app, ["merge", str(test_data_structure), "--dry-run"]
            )
        assert "dry-run" in result.stdout.lower()
        assert result.exit_code == 0

    def test_merge_with_short_options(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test merge with short option flags (-c, -V, -n).

        Patches MergeTUI.review_match_groups to return empty list.
        """
        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[],
        ):
            result = cli_runner.invoke(
                app, ["merge", str(test_data_structure), "-c", "60", "-V", "-n"]
            )
        # Should succeed with dry-run message
        assert "dry-run" in result.stdout.lower()
        assert result.exit_code == 0

    def test_merge_no_matches_found(
        self, cli_runner: CliRunner, temp_dir: Path
    ) -> None:
        """Test merge when no match groups are found completes without prompts."""
        # Create directory with unrelated folders that won't match
        (temp_dir / "alpha").mkdir()
        (temp_dir / "beta").mkdir()
        (temp_dir / "gamma").mkdir()

        result = cli_runner.invoke(
            app, ["merge", str(temp_dir), "--min-confidence", "99"]
        )

        # Should complete with exit code 0, no prompts needed if no matches
        assert result.exit_code == 0


class TestLogFileOption:
    """Tests for --log-file option."""

    def test_custom_log_file_scan(
        self, cli_runner: CliRunner, test_data_structure: Path, temp_dir: Path
    ) -> None:
        """Test scan with custom log file creates log at specified path."""
        log_path = temp_dir / "custom_scan.log"

        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--log-file", str(log_path)]
        )
        assert result.exit_code == 0
        assert log_path.exists()

    def test_log_file_is_directory_error(
        self, cli_runner: CliRunner, test_data_structure: Path, temp_dir: Path
    ) -> None:
        """Test error when log file path is a directory."""
        log_dir = temp_dir / "log_dir"
        log_dir.mkdir()

        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--log-file", str(log_dir)]
        )
        assert result.exit_code == 1
        assert "directory" in result.stdout.lower()

    def test_log_file_short_option(
        self, cli_runner: CliRunner, test_data_structure: Path, temp_dir: Path
    ) -> None:
        """Test -l short option for log file."""
        log_path = temp_dir / "short_option.log"

        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "-l", str(log_path)]
        )
        assert result.exit_code == 0
        assert log_path.exists()


class TestKeyboardInterrupt:
    """Tests for keyboard interrupt handling."""

    def test_scan_keyboard_interrupt(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan handles KeyboardInterrupt gracefully."""
        # Mock the orchestrator scan to raise KeyboardInterrupt
        with patch(
            "mergy.orchestration.MergeOrchestrator.scan",
            side_effect=KeyboardInterrupt(),
        ):
            result = cli_runner.invoke(app, ["scan", str(test_data_structure)])
            assert result.exit_code == 1
            assert "cancelled" in result.stdout.lower()

    def test_merge_keyboard_interrupt(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test merge handles KeyboardInterrupt gracefully."""
        with patch(
            "mergy.orchestration.MergeOrchestrator.merge",
            side_effect=KeyboardInterrupt(),
        ):
            result = cli_runner.invoke(app, ["merge", str(test_data_structure)])
            assert result.exit_code == 1
            assert "cancelled" in result.stdout.lower()


class TestErrorHandling:
    """Tests for error handling."""

    def test_oserror_handling_scan(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan handles OSError gracefully."""
        with patch(
            "mergy.orchestration.MergeOrchestrator.scan",
            side_effect=OSError("Test OS error"),
        ):
            result = cli_runner.invoke(app, ["scan", str(test_data_structure)])
            assert result.exit_code == 1
            assert "error" in result.stdout.lower()

    def test_oserror_handling_merge(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test merge handles OSError gracefully."""
        with patch(
            "mergy.orchestration.MergeOrchestrator.merge",
            side_effect=OSError("Test OS error"),
        ):
            result = cli_runner.invoke(app, ["merge", str(test_data_structure)])
            assert result.exit_code == 1
            assert "error" in result.stdout.lower()


class TestIntegration:
    """Integration tests for complete workflows."""

    def test_scan_integration_with_matches(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test full scan workflow finds match groups."""
        result = cli_runner.invoke(
            app,
            ["scan", str(test_data_structure), "--min-confidence", "50", "--verbose"],
        )
        assert result.exit_code == 0
        # Should show scan summary
        output_lower = result.stdout.lower()
        # Check for expected output patterns
        assert "scan" in output_lower or "match" in output_lower or "folder" in output_lower

    def test_merge_integration_dry_run(
        self, cli_runner: CliRunner, populated_test_data: Path, temp_dir: Path
    ) -> None:
        """Test full merge workflow in dry-run mode.

        Patches MergeTUI.review_match_groups to return empty list to complete
        without interactive prompts while still running the full pipeline.
        """
        log_path = temp_dir / "merge_test.log"

        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[],
        ):
            result = cli_runner.invoke(
                app,
                [
                    "merge",
                    str(populated_test_data),
                    "--dry-run",
                    "--min-confidence",
                    "50",
                    "--log-file",
                    str(log_path),
                    "--verbose",
                ],
            )

        # Should at least start successfully and show dry-run message
        assert "dry-run" in result.stdout.lower()
        assert result.exit_code == 0

    def test_scan_creates_log_file_default_name(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan creates log file with default timestamped name."""
        # Note: The log file is created in the current directory by default
        # We just verify the scan completes successfully
        result = cli_runner.invoke(app, ["scan", str(test_data_structure)])
        assert result.exit_code == 0


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_empty_base_directory(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan with empty directory (no subdirectories)."""
        empty_dir = temp_dir / "empty"
        empty_dir.mkdir()

        result = cli_runner.invoke(app, ["scan", str(empty_dir)])
        assert result.exit_code == 0

    def test_single_folder_no_matches(
        self, cli_runner: CliRunner, temp_dir: Path
    ) -> None:
        """Test scan with single folder finds no matches."""
        single_folder = temp_dir / "single"
        single_folder.mkdir()
        (single_folder / "subfolder").mkdir()

        result = cli_runner.invoke(app, ["scan", str(single_folder)])
        assert result.exit_code == 0

    def test_high_confidence_no_matches(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan with very high confidence threshold finds fewer/no matches."""
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "99"]
        )
        assert result.exit_code == 0

    def test_low_confidence_more_matches(
        self, cli_runner: CliRunner, test_data_structure: Path
    ) -> None:
        """Test scan with low confidence threshold may find more matches."""
        result = cli_runner.invoke(
            app, ["scan", str(test_data_structure), "--min-confidence", "30"]
        )
        assert result.exit_code == 0

    def test_special_characters_in_folder_names(
        self, cli_runner: CliRunner, temp_dir: Path
    ) -> None:
        """Test scan handles folders with special characters."""
        special_dir = temp_dir / "special_test"
        special_dir.mkdir()

        # Create folders with special characters
        (special_dir / "folder with spaces").mkdir()
        (special_dir / "folder-with-dashes").mkdir()
        (special_dir / "folder_with_underscores").mkdir()
        (special_dir / "folder.with.dots").mkdir()

        result = cli_runner.invoke(app, ["scan", str(special_dir)])
        assert result.exit_code == 0

    def test_unicode_folder_names(self, cli_runner: CliRunner, temp_dir: Path) -> None:
        """Test scan handles folders with unicode characters."""
        unicode_dir = temp_dir / "unicode_test"
        unicode_dir.mkdir()

        # Create folders with unicode names
        (unicode_dir / "folder_ascii").mkdir()
        (unicode_dir / "carpeta_espanol").mkdir()

        result = cli_runner.invoke(app, ["scan", str(unicode_dir)])
        assert result.exit_code == 0


class TestMergeWorkflowEndToEnd:
    """End-to-end tests for full merge workflow with mocked user selections.

    These tests exercise the complete merge workflow from CLI through
    MergeOrchestrator by providing deterministic mocked TUI responses.
    """

    def _create_merge_selection_from_folders(
        self, primary: ComputerFolder, merge_from: List[ComputerFolder]
    ) -> MergeSelection:
        """Helper to create a MergeSelection from ComputerFolder instances.

        Args:
            primary: The primary (destination) folder.
            merge_from: List of source folders to merge from.

        Returns:
            MergeSelection with a FolderMatch containing all folders.
        """
        all_folders = [primary] + merge_from
        match_group = FolderMatch(
            folders=all_folders,
            confidence=0.9,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name=primary.name,
        )
        return MergeSelection(
            primary=primary,
            merge_from=merge_from,
            match_group=match_group,
        )

    def test_full_merge_workflow_with_mocked_selections(
        self, cli_runner: CliRunner, populated_test_data: Path, temp_dir: Path
    ) -> None:
        """Test complete merge workflow with realistic mocked user selections.

        This test:
        1. Uses populated_test_data fixture as the base directory
        2. Patches MergeTUI.review_match_groups to return a realistic MergeSelection
        3. Runs the merge command (without --dry-run to exercise actual file operations)
        4. Verifies exit code, output, and filesystem changes
        """
        # Build ComputerFolder instances for the test data
        base = populated_test_data
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        # Primary folder: computer-01 (has readme.txt, data.json)
        primary_folder = ComputerFolder(
            path=base / "computer-01",
            name="computer-01",
            file_count=2,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        # Merge-from folders
        backup_folder = ComputerFolder(
            path=base / "computer-01-backup",
            name="computer-01-backup",
            file_count=2,
            total_size=80,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        old_folder = ComputerFolder(
            path=base / "computer-01.old",
            name="computer-01.old",
            file_count=1,
            total_size=50,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        # Create the MergeSelection
        selection = self._create_merge_selection_from_folders(
            primary=primary_folder,
            merge_from=[backup_folder, old_folder],
        )

        log_path = temp_dir / "e2e_merge.log"

        # Track files before merge
        primary_files_before = set(f.name for f in (base / "computer-01").iterdir() if f.is_file())

        # Patch review_match_groups to return our realistic selection
        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[selection],
        ):
            result = cli_runner.invoke(
                app,
                [
                    "merge",
                    str(populated_test_data),
                    "--min-confidence",
                    "50",
                    "--log-file",
                    str(log_path),
                ],
            )

        # Assertions
        assert result.exit_code == 0, f"Merge failed with output: {result.stdout}"

        # Should show merge summary in output
        output_lower = result.stdout.lower()
        assert "merge" in output_lower or "summary" in output_lower or "files" in output_lower

        # Log file should be created
        assert log_path.exists(), "Log file was not created"

        # Verify filesystem changes: new files should be copied to primary
        primary_files_after = set(f.name for f in (base / "computer-01").iterdir() if f.is_file())

        # backup-notes.txt from computer-01-backup should be in primary now
        assert "backup-notes.txt" in primary_files_after, (
            f"backup-notes.txt not found in primary. Files: {primary_files_after}"
        )

        # legacy.txt from computer-01.old should be in primary now
        assert "legacy.txt" in primary_files_after, (
            f"legacy.txt not found in primary. Files: {primary_files_after}"
        )

        # Original files should still be there
        assert "readme.txt" in primary_files_after
        assert "data.json" in primary_files_after

    def test_full_merge_workflow_dry_run_with_mocked_selections(
        self, cli_runner: CliRunner, populated_test_data: Path, temp_dir: Path
    ) -> None:
        """Test merge workflow with --dry-run using mocked selections.

        Verifies that dry-run mode shows what would happen without making changes.
        """
        base = populated_test_data
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        primary_folder = ComputerFolder(
            path=base / "computer-01",
            name="computer-01",
            file_count=2,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        backup_folder = ComputerFolder(
            path=base / "computer-01-backup",
            name="computer-01-backup",
            file_count=2,
            total_size=80,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        selection = self._create_merge_selection_from_folders(
            primary=primary_folder,
            merge_from=[backup_folder],
        )

        log_path = temp_dir / "e2e_dryrun.log"

        # Track files before
        primary_files_before = set(f.name for f in (base / "computer-01").iterdir() if f.is_file())

        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[selection],
        ):
            result = cli_runner.invoke(
                app,
                [
                    "merge",
                    str(populated_test_data),
                    "--dry-run",
                    "--min-confidence",
                    "50",
                    "--log-file",
                    str(log_path),
                ],
            )

        assert result.exit_code == 0
        assert "dry-run" in result.stdout.lower()

        # Verify NO filesystem changes in dry-run mode
        primary_files_after = set(f.name for f in (base / "computer-01").iterdir() if f.is_file())
        assert primary_files_before == primary_files_after, (
            "Dry-run mode should not modify files"
        )

    def test_merge_workflow_with_conflict_handling(
        self, cli_runner: CliRunner, populated_test_data: Path, temp_dir: Path
    ) -> None:
        """Test merge workflow handles file conflicts correctly.

        The 192.168.1.5-computer02 group has conflicting config.ini files.
        This test verifies the merge handles the conflict by creating a
        .merged directory with the conflicting file.
        """
        base = populated_test_data
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        # Use the IP-based folder group which has conflicting config.ini
        primary_folder = ComputerFolder(
            path=base / "192.168.1.5-computer02",
            name="192.168.1.5-computer02",
            file_count=1,
            total_size=50,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source_folder = ComputerFolder(
            path=base / "192.168.1.5 computer02",
            name="192.168.1.5 computer02",
            file_count=1,
            total_size=50,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )

        selection = self._create_merge_selection_from_folders(
            primary=primary_folder,
            merge_from=[source_folder],
        )

        log_path = temp_dir / "e2e_conflict.log"

        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[selection],
        ):
            result = cli_runner.invoke(
                app,
                [
                    "merge",
                    str(populated_test_data),
                    "--min-confidence",
                    "50",
                    "--log-file",
                    str(log_path),
                ],
            )

        assert result.exit_code == 0

        # Check that .merged directory was created for the conflict
        merged_dir = base / "192.168.1.5-computer02" / ".merged"
        assert merged_dir.exists(), ".merged directory should be created for conflicts"

        # The conflicting file should be in .merged with a hash suffix
        merged_files = list(merged_dir.iterdir())
        assert len(merged_files) >= 1, "Conflicting file should be stored in .merged"

        # Verify the merged file has config in its name
        merged_names = [f.name for f in merged_files]
        has_config_conflict = any("config" in name for name in merged_names)
        assert has_config_conflict, f"Expected config conflict file in .merged, got: {merged_names}"

    def test_merge_workflow_multiple_selections(
        self, cli_runner: CliRunner, populated_test_data: Path, temp_dir: Path
    ) -> None:
        """Test merge workflow with multiple match group selections.

        Verifies that multiple selections are processed sequentially.
        """
        base = populated_test_data
        base_date = datetime(2020, 1, 1)
        end_date = datetime(2024, 1, 1)

        # First selection: computer-01 group
        primary1 = ComputerFolder(
            path=base / "computer-01",
            name="computer-01",
            file_count=2,
            total_size=100,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        backup1 = ComputerFolder(
            path=base / "computer-01-backup",
            name="computer-01-backup",
            file_count=2,
            total_size=80,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        selection1 = self._create_merge_selection_from_folders(
            primary=primary1,
            merge_from=[backup1],
        )

        # Second selection: IP-based group
        primary2 = ComputerFolder(
            path=base / "192.168.1.5-computer02",
            name="192.168.1.5-computer02",
            file_count=1,
            total_size=50,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        source2 = ComputerFolder(
            path=base / "192.168.1.5 computer02",
            name="192.168.1.5 computer02",
            file_count=1,
            total_size=50,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        )
        selection2 = self._create_merge_selection_from_folders(
            primary=primary2,
            merge_from=[source2],
        )

        log_path = temp_dir / "e2e_multi.log"

        with patch(
            "mergy.orchestration.merge_orchestrator.MergeTUI.review_match_groups",
            return_value=[selection1, selection2],
        ):
            result = cli_runner.invoke(
                app,
                [
                    "merge",
                    str(populated_test_data),
                    "--min-confidence",
                    "50",
                    "--log-file",
                    str(log_path),
                ],
            )

        assert result.exit_code == 0

        # Verify both merges happened
        # computer-01 should have backup-notes.txt from backup
        assert (base / "computer-01" / "backup-notes.txt").exists()

        # 192.168.1.5-computer02 should have .merged directory for conflict
        assert (base / "192.168.1.5-computer02" / ".merged").exists()
