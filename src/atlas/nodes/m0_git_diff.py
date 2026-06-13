"""
M0: Git Diff Filter — Identifies changed files and functions for targeted test generation.

This is the entry point of the ATLAS pipeline. It analyzes the git repository
to determine which source files have changed and extracts function-level
diff information for targeted test generation.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import git

from atlas.state import ATLASState

logger = logging.getLogger(__name__)

# File extensions we care about per language
SOURCE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".java",
    ".go",
    ".mjs",
    ".cjs",
}

# Patterns to exclude from analysis
EXCLUDE_PATTERNS = {
    "test_",
    "_test.",
    ".test.",
    ".spec.",
    "__pycache__",
    "node_modules",
    ".git",
    "dist/",
    "build/",
    ".venv/",
    "venv/",
    "migrations/",
    "alembic/",
}


def _is_source_file(file_path: str) -> bool:
    """Check if a file is a source code file (not test, config, or asset)."""
    path = Path(file_path)

    # Check extension
    if path.suffix not in SOURCE_EXTENSIONS:
        return False

    # Check exclusion patterns
    file_str = str(path).replace("\\", "/").lower()
    return not any(pattern in file_str for pattern in EXCLUDE_PATTERNS)


def _extract_diff_hunks(diff_item: git.Diff) -> list[dict[str, Any]]:
    """Extract function-level diff information from a git diff item."""
    hunks: list[dict[str, Any]] = []

    try:
        diff_text = diff_item.diff
        if isinstance(diff_text, bytes):
            diff_text = diff_text.decode("utf-8", errors="replace")

        if not diff_text:
            return hunks

        # Parse unified diff to extract changed line ranges
        current_hunk: dict[str, Any] | None = None
        for line in diff_text.split("\n"):
            if line.startswith("@@"):
                # Parse hunk header: @@ -old_start,old_count +new_start,new_count @@
                if current_hunk:
                    hunks.append(current_hunk)
                current_hunk = {
                    "header": line,
                    "added_lines": [],
                    "removed_lines": [],
                    "context": [],
                }
            elif current_hunk is not None:
                if line.startswith("+") and not line.startswith("+++"):
                    current_hunk["added_lines"].append(line[1:])
                elif line.startswith("-") and not line.startswith("---"):
                    current_hunk["removed_lines"].append(line[1:])
                else:
                    current_hunk["context"].append(line)

        if current_hunk:
            hunks.append(current_hunk)

    except Exception as e:
        logger.warning(f"Failed to parse diff hunks: {e}")

    return hunks


def m0_git_diff_filter(state: ATLASState) -> ATLASState:
    """
    M0: Git Diff Filter node.

    Analyzes the git repository to find changed source files.
    If no git repo or no changes, processes all source files in the project.

    Updates state with:
        - changed_files: List of changed source file paths
        - diff_hunks: Function-level diff details per file
    """
    project_root = state.get("project_context", {}).get("project_root", ".")
    repo_path = Path(project_root)

    changed_files: list[str] = []
    diff_hunks: list[dict[str, Any]] = []

    try:
        repo = git.Repo(repo_path, search_parent_directories=True)

        # Strategy 1: Staged changes (git diff --cached)
        staged_diffs = repo.index.diff("HEAD")

        # Strategy 2: Unstaged changes (git diff)
        unstaged_diffs = repo.index.diff(None)

        # Strategy 3: Untracked files
        untracked = repo.untracked_files

        # Process staged diffs
        for diff_item in staged_diffs:
            file_path = diff_item.b_path or diff_item.a_path
            if file_path and _is_source_file(file_path):
                if (repo_path / file_path).exists() and file_path not in changed_files:
                    changed_files.append(file_path)
                    diff_hunks.append(
                        {
                            "file": file_path,
                            "change_type": diff_item.change_type or "M",
                            "hunks": _extract_diff_hunks(diff_item),
                        }
                    )

        # Process unstaged diffs
        for diff_item in unstaged_diffs:
            file_path = diff_item.b_path or diff_item.a_path
            if file_path and _is_source_file(file_path):
                if (repo_path / file_path).exists() and file_path not in changed_files:
                    changed_files.append(file_path)
                    diff_hunks.append(
                        {
                            "file": file_path,
                            "change_type": diff_item.change_type or "M",
                            "hunks": _extract_diff_hunks(diff_item),
                        }
                    )

        # Process untracked source files
        for file_path in untracked:
            if _is_source_file(file_path) and file_path not in changed_files:
                changed_files.append(file_path)
                diff_hunks.append(
                    {
                        "file": file_path,
                        "change_type": "A",  # Added
                        "hunks": [],
                    }
                )

        if not changed_files:
            logger.info("No git changes detected — scanning all source files")
            changed_files, diff_hunks = _scan_all_sources(repo_path)

    except git.InvalidGitRepositoryError:
        logger.info("Not a git repository — scanning all source files")
        changed_files, diff_hunks = _scan_all_sources(repo_path)
    except Exception as e:
        logger.warning(f"Git diff failed ({e}) — scanning all source files")
        changed_files, diff_hunks = _scan_all_sources(repo_path)

    logger.info(f"M0: Found {len(changed_files)} source files to process")

    return {
        "changed_files": changed_files,
        "diff_hunks": diff_hunks,
    }


def _scan_all_sources(project_root: Path) -> tuple[list[str], list[dict[str, Any]]]:
    """Fallback: scan all source files in the project."""
    changed_files: list[str] = []
    diff_hunks: list[dict[str, Any]] = []

    for ext in SOURCE_EXTENSIONS:
        for file_path in project_root.rglob(f"*{ext}"):
            rel_path = str(file_path.relative_to(project_root))
            if _is_source_file(rel_path):
                changed_files.append(rel_path)
                diff_hunks.append(
                    {
                        "file": rel_path,
                        "change_type": "A",
                        "hunks": [],
                    }
                )

    return changed_files, diff_hunks
