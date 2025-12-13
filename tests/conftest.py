"""
Shared pytest fixtures and configuration for the test suite.

This module provides:
- Temporary directory fixtures for test isolation
- Sample data fixtures for matcher testing
- Test data structure setup per AGENTS.md section 13.2
- Mock fixtures for Rich Console output suppression
"""

import os
import shutil
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator, List
from unittest.mock import MagicMock

import pytest

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from merger_models import ComputerFolder, FolderMatch, MatchReason
from merger_ops import FileHasher, FolderScanner


# =============================================================================
# Pytest Configuration
# =============================================================================

def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests for individual components")
    config.addinivalue_line("markers", "integration: Integration tests for workflows")
    config.addinivalue_line("markers", "slow: Tests that take significant time")


# =============================================================================
# Temporary Directory Fixtures
# =============================================================================

@pytest.fixture
def temp_base_dir() -> Generator[Path, None, None]:
    """
    Create a temporary directory for a test and yield its Path.
    
    Returns:
        Path: Path to the created temporary directory. The directory and its contents are removed after the fixture completes.
    """
    temp_dir = tempfile.mkdtemp(prefix="mergy_test_")
    yield Path(temp_dir)
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def temp_file(temp_base_dir: Path) -> Generator[Path, None, None]:
    """
    Create a temporary file with known content.

    Args:
        temp_base_dir: Parent directory fixture.

    Yields:
        Path to temporary file with content "test content".
    """
    file_path = temp_base_dir / "test_file.txt"
    file_path.write_text("test content")
    yield file_path


# =============================================================================
# Sample Data Fixtures
# =============================================================================

@pytest.fixture
def sample_folders(temp_base_dir: Path) -> List[ComputerFolder]:
    """
    Create a set of example ComputerFolder objects covering common matching scenarios for tests.
    
    Returns:
        List[ComputerFolder]: Eight ComputerFolder instances representing exact-prefix matches, normalized name matches, token-based matches, an unrelated folder, and an empty-folder scenario.
    """
    base_date = datetime(2024, 1, 15, 12, 0, 0)

    folders = [
        # Group 1: Exact prefix matches (computer-01 family)
        ComputerFolder(
            path=temp_base_dir / "computer-01",
            name="computer-01",
            file_count=10,
            total_size=1024000,
            oldest_file_date=base_date - timedelta(days=30),
            newest_file_date=base_date
        ),
        ComputerFolder(
            path=temp_base_dir / "computer-01-backup",
            name="computer-01-backup",
            file_count=8,
            total_size=820000,
            oldest_file_date=base_date - timedelta(days=25),
            newest_file_date=base_date - timedelta(days=5)
        ),
        ComputerFolder(
            path=temp_base_dir / "computer-01.old",
            name="computer-01.old",
            file_count=5,
            total_size=512000,
            oldest_file_date=base_date - timedelta(days=60),
            newest_file_date=base_date - timedelta(days=30)
        ),

        # Group 2: Normalized matches (IP address naming)
        ComputerFolder(
            path=temp_base_dir / "192.168.1.5-computer02",
            name="192.168.1.5-computer02",
            file_count=15,
            total_size=2048000,
            oldest_file_date=base_date - timedelta(days=20),
            newest_file_date=base_date
        ),
        ComputerFolder(
            path=temp_base_dir / "192.168.1.5 computer02",
            name="192.168.1.5 computer02",
            file_count=12,
            total_size=1536000,
            oldest_file_date=base_date - timedelta(days=15),
            newest_file_date=base_date - timedelta(days=2)
        ),

        # Group 3: Token match scenario
        ComputerFolder(
            path=temp_base_dir / "workstation-alpha",
            name="workstation-alpha",
            file_count=7,
            total_size=700000,
            oldest_file_date=base_date - timedelta(days=10),
            newest_file_date=base_date
        ),

        # Unrelated folder (should not match)
        ComputerFolder(
            path=temp_base_dir / "unrelated-folder",
            name="unrelated-folder",
            file_count=3,
            total_size=300000,
            oldest_file_date=base_date - timedelta(days=5),
            newest_file_date=base_date
        ),

        # Empty folder scenario
        ComputerFolder(
            path=temp_base_dir / "empty-folder",
            name="empty-folder",
            file_count=0,
            total_size=0,
            oldest_file_date=None,
            newest_file_date=None
        ),
    ]

    return folders


@pytest.fixture
def test_data_structure(temp_base_dir: Path) -> Path:
    """
    Create a test directory hierarchy that mirrors the layout described in AGENTS.md section 13.2.
    
    The created structure (under the provided base Path) contains:
    - computer-01/: 5 files
    - computer-01-backup/: 3 files (2 duplicates of computer-01, 1 unique)
    - computer-01.old/: 4 files (1 conflicting file, 2 duplicates, 1 unique)
    - 192.168.1.5-computer02/: 6 files in nested subfolders
    - 192.168.1.5 computer02/: 4 files (3 duplicates, 1 unique)
    - unrelated-folder/: 3 files (no expected matches)
    
    Returns:
        Path: The provided base directory populated with the test data hierarchy.
    """
    # Create base directories
    folders = [
        "computer-01",
        "computer-01-backup",
        "computer-01.old",
        "192.168.1.5-computer02",
        "192.168.1.5 computer02",
        "unrelated-folder"
    ]

    for folder in folders:
        (temp_base_dir / folder).mkdir(exist_ok=True)

    # computer-01: Primary folder with 5 files
    computer01 = temp_base_dir / "computer-01"
    (computer01 / "data.txt").write_text("computer01 data content")
    (computer01 / "config.json").write_text('{"setting": "value1"}')
    (computer01 / "logs").mkdir(exist_ok=True)
    (computer01 / "logs" / "app.log").write_text("log entry 1\nlog entry 2")
    (computer01 / "readme.md").write_text("# Computer 01 Readme")
    (computer01 / "notes.txt").write_text("some notes here")

    # computer-01-backup: 3 files (2 duplicates of computer-01, 1 unique)
    backup = temp_base_dir / "computer-01-backup"
    (backup / "data.txt").write_text("computer01 data content")  # Duplicate
    (backup / "config.json").write_text('{"setting": "value1"}')  # Duplicate
    (backup / "backup_info.txt").write_text("backup created 2024-01-15")  # Unique

    # computer-01.old: 4 files (1 conflict, 2 duplicates, 1 unique)
    old = temp_base_dir / "computer-01.old"
    (old / "data.txt").write_text("OLD computer01 data - different content")  # Conflict
    (old / "readme.md").write_text("# Computer 01 Readme")  # Duplicate
    (old / "notes.txt").write_text("some notes here")  # Duplicate
    (old / "archive.zip").write_bytes(b"fake zip content here")  # Unique

    # 192.168.1.5-computer02: 6 files in nested structure
    ip_folder = temp_base_dir / "192.168.1.5-computer02"
    (ip_folder / "main.py").write_text("print('hello')")
    (ip_folder / "utils.py").write_text("def helper(): pass")
    (ip_folder / "docs").mkdir(exist_ok=True)
    (ip_folder / "docs" / "index.html").write_text("<html>docs</html>")
    (ip_folder / "docs" / "style.css").write_text("body { color: black; }")
    (ip_folder / "data").mkdir(exist_ok=True)
    (ip_folder / "data" / "dataset.csv").write_text("a,b,c\n1,2,3")
    (ip_folder / "data" / "config.yaml").write_text("key: value")

    # 192.168.1.5 computer02: 4 files (3 duplicates, 1 unique)
    ip_space_folder = temp_base_dir / "192.168.1.5 computer02"
    (ip_space_folder / "main.py").write_text("print('hello')")  # Duplicate
    (ip_space_folder / "utils.py").write_text("def helper(): pass")  # Duplicate
    (ip_space_folder / "docs").mkdir(exist_ok=True)
    (ip_space_folder / "docs" / "index.html").write_text("<html>docs</html>")  # Duplicate
    (ip_space_folder / "extra.txt").write_text("extra unique content")  # Unique

    # unrelated-folder: 3 files (should not match any group)
    unrelated = temp_base_dir / "unrelated-folder"
    (unrelated / "random1.txt").write_text("random content 1")
    (unrelated / "random2.txt").write_text("random content 2")
    (unrelated / "random3.txt").write_text("random content 3")

    return temp_base_dir


# =============================================================================
# Mock Fixtures
# =============================================================================

@pytest.fixture
def mock_console() -> MagicMock:
    """
    Create a mock Rich Console to prevent terminal output during tests.

    Returns:
        MagicMock instance that can replace Console.
    """
    mock = MagicMock()
    mock.print = MagicMock()
    return mock


@pytest.fixture
def file_hasher() -> FileHasher:
    """
    Create a fresh hasher instance with an empty cache.
    
    Returns:
        FileHasher: A new FileHasher instance whose internal cache is empty.
    """
    return FileHasher()


@pytest.fixture
def folder_scanner(temp_base_dir: Path) -> FolderScanner:
    """
    Create a FolderScanner configured to scan the provided temporary base directory.
    
    Parameters:
        temp_base_dir (Path): Base directory that the scanner will scan.
    
    Returns:
        FolderScanner: Scanner instance configured to scan the given directory.
    """
    return FolderScanner(temp_base_dir)


# =============================================================================
# Helper Functions for Tests
# =============================================================================

def create_file_with_content(path: Path, content: str) -> Path:
    """
    Create a file at the given path with the provided text content, creating parent directories if necessary.
    
    Parameters:
        path (Path): Destination file path to create.
        content (str): Text to write into the file.
    
    Returns:
        Path: The path to the created file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def create_file_with_bytes(path: Path, content: bytes) -> Path:
    """
    Create a binary file at the given path with the provided bytes content.
    
    This will create parent directories as needed and overwrite any existing file at that path.
    
    Parameters:
        path (Path): Target file path to create.
        content (bytes): Binary content to write to the file.
    
    Returns:
        Path: The same Path passed in, pointing to the created file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def assert_folder_match(match: FolderMatch, expected_count: int, expected_reason: MatchReason):
    """
    Validate that a FolderMatch meets expected count, reason, and basic integrity.
    
    Parameters:
        match (FolderMatch): The FolderMatch object to validate.
        expected_count (int): Expected number of folders in the match.
        expected_reason (MatchReason): Expected match reason value.
    
    Raises:
        AssertionError: If any of the following fail:
            - number of folders does not equal expected_count
            - match.match_reason does not equal expected_reason
            - match.confidence is not greater than 0
            - match.base_name is falsy
    """
    assert len(match.folders) == expected_count
    assert match.match_reason == expected_reason
    assert match.confidence > 0
    assert match.base_name


def count_files_recursive(path: Path) -> int:
    """
    Count files under the given directory recursively, ignoring any directories named ".merged".
    
    Parameters:
        path (Path): Root directory to search.
    
    Returns:
        int: Total number of files found beneath `path`, excluding files inside ".merged" directories.
    """
    count = 0
    for root, dirs, files in os.walk(path):
        # Skip .merged directories
        dirs[:] = [d for d in dirs if d != ".merged"]
        count += len(files)
    return count


def get_all_files(path: Path) -> List[Path]:
    """
    Return all file paths under the given directory recursively, excluding any files inside directories named ".merged".
    
    Parameters:
        path (Path): Root directory to search.
    
    Returns:
        List[Path]: All file paths found beneath `path`, not including files in ".merged" directories.
    """
    files = []
    for root, dirs, filenames in os.walk(path):
        dirs[:] = [d for d in dirs if d != ".merged"]
        for filename in filenames:
            files.append(Path(root) / filename)
    return files


def create_computer_folder(name: str, base_dir: Path) -> ComputerFolder:
    """
    Create a ComputerFolder instance with metadata computed from disk.

    This shared helper accepts a folder name and base directory, computes
    the current on-disk file count and total size, and constructs a
    ComputerFolder with suitable oldest_file_date and newest_file_date values.

    Args:
        name: Name of the folder.
        base_dir: Parent directory containing the folder.

    Returns:
        ComputerFolder instance with computed metadata.
    """
    folder_path = base_dir / name
    file_count = 0
    total_size = 0

    if folder_path.exists():
        file_count = sum(1 for _ in folder_path.rglob("*") if _.is_file())
        total_size = sum(f.stat().st_size for f in folder_path.rglob("*") if f.is_file())

    return ComputerFolder(
        path=folder_path,
        name=name,
        file_count=file_count,
        total_size=total_size,
        oldest_file_date=datetime.now() - timedelta(days=10),
        newest_file_date=datetime.now()
    )