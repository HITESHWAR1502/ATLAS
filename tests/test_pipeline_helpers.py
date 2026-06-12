import os
from pathlib import Path

from atlas.layers.base import _extract_json_object, _extract_last_code_block
from atlas.nodes.m6_test_executor import _build_rejection_feedback, m6_test_executor
from atlas.nodes.m7_disk_writer import _resolve_test_path
from atlas.nodes.m8_coverage import _python_test_env


def test_extract_last_code_block_ignores_json_block() -> None:
    raw_output = """```json
{"file_path": "tests/unit/example.py"}
```

```python
def test_example():
    assert True
```"""

    assert _extract_last_code_block(raw_output) == "def test_example():\n    assert True"


def test_extract_json_object_from_mixed_llm_output() -> None:
    raw_output = """Here is the test metadata:
{"file_path": "tests/unit/test_sample.py", "confidence": 0.9}

```python
def test_sample():
    assert True
```"""

    assert _extract_json_object(raw_output) == (
        '{"file_path": "tests/unit/test_sample.py", "confidence": 0.9}'
    )


def test_m6_skips_live_execution_for_non_python_projects() -> None:
    state = {
        "active_layer": "UNIT",
        "target_file": "src/example.ts",
        "project_context": {"language": "typescript"},
        "attempt": 1,
    }

    result = m6_test_executor(state)

    assert result["verdict"] == "PASS"
    assert result["execution_result"]["status"] == "SKIPPED"
    assert "typescript" in result["execution_result"]["reason"]


def test_m6_builds_deterministic_retry_feedback() -> None:
    feedback = _build_rejection_feedback(
        active_layer="UNIT",
        target_file="test.py",
        stdout="================= 1 failed, 2 passed in 0.12s =================",
        stderr="",
        failure_reason="E   ModuleNotFoundError: No module named 'test'",
    )

    assert feedback["status"] == "FAIL"
    assert feedback["issues"][0]["id"] == "PYTEST_FAILURE"
    assert feedback["issues"][0]["reason"] == "E   ModuleNotFoundError: No module named 'test'"
    assert feedback["metrics"] == {
        "tests_executed": 3,
        "tests_passed": 2,
        "tests_failed": 1,
    }


def test_resolve_test_path_stays_inside_tests_directory(tmp_path: Path) -> None:
    resolved = _resolve_test_path(tmp_path, "../outside.py")

    assert resolved == (tmp_path / "tests" / "outside.py")


def test_python_test_env_includes_project_root_and_src(tmp_path: Path) -> None:
    env = _python_test_env(tmp_path)

    python_path_parts = env["PYTHONPATH"].split(os.pathsep)
    assert str(tmp_path / "src") in python_path_parts
    assert str(tmp_path) in python_path_parts
