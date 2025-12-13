"""
Folder matching algorithm implementation.

This module contains the FolderMatcher class which implements the four-tier
matching algorithm for identifying related folders across computer backups.
"""

import re
from typing import List, Optional

from rapidfuzz import fuzz

from mergy.models import ComputerFolder, FolderMatch, MatchReason


class FolderMatcher:
    """
    Implements the four-tier folder matching algorithm.

    Tiers (in order of evaluation):
    1. Exact Prefix Match (100% confidence)
    2. Normalized Match (90% confidence)
    3. Token Match (70% confidence, scaled by similarity)
    4. Fuzzy Match (50% confidence, scaled by similarity)
    """

    # Pattern for normalizing folder names (replace delimiters with single space)
    DELIMITER_PATTERN = re.compile(r'[-_.\s]+')

    # Pattern for extracting tokens from folder names
    TOKEN_PATTERN = re.compile(r'[a-zA-Z0-9]+')

    def __init__(self, min_confidence: float = 70.0):
        """
        Initialize the FolderMatcher.

        Args:
            min_confidence: Minimum confidence threshold for matches (0-100).
        """
        self.min_confidence = min_confidence

    def find_matches(self, folders: List[ComputerFolder]) -> List[FolderMatch]:
        """
        Find all matching folder groups from a list of folders.

        Args:
            folders: List of ComputerFolder instances to analyze.

        Returns:
            List of FolderMatch instances above the confidence threshold.
        """
        matches: List[FolderMatch] = []
        matched_indices: set = set()

        for i, folder1 in enumerate(folders):
            if i in matched_indices:
                continue

            group = [folder1]
            group_reason: Optional[MatchReason] = None
            group_confidence = 0.0
            group_base_name = folder1.name

            for j, folder2 in enumerate(folders[i + 1:], start=i + 1):
                if j in matched_indices:
                    continue

                match_result = self._match_pair(folder1, folder2)
                if match_result is not None:
                    confidence, reason, base_name = match_result
                    if confidence >= self.min_confidence:
                        group.append(folder2)
                        matched_indices.add(j)
                        # Use highest confidence match for the group
                        if confidence > group_confidence:
                            group_confidence = confidence
                            group_reason = reason
                            group_base_name = base_name

            if len(group) > 1:
                matched_indices.add(i)
                matches.append(FolderMatch(
                    folders=group,
                    confidence=group_confidence,
                    match_reason=group_reason,
                    base_name=group_base_name
                ))

        return matches

    def _match_pair(
        self, folder1: ComputerFolder, folder2: ComputerFolder
    ) -> Optional[tuple[float, MatchReason, str]]:
        """
        Attempt to match two folders using the four-tier algorithm.

        Returns:
            Tuple of (confidence, reason, base_name) if matched, None otherwise.
        """
        name1 = folder1.name
        name2 = folder2.name

        # Tier 1: Exact Prefix Match (100% confidence)
        result = self._exact_prefix_match(name1, name2)
        if result is not None:
            return result

        # Tier 2: Normalized Match (90% confidence)
        result = self._normalized_match(name1, name2)
        if result is not None:
            return result

        # Tier 3: Token Match (70% confidence, scaled)
        result = self._token_match(name1, name2)
        if result is not None:
            return result

        # Tier 4: Fuzzy Match (50% confidence, scaled)
        result = self._fuzzy_match(name1, name2)
        if result is not None:
            return result

        return None

    def _exact_prefix_match(
        self, name1: str, name2: str
    ) -> Optional[tuple[float, MatchReason, str]]:
        """
        Tier 1: Check if one name is an exact prefix of the other.

        Validates that the prefix ends at a delimiter boundary.
        Confidence: 100%

        Example: "135897-ntp" matches "135897-ntp.newspace"
        """
        # Determine which is shorter (the potential prefix)
        if len(name1) <= len(name2):
            prefix, longer = name1, name2
        else:
            prefix, longer = name2, name1

        # Check if prefix matches the start of longer name
        if longer.startswith(prefix):
            # Validate delimiter boundary (next char should be a delimiter)
            if len(longer) == len(prefix):
                # Exact match, not a prefix relationship
                return (100.0, MatchReason.EXACT_PREFIX, prefix)

            next_char = longer[len(prefix)]
            if next_char in '-_.':
                return (100.0, MatchReason.EXACT_PREFIX, prefix)

        return None

    def _normalized_match(
        self, name1: str, name2: str
    ) -> Optional[tuple[float, MatchReason, str]]:
        """
        Tier 2: Match after normalizing delimiters.

        Normalizes by replacing -, _, ., and space with a single space.
        Confidence: 90%

        Example: "192.168.1.5-computer01" matches "192.168.1.5 computer01"
        """
        normalized1 = self.DELIMITER_PATTERN.sub(' ', name1).strip().lower()
        normalized2 = self.DELIMITER_PATTERN.sub(' ', name2).strip().lower()

        if normalized1 == normalized2:
            # Use the shorter original name as base
            base_name = name1 if len(name1) <= len(name2) else name2
            return (90.0, MatchReason.NORMALIZED, base_name)

        return None

    def _token_match(
        self, name1: str, name2: str
    ) -> Optional[tuple[float, MatchReason, str]]:
        """
        Tier 3: Token-based matching using Jaccard similarity.

        Extracts tokens and compares using set intersection/union ratio.
        Confidence: 70% base, scaled by Jaccard similarity.

        Example: "computer01" matches "192.168.1.5-computer01"
        """
        tokens1 = set(self.TOKEN_PATTERN.findall(name1.lower()))
        tokens2 = set(self.TOKEN_PATTERN.findall(name2.lower()))

        if not tokens1 or not tokens2:
            return None

        intersection = tokens1 & tokens2
        union = tokens1 | tokens2

        if not union:
            return None

        jaccard = len(intersection) / len(union)

        # Scale confidence: 70% * jaccard similarity
        # Only return if similarity is meaningful (at least 50% token overlap)
        if jaccard >= 0.5:
            confidence = 70.0 * jaccard
            # Use the name with fewer tokens as base
            base_name = name1 if len(tokens1) <= len(tokens2) else name2
            return (confidence, MatchReason.TOKEN_MATCH, base_name)

        return None

    def _fuzzy_match(
        self, name1: str, name2: str
    ) -> Optional[tuple[float, MatchReason, str]]:
        """
        Tier 4: Fuzzy matching using Levenshtein distance.

        Uses rapidfuzz's token_sort_ratio for spelling variations.
        Confidence: 50% base, scaled by similarity ratio.

        Example: "comptuer01" matches "computer01"
        """
        # Use token_sort_ratio for better handling of word order variations
        similarity = fuzz.token_sort_ratio(name1.lower(), name2.lower())

        # Similarity is 0-100, we scale by 50% (the base confidence for fuzzy)
        # Only return if similarity is high enough (at least 80% similar)
        if similarity >= 80:
            confidence = 50.0 * (similarity / 100.0)
            # Use shorter name as base
            base_name = name1 if len(name1) <= len(name2) else name2
            return (confidence, MatchReason.FUZZY_MATCH, base_name)

        return None

    def match_folders(
        self, folder1: ComputerFolder, folder2: ComputerFolder
    ) -> Optional[FolderMatch]:
        """
        Match two specific folders and return a FolderMatch if they match.

        Args:
            folder1: First folder to compare.
            folder2: Second folder to compare.

        Returns:
            FolderMatch if the folders match above threshold, None otherwise.
        """
        result = self._match_pair(folder1, folder2)
        if result is not None:
            confidence, reason, base_name = result
            if confidence >= self.min_confidence:
                return FolderMatch(
                    folders=[folder1, folder2],
                    confidence=confidence,
                    match_reason=reason,
                    base_name=base_name
                )
        return None
