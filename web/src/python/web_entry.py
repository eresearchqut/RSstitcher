"""
Thin bridge between the Pyodide web worker and rsstitcher.

Called from JavaScript via pyodide.runPython / pyodide.globals.
All file I/O goes through Pyodide's virtual FS (Emscripten FS).
"""

import json
import sys
from pathlib import Path

# rsstitcher source is mounted at /rsstitcher on the virtual FS
if "/rsstitcher" not in sys.path:
    sys.path.insert(0, "/rsstitcher")

from rsstitcher.main import (
    build_overlay_grid,
    run_experiment,
    write_azimuthal_csv,
    write_experiment_json,
    write_grid_tiff,
    write_pixels_tiff,
    write_radial_csv,
)


def process(
    input_dir: str = "/input",
    output_dir: str = "/output",
    mode: str = "auto",
    scale: str = "linear",
    phi_tolerance: float = 5.0,
    blur_fraction: float = 0.1,
    azimuthal_bins: int | None = None,
    radial_bins_str: str | None = None,
    circles_str: str | None = None,
):
    """Run rsstitcher and write outputs to the virtual FS.

    Parameters are passed as simple types (strings/floats/ints) from JS.
    Returns a dict with output paths and metadata.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    radial_bins = None
    if radial_bins_str:
        radial_bins = [
            (float(pair.split(",")[0]), float(pair.split(",")[1]))
            for pair in json.loads(radial_bins_str)
        ]

    result = run_experiment(
        path=input_dir,
        mode=mode,
        scale=scale,
        phi_tolerance=phi_tolerance,
        blur_fraction=blur_fraction,
        azimuthal_bins=azimuthal_bins,
        radial_bins=radial_bins,
    )

    outputs = {}

    # Always write pixels TIFF
    pixels_path = f"{output_dir}/pixels.tiff"
    write_pixels_tiff(pixels_path, result["result_array"], result["experiment"])
    outputs["pixels_tiff"] = pixels_path

    # Always write experiment JSON
    json_path = f"{output_dir}/experiment.json"
    write_experiment_json(json_path, result["experiment"])
    outputs["experiment_json"] = json_path

    # Grid overlay if circles requested
    if circles_str is not None:
        circles = json.loads(circles_str)
        grid_array = build_overlay_grid(
            out_sx=result["out_sx_inv_angstroms"],
            out_sz=result["out_sz_inv_angstroms"],
            radii=circles,
            n_decimals=result["experiment"].n_decimals,
            delta_s=result["experiment"].delta_s,
        )
        grid_path = f"{output_dir}/grid.tiff"
        write_grid_tiff(grid_path, grid_array, result["experiment"])
        outputs["grid_tiff"] = grid_path

    # Azimuthal CSV
    if "azimuthal_profile" in result:
        az_path = f"{output_dir}/azimuthal.csv"
        write_azimuthal_csv(az_path, result["azimuthal_profile"])
        outputs["azimuthal_csv"] = az_path

    # Radial CSV
    if "radial_profiles" in result:
        rad_path = f"{output_dir}/radial.csv"
        write_radial_csv(rad_path, result["radial_profiles"])
        outputs["radial_csv"] = rad_path

    # Build summary dict
    e = result["experiment"]
    summary = {
        "type": e.type,
        "mode": result["mode"],
        "data_size": list(e.data_size),
        "detector_distance_mm": e.detector_distance_mm,
        "phi0_deg": e.phi0_deg,
        "wavelength_a": e.wavelength_a,
        "pixel_mm": e.pixel_mm,
        "theta_pixel_rad": e.theta_pixel_rad,
        "delta_s": e.delta_s,
        "n_decimals": e.n_decimals,
        "blur_pixels": e.blur_pixels,
        "scale": e.scale,
        "sx_range": [
            float(result["out_sx_inv_angstroms"][0]),
            float(result["out_sx_inv_angstroms"][-1]),
        ],
        "sz_range": [
            float(result["out_sz_inv_angstroms"][0]),
            float(result["out_sz_inv_angstroms"][-1]),
        ],
        "result_shape": list(result["result_array"].shape),
        "n_files": len(e.file_paths),
    }

    # Return raw array data for canvas preview
    import numpy as np

    arr = result["result_array"].astype(np.float32)
    array_shape = list(arr.shape)

    # Always generate a grid overlay (auto circles) for the preview toggle
    grid_array = build_overlay_grid(
        out_sx=result["out_sx_inv_angstroms"],
        out_sz=result["out_sz_inv_angstroms"],
        radii=json.loads(circles_str) if circles_str is not None else [-1.0],
        n_decimals=result["experiment"].n_decimals,
        delta_s=result["experiment"].delta_s,
    )
    grid_data = grid_array.astype(np.uint8).tobytes()

    return {
        "outputs": outputs,
        "summary": summary,
        "array_data": arr.tobytes(),
        "array_shape": array_shape,
        "grid_data": grid_data,
    }
