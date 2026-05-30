"""Noxus AgentSecOps — Milestone 1 deterministic local skeleton.

This package proves the full attack -> evaluate -> patch -> retest loop can run
deterministically, without any LLM, network, or cloud dependency.
"""

from .constants import MAX_TUNING_ITERATIONS

__all__ = ["MAX_TUNING_ITERATIONS"]
__version__ = "0.1.0"
