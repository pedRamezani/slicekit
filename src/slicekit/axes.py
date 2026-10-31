"""Coordinate frame: scanner axes, anatomical planes and each plate's (u, v) axes.

Values are ``Literal`` strings, so the dataclass, CLI flags and menus need no conversion;
``get_args`` gives the allowed values from the one definition.
"""

from __future__ import annotations

from typing import Literal, get_args

Axis = Literal["x", "y", "z"]
"""Scanner axes of an axial CT: x = left-right, y = front-back, z = feet-head."""


AnatomicalPlane = Literal["sagittal", "coronal", "axial", "transversal", "transverse"]


AXES: tuple[Axis, ...] = get_args(Axis)


ANATOMICAL_PLANES: tuple[AnatomicalPlane, ...] = get_args(AnatomicalPlane)


PLANE_NORMAL: dict[AnatomicalPlane, Axis] = {
    "sagittal": "x",
    "coronal": "y",
    "axial": "z",
    "transversal": "z",
    "transverse": "z",
}


PLANE_NAME: dict[Axis, AnatomicalPlane] = {"x": "sagittal", "y": "coronal", "z": "axial"}


# Array axis of each scanner axis in Volume.hu, which is indexed [z, y, x].
AXIS_INDEX: dict[Axis, int] = {"z": 0, "y": 1, "x": 2}


# The two world axes a plate spans, as its (u, v): normal z spans (x, y), y spans (x, z), x spans (y, z).
PLATE_AXES: dict[Axis, tuple[Axis, Axis]] = {"z": ("x", "y"), "y": ("x", "z"), "x": ("y", "z")}
