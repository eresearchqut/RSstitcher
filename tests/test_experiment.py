"""Unit tests for the run_experiment pipeline semantics."""

import logging

import numpy as np
import pytest

from rsstitcher.experiment import (
    get_experiment,
    output_axis,
    prescan_frames,
    run_experiment,
    transform_frame,
)

GID_DATA = "tests/data/rigaku_gid"
SYMMETRIC_DATA = "tests/data/rigaku_symmetric"


@pytest.fixture(scope="module")
def gid_result():
    return run_experiment(GID_DATA)


@pytest.fixture(scope="module")
def symmetric_result():
    return run_experiment(SYMMETRIC_DATA, azimuthal_bins=2, radial_bins=[(0.3, 0.5)])


def test_mode_detection(gid_result, symmetric_result):
    assert gid_result["mode"] == "gid"
    assert symmetric_result["mode"] == "symmetric"


def test_beta_default_gid(gid_result):
    assert gid_result["beta_deg"] == 1.5


def test_beta_default_symmetric(symmetric_result):
    assert symmetric_result["beta_deg"] == 1.5


def test_beta_override(gid_result):
    result = run_experiment(GID_DATA, beta=2.0)
    assert result["beta_deg"] == 2.0
    # A larger cutoff drops more pixels
    assert result["n_pixels"] < gid_result["n_pixels"]


def test_blur_ignored_in_symmetric(symmetric_result):
    result = run_experiment(SYMMETRIC_DATA, blur_fraction=0.0)
    a = symmetric_result["result_array"]
    b = result["result_array"]
    assert a.shape == b.shape
    assert np.array_equal(a, b, equal_nan=True)


def test_blur_applied_in_gid(gid_result):
    result = run_experiment(GID_DATA, blur_fraction=0.0)
    a = gid_result["result_array"]
    b = result["result_array"]
    assert not (a.shape == b.shape and np.array_equal(a, b, equal_nan=True)), (
        "Disabling blur should change GID output"
    )


def test_mode_override_drives_full_branch():
    """Explicit --mode symmetric on GID data applies symmetric semantics."""
    result = run_experiment(GID_DATA, mode="symmetric")
    assert result["mode"] == "symmetric"
    assert result["beta_deg"] == 1.5
    # Symmetric branch has no blur: blur_fraction must not affect output
    result_no_blur = run_experiment(GID_DATA, mode="symmetric", blur_fraction=0.0)
    assert np.array_equal(
        result["result_array"], result_no_blur["result_array"], equal_nan=True
    )


def test_retained_pixel_count_is_set_by_geometry(symmetric_result):
    """No pixel is dropped for having zero intensity: the retained count
    equals the count of pixels surviving the beta cutoff, which depends on
    geometry alone."""
    e = get_experiment(SYMMETRIC_DATA)
    expected = sum(
        int(transform_frame(e, h.image, h.mirror, "symmetric", 1.5).keep.sum())
        for h in prescan_frames(e)
    )
    assert symmetric_result["n_pixels"] == expected


def test_profiles_present_in_symmetric(symmetric_result):
    assert "azimuthal_profile" in symmetric_result
    assert "radial_profiles" in symmetric_result


def test_progress_records_carry_stage_counts(caplog):
    with caplog.at_level(logging.DEBUG, logger="rsstitcher.experiment"):
        run_experiment(GID_DATA)
    records = [r for r in caplog.records if hasattr(r, "progress")]
    payloads = [r.progress for r in records]
    n = len(get_experiment(GID_DATA).file_paths)

    assert payloads[0] == {"stage": "headers", "done": 0, "total": n}
    for stage in ("bounds", "accumulate"):
        ticks = [p for p in payloads if p["stage"] == stage]
        assert [p["done"] for p in ticks] == list(range(n + 1))
        assert {p["total"] for p in ticks} == {n}
    assert "profiles" not in {p["stage"] for p in payloads}

    messages = [r.getMessage() for r in records]
    assert "Grid bounds pass: frame 1 of %d" % n in messages
    assert "Frame accumulation pass: frame %d of %d" % (n, n) in messages
    # The payload rides in the record's extra, not in the formatted text.
    assert "{'stage'" not in caplog.text


def test_profiles_ignored_in_gid(gid_result, caplog):
    """Profiles are defined for symmetric scans only: GID ignores the bins
    with a warning and the map is unchanged."""
    with caplog.at_level(logging.WARNING, logger="rsstitcher.experiment"):
        result = run_experiment(GID_DATA, azimuthal_bins=2, radial_bins=[(0.3, 0.5)])
    assert "azimuthal_profile" not in result
    assert "radial_profiles" not in result
    assert any("symmetric scans" in r.message for r in caplog.records)
    assert np.array_equal(
        result["result_array"], gid_result["result_array"], equal_nan=True
    )


def _reference_axis(min_value, max_value, delta_s, n_decimals):
    """The reference script's np.arange axis, as evaluated on this platform."""
    return np.arange(
        round(min_value, n_decimals) - delta_s,
        round(max_value, n_decimals) + delta_s,
        delta_s,
    ).round(n_decimals)


@pytest.mark.parametrize(
    "min_value,max_value,delta_s,n_decimals",
    [
        (-0.001, 0.4532, 0.001, 3),
        (0.0, 0.6417, 0.002, 3),
        (-0.30171, 0.30165, 0.001, 3),
        (-0.0009, 0.45153, 0.0009, 4),
    ],
)
def test_output_axis_matches_reference_coverage(
    min_value, max_value, delta_s, n_decimals
):
    axis = output_axis(min_value, max_value, delta_s, n_decimals)
    expected = _reference_axis(min_value, max_value, delta_s, n_decimals)
    assert np.array_equal(axis, expected)
    assert np.all(np.diff(axis) > 0)


def test_output_axis_keeps_top_cell_on_non_integer_span():
    """With delta_s = 0.0009 the span is not a whole number of steps and a
    plain round of the ratio would drop the top cell."""
    axis = output_axis(-0.0009, 0.45153, 0.0009, 4)
    start, stop = -0.0009 - 0.0009, 0.4515 + 0.0009
    assert len(axis) == int(np.ceil((stop - start) / 0.0009))
    assert axis[-1] < stop
    assert axis[-1] + 0.0009 >= stop
