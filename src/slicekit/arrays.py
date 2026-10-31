"""NumPy array type used in annotations across slicekit.

``np.ndarray`` without type arguments is only accepted by the stubs of newer NumPy
releases; this alias spells the arguments out, so strict mypy passes on every supported
Python (3.10 resolves NumPy 2.2).
"""

from __future__ import annotations

from typing import Any

import numpy.typing as npt

Array = npt.NDArray[Any]
"""Array of any shape and dtype (shapes and dtypes are given in the docstrings)."""
