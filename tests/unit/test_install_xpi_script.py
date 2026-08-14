"""
Tests for scripts/install-xpi.sh, the documented way to install the extension

README's Method 3 tells users to run this script against their Firefox profile,
and until now nothing checked that it works: the suite installs the XPI through
firefox_test_utils.py, which is a separate implementation of the same idea. A
break in the script would have reached users without failing a single test.

These tests drive the script against a directory that looks like a profile. They
do not start Firefox — whether Firefox then *loads* the extension depends on the
channel, since release and beta enforce signing regardless of the preference the
script sets.
"""

import subprocess
from pathlib import Path

import pytest

import test_imports  # Automatic path setup

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / 'scripts' / 'install-xpi.sh'
BUILT_XPI = REPO_ROOT / 'dist' / 'packages' / 'foxmcp@codemud.org.xpi'
EXTENSION_ID = 'foxmcp@codemud.org'
SIGNATURES_PREF = 'user_pref("xpinstall.signatures.required", false);'


@pytest.fixture
def profile(tmp_path):
    """A directory that install-xpi.sh will accept as a Firefox profile

    The script's only test for a real profile is that prefs.js exists, so that
    is what makes this one valid.
    """
    profile_dir = tmp_path / 'profile'
    profile_dir.mkdir()
    (profile_dir / 'prefs.js').write_text('// placeholder\n')
    return profile_dir


def run_installer(profile_dir):
    """Run install-xpi.sh against a profile and return the completed process

    Skips rather than fails when the XPI has not been built: `make test` runs
    `make package` first, so under the documented command it is always there,
    and CI fails the build if any test skips.
    """
    if not BUILT_XPI.exists():
        pytest.skip(f"{BUILT_XPI} not built; run `make package` first")

    return subprocess.run(
        [str(INSTALL_SCRIPT), str(profile_dir)],
        capture_output=True, text=True, timeout=30
    )


def test_installs_the_xpi_and_sets_the_preference(profile):
    """A fresh profile gets the extension and the unsigned-extension preference"""
    result = run_installer(profile)

    assert result.returncode == 0, result.stderr
    installed = profile / 'extensions' / f'{EXTENSION_ID}.xpi'
    assert installed.exists()
    assert installed.read_bytes() == BUILT_XPI.read_bytes()
    assert SIGNATURES_PREF in (profile / 'user.js').read_text()


def test_reinstalling_replaces_rather_than_accumulates(profile):
    """Running it twice leaves one extension file and one copy of the preference

    An installed extension is a single file named for the extension id, so a
    second run has to overwrite it; and user.js is appended to, so the
    preference is the part that could pile up.
    """
    run_installer(profile)
    stale = profile / 'extensions' / f'{EXTENSION_ID}.xpi'
    stale.write_bytes(b'not the extension')

    result = run_installer(profile)

    assert result.returncode == 0, result.stderr
    assert stale.read_bytes() == BUILT_XPI.read_bytes()
    assert len(list((profile / 'extensions').iterdir())) == 1
    assert (profile / 'user.js').read_text().count(SIGNATURES_PREF) == 1


def test_a_preference_set_the_other_way_is_corrected(profile):
    """user.js already requiring signatures is rewritten, not left alone

    A profile that has been used will often carry this preference already, and
    leaving it at true installs an extension Firefox will then refuse to load.
    """
    (profile / 'user.js').write_text(
        'user_pref("xpinstall.signatures.required", true);\n'
    )

    result = run_installer(profile)

    assert result.returncode == 0, result.stderr
    contents = (profile / 'user.js').read_text()
    assert SIGNATURES_PREF in contents
    assert 'required", true' not in contents


def test_a_directory_that_is_not_a_profile_is_refused(tmp_path):
    """Pointing it at the wrong directory fails instead of writing into it

    The path comes from about:profiles by hand, so a mistyped one is the likely
    error, and a silent install into an unrelated directory is the bad outcome.
    """
    not_a_profile = tmp_path / 'somewhere-else'
    not_a_profile.mkdir()

    result = run_installer(not_a_profile)

    assert result.returncode != 0
    assert 'prefs.js not found' in result.stderr
    assert not (not_a_profile / 'extensions').exists()
