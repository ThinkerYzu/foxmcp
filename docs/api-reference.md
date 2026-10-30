# FoxMCP API Reference

Complete reference for all MCP tools and browser functions available through FoxMCP.

## Available MCP Tools

All 46 tools are offered by default. Each section below corresponds to a *group*
that `--disable-tools` can leave unregistered, which is how you shrink what an MCP
client carries in its context. The group name is the tool-name prefix, not the
heading: Tab Management is `tabs`, Web Request Monitoring is `requests`, Debugging
Tools is `debug`. Window Management is the exception: its group is `windows`, but
its tools are named `create_window`, `list_windows` and so on. `--enable-tools` takes the tool names below, for keeping one
tool out of a group you disabled. See
[configuration.md](configuration.md#reducing-the-tool-surface) for the full list
and what each group costs.

### Firefox Profiles

`profiles_list(populate=True)` returns an object with a `profiles` array. Each entry
contains `profile_id`, `name`, `name_error`, `extension_version`, and `windows`.
Windows include their tabs, titles and URLs when `populate=True`. A window-query
failure is returned as that profile's `error`, without hiding other profiles.

Every browser tool below requires `profile_id`, even when only one profile is
connected. `profiles_list` and `debug_websocket_status` need no target. IDs for
tabs, windows, groups, containers and monitors belong to their selected profile.
Names are labels, may repeat, and cannot substitute for a routing ID.

| Profile field | Meaning |
|---|---|
| `profile_id` | Server-assigned positive integer target, unique during the server lifetime; replaced on every reconnect. |
| `name` | Local Firefox name, or `null` when unavailable or ambiguous. |
| `name_error` | Name-resolution explanation, or `null` on success. |
| `extension_version` | Reported extension release version, or `null` when unavailable. |
| `windows` | Profile windows, populated with tabs/titles/URLs when requested. |
| `error` | Present when querying this profile's windows failed; other profiles remain listed. |

There is no active-profile setting, `profiles_select` tool or implicit fallback.
A missing/disconnected target fails. Rediscover after any connection loss or
server restart before reusing native object IDs. Both halves must support
protocol 4. IDs are scoped to the server lifetime, so do not persist them as
permanent Firefox profile identifiers.

Names are read from Firefox's local metadata on the server machine. Registered
`profiles.ini` names take precedence, preserving their spelling and case; the
profile-manager database supplies names for profiles without an INI name. On
Linux, a unique held profile lock distinguishes a running profile from stale
copies sharing its extension UUID. Multiple running candidates or unavailable
activity evidence leave duplicate matches ambiguous. Temporary,
inaccessible or ambiguous profiles have `name=null` and an explicit `name_error`;
they remain usable by ID. Names refresh on discovery and need not be unique.
Discovery requires the server to have access to the browser profile files; it
does not rely on an extension-supplied name or a user-entered label.

### Tab Management
- `tabs_list(profile_id, window_id=None, cookie_store_id=None)` - List tabs with optional
  window and cookie-store filters, applied together
  - Each line includes `[window {window_id}, index {index}]` followed by
    `[cookie store {cookie_store_id}]`; the index counts from 0
  - Store metadata from an older extension is reported as unavailable. An
    unverifiable store filter fails instead of returning an unfiltered listing.
- `tabs_create(profile_id, url, active=True, pinned=False, window_id=None, cookie_store_id=None)`
  - Create a tab, optionally selecting a window and cookie store
  - Reports the actual store. Explicit selection requires an updated extension
    and never falls back to the default store.
- `tabs_close(profile_id, tab_id)` - Close specific tab
- `tabs_switch(profile_id, tab_id)` - Switch to specific tab
- `tabs_move(profile_id, tab_ids, window_id=None, index=-1)` - Move tabs to a position, optionally into another window
  - `tab_ids` takes one ID, a list, or a JSON string such as `"[12, 15]"`
  - `index` is the destination, counting from 0; `-1` is the end
  - Without `window_id`, tabs are reordered within the window they are in
  - Reports `Moved {n} of {m}` — Firefox refuses some moves silently, chiefly moving an
    unpinned tab in front of a pinned one, and a refused tab is absent from the result
- `tabs_group(profile_id, tab_ids, group_id=None, title=None, color=None)` - Group tabs into a new group, or into an existing one
  - Without `group_id`, the new group goes in the first tab's window, and tabs from other
    windows move there
  - Reports `Tabs grouped into group {id}`; see [Tab groups](#tab-groups)
- `tabs_ungroup(profile_id, tab_ids)` - Take tabs out of their group
- `tabs_groups_update(profile_id, group_id, title=None, color=None, collapsed=None)` - Change a group's title, colour or collapsed state
- `tabs_groups_query(profile_id, window_id=None, title=None, color=None, collapsed=None)` - List tab groups and their IDs
- `tabs_capture_screenshot(profile_id, filename=None, window_id=None, format="png", quality=90, tab_id=None)` - Capture screenshot of the visible tab, or of one given tab
  - If `filename` provided: saves screenshot to file and returns success message
  - If `filename` omitted: returns base64 encoded image data URL
  - Automatically adds file extension (.png/.jpeg) if not provided
  - Without `tab_id`, it is the tab a window is showing (`window_id`, or the current window)
  - With `tab_id`, that tab is captured wherever it is: a background tab, or one in a window that is
    not in front, and nothing is switched. Not together with `window_id`. Needs an extension that
    has `tabs.captureTab`; an older one answers that it is too old

### Firefox Containers

- `containers_list(profile_id)` returns JSON with `containers` (named identities with
  `cookie_store_id`, `name`, `color`, `icon`) and `default_cookie_store_id`.
- `containers_create(profile_id, name, color="blue", icon="fingerprint")` returns
  `{container: {cookie_store_id, name, color, icon}}` as JSON.
- `containers_update(profile_id, cookie_store_id, name=None, color=None, icon=None)` requires
  at least one property; unspecified properties and identity are preserved.
- `containers_remove(profile_id, cookie_store_id)` returns `{removed: true, cookie_store_id}`.
  Refuses open tabs (`CONTAINER_IN_USE` with `tab_ids`) and default/private stores.
  Removal clears stored site data. The open-tab check cannot exclude races with
  browser UI or other extensions. Containers are never cleaned up on disconnect.

Use opaque IDs from discovery, not names or numeric suffixes. Names may repeat;
IDs belong to the connected profile. `firefox-default` selects normal browsing;
`firefox-private` can only filter listings with existing private access. Explicit
store creation into a private window is refused. Omission preserves existing tab
creation behavior. Invalid/deleted selections fail without opening a fallback tab.
Older extensions must be updated for explicit selection and verified filtering.
Existing tabs cannot change containers in place. Other tools continue by tab ID.

The `containers` group is enabled by default and supports `--disable-tools` and
`--enable-tools`. Disabling discovery does not prevent tab tools from accepting
known store IDs. Required `cookies` permission supports store selection/query;
there are no cookie export/edit tools. Installation can enable Firefox containers;
subsequent user disabling is respected. History and bookmarks remain shared.

### History Operations
- `history_query(profile_id, query, max_results=50)` - Search browser history
- `history_get_recent(profile_id, count=10)` - Get recent history items
- `history_delete_item(profile_id, url)` - Delete specific history item

### Bookmark Management
- `bookmarks_list(profile_id, folder_id=None)` - List bookmarks from all folders or a specific folder
  - Returns formatted text with folder (📁) and bookmark (🔖) entries
  - Each item includes unique ID, parent folder ID, and index (position within the parent, from 0)
  - When `folder_id` is provided, returns only direct children of that folder, in order
- `bookmarks_search(profile_id, query)` - Search bookmarks by title or URL
  - Returns formatted text with matching bookmark entries including ID and parent folder ID
- `bookmarks_create(profile_id, title, url, parent_id=None)` - Create bookmark
- `bookmarks_create_folder(profile_id, title, parent_id=None)` - Create bookmark folder
- `bookmarks_update(profile_id, bookmark_id, title=None, url=None)` - Update bookmark or folder title/URL
- `bookmarks_move(profile_id, bookmark_id, parent_id=None, index=None)` - Move a bookmark or folder into another folder, or to another position
  - Needs at least one of `parent_id` and `index`; the bookmark keeps its ID
  - `index` is the final position, counting from 0; omitted, the item goes to the end of the folder
- For `bookmarks_create`, `bookmarks_create_folder` and `bookmarks_move`, `parent_id` must be a folder; a bookmark or separator ID is refused
- `bookmarks_delete(profile_id, bookmark_id)` - Delete bookmark

### Navigation Control
- `navigation_back(profile_id, params)` - Navigate back in tab
- `navigation_forward(profile_id, params)` - Navigate forward in tab
  - For back/forward, `params` is an object such as `{"tab_id": 12}`.
- `navigation_reload(profile_id, tab_id, bypass_cache=False)` - Reload tab
- `navigation_go_to_url(profile_id, tab_id, url)` - Navigate to URL

### Content Access

`content_load_file` includes a short handle-lookup snippet and Firefox page-cloning guidance
in its MCP description. See [Loading local files](scripts.md#loading-local-files)
for the complete input-assignment example and transfer details.

- `content_load_file(profile_id, tab_id, path, mime_type=None)` - Load one regular local file into the tab's extension-isolated JavaScript scope. Returns JSON with `file_id`, `name` (basename only), `type`, `size`, `lastModified` and `expires_in_seconds` (300). Use `globalThis.foxmcpFiles.get(file_id)` from `content_execute_script` or a predefined script, and delete the entry after use. MIME is inferred from the filename unless overridden, with `application/octet-stream` as the fallback. Does not select an input or submit a form. Private tabs are refused. See [Loading local files](scripts.md#loading-local-files).
- `content_get_text(profile_id, tab_id, max_length=None)` - Extract page text content
  - `max_length`: Optional maximum length of text to return (default: unlimited)
- `content_get_html(profile_id, tab_id)` - Get page HTML source
- `content_execute_script(profile_id, tab_id, code)` - Execute JavaScript directly
- `content_execute_predefined(profile_id, tab_id, script_name, script_args="")` - Execute predefined external scripts

### Web Request Monitoring
- `requests_start_monitoring(profile_id, url_patterns, options=None, tab_id=None)` - Start monitoring web requests
  - `url_patterns`: List of URL patterns to monitor (e.g., `["https://api.example.com/*", "*/api/*"]`)
  - `options`: Optional configuration dict with capture settings
  - `tab_id`: Optional tab ID to monitor (if not provided, monitors all tabs)
  - Returns JSON with `monitor_id` and monitoring status
- `requests_stop_monitoring(profile_id, monitor_id, drain_timeout=5)` - Stop monitoring
  - `monitor_id`: ID of the monitoring session to stop
  - `drain_timeout`: **ignored** — the monitor stops immediately
  - Returns JSON with stop status and statistics
  - Captured data outlives the monitor: the two tools below still answer afterwards
- `requests_list_captured(profile_id, monitor_id)` - List captured request summaries
  - Returns JSON with array of request summaries (metadata only, no full content)
  - A request appears once it has completed, so a navigation started a moment ago
    is not in the list yet
  - `MONITOR_NOT_FOUND` for an id that never existed or has been cleared. Monitors
    are cleared when the client that started them disconnects, and when the
    extension loses its connection to the server
- `requests_get_content(profile_id, monitor_id, request_id, include_binary=False, save_request_body_to=None, save_response_body_to=None)` - Get full request/response content
  - `include_binary`: **ignored** — non-text bodies never come back as content, only as a size
  - `save_request_body_to`, `save_response_body_to`: **ignored** — `saved_to_file` is always `null`
  - Returns JSON with response headers and both bodies. `request_headers` is always
    empty: no listener collects them

See [web-request-monitoring.md](web-request-monitoring.md) for the options, the
pattern syntax, where captured data lives, and the full list of parameters that are
accepted and ignored.

#### What response body capture actually delivers

The `webRequest` API does not expose response bodies, so the extension taps the
response stream itself with `webRequest.filterResponseData`. That covers every
matching request, the document load included, and Firefox has already undone any
`Content-Encoding` by the time the bytes arrive — so what you get back is the
real body, not a compressed one.

**You get a body only if you asked for its content type.** `content` is filled
in when the response is text *and* its content type matches
`content_types_to_capture` — which defaults to
`["application/json", "text/plain"]`. An HTML page therefore returns no content
unless you pass `content_types_to_capture: ["text/html"]`. Binary responses
never return content, whatever you pass. In every one of these cases `included`
is `false`, `content` is `null`, and `note` says which reason applied.

**`size_bytes` is the whole body, even when `content` is not.** It counts the
bytes Firefox delivered, so it is right for a body dropped for its content type
and right for one cut short by `max_body_size`; `truncated` is what tells you
the `content` you were given is short of `size_bytes`. It is not read from
`Content-Length`, which compressed HTTP/2 responses routinely omit. `size_bytes` is `null` only when the response could
not be tapped at all: monitoring did not ask for bodies, or Firefox refused the
filter, which it does for a redirect and for a response served from its
alternate-data cache.

`requests_list_captured` is unaffected by any of this. Request metadata comes
from `webRequest` and is captured for every matching request.

### Window Management
- `list_windows(profile_id, populate=True)` - List all browser windows with optional tab details
- `get_window(profile_id, window_id, populate=True)` - Get specific window information
- `get_current_window(profile_id, populate=True)` - Get current active window
- `create_window(profile_id, url=None, window_type="normal", state="normal", focused=True, width=None, height=None, top=None, left=None, incognito=False)` - Create new browser window
  - Firefox always focuses a new window; with `focused=False`, focus goes back to the
    window that had it. The result ends in `(focused)` if the new window has focus
- `close_window(profile_id, window_id)` - Close specific window
- `focus_window(profile_id, window_id)` - Bring window to front and focus it
- `update_window(profile_id, window_id, state=None, focused=None, width=None, height=None, top=None, left=None)` - Update window properties
  - `focused=False` is refused: Firefox cannot take focus away from a window. Call
    `focus_window` on the window that should have it

### Debugging Tools
- `debug_websocket_status()` - Check browser extension connection status

## Usage Examples

The examples use an already connected FastMCP `client`. Inspect discovery, then
choose a profile ID for the task. Do not automatically choose the first entry
when several profiles are connected.

```python
import json
import re

discovery = await client.call_tool("profiles_list", {"populate": True})
profiles = json.loads(discovery.content[0].text)["profiles"]
print(profiles)
profile_id = 1  # Use the integer returned by profiles_list().
```

Use that same `profile_id` with IDs discovered in that profile in the following
examples. Replace illustrative tab/window/bookmark IDs with actual results.

### Basic Tab Operations
```python
# List all tabs
tabs = await client.call_tool("tabs_list", {"profile_id": profile_id})

# Create new tab
result = await client.call_tool("tabs_create", {"profile_id": profile_id, "url": "https://example.org"})

# Take screenshot
screenshot = await client.call_tool("tabs_capture_screenshot", {"profile_id": profile_id, "format": "png"})
```

### Gathering Tabs Into Their Own Window
```python
# Find the tabs to gather. Every window is listed, and each line ends with
# "[window {id}, index {n}]", so the tab IDs can be picked out of the listing.
listing = await client.call_tool("tabs_list", {"profile_id": profile_id})

# Open the window they are going to
window = await client.call_tool("create_window", {"profile_id": profile_id, "url": "about:blank"})
window_id = int(re.search(r'ID (\d+)', window.content[0].text).group(1))

# Move them in, keeping the given order, appended at the end
await client.call_tool("tabs_move", {"profile_id": profile_id, "tab_ids": [12, 15, 18], "window_id": window_id})

# Confirm they arrived, and nothing else came along
await client.call_tool("tabs_list", {"profile_id": profile_id, "window_id": window_id})
```

The new window opens with a blank tab of its own, which stays until closed with
`tabs_close`. Its ID is in the scoped `tabs_list` above.

### Reordering Tabs
```python
# Move one tab to the front of its window
await client.call_tool("tabs_move", {"profile_id": profile_id, "tab_ids": 12, "index": 0})

# Move several to the end, in the order given
await client.call_tool("tabs_move", {"profile_id": profile_id, "tab_ids": [12, 15], "index": -1})
```

### History and Bookmarks
```python
# Search history
history = await client.call_tool("history_query", {"profile_id": profile_id, "query": "python", "max_results": 10})

# List bookmarks
bookmarks = await client.call_tool("bookmarks_list", {"profile_id": profile_id})

# Create bookmark
bookmark = await client.call_tool("bookmarks_create", {
    "profile_id": profile_id,
    "title": "Example Site",
    "url": "https://example.org"
})

# Create bookmark folder
folder = await client.call_tool("bookmarks_create_folder", {
    "profile_id": profile_id,
    "title": "My Projects"
})

# Create bookmark in folder
bookmark = await client.call_tool("bookmarks_create", {
    "profile_id": profile_id,
    "title": "Project Repository",
    "url": "https://github.com/example/project",
    "parent_id": "folder_id_here"
})

# Update bookmark title
await client.call_tool("bookmarks_update", {
    "profile_id": profile_id,
    "bookmark_id": "bookmark_id_here",
    "title": "New Title"
})

# Update bookmark URL
await client.call_tool("bookmarks_update", {
    "profile_id": profile_id,
    "bookmark_id": "bookmark_id_here",
    "url": "https://example.org/new"
})

# Rename a folder
await client.call_tool("bookmarks_update", {
    "profile_id": profile_id,
    "bookmark_id": "folder_id_here",
    "title": "Renamed Folder"
})

# Move a bookmark to the top of another folder
await client.call_tool("bookmarks_move", {
    "profile_id": profile_id,
    "bookmark_id": "bookmark_id_here",
    "parent_id": "folder_id_here",
    "index": 0
})
```

### Content Interaction
```python
# Get page text (unlimited)
text = await client.call_tool("content_get_text", {"profile_id": profile_id, "tab_id": 123})

# Get page text with length limit
text = await client.call_tool("content_get_text", {
    "profile_id": profile_id,
    "tab_id": 123,
    "max_length": 1000
})

# Execute JavaScript
result = await client.call_tool("content_execute_script", {
    "profile_id": profile_id,
    "tab_id": 123,
    "code": "document.title"
})
```

### Window Management
```python
# List all windows
windows = await client.call_tool("list_windows", {"profile_id": profile_id, "populate": True})

# Create new window
window = await client.call_tool("create_window", {
    "profile_id": profile_id,
    "url": "https://example.org",
    "width": 800,
    "height": 600
})

# Focus window
await client.call_tool("focus_window", {"profile_id": profile_id, "window_id": 456})
```

### Tab groups

These are Firefox's own tab groups, and need Firefox 139 or later. None of the
four tools activates a tab or focuses a window.

```python
tabs_group(profile_id=profile_id, tab_ids=[12, 15], title="Research", color="blue")
# Tabs grouped into group 1789744400280043
tabs_group(profile_id=profile_id, tab_ids=18, group_id=1789744400280043)
tabs_groups_query(profile_id=profile_id, window_id=1)
# Tab groups (1 found):
# - ID 1789744400280043: Research - blue [window 1]
```

Group IDs are large numbers, not small counters like tab IDs. `tabs_group` reports
one only when it creates the group; `tabs_groups_query` finds any other.

Colours are `blue`, `cyan`, `grey`, `green`, `orange`, `pink`, `purple`, `red` and
`yellow`. Omitting `title` or `color` leaves it as it is, and `title=""` clears it.

Grouping and styling are two calls to Firefox. If the tabs are grouped but the title
or colour cannot be set, `tabs_group` still reports the group, and says what failed:

```
Tabs grouped into group 1789744400280043, but its title/colour could not be set:
<reason>. Retry the styling with tabs_groups_update.
```

What Firefox does on its own:
- A pinned tab is unpinned before it is grouped.
- Private and non-private tabs cannot share a group; the call fails.
- A group whose last tab leaves it is deleted.

For WebSocket protocol details, see [protocol.md](protocol.md).
