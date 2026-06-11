"""
Base Layer Agent — Abstract class implementing the 6-step execution chain.

All M5 layer agents (UNIT, INTEGRATION, FUNCTIONAL, PERFORMANCE, OWASP)
inherit from this base and override layer-specific configuration.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from atcg.config import ATCGConfig
from atcg.state import ATCGState, TestLayer

logger = logging.getLogger(__name__)


class BaseLayerAgent(ABC):
    """
    Abstract base for all M5 layer agents.

    Implements the 6-step execution chain from the spec:
      Step 0 — Layer identification + Neon history check
      Step 1 — Understand the target (layer-aware)
      Step 2 — Plan the test suite (layer-governed)
      Step 3 — Generate mocks & fixtures (registry-aware)
      Step 4 — Write each test case
      Step 5 — Self-critique
      Step 6 — Emit structured output
    """

    def __init__(self, config: ATCGConfig) -> None:
        self._config = config
        self._llm = ChatGoogleGenerativeAI(
            model=config.llm.model,
            google_api_key=config.llm.api_key,
            temperature=config.llm.temperature,
            max_output_tokens=config.llm.max_output_tokens,
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

    async def execute(self, state: ATCGState) -> ATCGState:
        """
        Execute the full 6-step chain for this layer.

        This is the main entry point called by the LangGraph node.
        """
        target_id = state.get("target_id", "unknown")
        layer_name = self.layer.value

        logger.info(f"M5-{layer_name}: Starting for target={target_id}")

        # Step 0: Layer identification + history check
        history_context = self._step0_check_history(state)

        # Step 1–5: LLM-powered test generation
        test_output = await self._generate_tests(state, history_context)

        # Step 6: Emit structured output
        return self._step6_emit_output(state, test_output)

    def _step0_check_history(self, state: ATCGState) -> dict[str, Any]:
        """
        Step 0: Layer identification + Neon history check.

        Scans neon_fixtures for reusable fixtures and neon_history for prior runs.
        """
        layer_name = self.layer.value
        neon_history = state.get("neon_history", [])
        neon_fixtures = state.get("neon_fixtures", [])
        attempt = state.get("attempt", 1)
        rejection_feedback = state.get("rejection_feedback")

        # Filter history to this layer
        prior_runs = [r for r in neon_history if r.get("layer") == layer_name]

        # Find most recent PASS run
        latest_pass = next(
            (r for r in prior_runs if r.get("verdict") == "PASS"),
            None,
        )

        # Collect known failure modes from RETRY runs
        known_failures = [
            r.get("quality_flags", [])
            for r in prior_runs
            if r.get("verdict") == "RETRY"
        ]

        # Available fixtures
        available_fixtures = [
            {
                "fixture_key": f.get("fixture_key"),
                "fixture_code": f.get("fixture_code"),
                "tags": f.get("tags", []),
            }
            for f in neon_fixtures
        ]

        context = {
            "prior_pass": latest_pass,
            "known_failures": known_failures,
            "available_fixtures": available_fixtures,
            "attempt": attempt,
            "rejection_feedback": rejection_feedback,
        }

        if latest_pass:
            logger.info("  Step 0: Found prior PASS run to use as baseline")
        if known_failures:
            logger.info(f"  Step 0: {len(known_failures)} known failure patterns to avoid")
        if available_fixtures:
            logger.info(f"  Step 0: {len(available_fixtures)} fixtures available from registry")

        return context

    async def _generate_tests(
        self, state: ATCGState, history_context: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Steps 1–5: Use LLM to generate tests.

        Constructs a detailed prompt with function context, history,
        and layer-specific instructions, then invokes the LLM.
        """
        target_context = state.get("target_context", {})
        project_context = state.get("project_context", {})
        target_id = state.get("target_id", "unknown")

        # Build the generation prompt
        user_prompt = self._build_generation_prompt(
            target_context=target_context,
            project_context=project_context,
            history_context=history_context,
            target_id=target_id,
        )

        # Invoke LLM
        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = await self._llm.ainvoke(messages)
            raw_output = response.content

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
        target_id: str,
    ) -> str:
        """Build the user prompt for test generation."""
        language = project_context.get("language", "python")
        framework = project_context.get("test_framework", "pytest")

        # Get source code
        source_code = target_context.get("source_code", "")
        if not source_code and isinstance(target_context, dict):
            # Try extracting from functions list
            functions = target_context.get("functions", [])
            for fn in functions:
                if fn.get("id") == target_id:
                    source_code = fn.get("source_code", "")
                    break

        prompt_parts = [
            "## Target Function",
            f"**ID:** {target_id}",
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
            prompt_parts.extend([
                "## Prior PASS Run (baseline)",
                "A previous test run passed for this target. Use it as a foundation if source is unchanged.",
                "",
            ])

        if history_context.get("known_failures"):
            prompt_parts.extend([
                "## Known Failure Patterns (AVOID THESE)",
                json.dumps(history_context["known_failures"], indent=2),
                "",
            ])

        if history_context.get("available_fixtures"):
            prompt_parts.extend([
                "## Available Fixtures from Registry (REUSE, DO NOT REGENERATE)",
                json.dumps(history_context["available_fixtures"], indent=2),
                "",
            ])

        if history_context.get("rejection_feedback"):
            prompt_parts.extend([
                "## REJECTION FEEDBACK (this is a retry — fix these issues)",
                json.dumps(history_context["rejection_feedback"], indent=2),
                "",
            ])

        # Layer-specific additions
        prompt_parts.extend(self._get_layer_specific_prompt_additions(target_context))

        prompt_parts.extend([
            "",
            "## Required Output Format",
            "Return a JSON object with EXACTLY these fields:",
            "```json",
            "{",
            '  "file_path": "tests/<layer>/<module>.<fn>.<layer>.test.<ext>",',
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
            '  },',
            '  "mocks_required": [',
            '    {"module": "<path>", "mock_type": "<type>", "from_registry": true|false}',
            '  ],',
            '  "test_code": "<complete, valid, executable test file>",',
            '  "quality_flags": ["<flag>", ...]',
            "}",
            "```",
            "",
            "CRITICAL: The test_code must be a COMPLETE, VALID, EXECUTABLE test file.",
            "Include all imports, all setup/teardown, and all test cases.",
            "Use AAA (Arrange-Act-Assert) structure for every test.",
        ])

        return "\n".join(prompt_parts)

    def _get_layer_specific_prompt_additions(
        self, target_context: dict[str, Any]
    ) -> list[str]:
        """Override in subclasses to add layer-specific prompt sections."""
        return []

    def _parse_llm_output(self, raw_output: str, state: ATCGState) -> dict[str, Any]:
        """Parse the LLM's JSON output, with fallback handling."""
        # Try to extract JSON from the response
        json_str = raw_output
        if "```json" in raw_output:
            start = raw_output.index("```json") + 7
            end = raw_output.index("```", start)
            json_str = raw_output[start:end].strip()
        elif "```" in raw_output:
            start = raw_output.index("```") + 3
            end = raw_output.index("```", start)
            json_str = raw_output[start:end].strip()

        try:
            parsed = json.loads(json_str)
            parsed["target_id"] = state.get("target_id", "unknown")
            parsed["active_layer"] = self.layer.value
            return parsed
        except json.JSONDecodeError:
            # Fallback: extract test code from response and build minimal output
            logger.warning(
                f"M5-{self.layer.value}: Failed to parse JSON output, "
                f"extracting test code directly"
            )
            return self._create_fallback_output(raw_output, state)

    def _create_fallback_output(
        self, raw_output: str, state: ATCGState
    ) -> dict[str, Any]:
        """Create output when JSON parsing fails — extracts test code directly."""
        # Try to find code block in the output
        test_code = raw_output
        if "```python" in raw_output:
            start = raw_output.index("```python") + 9
            end = raw_output.rindex("```")
            test_code = raw_output[start:end].strip()
        elif "```typescript" in raw_output:
            start = raw_output.index("```typescript") + 13
            end = raw_output.rindex("```")
            test_code = raw_output[start:end].strip()
        elif "```javascript" in raw_output:
            start = raw_output.index("```javascript") + 13
            end = raw_output.rindex("```")
            test_code = raw_output[start:end].strip()

        target_id = state.get("target_id", "unknown")
        language = state.get("project_context", {}).get("language", "python")
        ext = {"python": "py", "typescript": "ts", "javascript": "js"}.get(language, "py")

        module_name = target_id.rsplit(".", 1)[0] if "." in target_id else target_id
        func_name = target_id.rsplit(".", 1)[-1] if "." in target_id else target_id

        return {
            "target_id": target_id,
            "active_layer": self.layer.value,
            "file_path": f"tests/{self.file_suffix}/{module_name}.{func_name}.{self.file_suffix}.test.{ext}",
            "framework": state.get("project_context", {}).get("test_framework", "pytest"),
            "confidence": 0.6,
            "reasoning": f"Generated {self.layer.value} tests (JSON parsing fallback used)",
            "history_used": "none",
            "fixtures_reused": [],
            "fixtures_registered": [],
            "coverage_intent": {
                "layer_target": self.coverage_target,
                "branches_covered": [],
                "known_gaps": ["JSON output parsing failed — manual review recommended"],
            },
            "mocks_required": [],
            "test_code": test_code,
            "quality_flags": ["OUTPUT_PARSE_FALLBACK — JSON parsing failed"],
        }

    def _create_error_output(self, state: ATCGState, error: str) -> dict[str, Any]:
        """Create output for error cases."""
        target_id = state.get("target_id", "unknown")
        return {
            "target_id": target_id,
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

    def _step6_emit_output(self, state: ATCGState, test_output: dict[str, Any]) -> ATCGState:
        """Step 6: Format and emit structured output into state."""
        target_id = state.get("target_id", "unknown")
        layer_name = self.layer.value

        # Build neon_write payload
        neon_write: dict[str, Any] = {
            "table": f"atcg_{layer_name.lower()}_runs",
            "payload": {
                "run_id": state.get("run_id"),
                "target_id": target_id,
                "attempt": state.get("attempt", 1),
                "test_code": test_output.get("test_code", ""),
                "file_path": test_output.get("file_path", ""),
                "framework": test_output.get("framework", ""),
                "confidence": test_output.get("confidence", 0.0),
                "quality_flags": test_output.get("quality_flags", []),
                "fixtures_reused": test_output.get("fixtures_reused", []),
                "fixtures_registered": test_output.get("fixtures_registered", []),
                "reasoning": test_output.get("reasoning", ""),
                "verdict": "PASS",  # Default; M6 may override
            },
        }

        # Add new fixtures to secondary write
        new_fixtures = test_output.get("fixtures_registered", [])
        if new_fixtures:
            neon_write["secondary"] = {
                "table": "atcg_shared_fixtures",
                "fixtures": new_fixtures,
            }

        logger.info(
            f"M5-{layer_name}: Complete for target={target_id} "
            f"(confidence={test_output.get('confidence', 0):.2f})"
        )

        return {
            "layer_outputs": {layer_name: test_output},
            "neon_writes_queue": [neon_write],
        }
