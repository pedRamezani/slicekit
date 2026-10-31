"""Build a kit step by step in VS Code cells (``# %%``), previewing with ocp_vscode.

Download a series first, e.g. ``slicekit-download get <SeriesInstanceUID> -o tests/data``,
then run the cells one by one.
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

params = KitParams(
    scale=0.4,
    thickness=3.0,
    gap=9.0,
    tolerance=0.15,
    normals=("z", "y"),  # axial plates + coronal plates sliding along x
    stack=None,  # "sagittal" / "coronal" / "axial": gapless slices, no slots
    infill="hex",  # "hex" | "dither" | "voronoi" | "none"
    tone="equalize",  # or "linear" over hu_range
    pitch=3.0,  # hex / dither cell pitch
    wall=0.6,  # thinnest wall (lightest tissue); dense tissue goes solid
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
