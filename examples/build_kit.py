"""Build a kit step by step in VS Code cells (``# %%``), previewing with ocp_vscode.

Download a series first, e.g. ``slicekit-download get <SeriesInstanceUID> -o tests/data``,
then run the cells one by one.

The parameters below were chosen by comparing infill settings on the NLST chest CT used
here, scoring how closely each plate (blurred as the eye sees it) matches the CT and
how much of it is thinner than a 0.4 mm nozzle can print. Hex holes at 2.5-2.75 mm pitch
with single-line walls scored best; two-line walls (``wall=0.85``) are sturdier but lose
about a third of the contrast, and a line screen (``infill="lines"``, ``pitch=3``) gives
more contrast with a little less detail.
"""

# %% Module import
from pathlib import Path

from ocp_vscode import show

from slicekit import KitParams, build_kit, load_series, prepare_volume

# %% Parameters (all lengths in printed mm)
# folder of .dcm slices, e.g. from: slicekit-download get <SeriesInstanceUID> -o tests/data
dicom_dir = (
    Path(__file__).parents[1] / "tests" / "data" / "1.3.6.1.4.1.14519.5.2.1.7009.9004.300915470453119236782416009817"
)
out_dir = Path(__file__).parent / "out"

# Tuned for a standard 0.4 mm nozzle: the finest pattern that still prints, which
# also gave the best anatomy in a comparison on a chest CT (see the module docstring).
params = KitParams(
    # Layout
    scale=0.4,  # a chest (~350 mm wide) prints ~140 mm wide
    thickness=3.0,
    gap=9.0,  # free space between parallel plates; slots are thickness + tolerance wide
    tolerance=0.15,  # slot clearance; increase if plates bind
    normals=("z", "y"),  # axial plates + coronal plates sliding along x
    stack=None,  # "sagittal" / "coronal" / "axial": gapless slices, no slots
    # Infill: hex halftone, hole size follows the tissue density
    infill="hex",  # "hex" | "lines" | "dither" | "voronoi" | "none"
    pitch=2.75,  # hole spacing; 2.5-2.75 mm resolves vessels and ribs best at this scale
    wall=0.45,  # thinnest wall = one extrusion line; thinner walls do not print
    min_hole=0.55,  # narrower holes are dropped, as they would fuse shut
    perimeter=1.2,  # solid band along the outline and slots (about three lines)
    # Tone: how CT density maps to how solid the plate looks
    tone="equalize",  # spread the tones over the tissue present (or "linear" over hu_range)
    perceptual=True,  # equal density steps look equally darker
    tone_blur=0.5,  # mm of smoothing on the CT before toning; less keeps more detail
)

# %% Load and segment
volume, mask = prepare_volume(load_series(dicom_dir), params)
print(f"Prepared volume {volume.shape} at {volume.spacing[0]} mm")

# %% Build plates
kit = build_kit(volume, mask, params)
print(", ".join(p.name for p in kit.plates))

# %% Quick 2D preview of every plate (seconds, no CAD)
kit.preview(out_dir / "preview.png")

# %% 3D preview
show(kit.assembled())

# %% Single plate, flat
show(kit.plates[len(kit.plates) // 4].flat(params.thickness))

# %% Export
kit.export(out_dir)
