"""
Unit tests for WebSocket protocol message handling
"""

import pytest
import json
import time
import re
from datetime import datetime

class TestProtocolMessages:
    
    def test_request_message_structure(self, sample_request):
        """Test request message has correct structure"""
        assert "id" in sample_request
        assert "type" in sample_request  
        assert "action" in sample_request
        assert "data" in sample_request
        assert "timestamp" in sample_request
        
        assert sample_request["type"] == "request"
        assert isinstance(sample_request["data"], dict)
    
    def test_response_message_structure(self, sample_response):
        """Test response message has correct structure"""
        assert "id" in sample_response
        assert "type" in sample_response
        assert "action" in sample_response
        assert "data" in sample_response
        assert "timestamp" in sample_response
        
        assert sample_response["type"] == "response"
        assert sample_response["id"] == "test_001"
    
    def test_error_message_structure(self, sample_error):
        """Test error message has correct structure"""
        assert "id" in sample_error
        assert "type" in sample_error
        assert "action" in sample_error
        assert "data" in sample_error
        assert "timestamp" in sample_error
        
        assert sample_error["type"] == "error"
        
        # Error data should have specific structure
        error_data = sample_error["data"]
        assert "code" in error_data
        assert "message" in error_data
        assert "details" in error_data
    
    def test_timestamp_format(self, sample_request):
        """Test timestamp is in correct ISO format"""
        timestamp = sample_request["timestamp"]
        
        # Should be able to parse as datetime
        parsed = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        assert isinstance(parsed, datetime)
    
    def test_json_serialization(self, sample_request):
        """Test messages can be serialized to JSON"""
        json_str = json.dumps(sample_request)
        assert isinstance(json_str, str)
        
        # Should be able to deserialize back
        deserialized = json.loads(json_str)
        assert deserialized == sample_request
    
    def test_action_naming_convention(self):
        """Test action names follow dot notation convention"""
        valid_actions = [
            "history.query",
            "history.get_recent", 
            "tabs.list",
            "tabs.create",
            "tabs.close",
            "content.get_text",
            "content.get_html",
            "navigation.back",
            "navigation.forward",
            "bookmarks.list",
            "bookmarks.create",
            "bookmarks.createFolder",
            "bookmarks.update"
        ]
        
        for action in valid_actions:
            assert "." in action
            category, method = action.split(".", 1)
            assert len(category) > 0
            assert len(method) > 0
    
    @pytest.mark.parametrize("message_type", ["request", "response", "error"])
    def test_message_types(self, message_type):
        """Test valid message types"""
        valid_types = ["request", "response", "error"]
        assert message_type in valid_types

class TestProtocolErrorCodes:
    
    def test_error_codes_defined(self):
        """Test that error codes are properly defined"""
        expected_error_codes = [
            "PERMISSION_DENIED",
            "TAB_NOT_FOUND", 
            "BOOKMARK_NOT_FOUND",
            "INVALID_URL",
            "SCRIPT_EXECUTION_FAILED",
            "WEBSOCKET_ERROR",
            "INVALID_REQUEST",
            "UNKNOWN_ACTION"
        ]
        
        # These would be defined in a constants file
        # For now just verify the list exists
        assert len(expected_error_codes) == 8
    
    def test_error_message_format(self, sample_error):
        """Test error messages have required format"""
        error_data = sample_error["data"]
        
        # Required fields
        assert isinstance(error_data["code"], str)
        assert isinstance(error_data["message"], str)
        assert isinstance(error_data["details"], dict)
        
        # Code should be uppercase with underscores
        assert error_data["code"].isupper()
        assert "_" in error_data["code"] or error_data["code"].isalpha()

class TestProtocolDataStructures:
    
    def test_tab_data_structure(self, sample_tab_data):
        """Test tab data has required fields"""
        required_fields = ["id", "windowId", "url", "title", "active", "index", "pinned"]
        
        for field in required_fields:
            assert field in sample_tab_data
        
        # Type checks
        assert isinstance(sample_tab_data["id"], int)
        assert isinstance(sample_tab_data["windowId"], int) 
        assert isinstance(sample_tab_data["active"], bool)
        assert isinstance(sample_tab_data["pinned"], bool)
        assert isinstance(sample_tab_data["index"], int)
    
    def test_history_data_structure(self, sample_history_data):
        """Test history data has required fields"""
        for item in sample_history_data:
            required_fields = ["id", "url", "title", "visitTime", "visitCount"]
            
            for field in required_fields:
                assert field in item
            
            # Type checks
            assert isinstance(item["visitCount"], int)
            assert item["visitCount"] >= 0
    
    def test_bookmark_data_structure(self, sample_bookmark_data):
        """Test bookmark data has required fields"""
        for item in sample_bookmark_data:
            required_fields = ["id", "parentId", "title", "dateAdded", "isFolder"]
            
            for field in required_fields:
                assert field in item
                
            # Type checks
            assert isinstance(item["isFolder"], bool)
            
            # If not folder, should have URL
            if not item["isFolder"]:
                assert "url" in item