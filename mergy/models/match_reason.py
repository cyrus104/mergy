"""
MatchReason enum for the four-tier folder matching algorithm.

The matching algorithm uses four tiers, in order of evaluation:
1. Exact Prefix Match (100% confidence) - One folder name is exact prefix of another
2. Normalized Match (90% confidence) - Names match after normalizing delimiters
3. Token Match (70% confidence, scaled) - Token-based Jaccard similarity match
4. Fuzzy Match (50% confidence, scaled) - Levenshtein distance-based fuzzy match
"""

from enum import Enum


class MatchReason(Enum):
    """Encodes the match rationale categories for the four-tier matching algorithm."""
    EXACT_PREFIX = "exact_prefix"      # Tier 1: One folder name is exact prefix of another
    NORMALIZED = "normalized"          # Tier 2: Names match after normalizing delimiters
    TOKEN_MATCH = "token_match"        # Tier 3: Token-based Jaccard similarity match
    FUZZY_MATCH = "fuzzy_match"        # Tier 4: Levenshtein distance-based fuzzy match
