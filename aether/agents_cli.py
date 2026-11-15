"""CLI for experimental AI-agent log analysis."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from . import config
from .baseline import builder, store
from .detect.agent_rules import find_risky_actions
from .detect.engine import detect
from .ingest.claude_code import read_claude_code_file
from .report import terminal

console = Console()
agents_app = typer.Typer(help="Experimental analysis of AI agent (Claude Code) logs.")


@agents_app.command("scan")
def agents_scan(
    file: Path = typer.Argument(..., exists=True, readable=True, help="JSON-lines OTEL/agent log file"),
    hours: int = typer.Option(24, "--hours", "-h", help="Window to analyze"),
    build_baseline: bool = typer.Option(True, "--baseline/--no-baseline", help="Build baseline from older part of the file"),
):
    """Scan an agent log file for behavioral anomalies and risky actions."""
    if hours < 1:
        console.print("[red]Error:[/] --hours must be >= 1")
        raise typer.Exit(1)

    until = datetime.now().astimezone()
    since = until - timedelta(hours=hours)

    events = list(read_claude_code_file(file, since - timedelta(hours=hours), until))
    if not events:
        console.print("[yellow]No events parsed from file.[/]")
        raise typer.Exit(1)

    # Simple split: older half as baseline, recent window as scan
    events_sorted = sorted(events, key=lambda e: e.timestamp)
    mid = events_sorted[len(events_sorted) // 2].timestamp
    base_events = [e for e in events_sorted if e.timestamp < mid]
    recent = [e for e in events_sorted if e.timestamp >= max(mid, since)]

    if build_baseline and base_events:
        base = builder.build_baseline(
            base_events,
            base_events[0].timestamp,
            base_events[-1].timestamp,
            max(1, int((base_events[-1].timestamp - base_events[0].timestamp).total_seconds() // 3600) or 1),
        )
    else:
        base = store.load()
        if base is None:
            console.print("[red]No baseline and not enough data to build one.[/]")
            raise typer.Exit(1)

    anomalies = detect(base, recent, recent[0].timestamp if recent else since, until)
    anomalies += find_risky_actions(recent, since, until)
    anomalies.sort(key=lambda a: (-a.level.rank, a.window_start))

    terminal.render_scan(
        anomalies,
        len(recent),
        0.0,
        recent[0].timestamp if recent else since,
        until,
    )
