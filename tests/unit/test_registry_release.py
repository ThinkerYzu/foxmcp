"""Reject release metadata drift before any registry publication."""

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release_tree(tmp_path):
    files = (
        "scripts/check-version.sh", "extension/manifest.json", "package.json",
        "pyproject.toml", "server/version.py", "scripts/install-from-github.sh",
        "scripts/install-from-github.ps1", "README.md", "CHANGELOG.md", "server.json",
    )
    for relative in files:
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, target)
    return tmp_path


def check_version(root):
    version = json.loads((ROOT / "package.json").read_text())["version"]
    return subprocess.run(
        ["bash", str(root / "scripts/check-version.sh"), version],
        capture_output=True, text=True,
    )


@pytest.mark.parametrize("field", ["version", "package-version", "name"])
def test_independent_registry_fields_must_agree(release_tree, field):
    assert check_version(release_tree).returncode == 0
    path = release_tree / "server.json"
    metadata = json.loads(path.read_text())
    if field == "version":
        metadata["version"] = "0.0.0"
    elif field == "package-version":
        metadata["packages"][0]["version"] = "0.0.0"
    else:
        metadata["name"] = "io.github.SomeoneElse/foxmcp"
    path.write_text(json.dumps(metadata))
    result = check_version(release_tree)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "MISMATCH" in result.stdout


@pytest.mark.parametrize("replacement", ["", "wrong-name", "duplicate", "punctuation"])
def test_ownership_marker_must_match_exactly_once(release_tree, replacement):
    path = release_tree / "README.md"
    name = json.loads((release_tree / "server.json").read_text())["name"]
    marker = f"<!-- mcp-name: {name} -->"
    alternatives = {
        "": "",
        "wrong-name": "<!-- mcp-name: io.github.SomeoneElse/foxmcp -->",
        "duplicate": marker + "\n" + marker,
        "punctuation": f"<!-- mcp-name: {name}. -->",
    }
    assert marker in path.read_text()
    path.write_text(path.read_text().replace(marker, alternatives[replacement]))
    result = check_version(release_tree)
    assert result.returncode == 1, result.stdout + result.stderr
    assert "README.md mcp-name" in result.stdout


@pytest.mark.parametrize("contents", [None, "{broken", '{"packages": []}'])
def test_missing_or_malformed_registry_metadata_blocks_release(release_tree, contents):
    path = release_tree / "server.json"
    if contents is None:
        path.unlink()
    else:
        path.write_text(contents)
    assert check_version(release_tree).returncode == 1


def test_corrupt_publisher_download_is_never_installed(tmp_path):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    curl = fake_bin / "curl"
    curl.write_text(
        '#!/bin/bash\n'
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = --output ]; then printf tampered > "$2"; exit; fi\n'
        '  shift\n'
        'done\nexit 1\n'
    )
    curl.chmod(0o755)
    destination = tmp_path / "installed"
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/install-mcp-publisher.sh"), str(destination)],
        env={**os.environ, "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"]},
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "FAILED" in result.stdout
    assert not (destination / "mcp-publisher").exists()
