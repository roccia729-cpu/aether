import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console

from . import __version__, config
from .baseline import builder, store
from .detect.engine import detect
from .ingest import collect
from .ingest.journald import JournalError
from .report import terminal

app = typer.Typer(
    help="Aether: behavioral log analysis for Linux.",
    no_args_is_help=True,
    add_completion=False,
)
baseline_app = typer.Typer(help="Manage the behavioral baseline.", no_args_is_help=True)
app.add_typer(baseline_app, name="baseline")
console = Console()

SourceOpt = typer.Option("auto", "--source", "-s", help="auto | journald | files")
FilesOpt = typer.Option(None, "--file", "-f", help="Log file (repeatable, files source)")


def _version(value: bool):
    if value:
        console.print(f"Aether v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True,
                                 help="Show version."),
):
    """Aether: detects when a machine starts behaving differently."""


def _collect(since, until, source, files):
    try:
        with console.status("Reading logs..."):
            return collect(since, until, source, files)
    except (JournalError, ValueError) as exc:
        console.print(f"[red]Error:[/] {exc}")
        raise typer.Exit(1)


@app.command()
def scan(
    hours: int = typer.Option(config.DEFAULT_SCAN_HOURS, "--hours", "-h", help="Recent window to analyze."),
    source: str = SourceOpt,
    files: Optional[List[Path]] = FilesOpt,
):
    """Analyze recent logs against the baseline and print a report."""
    base = store.load()
    if base is None:
        console.print("[red]No baseline found.[/] Run: [bold]aether baseline build[/]")
        raise typer.Exit(1)
    start = time.perf_counter()
    until = datetime.now().astimezone()
    since = until - timedelta(hours=hours)
    events = _collect(since, until, source, files)
    if not events:
        console.print("[yellow]No events found in the window (permissions? try sudo).[/]")
        raise typer.Exit(1)
    anomalies = detect(base, events, since, until)
    terminal.render_scan(anomalies, len(events), time.perf_counter() - start, since, until)


@baseline_app.command("build")
def baseline_build(
    hours: int = typer.Option(config.DEFAULT_PERIOD_HOURS, "--hours", "-h", help="Baseline period."),
    source: str = SourceOpt,
    files: Optional[List[Path]] = FilesOpt,
):
    """Build (or rebuild) the baseline from recent logs."""
    until = datetime.now().astimezone()
    since = until - timedelta(hours=hours)
    events = _collect(since, until, source, files)
    if not events:
        console.print("[yellow]No events found: cannot build baseline (permissions? try sudo).[/]")
        raise typer.Exit(1)
    base = builder.build_baseline(events, since, until, hours)
    path = store.save(base)
    console.print("[green]Baseline saved.[/]")
    terminal.render_baseline(base, path)


@baseline_app.command("show")
def baseline_show():
    """Show info about the current baseline."""
    base = store.load()
    if base is None:
        console.print("[red]No baseline found.[/] Run: [bold]aether baseline build[/]")
        raise typer.Exit(1)
    terminal.render_baseline(base, config.db_path())


if __name__ == "__main__":
    app()
