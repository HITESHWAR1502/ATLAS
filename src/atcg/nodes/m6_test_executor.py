"""
M6: Test Executor Node

Replaces the static validator. This node writes the generated test code
to a sandboxed temporary directory, executes it via pytest, and returns
the execution results and tracebacks to drive the autonomous feedback loop.
"""

from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage

from atcg.config import ATCGConfig
from atcg.llm_router import get_llm
from atcg.state import ATCGState

logger = logging.getLogger(__name__)

MAX_TRACEBACK_CHARS = 4000

M6_EVALUATOR_PROMPT = """You are an ATLAS execution agent running under strict rate-limit and token-budget constraints.

HARD LIMITS:
- Max response: 180 tokens
- Max code generation: 80 lines
- Max issue count: 3
- Never include chain-of-thought or step-by-step reasoning

PRIMARY OBJECTIVE:
Return only actionable output required by downstream agents.

CONTEXT RULES:
- Assume shared project context already exists.
- Read only the provided target scope.
- Never repeat source code, logs, stack traces, or requirements.
- Reference files/functions by path or name only.

OUTPUT RULES:
- No introductions, conclusions, greetings, or explanations.
- No markdown unless explicitly requested.
- No repeated information.
- If nothing actionable exists, return exactly:
{"status": "PASS"}

TEST GENERATION RULES:
Generate only high-value tests:
1. Boundary cases
2. Null/empty inputs
3. Invalid types
4. Error handling
5. Security/concurrency edge cases

Avoid:
- Happy-path duplicates
- Exhaustive permutations
- Commentary about why tests matter

EVALUATION RULES:
Return only mismatches between expected and actual behavior.

REPORT FORMAT:
Return ONLY valid JSON. Do not use markdown backticks (```json).

{
  "status": "PASS|FAIL",
  "issues": [
    {
      "id": "<short_id>",
      "severity": "critical|high|medium|low",
      "location": "<file_or_function>",
      "reason": "<max 18 words>",
      "evidence": "<max 24 words>",
      "recommendation": "<max 16 words>"
    }
  ],
  "metrics": {
    "tests_executed": n,
    "tests_passed": n,
    "tests_failed": n
  }
}

RATE-LIMIT SAFETY RULES:
- If provider returns 429 or 503, do not retry within this response.
- Return a compact retry signal instead of regenerating content.
- Retry signal format:
{"status":"retry_later","provider":"<name>","retry_after_seconds":n}

TOKEN OPTIMIZATION RULES:
- Use fragments instead of full sentences.
- Merge duplicate failures.
- Prefer IDs over descriptions.
- Prefer file references over code snippets.
- Never echo the user prompt.
- Never explain execution process.

TEST EXECUTION FIX RULE:
When generating Python tests, import and call module-level functions directly.
Do NOT instantiate test classes to access production functions.

FAILSAFE:
If confidence < 70%, return:
{"status":"needs_review","reason":"<short_reason>"}
"""


def m6_test_executor(state: ATCGState) -> ATCGState:
    """
    Executes the generated test code in a sandboxed temporary directory.
    Returns the verdict (PASS/RETRY/ESCALATE) and any execution errors.
    Uses an LLM to summarize failures into a compact JSON format to save tokens.
    """
    active_layer = state.get("active_layer", "unknown")
    target_id = state.get("target_id", "unknown")
    layer_outputs = state.get("layer_outputs", {})
    output_key = f"{target_id}_{active_layer}"
    output = layer_outputs.get(output_key, layer_outputs.get(active_layer, {}))
    
    test_code = output.get("test_code", "")
    if not test_code:
        logger.warning(f"M6: No test code found for {active_layer} on {target_id}")
        return {**state, "verdict": "PASS"}  # Nothing to test
        
    project_context = state.get("project_context", {})
    project_root = project_context.get("project_root", "")
        
    # Write to temp sandbox and execute
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / f"test_{target_id.replace('.', '_')}.py"
        test_file.write_text(test_code, encoding="utf-8")
        
        # Determine PYTHONPATH so it can import the actual project code
        env = None
        if project_root:
            import os
            env = os.environ.copy()
            env["PYTHONPATH"] = str(Path(project_root) / "src") + os.pathsep + env.get("PYTHONPATH", "")
            
        logger.info(f"M6: Executing {active_layer} test for {target_id} via pytest in sandbox")
        
        try:
            # We run pytest on the temporary file
            result = subprocess.run(
                ["pytest", str(test_file), "-v"],
                capture_output=True,
                text=True,
                env=env,
                timeout=30  # Timeout to prevent hanging tests
            )
            
            stdout = result.stdout
            stderr = result.stderr
            return_code = result.returncode
            
            if return_code == 0:
                verdict = "PASS"
                rejection_feedback = None
                logger.info(f"M6: {active_layer} test PASSED. Skipping summarization.")
            else:
                verdict = "RETRY"
                # Extract the failure reason/traceback from pytest output
                failure_reason = _extract_pytest_failure(stdout, stderr)
                
                # Truncate to MAX_TRACEBACK_CHARS to save tokens
                if len(failure_reason) > MAX_TRACEBACK_CHARS:
                    failure_reason = failure_reason[-MAX_TRACEBACK_CHARS:]
                
                logger.warning(f"M6: {active_layer} test FAILED. Summarizing with LLM...")
                
                # LLM Summarization
                try:
                    config = ATCGConfig.from_env()
                    llm = get_llm(config, tool_calling=False)
                    
                    messages = [
                        SystemMessage(content=M6_EVALUATOR_PROMPT),
                        HumanMessage(content=f"Test Execution Failed.\n\nRaw Traceback:\n{failure_reason}")
                    ]
                    
                    llm_response = llm.invoke(messages)
                    response_text = llm_response.content
                    
                    if isinstance(response_text, list):
                        text_parts = [part["text"] for part in response_text if isinstance(part, dict) and "text" in part]
                        response_text = "\n".join(text_parts) if text_parts else str(response_text)
                    elif not isinstance(response_text, str):
                        response_text = str(response_text)
                        
                    # Clean up backticks if model ignored instructions
                    if response_text.startswith("```json"):
                        response_text = response_text[7:].strip()
                    if response_text.startswith("```"):
                        response_text = response_text[3:].strip()
                    if response_text.endswith("```"):
                        response_text = response_text[:-3].strip()
                        
                    summary_json = json.loads(response_text)
                    
                    # Handle LLM explicitly requesting a retry or returning failure modes
                    if summary_json.get("status") == "retry_later":
                        logger.error(f"M6: LLM Summarizer returned retry_later: {summary_json}")
                        verdict = "ESCALATE" # Treat provider issues as terminal
                        summary_json = {
                            "status": "FAIL",
                            "issues": [{"error": "LLM Provider Rate Limited during evaluation"}],
                            "metrics": {}
                        }
                    
                    rejection_feedback = summary_json

                except Exception as llm_e:
                    error_str = str(llm_e).lower()
                    if "429" in error_str or "rate limit" in error_str or "quota" in error_str:
                        logger.error(f"M6: TERMINAL 429 Rate Limit Error from LLM: {llm_e}")
                        verdict = "ESCALATE"
                    else:
                        logger.error(f"M6: LLM Summarization failed: {llm_e}")
                        verdict = "RETRY"
                    
                    # Deterministic fallback format
                    rejection_feedback = {
                        "status": "FAIL",
                        "issues": [{
                            "id": "ERR_M6_LLM_FAIL",
                            "severity": "high",
                            "location": "m6_test_executor",
                            "reason": f"Summarizer failed: {type(llm_e).__name__}",
                            "evidence": "LLM parsing error",
                            "recommendation": "Review raw pytest output manually"
                        }],
                        "metrics": {
                            "tests_executed": 0,
                            "tests_passed": 0,
                            "tests_failed": 1
                        }
                    }
                
            execution_result = {
                "status": verdict,
                "stdout": stdout,  # Not sent back to LLM in M5, just stored in state for record
                "stderr": stderr,
                "layer": active_layer,
                "attempt": state.get("attempt", 1)
            }
            
            return {
                **state,
                "verdict": verdict,
                "rejection_feedback": rejection_feedback,
                "execution_result": execution_result
            }
            
        except subprocess.TimeoutExpired as e:
            logger.error(f"M6: Test execution timed out: {e}")
            return {
                **state,
                "verdict": "RETRY",
                "rejection_feedback": {
                    "status": "FAIL",
                    "issues": [{
                        "id": "ERR_TIMEOUT",
                        "severity": "critical",
                        "location": "pytest_execution",
                        "reason": "Test suite timed out (>30s)",
                        "evidence": str(e),
                        "recommendation": "Check for infinite loops or unmocked blocking calls"
                    }],
                    "metrics": {}
                },
                "execution_result": {"status": "TIMEOUT", "attempt": state.get("attempt", 1)}
            }
        except Exception as e:
            logger.error(f"M6: Test execution failed unexpectedly: {e}")
            return {
                **state,
                "verdict": "ESCALATE",
                "rejection_feedback": {
                    "status": "FAIL",
                    "issues": [{
                        "id": "ERR_SYSTEM",
                        "severity": "critical",
                        "location": "m6_test_executor",
                        "reason": "Unexpected system exception",
                        "evidence": str(e),
                        "recommendation": "Check M6 environment and sandbox permissions"
                    }],
                    "metrics": {}
                },
                "execution_result": {"status": "ERROR", "error": str(e), "attempt": state.get("attempt", 1)}
            }


def _extract_pytest_failure(stdout: str, stderr: str) -> str:
    """Extracts the relevant failure traceback from pytest output."""
    output = stdout + "\n" + stderr
    # Pytest usually puts failures after '=================================== FAILURES ==================================='
    if "FAILURES" in output and "===" in output:
        parts = output.split("FAILURES", 1)
        if len(parts) > 1:
            failure_section = parts[1].split("short test summary info", 1)[0]
            return failure_section.strip()
    
    # Fallback if standard format isn't found
    return output[-MAX_TRACEBACK_CHARS:]


def get_routing_verdict(state: ATCGState) -> str:
    """Routes based on execution verdict and retry limits."""
    verdict = state.get("verdict", "ESCALATE")
    attempt = state.get("attempt", 1)
    max_retries = state.get("max_retries", 3)
    
    if verdict == "PASS":
        return "task_dispatcher"
    elif verdict == "RETRY":
        if attempt < max_retries:
            return "retry_handler"
        else:
            logger.warning(f"M6: Max retries ({max_retries}) exhausted. Skipping to next task.")
            return "task_dispatcher"  # Move on instead of halting pipeline
    else:
        return "hitl_interrupt"
