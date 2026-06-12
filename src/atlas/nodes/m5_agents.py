"""
M5 Layer Node Wrappers — Thin wrappers that instantiate layer agents for LangGraph nodes.
"""

from __future__ import annotations


from atlas.config import ATLASConfig
from atlas.agents.unit import UnitLayerAgent
from atlas.agents.integration import IntegrationLayerAgent
from atlas.agents.functional import FunctionalLayerAgent
from atlas.agents.performance import PerformanceLayerAgent
from atlas.state import ATLASState

# Global config reference (set during graph construction)
_config: ATLASConfig | None = None


def set_config(config: ATLASConfig) -> None:
    """Set the global config for layer agents."""
    global _config
    _config = config


def _get_config() -> ATLASConfig:
    if _config is None:
        raise RuntimeError("Config not set. Call set_config() before running the graph.")
    return _config


async def m5_unit(state: ATLASState) -> ATLASState:
    """M5-UNIT node — Unit test generation."""
    agent = UnitLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_integration(state: ATLASState) -> ATLASState:
    """M5-INTEGRATION node — Integration test generation."""
    agent = IntegrationLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_functional(state: ATLASState) -> ATLASState:
    """M5-FUNCTIONAL node — Functional test generation."""
    agent = FunctionalLayerAgent(_get_config())
    return await agent.execute(state)


async def m5_performance(state: ATLASState) -> ATLASState:
    """M5-PERFORMANCE node — Performance test generation."""
    agent = PerformanceLayerAgent(_get_config())
    return await agent.execute(state)
