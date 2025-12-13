"""Pytest fixtures for Mergy tests."""

import io
import os
import platform
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Generator, List

import pytest
from rich.console import Console

from mergy.matching import FolderMatcher
from mergy.models import (
    ComputerFolder,
    FileConflict,
    FolderMatch,
    MergeOperation,
    MergeSelection,
    MergeSummary,
)
from mergy.models.match_reason import MatchReason
from mergy.operations import FileOperations
from mergy.scanning import FileHasher
from mergy.ui import MergeTUI


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for isolated test environments.

    Yields:
        Path to the temporary directory.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_files(temp_dir: Path) -> dict[str, Path]:
    """Create test files of various sizes with known content.

    Creates:
        - empty.txt: 0 bytes
        - small.txt: 1KB with 'a' characters
        - medium.txt: 1MB with 'b' characters
        - large.txt: 10MB with 'c' characters

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Dictionary mapping file names to their paths.
    """
    files = {}

    # Empty file
    empty_file = temp_dir / "empty.txt"
    empty_file.touch()
    files["empty"] = empty_file

    # Small file (1KB)
    small_file = temp_dir / "small.txt"
    small_file.write_bytes(b"a" * 1024)
    files["small"] = small_file

    # Medium file (1MB)
    medium_file = temp_dir / "medium.txt"
    medium_file.write_bytes(b"b" * (1024 * 1024))
    files["medium"] = medium_file

    # Large file (10MB)
    large_file = temp_dir / "large.txt"
    large_file.write_bytes(b"c" * (10 * 1024 * 1024))
    files["large"] = large_file

    return files


@pytest.fixture
def restricted_file(temp_dir: Path) -> Generator[Path | None, None, None]:
    """Create a file with no read permissions.

    Note: This fixture is platform-specific. On Windows, it may not work
    as expected due to different permission models.

    Args:
        temp_dir: Temporary directory fixture.

    Yields:
        Path to the restricted file, or None if permissions cannot be set.
    """
    if platform.system() == "Windows":
        # Windows has different permission model
        yield None
        return

    restricted = temp_dir / "restricted.txt"
    restricted.write_text("secret content")

    # Remove read permissions
    original_mode = restricted.stat().st_mode
    os.chmod(restricted, 0o000)

    try:
        yield restricted
    finally:
        # Restore permissions for cleanup
        os.chmod(restricted, original_mode)


@pytest.fixture
def symlink_file(temp_dir: Path) -> Generator[Path | None, None, None]:
    """Create a symlink to a regular file.

    Note: Symlinks may not be supported on all Windows configurations.

    Args:
        temp_dir: Temporary directory fixture.

    Yields:
        Path to the symlink, or None if symlinks are not supported.
    """
    target_file = temp_dir / "target.txt"
    target_file.write_text("target content")

    symlink_path = temp_dir / "link.txt"

    try:
        symlink_path.symlink_to(target_file)
        yield symlink_path
    except OSError:
        # Symlinks not supported on this platform/configuration
        yield None


@pytest.fixture
def nested_folder_structure(temp_dir: Path) -> Path:
    """Create a nested folder structure for testing.

    Creates:
        temp_dir/
        ├── folder1/
        │   ├── file1.txt (100 bytes)
        │   └── subfolder/
        │       └── file2.txt (200 bytes)
        ├── folder2/
        │   └── file3.txt (300 bytes)
        └── folder3/
            ├── .merged/
            │   └── old_file.txt (should be skipped)
            └── current.txt (400 bytes)

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Path to the base temporary directory.
    """
    # folder1 with nested subfolder
    folder1 = temp_dir / "folder1"
    folder1.mkdir()
    (folder1 / "file1.txt").write_bytes(b"x" * 100)

    subfolder = folder1 / "subfolder"
    subfolder.mkdir()
    (subfolder / "file2.txt").write_bytes(b"y" * 200)

    # folder2 with single file
    folder2 = temp_dir / "folder2"
    folder2.mkdir()
    (folder2 / "file3.txt").write_bytes(b"z" * 300)

    # folder3 with .merged directory (should be skipped)
    folder3 = temp_dir / "folder3"
    folder3.mkdir()

    merged_dir = folder3 / ".merged"
    merged_dir.mkdir()
    (merged_dir / "old_file.txt").write_bytes(b"old" * 100)

    (folder3 / "current.txt").write_bytes(b"w" * 400)

    return temp_dir


@pytest.fixture
def sample_computer_folders() -> List[ComputerFolder]:
    """Create a list of ComputerFolder instances for matcher testing.

    Creates folders with various naming patterns to test all matching tiers:
    - Exact prefix matches
    - Normalized matches
    - Token-based matches
    - Fuzzy matches
    - Unrelated folders

    Returns:
        List of ComputerFolder instances.
    """
    base_date = datetime(2020, 1, 1)
    end_date = datetime(2024, 1, 1)

    return [
        # Exact prefix group
        ComputerFolder(
            path=Path("/computers/pc1/135897-ntp"),
            name="135897-ntp",
            file_count=100,
            total_size=10000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        ComputerFolder(
            path=Path("/computers/pc2/135897-ntp.newspace"),
            name="135897-ntp.newspace",
            file_count=150,
            total_size=15000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        # Normalized match group
        ComputerFolder(
            path=Path("/computers/pc1/192.168.1.5-computer01"),
            name="192.168.1.5-computer01",
            file_count=200,
            total_size=20000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        ComputerFolder(
            path=Path("/computers/pc2/192.168.1.5 computer01"),
            name="192.168.1.5 computer01",
            file_count=180,
            total_size=18000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        # Fuzzy match group (typo)
        ComputerFolder(
            path=Path("/computers/pc1/comptuer01"),
            name="comptuer01",
            file_count=50,
            total_size=5000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        ComputerFolder(
            path=Path("/computers/pc2/computer01"),
            name="computer01",
            file_count=55,
            total_size=5500,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
        # Unrelated folder
        ComputerFolder(
            path=Path("/computers/pc3/unrelated-folder"),
            name="unrelated-folder",
            file_count=30,
            total_size=3000,
            oldest_file_date=base_date,
            newest_file_date=end_date,
        ),
    ]


@pytest.fixture
def matcher_default() -> FolderMatcher:
    """Create a FolderMatcher with default confidence threshold (0.7)."""
    return FolderMatcher()


@pytest.fixture
def matcher_low_threshold() -> FolderMatcher:
    """Create a FolderMatcher with low confidence threshold (0.5) for edge case testing."""
    return FolderMatcher(min_confidence=0.5)


@pytest.fixture
def file_operations_instance() -> FileOperations:
    """Return a FileOperations instance with fresh FileHasher.

    Returns:
        FileOperations instance ready for testing.
    """
    return FileOperations(hasher=FileHasher())


@pytest.fixture
def merge_scenario_simple(temp_dir: Path) -> Dict[str, Path]:
    """Create a realistic merge scenario for testing.

    Creates:
        - Primary folder: 3 files (file1.txt, file2.txt, shared.txt with hash A)
        - Source folder: 4 files (file3.txt new, file2.txt duplicate,
          shared.txt with hash B conflict, file4.txt new)

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Dictionary with paths and expected outcomes:
        - 'primary': Path to primary folder
        - 'source': Path to source folder
        - 'expected_new': List of new file names
        - 'expected_duplicate': List of duplicate file names
        - 'expected_conflict': List of conflicting file names
    """
    # Create primary folder
    primary = temp_dir / "primary"
    primary.mkdir()
    (primary / "file1.txt").write_text("primary file 1 content")
    (primary / "file2.txt").write_text("duplicate content - same in both")
    (primary / "shared.txt").write_text("primary version of shared file")

    # Create source folder
    source = temp_dir / "source"
    source.mkdir()
    (source / "file3.txt").write_text("new file 3 content")  # New
    (source / "file2.txt").write_text("duplicate content - same in both")  # Duplicate
    (source / "shared.txt").write_text("source version of shared file")  # Conflict
    (source / "file4.txt").write_text("new file 4 content")  # New

    # Set times for conflict resolution (primary is newer for shared.txt)
    _create_file_with_ctime(primary / "shared.txt", datetime(2024, 6, 1))
    _create_file_with_ctime(source / "shared.txt", datetime(2024, 1, 1))

    return {
        "primary": primary,
        "source": source,
        "expected_new": ["file3.txt", "file4.txt"],
        "expected_duplicate": ["file2.txt"],
        "expected_conflict": ["shared.txt"],
    }


@pytest.fixture
def merge_scenario_with_nested_conflicts(temp_dir: Path) -> Dict[str, Path]:
    """Create complex nested structure for conflict testing.

    Creates:
        - Primary: logs/app/system.log, data/reports/2024/jan.csv
        - Source: Same paths with different content (conflicts)

    Args:
        temp_dir: Temporary directory fixture.

    Returns:
        Dictionary with paths to primary and source folders.
    """
    # Create primary folder with nested structure
    primary = temp_dir / "primary"

    logs_dir = primary / "logs" / "app"
    logs_dir.mkdir(parents=True)
    (logs_dir / "system.log").write_text("primary system log")

    reports_dir = primary / "data" / "reports" / "2024"
    reports_dir.mkdir(parents=True)
    (reports_dir / "jan.csv").write_text("primary,jan,data")

    # Create source folder with same structure but different content
    source = temp_dir / "source"

    source_logs = source / "logs" / "app"
    source_logs.mkdir(parents=True)
    (source_logs / "system.log").write_text("source system log - different")

    source_reports = source / "data" / "reports" / "2024"
    source_reports.mkdir(parents=True)
    (source_reports / "jan.csv").write_text("source,jan,data,different")

    # Set times (primary is newer)
    _create_file_with_ctime(logs_dir / "system.log", datetime(2024, 6, 1))
    _create_file_with_ctime(source_logs / "system.log", datetime(2024, 1, 1))
    _create_file_with_ctime(reports_dir / "jan.csv", datetime(2024, 6, 1))
    _create_file_with_ctime(source_reports / "jan.csv", datetime(2024, 1, 1))

    return {
        "primary": primary,
        "source": source,
        "conflict_paths": ["logs/app/system.log", "data/reports/2024/jan.csv"],
    }


# Helper functions for test fixtures


def _create_file_with_ctime(path: Path, ctime: datetime) -> None:
    """Set file creation/modification time.

    Creates the file if it doesn't exist, then sets timestamps.

    Note: On most Unix systems, ctime (inode change time) cannot be set
    directly. We set mtime and atime as a proxy since the implementation
    uses st_ctime which may vary by platform.

    Args:
        path: Path to the file.
        ctime: Desired creation time.
    """
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    timestamp = ctime.timestamp()
    os.utime(path, (timestamp, timestamp))


def verify_merged_file_format(
    merged_path: Path, original_name: str, hash_value: str
) -> bool:
    """Verify .merged/ file naming follows the expected format.

    Checks that the merged file name follows the pattern:
    originalname_hash16chars.ext

    Args:
        merged_path: Path to the merged file.
        original_name: Original file name before merging.
        hash_value: Full SHA256 hash of the file.

    Returns:
        True if the naming format is correct, False otherwise.
    """
    merged_name = merged_path.name
    expected_hash_prefix = hash_value[:16]

    # Parse original name
    if "." in original_name:
        name_part, ext = original_name.rsplit(".", 1)
        expected_name = f"{name_part}_{expected_hash_prefix}.{ext}"
    else:
        expected_name = f"{original_name}_{expected_hash_prefix}"

    return merged_name == expected_name


# MergeLogger-related fixtures


@pytest.fixture
def sample_folder_matches() -> List[FolderMatch]:
    """Create a list of FolderMatch objects for scan phase testing.

    Returns:
        List of FolderMatch objects with various confidence levels and match reasons.
    """
    base_date = datetime(2020, 1, 1)
    end_date = datetime(2024, 1, 1)

    folder1 = ComputerFolder(
        path=Path("/computers/pc1/135897-ntp"),
        name="135897-ntp",
        file_count=100,
        total_size=10000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )
    folder2 = ComputerFolder(
        path=Path("/computers/pc2/135897-ntp.newspace"),
        name="135897-ntp.newspace",
        file_count=150,
        total_size=15000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )
    folder3 = ComputerFolder(
        path=Path("/computers/pc1/192.168.1.5-computer01"),
        name="192.168.1.5-computer01",
        file_count=200,
        total_size=20000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )
    folder4 = ComputerFolder(
        path=Path("/computers/pc2/192.168.1.5 computer01"),
        name="192.168.1.5 computer01",
        file_count=180,
        total_size=18000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )

    return [
        FolderMatch(
            folders=[folder1, folder2],
            confidence=0.95,
            match_reason=MatchReason.EXACT_PREFIX,
            base_name="135897-ntp",
        ),
        FolderMatch(
            folders=[folder3, folder4],
            confidence=0.85,
            match_reason=MatchReason.NORMALIZED,
            base_name="192.168.1.5-computer01",
        ),
    ]


@pytest.fixture
def sample_merge_selection() -> MergeSelection:
    """Create a realistic MergeSelection for testing.

    Returns:
        MergeSelection with primary folder and source folders.
    """
    base_date = datetime(2020, 1, 1)
    end_date = datetime(2024, 1, 1)

    primary = ComputerFolder(
        path=Path("/computers/pc1/135897-ntp"),
        name="135897-ntp",
        file_count=100,
        total_size=10000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )
    source = ComputerFolder(
        path=Path("/computers/pc2/135897-ntp.newspace"),
        name="135897-ntp.newspace",
        file_count=150,
        total_size=15000,
        oldest_file_date=base_date,
        newest_file_date=end_date,
    )
    match_group = FolderMatch(
        folders=[primary, source],
        confidence=0.95,
        match_reason=MatchReason.EXACT_PREFIX,
        base_name="135897-ntp",
    )

    return MergeSelection(
        primary=primary,
        merge_from=[source],
        match_group=match_group,
    )


@pytest.fixture
def sample_merge_operation(sample_merge_selection: MergeSelection) -> MergeOperation:
    """Create a realistic MergeOperation with statistics and errors.

    Args:
        sample_merge_selection: The merge selection fixture.

    Returns:
        MergeOperation with realistic statistics.
    """
    return MergeOperation(
        selection=sample_merge_selection,
        dry_run=False,
        timestamp=datetime.now(),
        files_copied=25,
        files_skipped=8,
        conflicts_resolved=3,
        folders_removed=1,
        errors=[],
    )


@pytest.fixture
def sample_merge_summary() -> MergeSummary:
    """Create a MergeSummary with aggregated statistics and duration.

    Returns:
        MergeSummary with realistic values matching specification examples.
    """
    return MergeSummary(
        total_operations=5,
        total_files_copied=120,
        total_files_skipped=35,
        total_conflicts_resolved=12,
        total_folders_removed=5,
        duration_seconds=323.5,  # 5m 23s
        errors=[],
    )


@pytest.fixture
def sample_file_conflicts() -> List[FileConflict]:
    """Create a list of FileConflict objects for conflict logging testing.

    Returns:
        List of FileConflict objects with various relative paths.
    """
    return [
        FileConflict(
            relative_path=Path("logs/app/system.log"),
            primary_file=Path("/computers/pc1/135897-ntp/logs/app/system.log"),
            conflicting_file=Path("/computers/pc2/135897-ntp.newspace/logs/app/system.log"),
            primary_hash="a1b2c3d4e5f6789012345678901234567890abcdef1234567890abcdef12345678",
            conflict_hash="fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",
            primary_ctime=datetime(2024, 6, 1),
            conflict_ctime=datetime(2024, 1, 1),
        ),
        FileConflict(
            relative_path=Path("data/reports/2024/jan.csv"),
            primary_file=Path("/computers/pc1/135897-ntp/data/reports/2024/jan.csv"),
            conflicting_file=Path("/computers/pc2/135897-ntp.newspace/data/reports/2024/jan.csv"),
            primary_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
            conflict_hash="abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            primary_ctime=datetime(2024, 5, 15),
            conflict_ctime=datetime(2024, 3, 10),
        ),
    ]


@pytest.fixture
def tui_with_captured_output() -> MergeTUI:
    """Create a MergeTUI instance with Console output captured to StringIO.

    This fixture is useful for testing TUI output without terminal interaction.
    Access captured output via: tui.console.file.getvalue()

    Returns:
        MergeTUI instance with StringIO-backed Console for output inspection.
    """
    output = io.StringIO()
    console = Console(file=output, force_terminal=True, width=120)
    return MergeTUI(console=console)
