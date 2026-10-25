"""Console entry point for the installed FoxMCP distribution."""

import os
from pathlib import Path

from .server import run


def main() -> None:
    """Use bundled examples unless configured, then start the existing server."""
    examples = Path(__file__).with_name("examples")
    if examples.is_dir():
        os.environ.setdefault("FOXMCP_EXT_SCRIPTS", str(examples))
    run()
