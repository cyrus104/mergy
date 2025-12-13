"""Folder matching package for Mergy.

This package contains the FolderMatcher implementation for identifying
related folders across different computers based on name similarity.

Example:
    >>> from mergy.matching import FolderMatcher
    >>> from mergy.models import ComputerFolder
    >>> matcher = FolderMatcher(min_confidence=0.7)
    >>> folders = [folder1, folder2, folder3]
    >>> matches = matcher.find_matches(folders)
    >>> for match in matches:
    ...     print(f"{match.base_name}: {match.confidence:.0%}")
"""

from .folder_matcher import FolderMatcher

__all__ = [
    "FolderMatcher",
]
