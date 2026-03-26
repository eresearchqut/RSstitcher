import argparse
import functools
import json
import logging
import os
import pathlib
import time
from dataclasses import dataclass
from math import floor, log10
from typing import Literal, NotRequired, Optional, TypedDict

import fabio
import numpy as np
import pandas as pd
import tifffile
from fabio.openimage import FabioImage
from scipy.ndimage import gaussian_filter

IMAGE_COLUMNS = ("Intensity", "x", "y", "TwoTheta", "Chi", "Sx", "Sz", "Omega")
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
    type: Literal["gfrm", "img"]
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
) -> Experiment:
    """
    Get experiment parameters from file headers
    """
    for file_type in ("gfrm", "img"):
        experiment_file_paths = sorted(
            list(pathlib.Path(file_path).rglob(f"*.{file_type}"))
        )
        if not experiment_file_paths:
            continue

        obj: FabioImage = fabio.open(experiment_file_paths[0])
        if file_type == "img":
            image = parse_img(obj)
        elif file_type == "gfrm":
            image = parse_gfrm(obj)
        else:
            raise FileTypeError(file_type)

        return Experiment(
            type=file_type,
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


@dataclass
class Image:
    data_size: tuple[int, int]
    beam_position_x: float
    beam_position_y: float
    chi_degrees: float
    phi_degrees: float
    omega_degrees: float
    detector_distance_mm: float
    wavelength_a: float
    pixel_mm: float
    theta_pixel_rad: float


class MissingHeaderError(RSstitcherError):
    pass


class InvalidHeaderError(RSstitcherError):
    pass


def _float_header_at_index(headers: dict[str, str], header: str, index: int):
    str_header = headers.get(header)
    if str_header is None:
        raise MissingHeaderError(f"Missing header: {header}")
    split = str_header.split()

    try:
        value = split[index]
    except IndexError:
        raise InvalidHeaderError(f"Invalid header value: {header}: {str_header}")

    try:
        return float(value)
    except ValueError:
        raise InvalidHeaderError(f"Invalid header value: {header}: {value}")


def parse_gfrm(obj: FabioImage) -> Image:
    """
    Parse a GFRM file and extract relevant parameters
    """
    h = functools.partial(_float_header_at_index, obj.header)
    beam_position_x = (-1 * h("START", 0)) / h("INCREME", 0)
    beam_position_y = h("CENTER", 1)
    chi_degrees = h("ANGLES", 3) - 180
    phi_degrees = h("ANGLES", 2)
    omega_degrees = h("ANGLES", 1)
    detector_distance_mm = h("DISTANC", 0) * 10
    wavelength_a = h("WAVELEN", 1)
    pixel_mm = DEFAULT_PIXEL_SIZE
    theta_pixel_rad = np.radians(h("INCREME", 0))

    return Image(
        data_size=obj.shape,
        beam_position_x=beam_position_x,
        beam_position_y=beam_position_y,
        chi_degrees=chi_degrees,
        phi_degrees=phi_degrees,
        omega_degrees=omega_degrees,
        detector_distance_mm=detector_distance_mm,
        wavelength_a=wavelength_a,
        pixel_mm=pixel_mm,
        theta_pixel_rad=theta_pixel_rad,
    )


def parse_img(obj: FabioImage) -> Image:
    """
    Parse an IMG file and extract relevant parameters
    """
    h = functools.partial(_float_header_at_index, obj.header)
    beam_position_x = h("PXD_SPATIAL_BEAM_POSITION", 0)
    beam_position_y = h("PXD_SPATIAL_BEAM_POSITION", 1)
    chi_degrees = h("CRYSTAL_GONIO_VALUES", 1)
    phi_degrees = h("CRYSTAL_GONIO_VALUES", 2)
    omega_degrees = h("CRYSTAL_GONIO_VALUES", 0)
    start_theta = h("PXD_GONIO_VALUES", 1)
    detector_distance_mm = h("PXD_GONIO_VALUES", -1)
    wavelength_a = h("SOURCE_WAVELENGTH", -1)
    pixel_mm = h("PXD_DETECTOR_SIZE", -1) / h("PXD_DETECTOR_DIMENSIONS", -1)
    theta_pixel_rad = np.arctan(pixel_mm / detector_distance_mm)
    beam_position_x = beam_position_x - np.radians(start_theta) / theta_pixel_rad

    return Image(
        data_size=obj.shape,
        beam_position_x=beam_position_x,
        beam_position_y=beam_position_y,
        chi_degrees=chi_degrees,
        phi_degrees=phi_degrees,
        omega_degrees=omega_degrees,
        detector_distance_mm=detector_distance_mm,
        wavelength_a=wavelength_a,
        pixel_mm=pixel_mm,
        theta_pixel_rad=theta_pixel_rad,
    )


def process_image(e: Experiment, file_path: str) -> pd.DataFrame:
    """
    Process a single image file into Sx, Sz space
    """
    obj: FabioImage = fabio.open(file_path)

    if e.type == "img":
        parse_func = parse_img
    elif e.type == "gfrm":
        parse_func = parse_gfrm
    else:
        raise ValueError(f"Unknown experiment type: {e.type}")
    image = parse_func(obj)

    if e.data_size != obj.shape:
        raise ImageProcessingError(
            f"Not all frames are the same size, got {obj.shape} expected {e.data_size}",
            file_path,
        )

    logger.debug(f"File: {file_path}: {image.chi_degrees=}, {image.phi_degrees=}")

    image_data: np.ndarray = obj.data
    if not np.any(image_data):
        raise ImageProcessingError("Image data is all zeros", file_path)

    non_zero_minimum = np.min(image_data[np.nonzero(image_data)]).astype(np.float64)
    image_data = np.maximum(0, image_data - non_zero_minimum)

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

    image_data = image_data * e.alpha_crop
    i, j = np.indices(e.data_size)

    intensity_full = image_data.ravel()
    intensity_mask = intensity_full != 0
    intensity = intensity_full[intensity_mask]

    x = (i.ravel()[intensity_mask] - image.beam_position_y) * e.pixel_mm
    y = (j.ravel()[intensity_mask] - image.beam_position_x) * e.theta_pixel_rad

    two_theta = np.arccos(
        (e.detector_distance_mm * np.cos(y)) / np.sqrt(e.detector_distance_mm**2 + x**2)
    )

    chi = np.arctan2(x, 2 * e.detector_distance_mm * np.sin(y / 2)) + np.radians(
        image.chi_degrees + 90
    )

    factor = 2 * np.sin(two_theta / 2) / e.wavelength_a

    if np.abs((np.abs(e.phi0_deg - image.phi_degrees) - 180)) < e.phi_tolerance_deg:
        mirror = -1
    elif np.abs(e.phi0_deg - image.phi_degrees) < e.phi_tolerance_deg:
        mirror = 1
    else:
        raise ImageProcessingError(
            f"Image phi does not match expected phi: {image.phi_degrees} vs {e.phi0_deg}",
            file_path,
        )

    sz = factor * np.cos(chi)
    sx = factor * np.sin(chi) * mirror

    df = pd.DataFrame(
        {
            "Intensity": intensity,
            "x": x,
            "y": y,
            "TwoTheta": two_theta,
            "Chi": chi,
            "Sz": sz,
            "Sx": sx,
            "Omega": np.full_like(intensity, image.omega_degrees),
        },
        columns=IMAGE_COLUMNS,
    )
    return df


def _make_grid(start: float, stop: float, step: float, n_decimals: int) -> np.ndarray:
    """Create an evenly-spaced grid with deterministic length across platforms.

    Uses integer-based stepping instead of np.arange with float step,
    which can produce different array lengths due to FP accumulation.
    """
    n = int(round((stop - start) / step))
    return np.round(start + np.arange(n) * step, n_decimals)


def _snap_to_nearest(values: np.ndarray, targets: np.ndarray) -> np.ndarray:
    """
    Snap each value to the nearest value in a sorted targets array.
    """
    idx = np.searchsorted(targets, values, side="left")
    idx = np.clip(idx, 1, len(targets) - 1)
    left = targets[idx - 1]
    right = targets[idx]
    return np.where(np.abs(values - left) <= np.abs(values - right), left, right)


def detect_mode(image_df: pd.DataFrame) -> Literal["symmetric", "gid"]:
    """Detect whether the experiment is symmetric or GID based on omega range."""
    omega_range = image_df["Omega"].max() - image_df["Omega"].min()
    return "gid" if omega_range > 0 else "symmetric"


def apply_gid_transform(image_df: pd.DataFrame, wavelength_a: float) -> pd.DataFrame:
    """Apply GID coordinate transform, replacing Sx/Sz columns."""
    df = image_df.copy()
    two_theta = df["TwoTheta"].to_numpy()
    chi = df["Chi"].to_numpy()
    y = df["y"].to_numpy()
    sx = df["Sx"].to_numpy()

    factor = 2 * np.sin(two_theta / 2) / wavelength_a

    gid_sz = factor * np.cos(y / 2) * np.cos(chi)

    sin_chi = np.sin(chi)
    safe_sin_chi = np.where(
        np.abs(sin_chi) < 1e-10, np.copysign(1e-10, sin_chi), sin_chi
    )
    cos_term = np.clip(np.cos(chi) * np.cos(y / 2), -1.0, 1.0)
    gid_sr_raw = (sx / safe_sin_chi) * np.sin(np.arccos(cos_term))
    gid_sr = np.where(chi >= 0, gid_sr_raw, -gid_sr_raw)

    df["Sz"] = gid_sz
    df["Sx"] = gid_sr
    return df


def build_grid(
    image_df: pd.DataFrame,
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    n_decimals: int,
) -> np.ndarray:
    """
    Bin reciprocal data into 2D grid
    """
    df = image_df.copy()
    df["Sx_r"] = np.round(df["Sx"], n_decimals)
    df["Sz_r"] = np.round(df["Sz"], n_decimals)
    out_sx_r = np.round(out_sx, n_decimals)
    out_sz_r = np.round(out_sz, n_decimals)

    grid = (
        df.groupby(["Sx_r", "Sz_r"])["Intensity"]
        .max()
        .unstack()
        .reindex(index=out_sx_r, columns=out_sz_r)
    )
    return grid.to_numpy()


def build_grid_azimuth(
    image_df: pd.DataFrame,
    out_r: np.ndarray,
    out_gamma: np.ndarray,
    n_decimals: int,
) -> np.ndarray:
    """
    Bin intensity data into R-Gamma space using sum aggregation.
    """
    df = image_df.copy()
    df["R_r"] = np.round(df["R"], n_decimals)
    df["Gamma_r"] = np.round(df["Gamma"], n_decimals)
    grid = (
        df.groupby(["R_r", "Gamma_r"])["Intensity"]
        .sum()
        .unstack()
        .reindex(
            index=np.round(out_r, n_decimals),
            columns=np.round(out_gamma, n_decimals),
        )
    )
    return grid.to_numpy()


def _normalize_radii(
    radii: list[float],
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    n_decimals: int,
) -> list[float]:
    """Normalize user-provided radii.

    - If radii is None or empty list: return empty list (no circles).
    - If any value < 0: generate default radii every 0.1 Å⁻¹ up to max radius.
    - Always round to n_decimals and ensure 0 is included.
    """
    if any(r < 0 for r in radii):
        max_r = float(
            np.sqrt((np.max(np.abs(out_sx)) ** 2) + (np.max(np.abs(out_sz)) ** 2))
        )
        radii = list(np.arange(0.0, max_r, 0.1))

    radii_arr = np.round(np.asarray(radii, dtype=float), n_decimals)
    if not np.any(np.isclose(radii_arr, 0.0)):
        radii_arr = np.concatenate([np.array([0.0]), radii_arr])
    radii_arr = np.unique(radii_arr)
    return radii_arr.tolist()


def circle_mask(
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    radii: list[float],
    n_decimals: int,
    delta_s: float,
) -> np.ndarray:
    """Compute a boolean mask for circular overlays in Sx/Sz space.

    Efficient vectorized implementation: build a 2D matrix of rounded radii
    for each (Sx, Sz) pixel and check membership against the set of target
    radii using numpy broadcasting and isin.
    """
    normalized_radii = _normalize_radii(radii, out_sx, out_sz, n_decimals)
    if len(normalized_radii) == 0:
        return np.zeros((out_sx.shape[0], out_sz.shape[0]), dtype=bool)

    sx_grid, sz_grid = np.meshgrid(out_sx, out_sz, indexing="ij")
    r = np.round(np.sqrt(sx_grid**2 + sz_grid**2), n_decimals)

    mask = np.zeros_like(r, dtype=bool)
    for target_r in normalized_radii:
        mask |= np.isclose(r, target_r, atol=delta_s / 2)
    return mask


def axis_mask(
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    delta_s: float,
) -> np.ndarray:
    """Compute boolean mask for axes (Sx=0 or Sz=0 within delta_s/2 tolerance)."""
    sx_zero = np.isclose(out_sx, 0.0, atol=delta_s / 2.0)[:, None]
    sz_zero = np.isclose(out_sz, 0.0, atol=delta_s / 2.0)[None, :]
    return sx_zero | sz_zero


def build_overlay_grid(
    out_sx: np.ndarray,
    out_sz: np.ndarray,
    radii: list[float],
    n_decimals: int,
    delta_s: float,
) -> np.ndarray:
    """Build a grid for overlays (circles + optional axes) as a boolean array."""
    grid = np.zeros((out_sx.shape[0], out_sz.shape[0]), dtype=bool)
    grid |= axis_mask(out_sx, out_sz, delta_s)
    grid |= circle_mask(
        out_sx, out_sz, radii=radii, n_decimals=n_decimals, delta_s=delta_s
    )
    return grid


def _build_polar_grid(
    image_df: pd.DataFrame,
    n_decimals: int,
    delta_s: float,
    sx_min: float,
    sx_max_raw: float,
    sz_max_raw: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, pd.DataFrame]:
    """
    Build shared R-Gamma intensity grid for azimuthal/radial profiles.
    """
    df = image_df.copy()
    df["R"] = np.sqrt(df["Sx"] ** 2 + df["Sz"] ** 2)
    df["Gamma"] = np.arctan2(df["Sz"], df["Sx"])

    # Position grid from positive-Sz half-plane
    out_sx_full = np.arange(
        round(sx_min, n_decimals),
        round(sx_max_raw, n_decimals) + delta_s,
        delta_s,
    )
    out_sz_full = np.arange(0, round(sz_max_raw, n_decimals) + delta_s, delta_s)
    full_x, full_z = np.meshgrid(out_sx_full, out_sz_full)
    positions = pd.DataFrame(
        {
            "R": np.sqrt(full_x.ravel() ** 2 + full_z.ravel() ** 2),
            "Gamma": np.arctan2(full_z.ravel(), full_x.ravel()),
            "Intensity": 1.0,
        }
    )

    # R and Gamma grids derived from positions (using delta_s as R step)
    out_r = np.arange(
        round(float(positions["R"].min()), n_decimals) - delta_s,
        round(float(positions["R"].max()), n_decimals) + delta_s,
        delta_s,
    )
    delta_gamma = np.radians(0.5)
    out_gamma = np.arange(
        round(float(positions["Gamma"].min()), n_decimals) - delta_gamma,
        round(float(positions["Gamma"].max()), n_decimals) + delta_gamma,
        delta_gamma,
    )

    # Snap positions and data to grids
    positions["R"] = _snap_to_nearest(positions["R"].to_numpy(), out_r)
    positions["Gamma"] = _snap_to_nearest(positions["Gamma"].to_numpy(), out_gamma)

    df["R"] = _snap_to_nearest(df["R"].to_numpy(), out_r)
    df["Gamma"] = _snap_to_nearest(df["Gamma"].to_numpy(), out_gamma)

    # Build intensity grid
    r_gamma = build_grid_azimuth(df, out_r, out_gamma, n_decimals)

    return r_gamma, out_r, out_gamma, positions


def compute_azimuthal_profile(
    r_gamma: np.ndarray,
    out_r: np.ndarray,
    out_gamma: np.ndarray,
    positions: pd.DataFrame,
    n_sectors: int,
) -> pd.DataFrame:
    """
    Compute azimuthal average profile split into N sectors over [0, pi].
    """
    sector_boundaries = np.linspace(0, np.pi, n_sectors + 1)
    gamma_cols: dict[str, pd.Series] = {}
    radius = pd.Series(dtype=float)

    for s in range(n_sectors):
        lo = sector_boundaries[s]
        hi = sector_boundaries[s + 1]

        n_sector = positions[(positions["Gamma"] >= lo) & (positions["Gamma"] < hi)]
        values, counts = np.unique(
            n_sector["R"].to_numpy(), return_counts=True, equal_nan=False
        )

        gamma_mask = (out_gamma >= lo) & (out_gamma < hi)
        g_sector = np.nansum(r_gamma[:, gamma_mask], axis=1)[: len(counts)] / counts

        radius = pd.Series(values)
        gamma_cols[f"Gamma {np.degrees(lo):.1f} : {np.degrees(hi):.1f}"] = pd.Series(
            g_sector
        )

    # Single shared Radius column — all sectors share the same non-NaN radii
    # because the detector's angular coverage doesn't reach the grid corners
    # (the truncated tail is only NaN).
    result: dict[str, pd.Series] = {"Radius (S^-1)": radius}
    result.update(gamma_cols)
    return pd.DataFrame.from_dict(result)


def write_azimuthal_csv(file_path: str, df: pd.DataFrame) -> None:
    """Write azimuthal profile to CSV."""
    df.to_csv(file_path, index=False)


def compute_radial_profiles(
    r_gamma: np.ndarray,
    out_r: np.ndarray,
    out_gamma: np.ndarray,
    radial_bins: list[tuple[float, float]],
    n_decimals: int,
) -> pd.DataFrame:
    """Compute radial intensity profiles from the shared R-Gamma grid.

    Returns DataFrame with columns: angle (degrees), S = r_min to r_max A^-1, etc.
    """
    result = {"angle (degrees)": np.degrees(out_gamma) - 90}

    for r_lo, r_hi in radial_bins:
        col_name = f"S = {r_lo} to {r_hi} A^-1"
        mask = (out_r >= r_lo) & (out_r < r_hi)
        if mask.any():
            result[col_name] = np.nanmax(r_gamma[mask, :], axis=0)
        else:
            result[col_name] = np.full(len(out_gamma), np.nan)

    return pd.DataFrame(result)


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
    tifffile.imwrite(file_path, np.fliplr(np.rot90(result_array, 1)).astype(np.float32))


def write_grid_tiff(
    file_path: str, grid_array: np.ndarray, experiment: Experiment
) -> None:
    """
    Write the overlay grid (axes + circles) to a TIFF file as float32 (0/1)
    """
    data = grid_array.astype(np.float32)
    tifffile.imwrite(file_path, np.fliplr(np.rot90(data, 1)))


def write_experiment_json(file_path: str, experiment: Experiment) -> None:
    """
    Write the experiment parameters to a JSON file
    """
    experiment_dict = {
        "type": experiment.type,
        "mode": experiment.mode,
        "data_size": experiment.data_size,
        "detector_distance_mm": experiment.detector_distance_mm,
        "phi0_deg": experiment.phi0_deg,
        "wavelength_a": experiment.wavelength_a,
        "pixel_mm": experiment.pixel_mm,
        "theta_pixel_rad": experiment.theta_pixel_rad,
        "delta_s": experiment.delta_s,
        "n_decimals": experiment.n_decimals,
        "blur_pixels": experiment.blur_pixels,
    }
    with open(file_path, "w") as f:
        json.dump(experiment_dict, f, indent=4)


class Result(TypedDict):
    result_array: np.ndarray
    out_sx_inv_angstroms: np.ndarray
    out_sz_inv_angstroms: np.ndarray
    experiment: Experiment
    mode: Literal["symmetric", "gid"]
    image_df: pd.DataFrame
    azimuthal_profile: NotRequired[pd.DataFrame]
    radial_profiles: NotRequired[pd.DataFrame]


def run_experiment(
    path: str,
    mode: Literal["auto", "symmetric", "gid"] = "auto",
    scale: Optional[Literal["linear", "log", "sqrt"]] = "linear",
    phi_tolerance: float = 5.0,
    blur_fraction: float = 0.1,
    azimuthal_bins: Optional[int] = None,
    radial_bins: Optional[list[tuple[float, float]]] = None,
) -> Result:
    """
    Building the 2D reciprocal space map from the images in the path
    """
    e = get_experiment(
        path,
        mode=mode,
        scale=scale,
        phi_tolerance=phi_tolerance,
        blur_fraction=blur_fraction,
    )

    n_decimals = get_decimal_places(e.delta_s)

    logger.info(f"Setting up a projection orthogonal to phi = {e.phi0_deg} degrees")

    results = map(functools.partial(process_image, e), e.file_paths)
    image_df = pd.concat(results)

    resolved_mode = detect_mode(image_df) if e.mode == "auto" else e.mode
    if resolved_mode == "gid":
        image_df = apply_gid_transform(image_df, e.wavelength_a)

    if image_df["Sx"].min() >= 0:
        sx_min = -e.delta_s
    else:
        sx_min = round(image_df["Sx"].min(), n_decimals)

    if image_df["Sz"].min() >= 0:
        sz_min = -e.delta_s
    else:
        sz_min = round(image_df["Sz"].min(), n_decimals)

    out_sx_inv_angstroms = np.round(
        np.arange(
            sx_min - e.delta_s,
            round(image_df["Sx"].max(), n_decimals) + e.delta_s,
            e.delta_s,
        ),
        n_decimals,
    )
    out_sz_inv_angstroms = np.round(
        np.arange(
            sz_min - e.delta_s,
            round(image_df["Sz"].max(), n_decimals) + e.delta_s,
            e.delta_s,
        ),
        n_decimals,
    )

    sx_max_raw = float(image_df["Sx"].max())
    sz_max_raw = float(image_df["Sz"].max())

    image_df["Sx"] = _snap_to_nearest(image_df["Sx"].to_numpy(), out_sx_inv_angstroms)
    image_df["Sz"] = _snap_to_nearest(image_df["Sz"].to_numpy(), out_sz_inv_angstroms)

    result_array = build_grid(
        image_df,
        out_sx_inv_angstroms,
        out_sz_inv_angstroms,
        n_decimals=e.n_decimals,
    )

    result: Result = {
        "result_array": result_array,
        "out_sx_inv_angstroms": out_sx_inv_angstroms,
        "out_sz_inv_angstroms": out_sz_inv_angstroms,
        "experiment": e,
        "mode": resolved_mode,
        "image_df": image_df,
    }

    need_polar = (azimuthal_bins is not None and azimuthal_bins >= 1) or (
        radial_bins is not None and len(radial_bins) > 0
    )
    if need_polar:
        r_gamma, out_r, out_gamma, positions = _build_polar_grid(
            image_df,
            n_decimals=n_decimals,
            delta_s=e.delta_s,
            sx_min=sx_min,
            sx_max_raw=sx_max_raw,
            sz_max_raw=sz_max_raw,
        )

    if azimuthal_bins is not None and azimuthal_bins >= 1:
        result["azimuthal_profile"] = compute_azimuthal_profile(
            r_gamma, out_r, out_gamma, positions, n_sectors=azimuthal_bins
        )

    if radial_bins is not None and len(radial_bins) > 0:
        result["radial_profiles"] = compute_radial_profiles(
            r_gamma, out_r, out_gamma, radial_bins, n_decimals
        )

    return result


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

    start_time = time.perf_counter()
    result = run_experiment(
        path=args.path,
        mode=args.mode,
        scale=args.scale,
        phi_tolerance=args.phi_tolerance,
        blur_fraction=args.blur_fraction,
        azimuthal_bins=args.azimuthal_bins,
        radial_bins=radial_bins,
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
                logger.info(f"Wrote pixels TIFF to {out_path}")
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
                logger.info(f"Wrote grid TIFF to {out_path}")
            elif output == "experiment_json":
                write_experiment_json(
                    file_path=out_path, experiment=result["experiment"]
                )
                logger.info(f"Wrote experiment JSON to {out_path}")
            elif output == "azimuthal_csv":
                if "azimuthal_profile" not in result:
                    raise ValueError(
                        "azimuthal_csv requires --azimuthal-bins to be set"
                    )
                write_azimuthal_csv(out_path, result["azimuthal_profile"])
                logger.info(f"Wrote azimuthal CSV to {out_path}")
            elif output == "radial_csv":
                if "radial_profiles" not in result:
                    raise ValueError("radial_csv requires --radial-bins to be set")
                write_radial_csv(out_path, result["radial_profiles"])
                logger.info(f"Wrote radial CSV to {out_path}")
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
                logger.info(f"Wrote radial overlay TIFF to {out_path}")
            else:
                raise ValueError(f"Unknown output type: {output}")

            written_files.append((output, out_path))

    if not args.quiet:
        _print_results(result, start_time, end_time, written_files)


if __name__ == "__main__":
    main_cli()
