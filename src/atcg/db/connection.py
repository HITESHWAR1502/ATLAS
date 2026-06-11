"""
ATCG Neon Database Connection — Async connection pool management.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from atcg.config import ATCGConfig

logger = logging.getLogger(__name__)


class NeonConnection:
    """
    Manages async connection pool to Neon PostgreSQL.

    Usage:
        config = ATCGConfig.from_env()
        db = NeonConnection(config)
        await db.initialize()

        async with db.acquire() as conn:
            result = await conn.execute("SELECT 1")

        await db.close()
    """

    def __init__(self, config: ATCGConfig) -> None:
        self._config = config
        self._pool: AsyncConnectionPool | None = None

    async def initialize(self) -> None:
        """Create the connection pool."""
        logger.info("Initializing Neon connection pool...")
        self._pool = AsyncConnectionPool(
            conninfo=self._config.neon.database_url,
            min_size=2,
            max_size=10,
            kwargs={"row_factory": dict_row},
            open=False,
        )
        await self._pool.open()
        await self._pool.wait()
        logger.info("Neon connection pool ready")

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Neon connection pool closed")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[psycopg.AsyncConnection[dict[str, Any]], None]:
        """Acquire a connection from the pool."""
        if not self._pool:
            raise RuntimeError("Connection pool not initialized. Call initialize() first.")
        async with self._pool.connection() as conn:
            yield conn

    async def execute(self, query: str, params: tuple[Any, ...] | None = None) -> list[dict[str, Any]]:
        """Execute a query and return all rows as dicts."""
        async with self.acquire() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                if cur.description:
                    return await cur.fetchall()
                return []

    async def execute_one(self, query: str, params: tuple[Any, ...] | None = None) -> dict[str, Any] | None:
        """Execute a query and return a single row."""
        async with self.acquire() as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(query, params)
                if cur.description:
                    return await cur.fetchone()
                return None

    async def execute_many(self, query: str, params_seq: list[tuple[Any, ...]]) -> None:
        """Execute a query for multiple parameter sets."""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(query, params_seq)

    async def health_check(self) -> bool:
        """Verify the database connection is alive."""
        try:
            result = await self.execute_one("SELECT 1 AS ok")
            return result is not None and result.get("ok") == 1
        except Exception as e:
            logger.error(f"Neon health check failed: {e}")
            return False
