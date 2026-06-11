"""
M5 Layer Node Wrappers — Thin wrappers that instantiate layer agents for LangGraph nodes.
"""

from __future__ import annotations


from atcg.config import ATCGConfig
from atcg.layers.unit import UnitLayerAgent
from atcg.layers.integration import IntegrationLayerAgent
from atcg.layers.functional import FunctionalLayerAgent
from atcg.layers.performance import PerformanceLayerAgent
from atcg.state import ATCGState

# Global config reference (set during graph construction)
_config: ATCGConfig | None = None


def set_config(config: ATCGConfig) -> None:
    """Set the global config for layer agents."""
    global _config
    _config = config


def _get_config() -> ATCGConfig:
    if _config is None:
        raise RuntimeError("Config not set. Call set_config() before running the graph.")
    return _config


async def m5_unit(state: ATCGState) -> ATCGState:
    """M5-UNIT node — Unit test generation."""
    agent = UnitLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_integration(state: ATCGState) -> ATCGState:
    """M5-INTEGRATION node — Integration test generation."""
    agent = IntegrationLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_functional(state: ATCGState) -> ATCGState:
    """M5-FUNCTIONAL node — Functional test generation."""
    agent = FunctionalLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_performance(state: ATCGState) -> ATCGState:
    """M5-PERFORMANCE node — Performance test generation."""
    agent = PerformanceLayerAgent(_get_config())
    return await agent.execute(state)
