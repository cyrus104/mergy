"""File scanning package for Mergy.

This package provides utilities for scanning folders and computing file hashes.
It contains two main classes:

- FileHasher: Computes SHA256 hashes of files with caching support for
  efficient deduplication operations.
- FolderScanner: Scans folders to collect metadata (file counts, sizes,
  date ranges) for ComputerFolder instances.

Example:
    >>> from mergy.scanning import FileHasher, FolderScanner
    >>> from pathlib import Path
    >>>
    >>> # Scan folders
    >>> scanner = FolderScanner()
    >>> folders = scanner.scan_immediate_subdirectories(Path("/data"))
    >>>
    >>> # Hash files for deduplication
    >>> hasher = FileHasher()
    >>> hash_value = hasher.hash_file(Path("/data/file.txt"))
"""

from .file_hasher import FileHasher
from .folder_scanner import FolderScanner

__all__ = ["FileHasher", "FolderScanner"]
