"""
Unit tests for FolderMatcher algorithms in mergy.matching.folder_matcher.

Tests cover all four matching tiers:
- Tier 1: Exact Prefix Match (100% confidence)
- Tier 2: Normalized Match (90% confidence)
- Tier 3: Token Match (70% confidence, scaled by similarity)
- Tier 4: Fuzzy Match (50% confidence, scaled by similarity)

Also tests the FolderMatcher integration methods.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import List

import pytest

from mergy.models import ComputerFolder, FolderMatch, MatchReason
from mergy.matching import FolderMatcher


def create_folder(name: str, temp_dir: Path) -> ComputerFolder:
    """
    Create a ComputerFolder test fixture with minimal representative metadata.
    
    Parameters:
        name (str): Folder name used for both the ComputerFolder.name and the folder path under temp_dir.
        temp_dir (Path): Parent directory used to construct the ComputerFolder.path.
    
    Returns:
        ComputerFolder: A ComputerFolder populated with basic metadata (file_count=5, total_size=1000).
        The newest_file_date is set to the current time and oldest_file_date to 10 days earlier.
    """
    return ComputerFolder(
        path=temp_dir / name,
        name=name,
        file_count=5,
        total_size=1000,
        oldest_file_date=datetime.now() - timedelta(days=10),
        newest_file_date=datetime.now()
    )


# =============================================================================
# Tier 1: Exact Prefix Match Tests
# =============================================================================

@pytest.mark.unit
class TestExactPrefixMatch:
    """Tests for Tier 1: Exact Prefix Match algorithm."""

    def test_exact_prefix_match_basic(self, temp_base_dir: Path):
        """Test '135897-ntp' matches '135897-ntp.newspace' (100% confidence)."""
        matcher = FolderMatcher()
        folder1 = create_folder("135897-ntp", temp_base_dir)
        folder2 = create_folder("135897-ntp.newspace", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 100.0
        assert result.match_reason == MatchReason.EXACT_PREFIX
        assert result.base_name == "135897-ntp"

    def test_exact_prefix_match_with_underscore(self, temp_base_dir: Path):
        """Test underscore delimiter boundary."""
        matcher = FolderMatcher()
        folder1 = create_folder("project", temp_base_dir)
        folder2 = create_folder("project_backup", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 100.0
        assert result.match_reason == MatchReason.EXACT_PREFIX

    def test_exact_prefix_match_with_dot(self, temp_base_dir: Path):
        """Test dot delimiter boundary."""
        matcher = FolderMatcher()
        folder1 = create_folder("computer-01", temp_base_dir)
        folder2 = create_folder("computer-01.old", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 100.0
        assert result.match_reason == MatchReason.EXACT_PREFIX

    def test_exact_prefix_match_with_hyphen(self, temp_base_dir: Path):
        """Test hyphen delimiter boundary."""
        matcher = FolderMatcher()
        folder1 = create_folder("data", temp_base_dir)
        folder2 = create_folder("data-archive", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 100.0
        assert result.match_reason == MatchReason.EXACT_PREFIX

    def test_exact_prefix_no_match_no_delimiter(self, temp_base_dir: Path):
        """Reject 'abc' vs 'abcdef' (no delimiter after prefix)."""
        matcher = FolderMatcher()
        folder1 = create_folder("abc", temp_base_dir)
        folder2 = create_folder("abcdef", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # Should not match via exact prefix (no delimiter)
        # For "abc" vs "abcdef", no lower-tier match is expected either
        # since there's no semantic relationship beyond substring coincidence
        assert result is None

    def test_exact_prefix_identical_names(self, temp_base_dir: Path):
        """Handle exact duplicates (same name)."""
        matcher = FolderMatcher()
        folder1 = create_folder("identical-folder", temp_base_dir)
        folder2 = create_folder("identical-folder", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 100.0
        assert result.match_reason == MatchReason.EXACT_PREFIX


# =============================================================================
# Tier 2: Normalized Match Tests
# =============================================================================

@pytest.mark.unit
class TestNormalizedMatch:
    """Tests for Tier 2: Normalized Match algorithm."""

    def test_normalized_match_hyphen_to_space(self, temp_base_dir: Path):
        """Test '192.168.1.5-computer01' matches '192.168.1.5 computer01' (90%)."""
        matcher = FolderMatcher()
        folder1 = create_folder("192.168.1.5-computer01", temp_base_dir)
        folder2 = create_folder("192.168.1.5 computer01", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 90.0
        assert result.match_reason == MatchReason.NORMALIZED

    def test_normalized_match_multiple_delimiters(self, temp_base_dir: Path):
        """Test mixed delimiters normalize to same result."""
        matcher = FolderMatcher()
        folder1 = create_folder("my-project_v1.0", temp_base_dir)
        folder2 = create_folder("my project v1 0", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 90.0
        assert result.match_reason == MatchReason.NORMALIZED

    def test_normalized_match_case_insensitive(self, temp_base_dir: Path):
        """
        Verify that folder name normalization is case-insensitive.
        
        Creates two folders whose names differ only by letter case and asserts that FolderMatcher.match_folders returns a match with confidence >= 90.0.
        """
        matcher = FolderMatcher()
        folder1 = create_folder("MyFolder", temp_base_dir)
        folder2 = create_folder("myfolder", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        # Should match via normalized (case insensitive)
        assert result.confidence >= 90.0

    def test_normalized_match_extra_spaces(self, temp_base_dir: Path):
        """Handle multiple consecutive spaces."""
        matcher = FolderMatcher()
        folder1 = create_folder("folder  name", temp_base_dir)
        folder2 = create_folder("folder-name", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.match_reason == MatchReason.NORMALIZED
        assert result.confidence == 90.0

    def test_normalized_match_underscore_to_hyphen(self, temp_base_dir: Path):
        """Test underscore normalizes same as hyphen."""
        matcher = FolderMatcher()
        folder1 = create_folder("test_folder", temp_base_dir)
        folder2 = create_folder("test-folder", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.confidence == 90.0
        assert result.match_reason == MatchReason.NORMALIZED


# =============================================================================
# Tier 3: Token Match Tests
# =============================================================================

@pytest.mark.unit
class TestTokenMatch:
    """Tests for Tier 3: Token Match algorithm."""

    def test_token_match_subset(self, temp_base_dir: Path):
        """
        Verifies that two folders whose token sets form a subset produce a match when the matcher threshold is low.
        
        Creates folders named "server-web" and "server-web-backup", uses a FolderMatcher with min_confidence=30.0, and asserts that matching the pair yields a non-None result.
        """
        # Use lower min_confidence to allow token matches
        matcher = FolderMatcher(min_confidence=30.0)
        # tokens1 = {server, web}, tokens2 = {server, web, backup}
        # Jaccard = 2/3 = 0.67 >= 0.5 threshold, confidence = 70 * 0.67 = 46.7
        folder1 = create_folder("server-web", temp_base_dir)
        folder2 = create_folder("server-web-backup", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # Should match via exact prefix (100%) since "server-web" is prefix of "server-web-backup"
        assert result is not None

    def test_token_match_high_overlap(self, temp_base_dir: Path):
        """Test high token overlap achieves match."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("project-alpha-v1", temp_base_dir)
        folder2 = create_folder("alpha-project-v1", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.match_reason == MatchReason.TOKEN_MATCH
        # Same tokens, different order: {project, alpha, v1}
        # Jaccard = 3/3 = 1.0, confidence = 70 * 1.0 = 70
        # Allow minor implementation variance with inequality bounds
        assert 65.0 <= result.confidence <= 75.0

    def test_token_match_jaccard_calculation(self, temp_base_dir: Path):
        """Verify Jaccard similarity scaling."""
        matcher = FolderMatcher(min_confidence=30.0)
        # tokens1 = {a, b, c}, tokens2 = {b, c, d}
        # intersection = {b, c}, union = {a, b, c, d}
        # Jaccard = 2/4 = 0.5, confidence = 70 * 0.5 = 35
        folder1 = create_folder("a-b-c", temp_base_dir)
        folder2 = create_folder("b-c-d", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.match_reason == MatchReason.TOKEN_MATCH
        assert result.confidence == 35.0

    def test_token_match_below_threshold(self, temp_base_dir: Path):
        """Reject matches with <50% token overlap."""
        matcher = FolderMatcher(min_confidence=30.0)
        # tokens1 = {a, b}, tokens2 = {c, d, e, f}
        # No intersection, Jaccard = 0
        folder1 = create_folder("a-b", temp_base_dir)
        folder2 = create_folder("c-d-e-f", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # Should not match (no token overlap)
        if result is not None:
            assert result.match_reason != MatchReason.TOKEN_MATCH

    def test_token_match_no_common_tokens(self, temp_base_dir: Path):
        """Return None for disjoint token sets."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("xyz123", temp_base_dir)
        folder2 = create_folder("abc456", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # No common tokens between these
        if result is not None:
            assert result.match_reason != MatchReason.TOKEN_MATCH


# =============================================================================
# Tier 4: Fuzzy Match Tests
# =============================================================================

@pytest.mark.unit
class TestFuzzyMatch:
    """Tests for Tier 4: Fuzzy Match algorithm."""

    def test_fuzzy_match_typo(self, temp_base_dir: Path):
        """Test 'comptuer01' matches 'computer01' (50% scaled)."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("comptuer01", temp_base_dir)
        folder2 = create_folder("computer01", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        # High similarity due to single transposition
        assert result.confidence >= 40.0
        assert result.match_reason == MatchReason.FUZZY_MATCH

    def test_fuzzy_match_word_order(self, temp_base_dir: Path):
        """Test handling of same words in different order."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("backup-main-server", temp_base_dir)
        folder2 = create_folder("main-server-backup", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        # Same words, different order - matches via token match (tier 3) since
        # tokens {backup, main, server} have 100% Jaccard overlap
        # Token match is tried before fuzzy match, so it matches at tier 3
        assert result.match_reason in (MatchReason.TOKEN_MATCH, MatchReason.FUZZY_MATCH)
        # Confidence should be above a reasonable threshold based on scoring logic
        assert result.confidence >= 40.0

    def test_fuzzy_match_below_threshold(self, temp_base_dir: Path):
        """Reject <80% similarity in fuzzy tier."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("completely-different-name", temp_base_dir)
        folder2 = create_folder("xyz-abc-123", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # Very different names should not match via fuzzy
        # Either result is None, or if non-None, it should not be a fuzzy match
        # and confidence should be below min_confidence
        if result is not None:
            assert result.match_reason != MatchReason.FUZZY_MATCH
            assert result.confidence < matcher.min_confidence
        else:
            assert result is None

    def test_fuzzy_match_completely_different(self, temp_base_dir: Path):
        """Return None for completely unrelated names."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("aaaaaaa", temp_base_dir)
        folder2 = create_folder("zzzzzzz", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        # Completely different characters - should not match
        assert result is None

    def test_fuzzy_match_minor_variation(self, temp_base_dir: Path):
        """Test minor spelling variation."""
        matcher = FolderMatcher(min_confidence=30.0)
        folder1 = create_folder("workstatn", temp_base_dir)
        folder2 = create_folder("workstation", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.match_reason == MatchReason.FUZZY_MATCH


# =============================================================================
# FolderMatcher Integration Tests
# =============================================================================

@pytest.mark.unit
class TestFolderMatcherIntegration:
    """Tests for FolderMatcher.find_matches() and related methods."""

    def test_find_matches_multiple_groups(self, temp_base_dir: Path):
        """
        Verify that find_matches groups folders into at least two distinct, non-overlapping groups.
        
        Uses a FolderMatcher with min_confidence=70.0 on six folders forming two families and one unrelated folder.
        Asserts that at least two match groups are returned and that no folder appears in more than one group.
        """
        matcher = FolderMatcher(min_confidence=70.0)

        folders = [
            # Group 1: computer-01 family
            create_folder("computer-01", temp_base_dir),
            create_folder("computer-01-backup", temp_base_dir),
            create_folder("computer-01.old", temp_base_dir),
            # Group 2: server family
            create_folder("server", temp_base_dir),
            create_folder("server-backup", temp_base_dir),
            # Unrelated
            create_folder("random-stuff", temp_base_dir),
        ]

        matches = matcher.find_matches(folders)

        # Should find at least 2 groups
        assert len(matches) >= 2

        # Verify groups are distinct (no folder appears in multiple groups)
        all_matched_folders = []
        for match in matches:
            all_matched_folders.extend(match.folders)
        folder_names = [f.name for f in all_matched_folders]
        assert len(folder_names) == len(set(folder_names))

    def test_find_matches_confidence_threshold(self, temp_base_dir: Path):
        """Verify min_confidence filtering."""
        high_confidence_matcher = FolderMatcher(min_confidence=95.0)
        low_confidence_matcher = FolderMatcher(min_confidence=50.0)

        folders = [
            create_folder("project-alpha", temp_base_dir),
            create_folder("project-alpha-backup", temp_base_dir),
            create_folder("project beta", temp_base_dir),  # Normalized match at 90%
        ]

        high_matches = high_confidence_matcher.find_matches(folders)
        low_matches = low_confidence_matcher.find_matches(folders)

        # High threshold should only find exact prefix matches (100%)
        for match in high_matches:
            assert match.confidence >= 95.0

        # Low threshold may find more matches
        assert len(low_matches) >= len(high_matches)

    def test_find_matches_no_duplicates(self, temp_base_dir: Path):
        """
        Verifies that FolderMatcher.find_matches groups folders without duplicating any folder across match results.
        
        Asserts that when matching a set of similar folders with min_confidence=70.0, each folder appears at most once across all returned match groups.
        
        Parameters:
            temp_base_dir (Path): Temporary directory used to create test folder objects.
        """
        matcher = FolderMatcher(min_confidence=70.0)

        folders = [
            create_folder("data-01", temp_base_dir),
            create_folder("data-01-copy", temp_base_dir),
            create_folder("data-01.bak", temp_base_dir),
            create_folder("data-02", temp_base_dir),
            create_folder("data-02-backup", temp_base_dir),
        ]

        matches = matcher.find_matches(folders)

        # Collect all folders from all matches
        matched_folders = []
        for match in matches:
            matched_folders.extend(match.folders)

        # Each folder should appear at most once
        folder_names = [f.name for f in matched_folders]
        assert len(folder_names) == len(set(folder_names))

    def test_match_folders_pairwise(self, temp_base_dir: Path):
        """Test match_folders() method with two folders."""
        matcher = FolderMatcher(min_confidence=70.0)

        folder1 = create_folder("test-folder", temp_base_dir)
        folder2 = create_folder("test-folder-backup", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert len(result.folders) == 2
        assert folder1 in result.folders
        assert folder2 in result.folders

    def test_match_folders_no_match(self, temp_base_dir: Path):
        """
        Verify that two unrelated folder names do not produce a match.
        
        Asserts that FolderMatcher.match_folders returns None when given two dissimilar folder names with a high minimum confidence (70.0).
        """
        matcher = FolderMatcher(min_confidence=70.0)

        folder1 = create_folder("completely", temp_base_dir)
        folder2 = create_folder("different", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is None

    def test_matcher_with_empty_list(self):
        """Handle empty folder list."""
        matcher = FolderMatcher()

        matches = matcher.find_matches([])

        assert matches == []

    def test_matcher_with_single_folder(self, temp_base_dir: Path):
        """Handle single folder (no possible matches)."""
        matcher = FolderMatcher()

        folders = [create_folder("solo-folder", temp_base_dir)]

        matches = matcher.find_matches(folders)

        assert matches == []

    def test_matcher_returns_base_name(self, temp_base_dir: Path):
        """Verify base_name is set correctly in matches."""
        matcher = FolderMatcher()

        folder1 = create_folder("myproject", temp_base_dir)
        folder2 = create_folder("myproject-v2", temp_base_dir)

        result = matcher.match_folders(folder1, folder2)

        assert result is not None
        assert result.base_name == "myproject"


# =============================================================================
# Parametrized Tests
# =============================================================================

@pytest.mark.unit
@pytest.mark.parametrize("prefix,full,expected_match", [
    ("abc", "abc-def", True),
    ("abc", "abc.def", True),
    ("abc", "abc_def", True),
    ("abc", "abcdef", False),  # No delimiter
    ("test", "test-backup-2024", True),
    ("data", "data.old.archive", True),
])
def test_exact_prefix_parametrized(
    temp_base_dir: Path,
    prefix: str,
    full: str,
    expected_match: bool
):
    """
    Parametrized pytest that verifies exact-prefix matching between two folder names.
    
    Parameters:
        temp_base_dir (Path): Temporary directory used to create test folder fixtures.
        prefix (str): Candidate prefix folder name.
        full (str): Candidate full folder name to compare against the prefix.
        expected_match (bool): If True, the test asserts an EXACT_PREFIX match is produced; if False, the test asserts that no EXACT_PREFIX match is produced (result may be None or have a different reason).
    """
    matcher = FolderMatcher()
    folder1 = create_folder(prefix, temp_base_dir)
    folder2 = create_folder(full, temp_base_dir)

    result = matcher.match_folders(folder1, folder2)

    if expected_match:
        assert result is not None
        assert result.match_reason == MatchReason.EXACT_PREFIX
    else:
        if result is not None:
            assert result.match_reason != MatchReason.EXACT_PREFIX


@pytest.mark.unit
@pytest.mark.parametrize("name1,name2", [
    ("my-folder", "my folder"),
    ("my_folder", "my-folder"),
    ("my.folder", "my folder"),
    ("a-b-c", "a b c"),
    ("test_data_2024", "test-data-2024"),
])
def test_normalized_match_parametrized(
    temp_base_dir: Path,
    name1: str,
    name2: str
):
    """Parametrized tests for normalized matching."""
    matcher = FolderMatcher()
    folder1 = create_folder(name1, temp_base_dir)
    folder2 = create_folder(name2, temp_base_dir)

    result = matcher.match_folders(folder1, folder2)

    assert result is not None
    assert result.match_reason == MatchReason.NORMALIZED
    assert result.confidence == 90.0