"""Declarative instrument configuration for RSstitcher.

Instrument configs define how to extract detector parameters from image file
headers. Built-in configs for Bruker (.gfrm) and Rigaku (.img) are shipped
as JSON files in the instruments/ directory; users can supply additional
configs via the --instrument CLI flag.

A config file is JSON with four keys:

    name            — human-readable instrument name
    file_extension  — file extension to match (without the dot)
    header_values   — named extractions from the fabio header dict
    fields          — expressions evaluated in order to produce Image fields

Field expressions support arithmetic (+, -, *, /, **), unary negation,
numeric literals, references to header_values or previously computed fields,
and math functions: radians, degrees, arctan, arctan2, sin, cos, sqrt, abs,
log.
"""

import functools
import json
import math
import pathlib
import sys
from dataclasses import dataclass

import numpy as np
import simpleeval
from fabio.openimage import FabioImage


class MissingHeaderError(Exception):
    pass


class InvalidHeaderError(Exception):
    pass


@dataclass
class HeaderValueSpec:
    header: str
    index: int


@dataclass
class InstrumentConfig:
    name: str
    file_extension: str
    header_values: dict[str, HeaderValueSpec]
    fields: dict[str, str]
    delimiter: str | None = None


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


_REQUIRED_FIELDS = frozenset(
    {
        "beam_position_x",
        "beam_position_y",
        "chi_degrees",
        "phi_degrees",
        "omega_degrees",
        "detector_distance_mm",
        "wavelength_a",
        "pixel_mm",
        "theta_pixel_rad",
    }
)


# ---------------------------------------------------------------------------
# Expression evaluator (backed by simpleeval)
# ---------------------------------------------------------------------------


def safe_eval(expression: str, variables: dict[str, float]) -> float:
    """Evaluate a math expression safely using simpleeval.

    Supports arithmetic, variable references, shorthand math functions
    (radians, arctan, sin, cos, …), and the full numpy namespace via ``np``
    (e.g. ``np.radians(x)``, ``np.arctan2(a, b)``).
    """
    evaluator = simpleeval.EvalWithCompoundTypes(
        names={
            **variables,
            "np": simpleeval.ModuleWrapper(np),
            "math": simpleeval.ModuleWrapper(math),
        },
        functions={},
    )
    return evaluator.eval(expression)


# ---------------------------------------------------------------------------
# Header helpers
# ---------------------------------------------------------------------------


def _float_header_at_index(
    headers: dict[str, str], header: str, index: int, delimiter: str | None = None
) -> float:
    str_header = headers.get(header)
    if str_header is None:
        raise MissingHeaderError(f"Missing header: {header}")
    split = str_header.split(delimiter)
    try:
        value = split[index]
    except IndexError:
        raise InvalidHeaderError(f"Invalid header value: {header}: {str_header}")
    try:
        return float(value)
    except ValueError:
        raise InvalidHeaderError(f"Invalid header value: {header}: {value}")


# ---------------------------------------------------------------------------
# Instrument loading
# ---------------------------------------------------------------------------


def _get_instruments_dir() -> pathlib.Path:
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return pathlib.Path(base) / "rsstitcher" / "instruments"
    return pathlib.Path(__file__).parent / "instruments"


def load_instrument(path: str | pathlib.Path) -> InstrumentConfig:
    """Load an instrument config from a JSON file."""
    with open(path) as f:
        data = json.load(f)

    missing = _REQUIRED_FIELDS - set(data.get("fields", {}).keys())
    if missing:
        raise ValueError(
            f"Instrument config {path} missing required fields: {', '.join(sorted(missing))}"
        )

    header_values = {
        name: HeaderValueSpec(header=spec["header"], index=spec["index"])
        for name, spec in data["header_values"].items()
    }

    return InstrumentConfig(
        name=data["name"],
        file_extension=data["file_extension"],
        header_values=header_values,
        fields=data["fields"],
        delimiter=data.get("delimiter"),
    )


@functools.lru_cache(maxsize=1)
def load_builtin_instruments() -> tuple[InstrumentConfig, ...]:
    """Load all built-in instrument configs from the instruments/ directory."""
    instruments_dir = _get_instruments_dir()
    configs = []
    for path in sorted(instruments_dir.glob("*.json")):
        configs.append(load_instrument(path))
    return tuple(configs)


def get_instrument(name: str) -> InstrumentConfig:
    """Look up a built-in instrument by name or file extension.

    Matches case-insensitively against both InstrumentConfig.name and
    InstrumentConfig.file_extension.
    """
    key = name.lower()
    for inst in load_builtin_instruments():
        if inst.name.lower() == key or inst.file_extension.lower() == key:
            return inst
    available = ", ".join(
        f"{i.name} ({i.file_extension})" for i in load_builtin_instruments()
    )
    raise ValueError(f"Unknown instrument: {name!r}. Available: {available}")


def resolve_instrument(value: str) -> list[InstrumentConfig] | None:
    """Resolve a CLI ``--instrument`` value.

    Returns:
        None          if *value* is ``"auto"`` (use default auto-detection).
        [single]      if *value* names a built-in instrument (match only that).
        [single]      if *value* is a path to a JSON file (custom instrument).
    """
    if value.lower() == "auto":
        return None

    # Try as a file path first (custom instrument)
    path = pathlib.Path(value)
    if path.is_file():
        return [load_instrument(path)]

    # Try as a built-in name / extension
    return [get_instrument(value)]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def parse_with_instrument(instrument: InstrumentConfig, obj: FabioImage) -> Image:
    """Parse a fabio image using a declarative instrument config.

    Extracts header values, then evaluates field expressions in order.
    Each field expression can reference header values and previously computed
    fields.
    """
    variables: dict[str, float] = {}

    for name, spec in instrument.header_values.items():
        variables[name] = _float_header_at_index(
            obj.header, spec.header, spec.index, instrument.delimiter
        )

    for field_name, expression in instrument.fields.items():
        value = safe_eval(expression, variables)
        variables[field_name] = value

    return Image(
        data_size=obj.shape,
        beam_position_x=variables["beam_position_x"],
        beam_position_y=variables["beam_position_y"],
        chi_degrees=variables["chi_degrees"],
        phi_degrees=variables["phi_degrees"],
        omega_degrees=variables["omega_degrees"],
        detector_distance_mm=variables["detector_distance_mm"],
        wavelength_a=variables["wavelength_a"],
        pixel_mm=variables["pixel_mm"],
        theta_pixel_rad=variables["theta_pixel_rad"],
    )
