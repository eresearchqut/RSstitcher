#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEEL_DIR="$SCRIPT_DIR/public/wheels"

echo "Building fabio WASM wheel for Pyodide..."
echo "Output: $WHEEL_DIR"
echo

# Clean previous wheels
rm -f "$WHEEL_DIR"/fabio-*.whl

# Build fabio for WASM via pyodide-build (installed on-demand by uvx)
# --skip-built-in-packages: skip numpy, h5py, lxml, Pillow, etc. that ship with Pyodide
# --skip-dependency hdf5plugin: not a Pyodide built-in but not needed (imports are guarded)
# --no-build-dependencies: don't recurse into transitive deps
uvx --python 3.13 --from 'pyodide-build[resolve]==0.33.0' pyodide build \
    --outdir "$WHEEL_DIR" \
    --skip-built-in-packages \
    --skip-dependency hdf5plugin \
    fabio

# Write manifest so the worker knows the exact filename
WHEEL_FILE=$(basename "$WHEEL_DIR"/fabio-*.whl)
echo "$WHEEL_FILE" > "$WHEEL_DIR/fabio-wheel.txt"

echo
echo "Done. Wheel in $WHEEL_DIR:"
ls -lh "$WHEEL_DIR"/fabio-*.whl
