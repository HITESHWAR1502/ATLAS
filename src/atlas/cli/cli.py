"""Command-line interface for ATLAS."""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
from enum import Enum
from pathlib import Path
from typing import Any

if platform.system() == "Windows":
    import io

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from atlas import __version__
from atlas.config import ATLASConfig

console = Console()


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@click.group()
@click.version_option(version=__version__, prog_name="atlas")
@click.option("--log-level", default="INFO", help="Log level: DEBUG, INFO, WARNING, ERROR.")
@click.pass_context
def main(ctx: click.Context, log_level: str) -> None:
    """ATLAS v3.0 - Automated Test Case Generator."""
    _setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level


@main.command()
@click.option("--env", type=click.Path(), help="Path to a .env file.")
@click.pass_context
def run(ctx: click.Context, env: str | None) -> None:
    """Run the ATLAS pipeline interactively."""
    console.print(
        Panel.fit(
            f"[bold cyan]ATLAS v{__version__}[/bold cyan]\n"
            "[dim]Automated Test Case Generator - 5-layer pipeline[/dim]",
            border_style="cyan",
        )
    )

    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice

        repo_path = inquirer.filepath(
            message="Enter the target file path or repository path:",
            default="./",
            validate=lambda result: len(result) > 0,
        ).execute()

        selected_layers = inquirer.checkbox(
            message="Select testing layers:",
            choices=[
                Choice("UNIT", name="Unit testing", enabled=True),
                Choice("INTEGRATION", name="Integration testing", enabled=True),
                Choice("FUNCTIONAL", name="Functional testing", enabled=True),
                Choice("PERFORMANCE", name="Performance testing", enabled=True),
                Choice("SECURITY", name="Security testing", enabled=True),
            ],
            validate=lambda result: len(result) >= 1,
            invalid_message="Please select at least one layer.",
            instruction="Use space to select and enter to confirm.",
            pointer=">",
        ).execute()

        config = ATLASConfig.from_env(env)
        for warning in config.validate():
            console.print(f"[yellow]Warning: {warning}[/yellow]")

        asyncio.run(_run_pipeline(config, repo_path, selected_layers))

    except ValueError as exc:
        console.print(f"[red]Configuration error: {exc}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted[/yellow]")
        sys.exit(130)
    except Exception as exc:
        console.print(f"[red]Pipeline failed: {exc}[/red]")
        logging.exception("Pipeline error")
        sys.exit(1)


async def _run_pipeline(config: ATLASConfig, repo_path: str, selected_layers: list[str]) -> None:
    """Build and execute the ATLAS graph."""
    from atlas.graph import build_graph, create_initial_state

    graph = build_graph(config).compile()
    target_path = str(Path(repo_path).resolve())
    initial_state = create_initial_state(target_path, selected_layers)

    _display_pipeline_info(target_path)
    console.print("\n[bold]Starting pipeline...[/bold]\n")

    try:
        final_state = await graph.ainvoke(initial_state)
        _display_results(final_state)
    except Exception as exc:
        console.print(f"[red]Pipeline execution error: {exc}[/red]")
        logging.exception("Pipeline execution error")


def _display_pipeline_info(repo_path: str) -> None:
    """Display the pipeline stages before execution."""
    tree = Tree("[bold]Pipeline stages[/bold]")
    tree.add("[dim]M0:[/dim] Git diff filter")
    tree.add("[dim]M1:[/dim] Project ingestion")
    tree.add("[dim]M2:[/dim] AST parser")
    tree.add("[dim]M4:[/dim] Test planner")

    loop = tree.add("[bold cyan]Sequential execution loop[/bold cyan]")
    loop.add("M5 Layer agent")
    loop.add("M6 Test executor")

    tree.add("[dim]M7:[/dim] Disk writer")
    tree.add("[dim]M8:[/dim] Coverage runner")
    console.print(tree)
    console.print(f"\n[dim]Repository: {repo_path}[/dim]")


def _display_results(state: dict[str, Any]) -> None:
    """Display pipeline results in a compact CLI report."""
    console.print("\n" + "=" * 60)
    console.print("[bold green]Pipeline complete[/bold green]\n")

    verdict = state.get("verdict", "N/A")
    verdict_color = {"PASS": "green", "RETRY": "yellow", "ESCALATE": "red"}.get(
        verdict,
        "white",
    )

    console.print(f"Target: {state.get('target_file', 'unknown')}")
    console.print(f"Selected layers: {', '.join(state.get('selected_layers', []))}")
    console.print(f"Final verdict: [{verdict_color}]{verdict}[/{verdict_color}]\n")

    _display_layer_outputs(state.get("layer_outputs", {}))
    _display_rejection_feedback(state)
    _display_security_findings(state.get("security_findings", []))

    coverage = state.get("coverage_results")
    if coverage:
        files = coverage.get("files_written", [])
        overall = coverage.get("overall", {})
        console.print(
            f"\nCoverage runner: {len(files)} file(s), "
            f"executed={overall.get('executed', False)}, "
            f"passed={overall.get('passed', 'N/A')}"
        )

    console.print("\n" + "=" * 60)


def _display_layer_outputs(layer_outputs: dict[str, dict[str, Any]]) -> None:
    if not layer_outputs:
        return

    table = Table(title="Test generation summary", show_lines=True)
    table.add_column("Layer", style="cyan")
    table.add_column("File written", style="blue")
    table.add_column("Confidence", justify="right")

    for output in layer_outputs.values():
        layer = output.get("active_layer", "Unknown")
        if isinstance(layer, Enum):
            layer = layer.value
        table.add_row(
            str(layer),
            output.get("file_path", "None"),
            f"{output.get('confidence', 0):.0%}",
        )

    console.print(table)


def _display_rejection_feedback(state: dict[str, Any]) -> None:
    rejection_feedback = state.get("rejection_feedback")
    if not rejection_feedback:
        return

    metrics = rejection_feedback.get("metrics", {})
    if metrics:
        console.print(
            "Test metrics: "
            f"{metrics.get('tests_executed', 0)} executed | "
            f"[green]{metrics.get('tests_passed', 0)} passed[/green] | "
            f"[red]{metrics.get('tests_failed', 0)} failed[/red]"
        )

    fail_table = Table(title="Execution failures", style="red", show_lines=True)
    fail_table.add_column("Layer", style="cyan")
    fail_table.add_column("Error message", style="red")

    layer = state.get("active_layer", "Unknown")
    for issue in rejection_feedback.get("issues", []):
        error_msg = issue.get("reason", issue.get("error", "Unknown error"))
        if len(error_msg) > 100:
            error_msg = error_msg[:97] + "..."
        fail_table.add_row(str(layer), error_msg)

    console.print("\n")
    console.print(fail_table)


def _display_security_findings(findings: list[dict[str, Any]]) -> None:
    if not findings:
        return

    table = Table(title="Security findings", style="red", show_lines=True)
    table.add_column("Category", style="cyan")
    table.add_column("Severity", justify="center")
    table.add_column("Verdict", justify="center")

    for finding in findings:
        severity = finding.get("severity", "HIGH")
        severity_color = "red" if severity in {"CRITICAL", "HIGH"} else "yellow"
        table.add_row(
            finding.get("owasp_category", "Unknown"),
            f"[{severity_color}]{severity}[/{severity_color}]",
            finding.get("verdict", "Unknown"),
        )

    console.print("\n")
    console.print(table)


if __name__ == "__main__":
    main()
