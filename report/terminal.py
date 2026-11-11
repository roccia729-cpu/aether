from datetime import datetime

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from ..models import Anomaly, Baseline, Level

console = Console()
COLORS = {Level.CRITICAL: "bold red", Level.WARNING: "yellow", Level.INFO: "cyan"}


def _window(a: Anomaly) -> str:
    s, e = a.window_start.astimezone(), a.window_end.astimezone()
    if s.date() == e.date():
        return f"{s:%d %b %H:%M} → {e:%H:%M}"
    return f"{s:%d %b %H:%M} → {e:%d %b %H:%M}"


def render_scan(anomalies: list[Anomaly], scanned: int, elapsed: float,
                since: datetime, until: datetime) -> None:
    n = {lvl: sum(1 for a in anomalies if a.level == lvl) for lvl in Level}
    grid = Table.grid(padding=(0, 2))
    grid.add_row("Events scanned", f"{scanned:,}")
    grid.add_row("Window", f"{since.astimezone():%d %b %H:%M} → {until.astimezone():%d %b %H:%M}")
    grid.add_row("Elapsed", f"{elapsed:.2f}s")
    grid.add_row(
        "Anomalies",
        f"[bold red]{n[Level.CRITICAL]} critical[/] · "
        f"[yellow]{n[Level.WARNING]} warning[/] · [cyan]{n[Level.INFO]} info[/]",
    )
    console.print(Panel(grid, title="[bold]Aether scan[/]", border_style="blue"))

    if not anomalies:
        console.print("[green]No relevant deviations from baseline.[/]")
        return

    table = Table(show_lines=False)
    for col in ("#", "Level", "Type", "Window"):
        table.add_column(col)
    for i, a in enumerate(anomalies, 1):
        table.add_row(str(i), f"[{COLORS[a.level]}]{a.level.value.upper()}[/]", a.kind, _window(a))
    console.print(table)

    for i, a in enumerate(anomalies, 1):
        lines = [escape(a.description), ""]
        lines += [f"[dim]{k}:[/] {escape(str(v))}" for k, v in a.evidence.items()]
        console.print(Panel("\n".join(lines),
                            title=f"#{i} [{COLORS[a.level]}]{a.level.value.upper()}[/] · {a.kind}",
                            subtitle=_window(a), border_style=COLORS[a.level].split()[-1]))


def render_baseline(b: Baseline, path) -> None:
    grid = Table.grid(padding=(0, 2))
    grid.add_row("File", str(path))
    grid.add_row("Created", f"{b.created_at.astimezone():%Y-%m-%d %H:%M}")
    grid.add_row("Period", f"{b.period_hours}h")
    grid.add_row("Events", f"{b.total_events:,}")
    grid.add_row("Errors", f"{b.error_total:,}")
    grid.add_row("Unique templates", f"{len(b.templates):,}")
    grid.add_row("Avg events/hour", f"{b.avg_per_hour:.1f}")
    console.print(Panel(grid, title="[bold]Aether baseline[/]", border_style="blue"))
