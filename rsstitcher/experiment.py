import functools
import json
import logging
import pathlib
import time
from dataclasses import dataclass
from math import ceil, floor, log10
from typing import Literal, NotRequired, Optional, TypedDict

import fabio
import numpy as np
import pandas as pd
import tifffile
from fabio.openimage import FabioImage
from scipy.ndimage import gaussian_filter
from skimage.draw import circle_perimeter

from .accumulate import GridAccumulator, ProfileAccumulator
from .groupreduce import nearest_indexer
from .instrument import (
    Image,
    InstrumentConfig,
    load_builtin_instruments,
    parse_with_instrument,
)

DEFAULT_PIXEL_SIZE = 0.075


logger = logging.getLogger(__name__)


class RSstitcherError(Exception):
    pass


class FileTypeError(RSstitcherError):
    def __init__(self, file_type: str) -> None:
        super().__init__(f"Unknown file type: {file_type}")


class ImageProcessingError(RSstitcherError):
    def __init__(self, message: str, file_path: str) -> None:
        super().__init__(f"{message} in file: {file_path}")


@dataclass
class Experiment:
    type: str
    instrument: InstrumentConfig
    file_paths: list[pathlib.Path]

    data_size: tuple[int, int]

    detector_distance_mm: float
    phi0_deg: float
    wavelength_a: float
    pixel_mm: float
    theta_pixel_rad: float

    mode: Literal["auto", "symmetric", "gid"] = "auto"
    scale: Literal["linear", "log", "sqrt"] = "linear"
    phi_tolerance_deg: float = 5.0
    blur_fraction: float = 0.1

    @functools.cached_property
    def alpha_crop(self) -> np.ndarray:
        """
        Create a mask with blurred edges to reduce edge effects.
        If blur is disabled, return a flat mask of ones (no blurring).
        """
        if self.blur_fraction <= 0.0:
            return np.ones(self.data_size)
        # Pads by half the frame. Only pixels within the truncated kernel's
        # reach (4 sigma) can see the padding boundary, so capping pad at
        # int(4 * self.blur_pixels + 0.5) + 1 gives the same mask bit for
        # bit and builds it about five times faster on wide frames.
        pad = int(round(max(self.data_size) / 2))
        mask = np.ones(self.data_size, dtype=float)
        padded = np.pad(
            mask, ((pad, pad), (pad, pad)), mode="constant", constant_values=0.0
        )
        blurred = gaussian_filter(padded, sigma=self.blur_pixels)
        return blurred[pad : pad + self.data_size[0], pad : pad + self.data_size[1]]

    @functools.cached_property
    def delta_s(self) -> float:
        """
        Theoretical S resolution in A^-1
        """
        return round_to_1((2 * np.sin(self.theta_pixel_rad)) / self.wavelength_a)

    @functools.cached_property
    def n_decimals(self) -> int:
        """
        Number of decimal places to round Sx, Sy to
        """
        return get_decimal_places(self.delta_s)

    @functools.cached_property
    def blur_pixels(self) -> int:
        """
        Number of pixels to use for Gaussian blur
        """
        return int(self.data_size[0] * self.blur_fraction)


def round_to_1(x: float) -> float:
    """
    Round x to 1 significant figure
    """
    if x == 0 or not np.isfinite(x):
        return 0.0
    return np.round(x, -int(floor(log10(abs(x)))))


def get_decimal_places(number: float) -> int:
    """
    Get the number of decimal places in a float
    """
    s = str(number)
    if "." not in s:
        return 0
    return len(s.split(".")[1])


def get_experiment(
    file_path: str,
    mode: Literal["auto", "symmetric", "gid"] = "auto",
    scale: Optional[Literal["linear", "log", "sqrt"]] = "linear",
    phi_tolerance: float = 5.0,
    blur_fraction: float = 0.1,
    instruments: list[InstrumentConfig] | None = None,
) -> Experiment:
    """
    Get experiment parameters from file headers.

    If *instruments* is None the built-in Bruker/Rigaku configs are used.
    Custom instruments are matched first when prepended to the list.
    """
    if instruments is None:
        instruments = list(load_builtin_instruments())

    for instrument in instruments:
        experiment_file_paths = sorted(
            list(pathlib.Path(file_path).rglob(f"*.{instrument.file_extension}"))
        )
        if not experiment_file_paths:
            continue

        obj: FabioImage = fabio.open(experiment_file_paths[0])
        image = parse_with_instrument(instrument, obj)

        return Experiment(
            type=instrument.file_extension,
            instrument=instrument,
            file_paths=experiment_file_paths,
            data_size=image.data_size,
            detector_distance_mm=image.detector_distance_mm,
            phi0_deg=image.phi_degrees,
            wavelength_a=image.wavelength_a,
            pixel_mm=image.pixel_mm,
            theta_pixel_rad=image.theta_pixel_rad,
            mode=mode,
            scale=scale if scale is not None else "linear",
            phi_tolerance_deg=phi_tolerance,
            blur_fraction=blur_fraction,
        )

    raise Exception("No matching experiment files found")


def parse_gfrm(obj: FabioImage) -> Image:
    """Parse a Bruker GFRM file. Delegates to the built-in instrument config."""
    instrument = next(
        i for i in load_builtin_instruments() if i.file_extension == "gfrm"
    )
    return parse_with_instrument(instrument, obj)


def parse_img(obj: FabioImage) -> Image:
    """Parse a Rigaku IMG file. Delegates to the built-in instrument config."""
    instrument = next(
        i for i in load_builtin_instruments() if i.file_extension == "img"
    )
    return parse_with_instrument(instrument, obj)


@dataclass
class FrameHeader:
    """Parsed header of one frame plus its phi-mirroring sign."""

    file_path: pathlib.Path
    image: Image
    mirror: int


def _frame_mirror(e: Experiment, image: Image, file_path: str) -> int:
    if np.isclose(image.phi_degrees, e.phi0_deg, atol=e.phi_tolerance_deg):
        return 1
    if np.isclose(
        image.phi_degrees, (e.phi0_deg + 180) % 360, atol=e.phi_tolerance_deg
    ):
        return -1
    raise ImageProcessingError(
        f"Image phi does not match expected phi: {image.phi_degrees} vs {e.phi0_deg}",
        file_path,
    )


def prescan_frames(e: Experiment) -> list[FrameHeader]:
    """Read every frame header, validating frame shapes and phi mirroring."""
    headers: list[FrameHeader] = []
    for file_path in e.file_paths:
        obj: FabioImage = fabio.open(file_path)
        if e.data_size != obj.shape:
            raise ImageProcessingError(
                f"Not all frames are the same size, got {obj.shape} expected {e.data_size}",
                str(file_path),
            )
        image = parse_with_instrument(e.instrument, obj)
        logger.debug(f"File: {file_path}: {image.chi_degrees=}, {image.phi_degrees=}")
        mirror = _frame_mirror(e, image, str(file_path))
        headers.append(FrameHeader(file_path=file_path, image=image, mirror=mirror))
    return headers


def detect_mode(omega_degrees: np.ndarray) -> Literal["symmetric", "gid"]:
    """Detect whether the experiment is symmetric or GID based on omega range."""
    omegas = np.asarray(omega_degrees, dtype=float)
    return "symmetric" if omegas.max() - omegas.min() == 0 else "gid"


def read_intensity(
    e: Experiment, file_path: str, mode: Literal["symmetric", "gid"]
) -> np.ndarray:
    """
    Read one frame's pixel values as a 2D array, scaled (linear/log/sqrt) and
    edge-blurred in GID mode. Raw detector values are kept as-is (no baseline
    subtraction).
    """
    obj: FabioImage = fabio.open(file_path)
    if e.data_size != obj.shape:
        raise ImageProcessingError(
            f"Not all frames are the same size, got {obj.shape} expected {e.data_size}",
            file_path,
        )

    image_data: np.ndarray = obj.data
    if not np.any(image_data):
        raise ImageProcessingError("Image data is all zeros", file_path)

    if e.scale == "linear":
        pass
    elif e.scale == "log":
        data_no_zero = image_data.astype(np.float32)
        data_no_zero[data_no_zero == 0] = np.nan
        image_data = np.log(data_no_zero)
    elif e.scale == "sqrt":
        image_data = np.sqrt(image_data)
    else:
        raise ValueError(f"Unknown scale: {e.scale}")

    if mode == "gid":
        image_data = image_data * e.alpha_crop
    return image_data


@dataclass
class FrameTransform:
    """Pixels of one frame that survive the beta cutoff, in raster order."""

    keep: np.ndarray  # 2D bool mask over the frame
    sx: np.ndarray  # 1D float64, kept pixels
    sz: np.ndarray  # 1D float64, kept pixels
    correction: np.ndarray | None  # 1D float64 (1 + sin alpha / sin beta), kept pixels


def transform_frame(
    e: Experiment,
    image: Image,
    mirror: int,
    mode: Literal["symmetric", "gid"],
    beta_deg: float,
    with_correction: bool = True,
) -> FrameTransform:
    """
    Compute per-pixel reciprocal coordinates and the sin(alpha)/sin(beta)
    intensity correction for one frame, dropping pixels below the beta cutoff.

    Geometry depends only on the pixel row (x) or column (y), so row- and
    column-wise terms are evaluated once as 1D vectors and broadcast, which
    gives the same per-pixel values as full per-pixel evaluation.
    """
    d = e.detector_distance_mm
    n_i, n_j = e.data_size

    x = (image.beam_position_y - np.arange(n_i)) * e.pixel_mm
    y = (np.arange(n_j) - image.beam_position_x) * e.theta_pixel_rad
    chi = np.radians(image.chi_degrees)
    cos_chi = np.cos(chi)
    sin_chi = np.sin(chi)

    # invalid: arccos of values a float ulp outside [-1, 1] and the 0/0
    # correction; divide: sin_beta == 0 in the correction. Both produce
    # NaN/inf that the accumulators skip.
    with np.errstate(invalid="ignore", divide="ignore"):
        hypot = np.sqrt(d**2 + x**2)
        sin_half_y = np.sin(y / 2)
        two_theta = np.arccos((d * np.cos(y))[None, :] / hypot[:, None])
        chi_prime = np.arctan2(x[:, None], (2 * d * sin_half_y)[None, :])
        x_sin_chi = x * sin_chi

        if mode == "symmetric":
            sin_alpha = sin_half_y * cos_chi
            sin_beta = (
                ((d * sin_half_y) * cos_chi)[None, :] + x_sin_chi[:, None]
            ) / hypot[:, None]
            # ~(a < cutoff) rather than a >= cutoff keeps NaN sin_beta pixels
            keep = ~(sin_beta < np.sin(np.radians(beta_deg)))

            q = (2 * np.sin(two_theta / 2)) / e.wavelength_a
            del two_theta
            chi_s = chi_prime - chi
            del chi_prime
            sz = q * np.cos(chi_s)
            sx = (q * np.sin(chi_s)) * mirror
            del q, chi_s
            correction = (
                (1 + sin_alpha[None, :] / sin_beta) if with_correction else None
            )
        else:
            omega = np.radians(image.omega_degrees)
            sin_alpha = np.sin(omega) * cos_chi
            sin_beta = (
                ((d * np.sin(y - np.arcsin(sin_alpha))) * cos_chi)[None, :]
                + x_sin_chi[:, None]
            ) / hypot[:, None]
            keep = ~(sin_beta < np.sin(np.radians(beta_deg)))

            eoc = np.arccos(
                (cos_chi * np.cos(y / 2))[None, :] * np.cos(chi_prime)
                + sin_chi * np.sin(chi_prime)
            )
            del chi_prime
            q = (2 * np.sin(two_theta / 2)) / e.wavelength_a
            del two_theta
            sr = (q * np.sin(eoc)) * mirror
            gamma = np.arctan2(x[:, None], (d * np.sin(y))[None, :])
            sx = np.where(gamma - chi >= 0, sr, -sr)
            del gamma, sr
            sz = q * np.cos(eoc)
            del q, eoc
            correction = (1 + sin_alpha / sin_beta) if with_correction else None

        del sin_beta
        return FrameTransform(
            keep=keep,
            sx=sx[keep],
            sz=sz[keep],
            correction=correction[keep] if correction is not None else None,
        )


def _normalize_radii(
    radii: list[float],
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    n_decimals: int,
) -> list[float]:
    """Normalize user-provided radii.

    - If radii is empty: return empty list (no circles).
    - If any value < 0: generate default radii every 0.1 Å⁻¹ up to max radius.
    - Round to n_decimals.
    """
    if not radii:
        return []
    if any(r < 0 for r in radii):
        max_r = float(np.sqrt(np.abs(out_sx.max()) ** 2 + np.abs(out_sz.max()) ** 2))
        radii = np.arange(start=0.0, stop=max_r, step=0.1).tolist()
    return list(np.round(radii, n_decimals))


def build_overlay_grid(
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    radii: list[float],
    n_decimals: int,
    delta_s: float,
) -> np.ndarray:
    """Build a grid overlay (circles + axes) as a 0/1 float array."""
    grid = np.zeros((len(out_sx), len(out_sz)))
    shape = grid.shape

    centre_x = int(np.argmin(np.abs(out_sx)))
    centre_z = int(np.argmin(np.abs(out_sz)))

    normalized_radii = _normalize_radii(radii, out_sx, out_sz, n_decimals)
    for radius in normalized_radii:
        rr, cc = circle_perimeter(
            centre_x, centre_z, int(radius / delta_s), shape=shape
        )
        grid[rr, cc] = 1

    grid[:, centre_z] = 1
    grid[centre_x, :] = 1
    return grid


def write_azimuthal_csv(file_path: str, df: pd.DataFrame) -> None:
    """Write azimuthal profile to CSV."""
    df.to_csv(file_path, index=False)


def write_radial_csv(file_path: str, df: pd.DataFrame) -> None:
    """Write radial profiles to CSV."""
    df.to_csv(file_path, index=False)


def radial_bin_mask(
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    radial_bins: list[tuple[float, float]],
    n_decimals: int,
    delta_s: float,
) -> np.ndarray:
    """Create a boolean mask showing radial bin boundaries on the Sx/Sz grid."""
    sx_grid, sz_grid = np.meshgrid(out_sx, out_sz, indexing="ij")
    r = np.round(np.sqrt(sx_grid**2 + sz_grid**2), n_decimals)
    mask = np.zeros_like(r, dtype=bool)
    for r_min, r_max in radial_bins:
        mask |= np.isclose(r, r_min, atol=delta_s / 2)
        mask |= np.isclose(r, r_max, atol=delta_s / 2)
    return mask


def write_pixels_tiff(
    file_path: str, result_array: np.ndarray, experiment: Experiment
) -> None:
    """
    Write the result array to a TIFF file
    """
    tifffile.imwrite(file_path, np.rot90(result_array, 1).astype(np.float32))


def write_grid_tiff(
    file_path: str, grid_array: np.ndarray, experiment: Experiment
) -> None:
    """
    Write the overlay grid (axes + circles) to a TIFF file as float32 (0/1)
    """
    tifffile.imwrite(file_path, np.rot90(grid_array, 1).astype(np.float32))


def write_experiment_json(
    file_path: str,
    experiment: Experiment,
    mode: str | None = None,
    beta_deg: float | None = None,
) -> None:
    """
    Write the experiment parameters to a JSON file.

    Pass the resolved mode and beta from the Result for accurate reporting;
    blur is reported as 0 in symmetric mode since it only applies to GID.
    """
    reported_mode = mode if mode is not None else experiment.mode
    blur_pixels = 0 if reported_mode == "symmetric" else experiment.blur_pixels
    experiment_dict = {
        "type": experiment.type,
        "instrument": experiment.instrument.name,
        "mode": reported_mode,
        "data_size": experiment.data_size,
        "detector_distance_mm": experiment.detector_distance_mm,
        "phi0_deg": experiment.phi0_deg,
        "wavelength_a": experiment.wavelength_a,
        "pixel_mm": experiment.pixel_mm,
        "theta_pixel_rad": experiment.theta_pixel_rad,
        "delta_s": experiment.delta_s,
        "n_decimals": experiment.n_decimals,
        "blur_pixels": blur_pixels,
    }
    if beta_deg is not None:
        experiment_dict["beta_deg"] = beta_deg
    with open(file_path, "w") as f:
        json.dump(experiment_dict, f, indent=4)


class Result(TypedDict):
    result_array: np.ndarray
    out_sx_inv_angstroms: np.ndarray
    out_sz_inv_angstroms: np.ndarray
    experiment: Experiment
    mode: Literal["symmetric", "gid"]
    beta_deg: float
    n_pixels: int
    azimuthal_profile: NotRequired[pd.DataFrame]
    radial_profiles: NotRequired[pd.DataFrame]


def output_axis(
    min_value: float, max_value: float, delta_s: float, n_decimals: int
) -> np.ndarray:
    """
    Build an output grid axis of ``delta_s`` steps spanning
    ``[round(min) - delta_s, round(max) + delta_s)``, rounded to the grid
    precision.

    Stepping an integer index rather than accumulating a float step keeps
    the axis length identical across platforms; the top cell is kept when
    the span is not a whole number of steps.
    """
    start = round(min_value, n_decimals) - delta_s
    stop = round(max_value, n_decimals) + delta_s
    ratio = (stop - start) / delta_s
    n = round(ratio) if abs(ratio - round(ratio)) < 1e-6 else ceil(ratio)
    return np.round(start + np.arange(n) * delta_s, n_decimals)


def _stage(name: str, started: float) -> float:
    now = time.perf_counter()
    logger.info(f"{name}: {now - started:.2f} s")
    return now


def _progress(stage: str, done: int, total: int) -> dict:
    """
    ``extra`` for a log record that also carries machine-readable progress.

    Formatters leave the attribute out, so the CLI log shows the message
    only; a handler can read ``record.progress`` to drive a progress display.
    """
    return {"progress": {"stage": stage, "done": done, "total": total}}


def run_experiment(
    path: str,
    mode: Literal["auto", "symmetric", "gid"] = "auto",
    scale: Optional[Literal["linear", "log", "sqrt"]] = "linear",
    phi_tolerance: float = 5.0,
    blur_fraction: float = 0.1,
    beta: Optional[float] = None,
    azimuthal_bins: Optional[int] = None,
    radial_bins: Optional[list[tuple[float, float]]] = None,
    instruments: list[InstrumentConfig] | None = None,
) -> Result:
    """
    Building the 2D reciprocal space map from the images in the path.

    The mode (symmetric vs GID) is resolved from the omega range across all
    frame headers before any pixel processing, since it controls edge
    blurring, the coordinate transform and grid aggregation. When *beta* is
    None the cutoff is 1.5 degrees in both modes.

    The azimuthal and radial profiles are defined for symmetric scans only;
    *azimuthal_bins* and *radial_bins* are ignored, with a warning, when the
    resolved mode is GID.

    Frames are processed one at a time. A first pass over the frame headers
    computes the reciprocal-space bounds of the output grid; a second pass
    reads each frame's pixels, applies the cutoff and correction, snaps to
    grid cells and folds them into fixed-size accumulators, so memory scales
    with the output grid rather than the total pixel count.
    """
    e = get_experiment(
        path,
        mode=mode,
        scale=scale,
        phi_tolerance=phi_tolerance,
        blur_fraction=blur_fraction,
        instruments=instruments,
    )

    n_decimals = e.n_decimals

    logger.info(f"Setting up a projection orthogonal to phi = {e.phi0_deg} degrees")

    started = time.perf_counter()
    n_frames = len(e.file_paths)
    logger.info(
        "Reading %d frame headers", n_frames, extra=_progress("headers", 0, n_frames)
    )
    headers = prescan_frames(e)
    omegas = np.array([h.image.omega_degrees for h in headers], dtype=float)
    resolved_mode = detect_mode(omegas) if e.mode == "auto" else e.mode
    resolved_beta = beta if beta is not None else 1.5
    started = _stage("Header pre-scan", started)

    logger.info("Computing the grid bounds", extra=_progress("bounds", 0, n_frames))
    sx_min, sx_max = np.inf, -np.inf
    sz_max = -np.inf
    for i, header in enumerate(headers, 1):
        frame = transform_frame(
            e,
            header.image,
            header.mirror,
            resolved_mode,
            resolved_beta,
            with_correction=False,
        )
        if len(frame.sx):
            sx_min = min(sx_min, np.nanmin(frame.sx))
            sx_max = max(sx_max, np.nanmax(frame.sx))
            sz_max = max(sz_max, np.nanmax(frame.sz))
        logger.debug(
            "Grid bounds pass: frame %d of %d",
            i,
            n_frames,
            extra=_progress("bounds", i, n_frames),
        )
    started = _stage("Grid bounds pass", started)

    if sx_min >= 0:
        sx_min = -e.delta_s
    sz_min = 0.0

    out_sx_inv_angstroms = output_axis(sx_min, sx_max, e.delta_s, n_decimals)
    out_sz_inv_angstroms = output_axis(sz_min, sz_max, e.delta_s, n_decimals)
    n_sz = len(out_sz_inv_angstroms)

    grid = GridAccumulator(
        (len(out_sx_inv_angstroms), n_sz),
        aggregation="mean" if resolved_mode == "symmetric" else "max",
    )
    need_profiles = (azimuthal_bins is not None and azimuthal_bins >= 1) or (
        radial_bins is not None and len(radial_bins) > 0
    )
    if need_profiles and resolved_mode == "gid":
        logger.warning(
            "Azimuthal and radial profiles are only defined for symmetric scans; "
            "ignoring them for this GID scan"
        )
        need_profiles = False
    profiles = (
        ProfileAccumulator(
            out_sx_inv_angstroms,
            out_sz_inv_angstroms,
            n_decimals,
            azimuthal_bins,
            radial_bins,
        )
        if need_profiles
        else None
    )

    logger.info("Accumulating frames", extra=_progress("accumulate", 0, n_frames))
    n_pixels = 0
    for i, header in enumerate(headers, 1):
        intensity = read_intensity(e, str(header.file_path), resolved_mode)
        frame = transform_frame(
            e, header.image, header.mirror, resolved_mode, resolved_beta
        )
        # invalid: 0 * inf where a zero pixel meets an infinite correction
        with np.errstate(invalid="ignore"):
            corrected = (intensity[frame.keep] * frame.correction) / 2
        del intensity
        cells = nearest_indexer(
            out_sx_inv_angstroms, frame.sx
        ) * n_sz + nearest_indexer(out_sz_inv_angstroms, frame.sz)
        del frame
        grid.add(cells, corrected)
        if profiles is not None:
            profiles.add(cells, corrected)
        n_pixels += len(corrected)
        logger.debug(
            "Frame accumulation pass: frame %d of %d",
            i,
            n_frames,
            extra=_progress("accumulate", i, n_frames),
        )
    started = _stage("Frame accumulation pass", started)

    result: Result = {
        "result_array": grid.result(),
        "out_sx_inv_angstroms": out_sx_inv_angstroms,
        "out_sz_inv_angstroms": out_sz_inv_angstroms,
        "experiment": e,
        "mode": resolved_mode,
        "beta_deg": resolved_beta,
        "n_pixels": n_pixels,
    }

    if profiles is not None:
        logger.info("Computing the profiles", extra=_progress("profiles", 0, 1))
        if profiles.n_sectors:
            result["azimuthal_profile"] = profiles.azimuthal_profile()
        if profiles.radial_bins:
            result["radial_profiles"] = profiles.radial_profiles()
        _stage("Profiles", started)

    return result
