import hashlib
import sys
import time
from pathlib import Path

import pytest

from rsstitcher.main import main_cli as rsstitcher_main

DATASETS = {
    "bruker_gid": {
        "tiff_hash": "c7b2a3667012fffdafa9773c4acd4a21",
    },
    "bruker_symmetric": {
        "tiff_hash": "bd63e33972528d3cdda4a854c895b0e4",
    },
    "rigaku_gid": {
        "tiff_hash": "2fe3358fd1931692892838982b386bd4",
    },
    "rigaku_symmetric": {
        "tiff_hash": "956ab201cd97d97318a41a68c18bb51d",
    },
    "new_data": {
        "tiff_hash": "c6f8eaab40dcef52d1ee16d6bccf2f80",
    },
    "cor_powder": {
        "tiff_hash": "d17832b554b6141a75503836542b1074",
    },
}


def md5sum(file_path: Path) -> str:
    """Compute md5 hash of a file."""
    h = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


@pytest.mark.parametrize("dataset", DATASETS.keys())
def test_rsstitcher_outputs(dataset, tmp_path):
    start_time = time.time()

    output_dir = tmp_path
    tiff_file = output_dir / "pixels.tiff"

    args = [
        "-q",
        f"tests/data/{dataset}",
        "--write",
        f"pixels_tiff={tiff_file}",
    ]

    sys.argv = ["rsstitcher"] + args
    rsstitcher_main()

    # Check output file exists
    assert tiff_file.exists(), f"TIFF file missing for dataset {dataset}"

    # Check modification time
    tiff_mod = tiff_file.stat().st_mtime
    assert tiff_mod >= start_time, f"TIFF file not updated for {dataset}"

    # Check hash
    expected = DATASETS[dataset]
    assert md5sum(tiff_file) == expected["tiff_hash"], (
        f"TIFF hash mismatch for {dataset}"
    )


@pytest.mark.parametrize(
    "dataset,mode",
    [("bruker_gid", "symmetric"), ("bruker_gid", "gid"), ("rigaku_gid", "gid")],
)
def test_mode_override(dataset, mode, tmp_path):
    """Test explicit --mode override produces output without error."""
    tiff_file = tmp_path / "pixels.tiff"
    args = [
        "-q",
        f"tests/data/{dataset}",
        "--mode",
        mode,
        "--write",
        f"pixels_tiff={tiff_file}",
    ]
    sys.argv = ["rsstitcher"] + args
    rsstitcher_main()
    assert tiff_file.exists()


def test_azimuthal_bins(tmp_path):
    """Test --azimuthal-bins produces valid CSV with correct column count."""
    csv_file = tmp_path / "azimuthal.csv"
    args = [
        "-q",
        "tests/data/bruker_gid",
        "--azimuthal-bins",
        "3",
        "--write",
        f"azimuthal_csv={csv_file}",
    ]
    sys.argv = ["rsstitcher"] + args
    rsstitcher_main()
    assert csv_file.exists()

    import csv

    with open(csv_file) as f:
        reader = csv.reader(f)
        header = next(reader)
    # 1 shared Radius + 3 Gamma sector columns
    assert len(header) == 4, f"Expected 4 columns, got {len(header)}: {header}"
    assert header[0] == "Radius (S^-1)"
    assert "Gamma" in header[1]

    assert md5sum(csv_file) == "65bb8ecd679f9eaea0843a1199c5c5c3", (
        "Azimuthal CSV hash mismatch"
    )


def test_radial_bins(tmp_path):
    """Test --radial-bins produces valid CSV."""
    csv_file = tmp_path / "radial.csv"
    args = [
        "-q",
        "tests/data/bruker_gid",
        "--radial-bins",
        "0.5,1.0",
        "--write",
        f"radial_csv={csv_file}",
    ]
    sys.argv = ["rsstitcher"] + args
    rsstitcher_main()
    assert csv_file.exists()

    import csv

    with open(csv_file) as f:
        reader = csv.reader(f)
        header = next(reader)
    # angle (degrees) + 1 bin column
    assert len(header) == 2, f"Expected 2 columns, got {len(header)}: {header}"
    assert header[0] == "angle (degrees)"
    assert "S = " in header[1]

    assert md5sum(csv_file) == "8d8b9d9e35e5e3178bfb17ac86d5e382", (
        "Radial CSV hash mismatch"
    )
