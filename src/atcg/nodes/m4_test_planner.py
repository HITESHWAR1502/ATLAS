"""
M4: Test Planner + Layer Router

Analyzes each function target and determines which test layers are active.
Uses LangGraph's Send() API to dispatch parallel sub-states to layer agents.
"""

from __future__ import annotations

import logging
from typing import Any

from langgraph.types import Send

from atcg.state import ATCGState, FunctionClassification, TestLayer

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer Activation Rules (from spec lines 108–110, 123, 162, 215, 265, 343)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def _determine_active_layers(func: dict[str, Any]) -> list[str]:
    """
    Determine which test layers are active for a given function.

    Rules:
      - UNIT: Always active for every function
      - INTEGRATION: Active for functions with ≥1 dependency (DB, cache, queues)
      - FUNCTIONAL: Active for API handlers, service layer, domain logic, workflows
      - PERFORMANCE: Active for hot paths, data processing, DB wrappers, caching
      - SECURITY: Active for user input, auth, DB access, external comms, file paths
    """
    layers = [TestLayer.UNIT.value]  # Always active
    classification = func.get("classification", "PURE_FUNCTION")
    deps = func.get("dependencies", [])
    complexity = func.get("cyclomatic_complexity", 1)

    # ── INTEGRATION ──────────────────────────────────────────────────────────
    if deps:
        layers.append(TestLayer.INTEGRATION.value)

    # ── FUNCTIONAL ───────────────────────────────────────────────────────────
    functional_classifications = {
        FunctionClassification.API_HANDLER.value,
        FunctionClassification.SERVICE_LAYER.value,
        FunctionClassification.DOMAIN_LOGIC.value,
        FunctionClassification.WORKFLOW_ORCHESTRATOR.value,
        FunctionClassification.AUTH_HANDLER.value,
    }
    if classification in functional_classifications:
        layers.append(TestLayer.FUNCTIONAL.value)

    # ── PERFORMANCE ──────────────────────────────────────────────────────────
    performance_classifications = {
        FunctionClassification.DB_ACCESSOR.value,
        FunctionClassification.CACHE_LAYER.value,
        FunctionClassification.DATA_PROCESSOR.value,
        FunctionClassification.SERIALIZER.value,
    }
    if classification in performance_classifications or complexity >= 8:
        layers.append(TestLayer.PERFORMANCE.value)

    # ── SECURITY (tracked separately — runs after JOIN) ──────────────────────
    security_triggers = (
        func.get("accepts_user_input", False)
        or func.get("performs_auth", False)
        or func.get("accesses_db", False)
        or func.get("handles_files", False)
        or func.get("calls_external", False)
    )
    if security_triggers:
        layers.append(TestLayer.SECURITY.value)

    return layers


def m4_test_planner(state: ATCGState) -> ATCGState:
    """
    M4: Test Planner node.

    Analyzes all function targets and assigns active layers to each.
    Prepares the test_plan for parallel fan-out dispatch.

    Updates state with:
        - test_plan: Per-function layer assignments
    """
    target_context = state.get("target_context", {})
    functions = target_context.get("functions", [])
    project_context = state.get("project_context", {})

    targets: list[dict[str, Any]] = []
    total_dispatches = 0

    for func in functions:
        active_layers = _determine_active_layers(func)
        total_dispatches += len(active_layers)

        targets.append({
            "id": func["id"],
            "name": func["name"],
            "module_path": func["module_path"],
            "source_code": func["source_code"],
            "signature": func["signature"],
            "parameters": func.get("parameters", []),
            "return_type": func.get("return_type"),
            "decorators": func.get("decorators", []),
            "classification": func.get("classification"),
            "cyclomatic_complexity": func.get("cyclomatic_complexity", 1),
            "dependencies": func.get("dependencies", []),
            "is_async": func.get("is_async", False),
            "accepts_user_input": func.get("accepts_user_input", False),
            "performs_auth": func.get("performs_auth", False),
            "accesses_db": func.get("accesses_db", False),
            "handles_files": func.get("handles_files", False),
            "calls_external": func.get("calls_external", False),
            "semantic_neighbors": func.get("semantic_neighbors", []),
            "active_layers": active_layers,
            "context": func,  # Full function context for layer agents
        })

    test_plan = {
        "targets": targets,
        "total_functions": len(targets),
        "total_layer_dispatches": total_dispatches,
        "project_language": project_context.get("language", "python"),
        "test_framework": project_context.get("test_framework", "pytest"),
    }

    logger.info(
        f"M4: Planned {len(targets)} targets → "
        f"{total_dispatches} layer dispatches"
    )

    # Log layer distribution
    layer_counts: dict[str, int] = {}
    for t in targets:
        for layer in t["active_layers"]:
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
    for layer, count in sorted(layer_counts.items()):
        logger.info(f"  {layer}: {count} targets")

    return {
        **state,
        "test_plan": test_plan,
    }


def route_to_layers(state: ATCGState) -> list[Send]:
    """
    LangGraph routing function — dispatches parallel Send() calls.

    Called by the conditional edge after M4 to fan out to layer agents.
    Each function × layer combination gets its own sub-state.

    Per spec (lines 654–669):
        for function_target in state.test_plan["targets"]:
            for layer in function_target["active_layers"]:
                sends.append(Send(
                    node  = f"M5_{layer}",
                    state = { ...state, target_id, active_layer, target_context }
                ))
    """
    test_plan = state.get("test_plan", {})
    targets = test_plan.get("targets", [])

    sends: list[Send] = []

    for target in targets:
        for layer in target["active_layers"]:
            # SECURITY runs after JOIN, not in parallel fan-out
            if layer == TestLayer.SECURITY.value:
                continue

            node_name = f"m5_{layer.lower()}"

            sub_state: dict[str, Any] = {
                **state,
                "target_id": target["id"],
                "active_layer": layer,
                "target_context": target["context"],
                "attempt": 1,
            }

            sends.append(Send(node_name, sub_state))

    logger.info(f"M4 Router: Dispatching {len(sends)} parallel layer tasks")
    return sends
