"""Actions that choose the CT series: a local folder, or a download from IDC."""

from __future__ import annotations

from pathlib import Path

from ...imaging.dicom import find_series
from .. import prompts
from ..prompts import Option, console
from ..session import Session


def select_local(s: Session) -> None:
    """Pick a series found under tests/data, data or the current folder, or type a path."""
    with console.status("Looking for DICOM series..."):
        found = find_series([Path("tests/data"), Path("data"), Path.cwd()])
    options = [Option(f"{_short(info.folder)}  {info.summary()}", info, info.uid) for info in found]
    options += [Option("Enter a path...", "path"), Option("Back", None)]
    if not found:
        console.print("[dim]No DICOM series found under tests/data, data or the current folder.[/]")
    choice = prompts.select("DICOM series", options)
    if choice == "path":
        s.select(
            Path(
                prompts.text(
                    "Path to a DICOM folder",
                    validate=lambda t: None if Path(t).expanduser().exists() else "No such path",
                )
            ).expanduser()
        )
    elif choice is not None:
        s.select(choice.folder, choice.uid)


def download(s: Session) -> None:
    """Search IDC by body part, collection and size, download a series and select it."""
    from ...imaging import idc

    try:
        with console.status("Loading the IDC index (first time can take a minute)..."):
            idc.client()
    except ImportError as err:
        console.print(f'[red]{err}[/]\nInstall with: [bold]pip install -e ".[download]"')
        return
    body = prompts.select(
        "Body part",
        [Option(b, b) for b in ("CHEST", "ABDOMEN", "CHESTABDPELVIS", "HEAD", "HEADNECK", "PELVIS")]
        + [Option("any", None)],
    )
    collection = prompts.text("Collection (blank = any, e.g. nlst)")
    max_mb = prompts.number("Max series size (MB)", 60.0)
    with console.status("Searching..."):
        rows = idc.find_ct_series(collection or None, body, max_size_mb=max_mb, limit=15)
    if rows.empty:
        console.print("[yellow]No matching series.")
        return
    options = [
        Option(
            f"{r.collection_id:<10} {r.instanceCount:>4} slices {r.series_size_MB:6.1f} MB  {str(r.SeriesDescription)[:40]}",
            r.SeriesInstanceUID,
            help=f"{r.BodyPartExamined} | {r.license_short_name} | {r.SeriesInstanceUID}",
        )
        for r in rows.itertuples()
    ] + [Option("Cancel", None)]
    uid = prompts.select("Download which series? (smallest first)", options)
    if uid is None:
        return
    dest = Path(prompts.text("Download folder", "tests/data"))
    path = idc.download_series(uid, dest)
    s.select(path)
    console.print(f"[green]Downloaded to {path}")


def _short(path: Path) -> str:
    """``path`` relative to the current folder if it is inside it."""
    try:
        return str(path.relative_to(Path.cwd()))
    except ValueError:
        return str(path)
