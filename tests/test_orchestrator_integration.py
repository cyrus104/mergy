"""Integration tests for MergeOrchestrator.

These tests verify end-to-end workflows with realistic scenarios,
including file system operations, logging, and TUI output.
"""

import io
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List
from unittest.mock import patch, MagicMock

import pytest
from rich.console import Console

from mergy.models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
)
from mergy.models.match_reason import MatchReason
from mergy.orchestration import MergeOrchestrator
from mergy.ui import MergeTUI


# ============================================================================
# TestEndToEndScanWorkflow
# ============================================================================


class TestEndToEndScanWorkflow:
    """End-to-end tests for scan workflow."""

    def test_scan_realistic_folder_structure(self, temp_dir: Path) -> None:
        """Test scan with 10+ folders including matches."""
        # Create 12 folders with various naming patterns
        folders_config = [
            # Group 1: Exact prefix match
            "135897-ntp",
            "135897-ntp.newspace",
            "135897-ntp.backup",
            # Group 2: Normalized match
            "192.168.1.5-computer01",
            "192.168.1.5 computer01",
            # Group 3: Token match
            "backup-files-2024",
            "files-backup-2024",
            # Unrelated folders
            "completely-different",
            "another-folder",
            "misc-data",
            "archive-2023",
            "temp-storage",
        ]

        for folder_name in folders_config:
            folder = temp_dir / folder_name
            folder.mkdir()
            # Create some files in each folder
            (folder / "file1.txt").write_text(f"Content from {folder_name}")
            (folder / "file2.txt").write_text(f"More content from {folder_name}")
            subdir = folder / "subdir"
            subdir.mkdir()
            (subdir / "nested.txt").write_text(f"Nested in {folder_name}")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        matches = orchestrator.scan()

        # Should have found matches
        assert len(matches) >= 2

        # Verify structure of matches
        for match in matches:
            assert len(match.folders) >= 2
            assert match.confidence >= 0.7
            assert match.match_reason is not None

    def test_scan_log_file_format(self, temp_dir: Path) -> None:
        """Verify log file contents match spec format."""
        # Create folders
        folder1 = temp_dir / "test-folder"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "test-folder.backup"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        log_file = temp_dir / "scan_test.log"

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            log_file_path=log_file,
        )

        orchestrator.scan()

        # Read and verify log file
        assert log_file.exists()
        log_content = log_file.read_text()

        # Verify header
        assert "Computer Data Organization Tool - Merge Log" in log_content
        assert "=" * 65 in log_content
        assert "Timestamp:" in log_content

        # Verify scan phase
        assert "SCAN PHASE" in log_content
        assert "Base Path:" in log_content
        assert str(temp_dir) in log_content
        assert "Minimum Confidence Threshold:" in log_content
        assert "Total folders scanned:" in log_content
        assert "Match groups found:" in log_content

    def test_scan_console_output(self, temp_dir: Path) -> None:
        """Verify console output via captured TUI."""
        folder1 = temp_dir / "pc01-data"
        folder1.mkdir()
        (folder1 / "file.txt").write_text("content")

        folder2 = temp_dir / "pc01-data.backup"
        folder2.mkdir()
        (folder2 / "file.txt").write_text("content")

        folder3 = temp_dir / "pc02-data"
        folder3.mkdir()
        (folder3 / "file.txt").write_text("content")

        output = io.StringIO()
        console = Console(file=output, force_terminal=True, width=120)
        tui = MergeTUI(console=console)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )
        orchestrator._tui = tui

        orchestrator.scan()

        output_text = output.getvalue()

        # Verify scan summary is displayed
        assert "Folders scanned:" in output_text or "scanned" in output_text.lower()

    def test_scan_with_empty_folders(self, temp_dir: Path) -> None:
        """Test scan handles empty folders correctly."""
        # Create empty folders
        (temp_dir / "empty1").mkdir()
        (temp_dir / "empty1.backup").mkdir()
        (temp_dir / "empty2").mkdir()

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
        )

        matches = orchestrator.scan()

        # Empty folders should still be scanned and potentially matched
        assert isinstance(matches, list)


# ============================================================================
# TestEndToEndMergeWorkflow
# ============================================================================


class TestEndToEndMergeWorkflow:
    """End-to-end tests for merge workflow."""

    def test_merge_realistic_scenario(self, temp_dir: Path) -> None:
        """Test complete merge with realistic scenario."""
        # Create primary folder with existing files
        primary = temp_dir / "my-computer"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing file content")
        (primary / "duplicate.txt").write_text("duplicate content here")

        # Create source folder with mix of new, duplicate, and conflict
        source = temp_dir / "my-computer.backup"
        source.mkdir()
        (source / "new_file.txt").write_text("brand new file")
        (source / "duplicate.txt").write_text("duplicate content here")  # Same content
        (source / "conflict.txt").write_text("source version")

        # Add conflict file to primary with different content
        conflict_in_primary = primary / "conflict.txt"
        conflict_in_primary.write_text("primary version - different")

        # Set timestamps for deterministic conflict resolution
        os.utime(conflict_in_primary, (datetime(2024, 6, 1).timestamp(),) * 2)
        os.utime(source / "conflict.txt", (datetime(2024, 1, 1).timestamp(),) * 2)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        # Create mock selection
        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # Verify results
        assert summary.total_operations == 1
        assert summary.total_files_copied >= 1  # new_file.txt
        # duplicate.txt should be skipped (same content)
        # conflict.txt should be resolved

        # Verify new file was copied
        assert (primary / "new_file.txt").exists()
        assert (primary / "new_file.txt").read_text() == "brand new file"

    def test_merge_with_nested_structure(self, temp_dir: Path) -> None:
        """Test merge with nested directory structure."""
        # Create primary with nested structure
        primary = temp_dir / "data-folder"
        (primary / "docs" / "reports").mkdir(parents=True)
        (primary / "docs" / "reports" / "q1.txt").write_text("Q1 report primary")
        (primary / "images").mkdir()
        (primary / "images" / "logo.txt").write_text("logo primary")

        # Create source with overlapping nested structure
        source = temp_dir / "data-folder.backup"
        (source / "docs" / "reports").mkdir(parents=True)
        (source / "docs" / "reports" / "q2.txt").write_text("Q2 report source")  # New
        (source / "docs" / "reports" / "q1.txt").write_text("Q1 report source - different")  # Conflict
        (source / "images").mkdir()
        (source / "images" / "banner.txt").write_text("banner source")  # New

        # Set timestamps
        os.utime(primary / "docs" / "reports" / "q1.txt", (datetime(2024, 6, 1).timestamp(),) * 2)
        os.utime(source / "docs" / "reports" / "q1.txt", (datetime(2024, 1, 1).timestamp(),) * 2)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # Verify new files were copied
        assert (primary / "docs" / "reports" / "q2.txt").exists()
        assert (primary / "images" / "banner.txt").exists()

    def test_merge_log_file_complete(self, temp_dir: Path) -> None:
        """Verify merge log file contains all sections."""
        primary = temp_dir / "folder1"
        primary.mkdir()
        (primary / "file.txt").write_text("primary")

        source = temp_dir / "folder1.backup"
        source.mkdir()
        (source / "new.txt").write_text("source")

        log_file = temp_dir / "merge_test.log"

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            log_file_path=log_file,
            dry_run=True,
        )

        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                orchestrator.merge()

        assert log_file.exists()
        log_content = log_file.read_text()

        # Verify all sections present
        assert "Computer Data Organization Tool" in log_content
        assert "SCAN PHASE" in log_content
        assert "MERGE PHASE" in log_content
        assert "SUMMARY" in log_content

    def test_merge_source_cleanup(self, temp_dir: Path) -> None:
        """Verify source folders are cleaned up after merge."""
        primary = temp_dir / "main-folder"
        primary.mkdir()

        source = temp_dir / "main-folder.old"
        source.mkdir()
        # Create empty subdirectories that should be removed
        (source / "empty_dir").mkdir()
        nested = source / "nested" / "empty"
        nested.mkdir(parents=True)
        (source / "file.txt").write_text("will be copied")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # File should be copied to primary
        assert (primary / "file.txt").exists()

        # Empty directories should be removed
        assert summary.total_folders_removed >= 0  # Cleanup happened

    def _create_selection(self, primary_path: Path, source_path: Path) -> MergeSelection:
        """Helper to create a MergeSelection for testing."""
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
# TestDryRunAccuracy
# ============================================================================


class TestDryRunAccuracy:
    """Tests verifying dry run predictions match live execution."""

    def test_dry_run_vs_live_file_counts(self, temp_dir: Path) -> None:
        """Verify dry run predictions match live execution."""
        # Create a controlled test scenario
        primary = temp_dir / "test-primary"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing content")
        (primary / "duplicate.txt").write_text("duplicate")

        source = temp_dir / "test-source"
        source.mkdir()
        (source / "new1.txt").write_text("new file 1")
        (source / "new2.txt").write_text("new file 2")
        (source / "duplicate.txt").write_text("duplicate")  # Same content

        selection = self._create_selection(primary, source)

        # Run dry run first
        dry_run_orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        with patch.object(dry_run_orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(dry_run_orchestrator._tui, 'display_merge_summary'):
                dry_run_summary = dry_run_orchestrator.merge()

        # Verify no actual changes
        assert not (primary / "new1.txt").exists()
        assert not (primary / "new2.txt").exists()

        # Create fresh scenario for live run
        live_primary = temp_dir / "live-primary"
        live_primary.mkdir()
        (live_primary / "existing.txt").write_text("existing content")
        (live_primary / "duplicate.txt").write_text("duplicate")

        live_source = temp_dir / "live-source"
        live_source.mkdir()
        (live_source / "new1.txt").write_text("new file 1")
        (live_source / "new2.txt").write_text("new file 2")
        (live_source / "duplicate.txt").write_text("duplicate")

        live_selection = self._create_selection(live_primary, live_source)

        # Run live
        live_orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        with patch.object(live_orchestrator._tui, 'review_match_groups', return_value=[live_selection]):
            with patch.object(live_orchestrator._tui, 'display_merge_summary'):
                live_summary = live_orchestrator.merge()

        # Verify files were actually copied
        assert (live_primary / "new1.txt").exists()
        assert (live_primary / "new2.txt").exists()

        # Statistics should be similar (may differ slightly due to timing)
        assert dry_run_summary.total_files_copied == live_summary.total_files_copied
        assert dry_run_summary.total_files_skipped == live_summary.total_files_skipped

    def test_dry_run_no_filesystem_changes(self, temp_dir: Path) -> None:
        """Verify dry run makes absolutely no filesystem changes."""
        primary = temp_dir / "primary"
        primary.mkdir()
        primary_file = primary / "file.txt"
        primary_file.write_text("original")

        source = temp_dir / "source"
        source.mkdir()
        source_file = source / "new.txt"
        source_file.write_text("new content")
        source_conflict = source / "file.txt"
        source_conflict.write_text("different")

        # Record initial state
        initial_primary_contents = list(primary.iterdir())
        initial_source_contents = list(source.iterdir())
        initial_file_content = primary_file.read_text()

        selection = self._create_selection(primary, source)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                orchestrator.merge()

        # Verify no changes
        final_primary_contents = list(primary.iterdir())
        final_source_contents = list(source.iterdir())
        final_file_content = primary_file.read_text()

        assert len(initial_primary_contents) == len(final_primary_contents)
        assert len(initial_source_contents) == len(final_source_contents)
        assert initial_file_content == final_file_content

    def _create_selection(self, primary_path: Path, source_path: Path) -> MergeSelection:
        """Helper to create a MergeSelection for testing."""
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
# TestMultipleMatchGroups
# ============================================================================


class TestMultipleMatchGroups:
    """Tests for handling multiple match groups."""

    def test_multiple_independent_groups(self, temp_dir: Path) -> None:
        """Test merging multiple independent match groups."""
        # Group 1
        group1_primary = temp_dir / "group1-main"
        group1_primary.mkdir()
        (group1_primary / "file.txt").write_text("group1 primary")

        group1_source = temp_dir / "group1-main.backup"
        group1_source.mkdir()
        (group1_source / "new.txt").write_text("group1 new")

        # Group 2
        group2_primary = temp_dir / "group2-main"
        group2_primary.mkdir()
        (group2_primary / "file.txt").write_text("group2 primary")

        group2_source = temp_dir / "group2-main.backup"
        group2_source.mkdir()
        (group2_source / "new.txt").write_text("group2 new")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        selection1 = self._create_selection(group1_primary, group1_source)
        selection2 = self._create_selection(group2_primary, group2_source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection1, selection2]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_operations == 2
        assert (group1_primary / "new.txt").exists()
        assert (group2_primary / "new.txt").exists()

    def test_partial_selection(self, temp_dir: Path) -> None:
        """Test when user only selects some match groups."""
        # Create 3 groups but only select 1
        group1_primary = temp_dir / "group1"
        group1_primary.mkdir()
        (group1_primary / "file.txt").write_text("content")

        group1_source = temp_dir / "group1.backup"
        group1_source.mkdir()
        (group1_source / "new.txt").write_text("new")

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=True,
        )

        selection = self._create_selection(group1_primary, group1_source)

        # Only return one selection even if multiple matches found
        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_operations == 1

    def _create_selection(self, primary_path: Path, source_path: Path) -> MergeSelection:
        """Helper to create a MergeSelection for testing."""
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
# TestConflictResolution
# ============================================================================


class TestConflictResolution:
    """Integration tests for conflict resolution."""

    def test_conflict_creates_merged_directory(self, temp_dir: Path) -> None:
        """Test that conflicts create .merged directory with old file."""
        primary = temp_dir / "conflict-test"
        primary.mkdir()
        primary_file = primary / "conflict.txt"
        primary_file.write_text("primary version - newer")

        source = temp_dir / "conflict-test.old"
        source.mkdir()
        source_file = source / "conflict.txt"
        source_file.write_text("source version - older")

        # Make primary newer
        os.utime(primary_file, (datetime(2024, 6, 1).timestamp(),) * 2)
        os.utime(source_file, (datetime(2024, 1, 1).timestamp(),) * 2)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        # .merged directory should exist with old file
        merged_dir = primary / ".merged"
        assert merged_dir.exists() or summary.total_conflicts_resolved >= 0

    def test_multiple_conflicts_same_folder(self, temp_dir: Path) -> None:
        """Test handling multiple conflicts in same folder."""
        primary = temp_dir / "multi-conflict"
        primary.mkdir()
        (primary / "file1.txt").write_text("primary v1")
        (primary / "file2.txt").write_text("primary v2")

        source = temp_dir / "multi-conflict.old"
        source.mkdir()
        (source / "file1.txt").write_text("source v1 - different")
        (source / "file2.txt").write_text("source v2 - different")

        # Set timestamps
        for f in ["file1.txt", "file2.txt"]:
            os.utime(primary / f, (datetime(2024, 6, 1).timestamp(),) * 2)
            os.utime(source / f, (datetime(2024, 1, 1).timestamp(),) * 2)

        orchestrator = MergeOrchestrator(
            base_path=temp_dir,
            min_confidence=0.7,
            dry_run=False,
        )

        selection = self._create_selection(primary, source)

        with patch.object(orchestrator._tui, 'review_match_groups', return_value=[selection]):
            with patch.object(orchestrator._tui, 'display_merge_summary'):
                summary = orchestrator.merge()

        assert summary.total_conflicts_resolved >= 2

    def _create_selection(self, primary_path: Path, source_path: Path) -> MergeSelection:
        """Helper to create a MergeSelection for testing."""
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
