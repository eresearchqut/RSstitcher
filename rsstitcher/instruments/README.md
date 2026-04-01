# Custom Instrument Configs

RSstitcher uses declarative JSON files to describe how detector parameters are extracted from image file headers. Built-in configs are provided for [Bruker (.gfrm)](bruker_gfrm.json) and [Rigaku (.img)](rigaku_img.json) detectors. You can add support for any detector by writing your own config file, as long as the file format is [supported by fabio](https://github.com/silx-kit/fabio). RSstitcher relies on fabio to read image data and headers, so your detector's file format must be one that fabio can open.

## Config file structure

```json
{
    "name": "My Detector",
    "file_extension": "ext",
    "delimiter": null,
    "header_values": {
        "var_name": {"header": "HEADER_KEY", "index": 0}
    },
    "fields": {
        "beam_position_x": "var_name * 2",
        "beam_position_y": "other_var",
        ...
    }
}
```

### Top-level keys

| Key | Required | Description |
|---|---|---|
| `name` | Yes | Human-readable name for the instrument. |
| `file_extension` | Yes | File extension to match (without the dot), e.g. `"gfrm"`, `"img"`. |
| `delimiter` | No | Delimiter used to split header values. Defaults to `null` (split on whitespace). Set to `","` for comma-separated headers, `"\t"` for tab-separated, etc. |
| `header_values` | Yes | Named values extracted from the [fabio](https://github.com/silx-kit/fabio) header dictionary. Each entry specifies a `header` key and an `index` into the split values. Negative indices work (e.g. `-1` for the last value). |
| `fields` | Yes | Expressions that compute the final detector parameters. Evaluated in order, so later fields can reference earlier ones. |

### Required fields

Every config must define all of the following in `fields`:

| Field | Unit | Description |
|---|---|---|
| `beam_position_x` | pixels | Horizontal beam centre on the detector. |
| `beam_position_y` | pixels | Vertical beam centre on the detector. |
| `chi_degrees` | degrees | Chi goniometer angle. |
| `phi_degrees` | degrees | Phi goniometer angle. |
| `omega_degrees` | degrees | Omega goniometer angle. |
| `detector_distance_mm` | mm | Sample-to-detector distance. |
| `wavelength_a` | angstroms | X-ray wavelength. |
| `pixel_mm` | mm | Physical size of one pixel. |
| `theta_pixel_rad` | radians | Angular size of one pixel. |

### Expressions

Field expressions are evaluated with [simpleeval](https://github.com/danthedeckie/simpleeval) and support:

- Arithmetic: `+`, `-`, `*`, `/`, `**`
- Parentheses: `(a + b) * c`
- Numeric literals: `0.075`, `-1`, `180`
- References to `header_values` names and previously computed fields
- The full `np` (numpy) namespace: `np.radians(x)`, `np.arctan2(a, b)`, `np.sqrt(x)`, etc.
- The full `math` namespace: `math.pi`, `math.log(x)`, etc.

Fields are evaluated top-to-bottom, so ordering matters when one field depends on another.

## Examples

See the built-in configs for complete working examples:

- [bruker_gfrm.json](bruker_gfrm.json) — Bruker GFRM detector
- [rigaku_img.json](rigaku_img.json) — Rigaku IMG detector

## Usage

### CLI

```bash
# Use a specific built-in instrument
rsstitcher data/ --instrument gfrm

# Use a custom instrument config
rsstitcher data/ --instrument-path my_detector.json
```

### Web UI

Select **Custom...** from the Instrument dropdown and upload your JSON file.

## Inspecting headers

To see what headers are available in your files, you can use fabio in Python:

```python
import fabio
img = fabio.open("your_file.ext")
for key, value in img.header.items():
    print(f"{key}: {value}")
```

This will show all header keys and their values, which you can then reference in `header_values`.

## Contributing

If you've written a config for your instrument, please consider [opening a pull request](https://github.com/eresearchqut/RSstitcher/pulls) to add it to the built-in configs so others with the same detector can use it out of the box. Just drop your JSON file into this directory.
