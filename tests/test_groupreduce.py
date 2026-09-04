"""Streaming grouped reductions against pandas.

The sums must match the pandas oracle within floating-point noise; the
maxima and the nearest-target snap must match it exactly.
"""

import numpy as np
import pandas as pd

from rsstitcher.groupreduce import GroupMax, GroupSum, nearest_indexer


class PandasGroupSum:
    """Reference: concatenate every batch and call pandas groupby."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._batches: list[tuple[np.ndarray, np.ndarray]] = []

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        self._batches.append((np.asarray(keys), np.asarray(values, dtype=float)))

    def _grouped(self):
        keys = np.concatenate([k for k, _ in self._batches] or [np.zeros(0, int)])
        values = np.concatenate([v for _, v in self._batches] or [np.zeros(0)])
        return pd.DataFrame({"key": keys, "value": values}).groupby("key")["value"]

    def _full(self, series: pd.Series, fill: float) -> np.ndarray:
        return series.reindex(np.arange(self.size), fill_value=fill).to_numpy()

    @property
    def sum(self) -> np.ndarray:
        return self._full(self._grouped().sum(), 0.0)

    @property
    def nobs(self) -> np.ndarray:
        return self._full(self._grouped().count(), 0).astype(np.int64)

    @property
    def count(self) -> np.ndarray:
        return self._full(self._grouped().size(), 0).astype(np.int64)

    def mean(self) -> np.ndarray:
        return self._grouped().mean().reindex(np.arange(self.size)).to_numpy()


class PandasGroupMax:
    """Reference: concatenate every batch and call pandas groupby."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._batches: list[tuple[np.ndarray, np.ndarray]] = []

    def add(self, keys: np.ndarray, values: np.ndarray) -> None:
        self._batches.append((np.asarray(keys), np.asarray(values, dtype=float)))

    def result(self) -> np.ndarray:
        keys = np.concatenate([k for k, _ in self._batches] or [np.zeros(0, int)])
        values = np.concatenate([v for _, v in self._batches] or [np.zeros(0)])
        grouped = pd.DataFrame({"key": keys, "value": values}).groupby("key")["value"]
        return grouped.max().reindex(np.arange(self.size)).to_numpy()


def _random_batches(rng, size, *, long_runs):
    batches = []
    for _ in range(int(rng.integers(1, 5))):
        n = int(rng.integers(0, 3000))
        keys = rng.integers(0, size, n)
        magnitude = 10.0 ** rng.integers(-8, 8, n)
        values = rng.random(n) * magnitude
        values[rng.random(n) < 0.05] = np.nan
        if long_runs and n:
            keys[: n // 2] = keys[0]
        batches.append((keys, values))
    return batches


def _fill(acc, batches):
    for keys, values in batches:
        acc.add(keys, values)
    return acc


def test_group_sum_matches_pandas_within_noise():
    rng = np.random.default_rng(2)
    for trial in range(40):
        size = int(rng.integers(1, 40))
        batches = _random_batches(rng, size, long_runs=trial % 2 == 0)
        acc = _fill(GroupSum(size), batches)
        oracle = _fill(PandasGroupSum(size), batches)

        assert np.array_equal(np.isnan(acc.mean()), np.isnan(oracle.mean()))
        assert np.allclose(acc.mean(), oracle.mean(), rtol=1e-12, equal_nan=True)
        assert np.allclose(acc.sum, oracle.sum, rtol=1e-12)
        assert np.array_equal(acc.nobs, oracle.nobs)
        assert np.array_equal(acc.count, oracle.count)


def test_group_max_matches_pandas():
    rng = np.random.default_rng(3)
    choices = np.array([0.0, -0.0, 1.0, np.inf, -np.inf, np.nan, 2.5])
    for _ in range(40):
        size = int(rng.integers(1, 40))
        batches = []
        for _ in range(int(rng.integers(1, 5))):
            n = int(rng.integers(0, 2000))
            batches.append((rng.integers(0, size, n), rng.choice(choices, n)))
        result = _fill(GroupMax(size), batches).result()
        expected = _fill(PandasGroupMax(size), batches).result()
        assert np.array_equal(expected, result, equal_nan=True)


def test_nearest_indexer_rule():
    """A midpoint goes to the upper cell, the ends clamp, NaN goes last."""
    rng = np.random.default_rng(0)
    for _ in range(50):
        step = 10.0 ** -int(rng.integers(1, 4))
        n = int(rng.integers(2, 50))
        targets = np.round(rng.uniform(-1, 1) + np.arange(n) * step, 4)
        midpoints = (targets[:-1] + targets[1:]) / 2
        upper = np.arange(1, n)

        assert np.array_equal(nearest_indexer(targets, targets), np.arange(n))
        assert np.array_equal(nearest_indexer(targets, midpoints), upper)
        above = np.nextafter(midpoints, np.inf)
        assert np.array_equal(nearest_indexer(targets, above), upper)
        below = np.nextafter(midpoints, -np.inf)
        assert np.array_equal(nearest_indexer(targets, below), upper - 1)

        ends = np.array([-np.inf, targets[0] - 1e9, targets[-1] + 1e9, np.inf, np.nan])
        assert np.array_equal(
            nearest_indexer(targets, ends), [0, 0, n - 1, n - 1, n - 1]
        )

    single = np.array([0.5])
    values = np.array([-np.inf, -1.0, 0.5, 2.0, np.inf, np.nan])
    assert np.array_equal(nearest_indexer(single, values), np.zeros(6, int))


def test_nearest_indexer_matches_pandas_away_from_midpoints():
    """Same rule as pandas' nearest indexer once values are off the midpoints."""
    rng = np.random.default_rng(1)
    for _ in range(200):
        step = 10.0 ** -int(rng.integers(1, 4))
        start = rng.uniform(-1, 1)
        targets = np.arange(start, start + int(rng.integers(2, 50)) * step, step)
        if rng.random() < 0.5:
            targets = targets.round(3)
        targets = np.unique(targets)
        values = rng.uniform(targets[0] - 2 * step, targets[-1] + 2 * step, 300)
        midpoints = (targets[:-1] + targets[1:]) / 2
        # pandas compares two distances, the indexer one stored midpoint;
        # they can disagree for a value within an ulp of a midpoint.
        off_midpoint = np.abs(values[:, None] - midpoints[None, :]).min(axis=1)
        values = values[off_midpoint > 1e-9 * step]
        values = np.concatenate(
            [values, targets, [np.nan, np.inf, -np.inf, targets[0] - 1e9]]
        )
        expected = pd.Index(targets).get_indexer(values, method="nearest")
        assert np.array_equal(nearest_indexer(targets, values), expected)
