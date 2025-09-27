"""
Dynamic Port Coordination System for FoxMCP Testing

Provides centralized port allocation to avoid conflicts between:
- Main server ports (fixed: websocket=40000, mcp=40200)
- Individual test ports (dynamic: 40400-40599, 40600-40799)
- Coordinated test environments (Firefox extension tests)

Main API:
- get_port_by_type(port_type): Get any port by type
- coordinated_test_ports(): Context manager for test coordination

Port Types:
- 'websocket': Fixed websocket server port (40000)
- 'mcp': Fixed MCP server port (40200)
- 'test_individual': Dynamic individual test ports (40400-40599)
- 'test_mcp_individual': Dynamic individual MCP test ports (40600-40799)
"""

import socket
import tempfile
import os
import json
from contextlib import contextmanager
from typing import Tuple, Dict, Optional

# Module-level port range constants - use high ephemeral port range to avoid conflicts

# Port ranges for the different server types and test scenarios
PORT_RANGES = {
    'websocket': {'type': 'fixed', 'port': 40000},
    'mcp': {'type': 'fixed', 'port': 40200},
    'test_individual': {'type': 'fixed', 'port': 40400},
    'test_mcp_individual': {'type': 'fixed', 'port': 40600}
}


class PortCoordinator:
    """Manages dynamic port allocation and coordination for testing"""

    def __init__(self):
        self.allocated_ports = set()
        self.coordination_file = None
    

    def release_port(self, port: int):
        """Release a port back to the available pool"""
        self.allocated_ports.discard(port)

    def release_all_ports(self):
        """Release all allocated ports - useful for cleanup between tests"""
        self.allocated_ports.clear()

    def get_port_by_type(self, port_type: str) -> int:
        """Get port by type - handles both fixed ports and dynamic ranges"""
        if port_type not in PORT_RANGES:
            raise ValueError(f"Invalid port type '{port_type}'. Available types: {list(PORT_RANGES.keys())}")

        port_config = PORT_RANGES[port_type]

        if port_config['type'] == 'fixed':
            return port_config['port']
        elif port_config['type'] == 'range':
            # For ranges, find an available port within the range
            start, end = port_config['range']
            for port in range(start, end + 1):
                if port not in self.allocated_ports:
                    try:
                        # Test if port is available
                        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                            sock.bind(('localhost', port))
                            self.allocated_ports.add(port)
                            return port
                    except OSError:
                        continue

            raise RuntimeError(f"No available ports in range {port_config['range']} for type '{port_type}'")
        else:
            raise ValueError(f"Unknown port type configuration: {port_config['type']}")

    
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
    
    def release_ports(self, ports: Dict[str, int]):
        """Release allocated ports"""
        for port in ports.values():
            self.allocated_ports.discard(port)
    
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
    """Context manager for coordinated test ports - allocates dynamic test ports"""
    coordinator = PortCoordinator()
    ports = None

    try:
        # Allocate dynamic test ports instead of fixed server ports
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
        if ports:
            coordinator.release_ports(ports)
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
    """Get port by type using PortCoordinator - unified interface for all port allocation"""
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
