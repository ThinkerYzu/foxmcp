#!/bin/bash
#
# Fail unless every file that carries the version agrees with the one given.
#
# The version is written out by hand in nine files, so a tag can disagree with
# the manifest and nothing notices until a user installs the result. The release
# workflow runs this first and refuses to build when it fails. Run it yourself
# after bumping, before tagging.
#
# Usage: scripts/check-version.sh 1.2.0     (no leading "v")

set -uo pipefail

version="${1:-}"
if [ -z "$version" ]; then
    echo "usage: $0 <version>   e.g. $0 1.2.0" >&2
    exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" || exit 2
cd "$root" || exit 2

# Dots are wildcards to grep, so 1.2.0 would happily match 1x2x0.
escaped="${version//./\\.}"

failed=0

# Report one file as ok or as a mismatch, and remember that anything failed.
#
# Takes the file, a description of what the file should have said, and the
# extended-regex pattern that has to match somewhere in it. Every file is
# checked even after one fails, so a single run lists everything left to bump.
check() {
    local file="$1" expected="$2" pattern="$3"

    if [ ! -f "$file" ]; then
        printf '  %-32s MISSING\n' "$file"
        failed=1
    elif grep -Eq -- "$pattern" "$file"; then
        printf '  %-32s ok\n' "$file"
    else
        printf '  %-32s MISMATCH - expected %s\n' "$file" "$expected"
        failed=1
    fi
}

echo "Checking that every file says $version:"

check extension/manifest.json \
      "\"version\": \"$version\"" \
      "\"version\"[[:space:]]*:[[:space:]]*\"$escaped\""

check package.json \
      "\"version\": \"$version\"" \
      "\"version\"[[:space:]]*:[[:space:]]*\"$escaped\""

check pyproject.toml \
      "version = \"$version\"" \
      "^version[[:space:]]*=[[:space:]]*\"$escaped\"[[:space:]]*$"

check server/version.py \
      "VERSION = \"$version\"" \
      "^VERSION[[:space:]]*=[[:space:]]*\"$escaped\"[[:space:]]*$"

check scripts/install-from-github.sh \
      "VERSION=\"v$version\"" \
      "^VERSION=\"?v$escaped\"?"

check scripts/install-from-github.ps1 \
      "VERSION = v$version" \
      '^\$script:VERSION[[:space:]]*=[[:space:]]*"v'"$escaped"'"'

check README.md \
      "the download URL to point at v$version" \
      "releases/download/v$escaped/"

check CHANGELOG.md \
      "a '## [$version]' section" \
      "^##[[:space:]]+\[$escaped\]"

# Parse registry metadata instead of matching a version anywhere in the JSON:
# its top-level and package versions must each match the release independently.
# Python 3 is already required to build and run FoxMCP.
if ! python3 - "$version" <<'PY'
import json
import re
import sys
from pathlib import Path

try:
    metadata = json.loads(Path("server.json").read_text())
    expected = sys.argv[1]
    checks = [("server.json version", metadata.get("version") == expected)]
    packages = metadata.get("packages")
    if not isinstance(packages, list) or not packages:
        raise ValueError("server.json must contain packages")
    checks.extend(
        (f"server.json packages[{i}].version", package.get("version") == expected)
        for i, package in enumerate(packages)
    )
    name = metadata.get("name")
    markers = re.findall(
        r"mcp-name:[ \t]*(\S+?)(?=\s|<|-->|$)", Path("README.md").read_text()
    )
    checks.append(("README.md mcp-name", isinstance(name, str) and bool(name)
                   and markers == [name]))
    for label, passed in checks:
        print(f"  {label:<38} {'ok' if passed else 'MISMATCH'}")
    sys.exit(0 if all(passed for _, passed in checks) else 1)
except (OSError, ValueError, AttributeError, TypeError) as exc:
    print(f"  Registry metadata check failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
then
    failed=1
fi

# The README also names the version in prose next to the download URL, which is
# easy to bump halfway. Old versions are legitimate in CHANGELOG.md and
# RELEASES.md, so only the README is swept.
stale="$(grep -Eo 'v[0-9]+\.[0-9]+\.[0-9]+' README.md | sort -u | grep -v "^v$escaped$")"
if [ -n "$stale" ]; then
    echo
    echo "Warning: README.md still mentions $(echo "$stale" | tr '\n' ' ')"
fi

if [ "$failed" -ne 0 ]; then
    echo
    echo "Bump the files above, or tag the version they already carry." >&2
    exit 1
fi

echo "All files agree on $version."
