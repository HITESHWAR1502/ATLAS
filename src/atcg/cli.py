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
from rich.markdown import Markdown

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
@click.option("--env", type=click.Path(), help="Path to .env file")
@click.pass_context
def run(ctx: click.Context, env: str | None) -> None:
    """Run the ATCG pipeline interactively."""
    console.print(Panel.fit(
        f"[bold cyan]🧪 ATCG v{__version__}[/bold cyan]\n"
        f"[dim]Automated Test Case Generator — 5-Layer Pipeline[/dim]",
        border_style="cyan",
    ))

    try:
        from InquirerPy import inquirer
        from InquirerPy.base.control import Choice
        
        repo_path = inquirer.filepath(
            message="Enter the target file path or repository path:",
            default="./",
            validate=lambda result: len(result) > 0,
        ).execute()
        
        selected_layers = inquirer.checkbox(
            message="Select the testing layers to conduct (+ to select/deselect, Enter to confirm):",
            choices=[
                Choice("UNIT", name="Unit Testing", enabled=True),
                Choice("INTEGRATION", name="Integration Testing", enabled=True),
                Choice("FUNCTIONAL", name="Functional Testing", enabled=True),
                Choice("PERFORMANCE", name="Performance Testing", enabled=True),
                Choice("SECURITY", name="Security Testing", enabled=True),
            ],
            validate=lambda result: len(result) >= 1,
            invalid_message="Please select at least one layer.",
            instruction="(Use <space> or <+> to select, <enter> to confirm)",
            pointer="+",
        ).execute()
        
        config = ATCGConfig.from_env(env)
        warnings = config.validate()
        for w in warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")

        asyncio.run(_run_pipeline(config, repo_path, selected_layers))

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
    config: ATCGConfig, repo_path: str, selected_layers: list[str]
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
    initial_state = create_initial_state(str(Path(repo_path).resolve()), selected_layers)

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
    tree.add("[dim]M4:[/dim] Test Planner + Task Dispatcher")
    
    seq = tree.add("[bold cyan]🔄 Sequential Execution Loop[/bold cyan]")
    seq.add("M5 Layer Agent")
    seq.add("M6 Test Executor (Feedback Loop)")
    
    tree.add("[dim]M7:[/dim] Neon Writer")
    tree.add("[dim]M8:[/dim] Coverage Runner")
    console.print(tree)
    console.print(f"\n[dim]Repository: {repo_path}[/dim]")


def _display_results(state: dict) -> None:
    """Display minimal pipeline results and generate a detailed markdown report."""
    console.print("\n" + "=" * 60)
    console.print("[bold green]✅ Pipeline Complete[/bold green]\n")

    # Generate Markdown Report
    report_path = Path("tests/atlas_test_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    _generate_markdown_report(state, report_path)

    # Minimal terminal output
    test_plan = state.get("test_plan", {})
    verdict = state.get("verdict", "N/A")
    verdict_color = {"PASS": "green", "RETRY": "yellow", "ESCALATE": "red"}.get(verdict, "white")
    
    console.print(f"Total Functions Analyzed: {test_plan.get('total_functions', 0)}")
    console.print(f"Selected Layers: {', '.join(state.get('selected_layers', []))}")
    console.print(f"Final Verdict: [{verdict_color}]{verdict}[/{verdict_color}]")
    
    findings = state.get("security_findings", [])
    if findings:
        console.print(f"[bold red]Security Vulnerabilities Found: {len(findings)}[/bold red]")
        
    console.print(f"\n[bold cyan]Detailed report generated at: {report_path.absolute()}[/bold cyan]")
    console.print("\n" + "=" * 60)
    console.print("\n[bold]--- Final AI Output ---[/bold]\n")
    console.print(Markdown(report_path.read_text(encoding="utf-8")))

def _generate_markdown_report(state: dict, path: Path) -> None:
    """Generates a comprehensive markdown report."""
    md = [
        "# ATLAS Autonomous Test Generation Report",
        f"**Verdict:** {state.get('verdict', 'N/A')}",
        "",
        "## Summary",
    ]
    
    test_plan = state.get("test_plan", {})
    md.append(f"- **Functions Analyzed:** {test_plan.get('total_functions', 0)}")
    md.append(f"- **Selected Layers:** {', '.join(state.get('selected_layers', []))}")
    md.append("")
    
    layer_outputs = state.get("layer_outputs", {})
    if layer_outputs:
        md.append("## Layer Results")
        for output_key, output in layer_outputs.items():
            layer = output.get("active_layer", "Unknown")
            from enum import Enum
            if isinstance(layer, Enum):
                layer = layer.value
            elif not isinstance(layer, str):
                layer = str(layer)
            target_id = output.get("target_id", "Unknown")
            md.append(f"### {layer} - {target_id}")
            md.append(f"- **Confidence:** {output.get('confidence', 0):.0%}")
            
            # Print explicit errors if any
            rejection_feedback = state.get("rejection_feedback")
            if rejection_feedback and rejection_feedback.get("layer") == layer:
                md.append("\n#### 🚨 Execution Failures")
                md.append("The following errors were encountered during test execution:")
                for f in rejection_feedback.get("failures", []):
                    md.append(f"```text\n{f.get('error')}\n```")
                if rejection_feedback.get("raw_output"):
                    md.append("<details><summary>Raw Pytest Output</summary>\n")
                    md.append(f"```text\n{rejection_feedback.get('raw_output')}\n```\n</details>\n")
                    
            test_code = output.get("test_code", "")
            if test_code:
                md.append("\n#### Generated Test Code")
                md.append(f"```python\n{test_code}\n```\n")
    
    findings = state.get("security_findings", [])
    if findings:
        md.append("## Security Findings")
        for f in findings:
            md.append(f"### {f.get('owasp_category')} in `{f.get('function_name')}`")
            md.append(f"- **Severity:** {f.get('severity', 'HIGH')}")
            md.append(f"- **Verdict:** {f.get('verdict')}")
            md.append(f"- **Recommendation:** {f.get('recommendation', 'N/A')}")
            md.append("")
            
    coverage = state.get("coverage_results", {})
    files_written = coverage.get("files_written", []) if coverage else []
    if files_written:
        md.append("## Files Written")
        for f in files_written:
            md.append(f"- `{f}`")
            
    path.write_text("\n".join(md), encoding="utf-8")


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
