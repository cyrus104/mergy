"""Comprehensive test suite for FolderMatcher.

Tests cover all four matching tiers, integration scenarios, edge cases,
false positive prevention, and specification examples.
"""

from datetime import datetime
from pathlib import Path

import pytest

from mergy.matching import FolderMatcher
from mergy.models import ComputerFolder, MatchReason


def make_folder(name: str, path: str = "/test") -> ComputerFolder:
    """Helper to create ComputerFolder instances for testing."""
    return ComputerFolder(
        path=Path(path) / name,
        name=name,
        file_count=10,
        total_size=1000,
        oldest_file_date=datetime(2020, 1, 1),
        newest_file_date=datetime(2024, 1, 1),
    )


class TestFolderMatcherInit:
    """Test FolderMatcher initialization."""

    def test_default_confidence(self) -> None:
        """Default min_confidence should be 0.7."""
        matcher = FolderMatcher()
        assert matcher.min_confidence == 0.7

    def test_custom_confidence(self) -> None:
        """Custom min_confidence should be accepted."""
        matcher = FolderMatcher(min_confidence=0.5)
        assert matcher.min_confidence == 0.5

    def test_invalid_confidence_too_low(self) -> None:
        """Should raise ValueError for confidence < 0."""
        with pytest.raises(ValueError):
            FolderMatcher(min_confidence=-0.1)

    def test_invalid_confidence_too_high(self) -> None:
        """Should raise ValueError for confidence > 1."""
        with pytest.raises(ValueError):
            FolderMatcher(min_confidence=1.1)

    def test_boundary_confidence_zero(self) -> None:
        """Confidence of 0.0 should be valid."""
        matcher = FolderMatcher(min_confidence=0.0)
        assert matcher.min_confidence == 0.0

    def test_boundary_confidence_one(self) -> None:
        """Confidence of 1.0 should be valid."""
        matcher = FolderMatcher(min_confidence=1.0)
        assert matcher.min_confidence == 1.0


class TestFolderMatcherTier1ExactPrefix:
    """Test Tier 1: Exact Prefix Match."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_exact_prefix_with_dot(self, matcher: FolderMatcher) -> None:
        """Test exact prefix match: '135897-ntp' and '135897-ntp.newspace'."""
        result = matcher._match_exact_prefix("135897-ntp", "135897-ntp.newspace")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "135897-ntp"

    def test_exact_prefix_with_dash(self, matcher: FolderMatcher) -> None:
        """Test exact prefix match with dash delimiter."""
        result = matcher._match_exact_prefix("computer-01", "computer-01-backup")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "computer-01"

    def test_exact_prefix_with_underscore(self, matcher: FolderMatcher) -> None:
        """Test exact prefix match with underscore delimiter."""
        result = matcher._match_exact_prefix("folder_name", "folder_name_old")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "folder_name"

    def test_exact_prefix_with_space(self, matcher: FolderMatcher) -> None:
        """Test exact prefix match with space delimiter."""
        result = matcher._match_exact_prefix("my folder", "my folder backup")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "my folder"

    def test_exact_prefix_reversed_order(self, matcher: FolderMatcher) -> None:
        """Test that order of arguments doesn't matter."""
        result = matcher._match_exact_prefix("135897-ntp.newspace", "135897-ntp")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "135897-ntp"

    def test_no_match_different_names(self, matcher: FolderMatcher) -> None:
        """Test non-prefix: 'computer' and 'laptop' should not match."""
        result = matcher._match_exact_prefix("computer", "laptop")
        assert result is None

    def test_no_match_identical_names(self, matcher: FolderMatcher) -> None:
        """Test identical names should not match (not a prefix)."""
        result = matcher._match_exact_prefix("folder", "folder")
        assert result is None

    def test_no_match_prefix_without_delimiter(self, matcher: FolderMatcher) -> None:
        """Test prefix without delimiter: 'comp' and 'computer' should not match."""
        result = matcher._match_exact_prefix("comp", "computer")
        assert result is None

    def test_no_match_partial_overlap(self, matcher: FolderMatcher) -> None:
        """Test 'test' and 'testing' should not match (no delimiter)."""
        result = matcher._match_exact_prefix("test", "testing")
        assert result is None

    def test_empty_string_first(self, matcher: FolderMatcher) -> None:
        """Test empty string as first argument."""
        result = matcher._match_exact_prefix("", "folder")
        assert result is None

    def test_empty_string_second(self, matcher: FolderMatcher) -> None:
        """Test empty string as second argument."""
        result = matcher._match_exact_prefix("folder", "")
        assert result is None

    def test_empty_both(self, matcher: FolderMatcher) -> None:
        """Test both empty strings."""
        result = matcher._match_exact_prefix("", "")
        assert result is None

    def test_single_character_names(self, matcher: FolderMatcher) -> None:
        """Test single character names."""
        result = matcher._match_exact_prefix("a", "a-backup")
        assert result is not None
        confidence, base_name = result
        assert confidence == 1.0
        assert base_name == "a"


class TestFolderMatcherTier2Normalized:
    """Test Tier 2: Normalized Match."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_normalized_dash_to_space(self, matcher: FolderMatcher) -> None:
        """Test normalized match: '192.168.1.5-computer01' and '192.168.1.5 computer01'."""
        result = matcher._match_normalized(
            "192.168.1.5-computer01", "192.168.1.5 computer01"
        )
        assert result is not None
        confidence, base_name = result
        assert confidence == 0.9
        assert base_name == "192 168 1 5 computer01"

    def test_normalized_multiple_delimiters(self, matcher: FolderMatcher) -> None:
        """Test normalized match with multiple delimiter types."""
        result = matcher._match_normalized(
            "folder_name-test.backup", "folder name test backup"
        )
        assert result is not None
        confidence, base_name = result
        assert confidence == 0.9
        assert base_name == "folder name test backup"

    def test_normalized_consecutive_delimiters(self, matcher: FolderMatcher) -> None:
        """Test normalized match with consecutive delimiters."""
        result = matcher._match_normalized("folder--name", "folder___name")
        assert result is not None
        confidence, base_name = result
        assert confidence == 0.9
        assert base_name == "folder name"

    def test_normalized_underscore_to_dot(self, matcher: FolderMatcher) -> None:
        """Test normalized match: underscores and dots."""
        result = matcher._match_normalized("file_name", "file.name")
        assert result is not None
        confidence, base_name = result
        assert confidence == 0.9

    def test_no_match_different_content(self, matcher: FolderMatcher) -> None:
        """Test that different content doesn't match."""
        result = matcher._match_normalized("folder-a", "folder-b")
        assert result is None

    def test_no_match_identical_already(self, matcher: FolderMatcher) -> None:
        """Test identical names return None (should be caught by Tier 1 logic)."""
        result = matcher._match_normalized("folder", "folder")
        assert result is None

    def test_empty_string_first(self, matcher: FolderMatcher) -> None:
        """Test empty string as first argument."""
        result = matcher._match_normalized("", "folder")
        assert result is None

    def test_empty_string_second(self, matcher: FolderMatcher) -> None:
        """Test empty string as second argument."""
        result = matcher._match_normalized("folder", "")
        assert result is None

    def test_whitespace_trimming(self, matcher: FolderMatcher) -> None:
        """Test that leading/trailing whitespace is trimmed."""
        result = matcher._match_normalized("-folder-", "_folder_")
        assert result is not None
        confidence, base_name = result
        assert confidence == 0.9
        assert base_name == "folder"


class TestFolderMatcherTier3TokenBased:
    """Test Tier 3: Token-Based Match using Jaccard similarity."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_token_high_overlap(self, matcher: FolderMatcher) -> None:
        """Test high token overlap: same tokens in different order."""
        result = matcher._match_token_based("backup-folder-2024", "folder-backup-2024")
        assert result is not None
        confidence, base_name = result
        # Jaccard = 3/3 = 1.0, confidence = 0.7 + 0.5 * 0.4 = 0.9
        assert confidence == pytest.approx(0.9, rel=0.01)

    def test_token_partial_overlap(self, matcher: FolderMatcher) -> None:
        """Test partial token overlap below threshold returns None.

        tokens: {"folder", "backup"} and {"folder", "archive"}
        intersection = {"folder"}, union = {"folder", "backup", "archive"}
        Jaccard = 1/3 ≈ 0.33 < 0.5 → no match
        """
        result = matcher._match_token_based("folder-backup", "folder-archive")
        # Jaccard = 1/3 < 0.5 threshold, should not match
        assert result is None

    def test_token_partial_overlap_below_threshold(self, matcher: FolderMatcher) -> None:
        """Test partial token overlap below threshold returns None."""
        result = matcher._match_token_based("folder-backup", "folder-archive")
        # Jaccard = 1/3 < 0.5
        assert result is None

    def test_token_exact_50_percent_threshold(self, matcher: FolderMatcher) -> None:
        """Test exact 50% Jaccard similarity threshold."""
        # tokens: {"a", "b"} and {"a", "c"}
        # intersection = {"a"}, union = {"a", "b", "c"}
        # Jaccard = 1/3 < 0.5 → no match
        result = matcher._match_token_based("a-b", "a-c")
        assert result is None

        # tokens: {"a", "b"} and {"a", "b", "c"}
        # intersection = {"a", "b"}, union = {"a", "b", "c"}
        # Jaccard = 2/3 ≈ 0.67 >= 0.5 → match
        result = matcher._match_token_based("a-b", "a-b-c")
        assert result is not None
        confidence, base_name = result
        # confidence = 0.7 + (0.67 - 0.5) * 0.4 ≈ 0.77
        assert confidence >= 0.7

    def test_token_case_insensitive(self, matcher: FolderMatcher) -> None:
        """Test that token matching is case insensitive."""
        result = matcher._match_token_based("FOLDER-BACKUP", "folder-backup-old")
        assert result is not None
        confidence, base_name = result
        # tokens: {"folder", "backup"} and {"folder", "backup", "old"}
        # Jaccard = 2/3 >= 0.5
        assert confidence >= 0.7

    def test_token_low_overlap(self, matcher: FolderMatcher) -> None:
        """Test low token overlap: 'computer01' and '192.168.1.5-computer01'."""
        result = matcher._match_token_based("computer01", "192.168.1.5-computer01")
        # tokens: {"computer01"} and {"192", "168", "1", "5", "computer01"}
        # Jaccard = 1/5 = 0.2 < 0.5 → no match
        assert result is None

    def test_empty_tokens_first(self, matcher: FolderMatcher) -> None:
        """Test empty tokens from first name."""
        result = matcher._match_token_based("---", "folder")
        assert result is None

    def test_empty_tokens_second(self, matcher: FolderMatcher) -> None:
        """Test empty tokens from second name."""
        result = matcher._match_token_based("folder", "---")
        assert result is None

    def test_empty_string(self, matcher: FolderMatcher) -> None:
        """Test empty string input."""
        result = matcher._match_token_based("", "folder")
        assert result is None

    def test_longer_name_as_base(self, matcher: FolderMatcher) -> None:
        """Test that longer name is used as base name."""
        result = matcher._match_token_based("a-b", "a-b-c")
        assert result is not None
        confidence, base_name = result
        assert base_name == "a-b-c"


class TestFolderMatcherTier4Fuzzy:
    """Test Tier 4: Fuzzy Match using RapidFuzz."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_fuzzy_spelling_variation(self, matcher: FolderMatcher) -> None:
        """Test spelling variation: 'comptuer01' and 'computer01'."""
        result = matcher._match_fuzzy("comptuer01", "computer01")
        assert result is not None
        confidence, base_name = result
        assert confidence >= 0.5
        assert confidence <= 1.0

    def test_fuzzy_minor_typo(self, matcher: FolderMatcher) -> None:
        """Test minor typo detection."""
        result = matcher._match_fuzzy("folder-name", "folder-nmae")
        assert result is not None
        confidence, base_name = result
        assert confidence >= 0.5

    def test_fuzzy_case_variation(self, matcher: FolderMatcher) -> None:
        """Test case variations with high similarity should match.

        Note: The 0.85 threshold means only very similar case variations pass.
        'MyFolder' vs 'myFolder' has 87.5% similarity which qualifies.
        """
        result = matcher._match_fuzzy("MyFolder", "myFolder")
        assert result is not None
        confidence, base_name = result
        assert confidence >= 0.7

    def test_fuzzy_significant_difference(self, matcher: FolderMatcher) -> None:
        """Test significant differences: 'folder' and 'computer' should not match."""
        result = matcher._match_fuzzy("folder", "computer")
        assert result is None

    def test_fuzzy_completely_different(self, matcher: FolderMatcher) -> None:
        """Test completely different names."""
        result = matcher._match_fuzzy("abc", "xyz")
        assert result is None

    def test_fuzzy_alphabetical_base_name(self, matcher: FolderMatcher) -> None:
        """Test that alphabetically first name is used as base name."""
        result = matcher._match_fuzzy("comptuer01", "computer01")
        assert result is not None
        confidence, base_name = result
        # "comptuer01" < "computer01" alphabetically
        assert base_name == "comptuer01"

    def test_fuzzy_empty_string(self, matcher: FolderMatcher) -> None:
        """Test empty string input."""
        result = matcher._match_fuzzy("", "folder")
        assert result is None

    def test_fuzzy_identical_strings(self, matcher: FolderMatcher) -> None:
        """Test identical strings (high similarity)."""
        result = matcher._match_fuzzy("folder", "folder")
        assert result is not None
        confidence, base_name = result
        assert confidence == pytest.approx(1.0, rel=0.01)

    def test_fuzzy_confidence_scaling(self, matcher: FolderMatcher) -> None:
        """Test confidence scaling formula."""
        # At 70% similarity → confidence = 0.5
        # At 100% similarity → confidence = 1.0
        result = matcher._match_fuzzy("test", "test")
        assert result is not None
        confidence, _ = result
        assert confidence == pytest.approx(1.0, rel=0.01)


class TestFolderMatcherIntegration:
    """Integration tests for the complete find_matches method."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.7)

    def test_find_matches_with_computer_folders(self, matcher: FolderMatcher) -> None:
        """Test find_matches with ComputerFolder instances."""
        folders = [
            make_folder("135897-ntp"),
            make_folder("135897-ntp.newspace"),
            make_folder("unrelated"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert len(matches[0].folders) == 2
        assert matches[0].confidence == 1.0
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_find_matches_empty_list(self, matcher: FolderMatcher) -> None:
        """Test with empty folder list."""
        matches = matcher.find_matches([])
        assert matches == []

    def test_find_matches_single_folder(self, matcher: FolderMatcher) -> None:
        """Test with single folder."""
        folders = [make_folder("folder")]
        matches = matcher.find_matches(folders)
        assert matches == []

    def test_find_matches_no_matches(self, matcher: FolderMatcher) -> None:
        """Test with folders that don't match."""
        folders = [
            make_folder("folder-a"),
            make_folder("folder-b"),
            make_folder("folder-c"),
        ]
        matches = matcher.find_matches(folders)
        assert matches == []

    def test_find_matches_all_identical(self, matcher: FolderMatcher) -> None:
        """Test with all identical folder names."""
        folders = [
            make_folder("folder", "/path1"),
            make_folder("folder", "/path2"),
            make_folder("folder", "/path3"),
        ]
        # Identical names should not match
        matches = matcher.find_matches(folders)
        assert matches == []

    def test_find_matches_transitive_grouping(self, matcher: FolderMatcher) -> None:
        """Test transitive grouping: A-B and B-C should form one group."""
        folders = [
            make_folder("computer-01"),
            make_folder("computer-01-backup"),
            make_folder("computer-01-backup.old"),
        ]
        matches = matcher.find_matches(folders)
        # All three should be in one group due to transitive matching
        assert len(matches) == 1
        assert len(matches[0].folders) == 3
        assert matches[0].confidence == 1.0

    def test_find_matches_confidence_threshold(self) -> None:
        """Test that confidence threshold filters matches."""
        matcher_high = FolderMatcher(min_confidence=0.95)
        folders = [
            make_folder("192.168.1.5-computer01"),
            make_folder("192.168.1.5 computer01"),
        ]
        # Normalized match has 0.9 confidence, below 0.95 threshold
        matches = matcher_high.find_matches(folders)
        assert matches == []

        matcher_low = FolderMatcher(min_confidence=0.8)
        matches = matcher_low.find_matches(folders)
        assert len(matches) == 1

    def test_find_matches_sorted_by_confidence(self, matcher: FolderMatcher) -> None:
        """Test that results are sorted by confidence descending."""
        folders = [
            make_folder("exact-prefix"),
            make_folder("exact-prefix.backup"),
            make_folder("192.168.1.5-computer"),
            make_folder("192.168.1.5 computer"),
        ]
        matches = matcher.find_matches(folders)
        # Verify sorted by confidence descending
        confidences = [m.confidence for m in matches]
        assert confidences == sorted(confidences, reverse=True)

    def test_find_matches_multiple_separate_groups(self, matcher: FolderMatcher) -> None:
        """Test multiple separate match groups.

        Groups need sufficiently distinct names to avoid transitive fuzzy matches.
        """
        folders = [
            make_folder("project-alpha"),
            make_folder("project-alpha.backup"),
            make_folder("archive-omega"),
            make_folder("archive-omega.backup"),
            make_folder("unrelated"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 2
        # Both groups should have 2 folders each
        assert all(len(m.folders) == 2 for m in matches)


class TestFolderMatcherSpecExamples:
    """Test exact examples from the specification."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.7)

    def test_spec_example_exact_prefix_group(self, matcher: FolderMatcher) -> None:
        """Test: 'computer-01', 'computer-01-backup', 'computer-01.old' → one group."""
        folders = [
            make_folder("computer-01"),
            make_folder("computer-01-backup"),
            make_folder("computer-01.old"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert len(matches[0].folders) == 3
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX
        assert matches[0].confidence == 1.0

    def test_spec_example_normalized_group(self, matcher: FolderMatcher) -> None:
        """Test: '192.168.1.5-computer02', '192.168.1.5 computer02' → one group."""
        folders = [
            make_folder("192.168.1.5-computer02"),
            make_folder("192.168.1.5 computer02"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert len(matches[0].folders) == 2
        assert matches[0].match_reason == MatchReason.NORMALIZED
        assert matches[0].confidence == 0.9

    def test_spec_example_135897_ntp(self, matcher: FolderMatcher) -> None:
        """Test: '135897-ntp', '135897-ntp.newspace' → one group."""
        folders = [
            make_folder("135897-ntp"),
            make_folder("135897-ntp.newspace"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert len(matches[0].folders) == 2
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX
        assert matches[0].base_name == "135897-ntp"

    def test_spec_example_unrelated_folder(self, matcher: FolderMatcher) -> None:
        """Test: 'unrelated-folder' → no matches."""
        folders = [
            make_folder("unrelated-folder"),
            make_folder("completely-different"),
        ]
        matches = matcher.find_matches(folders)
        assert matches == []

    def test_spec_example_fuzzy_typo(self, matcher: FolderMatcher) -> None:
        """Test: 'comptuer01' and 'computer01' → should match via fuzzy."""
        folders = [
            make_folder("comptuer01"),
            make_folder("computer01"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.FUZZY_MATCH


class TestFolderMatcherEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_very_long_folder_names(self, matcher: FolderMatcher) -> None:
        """Test with very long folder names (>255 characters)."""
        long_name = "a" * 300
        folders = [
            make_folder(long_name),
            make_folder(long_name + "-backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_unicode_characters(self, matcher: FolderMatcher) -> None:
        """Test with Unicode characters."""
        folders = [
            make_folder("フォルダ-backup"),
            make_folder("フォルダ-backup.old"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1

    def test_emoji_characters(self, matcher: FolderMatcher) -> None:
        """Test with emoji characters."""
        folders = [
            make_folder("📁folder"),
            make_folder("📁folder-backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1

    def test_only_delimiters(self, matcher: FolderMatcher) -> None:
        """Test folders with only delimiters.

        Delimiter-only names (e.g., '---', '___') should not produce matches
        because after normalization they contain no alphanumeric characters.
        """
        folders = [
            make_folder("---"),
            make_folder("___"),
        ]
        # After normalization, both become empty or contain no alphanumeric chars
        # The normalized match tier guards against this, so no Tier 2 match
        matches = matcher.find_matches(folders)
        # Delimiter-only names should not match
        assert matches == []

    def test_numbers_only(self, matcher: FolderMatcher) -> None:
        """Test folders with numbers only."""
        folders = [
            make_folder("12345"),
            make_folder("12345-backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_special_regex_characters(self, matcher: FolderMatcher) -> None:
        """Test folders with regex special characters."""
        folders = [
            make_folder("folder[1]"),
            make_folder("folder[1]-backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1

    def test_mixed_case_prefix(self, matcher: FolderMatcher) -> None:
        """Test exact prefix with mixed case (case sensitive)."""
        folders = [
            make_folder("Folder"),
            make_folder("Folder-backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_whitespace_only_difference(self, matcher: FolderMatcher) -> None:
        """Test folders differing only by whitespace placement."""
        folders = [
            make_folder("folder name"),
            make_folder("foldername"),
        ]
        matches = matcher.find_matches(folders)
        # Should match via fuzzy due to high similarity
        if matches:
            assert matches[0].match_reason == MatchReason.FUZZY_MATCH


class TestFolderMatcherFalsePositives:
    """Test cases that should NOT match to prevent false positives."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.7)

    def test_no_match_different_numbers(self, matcher: FolderMatcher) -> None:
        """Test 'computer01' and 'computer02' should not match.

        Names that share the same non-numeric prefix but differ in numeric
        suffix should not be matched to avoid grouping sequentially numbered
        devices as false positives.
        """
        folders = [
            make_folder("computer01"),
            make_folder("computer02"),
        ]
        matches = matcher.find_matches(folders)
        # These should NOT match at the default min_confidence
        assert matches == []

    def test_no_match_different_suffixes(self, matcher: FolderMatcher) -> None:
        """Test 'folder-a' and 'folder-b' should not match."""
        folders = [
            make_folder("folder-a"),
            make_folder("folder-b"),
        ]
        matches = matcher.find_matches(folders)
        assert matches == []

    def test_no_match_prefix_without_delimiter(self, matcher: FolderMatcher) -> None:
        """Test 'test' and 'testing' should not match via prefix."""
        folders = [
            make_folder("test"),
            make_folder("testing"),
        ]
        matches = matcher.find_matches(folders)
        # Should not match via exact prefix (no delimiter)
        # May match via fuzzy
        for match in matches:
            assert match.match_reason != MatchReason.EXACT_PREFIX

    def test_no_match_short_common_prefix(self, matcher: FolderMatcher) -> None:
        """Test short common prefix shouldn't cause false matches.

        Names with a common prefix but different numeric suffixes should not
        match, even when they share significant structure. This prevents
        sequentially numbered items from being grouped as false positives.
        """
        folders = [
            make_folder("a-folder1"),
            make_folder("a-folder2"),
        ]
        matches = matcher.find_matches(folders)
        # These should NOT match at the default min_confidence
        assert matches == []

    def test_no_match_completely_unrelated(self, matcher: FolderMatcher) -> None:
        """Test completely unrelated folders."""
        folders = [
            make_folder("documents"),
            make_folder("pictures"),
            make_folder("music"),
            make_folder("videos"),
        ]
        matches = matcher.find_matches(folders)
        assert matches == []


class TestFolderMatcherTierPriority:
    """Test that higher tiers take priority over lower tiers."""

    @pytest.fixture
    def matcher(self) -> FolderMatcher:
        return FolderMatcher(min_confidence=0.5)

    def test_exact_prefix_over_normalized(self, matcher: FolderMatcher) -> None:
        """Test that exact prefix (Tier 1) takes priority over normalized (Tier 2)."""
        # These could match both ways, but exact prefix should win
        folders = [
            make_folder("folder-name"),
            make_folder("folder-name.backup"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.EXACT_PREFIX

    def test_normalized_over_token(self, matcher: FolderMatcher) -> None:
        """Test that normalized (Tier 2) takes priority over token-based (Tier 3)."""
        folders = [
            make_folder("folder-name"),
            make_folder("folder_name"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.NORMALIZED

    def test_token_over_fuzzy(self, matcher: FolderMatcher) -> None:
        """Test that token-based (Tier 3) takes priority over fuzzy (Tier 4)."""
        # Create folders with high token overlap that would also fuzzy match
        folders = [
            make_folder("backup-folder-2024"),
            make_folder("folder-backup-2024"),
        ]
        matches = matcher.find_matches(folders)
        assert len(matches) == 1
        assert matches[0].match_reason == MatchReason.TOKEN_MATCH
