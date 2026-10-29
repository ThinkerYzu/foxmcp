# Web Request Monitoring

Every browser tool requires an explicit `profile_id` from `profiles_list` in
addition to the arguments shown below. Tab and monitor IDs are local to that
profile; see [profile discovery](api-reference.md#firefox-profiles).

FoxMCP can watch the HTTP requests Firefox makes and hand them to an MCP client:
the URLs, the status codes, the response headers, and — for text responses — the
response bodies. It is built on the extension's `webRequest` listeners, so it sees
the document load and every subresource, not only what page JavaScript issues.

Four tools cover it:

| Tool | Takes | Gives back |
|---|---|---|
| `requests_start_monitoring` | `url_patterns`, optional `options`, optional `tab_id` | `monitor_id` |
| `requests_list_captured` | `monitor_id` | one summary line per request |
| `requests_get_content` | `monitor_id`, `request_id` | headers and bodies for one request |
| `requests_stop_monitoring` | `monitor_id`, `drain_timeout` | stop confirmation and totals |

Keep the `monitor_id`. The other three tools all take it, and there is no tool that
lists monitors, so losing it leaves a monitor running with no way to read or stop it.

## The workflow

Start a monitor, let the browser do some work, then read what was captured.

```python
profile_id = 1  # Use the integer returned by profiles_list().  # Inspect profiles_list() first.

# 1. Start. Returns {"monitor_id": "mon_1755205412345", "status": "active", ...}
requests_start_monitoring(profile_id=profile_id, url_patterns=["https://example.org/*"])

# 2. Drive the browser — navigate, click, whatever generates the traffic
tabs_create(profile_id=profile_id, url="https://example.org/")

# 3. See what was caught
requests_list_captured(profile_id=profile_id, monitor_id="mon_1755205412345")

# 4. Pull one request apart
requests_get_content(profile_id=profile_id, monitor_id="mon_1755205412345", request_id="1234")

# 5. Stop
requests_stop_monitoring(profile_id=profile_id, monitor_id="mon_1755205412345")
```

A request is listed once it has completed, and step 2 above returns before that
happens: `tabs_create` and `navigation_reload` both come back as soon as the browser
has been told what to do, not when the page has loaded. Listing straight after one of
them gives an empty list on a monitor that is working perfectly.

Captured data outlives the monitor: `requests_list_captured` and
`requests_get_content` still answer after `requests_stop_monitoring`. What ends is
the capturing, not the record. It does not outlive the connection, though: see
[How long a monitor lives](#how-long-a-monitor-lives).

Stopping also returns statistics — duration, requests per second, and
`total_data_size`. Read the last one as a lower bound: it sums the `Content-Length`
each response declared, which compressed HTTP/2 responses routinely omit, and those
count as zero. The measured `size_bytes` from `requests_get_content` is the
trustworthy figure, per request.

## How long a monitor lives

Captured data lives in the selected profile's extension background page. The
server records monitor ownership so it can stop captures abandoned by an MCP
client. A monitor ends when its client departs or its profile connection drops:

| What happens | The monitors it ends |
|---|---|
| `requests_stop_monitoring` | that one, and its captured data stays readable |
| Your MCP client disconnects | every monitor that client started, across its targeted profiles, within a few seconds |
| A profile connection drops, including when its endpoint changes | all monitors in that profile, captured data included; other profiles are unaffected |
| The extension answers for a monitor no client owns | that one, on sight |

The middle two are the same rule seen from either side. The last is the backstop for
the two halves drifting apart, which takes an extension and a server that disagree
about whether a monitor survived a connection: whichever side let go, the monitor is
capturing for a reader that cannot reach it, and the server stops it the moment the
extension mentions it. A monitor whose client has
gone can never be read or stopped again, and it is not harmless while it sits
there: the extension keeps its `webRequest` listeners registered and goes on
filtering response bodies for a reader that will not come back.

`requests_list_captured` and `requests_get_content` answer `MONITOR_NOT_FOUND` for
an id that has been cleared. That matters more than it sounds: an empty list is
what a healthy monitor returns before anything has completed, so a monitor that
has quietly gone and one that is simply early would otherwise look identical.

## URL patterns

A pattern is a glob, not a WebExtensions match pattern. `*` becomes `.*`, `?`
becomes `.`, and the result is tested against the full URL as an **unanchored**
regular expression — so `example.org` matches `https://example.org/a` and
`https://cdn.example.org/b` alike. Two patterns are special-cased to match
everything: the bare `*`, and `<all_urls>`, which holds no wildcard of its own and
is accepted because it is the spelling a WebExtensions caller reaches for.

| Pattern | Matches |
|---|---|
| `*` | every request |
| `<all_urls>` | every request |
| `https://example.org/*` | anything under that origin |
| `*/api/*` | any URL with `/api/` in the path |
| `.json` | any URL containing `.json`, anywhere |

An invalid pattern is not an error: it is logged in the extension console and
matches nothing.

Pass `tab_id` to narrow a monitor to one tab. Several monitors can run at once, and
a request that matches more than one is captured by each.

## Options

`options` is a dict passed to `requests_start_monitoring`. Three settings do
something:

| Option | Default | Effect |
|---|---|---|
| `capture_response_bodies` | `true` | Set `false` and no response body is read at all |
| `max_body_size` | `50000` | Bytes kept per body. The rest is dropped and `truncated` is `true`, but the full size is still counted |
| `content_types_to_capture` | `["application/json", "text/plain"]` | A body is returned as text only if its `Content-Type` **contains** one of these — `application/json` matches `application/json; charset=utf-8`, and the bare string `json` would match it too. An entry with a `*`, such as `text/*`, matches on the major type. An empty list means every type. Whatever does not match is still counted, and comes back with `content: null` |

Three settings are accepted and ignored — see [Not implemented](#not-implemented).

## What a summary looks like

`requests_list_captured` returns `{"monitor_id": ..., "total_requests": n,
"requests": [...]}`, one entry per request:

```json
{
  "request_id": "1234",
  "url": "https://example.org/api/items",
  "method": "GET",
  "status_code": 200,
  "duration_ms": 118,
  "timestamp": "2026-08-14T09:12:03.221Z",
  "tab_id": 7,
  "type": "xmlhttprequest",
  "error": null
}
```

`request_id` is Firefox's own `webRequest` id, and is what `requests_get_content`
takes. `error` is set only for requests that failed before completing, and
`status_code` is absent for those.

## What content looks like

`requests_get_content` returns the headers and both bodies for one request:

```json
{
  "request_id": "1234",
  "request_headers": {},
  "response_headers": {"content-type": "application/json", "server": "nginx"},
  "request_body": {"included": false, "content": null, "size_bytes": 0,
                   "truncated": false, "saved_to_file": null},
  "response_body": {"included": true, "content": "{\"items\":[]}",
                    "content_type": "application/json", "encoding": "utf-8",
                    "size_bytes": 12, "truncated": false, "saved_to_file": null,
                    "note": "Response body read from the response stream"}
}
```

Read `response_body` by its fields, not by presence:

| Field | Meaning |
|---|---|
| `included` | Whether `content` holds the body. When `false`, `note` says why |
| `size_bytes` | Bytes Firefox actually delivered, counted as the body streamed through. Correct even when the body itself was withheld or truncated; `null` only when the response could not be tapped at all |
| `truncated` | The body was longer than `max_body_size` |
| `note` | Present on every response body — either how it was read, or which of the reasons it was not |

`size_bytes` is measured rather than read from `Content-Length`, which compressed
HTTP/2 responses routinely omit. Firefox has already undone any `Content-Encoding`
by the time the bytes reach the filter, so the content is the decoded body.

A body has to pass two gates to come back as text. `content_types_to_capture`
decides whether the monitor wanted it, and the decoder then requires a type that
really is text — `text/*`, `application/json`, `application/xml`,
`application/javascript` or `application/xhtml+xml`. Adding `image/png` to
`content_types_to_capture` therefore does not produce a PNG body; it produces
`content: null` with the size filled in.

`request_headers` is always `{}` — the extension registers no listener that
collects them. `request_body` is populated only for requests that carried one, from
what `webRequest` reports at `onBeforeRequest`; a form post arrives as the parsed
`formData` structure rather than the raw bytes.

## Where the data lives

Everything is held in memory in the extension's background page. Nothing is written
to disk. The server keeps ownership metadata per profile connection, but does not
store the captured bodies or request records.

- **Response bodies:** the most recent 200 across all monitors. A monitor on `*`
  sees every request the browser makes, so older bodies are evicted to keep memory
  bounded. The size recorded on the request survives eviction, so an evicted request
  still reports how large its body was.
- **Request summaries and details:** kept for the life of the background page, and
  not freed when a monitor stops. Long-running monitoring on a broad pattern grows
  the extension's memory until Firefox or the extension restarts.
- **Across restarts:** nothing survives. Reloading the extension, or restarting
  Firefox, discards every monitor and everything captured.

## Not implemented

These are accepted by the tools and do nothing. They are documented here so a
caller does not conclude the feature is broken.

| Parameter | What actually happens |
|---|---|
| `save_request_body_to`, `save_response_body_to` on `requests_get_content` | Forwarded to the extension and ignored. `saved_to_file` is always `null`. A WebExtension cannot write to an arbitrary path, so this needs a design decision — the `downloads` API, or having the server write the bytes it already receives — rather than a patch |
| `include_binary` on `requests_get_content` | Ignored. Non-text bodies are never returned; their size is |
| `drain_timeout` on `requests_stop_monitoring` | Ignored. The monitor stops immediately |
| `capture_request_bodies` in `options` | Ignored. Request bodies are captured whenever `webRequest` reports one |
| `sensitive_headers` in `options` | Ignored, and moot: no request headers are captured to redact |

## Permissions

Body capture uses `webRequest.filterResponseData`, which Firefox only attaches to a
request whose extension registered a **blocking** listener — so `onBeforeRequest`
asks for `["requestBody", "blocking"]` and the extension carries
`webRequestBlocking`. No listener blocks, cancels or rewrites anything; the
permission buys read access to the stream and nothing else. It has no description
string in Gecko, so it raises no install prompt.

The full permission list is in [`configuration.md`](configuration.md).

## See also

- [`api-reference.md`](api-reference.md) — every tool's parameters
- [`protocol.md`](protocol.md) — the `requests.*` messages between server and extension
- [`architecture.md`](architecture.md) — where the two halves split

---

*This file previously held an implementation plan for a much larger monitoring API —
search, retention policies, storage quotas, session save and load, roughly twenty
tools in all. Only the four above were ever built. The plan was replaced by this
reference on 2026-08-14; the unbuilt parts are not planned work.*
