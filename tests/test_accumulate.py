"""Streaming accumulators against the reference (Phase 1) pandas formulas."""

import numpy as np
import pandas as pd

from rsstitcher.accumulate import GridAccumulator, ProfileAccumulator


def test_grid_aggregation():
    cells = np.array([0, 0, 1])
    intensity = np.array([1.0, 3.0, 5.0])

    mean_grid = GridAccumulator((2, 1), aggregation="mean")
    mean_grid.add(cells, intensity)
    assert mean_grid.result()[0, 0] == 2.0
    assert mean_grid.result()[1, 0] == 5.0

    max_grid = GridAccumulator((2, 1), aggregation="max")
    max_grid.add(cells, intensity)
    assert max_grid.result()[0, 0] == 3.0
    assert max_grid.result()[1, 0] == 5.0


def test_zero_intensity_pixels_participate_in_mean():
    grid = GridAccumulator((1, 1), aggregation="mean")
    grid.add(np.array([0, 0]), np.array([0.0, 10.0]))
    assert grid.result()[0, 0] == 5.0


def test_empty_cells_are_nan():
    grid = GridAccumulator((2, 2), aggregation="mean")
    grid.add(np.array([3]), np.array([1.0]))
    assert np.isnan(grid.result()[0, 0])
    assert grid.result()[1, 1] == 1.0


def _reference_profiles(df, n_decimals, n_sectors, radial_bins):
    """The Phase 1 (pandas, whole-table) profile computation."""
    df = df.copy()
    df["S_radius"] = np.sqrt(df["new Sz"] ** 2 + df["new Sx"] ** 2)
    df["Zenith Angle"] = np.pi / 2 - np.arctan2(df["new Sz"], df["new Sx"])
    df["new_R"] = np.round(df["S_radius"], n_decimals)
    df["new_Z"] = np.round(np.degrees(df["Zenith Angle"]), 0)

    sectors = np.degrees(np.linspace(-np.pi / 2, np.pi / 2, n_sectors + 1))
    per_sector = []
    for s in range(n_sectors):
        n_sector = df[(df["new_Z"] >= sectors[s]) & (df["new_Z"] < sectors[s + 1])]
        g_sector = n_sector.groupby("new_R")["Intensity"].mean()
        per_sector.append((f"Zenith {sectors[s]:.1f} : {sectors[s + 1]:.1f}", g_sector))
    all_radii = pd.Index(np.unique(np.concatenate([g.index for _, g in per_sector])))
    azimuthal = {"Radius (A^-1)": all_radii.to_numpy()}
    for label, g_sector in per_sector:
        azimuthal[label] = g_sector.reindex(all_radii).to_numpy()

    per_bin = []
    for r_lo, r_hi in radial_bins:
        r_sector = df[(df["new_R"] >= r_lo) & (df["new_R"] < r_hi)]
        _, counts = np.unique(r_sector["new_Z"], return_counts=True)
        profile = r_sector.groupby("new_Z")["Intensity"].sum() / counts
        per_bin.append((f"S = {r_lo} to {r_hi} A^-1", profile))
    all_zeniths = pd.Index(np.unique(np.concatenate([p.index for _, p in per_bin])))
    radial = {"Zenith (degrees)": all_zeniths.to_numpy()}
    for label, profile in per_bin:
        radial[label] = profile.reindex(all_zeniths).to_numpy()
    return pd.DataFrame(azimuthal), pd.DataFrame(radial)


def _assert_frames_close(actual: pd.DataFrame, expected: pd.DataFrame):
    """Same layout and keys; values within summation-order noise."""
    assert list(actual.columns) == list(expected.columns)
    assert actual.shape == expected.shape
    assert np.array_equal(actual.iloc[:, 0].to_numpy(), expected.iloc[:, 0].to_numpy())
    a, b = actual.to_numpy(), expected.to_numpy()
    assert np.array_equal(np.isnan(a), np.isnan(b))
    assert np.allclose(a, b, rtol=1e-12, atol=0, equal_nan=True)


def test_profile_accumulator_matches_reference_formulas():
    rng = np.random.default_rng(7)
    n_decimals = 2
    out_sx = np.arange(-0.51, 0.51, 0.01).round(n_decimals)
    out_sz = np.arange(-0.01, 0.80, 0.01).round(n_decimals)
    n_sectors = 3
    radial_bins = [(0.2, 0.4), (0.35, 0.6)]

    acc = ProfileAccumulator(out_sx, out_sz, n_decimals, n_sectors, radial_bins)
    frames = []
    for _ in range(4):
        n = 5000
        ix = rng.integers(0, len(out_sx), n)
        iz = rng.integers(0, len(out_sz), n)
        intensity = rng.random(n) * 10.0 ** rng.integers(0, 6, n)
        intensity[rng.random(n) < 0.05] = np.nan
        acc.add(ix * len(out_sz) + iz, intensity)
        frames.append(
            pd.DataFrame(
                {"new Sx": out_sx[ix], "new Sz": out_sz[iz], "Intensity": intensity}
            )
        )

    expected_azimuthal, expected_radial = _reference_profiles(
        pd.concat(frames, ignore_index=True), n_decimals, n_sectors, radial_bins
    )
    _assert_frames_close(acc.azimuthal_profile(), expected_azimuthal)
    _assert_frames_close(acc.radial_profiles(), expected_radial)
