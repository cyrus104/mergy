"""
Orchestration package for the Computer Data Organization Tool.

This package contains the high-level workflow coordination components:
- MergeOrchestrator: Coordinates the complete 5-phase merge workflow
- MergeLogger: Structured logging for merge operations
"""

from mergy.orchestration.merge_orchestrator import MergeOrchestrator
from mergy.orchestration.merge_logger import MergeLogger

__all__ = ["MergeOrchestrator", "MergeLogger"]
