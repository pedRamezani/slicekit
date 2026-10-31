"""Kit parameters: one dataclass that drives the pipeline, the CLI flags and the menu.

Each field's ``metadata`` holds its help text (and ``choices``/``nargs``/``type`` where
needed), which ``cli.options`` turns into CLI flags, menu input and the docs' Parameters page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, get_args

from ..axes import ANATOMICAL_PLANES, AXES, PLANE_NORMAL, AnatomicalPlane, Axis

InfillMode = Literal["none", "hex", "dither", "lines", "voronoi"]


ToneMode = Literal["linear", "equalize"]


INFILL_MODES: tuple[InfillMode, ...] = get_args(InfillMode)


TONE_MODES: tuple[ToneMode, ...] = get_args(ToneMode)


@dataclass
class KitParams:
    """Every setting of the pipeline; all lengths are printed millimetres (after ``scale``).

    Each field's help text lives in its ``metadata``; the CLI flags, the menu's
    parameter editor and the documentation's Parameters page (``parameter_table``)
    are all generated from these fields.

    Raises:
        ValueError: An invalid ``infill``, ``tone``, ``stack`` or ``normals`` value.
    """

    thickness: float = field(default=3.0, metadata={"help": "plate thickness"})
    gap: float = field(default=9.0, metadata={"help": "free space between neighbouring parallel plates"})
    tolerance: float = field(default=0.15, metadata={"help": "extra slot width/depth clearance"})
    normals: tuple[Axis, Axis] = field(
        default=("z", "y"), metadata={"help": "plate normals of the two families (x/y/z)"}
    )
    scale: float = field(default=1.0, metadata={"help": "model scale (0.5 = half size)"})
    voxel_size: float = field(default=0.5, metadata={"help": "resampling voxel size"})
    body_hu: float = field(default=-400.0, metadata={"help": "HU threshold for the body outline"})
    stack: Axis | AnatomicalPlane | None = field(
        default=None,
        metadata={
            "help": "instead of interlocking plates, gapless slices along x/y/z or sagittal/coronal/axial (no slots)",
            "type": str,
            "choices": AXES + ANATOMICAL_PLANES,
        },
    )
    infill: InfillMode = field(
        default="hex",
        metadata={"help": "halftone pattern cut into each plate (none = solid plates)", "choices": INFILL_MODES},
    )
    tone: ToneMode = field(
        default="equalize",
        metadata={
            "help": "HU -> tone: equalize (histogram of the body) or linear over hu_range",
            "choices": TONE_MODES,
        },
    )
    hu_range: tuple[float, float] | None = field(
        default=None,
        metadata={"help": "HU mapped to open / solid; None = hu_percentiles of the body", "nargs": 2},
    )
    hu_percentiles: tuple[float, float] = field(
        default=(2.0, 99.0), metadata={"help": "body HU percentiles used when hu_range is not given"}
    )
    gamma: float = field(default=1.0, metadata={"help": "curve on the tone (<1 lifts mid tones towards solid)"})
    invert: bool = field(default=False, metadata={"help": "dense tissue open, light tissue solid"})
    solid_tone: float = field(default=0.95, metadata={"help": "tone above which the plate is solid (bone)"})
    perceptual: bool = field(default=True, metadata={"help": "equal tone steps look equally lighter (CIE L*)"})
    tone_blur: float = field(default=0.75, metadata={"help": "Gaussian sigma on the HU before toning"})
    pitch: float = field(default=3.0, metadata={"help": "cell / line pitch for hex, dither and lines"})
    line_angle: float = field(default=45.0, metadata={"help": "lines: angle in degrees"})
    line_wave: float = field(default=0.0, metadata={"help": "lines: wave amplitude (0 = straight)"})
    line_wavelength: float = field(default=0.0, metadata={"help": "lines: wave length (0 = 4 x pitch)"})
    wall: float = field(default=0.6, metadata={"help": "thinnest wall (lightest tissue)"})
    min_cell: float = field(default=2.5, metadata={"help": "voronoi: smallest pitch (densest tissue)"})
    max_cell: float = field(default=10.0, metadata={"help": "voronoi: largest pitch (lightest tissue)"})
    wall_contrast: float = field(default=1.0, metadata={"help": "voronoi: 0 = constant walls, 1 = walls up to solid"})
    lloyd_iterations: int = field(default=40, metadata={"help": "voronoi: relaxation steps for the seeds"})
    perimeter: float = field(default=1.2, metadata={"help": "solid band along outlines and slots"})
    min_hole: float = field(default=0.8, metadata={"help": "holes narrower than this are dropped"})
    smooth: float = field(default=1.0, metadata={"help": "outline smoothing (voxels)"})
    simplify: float = field(default=0.1, metadata={"help": "outline simplification tolerance"})
    min_area: float = field(default=4.0, metadata={"help": "drop plate islands smaller than this (mm^2)"})
    seed: int = field(default=0, metadata={"help": "random seed for the infill"})

    def __post_init__(self) -> None:
        """Validate the closed-set options (dataclasses do not check ``Literal`` types)."""
        if self.infill not in INFILL_MODES:
            raise ValueError(f"infill must be one of {INFILL_MODES}, got {self.infill!r}")
        if self.tone not in TONE_MODES:
            raise ValueError(f"tone must be one of {TONE_MODES}, got {self.tone!r}")
        if self.stack is not None and self.stack.lower() not in AXES + ANATOMICAL_PLANES:
            raise ValueError(f"stack must be one of {AXES + ANATOMICAL_PLANES}, got {self.stack!r}")
        a, b = self.normals
        if a == b or {a, b} - set(AXES):
            raise ValueError(f"normals must be two different axes of x/y/z, got {self.normals}")

    @property
    def plate_pitch(self) -> float:
        """Centre distance of neighbouring parallel interlocking plates."""
        return self.thickness + self.gap

    @property
    def stack_axis(self) -> Axis | None:
        """``stack`` as a scanner axis (anatomical names resolved), or None for interlocking plates."""
        if self.stack is None:
            return None
        name = self.stack.lower()
        return PLANE_NORMAL[name] if name in PLANE_NORMAL else next(a for a in AXES if a == name)

    @property
    def line_axis(self) -> Axis:
        """Axis along which the two interlocking families cross (and B plates slide)."""
        return next(a for a in AXES if a not in self.normals)


# name -> (what it looks like, KitParams overrides)
PRESETS: dict[str, tuple[str, dict[str, Any]]] = {
    "photo": ("hex halftone, reads like a photo", {"infill": "hex", "pitch": 3.0, "perceptual": True}),
    "engraving": (
        "straight line screen, always one piece",
        {"infill": "lines", "pitch": 4.0, "line_angle": 45.0, "line_wave": 0.0, "perceptual": True},
    ),
    "wavy": (
        "wavy line screen, engraving look",
        {"infill": "lines", "pitch": 4.0, "line_angle": 0.0, "line_wave": 1.0, "perceptual": True},
    ),
    "screen": (
        "fine line screen: continuous lines, soft gradations, never solid (0.4 mm nozzle limit)",
        {
            "infill": "lines",
            "pitch": 2.0,
            "line_angle": -60.0,
            "line_wave": 0.0,
            "wall": 0.45,
            "min_hole": 0.45,
            "solid_tone": 1.01,
            "tone_blur": 1.0,
            "perceptual": True,
        },
    ),
    "dither": ("open or solid hex cells, finest detail, some worm artefacts", {"infill": "dither", "pitch": 2.0}),
    "voronoi": ("graded organic cells", {"infill": "voronoi"}),
    "solid": ("no infill", {"infill": "none"}),
}
