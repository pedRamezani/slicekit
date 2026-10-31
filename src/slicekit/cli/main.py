"""Command line.

``slicekit`` without arguments opens the interactive menu; with a DICOM folder it
builds directly, e.g. ``slicekit DICOM_DIR -o out --thickness 3 --scale 0.5``.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from rich.logging import RichHandler
from rich.progress import track

from ..export.formats import EXPORT_FORMATS, ExportFormat
from ..imaging.dicom import load_series
from ..pipeline import build_kit, prepare_volume
from .options import add_param_arguments, params_from_args


class CliArgs(argparse.Namespace):
    """Typed result of ``parse_args`` for the options defined in ``_main``.

    The KitParams options are generated from the dataclass fields and read back with
    ``params_from_args``, where ``KitParams.__post_init__`` validates them.
    """

    dicom: Path
    out: Path
    series_uid: str | None
    formats: list[ExportFormat]
    show: bool
    preview: bool
    no_cad: bool


def build_parser() -> argparse.ArgumentParser:
    """Parser for the direct (non-menu) mode; parse into ``CliArgs`` for typed attributes."""
    parser = argparse.ArgumentParser(prog="slicekit", description=__doc__)
    parser.add_argument("dicom", type=Path, help="folder with the CT series (or a multi-frame file)")
    parser.add_argument("-o", "--out", type=Path, default=Path("kit_out"), help="output folder")
    parser.add_argument("--series-uid", help="SeriesInstanceUID if the folder holds several series")
    parser.add_argument("--formats", nargs="+", default=list(EXPORT_FORMATS), choices=EXPORT_FORMATS)
    parser.add_argument("--show", action="store_true", help="show the assembly in ocp_vscode")
    parser.add_argument("--preview", action="store_true", help="write a PNG contact sheet of all plates")
    parser.add_argument("--no-cad", action="store_true", help="skip STL/STEP export (use with --preview)")
    add_param_arguments(parser)
    return parser


def setup_logging() -> None:
    """Send log messages through rich, so they line up with the panels and progress bars."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", handlers=[RichHandler(show_path=False)])


def main(argv: list[str] | None = None) -> None:
    """Entry point of ``slicekit``: the interactive menu without arguments, else a direct build.

    Args:
        argv: Command-line arguments without the program name; defaults to ``sys.argv[1:]``.
    """
    try:
        _main(sys.argv[1:] if argv is None else argv)
    except KeyboardInterrupt:
        sys.exit(130)


def _main(argv: list[str]) -> None:
    if not argv or argv == ["menu"]:
        from .menu import run

        setup_logging()
        run()
        return

    args = build_parser().parse_args(argv, namespace=CliArgs())

    setup_logging()
    params = params_from_args(args)

    from .panels import kit_summary
    from .prompts import console

    with console.status("Loading and segmenting the series..."):
        volume, mask = prepare_volume(load_series(args.dicom, args.series_uid), params)
    kit = build_kit(volume, mask, params, progress=track)
    files: list[Path] = []
    if args.preview:
        files.append(kit.preview(args.out / "preview.png"))
    if not args.no_cad:
        kit.export(args.out, tuple(args.formats), progress=track)
        files += [args.out / f"assembly.{f}" for f in args.formats]
    console.print(kit_summary(kit, files))
    if args.show:
        from ocp_vscode import show

        show(kit.assembled())


if __name__ == "__main__":
    main()
