"""Match reason enumeration for folder matching tiers."""

from enum import Enum


class MatchReason(Enum):
    """Enumeration of matching tiers with associated confidence levels.

    Each tier represents a different matching strategy with varying
    confidence levels as defined in the matching specification.
    """

    EXACT_PREFIX = "exact_prefix"  # Tier 1: 100% confidence
    NORMALIZED = "normalized"      # Tier 2: 90% confidence
    TOKEN_MATCH = "token_match"    # Tier 3: 70% base confidence, scaled
    FUZZY_MATCH = "fuzzy_match"    # Tier 4: 50% base confidence, scaled
