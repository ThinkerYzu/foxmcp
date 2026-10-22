#!/usr/bin/env python3
"""Validate Python distribution contents, permissions, dependencies and version."""

import argparse
from email.parser import BytesParser
import ast
import json
from pathlib import Path
import tarfile
import zipfile

from packaging.requirements import Requirement


def check(directory: Path, root: Path) -> None:
    """Check the final archives against source, including executable examples."""
    wheels = list(directory.glob("*.whl"))
    sources = list(directory.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Expected one wheel and one sdist"
    version = json.loads((root / "extension/manifest.json").read_text())["version"]
    dependencies = {
        Requirement(line.strip())
        for line in (root / "server/requirements.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }
    modules = {f"foxmcp/{p.name}" for p in (root / "server").glob("*.py")}
    examples = {p.name: p for p in (root / "predefined-ex").iterdir() if p.suffix in (".py", ".sh")}
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = set(wheel.namelist())
        metadata = BytesParser().parsebytes(wheel.read(f"foxmcp-{version}.dist-info/METADATA"))
        assert metadata["Name"] == "foxmcp"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.10"
        assert {Requirement(r) for r in metadata.get_all("Requires-Dist", [])} == dependencies
        assert modules <= names, modules - names
        version_tree = ast.parse(wheel.read("foxmcp/version.py"))
        constants = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in version_tree.body if isinstance(node, ast.Assign)
        }
        assert constants["VERSION"] == version, "Server announcement version differs from metadata"
        assert all(name.startswith(("foxmcp/", f"foxmcp-{version}.dist-info/")) for name in names)
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        assert {
            name.removeprefix("foxmcp/examples/")
            for name in names
            if name.startswith("foxmcp/examples/")
        } == examples.keys()
        for name, path in examples.items():
            info = wheel.getinfo(f"foxmcp/examples/{name}")
            assert (info.external_attr >> 16) & 0o111, f"Not executable: {name}"
            assert wheel.read(info) == path.read_bytes(), name
        entry_points = wheel.read(f"foxmcp-{version}.dist-info/entry_points.txt").decode()
        assert "foxmcp = foxmcp.cli:main" in entry_points, entry_points
        assert f"foxmcp-{version}.dist-info/licenses/LICENSE" in names
    with tarfile.open(sources[0]) as source:
        prefix = f"foxmcp-{version}/"
        names = {member.name.removeprefix(prefix) for member in source.getmembers()}
        required = {"pyproject.toml", "README.md", "LICENSE", "server/requirements.txt"}
        required.update(f"server/{p.name}" for p in (root / "server").glob("*.py"))
        required.update(f"predefined-ex/{name}" for name in examples)
        assert required <= names, required - names
        assert not any("__pycache__" in name or name.endswith(".pyc") for name in names)
        for name in examples:
            assert source.getmember(f"{prefix}predefined-ex/{name}").mode & 0o111, name
    print(f"Python distributions checked: foxmcp {version}, {len(examples)} executable examples")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    check(args.directory, Path(__file__).resolve().parents[1])
