"""Firefox profile names come from metadata, never directory-name guesses."""

import json
from contextlib import contextmanager, nullcontext
import subprocess
import sys
from pathlib import Path
import sqlite3

import pytest

from server.profile_names import FirefoxProfileNames, firefox_roots

UUID = "3f9a6b34-5964-4e75-8ab4-9b84b8d41d20"
ORIGIN = "moz-extension://" + UUID


def register(root, name="Work", directory="Profiles/test", extension_uuid=UUID):
    profile = root / directory
    profile.mkdir(parents=True, exist_ok=True)
    ini = root / "profiles.ini"
    section = len(ini.read_text().split("[Profile")) if ini.exists() else 0
    with ini.open("a", encoding="utf-8") as stream:
        stream.write(f"[Profile{section}]\nName={name}\nIsRelative=1\nPath={directory}\n\n")
    mapping = json.dumps({"foxmcp@codemud.org": extension_uuid})
    (profile / "prefs.js").write_text(
        'user_pref("extensions.webextensions.uuids", ' + json.dumps(mapping) + ');\n',
        encoding="utf-8")
    return profile


def test_legacy_profile_name_and_unknown_origin(tmp_path):
    register(tmp_path, "Рабочий")
    resolver = FirefoxProfileNames([tmp_path])
    result = resolver.resolve([ORIGIN, "moz-extension://unknown"])
    assert result[ORIGIN] == {"name": "Рабочий", "name_error": None}
    assert result["moz-extension://unknown"]["name"] is None
    assert result["moz-extension://unknown"]["name_error"]


def test_group_only_name_refreshes_after_rename(tmp_path):
    register(tmp_path, "dev-edition-default")
    (tmp_path / "profiles.ini").unlink()
    group = tmp_path / "Profile Groups"
    group.mkdir()
    database = group / "group.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE Profiles (id INTEGER, path TEXT, name TEXT)")
        connection.execute("INSERT INTO Profiles VALUES (1, ?, ?)", ("Profiles/test", "Personal"))
        connection.commit()
        resolver = FirefoxProfileNames([tmp_path])
        assert resolver.resolve([ORIGIN])[ORIGIN]["name"] == "Personal"
        connection.execute("UPDATE Profiles SET name = ?", ("Renamed",))
        connection.commit()
        assert resolver.resolve([ORIGIN])[ORIGIN]["name"] == "Renamed"


def test_copied_profile_with_same_origin_is_explicitly_ambiguous(tmp_path):
    register(tmp_path, "One", "Profiles/one")
    register(tmp_path, "Two", "Profiles/two")
    result = FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]
    assert result["name"] is None
    assert "Ambiguous" in result["name_error"]


def test_unreadable_group_does_not_hide_registered_name(tmp_path):
    register(tmp_path, "stale-internal-name")
    ini = tmp_path / "profiles.ini"
    ini.write_text(ini.read_text() + "StoreID=group\n", encoding="utf-8")
    group = tmp_path / "Profile Groups"
    group.mkdir()
    (group / "group.sqlite").write_bytes(b"invalid database")
    result = FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]
    assert result == {"name": "stale-internal-name", "name_error": None}


def test_corrupt_metadata_does_not_hide_other_profile(tmp_path):
    good, bad = tmp_path / "good", tmp_path / "bad"
    register(good)
    register(bad, "Bad", extension_uuid="unknown")
    (bad / "profiles.ini").write_text("not an ini file")
    result = FirefoxProfileNames([good, bad]).resolve([ORIGIN])
    assert result[ORIGIN]["name"] == "Work"


def test_prefs_are_parsed_as_data_without_execution(tmp_path):
    profile = register(tmp_path)
    (profile / "prefs.js").write_text('user_pref("extensions.webextensions.uuids", not_json());')
    assert FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]["name"] is None


def test_malformed_origin_does_not_hide_other_profiles(tmp_path):
    register(tmp_path)
    result = FirefoxProfileNames([tmp_path]).resolve(["moz-extension://[invalid", ORIGIN])
    assert result["moz-extension://[invalid"]["name"] is None
    assert result[ORIGIN]["name"] == "Work"


@pytest.mark.parametrize("platform", ["win32", "linux", "darwin"])
def test_platform_locations(monkeypatch, tmp_path, platform):
    monkeypatch.setattr("server.profile_names.sys.platform", platform)
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    roots = firefox_roots()
    if platform == "win32":
        assert roots == [tmp_path / "roaming/Mozilla/Firefox"]
    elif platform == "linux":
        assert tmp_path / "xdg/mozilla/firefox" in roots
        assert Path.home() / ".mozilla/firefox" in roots
    else:
        assert roots == [Path.home() / "Library/Application Support/Firefox"]


def test_registered_name_wins_over_group_label_and_preserves_case(tmp_path):
    register(tmp_path, "Mozilla")
    ini = tmp_path / "profiles.ini"
    ini.write_text(ini.read_text() + "StoreID=group\n")
    group = tmp_path / "Profile Groups"
    group.mkdir()
    with sqlite3.connect(group / "group.sqlite") as connection:
        connection.execute("CREATE TABLE Profiles (path TEXT, name TEXT)")
        connection.execute("INSERT INTO Profiles VALUES (?, ?)",
                           ("Profiles/test", "Original profile"))
    resolver = FirefoxProfileNames([tmp_path])
    assert resolver.resolve([ORIGIN])[ORIGIN] == {"name": "Mozilla", "name_error": None}
    ini.write_text(ini.read_text().replace("Name=Mozilla", "Name=default"))
    assert resolver.resolve([ORIGIN])[ORIGIN]["name"] == "default"


@contextmanager
def held_profile_lock(profile, start=0):
    lock = profile / ".parentlock"
    lock.touch()
    script = """
import fcntl, sys
with open(sys.argv[1], 'r+') as stream:
    fcntl.lockf(stream, fcntl.LOCK_EX, 0, int(sys.argv[2]))
    print('locked', flush=True)
    sys.stdin.read()
"""
    with subprocess.Popen([sys.executable, "-c", script, str(lock), str(start)],
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True) as child:
        try:
            assert child.stdout.readline().strip() == "locked"
            yield
        finally:
            child.stdin.close()
            child.wait(timeout=5)


@pytest.mark.skipif(sys.platform != "linux", reason="Linux profile lock discovery")
def test_running_profile_disambiguates_stale_copy_in_another_root(tmp_path):
    native, snap = tmp_path / "native", tmp_path / "snap"
    active = register(native, "default")
    stale = register(snap, "Old copy")
    (stale / "lock").symlink_to("192.0.2.1:+12345")
    with held_profile_lock(active):
        for roots in ([native, snap], [snap, native]):
            assert FirefoxProfileNames(roots).resolve([ORIGIN])[ORIGIN] == {
                "name": "default", "name_error": None}


@pytest.mark.skipif(sys.platform != "linux", reason="Linux profile lock discovery")
def test_two_running_copies_remain_ambiguous(tmp_path):
    one = register(tmp_path, "One", "Profiles/one")
    two = register(tmp_path, "Two", "Profiles/two")
    with held_profile_lock(one), held_profile_lock(two):
        result = FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]
        assert result["name"] is None and "Ambiguous" in result["name_error"]


@pytest.mark.skipif(sys.platform != "linux", reason="Linux profile lock discovery")
def test_lock_file_without_held_lock_does_not_disambiguate(tmp_path):
    one = register(tmp_path, "One", "Profiles/one")
    register(tmp_path, "Two", "Profiles/two")
    (one / ".parentlock").touch()
    with held_profile_lock(one, start=1):
        assert FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]["name"] is None


@pytest.mark.parametrize("unavailable", ["proc", "candidate", "platform"])
def test_unavailable_lock_metadata_keeps_duplicate_ambiguous(tmp_path, monkeypatch, unavailable):
    one = register(tmp_path, "One", "Profiles/one")
    two = register(tmp_path, "Two", "Profiles/two")
    held = held_profile_lock(two) if sys.platform == "linux" else nullcontext()
    if unavailable == "platform":
        monkeypatch.setattr("server.profile_names.sys.platform", "darwin")
    elif unavailable == "proc":
        original = Path.read_text
        def read_text(path, *args, **kwargs):
            if path == Path("/proc/locks"):
                raise PermissionError("hidden locks")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", read_text)
    else:
        original = Path.stat
        def stat(path, *args, **kwargs):
            if path == one / ".parentlock":
                raise PermissionError("hidden lock file")
            return original(path, *args, **kwargs)
        monkeypatch.setattr(Path, "stat", stat)
    with held:
        assert FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]["name"] is None
