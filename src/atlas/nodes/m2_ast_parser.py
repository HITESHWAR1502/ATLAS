"""
M2: AST Parser — Multi-language AST parsing via tree-sitter.

Extracts per-function metadata: signature, parameters, return type,
dependencies, cyclomatic complexity, and function classification.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from atlas.state import ATLASState, FunctionClassification

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dependency detection patterns (heuristic-based for initial version)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DB_PATTERNS = [
    "query",
    "execute",
    "fetch",
    "fetchone",
    "fetchall",
    "fetchrow",
    "fetchval",
    "insert",
    "update",
    "delete",
    "select",
    "commit",
    "rollback",
    "transaction",
    "cursor",
    "connection",
    "pool",
    "postgres",
    "mysql",
    "sqlite",
    "prisma",
    "drizzle",
    "sequelize",
    "sqlalchemy",
    "typeorm",
]

AUTH_PATTERNS = [
    "auth",
    "login",
    "logout",
    "signin",
    "signup",
    "register",
    "token",
    "jwt",
    "session",
    "cookie",
    "password",
    "credential",
    "bcrypt",
    "hash_password",
    "verify_password",
    "check_password",
    "permission",
    "role",
    "acl",
    "rbac",
    "scope",
]

HTTP_PATTERNS = [
    "fetch",
    "request",
    "axios",
    "http",
    "https",
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "api",
    "endpoint",
    "route",
    "handler",
    "req",
    "res",
    "response",
    "request",
]

CACHE_PATTERNS = [
    "cache",
    "redis",
    "memcached",
    "get_cache",
    "set_cache",
    "invalidate",
    "ttl",
    "expire",
]

FILE_PATTERNS = [
    "open(",
    "read_file",
    "write_file",
    "os.path",
    "fs.readFile",
    "fs.writeFile",
    "path.join",
    "upload",
    "download",
    "file_path",
]


def _classify_function(
    name: str,
    source: str,
    decorators: list[str],
    params: list[dict[str, Any]],
) -> tuple[FunctionClassification, list[str], dict[str, bool]]:
    """
    Classify a function and detect its characteristics.

    Returns:
        (classification, dependencies, characteristics_dict)
    """
    source_lower = source.lower()
    name_lower = name.lower()
    deps: list[str] = []
    chars = {
        "accepts_user_input": False,
        "performs_auth": False,
        "accesses_db": False,
        "handles_files": False,
        "calls_external": False,
    }

    # ── Detect dependencies ───────────────────────────────────────────────────
    if any(p in source_lower for p in DB_PATTERNS):
        deps.append("database")
        chars["accesses_db"] = True

    if any(p in source_lower for p in AUTH_PATTERNS):
        deps.append("auth")
        chars["performs_auth"] = True

    if any(p in source_lower for p in HTTP_PATTERNS):
        deps.append("http")
        chars["calls_external"] = True

    if any(p in source_lower for p in CACHE_PATTERNS):
        deps.append("cache")

    if any(p in source_lower for p in FILE_PATTERNS):
        deps.append("filesystem")
        chars["handles_files"] = True

    # ── Check for user input handling ─────────────────────────────────────────
    input_indicators = ["request", "req.", "body", "params", "query", "form_data", "payload"]
    if any(ind in source_lower for ind in input_indicators):
        chars["accepts_user_input"] = True

    # ── Classify ──────────────────────────────────────────────────────────────
    # Check decorators for route handlers
    route_decorators = [
        "@app.",
        "@router.",
        "@get",
        "@post",
        "@put",
        "@delete",
        "@RequestMapping",
        "@GetMapping",
        "@PostMapping",
    ]
    is_handler = any(d for d in decorators if any(rd in d for rd in route_decorators))

    if is_handler or any(kw in name_lower for kw in ["handler", "endpoint", "view"]):
        return FunctionClassification.API_HANDLER, deps, chars

    if chars["performs_auth"]:
        return FunctionClassification.AUTH_HANDLER, deps, chars

    if any(kw in name_lower for kw in ["service", "use_case", "interactor"]):
        return FunctionClassification.SERVICE_LAYER, deps, chars

    if chars["accesses_db"] and not chars["calls_external"]:
        return FunctionClassification.DB_ACCESSOR, deps, chars

    if any(kw in name_lower for kw in ["cache", "redis"]):
        return FunctionClassification.CACHE_LAYER, deps, chars

    if any(kw in name_lower for kw in ["process", "transform", "parse", "convert", "serialize"]):
        return FunctionClassification.DATA_PROCESSOR, deps, chars

    if any(kw in name_lower for kw in ["workflow", "pipeline", "orchestrat"]):
        return FunctionClassification.WORKFLOW_ORCHESTRATOR, deps, chars

    if deps:
        return FunctionClassification.DOMAIN_LOGIC, deps, chars

    if any(kw in name_lower for kw in ["util", "helper", "format", "validate", "sanitize"]):
        return FunctionClassification.UTILITY_HELPER, deps, chars

    return FunctionClassification.PURE_FUNCTION, deps, chars


def _estimate_complexity(source: str) -> int:
    """Estimate cyclomatic complexity via simple heuristic counting."""
    keywords = [
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "except ",
        "case ",
        "? ",
        "&&",
        "||",
        "and ",
        "or ",
        "catch",
        "switch",
        "?.",
        "??",
    ]
    return 1 + sum(source.lower().count(kw) for kw in keywords)


def _extract_functions_python(source: str, file_path: str) -> list[dict[str, Any]]:
    """Extract functions from Python source using tree-sitter."""
    import tree_sitter_python as tspython
    from tree_sitter import Language, Parser

    PY_LANGUAGE = Language(tspython.language())
    parser = Parser(PY_LANGUAGE)
    tree = parser.parse(bytes(source, "utf8"))

    functions: list[dict[str, Any]] = []
    source_bytes = source.encode("utf-8")

    def find_functions(node: Any, func_nodes: list[Any]) -> None:
        if node.type in ["function_definition", "async_function_definition"]:
            func_nodes.append(node)
        for child in node.children:
            # Skip inner classes or nested functions for now
            if node.type == "class_definition" and child.type == "block":
                find_functions(child, func_nodes)
            elif node.type != "function_definition":
                find_functions(child, func_nodes)

    func_nodes: list[Any] = []
    find_functions(tree.root_node, func_nodes)

    for node in func_nodes:
        is_async = node.type == "async_function_definition"

        name_node = node.child_by_field_name("name")
        if not name_node:
            continue

        name = source_bytes[name_node.start_byte : name_node.end_byte].decode("utf-8")

        # Skip private/magic methods (except __init__)
        if name.startswith("_") and name != "__init__":
            continue

        params_node = node.child_by_field_name("parameters")
        params_str = (
            source_bytes[params_node.start_byte : params_node.end_byte].decode("utf-8")
            if params_node
            else "()"
        )

        return_node = node.child_by_field_name("return_type")
        return_type = (
            source_bytes[return_node.start_byte : return_node.end_byte].decode("utf-8")
            if return_node
            else None
        )

        func_source = source_bytes[node.start_byte : node.end_byte].decode("utf-8")

        # Simple extraction of decorators for now
        decorators = []
        prev = node.prev_sibling
        while prev and prev.type == "decorator":
            decorators.append(source_bytes[prev.start_byte : prev.end_byte].decode("utf-8"))
            prev = prev.prev_sibling

        params = _parse_python_params(params_str[1:-1])  # Strip parens

        # Classify
        classification, deps, chars = _classify_function(name, func_source, decorators, params)

        module_id = file_path.replace("/", ".").replace("\\", ".").rsplit(".", 1)[0]

        functions.append(
            {
                "id": f"{module_id}.{name}",
                "name": name,
                "module_path": file_path,
                "source_code": func_source,
                "signature": f"{'async ' if is_async else ''}def {name}{params_str}{' -> ' + return_type if return_type else ''}:",
                "parameters": params,
                "return_type": return_type,
                "decorators": decorators,
                "classification": classification.value,
                "cyclomatic_complexity": _estimate_complexity(func_source),
                "dependencies": deps,
                "is_async": is_async,
                **chars,
            }
        )

    return functions


def _parse_python_params(params_str: str) -> list[dict[str, Any]]:
    """Parse Python function parameters."""
    params: list[dict[str, Any]] = []
    if not params_str.strip():
        return params

    for p in params_str.split(","):
        p = p.strip()
        if not p or p == "self" or p == "cls":
            continue

        param_info: dict[str, Any] = {"name": p, "type": None, "default": None}

        # Handle type annotations
        if ":" in p:
            parts = p.split(":", 1)
            param_info["name"] = parts[0].strip()
            type_and_default = parts[1].strip()
            if "=" in type_and_default:
                type_part, default = type_and_default.rsplit("=", 1)
                param_info["type"] = type_part.strip()
                param_info["default"] = default.strip()
            else:
                param_info["type"] = type_and_default
        elif "=" in p:
            name_part, default = p.split("=", 1)
            param_info["name"] = name_part.strip()
            param_info["default"] = default.strip()

        params.append(param_info)

    return params


def _extract_decorators(source: str, func_start: int) -> list[str]:
    """Extract decorators above a function definition."""
    decorators: list[str] = []
    lines_before = source[:func_start].rstrip().split("\n")

    for line in reversed(lines_before):
        stripped = line.strip()
        if stripped.startswith("@"):
            decorators.insert(0, stripped)
        elif stripped == "" or stripped.startswith("#"):
            continue
        else:
            break

    return decorators


def m2_ast_parser(state: ATLASState) -> ATLASState:
    """
    M2: AST Parser node.

    Parses changed source files to extract function-level metadata.
    Uses regex-based parsing as a foundation (tree-sitter integration
    for enhanced accuracy is available via the parsers/ package).

    Updates state with:
        - module_context: Per-module metadata
        - target_context: Per-function targets with classification
    """
    project_context = state.get("project_context", {})
    project_root = Path(project_context.get("project_root", "."))
    language = project_context.get("language", "python")
    changed_files = state.get("changed_files", [])

    all_functions: list[dict[str, Any]] = []
    module_contexts: list[dict[str, Any]] = []
    vulnerable_imports: list[dict[str, str]] = []

    for file_path in changed_files:
        full_path = project_root / file_path
        if not full_path.exists():
            logger.warning(f"M2: File not found: {file_path}")
            continue

        try:
            source = full_path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.warning(f"M2: Failed to read {file_path}: {e}")
            continue

        # Extract functions based on language
        if language == "python":
            functions = _extract_functions_python(source, file_path)
        else:
            # For JS/TS/Java/Go, use a generalized regex approach
            # (tree-sitter integration provides better accuracy)
            functions = _extract_functions_generic(source, file_path, language)

        all_functions.extend(functions)

        # Build module context
        imports = _extract_imports(source, language)
        module_contexts.append(
            {
                "module_path": file_path,
                "imports": imports,
                "dependencies": list(
                    {dep for fn in functions for dep in fn.get("dependencies", [])}
                ),
                "functions_count": len(functions),
                "vulnerable_imports": vulnerable_imports,
            }
        )

    logger.info(f"M2: Parsed {len(changed_files)} files → {len(all_functions)} functions extracted")

    return {
        "module_context": {
            "modules": module_contexts,
            "total_functions": len(all_functions),
        },
        "target_context": {
            "functions": all_functions,
        },
    }


def _extract_functions_generic(source: str, file_path: str, language: str) -> list[dict[str, Any]]:
    """Generic function extraction for JS/TS/Java/Go."""
    import re

    functions: list[dict[str, Any]] = []

    if language in ("javascript", "typescript"):
        # Match: function name(...) { , async function name(...) { ,
        #        const name = (...) => { , export function name(...)
        patterns = [
            re.compile(
                r"(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\((.*?)\)",
                re.MULTILINE | re.DOTALL,
            ),
            re.compile(
                r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\((.*?)\)\s*=>",
                re.MULTILINE | re.DOTALL,
            ),
        ]
    elif language == "java":
        patterns = [
            re.compile(
                r"(?:public|private|protected)?\s*(?:static\s+)?(?:\w+)\s+(\w+)\s*\((.*?)\)",
                re.MULTILINE | re.DOTALL,
            ),
        ]
    elif language == "go":
        patterns = [
            re.compile(
                r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\((.*?)\)",
                re.MULTILINE | re.DOTALL,
            ),
        ]
    else:
        return functions

    for pattern in patterns:
        for match in pattern.finditer(source):
            name = match.group(1)
            params_str = match.group(2)
            is_async = "async" in source[max(0, match.start() - 20) : match.start()]

            func_source = source[match.start() : match.start() + 500]  # Approximate body
            classification, deps, chars = _classify_function(name, func_source, [], [])
            module_id = file_path.replace("/", ".").replace("\\", ".").rsplit(".", 1)[0]

            functions.append(
                {
                    "id": f"{module_id}.{name}",
                    "name": name,
                    "module_path": file_path,
                    "source_code": func_source,
                    "signature": match.group(0).strip(),
                    "parameters": [{"name": p.strip()} for p in params_str.split(",") if p.strip()],
                    "return_type": None,
                    "decorators": [],
                    "classification": classification.value,
                    "cyclomatic_complexity": _estimate_complexity(func_source),
                    "dependencies": deps,
                    "is_async": is_async,
                    **chars,
                }
            )

    return functions


def _extract_imports(source: str, language: str) -> list[str]:
    """Extract import statements from source."""
    import re

    imports: list[str] = []

    if language == "python":
        for match in re.finditer(r"^(?:from\s+(\S+)\s+)?import\s+(.+)$", source, re.MULTILINE):
            module = match.group(1) or match.group(2).split(",")[0].strip()
            imports.append(module)
    elif language in ("javascript", "typescript"):
        for match in re.finditer(r"(?:import|require)\s*\(?['\"](.+?)['\"]", source):
            imports.append(match.group(1))
    elif language == "java":
        for match in re.finditer(r"^import\s+(.+?);", source, re.MULTILINE):
            imports.append(match.group(1))
    elif language == "go":
        for match in re.finditer(r'"(.+?)"', source):
            imports.append(match.group(1))

    return imports
