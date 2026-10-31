"""Command line ``slicekit-download``: search and download public CT series from IDC.

slicekit-download search --body-part CHEST --max-size 60
slicekit-download get <SeriesInstanceUID> -o tests/data
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Literal

from ..imaging import idc


class DownloadArgs(argparse.Namespace):
    """Typed result of ``parse_args``; the search or get fields are set depending on ``command``."""

    command: Literal["search", "get"]
    # search
    collection: str | None
    body_part: str | None
    min_slices: int
    max_slices: int | None
    max_size: float | None
    any_license: bool
    include_reformats: bool
    limit: int
    # get
    series_uid: list[str]
    out: Path
    dry_run: bool


def main(argv: list[str] | None = None) -> None:
    """Entry point of ``slicekit-download`` (``search`` and ``get`` subcommands).

    Args:
        argv: Command-line arguments without the program name; defaults to ``sys.argv[1:]``.
    """
    parser = argparse.ArgumentParser(prog="slicekit-download", description="Find and download CT series from IDC.")
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="list matching CT series, smallest first")
    search.add_argument("--collection", help="IDC collection id, e.g. nlst")
    search.add_argument("--body-part", help="BodyPartExamined, e.g. CHEST, ABDOMEN, HEAD")
    search.add_argument("--min-slices", type=int, default=80)
    search.add_argument("--max-slices", type=int)
    search.add_argument("--max-size", type=float, help="maximum series size in MB")
    search.add_argument("--any-license", action="store_true", help="include non-commercial and other licences")
    search.add_argument("--include-reformats", action="store_true", help="keep coronal/sagittal/MIP/scout series")
    search.add_argument("--limit", type=int, default=20)

    get = commands.add_parser("get", help="download series by SeriesInstanceUID")
    get.add_argument("series_uid", nargs="+")
    get.add_argument("-o", "--out", type=Path, default=Path("data"), help="download folder")
    get.add_argument("--dry-run", action="store_true", help="report the size without downloading")

    args = parser.parse_args(argv, namespace=DownloadArgs())
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    if args.command == "search":
        rows = idc.find_ct_series(
            args.collection,
            args.body_part,
            args.min_slices,
            args.max_slices,
            args.max_size,
            licenses=None if args.any_license else ("CC BY 4.0", "CC BY 3.0"),
            axial_only=not args.include_reformats,
            limit=args.limit,
        )
        print(rows.to_string() if len(rows) else "No matching series")
    else:
        for uid in args.series_uid:
            print(idc.download_series(uid, args.out, args.dry_run))


if __name__ == "__main__":
    main()
