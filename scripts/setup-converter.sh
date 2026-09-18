#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$ROOT/vendor/tei-stylesheets"
REVISION=a65259ebbd5005c4edb3793f714524e1bf6c4c43
if [[ ! -d "$DEST/.git" ]]; then
  git clone https://github.com/petrul/tei-stylesheets.git "$DEST"
fi
if [[ "$(git -C "$DEST" rev-parse HEAD)" != "$REVISION" ]]; then
  git -C "$DEST" fetch origin "$REVISION"
  git -C "$DEST" checkout --detach "$REVISION"
fi
printf 'TEI converter ready: %s\n' "$REVISION"
