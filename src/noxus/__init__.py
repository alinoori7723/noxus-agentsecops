"""Noxus AgentSecOps readiness assessment package.

This package implements an attack -> evaluate -> patch -> retest loop that can
run deterministically, without an LLM, network, or cloud dependency.
"""

from .constants import MAX_TUNING_ITERATIONS

__all__ = ["MAX_TUNING_ITERATIONS"]
__version__ = "0.1.0"
