#!/usr/bin/env python3
"""
Test the port coordination system
"""

import test_imports  # Automatic path setup
import sys
import os
import json
import tempfile
import re

from port_coordinator import coordinated_test_ports, FirefoxPortCoordinator
from firefox_test_utils import FirefoxTestManager

def test_port_coordination_basic():
    """Test basic port coordination functionality"""
    print("Testing basic port coordination...")
    
    # Test 1: Basic port allocation
    with coordinated_test_ports() as (ports, coord_file):
        print(f"✓ Allocated ports: {ports}")
        print(f"✓ Coordination file: {coord_file}")
        
        # Verify coordination file exists and is readable
        assert os.path.exists(coord_file), "Coordination file should exist"
        
        with open(coord_file, 'r') as f:
            data = json.load(f)
            assert data['websocket_port'] == ports['websocket']
            assert data['mcp_port'] == ports['mcp']
        
        print("✓ Coordination file contains correct port information")
    
    # After context exit, file should be cleaned up
    assert not os.path.exists(coord_file), "Coordination file should be cleaned up"
    print("✓ Coordination file cleaned up after context exit")

def test_firefox_coordination():
    """Test Firefox extension coordination"""
    print("\nTesting Firefox extension coordination...")
    
    with coordinated_test_ports() as (ports, coord_file):
        # Test Firefox configuration
        with tempfile.TemporaryDirectory() as temp_profile:
            configured_port = FirefoxPortCoordinator.create_extension_config(coord_file, temp_profile)
            
            assert configured_port == ports['websocket']
            print(f"✓ Firefox configured for WebSocket port: {configured_port}")
            
            # Verify configuration file was created
            config_path = os.path.join(temp_profile, 'browser-extension-data', 'foxmcp@codemud.org', 'config.json')
            assert os.path.exists(config_path), "Extension config should be created"
            
            # Verify config content
            with open(config_path, 'r') as f:
                config = json.load(f)
                assert config['port'] == ports['websocket']
                assert config['hostname'] == 'localhost'
            
            print("✓ Extension configuration file created with correct settings")

def test_firefox_test_manager_coordination():
    """Test FirefoxTestManager with port coordination"""
    print("\nTesting FirefoxTestManager with coordination...")
    
    with coordinated_test_ports() as (ports, coord_file):
        # Create Firefox manager with coordination
        firefox = FirefoxTestManager(test_port=ports['websocket'], coordination_file=coord_file)
        
        # The coordination should be handled internally by the test manager
        try:
            # Verify port was set correctly
            assert firefox.test_port == ports['websocket']
            print(f"✓ Firefox manager configured for port: {firefox.test_port}")

            # Note: setup_and_start_firefox() would normally be called here, but for this test
            # we're just verifying the coordination setup, not actually starting Firefox
            print("✓ Firefox test manager coordination verified")

        finally:
            firefox.cleanup()

def test_multiple_coordination_instances():
    """Test that nested coordination instances agree on ports and keep separate files"""
    print("\nTesting multiple coordination instances...")

    # Ports are fixed per role, so both instances name the same two ports. What
    # must differ is the coordination file: each Firefox profile reads its own
    # copy, and a shared path would let one instance delete the other's file on
    # exit.
    with coordinated_test_ports() as (ports1, coord_file1):
        with coordinated_test_ports() as (ports2, coord_file2):
            assert ports1['websocket'] == ports2['websocket']
            assert ports1['mcp'] == ports2['mcp']
            assert coord_file1 != coord_file2
            assert os.path.exists(coord_file1)
            assert os.path.exists(coord_file2)

            print(f"✓ Instance 1 ports: {ports1} ({coord_file1})")
            print(f"✓ Instance 2 ports: {ports2} ({coord_file2})")
            print("✓ Nested coordination instances share ports and keep separate files")

if __name__ == "__main__":
    print("🧪 Running Port Coordination Tests...")
    
    try:
        test_port_coordination_basic()
        test_firefox_coordination() 
        test_firefox_test_manager_coordination()
        test_multiple_coordination_instances()
        
        print("\n🎉 All port coordination tests passed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)