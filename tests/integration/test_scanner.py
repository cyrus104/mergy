"""
Integration tests for FolderScanner workflow in mergy.scanning.folder_scanner.

Tests cover:
- Basic scanning of directory structure
- Metadata collection (file count, total size, date ranges)
- Recursive file counting
- Skipping .merged directories
- Empty folder handling
- Symlink following
- Permission error handling
- Large directory performance
"""

import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from mergy.scanning import FolderScanner


@pytest.mark.integration
class TestScannerBasic:
    """Basic FolderScanner functionality tests."""

    def test_scan_basic_structure(self, test_data_structure: Path):
        """Scan test_data directory, verify folder count."""
        scanner = FolderScanner(test_data_structure)
        folders = scanner.scan()

        # Should find 6 folders from test_data_structure
        assert len(folders) == 6

        folder_names = {f.name for f in folders}
        expected = {
            "computer-01",
            "computer-01-backup",
            "computer-01.old",
            "192.168.1.5-computer02",
            "192.168.1.5 computer02",
            "unrelated-folder"
        }
        assert folder_names == expected

    def test_scan_metadata_collection(self, test_data_structure: Path):
        """Verify file_count, total_size, date ranges."""
        scanner = FolderScanner(test_data_structure)
        folders = scanner.scan()

        # Find computer-01 folder
        computer01 = next(f for f in folders if f.name == "computer-01")

        # Should have 5 files
        assert computer01.file_count == 5
        assert computer01.total_size > 0
        assert computer01.oldest_file_date is not None
        assert computer01.newest_file_date is not None
        assert computer01.oldest_file_date <= computer01.newest_file_date

    def test_scan_recursive_file_counting(self, temp_base_dir: Path):
        """Create nested structure, verify recursive count."""
        # Create nested structure
        folder = temp_base_dir / "nested"
        folder.mkdir()
        (folder / "file1.txt").write_text("content")
        (folder / "level1").mkdir()
        (folder / "level1" / "file2.txt").write_text("content")
        (folder / "level1" / "level2").mkdir()
        (folder / "level1" / "level2" / "file3.txt").write_text("content")
        (folder / "level1" / "level2" / "file4.txt").write_text("content")

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        nested_folder = next(f for f in folders if f.name == "nested")
        assert nested_folder.file_count == 4


@pytest.mark.integration
class TestScannerMergedHandling:
    """Tests for .merged directory handling."""

    def test_scan_skips_merged_directories(self, temp_base_dir: Path):
        """Create .merged/ dirs, verify they're skipped."""
        folder = temp_base_dir / "with_merged"
        folder.mkdir()
        (folder / "file1.txt").write_text("content")

        # Create .merged directory with files (should be skipped)
        merged = folder / ".merged"
        merged.mkdir()
        (merged / "archived1.txt").write_text("archived")
        (merged / "archived2.txt").write_text("archived")

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        with_merged = next(f for f in folders if f.name == "with_merged")
        # Should only count file1.txt, not files in .merged
        assert with_merged.file_count == 1

    def test_scan_skips_nested_merged(self, temp_base_dir: Path):
        """Verify nested .merged directories are skipped."""
        folder = temp_base_dir / "nested_merged"
        folder.mkdir()
        (folder / "subdir").mkdir()
        (folder / "subdir" / "file.txt").write_text("content")
        (folder / "subdir" / ".merged").mkdir()
        (folder / "subdir" / ".merged" / "old.txt").write_text("old")

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        nested = next(f for f in folders if f.name == "nested_merged")
        assert nested.file_count == 1


@pytest.mark.integration
class TestScannerEmptyFolders:
    """Tests for empty folder handling."""

    def test_scan_empty_folder(self, temp_base_dir: Path):
        """Scan folder with no files, verify None dates."""
        empty = temp_base_dir / "empty"
        empty.mkdir()

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        empty_folder = next(f for f in folders if f.name == "empty")
        assert empty_folder.file_count == 0
        assert empty_folder.total_size == 0
        assert empty_folder.oldest_file_date is None
        assert empty_folder.newest_file_date is None

    def test_scan_folder_with_empty_subdirs(self, temp_base_dir: Path):
        """Folder with only empty subdirectories."""
        folder = temp_base_dir / "empty_subdirs"
        folder.mkdir()
        (folder / "empty1").mkdir()
        (folder / "empty2").mkdir()
        (folder / "empty2" / "empty3").mkdir()

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        result = next(f for f in folders if f.name == "empty_subdirs")
        assert result.file_count == 0


@pytest.mark.integration
class TestScannerDates:
    """Tests for date detection."""

    def test_scan_oldest_newest_dates(self, temp_base_dir: Path):
        """Verify correct min/max date detection."""
        folder = temp_base_dir / "dated"
        folder.mkdir()

        # Create first file
        file1 = folder / "old.txt"
        file1.write_text("old")

        # Wait a small amount to ensure different ctime
        time.sleep(0.1)

        # Create second file
        file2 = folder / "new.txt"
        file2.write_text("new")

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        dated = next(f for f in folders if f.name == "dated")
        assert dated.oldest_file_date is not None
        assert dated.newest_file_date is not None
        # oldest should be <= newest (could be equal if created in same second)
        assert dated.oldest_file_date <= dated.newest_file_date


@pytest.mark.integration
class TestScannerSymlinks:
    """Tests for symlink handling."""

    def test_scan_symlink_handling(self, temp_base_dir: Path):
        """Test symlink following behavior."""
        folder = temp_base_dir / "with_symlink"
        folder.mkdir()

        # Create real file
        real_file = folder / "real.txt"
        real_file.write_text("real content")

        # Create symlink
        link_file = folder / "link.txt"
        try:
            link_file.symlink_to(real_file)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        scanner = FolderScanner(temp_base_dir)
        folders = scanner.scan()

        with_symlink = next(f for f in folders if f.name == "with_symlink")
        # Both real file and symlink should be counted
        assert with_symlink.file_count == 2


@pytest.mark.integration
class TestScannerErrors:
    """Tests for error handling during scanning."""

    def test_scan_permission_errors(self, temp_base_dir: Path):
        """Mock permission denied, verify error tracking."""
        test_folder = temp_base_dir / "test_folder"
        test_folder.mkdir()
        (test_folder / "file.txt").write_text("content")

        scanner = FolderScanner(temp_base_dir)

        # Mock os.walk to simulate permission error when invoked on test_folder
        original_walk = os.walk
        test_folder_resolved = str(test_folder.resolve())

        def mock_walk(path, **kwargs):
            # Check exact path equality with the test_folder directory path
            if str(Path(path).resolve()) == test_folder_resolved:
                raise PermissionError("Access denied")
            return original_walk(path, **kwargs)

        with patch('os.walk', side_effect=mock_walk):
            folders = scanner.scan()

        # Assert that scanner.errors is non-empty and contains permission-related error
        assert len(scanner.errors) > 0
        # Check that at least one error message contains relevant substring
        # The error message format is "Permission denied scanning folder: <path>"
        assert any("Permission denied" in err or "PermissionError" in err or "Access denied" in err for err in scanner.errors)

    def test_scanner_invalid_base_path(self, temp_base_dir: Path):
        """Test scanner with non-existent path."""
        non_existent = temp_base_dir / "does_not_exist"

        with pytest.raises(ValueError, match="does not exist"):
            FolderScanner(non_existent)

    def test_scanner_file_as_base_path(self, temp_base_dir: Path):
        """Test scanner with file instead of directory."""
        file_path = temp_base_dir / "file.txt"
        file_path.write_text("content")

        with pytest.raises(ValueError, match="not a directory"):
            FolderScanner(file_path)


@pytest.mark.integration
@pytest.mark.slow
class TestScannerPerformance:
    """Performance tests for large directories."""

    def test_scan_large_directory(self, temp_base_dir: Path):
        """Create 100+ files, verify performance."""
        folder = temp_base_dir / "large"
        folder.mkdir()

        # Create 150 files
        for i in range(150):
            (folder / f"file_{i:03d}.txt").write_text(f"content {i}")

        scanner = FolderScanner(temp_base_dir)

        start = time.time()
        folders = scanner.scan()
        duration = time.time() - start

        large = next(f for f in folders if f.name == "large")
        assert large.file_count == 150

        # Should complete reasonably quickly (under 5 seconds)
        assert duration < 5.0
