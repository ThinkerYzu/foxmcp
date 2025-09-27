"""
Test configuration constants for FoxMCP testing
Uses dynamic port allocation to avoid conflicts
"""

from port_coordinator import get_port_by_type

# Default test configuration - uses dynamic ports
DEFAULT_TEST_CONFIG = {
    'test_timeout': 10.0,    # Default test timeout
    'server_startup_wait': 0.5,  # Time to wait for server startup
}

# Firefox extension test configuration - uses dynamic ports
FIREFOX_TEST_CONFIG = {
    'profile_name': 'foxmcp-test-profile',
    'extension_install_wait': 3.0,  # Time for extension to install and connect
    'firefox_startup_wait': 5.0,    # Time for Firefox to fully start
}

def get_test_ports(suite_name):
    """Get dynamically allocated port configuration for a specific test suite"""
    return {
        'websocket': get_port_by_type('websocket'),
        'mcp': get_port_by_type('mcp')
    }

def get_available_port_range(suite_name):
    """Get a safe port range for dynamic allocation within a test suite"""
    # Return the websocket port as a single-port range (for backward compatibility)
    websocket_port = get_port_by_type('websocket')
    return (websocket_port, websocket_port)

# Backward compatibility - kept for existing tests
def get_firefox_test_port():
    """Get a dynamically allocated port for Firefox extension tests"""
    ports = get_test_ports('integration_basic')
    return ports['websocket']

# Legacy TEST_PORTS for backward compatibility
def _get_test_ports_dict():
    """Get test ports dictionary with dynamic allocation"""
    return {
        'integration': get_test_ports('integration_basic'),              # Shared by Firefox and WebSocket server tests
        'integration_mcp': get_test_ports('integration_mcp'),            # MCP protocol functionality tests
    }

TEST_PORTS = _get_test_ports_dict()