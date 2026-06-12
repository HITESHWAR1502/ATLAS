"""
M5-OWASP Node Wrapper — Runs the security overlay after JOIN.
"""

from __future__ import annotations

from atlas.security.security import SecurityLayerAgent
from atlas.nodes.m5_agents import _get_config
from atlas.state import ATLASState


async def m5_owasp(state: ATLASState) -> ATLASState:
    """M5-OWASP node — Security overlay runs after JOIN."""
    agent = SecurityLayerAgent(_get_config())
    return await agent.execute(state)
