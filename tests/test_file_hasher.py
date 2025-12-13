"""Unit tests for FileHasher class."""

import hashlib
import os
import platform
import time
from pathlib import Path
from unittest.mock import mock_open, patch

import pytest

from mergy.scanning import FileHasher


class TestFileHasherBasic:
    """Basic functionality tests for FileHasher."""

    def test_hash_file_normal(self, temp_dir: Path) -> None:
        """Test hashing a regular file produces correct SHA256."""
        test_file = temp_dir / "test.txt"
        content = b"Hello, World!"
        test_file.write_bytes(content)

        expected_hash = hashlib.sha256(content).hexdigest()

        hasher = FileHasher()
        result = hasher.hash_file(test_file)

        assert result == expected_hash

    def test_hash_file_empty(self, temp_dir: Path) -> None:
        """Test hashing an empty file returns SHA256 of empty string."""
        empty_file = temp_dir / "empty.txt"
        empty_file.touch()

        expected_hash = hashlib.sha256(b"").hexdigest()

        hasher = FileHasher()
        result = hasher.hash_file(empty_file)

        assert result == expected_hash

    def test_hash_file_large(self, sample_files: dict[str, Path]) -> None:
        """Test hashing a large file (10MB) works correctly with chunked reading."""
        large_file = sample_files["large"]

        # Compute expected hash
        expected_hash = hashlib.sha256(b"c" * (10 * 1024 * 1024)).hexdigest()

        hasher = FileHasher()
        result = hasher.hash_file(large_file)

        assert result == expected_hash


class TestFileHasherCaching:
    """Cache-related tests for FileHasher."""

    def test_hash_caching(self, temp_dir: Path) -> None:
        """Test that hashing same file twice uses cache on second call."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"test content")

        hasher = FileHasher()

        # First hash - cache miss
        result1 = hasher.hash_file(test_file)
        stats1 = hasher.get_cache_stats()
        assert stats1["misses"] == 1
        assert stats1["hits"] == 0

        # Second hash - cache hit
        result2 = hasher.hash_file(test_file)
        stats2 = hasher.get_cache_stats()
        assert stats2["misses"] == 1
        assert stats2["hits"] == 1

        # Results should be identical
        assert result1 == result2

    def test_hash_cache_invalidation(self, temp_dir: Path) -> None:
        """Test that modifying file (changing mtime) invalidates cache."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"original content")

        hasher = FileHasher()

        # First hash
        result1 = hasher.hash_file(test_file)

        # Small delay to ensure mtime changes
        time.sleep(0.1)

        # Modify file - this changes mtime
        test_file.write_bytes(b"modified content")

        # Second hash should be a cache miss due to new mtime
        result2 = hasher.hash_file(test_file)
        stats = hasher.get_cache_stats()

        assert result1 != result2
        assert stats["misses"] == 2  # Both should be misses

    def test_clear_cache(self, temp_dir: Path) -> None:
        """Test that clearing cache empties it and resets counters."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"test content")

        hasher = FileHasher()

        # Populate cache
        hasher.hash_file(test_file)
        stats_before = hasher.get_cache_stats()
        assert stats_before["size"] == 1
        assert stats_before["misses"] == 1

        # Clear cache
        hasher.clear_cache()
        stats_after = hasher.get_cache_stats()

        assert stats_after["size"] == 0
        assert stats_after["hits"] == 0
        assert stats_after["misses"] == 0

    def test_concurrent_hashing(self, temp_dir: Path) -> None:
        """Test hashing multiple different files caches all correctly."""
        files = []
        for i in range(5):
            f = temp_dir / f"file{i}.txt"
            f.write_bytes(f"content {i}".encode())
            files.append(f)

        hasher = FileHasher()

        # Hash all files
        hashes = [hasher.hash_file(f) for f in files]

        stats = hasher.get_cache_stats()
        assert stats["size"] == 5
        assert stats["misses"] == 5
        assert stats["hits"] == 0

        # All hashes should be unique and not None
        assert len(set(hashes)) == 5
        assert None not in hashes


class TestFileHasherErrors:
    """Error handling tests for FileHasher."""

    def test_hash_file_not_found(self, temp_dir: Path) -> None:
        """Test hashing non-existent file returns None and logs error."""
        nonexistent = temp_dir / "nonexistent.txt"

        hasher = FileHasher()
        result = hasher.hash_file(nonexistent)

        assert result is None
        errors = hasher.get_errors()
        assert len(errors) == 1
        assert "not found" in errors[0].lower() or "File not found" in errors[0]

    @pytest.mark.skipif(
        platform.system() == "Windows",
        reason="Permission handling differs on Windows",
    )
    def test_hash_file_permission_denied(self, restricted_file: Path | None) -> None:
        """Test hashing file without read permissions returns None and logs error."""
        if restricted_file is None:
            pytest.skip("Restricted file fixture not available")

        hasher = FileHasher()
        result = hasher.hash_file(restricted_file)

        assert result is None
        errors = hasher.get_errors()
        assert len(errors) >= 1
        assert any("permission" in e.lower() for e in errors)

    def test_hash_corrupted_file(self, temp_dir: Path) -> None:
        """Test handling I/O error during file reading (mocked)."""
        test_file = temp_dir / "test.txt"
        test_file.write_bytes(b"test content")

        hasher = FileHasher()

        # Mock open to raise OSError when reading
        with patch("builtins.open", side_effect=OSError("Simulated I/O error")):
            result = hasher.hash_file(test_file)

        assert result is None
        errors = hasher.get_errors()
        assert len(errors) >= 1


class TestFileHasherSymlinks:
    """Symlink handling tests for FileHasher."""

    def test_hash_file_symlink(self, symlink_file: Path | None, temp_dir: Path) -> None:
        """Test hashing a symlink follows it and hashes the target file."""
        if symlink_file is None:
            pytest.skip("Symlinks not supported on this platform")

        # Get target file path and compute expected hash
        target_file = temp_dir / "target.txt"
        expected_hash = hashlib.sha256(target_file.read_bytes()).hexdigest()

        hasher = FileHasher()
        result = hasher.hash_file(symlink_file)

        assert result == expected_hash


class TestFileHasherErrorManagement:
    """Error list management tests."""

    def test_get_errors_returns_copy(self, temp_dir: Path) -> None:
        """Test that get_errors returns a copy of the error list."""
        hasher = FileHasher()
        hasher.hash_file(temp_dir / "nonexistent.txt")

        errors1 = hasher.get_errors()
        errors2 = hasher.get_errors()

        # Should be equal but not the same object
        assert errors1 == errors2
        assert errors1 is not errors2

    def test_clear_errors(self, temp_dir: Path) -> None:
        """Test that clear_errors empties the error list."""
        hasher = FileHasher()
        hasher.hash_file(temp_dir / "nonexistent.txt")

        assert len(hasher.get_errors()) > 0

        hasher.clear_errors()

        assert len(hasher.get_errors()) == 0
