#!/usr/bin/env bash
#
# Builds the XBRL-flavored conformance suite and packages it for release.
#
# Runs the xbrl_xsdtests generator over the committed XSTS test data and zips
# the generated output directory into build.zip, ready to be uploaded as a
# release asset.

set -euo pipefail

OUT_DIR="output"
ZIP_NAME="build.zip"

# Start from a clean output directory and archive.
rm -rf "$OUT_DIR" "$ZIP_NAME"

# Run the generator against the XSTS test data committed in this repo.
python -m xbrl_xsdtests --data-root . --out "$OUT_DIR"

# Package the generated suite for release.
( cd "$OUT_DIR" && zip -r -X -q "../$ZIP_NAME" . )

echo "Build complete: $ZIP_NAME"
