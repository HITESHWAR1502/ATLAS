"""
ATLAS v3.0 — LangGraph StateGraph Assembly

Assembles the complete pipeline graph:
  M0 → M1 → M2 → M3 → M4 → [Fan-out → M5-* → JOIN] → M5-OWASP → M6 → M7 → M8
"""

from __future__ import annotations

import logging
import uuid

from langgraph.graph import END, StateGraph

from langchain_core.messages import RemoveMessage

from atlas.config import ATLASConfig
from atlas.nodes.m0_git_diff import m0_git_diff_filter
from atlas.nodes.m1_ingestion import m1_ingestion
from atlas.nodes.m2_ast_parser import m2_ast_parser
from atlas.nodes.m4_test_planner import m4_test_planner
from atlas.nodes.m5_agents import (
    m5_functional,
    m5_integration,
    m5_performance,
    m5_unit,
    set_config,
)
from atlas.nodes.m5_join import m5_join
from atlas.nodes.m5_owasp import m5_owasp
from atlas.nodes.m6_test_executor import get_routing_verdict, m6_test_executor
from atlas.nodes.m7_disk_writer import m7_disk_writer
from atlas.nodes.m8_coverage import m8_coverage_runner
from atlas.state import ATLASState

logger = logging.getLogger(__name__)


def build_graph(config: ATLASConfig) -> StateGraph:  # type: ignore[type-arg]
    """
    Build the complete ATLAS LangGraph StateGraph.

    Graph topology:
      M0 → M1 → M2 → M4 → [parallel fan-out] → JOIN → OWASP → M6 → M7 → M8

    Returns:
        Compiled StateGraph ready to invoke
    """
    # Set config for layer agents
    set_config(config)

    # Create graph
    graph = StateGraph(ATLASState)

    # ── Add nodes ────────────────────────────────────────────────────────────

    # Upstream pipeline (M0–M4) — synchronous/async nodes with injected dependencies
    graph.add_node("m0_git_diff", m0_git_diff_filter)

    async def m1_ingestion_node(state: ATLASState) -> ATLASState:
        return await m1_ingestion(state, config)

    graph.add_node("m1_ingestion", m1_ingestion_node)

    graph.add_node("m2_ast_parser", m2_ast_parser)
    graph.add_node("m4_test_planner", m4_test_planner)

    # Parallel layer agents (M5-*)
    graph.add_node("m5_unit", m5_unit)
    graph.add_node("m5_integration", m5_integration)
    graph.add_node("m5_functional", m5_functional)
    graph.add_node("m5_performance", m5_performance)

    # JOIN + OWASP overlay
    graph.add_node("m5_join", m5_join)
    graph.add_node("m5_owasp", m5_owasp)

    # Execution + Validation
    graph.add_node("m6_test_executor", m6_test_executor)

    async def m7_disk_writer_node(state: ATLASState) -> ATLASState:
        return await m7_disk_writer(state)

    graph.add_node("m7_disk_writer", m7_disk_writer_node)

    graph.add_node("m8_coverage", m8_coverage_runner)

    graph.add_node("task_dispatcher", task_dispatcher)

    # HITL interrupt (placeholder — logs and continues)
    graph.add_node("hitl_interrupt", _hitl_interrupt)

    # Retry handler (increments attempt, routes back to current layer)
    graph.add_node("retry_handler", _retry_handler)

    # ── Set entry point ──────────────────────────────────────────────────────
    graph.set_entry_point("m0_git_diff")

    # ── Add edges (linear upstream pipeline) ─────────────────────────────────
    graph.add_edge("m0_git_diff", "m1_ingestion")
    graph.add_edge("m1_ingestion", "m2_ast_parser")
    graph.add_edge("m2_ast_parser", "m4_test_planner")

    # ── M4 -> Task Dispatcher ────────────────────────────────────────────────
    graph.add_edge("m4_test_planner", "task_dispatcher")

    # ── Task Dispatcher -> Layer Agent (or M7 if done) ───────────────────────
    graph.add_conditional_edges(
        "task_dispatcher",
        route_from_dispatcher,
        [
            "m5_unit",
            "m5_integration",
            "m5_functional",
            "m5_performance",
            "m5_owasp",
            "m7_disk_writer",
        ],
    )

    # ── Layer Agents -> Test Executor/Validator ──────────────────────────────
    graph.add_edge("m5_unit", "m6_test_executor")
    graph.add_edge("m5_integration", "m6_test_executor")
    graph.add_edge("m5_functional", "m6_test_executor")
    graph.add_edge("m5_performance", "m6_test_executor")
    graph.add_edge("m5_owasp", "m6_test_executor")

    # ── Conditional routing from M6 ──────────────────────────────────────────
    graph.add_conditional_edges(
        "m6_test_executor",
        get_routing_verdict,
        {
            "task_dispatcher": "task_dispatcher",  # If PASS
            "retry_handler": "retry_handler",  # If RETRY
            "hitl_interrupt": "hitl_interrupt",  # If ESCALATE
        },
    )

    # ── Persistence and coverage ─────────────────────────────────────────────
    graph.add_edge("m7_disk_writer", "m8_coverage")
    graph.add_edge("m8_coverage", END)

    # ── HITL → END (after human review, pipeline terminates) ─────────────────
    graph.add_edge("hitl_interrupt", END)

    # ── Retry → back to layer ──────────────────────────────────────────────
    graph.add_conditional_edges(
        "retry_handler",
        route_from_dispatcher,
        ["m5_unit", "m5_integration", "m5_functional", "m5_performance", "m5_owasp"],
    )

    return graph


from typing import Any, Callable

async def _wrap_async(fn: Callable[..., Any], state: ATLASState, *args: Any) -> Any:
    """Wrap async functions for LangGraph nodes that need dependency injection."""
    return await fn(state, *args)


def _hitl_interrupt(state: ATLASState) -> ATLASState:
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

    return {}


def task_dispatcher(state: ATLASState) -> ATLASState:
    """Pops the next task from the execution queue."""
    queue = state.get("execution_queue", [])
    if not queue:
        return {"active_layer": ""}  # Signals done

    import os
    import time

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    model = os.getenv("LLM_MODEL", "gemini-2.5-flash").lower()

    # Check if this isn't the very first task being popped (by checking if original queue size matches)
    # We add a delay to respect the Gemini free tier 5 RPM limit
    if provider == "gemini" and "2.5" in model:
        logger.info("DISPATCHER: Applying 12-second rate limit delay for Gemini 2.5 free tier...")
        time.sleep(12.5)

    task = queue.pop(0)
    logger.info(f"DISPATCHER: Popping task for {task['layer']} targeting {task['target_file']}")

    # Clear previous messages so the LLM doesn't reuse test code from the previous function
    clear_msgs = [
        RemoveMessage(id=m.id) for m in state.get("messages", []) if hasattr(m, "id") and m.id
    ]

    return {
        "target_file": task["target_file"],
        "active_layer": task["layer"],
        "target_context": task["target_context"],
        "attempt": 1,
        "messages": clear_msgs,  # type: ignore[typeddict-item]
        "execution_queue": queue,
    }


def route_from_dispatcher(state: ATLASState) -> str:
    """Routes to the correct layer agent or ends execution."""
    active_layer = state.get("active_layer", "")
    if not active_layer:
        return "m7_disk_writer"
    layer_name = active_layer.lower()
    if layer_name == "security":
        return "m5_owasp"
    return f"m5_{layer_name}"


def _retry_handler(state: ATLASState) -> ATLASState:
    """
    Retry handler — increments attempt counter and loops back to current layer.
    """
    attempt = state.get("attempt", 1)
    layer = state.get("active_layer", "unknown")
    logger.info(f"RETRY {layer}: Attempt {attempt} → {attempt + 1}")

    return {
        "attempt": attempt + 1,
    }


def create_initial_state(project_root: str, selected_layers: list[str] | None = None) -> ATLASState:
    """Create the initial state for a pipeline run."""
    run_id = str(uuid.uuid4())
    thread_id = f"atlas-{run_id[:8]}"

    return ATLASState(
        run_id=run_id,
        thread_id=thread_id,
        target_file="",
        attempt=1,
        active_layer="",
        project_context={"project_root": project_root},
        module_context={},
        target_context={},
        test_plan={},
        changed_files=[],
        diff_hunks=[],
        layer_outputs={},
        disk_writes_queue=[],
        reasoning="",
        test_output={},
        verdict="",
        owasp_output=None,
        security_findings=[],
        rejection_feedback=None,
        messages=[],
        execution_result=None,
        retry_count=0,
        max_retries=3,
        selected_layers=selected_layers or [],
        current_layer_index=0,
        execution_queue=[],
        disk_write={},
        coverage_results=None,
        errors=[],
    )
