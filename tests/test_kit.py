import numpy as np
import pytest
from conftest import DENSE_CENTRE

from slicekit import KitParams, build_kit, prepare_volume
from slicekit.geometry.shapes import polygons
from slicekit.pipeline.slots import intersect_intervals, material_intervals

PARAMS = {
    "thickness": 2.0,
    "gap": 6.0,
    "voxel_size": 1.0,
    "min_cell": 2.5,
    "max_cell": 9.0,
    "wall": 0.8,
    "perimeter": 1.2,
}


@pytest.fixture
def kit(phantom):
    params = KitParams(**PARAMS)
    return build_kit(*prepare_volume(phantom, params), params)


def crossing_overlap(kit, half_width):
    """Total length along the line axis where crossing plates would occupy the same space."""
    p = kit.params
    fam_a = [pl for pl in kit.plates if pl.normal == p.normals[0]]
    fam_b = [pl for pl in kit.plates if pl.normal == p.normals[1]]
    total = 0.0
    for a in fam_a:
        for b in fam_b:
            a_iv = material_intervals(a.outline, a.normal, b.normal, b.position, half_width, p.line_axis)
            b_iv = material_intervals(b.outline, b.normal, a.normal, a.position, half_width, p.line_axis)
            total += sum(hi - lo for lo, hi in intersect_intervals(a_iv, b_iv))
    return total


def test_both_families_present(kit):
    normals = {p.normal for p in kit.plates}
    assert normals == {"z", "y"}
    assert len(kit.plates) >= 10


def test_slots_remove_every_collision(kit):
    assert crossing_overlap(kit, kit.params.thickness / 2) == pytest.approx(0.0, abs=1e-6)


def test_plates_stay_in_one_piece(kit):
    # The phantom is convex, so no slit should split a plate.
    assert all(len(polygons(p.outline)) == 1 for p in kit.plates)


def test_dense_tissue_gets_smaller_cells(kit):
    """On the plate through the bone sphere, holes there are smaller than in soft tissue."""
    dz = DENSE_CENTRE[0]
    plate = min((p for p in kit.plates if p.normal == "z"), key=lambda p: abs(p.position - dz))
    holes = [h for poly in polygons(plate.geometry) for h in poly.interiors]
    centre = np.array([DENSE_CENTRE[2], DENSE_CENTRE[1]])  # plate (u, v) = (x, y)

    def mean_area(near: bool) -> float:
        from shapely.geometry import Polygon

        areas = [
            Polygon(h).area
            for h in holes
            if (np.linalg.norm(np.array(Polygon(h).centroid.coords[0]) - centre) < 8) == near
        ]
        return float(np.mean(areas)) if areas else 0.0

    assert mean_area(near=False) > 3 * mean_area(near=True)


def test_cad_export(kit, tmp_path):
    kit.export(tmp_path, formats=("stl",))
    assert (tmp_path / "assembly.stl").stat().st_size > 0
    assert len(list((tmp_path / "plates").glob("*.stl"))) == len(kit.plates)


def test_assembled_plates_do_not_intersect(phantom):
    params = KitParams(**PARAMS, infill="none")
    kit = build_kit(*prepare_volume(phantom, params), params)
    t = params.thickness
    from slicekit.export import cad

    a = next(p for p in kit.plates if p.normal == "z")
    b = min((p for p in kit.plates if p.normal == "y"), key=lambda p: abs(p.position))
    solid_a = cad.place(a.flat(t), a.normal, a.position, t)
    solid_b = cad.place(b.flat(t), b.normal, b.position, t)
    assert solid_a.volume == pytest.approx(a.outline.area * t, rel=1e-3)
    assert (solid_a & solid_b).volume < 1e-6
