"""
SHA256 file hashing with caching for the Computer Data Organization Tool.

This module provides FileHasher class for calculating SHA256 hashes with
in-memory caching to prevent redundant calculations when comparing files
across multiple folders.
"""

from pathlib import Path
from typing import Dict
import hashlib
import logging

# Configure module logger
logger = logging.getLogger(__name__)


class FileHasher:
    """
    Calculates SHA256 hashes for files with in-memory caching.

    The cache prevents redundant calculations when comparing files
    across multiple folders, significantly improving performance for
    duplicate detection.
    """

    # Chunk size for reading large files (8KB)
    CHUNK_SIZE = 8192

    def __init__(self) -> None:
        """Initialize empty hash cache dictionary."""
        self._cache: Dict[Path, str] = {}

    def get_hash(self, file_path: Path) -> str:
        """
        Return cached hash or calculate new one.

        Args:
            file_path: Path to the file to hash.

        Returns:
            Full 64-character SHA256 hex digest, or empty string on error.
        """
        # Resolve to absolute path for consistent caching
        resolved_path = file_path.resolve()

        # Check cache first
        if resolved_path in self._cache:
            return self._cache[resolved_path]

        # Calculate hash
        try:
            hash_value = self._calculate_hash(resolved_path)
            self._cache[resolved_path] = hash_value
            return hash_value
        except FileNotFoundError:
            logger.error(f"File not found: {file_path}")
            return ""
        except PermissionError:
            logger.error(f"Permission denied: {file_path}")
            return ""
        except OSError as e:
            logger.error(f"OS error reading {file_path}: {e}")
            return ""

    def _calculate_hash(self, file_path: Path) -> str:
        """
        Calculate SHA256 hash for a file using chunked reading.

        Args:
            file_path: Path to the file to hash.

        Returns:
            Full 64-character SHA256 hex digest.
        """
        sha256 = hashlib.sha256()

        with open(file_path, 'rb') as f:
            while chunk := f.read(self.CHUNK_SIZE):
                sha256.update(chunk)

        return sha256.hexdigest()

    def get_short_hash(self, file_path: Path) -> str:
        """
        Return first 16 characters of hash for filename suffixes.

        Args:
            file_path: Path to the file to hash.

        Returns:
            First 16 characters of SHA256 hex digest, or empty string on error.
        """
        full_hash = self.get_hash(file_path)
        return full_hash[:16] if full_hash else ""

    def clear_cache(self) -> None:
        """Clear the hash cache (useful for testing or memory management)."""
        self._cache.clear()
