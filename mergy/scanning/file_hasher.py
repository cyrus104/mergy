"""File hashing utility with caching support.

This module provides the FileHasher class for computing SHA256 hashes of files
with an in-memory cache to avoid redundant hashing operations.

Example:
    >>> from mergy.scanning import FileHasher
    >>> hasher = FileHasher()
    >>> hash_value = hasher.hash_file(Path("/path/to/file.txt"))
    >>> if hash_value:
    ...     print(f"SHA256: {hash_value}")
"""

import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Buffer size for chunked file reading (8KB)
CHUNK_SIZE = 8192


class FileHasher:
    """Computes SHA256 hashes of files with caching support.

    This class provides efficient file hashing by maintaining an in-memory cache
    keyed by (file_path, modification_time) tuples. This ensures that:
    - Files are not re-hashed unnecessarily when accessed multiple times
    - Modified files are automatically re-hashed (cache invalidation via mtime)

    The hasher uses chunked reading (8KB chunks) to efficiently handle large files
    without loading them entirely into memory.

    Attributes:
        _cache: Dictionary mapping (path, mtime) tuples to SHA256 hex digests.
        _errors: List of error messages encountered during hashing operations.
        _cache_hits: Counter for cache hits (for debugging/statistics).
        _cache_misses: Counter for cache misses (for debugging/statistics).

    Example:
        >>> hasher = FileHasher()
        >>> hash1 = hasher.hash_file(Path("file.txt"))
        >>> hash2 = hasher.hash_file(Path("file.txt"))  # Uses cache
        >>> stats = hasher.get_cache_stats()
        >>> print(f"Hits: {stats['hits']}, Misses: {stats['misses']}")
    """

    def __init__(self) -> None:
        """Initialize the FileHasher with an empty cache."""
        self._cache: Dict[Tuple[Path, float], str] = {}
        self._errors: List[str] = []
        self._cache_hits: int = 0
        self._cache_misses: int = 0

    def hash_file(self, file_path: Path) -> Optional[str]:
        """Compute the SHA256 hash of a file.

        This method first checks if the file exists and is readable, then looks
        up the cache using the file's path and modification time. If a cache hit
        occurs, the cached hash is returned. Otherwise, the file is read in chunks
        and its SHA256 hash is computed, cached, and returned.

        Args:
            file_path: Path to the file to hash.

        Returns:
            The SHA256 hex digest of the file, or None if an error occurred.
            Errors include: file not found, permission denied, I/O errors.

        Example:
            >>> hasher = FileHasher()
            >>> result = hasher.hash_file(Path("/path/to/file.txt"))
            >>> if result is None:
            ...     print("Failed to hash file")
            ... else:
            ...     print(f"Hash: {result}")
        """
        try:
            # Resolve the path to handle symlinks
            resolved_path = file_path.resolve()

            # Check if file exists and get its stats
            if not resolved_path.exists():
                self._errors.append(f"File not found: {file_path}")
                return None

            if not resolved_path.is_file():
                self._errors.append(f"Not a file: {file_path}")
                return None

            # Get modification time for cache key
            stat_result = resolved_path.stat()
            mtime = stat_result.st_mtime

            # Check cache using (path, mtime) key
            cache_key = (resolved_path, mtime)
            if cache_key in self._cache:
                self._cache_hits += 1
                return self._cache[cache_key]

            # Cache miss - compute hash
            self._cache_misses += 1
            hash_value = self._compute_hash(resolved_path)

            if hash_value is not None:
                self._cache[cache_key] = hash_value

            return hash_value

        except PermissionError:
            self._errors.append(f"Permission denied: {file_path}")
            return None
        except FileNotFoundError:
            self._errors.append(f"File not found: {file_path}")
            return None
        except OSError as e:
            self._errors.append(f"OS error reading {file_path}: {e}")
            return None

    def _compute_hash(self, file_path: Path) -> Optional[str]:
        """Compute SHA256 hash by reading file in chunks.

        Args:
            file_path: Resolved path to the file to hash.

        Returns:
            The SHA256 hex digest, or None if an error occurred.
        """
        try:
            sha256_hash = hashlib.sha256()

            with open(file_path, "rb") as f:
                # Read file in chunks to handle large files efficiently
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    sha256_hash.update(chunk)

            return sha256_hash.hexdigest()

        except PermissionError:
            self._errors.append(f"Permission denied reading: {file_path}")
            return None
        except OSError as e:
            self._errors.append(f"Error reading {file_path}: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the internal hash cache.

        This removes all cached hash values and resets the hit/miss counters.
        Useful for testing or when files may have been modified externally.

        Example:
            >>> hasher = FileHasher()
            >>> hasher.hash_file(Path("file.txt"))
            >>> hasher.clear_cache()
            >>> stats = hasher.get_cache_stats()
            >>> assert stats['size'] == 0
        """
        self._cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics for debugging and monitoring.

        Returns:
            Dictionary containing:
            - 'size': Number of entries in the cache
            - 'hits': Number of cache hits
            - 'misses': Number of cache misses

        Example:
            >>> hasher = FileHasher()
            >>> hasher.hash_file(Path("file.txt"))  # miss
            >>> hasher.hash_file(Path("file.txt"))  # hit
            >>> stats = hasher.get_cache_stats()
            >>> print(stats)  # {'size': 1, 'hits': 1, 'misses': 1}
        """
        return {
            "size": len(self._cache),
            "hits": self._cache_hits,
            "misses": self._cache_misses,
        }

    def get_errors(self) -> List[str]:
        """Get list of errors encountered during hashing operations.

        Returns:
            List of error message strings.

        Example:
            >>> hasher = FileHasher()
            >>> hasher.hash_file(Path("/nonexistent/file.txt"))
            >>> errors = hasher.get_errors()
            >>> print(errors[0])  # 'File not found: /nonexistent/file.txt'
        """
        return self._errors.copy()

    def clear_errors(self) -> None:
        """Clear the list of accumulated errors."""
        self._errors.clear()
