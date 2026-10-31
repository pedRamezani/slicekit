"""Slots that let the two plate families of the interlocking layout slide into each other.

Adapted from the CadQuery sphere kit card: plates of family A (normal ``normals[0]``)
and family B (normal ``normals[1]``) cross along the third axis ``c``. Where a pair
overlaps, A is slotted on one side of a split point ``s`` and B on the other, so each
B plate slides along ``c`` into the stack of A plates. Unlike the sphere, a body
section is not convex, so ``s`` and the sliding direction are chosen per line/plate
to cut as little extra material as possible.
"""

from __future__ import annotations

from collections import defaultdict

import shapely
from shapely.geometry import Polygon
from shapely.geometry.base import BaseGeometry

from ..axes import PLATE_AXES, Axis
from ..geometry.shapes import keep_polygons, plate_box, polygons
from .model import Plate
from .params import KitParams

BIG = 1e5


Intervals = list[tuple[float, float]]


def material_intervals(
    geom: BaseGeometry, normal: Axis, fixed_axis: Axis, fixed_value: float, half_width: float, line_axis: Axis
) -> Intervals:
    """Where a plate has material along a crossing line.

    The crossing plate occupies the strip ``|fixed_axis - fixed_value| < half_width``;
    the plate's material inside that strip, projected onto ``line_axis``, is exactly
    where the two plates would collide.

    Args:
        geom: Plate geometry in its (u, v) frame.
        normal: The plate's normal.
        fixed_axis: The crossing plate's normal.
        fixed_value: The crossing plate's position along ``fixed_axis`` in mm.
        half_width: Half the crossing plate's thickness in mm.
        line_axis: The axis both plates share (the crossing line's direction).

    Returns:
        Merged, sorted (low, high) intervals along ``line_axis`` in mm.
    """
    strip = plate_box(
        normal, {fixed_axis: (fixed_value - half_width, fixed_value + half_width), line_axis: (-BIG, BIG)}
    )
    i = PLATE_AXES[normal].index(line_axis)
    return merge_intervals([(p.bounds[i], p.bounds[i + 2]) for p in polygons(geom.intersection(strip))])


def merge_intervals(intervals: Intervals) -> Intervals:
    """Sort intervals and merge the ones that overlap or touch.

    Args:
        intervals: (low, high) pairs in any order.

    Returns:
        Disjoint intervals in increasing order.
    """
    merged: Intervals = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], hi))
        else:
            merged.append((lo, hi))
    return merged


def intersect_intervals(a: Intervals, b: Intervals) -> Intervals:
    """Overlap of two interval lists.

    Args:
        a: Disjoint intervals.
        b: Disjoint intervals.

    Returns:
        The non-empty pairwise intersections.
    """
    out = [(max(a_lo, b_lo), min(a_hi, b_hi)) for a_lo, a_hi in a for b_lo, b_hi in b]
    return [(lo, hi) for lo, hi in out if hi > lo]


def length_beyond(intervals: Intervals, s: float, direction: int) -> float:
    """Total interval length on one side of a split point.

    Args:
        intervals: Disjoint intervals.
        s: Split point.
        direction: +1 counts the length above ``s``, -1 the length below.

    Returns:
        The summed length in the same unit as the intervals.
    """
    if direction > 0:
        return sum(max(hi - max(lo, s), 0.0) for lo, hi in intervals)
    return sum(max(min(hi, s) - lo, 0.0) for lo, hi in intervals)


def cut_slots(family_a: list[Plate], family_b: list[Plate], params: KitParams) -> None:
    """Cut half-slots into every crossing pair so B plates slide into the stack of A plates.

    Each B plate slides along ``params.line_axis``. The split point of each slot and
    each B plate's sliding direction are chosen to cut as little extra material as
    possible. Outlines are modified in place.

    Args:
        family_a: Plates of the first family (``params.normals[0]``).
        family_b: Plates of the second, sliding family (``params.normals[1]``).
        params: Uses ``thickness``, ``tolerance`` and ``min_area``.
    """
    t, tol, c = params.thickness, params.tolerance, params.line_axis
    half_slot = (t + tol) / 2
    cuts: dict[str, list[Polygon]] = defaultdict(list)

    for b in family_b:
        lines = []
        for a in family_a:
            a_iv = material_intervals(a.outline, a.normal, b.normal, b.position, t / 2, c)
            b_iv = material_intervals(b.outline, b.normal, a.normal, a.position, t / 2, c)
            overlap = intersect_intervals(a_iv, b_iv)
            if overlap:
                lines.append((a, a_iv, b_iv, overlap))

        # direction +1: A is cut above s, B below s, so B slides in towards -c.
        candidates = []
        for direction in (1, -1):
            total, splits = 0.0, []
            for a, a_iv, b_iv, overlap in lines:
                cost, s = min(
                    (length_beyond(a_iv, s, direction) + length_beyond(b_iv, s, -direction), s)
                    for s in ((lo + hi) / 2 for lo, hi in overlap)
                )
                total += cost
                splits.append((a, s))
            candidates.append((total, direction, splits))
        # Keep the default direction unless flipping clearly saves material,
        # so symmetric bodies get consistently oriented slots.
        keep, flip = candidates
        _, direction, splits = flip if flip[0] < 0.8 * keep[0] else keep

        for a, s in splits:
            a_range = (s - tol / 2, BIG) if direction > 0 else (-BIG, s + tol / 2)
            b_range = (-BIG, s + tol / 2) if direction > 0 else (s - tol / 2, BIG)
            cuts[a.name].append(
                plate_box(a.normal, {b.normal: (b.position - half_slot, b.position + half_slot), c: a_range})
            )
            cuts[b.name].append(
                plate_box(b.normal, {a.normal: (a.position - half_slot, a.position + half_slot), c: b_range})
            )

    for plate in family_a + family_b:
        if cuts[plate.name]:
            plate.outline = keep_polygons(
                plate.outline.difference(shapely.union_all(cuts[plate.name])), params.min_area
            )
