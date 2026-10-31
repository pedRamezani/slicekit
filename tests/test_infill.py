import dataclasses

import numpy as np
import pytest
import shapely

from slicekit import KitParams, build_kit, prepare_volume
from slicekit.geometry.sections import Section
from slicekit.infill import ToneMap, make_infill
from slicekit.infill.patterns import error_diffusion, hex_fraction_range, hex_grid

BASE = KitParams(pitch=3.0, wall=0.6, perimeter=1.0, min_hole=0.3, tone_blur=0.0, perceptual=False)


def uniform_plate(hu: float, size: float = 60.0, step: float = 0.5):
    n = int(size / step)
    section = Section(np.full((n, n), hu, np.float32), np.ones((n, n), bool), 0.0, 0.0, step)
    return section, shapely.box(0, 0, (n - 1) * step, (n - 1) * step)


def interior_solid_fraction(geom, outline, perimeter):
    interior = outline.buffer(-perimeter - 3, join_style="mitre")  # away from edge effects
    return geom.intersection(interior).area / interior.area


@pytest.mark.parametrize("t", [0.0, 0.3, 0.6, 0.9])
def test_hex_solid_fraction_follows_tone(t):
    """What you see (solid fraction) is linear in tone, from the thinnest lattice to solid."""
    section, outline = uniform_plate(hu=t * 100)
    tone = ToneMap.linear(0, 100)
    geom = make_infill(outline, section, tone, BASE, np.random.default_rng(0))
    f_min, f_max = hex_fraction_range(BASE.pitch, BASE)
    expected = f_min + (f_max - f_min) * t / BASE.solid_tone
    assert interior_solid_fraction(geom, outline, BASE.perimeter) == pytest.approx(expected, abs=0.03)


@pytest.mark.parametrize("t", [0.0, 0.5, 0.9])
def test_lines_solid_fraction_follows_tone_and_stay_connected(t):
    params = dataclasses.replace(BASE, infill="lines", pitch=4.0, line_angle=30.0)
    section, outline = uniform_plate(hu=t * 100)
    geom = make_infill(outline, section, ToneMap.linear(0, 100), params, np.random.default_rng(0))
    f_min, f_max = params.wall / params.pitch, 1 - 1.05 * params.min_hole / params.pitch
    expected = f_min + (f_max - f_min) * t / params.solid_tone
    assert interior_solid_fraction(geom, outline, params.perimeter) == pytest.approx(expected, abs=0.03)
    assert geom.geom_type == "Polygon"  # one connected piece


def test_perceptual_darkens_mid_tones():
    from slicekit.infill.tone import tone_curve

    assert tone_curve(np.array([0.0, 1.0]), perceptual=True) == pytest.approx([0.0, 1.0])
    # L* = 50 is ~18% luminance, so mid tone is ~82% coverage.
    assert tone_curve(np.array([0.5]), perceptual=True)[0] == pytest.approx(0.816, abs=0.01)


def test_dither_average_matches_tone():
    rng = np.random.default_rng(1)
    centres, index = hex_grid((0, 0, 60, 60), 1.0)
    for level in (0.2, 0.5, 0.8):
        out = error_diffusion(np.full(len(centres), level) + rng.normal(0, 0.01, len(centres)), index)
        assert out.dtype == bool
        assert out.mean() == pytest.approx(level, abs=0.03)


def test_dither_and_voronoi_darken_with_density():
    for mode in ("dither", "voronoi"):
        params = dataclasses.replace(BASE, infill=mode)
        fractions = []
        for hu in (10, 90):
            section, outline = uniform_plate(hu)
            geom = make_infill(outline, section, ToneMap.linear(0, 100), params, np.random.default_rng(0))
            fractions.append(interior_solid_fraction(geom, outline, params.perimeter))
        assert fractions[1] > fractions[0] + 0.3, mode


def test_tone_map_equalize_and_invert():
    body = np.concatenate([np.full(500, -800.0), np.linspace(-100, 100, 500)])
    tone = ToneMap.equalized(body, (0, 100))
    # Half the tissue is lung, so lung sits at the bottom half of the tone range.
    assert tone(np.array([-800.0]))[0] <= 0.5
    assert tone(np.array([0.0]))[0] == pytest.approx(0.75, abs=0.05)
    inverted = ToneMap.linear(0, 100, invert=True)
    assert inverted(np.array([0.0, 100.0])).tolist() == [1.0, 0.0]


def test_anatomical_stack_names():
    assert KitParams(stack="Coronal").stack_axis == "y"
    assert KitParams(stack="transversal").stack_axis == "z"
    assert KitParams(stack="x").stack_axis == "x"
    assert KitParams().stack_axis is None
    with pytest.raises(ValueError):
        KitParams(stack="oblique")
    with pytest.raises(ValueError):
        KitParams(infill="stripes")


def test_stack_is_gapless(phantom, tmp_path):
    params = KitParams(stack="sagittal", thickness=2.0, voxel_size=1.0, pitch=2.5)
    kit = build_kit(*prepare_volume(phantom, params), params)
    positions = np.array([p.position for p in kit.plates])
    assert {p.normal for p in kit.plates} == {"x"}
    np.testing.assert_allclose(np.diff(positions), params.thickness)
    # Covers the whole body: phantom half-width along x is 50 mm.
    assert positions[0] - 1 <= -49 and positions[-1] + 1 >= 49
    assert kit.preview(tmp_path / "sheet.png").stat().st_size > 0
