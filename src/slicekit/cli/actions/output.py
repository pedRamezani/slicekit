"""Actions that produce output: PNG preview, STL/STEP export and the 3D viewer."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from rich.progress import track

from .. import prompts
from ..panels import kit_summary
from ..prompts import Option, console
from ..session import Session


def open_file(path: Path) -> None:
    """Open a file we wrote with the system viewer (fixed command, no shell)."""
    if sys.platform == "darwin":
        subprocess.run(["open", str(path)], check=False)  # noqa: S603, S607
    elif sys.platform.startswith("win"):
        os.startfile(path)  # type: ignore[attr-defined]  # noqa: S606
    else:
        subprocess.run(["xdg-open", str(path)], check=False)  # noqa: S603, S607


def preview(s: Session) -> None:
    """Build the kit if needed, write ``<out>/preview.png`` and offer to open it."""
    kit = s.kit()
    with console.status("Rendering contact sheet..."):
        path = kit.preview(s.out / "preview.png")
    console.print(kit_summary(kit, [path]))
    if prompts.confirm("Open the preview?", default=True):
        open_file(path)


def export(s: Session) -> None:
    """Ask for formats and folder, then export every plate and the assembly."""
    formats = prompts.select(
        "Formats",
        [
            Option("STL", ("stl",), "meshes for the slicer"),
            Option("STEP", ("step",), "exact CAD, slower and larger"),
            Option("STL + STEP", ("stl", "step")),
        ],
    )
    s.out = Path(prompts.text("Output folder", str(s.out)))
    kit = s.kit()
    with console.status("Loading the CAD kernel (build123d)..."):
        import build123d  # noqa: F401  first import takes a few seconds
    kit.export(s.out, formats, progress=track)
    console.print(kit_summary(kit, [s.out / f"assembly.{f}" for f in formats] + [s.out / "plates"]))


def show_3d(s: Session) -> None:
    """Send the assembled kit to the ocp_vscode viewer (needs the ``viz`` extra)."""
    try:
        from ocp_vscode import show
    except ImportError:
        console.print('[red]ocp_vscode is not installed: pip install -e ".[viz]"')
        return
    kit = s.kit()
    with console.status("Loading build123d, building solids and sending to the viewer..."):
        show(kit.assembled())
