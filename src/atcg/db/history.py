"""
ATCG Test Run History — Query and write operations for per-layer test run tables.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from uuid import UUID

from atcg.db.connection import NeonConnection
from atcg.db.schema import LAYER_TABLE_MAP

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Read Operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def get_target_history(
    db: NeonConnection,
    target_id: str,
    layer: str | None = None,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Fetch prior test runs for a target, optionally filtered by layer.

    If layer is None, fetches from ALL layer tables and merges results.

    Returns most recent runs first.
    """
    import asyncio
    results: list[dict[str, Any]] = []

    layers_to_query = [layer] if layer else list(LAYER_TABLE_MAP.keys())

    async def query_layer(lyr: str):
        table = LAYER_TABLE_MAP.get(lyr)
        if not table:
            return []

        # Security findings have a different schema
        if lyr == "SECURITY":
            return await db.execute(
                f"""
                SELECT *, 'SECURITY' AS layer FROM {table}
                WHERE target_id = %s
                ORDER BY detected_at DESC
                LIMIT %s
                """,
                (target_id, limit),
            )
        else:
            return await db.execute(
                f"""
                SELECT *, %s AS layer FROM {table}
                WHERE target_id = %s
                ORDER BY generated_at DESC
                LIMIT %s
                """,
                (lyr, target_id, limit),
            )

    rows_list = await asyncio.gather(*(query_layer(lyr) for lyr in layers_to_query))
    for rows in rows_list:
        results.extend(rows)

    # Sort all results by timestamp (most recent first)
    results.sort(
        key=lambda r: r.get("generated_at") or r.get("detected_at") or "",
        reverse=True,
    )

    return results[:limit]


async def get_security_findings(
    db: NeonConnection,
    target_id: str | None = None,
    unresolved_only: bool = True,
    severity: str | None = None,
    owasp_category: str | None = None,
) -> list[dict[str, Any]]:
    """
    Query OWASP security findings from the audit log.

    Supports filtering by target, resolution status, severity, and OWASP category.
    """
    conditions = []
    params: list[Any] = []

    if target_id:
        conditions.append("target_id = %s")
        params.append(target_id)
    if unresolved_only:
        conditions.append("resolved_at IS NULL")
    if severity:
        conditions.append("severity = %s")
        params.append(severity)
    if owasp_category:
        conditions.append("owasp_category = %s")
        params.append(owasp_category)

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    return await db.execute(
        f"""
        SELECT * FROM atcg_security_findings
        WHERE {where_clause}
        ORDER BY detected_at DESC
        """,
        tuple(params),
    )


async def get_latest_pass_run(
    db: NeonConnection,
    target_id: str,
    layer: str,
) -> dict[str, Any] | None:
    """Get the most recent PASS run for a target in a specific layer."""
    table = LAYER_TABLE_MAP.get(layer)
    if not table or layer == "SECURITY":
        return None

    return await db.execute_one(
        f"""
        SELECT * FROM {table}
        WHERE target_id = %s AND verdict = 'PASS'
        ORDER BY generated_at DESC
        LIMIT 1
        """,
        (target_id,),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Write Operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def create_run(
    db: NeonConnection,
    thread_id: str,
    project_name: str,
    language: str,
    test_framework: str,
    targets_count: int = 0,
    layers_dispatched: int = 0,
) -> dict[str, Any] | None:
    """Create a new master run record and return it."""
    return await db.execute_one(
        """
        INSERT INTO atcg_runs
            (thread_id, project_name, language, test_framework,
             targets_count, layers_dispatched)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (thread_id, project_name, language, test_framework,
         targets_count, layers_dispatched),
    )


async def complete_run(
    db: NeonConnection,
    run_id: str | UUID,
    status: str = "COMPLETED",
) -> None:
    """Mark a run as completed (or failed)."""
    await db.execute(
        """
        UPDATE atcg_runs
        SET status = %s, completed_at = NOW()
        WHERE run_id = %s
        """,
        (status, str(run_id)),
    )


async def write_layer_run(
    db: NeonConnection,
    layer: str,
    payload: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Write a test run record to the appropriate layer table.

    The payload dict must match the table's column structure.
    """
    table = LAYER_TABLE_MAP.get(layer)
    if not table:
        raise ValueError(f"Unknown layer: {layer}. Must be one of: {list(LAYER_TABLE_MAP.keys())}")

    # Build dynamic INSERT statement from payload keys
    columns = list(payload.keys())
    placeholders = ["%s"] * len(columns)

    # Convert complex types to JSON strings
    values = []
    for key, value in payload.items():
        if isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        else:
            values.append(value)

    column_str = ", ".join(columns)
    placeholder_str = ", ".join(placeholders)

    query = f"INSERT INTO {table} ({column_str}) VALUES ({placeholder_str}) RETURNING *"

    result = await db.execute_one(query, tuple(values))
    if result:
        logger.info(f"Written {layer} run for target={payload.get('target_id')}")
    return result


async def write_security_finding(
    db: NeonConnection,
    finding: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Append a security finding to the OWASP audit log.

    This table is APPEND-ONLY — records are never deleted, only resolved.
    """
    return await db.execute_one(
        """
        INSERT INTO atcg_security_findings
            (run_id, target_id, function_name, owasp_category,
             severity, test_name, test_code_snippet, verdict)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *
        """,
        (
            finding["run_id"],
            finding["target_id"],
            finding["function_name"],
            finding["owasp_category"],
            finding["severity"],
            finding["test_name"],
            finding.get("test_code_snippet"),
            finding["verdict"],
        ),
    )


async def resolve_finding(
    db: NeonConnection,
    finding_id: str | UUID,
    jira_ticket: str | None = None,
) -> None:
    """Mark a security finding as resolved."""
    await db.execute(
        """
        UPDATE atcg_security_findings
        SET resolved_at = NOW(), jira_ticket = %s
        WHERE id = %s AND resolved_at IS NULL
        """,
        (jira_ticket, str(finding_id)),
    )
