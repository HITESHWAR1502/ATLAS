"""
M5-OWASP Node Wrapper — Runs the security overlay after JOIN.
"""

from __future__ import annotations

from atcg.layers.security import SecurityLayerAgent
from atcg.nodes.m5_agents import _get_config
from atcg.state import ATCGState


async def m5_owasp(state: ATCGState) -> ATCGState:
    """M5-OWASP node — Security overlay runs after JOIN."""
    agent = SecurityLayerAgent(_get_config())
    return await agent.execute(state)
