#!/bin/bash
#
# Fail unless every file that carries the version agrees with the one given.
#
# The version is written out by hand in five places, so a tag can disagree with
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

check scripts/install-from-github.sh \
      "VERSION=\"v$version\"" \
      "^VERSION=\"?v$escaped\"?"

check README.md \
      "the download URL to point at v$version" \
      "releases/download/v$escaped/"

check CHANGELOG.md \
      "a '## [$version]' section" \
      "^##[[:space:]]+\[$escaped\]"

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
