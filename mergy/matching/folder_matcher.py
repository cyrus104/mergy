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
        Create a FolderMatcher configured with the minimum confidence required to accept matches.
        
        Parameters:
            min_confidence (float): Minimum confidence threshold for accepting a match, in the range 0–100.
        """
        self.min_confidence = min_confidence

    def find_matches(self, folders: List[ComputerFolder]) -> List[FolderMatch]:
        """
        Identify groups of related folders from the provided list using the matcher’s configured thresholds.
        
        Scans the list in order, seeding groups from the first unmatched folder and adding later folders that meet or exceed the matcher’s min_confidence. For each group with more than one folder, the group's representative base_name and match_reason are taken from the highest-confidence pair found while grouping; folders included in a group are not considered again as group seeds.
        
        Parameters:
            folders (List[ComputerFolder]): Folders to analyze; the input order determines group-seeding precedence.
        
        Returns:
            List[FolderMatch]: FolderMatch objects for each identified group containing more than one folder whose computed confidence meets or exceeds min_confidence.
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
        Attempt to match two folders using the class's four-tier matching algorithm.
        
        Tries tiers in order: exact prefix, normalized, token-based (Jaccard), and fuzzy (token-sort) and returns the first successful match.
        
        Returns:
            (confidence, reason, base_name) tuple when a tier produces a match, `None` otherwise.
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
        Determine whether one folder name is an exact prefix of the other at a delimiter boundary.
        
        Compares the two provided folder names; if one is identical to the start of the other and either the names are equal in length or the character following the prefix in the longer name is a delimiter (`-`, `_`, `.`), this is considered an exact prefix match.
        
        Parameters:
            name1 (str): First folder name to compare.
            name2 (str): Second folder name to compare.
        
        Returns:
            tuple[float, MatchReason, str] | None: A tuple `(confidence, reason, base_name)` with `confidence` set to `100.0`, `reason` set to `MatchReason.EXACT_PREFIX`, and `base_name` equal to the prefix used when a match is found; `None` if no exact-prefix match exists.
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
        Determine whether two folder names are equal after normalizing delimiter characters.
        
        Normalizes sequences of '-', '_', '.', or whitespace to a single space, trims and lowercases both names before comparing.
        
        Returns:
            A tuple (90.0, MatchReason.NORMALIZED, base_name) when the normalized names are equal, `None` otherwise. `base_name` is the shorter of the two original input names.
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
        Compute a token-based similarity score between two folder names using Jaccard similarity.
        
        If both names contain alphanumeric tokens and their Jaccard similarity is at least 0.5, returns a tuple with a confidence scaled from a 70% base by the Jaccard value, the TOKEN_MATCH reason, and the original name that has fewer tokens as the base. Returns `None` if either name has no tokens or the Jaccard similarity is below 0.5.
        
        Returns:
            (confidence, MatchReason.TOKEN_MATCH, base_name): 
                - confidence (float): 70.0 multiplied by the Jaccard similarity (range >0.0 up to 70.0).
                - base_name (str): the original input name that contains fewer tokens.
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
        Compute a fuzzy match between two folder names and return match details when they meet the fuzzy-tier threshold.
        
        Uses a token-sorted fuzzy similarity measure; if the measured similarity is at least 80, returns a tuple containing the confidence, the `MatchReason.FUZZY_MATCH` reason, and a chosen base name. The confidence equals 50.0 multiplied by the similarity fraction (similarity / 100.0). The base name is the shorter of the two original inputs.
        
        Returns:
            tuple[float, MatchReason, str]: (confidence, MatchReason.FUZZY_MATCH, base_name) when similarity >= 80, `None` otherwise.
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
        Compare two folders and return a FolderMatch when their match confidence meets the matcher's threshold.
        
        Parameters:
            folder1 (ComputerFolder): First folder to compare.
            folder2 (ComputerFolder): Second folder to compare.
        
        Returns:
            FolderMatch: Contains both folders, the computed confidence, match reason, and base name when confidence >= min_confidence.
            None: If the computed confidence is below the matcher's threshold or no match is found.
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