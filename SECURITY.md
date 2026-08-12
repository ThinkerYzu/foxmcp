# Security Policy

## Reporting a Vulnerability

Use [**GitHub private vulnerability reporting**](https://github.com/ThinkerYzu/foxmcp/security/advisories/new)
— the "Report a vulnerability" button under the repository's Security tab. It is private
between you and the maintainer, and it works without exposing an email address to
scrapers.

Please do not open a public issue for something you believe is exploitable. If you have
already published, that is not a problem — say so in the report and we will work from
there.

**What helps:** the file and function, what an attacker controls, and what they get. A
proof of concept is welcome but not required; a clear description of the path is worth
more than a script.

**What to expect:** an acknowledgement within a week, and an assessment — fix, decline, or
"need more information" — within two. Declines come with reasons. Fixes are credited
unless you ask otherwise.

## Supported Versions

| Version | Supported |
|---|---|
| `master` | Yes — this is where fixes land first |
| v1.1.0 (current release) | Yes |
| Earlier releases | No |

`master` is continuously deployed for the maintainer's own use, so it is generally the
best-tested branch. Released versions lag it.

## Threat Model

Knowing what FoxMCP does *not* defend against will save you time, and tells you whether a
finding is a bug or a documented property.

**FoxMCP defends against the network and the web. It does not defend against local
processes.**

A process running as the same user already holds the browser profile, the cookie jar, the
predefined-script directory, and `ptrace`. Authentication between two components that this
user controls protects nothing: whoever can read a token file can read everything the
token guards. So the absence of a shared secret between the extension and the server is
deliberate, not an oversight.

What that argument does not cover is a **web page**, which is neither on the network nor a
local process — it reaches `localhost` from inside the user's own browser. Pages are
excluded deliberately:

| Surface | How pages are kept out |
|---|---|
| Extension WebSocket | An origin allowlist. Handshakes that are not `moz-extension://` are rejected with a `403`. WebSockets are exempt from the same-origin policy and are never preflighted, so the server has to do this itself |
| MCP HTTP port | No CORS headers, so the browser blocks preflighted requests; `Content-Type` enforcement, which closes the `text/plain` path that would skip the preflight; and a session id cross-origin JavaScript cannot read |

**Consequences accepted on purpose**, so please do not report these as vulnerabilities
unless you can show the reasoning is wrong:

- **The extension holds broad permissions** — `<all_urls>`, `webRequest`, `tabs`,
  `history`, `bookmarks`. This is what the tool is for. Treat an installed FoxMCP as
  granting its MCP client the same reach over the browser that you have.
- **Neither port authenticates local callers.** Any local process can drive the MCP port.
  See the threat model above.
- **On a shared machine, another local user can reach both ports.** Localhost binding
  restricts by network interface, not by uid. FoxMCP assumes a single-user workstation.
- **Predefined scripts run arbitrary programs by design.** They are disabled unless
  `FOXMCP_EXT_SCRIPTS` is set, and are validated and logged
  ([`docs/scripts.md`](docs/scripts.md#security-features)), but a caller that can reach the
  MCP port can run anything in that directory.
- **A malicious installed extension** can present a `moz-extension://` origin of its own.
  That requires the user to install hostile software, at which point the browser is
  already compromised.

**In scope and worth reporting:** anything that lets a web page, a remote host, or a
lower-privileged local user reach either port or influence what the extension does; any
way to escape the predefined-script directory; any way to make the server execute
JavaScript in a tab the caller should not reach.

## Past Reports

- [Issue #5](https://github.com/ThinkerYzu/foxmcp/issues/5) — response to the 2026-05-07
  third-party static audit, including which findings were fixed and which were declined
  and why.
