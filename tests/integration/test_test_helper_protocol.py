"""
Test Helper Protocol Tests

Unit tests for the test helper protocol implementation without requiring Firefox.
Tests the server-side test helper methods and message formatting.
"""

import pytest
import pytest_asyncio
import asyncio
import json
import time
import re
from datetime import datetime

import sys
import os

import test_imports  # Automatic path setup
from server.server import FoxMCPServer


class MockWebSocket:
    """Mock WebSocket for testing without actual connection"""
    def __init__(self):
        self.sent_messages = []
        self.response_data = {}
        
    async def send(self, message):
        """Mock send method that stores messages"""
        self.sent_messages.append(json.loads(message))
        
        # Auto-respond to test helper requests
        msg_data = json.loads(message)
        if msg_data.get("action", "").startswith("test."):
            await self._auto_respond(msg_data)
    
    async def _auto_respond(self, request):
        """Generate mock responses for test helper requests"""
        action = request["action"]
        response = {
            "id": request["id"],
            "type": "response", 
            "action": action,
            "timestamp": datetime.now().isoformat()
        }
        
        # Mock response data based on action
        if action == "test.get_popup_state":
            response["data"] = {
                "serverUrl": "ws://localhost:7777",
                "retryInterval": 1000,
                "maxRetries": 5,
                "pingTimeout": 2000,
                "hasTestOverrides": True,
                "effectiveHostname": "localhost",
                "effectivePort": 7777,
                "testIndicatorShown": True,
                "storageValues": {
                    "hostname": "localhost",
                    "port": 8765,
                    "testPort": 7777,
                    "testHostname": "localhost"
                }
            }
        elif action == "test.get_options_state":
            response["data"] = {
                "displayHostname": "localhost",
                "displayPort": 7777,
                "retryInterval": 1000,
                "maxRetries": 5,
                "pingTimeout": 2000,
                "webSocketUrl": "ws://localhost:7777",
                "hasTestOverrides": True,
                "testOverrideWarningShown": True,
                "storageValues": {
                    "hostname": "localhost",
                    "port": 8765,
                    "testPort": 7777,
                    "testHostname": "localhost"
                }
            }
        elif action == "test.get_storage_values":
            response["data"] = {
                "hostname": "localhost",
                "port": 8765,
                "retryInterval": 1000,
                "maxRetries": 5,
                "pingTimeout": 2000,
                "testPort": 7777,
                "testHostname": "localhost"
            }
        elif action == "test.validate_ui_sync":
            response["data"] = {
                "popupSyncValid": True,
                "optionsSyncValid": True,
                "storageMatches": True,
                "effectiveValues": {
                    "hostname": "localhost",
                    "port": 7777
                },
                "issues": []
            }
        elif action == "test.refresh_ui_state":
            response["data"] = {
                "refreshed": True,
                "popupStateUpdated": True,
                "optionsStateUpdated": True,
                "timestamp": datetime.now().isoformat()
            }
        else:
            response["type"] = "error"
            response["data"] = {
                "code": "UNKNOWN_ACTION",
                "message": f"Unknown test action: {action}"
            }
        
        # Store response for the server to pick up
        self.response_data[request["id"]] = response


class TestTestHelperProtocol:
    """Test the test helper protocol implementation"""
    
    @pytest_asyncio.fixture
    async def mock_server(self):
        """Create server with mock WebSocket connection"""
        server = FoxMCPServer(port=0, start_mcp=False)  # Port 0 to avoid binding
        
        # Replace extension connection with mock
        mock_ws = MockWebSocket()
        server.extension_connection = mock_ws
        
        # Override send_to_extension to use mock
        async def mock_send_to_extension(message):
            await mock_ws.send(json.dumps(message))
            return True
        server.send_to_extension = mock_send_to_extension
        
        # Override send_request_and_wait to use mock responses
        async def mock_send_request_and_wait(request, timeout=5.0):
            await mock_ws.send(json.dumps(request))
            
            # Wait briefly for mock to generate response
            await asyncio.sleep(0.1)
            
            # Return mock response data (extract data field)
            response = mock_ws.response_data.get(request["id"], {"error": "No response"})
            if response.get("type") == "response" and "data" in response:
                return response["data"]
            return response
        server.send_request_and_wait = mock_send_request_and_wait
        
        return server, mock_ws
    
    @pytest.mark.asyncio
    async def test_get_popup_state_message_format(self, mock_server):
        """Test get_popup_state generates correct message format"""
        server, mock_ws = mock_server
        
        result = await server.get_popup_state()
        
        # Verify request was sent
        assert len(mock_ws.sent_messages) == 1
        request = mock_ws.sent_messages[0]
        
        # Verify request format
        assert request["type"] == "request"
        assert request["action"] == "test.get_popup_state"
        assert "id" in request
        assert "timestamp" in request
        assert request["data"] == {}
        
        # Verify response data
        assert "serverUrl" in result
        assert "hasTestOverrides" in result
        assert "effectivePort" in result
        assert result["effectivePort"] == 7777
        
    @pytest.mark.asyncio
    async def test_get_options_state_message_format(self, mock_server):
        """Test get_options_state generates correct message format"""
        server, mock_ws = mock_server
        
        result = await server.get_options_state()
        
        # Verify request was sent
        assert len(mock_ws.sent_messages) == 1
        request = mock_ws.sent_messages[0]
        
        # Verify request format
        assert request["type"] == "request"
        assert request["action"] == "test.get_options_state"
        assert "id" in request
        assert "timestamp" in request
        assert request["data"] == {}
        
        # Verify response data
        assert "displayHostname" in result
        assert "displayPort" in result
        assert "webSocketUrl" in result
        assert result["displayPort"] == 7777
        
    @pytest.mark.asyncio
    async def test_get_storage_values_message_format(self, mock_server):
        """Test get_storage_values generates correct message format"""
        server, mock_ws = mock_server
        
        result = await server.get_storage_values()
        
        # Verify request was sent
        request = mock_ws.sent_messages[0]
        assert request["action"] == "test.get_storage_values"
        
        # Verify response contains storage values
        assert "hostname" in result
        assert "port" in result
        assert "testPort" in result
        assert result["testPort"] == 7777
        
    @pytest.mark.asyncio
    async def test_validate_ui_sync_message_format(self, mock_server):
        """Test validate_ui_sync generates correct message format"""
        server, mock_ws = mock_server
        
        expected_values = {"testPort": 7777, "hostname": "localhost"}
        result = await server.validate_ui_sync(expected_values)
        
        # Verify request was sent with expected values
        request = mock_ws.sent_messages[0]
        assert request["action"] == "test.validate_ui_sync"
        assert request["data"]["expectedValues"] == expected_values
        
        # Verify response format
        assert "popupSyncValid" in result
        assert "optionsSyncValid" in result
        assert "storageMatches" in result
        assert "effectiveValues" in result
        assert "issues" in result
        
    @pytest.mark.asyncio
    async def test_refresh_ui_state_message_format(self, mock_server):
        """Test refresh_ui_state generates correct message format"""
        server, mock_ws = mock_server
        
        result = await server.refresh_ui_state()
        
        # Verify request format
        request = mock_ws.sent_messages[0]
        assert request["action"] == "test.refresh_ui_state"
        assert request["data"] == {}
        
        # Verify response format
        assert result["refreshed"] == True
        assert result["popupStateUpdated"] == True
        assert result["optionsStateUpdated"] == True
        
    @pytest.mark.asyncio
    async def test_test_storage_sync_workflow(self, mock_server):
        """Test complete storage sync workflow"""
        server, mock_ws = mock_server
        
        test_values = {"testPort": 7777, "hostname": "localhost"}
        result = await server.test_storage_sync_workflow(test_values)
        
        # Should have made multiple requests
        assert len(mock_ws.sent_messages) >= 4  # storage, popup, options, validate
        
        # Verify workflow result
        assert result["workflow_success"] == True
        assert len(result["errors"]) == 0
        assert "steps" in result
        
        # Verify all steps completed
        steps = result["steps"]
        assert "initial_storage" in steps
        assert "popup_state" in steps
        assert "options_state" in steps
        assert "validation" in steps
        
    @pytest.mark.asyncio
    async def test_request_id_generation(self, mock_server):
        """Test that each request gets a unique ID"""
        server, mock_ws = mock_server
        
        # Make multiple requests
        await server.get_popup_state()
        await server.get_options_state()
        await server.get_storage_values()
        
        # Verify all requests have unique IDs
        request_ids = [msg["id"] for msg in mock_ws.sent_messages]
        assert len(request_ids) == len(set(request_ids)), "All request IDs should be unique"
        
        # Verify ID format (should contain timestamp-like data)
        for request_id in request_ids:
            assert "test_" in request_id
            assert "_" in request_id
            
    @pytest.mark.asyncio
    async def test_message_timestamps(self, mock_server):
        """Test that messages include proper timestamps"""
        server, mock_ws = mock_server
        
        await server.get_popup_state()
        
        request = mock_ws.sent_messages[0]
        assert "timestamp" in request
        
        # Verify timestamp format (ISO format)
        timestamp = request["timestamp"]
        assert "T" in timestamp  # ISO format includes T between date and time
        assert ":" in timestamp  # Time includes colons
        

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])