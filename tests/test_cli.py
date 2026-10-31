import dataclasses
import re
from pathlib import Path

from slicekit import KitParams
from slicekit.cli.download import DownloadArgs
from slicekit.cli.main import CliArgs, build_parser
from slicekit.cli.options import parameter_table, params_from_args


def test_parse_into_typed_namespace():
    args = build_parser().parse_args(
        ["scan", "-o", "out", "--formats", "stl", "--preview", "--hu-range", "-900", "400", "--stack", "coronal"],
        namespace=CliArgs(),
    )
    assert isinstance(args, CliArgs)
    assert args.dicom == Path("scan")
    assert args.out == Path("out")
    assert args.formats == ["stl"]
    assert args.preview is True
    assert args.no_cad is False


def test_params_from_args_converts_and_validates():
    args = build_parser().parse_args([
        "scan",
        "--hu-range",
        "-900",
        "400",
        "--normals",
        "z",
        "x",
        "--no-perceptual",
        "--infill",
        "lines",
    ])
    params = params_from_args(args)
    assert params.hu_range == (-900.0, 400.0)  # nargs lists become tuples
    assert params.normals == ("z", "x")
    assert params.perceptual is False
    assert params.infill == "lines"
    # Everything not given keeps the dataclass default.
    assert params.thickness == KitParams().thickness


def test_download_namespace():
    from slicekit.cli import download
    from slicekit.imaging import idc

    parser_args = ["get", "uid1", "uid2", "-o", "data", "--dry-run"]
    captured: list[DownloadArgs] = []

    def fake_download(uid: str, out: Path, dry_run: bool) -> Path:
        captured.append(DownloadArgs(series_uid=[uid], out=out, dry_run=dry_run))
        return out / uid

    original = idc.download_series
    idc.download_series = fake_download
    try:
        download.main(parser_args)
    finally:
        idc.download_series = original
    assert [c.series_uid for c in captured] == [["uid1"], ["uid2"]]
    assert all(c.out == Path("data") and c.dry_run for c in captured)


def test_parameter_table_matches_fields_and_cli():
    """The docs table has one well-formed row per field, and every flag it shows exists."""
    rows = parameter_table().splitlines()[2:]
    names = [f.name for f in dataclasses.fields(KitParams)]
    assert len(rows) == len(names)

    parser_flags = {flag for action in build_parser()._actions for flag in action.option_strings}
    for name, row in zip(names, rows, strict=True):
        cells = re.split(r"(?<!\\)\|", row.strip().strip("|"))  # split on unescaped pipes
        assert len(cells) == 5, row
        assert cells[0].strip() == f"`{name}`"
        for flag in re.findall(r"--[a-z-]+", cells[1]):
            assert flag in parser_flags, flag
