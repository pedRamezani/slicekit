"""Halftone infill: tone mapping (``tone``) and the hole patterns cut into each plate (``patterns``)."""

from __future__ import annotations

from .patterns import make_infill
from .tone import ToneMap, make_tone_map

__all__ = ["ToneMap", "make_infill", "make_tone_map"]
