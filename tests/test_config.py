"""
Test configuration constants for FoxMCP testing
Ports come from port_coordinator, which assigns a fixed port per server role
"""

from port_coordinator import get_port_by_type

DEFAULT_TEST_CONFIG = {
    'test_timeout': 10.0,    # Default test timeout
    'server_startup_wait': 0.5,  # Time to wait for server startup
}

FIREFOX_TEST_CONFIG = {
    'profile_name': 'foxmcp-test-profile',
    'extension_install_wait': 3.0,  # Time for extension to install and connect
    'firefox_startup_wait': 5.0,    # Time for Firefox to fully start
}

def get_test_ports(suite_name):
    """Get the main websocket and MCP ports; suite_name is accepted but not used"""
    return {
        'websocket': get_port_by_type('websocket'),
        'mcp': get_port_by_type('mcp')
    }

def get_available_port_range(suite_name):
    """Get the websocket port as a single-port range, for callers that still expect a range"""
    # Return the websocket port as a single-port range (for backward compatibility)
    websocket_port = get_port_by_type('websocket')
    return (websocket_port, websocket_port)

# Backward compatibility - kept for existing tests
def get_firefox_test_port():
    """Get the websocket port used by Firefox extension tests"""
    ports = get_test_ports('integration_basic')
    return ports['websocket']

# Legacy TEST_PORTS for backward compatibility
def _get_test_ports_dict():
    """Build the legacy TEST_PORTS dictionary from the assigned ports"""
    return {
        'integration': get_test_ports('integration_basic'),              # Shared by Firefox and WebSocket server tests
        'integration_mcp': get_test_ports('integration_mcp'),            # MCP protocol functionality tests
    }

TEST_PORTS = _get_test_ports_dict()