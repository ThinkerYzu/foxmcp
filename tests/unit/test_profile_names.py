"""Firefox profile names come from metadata, never directory-name guesses."""

import json
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


def test_new_manager_overrides_legacy_name_and_refreshes_after_rename(tmp_path):
    register(tmp_path, "dev-edition-default")
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


def test_unreadable_new_manager_does_not_report_stale_legacy_name(tmp_path):
    register(tmp_path, "stale-internal-name")
    ini = tmp_path / "profiles.ini"
    ini.write_text(ini.read_text() + "StoreID=group\n", encoding="utf-8")
    group = tmp_path / "Profile Groups"
    group.mkdir()
    (group / "group.sqlite").write_bytes(b"invalid database")
    result = FirefoxProfileNames([tmp_path]).resolve([ORIGIN])[ORIGIN]
    assert result["name"] is None
    assert "name unavailable" in result["name_error"]
    assert "DatabaseError" in result["name_error"]


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
