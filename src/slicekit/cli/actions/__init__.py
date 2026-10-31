"""Menu actions: each is a plain ``(session) -> None`` function; ``ACTIONS`` sets the menu order.

To add one, write the function in the module that fits (or a new one) and list it here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from ..session import Session
from .output import export, preview, show_3d
from .series import download, select_local
from .settings import choose_layout, choose_preset, edit_params


@dataclass(frozen=True)
class Action:
    """One main-menu entry.

    Attributes:
        label: Text in the menu (also the section title while it runs).
        run: Function doing the work; None quits the menu.
        help: Description shown while the entry is highlighted.
        needs_series: Greyed out until a series is selected.
    """

    label: str
    run: Callable[[Session], None] | None  # None quits the menu
    help: str = ""
    needs_series: bool = False


ACTIONS: tuple[Action, ...] = (
    Action("Select a local DICOM series", select_local, "pick a folder under tests/data, data or the current folder"),
    Action("Search & download from IDC", download, "public CT series from the NCI Imaging Data Commons"),
    Action("Layout", choose_layout, "interlocking plates or a gapless slice stack; thickness and scale"),
    Action("Infill preset", choose_preset, "photo, engraving, screen, dither, ..."),
    Action("Edit all parameters", edit_params, "every setting, with explanations"),
    Action("Preview", preview, "PNG of every plate in seconds, no CAD", needs_series=True),
    Action("Build & export STL/STEP", export, "about 3 s per plate", needs_series=True),
    Action("Show in ocp_vscode", show_3d, "3D view of the assembly", needs_series=True),
    Action("Quit", None),
)
SELECT_SERIES, PREVIEW = ACTIONS[0], ACTIONS[5]

__all__ = ["ACTIONS", "PREVIEW", "SELECT_SERIES", "Action"]
