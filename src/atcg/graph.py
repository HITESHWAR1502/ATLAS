"""
ATCG v3.0 — LangGraph StateGraph Assembly

Assembles the complete pipeline graph:
  M0 → M1 → M2 → M3 → M4 → [Fan-out → M5-* → JOIN] → M5-OWASP → M6 → M7 → M8
"""

from __future__ import annotations

import logging
import uuid

from langgraph.graph import END, StateGraph

from atcg.config import ATCGConfig
from atcg.db.connection import NeonConnection
from atcg.nodes.m0_git_diff import m0_git_diff_filter
from atcg.nodes.m1_ingestion import m1_ingestion
from atcg.nodes.m2_ast_parser import m2_ast_parser
from atcg.nodes.m3_rag_embedder import m3_rag_embedder
from atcg.nodes.m4_test_planner import m4_test_planner, route_to_layers
from atcg.nodes.m5_agents import (
    m5_functional,
    m5_integration,
    m5_performance,
    m5_unit,
    set_config,
)
from atcg.nodes.m5_join import m5_join
from atcg.nodes.m5_owasp import m5_owasp
from atcg.nodes.m6_validator import get_routing_verdict, m6_validator
from atcg.nodes.m7_neon_writer import m7_neon_writer
from atcg.nodes.m8_coverage import m8_coverage_runner
from atcg.state import ATCGState

logger = logging.getLogger(__name__)


def build_graph(config: ATCGConfig, db: NeonConnection) -> StateGraph:
    """
    Build the complete ATCG LangGraph StateGraph.

    Graph topology:
      M0 → M1 → M2 → M3 → M4 → [parallel fan-out] → JOIN → OWASP → M6 → M7 → M8

    Returns:
        Compiled StateGraph ready to invoke
    """
    # Set config for layer agents
    set_config(config)

    # Create graph
    graph = StateGraph(ATCGState)

    # ── Add nodes ────────────────────────────────────────────────────────────

    # Upstream pipeline (M0–M4) — synchronous/async nodes with injected dependencies
    graph.add_node("m0_git_diff", m0_git_diff_filter)
    
    async def m1_ingestion_node(state: ATCGState) -> ATCGState:
        return await m1_ingestion(state, config, db)
    graph.add_node("m1_ingestion", m1_ingestion_node)
    
    graph.add_node("m2_ast_parser", m2_ast_parser)
    
    async def m3_rag_embedder_node(state: ATCGState) -> ATCGState:
        return await m3_rag_embedder(state, config, db)
    graph.add_node("m3_rag_embedder", m3_rag_embedder_node)
    
    graph.add_node("m4_test_planner", m4_test_planner)

    # Parallel layer agents (M5-*)
    graph.add_node("m5_unit", m5_unit)
    graph.add_node("m5_integration", m5_integration)
    graph.add_node("m5_functional", m5_functional)
    graph.add_node("m5_performance", m5_performance)

    # JOIN + OWASP overlay
    graph.add_node("m5_join", m5_join)
    graph.add_node("m5_owasp", m5_owasp)

    # Validation + persistence
    graph.add_node("m6_validator", m6_validator)
    
    async def m7_neon_writer_node(state: ATCGState) -> ATCGState:
        return await m7_neon_writer(state, db)
    graph.add_node("m7_neon_writer", m7_neon_writer_node)
    
    graph.add_node("m8_coverage", m8_coverage_runner)

    # HITL interrupt (placeholder — logs and continues)
    graph.add_node("hitl_interrupt", _hitl_interrupt)

    # Retry handler (increments attempt, routes back to fan-out)
    graph.add_node("retry_handler", _retry_handler)

    # ── Set entry point ──────────────────────────────────────────────────────
    graph.set_entry_point("m0_git_diff")

    # ── Add edges (linear upstream pipeline) ─────────────────────────────────
    graph.add_edge("m0_git_diff", "m1_ingestion")
    graph.add_edge("m1_ingestion", "m2_ast_parser")
    graph.add_edge("m2_ast_parser", "m3_rag_embedder")
    graph.add_edge("m3_rag_embedder", "m4_test_planner")

    # ── Fan-out: M4 → parallel M5 agents via Send() ─────────────────────────
    graph.add_conditional_edges(
        "m4_test_planner",
        route_to_layers,
        ["m5_unit", "m5_integration", "m5_functional", "m5_performance"],
    )

    # ── Fan-in: All M5 → JOIN ────────────────────────────────────────────────
    graph.add_edge("m5_unit", "m5_join")
    graph.add_edge("m5_integration", "m5_join")
    graph.add_edge("m5_functional", "m5_join")
    graph.add_edge("m5_performance", "m5_join")

    # ── Post-JOIN: OWASP → Validator ─────────────────────────────────────────
    graph.add_edge("m5_join", "m5_owasp")
    graph.add_edge("m5_owasp", "m6_validator")

    # ── Conditional routing from M6 ──────────────────────────────────────────
    graph.add_conditional_edges(
        "m6_validator",
        get_routing_verdict,
        {
            "m7_neon_writer": "m7_neon_writer",
            "retry_handler": "retry_handler",
            "hitl_interrupt": "hitl_interrupt",
        },
    )

    # ── Persistence and coverage ─────────────────────────────────────────────
    graph.add_edge("m7_neon_writer", "m8_coverage")
    graph.add_edge("m8_coverage", END)

    # ── HITL → END (after human review, pipeline terminates) ─────────────────
    graph.add_edge("hitl_interrupt", END)

    # ── Retry → back to fan-out ──────────────────────────────────────────────
    graph.add_conditional_edges(
        "retry_handler",
        route_to_layers,
        ["m5_unit", "m5_integration", "m5_functional", "m5_performance"],
    )

    return graph


async def _wrap_async(fn, state, *args):
    """Wrap async functions for LangGraph nodes that need dependency injection."""
    return await fn(state, *args)


def _hitl_interrupt(state: ATCGState) -> ATCGState:
    """
    HITL Interrupt — pauses pipeline for human review.

    In production, this would integrate with Slack/Jira/etc.
    For now, it logs the escalation details and terminates.
    """
    verdict = state.get("verdict", "ESCALATE")
    security_findings = state.get("security_findings", [])
    rejection_feedback = state.get("rejection_feedback")

    logger.warning("=" * 60)
    logger.warning("HITL INTERRUPT — HUMAN REVIEW REQUIRED")
    logger.warning("=" * 60)
    logger.warning(f"Verdict: {verdict}")

    if security_findings:
        for finding in security_findings:
            if finding.get("verdict") == "VULNERABLE":
                logger.warning(
                    f"  🔴 SECURITY VULNERABILITY: {finding.get('owasp_category')} "
                    f"in {finding.get('function_name')} — "
                    f"severity={finding.get('severity')}"
                )

    if rejection_feedback:
        logger.warning(f"  Rejection details: {rejection_feedback}")

    logger.warning("=" * 60)

    return state


def _retry_handler(state: ATCGState) -> ATCGState:
    """
    Retry handler — increments attempt counter and routes back to fan-out.
    """
    attempt = state.get("attempt", 1)
    logger.info(f"RETRY: Attempt {attempt} → {attempt + 1}")

    return {
        **state,
        "attempt": attempt + 1,
    }


def create_initial_state(project_root: str) -> ATCGState:
    """Create the initial state for a pipeline run."""
    run_id = str(uuid.uuid4())
    thread_id = f"atcg-{run_id[:8]}"

    return ATCGState(
        run_id=run_id,
        thread_id=thread_id,
        target_id="",
        attempt=1,
        active_layer="",
        project_context={"project_root": project_root},
        module_context={},
        target_context={},
        test_plan={},
        neon_history=[],
        neon_fixtures=[],
        changed_files=[],
        diff_hunks=[],
        layer_outputs={},
        neon_writes_queue=[],
        reasoning="",
        test_output={},
        verdict="",
        owasp_output=None,
        security_findings=[],
        rejection_feedback=None,
        neon_write={},
        coverage_results=None,
        errors=[],
    )
