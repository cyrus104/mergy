"""Unit tests for FolderScanner class."""

import os
import platform
import time
from pathlib import Path

import pytest

from mergy.scanning import FileHasher, FolderScanner


class TestFolderScannerBasic:
    """Basic functionality tests for FolderScanner."""

    def test_scan_folder_normal(self, temp_dir: Path) -> None:
        """Test scanning a folder with multiple files collects correct metadata."""
        # Create folder with files
        folder = temp_dir / "test_folder"
        folder.mkdir()

        (folder / "file1.txt").write_bytes(b"a" * 100)
        (folder / "file2.txt").write_bytes(b"b" * 200)
        (folder / "file3.txt").write_bytes(b"c" * 300)

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.name == "test_folder"
        assert result.file_count == 3
        assert result.total_size == 600
        assert result.path == folder.resolve()

    def test_scan_folder_empty(self, temp_dir: Path) -> None:
        """Test scanning an empty folder returns file_count=0 with folder timestamp."""
        empty_folder = temp_dir / "empty_folder"
        empty_folder.mkdir()

        scanner = FolderScanner()
        result = scanner.scan_folder(empty_folder)

        assert result is not None
        assert result.file_count == 0
        assert result.total_size == 0
        # Dates should be set to folder's mtime
        assert result.oldest_file_date is not None
        assert result.newest_file_date is not None
        assert result.oldest_file_date == result.newest_file_date

    def test_scan_folder_nested(self, temp_dir: Path) -> None:
        """Test scanning folder with nested subdirectories counts all files."""
        folder = temp_dir / "nested_folder"
        folder.mkdir()

        # Root level file
        (folder / "root.txt").write_bytes(b"root" * 25)

        # Nested level 1
        sub1 = folder / "sub1"
        sub1.mkdir()
        (sub1 / "file1.txt").write_bytes(b"sub1" * 25)

        # Nested level 2
        sub2 = sub1 / "sub2"
        sub2.mkdir()
        (sub2 / "file2.txt").write_bytes(b"sub2" * 25)

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.file_count == 3  # All nested files counted
        assert result.total_size == 300  # 3 files * 100 bytes each


class TestFolderScannerMergedSkipping:
    """Tests for .merged directory skipping."""

    def test_scan_folder_skips_merged(self, nested_folder_structure: Path) -> None:
        """Test that .merged subfolder is skipped during scanning."""
        folder3 = nested_folder_structure / "folder3"

        scanner = FolderScanner()
        result = scanner.scan_folder(folder3)

        assert result is not None
        # Should only count current.txt (400 bytes), not .merged/old_file.txt
        assert result.file_count == 1
        assert result.total_size == 400


class TestFolderScannerSymlinks:
    """Symlink handling tests for FolderScanner."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_scan_folder_symlink(self, temp_dir: Path) -> None:
        """Test scanning folder containing symlinked files follows symlinks."""
        folder = temp_dir / "folder_with_symlink"
        folder.mkdir()

        # Create target file outside folder
        target = temp_dir / "target.txt"
        target.write_bytes(b"target content")

        # Create symlink inside folder
        symlink = folder / "link.txt"
        try:
            symlink.symlink_to(target)
        except OSError:
            pytest.skip("Symlinks not supported")

        # Create regular file
        (folder / "regular.txt").write_bytes(b"regular")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.file_count == 2  # Both regular and symlinked file

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_scan_folder_directory_symlink_cycle_to_self(self, temp_dir: Path) -> None:
        """Test scanning terminates when directory contains symlink to itself."""
        folder = temp_dir / "folder_with_cycle"
        folder.mkdir()

        # Create a file to count
        (folder / "file.txt").write_bytes(b"content")

        # Create symlink pointing back to the same folder
        cycle_link = folder / "cycle"
        try:
            cycle_link.symlink_to(folder)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        # Should complete without infinite loop
        assert result is not None
        # Should count only the real file, not traverse the cycle infinitely
        assert result.file_count == 1
        assert result.total_size == len(b"content")

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_scan_folder_directory_symlink_cycle_to_parent(self, temp_dir: Path) -> None:
        """Test scanning terminates when subdirectory contains symlink to parent."""
        folder = temp_dir / "parent_folder"
        folder.mkdir()

        # Create a file in parent
        (folder / "parent_file.txt").write_bytes(b"parent content")

        # Create subdirectory
        subdir = folder / "subdir"
        subdir.mkdir()

        # Create a file in subdir
        (subdir / "child_file.txt").write_bytes(b"child content")

        # Create symlink in subdir pointing back to parent
        cycle_link = subdir / "back_to_parent"
        try:
            cycle_link.symlink_to(folder)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        # Should complete without infinite loop
        assert result is not None
        # Should count both real files but not traverse the cycle
        assert result.file_count == 2

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_scan_folder_directory_symlink_mutual_cycle(self, temp_dir: Path) -> None:
        """Test scanning terminates with mutually referencing directory symlinks."""
        folder = temp_dir / "mutual_cycle"
        folder.mkdir()

        # Create two subdirectories
        dir_a = folder / "dir_a"
        dir_a.mkdir()
        dir_b = folder / "dir_b"
        dir_b.mkdir()

        # Create files in each
        (dir_a / "file_a.txt").write_bytes(b"a")
        (dir_b / "file_b.txt").write_bytes(b"b")

        try:
            # Create mutual symlinks
            (dir_a / "link_to_b").symlink_to(dir_b)
            (dir_b / "link_to_a").symlink_to(dir_a)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        # Should complete without infinite loop
        assert result is not None
        # Should count the real files only
        assert result.file_count == 2


class TestFolderScannerErrors:
    """Error handling tests for FolderScanner."""

    def test_scan_folder_not_found(self, temp_dir: Path) -> None:
        """Test scanning non-existent folder returns None and logs error."""
        nonexistent = temp_dir / "nonexistent"

        scanner = FolderScanner()
        result = scanner.scan_folder(nonexistent)

        assert result is None
        errors = scanner.get_errors()
        assert len(errors) == 1
        assert "not found" in errors[0].lower()

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Permission handling differs on Windows",
    )
    def test_scan_folder_permission_denied(self, temp_dir: Path) -> None:
        """Test scanning folder without read permissions returns None and logs error."""
        restricted = temp_dir / "restricted"
        restricted.mkdir()

        # Remove permissions
        original_mode = restricted.stat().st_mode
        os.chmod(restricted, 0o000)

        try:
            scanner = FolderScanner()
            result = scanner.scan_folder(restricted)

            assert result is None
            errors = scanner.get_errors()
            assert len(errors) >= 1
            assert any("permission" in e.lower() for e in errors)
        finally:
            os.chmod(restricted, original_mode)


class TestFolderScannerImmediateSubdirectories:
    """Tests for scan_immediate_subdirectories method."""

    def test_scan_immediate_subdirectories(self, nested_folder_structure: Path) -> None:
        """Test scanning immediate subdirectories returns correct folder count."""
        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(nested_folder_structure)

        # Should find folder1, folder2, folder3
        assert len(folders) == 3
        folder_names = {f.name for f in folders}
        assert folder_names == {"folder1", "folder2", "folder3"}

    def test_scan_immediate_subdirectories_mixed(self, temp_dir: Path) -> None:
        """Test that only directories are scanned, not files at base level."""
        # Create mix of files and folders at base level
        (temp_dir / "file.txt").write_bytes(b"file at base")
        (temp_dir / "folder1").mkdir()
        (temp_dir / "folder2").mkdir()
        (temp_dir / "another_file.log").write_bytes(b"another file")

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(temp_dir)

        # Should only return 2 folders, not the files
        assert len(folders) == 2
        folder_names = {f.name for f in folders}
        assert folder_names == {"folder1", "folder2"}

    def test_scan_immediate_subdirectories_empty_base(self, temp_dir: Path) -> None:
        """Test scanning empty base path returns empty list."""
        empty_base = temp_dir / "empty_base"
        empty_base.mkdir()

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(empty_base)

        assert folders == []


class TestFolderScannerDateTracking:
    """Tests for oldest/newest date tracking."""

    def test_scan_folder_oldest_newest_dates(self, temp_dir: Path) -> None:
        """Test that oldest and newest file dates are correctly detected."""
        folder = temp_dir / "dated_folder"
        folder.mkdir()

        # Create files with different timestamps
        file1 = folder / "old.txt"
        file2 = folder / "new.txt"

        file1.write_bytes(b"old content")
        time.sleep(0.1)  # Ensure different timestamps
        file2.write_bytes(b"new content")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        # Newest should be >= oldest
        assert result.newest_file_date >= result.oldest_file_date


class TestFolderScannerSizeCalculation:
    """Tests for total size calculation."""

    def test_scan_folder_total_size(self, temp_dir: Path) -> None:
        """Test that total size is calculated correctly."""
        folder = temp_dir / "sized_folder"
        folder.mkdir()

        # Create files with known sizes
        (folder / "file100.txt").write_bytes(b"x" * 100)
        (folder / "file200.txt").write_bytes(b"y" * 200)
        (folder / "file500.txt").write_bytes(b"z" * 500)

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.total_size == 800


class TestFolderScannerWithErrors:
    """Tests for partial success with errors."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Permission handling differs on Windows",
    )
    def test_scan_folder_with_inaccessible_files(self, temp_dir: Path) -> None:
        """Test scanning folder with some inaccessible files succeeds partially."""
        folder = temp_dir / "mixed_folder"
        folder.mkdir()

        # Create accessible file
        accessible = folder / "accessible.txt"
        accessible.write_bytes(b"accessible content")

        # Create inaccessible file
        inaccessible = folder / "inaccessible.txt"
        inaccessible.write_bytes(b"secret")
        original_mode = inaccessible.stat().st_mode
        os.chmod(inaccessible, 0o000)

        try:
            scanner = FolderScanner()
            result = scanner.scan_folder(folder)

            # Should still return a result with partial data
            assert result is not None
            assert result.file_count >= 1  # At least the accessible file

            # Should have logged an error
            errors = scanner.get_errors()
            assert len(errors) >= 1
        finally:
            os.chmod(inaccessible, original_mode)


class TestFolderScannerIntegration:
    """Integration tests with FileHasher."""

    def test_scanner_with_custom_hasher(self, temp_dir: Path) -> None:
        """Test FolderScanner works with a provided FileHasher instance."""
        custom_hasher = FileHasher()
        scanner = FolderScanner(file_hasher=custom_hasher)

        assert scanner.file_hasher is custom_hasher

    def test_scanner_creates_default_hasher(self) -> None:
        """Test FolderScanner creates a default FileHasher if none provided."""
        scanner = FolderScanner()

        assert scanner.file_hasher is not None
        assert isinstance(scanner.file_hasher, FileHasher)


class TestFolderScannerErrorManagement:
    """Error list management tests."""

    def test_get_errors_returns_copy(self, temp_dir: Path) -> None:
        """Test that get_errors returns a copy of the error list."""
        scanner = FolderScanner()
        scanner.scan_folder(temp_dir / "nonexistent")

        errors1 = scanner.get_errors()
        errors2 = scanner.get_errors()

        assert errors1 == errors2
        assert errors1 is not errors2

    def test_clear_errors(self, temp_dir: Path) -> None:
        """Test that clear_errors empties the error list."""
        scanner = FolderScanner()
        scanner.scan_folder(temp_dir / "nonexistent")

        assert len(scanner.get_errors()) > 0

        scanner.clear_errors()

        assert len(scanner.get_errors()) == 0
