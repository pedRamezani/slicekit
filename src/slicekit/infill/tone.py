"""Tone mapping: HU -> tone in [0, 1] -> wanted coverage (0 open .. 1 solid).

The tone map is shared by all plates of a kit, so equal HU print equally dark everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt
from scipy import ndimage

from ..geometry.sections import Section
from ..imaging.dicom import Volume

if TYPE_CHECKING:
    from ..pipeline.params import KitParams


@dataclass
class ToneMap:
    """HU -> tone curve: piecewise linear through knots, then gamma and optional inversion.

    Tone 0 prints as the most open lattice, tone 1 as solid.

    Attributes:
        hu: Knot positions in HU, strictly increasing.
        tone: Tone at each knot, in [0, 1].
        gamma: Exponent applied to the tone; below 1 lifts mid tones towards solid.
        invert: Swap open and solid (dense tissue open).
    """

    hu: np.ndarray
    tone: np.ndarray
    gamma: float = 1.0
    invert: bool = False

    @classmethod
    def linear(cls, lo: float, hi: float, gamma: float = 1.0, invert: bool = False) -> ToneMap:
        """Straight ramp from ``lo`` HU (tone 0) to ``hi`` HU (tone 1).

        Args:
            lo: HU that maps to tone 0 (and everything below it).
            hi: HU that maps to tone 1 (and everything above it).
            gamma: See ``ToneMap.gamma``.
            invert: See ``ToneMap.invert``.

        Returns:
            The tone map.
        """
        return cls(np.array([lo, hi]), np.array([0.0, 1.0]), gamma, invert)

    @classmethod
    def equalized(
        cls, body_hu: np.ndarray, percentiles: tuple[float, float], gamma: float = 1.0, invert: bool = False
    ) -> ToneMap:
        """Histogram equalisation: equal tone steps hold equal amounts of body tissue.

        Args:
            body_hu: HU of every voxel inside the body.
            percentiles: Range of the HU distribution spread over tone 0..1, e.g. (2, 99).
            gamma: See ``ToneMap.gamma``.
            invert: See ``ToneMap.invert``.

        Returns:
            The tone map, with 65 knots at evenly spaced percentiles.
        """
        knots = np.percentile(body_hu, np.linspace(*percentiles, 65))
        knots = knots + np.arange(len(knots)) * 1e-6  # strictly increasing for interp
        return cls(knots, np.linspace(0.0, 1.0, len(knots)), gamma, invert)

    def __call__(self, hu: np.ndarray) -> np.ndarray:
        """Tone in [0, 1] for each HU value."""
        t = np.asarray(np.interp(hu, self.hu, self.tone) ** self.gamma)
        return 1.0 - t if self.invert else t


def tone_field(section: Section, tone: ToneMap, blur: float) -> np.ndarray:
    """Tone per section pixel.

    Args:
        section: Plate section with its mean HU.
        tone: HU -> tone curve.
        blur: Gaussian sigma in mm applied to the HU first; 0 = no blur.

    Returns:
        Tone in [0, 1], indexed like ``section.hu``.
    """
    hu = section.hu.astype(np.float32)
    if blur > 0:
        hu = ndimage.gaussian_filter(hu, blur / section.step)
    return tone(hu)


def tone_curve(t: npt.ArrayLike, perceptual: bool = False) -> np.ndarray:
    """Coverage (0 open .. 1 solid) wanted for a tone.

    Args:
        t: Tone in [0, 1] (values outside are clipped).
        perceptual: Choose the open area (the light let through or reflected) as the CIE
            luminance Y giving lightness L* = 100 (1 - t), so equal tone steps look
            equally lighter. Otherwise coverage equals the tone.

    Returns:
        Coverage in [0, 1].
    """
    tone = np.asarray(np.clip(np.asarray(t, dtype=float), 0.0, 1.0))
    if not perceptual:
        return tone
    lightness = 100.0 * (1.0 - tone)
    luminance = np.where(lightness > 8.0, ((lightness + 16.0) / 116.0) ** 3, lightness / 903.3)
    return np.asarray(1.0 - luminance)


def make_tone_map(volume: Volume, mask: np.ndarray, params: KitParams) -> ToneMap:
    """HU -> tone curve shared by all plates, from the HU distribution inside the body.

    Args:
        volume: Prepared volume.
        mask: Body mask.
        params: Uses ``tone`` (equalize or linear), ``hu_range``, ``hu_percentiles``,
            ``gamma`` and ``invert``.

    Returns:
        The tone map.
    """
    body = volume.hu[mask]
    gamma, invert = params.gamma, params.invert
    if params.tone == "equalize":
        if params.hu_range:
            body = body[(body >= params.hu_range[0]) & (body <= params.hu_range[1])]
            return ToneMap.equalized(body, (0.0, 100.0), gamma, invert)
        return ToneMap.equalized(body, params.hu_percentiles, gamma, invert)
    lo, hi = params.hu_range or np.percentile(body, params.hu_percentiles)
    return ToneMap.linear(float(lo), float(hi), gamma, invert)
