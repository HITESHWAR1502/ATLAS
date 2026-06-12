from __future__ import annotations

import unittest
from unittest.mock import MagicMock, AsyncMock
import pytest
from pathlib import Path
from enum import Enum

from atcg.state import ATCGState, TestLayer
from atcg.layers.unit import UnitLayerAgent
from atcg.nodes.m6_test_executor import m6_test_executor
from atcg.nodes.m7_neon_writer import m7_neon_writer
from atcg.nodes.m8_coverage import m8_coverage_runner
from atcg.nodes.m5_join import m5_join
from atcg.cli import _generate_markdown_report


class MockConfig:
    pass


class DummyBaseAgent(UnitLayerAgent):
    def __init__(self):
        self._config = MockConfig()


def test_step6_emit_output_composite_key():
    agent = DummyBaseAgent()
    state: ATCGState = {
        "run_id": "test-run-123",
        "target_id": "math.add",
        "attempt": 1,
    }
    test_output = {
        "test_code": "def test_add(): assert 1 + 1 == 2",
        "file_path": "tests/unit/test_add.py",
        "framework": "pytest",
        "confidence": 0.95,
        "quality_flags": [],
        "fixtures_reused": [],
        "fixtures_registered": [],
        "reasoning": "Simple unit test",
        "active_layer": "UNIT",
        "target_id": "math.add",
    }
    
    # We call the internal _step6_emit_output
    result = agent._step6_emit_output(state, test_output)
    
    assert "layer_outputs" in result
    assert "math.add_UNIT" in result["layer_outputs"]
    assert result["layer_outputs"]["math.add_UNIT"] == test_output


def test_m6_test_executor_lookup():
    # Test that m6_test_executor finds test code using composite key
    test_output = {
        "test_code": "def test_add(): assert 1 + 1 == 2",
        "active_layer": "UNIT",
        "target_id": "math.add",
    }
    
    state: ATCGState = {
        "active_layer": "UNIT",
        "target_id": "math.add",
        "layer_outputs": {
            "math.add_UNIT": test_output
        },
        "project_context": {"project_root": ""},
        "attempt": 1,
    }
    
    # Mock subprocess.run to prevent actual test execution
    import subprocess
    original_run = subprocess.run
    try:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "PASSED"
        mock_result.stderr = ""
        subprocess.run = MagicMock(return_value=mock_result)
        
        updated_state = m6_test_executor(state)
        assert updated_state["verdict"] == "PASS"
    finally:
        subprocess.run = original_run


@pytest.mark.asyncio
async def test_m7_neon_writer_composite_key():
    test_output_1 = {
        "target_id": "math.add",
        "active_layer": TestLayer.UNIT,
        "test_code": "def test_add(): pass",
        "file_path": "tests/unit/test_add.py",
    }
    test_output_2 = {
        "target_id": "math.subtract",
        "active_layer": TestLayer.UNIT,
        "test_code": "def test_sub(): pass",
        "file_path": "tests/unit/test_sub.py",
    }
    
    state: ATCGState = {
        "run_id": "run-1",
        "verdict": "PASS",
        "layer_outputs": {
            "math.add_UNIT": test_output_1,
            "math.subtract_UNIT": test_output_2,
        },
        "neon_write": {},
    }
    
    mock_db = MagicMock()
    
    # Mock write_layer_run
    import atcg.nodes.m7_neon_writer
    original_write = atcg.nodes.m7_neon_writer.write_layer_run
    
    called_layers = []
    
    async def mock_write_layer_run(db, layer, payload):
        called_layers.append(layer)
        return {"ok": True}
        
    atcg.nodes.m7_neon_writer.write_layer_run = mock_write_layer_run
    
    try:
        result = await m7_neon_writer(state, mock_db)
        # Should have processed both
        assert len(called_layers) == 2
        assert "UNIT" in called_layers
        assert result["neon_write"]["records_count"] == 2
    finally:
        atcg.nodes.m7_neon_writer.write_layer_run = original_write


@pytest.mark.asyncio
async def test_m8_coverage_runner_composite_keys(tmp_path):
    test_output_1 = {
        "target_id": "math.add",
        "test_code": "def test_add(): pass",
        "file_path": "tests/unit/test_add.py",
    }
    
    state: ATCGState = {
        "layer_outputs": {
            "math.add_UNIT": test_output_1,
        },
        "project_context": {"project_root": str(tmp_path), "language": "python"},
    }
    
    # We mock _run_coverage to avoid actual pytest run
    import atcg.nodes.m8_coverage
    original_run_cov = atcg.nodes.m8_coverage._run_coverage
    atcg.nodes.m8_coverage._run_coverage = MagicMock(return_value={"executed": True})
    
    try:
        result = await m8_coverage_runner(state)
        assert len(result["coverage_results"]["files_written"]) == 1
        assert (tmp_path / "tests/unit/test_add.py").exists()
    finally:
        atcg.nodes.m8_coverage._run_coverage = original_run_cov


def test_m5_join_composite_keys():
    state: ATCGState = {
        "layer_outputs": {
            "math.add_UNIT": {"test_code": "import pytest\ndef test_add(): pass", "quality_flags": ["OK"]},
            "math.subtract_UNIT": {"test_code": "import pytest\ndef test_sub(): pass"},
        },
        "neon_writes_queue": [],
    }
    
    result = m5_join(state)
    assert len(result["layer_outputs"]) == 2
    assert "IMPORT_CONFLICTS_DETECTED" not in "".join(result["quality_flags"])


def test_cli_report_generation(tmp_path):
    state = {
        "verdict": "PASS",
        "test_plan": {"total_functions": 2},
        "selected_layers": ["UNIT"],
        "layer_outputs": {
            "math.add_UNIT": {
                "active_layer": TestLayer.UNIT,
                "target_id": "math.add",
                "confidence": 0.9,
                "test_code": "def test_add(): pass",
            }
        }
    }
    
    report_file = tmp_path / "atlas_test_report.md"
    _generate_markdown_report(state, report_file)
    
    content = report_file.read_text(encoding="utf-8")
    assert "## Layer Results" in content
    assert "### UNIT - math.add" in content
    assert "- **Confidence:** 90%" in content
