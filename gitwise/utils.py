"""
utils.py — Shared helpers, Rich formatting, and UI components.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box

console = Console()
err_console = Console(stderr=True)


# ---------------------------------------------------------------------------
# Panels
# ---------------------------------------------------------------------------

def panel(content: str, title: str = "", style: str = "bold cyan", border_style: str = "cyan") -> None:
    """Print a Rich panel."""
    console.print(Panel(content, title=title, border_style=border_style, style=style, expand=False))


def success_panel(content: str, title: str = "✅ Success") -> None:
    panel(content, title=title, style="bold green", border_style="green")


def warning_panel(content: str, title: str = "⚠️  Warning") -> None:
    panel(content, title=title, style="bold yellow", border_style="yellow")


def error_panel(content: str, title: str = "❌ Error") -> None:
    err_console.print(Panel(content, title=title, border_style="red", style="bold red", expand=False))


def info_panel(content: str, title: str = "ℹ️  Info") -> None:
    panel(content, title=title, style="bold blue", border_style="blue")


def ai_panel(content: str, title: str = "🤖 AI Response") -> None:
    panel(content, title=title, style="bold magenta", border_style="magenta")


def danger_panel(content: str, title: str = "🚨 Danger — Destructive Operation") -> None:
    panel(content, title=title, style="bold red on dark_red", border_style="bright_red")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

def ask(prompt: str, default: str = "") -> str:
    return Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]", default=default)


def confirm(prompt: str, default: bool = True) -> bool:
    return Confirm.ask(f"[bold yellow]{prompt}[/bold yellow]", default=default)


def pick_number(prompt: str, min_val: int, max_val: int) -> int:
    """Prompt user for a number in a range, looping until valid."""
    while True:
        raw = Prompt.ask(f"[bold cyan]{prompt}[/bold cyan]")
        try:
            val = int(raw)
            if min_val <= val <= max_val:
                return val
            console.print(f"[yellow]Please enter a number between {min_val} and {max_val}.[/yellow]")
        except ValueError:
            console.print("[yellow]Invalid input — enter a number.[/yellow]")


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------

def make_table(*headers: str, box_style: Any = box.ROUNDED) -> Table:
    """Create a styled Rich table with the given headers."""
    t = Table(box=box_style, show_header=True, header_style="bold cyan", border_style="dim")
    for h in headers:
        t.add_column(h, overflow="fold")
    return t


# ---------------------------------------------------------------------------
# Commit log table
# ---------------------------------------------------------------------------

def print_commit_table(commits: list[dict]) -> None:
    """Display a list of commits as a Rich table.
    Each item: {index, hash, date, author, message}
    """
    t = make_table("#", "Hash", "Date", "Author", "Message")
    for c in commits:
        t.add_row(
            str(c["index"]),
            f"[dim]{c['hash']}[/dim]",
            f"[dim]{c['date']}[/dim]",
            f"[green]{c['author']}[/green]",
            c["message"],
        )
    console.print(t)


# ---------------------------------------------------------------------------
# Command sequence table
# ---------------------------------------------------------------------------

def print_command_table(commands: list[str], title: str = "Git Commands to Execute") -> None:
    """Display a list of shell commands as a numbered Rich table."""
    t = make_table("#", "Command")
    t.title = f"[bold cyan]{title}[/bold cyan]"
    for i, cmd in enumerate(commands, 1):
        t.add_row(str(i), f"[bold yellow]{cmd}[/bold yellow]")
    console.print(t)


# ---------------------------------------------------------------------------
# Severity helpers (for review command)
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "critical": "bold red",
    "high": "red",
    "medium": "yellow",
    "low": "dim",
    "info": "cyan",
}


def severity_text(label: str) -> Text:
    color = SEVERITY_COLORS.get(label.lower(), "white")
    return Text(label.upper(), style=color)


# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------

def divider() -> None:
    console.rule(style="dim")


def print_key_value(key: str, value: str) -> None:
    console.print(f"  [bold cyan]{key}:[/bold cyan] {value}")
