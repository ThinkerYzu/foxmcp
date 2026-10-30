"""Resolve connected extensions to Firefox's own profile names, read-only."""

import configparser
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
from urllib.parse import urlsplit


def firefox_roots():
    """Return Firefox metadata locations, including legacy and XDG layouts."""
    home = Path.home()
    if sys.platform == "win32":
        return [Path(os.environ.get("APPDATA", home / "AppData/Roaming")) / "Mozilla/Firefox"]
    if sys.platform == "darwin":
        return [home / "Library/Application Support/Firefox"]
    return [Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")) / "mozilla/firefox",
            home / ".mozilla/firefox",
            home / "snap/firefox/common/.mozilla/firefox",
            home / ".var/app/org.mozilla.firefox/.mozilla/firefox"]


def locked_profile_files():
    """Read whole-file POSIX write locks on Linux without acquiring any locks.

    Return device/inode keys, or None when activity evidence is unavailable.
    A leftover lock symlink or file alone is not evidence of a running Firefox.
    """
    if sys.platform != "linux":
        return None
    try:
        lines = Path("/proc/locks").read_text(encoding="ascii").splitlines()
    except (OSError, ValueError):
        return None
    result = set()
    for line in lines:
        fields = line.split()
        if (len(fields) != 8 or fields[1:4] != ["POSIX", "ADVISORY", "WRITE"]
                or fields[6:] != ["0", "EOF"]):
            continue
        try:
            major, minor, inode = fields[5].split(":")
            result.add((int(major, 16), int(minor, 16), int(inode)))
        except ValueError:
            continue
    return result


class FirefoxProfileNames:
    """Match Origin UUIDs against metadata; never evaluate prefs.js as code."""

    def __init__(self, roots=None):
        self.roots = list(roots) if roots is not None else firefox_roots()

    def resolve(self, origins):
        """Resolve a batch against one fresh snapshot of the on-disk metadata."""
        candidates = {}
        failures = []
        for root in self.roots:
            root = Path(root)
            paths = {}
            try:
                ini = configparser.RawConfigParser()
                ini.read(root / "profiles.ini", encoding="utf-8-sig")
                for section in ini.sections():
                    if section.startswith("Profile") and ini.has_option(section, "Path"):
                        path = Path(ini.get(section, "Path"))
                        if ini.getboolean(section, "IsRelative", fallback=True):
                            path = root / path
                        paths[path.resolve()] = ini.get(section, "Name", fallback=None)
            except (OSError, ValueError, configparser.Error) as error:
                failures.append(type(error).__name__)
            # Group metadata also registers profiles absent from profiles.ini.
            for database in (root / "Profile Groups").glob("*.sqlite"):
                try:
                    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro",
                                                 uri=True, timeout=0.1)) as connection:
                        connection.execute("PRAGMA query_only=ON")
                        for path, name in connection.execute("SELECT path, name FROM Profiles"):
                            path = Path(path)
                            if not path.is_absolute():
                                path = root / path
                            path = path.resolve()
                            if not paths.get(path):
                                paths[path] = name
                except (OSError, ValueError, sqlite3.Error) as error:
                    failures.append(type(error).__name__)
            for path, name in paths.items():
                try:
                    text = (path / "prefs.js").read_text(encoding="utf-8")
                    matches = re.findall(
                        r'^user_pref\("extensions\.webextensions\.uuids",\s*("(?:\\.|[^"\\])*")\);\s*$',
                        text, re.MULTILINE)
                    if not matches:
                        continue
                    mapping = json.loads(json.loads(matches[-1]))
                    extension_uuid = mapping.get("foxmcp@codemud.org")
                    if isinstance(extension_uuid, str):
                        candidates.setdefault(extension_uuid.lower(), {})[path] = name
                except (OSError, ValueError, TypeError, AttributeError) as error:
                    failures.append(type(error).__name__)
        result = {}
        locked_files = None
        checked_locks = False
        for origin in origins:
            try:
                matches = candidates.get(urlsplit(origin).hostname, {})
            except ValueError:
                matches = {}
            if len(matches) > 1:
                if not checked_locks:
                    locked_files = locked_profile_files()
                    checked_locks = True
                if locked_files is not None:
                    try:
                        running = {}
                        for path, name in matches.items():
                            try:
                                info = (path / ".parentlock").stat()
                            except FileNotFoundError:
                                continue
                            key = (os.major(info.st_dev), os.minor(info.st_dev), info.st_ino)
                            if key in locked_files:
                                running[path] = name
                        if len(running) == 1:
                            matches = running
                    except OSError:
                        # An inaccessible candidate might also be running.
                        pass
            if len(matches) == 1 and next(iter(matches.values())):
                result[origin] = {"name": next(iter(matches.values())), "name_error": None}
            else:
                if len(matches) > 1:
                    reason = "Ambiguous Firefox profile metadata"
                elif matches:
                    reason = "Firefox profile name unavailable"
                else:
                    reason = "No matching local Firefox profile metadata"
                if len(matches) <= 1 and failures:
                    reason += ": " + ", ".join(sorted(set(failures)))
                result[origin] = {"name": None, "name_error": reason}
        return result
