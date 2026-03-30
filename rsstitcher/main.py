import argparse
import logging
import os
import time

import numpy as np

from .experiment import (
    Result,
    build_overlay_grid,
    radial_bin_mask,
    run_experiment,
    write_azimuthal_csv,
    write_experiment_json,
    write_grid_tiff,
    write_pixels_tiff,
    write_radial_csv,
)
from .instrument import get_instrument, load_instrument


def _print_results(
    result: Result,
    start_time: float,
    end_time: float,
    written_files: list[tuple[str, str]],
) -> None:
    pad_length = 30
    print(f"""Experiment parameters:
----------------------
{"Type":{pad_length}} {result["experiment"].type}
{"Data size":{pad_length}} {result["experiment"].data_size[0]} x {result["experiment"].data_size[1]} pixels
{"Detector distance":{pad_length}} {result["experiment"].detector_distance_mm} mm
{"Phi 0":{pad_length}} {result["experiment"].phi0_deg} degrees
{"Wavelength":{pad_length}} {result["experiment"].wavelength_a} Å
{"Pixel size":{pad_length}} {result["experiment"].pixel_mm} mm
{"Theta pixel":{pad_length}} {np.degrees(result["experiment"].theta_pixel_rad):.3f} degrees
{"Phi tolerance":{pad_length}} {result["experiment"].phi_tolerance_deg} degrees
{"Blur":{pad_length}} {result["experiment"].blur_pixels} pixels
{"Delta s":{pad_length}} {result["experiment"].delta_s} Å⁻¹
{"Rounding":{pad_length}} {result["experiment"].n_decimals} decimal places
{"Scaling":{pad_length}} {result["experiment"].scale}
{"Mode":{pad_length}} {result["mode"]}

Results:
--------
{"Sx range":{pad_length}} {result["out_sx_inv_angstroms"][0]:.3f} to {result["out_sx_inv_angstroms"][-1]:.3f} Å⁻¹
{"Sz range":{pad_length}} {result["out_sz_inv_angstroms"][0]:.3f} to {result["out_sz_inv_angstroms"][-1]:.3f} Å⁻¹
{"Number of pixels":{pad_length}} {result["result_array"].shape[0]} x {result["result_array"].shape[1]} pixels
{"Number of images processed":{pad_length}} {len(result["experiment"].file_paths)} images
{"Time taken":{pad_length}} {end_time - start_time:.2f} seconds""")

    if written_files:
        print()
        print("Files written:")
        print("--------------")
        for output, path in written_files:
            full_path = os.path.abspath(path)
            print(f"{output:{pad_length}} {full_path}")


def main_cli():
    parser = argparse.ArgumentParser(
        prog="rsstitcher",
        description="Process 2D diffraction images into a 2D reciprocal space map.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "path", type=str, help="Path to the directory containing the experiment data."
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Suppress all output except errors"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Set the logging level",
    )
    parser.add_argument(
        "--write",
        action="append",
        metavar="OUTPUT=PATH",
        help=(
            """Write output to a custom path or template

Format: OUTPUT=PATH
Outputs: pixels_tiff, grid_tiff, experiment_json, azimuthal_csv, radial_csv, radial_overlay_tiff.

Example: --write pixels_tiff=project_{delta_s}_S.tiff --write grid_tiff=overlays.tiff

Template variables:
    - type
    - data_size
    - detector_distance_mm
    - phi0_deg
    - wavelength_a
    - pixel_mm
    - theta_pixel_rad
    - delta_s
    - n_decimals
    - blur_pixels
    - scale

"""
        ),
    )
    parser.add_argument(
        "--circles",
        nargs="*",
        type=float,
        help=(
            "Overlay radial circles in Å⁻¹ on the output grid.\n"
            "Provide a list of radii (e.g., --circles 0.5 1.0 1.5), or pass -1 to draw\n"
            "default circles every 0.1 Å⁻¹ up to the max radius (e.g., --circles -1).\n"
            "If provided with no values (just --circles), defaults to -1."
        ),
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["auto", "symmetric", "gid"],
        default="auto",
        help="Coordinate transform mode. 'auto' detects from omega range. Default: auto",
    )
    parser.add_argument(
        "--scale",
        type=str,
        choices=["linear", "log", "sqrt"],
        default="linear",
        help="Intensity scaling mode to apply after baseline subtraction and before blur. Default: linear",
    )
    parser.add_argument(
        "--phi-tolerance",
        type=float,
        default=5.0,
        help="Allowed tolerance for phi angle mirroring, in degrees. Default: 5.0 degrees",
    )
    parser.add_argument(
        "--blur-fraction",
        type=float,
        default=0.1,
        help="Fraction of pixels to blur after scaling. Use 0 to disable blurring. Default: 0.1",
    )
    parser.add_argument(
        "--azimuthal-bins",
        type=int,
        default=None,
        metavar="N",
        help="Number of azimuthal sectors for averaging. Enables azimuthal_csv output.",
    )
    parser.add_argument(
        "--radial-bins",
        nargs="+",
        type=str,
        default=None,
        metavar="MIN,MAX",
        help="Radial bins as MIN,MAX pairs (e.g., --radial-bins 0.5,1.0 1.0,2.0). Enables radial_csv output.",
    )
    instrument_group = parser.add_mutually_exclusive_group()
    instrument_group.add_argument(
        "--instrument",
        type=str,
        default=None,
        metavar="NAME",
        help=(
            "Use a specific built-in instrument instead of auto-detecting.\n"
            "Accepts a name or file extension (e.g. 'gfrm', 'Bruker GFRM', 'img', 'Rigaku IMG')."
        ),
    )
    instrument_group.add_argument(
        "--instrument-path",
        type=str,
        default=None,
        metavar="PATH",
        help="Path to a custom instrument config JSON file.",
    )

    args = parser.parse_args()

    if args.log_level:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
        )
    if args.quiet:
        logging.getLogger().setLevel(logging.ERROR)

    radial_bins = None
    if args.radial_bins:
        radial_bins = []
        for spec in args.radial_bins:
            parts = spec.split(",")
            if len(parts) != 2:
                raise ValueError(
                    f"Invalid --radial-bins format: {spec}. Expected MIN,MAX"
                )
            radial_bins.append((float(parts[0]), float(parts[1])))

    instruments = None
    if args.instrument:
        instruments = [get_instrument(args.instrument)]
    elif args.instrument_path:
        instruments = [load_instrument(args.instrument_path)]

    start_time = time.perf_counter()
    result = run_experiment(
        path=args.path,
        mode=args.mode,
        scale=args.scale,
        phi_tolerance=args.phi_tolerance,
        blur_fraction=args.blur_fraction,
        azimuthal_bins=args.azimuthal_bins,
        radial_bins=radial_bins,
        instruments=instruments,
    )
    end_time = time.perf_counter()
    written_files = []

    if args.write:
        for write_arg in args.write:
            try:
                output, out_path = write_arg.split("=", 1)
            except ValueError:
                raise ValueError(f"Invalid --write argument: {write_arg}")
            out_path = out_path.format(**result["experiment"].__dict__)
            if output == "pixels_tiff":
                write_pixels_tiff(
                    file_path=out_path,
                    result_array=result["result_array"],
                    experiment=result["experiment"],
                )
                logging.getLogger(__name__).info(f"Wrote pixels TIFF to {out_path}")
            elif output == "grid_tiff":
                grid_array = build_overlay_grid(
                    out_sx=result["out_sx_inv_angstroms"],
                    out_sz=result["out_sz_inv_angstroms"],
                    radii=args.circles if args.circles else [-1.0],
                    n_decimals=result["experiment"].n_decimals,
                    delta_s=result["experiment"].delta_s,
                )
                write_grid_tiff(
                    file_path=out_path,
                    grid_array=grid_array,
                    experiment=result["experiment"],
                )
                logging.getLogger(__name__).info(f"Wrote grid TIFF to {out_path}")
            elif output == "experiment_json":
                write_experiment_json(
                    file_path=out_path, experiment=result["experiment"]
                )
                logging.getLogger(__name__).info(f"Wrote experiment JSON to {out_path}")
            elif output == "azimuthal_csv":
                if "azimuthal_profile" not in result:
                    raise ValueError(
                        "azimuthal_csv requires --azimuthal-bins to be set"
                    )
                write_azimuthal_csv(out_path, result["azimuthal_profile"])
                logging.getLogger(__name__).info(f"Wrote azimuthal CSV to {out_path}")
            elif output == "radial_csv":
                if "radial_profiles" not in result:
                    raise ValueError("radial_csv requires --radial-bins to be set")
                write_radial_csv(out_path, result["radial_profiles"])
                logging.getLogger(__name__).info(f"Wrote radial CSV to {out_path}")
            elif output == "radial_overlay_tiff":
                if radial_bins is None:
                    raise ValueError(
                        "radial_overlay_tiff requires --radial-bins to be set"
                    )
                overlay = radial_bin_mask(
                    out_sx=result["out_sx_inv_angstroms"],
                    out_sz=result["out_sz_inv_angstroms"],
                    radial_bins=radial_bins,
                    n_decimals=result["experiment"].n_decimals,
                    delta_s=result["experiment"].delta_s,
                )
                write_grid_tiff(
                    file_path=out_path,
                    grid_array=overlay,
                    experiment=result["experiment"],
                )
                logging.getLogger(__name__).info(
                    f"Wrote radial overlay TIFF to {out_path}"
                )
            else:
                raise ValueError(f"Unknown output type: {output}")

            written_files.append((output, out_path))

    if not args.quiet:
        _print_results(result, start_time, end_time, written_files)


if __name__ == "__main__":
    main_cli()
