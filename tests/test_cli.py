import hashlib
import sys
import time
from pathlib import Path

import pytest

from rsstitcher.main import main_cli as rsstitcher_main

DATASETS = {
    "bruker_gid": {
        "tiff_hash": "d2ee4f7c90c81380efef3dda8c1873db",
    },
    "bruker_symmetric": {
        "tiff_hash": "c0e5bc576f5ba1eed4a84d3045a1f143",
    },
    "rigaku_gid": {
        "tiff_hash": "a184c6d34438a64432eab57304cc05a7",
    },
    "rigaku_symmetric": {
        "tiff_hash": "1a0eec3609edeffd6face1bc4dd5ca2b",
    },
    "cor_powder": {
        "tiff_hash": "14b46cd5524276e0689bb3acbf8e9f84",
    },
    "alfoil_rigaku": {
        "tiff_hash": "3db08d2cb59a98a6961d844e5fb207e1",
    },
    "bruker_symmetric_phi0": {
        "tiff_hash": "f002b5f9a58979d52ed40254d27bad5e",
    },
    "nist_srm1976c": {
        "tiff_hash": "858cd1ec4b21ea37adc55fe721f53282",
    },
    "zircon": {
        "tiff_hash": "e8807ef0cbf264166778a1293c6624d6",
    },
    "rigaku_si_wafer_a": {
        "tiff_hash": "742d18f10769a6262f2fd449c7957f68",
    },
    "rigaku_si_wafer_b": {
        "tiff_hash": "f4c6e6a6ddbc4002fc1b94a2cc74a702",
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
        "tests/data/rigaku_symmetric",
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
    # 1 shared Radius + 3 Zenith sector columns
    assert len(header) == 4, f"Expected 4 columns, got {len(header)}: {header}"
    assert header[0] == "Radius (A^-1)"
    assert "Zenith" in header[1]

    assert md5sum(csv_file) == "d148240fdf0edeb3a35d1b1a342b7a07", (
        "Azimuthal CSV hash mismatch"
    )


def test_radial_bins(tmp_path):
    """Test --radial-bins produces valid CSV."""
    csv_file = tmp_path / "radial.csv"
    args = [
        "-q",
        "tests/data/rigaku_symmetric",
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
    # Zenith (degrees) + 1 bin column
    assert len(header) == 2, f"Expected 2 columns, got {len(header)}: {header}"
    assert header[0] == "Zenith (degrees)"
    assert "S = " in header[1]

    assert md5sum(csv_file) == "e58d52b3bb3ec2c55c69dfcb9187f9f8", (
        "Radial CSV hash mismatch"
    )


@pytest.mark.parametrize(
    "output,flags",
    [
        ("azimuthal_csv", ["--azimuthal-bins", "3"]),
        ("radial_csv", ["--radial-bins", "0.5,1.0"]),
        ("radial_overlay_tiff", ["--radial-bins", "0.5,1.0"]),
    ],
)
def test_profile_outputs_refused_for_gid(output, flags, tmp_path):
    """Profiles are symmetric-only: asking for one on a GID scan is an error
    that names the mode."""
    out_file = tmp_path / "out"
    args = ["-q", "tests/data/bruker_gid", *flags, "--write", f"{output}={out_file}"]
    sys.argv = ["rsstitcher"] + args
    with pytest.raises(ValueError, match="gid"):
        rsstitcher_main()
    assert not out_file.exists()
