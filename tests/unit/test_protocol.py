"""
Unit tests for WebSocket protocol message handling
"""

import pytest
import json
import time
import re
from datetime import datetime
from pathlib import Path

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
    
    def test_error_codes_match_extension_documentation(self):
        """Pair the error reference with real emitters, not a fixture-only list."""
        root = Path(__file__).resolve().parents[2]
        source = (root / "extension/background.js").read_text()
        # Literal codes, container helper errors and sendError fallback codes.
        codes = set(re.findall(r"sendError\(id,\s*'([A-Z_]+)'", source))
        codes.update(re.findall(r"containerError\('([A-Z_]+)'", source))
        codes.update(re.findall(
            r"sendError\(id,\s*\w+\.\w+\s*\|\|\s*'([A-Z_]+)'", source))
        # Consent errors are attached to Error.code before sendError receives them.
        gate = source.split("class ScriptConsentGate", 1)[1].split(
            "const scriptConsent =", 1)[0]
        codes.update(re.findall(r"'(SCRIPT_[A-Z_]+)'", gate))
        assert {"API_ERROR", "UNKNOWN_ACTION", "SCRIPT_ERROR"} <= codes
        doc = (root / "docs/protocol.md").read_text()
        section = doc.split("## Error Codes\n", 1)[1].split("## Test Helper Messages", 1)[0]
        documented = set(re.findall(r"^\| `([A-Z_]+)` \|", section, re.MULTILINE))
        assert documented == codes, (
            f"undocumented: {sorted(codes - documented)}; "
            f"not emitted: {sorted(documented - codes)}")

    def test_documented_error_envelope_matches_extension(self, sample_error):
        """The shared fixture and example must reflect the actual error sender."""
        root = Path(__file__).resolve().parents[2]
        source = (root / "extension/background.js").read_text()
        sender = source.split("function sendError(", 1)[1].split("\n}", 1)[0]
        assert "details = {}" in sender
        doc = (root / "docs/protocol.md").read_text()
        section = doc.split("## Error Messages\n", 1)[1].split("## Error Codes", 1)[0]
        example = json.loads(re.search(r"```json\n(.*?)```", section, re.DOTALL)[1])
        for key in ("type", "action"):
            value = re.search(rf"\b{key}:\s*'([^']*)'", sender)[1]
            assert example[key] == sample_error[key] == value
        assert example["data"]["code"] == sample_error["data"]["code"]
        assert example["data"]["details"] == sample_error["data"]["details"] == {}

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