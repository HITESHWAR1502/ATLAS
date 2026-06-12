"""
M7: Disk Writer Node

Writes generated tests directly to the local filesystem in the appropriate test directory.
"""

from __future__ import annotations

import logging
from pathlib import Path

from atlas.state import ATLASState

logger = logging.getLogger(__name__)


def _resolve_test_path(project_root: Path, file_path: str) -> Path:
    """Resolve an agent-provided test path while keeping writes inside tests/."""
    provided_path = Path(file_path)
    if provided_path.is_absolute():
        return project_root / "tests" / provided_path.name

    candidate = (project_root / provided_path).resolve()
    tests_root = (project_root / "tests").resolve()

    try:
        candidate.relative_to(tests_root)
        return candidate
    except ValueError:
        return tests_root / provided_path.name


async def m7_disk_writer(state: ATLASState) -> ATLASState:
    """
    M7: Writes generated test code to the local filesystem.
    """
    writes_queue = state.get("disk_writes_queue", [])
    if not writes_queue:
        logger.info("M7: No test files to write.")
        return state

    project_root = Path(state.get("project_context", {}).get("project_root", "."))

    latest_writes: dict[Path, str] = {}

    for write_payload in writes_queue:
        # Expected format from DiskWritePayload -> TestFileWrite
        file_path = write_payload.get("file_path")
        content = write_payload.get("content")

        if not file_path or not content:
            continue

        target_path = _resolve_test_path(project_root, file_path)
        latest_writes[target_path] = content

    for target_path, content in latest_writes.items():
        # Ensure parent directories exist
        target_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            target_path.write_text(content, encoding="utf-8")
            logger.info(f"M7: Wrote test file to {target_path}")
        except Exception as e:
            logger.error(f"M7: Failed to write {target_path}: {e}")

    # Clear queue after writing
    return {
        "disk_writes_queue": []
    }
