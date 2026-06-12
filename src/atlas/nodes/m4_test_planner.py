"""
M4: Test Planner + Layer Router

Analyzes each function target and determines which test layers are active.
Uses LangGraph's Send() API to dispatch parallel sub-states to layer agents.
"""

from __future__ import annotations

import logging
from typing import Any
from pathlib import Path

from atlas.state import ATLASState, FunctionClassification, TestLayer

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


def m4_test_planner(state: ATLASState) -> ATLASState:
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

    # Build execution queue for sequential processing of the whole file
    selected_layers = state.get("selected_layers", [])
    execution_queue = []
    
    # We now test the entire file as one unit instead of function by function
    # M0 provides changed_files, M2 parsed them. We need to queue each changed file.
    changed_files = state.get("changed_files", [])
    
    for file_path in changed_files:
        # Get source code from disk to pass to M5
        full_path = Path(project_context.get("project_root", ".")) / file_path
        source_code = ""
        if full_path.exists():
            try:
                source_code = full_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass
                
        file_target_context = {
            "functions": [f for f in targets if f.get("module_path") == file_path],
            "source_code": source_code
        }
        
        for layer in selected_layers:
            execution_queue.append({
                "target_file": file_path,
                "layer": layer,
                "target_context": file_target_context,
            })

    logger.info(
        f"M4: Planned {len(targets)} targets → "
        f"{total_dispatches} active layer dispatches."
    )
    logger.info(f"M4: Queued {len(execution_queue)} sequential tasks based on selected layers: {selected_layers}")

    return {
        "test_plan": test_plan,
        "execution_queue": execution_queue,
    }



