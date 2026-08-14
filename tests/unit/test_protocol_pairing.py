"""
Pairing tests for protocol action names across the two halves of FoxMCP

The server names an action in a request dict; the extension answers it in a
switch case. Nothing checks that spelling at runtime, and the two files are
edited in separate sessions, so the pairing is what drifts. These tests read
the names out of both sides and compare the sets.
"""

import re
from pathlib import Path


# Every file that puts an action name on the wire. server.py carries the test
# helper protocol (test.*) while mcp_tools.py carries everything a client can
# reach, and a handler only looks orphaned if both are read.
SENDER_FILES = ("server/mcp_tools.py", "server/server.py")

HANDLER_FILE = "extension/background.js"

# Handlers deliberately kept without a sender. Each needs a reason, and the
# test below fails if a name here stops being handled - an exemption that
# outlives the thing it excuses is how a list like this rots.
UNSENT_HANDLERS_ALLOWED = {
    # Working browser capability with no MCP tool in front of it yet. Kept on
    # purpose: tabs.update is how a tab's URL or pinned state would be changed
    # without creating a new tab, and nothing else offers that.
    "tabs.update",
}

# A floor, not a count. It guards against a regex that silently stops matching
# and turns these tests green by finding nothing at all.
MINIMUM_EXPECTED_ACTIONS = 30


def _repo_root():
    """Path to the checkout, from this file's location"""
    return Path(__file__).resolve().parent.parent.parent


def _actions_sent_by_server():
    """Action strings the server puts on the wire

    Read from source rather than by calling the tools, because the action is a
    literal inside each request dict and never appears in a signature or a
    return value.
    """
    actions = set()
    for name in SENDER_FILES:
        source = (_repo_root() / name).read_text()
        actions |= set(re.findall(r'"action":\s*"([A-Za-z_]+\.[A-Za-z_]+)"', source))
    return actions


def _actions_handled_by_extension():
    """Action strings background.js has a switch case for

    'ping' is matched by an if above the switch rather than a case, so it is
    outside this scan; every other action reaches the extension through a case.
    """
    source = (_repo_root() / HANDLER_FILE).read_text()
    return set(re.findall(r"case\s*'([A-Za-z_]+\.[A-Za-z_]+)'", source))


def test_every_sent_action_has_an_extension_handler():
    """An action the server sends must have a case in background.js

    A request that reaches no handler fails silently: the extension falls
    through to its unknown-action error or ignores the message, and the caller
    waits out the 30 s timeout for an error that says nothing about the cause.
    """
    sent = _actions_sent_by_server()
    handled = _actions_handled_by_extension()

    assert len(sent) >= MINIMUM_EXPECTED_ACTIONS, (
        f"only found {len(sent)} actions in {list(SENDER_FILES)} - has the request "
        f"format changed, or did this test stop reading the right files?"
    )
    assert sent <= handled, (
        f"actions with no handler in {HANDLER_FILE}: {sorted(sent - handled)}"
    )


def test_no_orphan_handler_in_the_extension():
    """A case in background.js should be reachable, or listed as deliberate

    The reverse pairing, and the one that catches a rename: when an action is
    respelled, the old case stays behind and reads as working code. Six such
    names accumulated before they were removed - content.text, navigation.go
    and four others, each an old spelling sharing a body with its replacement.
    """
    sent = _actions_sent_by_server()
    handled = _actions_handled_by_extension()

    orphans = handled - sent - UNSENT_HANDLERS_ALLOWED

    assert not orphans, (
        f"handlers in {HANDLER_FILE} that nothing sends: {sorted(orphans)}. "
        f"Either send the action from {SENDER_FILES[0]}, delete the handler, or "
        f"add the name to UNSENT_HANDLERS_ALLOWED with the reason it stays."
    )


def test_every_allowed_orphan_is_still_handled():
    """UNSENT_HANDLERS_ALLOWED should not outlive the handlers it excuses

    Without this, deleting a handler leaves its exemption behind, and the next
    handler to take that name is exempted before anyone notices.
    """
    handled = _actions_handled_by_extension()
    stale = UNSENT_HANDLERS_ALLOWED - handled

    assert not stale, (
        f"UNSENT_HANDLERS_ALLOWED names actions {HANDLER_FILE} no longer handles: "
        f"{sorted(stale)}. Remove them from the list."
    )


def test_no_allowed_orphan_is_actually_sent():
    """An exempted name that gained a sender should leave the list

    The list means 'handled but unreachable'. A name that is now sent is
    ordinary paired code, and leaving it exempted only hides the next rename.
    """
    sent = _actions_sent_by_server()
    unnecessary = UNSENT_HANDLERS_ALLOWED & sent

    assert not unnecessary, (
        f"UNSENT_HANDLERS_ALLOWED names actions the server does send: "
        f"{sorted(unnecessary)}. Remove them from the list."
    )
