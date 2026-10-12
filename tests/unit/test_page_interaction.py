"""
Tests for the page interaction tools: content_snapshot, content_click,
content_type and content_press_key

These stub the WebSocket server, so they check the request each tool builds and
how it renders the extension's answer. The events the content script dispatches
are exercised against real Firefox, where a stub could not tell a click that
opens a mousedown menu from one that does not.
"""

import base64

import pytest

import test_imports  # Automatic path setup
from server.mcp_tools import FoxMCPTools, UPLOAD_CHUNK_BYTES


class StubWebSocketServer:
    """Records the request and replays a canned response"""

    def __init__(self):
        self.sent_request = None
        self.response = {"type": "response", "data": {}}

    async def send_request_and_wait(self, request):
        self.sent_request = request
        return self.response


@pytest.fixture
def stub_server():
    return StubWebSocketServer()


@pytest.fixture
def call_tool(stub_server):
    tools = FoxMCPTools(stub_server)

    async def call(name, **kwargs):
        tool = await tools.mcp.get_tool(name)
        return await tool.fn(**kwargs)

    return call


class TestSnapshot:

    @pytest.mark.asyncio
    async def test_lists_elements_under_the_page_title(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {
            "title": "Form", "url": "https://example.org/form",
            "snapshot": '[r1] input "Name" (type=text)\n[r2] button "Save"'}}

        result = await call_tool("content_snapshot", tab_id=4)

        assert stub_server.sent_request["action"] == "content.snapshot"
        assert stub_server.sent_request["data"] == {"tabId": 4, "maxElements": 300}
        assert result.startswith("Snapshot of Form (https://example.org/form):")
        assert '[r2] button "Save"' in result


class TestClick:

    @pytest.mark.asyncio
    async def test_sends_the_ref(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"clicked": '[r2] button "Save"'}}

        result = await call_tool("content_click", tab_id=4, ref="r2")

        assert stub_server.sent_request["action"] == "content.click"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "ref": "r2", "selector": None, "doubleClick": False}
        assert result == 'Clicked [r2] button "Save"'

    @pytest.mark.asyncio
    async def test_double_click(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"clicked": '[r9] row "Characters"'}}

        result = await call_tool("content_click", tab_id=4, ref="r9", double_click=True)

        assert stub_server.sent_request["data"]["doubleClick"] is True
        assert result == 'Double-clicked [r9] row "Characters"'

    @pytest.mark.asyncio
    async def test_requires_a_target(self, call_tool, stub_server):
        with pytest.raises(ValueError, match="ref"):
            await call_tool("content_click", tab_id=4)
        assert stub_server.sent_request is None

    @pytest.mark.asyncio
    async def test_reports_a_stale_ref(self, call_tool, stub_server):
        stub_server.response = {"type": "error", "data": {
            "message": "No element with ref r9; take a new snapshot"}}

        result = await call_tool("content_click", tab_id=4, ref="r9")

        assert result == "Failed to click: No element with ref r9; take a new snapshot"


class TestType:

    @pytest.mark.asyncio
    async def test_replaces_by_default_and_can_submit(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"typed": '[r1] input "Dor"'}}

        await call_tool("content_type", tab_id=4, selector="#name", text="Dor", submit=True)

        assert stub_server.sent_request["action"] == "content.type"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "ref": None, "selector": "#name",
            "text": "Dor", "clear": True, "submit": True}


class TestPressKey:

    @pytest.mark.asyncio
    async def test_targets_the_focused_element_when_none_given(self, call_tool, stub_server):
        stub_server.response = {"type": "response", "data": {"pressed": "Escape"}}

        result = await call_tool("content_press_key", tab_id=4, key="Escape")

        assert stub_server.sent_request["action"] == "content.press_key"
        assert stub_server.sent_request["data"] == {
            "tabId": 4, "key": "Escape", "ref": None, "selector": None}
        assert result == "Pressed Escape"


class RecordingWebSocketServer:
    """Records every request; answers capture and finish the way the extension does"""

    def __init__(self):
        self.requests = []

    async def send_request_and_wait(self, request):
        self.requests.append(request)
        if request["action"] == "content.capture_file_input":
            return {"type": "response", "data": {"ref": "r7", "multiple": False, "directory": True}}
        if request["action"] == "content.upload_finish":
            return {"type": "response", "data": {
                "count": 2, "paths": ["Assets/a.txt", "Assets/sub/b.bin"], "target": "[r7] input"}}
        return {"type": "response", "data": {"ok": True}}

    def actions(self):
        return [r["action"] for r in self.requests]


class TestUploadFiles:

    @pytest.fixture
    def recorder(self):
        return RecordingWebSocketServer()

    @pytest.fixture
    def upload(self, recorder):
        tools = FoxMCPTools(recorder)

        async def call(**kwargs):
            tool = await tools.mcp.get_tool("content_upload_files")
            return await tool.fn(**kwargs)

        return call

    @pytest.fixture
    def folder(self, tmp_path):
        root = tmp_path / "Assets"
        (root / "sub").mkdir(parents=True)
        (root / "a.txt").write_text("alpha")
        (root / "sub" / "b.bin").write_bytes(b"\x00" * (UPLOAD_CHUNK_BYTES + 10))
        return root

    @pytest.mark.asyncio
    async def test_folder_files_keep_paths_under_the_folder_name(self, upload, recorder, folder):
        await upload(tab_id=4, path=str(folder), ref="r2")

        begin = recorder.requests[0]
        assert begin["action"] == "content.upload_begin"
        assert begin["data"]["files"] == [
            {"name": "a.txt", "relativePath": "Assets/a.txt"},
            {"name": "b.bin", "relativePath": "Assets/sub/b.bin"}]

    @pytest.mark.asyncio
    async def test_large_files_are_split_into_chunks(self, upload, recorder, folder):
        await upload(tab_id=4, path=str(folder), ref="r2")

        chunks = [r["data"] for r in recorder.requests if r["action"] == "content.upload_chunk"]
        assert [c["fileIndex"] for c in chunks] == [0, 1, 1]
        sizes = [len(base64.b64decode(c["data"])) for c in chunks]
        assert sizes == [5, UPLOAD_CHUNK_BYTES, 10]
        finish = recorder.requests[-1]
        assert finish["action"] == "content.upload_finish"
        assert finish["data"]["ref"] == "r2"

    @pytest.mark.asyncio
    async def test_trigger_fills_the_input_it_opens(self, upload, recorder, folder):
        result = await upload(tab_id=4, path=str(folder), trigger_ref="r5")

        assert recorder.actions()[0] == "content.capture_file_input"
        assert recorder.requests[0]["data"]["triggerRef"] == "r5"
        assert recorder.requests[-1]["data"]["ref"] == "r7"
        assert result.startswith("Set 2 file(s) on [r7] input")

    @pytest.mark.asyncio
    async def test_single_file_has_no_relative_path(self, upload, recorder, folder):
        await upload(tab_id=4, path=str(folder / "a.txt"), selector="#plain")

        assert recorder.requests[0]["data"]["files"] == [{"name": "a.txt", "relativePath": ""}]

    @pytest.mark.asyncio
    async def test_missing_path_sends_nothing(self, upload, recorder, tmp_path):
        result = await upload(tab_id=4, path=str(tmp_path / "nope"), ref="r2")

        assert result.endswith("does not exist")
        assert recorder.requests == []
