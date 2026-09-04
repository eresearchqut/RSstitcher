"""
Streaming accumulators for the reciprocal-space map and the 1D profiles.

``run_experiment`` snaps each frame's pixels to grid cells and hands the
flat cell indices plus corrected intensities to these accumulators, one
frame at a time, so memory scales with the output grid rather than the
total pixel count. The arithmetic of the per-group reductions lives in
``groupreduce``; this module decides what is grouped by what.

The reductions are order-independent, so frames may arrive in any order.
"""

from typing import Literal

import numpy as np
import pandas as pd

from .groupreduce import GroupMax, GroupSum


class GridAccumulator:
    """
    Streaming 2D grid over snapped (Sx, Sz) cells.

    Symmetric mode averages every contributing pixel (zeros included); GID
    keeps the maximum.
    """

    def __init__(
        self,
        shape: tuple[int, int],
        aggregation: Literal["mean", "max"],
    ) -> None:
        self.shape = shape
        self.aggregation = aggregation
        n_cells = shape[0] * shape[1]
        if aggregation == "mean":
            self._sums = GroupSum(n_cells)
        elif aggregation == "max":
            self._max = GroupMax(n_cells)
        else:
            raise ValueError(f"Unknown aggregation: {aggregation}")

    def add(self, cells: np.ndarray, intensity: np.ndarray) -> None:
        """Fold pixel intensities into their flat cell indices."""
        if self.aggregation == "mean":
            self._sums.add(cells, intensity)
        else:
            self._max.add(cells, intensity)

    def result(self) -> np.ndarray:
        flat = self._sums.mean() if self.aggregation == "mean" else self._max.result()
        return flat.reshape(self.shape)


class ProfileAccumulator:
    """
    Streaming azimuthal (per-sector radius) and Debye-ring (per-degree
    zenith) profiles over the snapped grid.

    Radius and zenith are properties of a grid cell, so they are computed
    once per cell here; pixels are then folded into per-(sector, radius) and
    per-(ring, zenith) group sums. The azimuthal profile is the mean
    corrected intensity per rounded radius within each sector; the Debye
    ring profile is the summed intensity per whole degree of zenith divided
    by the number of rows at that degree (NaN intensities count in the
    denominator).
    """

    def __init__(
        self,
        out_sx: np.ndarray,
        out_sz: np.ndarray,
        n_decimals: int,
        n_sectors: int | None,
        radial_bins: list[tuple[float, float]] | None,
    ) -> None:
        self.n_sectors = n_sectors if n_sectors is not None and n_sectors >= 1 else 0
        self.radial_bins = list(radial_bins) if radial_bins else []
        self._scale = float(10**n_decimals)

        # np.round(v, n) is rint(v * 10**n) / 10**n, so the rounded radius
        # maps one-to-one onto an integer key.
        s_radius = np.sqrt(out_sz[None, :] ** 2 + out_sx[:, None] ** 2)
        zenith = np.pi / 2 - np.arctan2(out_sz[None, :], out_sx[:, None])
        new_r = np.round(s_radius, n_decimals)
        new_z = np.round(np.degrees(zenith), 0)
        r_key = np.rint(new_r * self._scale).astype(np.int64)
        z_key = new_z.astype(np.int64)
        self._n_r = int(r_key.max()) + 1
        self._z_min = int(z_key.min())
        self._n_z = int(z_key.max()) - self._z_min + 1

        self.sectors = np.degrees(
            np.linspace(-np.pi / 2, np.pi / 2, self.n_sectors + 1)
        )
        sector = np.full(new_z.shape, -1, dtype=np.int64)
        for s in range(self.n_sectors):
            in_sector = (new_z >= self.sectors[s]) & (new_z < self.sectors[s + 1])
            sector[in_sector] = s
        self._azimuthal_key = np.where(
            sector >= 0, sector * self._n_r + r_key, -1
        ).ravel()

        self._n_azimuthal = self.n_sectors * self._n_r
        self._radial_base = [
            self._n_azimuthal + b * self._n_z for b in range(len(self.radial_bins))
        ]
        self._radial_key = [
            np.where(
                (new_r >= r_lo) & (new_r < r_hi),
                base + (z_key - self._z_min),
                -1,
            ).ravel()
            for base, (r_lo, r_hi) in zip(self._radial_base, self.radial_bins)
        ]
        self._sums = GroupSum(self._n_azimuthal + len(self.radial_bins) * self._n_z)

    def add(self, cells: np.ndarray, intensity: np.ndarray) -> None:
        """Fold pixel intensities (by flat cell index) into the profiles."""
        keys: list[np.ndarray] = []
        values: list[np.ndarray] = []
        if self.n_sectors:
            key = self._azimuthal_key[cells]
            in_profile = key >= 0
            keys.append(key[in_profile])
            values.append(intensity[in_profile])
        for radial_key in self._radial_key:
            key = radial_key[cells]
            in_ring = key >= 0
            keys.append(key[in_ring])
            values.append(intensity[in_ring])
        if not keys:
            return
        self._sums.add(np.concatenate(keys), np.concatenate(values))

    def azimuthal_profile(self) -> pd.DataFrame:
        """Per-sector mean corrected intensity per rounded radius."""
        means = self._sums.mean()
        count = self._sums.count
        per_sector: list[tuple[str, np.ndarray, np.ndarray]] = []
        for s in range(self.n_sectors):
            lo, hi = s * self._n_r, (s + 1) * self._n_r
            present = np.flatnonzero(count[lo:hi] > 0)
            label = f"Zenith {self.sectors[s]:.1f} : {self.sectors[s + 1]:.1f}"
            per_sector.append((label, present, means[lo:hi][present]))

        all_keys = np.unique(np.concatenate([p for _, p, _ in per_sector]))
        result: dict[str, np.ndarray] = {"Radius (A^-1)": all_keys / self._scale}
        for label, present, sector_means in per_sector:
            column = np.full(len(all_keys), np.nan)
            column[np.searchsorted(all_keys, present)] = sector_means
            result[label] = column
        return pd.DataFrame(result)

    def radial_profiles(self) -> pd.DataFrame:
        """Per-ring zenith profile: summed corrected intensity over row count."""
        count = self._sums.count
        sums = self._sums.sum
        per_bin: list[tuple[str, np.ndarray, np.ndarray]] = []
        for base, (r_lo, r_hi) in zip(self._radial_base, self.radial_bins):
            lo, hi = base, base + self._n_z
            present = np.flatnonzero(count[lo:hi] > 0)
            profile = sums[lo:hi][present] / count[lo:hi][present]
            per_bin.append((f"S = {r_lo} to {r_hi} A^-1", present, profile))

        all_keys = np.unique(np.concatenate([p for _, p, _ in per_bin]))
        result: dict[str, np.ndarray] = {
            "Zenith (degrees)": (all_keys + self._z_min).astype(float)
        }
        for label, present, profile in per_bin:
            column = np.full(len(all_keys), np.nan)
            column[np.searchsorted(all_keys, present)] = profile
            result[label] = column
        return pd.DataFrame(result)
