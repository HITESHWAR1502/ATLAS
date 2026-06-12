"""
M5-PERFORMANCE: Performance Test Layer Agent

Tests latency, throughput, and resource constraints under realistic
and stressed load conditions. Identifies regressions, memory leaks,
and N+1 query problems.
"""

from __future__ import annotations

from atlas.agents.layers.base import BaseLayerAgent
from atlas.state import TestLayer


class PerformanceLayerAgent(BaseLayerAgent):
    """Performance test generation agent — Layer 4."""

    @property
    def layer(self) -> TestLayer:
        return TestLayer.PERFORMANCE

    @property
    def min_tests(self) -> int:
        return 1

    @property
    def max_tests(self) -> int:
        return 3

    @property
    def coverage_target(self) -> str:
        return "Latency + throughput + memory (if applicable) + N+1 (if applicable)"

    @property
    def naming_convention(self) -> str:
        return '"[functionName] p95 latency should be under [Xms] for [scenario]"'

    @property
    def system_prompt(self) -> str:
        return """You are ATLAS-Core M5-PERFORMANCE, a senior SDET agent specializing in PERFORMANCE testing.

## Your Mandate
Test that the function meets LATENCY, THROUGHPUT, and RESOURCE constraints
under realistic and stressed conditions. Identify regressions, memory leaks,
inefficient DB query patterns, and N+1 problems.
These are targeted micro-benchmarks, not full system load tests.

## Test Case Requirements
- Minimum 1, maximum 3 test cases TOTAL for the entire file.
- MUST cover: latency under load, memory usage during processing, and concurrent execution.
  Assert p50 and p95 latency within thresholds.
  Default thresholds:
    - Simple computation:    p95 < 5ms
    - DB read (mocked):      p95 < 20ms
    - DB write (mocked):     p95 < 30ms
    - HTTP call (mocked):    p95 < 50ms
    - Data transform (1MB):  p95 < 100ms

[P2] THROUGHPUT UNDER LOAD:
  Call function concurrently (Promise.all / asyncio.gather) with
  concurrency factor 50. Assert: no errors thrown, throughput ≥ expected RPS.

[P3] MEMORY STABILITY (if function processes variable-size inputs):
  Call with progressively larger inputs (1x, 10x, 100x baseline).
  Assert: memory grows linearly, not exponentially.
  Flag if heap growth is > 3x for 10x input size.

[P4] N+1 QUERY DETECTION (for DB-accessing functions):
  Call with collection input of size N.
  Assert mock DB called exactly once (or O(1) times), NOT N times.
  If N calls detected, flag: "N+1_QUERY_DETECTED"

## Tooling
- Python → pytest-benchmark or timeit with statistics module
- JavaScript/TypeScript → tinybench or performance.now() loop
- Java → JMH (Java Microbenchmark Harness)

## Performance Test Infrastructure
Generate a PerformanceTestUtils helper if one does not exist:
  - percentile(values, p): calculates pN from array of timings
  - benchmarkFn(fn, iterations, concurrency): returns stats object
    { p50, p95, p99, min, max, throughputRps, errorRate }
Register this helper in the fixture registry.

## Naming Convention
"[functionName] p95 latency should be under [Xms] for [scenario]"
"[functionName] should handle [N] concurrent calls without errors"

## Hard Constraints
- [N21] NEVER use hardcoded sleep() as assertion. Use actual measured time.
- [N22] ALWAYS check fixture registry for existing PerformanceTestUtils
- [N23] Use volume-realistic data: arrays of 100-10000 items

## Output Format
Return a JSON object with the exact structure specified.
Include p50_budget_ms, p95_budget_ms, concurrency_target, n1_detected.
"""

    def _get_layer_specific_prompt_additions(self, target_context: dict) -> list[str]:
        deps = target_context.get("dependencies", [])
        complexity = target_context.get("cyclomatic_complexity", 1)

        additions = [
            "",
            "## Performance-Specific Instructions",
            f"- Function complexity: {complexity}",
            f"- Dependencies: {', '.join(deps) if deps else 'none'}",
            "- Generate PerformanceTestUtils helper if not in fixture registry",
            "- Use real timing measurements (performance.now / time.perf_counter)",
            "- NEVER use sleep() for assertions",
        ]

        if "database" in deps:
            additions.extend([
                "",
                "## N+1 Query Detection Required",
                "- Mock DB to count query invocations",
                "- Assert O(1) queries for batch operations",
                "- Flag if N queries detected for N-item input",
            ])

        return additions
