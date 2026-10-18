"""Manual schema usability check with a fresh agent and real Firefox.

Run with the project venv. Requires an authenticated Codex or Claude CLI and Firefox;
this launches a model and is deliberately outside the automated pytest suite.
"""

import argparse
import asyncio
import hashlib
import json
import shutil
import tempfile
import threading
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import test_imports
from fastmcp import Client
from firefox_test_utils import FirefoxTestManager, resolve_firefox_path
from server.server import FoxMCPServer


PAGE = b'''<!doctype html><meta charset="utf-8"><title>CSV importer</title>
<h1>Import a CSV report</h1>
<form id="import-form">
<label>Report <input id="report" name="file" type="file" accept=".csv,text/csv" required></label>
<input id="changes" type="hidden" name="changes" value="0">
<button type="submit">Import report</button></form>
<pre id="result">No report imported.</pre>
<script>
document.querySelector('#report').addEventListener('change', () => {
  document.querySelector('#changes').value++;
});
document.querySelector('form').addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/upload', {method: 'POST', body: new FormData(event.target)});
  const data = await response.json();
  document.querySelector('#result').textContent = response.ok
    ? `Imported ${data.name}: ${data.rows} rows. SHA-256: ${data.sha256}`
    : `Import failed: ${data.error}`;
});
</script>'''


async def evaluate(args):
    output = Path(args.output_dir or tempfile.mkdtemp(prefix="foxmcp-agent-eval-"))
    output.mkdir(parents=True, exist_ok=True)
    agent_dir = output / "agent"
    agent_dir.mkdir(exist_ok=True)
    data_dir = output / "data"
    data_dir.mkdir(exist_ok=True)
    source = data_dir / "quarterly report.csv"
    contents = 'quarter,region,revenue\nQ1,North,1200\nQ2,"West, coast",2300\n'.encode()
    source.write_bytes(contents)
    expected_hash = hashlib.sha256(contents).hexdigest()
    receipts = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, status, body, media_type):
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/":
                self.respond(200, PAGE, "text/html; charset=utf-8")
            else:
                self.respond(404, b"Not found", "text/plain")

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/upload" or not 0 < length <= 1024 * 1024:
                self.respond(400, b'{"error":"Invalid upload"}', "application/json")
                return
            headers = f"Content-Type: {self.headers['Content-Type']}\r\nMIME-Version: 1.0\r\n\r\n"
            message = BytesParser(policy=policy.default).parsebytes(
                headers.encode() + self.rfile.read(length))
            fields = {part.get_param("name", header="content-disposition"): part
                      for part in message.iter_parts()}
            file = fields.get("file")
            if file is None:
                self.respond(400, b'{"error":"No file received"}', "application/json")
                return
            body = file.get_payload(decode=True)
            receipt = {"name": file.get_filename(), "type": file.get_content_type(),
                       "size": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                       "rows": len(body.decode("utf-8").splitlines()) - 1,
                       "change_events": int(fields["changes"].get_content())}
            receipts.append(receipt)
            (output / "receipts.json").write_text(json.dumps(receipts, indent=2))
            self.respond(200, json.dumps(receipt).encode(), "application/json")

    website = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=website.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{website.server_port}/"
    server = FoxMCPServer(port=args.ws_port, mcp_port=args.mcp_port)
    server_task = asyncio.create_task(server.start_server())
    firefox = FirefoxTestManager(firefox_path=resolve_firefox_path(), test_port=args.ws_port)
    process = None
    try:
        await asyncio.sleep(.2)
        if server_task.done():
            await server_task
        if not firefox.setup_and_start_firefox(headless=True):
            raise RuntimeError("Firefox setup failed")
        if not await firefox.async_wait_for_extension_connection(timeout=30, server=server):
            raise RuntimeError("Extension did not connect")
        endpoint = f"http://127.0.0.1:{server.mcp_port}/mcp"
        async with Client(endpoint) as client:
            definitions = [tool.model_dump(by_alias=True, exclude_none=True)
                           for tool in await client.list_tools()]
        (output / "schemas.json").write_text(json.dumps(definitions, indent=2))
        prompt = (
            f"Upload the local CSV report at {source} to the CSV importer at {url} "
            "and report what the page says after importing.\n\n"
            "Use only the FoxMCP MCP tools for this task. Do not use shell commands, "
            "filesystem tools, web search, source code or project documentation. "
            "Work only with the dummy file and local test website identified above."
        )
        (output / "prompt.txt").write_text(prompt)
        if args.agent_cli == "claude":
            config = {"mcpServers": {"foxmcp": {"type": "http", "url": endpoint}}}
            command = [shutil.which("claude"), "--print", "--output-format", "stream-json",
                       "--verbose", "--no-session-persistence", "--setting-sources", "",
                       "--strict-mcp-config", "--mcp-config", json.dumps(config),
                       "--tools", "", "--allowedTools", "mcp__foxmcp",
                       "--permission-mode", "dontAsk", "--", prompt]
        else:
            command = [shutil.which("codex"), "-a", "never", "exec", "--ignore-user-config",
                       "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                       "--json", "--cd", str(agent_dir),
                       "-c", f'mcp_servers.foxmcp.url="{endpoint}"',
                       "-c", 'mcp_servers.foxmcp.default_tools_approval_mode="approve"',
                       "--output-last-message", str(output / "agent-answer.txt"), prompt]
        print(f"Agent test artifacts: {output}", flush=True)
        print(f"Website: {url}; MCP tools: {len(definitions)}", flush=True)
        with (output / "agent.jsonl").open("w") as transcript, \
                (output / "agent-stderr.log").open("w") as errors:
            process = await asyncio.create_subprocess_exec(
                *command, cwd=agent_dir, stdout=transcript, stderr=errors)
            try:
                code = await asyncio.wait_for(process.wait(), timeout=args.timeout)
            except asyncio.TimeoutError:
                process.terminate()
                await process.wait()
                raise RuntimeError("Agent test timed out")
        calls = []
        for line in (output / "agent.jsonl").read_text().splitlines():
            event = json.loads(line)
            item = event.get("item", {})
            if event.get("type") == "item.completed" and item.get("type") == "mcp_tool_call":
                calls.append(item)
            if args.agent_cli == "claude" and event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if block.get("type") == "tool_use" and block.get("name", "").startswith("mcp__foxmcp__"):
                        calls.append({"tool": block["name"].removeprefix("mcp__foxmcp__"),
                                      "arguments": block.get("input", {})})
            if args.agent_cli == "claude" and event.get("type") == "result":
                (output / "agent-answer.txt").write_text(event.get("result", ""))
        loaded = any(call.get("tool") == "content_load_file" for call in calls)
        passed = (code == 0 and loaded and len(receipts) == 1
                  and receipts[0]["name"] == source.name
                  and receipts[0]["sha256"] == expected_hash
                  and receipts[0]["type"] == "text/csv"
                  and receipts[0]["change_events"] >= 1)
        result = {"passed": passed, "agent_cli": args.agent_cli, "agent_exit_code": code,
                  "used_content_load_file": loaded, "tool_calls": len(calls),
                  "expected_sha256": expected_hash, "receipts": receipts}
        (output / "result.json").write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2), flush=True)
        return passed
    finally:
        if process and process.returncode is None:
            process.terminate()
            await process.wait()
        firefox.cleanup()
        await server.shutdown(server_task)
        website.shutdown()
        website.server_close()
        thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent-cli", choices=("codex", "claude"), default="codex")
    parser.add_argument("--output-dir")
    parser.add_argument("--ws-port", type=int, default=31087)
    parser.add_argument("--mcp-port", type=int, default=31086)
    parser.add_argument("--timeout", type=float, default=300)
    options = parser.parse_args()
    if not shutil.which(options.agent_cli):
        parser.error(f"{options.agent_cli} CLI is required")
    raise SystemExit(0 if asyncio.run(evaluate(options)) else 1)
