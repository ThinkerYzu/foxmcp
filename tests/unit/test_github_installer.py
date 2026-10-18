"""Run release downloads against an isolated local HTTP fixture."""

import hashlib
import io
import subprocess
import threading
import zipfile
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

import test_imports

INSTALLER = Path(__file__).resolve().parents[2] / "scripts/install-from-github.sh"


def archive(name, content):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as output:
        output.writestr(name, content)
    return data.getvalue()


@pytest.fixture
def release(tmp_path):
    assets = tmp_path / "assets"
    assets.mkdir()
    files = {"foxmcp-server.zip": archive("server-package/server.py", "# server\n"),
             "foxmcp@codemud.org.xpi": archive("manifest.json", "{}")}
    for name, body in files.items():
        (assets / name).write_bytes(body)
    (assets / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256(body).hexdigest()}  {name}\n" for name, body in files.items()))
    (assets / "scripts").mkdir()
    (assets / "scripts/install-xpi.sh").write_text("#!/bin/bash\nexit 0\n")
    (assets / "predefined-ex").mkdir()
    for name in ("gcal-cal-event-js.sh", "gcal-daily-events-js.sh", "gcal-monthly-events-js.sh",
                 "dom-summarize.sh", "youtube-play-pause.sh", "set-file-input.py"):
        (assets / "predefined-ex" / name).write_text("# example\n")
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(assets)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    install = tmp_path / "install"
    install.mkdir()
    yield assets, install, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()
    thread.join()


def download(release):
    _, install, url = release
    return subprocess.run(["bash", "-c", 'source "$1"; GITHUB_RELEASE_URL="$2"; '
                           'GITHUB_SOURCE_URL="$2"; download_release; extract_and_setup',
                           "installer-test", str(INSTALLER), url],
                          cwd=install, text=True, capture_output=True, timeout=30)


def test_installs_verified_archives_and_upload_example(release):
    result = download(release)
    assert result.returncode == 0, result.stdout + result.stderr
    assert (release[1] / "server/server.py").is_file()
    helper = release[1] / "predefined-scripts/set-file-input.py"
    assert helper.is_file()
    # Unattended retries must refuse to overwrite an existing installation.
    refused = subprocess.run(["bash", str(INSTALLER), "--non-interactive"],
                             cwd=release[1], text=True, capture_output=True, timeout=10)
    assert refused.returncode != 0
    assert "requires an empty directory" in refused.stdout + refused.stderr
    assert helper.read_text() == "# example\n"


@pytest.mark.parametrize("asset", ["foxmcp-server.zip", "foxmcp@codemud.org.xpi",
                                   "SHA256SUMS", "scripts/install-xpi.sh"])
def test_missing_required_download_fails(release, asset):
    (release[0] / asset).unlink()
    result = download(release)
    assert result.returncode != 0
    assert not (release[1] / "server").exists()


def test_checksum_mismatch_fails_before_extraction(release):
    (release[0] / "foxmcp-server.zip").write_bytes(b"tampered")
    result = download(release)
    assert result.returncode != 0
    assert "checksum verification failed" in result.stdout + result.stderr
    assert not (release[1] / "server").exists()


def test_corrupt_archive_with_matching_checksum_is_rejected(release):
    assets = release[0]
    (assets / "foxmcp-server.zip").write_bytes(b"invalid zip")
    (assets / "SHA256SUMS").write_text("".join(
        f"{hashlib.sha256((assets / name).read_bytes()).hexdigest()}  {name}\n"
        for name in ("foxmcp-server.zip", "foxmcp@codemud.org.xpi")))
    result = download(release)
    assert result.returncode != 0
    assert "Invalid server archive" in result.stdout + result.stderr


@pytest.mark.parametrize("manifest", ["", "0" * 64 + "  ../outside\n"])
def test_incomplete_or_unexpected_checksum_manifest_is_rejected(release, manifest):
    (release[0] / "SHA256SUMS").write_text(manifest)
    result = download(release)
    assert result.returncode != 0
    assert "Invalid SHA256SUMS" in result.stdout + result.stderr
