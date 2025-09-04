"""
Test configuration constants for FoxMCP testing
Provides fixed port assignments for reliable testing
"""

# Fixed test port assignments to ensure extension-server coordination
TEST_PORTS = {
    # WebSocket server ports for different test suites
    'unit_tests': {
        'websocket': 8700,
        'mcp': 3100,
    },
    'integration_basic': {
        'websocket': 8701, 
        'mcp': 3101,
    },
    'integration_live': {
        'websocket': 8702,
        'mcp': 3102,
    },
    'integration_websocket': {
        'websocket': 8703,
        'mcp': 3103,
    },
    'integration_firefox': {
        'websocket': 8704,  # Extension will connect here for Firefox tests
        'mcp': 3104,
    },
    'integration_mcp': {
        'websocket': 8705,
        'mcp': 3105,
    },
    'integration_ping_pong': {
        'websocket': 8706,
        'mcp': 3106,
    }
}

# Default test configuration
DEFAULT_TEST_CONFIG = {
    'websocket_port': 8765,  # Default for extension
    'mcp_port': 3000,        # Default for MCP clients
    'test_timeout': 10.0,    # Default test timeout
    'server_startup_wait': 0.5,  # Time to wait for server startup
}

# Firefox extension test configuration
FIREFOX_TEST_CONFIG = {
    'websocket_port': TEST_PORTS['integration_firefox']['websocket'],
    'mcp_port': TEST_PORTS['integration_firefox']['mcp'],
    'profile_name': 'foxmcp-test-profile',
    'extension_install_wait': 3.0,  # Time for extension to install and connect
    'firefox_startup_wait': 5.0,    # Time for Firefox to fully start
}

def get_test_ports(suite_name):
    """Get port configuration for a specific test suite"""
    return TEST_PORTS.get(suite_name, TEST_PORTS['integration_basic'])

def get_firefox_test_port():
    """Get the fixed port that Firefox extension should connect to during tests"""
    return FIREFOX_TEST_CONFIG['websocket_port']

def get_available_port_range(suite_name):
    """Get a safe port range for dynamic allocation within a test suite"""
    base_port = TEST_PORTS.get(suite_name, TEST_PORTS['integration_basic'])['websocket']
    return range(base_port + 10, base_port + 100)  # 90 port range for dynamic allocation