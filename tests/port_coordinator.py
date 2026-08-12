"""
Port Assignments for FoxMCP Testing

Gives every test server a port well away from the ones a live FoxMCP server
uses (8767 for the websocket, 3000 for MCP), so running the suite never
disturbs a running installation.

Each role gets one fixed port rather than a port picked from a range. Tests run
sequentially in a single process, so only one server holds a port at a time,
and SO_REUSEADDR lets the next test rebind it without waiting out TIME_WAIT.
Fixed ports also keep the Firefox profile cache worth having: a cached profile
records the port it was built for, so a stable port means the profile is reused
instead of rebuilt from scratch.

The cost is that two test runs at once collide - the second one fails to bind
with "address already in use". Run one suite at a time.

Main API:
- get_port_by_type(port_type): Get the port assigned to a role
- coordinated_test_ports(): Context manager pairing a websocket and MCP port
  with a coordination file, for Firefox extension tests

Port Types:
- 'websocket': Main websocket server port (40000)
- 'mcp': Main MCP server port (40200)
- 'test_individual': Individual test websocket port (40400)
- 'test_mcp_individual': Individual test MCP port (40600)
"""

import tempfile
import os
import json
import time
from contextlib import contextmanager
from typing import Tuple, Dict, Optional

# The port assigned to each server role, kept high to stay clear of the live
# server and of anything else likely to be listening on a developer's machine.
FIXED_PORTS = {
    'websocket': 40000,
    'mcp': 40200,
    'test_individual': 40400,
    'test_mcp_individual': 40600
}


class PortCoordinator:
    """Hands out test server ports and the coordination file that shares them with Firefox"""

    def __init__(self):
        self.coordination_file = None

    def get_port_by_type(self, port_type: str) -> int:
        """
        Return the port assigned to a server role.

        Raises ValueError for an unknown role, since a typo would otherwise
        surface much later as a connection that never arrives.
        """
        if port_type not in FIXED_PORTS:
            raise ValueError(f"Invalid port type '{port_type}'. Available types: {list(FIXED_PORTS.keys())}")

        return FIXED_PORTS[port_type]

    def create_coordination_file(self, ports: Dict[str, int]) -> str:
        """Create a temporary file with port coordination info"""
        # Create temp file that both server and extension can access
        fd, path = tempfile.mkstemp(prefix='foxmcp-ports-', suffix='.json')
        
        try:
            with os.fdopen(fd, 'w') as f:
                coordination_data = {
                    'websocket_port': ports['websocket'],
                    'mcp_port': ports['mcp'],
                    'hostname': 'localhost',
                    'timestamp': str(int(os.time.time())) if hasattr(os, 'time') else '0'
                }
                json.dump(coordination_data, f, indent=2)
            
            self.coordination_file = path
            return path
            
        except Exception:
            # Cleanup on error
            try:
                os.close(fd)
                os.unlink(path)
            except:
                pass
            raise
    
    def read_coordination_file(self, file_path: str) -> Optional[Dict[str, int]]:
        """Read port coordination from file"""
        try:
            with open(file_path, 'r') as f:
                data = json.load(f)
                return {
                    'websocket': data['websocket_port'],
                    'mcp': data['mcp_port']
                }
        except Exception:
            return None
    
    def cleanup(self):
        """Clean up coordination file"""
        if self.coordination_file and os.path.exists(self.coordination_file):
            try:
                os.unlink(self.coordination_file)
            except:
                pass
            self.coordination_file = None


@contextmanager
def coordinated_test_ports():
    """
    Yield the individual-test port pair together with a coordination file.

    Firefox cannot be told the port on the command line, so the extension reads
    it from the coordination file this creates; the file is removed on exit.
    Ports are the fixed individual-test pair, so nested or repeated use hands
    back the same two numbers.
    """
    coordinator = PortCoordinator()

    try:
        websocket_port = get_port_by_type('test_individual')
        mcp_port = get_port_by_type('test_mcp_individual')

        ports = {
            'websocket': websocket_port,
            'mcp': mcp_port
        }

        coordination_file = coordinator.create_coordination_file(ports)

        # Provide both ports and coordination file path
        yield ports, coordination_file

    finally:
        coordinator.cleanup()


class FirefoxPortCoordinator:
    """Specialized coordinator for Firefox extension testing"""
    
    @staticmethod
    def create_extension_config(coordination_file: str, profile_dir: str):
        """Create extension configuration from coordination file"""
        coordinator = PortCoordinator()
        ports = coordinator.read_coordination_file(coordination_file)
        
        if not ports:
            raise ValueError(f"Could not read coordination file: {coordination_file}")
        
        # Create extension storage directory
        storage_dir = os.path.join(profile_dir, 'browser-extension-data', 'foxmcp@codemud.org')
        os.makedirs(storage_dir, exist_ok=True)
        
        # Write extension configuration
        extension_config = {
            'hostname': 'localhost',
            'port': ports['websocket'],
            'retryInterval': 1000,  # Fast retry for testing
            'maxRetries': 5,        # Limited retries
            'pingTimeout': 2000     # Short timeout
        }
        
        config_file = os.path.join(storage_dir, 'config.json')
        with open(config_file, 'w') as f:
            json.dump(extension_config, f, indent=2)
        
        return ports['websocket']
    
    @staticmethod  
    def wait_for_coordination_file(file_path: str, timeout: float = 10.0) -> Optional[Dict[str, int]]:
        """Wait for coordination file to be created"""
        import time
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if os.path.exists(file_path):
                coordinator = PortCoordinator()
                ports = coordinator.read_coordination_file(file_path)
                if ports:
                    return ports
            time.sleep(0.1)
        
        return None


def get_port_by_type(port_type: str) -> int:
    """Return the port assigned to a role - the one entry point tests should use for ports"""
    coordinator = PortCoordinator()
    return coordinator.get_port_by_type(port_type)


# Note: Context manager (coordinated_test_ports) is kept for specific use cases
# All other port allocation should use get_port_by_type() directly




if __name__ == "__main__":
    # Test the port coordination system
    print("Testing Port Coordination System...")
    
    # Test 1: Basic port allocation
    with coordinated_test_ports() as (ports, coord_file):
        print(f"✓ Allocated ports: {ports}")
        print(f"✓ Coordination file: {coord_file}")
        
        # Test reading coordination file
        coordinator = PortCoordinator()
        read_ports = coordinator.read_coordination_file(coord_file)
        assert read_ports == ports
        print(f"✓ Coordination file readable: {read_ports}")
    
    # Test 2: Firefox coordination
    try:
        import tempfile
        with tempfile.TemporaryDirectory() as temp_dir:
            with coordinated_test_ports() as (ports, coord_file):
                firefox_port = FirefoxPortCoordinator.create_extension_config(coord_file, temp_dir)
                assert firefox_port == ports['websocket']
                print(f"✓ Firefox extension configured for port: {firefox_port}")
    except Exception as e:
        print(f"✗ Firefox coordination test failed: {e}")
    
    print("🎉 Port Coordination System working correctly!")
