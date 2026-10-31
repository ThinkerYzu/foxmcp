#!/usr/bin/env python3
"""
MCP Tool definitions for FoxMCP server
These tools bridge browser functions through WebSocket to the Firefox extension

Copyright (c) 2024 FoxMCP Project
Licensed under the MIT License - see LICENSE file for details
"""

import asyncio
import inspect
import logging
import uuid
import os
import re
import subprocess
import shutil
import shlex
import sys
import time
import json
import base64
from datetime import datetime
from typing import Dict, Any, Optional, List, TypedDict, Union

from fastmcp import FastMCP
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Longest a single script argument may appear in the log before being cut short.
#
# Arguments carry real content - a Bugzilla comment, a chat message - so the log
# records them: knowing that element-send-message.sh ran without knowing what it
# sent is not an audit trail. The cap keeps one long comment from burying the
# rest of the log, since start.sh writes it to a plain file that only truncates
# when the server restarts.
MAX_LOGGED_ARG_LENGTH = 120


def format_script_args_for_log(args_list):
    """Render predefined-script arguments as a single line for the log

    Long arguments are cut to MAX_LOGGED_ARG_LENGTH with an ellipsis and their
    full length appended, so a truncated entry still says how much was elided.
    Returns "(no arguments)" for an empty list rather than an empty string,
    which would read as missing information in the log.
    """
    if not args_list:
        return "(no arguments)"

    rendered = []
    for arg in args_list:
        if len(arg) > MAX_LOGGED_ARG_LENGTH:
            rendered.append(f"{arg[:MAX_LOGGED_ARG_LENGTH]!r}...[{len(arg)} chars]")
        else:
            rendered.append(repr(arg))
    return ", ".join(rendered)


# Names content_execute_predefined will run; anything else is refused.
SCRIPT_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9._-]+$')


def predefined_script_command(script_path):
    """Choose a native Windows interpreter without evaluating a shell command.

    This belongs here because content_execute_predefined launches the scripts.
    Windows cannot launch .py/.sh files through their shebang like Linux/macOS,
    so it needs an explicit interpreter. The guard leaves POSIX launches alone.
    POSIX keeps its executable/shebang behaviour. On Windows, prefer Git's Bash
    over a bare bash.exe lookup, which can select the WSL launcher instead.
    """
    if sys.platform != 'win32':
        return [script_path]
    extension = os.path.splitext(script_path)[1].lower()
    if extension == '.py':
        # Reuses the server's environment and dependencies
        return [sys.executable, script_path]
    if extension != '.sh':
        return [script_path]

    # Allow a custom Git installation without changing the machine's PATH.
    override = os.environ.get('FOXMCP_BASH')
    if override:
        if not os.path.isabs(override) or not os.path.isfile(override):
            raise ValueError('FOXMCP_BASH must be the absolute path to Git Bash bash.exe')
        return [override, '--', script_path.replace('\\', '/')]

    candidates = []
    git = shutil.which('git')
    if git:
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(git)), 'bin', 'bash.exe'))
    for variable, relative in (
        ('ProgramFiles', 'Git/bin/bash.exe'),
        ('ProgramFiles(x86)', 'Git/bin/bash.exe'),
        ('LOCALAPPDATA', 'Programs/Git/bin/bash.exe'),
    ):
        root = os.environ.get(variable)
        if root:
            candidates.append(os.path.join(root, relative))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return [candidate, '--', script_path.replace('\\', '/')]
    raise ValueError(
        'Shell scripts on Windows require Git Bash. Install Git for Windows '
        'or set FOXMCP_BASH to the absolute path to its bash.exe, then restart FoxMCP.'
    )


def run_predefined_script(command, args_list):
    """Run argv with the quoting required by Git Bash's Windows runtime."""
    argv = command + args_list
    if sys.platform == 'win32' and len(command) == 3 and command[1] == '--':
        # MSYS parses POSIX quotes, not Python's default MS C-runtime escaping.
        # Without this, spaces, quotes, or empty arguments can arrive changed.
        # Quote argv[0] for the Windows launcher, then each MSYS argument.
        # shell=False: no command shell evaluates these user-supplied values.
        argv = f'"{argv[0]}" ' + shlex.join(argv[1:])
    # Keeps the existing output capture and 30-second timeout on every platform.
    return subprocess.run(argv, shell=False, capture_output=True, text=True, timeout=30)

# How many lines from the top of a script read_script_header looks at.
#
# A script's description sits in its header, and a generated script can run to
# tens of kilobytes, so reading the whole file would slow startup for nothing.
SCRIPT_HEADER_LINES = 30

# Longest a script's description or argument summary may be in the tool listing.
MAX_SCRIPT_DESCRIPTION_LENGTH = 200

# Longest each output stream of a failed script may be in the error it returns.
MAX_FAILED_OUTPUT_LENGTH = 2000

# Comment lines that never make a description when a script has no marker.
#
# They say how to call the script, or carry editor and licence boilerplate,
# rather than what the script does. Matched case-insensitively at the start.
NON_DESCRIPTION_PREFIXES = ('copyright', 'spdx-', 'usage:', 'example:', 'arguments:', 'vim:')


def shorten(text, limit):
    """text cut to limit characters, with '...' marking a cut"""
    return text if len(text) <= limit else text[:limit] + '...'


def comment_text(line):
    """The text of a comment line with its #, // or -- prefix removed, or None

    Returns None for a line that is not a comment at all, which is how
    read_script_header knows the header has ended.
    """
    stripped = line.strip()
    for prefix in ('#', '//', '--'):
        if stripped.startswith(prefix):
            return stripped.lstrip(prefix[0]).strip()
    return None


def read_script_header(path):
    """What a predefined script says about itself: (description, args)

    Either may be None. The description comes from a 'foxmcp-description:' line
    and the args from 'foxmcp-args:', found anywhere in the first
    SCRIPT_HEADER_LINES lines whatever the comment syntax. With no description
    marker, the first comment line that describes the script stands in for it;
    args have no stand-in, since a guessed argument list misleads more than a
    missing one. Returns (None, None) for a file that cannot be read.

    The fallback reads only the opening comment block - the shebang, blank lines
    and comments - and skips boilerplate such as Usage: and Copyright lines, so
    a comment inside the code never becomes a description.
    """
    try:
        with open(path, encoding='utf-8', errors='replace') as script:
            lines = [line for _, line in zip(range(SCRIPT_HEADER_LINES), script)]
    except OSError:
        return None, None

    description = args = fallback = None
    in_opening_comments = True
    for index, line in enumerate(lines):
        if 'foxmcp-description:' in line and description is None:
            description = line.split('foxmcp-description:', 1)[1].strip() or None
        elif 'foxmcp-args:' in line and args is None:
            args = line.split('foxmcp-args:', 1)[1].strip() or None
        elif in_opening_comments and fallback is None:
            if (index == 0 and line.startswith('#!')) or not line.strip():
                continue
            text = comment_text(line)
            if text is None:
                in_opening_comments = False
            elif text and '-*-' not in text and not text.lower().startswith(NON_DESCRIPTION_PREFIXES):
                fallback = text

    description = description or fallback
    if description:
        description = shorten(description, MAX_SCRIPT_DESCRIPTION_LENGTH)
    if args:
        args = shorten(args, MAX_SCRIPT_DESCRIPTION_LENGTH)
    return description, args


def describe_predefined_scripts(scripts_dir):
    """The script listing appended to content_execute_predefined's description

    scripts_dir is FOXMCP_EXT_SCRIPTS, or None when it is unset. Lists the files
    the tool would run - executable regular files directly in the directory with
    an allowed name - except dot files, one line each from read_script_header.
    Scripts with nothing to say for themselves share one line of names. When
    there is nothing to list, says why, so an agent does not spend a call to
    find out.

    Read once, when the tool is registered: a script added later runs at once
    but is listed only after the server restarts.
    """
    if not scripts_dir:
        return "No scripts are available: FOXMCP_EXT_SCRIPTS is not set."

    scripts_dir = os.path.abspath(scripts_dir)
    try:
        names = sorted(os.listdir(scripts_dir))
    except OSError as e:
        logger.warning(f"Cannot list predefined scripts in {scripts_dir!r}: {e}")
        return "No scripts are available: the scripts directory cannot be read."

    described = []
    undescribed = []
    for name in names:
        path = os.path.join(scripts_dir, name)
        if (name.startswith('.') or not SCRIPT_NAME_PATTERN.match(name)
                or not os.path.isfile(path) or not os.access(path, os.X_OK)):
            continue
        description, args = read_script_header(path)
        if not description and not args:
            undescribed.append(name)
            continue
        line = f"- {name} {args}" if args else f"- {name}"
        described.append(f"{line}: {description}" if description else line)

    if not described and not undescribed:
        logger.info(f"No runnable predefined scripts in {scripts_dir}")
        return "No scripts are available: the scripts directory has none that can run."

    lines = ["Available scripts:"] + described
    if undescribed:
        label = "Also available, without a description" if described else "Without a description"
        lines.append(f"{label}: {', '.join(undescribed)}")
    listing = "\n".join(lines)

    logger.info(
        f"Listing {len(described) + len(undescribed)} predefined scripts from {scripts_dir} "
        f"({len(undescribed)} without a description) in {len(listing)} characters"
    )
    return listing


def format_failed_script_reply(script_name, returncode, stdout, stderr):
    """The error content_execute_predefined returns when a script exits non-zero

    Carries both output streams, each cut to MAX_FAILED_OUTPUT_LENGTH, and leaves
    out an empty one. stdout matters as much as stderr here: scripts commonly
    print their usage there, and that is what tells an agent how to call the
    script after a wrong guess at its arguments.
    """
    parts = [f"Error: Script '{script_name}' failed with exit code {returncode}."]
    for stream_name, text in (("stdout", stdout), ("stderr", stderr)):
        text = (text or "").strip()
        if text:
            parts.append(f"{stream_name}: {shorten(text, MAX_FAILED_OUTPUT_LENGTH)}")
    return "\n".join(parts)


# Colours Firefox accepts for a tab group.
TAB_GROUP_COLORS = ("blue", "cyan", "grey", "green", "orange", "pink", "purple", "red", "yellow")


def parse_id(value, name):
    """A browser ID given as an int or a numeric string, as a non-negative int

    Raises ValueError naming the argument when the value is not one. A bool is
    refused even though Python counts it as an int, and so is a float, which int()
    would otherwise truncate to some other tab's ID.
    """
    try:
        if isinstance(value, bool) or not isinstance(value, (int, str)):
            raise ValueError
        parsed = int(value)
    except (ValueError, TypeError):
        raise ValueError(f"Invalid {name} '{value}'. Must be a non-negative integer.")
    if parsed < 0:
        raise ValueError(f"Invalid {name} '{value}'. Must be a non-negative integer.")
    return parsed


def parse_tab_ids(tab_ids):
    """The tab IDs a tool's tab_ids argument names, as a non-empty list of ints

    tab_ids is one ID, a list of them, or a JSON string of either; the string form
    is how MCP clients that cannot send arrays pass a list, the same convention
    content_execute_predefined uses for its arguments. Raises ValueError with a
    message fit to return to the client.
    """
    if isinstance(tab_ids, str):
        try:
            tab_ids = json.loads(tab_ids)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid tab_ids '{tab_ids}'. Must be an integer or a JSON list of integers.")

    requested_ids = tab_ids if isinstance(tab_ids, list) else [tab_ids]
    if not requested_ids:
        raise ValueError("tab_ids is empty. Provide at least one tab ID.")
    return [parse_id(tab_id, "tab ID") for tab_id in requested_ids]


def parse_group_properties(title=None, color=None, collapsed=None):
    """The tab group properties a caller gave, keyed as Firefox names them

    Arguments left as None are omitted, so Firefox keeps the group's current value
    for them. An empty title is kept: it clears the title. Raises ValueError on a
    colour Firefox does not offer.
    """
    properties = {}
    if title is not None:
        if not isinstance(title, str):
            raise ValueError("title must be a string")
        properties["title"] = title
    if color is not None:
        if color not in TAB_GROUP_COLORS:
            raise ValueError(f"Invalid color '{color}'. Must be one of: {', '.join(TAB_GROUP_COLORS)}.")
        properties["color"] = color
    if collapsed is not None:
        if not isinstance(collapsed, bool):
            raise ValueError("collapsed must be a boolean")
        properties["collapsed"] = collapsed
    return properties


def validate_cookie_store_id(value):
    """Validate the opaque string without coercion or parsing profile-specific IDs."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("cookie_store_id must be a nonempty string")
    return value


def browser_tool_error(response):
    """Preserve browser error codes and details in public tool diagnostics."""
    if "error" in response:
        return str(response["error"])
    if response.get("type") == "error":
        data = response.get("data", {})
        return f"{data.get('code', 'API_ERROR')}: {data.get('message', 'Browser error')} {json.dumps(data.get('details', {}))}"
    return None


class TabInfo(TypedDict):
    """Type definition for tab information from browser extension"""
    url: str
    id: int
    title: str
    active: bool
    windowId: int
    pinned: bool
    index: int
    cookieStoreId: str

class TabsListResponse(TypedDict):
    """Type definition for tabs.list response from browser extension"""
    tabs: List[TabInfo]
    debug: Dict[str, Any]

class FoxMCPTools:
    """MCP tools that communicate with Firefox extension via WebSocket"""

    # The tool groups a user can turn off, mapped to the method that registers each.
    #
    # Every tool description an MCP client is offered sits in that client's context
    # for the whole session, whether or not it is ever called, so a user who never
    # touches bookmarks pays for them on every request. The keys are the names
    # --disable-tools accepts; docs/configuration.md lists what each group costs.
    #
    # This is also the only route by which a tool gets registered - every tool
    # definition goes through _tool while one of these methods is running - so a
    # new tool added to any _setup_* method below can be disabled with its group,
    # or enabled on its own, without further work.
    TOOL_GROUPS = {
        'profiles': '_setup_profile_tools',
        'windows': '_setup_window_tools',
        'tabs': '_setup_tab_tools',
        'containers': '_setup_container_tools',
        'history': '_setup_history_tools',
        'bookmarks': '_setup_bookmark_tools',
        'navigation': '_setup_navigation_tools',
        'content': '_setup_content_tools',
        'requests': '_setup_request_monitoring_tools',
        'debug': '_setup_debug_tools',
    }

    def __init__(self, websocket_server, disabled_groups=None, enabled_tools=None):
        """Initialize with reference to WebSocket server

        disabled_groups names tool groups to leave unregistered, so their
        descriptions never reach a client's context - see TOOL_GROUPS for the
        names. enabled_tools names individual tools to register anyway, for when
        one tool out of a disabled group is the one that is wanted: disabling
        'tabs' while enabling 'tabs_capture_screenshot' offers the screenshot
        without the nine tab tools around it.

        Raises ValueError on a name that is not a group, or an enabled_tools name
        that is not a tool: a typo that silently registered everything - or that
        silently dropped the one tool that was wanted - would defeat the point of
        the options.
        """
        self.websocket_server = websocket_server
        self.disabled_groups = self._validate_groups(disabled_groups)
        self.enabled_tools = set(enabled_tools or ())

        # The group each tool belongs to, filled in by _tool as the definitions run.
        #
        # It covers every tool that exists, including the ones left unregistered,
        # which is what lets an --enable-tools name that matches nothing be
        # reported as the typo it is.
        self.group_by_tool = {}
        self._registering_group = None

        self.mcp = FastMCP("FoxMCP")
        self._setup_tools()

    @classmethod
    def _validate_groups(cls, disabled_groups):
        """Check requested group names against TOOL_GROUPS, returning them as a set

        Raises ValueError naming both the unknown groups and the valid ones. The
        message reaches a user through server.py's --disable-tools, so it carries
        the whole list rather than telling them where to look it up.
        """
        groups = set(disabled_groups or ())
        unknown = sorted(groups - set(cls.TOOL_GROUPS))
        if unknown:
            raise ValueError(
                f"Unknown tool group(s): {', '.join(unknown)}. "
                f"Valid groups: {', '.join(sorted(cls.TOOL_GROUPS))}"
            )
        return groups

    def _setup_tools(self):
        """Set up all MCP tool definitions, minus any disabled group

        Every group's definitions run even when the group is disabled, because
        defining a tool is not registering it - _tool decides that, and needs to
        see each definition to record the name. Running them all is what builds
        the catalogue that _validate_tools checks --enable-tools against.
        """
        for group, setup_method in self.TOOL_GROUPS.items():
            self._registering_group = group
            getattr(self, setup_method)()
        self._registering_group = None

        self._validate_tools()
        self._log_disabled_groups()

    def _tool(self, describe_more=None):
        """Return the decorator that registers one tool, in place of @self.mcp.tool()

        Every tool definition below goes through here, which is what gives
        --enable-tools its per-tool grip: this is the one place that knows both
        the group being set up and the name of the tool being defined. A tool
        from a disabled group is registered only if it was named individually.

        describe_more, if given, is called only when the tool is registered, and
        the text it returns is appended to the tool's description. That keeps the
        work it does, such as reading a directory, off servers that never offer
        the tool.

        A tool that is not registered is still recorded in group_by_tool, and the
        undecorated function is handed back - the closure stays defined, and no
        MCP client ever hears about it.
        """
        group = self._registering_group

        def register(fn):
            self.group_by_tool[fn.__name__] = group
            if group in self.disabled_groups and fn.__name__ not in self.enabled_tools:
                return fn
            summary = fn.__doc__.strip().split('\n\n')[0]
            if 'profile_id' in inspect.signature(fn).parameters:
                summary += ("\n\nprofile_id is required: obtain it from profiles_list. "
                            "All object IDs are local to that profile; never reuse them in another profile.")
            if describe_more is not None:
                summary += "\n\n" + describe_more()
            return self.mcp.tool(description=summary)(fn)

        return register

    def _validate_tools(self):
        """Check enabled_tools against the tools that exist, once they have been defined

        Raises ValueError naming both the unknown tools and every valid name. The
        message reaches a user through server.py's --enable-tools, so it carries
        the whole list rather than telling them where to look it up.
        """
        unknown = sorted(self.enabled_tools - set(self.group_by_tool))
        if unknown:
            raise ValueError(
                f"Unknown tool(s): {', '.join(unknown)}. "
                f"Valid tools: {', '.join(sorted(self.group_by_tool))}"
            )

    def _log_disabled_groups(self):
        """Log each disabled group, and any of its tools that were kept anyway"""
        for group in sorted(self.disabled_groups):
            kept = sorted(
                name for name, tool_group in self.group_by_tool.items()
                if tool_group == group and name in self.enabled_tools
            )
            if kept:
                logger.info(
                    f"Tool group '{group}' disabled - registering only: {', '.join(kept)}"
                )
            else:
                logger.info(f"Tool group '{group}' disabled - not registering its tools")

    async def _send(self, profile_id, request, timeout=30.0):
        return await self.websocket_server.send_request_and_wait(
            {**request, "profile_id": profile_id}, timeout=timeout)

    def _setup_profile_tools(self):
        """Profile discovery is independent of the other optional tool groups."""
        @self._tool()
        async def profiles_list(populate: bool = True) -> dict:
            """List all connected Firefox profiles, their real names and windows.

            Use profile_id explicitly in every browser command. Window, tab, group,
            container and monitor IDs belong to that profile only. Inspect window
            tabs (titles and URLs) to choose the correct target. A profile_id identifies one connection and changes on every reconnect.
            Call profiles_list again after a disconnect or server restart.
            Unavailable names and per-profile window errors are reported separately.

            Args:
                populate: Include each window's tabs with titles and URLs.
            """
            return await self.websocket_server.list_profiles(populate=populate)

    def _setup_window_tools(self):
        """Setup window management tools"""

        @self._tool()
        async def list_windows(profile_id: int, populate: bool = True) -> str:
            """
            List all browser windows
            
            Args:
                populate: Whether to include tab information for each window
                
            Returns:
                String containing list of windows with their details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.list",
                "data": {"populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error getting windows: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                windows_data = response["data"]
                windows = windows_data.get("windows", [])
                if not windows:
                    return "No windows found"

                result = f"Browser windows ({len(windows)} found): [profile {profile_id}]\n"
                for window in windows:
                    state_info = f"state: {window.get('state', 'unknown')}"
                    focused_info = " (focused)" if window.get("focused") else ""
                    size_info = f"{window.get('width', '?')}x{window.get('height', '?')}"
                    tabs_count = len(window.get('tabs', [])) if populate else '?'
                    result += f"- ID {window.get('id')}: {window.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs{focused_info}\n"
                return result

            return "Unable to retrieve windows"

        @self._tool()
        async def get_window(profile_id: int, window_id: int, populate: bool = True) -> str:
            """
            Get information about a specific window
            
            Args:
                window_id: The ID of the window to retrieve
                populate: Whether to include tab information
                
            Returns:
                String containing window details
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.get",
                "data": {"windowId": window_id, "populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error getting window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if not window_data:
                    return f"Window {window_id} not found"

                state_info = f"state: {window_data.get('state', 'unknown')}"
                focused_info = " (focused)" if window_data.get("focused") else ""
                size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                tabs_count = len(window_data.get('tabs', [])) if populate else '?'
                return f"Window {window_data.get('id')}: {window_data.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs{focused_info}"

            return f"Unable to retrieve window {window_id}"

        # There is no get_last_focused_window tool because it could not have differed
        # from this one.
        #
        # ext-windows.js reads `context.currentWindow || windowTracker.topWindow` for
        # getCurrent and plain `windowTracker.topWindow` for getLastFocused, and
        # ExtensionParent.sys.mjs returns undefined for `currentWindow` whenever the
        # context's viewType is "background" - which is the only context this
        # extension has. So both calls evaluate the same expression. A separate tool
        # shipped until 1.2.0 and always returned the same window as this one.
        @self._tool()
        async def get_current_window(profile_id: int, populate: bool = True) -> str:
            """Get the current active window, which is also the last focused window

            Args:
                populate: Whether to include tab information
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.get_current",
                "data": {"populate": populate},
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error getting current window: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if not window_data:
                    return "No current window found"

                state_info = f"state: {window_data.get('state', 'unknown')}"
                size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                tabs_count = len(window_data.get('tabs', [])) if populate else '?'
                return f"Current window (ID {window_data.get('id')}): {window_data.get('type', 'normal')} window, {state_info}, {size_info}, {tabs_count} tabs"

            return "Unable to retrieve current window"

        @self._tool()
        async def create_window(
            profile_id: int,
            url: Optional[str] = None,
            window_type: str = "normal",
            state: str = "normal", 
            focused: bool = True,
            width: Optional[int] = None,
            height: Optional[int] = None,
            top: Optional[int] = None,
            left: Optional[int] = None,
            incognito: bool = False
        ) -> str:
            """
            Create a new browser window
            
            Args:
                url: URL to load in the new window
                window_type: Type of window ("normal", "popup", "panel", "detached_panel")
                state: Window state ("normal", "minimized", "maximized", "fullscreen")
                focused: Whether the new window takes focus. Firefox always focuses a
                    new window, so with False the extension hands focus back to the
                    window that had it; the result says "(focused)" if the new window
                    kept it anyway.
                width: Window width in pixels
                height: Window height in pixels  
                top: Window top position in pixels
                left: Window left position in pixels
                incognito: Whether to create an incognito window
                
            Returns:
                String containing created window details
            """
            data = {'type': window_type, 'state': state, 'focused': focused, 'incognito': incognito}
            if url: data['url'] = url
            if width: data['width'] = width
            if height: data['height'] = height
            if top is not None: data['top'] = top
            if left is not None: data['left'] = left
            
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.create",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error creating window: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if window_data:
                    window_id = window_data.get('id')
                    window_url = url or "about:blank"
                    size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                    focused_info = " (focused)" if window_data.get("focused") else ""
                    return f"Created {window_type} window (ID {window_id}): {window_url}, {size_info}{focused_info}"

            return "Window created but unable to retrieve details"

        @self._tool() 
        async def close_window(profile_id: int, window_id: int) -> str:
            """
            Close a browser window
            
            Args:
                window_id: The ID of the window to close
                
            Returns:
                String indicating success/failure
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.close",
                "data": {"windowId": window_id},
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error closing window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                if response["data"].get("success"):
                    return f"Window {window_id} closed successfully"
                else:
                    return f"Failed to close window {window_id}"

            return f"Unable to close window {window_id}"

        @self._tool()
        async def focus_window(profile_id: int, window_id: int) -> str:
            """
            Bring a window to front and focus it
            
            Args:
                window_id: The ID of the window to focus
                
            Returns:
                String indicating success/failure
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.focus",
                "data": {"windowId": window_id},
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error focusing window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                if response["data"].get("success"):
                    return f"Window {window_id} focused successfully"
                else:
                    return f"Failed to focus window {window_id}"

            return f"Unable to focus window {window_id}"

        @self._tool()
        async def update_window(
            profile_id: int,
            window_id: int,
            state: Optional[str] = None,
            focused: Optional[bool] = None,
            width: Optional[int] = None,
            height: Optional[int] = None,
            top: Optional[int] = None,
            left: Optional[int] = None
        ) -> str:
            """
            Update window properties
            
            Args:
                window_id: The ID of the window to update
                state: New window state ("normal", "minimized", "maximized", "fullscreen")
                focused: True brings the window to the front. False is refused:
                    Firefox cannot take focus away from a window, so call
                    focus_window on the window that should have it instead.
                width: New window width in pixels
                height: New window height in pixels
                top: New window top position in pixels
                left: New window left position in pixels
                
            Returns:
                String containing updated window details
            """
            # Firefox's windows.update ignores focused: false without an error.
            if focused is False:
                return ("Error: focused=False is not supported; Firefox cannot take focus "
                        "away from a window. Call focus_window on the window that should "
                        "have focus instead.")

            data = {'windowId': window_id}
            if state: data['state'] = state
            if focused is not None: data['focused'] = focused
            if width: data['width'] = width
            if height: data['height'] = height
            if top is not None: data['top'] = top
            if left is not None: data['left'] = left
            
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "windows.update",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error updating window {window_id}: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                window_data = response["data"].get("window", {})
                if window_data:
                    state_info = f"state: {window_data.get('state', 'unknown')}"
                    size_info = f"{window_data.get('width', '?')}x{window_data.get('height', '?')}"
                    return f"Updated window {window_id}: {state_info}, {size_info}"
                else:
                    return f"Window {window_id} updated successfully"

            return f"Unable to update window {window_id}"

    def _setup_container_tools(self):
        """Container discovery and profile resources, independent of client lifetime."""
        @self._tool()
        async def containers_list(profile_id: int) -> str:
            """List Firefox containers as JSON with opaque cookie_store_id, name, color
            and icon; default_cookie_store_id identifies normal browsing separately.
            IDs belong to the connected profile. Names may repeat.
            """
            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": "containers.list",
                "data": {}, "timestamp": datetime.now().isoformat(),
            })
            error = browser_tool_error(response)
            if error:
                return f"Error listing containers: {error}"
            return json.dumps(response.get("data", {}))

        async def container_request(profile_id, action, data):
            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": action,
                "data": data, "timestamp": datetime.now().isoformat(),
            })
            error = browser_tool_error(response)
            if error:
                return f"Error managing container: {error}"
            return json.dumps(response.get("data", {}))

        def properties(name=None, color=None, icon=None):
            result = {}
            for key, value in (("name", name), ("color", color), ("icon", icon)):
                if value is not None:
                    if not isinstance(value, str) or not value.strip():
                        raise ValueError(f"{key} must be a nonempty string")
                    result[key] = value
            return result

        def named_store(value):
            validate_cookie_store_id(value)
            if value in ("firefox-default", "firefox-private"):
                raise ValueError("Default and private stores are not named containers")
            return value

        @self._tool()
        async def containers_create(profile_id: int, name: str, color: str = "blue", icon: str = "fingerprint") -> str:
            """Create a persistent Firefox container. Return JSON container metadata.
            Duplicate names are permitted. Firefox validates color and icon.
            """
            try:
                if name is None or color is None or icon is None:
                    raise ValueError("name, color and icon must be nonempty strings")
                data = properties(name, color, icon)
            except ValueError as error:
                return f"Error: INVALID_PARAMETER: {error}"
            return await container_request(profile_id, "containers.create", data)

        @self._tool()
        async def containers_update(profile_id: int, cookie_store_id: str, name: Optional[str] = None,
                                    color: Optional[str] = None, icon: Optional[str] = None) -> str:
            """Update a named Firefox container, preserving its ID and omitted properties.
            Supply at least one of name, color or icon. Return JSON container metadata.
            """
            try:
                store = named_store(cookie_store_id)
                data = properties(name, color, icon)
                if not data:
                    raise ValueError("Supply at least one of name, color or icon")
            except ValueError as error:
                return f"Error: INVALID_PARAMETER: {error}"
            return await container_request(profile_id, "containers.update", {"cookieStoreId": store, **data})

        @self._tool()
        async def containers_remove(profile_id: int, cookie_store_id: str) -> str:
            """Remove a named Firefox container and its stored site data. Refuses open
            tabs with CONTAINER_IN_USE and tab_ids. Close tabs explicitly first.
            The check cannot exclude races with browser UI. No automatic cleanup.
            """
            try:
                store = named_store(cookie_store_id)
            except ValueError as error:
                return f"Error: INVALID_PARAMETER: {error}"
            return await container_request(profile_id, "containers.remove", {"cookieStoreId": store})

    def _setup_tab_tools(self):
        """Setup tab management tools"""

        # Tab List Tool
        @self._tool()
        async def tabs_list(profile_id: int, window_id: Optional[Union[int, str]] = None,
                            cookie_store_id: Optional[str] = None) -> str:
            """
            List open browser tabs, optionally filtered by window and cookie store

            Each line includes "[window {id}, index {n}] [cookie store {cookie_store_id}]", and carries "(active)" for the
            active tab of its window and "(pinned)" for a pinned one. The window, the index
            and the pinned mark are what tabs_move needs: the window to move a tab out of or
            into, the position it currently holds, and whether a leading run of pinned tabs
            blocks the low indexes.

            Args:
                window_id: Restrict the listing to this window (optional, accepts int or
                    string). Omit it to list tabs in every window.
                cookie_store_id: Opaque store ID to filter by, combined with window_id.

            Returns:
                Formatted string with tab information:
                "Open tabs ({count} found):
                - ID {tab_id}: {title} - {url}{status_indicators} [window {window_id}, index {index}]"

                The index is the tab's position in its window, counting from 0 — pass it to
                tabs_move to reorder.

                Not exposed to clients — see the description above.
            """
            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."

            if cookie_store_id is not None:
                try:
                    validate_cookie_store_id(cookie_store_id)
                except ValueError as error:
                    return f"Error: INVALID_PARAMETER: {error}"

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.list",
                "data": {
                    **({"windowId": window_id} if window_id else {}),
                    **({"cookieStoreId": cookie_store_id} if cookie_store_id is not None else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            error = browser_tool_error(response)
            if error:
                return f"Error getting tabs: {error}"

            if response.get("type") == "response" and "data" in response:
                tabs_data: TabsListResponse = response["data"]
                tabs: List[TabInfo] = tabs_data.get("tabs", [])
                if cookie_store_id is not None and any(
                    tab.get("cookieStoreId") != cookie_store_id for tab in tabs
                ):
                    return "Error: UNSUPPORTED_API: Cannot verify cookie-store filter. Update the extension."
                if not tabs:
                    # More informative message for debugging
                    return f"No tabs found. Extension response: {response.get('data', {})}"

                # The location goes at the end of the line, not next to the tab ID.
                #
                # Callers pick tab IDs out of this listing with an `ID (\d+):` pattern, so
                # nothing may come between the ID and its colon. One test in the suite feeds
                # that match into pytest.skip, which would quietly stop testing rather than
                # fail if the pattern broke.
                scope = f" in window {window_id}" if window_id else ""
                result = f"Open tabs{scope} ({len(tabs)} found): [profile {profile_id}]\n"
                for tab in tabs:
                    active = " (active)" if tab.get("active") else ""
                    pinned = " (pinned)" if tab.get("pinned") else ""
                    location = f" [window {tab.get('windowId')}, index {tab.get('index')}]"
                    result += f"- ID {tab.get('id')}: {tab.get('title', 'No title')} - {tab.get('url', 'No URL')}{active}{pinned}{location} [cookie store {tab.get('cookieStoreId', 'unavailable')}]\n"
                return result

            return "Unable to retrieve tabs"

        # Tab Create Tool
        @self._tool()
        async def tabs_create(
            profile_id: int,
            url: str,
            active: bool = True,
            pinned: bool = False,
            window_id: Optional[Union[int, str]] = None,
            cookie_store_id: Optional[str] = None
        ) -> str:
            """Create a new browser tab

            Args:
                url: URL to open in the new tab
                active: Whether the tab should be active (default: True)
                pinned: Whether the tab should be pinned (default: False)
                window_id: Window ID to create tab in (optional, accepts int or string)
                cookie_store_id: Opaque store ID from containers_list, or firefox-default.
                    Omit for existing behavior. Explicit selection never falls back.
            """
            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."
            
            if cookie_store_id is not None:
                try:
                    validate_cookie_store_id(cookie_store_id)
                except ValueError as error:
                    return f"Error: INVALID_PARAMETER: {error}"

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.create_in_store" if cookie_store_id is not None else "tabs.create",
                "data": {
                    "url": url,
                    "active": active,
                    "pinned": pinned,
                    **({"windowId": window_id} if window_id else {}),
                    **({"cookieStoreId": cookie_store_id} if cookie_store_id is not None else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            error = browser_tool_error(response)
            if error:
                if cookie_store_id is not None and response.get("data", {}).get("code") == "UNKNOWN_ACTION":
                    return "Error: UNSUPPORTED_API: Update the extension for container tab creation. No fallback attempted."
                return f"Error creating tab: {error}"

            if response.get("type") == "response" and "data" in response:
                tab = response["data"].get("tab", {})
                if cookie_store_id is not None and tab.get("cookieStoreId") != cookie_store_id:
                    return (f"Error: API_ERROR: Created tab ID {tab.get('id')} has cookie store "
                            f"{tab.get('cookieStoreId', 'unavailable')}, expected {cookie_store_id}.")
                return f"Created tab: ID {tab.get('id')} - {tab.get('title', 'Loading...')} - {tab.get('url', url)} [cookie store {tab.get('cookieStoreId', 'unavailable')}]"

            return "Unable to create tab"

        # Tab Close Tool
        @self._tool()
        async def tabs_close(profile_id: int, tab_id: int) -> str:
            """Close a browser tab

            Args:
                tab_id: ID of the tab to close
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.close",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error closing tab: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully closed tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to close tab: {error_msg}"

            return f"Unable to close tab {tab_id}"

        # Tab Switch Tool
        @self._tool()
        async def tabs_switch(profile_id: int, tab_id: int) -> str:
            """Switch to a specific browser tab

            Args:
                tab_id: ID of the tab to switch to
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.switch",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error switching to tab: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully switched to tab {tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to switch to tab: {error_msg}"

            return f"Unable to switch to tab {tab_id}"

        @self._tool()
        async def tabs_group(
            profile_id: int,
            tab_ids: Union[int, str, List[Union[int, str]]],
            group_id: Optional[Union[int, str]] = None,
            title: Optional[str] = None,
            color: Optional[str] = None
        ) -> str:
            """Group existing tabs, optionally setting the group's title and colour

            Never activates a tab or focuses a window. Requires Firefox 139+. Omit
            group_id to create a group in the first tab's window, which moves tabs from
            other windows into it; pass a group_id from tabs_groups_query to add tabs
            to that group instead. Firefox unpins a pinned tab before grouping it, and
            refuses to mix private and non-private tabs.

            Grouping and styling are separate steps in Firefox. If the tabs were
            grouped but the title or colour could not be set, the result still names
            the group, and tabs_groups_update can retry the styling.

            Args:
                tab_ids: Tab ID, or several as a list (`[12, 15]`) or a JSON string
                    (`"[12, 15]"`).
                group_id: Group to add the tabs to; omit it to create a new group.
                title: Group title; an empty string clears it. Omit to leave as is.
                color: blue, cyan, grey, green, orange, pink, purple, red or yellow.
                    Omit to leave as is.
            """
            try:
                data = {"tabIds": parse_tab_ids(tab_ids)}
                if group_id is not None:
                    data["groupId"] = parse_id(group_id, "group_id")
                data.update(parse_group_properties(title=title, color=color))
            except ValueError as error:
                return f"Error: {error}"

            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": "tabs.group",
                "data": data, "timestamp": datetime.now().isoformat()
            })
            if "error" in response:
                return f"Error grouping tabs: {response['error']}"
            if response.get("type") == "error":
                return f"Failed to group tabs: {response.get('data', {}).get('message', 'Unknown error')}"
            reply = response.get("data", {})
            if response.get("type") == "response" and "groupId" in reply:
                if reply.get("styleError"):
                    return (f"Tabs grouped into group {reply['groupId']}, but its title/colour "
                            f"could not be set: {reply['styleError']}. "
                            f"Retry the styling with tabs_groups_update.")
                return f"Tabs grouped into group {reply['groupId']}"
            return "Unable to group tabs"

        @self._tool()
        async def tabs_ungroup(
            profile_id: int,
            tab_ids: Union[int, str, List[Union[int, str]]]
        ) -> str:
            """Remove tabs from their tab group

            Never activates a tab or focuses a window. Requires Firefox 138+. Firefox
            deletes a group once its last tab leaves it.

            Args:
                tab_ids: Tab ID, or several as a list (`[12, 15]`) or a JSON string
                    (`"[12, 15]"`).
            """
            try:
                data = {"tabIds": parse_tab_ids(tab_ids)}
            except ValueError as error:
                return f"Error: {error}"

            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": "tabs.ungroup",
                "data": data, "timestamp": datetime.now().isoformat()
            })
            if "error" in response:
                return f"Error ungrouping tabs: {response['error']}"
            if response.get("type") == "error":
                return f"Failed to ungroup tabs: {response.get('data', {}).get('message', 'Unknown error')}"
            if response.get("type") == "response" and response.get("data", {}).get("success"):
                return f"Ungrouped {len(data['tabIds'])} tab(s)"
            return "Unable to ungroup tabs"

        @self._tool()
        async def tabs_groups_update(
            profile_id: int,
            group_id: Union[int, str],
            title: Optional[str] = None,
            color: Optional[str] = None,
            collapsed: Optional[bool] = None
        ) -> str:
            """Change a tab group's title, colour or collapsed state

            Leaves the group's tabs where they are. Requires Firefox 139+. Give at
            least one of title, color or collapsed.

            Args:
                group_id: The group to change, from tabs_group or tabs_groups_query.
                title: New title; an empty string clears it.
                color: blue, cyan, grey, green, orange, pink, purple, red or yellow.
                collapsed: Whether the group should be collapsed.
            """
            try:
                data = {"groupId": parse_id(group_id, "group_id")}
                properties = parse_group_properties(title=title, color=color, collapsed=collapsed)
                if not properties:
                    raise ValueError("Provide at least one of title, color or collapsed")
                data.update(properties)
            except ValueError as error:
                return f"Error: {error}"

            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": "tabGroups.update",
                "data": data, "timestamp": datetime.now().isoformat()
            })
            if "error" in response:
                return f"Error updating group: {response['error']}"
            if response.get("type") == "error":
                return f"Failed to update group: {response.get('data', {}).get('message', 'Unknown error')}"
            if response.get("type") == "response" and "group" in response.get("data", {}):
                group = response["data"]["group"]
                return f"Updated group {group.get('id', data['groupId'])}"
            return "Unable to update group"

        @self._tool()
        async def tabs_groups_query(
            profile_id: int,
            window_id: Optional[Union[int, str]] = None,
            title: Optional[str] = None,
            color: Optional[str] = None,
            collapsed: Optional[bool] = None
        ) -> str:
            """List tab groups with their IDs, in every window or filtered

            Requires Firefox 139+. tabs_group reports a group's ID only when it creates
            the group, so this is how to find the ID of any other group.

            Args:
                window_id: Only groups in this window (optional, accepts int or string).
                title: Only groups with exactly this title.
                color: Only groups of this colour.
                collapsed: Only collapsed (True) or expanded (False) groups.
            """
            try:
                data = {}
                if window_id is not None:
                    data["windowId"] = parse_id(window_id, "window_id")
                data.update(parse_group_properties(title=title, color=color, collapsed=collapsed))
            except ValueError as error:
                return f"Error: {error}"

            response = await self._send(profile_id, {
                "id": str(uuid.uuid4()), "type": "request", "action": "tabGroups.query",
                "data": data, "timestamp": datetime.now().isoformat()
            })
            if "error" in response:
                return f"Error listing groups: {response['error']}"
            if response.get("type") == "error":
                return f"Failed to list groups: {response.get('data', {}).get('message', 'Unknown error')}"
            if response.get("type") == "response" and "groups" in response.get("data", {}):
                groups = response["data"]["groups"]
                if not groups:
                    return "No tab groups found"
                result = f"Tab groups ({len(groups)} found):\n"
                for group in groups:
                    collapsed_info = " (collapsed)" if group.get("collapsed") else ""
                    result += (
                        f"- ID {group.get('id')}: {group.get('title') or 'Untitled'} - "
                        f"{group.get('color')}{collapsed_info} [window {group.get('windowId')}]\n"
                    )
                return result
            return "Unable to list groups"

        # Tab Move Tool
        @self._tool()
        async def tabs_move(
            profile_id: int,
            tab_ids: Union[int, str, List[Union[int, str]]],
            window_id: Optional[Union[int, str]] = None,
            index: int = -1
        ) -> str:
            """Move tabs to a new position, optionally into another window

            Reorders tabs within their window, or gathers them into a different window —
            to collect every tab for one site into a window of its own, create the window
            with create_window and pass its ID here.

            Succeeding partially is normal, so check the result: it reads
            "Moved {n} of {m}", and a tab missing from the list did not move. Firefox
            declines some moves without raising an error, and the common one is that
            **an unpinned tab cannot be placed in front of a pinned tab** — with 3 pinned
            tabs, the lowest index an unpinned tab can reach is 3, and asking for 0, 1 or 2
            moves nothing. Use tabs_list to see which tabs are pinned and what index each
            tab currently holds. A pinned tab can be moved to index 0 freely.

            Moving between windows requires both to be normal windows, not popups, and
            either both private or both non-private.

            Args:
                tab_ids: Tab ID, or several as a list (`[12, 15]`) or a JSON string
                    (`"[12, 15]"`). Listed tabs keep their given order at the destination.
                window_id: Window to move the tabs into (optional, accepts int or string).
                    Omit it to reorder within each tab's current window.
                index: Position to move to, counting from 0; -1 means the end (default: -1).
                    An index inside a leading run of pinned tabs is refused for an unpinned
                    tab — the move reports "No tabs moved" rather than failing.

            Returns:
                "Moved {n} of {m} tab(s):" and one line per moved tab with its new window
                and index, or "No tabs moved." when Firefox declined every one. Note that
                FastMCP does not expose this section to clients — anything a caller must
                know belongs in the description above or on the arguments.
            """
            try:
                normalized_ids = parse_tab_ids(tab_ids)
            except ValueError as error:
                return f"Error: {error}"

            # Convert window_id to int if it's a string (for MCP client compatibility)
            if window_id is not None and isinstance(window_id, str):
                try:
                    window_id = int(window_id)
                except (ValueError, TypeError):
                    return f"Error: Invalid window_id '{window_id}'. Must be a valid integer."

            if index < -1:
                return f"Error: Invalid index {index}. Must be -1 (end) or 0 or greater."

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "tabs.move",
                "data": {
                    "tabIds": normalized_ids,
                    "index": index,
                    **({"windowId": window_id} if window_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error moving tabs: {response['error']}"

            if response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to move tabs: {error_msg}"

            if response.get("type") == "response" and "data" in response:
                moved_tabs: List[TabInfo] = response["data"].get("tabs", [])
                if not moved_tabs:
                    return (
                        f"No tabs moved. Firefox refused the move of {len(normalized_ids)} tab(s) — "
                        "check that the target index is not in front of a pinned tab."
                    )

                result = f"Moved {len(moved_tabs)} of {len(normalized_ids)} tab(s):\n"
                for tab in moved_tabs:
                    result += f"- ID {tab.get('id')} -> window {tab.get('windowId')}, index {tab.get('index')}: {tab.get('title', 'No title')}\n"
                return result

            return "Unable to move tabs"

        # Tab Screenshot Tool
        @self._tool()
        async def tabs_capture_screenshot(
            profile_id: int,
            filename: Optional[str] = None,
            window_id: Optional[int] = None,
            format: str = "png",
            quality: int = 90,
            tab_id: Optional[int] = None
        ) -> str:
            """Capture a screenshot of the visible tab, or of the tab given by tab_id

            What comes back depends on whether you pass a filename: with one, the image is
            written to disk and you get a success message and the path; without one, you get
            the image inline as a base64 data URL, which for a full window is large.

            Args:
                filename: Name of the file to save the screenshot (optional, if not provided returns base64)
                window_id: ID of the window to capture (optional, defaults to current window)
                format: Image format ('png' or 'jpeg', default: 'png')
                quality: Image quality for JPEG format (1-100, default: 90)
                tab_id: Capture this tab, even in the background (not with window_id)

            Returns:
                Success message with file path if filename provided, otherwise base64 encoded image data URL

                Not exposed to clients — see the description above.
            """
            if tab_id is not None and window_id is not None:
                return "Error capturing screenshot: pass tab_id or window_id, not both"

            if tab_id is not None:
                request = {
                    "id": str(uuid.uuid4()),
                    "type": "request",
                    "action": "tabs.captureTab",
                    "data": {"tabId": tab_id, "format": format, "quality": quality},
                    "timestamp": datetime.now().isoformat()
                }
            else:
                request = {
                    "id": str(uuid.uuid4()),
                    "type": "request",
                    "action": "tabs.captureVisibleTab",
                    "data": {
                        **({"windowId": window_id} if window_id else {}),
                        "format": format,
                        "quality": quality
                    },
                    "timestamp": datetime.now().isoformat()
                }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error capturing screenshot: {response['error']}"

            if (tab_id is not None and response.get("type") == "error"
                    and response.get("data", {}).get("code") == "UNKNOWN_ACTION"):
                return (
                    "Failed to capture screenshot: this FoxMCP extension is too old to capture a "
                    "tab that is not showing (it has no tabs.captureTab). Update the extension, or "
                    "make the tab the active one (tabs_switch) and use window_id."
                )

            if response.get("type") == "response" and "data" in response:
                data_url = response["data"].get("dataUrl", "")
                captured_format = response["data"].get("format", format)
                captured_quality = response["data"].get("quality", quality)
                captured_window_id = response["data"].get("windowId", "current")
                captured_tab_id = response["data"].get("tabId")
                captured_from = (
                    f"tab {captured_tab_id}" if captured_tab_id is not None
                    else f"window {captured_window_id}"
                )

                if not data_url:
                    return "No screenshot data received"

                # Extract the base64 part from data URL
                data_prefix = f"data:image/{captured_format};base64,"
                if not data_url.startswith(data_prefix):
                    return f"Screenshot captured but unexpected format: {data_url[:100]}..."

                base64_data = data_url[len(data_prefix):]

                # If filename is provided, save to file
                if filename:
                    try:
                        # Add file extension if not provided
                        if not filename.lower().endswith(('.png', '.jpg', '.jpeg')):
                            filename = f"{filename}.{captured_format}"

                        # Decode base64 and save to file
                        image_data = base64.b64decode(base64_data)
                        with open(filename, 'wb') as f:
                            f.write(image_data)

                        file_size = len(image_data)
                        return (
                            f"Screenshot saved to '{filename}' "
                            f"({captured_from}, {captured_format}, "
                            f"quality: {captured_quality}, size: {file_size} bytes)"
                        )

                    except Exception as e:
                        return f"Error saving screenshot to file '{filename}': {str(e)}"

                else:
                    # Return base64 data as before when no filename provided
                    data_size = len(base64_data)
                    return (
                        f"Screenshot captured successfully from {captured_from} "
                        f"({captured_format}, quality: {captured_quality}):\n"
                        f"{data_url[:100]}...\n\n"
                        f"Base64 data size: {data_size} characters"
                    )

            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to capture screenshot: {error_msg}"

            return "Unable to capture screenshot"

    def _setup_history_tools(self):
        """Setup history management tools"""

        # History Query Tool
        @self._tool()
        async def history_query(
            profile_id: int,
            query: str,
            max_results: int = 200,
            start_time: Optional[str] = None,
            end_time: Optional[str] = None
        ) -> str:
            """Search browser history

            Args:
                query: Substring to match in URL or title (exact substring match, not tokenized keywords)
                max_results: Maximum number of results (default: 200)
                start_time: Start time filter (ISO format, optional)
                end_time: End time filter (ISO format, optional)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.query",
                "data": {
                    "query": query,
                    "maxResults": max_results,
                    **({"startTime": start_time} if start_time else {}),
                    **({"endTime": end_time} if end_time else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error querying history: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])
                total_count = response["data"].get("totalCount", len(items))

                if not items:
                    return f"No history items found for query: {query}"

                result = f"Found {total_count} history items for '{query}':\n"
                for item in items:
                    visit_time = item.get("lastVisitTime", "Unknown time")
                    visit_count = item.get("visitCount", 0)
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (visited {visit_count} times, last: {visit_time})\n"

                return result

            return f"Unable to query history for: {query}"

        # Get Recent History Tool
        @self._tool()
        async def history_get_recent(profile_id: int, count: int = 10) -> str:
            """Get recent browser history

            Args:
                count: Number of recent items to get (default: 10)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.recent",
                "data": {
                    "count": count
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            # Debug logging for troubleshooting
            #
            # A print() here would go to stdout, which under --stdio carries the
            # JSON-RPC framing: dumping a response there breaks the client's
            # connection on the first call to this tool.
            logger.debug(f"Recent history WebSocket response: {json.dumps(response, indent=2)}")

            if "error" in response:
                return f"Error getting recent history: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                items = response["data"].get("items", [])

                if not items:
                    return "No recent history items found"

                result = f"Recent {len(items)} history items:\n"
                for item in items:
                    visit_time = item.get("lastVisitTime", "Unknown time")
                    result += f"- {item.get('title', 'No title')} - {item.get('url', 'No URL')} (last visit: {visit_time})\n"

                return result

            # More detailed error message for debugging
            return f"Unable to get recent history. Response type: {response.get('type')}, has_data: {'data' in response}, keys: {list(response.keys())}"

        # Delete History Item Tool
        @self._tool()
        async def history_delete_item(profile_id: int, url: str) -> str:
            """Delete a specific history item

            Args:
                url: URL of the history item to delete
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "history.delete_item",
                "data": {
                    "url": url
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error deleting history item: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully deleted history item: {url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete history item: {error_msg}"

            return f"Unable to delete history item: {url}"

    def _setup_bookmark_tools(self):
        """Setup bookmark management tools"""

        # List Bookmarks Tool
        @self._tool()
        async def bookmarks_list(profile_id: int, folder_id: Optional[str] = None) -> str:
            """List browser bookmarks

            Folders are marked 📁 and bookmarks 🔖. Every line carries its own ID, its
            parent folder's ID and its index, its position within that folder counting
            from 0. The IDs are what bookmarks_update, bookmarks_delete, bookmarks_move and
            the parent_id of bookmarks_create take, so this listing is how you find them.
            With folder_id, the lines are that folder's direct children in order. Without
            it, the whole tree is listed and a folder's children are interleaved with
            everything nested under them, so read positions from Index, not line order.
            An empty folder returns "No bookmarks found".

            Args:
                folder_id: Optional folder ID to list bookmarks from

            Returns:
                Formatted string with bookmark information:
                "Bookmarks:
                📁 {folder_title} (ID: {folder_id}, Parent: {parent_id}, Index: {index})
                🔖 {bookmark_title} - {bookmark_url} (ID: {bookmark_id}, Parent: {parent_id}, Index: {index})"

                Not exposed to clients — see the description above.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.list",
                "data": {
                    **({"folderId": folder_id} if folder_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error listing bookmarks: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])

                if not bookmarks:
                    return "No bookmarks found"

                result = "Bookmarks:\n"
                for bookmark in bookmarks:
                    parent_info = f", Parent: {bookmark.get('parentId', 'None')}"
                    # The root has no parent and so no index; leave the field out
                    # rather than print "Index: None"
                    if bookmark.get("index") is not None:
                        parent_info += f", Index: {bookmark['index']}"
                    if bookmark.get("isFolder", False):
                        result += f"📁 {bookmark.get('title', 'Untitled Folder')} (ID: {bookmark.get('id')}{parent_info})\n"
                    else:
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')} (ID: {bookmark.get('id')}{parent_info})\n"

                return result

            return "Unable to list bookmarks"

        # Search Bookmarks Tool
        @self._tool()
        async def bookmarks_search(profile_id: int, query: str) -> str:
            """Search browser bookmarks by title or URL

            Matches bookmarks only — **folders are never returned**, so a folder cannot be
            found this way; use bookmarks_list to walk the tree instead. Each result carries
            its own ID and its parent folder's ID, which is what bookmarks_update and
            bookmarks_delete take. No matches returns "No bookmarks found".

            Args:
                query: Search query for bookmarks

            Returns:
                Formatted string with search results:
                "Found N bookmarks for 'query':
                🔖 {bookmark_title} - {bookmark_url} (ID: {bookmark_id}, Parent: {parent_id})"

                Not exposed to clients — see the description above.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.search",
                "data": {
                    "query": query
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error searching bookmarks: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmarks = response["data"].get("bookmarks", [])

                if not bookmarks:
                    return f"No bookmarks found for query: {query}"

                result = f"Found {len(bookmarks)} bookmarks for '{query}':\n"
                for bookmark in bookmarks:
                    if not bookmark.get("isFolder", False):
                        parent_info = f", Parent: {bookmark.get('parentId', 'None')}"
                        result += f"🔖 {bookmark.get('title', 'Untitled')} - {bookmark.get('url', 'No URL')} (ID: {bookmark.get('id')}{parent_info})\n"

                return result

            return f"Unable to search bookmarks for: {query}"

        # Create Bookmark Tool
        @self._tool()
        async def bookmarks_create(
            profile_id: int,
            title: str,
            url: str,
            parent_id: Optional[str] = None
        ) -> str:
            """Create a new bookmark

            Args:
                title: Title of the bookmark
                url: URL of the bookmark
                parent_id: Optional ID of the folder to create it in. It must be a
                    folder; a bookmark or separator ID is refused.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.create",
                "data": {
                    "title": title,
                    "url": url,
                    **({"parentId": parent_id} if parent_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error creating bookmark: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return f"Created bookmark: {bookmark.get('title', title)} - {bookmark.get('url', url)} (ID: {bookmark.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to create bookmark: {error_msg}"

            return f"Unable to create bookmark: {title}"

        # Create Bookmark Folder Tool
        @self._tool()
        async def bookmarks_create_folder(
            profile_id: int,
            title: str,
            parent_id: Optional[str] = None
        ) -> str:
            """Create a new bookmark folder

            Args:
                title: Title of the folder
                parent_id: Optional ID of the folder to create it in. It must be a
                    folder; a bookmark or separator ID is refused.
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.createFolder",
                "data": {
                    "title": title,
                    **({"parentId": parent_id} if parent_id else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error creating folder: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                folder = response["data"].get("folder", {})
                return f"Created folder: {folder.get('title', title)} (ID: {folder.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to create folder: {error_msg}"

            return f"Unable to create folder: {title}"

        # Update Bookmark Tool
        @self._tool()
        async def bookmarks_update(
            profile_id: int,
            bookmark_id: str,
            title: Optional[str] = None,
            url: Optional[str] = None
        ) -> str:
            """Update a bookmark or folder's title and/or URL

            Args:
                bookmark_id: ID of the bookmark or folder to update
                title: New title (optional)
                url: New URL (optional, only for bookmarks not folders)
            """
            if title is None and url is None:
                return "Error: At least one of title or url must be provided"

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.update",
                "data": {
                    "bookmarkId": bookmark_id,
                    **({"title": title} if title is not None else {}),
                    **({"url": url} if url is not None else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error updating bookmark: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return f"Updated bookmark: {bookmark.get('title', '')} (ID: {bookmark.get('id')})"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to update bookmark: {error_msg}"

            return f"Unable to update bookmark: {bookmark_id}"

        # Move Bookmark Tool
        @self._tool()
        async def bookmarks_move(
            profile_id: int,
            bookmark_id: str,
            parent_id: Optional[str] = None,
            index: Optional[int] = None
        ) -> str:
            """Move a bookmark or folder into another folder, or to another position

            The bookmark keeps its ID, unlike deleting and recreating it. A folder moves
            with everything in it. Give at least one of parent_id and index. Use
            bookmarks_list to find IDs and the current index of each entry.

            Firefox refuses to move the hidden bookmark root, or a folder into itself or
            one of its own subfolders.

            Args:
                bookmark_id: ID of the bookmark or folder to move.
                parent_id: Folder to move it into. It must be a folder; a bookmark or
                    separator ID is refused. Omit it to reorder within the current folder.
                index: Position in the destination folder, counting from 0. It is the
                    final position: in the same folder, moving index 0 to index 2 leaves
                    it third. An index past the end means the last place. Omit it to put
                    the item at the end of parent_id.

            Returns:
                "Moved {title} (ID: {id}) to folder {parent_id} at index {index}", read
                from Firefox's reply, so the index is where it actually landed. Not
                exposed to clients — see the description above.
            """
            if parent_id is None and index is None:
                return "Error: At least one of parent_id or index must be provided"
            if index is not None and index < 0:
                return f"Error: Invalid index {index}. Must be 0 or greater."

            # Both are tested against None, not truthiness: index 0 is the first
            # place, and dropping it would move the item to the end instead
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.move",
                "data": {
                    "bookmarkId": bookmark_id,
                    **({"parentId": parent_id} if parent_id is not None else {}),
                    **({"index": index} if index is not None else {})
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error moving bookmark: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                bookmark = response["data"].get("bookmark", {})
                return (f"Moved {bookmark.get('title', '')} (ID: {bookmark.get('id')}) "
                        f"to folder {bookmark.get('parentId')} at index {bookmark.get('index')}")
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to move bookmark: {error_msg}"

            return f"Unable to move bookmark: {bookmark_id}"

        # Delete Bookmark Tool
        @self._tool()
        async def bookmarks_delete(profile_id: int, bookmark_id: str) -> str:
            """Delete a bookmark

            Args:
                bookmark_id: ID of the bookmark to delete
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "bookmarks.delete",
                "data": {
                    "bookmarkId": bookmark_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error deleting bookmark: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully deleted bookmark {bookmark_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to delete bookmark: {error_msg}"

            return f"Unable to delete bookmark {bookmark_id}"

    def _setup_debug_tools(self):
        """Setup connection diagnostics tools"""

        @self._tool()
        async def debug_websocket_status() -> str:
            """Debug WebSocket connection status

            Says whether the browser extension is connected, and from where. Every
            other tool fails with a timeout when it is not, so check here first.
            """
            return await self.websocket_server.get_extension_status()

    def _setup_navigation_tools(self):
        """Setup navigation tools"""

        # Navigate Back Tool
        class NavigationBackParams(BaseModel):
            """Parameters for navigating back"""
            tab_id: int = Field(description="ID of the tab to navigate back in")

        @self._tool()
        async def navigation_back(profile_id: int, params: NavigationBackParams) -> str:
            """Navigate back in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.back",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error navigating back: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated back in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate back: {error_msg}"

            return f"Unable to navigate back in tab {params.tab_id}"

        # Navigate Forward Tool
        class NavigationForwardParams(BaseModel):
            """Parameters for navigating forward"""
            tab_id: int = Field(description="ID of the tab to navigate forward in")

        @self._tool()
        async def navigation_forward(profile_id: int, params: NavigationForwardParams) -> str:
            """Navigate forward in browser history for a tab"""
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.forward",
                "data": {
                    "tabId": params.tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error navigating forward: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated forward in tab {params.tab_id}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate forward: {error_msg}"

            return f"Unable to navigate forward in tab {params.tab_id}"

        # Reload Page Tool
        @self._tool()
        async def navigation_reload(profile_id: int, tab_id: int, bypass_cache: bool = False) -> str:
            """Reload a page in a tab

            Returns as soon as the reload is issued, not when the page has
            finished loading. Code that watches for what the reload does - a
            request monitor, a content read - has to wait for the page itself.

            Args:
                tab_id: ID of the tab to reload
                bypass_cache: Whether to bypass cache when reloading (default: False)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.reload",
                "data": {
                    "tabId": tab_id,
                    "bypassCache": bypass_cache
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error reloading page: {response['error']}"

            if response.get("type") == "response":
                cache_text = " (bypassing cache)" if bypass_cache else ""
                return f"Successfully reloaded tab {tab_id}{cache_text}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to reload page: {error_msg}"

            return f"Unable to reload tab {tab_id}"

        # Go to URL Tool
        @self._tool()
        async def navigation_go_to_url(profile_id: int, tab_id: int, url: str) -> str:
            """Navigate to a specific URL in a tab

            Args:
                tab_id: ID of the tab to navigate
                url: URL to navigate to
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "navigation.go_to_url",
                "data": {
                    "tabId": tab_id,
                    "url": url
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error navigating to URL: {response['error']}"

            if response.get("type") == "response":
                return f"Successfully navigated tab {tab_id} to {url}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to navigate to URL: {error_msg}"

            return f"Unable to navigate tab {tab_id} to {url}"

    def _setup_content_tools(self):
        """Setup content access tools"""

        @self._tool()
        async def content_load_file(
            profile_id: int,
            tab_id: int, path: str, mime_type: Optional[str] = None
        ) -> str:
            """Load a server-local file for website uploads/imports; does not submit it.

            Waits for downloading to finish, then returns JSON with file_id and metadata.
            In the SAME tab, use content_execute_script or a predefined script:
            const file = globalThis.foxmcpFiles.get(file_id);
            For file inputs, use cloneInto(file, window), the page's
            window.wrappedJSObject.DataTransfer, and input/change events.
            Return metadata, not the File. Release: globalThis.foxmcpFiles.delete(file_id).
            Handle expires five minutes after loading or on navigation; assigned inputs
            remain valid. Download timeout: 110s. Private tabs unsupported.

            Args:
                tab_id: Target tab ID.
                path: Regular file on the server's machine; only its basename reaches the tab.
                mime_type: Optional MIME override; otherwise inferred from the filename,
                    falling back to application/octet-stream.
            """
            service = self.websocket_server.file_transfers
            token = None
            try:
                token, url, metadata = service.grant(path, mime_type)
                file_id = str(uuid.uuid4())
                logger.info("Loading local file %r (%s bytes, %s) into tab %s",
                            metadata["name"], metadata["size"], metadata["type"], tab_id)
                response = await self._send(profile_id, {
                    "id": str(uuid.uuid4()), "type": "request",
                    "action": "content.load_file",
                    "data": {"tabId": tab_id, "fileId": file_id,
                             "url": url, **metadata},
                    "timestamp": datetime.now().isoformat()
                }, timeout=120.0)
                if "error" in response or response.get("type") == "error":
                    detail = response.get("error") or response.get("data", {}).get("message", "Unknown error")
                    return f"Failed to load file: {detail}"
                data = response.get("data", {})
                if data.get("fileId") != file_id:
                    return "Failed to load file: extension did not confirm the file handle"
                return json.dumps({"file_id": file_id, **metadata, "expires_in_seconds": 300})
            except (OSError, ValueError, RuntimeError) as error:
                logger.warning("Local file load refused or failed: %s", error)
                return f"Failed to load file: {getattr(error, 'strerror', None) or error}"
            finally:
                if token is not None:
                    service.revoke(token)

        # Get Page Text Tool
        @self._tool()
        async def content_get_text(profile_id: int, tab_id: int, max_length: Optional[int] = None) -> str:
            """Get text content from a tab's page

            Args:
                tab_id: ID of the tab to get content from
                max_length: Optional maximum length of text to return (default: unlimited)
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_text",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error getting page text: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                text = response["data"].get("text", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")

                if not text:
                    return f"No text content found in tab {tab_id} ({title})"

                # Apply length limit if specified
                if max_length is not None and len(text) > max_length:
                    truncated_text = text[:max_length]
                    return f"Text content from {title} ({url}):\n\n{truncated_text}..."
                else:
                    return f"Text content from {title} ({url}):\n\n{text}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page text: {error_msg}"

            return f"Unable to get text content from tab {tab_id}"

        # Get Page HTML Tool
        @self._tool()
        async def content_get_html(profile_id: int, tab_id: int) -> str:
            """Get HTML content from a tab's page

            Args:
                tab_id: ID of the tab to get HTML content from
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.get_html",
                "data": {
                    "tabId": tab_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error getting page HTML: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                html = response["data"].get("html", "")
                url = response["data"].get("url", "Unknown URL")
                title = response["data"].get("title", "Unknown Title")

                if not html:
                    return f"No HTML content found in tab {tab_id} ({title})"

                return f"HTML content from {title} ({url}):\n\n{html[:2000]}{'...' if len(html) > 2000 else ''}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to get page HTML: {error_msg}"

            return f"Unable to get HTML content from tab {tab_id}"

        # Execute Script Tool
        @self._tool()
        async def content_execute_script(profile_id: int, tab_id: int, code: str) -> str:
            """Execute JavaScript code in a tab

            Args:
                tab_id: ID of the tab to execute script in
                code: JavaScript code to execute
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "content.execute_script",
                "data": {
                    "tabId": tab_id,
                    "script": code
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return f"Error executing script: {response['error']}"

            if response.get("type") == "response" and "data" in response:
                result = response["data"].get("result")
                url = response["data"].get("url", "Unknown URL")

                if result is None:
                    return f"Script executed successfully in tab {tab_id} ({url}) - no return value"

                return f"Script result from tab {tab_id} ({url}):\n{result}"
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return f"Failed to execute script: {error_msg}"

            return f"Unable to execute script in tab {tab_id}"

        # Execute Predefined Script Tool
        @self._tool(describe_more=lambda: describe_predefined_scripts(os.environ.get('FOXMCP_EXT_SCRIPTS')))
        async def content_execute_predefined(
            profile_id: int,
            tab_id: int,
            script_name: str,
            script_args: str = ""
        ) -> str:
            """Execute a predefined external script and run its JavaScript output in a tab

            Args:
                tab_id: ID of the tab to execute script in
                script_name: Name of the script to run, one of those listed above
                script_args: JSON array of strings to pass to the external script (e.g., '["arg1", "arg2"]')
                            or empty string for no arguments
            """
            # Every rejection below is logged at warning level.
            #
            # This is the code-execution surface an MCP client can reach, so a
            # refusal is worth a line whether it came from a typo or from an
            # attempt to escape the scripts directory - the two are
            # indistinguishable here, and only the log preserves the attempt.

            # Get the scripts directory from environment variable
            scripts_dir = os.environ.get('FOXMCP_EXT_SCRIPTS')
            if not scripts_dir:
                logger.warning(
                    f"Predefined script '{script_name}' refused: FOXMCP_EXT_SCRIPTS is not set"
                )
                return "Error: FOXMCP_EXT_SCRIPTS environment variable not set"

            # Validate script name to prevent path traversal attacks
            if not script_name or '..' in script_name or '/' in script_name or '\\' in script_name:
                logger.warning(
                    f"Predefined script refused: name {script_name!r} contains a path separator or '..'"
                )
                return f"Error: Invalid script name '{script_name}'. Script names cannot contain path separators or '..' sequences"

            # Additional validation: only allow alphanumeric, underscore, dash, and dot
            if not SCRIPT_NAME_PATTERN.match(script_name):
                logger.warning(
                    f"Predefined script refused: name {script_name!r} has characters outside [a-zA-Z0-9._-]"
                )
                return f"Error: Invalid script name '{script_name}'. Only alphanumeric characters, underscore, dash, and dot are allowed"

            # Resolve absolute paths to prevent symlink attacks
            scripts_dir = os.path.abspath(scripts_dir)
            script_path = os.path.abspath(os.path.join(scripts_dir, script_name))

            # Ensure the resolved script path is still within the scripts directory
            if not script_path.startswith(scripts_dir + os.sep) and script_path != scripts_dir:
                logger.warning(
                    f"Predefined script refused: {script_name!r} resolves to {script_path!r}, "
                    f"outside {scripts_dir!r}"
                )
                return f"Error: Script path '{script_name}' escapes the allowed directory"

            if not os.path.exists(script_path):
                logger.warning(f"Predefined script refused: {script_name!r} not found in {scripts_dir!r}")
                return f"Error: Script '{script_name}' not found in {scripts_dir}"

            if not os.access(script_path, os.X_OK):
                logger.warning(f"Predefined script refused: {script_name!r} is not executable")
                return f"Error: Script '{script_name}' is not executable"

            try:
                # Parse JSON arguments - handle both empty string and JSON arrays
                try:
                    if script_args.strip() == "":
                        # Empty string means no arguments
                        args_list = []
                    else:
                        # Parse as JSON array
                        args_list = json.loads(script_args)
                        if not isinstance(args_list, list):
                            logger.warning(
                                f"Predefined script {script_name!r} refused: script_args is "
                                f"{type(args_list).__name__}, not a list"
                            )
                            return f"Error: script_args must be a JSON array of strings or empty string, got: {type(args_list).__name__}"

                        # Validate all arguments are strings
                        for i, arg in enumerate(args_list):
                            if not isinstance(arg, str):
                                logger.warning(
                                    f"Predefined script {script_name!r} refused: argument {i} is "
                                    f"{type(arg).__name__}, not a string"
                                )
                                return f"Error: All arguments must be strings. Argument {i} is {type(arg).__name__}: {arg}"

                except json.JSONDecodeError as e:
                    logger.warning(f"Predefined script {script_name!r} refused: script_args is not valid JSON - {e}")
                    return f"Error: Invalid JSON in script_args: {e}"

                # Chooses an interpreter only where Windows needs one, after the existing script-name, permission, and argument validation.
                try:
                    command = predefined_script_command(script_path)
                except ValueError as e:
                    # Gives the MCP caller a setup fix instead a launch error.
                    logger.warning(f"Predefined script {script_name!r} refused: {e}")
                    return f"Error: {e}"

                # Executes the external script with arguments.
                # The helper handles Windows quoting while keeping argument values literal (shell=False).
                logger.info(
                    f"Running predefined script {script_name!r} in tab {tab_id} "
                    f"with {format_script_args_for_log(args_list)}"
                )
                started_at = time.monotonic()
                result = run_predefined_script(command, args_list)
                elapsed = time.monotonic() - started_at

                if result.returncode != 0:
                    logger.warning(
                        f"Predefined script {script_name!r} exited {result.returncode} "
                        f"after {elapsed:.1f}s: {result.stderr.strip()!r}"
                    )
                    return format_failed_script_reply(
                        script_name, result.returncode, result.stdout, result.stderr
                    )

                # The script output should be JavaScript code
                javascript_code = result.stdout.strip()
                if not javascript_code:
                    logger.warning(f"Predefined script {script_name!r} produced no output after {elapsed:.1f}s")
                    return f"Error: Script '{script_name}' produced no output"

                # Log the size, never the JavaScript itself - a generated
                # DOM-walking script runs to tens of kilobytes and would bury
                # every other line in the log.
                logger.info(
                    f"Predefined script {script_name!r} generated {len(javascript_code)} bytes "
                    f"of JavaScript in {elapsed:.1f}s; injecting into tab {tab_id}"
                )

                # Now execute the generated JavaScript in the tab
                request = {
                    "id": str(uuid.uuid4()),
                    "type": "request",
                    "action": "content.execute_script",
                    "data": {
                        "tabId": tab_id,
                        "script": javascript_code
                    },
                    "timestamp": datetime.now().isoformat()
                }

                response = await self._send(profile_id, request)

                if "error" in response:
                    logger.warning(
                        f"Predefined script {script_name!r} failed in tab {tab_id}: {response['error']}"
                    )
                    return f"Error executing generated script: {response['error']}"

                if response.get("type") == "response" and "data" in response:
                    result_data = response["data"].get("result")
                    url = response["data"].get("url", "Unknown URL")

                    # The URL is the point of this line: it says which page the
                    # script actually ran against, which the tab id alone does
                    # not - the tab may have navigated since the caller chose it.
                    logger.info(f"Predefined script {script_name!r} completed in tab {tab_id} ({url})")

                    if result_data is None:
                        return f"Predefined script '{script_name}' executed successfully in tab {tab_id} ({url}) - no return value"

                    return f"Predefined script '{script_name}' result from tab {tab_id} ({url}):\n{result_data}"
                elif response.get("type") == "error":
                    error_msg = response.get("data", {}).get("message", "Unknown error")
                    logger.warning(
                        f"Predefined script {script_name!r} failed in tab {tab_id}: {error_msg}"
                    )
                    return f"Failed to execute generated script: {error_msg}"

                return f"Unable to execute generated script in tab {tab_id}"

            except subprocess.TimeoutExpired:
                logger.warning(f"Predefined script {script_name!r} timed out after 30 seconds and was killed")
                return f"Error: Script '{script_name}' timed out after 30 seconds"
            except subprocess.SubprocessError as e:
                logger.warning(f"Predefined script {script_name!r} could not be run: {e}")
                return f"Error executing script '{script_name}': {e}"
            except Exception as e:
                logger.exception(f"Predefined script {script_name!r} raised an unexpected error")
                return f"Unexpected error running script '{script_name}': {e}"

    def _remember_monitor_owner(self, profile_id, monitor_id, connection_id):
        """Tie a monitor just started to the MCP client that asked for it

        The server stops a client's monitors when that client disconnects, and
        this is where it learns whose they are. Every monitor is recorded, session
        or no session: one started outside a transport has no client to outlive it
        and is never reaped, but a monitor missing from the registry altogether is
        taken for a stray and stopped on sight.
        """
        if not monitor_id:
            return

        register = getattr(self.websocket_server, 'register_monitor', None)
        if register is None:
            return

        try:
            from fastmcp.server.dependencies import get_context
            session_id = get_context().session_id
        except Exception:
            # Reached in-process rather than over a transport, as the test harness
            # does. register_monitor records its own marker for that.
            session_id = None

        register(profile_id, monitor_id, session_id, connection_id)

    def _setup_request_monitoring_tools(self):
        """Setup web request monitoring tools"""

        @self._tool()
        async def requests_start_monitoring(
            profile_id: int,
            url_patterns: List[str],
            options: Optional[Dict[str, Any]] = None,
            tab_id: Optional[int] = None
        ) -> str:
            """
            Start monitoring web requests

            Returns JSON containing a **monitor_id**. Keep it — requests_list_captured,
            requests_get_content and requests_stop_monitoring all take it, so losing it
            leaves the monitor running with no way to read or stop it.

            Args:
                url_patterns: List of URL patterns to monitor (e.g., ["https://api.example.com/*", "*/api/*"])
                options: Optional configuration for monitoring:
                    - capture_response_bodies: bool (default: True)
                    - max_body_size: int (default: 50000) — bytes kept per body; the
                      full size is reported either way
                    - content_types_to_capture: List[str] (default: ["application/json", "text/plain"])
                      — a body comes back as text only if its content type matches one
                      of these and is text to begin with
                tab_id: Optional tab ID to monitor (if not provided, monitors all tabs)

            Returns:
                JSON string with monitor_id and status information
            """
            if not url_patterns:
                return json.dumps({"error": "url_patterns is required"})

            # Set default options
            default_options = {
                "capture_request_bodies": True,
                "capture_response_bodies": True,
                "max_body_size": 50000,
                "content_types_to_capture": ["application/json", "text/plain"],
                "sensitive_headers": ["Authorization", "Cookie"]
            }

            if options:
                default_options.update(options)

            request_data = {
                "url_patterns": url_patterns,
                "options": default_options
            }

            if tab_id is not None:
                request_data["tab_id"] = tab_id

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.start_monitoring",
                "data": request_data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return json.dumps({"error": f"Failed to start monitoring: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                self._remember_monitor_owner(profile_id, response["data"].get("monitor_id"), response.get("connection_id"))
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to start monitoring: {error_msg}"})

            return json.dumps({"error": "Unable to start monitoring"})

        @self._tool()
        async def requests_stop_monitoring(
            profile_id: int,
            monitor_id: str,
            drain_timeout: int = 5
        ) -> str:
            """
            Stop monitoring web requests with graceful drainage

            Args:
                monitor_id: ID of the monitoring session to stop
                drain_timeout: Accepted and ignored; the monitor stops at once

            Returns:
                JSON string with stop status and statistics
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.stop_monitoring",
                "data": {
                    "monitor_id": monitor_id,
                    "drain_timeout": drain_timeout
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return json.dumps({"error": f"Failed to stop monitoring: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                forget = getattr(self.websocket_server, 'forget_monitor', None)
                if forget:
                    forget(profile_id, monitor_id, response.get("connection_id"))
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to stop monitoring: {error_msg}"})

            return json.dumps({"error": "Unable to stop monitoring"})

        @self._tool()
        async def requests_list_captured(profile_id: int, monitor_id: str) -> str:
            """
            List all captured request summaries from a monitoring session

            A request appears here once it has completed, so a page navigation
            started a moment ago will not be in the list yet.

            Args:
                monitor_id: ID of the monitoring session

            Returns:
                JSON string with captured request summaries
            """
            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.list_captured",
                "data": {
                    "monitor_id": monitor_id
                },
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return json.dumps({"error": f"Failed to list captured requests: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to list captured requests: {error_msg}"})

            return json.dumps({"error": "Unable to list captured requests"})

        @self._tool()
        async def requests_get_content(
            profile_id: int,
            monitor_id: str,
            request_id: str,
            include_binary: bool = False,
            save_request_body_to: Optional[str] = None,
            save_response_body_to: Optional[str] = None
        ) -> str:
            """
            Get full request/response content for a specific request

            The response carries **response_body.included** and **note**: a body that
            was not text, or not one of the monitored content types, comes back with
            `content: null` and its size filled in. `request_headers` is always empty.

            Args:
                monitor_id: ID of the monitoring session
                request_id: ID of the specific request
                include_binary: Accepted and ignored; binary bodies never come back
                save_request_body_to: Accepted and ignored; nothing is written to disk
                save_response_body_to: Accepted and ignored; nothing is written to disk

            Returns:
                JSON string with full request/response content
            """
            request_data = {
                "monitor_id": monitor_id,
                "request_id": request_id,
                "include_binary": include_binary
            }

            if save_request_body_to:
                request_data["save_request_body_to"] = save_request_body_to
            if save_response_body_to:
                request_data["save_response_body_to"] = save_response_body_to

            request = {
                "id": str(uuid.uuid4()),
                "type": "request",
                "action": "requests.get_content",
                "data": request_data,
                "timestamp": datetime.now().isoformat()
            }

            response = await self._send(profile_id, request)

            if "error" in response:
                return json.dumps({"error": f"Failed to get request content: {response['error']}"})

            if response.get("type") == "response" and "data" in response:
                return json.dumps(response["data"])
            elif response.get("type") == "error":
                error_msg = response.get("data", {}).get("message", "Unknown error")
                return json.dumps({"error": f"Failed to get request content: {error_msg}"})

            return json.dumps({"error": "Unable to get request content"})

    def get_mcp_app(self):
        """Get the FastMCP application instance"""
        return self.mcp
