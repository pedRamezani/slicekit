import numpy as np
import pytest

from slicekit import Volume

DENSE_CENTRE = (0.0, 8.0, 12.0)  # (z, y, x) mm, relative to the phantom centre


def make_phantom(shape=(70, 90, 110), spacing=(1.0, 1.0, 1.0)) -> Volume:
    """Air around a soft-tissue ellipsoid with a bone sphere and an air (lung) pocket."""
    z, y, x = np.meshgrid(
        *[(np.arange(n) - (n - 1) / 2) * s for n, s in zip(shape, spacing, strict=False)], indexing="ij"
    )
    hu = np.full(shape, -1000, np.int16)
    hu[(z / 30) ** 2 + (y / 40) ** 2 + (x / 50) ** 2 < 1] = 40
    dz, dy, dx = DENSE_CENTRE
    hu[(z - dz) ** 2 + (y - dy) ** 2 + (x - dx) ** 2 < 12**2] = 1200
    hu[(z - 0) ** 2 + (y + 10) ** 2 + (x + 25) ** 2 < 9**2] = -800
    return Volume(hu, spacing, tuple(-(n - 1) * s / 2 for n, s in zip(shape, spacing, strict=False)))


@pytest.fixture
def phantom() -> Volume:
    return make_phantom()
