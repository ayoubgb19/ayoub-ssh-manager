#!/usr/bin/env bash
set -Eeuo pipefail
REPO="ayoubgb19/ayoub-ssh-manager"
BRANCH="main"
BASE="https://raw.githubusercontent.com/$REPO/$BRANCH"
if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root (example: sudo bash install.sh)" >&2
  exit 1
fi
command -v curl >/dev/null 2>&1 || { echo "curl is required. Install it: apt-get update && apt-get install -y curl" >&2; exit 1; }
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT
echo "Fetching Ayoub SSH Manager files from GitHub..."
curl --fail --location --silent --show-error --retry 3 "$BASE/manager.py" -o "$tmpdir/manager.py"
curl --fail --location --silent --show-error --retry 3 "$BASE/setup.sh" -o "$tmpdir/setup.sh"
command -v python3 >/dev/null 2>&1 && python3 -m py_compile "$tmpdir/manager.py"
bash -n "$tmpdir/setup.sh"
echo "Installer will modify VPS services. Review setup.sh before executing on production."
exec bash "$tmpdir/setup.sh" "$tmpdir/manager.py"
