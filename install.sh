#!/usr/bin/env bash
# Symlinks cs and ccps into a directory on your PATH.
# Symlinks rather than copies, so `git pull` updates the installed commands.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${1:-$HOME/.local/bin}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required but not on PATH." >&2
  exit 1
fi

mkdir -p "$DEST"
for cmd in cs ccps; do
  ln -sf "$REPO/bin/$cmd" "$DEST/$cmd"
  echo "linked $DEST/$cmd -> $REPO/bin/$cmd"
done

echo
case ":$PATH:" in
  *":$DEST:"*)
    echo "Ready. Run: cs" ;;
  *)
    echo "$DEST is not on your PATH. Add this to your shell config:"
    echo
    echo "  export PATH=\"$DEST:\$PATH\""
    ;;
esac

if ! command -v fzf >/dev/null 2>&1; then
  echo
  echo "Note: fzf is not installed, so 'cs -i' will not work."
  echo "Everything else runs without it. Install with: brew install fzf"
fi
