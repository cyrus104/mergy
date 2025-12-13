"""
Unit tests for FileHasher in mergy.scanning.file_hasher.

Tests cover:
- Basic SHA256 hashing functionality
- Empty file handling
- Large file chunked reading
- Binary file support
- Cache behavior
- Short hash extraction
- Error handling (file not found, permission denied)
- Cache clearing
"""

import hashlib
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mergy.scanning import FileHasher


@pytest.mark.unit
class TestFileHasherBasic:
    """Basic FileHasher functionality tests."""

    def test_hash_file_basic(self, temp_base_dir: Path):
        """Hash small text file, verify SHA256 output format."""
        hasher = FileHasher()
        content = "Hello, World! This is test content."

        # Create test file
        test_file = temp_base_dir / "test.txt"
        test_file.write_text(content)

        # Calculate expected hash
        expected_hash = hashlib.sha256(content.encode()).hexdigest()

        # Get hash from FileHasher
        result = hasher.get_hash(test_file)

        assert result == expected_hash
        assert len(result) == 64  # SHA256 produces 64 hex characters
        assert all(c in '0123456789abcdef' for c in result)

    def test_hash_file_empty(self, temp_base_dir: Path):
        """Hash empty file (should produce valid hash)."""
        hasher = FileHasher()

        # Create empty file
        test_file = temp_base_dir / "empty.txt"
        test_file.write_text("")

        # Expected hash for empty content
        expected_hash = hashlib.sha256(b"").hexdigest()

        result = hasher.get_hash(test_file)

        assert result == expected_hash
        assert len(result) == 64

    def test_hash_file_large(self, temp_base_dir: Path):
        """Create 10MB file, verify chunked reading works."""
        hasher = FileHasher()

        # Create a 10MB file with repeating pattern
        test_file = temp_base_dir / "large_file.bin"
        chunk_size = 1024 * 1024  # 1MB chunks
        pattern = b"ABCDEFGHIJ" * 102400  # ~1MB of pattern

        with open(test_file, 'wb') as f:
            for _ in range(10):
                f.write(pattern)

        # Calculate expected hash by reading full file
        with open(test_file, 'rb') as f:
            expected_hash = hashlib.sha256(f.read()).hexdigest()

        result = hasher.get_hash(test_file)

        assert result == expected_hash
        assert len(result) == 64

    def test_hash_file_binary(self, temp_base_dir: Path):
        """Hash binary file (e.g., fake image data)."""
        hasher = FileHasher()

        # Create binary file with non-text data
        test_file = temp_base_dir / "image.bin"
        binary_content = bytes(range(256)) * 100  # All byte values
        test_file.write_bytes(binary_content)

        expected_hash = hashlib.sha256(binary_content).hexdigest()

        result = hasher.get_hash(test_file)

        assert result == expected_hash

    def test_hash_file_with_special_characters(self, temp_base_dir: Path):
        """Hash file containing unicode and special characters."""
        hasher = FileHasher()

        content = "Unicode: \u00e9\u00e8\u00ea \U0001F600 Special: <>\"'&"
        test_file = temp_base_dir / "special.txt"
        test_file.write_text(content, encoding='utf-8')

        # Read as bytes for expected hash
        expected_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()

        result = hasher.get_hash(test_file)

        assert result == expected_hash


@pytest.mark.unit
class TestFileHasherCaching:
    """Tests for FileHasher caching behavior."""

    def test_hash_caching(self, temp_base_dir: Path):
        """Hash same file twice, verify cache hit (no re-read)."""
        hasher = FileHasher()

        test_file = temp_base_dir / "cached.txt"
        test_file.write_text("content to cache")

        # First call - should calculate hash
        hash1 = hasher.get_hash(test_file)

        # Instrument file reads to verify the second call doesn't perform additional I/O
        with patch('builtins.open', wraps=open) as mock_open:
            # Second call - should return cached value without reading the file
            hash2 = hasher.get_hash(test_file)

            # Assert that open was not called (cache hit, no I/O)
            mock_open.assert_not_called()

        assert hash1 == hash2

    def test_hash_cache_different_files(self, temp_base_dir: Path):
        """Verify different files get different hashes."""
        hasher = FileHasher()

        file1 = temp_base_dir / "file1.txt"
        file2 = temp_base_dir / "file2.txt"
        file1.write_text("content one")
        file2.write_text("content two")

        hash1 = hasher.get_hash(file1)
        hash2 = hasher.get_hash(file2)

        # Different content = different hashes
        assert hash1 != hash2

        # Repeat calls to verify consistent behavior (caching works)
        assert hasher.get_hash(file1) == hash1
        assert hasher.get_hash(file2) == hash2

    def test_hash_cache_same_content_different_files(self, temp_base_dir: Path):
        """Files with same content should have same hash."""
        hasher = FileHasher()

        file1 = temp_base_dir / "duplicate1.txt"
        file2 = temp_base_dir / "duplicate2.txt"
        same_content = "identical content"
        file1.write_text(same_content)
        file2.write_text(same_content)

        hash1 = hasher.get_hash(file1)
        hash2 = hasher.get_hash(file2)

        # Same content = same hash
        assert hash1 == hash2

        # Repeat calls to verify consistent behavior
        assert hasher.get_hash(file1) == hash1
        assert hasher.get_hash(file2) == hash2

    def test_clear_cache(self, temp_base_dir: Path):
        """Verify cache clearing functionality."""
        hasher = FileHasher()

        test_file = temp_base_dir / "to_clear.txt"
        test_file.write_text("some content")

        # Get hash before clear
        hash_before = hasher.get_hash(test_file)

        # Clear cache
        hasher.clear_cache()

        # Get hash after clear - should still produce the same value
        hash_after = hasher.get_hash(test_file)

        # Hashes should be the same (content unchanged)
        assert hash_before == hash_after


@pytest.mark.unit
class TestShortHash:
    """Tests for get_short_hash() method."""

    def test_get_short_hash(self, temp_base_dir: Path):
        """Verify 16-character hash prefix extraction."""
        hasher = FileHasher()

        test_file = temp_base_dir / "short_hash.txt"
        test_file.write_text("test content")

        full_hash = hasher.get_hash(test_file)
        short_hash = hasher.get_short_hash(test_file)

        assert len(short_hash) == 16
        assert short_hash == full_hash[:16]

    def test_get_short_hash_from_cache(self, temp_base_dir: Path):
        """Short hash should use cached full hash."""
        hasher = FileHasher()

        test_file = temp_base_dir / "cached_short.txt"
        test_file.write_text("content")

        # Get full hash first (populates cache)
        full_hash = hasher.get_hash(test_file)

        # Short hash should use cached value
        short_hash = hasher.get_short_hash(test_file)

        assert short_hash == full_hash[:16]

    def test_get_short_hash_error_returns_empty(self, temp_base_dir: Path):
        """Short hash returns empty string on error."""
        hasher = FileHasher()

        non_existent = temp_base_dir / "does_not_exist.txt"

        result = hasher.get_short_hash(non_existent)

        assert result == ""


@pytest.mark.unit
class TestFileHasherErrors:
    """Tests for FileHasher error handling."""

    def test_hash_file_not_found(self, temp_base_dir: Path):
        """Test error handling for missing file."""
        hasher = FileHasher()

        non_existent = temp_base_dir / "non_existent_file.txt"

        result = hasher.get_hash(non_existent)

        # Should return empty string on error
        assert result == ""

    def test_hash_file_permission_denied(self, temp_base_dir: Path):
        """
        Verify that FileHasher.get_hash returns an empty string when opening the file raises PermissionError.
        
        Creates a file and patches builtins.open to raise PermissionError during read attempts, then asserts that get_hash returns an empty string.
        """
        hasher = FileHasher()

        test_file = temp_base_dir / "no_permission.txt"
        test_file.write_text("secret content")

        # Mock the open function to raise PermissionError
        with patch('builtins.open', side_effect=PermissionError("Access denied")):
            result = hasher.get_hash(test_file)

        # Should return empty string on permission error
        assert result == ""

    def test_hash_file_os_error(self, temp_base_dir: Path):
        """Test handling of generic OS errors."""
        hasher = FileHasher()

        test_file = temp_base_dir / "os_error.txt"
        test_file.write_text("content")

        # Mock to raise OSError
        with patch('builtins.open', side_effect=OSError("Disk error")):
            result = hasher.get_hash(test_file)

        assert result == ""

    def test_hash_directory_returns_error(self, temp_base_dir: Path):
        """Attempting to hash a directory should handle gracefully."""
        hasher = FileHasher()

        # Create a directory
        test_dir = temp_base_dir / "subdirectory"
        test_dir.mkdir()

        result = hasher.get_hash(test_dir)

        # Should return empty string (IsADirectoryError -> OSError)
        assert result == ""


@pytest.mark.unit
class TestFileHasherPathResolution:
    """Tests for path resolution behavior."""

    def test_hash_relative_path(self, temp_base_dir: Path):
        """Test that relative paths are resolved correctly."""
        hasher = FileHasher()

        # Create file
        test_file = temp_base_dir / "relative.txt"
        test_file.write_text("content")

        # Change to temp directory and use relative path
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_base_dir)
            relative_path = Path("relative.txt")

            hash1 = hasher.get_hash(relative_path)
            hash2 = hasher.get_hash(test_file)  # Absolute path

            # Both should produce same hash
            assert hash1 == hash2
        finally:
            os.chdir(original_cwd)

    def test_hash_symlink(self, temp_base_dir: Path):
        """Test hashing through symlinks."""
        hasher = FileHasher()

        # Create original file
        original = temp_base_dir / "original.txt"
        original.write_text("original content")

        # Create symlink
        symlink = temp_base_dir / "link.txt"
        try:
            symlink.symlink_to(original)
        except OSError:
            pytest.skip("Symlinks not supported on this platform")

        hash_original = hasher.get_hash(original)
        hash_symlink = hasher.get_hash(symlink)

        # Same content via symlink
        assert hash_original == hash_symlink


@pytest.mark.unit
class TestFileHasherChunkSize:
    """Tests related to chunk-based reading."""

    def test_chunk_boundary(self, temp_base_dir: Path):
        """Test file exactly at chunk boundary."""
        hasher = FileHasher()

        # Create file exactly at chunk size (8192 bytes)
        test_file = temp_base_dir / "exact_chunk.bin"
        content = b"X" * FileHasher.CHUNK_SIZE
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = hasher.get_hash(test_file)

        assert result == expected

    def test_multiple_chunks(self, temp_base_dir: Path):
        """Test file spanning multiple chunks."""
        hasher = FileHasher()

        # Create file spanning 3.5 chunks
        test_file = temp_base_dir / "multi_chunk.bin"
        content = b"Y" * int(FileHasher.CHUNK_SIZE * 3.5)
        test_file.write_bytes(content)

        expected = hashlib.sha256(content).hexdigest()
        result = hasher.get_hash(test_file)

        assert result == expected

    def test_one_byte_file(self, temp_base_dir: Path):
        """
        Verify that hashing a file containing a single byte produces the expected SHA-256 hex digest.
        """
        hasher = FileHasher()

        test_file = temp_base_dir / "one_byte.bin"
        test_file.write_bytes(b"A")

        expected = hashlib.sha256(b"A").hexdigest()
        result = hasher.get_hash(test_file)

        assert result == expected