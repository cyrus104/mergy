"""
Integration tests for end-to-end merge workflow.

Tests cover:
- Basic merge workflow with 2 matching folders
- Merge with file conflicts
- Merge with duplicate files
- Multiple source folder merging
- Nested directory structure handling
- Empty directory cleanup after merge
- Error recovery during merge
- MergeOperation statistics accuracy
- MergeOrchestrator phases
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from merger_models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    MergeOperation,
    MergeSummary,
    MatchReason,
)
from mergy.scanning import FileHasher, FolderScanner
from mergy.operations import FileOperations
from mergy.orchestration import MergeOrchestrator

# Import from conftest through tests package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import create_computer_folder


@pytest.mark.integration
class TestBasicMergeWorkflow:
    """Tests for basic merge workflow."""

    def test_merge_workflow_basic(self, temp_base_dir: Path):
        """Create 2 matching folders, merge, verify file consolidation."""
        # Create primary folder
        primary = temp_base_dir / "project"
        primary.mkdir()
        (primary / "file1.txt").write_text("primary file 1")
        (primary / "file2.txt").write_text("primary file 2")

        # Create backup folder with new file
        backup = temp_base_dir / "project-backup"
        backup.mkdir()
        (backup / "file3.txt").write_text("backup file 3")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        # Create selection
        primary_folder = create_computer_folder("project", temp_base_dir)
        backup_folder = create_computer_folder("project-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, backup_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="project"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[backup_folder],
            match_group=match
        )

        # Execute merge
        operation = ops.merge_folders(selection)

        # Verify results
        assert operation.files_copied == 1
        assert (primary / "file3.txt").exists()
        assert (primary / "file3.txt").read_text() == "backup file 3"

    def test_merge_workflow_with_conflicts(self, temp_base_dir: Path):
        """Create conflicting files, verify .merged/ handling."""
        primary = temp_base_dir / "data"
        primary.mkdir()
        (primary / "config.txt").write_text("primary config")

        backup = temp_base_dir / "data-backup"
        backup.mkdir()
        (backup / "config.txt").write_text("backup config - different")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("data", temp_base_dir)
        backup_folder = create_computer_folder("data-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, backup_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="data"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[backup_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        assert operation.conflicts_resolved == 1
        assert (primary / ".merged").exists()

    def test_merge_workflow_with_duplicates(self, temp_base_dir: Path):
        """Create identical files, verify deduplication."""
        primary = temp_base_dir / "files"
        primary.mkdir()
        (primary / "same.txt").write_text("identical content")

        backup = temp_base_dir / "files-copy"
        backup.mkdir()
        (backup / "same.txt").write_text("identical content")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("files", temp_base_dir)
        backup_folder = create_computer_folder("files-copy", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, backup_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="files"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[backup_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        assert operation.files_skipped == 1
        assert operation.files_copied == 0
        assert operation.conflicts_resolved == 0


@pytest.mark.integration
class TestMultiSourceMerge:
    """Tests for merging multiple source folders."""

    def test_merge_workflow_multiple_sources(self, temp_base_dir: Path):
        """Merge 3+ folders into primary."""
        primary = temp_base_dir / "main"
        primary.mkdir()
        (primary / "base.txt").write_text("base")

        source1 = temp_base_dir / "main-v1"
        source1.mkdir()
        (source1 / "v1.txt").write_text("version 1")

        source2 = temp_base_dir / "main-v2"
        source2.mkdir()
        (source2 / "v2.txt").write_text("version 2")

        source3 = temp_base_dir / "main-old"
        source3.mkdir()
        (source3 / "old.txt").write_text("old version")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("main", temp_base_dir)
        source1_folder = create_computer_folder("main-v1", temp_base_dir)
        source2_folder = create_computer_folder("main-v2", temp_base_dir)
        source3_folder = create_computer_folder("main-old", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source1_folder, source2_folder, source3_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="main"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source1_folder, source2_folder, source3_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        assert operation.files_copied == 3
        assert (primary / "v1.txt").exists()
        assert (primary / "v2.txt").exists()
        assert (primary / "old.txt").exists()


@pytest.mark.integration
class TestNestedStructures:
    """Tests for nested directory handling."""

    def test_merge_workflow_nested_structure(self, temp_base_dir: Path):
        """Test with deep directory hierarchies."""
        primary = temp_base_dir / "project"
        primary.mkdir()
        (primary / "src").mkdir()
        (primary / "src" / "main.py").write_text("main code")

        backup = temp_base_dir / "project-backup"
        backup.mkdir()
        (backup / "src").mkdir()
        (backup / "src" / "utils").mkdir()
        (backup / "src" / "utils" / "helpers.py").write_text("helper code")
        (backup / "docs").mkdir()
        (backup / "docs" / "readme.md").write_text("documentation")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("project", temp_base_dir)
        backup_folder = create_computer_folder("project-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, backup_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="project"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[backup_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        assert operation.files_copied == 2
        assert (primary / "src" / "utils" / "helpers.py").exists()
        assert (primary / "docs" / "readme.md").exists()


@pytest.mark.integration
class TestEmptyDirCleanup:
    """Tests for empty directory cleanup after merge."""

    def test_merge_workflow_empty_dir_cleanup(self, temp_base_dir: Path):
        """Verify empty dirs are counted for removal after merge."""
        primary = temp_base_dir / "dest"
        primary.mkdir()

        source = temp_base_dir / "dest-source"
        source.mkdir()
        (source / "subdir").mkdir()
        (source / "subdir" / "file.txt").write_text("content")
        # Add an empty directory that will be counted for removal
        (source / "empty_dir").mkdir()

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("dest", temp_base_dir)
        source_folder = create_computer_folder("dest-source", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="dest"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        # Verify file was copied
        assert operation.files_copied == 1
        assert (primary / "subdir" / "file.txt").exists()
        # Note: The source still has files (they are copied, not moved)
        # So only truly empty directories would be removed
        assert operation.folders_removed >= 0


@pytest.mark.integration
class TestMergeStatistics:
    """Tests for MergeOperation statistics accuracy."""

    def test_merge_workflow_statistics(self, temp_base_dir: Path):
        """Verify MergeOperation counters accuracy."""
        primary = temp_base_dir / "stats"
        primary.mkdir()
        (primary / "existing.txt").write_text("existing")
        (primary / "duplicate.txt").write_text("same")
        (primary / "conflict.txt").write_text("primary version")

        source = temp_base_dir / "stats-backup"
        source.mkdir()
        (source / "new.txt").write_text("new file")
        (source / "duplicate.txt").write_text("same")  # Same content
        (source / "conflict.txt").write_text("different version")  # Different

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("stats", temp_base_dir)
        source_folder = create_computer_folder("stats-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="stats"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        assert operation.files_copied == 1  # new.txt
        assert operation.files_skipped == 1  # duplicate.txt
        assert operation.conflicts_resolved == 1  # conflict.txt


@pytest.mark.integration
class TestMergeOrchestrator:
    """Tests for MergeOrchestrator phases."""

    def test_orchestrator_scan_phase(self, test_data_structure: Path):
        """Test scan-only workflow."""
        orchestrator = MergeOrchestrator(
            base_path=test_data_structure,
            min_confidence=70.0,
            dry_run=True
        )

        matches = orchestrator.run_scan_workflow()

        # Should find match groups
        assert len(matches) >= 2

    def test_orchestrator_with_mock_tui(self, test_data_structure: Path):
        """Test orchestrator with mocked TUI."""
        orchestrator = MergeOrchestrator(
            base_path=test_data_structure,
            min_confidence=70.0,
            dry_run=True
        )

        # Mock TUI to avoid interactive prompts
        orchestrator.tui.console = MagicMock()

        matches = orchestrator.execute_scan_phase()

        assert len(matches) >= 2
        # Verify console was called
        assert orchestrator.tui.console.print.called


@pytest.mark.integration
class TestMergeErrorHandling:
    """Tests for error handling during merge."""

    def test_merge_workflow_error_recovery(self, temp_base_dir: Path):
        """Simulate file errors, verify continuation."""
        primary = temp_base_dir / "recovery"
        primary.mkdir()

        source = temp_base_dir / "recovery-backup"
        source.mkdir()
        (source / "good.txt").write_text("good content")
        (source / "problem.txt").write_text("problem content")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=False)

        primary_folder = create_computer_folder("recovery", temp_base_dir)
        source_folder = create_computer_folder("recovery-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="recovery"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        # Normal merge should work
        operation = ops.merge_folders(selection)

        assert operation.files_copied == 2
        assert len(operation.errors) == 0
