import functools
import json
import logging
import pathlib
from dataclasses import dataclass
from math import floor, log10
from typing import Literal, NotRequired, Optional, TypedDict

import fabio
import numpy as np
import pandas as pd
import tifffile
from fabio.openimage import FabioImage
from scipy.ndimage import gaussian_filter

from .instrument import (
    Image,
    InstrumentConfig,
    load_builtin_instruments,
    parse_with_instrument,
)

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


def process_image(e: Experiment, file_path: str) -> pd.DataFrame:
    """
    Process a single image file into Sx, Sz space
    """
    obj: FabioImage = fabio.open(file_path)
    image = parse_with_instrument(e.instrument, obj)

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
        gamma_cols[f"Chi {np.degrees(lo) - 90:.1f} : {np.degrees(hi) - 90:.1f}"] = (
            pd.Series(g_sector)
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

    Returns DataFrame with columns: Chi (degrees), S = r_min to r_max A^-1, etc.
    """
    result = {"Chi (degrees)": np.degrees(out_gamma) - 90}

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
        "instrument": experiment.instrument.name,
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
    instruments: list[InstrumentConfig] | None = None,
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
        instruments=instruments,
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
