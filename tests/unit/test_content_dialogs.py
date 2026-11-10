"""Tests for content_handle_dialogs"""

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request, timeout=30.0):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def handle_dialogs(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(**kwargs):
        tool = await tools.mcp.get_tool("content_handle_dialogs")
        return await tool.fn(**kwargs)

    return call


class TestDialogs:

    @pytest.mark.asyncio
    async def test_lists_what_was_answered(self, handle_dialogs, stub_server):
        stub_server.response = {"type": "response", "data": {"mode": "accept", "dialogs": [
            {"type": "confirm", "message": "Delete?", "accepted": True},
            {"type": "alert", "message": "Done", "accepted": True}]}}

        result = await handle_dialogs(profile_id=1, tab_id=4, mode="accept")

        assert stub_server.sent_request["action"] == "content.dialogs"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "mode": "accept", "promptText": None}
        assert result == "Dialog handling: accept\n- confirm (accepted): Delete?\n- alert (shown): Done"

    @pytest.mark.asyncio
    async def test_dismissed_dialogs_say_so(self, handle_dialogs, stub_server):
        stub_server.response = {"type": "response", "data": {"mode": "dismiss", "dialogs": [
            {"type": "confirm", "message": "Sure?", "accepted": False}]}}

        result = await handle_dialogs(profile_id=1, tab_id=4, mode="dismiss")

        assert "- confirm (dismissed): Sure?" in result

    @pytest.mark.asyncio
    async def test_prompt_text_is_sent(self, handle_dialogs, stub_server):
        stub_server.response = {"type": "response", "data": {"mode": "accept", "dialogs": []}}

        result = await handle_dialogs(profile_id=1, tab_id=4, mode="accept", prompt_text="Dor")

        assert stub_server.sent_request["data"]["promptText"] == "Dor"
        assert result.endswith("No dialog was shown since the last call")

    @pytest.mark.asyncio
    async def test_mode_is_checked(self, handle_dialogs, stub_server):
        with pytest.raises(ValueError, match="mode"):
            await handle_dialogs(profile_id=1, tab_id=4, mode="maybe")
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_reports_an_extension_error(self, handle_dialogs, stub_server):
        stub_server.response = {"type": "error", "data": {"message": "Tab not found"}}

        result = await handle_dialogs(profile_id=1, tab_id=4, mode="dismiss")

        assert result == "Failed to handle dialogs: Tab not found"

    @pytest.mark.asyncio
    async def test_alerts_are_shown_not_accepted(self, handle_dialogs, stub_server):
        stub_server.response = {"type": "response", "data": {"mode": "accept", "dialogs": [
            {"type": "alert", "message": "Saved", "accepted": True}]}}

        result = await handle_dialogs(profile_id=1, tab_id=4, mode="log")

        assert result == "Dialog handling: accept\n- alert (shown): Saved"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("mode, prompt_text, message", [
        ("dismiss", "Dor", "only applies to mode accept"),
        ("log", "Dor", "only applies to mode accept"),
        ("accept", 5, "must be a string"),
    ])
    async def test_prompt_text_is_only_for_accept(
            self, handle_dialogs, stub_server, mode, prompt_text, message):
        with pytest.raises(ValueError, match=message):
            await handle_dialogs(profile_id=1, tab_id=4, mode=mode, prompt_text=prompt_text)
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_a_mode_is_required(self, handle_dialogs):
        with pytest.raises(TypeError):
            await handle_dialogs(profile_id=1, tab_id=4)