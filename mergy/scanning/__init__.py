"""
Scanning package for the Computer Data Organization Tool.

This package provides file and folder scanning capabilities:
- FileHasher: SHA256-based file comparison with caching
- FolderScanner: Collecting folder metadata from directories
"""

from mergy.scanning.file_hasher import FileHasher
from mergy.scanning.folder_scanner import FolderScanner

__all__ = ["FileHasher", "FolderScanner"]
