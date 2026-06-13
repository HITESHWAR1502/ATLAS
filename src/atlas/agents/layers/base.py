"""
Base Layer Agent — Abstract class implementing the 6-step execution chain.

All M5 layer agents (UNIT, INTEGRATION, FUNCTIONAL, PERFORMANCE, OWASP)
inherit from this base and override layer-specific configuration.
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

from langgraph.prebuilt import create_react_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from atlas.config import ATLASConfig
from atlas.state import ATLASState, TestLayer
from atlas.models.llm_router import get_llm
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


@tool
def run_test(test_code: str, language: str = "python") -> str:
    """Executes the provided test code and returns the output (stdout/stderr). Use this to verify test code before returning it."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        test_file = temp_path / "test_interactive.py"
        test_file.write_text(test_code, encoding="utf-8")
        try:
            result = subprocess.run(
                ["pytest", str(test_file), "-v"], capture_output=True, text=True, timeout=15
            )
            return f"Exit code {result.returncode}:\n{result.stdout}\n{result.stderr}"
        except Exception as e:
            return f"Execution failed: {str(e)}"


@tool
def read_source_file(filepath: str) -> str:
    """Reads and returns the contents of a source file. Use this to inspect project files."""
    try:
        return Path(filepath).read_text(encoding="utf-8")
    except Exception as e:
        return f"Failed to read {filepath}: {str(e)}"


class BaseLayerAgent(ABC):
    """
    Abstract base for all M5 layer agents.

    Implements the 6-step execution chain from the spec:
      Step 0 — Layer identification + History check
      Step 1 — Understand the target (layer-aware)
      Step 2 — Plan the test suite (layer-governed)
      Step 3 — Generate mocks & fixtures (registry-aware)
      Step 4 — Write each test case
      Step 5 — Self-critique
      Step 6 — Emit structured output
    """

    def __init__(self, config: ATLASConfig) -> None:
        self._config = config
        self._llm = get_llm(config, tool_calling=True)
        # We deliberately remove run_test from tools.
        # M6 handles execution + feedback. Providing run_test to M5 causes Groq parsing errors (tool_use_failed)
        self._tools = [read_source_file]

        self._agent_executor = create_react_agent(
            self._llm, tools=self._tools, prompt=self.system_prompt
        )

    # ── Abstract properties (override per layer) ─────────────────────────────

    @property
    @abstractmethod
    def layer(self) -> TestLayer:
        """The test layer this agent handles."""
        ...

    @property
    @abstractmethod
    def min_tests(self) -> int:
        """Minimum number of test cases per function."""
        ...

    @property
    @abstractmethod
    def max_tests(self) -> int:
        """Maximum number of test cases per function."""
        ...

    @property
    @abstractmethod
    def coverage_target(self) -> str:
        """Coverage target description."""
        ...

    @property
    @abstractmethod
    def naming_convention(self) -> str:
        """Test naming convention for this layer."""
        ...

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """The system prompt for this layer's LLM calls."""
        ...

    @property
    def file_suffix(self) -> str:
        """Test file naming suffix for this layer."""
        suffixes = {
            TestLayer.UNIT: "unit",
            TestLayer.INTEGRATION: "integration",
            TestLayer.FUNCTIONAL: "functional",
            TestLayer.PERFORMANCE: "perf",
            TestLayer.SECURITY: "security",
        }
        return suffixes.get(self.layer, "test")

    # ── Execution chain ──────────────────────────────────────────────────────

    async def execute(self, state: ATLASState) -> ATLASState:
        """
        Execute the full 6-step chain for this layer.

        This is the main entry point called by the LangGraph node.
        """
        target_file = state.get("target_file", "unknown_file")
        layer_name = self.layer.value

        logger.info(f"M5-{layer_name}: Starting for file={target_file}")

        # Step 0: Layer identification and retry feedback.
        history_context = {"rejection_feedback": state.get("rejection_feedback")}

        # Step 1–5: LLM-powered test generation
        test_output = await self._generate_tests(state, history_context)

        # Step 6: Emit structured output
        return self._step6_emit_output(state, test_output)

    async def _generate_tests(
        self, state: ATLASState, history_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Steps 1–5: Use LLM to generate tests.

        Constructs a detailed prompt with function context, history,
        and layer-specific instructions, then invokes the LLM.
        """
        target_context = state.get("target_context", {})
        project_context = state.get("project_context", {})
        target_file = state.get("target_file", "unknown_file")

        # Build the generation prompt
        user_prompt = self._build_generation_prompt(
            target_context=target_context,
            project_context=project_context,
            history_context=history_context,
            target_file=target_file,
        )

        # Manage Conversational Memory
        state_messages = list(state.get("messages", []))

        if not state_messages:
            # First attempt: add system + user prompt
            state_messages.append(SystemMessage(content=self.system_prompt))
            state_messages.append(HumanMessage(content=user_prompt))
        elif state.get("attempt", 1) > 1 and history_context.get("rejection_feedback"):
            # Retry attempt: add feedback
            feedback = history_context.get("rejection_feedback")
            if feedback:
                issues = feedback.get("issues") or feedback.get("failures") or []
                if issues:
                    error_str = "\n".join(
                    issue.get("reason") or issue.get("error") or issue.get("evidence") or str(issue)
                    for issue in issues
                )
            else:
                error_str = json.dumps(feedback, indent=2)
            state_messages.append(
                HumanMessage(
                    content=(
                        "Execution failed for the previous test file.\n"
                        f"{error_str}\n\n"
                        "Return a corrected, complete test file using the same required output format."
                    )
                )
            )

        try:
            response = await self._agent_executor.ainvoke({"messages": state_messages})
            # create_react_agent returns the full updated state containing all messages
            final_message = response["messages"][-1]
            raw_output = final_message.content

            # Handle LangChain Google GenAI returning a list of dicts instead of string
            if isinstance(raw_output, list):
                text_parts = [
                    part["text"] for part in raw_output if isinstance(part, dict) and "text" in part
                ]
                raw_output = "\n".join(text_parts) if text_parts else str(raw_output)
            elif not isinstance(raw_output, str):
                raw_output = str(raw_output)

            # Save the full message history to state
            state["messages"] = response["messages"]

            # Parse the JSON output from LLM response
            test_output = self._parse_llm_output(raw_output, state)
            return test_output

        except Exception as e:
            logger.error(f"M5-{self.layer.value}: LLM generation failed: {e}")
            return self._create_error_output(state, str(e))

    def _build_generation_prompt(
        self,
        target_context: dict[str, Any],
        project_context: dict[str, Any],
        history_context: dict[str, Any],
        target_file: str,
    ) -> str:
        """Build the user prompt for test generation."""
        language = project_context.get("language", "python")
        framework = project_context.get("test_framework", "pytest")

        # Get source code
        source_code = target_context.get("source_code", "")

        prompt_parts = [
            "## Target File",
            f"**File:** {target_file}",
            f"**Language:** {language}",
            f"**Test Framework:** {framework}",
            f"**Layer:** {self.layer.value}",
            f"**Naming Convention:** {self.naming_convention}",
            f"**Coverage Target:** {self.coverage_target}",
            f"**Min Tests:** {self.min_tests}, **Max Tests:** {self.max_tests}",
            "",
            "## Source Code",
            f"```{language}",
            source_code,
            "```",
            "",
        ]

        # Add history context
        if history_context.get("prior_pass"):
            prompt_parts.extend(
                [
                    "## Prior PASS Run (baseline)",
                    "A previous test run passed for this target. Use it as a foundation if source is unchanged.",
                    "",
                ]
            )

        if history_context.get("known_failures"):
            prompt_parts.extend(
                [
                    "## Known Failure Patterns (AVOID THESE)",
                    json.dumps(history_context["known_failures"], indent=2),
                    "",
                ]
            )

        if history_context.get("available_fixtures"):
            prompt_parts.extend(
                [
                    "## Available Fixtures from Registry (REUSE, DO NOT REGENERATE)",
                    json.dumps(history_context["available_fixtures"], indent=2),
                    "",
                ]
            )

        if history_context.get("rejection_feedback"):
            prompt_parts.extend(
                [
                    "## REJECTION FEEDBACK (this is a retry — fix these issues)",
                    json.dumps(history_context["rejection_feedback"], indent=2),
                    "",
                ]
            )

        # Layer-specific additions
        prompt_parts.extend(self._get_layer_specific_prompt_additions(target_context))

        prompt_parts.extend(
            [
                "",
                "## Required Output Format",
                "Return a JSON object with EXACTLY these fields:",
                "```json",
                "{",
                '  "file_path": "tests/<layer>/test_<module>_<fn>_<layer>.<ext>",',
                '  "framework": "<framework>",',
                '  "confidence": <0.0-1.0>,',
                '  "reasoning": "<2-3 sentence layer-specific analysis>",',
                '  "history_used": "none|reused_pass|diff_from_prior|avoided_known_failures",',
                '  "fixtures_reused": ["<fixture_key>", ...],',
                '  "fixtures_registered": ["<new_fixture_key>", ...],',
                '  "coverage_intent": {',
                '    "layer_target": "<coverage goal>",',
                '    "branches_covered": ["<branch>", ...],',
                '    "known_gaps": ["<gap and reason>", ...]',
                "  },",
                '  "mocks_required": [',
                '    {"module": "<path>", "mock_type": "<type>", "from_registry": true|false}',
                "  ],",
                '  "quality_flags": ["<flag>", ...]',
                "}",
                "```",
                "",
                "## Test Code Generation",
                "AFTER the JSON block, provide the complete, valid, executable test file in a standard markdown code block (e.g. ```python).",
                "CRITICAL: Do NOT put the test_code inside the JSON object! It must be completely outside the JSON block.",
                "CRITICAL: Keep the test cases extremely concise and limit the total number of tests to avoid exceeding output token limits.",
                "Include all imports, all setup/teardown, and all test cases.",
                "Use AAA (Arrange-Act-Assert) structure for every test.",
            ]
        )

        return "\n".join(prompt_parts)

    def _get_layer_specific_prompt_additions(self, target_context: dict[str, Any]) -> list[str]:
        """Override in subclasses to add layer-specific prompt sections."""
        return []

    def _parse_llm_output(self, raw_output: str, state: ATLASState) -> dict[str, Any]:
        """Parse the LLM's JSON output, with fallback handling."""
        json_str = _extract_json_object(raw_output)
        try:
            from typing import cast
            parsed = cast("dict[str, Any]", json.loads(json_str))
            parsed["target_file"] = state.get("target_file", "unknown")
            parsed["active_layer"] = self.layer.value

            # Extract test code from markdown blocks outside the JSON
            if "test_code" not in parsed:
                parsed["test_code"] = _extract_last_code_block(raw_output)

            return parsed
        except json.JSONDecodeError:
            # Fallback: extract test code from response and build minimal output
            logger.info(
                f"M5-{self.layer.value}: Failed to parse JSON output, using generated code fallback"
            )
            return self._create_fallback_output(raw_output, state)

    def _create_fallback_output(self, raw_output: str, state: ATLASState) -> dict[str, Any]:
        """Create output when JSON parsing fails — extracts test code directly."""
        test_code = _extract_last_code_block(raw_output)
        if not test_code and '"test_code"' in raw_output:
            import re

            # Extract everything between "test_code": " and the next JSON key or end of JSON
            match = re.search(r'"test_code"\s*:\s*"(.*?)"\s*,\s*"\w+"\s*:', raw_output, re.DOTALL)
            if match:
                # Decode the partially escaped broken JSON string
                extracted = match.group(1)
                # Only unescape if it looks like it was escaped
                if "\\n" in extracted or '\\"' in extracted:
                    extracted = (
                        extracted.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")
                    )
                test_code = extracted.strip()
            else:
                # Prevent returning raw JSON as python code
                test_code = "# Failed to extract test code from malformed JSON fallback.\n"
        elif not test_code:
            # Prevent returning raw JSON as python code
            test_code = "# LLM generation failed to produce test_code block.\n"

        target_file = state.get("target_file", "unknown")
        language = state.get("project_context", {}).get("language", "python")
        ext = {"python": "py", "typescript": "ts", "javascript": "js"}.get(language, "py")

        # Use filename as module name
        import os

        module_name = (
            os.path.splitext(os.path.basename(target_file))[0]
            if target_file != "unknown"
            else "unknown"
        )

        return {
            "target_file": target_file,
            "active_layer": self.layer.value,
            "file_path": f"tests/{self.file_suffix}/test_{module_name}_fallback_{self.file_suffix}.{ext}",
            "framework": state.get("project_context", {}).get("test_framework", "pytest"),
            "confidence": 0.6,
            "reasoning": f"Generated {self.layer.value} tests (JSON parsing fallback used)",
            "history_used": "none",
            "fixtures_reused": [],
            "fixtures_registered": [],
            "coverage_intent": {
                "layer_target": self.coverage_target,
                "branches_covered": [],
                "known_gaps": ["JSON output parsing failed - manual review recommended"],
            },
            "mocks_required": [],
            "test_code": test_code,
            "quality_flags": ["OUTPUT_PARSE_FALLBACK - JSON parsing failed"],
        }

    def _create_error_output(self, state: ATLASState, error: str) -> dict[str, Any]:
        """Create output for error cases."""
        target_file = state.get("target_file", "unknown")
        return {
            "target_file": target_file,
            "active_layer": self.layer.value,
            "file_path": "",
            "framework": state.get("project_context", {}).get("test_framework", "pytest"),
            "confidence": 0.0,
            "reasoning": f"Generation failed: {error}",
            "history_used": "none",
            "fixtures_reused": [],
            "fixtures_registered": [],
            "coverage_intent": {
                "layer_target": self.coverage_target,
                "branches_covered": [],
                "known_gaps": [f"GENERATION_FAILED: {error}"],
            },
            "mocks_required": [],
            "test_code": "",
            "quality_flags": [f"GENERATION_ERROR: {error}"],
        }

    def _step6_emit_output(self, state: ATLASState, test_output: dict[str, Any]) -> ATLASState:
        """Step 6: Format and emit structured output into state."""
        target_file = state.get("target_file", "unknown")
        layer_name = self.layer.value

        # Build disk_write payload using the file_path generated by the agent or fallback
        test_file_path = test_output.get("file_path", target_file)

        disk_write: dict[str, Any] = {
            "file_path": test_file_path,
            "content": test_output.get("test_code", ""),
        }

        logger.info(
            f"M5-{layer_name}: Complete for file={target_file} "
            f"(confidence={test_output.get('confidence', 0):.2f})"
        )

        output_key = f"{target_file}_{layer_name}"
        return {
            "layer_outputs": {output_key: test_output},
            "disk_writes_queue": [disk_write],
        }


def _extract_last_code_block(raw_output: str) -> str:
    """Return the last non-JSON fenced code block from an LLM response."""
    blocks = re.findall(r"```([a-zA-Z0-9_+-]*)\s*\n(.*?)```", raw_output, flags=re.DOTALL)
    for language, code in reversed(blocks):
        if str(language).lower() != "json":
            return str(code).strip()
    return ""


def _extract_json_object(raw_output: str) -> str:
    """Extract the first JSON object from fenced or mixed LLM output."""
    fenced = re.search(r"```json\s*(.*?)```", raw_output, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()

    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", raw_output):
        candidate = raw_output[match.start() :]
        try:
            _, end = decoder.raw_decode(candidate)
            return candidate[:end].strip()
        except json.JSONDecodeError:
            continue

    return raw_output.strip()
