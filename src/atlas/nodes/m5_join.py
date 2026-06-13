"""
M5-JOIN: Fan-out Aggregation Node

Runs after all parallel M5 layer agents complete.
Aggregates layer outputs, deduplicates fixtures, and resolves import conflicts.
"""

from __future__ import annotations

import logging
from typing import Any

from atlas.state import ATLASState

logger = logging.getLogger(__name__)


def m5_join(state: ATLASState) -> ATLASState:
    """
    JOIN node — aggregates all parallel M5 layer outputs.

    Per spec (lines 671–697):
      - Merges layer outputs into layer_outputs dict
      - Collects new fixtures for registry
      - Detects import conflicts across test files
      - Passes merged state to M5-OWASP
    """
    merged_layer_outputs = state.get("layer_outputs", {})

    shared_fixtures_to_register: list[dict[str, Any]] = []
    all_quality_flags: list[str] = []
    all_imports: dict[str, list[str]] = {}

    for output_key, test_output in merged_layer_outputs.items():
        # Collect quality flags
        all_quality_flags.extend(test_output.get("quality_flags", []))

        # Track imports for conflict detection
        test_code = test_output.get("test_code", "")
        imports = _extract_imports(test_code)
        layer = test_output.get("active_layer", "UNKNOWN")
        from enum import Enum

        if isinstance(layer, Enum):
            layer = layer.value
        elif not isinstance(layer, str):
            layer = str(layer)
        all_imports[layer] = all_imports.get(layer, []) + imports

    # Detect import conflicts across test files
    import_conflicts = _detect_import_conflicts(all_imports)
    if import_conflicts:
        all_quality_flags.append(f"IMPORT_CONFLICTS_DETECTED: {', '.join(import_conflicts)}")
        logger.warning(f"JOIN: Import conflicts detected: {import_conflicts}")

    # Deduplicate fixtures
    unique_fixtures = _deduplicate_fixtures(shared_fixtures_to_register)

    logger.info(
        f"JOIN: Merged {len(merged_layer_outputs)} layer outputs, "
        f"{len(unique_fixtures)} unique fixtures to register"
    )

    return {
        "layer_outputs": merged_layer_outputs,
        "fixtures": unique_fixtures,
        "quality_flags": all_quality_flags,
    }


def _extract_imports(test_code: str) -> list[str]:
    """Extract import statements from test code."""
    imports: list[str] = []
    for line in test_code.split("\n"):
        stripped = line.strip()
        if stripped.startswith("import ") or stripped.startswith("from "):
            imports.append(stripped)
        elif stripped.startswith("const ") and "require(" in stripped:
            imports.append(stripped)
    return imports


def _detect_import_conflicts(all_imports: dict[str, list[str]]) -> list[str]:
    """Detect conflicting imports across layer test files."""
    conflicts: list[str] = []
    seen_modules: dict[str, str] = {}  # module → first layer that imported it

    for layer, imports in all_imports.items():
        for imp in imports:
            # Extract module name from import
            module = imp.split("from ")[-1].strip().strip("'\"")
            if module in seen_modules and seen_modules[module] != layer:
                conflict = f"{module} imported by both {seen_modules[module]} and {layer}"
                if conflict not in conflicts:
                    conflicts.append(conflict)
            else:
                seen_modules[module] = layer

    return conflicts


def _deduplicate_fixtures(fixtures: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate fixture registration requests by fixture_key."""
    seen_keys: set[str] = set()
    unique: list[dict[str, Any]] = []

    for fixture in fixtures:
        fixture_list = fixture.get("fixtures", [fixture])
        if isinstance(fixture_list, dict):
            fixture_list = [fixture_list]

        for f in fixture_list:
            key = f.get("fixture_key", "")
            if key and key not in seen_keys:
                seen_keys.add(key)
                unique.append(f)

    return unique
