#!/bin/bash
#
# Print one version's CHANGELOG section, for use as the GitHub release notes.
#
# Takes everything under the "## [1.2.0] - date" heading up to the next "## ["
# heading. Exits non-zero when the version has no section, so the release
# workflow stops rather than publishing a release with empty notes.
#
# Usage: scripts/release-notes.sh 1.2.0     (no leading "v")

set -euo pipefail

version="${1:-}"
if [ -z "$version" ]; then
    echo "usage: $0 <version>   e.g. $0 1.2.0" >&2
    exit 2
fi

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# The awk prints the body of the wanted section; sed drops the blank lines that
# follow the heading. Trailing blank lines need no handling — $(...) strips them.
notes="$(awk -v want="$version" '
    /^## \[/ {
        # Headings look like "## [1.2.0] - 2026-08-12". Any heading ends the
        # section being printed; the wanted one starts it.
        inside = 0
        if (match($0, /\[[^]]+\]/) && substr($0, RSTART + 1, RLENGTH - 2) == want) {
            inside = 1
            next
        }
    }
    inside { print }
' "$root/CHANGELOG.md" | sed -e '/./,$!d')"

if [ -z "$notes" ]; then
    echo "CHANGELOG.md has no '## [$version]' section." >&2
    echo "Rename the '## [Unreleased]' heading to '## [$version] - $(date +%F)'." >&2
    exit 1
fi

printf '%s\n' "$notes"
