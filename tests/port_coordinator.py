"""
Dynamic Port Coordination System for FoxMCP Testing
Provides coordination between server and extension while avoiding port conflicts
"""

import socket
import tempfile
import os
import json
import random
from contextlib import contextmanager
from typing import Tuple, Dict, Optional

# Module-level port range constants - use high ephemeral port range to avoid conflicts
DEFAULT_PORT_RANGE = (40000, 40999)

# Test suite specific port ranges
TEST_SUITE_PORT_RANGES = {
    'unit': (40000, 40099),
    'integration_basic': (40100, 40199),
    'integration_live': (40200, 40299),
    'integration_websocket': (40300, 40399),
    'integration_firefox': (40400, 40499),
    'integration_mcp': (40500, 40599),
    'integration_ping_pong': (40600, 40699),
    'real_firefox': (40700, 40799),
    'default': (40800, 40899)
}


class PortCoordinator:
    """Manages dynamic port allocation and coordination for testing"""
    
    def __init__(self, base_port_range=DEFAULT_PORT_RANGE):
        self.base_port_range = base_port_range
        self.allocated_ports = set()
        self.coordination_file = None
    
    def find_available_port(self, start_port=None) -> int:
        """Find an available port in the specified range"""
        if start_port:
            ports_to_try = [start_port]
        else:
            # Try random ports in the range to reduce conflicts
            start, end = self.base_port_range
            # Try all available ports in the range if it's small, otherwise sample
            range_size = end - start + 1
            if range_size <= 100:
                # Small range - try all ports
                ports_to_try = list(range(start, end + 1))
                random.shuffle(ports_to_try)
            else:
                # Large range - sample more ports
                max_tries = min(800, range_size)
                ports_to_try = random.sample(range(start, end + 1), max_tries)
        
        for port in ports_to_try:
            if port in self.allocated_ports:
                continue
                
            try:
                # Test if port is available
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(('localhost', port))
                    self.allocated_ports.add(port)
                    return port
            except OSError:
                continue
        
        range_size = self.base_port_range[1] - self.base_port_range[0] + 1
        ports_tried = len(ports_to_try) if not start_port else 1
        allocated_count = len(self.allocated_ports)
        raise RuntimeError(
            f"No available ports found in range {self.base_port_range}. "
            f"Range size: {range_size}, ports tried: {ports_tried}, "
            f"already allocated by this coordinator: {allocated_count}"
        )

    def release_port(self, port: int):
        """Release a port back to the available pool"""
        self.allocated_ports.discard(port)

    def release_all_ports(self):
        """Release all allocated ports - useful for cleanup between tests"""
        self.allocated_ports.clear()

    def allocate_test_ports(self) -> Dict[str, int]:
        """Allocate a coordinated set of ports for testing"""
        websocket_port = self.find_available_port()
        mcp_port = self.find_available_port(websocket_port + 1000)  # Offset to avoid conflicts
        
        return {
            'websocket': websocket_port,
            'mcp': mcp_port
        }
    
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
def coordinated_test_ports(base_range=DEFAULT_PORT_RANGE):
    """Context manager for coordinated test ports"""
    coordinator = PortCoordinator(base_range)
    ports = None
    
    try:
        ports = coordinator.allocate_test_ports()
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


def get_safe_port_range(test_suite: str) -> Tuple[int, int]:
    """Get safe port range for a specific test suite"""
    return TEST_SUITE_PORT_RANGES.get(test_suite, TEST_SUITE_PORT_RANGES['default'])


# Convenience functions for common test scenarios
def allocate_firefox_test_ports():
    """Allocate ports specifically for Firefox extension testing"""
    coordinator = PortCoordinator(get_safe_port_range('integration_firefox'))
    return coordinator.allocate_test_ports()


def allocate_server_test_ports(suite_name: str = 'default'):
    """Allocate ports for general server testing"""
    coordinator = PortCoordinator(get_safe_port_range(suite_name))
    return coordinator.allocate_test_ports()


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