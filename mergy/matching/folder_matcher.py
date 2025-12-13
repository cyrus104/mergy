"""Folder matching implementation for Mergy.

This module provides the FolderMatcher class which implements a tiered
matching algorithm to identify related folders across different computers.

The matching algorithm uses four tiers, evaluated in order of decreasing confidence:
    1. Exact Prefix Match (100% confidence)
    2. Normalized Match (90% confidence)
    3. Token-Based Match (70-90% confidence, scaled by Jaccard similarity)
    4. Fuzzy Match (70-100% confidence, scaled by RapidFuzz similarity)

Example:
    >>> from mergy.matching import FolderMatcher
    >>> from mergy.models import ComputerFolder
    >>> matcher = FolderMatcher(min_confidence=0.7)
    >>> folders = [folder1, folder2, folder3]
    >>> matches = matcher.find_matches(folders)
    >>> for match in matches:
    ...     print(f"{match.base_name}: {match.confidence:.0%}")
"""

import re
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from rapidfuzz import fuzz

from mergy.models import ComputerFolder, FolderMatch, MatchReason


class FolderMatcher:
    """Matches folders based on name similarity using a tiered algorithm.

    The matcher evaluates folder pairs through four tiers of matching,
    returning early on the first successful match. This ensures that
    higher-confidence matches take precedence.

    Attributes:
        min_confidence: Minimum confidence threshold for matches (0.0-1.0).
            Matches below this threshold are filtered out.

    Example:
        >>> matcher = FolderMatcher(min_confidence=0.7)
        >>> matches = matcher.find_matches(folders)
    """

    # Delimiter pattern for splitting folder names
    _DELIMITER_PATTERN = re.compile(r'[-_.\s]+')

    def __init__(self, min_confidence: float = 0.7) -> None:
        """Initialize the FolderMatcher.

        Args:
            min_confidence: Minimum confidence threshold for matches.
                Must be between 0.0 and 1.0. Defaults to 0.7 (70%).

        Raises:
            ValueError: If min_confidence is not between 0.0 and 1.0.
        """
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError(
                f"min_confidence must be between 0.0 and 1.0, got {min_confidence}"
            )
        self.min_confidence = min_confidence

    def find_matches(self, folders: List[ComputerFolder]) -> List[FolderMatch]:
        """Find matching folder groups from a list of folders.

        Performs pairwise comparison of all folders, applies the tiered
        matching algorithm, filters by confidence threshold, and groups
        transitively connected folders.

        Args:
            folders: List of ComputerFolder instances to match.

        Returns:
            List of FolderMatch objects, sorted by confidence (descending).
            Each FolderMatch contains a group of related folders.

        Example:
            >>> folders = [folder1, folder2, folder3]
            >>> matches = matcher.find_matches(folders)
            >>> len(matches)
            2
        """
        if len(folders) < 2:
            return []

        # Collect all pairwise matches
        match_pairs: List[Tuple[ComputerFolder, ComputerFolder, float, MatchReason, str]] = []

        for i in range(len(folders)):
            for j in range(i + 1, len(folders)):
                result = self._try_match_pair(folders[i], folders[j])
                if result is not None:
                    confidence, match_reason, base_name = result
                    if confidence >= self.min_confidence:
                        match_pairs.append(
                            (folders[i], folders[j], confidence, match_reason, base_name)
                        )

        if not match_pairs:
            return []

        return self._group_matches(match_pairs)

    def _try_match_pair(
        self, folder1: ComputerFolder, folder2: ComputerFolder
    ) -> Optional[Tuple[float, MatchReason, str]]:
        """Attempt to match two folders using the tiered algorithm.

        Tries each tier in order, returning immediately on the first
        successful match.

        Args:
            folder1: First folder to compare.
            folder2: Second folder to compare.

        Returns:
            Tuple of (confidence, match_reason, base_name) if matched,
            None if no match found.
        """
        name1 = folder1.name
        name2 = folder2.name

        # Skip identical names
        if name1 == name2:
            return None

        # Tier 1: Exact Prefix Match
        result = self._match_exact_prefix(name1, name2)
        if result is not None:
            confidence, base_name = result
            return (confidence, MatchReason.EXACT_PREFIX, base_name)

        # Tier 2: Normalized Match
        result = self._match_normalized(name1, name2)
        if result is not None:
            confidence, base_name = result
            return (confidence, MatchReason.NORMALIZED, base_name)

        # Tier 3: Token-Based Match
        result = self._match_token_based(name1, name2)
        if result is not None:
            confidence, base_name = result
            return (confidence, MatchReason.TOKEN_MATCH, base_name)

        # Tier 4: Fuzzy Match
        result = self._match_fuzzy(name1, name2)
        if result is not None:
            confidence, base_name = result
            return (confidence, MatchReason.FUZZY_MATCH, base_name)

        return None

    def _match_exact_prefix(
        self, name1: str, name2: str
    ) -> Optional[Tuple[float, str]]:
        """Tier 1: Check for exact prefix match.

        A match occurs when one name is an exact prefix of the other,
        followed by a delimiter (-, _, ., space) or end of string.

        Args:
            name1: First folder name.
            name2: Second folder name.

        Returns:
            Tuple of (1.0, shorter_name) if match found, None otherwise.

        Example:
            >>> matcher._match_exact_prefix("135897-ntp", "135897-ntp.newspace")
            (1.0, "135897-ntp")
        """
        if not name1 or not name2:
            return None

        # Determine which is shorter/longer
        if len(name1) <= len(name2):
            shorter, longer = name1, name2
        else:
            shorter, longer = name2, name1

        # Check if shorter is prefix of longer
        if not longer.startswith(shorter):
            return None

        # If they're the same length, it's not a prefix match
        if len(shorter) == len(longer):
            return None

        # Check that the character after the prefix is a delimiter
        next_char = longer[len(shorter)]
        if next_char not in '-_. ':
            return None

        return (1.0, shorter)

    def _match_normalized(
        self, name1: str, name2: str
    ) -> Optional[Tuple[float, str]]:
        """Tier 2: Check for normalized match.

        Names are normalized by replacing all delimiters with spaces.
        If the normalized forms are equal, it's a match.

        Args:
            name1: First folder name.
            name2: Second folder name.

        Returns:
            Tuple of (0.9, normalized_name) if match found, None otherwise.

        Example:
            >>> matcher._match_normalized(
            ...     "192.168.1.5-computer01",
            ...     "192.168.1.5 computer01"
            ... )
            (0.9, "192.168.1.5 computer01")
        """
        if not name1 or not name2:
            return None

        # Normalize by replacing all delimiters with single space
        normalized1 = self._DELIMITER_PATTERN.sub(' ', name1).strip()
        normalized2 = self._DELIMITER_PATTERN.sub(' ', name2).strip()

        # Guard: ensure normalized values are non-empty and contain alphanumeric characters
        # This prevents delimiter-only names (e.g., '---', '___') from producing matches
        if not normalized1 or not normalized2:
            return None
        if not any(ch.isalnum() for ch in normalized1):
            return None
        if not any(ch.isalnum() for ch in normalized2):
            return None

        # If original names would match in Tier 1, skip here
        if name1 == name2:
            return None

        if normalized1 == normalized2:
            return (0.9, normalized1)

        return None

    def _match_token_based(
        self, name1: str, name2: str
    ) -> Optional[Tuple[float, str]]:
        """Tier 3: Check for token-based match using Jaccard similarity.

        Names are split into tokens, and Jaccard similarity is calculated.
        If similarity >= 0.5, confidence is scaled from 0.7 to 0.9.

        Scaling formula: 0.7 + (jaccard - 0.5) * 0.4

        Args:
            name1: First folder name.
            name2: Second folder name.

        Returns:
            Tuple of (scaled_confidence, longer_name) if Jaccard >= 0.5,
            None otherwise.

        Example:
            >>> matcher._match_token_based(
            ...     "backup-folder-2024",
            ...     "folder-backup-2024"
            ... )
            (0.9, "backup-folder-2024")  # High Jaccard overlap
        """
        if not name1 or not name2:
            return None

        # Extract tokens
        tokens1 = set(
            t.lower() for t in self._DELIMITER_PATTERN.split(name1) if t
        )
        tokens2 = set(
            t.lower() for t in self._DELIMITER_PATTERN.split(name2) if t
        )

        if not tokens1 or not tokens2:
            return None

        # Calculate Jaccard similarity
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        if union == 0:
            return None

        jaccard = intersection / union

        # Threshold: Jaccard >= 0.5
        if jaccard < 0.5:
            return None

        # Scale confidence: 0.7 at 0.5 similarity, 0.9 at 1.0 similarity
        # Formula: 0.7 + (jaccard - 0.5) * 0.4
        confidence = 0.7 + (jaccard - 0.5) * 0.4

        # Use longer name as base name
        base_name = name1 if len(name1) >= len(name2) else name2

        return (confidence, base_name)

    # Pattern to extract trailing numeric segment from a name
    _TRAILING_NUMERIC_PATTERN = re.compile(r'^(.*?)(\d+)$')
    # Pattern to extract trailing alphanumeric suffix after a delimiter
    _TRAILING_SUFFIX_PATTERN = re.compile(r'^(.+[-_.])([a-zA-Z0-9]+)$')

    def _match_fuzzy(
        self, name1: str, name2: str
    ) -> Optional[Tuple[float, str]]:
        """Tier 4: Check for fuzzy match using RapidFuzz.

        Uses token_sort_ratio for comparison. If similarity >= 85%,
        confidence is scaled from 0.5 to 1.0.

        This method is conservative for near-identical names that differ
        only in numeric suffixes (e.g., 'computer01' vs 'computer02') to
        avoid matching sequentially numbered devices.

        Scaling formula: 0.7 + (similarity - 0.85) * 2

        Args:
            name1: First folder name.
            name2: Second folder name.

        Returns:
            Tuple of (scaled_confidence, alphabetically_first_name)
            if similarity >= 0.85, None otherwise.

        Example:
            >>> matcher._match_fuzzy("comptuer01", "computer01")
            (0.85, "comptuer01")  # Typo correction
        """
        if not name1 or not name2:
            return None

        # Check if both names share the same non-numeric prefix but differ in numeric suffix
        # This avoids matching sequentially numbered devices like 'computer01' and 'computer02'
        match1 = self._TRAILING_NUMERIC_PATTERN.match(name1)
        match2 = self._TRAILING_NUMERIC_PATTERN.match(name2)
        if match1 and match2:
            prefix1, num1 = match1.groups()
            prefix2, num2 = match2.groups()
            # If prefixes are identical (case-insensitive) but numbers differ, reject
            if prefix1.lower() == prefix2.lower() and num1 != num2:
                return None

        # Also check for names with same prefix but different short suffixes after delimiter
        # This avoids matching 'folder-a' and 'folder-b' which differ only by suffix
        suffix_match1 = self._TRAILING_SUFFIX_PATTERN.match(name1)
        suffix_match2 = self._TRAILING_SUFFIX_PATTERN.match(name2)
        if suffix_match1 and suffix_match2:
            prefix1, suffix1 = suffix_match1.groups()
            prefix2, suffix2 = suffix_match2.groups()
            # If prefixes are identical (case-insensitive) but short suffixes differ, reject
            if prefix1.lower() == prefix2.lower() and suffix1.lower() != suffix2.lower():
                # Only reject if suffixes are short (1-2 characters) to avoid false negatives
                if len(suffix1) <= 2 and len(suffix2) <= 2:
                    return None

        # RapidFuzz returns 0-100
        ratio = fuzz.token_sort_ratio(name1, name2)
        similarity = ratio / 100.0

        # Threshold: similarity >= 0.85 (increased from 0.7 to be more conservative)
        if similarity < 0.85:
            return None

        # Scale confidence: 0.7 at 0.85 similarity, 1.0 at 1.0 similarity
        # Formula: 0.7 + (similarity - 0.85) * 2
        confidence = 0.7 + (similarity - 0.85) * 2

        # Cap at 1.0
        confidence = min(confidence, 1.0)

        # Use alphabetically first name for consistency
        base_name = min(name1, name2)

        return (confidence, base_name)

    def _group_matches(
        self,
        match_pairs: List[Tuple[ComputerFolder, ComputerFolder, float, MatchReason, str]]
    ) -> List[FolderMatch]:
        """Group transitively connected folder pairs into match groups.

        Uses Union-Find algorithm to identify connected components.
        Each component becomes a FolderMatch with the highest confidence
        and corresponding match reason from any pair in the group.

        Args:
            match_pairs: List of tuples (folder1, folder2, confidence,
                match_reason, base_name) representing matched pairs.

        Returns:
            List of FolderMatch objects sorted by confidence (descending).
        """
        if not match_pairs:
            return []

        # Build Union-Find structure
        # Map folders to indices for union-find
        folder_to_idx: Dict[ComputerFolder, int] = {}
        idx_to_folder: Dict[int, ComputerFolder] = {}

        for folder1, folder2, _, _, _ in match_pairs:
            if folder1 not in folder_to_idx:
                idx = len(folder_to_idx)
                folder_to_idx[folder1] = idx
                idx_to_folder[idx] = folder1
            if folder2 not in folder_to_idx:
                idx = len(folder_to_idx)
                folder_to_idx[folder2] = idx
                idx_to_folder[idx] = folder2

        n = len(folder_to_idx)
        parent = list(range(n))
        rank = [0] * n

        def find(x: int) -> int:
            """Find with path compression."""
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            """Union by rank."""
            px, py = find(x), find(y)
            if px == py:
                return
            if rank[px] < rank[py]:
                px, py = py, px
            parent[py] = px
            if rank[px] == rank[py]:
                rank[px] += 1

        # Track best match info per pair for later use
        pair_info: Dict[Tuple[int, int], Tuple[float, MatchReason, str]] = {}

        for folder1, folder2, confidence, reason, base_name in match_pairs:
            idx1 = folder_to_idx[folder1]
            idx2 = folder_to_idx[folder2]
            union(idx1, idx2)

            # Store pair info (use sorted tuple as key)
            key = (min(idx1, idx2), max(idx1, idx2))
            if key not in pair_info or confidence > pair_info[key][0]:
                pair_info[key] = (confidence, reason, base_name)

        # Group folders by their root
        groups: Dict[int, Set[int]] = defaultdict(set)
        for idx in range(n):
            root = find(idx)
            groups[root].add(idx)

        # Build FolderMatch objects
        results: List[FolderMatch] = []

        for root, member_indices in groups.items():
            # Get all folders in this group
            folders = sorted(
                [idx_to_folder[idx] for idx in member_indices],
                key=lambda f: f.name
            )

            # Find the best (highest confidence) match in this group
            best_confidence = 0.0
            best_reason = MatchReason.FUZZY_MATCH
            base_names: List[str] = []

            for (idx1, idx2), (conf, reason, bname) in pair_info.items():
                if find(idx1) == root:
                    base_names.append(bname)
                    if conf > best_confidence:
                        best_confidence = conf
                        best_reason = reason

            # Determine base name: most common, or shortest as fallback
            if base_names:
                # Count occurrences
                name_counts: Dict[str, int] = defaultdict(int)
                for name in base_names:
                    name_counts[name] += 1
                # Get most common
                base_name = max(name_counts.keys(), key=lambda n: (name_counts[n], -len(n)))
            else:
                base_name = min(f.name for f in folders)

            results.append(FolderMatch(
                folders=folders,
                confidence=best_confidence,
                match_reason=best_reason,
                base_name=base_name
            ))

        # Sort by confidence descending
        results.sort(key=lambda m: -m.confidence)

        return results
