"""
Thin bridge between the Pyodide web worker and rsstitcher.

Called from JavaScript via pyodide.runPython / pyodide.globals.
All file I/O goes through Pyodide's virtual FS (Emscripten FS).
"""

import json
import logging
import time
from contextlib import contextmanager
from pathlib import Path

from rsstitcher.experiment import (
    build_overlay_grid,
    run_experiment,
    write_azimuthal_csv,
    write_experiment_json,
    write_grid_tiff,
    write_pixels_tiff,
    write_radial_csv,
)
from rsstitcher.instrument import resolve_instrument

logger = logging.getLogger("rsstitcher.web")


class _LogForwarder(logging.Handler):
    """Forward rsstitcher's log records to JS as JSON, progress payload included."""

    def __init__(self, callback):
        super().__init__(level=logging.DEBUG)
        self.callback = callback

    def emit(self, record):
        self.callback(
            json.dumps(
                {
                    "time": record.created,
                    "level": record.levelname,
                    "logger": record.name,
                    "message": record.getMessage(),
                    "progress": getattr(record, "progress", None),
                }
            )
        )


@contextmanager
def _forward_logs(callback):
    """Route every record of the ``rsstitcher`` logger to *callback* while active."""
    if callback is None:
        yield
        return
    root = logging.getLogger("rsstitcher")
    handler = _LogForwarder(callback)
    previous_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_level)


def process(
    input_dir: str = "/input",
    output_dir: str = "/output",
    mode: str = "auto",
    scale: str = "linear",
    phi_tolerance: float = 5.0,
    blur_fraction: float = 0.1,
    beta: float | None = None,
    azimuthal_bins: int | None = None,
    radial_bins_str: str | None = None,
    instrument: str = "auto",
    progress=None,
):
    """Run rsstitcher and write outputs to the virtual FS.

    Parameters are passed as simple types (strings/floats/ints) from JS.
    *progress*, when given, is a JS function that receives one JSON string
    per log record of the ``rsstitcher`` logger (time, level, logger,
    message and the progress payload when the record carries one) for the
    pipeline run and the output writes.
    Returns a dict with output paths and metadata.
    """
    with _forward_logs(progress):
        return _process(
            input_dir,
            output_dir,
            mode,
            scale,
            phi_tolerance,
            blur_fraction,
            beta,
            azimuthal_bins,
            radial_bins_str,
            instrument,
        )


def _process(
    input_dir,
    output_dir,
    mode,
    scale,
    phi_tolerance,
    blur_fraction,
    beta,
    azimuthal_bins,
    radial_bins_str,
    instrument,
):
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    radial_bins = None
    if radial_bins_str:
        radial_bins = [
            (float(pair.split(",")[0]), float(pair.split(",")[1]))
            for pair in json.loads(radial_bins_str)
        ]

    instruments = resolve_instrument(instrument)

    result = run_experiment(
        path=input_dir,
        mode=mode,
        scale=scale,
        phi_tolerance=phi_tolerance,
        blur_fraction=blur_fraction,
        beta=beta,
        azimuthal_bins=azimuthal_bins,
        radial_bins=radial_bins,
        instruments=instruments,
    )

    started = time.perf_counter()
    logger.info(
        "Writing the output files",
        extra={"progress": {"stage": "outputs", "done": 0, "total": 1}},
    )
    outputs = {}

    # Always write pixels TIFF
    pixels_path = f"{output_dir}/pixels.tiff"
    write_pixels_tiff(pixels_path, result["result_array"], result["experiment"])
    outputs["pixels_tiff"] = pixels_path

    # Always write experiment JSON
    json_path = f"{output_dir}/experiment.json"
    write_experiment_json(
        json_path,
        result["experiment"],
        mode=result["mode"],
        beta_deg=result["beta_deg"],
    )
    outputs["experiment_json"] = json_path

    # Grid overlay (always generate with auto circles)
    grid_array = build_overlay_grid(
        out_sx=result["out_sx_inv_angstroms"],
        out_sz=result["out_sz_inv_angstroms"],
        radii=[-1.0],
        n_decimals=result["experiment"].n_decimals,
        delta_s=result["experiment"].delta_s,
    )
    grid_path = f"{output_dir}/grid.tiff"
    write_grid_tiff(grid_path, grid_array, result["experiment"])
    outputs["grid_tiff"] = grid_path

    # Azimuthal CSV
    if "azimuthal_profile" in result:
        az_path = f"{output_dir}/1D.csv"
        write_azimuthal_csv(az_path, result["azimuthal_profile"])
        outputs["azimuthal_csv"] = az_path

    # Radial CSV
    if "radial_profiles" in result:
        rad_path = f"{output_dir}/debeye_ring_profile.csv"
        write_radial_csv(rad_path, result["radial_profiles"])
        outputs["radial_csv"] = rad_path

    logger.info(f"Output files: {time.perf_counter() - started:.2f} s")

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
        "blur_pixels": e.blur_pixels if result["mode"] == "gid" else 0,
        "beta_deg": result["beta_deg"],
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
        "n_pixels": result["n_pixels"],
    }

    # Return raw array data for canvas preview
    import numpy as np

    arr = result["result_array"].astype(np.float32)
    array_shape = list(arr.shape)

    # Reuse grid_array computed above for the preview toggle
    grid_data = grid_array.astype(np.uint8).tobytes()

    return {
        "outputs": outputs,
        "summary": summary,
        "array_data": arr.tobytes(),
        "array_shape": array_shape,
        "grid_data": grid_data,
    }
