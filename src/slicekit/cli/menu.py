"""Interactive menu (``slicekit`` without arguments): the loop around ``actions.ACTIONS``."""

from __future__ import annotations

from pathlib import Path

from rich.panel import Panel

from . import prompts
from .actions import ACTIONS, PREVIEW, SELECT_SERIES
from .panels import status_panel
from .prompts import Option, console
from .session import Session


def run(dicom: Path | None = None) -> None:
    """Show the status panel and main menu until the user quits.

    Left/Esc inside an action returns here; errors are shown as a panel instead of
    ending the menu. Ctrl-C or Ctrl-D at the main menu quits.

    Args:
        dicom: Series to start with; otherwise the user selects one from the menu.
    """
    session = Session()
    if dicom:
        session.select(dicom)
    while True:
        console.print()
        console.print(status_panel(session))
        options = [
            Option(
                a.label,
                a,
                a.help,
                disabled="select a series first" if a.needs_series and not session.dicom else None,
            )
            for a in ACTIONS
        ]
        try:
            action = prompts.select(
                "What next?", options, default=PREVIEW if session.dicom else SELECT_SERIES, back=False
            )
        except (KeyboardInterrupt, EOFError):  # Ctrl-C / Ctrl-D at the menu quits
            console.print()
            return
        if action.run is None:
            return
        console.rule(action.label)
        try:
            action.run(session)
        except prompts.Back:  # left/Esc anywhere in an action returns to this menu
            pass
        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Cancelled.[/] [dim]Ctrl-C again to quit.[/]")
        except Exception as err:  # keep the menu alive; show what went wrong
            console.print(Panel(f"{type(err).__name__}: {err}", title="Error", border_style="red", expand=False))
