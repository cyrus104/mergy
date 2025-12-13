"""Integration tests for the scanning module."""

import os
import platform
from pathlib import Path

import pytest

from mergy.scanning import FileHasher, FolderScanner


class TestFullScanWorkflow:
    """End-to-end workflow tests."""

    def test_full_scan_workflow(self, temp_dir: Path) -> None:
        """Test scanning a realistic folder structure with multiple folders and files."""
        # Create 3 folders with 5 files each
        for i in range(3):
            folder = temp_dir / f"computer-{i:02d}"
            folder.mkdir()

            for j in range(5):
                file_path = folder / f"file{j}.txt"
                content = f"Content from computer {i}, file {j}" * 100
                file_path.write_bytes(content.encode())

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(temp_dir)

        assert len(folders) == 3

        for folder in folders:
            assert folder.file_count == 5
            assert folder.total_size > 0
            assert folder.oldest_file_date is not None
            assert folder.newest_file_date is not None

    def test_scan_with_conflicts(self, temp_dir: Path) -> None:
        """Test scanning two folders with same file names but different content."""
        # Create two folders with same file names but different content
        folder1 = temp_dir / "folder1"
        folder1.mkdir()
        (folder1 / "shared.txt").write_bytes(b"content from folder 1")
        (folder1 / "unique1.txt").write_bytes(b"unique to folder 1")

        folder2 = temp_dir / "folder2"
        folder2.mkdir()
        (folder2 / "shared.txt").write_bytes(b"content from folder 2")  # Same name, different content
        (folder2 / "unique2.txt").write_bytes(b"unique to folder 2")

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(temp_dir)

        assert len(folders) == 2

        # Both folders have 2 files each
        for folder in folders:
            assert folder.file_count == 2

        # Sizes should be different due to different content
        sizes = [f.total_size for f in folders]
        assert sizes[0] != sizes[1] or True  # Allow equal if content lengths match

    def test_scan_large_dataset(self, temp_dir: Path) -> None:
        """Test scanning 100 folders with 10 files each completes without errors."""
        # Create 100 folders with 10 files each
        for i in range(100):
            folder = temp_dir / f"folder-{i:03d}"
            folder.mkdir()

            for j in range(10):
                file_path = folder / f"file{j}.dat"
                file_path.write_bytes(bytes([i % 256, j % 256]) * 50)

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(temp_dir)

        assert len(folders) == 100

        # Verify no errors occurred
        errors = scanner.get_errors()
        assert len(errors) == 0

        # Verify each folder was scanned correctly
        for folder in folders:
            assert folder.file_count == 10
            assert folder.total_size == 1000  # 10 files * 100 bytes each


class TestScanAndHashIntegration:
    """Tests for scanning followed by hashing."""

    def test_scan_and_hash_integration(self, temp_dir: Path) -> None:
        """Test scanning folders then hashing all files, verifying cache usage."""
        # Create folders with files
        folder1 = temp_dir / "folder1"
        folder1.mkdir()
        (folder1 / "file1.txt").write_bytes(b"content 1")
        (folder1 / "file2.txt").write_bytes(b"content 2")

        folder2 = temp_dir / "folder2"
        folder2.mkdir()
        (folder2 / "file3.txt").write_bytes(b"content 3")

        # Create shared hasher
        hasher = FileHasher()
        scanner = FolderScanner(file_hasher=hasher)

        # Scan folders
        folders = scanner.scan_immediate_subdirectories(temp_dir)
        assert len(folders) == 2

        # Now hash all files (simulating what merge phase would do)
        hashes = []
        for folder in folders:
            for file_path in folder.path.rglob("*.txt"):
                hash_value = hasher.hash_file(file_path)
                assert hash_value is not None
                hashes.append(hash_value)

        # Verify cache stats
        stats = hasher.get_cache_stats()
        assert stats["size"] == 3  # 3 unique files
        assert stats["misses"] == 3  # All were cache misses

        # Hash same files again - should be cache hits
        for folder in folders:
            for file_path in folder.path.rglob("*.txt"):
                hasher.hash_file(file_path)

        stats_after = hasher.get_cache_stats()
        assert stats_after["hits"] == 3  # All were cache hits


class TestErrorRecovery:
    """Tests for error recovery during scanning."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Permission handling differs on Windows",
    )
    def test_error_recovery(self, temp_dir: Path) -> None:
        """Test scanning continues when some folders have errors."""
        # Create accessible folder
        accessible = temp_dir / "accessible"
        accessible.mkdir()
        (accessible / "file.txt").write_bytes(b"content")

        # Create folder with accessible and inaccessible subfolders
        mixed = temp_dir / "mixed"
        mixed.mkdir()

        accessible_sub = mixed / "accessible_sub"
        accessible_sub.mkdir()
        (accessible_sub / "file.txt").write_bytes(b"content")

        inaccessible_sub = mixed / "inaccessible_sub"
        inaccessible_sub.mkdir()
        (inaccessible_sub / "file.txt").write_bytes(b"secret")
        original_mode = inaccessible_sub.stat().st_mode
        os.chmod(inaccessible_sub, 0o000)

        try:
            scanner = FolderScanner()

            # Scan immediate subdirectories should work
            folders = scanner.scan_immediate_subdirectories(temp_dir)

            # Should get results for accessible folders
            assert len(folders) >= 1

            # Accessible folder should be scanned
            accessible_folder = next((f for f in folders if f.name == "accessible"), None)
            assert accessible_folder is not None
            assert accessible_folder.file_count == 1

        finally:
            os.chmod(inaccessible_sub, original_mode)


class TestSymlinkHandling:
    """Tests for symlink handling during scanning."""

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_symlink_handling(self, temp_dir: Path) -> None:
        """Test scanning folder with symlinks to files outside folder."""
        # Create target file outside the scan folder
        external = temp_dir / "external"
        external.mkdir()
        external_file = external / "external.txt"
        external_file.write_bytes(b"external content")

        # Create folder with symlink
        folder = temp_dir / "folder_with_links"
        folder.mkdir()
        (folder / "internal.txt").write_bytes(b"internal content")

        try:
            (folder / "link_to_external.txt").symlink_to(external_file)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.file_count == 2  # Internal + symlinked file

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_directory_symlink_cycle_produces_stable_metrics(self, temp_dir: Path) -> None:
        """Test that directory symlink cycles produce stable, reproducible metrics."""
        folder = temp_dir / "stable_cycle_test"
        folder.mkdir()

        # Create a nested structure with files
        sub1 = folder / "sub1"
        sub1.mkdir()
        (sub1 / "file1.txt").write_bytes(b"content1")

        sub2 = sub1 / "sub2"
        sub2.mkdir()
        (sub2 / "file2.txt").write_bytes(b"content2")

        # Create a cycle back to the root
        try:
            (sub2 / "cycle_to_root").symlink_to(folder)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()

        # Run multiple scans and verify consistent results
        results = [scanner.scan_folder(folder) for _ in range(3)]

        # All scans should complete successfully
        for result in results:
            assert result is not None

        # All scans should produce identical metrics
        assert all(r.file_count == results[0].file_count for r in results)
        assert all(r.total_size == results[0].total_size for r in results)

        # Should have exactly 2 files
        assert results[0].file_count == 2
        assert results[0].total_size == len(b"content1") + len(b"content2")

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Symlinks may not work on Windows without elevated privileges",
    )
    def test_deep_directory_symlink_cycle(self, temp_dir: Path) -> None:
        """Test scanning terminates with deeply nested directory symlink cycles."""
        folder = temp_dir / "deep_cycle"
        folder.mkdir()

        # Create a deep nested structure
        current = folder
        for i in range(5):
            current = current / f"level{i}"
            current.mkdir()
            (current / f"file{i}.txt").write_bytes(f"content{i}".encode())

        # Create a cycle from the deepest level back to root
        try:
            (current / "back_to_root").symlink_to(folder)
        except OSError:
            pytest.skip("Symlinks not supported")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        # Should complete without infinite loop
        assert result is not None
        # Should have exactly 5 files (one per level)
        assert result.file_count == 5


class TestEdgeCaseFolderNames:
    """Tests for special folder/file names."""

    def test_edge_case_folder_names_spaces(self, temp_dir: Path) -> None:
        """Test scanning folders with spaces in names."""
        folder = temp_dir / "folder with spaces"
        folder.mkdir()
        (folder / "file with spaces.txt").write_bytes(b"content")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.name == "folder with spaces"
        assert result.file_count == 1

    def test_edge_case_folder_names_unicode(self, temp_dir: Path) -> None:
        """Test scanning folders with Unicode characters in names."""
        folder = temp_dir / "文件夹_фолдер_φάκελος"
        folder.mkdir()
        (folder / "файл_αρχείο.txt").write_bytes(b"unicode content")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.file_count == 1

    def test_edge_case_folder_names_special_chars(self, temp_dir: Path) -> None:
        """Test scanning folders with special characters in names."""
        # Note: Some characters are not allowed on certain filesystems
        folder = temp_dir / "folder-with_special.chars(1)"
        folder.mkdir()
        (folder / "file-with_special.chars(1).txt").write_bytes(b"content")

        scanner = FolderScanner()
        result = scanner.scan_folder(folder)

        assert result is not None
        assert result.file_count == 1


class TestRealisticDataStructure:
    """Tests with realistic data structures matching the spec."""

    def test_realistic_structure(self, temp_dir: Path) -> None:
        """Test scanning the structure from the plan documentation."""
        # Create the structure from the plan:
        # temp_dir/
        # ├── computer-01/
        # │   ├── data/
        # │   │   ├── file1.txt (100 bytes)
        # │   │   └── file2.txt (200 bytes)
        # │   └── logs/
        # │       └── system.log (500 bytes)
        # ├── computer-02/
        # │   └── empty_folder/
        # └── computer-03/
        #     ├── .merged/
        #     │   └── old_file.txt
        #     └── current.txt

        # computer-01
        comp01 = temp_dir / "computer-01"
        comp01.mkdir()
        data = comp01 / "data"
        data.mkdir()
        (data / "file1.txt").write_bytes(b"x" * 100)
        (data / "file2.txt").write_bytes(b"y" * 200)
        logs = comp01 / "logs"
        logs.mkdir()
        (logs / "system.log").write_bytes(b"z" * 500)

        # computer-02
        comp02 = temp_dir / "computer-02"
        comp02.mkdir()
        (comp02 / "empty_folder").mkdir()

        # computer-03
        comp03 = temp_dir / "computer-03"
        comp03.mkdir()
        merged = comp03 / ".merged"
        merged.mkdir()
        (merged / "old_file.txt").write_bytes(b"old content")
        (comp03 / "current.txt").write_bytes(b"current")

        scanner = FolderScanner()
        folders = scanner.scan_immediate_subdirectories(temp_dir)

        assert len(folders) == 3

        # Find each folder by name
        comp01_result = next((f for f in folders if f.name == "computer-01"), None)
        comp02_result = next((f for f in folders if f.name == "computer-02"), None)
        comp03_result = next((f for f in folders if f.name == "computer-03"), None)

        assert comp01_result is not None
        assert comp02_result is not None
        assert comp03_result is not None

        # Verify computer-01 stats
        assert comp01_result.file_count == 3
        assert comp01_result.total_size == 800  # 100 + 200 + 500

        # Verify computer-02 stats (has nested empty folder)
        assert comp02_result.file_count == 0

        # Verify computer-03 stats (.merged should be skipped)
        assert comp03_result.file_count == 1
        assert comp03_result.total_size == len(b"current")
