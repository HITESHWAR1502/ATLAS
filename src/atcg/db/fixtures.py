"""
ATCG Fixture Registry — CRUD operations for the shared fixture registry in Neon.

The fixture registry eliminates redundant mock regeneration across all functions
in a project. Before M5 generates any mock or fixture, M1 pre-fetches matching
entries from Neon.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from atcg.db.connection import NeonConnection

logger = logging.getLogger(__name__)


async def query_fixtures(
    db: NeonConnection,
    project_name: str,
    language: str,
    framework: str,
    dependency_tags: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Query the fixture registry for reusable fixtures matching the current context.

    This implements the registry query logic from the spec:
        SELECT * FROM atcg_shared_fixtures
        WHERE project_name IN ('<current_project>', 'GLOBAL')
          AND language = '<primary_language>'
          AND framework = '<test_framework>'
          AND tags && ARRAY[<dependency_tags_for_this_module>]
        ORDER BY usage_count DESC;

    Args:
        db: Active NeonConnection
        project_name: Current project name
        language: Primary language (python, typescript, etc.)
        framework: Test framework (pytest, jest, etc.)
        dependency_tags: Tags to match against fixture tags (e.g., ["neon", "db"])

    Returns:
        List of matching fixture records, ordered by usage_count DESC
    """
    if dependency_tags:
        query = """
            SELECT * FROM atcg_shared_fixtures
            WHERE project_name IN (%s, 'GLOBAL')
              AND language = %s
              AND framework = %s
              AND tags ?| %s
            ORDER BY usage_count DESC
        """
        params = (project_name, language, framework, dependency_tags)
    else:
        query = """
            SELECT * FROM atcg_shared_fixtures
            WHERE project_name IN (%s, 'GLOBAL')
              AND language = %s
              AND framework = %s
            ORDER BY usage_count DESC
        """
        params = (project_name, language, framework)

    results = await db.execute(query, params)
    logger.info(
        f"Fixture registry query: {len(results)} fixtures found for "
        f"project={project_name}, lang={language}, framework={framework}"
    )
    return results


async def register_fixture(
    db: NeonConnection,
    project_name: str,
    fixture_key: str,
    fixture_code: str,
    language: str,
    framework: str,
    layer_tags: list[str],
    tags: list[str],
    created_by_run: str | UUID,
) -> dict[str, Any] | None:
    """
    Register a new fixture in the shared registry.

    Uses INSERT ... ON CONFLICT to handle duplicate fixture_key gracefully
    (updates the code and bumps usage_count if the fixture already exists).

    Args:
        db: Active NeonConnection
        project_name: Project scope (or 'GLOBAL')
        fixture_key: Unique key, e.g., 'mock_neon_pool', 'factory_user_admin'
        fixture_code: Complete fixture/mock code as string
        language: Target language
        framework: Test framework
        layer_tags: Which layers use this fixture, e.g., ['UNIT', 'INTEGRATION']
        tags: Descriptive tags, e.g., ['neon', 'db', 'async']
        created_by_run: The run_id that generated this fixture

    Returns:
        The inserted/updated fixture record
    """
    import json

    query = """
        INSERT INTO atcg_shared_fixtures
            (project_name, fixture_key, fixture_code, language, framework,
             layer_tags, tags, created_by_run)
        VALUES (%s, %s, %s, %s, %s, %s::JSONB, %s::JSONB, %s)
        ON CONFLICT (project_name, fixture_key, language, framework)
        DO UPDATE SET
            fixture_code = EXCLUDED.fixture_code,
            usage_count = atcg_shared_fixtures.usage_count + 1,
            last_used_at = NOW(),
            layer_tags = EXCLUDED.layer_tags
        RETURNING *
    """
    result = await db.execute_one(
        query,
        (
            project_name,
            fixture_key,
            fixture_code,
            language,
            framework,
            json.dumps(layer_tags),
            json.dumps(tags),
            str(created_by_run),
        ),
    )

    if result:
        logger.info(f"Registered fixture: {fixture_key} (project={project_name})")
    return result


async def increment_usage(db: NeonConnection, fixture_id: str | UUID) -> None:
    """Bump usage_count and update last_used_at for a fixture."""
    await db.execute(
        """
        UPDATE atcg_shared_fixtures
        SET usage_count = usage_count + 1,
            last_used_at = NOW()
        WHERE fixture_id = %s
        """,
        (str(fixture_id),),
    )


async def find_fixture_by_key(
    db: NeonConnection,
    project_name: str,
    fixture_key: str,
    language: str,
    framework: str,
) -> dict[str, Any] | None:
    """Look up a specific fixture by its unique key."""
    return await db.execute_one(
        """
        SELECT * FROM atcg_shared_fixtures
        WHERE project_name IN (%s, 'GLOBAL')
          AND fixture_key = %s
          AND language = %s
          AND framework = %s
        """,
        (project_name, fixture_key, language, framework),
    )
