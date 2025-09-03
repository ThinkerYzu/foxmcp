"""
Pytest configuration and fixtures
"""

import asyncio
import json
import pytest
from unittest.mock import Mock, AsyncMock
from typing import Dict, Any

# Test fixtures
@pytest.fixture
def sample_request():
    """Sample WebSocket request message"""
    return {
        "id": "test_001",
        "type": "request",
        "action": "tabs.list",
        "data": {},
        "timestamp": "2025-09-03T12:00:00.000Z"
    }

@pytest.fixture
def sample_response():
    """Sample WebSocket response message"""
    return {
        "id": "test_001", 
        "type": "response",
        "action": "tabs.list",
        "data": {
            "tabs": [
                {
                    "id": 123,
                    "windowId": 1,
                    "url": "https://example.com",
                    "title": "Example Page",
                    "active": True,
                    "index": 0,
                    "pinned": False
                }
            ]
        },
        "timestamp": "2025-09-03T12:00:01.000Z"
    }

@pytest.fixture
def sample_error():
    """Sample WebSocket error message"""
    return {
        "id": "test_001",
        "type": "error",
        "action": "tabs.close", 
        "data": {
            "code": "TAB_NOT_FOUND",
            "message": "Tab with ID 999 not found",
            "details": {"tabId": 999}
        },
        "timestamp": "2025-09-03T12:00:01.000Z"
    }

@pytest.fixture
def mock_websocket():
    """Mock WebSocket connection"""
    mock_ws = AsyncMock()
    mock_ws.send = AsyncMock()
    mock_ws.close = AsyncMock()
    mock_ws.remote_address = ("127.0.0.1", 12345)
    return mock_ws

@pytest.fixture
def mock_chrome_api():
    """Mock Chrome extension API"""
    chrome_mock = Mock()
    
    # Mock chrome.tabs
    chrome_mock.tabs = Mock()
    chrome_mock.tabs.query = Mock()
    chrome_mock.tabs.create = Mock() 
    chrome_mock.tabs.remove = Mock()
    chrome_mock.tabs.update = Mock()
    
    # Mock chrome.history
    chrome_mock.history = Mock()
    chrome_mock.history.search = Mock()
    chrome_mock.history.deleteUrl = Mock()
    chrome_mock.history.deleteRange = Mock()
    
    # Mock chrome.bookmarks
    chrome_mock.bookmarks = Mock()
    chrome_mock.bookmarks.getTree = Mock()
    chrome_mock.bookmarks.search = Mock()
    chrome_mock.bookmarks.create = Mock()
    chrome_mock.bookmarks.remove = Mock()
    
    return chrome_mock

@pytest.fixture
def event_loop():
    """Create event loop for async tests"""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def sample_tab_data():
    """Sample tab data for testing"""
    return {
        "id": 123,
        "windowId": 1,
        "url": "https://example.com",
        "title": "Example Page", 
        "active": True,
        "index": 0,
        "pinned": False,
        "favIconUrl": "https://example.com/favicon.ico"
    }

@pytest.fixture 
def sample_history_data():
    """Sample history data for testing"""
    return [
        {
            "id": "hist_123",
            "url": "https://github.com/user/repo",
            "title": "GitHub Repository",
            "visitTime": "2025-09-02T14:30:00.000Z",
            "visitCount": 5
        },
        {
            "id": "hist_124", 
            "url": "https://example.com",
            "title": "Example Site",
            "visitTime": "2025-09-02T15:00:00.000Z", 
            "visitCount": 2
        }
    ]

@pytest.fixture
def sample_bookmark_data():
    """Sample bookmark data for testing"""
    return [
        {
            "id": "bm_001",
            "parentId": "1",
            "title": "GitHub",
            "url": "https://github.com",
            "dateAdded": "2025-09-01T10:00:00.000Z",
            "isFolder": False
        },
        {
            "id": "bm_002",
            "parentId": "1", 
            "title": "Development",
            "dateAdded": "2025-09-01T09:00:00.000Z",
            "isFolder": True,
            "children": []
        }
    ]