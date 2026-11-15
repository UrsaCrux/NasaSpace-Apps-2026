#!/usr/bin/env bash
# Field Shift launcher (Linux). Double-click or run ./FieldShift.sh
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$HERE/runtime"
# the first time: fix the paths of the bundled runtime for this folder
if [ ! -f "$RUNTIME/.unpacked" ]; then
    echo "Preparing Field Shift (first start, about a minute)..."
    "$RUNTIME/bin/python" "$RUNTIME/bin/conda-unpack" && touch "$RUNTIME/.unpacked" || exit 1
fi
# shellcheck disable=SC1091
source "$RUNTIME/bin/activate"
cd "$HERE/app" || exit 1
exec python -m fieldshift "$@"
