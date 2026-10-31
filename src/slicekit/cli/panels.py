"""Rich panels: the status panel above the main menu and the result summary."""

from __future__ import annotations

from pathlib import Path

from rich.console import Group
from rich.panel import Panel
from rich.table import Table

from ..axes import PLANE_NAME
from ..geometry.shapes import polygons
from ..pipeline import Kit
from .session import Session


def status_panel(s: Session) -> Panel:
    """Panel shown above the main menu: series, layout, scale, infill and output folder."""
    p = s.params
    grid = Table.grid(padding=(0, 2))
    grid.add_column(style="bold cyan", no_wrap=True)
    grid.add_column()
    grid.add_row("Series", f"{s.dicom}\n[dim]{s.summary}[/]" if s.dicom else "[yellow]none selected[/]")
    if p.stack_axis:
        layout = f"stack of {PLANE_NAME[p.stack_axis]} slices, {p.thickness} mm, no gaps"
    else:
        layout = f"interlocking: {p.normals[0]} + {p.normals[1]} plates, {p.thickness} mm thick, gap {p.gap} mm"
    grid.add_row("Layout", layout)
    grid.add_row("Scale", f"{p.scale}  [dim](voxel {p.voxel_size} mm)[/]")
    if p.infill == "none":
        infill = "none (solid plates)"
    else:
        infill = f"{p.infill}, pitch {p.pitch} mm, wall {p.wall} mm, tone {p.tone}" + (
            ", perceptual" if p.perceptual else ""
        )
    grid.add_row("Infill", infill)
    grid.add_row("Output", str(s.out))
    if s.built:
        grid.add_row("Built", f"[green]{len(s.built.plates)} plates[/] (current parameters)")
    return Panel(
        grid, title="[bold]slicekit", subtitle="CT -> printable halftone slices", border_style="blue", expand=False
    )


def kit_summary(kit: Kit, files: list[Path] | None = None) -> Panel:
    """Result panel: plates per family, plates that split into pieces, and written files.

    Args:
        kit: The built kit.
        files: Output files to list as clickable links.

    Returns:
        The panel.
    """
    table = Table(box=None, padding=(0, 2))
    table.add_column("Family", style="cyan")
    table.add_column("Plates", justify="right")
    table.add_column("Split into pieces", style="yellow")
    for normal in dict.fromkeys(pl.normal for pl in kit.plates):
        group = [pl for pl in kit.plates if pl.normal == normal]
        split = [f"{pl.name} ({len(polygons(pl.outline))})" for pl in group if len(polygons(pl.outline)) > 1]
        table.add_row(f"{normal} ({PLANE_NAME[normal]})", str(len(group)), ", ".join(split) or "-")
    body = [table]
    if files:
        body.append(Table.grid())
        body[-1].add_column(overflow="fold")
        for f in files:
            body[-1].add_row(f"[link=file://{f.resolve()}]{f}[/link]")
    return Panel(Group(*body), title="Result", border_style="green", expand=False)
