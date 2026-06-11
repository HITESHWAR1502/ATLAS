"""
ATCG v3.0 CLI — Command-line interface for the Automated Test Case Generator.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import sys
from pathlib import Path

# ── Windows event loop and encoding fix ──────────────────────────────────────
# Psycopg async requires SelectorEventLoop, not ProactorEventLoop (Windows default)
# Windows consoles require UTF-8 mode for stdout/stderr to avoid UnicodeEncodeErrors
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

from atcg import __version__
from atcg.config import ATCGConfig
from atcg.db.connection import NeonConnection
from atcg.db.migrations import get_schema_status, initialize_schema

console = Console()

# ── Logging setup ────────────────────────────────────────────────────────────


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


# ── CLI Group ────────────────────────────────────────────────────────────────


@click.group()
@click.version_option(version=__version__, prog_name="atcg")
@click.option("--log-level", default="INFO", help="Log level (DEBUG, INFO, WARNING, ERROR)")
@click.pass_context
def main(ctx: click.Context, log_level: str) -> None:
    """
    🧪 ATCG v3.0 — Automated Test Case Generator

    Multi-agent LangGraph pipeline with 5-layer test generation,
    OWASP security overlay, and Neon PostgreSQL persistence.
    """
    _setup_logging(log_level)
    ctx.ensure_object(dict)
    ctx.obj["log_level"] = log_level


# ── RUN command ──────────────────────────────────────────────────────────────


@main.command()
@click.argument("repo_path", type=click.Path(exists=True), default=".")
@click.option("--diff", is_flag=True, help="Only process git-changed files")
@click.option("--target", help="Target specific function (module.function_name)")
@click.option("--env", type=click.Path(), help="Path to .env file")
@click.pass_context
def run(ctx: click.Context, repo_path: str, diff: bool, target: str | None, env: str | None) -> None:
    """Run the ATCG pipeline on a repository."""
    console.print(Panel.fit(
        f"[bold cyan]🧪 ATCG v{__version__}[/bold cyan]\n"
        f"[dim]Automated Test Case Generator — 5-Layer Pipeline[/dim]",
        border_style="cyan",
    ))

    try:
        config = ATCGConfig.from_env(env)
        warnings = config.validate()
        for w in warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

        asyncio.run(_run_pipeline(config, repo_path, diff, target))

    except ValueError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"[red]Pipeline failed: {e}[/red]")
        logging.exception("Pipeline error")
        sys.exit(1)


async def _run_pipeline(
    config: ATCGConfig, repo_path: str, diff: bool, target: str | None
) -> None:
    """Execute the ATCG pipeline."""
    from atcg.graph import build_graph, create_initial_state

    # Initialize database
    db = NeonConnection(config)
    await db.initialize()

    health = await db.health_check()
    if not health:
        console.print("[red]❌ Cannot connect to Neon database[/red]")
        return

    console.print("[green]✓ Neon database connected[/green]")

    # Build and compile graph
    graph = build_graph(config, db)
    compiled = graph.compile()

    # Create initial state
    initial_state = create_initial_state(str(Path(repo_path).resolve()))

    # Display pipeline info
    _display_pipeline_info(str(Path(repo_path).resolve()))

    # Run the pipeline
    console.print("\n[bold]Starting pipeline...[/bold]\n")

    try:
        final_state = await compiled.ainvoke(initial_state)
        _display_results(final_state)
    finally:
        await db.close()


def _display_pipeline_info(repo_path: str) -> None:
    """Display pipeline execution info."""
    tree = Tree("[bold]📋 Pipeline Stages[/bold]")
    tree.add("[dim]M0:[/dim] Git Diff Filter")
    tree.add("[dim]M1:[/dim] Ingestion + Fixture Registry")
    tree.add("[dim]M2:[/dim] AST Parser")
    tree.add("[dim]M3:[/dim] RAG Embedder")
    tree.add("[dim]M4:[/dim] Test Planner + Layer Router")
    fan = tree.add("[bold cyan]⚡ Parallel Fan-out[/bold cyan]")
    fan.add("M5-UNIT")
    fan.add("M5-INTEGRATION")
    fan.add("M5-FUNCTIONAL")
    fan.add("M5-PERFORMANCE")
    tree.add("[dim]JOIN:[/dim] Aggregate Results")
    tree.add("[bold red]M5-OWASP:[/bold red] Security Overlay")
    tree.add("[dim]M6:[/dim] Validator")
    tree.add("[dim]M7:[/dim] Neon Writer")
    tree.add("[dim]M8:[/dim] Coverage Runner")
    console.print(tree)
    console.print(f"\n[dim]Repository: {repo_path}[/dim]")


def _display_results(state: dict) -> None:
    """Display pipeline results."""
    console.print("\n" + "=" * 60)
    console.print("[bold green]✅ Pipeline Complete[/bold green]\n")

    # Test plan summary
    test_plan = state.get("test_plan", {})
    console.print(f"Functions analyzed: {test_plan.get('total_functions', 0)}")
    console.print(f"Layer dispatches:   {test_plan.get('total_layer_dispatches', 0)}")

    # Verdict
    verdict = state.get("verdict", "N/A")
    verdict_color = {
        "PASS": "green",
        "RETRY": "yellow",
        "ESCALATE": "red",
    }.get(verdict, "white")
    console.print(f"Verdict:            [{verdict_color}]{verdict}[/{verdict_color}]")

    # Layer outputs
    layer_outputs = state.get("layer_outputs", {})
    if layer_outputs:
        table = Table(title="Layer Results")
        table.add_column("Layer", style="cyan")
        table.add_column("Target", style="white")
        table.add_column("Confidence", justify="center")
        table.add_column("Tests", justify="center")

        for layer, output in layer_outputs.items():
            confidence = output.get("confidence", 0)
            conf_color = "green" if confidence >= 0.8 else "yellow" if confidence >= 0.5 else "red"
            test_code = output.get("test_code", "")
            test_count = test_code.count("def test_") or test_code.count("it(")

            table.add_row(
                layer,
                output.get("target_id", ""),
                f"[{conf_color}]{confidence:.0%}[/{conf_color}]",
                str(test_count),
            )

        console.print(table)

    # Security findings
    findings = state.get("security_findings", [])
    if findings:
        console.print(f"\n[bold red]🔴 Security Findings: {len(findings)}[/bold red]")
        for f in findings:
            console.print(
                f"  [{f.get('severity', 'HIGH')}] {f.get('owasp_category')} — "
                f"{f.get('function_name')}: {f.get('verdict')}"
            )

    # Coverage
    coverage = state.get("coverage_results", {})
    files_written = coverage.get("files_written", []) if coverage else []
    if files_written:
        console.print(f"\n[bold]📁 Test Files Written: {len(files_written)}[/bold]")
        for f in files_written:
            console.print(f"  [dim]{f}[/dim]")

    console.print("\n" + "=" * 60)


# ── INIT-DB command ──────────────────────────────────────────────────────────


@main.command("init-db")
@click.option("--dry-run", is_flag=True, help="Show SQL without executing")
@click.option("--env", type=click.Path(), help="Path to .env file")
def init_db(dry_run: bool, env: str | None) -> None:
    """Initialize the Neon database schema."""
    try:
        config = ATCGConfig.from_env(env)
        asyncio.run(_init_db(config, dry_run))
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


async def _init_db(config: ATCGConfig, dry_run: bool) -> None:
    db = NeonConnection(config)
    await db.initialize()

    try:
        tables = await initialize_schema(db, dry_run)
        if dry_run:
            console.print("[yellow]Dry run — no changes made[/yellow]")
        else:
            console.print(f"[green]✓ Schema initialized: {len(tables)} tables[/green]")
            for t in tables:
                console.print(f"  [dim]✓ {t}[/dim]")
    finally:
        await db.close()


# ── STATUS command ───────────────────────────────────────────────────────────


@main.command("status")
@click.option("--env", type=click.Path(), help="Path to .env file")
def status(env: str | None) -> None:
    """Check Neon database status and schema."""
    try:
        config = ATCGConfig.from_env(env)
        asyncio.run(_check_status(config))
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


async def _check_status(config: ATCGConfig) -> None:
    db = NeonConnection(config)
    await db.initialize()

    try:
        health = await db.health_check()
        console.print(f"Connection: {'[green]✓ Healthy[/green]' if health else '[red]✗ Failed[/red]'}")

        schema = await get_schema_status(db)
        table = Table(title="Schema Status")
        table.add_column("Table", style="cyan")
        table.add_column("Exists", justify="center")
        table.add_column("Rows", justify="right")

        for name, info in schema.items():
            exists = "✓" if info.get("exists") else "✗"
            exists_style = "green" if info.get("exists") else "red"
            rows = str(info.get("row_count", 0)) if info.get("exists") else "-"
            table.add_row(name, f"[{exists_style}]{exists}[/{exists_style}]", rows)

        console.print(table)
    finally:
        await db.close()


# ── FINDINGS command ─────────────────────────────────────────────────────────


@main.command("findings")
@click.option("--severity", type=click.Choice(["CRITICAL", "HIGH", "MEDIUM", "LOW"]))
@click.option("--resolved", is_flag=True, help="Include resolved findings")
@click.option("--env", type=click.Path(), help="Path to .env file")
def findings(severity: str | None, resolved: bool, env: str | None) -> None:
    """View OWASP security findings."""
    try:
        config = ATCGConfig.from_env(env)
        asyncio.run(_show_findings(config, severity, resolved))
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        sys.exit(1)


async def _show_findings(config: ATCGConfig, severity: str | None, resolved: bool) -> None:
    from atcg.db.history import get_security_findings

    db = NeonConnection(config)
    await db.initialize()

    try:
        findings_list = await get_security_findings(
            db,
            unresolved_only=not resolved,
            severity=severity,
        )

        if not findings_list:
            console.print("[green]No security findings found ✓[/green]")
            return

        table = Table(title=f"Security Findings ({len(findings_list)})")
        table.add_column("Category", style="cyan")
        table.add_column("Severity")
        table.add_column("Function")
        table.add_column("Verdict")
        table.add_column("Detected")

        for f in findings_list:
            sev = f.get("severity", "")
            sev_color = {"CRITICAL": "red", "HIGH": "red", "MEDIUM": "yellow", "LOW": "dim"}.get(sev, "white")
            table.add_row(
                f.get("owasp_category", ""),
                f"[{sev_color}]{sev}[/{sev_color}]",
                f.get("function_name", ""),
                f.get("verdict", ""),
                str(f.get("detected_at", ""))[:10],
            )

        console.print(table)
    finally:
        await db.close()


if __name__ == "__main__":
    main()
