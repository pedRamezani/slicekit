"""2D plate geometry: volume sections and body outlines (``sections``) and shapely helpers (``shapes``)."""

from .sections import Section, mask_outline, take_section
from .shapes import keep_polygons, plate_box, polygons

__all__ = ["Section", "keep_polygons", "mask_outline", "plate_box", "polygons", "take_section"]
