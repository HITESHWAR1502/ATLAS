"""
M1: Ingestion + Neon Fixture Registry Query

Detects project language/framework, queries Neon for existing fixtures and
test history, and populates the upstream context fields in the state.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from atlas.config import ATLASConfig
from atlas.state import ATLASState

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Language / Framework Detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# File patterns → language detection
LANGUAGE_INDICATORS = {
    "python": {
        "files": ["setup.py", "pyproject.toml", "requirements.txt", "Pipfile"],
        "extensions": [".py"],
    },
    "typescript": {
        "files": ["tsconfig.json"],
        "extensions": [".ts", ".tsx"],
    },
    "javascript": {
        "files": ["package.json"],
        "extensions": [".js", ".jsx", ".mjs", ".cjs"],
    },
    "java": {
        "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
        "extensions": [".java"],
    },
    "go": {
        "files": ["go.mod", "go.sum"],
        "extensions": [".go"],
    },
}

# Framework detection patterns
FRAMEWORK_INDICATORS = {
    # Python
    "fastapi": ["fastapi", "from fastapi"],
    "django": ["django", "DJANGO_SETTINGS_MODULE"],
    "flask": ["flask", "from flask"],
    # JS/TS
    "express": ["express", "require('express')", "from 'express'"],
    "nextjs": ["next", "next.config"],
    "nestjs": ["@nestjs", "NestFactory"],
    # Java
    "spring": ["springframework", "@SpringBootApplication"],
}

# Test framework detection
TEST_FRAMEWORK_MAP = {
    "python": {
        "pytest": ["pytest", "conftest.py", "@pytest.fixture"],
        "unittest": ["unittest", "TestCase"],
    },
    "typescript": {
        "vitest": ["vitest", "vi.fn()", "vi.mock("],
        "jest": ["jest", "jest.fn()", "jest.mock("],
    },
    "javascript": {
        "vitest": ["vitest", "vi.fn()", "vi.mock("],
        "jest": ["jest", "jest.fn()", "jest.mock("],
    },
    "java": {
        "junit5": ["@Test", "org.junit.jupiter"],
        "junit4": ["org.junit.Test"],
    },
    "go": {
        "testing": ["testing.T", "testing.B"],
    },
}


def _detect_language(project_root: Path) -> str:
    """Detect primary project language."""
    scores: dict[str, int] = {}

    for lang, indicators in LANGUAGE_INDICATORS.items():
        score = 0
        # Check for indicator files
        for fname in indicators["files"]:
            if (project_root / fname).exists():
                score += 10

        # Count source files
        for ext in indicators["extensions"]:
            count = len(list(project_root.rglob(f"*{ext}")))
            score += min(count, 50)  # Cap at 50 to avoid huge repos skewing

        if score > 0:
            scores[lang] = score

    if not scores:
        return "python"  # Default

    # TypeScript takes priority over JavaScript if both detected
    if scores.get("typescript", 0) > 0 and scores.get("javascript", 0) > 0:
        scores["javascript"] = max(0, scores["javascript"] - scores["typescript"])

    return max(scores, key=scores.get)  # type: ignore[arg-type]


def _detect_framework(project_root: Path, language: str) -> str | None:
    """Detect web/app framework by scanning common config files and imports."""
    # Read key files for framework hints
    files_to_scan = []
    if language in ("javascript", "typescript"):
        pkg_json = project_root / "package.json"
        if pkg_json.exists():
            files_to_scan.append(pkg_json.read_text(encoding="utf-8", errors="replace"))
    elif language == "python":
        for fname in ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"]:
            fpath = project_root / fname
            if fpath.exists():
                files_to_scan.append(fpath.read_text(encoding="utf-8", errors="replace"))
    elif language == "java":
        for fname in ["pom.xml", "build.gradle", "build.gradle.kts"]:
            fpath = project_root / fname
            if fpath.exists():
                files_to_scan.append(fpath.read_text(encoding="utf-8", errors="replace"))

    combined = "\n".join(files_to_scan).lower()

    for framework, patterns in FRAMEWORK_INDICATORS.items():
        if any(p.lower() in combined for p in patterns):
            return framework

    return None


def _detect_test_framework(project_root: Path, language: str) -> str:
    """Detect existing test framework."""
    frameworks = TEST_FRAMEWORK_MAP.get(language, {})

    # Scan test files and config for clues
    test_content = ""
    for pattern in ["test_*", "*_test.*", "*.test.*", "*.spec.*", "conftest.py"]:
        for f in project_root.rglob(pattern):
            try:
                test_content += f.read_text(encoding="utf-8", errors="replace")[:2000]
            except Exception:
                pass

    # Also check package config
    for config_name in ["package.json", "pyproject.toml", "pom.xml"]:
        config_path = project_root / config_name
        if config_path.exists():
            try:
                test_content += config_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                pass

    for fw_name, indicators in frameworks.items():
        if any(ind.lower() in test_content.lower() for ind in indicators):
            return fw_name

    # Defaults per language
    defaults = {
        "python": "pytest",
        "typescript": "vitest",
        "javascript": "jest",
        "java": "junit5",
        "go": "testing",
    }
    return defaults.get(language, "pytest")


def _detect_project_name(project_root: Path) -> str:
    """Extract project name from config or directory name."""
    # Try package.json
    pkg_json = project_root / "package.json"
    if pkg_json.exists():
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
            if "name" in data:
                return data["name"]
        except Exception:
            pass

    # Try pyproject.toml
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text(encoding="utf-8")
            for line in content.split("\n"):
                if line.strip().startswith("name"):
                    return line.split("=")[1].strip().strip('"').strip("'")
        except Exception:
            pass

    return project_root.name


async def m1_ingestion(state: ATLASState, config: ATLASConfig) -> ATLASState:
    """
    M1: Ingestion.

    Detects project context.

    Updates state with:
        - project_context: Language, framework, conventions
    """
    project_root = Path(
        state.get("project_context", {}).get("project_root", str(config.project_root))
    )

    # ── Detect project characteristics ────────────────────────────────────────
    language = _detect_language(project_root)
    framework = _detect_framework(project_root, language)
    test_framework = _detect_test_framework(project_root, language)
    project_name = _detect_project_name(project_root)

    project_context = {
        "project_name": project_name,
        "project_root": str(project_root),
        "language": language,
        "framework": framework,
        "test_framework": test_framework,
        "conventions": {
            "naming": "snake_case" if language == "python" else "camelCase",
            "async_style": "asyncio" if language == "python" else "promise",
        },
    }

    logger.info(
        f"M1: Detected project '{project_name}' — "
        f"lang={language}, framework={framework}, tests={test_framework}"
    )

    return {
        "project_context": project_context,
    }
