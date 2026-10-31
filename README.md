# slicekit

[![Release](https://img.shields.io/github/v/release/pedRamezani/slicekit)](https://img.shields.io/github/v/release/pedRamezani/slicekit)
[![Build status](https://img.shields.io/github/actions/workflow/status/pedRamezani/slicekit/main.yml?branch=main)](https://github.com/pedRamezani/slicekit/actions/workflows/main.yml?query=branch%3Amain)
[![Commit activity](https://img.shields.io/github/commit-activity/m/pedRamezani/slicekit)](https://img.shields.io/github/commit-activity/m/pedRamezani/slicekit)
[![License](https://img.shields.io/github/license/pedRamezani/slicekit)](https://img.shields.io/github/license/pedRamezani/slicekit)

Slice a CT DICOM series into 3D-printable plates, built with build123d: either an
interlocking kit card (egg-crate) or a gapless stack of sagittal, coronal or axial
slices. Each plate gets a halftone infill (hex holes or a line screen) whose density
follows the CT, so the anatomy (lungs, heart, liver, bone) is visible in the print.

- **GitHub repository**: <https://github.com/pedRamezani/slicekit/>
- **Documentation**: <https://pedRamezani.github.io/slicekit/>

## Usage

```bash
uv sync --all-extras     # or: pip install "slicekit[download,viz]"
uv run slicekit          # interactive menu
uv run slicekit path/to/dicom_folder -o out --scale 0.4 --thickness 3 --gap 9
uv run slicekit --help   # all parameters
```

`slicekit` with no arguments opens an interactive menu: up/down to move, Enter to
confirm, left arrow or Esc to go back, Ctrl-C to cancel or quit. It shows the current
series and settings, and covers IDC search and download, layout and infill presets, a
parameter editor, a fast PNG preview, and STL/STEP export. With piped input it falls
back to numbered prompts.

```python
from slicekit import KitParams, make_kit

kit = make_kit("path/to/dicom_folder", KitParams(scale=0.4, thickness=3.0))
kit.preview("out/preview.png")  # PNG of every plate, in seconds
kit.export("out")               # out/plates/Z03.stl ..., out/assembly.stl/.step
show(kit.assembled())           # ocp_vscode
```

All lengths are in **printed millimetres**, so they are applied after `scale`. Every
setting is listed with its flag, default and allowed values on the
[Parameters](https://pedRamezani.github.io/slicekit/parameters/) page of the docs
(generated from `KitParams`), and in `slicekit --help`.
Compressed DICOM (JPEG baseline/extended/lossless and JPEG 2000; not JPEG-LS) is
decoded through pylibjpeg.

**Interlocking** (default): two plate families (normals `z` and `y` by default) cross along the
third axis, and each crossing gets a pair of half-slots of width `thickness + tolerance`.
To assemble, stand the first family (e.g. `Z..` plates) in order at `thickness + gap`
pitch, then slide each plate of the second family along the crossing axis.

**Stack**: `--stack sagittal|coronal|axial` (or `x|y|z`) makes gapless slices at
`thickness` pitch with no slots. They don't hold together, but they stack seamlessly and
the assembly loads straight into a slicer for checking.

**Tuning**: `--preview --no-cad` writes `out/preview.png`, a contact sheet of all plates,
in a few seconds. The STL/STEP export takes ~3 s per plate.

```bash
uv run slicekit DICOM_DIR -o out --scale 0.4 --stack coronal --preview --no-cad
uv run slicekit DICOM_DIR -o out --scale 0.4 --infill lines --pitch 4 --preview --no-cad
```

## Pipeline

1. **Load** (`imaging.dicom`): find the DICOM images by content (with or without a `.dcm`
   suffix), stack the series sorted by slice position, convert to HU.
2. **Prepare** (`imaging.segment`): scale to printed size, resample to isotropic `voxel_size`,
   threshold at `body_hu` (-400 HU), keep the largest component (drops the table),
   fill internal air, crop and centre.
3. **Outline** (`geometry.sections`): section the mask at each plate position and contour it with shapely.
4. **Layout and slots** (`pipeline.layout`, `pipeline.slots`): place the plates. When
   interlocking, for every crossing pair, find where both plates have material along
   the crossing line, split at the midpoint of an overlap and cut A on one side and B
   on the other. B plates slide along the line axis into the
   stack of A plates. The split point and each B plate's sliding direction are
   chosen to minimise the extra slit, which matters for non-convex anatomy.
5. **Infill** (`infill.tone`, `infill.patterns`): what you see on a printed plate is how much of it is
   solid, so HU is mapped to a tone t in [0, 1] and t to a solid fraction. Tone is
   histogram-equalised over the body by default (`tone="equalize"`), or linear over
   `hu_range`; `gamma`, `invert` and `tone_blur` adjust it. `perceptual` (default on)
   picks the coverage so equal tone steps look equally lighter (CIE L*). Coverage stays
   in the printable range, from the thinnest `wall` to the narrowest printable hole
   (`min_hole`), so only tissue above `solid_tone` (the densest bone) prints solid.
   Modes (`infill=`):
   - `hex` (default): fixed hex grid of `pitch`, hole size follows t. A halftone screen
     that reads like a photo, with the widest printable tone range.
   - `lines`: engraving-style line screen, line width follows t (`line_angle`, and
     `line_wave` for wavy lines). Every line ends on the solid border, so the plate is
     always one piece. Use `pitch` >= 4 mm, or the fine `screen` preset (2 mm) with a
     0.4 mm nozzle.
   - `dither`: fixed hex grid, each cell open or solid by error diffusion. Finest detail at
     ~2 mm pitch, but "worm" patterns in mid tones.
   - `voronoi`: graded organic cells (`min_cell`..`max_cell`, `wall_contrast`). Least readable.
   - `none`: solid plates.
6. **Output** (`export.cad`, `export.preview`): extrude the shapely polygons with build123d
   and export each plate flat plus the assembled model, or render a PNG contact sheet.

## Project layout

```
src/slicekit/
  axes.py       coordinate frame: Axis, anatomical planes, each plate's (u, v) axes
  imaging/      dicom.py (load_series, series_info, find_series) · segment.py · idc.py
  geometry/     sections.py (Section, take_section, mask_outline) · shapes.py
  infill/       tone.py (ToneMap, make_tone_map) · patterns.py (hex, dither, lines, voronoi)
  pipeline/     params.py (KitParams, PRESETS) · model.py (Plate, Kit) · layout.py
                slots.py · progress.py · build.py (prepare_volume, build_kit, make_kit)
  export/       formats.py · cad.py (build123d, STL/STEP) · preview.py (PNG)
  cli/          main.py (slicekit) · download.py (slicekit-download) · options.py
                menu.py · session.py · panels.py · prompts.py
    actions/    ACTIONS (menu order) · series.py · settings.py · output.py
```

## Downloading test data (optional)

The `download` extra wraps [idc-index](https://github.com/ImagingDataCommons/idc-index)
to fetch public CT series from the NCI Imaging Data Commons:

```bash
uv run slicekit-download search --body-part CHEST --max-size 40   # smallest first
uv run slicekit-download get <SeriesInstanceUID> -o tests/data     # -> tests/data/<uid>/
```

```python
from slicekit.imaging.idc import download_series, find_ct_series

uid = find_ct_series(collection="nlst", max_size_mb=40).SeriesInstanceUID[0]
folder = download_series(uid, "tests/data")
```

Search defaults to CC BY licences and skips series whose description looks like a
coronal/sagittal reformat, MIP or scout (a heuristic). Check the licence and cite the
collection's `source_DOI` if you publish anything made from the data. Downloaded series
in `tests/data/` are git-ignored.

## Development

```bash
make install     # uv sync + pre-commit hooks
make check       # lock file, pre-commit (ruff, formatting), mypy, deptry
make test        # pytest (synthetic phantom and synthetic DICOM series)
make docs        # serve the documentation locally
make help        # all targets
```

`tox` runs the tests on Python 3.10 to 3.14. CI (GitHub Actions) runs the same checks,
tests and docs build on every push to `main` and on pull requests.

## Releasing a new version

- Create an API token on [PyPI](https://pypi.org/).
- Add it to the repository secrets as `PYPI_TOKEN`
  ([settings](https://github.com/pedRamezani/slicekit/settings/secrets/actions/new)).
- Create a [new release](https://github.com/pedRamezani/slicekit/releases/new) on GitHub
  with a tag of the form `*.*.*`. The release workflow sets the version, publishes to PyPI
  and deploys the documentation to GitHub Pages.

---

Adapted from the CadQuery sphere kit card (`CQ/sphere_kitcard/sphere_kit_card.ipynb`).
Repository initiated with [osprey-oss/cookiecutter-uv](https://github.com/osprey-oss/cookiecutter-uv).
