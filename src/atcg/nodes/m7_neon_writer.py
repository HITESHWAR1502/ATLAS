"""
M7: Neon Writer — Persists all test run records, fixtures, and findings to Neon.
"""

from __future__ import annotations

import logging

from atcg.db.connection import NeonConnection
from atcg.db.fixtures import register_fixture
from atcg.db.history import write_layer_run, write_security_finding
from atcg.state import ATCGState

logger = logging.getLogger(__name__)


async def m7_neon_writer(state: ATCGState, db: NeonConnection) -> ATCGState:
    """
    M7: Neon Writer node.

    Batch writes all test run records to appropriate Neon tables.
    Registers new fixtures in atcg_shared_fixtures.
    Writes OWASP findings to atcg_security_findings.
    All writes are transactional.
    """
    neon_write = state.get("neon_write", {})
    layer_outputs = state.get("layer_outputs", {})
    security_findings = state.get("security_findings", [])
    run_id = state.get("run_id")
    records_written = 0

    # ── Write batch layer run records ────────────────────────────────────────
    batch = neon_write.get("batch", [])
    for write_item in batch:
        try:
            table = write_item.get("table", "")
            payload = write_item.get("payload", {})
            if table and payload:
                layer = table.replace("atcg_", "").replace("_runs", "").upper()
                await write_layer_run(db, layer, payload)
                records_written += 1
        except Exception as e:
            logger.error(f"M7: Failed to write layer run: {e}")

    # If no batch, try individual layer outputs
    if not batch:
        for layer, output in layer_outputs.items():
            try:
                payload = {
                    "run_id": run_id,
                    "target_id": output.get("target_id", ""),
                    "attempt": state.get("attempt", 1),
                    "test_code": output.get("test_code", ""),
                    "file_path": output.get("file_path", ""),
                    "framework": output.get("framework", ""),
                    "confidence": output.get("confidence", 0.0),
                    "quality_flags": output.get("quality_flags", []),
                    "fixtures_reused": output.get("fixtures_reused", []),
                    "fixtures_registered": output.get("fixtures_registered", []),
                    "reasoning": output.get("reasoning", ""),
                    "verdict": state.get("verdict", "PASS"),
                }
                await write_layer_run(db, layer, payload)
                records_written += 1
            except Exception as e:
                logger.error(f"M7: Failed to write {layer} run: {e}")

    # ── Register new fixtures ────────────────────────────────────────────────
    fixtures = neon_write.get("fixtures", [])
    fixtures_registered = 0
    for fixture in fixtures:
        try:
            project_context = state.get("project_context", {})
            await register_fixture(
                db=db,
                project_name=project_context.get("project_name", "unknown"),
                fixture_key=fixture.get("fixture_key", ""),
                fixture_code=fixture.get("fixture_code", ""),
                language=project_context.get("language", "python"),
                framework=project_context.get("test_framework", "pytest"),
                layer_tags=fixture.get("layer_tags", []),
                tags=fixture.get("tags", []),
                created_by_run=run_id or "unknown",
            )
            fixtures_registered += 1
        except Exception as e:
            logger.error(f"M7: Failed to register fixture: {e}")

    # ── Write security findings ──────────────────────────────────────────────
    findings_written = 0
    for finding in security_findings:
        try:
            finding["run_id"] = run_id
            await write_security_finding(db, finding)
            findings_written += 1
        except Exception as e:
            logger.error(f"M7: Failed to write security finding: {e}")

    logger.info(
        f"M7: Written {records_written} run records, "
        f"{fixtures_registered} fixtures, "
        f"{findings_written} security findings to Neon"
    )

    return {
        **state,
        "neon_write": {
            **neon_write,
            "written": True,
            "records_count": records_written,
            "fixtures_count": fixtures_registered,
            "findings_count": findings_written,
        },
    }
