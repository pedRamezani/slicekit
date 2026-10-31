"""slicekit: slice CT scans into a kit of 3D-printable plates with halftone infill.

The plates either interlock (slotted, egg-crate style) or form a gapless stack of slices.

Modules: ``axes`` (coordinate frame), ``imaging`` (DICOM loading and discovery,
segmentation, IDC download), ``geometry`` (plate sections and outlines), ``infill`` (tone
mapping and halftone patterns), ``pipeline`` (parameters, layout, slots, the build),
``export`` (CAD and PNG output) and ``cli`` (command lines and the interactive menu).
"""

from .imaging.dicom import Volume, load_series
from .pipeline import Kit, KitParams, Plate, build_kit, make_kit, prepare_volume

__all__ = ["Kit", "KitParams", "Plate", "Volume", "build_kit", "load_series", "make_kit", "prepare_volume"]
