"""Election and the discovery/shutdown race, independently of MCP transports."""

import json
from unittest.mock import AsyncMock, Mock

import pytest

import test_imports
from server import single_instance


def test_owner_lock_is_exclusive_and_reusable(tmp_path):
    path = tmp_path / "owner.lock"
    first = single_instance.InstanceLock(path)
    second = single_instance.InstanceLock(path)
    try:
        assert first.acquire()
        assert not second.acquire()
        first.close()
        assert second.acquire()
    finally:
        if not first.file.closed:
            first.close()
        second.close()
    assert path.exists()  # Removing a lock file can create two independent locks.


@pytest.mark.asyncio
async def test_discovery_retries_election_when_previous_owner_is_stopping(tmp_path, monkeypatch):
    server = Mock(port=8765)
    monkeypatch.setattr(single_instance, "runtime_directory", lambda: tmp_path)
    monkeypatch.setattr(single_instance, "configuration_id", lambda _: "config")
    loser = Mock()
    loser.poll.return_value = 0
    winner = Mock()
    winner.poll.return_value = None
    launches = []

    def spawn(*_):
        launches.append(True)
        if len(launches) == 1:
            return loser
        (tmp_path / "instance-8765.json").write_text(json.dumps({
            "protocol": single_instance.PROTOCOL, "port": 43210, "token": "token",
        }))
        return winner

    lease = AsyncMock()
    lease.recv.return_value = json.dumps({
        "protocol": single_instance.PROTOCOL, "configuration": "config",
        "pid": 123, "lease": "lease",
    })
    monkeypatch.setattr(single_instance, "spawn_worker", spawn)
    monkeypatch.setattr(single_instance.websockets, "connect", AsyncMock(return_value=lease))
    connection, url, headers = await single_instance.discover(server, 60)
    assert len(launches) == 2
    assert connection is lease
    assert url == "http://127.0.0.1:43210/mcp"
    assert headers["X-FoxMCP-Lease"] == "lease"
