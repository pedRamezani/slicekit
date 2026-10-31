"""Optional progress reporting, so the pipeline can show progress bars without depending on rich."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol, TypeVar

T = TypeVar("T")


class Progress(Protocol):
    """Optional progress wrapper; ``rich.progress.track`` fits this signature."""

    def __call__(self, sequence: Iterable[T], description: str) -> Iterable[T]:
        """Yield the items of ``sequence`` while showing progress labelled ``description``."""
        ...


def track(items: list[T], description: str, progress: Progress | None) -> Iterable[T]:
    """Iterate ``items`` through ``progress`` if one is given, else unchanged."""
    return progress(items, description) if progress else items
