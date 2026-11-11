"""Tests for content_wait, which waits for a script to return a value"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.timeout = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        self.timeout = timeout
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def wait(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("content_wait")
        return await tool.fn(**kwargs)

    return call


SCRIPT = "document.querySelector('#done') ? true : null"


class TestWait:

    @pytest.mark.asyncio
    async def test_sends_the_script_and_the_timings(self, wait, stub_server):
        stub_server.response = {"type": "response", "data": {
            "result": True, "waitedMs": 420, "attempts": 3, "url": "https://example.org/done"}}

        result = await wait(profile_id=1, tab_id=4, script=SCRIPT, timeout=5, interval=0.5)

        assert stub_server.sent_request["action"] == "content.wait"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "script": SCRIPT, "timeoutMs": 5000, "intervalMs": 500}
        assert result == ("Ready after 420 ms and 3 run(s) in tab 4 (https://example.org/done):\n"
                          "true")

    @pytest.mark.asyncio
    async def test_defaults_are_ten_seconds_and_200_ms(self, wait, stub_server):
        stub_server.response = {"type": "response", "data": {"result": "x"}}

        await wait(profile_id=1, tab_id=4, script=SCRIPT)

        assert stub_server.sent_request["data"]["timeoutMs"] == 10000
        assert stub_server.sent_request["data"]["intervalMs"] == 200

    @pytest.mark.asyncio
    async def test_a_string_result_is_returned_as_is_and_others_as_json(self, wait, stub_server):
        stub_server.response = {"type": "response", "data": {"result": "Saved"}}
        text = await wait(profile_id=1, tab_id=4, script=SCRIPT)
        stub_server.response = {"type": "response", "data": {"result": {"a": [1, None]}}}
        structured = await wait(profile_id=1, tab_id=4, script=SCRIPT)
        stub_server.response = {"type": "response", "data": {"result": 0}}
        zero = await wait(profile_id=1, tab_id=4, script=SCRIPT)

        assert text.endswith(":\nSaved")
        assert structured.endswith(':\n{"a": [1, null]}')
        assert zero.endswith(":\n0")

    @pytest.mark.asyncio
    async def test_server_timeout_outlasts_approval_and_the_wait(self, wait, stub_server):
        await wait(profile_id=1, tab_id=4, script=SCRIPT, timeout=120)

        assert stub_server.timeout == 240.0

    @pytest.mark.asyncio
    async def test_reports_a_timeout(self, wait, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "WAIT_TIMEOUT", "message": "Timed out after 1000 ms: the script kept returning null"}}

        result = await wait(profile_id=1, tab_id=4, script=SCRIPT, timeout=1)

        assert result == "Failed to wait: Timed out after 1000 ms: the script kept returning null"

    @pytest.mark.asyncio
    async def test_reports_a_script_that_threw(self, wait, stub_server):
        stub_server.response = {"type": "error", "data": {
            "code": "SCRIPT_ERROR", "message": "Wait script failed: x is not defined"}}

        result = await wait(profile_id=1, tab_id=4, script="x")

        assert result == "Failed to wait: Wait script failed: x is not defined"


class TestArguments:

    @pytest.mark.asyncio
    @pytest.mark.parametrize("script", ["", "   ", None, 5])
    async def test_script_must_be_a_nonempty_string(self, wait, stub_server, script):
        result = await wait(profile_id=1, tab_id=4, script=script)

        assert result == "Failed to wait: script must be a nonempty string"
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("timeout", [0, -1, 121, True, "5", float("nan"), float("inf")])
    async def test_timeout_must_be_a_number_above_zero_up_to_120(self, wait, stub_server, timeout):
        result = await wait(profile_id=1, tab_id=4, script=SCRIPT, timeout=timeout)

        assert result == "Failed to wait: timeout must be a number above 0 and at most 120"
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    @pytest.mark.parametrize("interval", [0, 0.05, 5.1, True, "1", float("nan"), float("inf")])
    async def test_interval_must_be_a_number_from_0_1_to_5(self, wait, stub_server, interval):
        result = await wait(profile_id=1, tab_id=4, script=SCRIPT, interval=interval)

        assert result == "Failed to wait: interval must be a number from 0.1 to 5"
        assert stub_server.sent_request is None
