# WebSocket Message Protocol

## Profile connections (protocol ID 3)

Multiple Firefox profiles connect concurrently at `/`. A new profile never closes
another profile's connection. Every browser request names an explicit `profile_id`;
window, tab, group, container, bookmark and monitor IDs are local to that profile.
There is no global current profile or automatic fallback to another profile.

The server assigns an increasing positive integer `profile_id` to each accepted
connection, starting at 1. IDs are never reused during a server lifetime. Every
reconnect gets a new ID; callers must rediscover targets. A server restart resets
the sequence and invalidates previous MCP sessions and cached targets.

The server sends `hello` with `data.version` and `data.protocol_version`. Within
five seconds the extension sends:

```json
{"type":"hello","data":{"version":"1.6.0","protocol_version":3}}
```

After registration the server sends `{"type":"ready","data":{}}`.
The extension never generates, stores or receives `profile_id`. The server strips
this routing field from commands before sending them to Firefox. Malformed,
missing or incompatible handshakes close with code 1008 and an update instruction.
Both extension and server must support ID 3.

Each socket owns its pending replies and monitors. Disconnecting one profile
fails only that profile's requests and removes only its monitor records. Replies
from an old socket cannot complete a request on a new socket. No request is replayed.

## Discovery and proxy routes

The configured extension port also serves local clients:

| Route | Purpose | Access |
|---|---|---|
| `/` | Existing Firefox extension WebSocket | `moz-extension://` Origin required |
| `/discovery` | HTTP GET identifying the forwarding protocol | Origin headers refused |
| `/proxy` | Browser-command WebSocket for stdio clients | Origin headers refused |

All routes require a loopback peer and exactly one well-formed Host header.
Only the literal hostnames `localhost`, `127.0.0.1` and `[::1]` are accepted
(case-insensitive), optionally followed by a decimal port from 1 to 65535.
The port may differ from the listener's port to support local TCP forwarding.
No CORS allowance is sent. Proxy connections never enter the extension handler
or replace the current extension. Local callers are trusted, as on the ordinary MCP HTTP port.

`GET /discovery` returns:

```json
{
  "server": "FoxMCP",
  "protocol_version": 3,
  "proxy_path": "/proxy",
  "pid": 1234,
  "lifetime": "automatic"
}
```

`lifetime` is `manual` for an explicitly started server. Such a server keeps its
existing lifetime when proxies disconnect. An automatically started worker stops
after its configured idle interval with no proxy connections.

After upgrading `/proxy`, the server sends the same fields with `"type": "hello"`.
Clients send browser requests in the message format below, with a nonempty string
`id`. An optional `timeout` is a positive finite number of seconds, up to 300;
the default is 30. `proxy.status` returns `data.status` describing the current
Firefox connections without sending a command to an extension.
`proxy.profiles` returns the same `data.profiles` structure as `profiles_list`;
its `data.populate` boolean defaults to true. Other browser requests require a
positive integer top-level `profile_id`, carried unchanged through `/proxy`. The ID is
routing metadata, not part of an action's `data` parameters. Missing or unavailable
IDs return an error without sending the request to any extension.

The server assigns a fresh ID before forwarding each command to Firefox, then
restores the originating client's ID in its reply. IDs may coincide across
different clients, but cannot be reused while still in flight on one connection.
Transport failures return `{"id": "original-id", "error": "description"}`;
extension responses and errors retain the structures below. Commands are never
replayed after a disconnection.

Request monitors are owned by the proxy that starts them. On disconnect, pending
requests finish before cleanup, including monitor-creation replies that arrive
after the caller has gone. Only that proxy's monitors are stopped.

<a id="script-consent-unreleased-2026-10-31"></a>

### Script consent (1.7.0)

The optional per-tab/origin gate retains protocol ID **3**. Script requests,
results and error envelopes are unchanged; no progress or cancellation message
is added. The only server behavior change is a **300-second** response timeout
for raw and predefined script tool calls, covering queue wait, approval and
execution. Other tools retain their existing timeouts. The proxy already
supports this timeout, so forwarding needs no changes.

The extension owns the approval queue and the independent **60-second** deadline
for each active prompt. Agents wait for approval or an ordinary response/error.
A long queue can exceed the five-minute overall server timeout. Client-side
call deadlines are independent, and existing caller-disconnect behavior is
unchanged. Earlier ID-3 servers can use the extension but retain shorter script
call timeouts; matching IDs do not imply the longer timeout is available.

Consent errors use the existing `type: error` envelope with `data.code`:
`SCRIPT_DENIED`, `SCRIPT_CONSENT_TIMEOUT`, `SCRIPT_CONSENT_CANCELLED` and
`SCRIPT_TARGET_CHANGED`. The cancellation code describes extension-local
invalidation, such as connection loss; it adds no transport cancellation API.
Origin-change cancellation applies to gated and not-yet-admitted jobs; an
injection admitted while consent is disabled retains ordinary script behavior.
Timeout rejects pending injections without remembering Deny. Explicit decisions
are remembered only for that tab/current origin.
See [configuration](configuration.md#script-injection-consent) for user behavior.

### Server composition refactor (2026-10-31)

The refactor alone retained protocol ID 3. Compared with released v1.6.0,
extracting `BrowserServer` and `MCPFrontend`, injecting local/remote browser
access and moving file-transfer
ownership change Python structure only. Extension and proxy handshakes, action
parameters, response/error envelopes, profile/request IDs, access checks and
monitor/worker lifetimes retain their contracts. This review does not authorize
publishing a release; repeat the complete release review before tagging.

### Profile name lookup correction (2026-10-30)

Protocol ID remains 3: preferring registered INI names and using Linux held
profile locks to disambiguate stale metadata changes only server-local label
lookup. No extension/server handshake, action, parameter, response or error
contract changes. The MCP name/name_error fields keep their existing meaning;
names remain best-effort labels and never routing keys. See
[profile selection](configuration.md#selecting-a-firefox-profile).

## Protocol ID compatibility policy

The checked protocol ID is `PROTOCOL_VERSION` in `server/browser_proxy.py`,
exposed as `protocol_version` in discovery and the proxy greeting. It identifies
the forwarding contract, including the browser API requests and responses
carried between the extension and MCP server. It is independent of the release
version in the extension's advisory `hello` announcement. Both the extension
handshake and local forwarding peers enforce this ID. The extension declares it
as `PROTOCOL_VERSION` in `extension/background.js`; pairing tests require it to
match the server contract. Popup and Options display this supported ID even
while disconnected. A connection becomes ready only after the server registers
its profile; incompatible peers are refused with an explicit update message.

Increase the protocol ID whenever an existing extension/server API is modified
or removed. This includes changes to action names, parameter types, defaults or
requiredness, response formats, error meanings and observable API behavior.
Update the implementation, protocol documentation and compatibility tests in
the same change. Adding a new API without changing existing contracts, or fixing
an implementation while preserving its contract, does not alone require a bump.

Increase at most once per release, using the previous released tag as the
baseline. Retain that released ID when existing contracts remain compatible;
otherwise use exactly the previous released ID plus one. Multiple incompatible
changes during unreleased development share this single increment. Do not
increment again for each PR, implementation step or intermediate candidate.

Before every release, review API changes since the previous released tag and
explicitly decide whether the protocol ID must increase. Record the baseline
tag, changed or removed APIs, previous/current IDs and the decision's rationale
in the release preparation record; describe any bump and affected APIs in the
changelog. Even when retaining the ID, record why no bump is required. Complete
this review before tagging or publishing; release-version consistency checks
do not replace it.

## Firefox container contract (protocol ID 2)

ID 2 adds `cookieStoreId` to serialized `tabs.list` records and an optional
`data.cookieStoreId` query filter, combined with `windowId`. Missing metadata
from an older extension is unavailable, never assumed to be the default store.
A selected-store listing must verify every returned record's store.

`tabs.create` retains its existing payload and defaults. Explicit store selection
uses **`tabs.create_in_store`**, with the same fields plus a required nonempty
string `cookieStoreId`. Validate the current identity and target window before
opening the URL. Never fall back, retry creation, or report success when the
returned tab's store differs. An old extension's unknown-action error requires
an extension update, without opening any tab. Private-store selection for
creation is refused, as is named/default selection into a private window.

The `containers` namespace uses required `contextualIdentities` and `cookies`
permissions. IDs are opaque, profile-scoped strings; duplicate display names
are valid. Default (`firefox-default`) and private (`firefox-private`) stores
are not named identities. Responses contain:

| Action | Request data | Response data |
|---|---|---|
| `containers.list` | `{}` | `{containers: [{cookie_store_id, name, color, icon}], default_cookie_store_id: "firefox-default"}` |
| `containers.create` | `{name, color, icon}` | `{container: {cookie_store_id, name, color, icon}}` |
| `containers.update` | `{cookieStoreId, name?, color?, icon?}` | `{container: {cookie_store_id, name, color, icon}}` |
| `containers.remove` | `{cookieStoreId}` | `{removed: true, cookie_store_id}` |

Update requires at least one property. Firefox's supported styling values are
authoritative; use feature detection for its newer enumeration APIs. Removal
rejects default/private stores and identities with open tabs, returning
`details.tab_ids`. It clears stored container data, and its open-tab precheck
cannot be atomic with browser UI or other extensions. Containers persist across
client disconnects and worker restarts; no automatic container cleanup occurs.

Errors: `INVALID_PARAMETER`, `UNSUPPORTED_API`, `CONTAINERS_UNAVAILABLE`,
`CONTAINER_NOT_FOUND`, `CONTAINER_IN_USE`, and unexpected `API_ERROR`.
Availability is probed with `contextualIdentities.query`, never by changing
preferences. Firefox exposes no structured disabled-feature error: recognize
its fixed, nonlocalized implementation message (Mozilla's `checkAPIEnabled`),
and preserve unknown failures as `API_ERROR`. Do not match translated text.

Historical v1.5.0 compatibility review against v1.4.0: checked ID increased
from 1 to 2 for the
existing tab-list response and filter contract. New lifecycle actions alone do
not require a further bump. Extension/server release matching remains advisory;
only forwarding peers enforced ID 2 in that release. Current source requires
the protocol-3 profile handshake described above. The complete v1.5.0 review is recorded in
[release preparation](../RELEASES.md#protocol-compatibility-review), including
other changes since the baseline. Reassess if the final diff changes before
publishing. See the [compatibility policy](#protocol-id-compatibility-policy).

## Connection version announcement

The mandatory profile handshake above also carries each peer's release version.
The extension reads its manifest; the Python server uses `server/version.py`.
Release-version equality remains advisory, independently of the checked protocol ID:
compatible protocol-3 peers keep serving tools even when release versions differ.
The server logs a mismatch and both settings views display it, preserving unsaved settings
while refreshing. Numeric versions contain one to four dot-separated components
and at most 64 characters. Invalid or absent release versions remain unavailable;
they do not bypass or invalidate the mandatory profile/protocol handshake.

Both settings views display an incompatible-protocol close reason. The extension
stops retrying that peer. Update both components and reload the extension to
register again, or change the effective endpoint. There is no manual Reconnect
button. Transient disconnects retain the normal constant-interval retry policy
and preserve the running extension's profile ID.

## Message Structure

Browser requests and their replies follow this JSON structure (the standalone
`hello` announcement above has no request ID, action or timestamp):
```json
{
  "id": "unique-request-id",
  "type": "request|response|error", 
  "action": "function_name",
  "data": {...},
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

## Request/Response Examples

### 1. History Management

#### Query History
**Request:**
```json
{
  "id": "req_001",
  "type": "request",
  "action": "history.query",
  "data": {
    "query": "github",
    "maxResults": 50,
    "startTime": "2025-09-01T00:00:00.000Z",
    "endTime": "2025-09-03T23:59:59.000Z"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_001",
  "type": "response",
  "action": "history.query",
  "data": {
    "items": [
      {
        "id": "hist_123",
        "url": "https://github.com/user/repo",
        "title": "GitHub Repository",
        "lastVisitTime": 1693664400000,
        "visitCount": 5
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

**Note:** `lastVisitTime` is in milliseconds since Unix epoch (not ISO 8601 string). This matches Firefox's WebExtensions API format.
`data` holds only `items`, Firefox's `HistoryItem` records; there is no total count.

#### Get Recent History
**Request:**
```json
{
  "id": "req_002", 
  "type": "request",
  "action": "history.recent",
  "data": {
    "count": 10
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Delete History Item
**Request:**
```json
{
  "id": "req_003",
  "type": "request", 
  "action": "history.delete_item",
  "data": {
    "url": "https://example.com/page"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 2. Tab Management

#### List All Tabs

`windowId` is optional. Omit it to list the tabs of every window; supply it to list
only that window's tabs.

**Request:**
```json
{
  "id": "req_004",
  "type": "request",
  "action": "tabs.list",
  "data": {
    "windowId": 1,
    "cookieStoreId": "firefox-default"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_004",
  "type": "response", 
  "action": "tabs.list",
  "data": {
    "tabs": [
      {
        "id": 123,
        "windowId": 1,
        "url": "https://example.com",
        "title": "Example Page",
        "active": true,
        "index": 0,
        "pinned": false,
        "cookieStoreId": "firefox-default"
      },
      {
        "id": 124,
        "windowId": 1, 
        "url": "https://github.com",
        "title": "GitHub",
        "active": false,
        "index": 1,
        "pinned": false,
        "cookieStoreId": "firefox-default"
      }
    ],
    "debug": {
      "totalFound": 2,
      "tabUrls": ["https://example.com", "https://github.com"]
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

`index` is the tab's position within its window, counting from 0. It is what
`tabs.move` takes as a destination.

The optional `cookieStoreId` filter is combined with `windowId`.

#### Create New Tab
**Request:**
```json
{
  "id": "req_005",
  "type": "request",
  "action": "tabs.create", 
  "data": {
    "url": "https://example.com",
    "active": true,
    "pinned": false,
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_005",
  "type": "response",
  "action": "tabs.create",
  "data": {
    "tab": {
      "id": 125,
      "windowId": 1,
      "url": "https://example.com", 
      "title": "Loading...",
      "active": true,
      "index": 2,
      "pinned": false,
      "cookieStoreId": "firefox-default"
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

For explicit store selection, send `tabs.create_in_store` instead and add
`cookieStoreId` to `data`. The response action matches that action and the tab
includes its actual store. `tabs.create` does not accept store selection.

#### Close Tab
**Request:**
```json
{
  "id": "req_006",
  "type": "request",
  "action": "tabs.close",
  "data": {
    "tabId": 124
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Switch to Tab
**Request:**
```json
{
  "id": "req_007",
  "type": "request",
  "action": "tabs.switch",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Move Tabs

Reorders tabs within a window, or moves them into another window. `tabIds` takes a
single ID or an array; `index` is the destination position, with `-1` meaning the end.
`windowId` is optional — without it, each tab moves within the window it is already in.

**Request:**
```json
{
  "id": "req_007a",
  "type": "request",
  "action": "tabs.move",
  "data": {
    "tabIds": [123, 124],
    "windowId": 2,
    "index": -1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007a",
  "type": "response",
  "action": "tabs.move",
  "data": {
    "tabs": [
      {
        "id": 123,
        "url": "https://example.com",
        "title": "Example Page",
        "windowId": 2,
        "index": 0,
        "pinned": false
      },
      {
        "id": 124,
        "url": "https://github.com",
        "title": "GitHub",
        "windowId": 2,
        "index": 1,
        "pinned": false
      }
    ],
    "requested": 2,
    "moved": 2
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

`requested` and `moved` exist because `browser.tabs.move` refuses some moves by
returning an empty array rather than by failing — moving an unpinned tab in front of a
pinned one is the usual cause. `moved` short of `requested` means Firefox declined,
and the response is still a success. Moves that do fail outright return an `API_ERROR`:
an unknown tab ID, a target window that is not a normal window, or a move between a
private window and a non-private one.

#### Group Tabs

Puts tabs into a tab group: a new one when `groupId` is absent, created in the
window of the first tab in `tabIds`, or the existing group `groupId`. `title` and
`color` are optional and are applied after grouping. Requires Firefox 139+.

**Request:**
```json
{
  "id": "req_007b",
  "type": "request",
  "action": "tabs.group",
  "data": {
    "tabIds": [123, 124],
    "title": "Research",
    "color": "blue"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007b",
  "type": "response",
  "action": "tabs.group",
  "data": {
    "groupId": 1789744400280043
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

If the tabs were grouped but `tabGroups.update` refused the title or colour, the
response is still a success, and `data` carries `styleError` with Firefox's message
beside the `groupId`. The grouping is not undone.

#### Ungroup Tabs

Takes tabs out of whatever group they are in. Firefox deletes a group once its last
tab leaves. Requires Firefox 138+.

**Request:**
```json
{
  "id": "req_007c",
  "type": "request",
  "action": "tabs.ungroup",
  "data": {
    "tabIds": [123, 124]
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:** `data` is `{"success": true}`.

#### Update Tab Group

Changes a group's `title`, `color` or `collapsed` state; at least one is required.
Requires Firefox 139+.

**Request:**
```json
{
  "id": "req_007d",
  "type": "request",
  "action": "tabGroups.update",
  "data": {
    "groupId": 1789744400280043,
    "collapsed": true
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:** `data.group` is the updated group, as Firefox returns it.

#### Query Tab Groups

Lists tab groups. Every field of `data` is an optional filter: `windowId`, `title`,
`color`, `collapsed`. Requires Firefox 139+.

**Request:**
```json
{
  "id": "req_007e",
  "type": "request",
  "action": "tabGroups.query",
  "data": {
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007e",
  "type": "response",
  "action": "tabGroups.query",
  "data": {
    "groups": [
      {
        "id": 1789744400280043,
        "title": "Research",
        "color": "blue",
        "collapsed": false,
        "windowId": 1
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

Colours are `blue`, `cyan`, `grey`, `green`, `orange`, `pink`, `purple`, `red` and
`yellow`, in all four actions.

#### Capture Screenshot of Tab
**Request:**
```json
{
  "id": "req_007b",
  "type": "request",
  "action": "tabs.captureVisibleTab",
  "data": {
    "windowId": 1,
    "format": "png",
    "quality": 90
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007b",
  "type": "response",
  "action": "tabs.captureVisibleTab",
  "data": {
    "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "format": "png",
    "quality": 90,
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Capture Screenshot of One Tab
`tabs.captureVisibleTab` can only see the tab a window is showing. This one captures a given tab
wherever it is, a background tab included, and does not switch to it. An extension without it
answers `UNKNOWN_ACTION`.

**Request:**
```json
{
  "id": "req_007c",
  "type": "request",
  "action": "tabs.captureTab",
  "data": {
    "tabId": 123,
    "format": "png",
    "quality": 90
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_007c",
  "type": "response",
  "action": "tabs.captureTab",
  "data": {
    "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==",
    "format": "png",
    "quality": 90,
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

Both capture actions accept an optional `rect` (`{"x", "y", "width", "height"}`, CSS pixels) to
capture only a region and an optional `scale` (a finite number above 0 and up to 1) for the
image size:

```json
{"action": "tabs.captureVisibleTab", "data": {"format": "png", "quality": 90, "rect": {"x": 0, "y": 0, "width": 400, "height": 200}, "scale": 0.5}}
{"action": "tabs.captureTab", "data": {"tabId": 123, "format": "png", "quality": 90, "rect": {"x": 0, "y": 0, "width": 400, "height": 200}, "scale": 0.5}}
```

`x`, `y`, `width` and `height` must be integers, `x` and `y` at least 0 and `width` and `height`
above 0. A `rect` or `scale` that breaks these rules is an `INVALID_PARAMETER` error, not a
full-size capture. An extension older than this change ignores both fields and returns the whole
image, so a client that needs the region should check the extension version.

`tabId` must be a non-negative integer (`INVALID_PARAMETER` otherwise). A tab
that does not exist or cannot be captured is a `CAPTURE_ERROR`.

### 3. Tab Content

#### Get Page Content
**Request:**
```json
{
  "id": "req_008",
  "type": "request", 
  "action": "content.get_text",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_008", 
  "type": "response",
  "action": "content.get_text",
  "data": {
    "text": "This is the page content..."
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get HTML Content
**Request:**
```json
{
  "id": "req_009",
  "type": "request",
  "action": "content.get_html", 
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Execute Script
**Request:**
```json
{
  "id": "req_010",
  "type": "request",
  "action": "content.execute_script",
  "data": {
    "tabId": 123,
    "script": "document.title"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_010", 
  "type": "response",
  "action": "content.execute_script",
  "data": {
    "result": "My Page Title",
    "url": "https://example.com"
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Execute Predefined Script

`content_execute_predefined` is an MCP tool implemented by
[FoxMCPTools](../server/mcp_tools.py), not a separate WebSocket action. The server
validates the script name and JSON arguments, executes the configured external
program, then sends its JavaScript output through `content.execute_script` with
`data.tabId` and `data.script`, as above. The extension replies with the same
`result`/`url` fields and applies the same script-consent policy as raw scripts.
Script names, generator arguments and generator stdout are not additional
fields in the extension response.

Validation, missing-file, permission, argument and generator failures return
MCP tool text from Python without sending a browser action. For example, an
invalid name returns `Error: Invalid script name ...`; it is not a wire error
code. Generator execution has a 30-second timeout; the subsequent browser call
has a 300-second response timeout. See the [script guide](scripts.md) for the
MCP invocation and external-program contract, and
[Script consent](#script-consent-unreleased-2026-10-31) for approval errors.

#### Load a local file

`content.load_file` fetches a one-use HTTP URL in the extension background page
and delivers a File to the target tab. Python reads the local path; only its
basename reaches the browser. The URL must use `http://127.0.0.1:<port>/files/<token>`.
The transfer token is opaque and expires after 60 seconds if unused.

```json
{
  "action": "content.load_file",
  "data": {
    "tabId": 17,
    "fileId": "<uuid>",
    "url": "http://127.0.0.1:12345/files/<43-character-token>",
    "name": "report.pdf",
    "type": "application/pdf",
    "size": 10485760,
    "lastModified": 1792330000000
  }
}
```

A successful response carries `{"fileId": "<uuid>"}`. The isolated content-script
scope stores the File in `globalThis.foxmcpFiles`, indexed by that ID. It expires
after 300 seconds, or when navigation destroys the scope. Delivery fails if the
document changed during the fetch, if the fetched size differs, or if the target
tab is private. The server waits up to 120 seconds, with a 110-second fetch
timeout in the extension. Errors use the existing `API_ERROR` response format.
No file bytes travel over the WebSocket. See [scripts.md](scripts.md#loading-local-files)
for page-side use.

### 4. Navigation

#### Navigate Back
**Request:**
```json
{
  "id": "req_011",
  "type": "request",
  "action": "navigation.back",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Navigate Forward
**Request:**
```json
{
  "id": "req_012", 
  "type": "request",
  "action": "navigation.forward",
  "data": {
    "tabId": 123
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Go to URL
**Request:**
```json
{
  "id": "req_013",
  "type": "request",
  "action": "navigation.go_to_url",
  "data": {
    "tabId": 123,
    "url": "https://newsite.com"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Reload Page
**Request:**
```json
{
  "id": "req_014",
  "type": "request", 
  "action": "navigation.reload",
  "data": {
    "tabId": 123,
    "bypassCache": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 5. Window Management

#### List All Windows
**Request:**
```json
{
  "id": "req_020",
  "type": "request",
  "action": "windows.list",
  "data": {
    "populate": true
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_020",
  "type": "response",
  "action": "windows.list",
  "data": {
    "windows": [
      {
        "id": 1,
        "type": "normal",
        "state": "normal",
        "focused": true,
        "top": 100,
        "left": 150,
        "width": 1024,
        "height": 768,
        "incognito": false,
        "sessionId": "session_1",
        "tabs": [
          {
            "id": 123,
            "url": "https://example.com",
            "title": "Example Page",
            "active": true
          }
        ]
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

`populate` is optional and defaults to `true`; `false` omits each window's
`tabs` list.

#### Get Window Information
**Request:**
```json
{
  "id": "req_021",
  "type": "request",
  "action": "windows.get",
  "data": {
    "windowId": 1,
    "populate": true
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_021",
  "type": "response",
  "action": "windows.get",
  "data": {
    "window": {
      "id": 1,
      "type": "normal",
      "state": "normal",
      "focused": true,
      "top": 100,
      "left": 150,
      "width": 1024,
      "height": 768,
      "incognito": false,
      "sessionId": "session_1",
      "tabs": [
        {
          "id": 123,
          "url": "https://example.com",
          "title": "Example Page",
          "active": true,
          "index": 0
        }
      ]
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Get Current Window
**Request:**
```json
{
  "id": "req_022",
  "type": "request",
  "action": "windows.get_current",
  "data": {
    "populate": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Create New Window

Firefox focuses every new window and ignores `"focused": false`. With `false`, the
extension hands focus back to the window that had it, and the response's
`window.focused` reports where focus ended up. If no Firefox window had focus, the
new one keeps it.

**Request:**
```json
{
  "id": "req_023",
  "type": "request",
  "action": "windows.create",
  "data": {
    "url": "https://example.com",
    "type": "normal",
    "state": "normal",
    "focused": true,
    "width": 800,
    "height": 600,
    "top": 200,
    "left": 300,
    "incognito": false
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_023",
  "type": "response",
  "action": "windows.create",
  "data": {
    "window": {
      "id": 2,
      "type": "normal",
      "state": "normal",
      "focused": true,
      "top": 200,
      "left": 300,
      "width": 800,
      "height": 600,
      "incognito": false,
      "tabs": [
        {
          "id": 124,
          "url": "https://example.com",
          "title": "Loading...",
          "active": true,
          "index": 0
        }
      ]
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Close Window
**Request:**
```json
{
  "id": "req_024",
  "type": "request",
  "action": "windows.close",
  "data": {
    "windowId": 2
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_024",
  "type": "response",
  "action": "windows.close",
  "data": {
    "success": true,
    "windowId": 2
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Focus Window
**Request:**
```json
{
  "id": "req_025",
  "type": "request",
  "action": "windows.focus",
  "data": {
    "windowId": 1
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Update Window
**Request:**
```json
{
  "id": "req_026",
  "type": "request",
  "action": "windows.update",
  "data": {
    "windowId": 1,
    "state": "normal",
    "width": 1280,
    "height": 800,
    "top": 0,
    "left": 0
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

`windowId` is required. `state`, `focused`, `width`, `height`, `top` and `left`
are optional and passed to Firefox's `windows.update`.

**Response:**
```json
{
  "id": "req_026",
  "type": "response",
  "action": "windows.update",
  "data": {
    "window": {
      "id": 1,
      "type": "normal",
      "state": "normal",
      "focused": true,
      "top": 0,
      "left": 0,
      "width": 1280,
      "height": 800,
      "incognito": false
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

### 6. Bookmark Management

#### List Bookmarks
**Request:**
```json
{
  "id": "req_015",
  "type": "request",
  "action": "bookmarks.list",
  "data": {
    "folderId": "1"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_015",
  "type": "response",
  "action": "bookmarks.list", 
  "data": {
    "bookmarks": [
      {
        "id": "bm_001",
        "parentId": "1",
        "title": "GitHub",
        "url": "https://github.com",
        "isFolder": false,
        "index": 0
      },
      {
        "id": "bm_002", 
        "parentId": "1",
        "title": "Development",
        "isFolder": true,
        "index": 1
      }
    ]
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

`index` is the entry's position within its parent, counting from 0. The root
entry of a full listing has neither `parentId` nor `index`.

#### Search Bookmarks
**Request:**
```json
{
  "id": "req_016",
  "type": "request",
  "action": "bookmarks.search",
  "data": {
    "query": "github"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

#### Create Bookmark
**Request:**
```json
{
  "id": "req_017",
  "type": "request",
  "action": "bookmarks.create",
  "data": {
    "title": "New Site",
    "url": "https://newsite.com",
    "parentId": "1"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_017",
  "type": "response",
  "action": "bookmarks.create",
  "data": {
    "bookmark": {
      "id": "bm_003",
      "parentId": "1",
      "index": 4,
      "title": "New Site",
      "url": "https://newsite.com",
      "dateAdded": 1756900800000,
      "type": "bookmark"
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Create Bookmark Folder
**Request:**
```json
{
  "id": "req_017a",
  "type": "request",
  "action": "bookmarks.createFolder",
  "data": {
    "title": "My Projects",
    "parentId": "1"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_017a",
  "type": "response",
  "action": "bookmarks.createFolder",
  "data": {
    "folder": {
      "id": "bm_004",
      "parentId": "1",
      "index": 5,
      "title": "My Projects",
      "dateAdded": 1756900800000,
      "type": "folder"
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

#### Update Bookmark or Folder
**Request:**
```json
{
  "id": "req_017b",
  "type": "request",
  "action": "bookmarks.update",
  "data": {
    "bookmarkId": "bm_003",
    "title": "Updated Title",
    "url": "https://updated-site.com"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_017b",
  "type": "response",
  "action": "bookmarks.update",
  "data": {
    "bookmark": {
      "id": "bm_003",
      "parentId": "1",
      "index": 4,
      "title": "Updated Title",
      "url": "https://updated-site.com",
      "dateAdded": 1756900800000,
      "type": "bookmark"
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

**Note:** For folders, omit the `url` parameter. Either `title` or `url` (or both) must be provided.
Create, create-folder and update responses carry Firefox's own `BookmarkTreeNode`
unchanged: `type` is `bookmark`, `folder` or `separator`, and dates are
milliseconds since the Unix epoch. Only `bookmarks.list` adds an `isFolder` flag.

#### Move Bookmark or Folder
**Request:**
```json
{
  "id": "req_017c",
  "type": "request",
  "action": "bookmarks.move",
  "data": {
    "bookmarkId": "bm_003",
    "parentId": "bm_002",
    "index": 0
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_017c",
  "type": "response",
  "action": "bookmarks.move",
  "data": {
    "bookmark": {
      "id": "bm_003",
      "parentId": "bm_002",
      "index": 0,
      "title": "Updated Title",
      "url": "https://updated-site.com",
      "type": "bookmark"
    }
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

**Note:** `parentId` and `index` are each optional; the server sends at least one.
Without `parentId` the item stays in its folder; without `index` it goes to the end
of the destination. `index` is the final position, and one past the end is clamped
to the last place, so the reply's `index` is where the item landed.

**Parent must be a folder.** `bookmarks.create`, `bookmarks.createFolder` and
`bookmarks.move` answer `INVALID_PARAMETER` ("Parent bm_001 is a bookmark, not a
folder") when `parentId` names a bookmark or a separator. Firefox accepts such a
parent and the item is then listed nowhere, so the extension checks first.

#### Delete Bookmark
**Request:**
```json
{
  "id": "req_018",
  "type": "request",
  "action": "bookmarks.delete",
  "data": {
    "bookmarkId": "bm_003"
  },
  "timestamp": "2025-09-03T12:00:00.000Z"
}
```

### 7. Web Request Monitoring

Four actions, shipped in v1.1.0 and undocumented here until 2026-08-14. The
behaviour behind them — pattern matching, which options are honoured, how long
captured data lives — is in
[`web-request-monitoring.md`](web-request-monitoring.md); this section is the wire
format only.

#### Start Monitoring
**Request:**
```json
{
  "id": "req_020",
  "type": "request",
  "action": "requests.start_monitoring",
  "data": {
    "url_patterns": ["https://example.org/*"],
    "options": {
      "capture_request_bodies": true,
      "capture_response_bodies": true,
      "max_body_size": 50000,
      "content_types_to_capture": ["application/json", "text/plain"]
    },
    "tab_id": 7
  },
  "timestamp": "2026-08-14T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_020",
  "type": "response",
  "action": "requests.start_monitoring",
  "data": {
    "monitor_id": "mon_1755205412345",
    "status": "active",
    "started_at": "2026-08-14T12:00:00.000Z",
    "url_patterns": ["https://example.org/*"],
    "options": {
      "capture_request_bodies": true,
      "capture_response_bodies": true,
      "max_body_size": 50000,
      "content_types_to_capture": ["application/json", "text/plain"]
    }
  },
  "timestamp": "2026-08-14T12:00:00.100Z"
}
```

`tab_id` is optional; without it the monitor watches every tab. The server and
extension normalize omitted options to the defaults above. Both body toggles must
be booleans, `max_body_size` must be a positive integer, and content-type patterns
must be an array of nonempty strings (an empty array selects all supported text).
Unknown fields, including `sensitive_headers`, and invalid values are rejected;
the extension returns `INVALID_PARAMETER` before starting a monitor.

Request bodies and retained response prefixes obey each monitor's own policy,
including overlapping and stopped monitors. `requests.get_content` returns
`MONITOR_NOT_FOUND` for an unknown monitor and `REQUEST_NOT_FOUND` if the request
was not captured by that monitor. The global response-body cache retains up to
200 monitor/request projections; each uses its own size and content-type rules.

#### List Captured
**Request:**
```json
{
  "id": "req_021",
  "type": "request",
  "action": "requests.list_captured",
  "data": {
    "monitor_id": "mon_1755205412345"
  },
  "timestamp": "2026-08-14T12:01:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_021",
  "type": "response",
  "action": "requests.list_captured",
  "data": {
    "monitor_id": "mon_1755205412345",
    "total_requests": 1,
    "requests": [
      {
        "request_id": "1234",
        "url": "https://example.org/api/items",
        "method": "GET",
        "status_code": 200,
        "duration_ms": 118,
        "timestamp": "2026-08-14T12:00:31.221Z",
        "tab_id": 7,
        "type": "xmlhttprequest"
      }
    ]
  },
  "timestamp": "2026-08-14T12:01:00.100Z"
}
```

A request that failed also carries `error`, Firefox's network error string.

#### Get Content
**Request:**
```json
{
  "id": "req_022",
  "type": "request",
  "action": "requests.get_content",
  "data": {
    "monitor_id": "mon_1755205412345",
    "request_id": "1234",
    "include_binary": false
  },
  "timestamp": "2026-08-14T12:01:30.000Z"
}
```

**Response:**
```json
{
  "id": "req_022",
  "type": "response",
  "action": "requests.get_content",
  "data": {
    "request_id": "1234",
    "request_headers": {},
    "response_headers": {"content-type": "application/json"},
    "request_body": {
      "included": false,
      "content": null,
      "size_bytes": 0,
      "truncated": false,
      "saved_to_file": null
    },
    "response_body": {
      "included": true,
      "content": "{\"items\":[]}",
      "content_type": "application/json",
      "encoding": "utf-8",
      "size_bytes": 12,
      "truncated": false,
      "saved_to_file": null,
      "note": "Response body read from the response stream"
    }
  },
  "timestamp": "2026-08-14T12:01:30.100Z"
}
```

An unknown `request_id` is answered with `REQUEST_NOT_FOUND`. `request_headers` is
always `{}`, and `saved_to_file` is always `null`; both are described in the
reference above.

#### Stop Monitoring
**Request:**
```json
{
  "id": "req_023",
  "type": "request",
  "action": "requests.stop_monitoring",
  "data": {
    "monitor_id": "mon_1755205412345",
    "drain_timeout": 5
  },
  "timestamp": "2026-08-14T12:02:00.000Z"
}
```

**Response:**
```json
{
  "id": "req_023",
  "type": "response",
  "action": "requests.stop_monitoring",
  "data": {
    "monitor_id": "mon_1755205412345",
    "status": "stopped",
    "stopped_at": "2026-08-14T12:02:00.050Z",
    "total_requests_captured": 1,
    "statistics": {
      "duration_seconds": 120.05,
      "requests_per_second": 0.008,
      "total_data_size": 0
    }
  },
  "timestamp": "2026-08-14T12:02:00.100Z"
}
```

An unknown `monitor_id` is answered with `MONITOR_NOT_FOUND`, by
`requests.list_captured` as well as `requests.stop_monitoring`.

The server sends `requests.stop_monitoring` on its own account in two cases: for
monitors whose MCP client has disconnected, and for a monitor named in a message
from the extension that no client owns. The extension clears every monitor it holds
when the WebSocket connection closes, so nothing has to be sent for that case.

The replies to `requests.start_monitoring` and `requests.stop_monitoring` are exempt
from the second rule. One names a monitor the server is about to record, the other a
monitor it has just removed, and reading either as a stray would stop every monitor
at birth or answer each removal with another.

## Error Messages

Extension action failures use the envelope emitted by `sendError` in
[background.js](../extension/background.js). Match the original request by `id`;
error replies set `action` to the empty string. `details` defaults to an empty
object and may contain action-specific diagnostics. Browser error-message text
can vary by Firefox version and locale.

For example, a failed `tabs.close` call is wrapped as `API_ERROR`:

```json
{
  "id": "req_001",
  "type": "error",
  "action": "",
  "data": {
    "code": "API_ERROR",
    "message": "Tabs API error: Invalid tab ID: 999",
    "details": {}
  },
  "timestamp": "2025-09-03T12:00:01.000Z"
}
```

## Error Codes

These are the codes explicitly produced by the current extension action
handlers and their container/consent helpers. Python-side request failures
(such as a timeout or disconnected profile) can instead return an `error`
string to the tool layer; predefined-script validation returns MCP tool text as
described [above](#execute-predefined-script). Neither is an extension
`data.code`. Handshake refusal uses WebSocket close status 1008, not this
request-error envelope.

### Browser action errors

| Code | Meaning |
|---|---|
| `API_ERROR` | A browser API or action handler failed; the message describes the failure. |
| `UNKNOWN_ACTION` | The action namespace or operation is unsupported. |
| `INVALID_PARAMETER` | An action field is missing or has an invalid type/value. |
| `UNSUPPORTED_API` | This Firefox lacks the API or permission required for the action. |
| `CAPTURE_ERROR` | The screenshot API rejected capture of the visible or specified tab. |
| `WINDOW_NOT_FOUND` | Firefox rejected a window ID as invalid. |
| `INVALID_WINDOW_STATE` | Firefox rejected a requested window state. |
| `INVALID_WINDOW_TYPE` | Firefox rejected a requested window type. |
| `INVALID_FOLDER_ID` | The bookmark-list folder lookup failed. |
| `MONITOR_NOT_FOUND` | No request monitor exists with the supplied ID. |
| `REQUEST_NOT_FOUND` | No captured request exists with the supplied ID. |

### Script execution and consent errors

| Code | Meaning |
|---|---|
| `SCRIPT_ERROR` | Script execution failed without a more specific consent code. |
| `SCRIPT_DENIED` | The user denied script injection for this tab/origin. |
| `SCRIPT_CONSENT_TIMEOUT` | The active approval prompt expired. |
| `SCRIPT_CONSENT_CANCELLED` | The extension invalidated the pending request, including on disconnect. |
| `SCRIPT_TARGET_CHANGED` | The target origin changed, is opaque, or the tab closed. |

Disconnect invalidates pending work locally, but a closed socket cannot deliver
its error reply. These codes do not add a transport cancellation API.

### Container errors

| Code | Meaning |
|---|---|
| `CONTAINERS_UNAVAILABLE` | Firefox contextual identities are disabled. |
| `CONTAINER_NOT_FOUND` | No named container matches the supplied cookie-store ID. |
| `CONTAINER_IN_USE` | Container removal was refused while tabs still use it. |

Container handlers also use the general validation/API errors above.

### Legacy test-helper errors

These codes belong to the retained `test.*` handlers, not ordinary MCP tools.

| Code | Meaning |
|---|---|
| `TEST_ERROR` | The test-action dispatcher caught an unexpected failure. |
| `STORAGE_ERROR` | A popup/options projection or raw storage read failed. |
| `VALIDATION_ERROR` | The UI/storage projection validation failed. |
| `REFRESH_ERROR` | Refreshing test UI state failed. |
| `INVALID_PARAMETERS` | A test visit/history request lacks required inputs. |
| `VISIT_URL_ERROR` | The single-URL test visit helper failed. |
| `VISIT_MULTIPLE_URLS_ERROR` | The multiple-URL test visit helper failed. |
| `CLEAR_HISTORY_ERROR` | The test-history cleanup helper failed. |

## Test Helper Messages

The extension retains these test helper messages as legacy storage/effective
configuration projections. They do not inspect the actual popup or Options DOM.
The `maxRetries` and `pingTimeout` response fields remain for compatibility but
no longer control the connection or appear in the UI. Editable Host/Port fields
show the user configuration; the connection status separately shows test
overrides. UI regression tests execute the actual scripts and HTML instead.

### Get Popup Display State

**Request:**
```json
{
  "id": "test_001",
  "type": "request", 
  "action": "test.get_popup_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_001",
  "type": "response",
  "action": "test.get_popup_state", 
  "data": {
    "serverUrl": "ws://localhost:7777",
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "hasTestOverrides": true,
    "effectiveHostname": "localhost",
    "effectivePort": 7777,
    "testIndicatorShown": true,
    "storageValues": {
      "hostname": "localhost",
      "port": 8765,
      "testPort": 7777,
      "testHostname": "localhost"
    }
  },
  "timestamp": "2025-09-04T12:00:00.500Z"
}
```

For consent debugging, pass `{"includeConsentDiagnostics": true}` in `data`.
The response adds `consentDiagnostics`: implementation identifier, gate enabled
state, pending flag, target tab ID, remaining milliseconds, target visibility,
visibility-wait/opening/decision flags, last popup error and popup-view count.
These fields are read-only and include no script contents or target URLs.
Omitting the option preserves the legacy response. Current source identifies
itself as `visibility-recovery-2026-10-31`; this lets a diagnostic caller verify
which consent code is actually loaded. This compatible opt-in addition retains
protocol ID 3 and requires no server transport changes.

### Get Options Page State

**Request:**
```json
{
  "id": "test_002", 
  "type": "request",
  "action": "test.get_options_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:01.000Z"
}
```

**Response:**
```json
{
  "id": "test_002",
  "type": "response",
  "action": "test.get_options_state",
  "data": {
    "displayHostname": "localhost",
    "displayPort": 7777,
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "webSocketUrl": "ws://localhost:7777",
    "hasTestOverrides": true,
    "testOverrideWarningShown": true,
    "storageValues": {
      "hostname": "localhost", 
      "port": 8765,
      "testPort": 7777,
      "testHostname": "localhost"
    }
  },
  "timestamp": "2025-09-04T12:00:01.500Z"
}
```

### Get Raw Storage Values

**Request:**
```json
{
  "id": "test_003",
  "type": "request",
  "action": "test.get_storage_values",
  "data": {},
  "timestamp": "2025-09-04T12:00:02.000Z"
}
```

**Response:**
```json
{
  "id": "test_003",
  "type": "response", 
  "action": "test.get_storage_values",
  "data": {
    "hostname": "localhost",
    "port": 8765,
    "retryInterval": 1000,
    "maxRetries": 5,
    "pingTimeout": 2000,
    "testPort": 7777,
    "testHostname": "localhost"
  },
  "timestamp": "2025-09-04T12:00:02.500Z"
}
```

### Validate UI-Storage Sync

**Request:**
```json
{
  "id": "test_004",
  "type": "request",
  "action": "test.validate_ui_sync",
  "data": {
    "expectedValues": {
      "hostname": "example.com",
      "port": 9000,
      "testPort": 7777,
      "testHostname": "test.local"
    }
  },
  "timestamp": "2025-09-04T12:00:03.000Z"
}
```

**Response:**
```json
{
  "id": "test_004", 
  "type": "response",
  "action": "test.validate_ui_sync",
  "data": {
    "popupSyncValid": true,
    "optionsSyncValid": true,
    "storageMatches": true,
    "effectiveValues": {
      "hostname": "test.local",
      "port": 7777
    },
    "issues": []
  },
  "timestamp": "2025-09-04T12:00:03.500Z"
}
```

### Trigger UI State Refresh

**Request:**
```json
{
  "id": "test_005",
  "type": "request",
  "action": "test.refresh_ui_state",
  "data": {},
  "timestamp": "2025-09-04T12:00:04.000Z"
}
```

**Response:**
```json
{
  "id": "test_005",
  "type": "response",
  "action": "test.refresh_ui_state", 
  "data": {
    "refreshed": true,
    "popupStateUpdated": true,
    "optionsStateUpdated": true
  },
  "timestamp": "2025-09-04T12:00:04.500Z"
}
```

### Visit URL for History Testing

**Request:**
```json
{
  "id": "test_006",
  "type": "request",
  "action": "test.visit_url",
  "data": {
    "url": "https://httpbin.org/json",
    "waitTime": 2000
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_006",
  "type": "response",
  "action": "test.visit_url",
  "data": {
    "success": true,
    "url": "https://httpbin.org/json",
    "tabId": 123,
    "visitTime": "2025-09-05T12:00:01.000Z",
    "message": "Successfully visited https://httpbin.org/json"
  },
  "timestamp": "2025-09-05T12:00:03.000Z"
}
```

### Visit Multiple URLs for History Testing

**Request:**
```json
{
  "id": "test_007",
  "type": "request",
  "action": "test.visit_multiple_urls",
  "data": {
    "urls": [
      "https://httpbin.org/status/200",
      "https://httpbin.org/user-agent",
      "https://httpbin.org/headers"
    ],
    "waitTime": 1500,
    "delayBetween": 500
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_007",
  "type": "response",
  "action": "test.visit_multiple_urls",
  "data": {
    "success": true,
    "totalUrls": 3,
    "successfulVisits": 3,
    "failedVisits": 0,
    "results": [
      {
        "url": "https://httpbin.org/status/200",
        "success": true,
        "tabId": 124,
        "visitTime": "2025-09-05T12:00:01.500Z"
      },
      {
        "url": "https://httpbin.org/user-agent",
        "success": true,
        "tabId": 125,
        "visitTime": "2025-09-05T12:00:03.000Z"
      },
      {
        "url": "https://httpbin.org/headers",
        "success": true,
        "tabId": 126,
        "visitTime": "2025-09-05T12:00:04.500Z"
      }
    ],
    "message": "Visited 3/3 URLs successfully"
  },
  "timestamp": "2025-09-05T12:00:06.000Z"
}
```

### Clear Test History

**Request:**
```json
{
  "id": "test_008",
  "type": "request",
  "action": "test.clear_test_history",
  "data": {
    "urls": [
      "https://httpbin.org/status/200",
      "https://httpbin.org/user-agent"
    ]
  },
  "timestamp": "2025-09-05T12:00:00.000Z"
}
```

**Response:**
```json
{
  "id": "test_008",
  "type": "response",
  "action": "test.clear_test_history",
  "data": {
    "success": true,
    "action": "cleared_specific_urls",
    "totalUrls": 2,
    "successfulClears": 2,
    "failedClears": 0,
    "results": [
      {
        "url": "https://httpbin.org/status/200",
        "success": true
      },
      {
        "url": "https://httpbin.org/user-agent",
        "success": true
      }
    ],
    "message": "Cleared 2/2 URLs from history"
  },
  "timestamp": "2025-09-05T12:00:01.000Z"
}
```

## Test Helper Usage

Test helpers enable automated validation of:

- **Storage-UI Synchronization**: Verify popup and options pages display current storage values
- **Test Override Priority**: Confirm test configurations take precedence over regular settings
- **Configuration Persistence**: Validate that UI changes preserve test overrides
- **State Consistency**: Ensure all UI components reflect the same effective configuration
- **Browser History Testing**: Create and verify actual browser history content
- **History Content Validation**: Test history queries with real visited URLs
- **History Cleanup**: Clean up test history entries for isolated testing

Example test workflows:

**UI Synchronization Testing:**
1. Set test configuration via storage
2. Use `test.get_popup_state` to verify popup displays test values
3. Use `test.validate_ui_sync` to confirm UI-storage alignment
4. Modify configuration and verify persistence

**History Content Testing:**
1. Use `test.visit_url` or `test.visit_multiple_urls` to create real browser history
2. Use `history.query` or `history.recent` to verify the visited URLs appear
3. Validate history item structure and timestamps
4. Use `test.clear_test_history` to clean up test data
