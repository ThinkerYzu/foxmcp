#!/bin/bash
# Install the pinned Linux x86-64 publisher used by release jobs.
set -euo pipefail

if [ "$#" -ne 1 ]; then
    echo "usage: $0 <destination-directory>" >&2
    exit 2
fi

version=v1.8.7
sha256=00b21004149a4ce66f0782508ae4a2bce67d1bea395a8da0bd8028159fb59579
archive=mcp-publisher_linux_amd64.tar.gz
url="https://github.com/modelcontextprotocol/registry/releases/download/$version"

mkdir -p "$1"
destination="$(cd "$1" && pwd)"
temporary="$(mktemp -d)"
trap 'rm -rf "$temporary"' EXIT
curl --fail --location --silent --show-error --retry 3 \
    "$url/$archive" --output "$temporary/$archive"
printf '%s  %s\n' "$sha256" "$temporary/$archive" | sha256sum --check --strict
tar -xzf "$temporary/$archive" -C "$temporary" mcp-publisher
install -m 755 "$temporary/mcp-publisher" "$destination/mcp-publisher"
