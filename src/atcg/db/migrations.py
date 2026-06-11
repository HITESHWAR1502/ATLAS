"""
ATCG Schema Migrations — Initialize and migrate the Neon database schema.
"""

from __future__ import annotations

import logging
from typing import Any

from atcg.db.connection import NeonConnection
from atcg.db.schema import ALL_TABLES

logger = logging.getLogger(__name__)


async def initialize_schema(db: NeonConnection, dry_run: bool = False) -> list[str]:
    """
    Create all ATCG tables in Neon if they don't exist.

    Args:
        db: Active NeonConnection instance
        dry_run: If True, only log the DDL without executing

    Returns:
        List of table names created/verified
    """
    created_tables: list[str] = []

    for table_name, ddl in ALL_TABLES:
        if dry_run:
            logger.info(f"[DRY RUN] Would create: {table_name}")
            logger.debug(ddl)
        else:
            try:
                async with db.acquire() as conn:
                    await conn.execute(ddl)
                    await conn.commit()
                logger.info(f"✓ Created/verified table: {table_name}")
                created_tables.append(table_name)
            except Exception as e:
                logger.error(f"✗ Failed to create {table_name}: {e}")
                raise

    return created_tables


async def drop_all_tables(db: NeonConnection, confirm: bool = False) -> None:
    """
    Drop all ATCG tables. USE WITH EXTREME CAUTION.

    Args:
        db: Active NeonConnection instance
        confirm: Must be True to actually execute
    """
    if not confirm:
        logger.warning("drop_all_tables called without confirm=True — aborting")
        return

    # Reverse order to respect FK constraints
    table_names = [name for name, _ in reversed(ALL_TABLES) if name != "extensions"]

    async with db.acquire() as conn:
        for table_name in table_names:
            try:
                await conn.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")
                logger.info(f"Dropped table: {table_name}")
            except Exception as e:
                logger.error(f"Failed to drop {table_name}: {e}")
        await conn.commit()


async def get_schema_status(db: NeonConnection) -> dict[str, Any]:
    """
    Check which ATCG tables exist and their row counts.

    Returns:
        Dict mapping table_name → {"exists": bool, "row_count": int}
    """
    status: dict[str, Any] = {}
    table_names = [name for name, _ in ALL_TABLES if name != "extensions"]

    for table_name in table_names:
        try:
            result = await db.execute_one(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = %s
                ) AS table_exists
                """,
                (table_name,),
            )
            exists = result["table_exists"] if result else False

            row_count = 0
            if exists:
                count_result = await db.execute_one(
                    f"SELECT COUNT(*) AS cnt FROM {table_name}"  # noqa: S608
                )
                row_count = count_result["cnt"] if count_result else 0

            status[table_name] = {"exists": exists, "row_count": row_count}
        except Exception as e:
            status[table_name] = {"exists": False, "error": str(e)}

    return status
