"""
Grouped reductions fed one batch of (key, value) rows at a time.

``run_experiment`` streams frames, so the reciprocal-space map and the 1D
profiles are built by folding each frame into per-group sums, counts and
maxima. The reductions are plain numpy (``np.bincount`` and ``np.fmax.at``),
so they are order-independent and run unchanged under Pyodide.

Both reductions share one contract: ``add(keys, values)`` folds a batch of
rows whose ``keys`` are integer group ids in ``[0, size)``. NaN values are
skipped by the reductions but still counted in ``count``.
"""

import numpy as np


def _mean(total: np.ndarray, nobs: np.ndarray) -> np.ndarray:
    with np.errstate(invalid="ignore", divide="ignore"):
        out = total / nobs
    out[nobs == 0] = np.nan
    return out


def _drop_nan(keys: np.ndarray, values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    valid = ~np.isnan(values)
    if valid.all():
        return keys, values
    return keys[valid], values[valid]


class GroupSum:
    """Per-group sum of non-NaN values, with counts, fed batch by batch."""

    def __init__(self, size: int) -> None:
        self.sum = np.zeros(size)
        # Number of non-NaN values per group
        self.nobs = np.zeros(size, dtype=np.int64)
        # Number of rows per group, NaN values included
        self.count = np.zeros(size, dtype=np.int64)

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        size = self.sum.shape[0]
        self.count += np.bincount(keys, minlength=size)
        keys, values = _drop_nan(keys, values)
        self.sum += np.bincount(keys, weights=values, minlength=size)
        self.nobs += np.bincount(keys, minlength=size)

    def mean(self) -> np.ndarray:
        """``sum / nobs``; NaN for groups without any non-NaN value."""
        return _mean(self.sum, self.nobs)


class GroupMax:
    """Per-group maximum of non-NaN values, fed batch by batch."""

    def __init__(self, size: int) -> None:
        self._max = np.full(size, np.nan)

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        np.fmax.at(self._max, keys, values)

    def result(self) -> np.ndarray:
        """Per-group maximum; NaN for groups without any non-NaN value."""
        return self._max


def nearest_indexer(targets: np.ndarray, values: np.ndarray) -> np.ndarray:
    """
    Index of the nearest target for each value.

    ``targets`` is a unique, increasing axis. A value belongs to the upper
    cell once it reaches the midpoint between two targets, so an exact
    midpoint resolves upward; values beyond either end clamp to that end;
    NaN sorts last and maps to the last target. This matches
    ``pd.Index(targets).get_indexer(values, method="nearest")`` except for
    values within about one ulp of a midpoint.
    """
    midpoints = (targets[:-1] + targets[1:]) / 2
    return np.searchsorted(midpoints, values, side="right")
