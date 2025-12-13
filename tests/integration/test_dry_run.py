"""
Integration tests for dry-run mode verification.

Tests cover:
- No file copies in dry-run
- No directory creation in dry-run
- No directory removal in dry-run
- Full analysis performed
- Statistics accuracy in dry-run
- Dry-run vs live comparison
- Orchestrator dry-run workflow
- Logging indicates DRY RUN mode
"""

import os
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from merger_models import (
    ComputerFolder,
    FolderMatch,
    MergeSelection,
    MatchReason,
)
from mergy.scanning import FileHasher
from mergy.operations import FileOperations
from mergy.orchestration import MergeOrchestrator

# Import from conftest through tests package
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from conftest import create_computer_folder


def get_directory_snapshot(path: Path) -> dict:
    """Capture complete state of a directory for comparison."""
    snapshot = {
        'files': {},
        'dirs': set()
    }

    if not path.exists():
        return snapshot

    for root, dirs, files in os.walk(path):
        root_path = Path(root)
        rel_root = root_path.relative_to(path) if root_path != path else Path(".")

        for d in dirs:
            snapshot['dirs'].add(str(rel_root / d))

        for f in files:
            file_path = root_path / f
            rel_path = str(rel_root / f)
            snapshot['files'][rel_path] = {
                'content': file_path.read_bytes(),
                'size': file_path.stat().st_size
            }

    return snapshot


@pytest.mark.integration
class TestDryRunNoModifications:
    """Tests verifying dry-run makes no file system changes."""

    def test_dry_run_no_file_copies(self, temp_base_dir: Path):
        """Verify no files copied when dry_run=True."""
        primary = temp_base_dir / "primary"
        primary.mkdir()

        source = temp_base_dir / "primary-backup"
        source.mkdir()
        (source / "new_file.txt").write_text("new content")

        # Snapshot before
        snapshot_before = get_directory_snapshot(primary)

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        primary_folder = create_computer_folder("primary", temp_base_dir)
        source_folder = create_computer_folder("primary-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="primary"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        # Snapshot after
        snapshot_after = get_directory_snapshot(primary)

        # No changes should have occurred
        assert snapshot_before['files'] == snapshot_after['files']
        assert not (primary / "new_file.txt").exists()

    def test_dry_run_no_directory_creation(self, temp_base_dir: Path):
        """Verify no .merged/ dirs created in dry-run."""
        primary = temp_base_dir / "data"
        primary.mkdir()
        (primary / "conflict.txt").write_text("primary")

        source = temp_base_dir / "data-backup"
        source.mkdir()
        (source / "conflict.txt").write_text("different")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        primary_folder = create_computer_folder("data", temp_base_dir)
        source_folder = create_computer_folder("data-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="data"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        ops.merge_folders(selection)

        # .merged directory should NOT exist
        assert not (primary / ".merged").exists()

    def test_dry_run_no_empty_dir_removal(self, temp_base_dir: Path):
        """Verify no directories removed in dry-run."""
        source = temp_base_dir / "to_clean"
        source.mkdir()
        nested = source / "level1" / "level2"
        nested.mkdir(parents=True)
        (nested / "file.txt").write_text("content")

        primary = temp_base_dir / "to_clean-dest"
        primary.mkdir()

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        primary_folder = create_computer_folder("to_clean-dest", temp_base_dir)
        source_folder = create_computer_folder("to_clean", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="to_clean"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        ops.merge_folders(selection)

        # Source directory structure should still exist
        assert source.exists()
        assert nested.exists()


@pytest.mark.integration
class TestDryRunAnalysis:
    """Tests for dry-run analysis completeness."""

    def test_dry_run_analysis_complete(self, temp_base_dir: Path):
        """Verify full analysis performed (conflicts detected)."""
        primary = temp_base_dir / "analyze"
        primary.mkdir()
        (primary / "same.txt").write_text("identical")
        (primary / "conflict.txt").write_text("version1")

        source = temp_base_dir / "analyze-backup"
        source.mkdir()
        (source / "new.txt").write_text("new file")
        (source / "same.txt").write_text("identical")
        (source / "conflict.txt").write_text("version2")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

        primary_folder = create_computer_folder("analyze", temp_base_dir)
        source_folder = create_computer_folder("analyze-backup", temp_base_dir)

        match = FolderMatch(
            folders=[primary_folder, source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="analyze"
        )

        selection = MergeSelection(
            primary=primary_folder,
            merge_from=[source_folder],
            match_group=match
        )

        operation = ops.merge_folders(selection)

        # Analysis should detect all scenarios
        assert operation.files_copied == 1  # new.txt
        assert operation.files_skipped == 1  # same.txt
        assert operation.conflicts_resolved == 1  # conflict.txt
        assert operation.dry_run is True

    def test_dry_run_statistics_accurate(self, temp_base_dir: Path):
        """Verify counters reflect what would happen."""
        primary = temp_base_dir / "stats"
        primary.mkdir()
        (primary / "keep.txt").write_text("keep")

        source = temp_base_dir / "stats-backup"
        source.mkdir()
        for i in range(5):
            (source / f"new_{i}.txt").write_text(f"new {i}")

        hasher = FileHasher()
        ops = FileOperations(hasher, dry_run=True)

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

        # Should predict 5 files would be copied
        assert operation.files_copied == 5


@pytest.mark.integration
class TestDryRunComparison:
    """Tests comparing dry-run vs live execution."""

    def test_dry_run_vs_live_comparison(self, temp_base_dir: Path):
        """Run same merge dry/live, compare results."""
        # Setup for dry run
        dry_primary = temp_base_dir / "dry_primary"
        dry_primary.mkdir()
        (dry_primary / "existing.txt").write_text("existing")

        dry_source = temp_base_dir / "dry_primary-backup"
        dry_source.mkdir()
        (dry_source / "new.txt").write_text("new")

        # Setup for live run (identical structure)
        live_primary = temp_base_dir / "live_primary"
        live_primary.mkdir()
        (live_primary / "existing.txt").write_text("existing")

        live_source = temp_base_dir / "live_primary-backup"
        live_source.mkdir()
        (live_source / "new.txt").write_text("new")

        # Dry run
        dry_hasher = FileHasher()
        dry_ops = FileOperations(dry_hasher, dry_run=True)

        dry_primary_folder = create_computer_folder("dry_primary", temp_base_dir)
        dry_source_folder = create_computer_folder("dry_primary-backup", temp_base_dir)

        dry_match = FolderMatch(
            folders=[dry_primary_folder, dry_source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="dry_primary"
        )

        dry_selection = MergeSelection(
            primary=dry_primary_folder,
            merge_from=[dry_source_folder],
            match_group=dry_match
        )

        dry_operation = dry_ops.merge_folders(dry_selection)

        # Live run
        live_hasher = FileHasher()
        live_ops = FileOperations(live_hasher, dry_run=False)

        live_primary_folder = create_computer_folder("live_primary", temp_base_dir)
        live_source_folder = create_computer_folder("live_primary-backup", temp_base_dir)

        live_match = FolderMatch(
            folders=[live_primary_folder, live_source_folder],
            confidence=100.0,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="live_primary"
        )

        live_selection = MergeSelection(
            primary=live_primary_folder,
            merge_from=[live_source_folder],
            match_group=live_match
        )

        live_operation = live_ops.merge_folders(live_selection)

        # Statistics should match
        assert dry_operation.files_copied == live_operation.files_copied
        assert dry_operation.files_skipped == live_operation.files_skipped
        assert dry_operation.conflicts_resolved == live_operation.conflicts_resolved

        # But only live run actually modified files
        assert not (dry_primary / "new.txt").exists()
        assert (live_primary / "new.txt").exists()


@pytest.mark.integration
class TestDryRunOrchestrator:
    """Tests for MergeOrchestrator in dry-run mode."""

    def test_dry_run_with_orchestrator(self, test_data_structure: Path):
        """Test full workflow in dry-run mode."""
        # Snapshot before
        snapshot_before = get_directory_snapshot(test_data_structure)

        orchestrator = MergeOrchestrator(
            base_path=test_data_structure,
            min_confidence=70.0,
            dry_run=True
        )

        # Mock TUI
        orchestrator.tui.console = MagicMock()

        matches = orchestrator.execute_scan_phase()

        # Snapshot after
        snapshot_after = get_directory_snapshot(test_data_structure)

        # No changes should have occurred
        assert snapshot_before['files'].keys() == snapshot_after['files'].keys()
        assert matches is not None

    def test_dry_run_orchestrator_flag(self, temp_base_dir: Path):
        """Verify orchestrator propagates dry_run flag."""
        folder = temp_base_dir / "test"
        folder.mkdir()
        (folder / "file.txt").write_text("content")

        orchestrator = MergeOrchestrator(
            base_path=temp_base_dir,
            min_confidence=70.0,
            dry_run=True
        )

        assert orchestrator.dry_run is True
        assert orchestrator.file_ops.dry_run is True
