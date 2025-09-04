"""
Firefox testing utilities for FoxMCP
Handles Firefox profile creation, extension configuration, and test coordination
"""

import os
import json
import tempfile
import shutil
import time
import subprocess
from pathlib import Path
try:
    from .test_config import FIREFOX_TEST_CONFIG, get_firefox_test_port
    from .port_coordinator import FirefoxPortCoordinator
except ImportError:
    from test_config import FIREFOX_TEST_CONFIG, get_firefox_test_port
    from port_coordinator import FirefoxPortCoordinator

class FirefoxTestManager:
    """Manages Firefox instances for testing with proper extension configuration"""
    
    def __init__(self, firefox_path=None, test_port=None, coordination_file=None):
        self.firefox_path = firefox_path or os.environ.get('FIREFOX_PATH', '~/tmp/ff2/bin/firefox')
        self.test_port = test_port or get_firefox_test_port()
        self.coordination_file = coordination_file
        self.profile_dir = None
        self.firefox_process = None
        
    def create_test_profile(self):
        """Create a temporary Firefox profile configured for testing"""
        self.profile_dir = tempfile.mkdtemp(prefix='foxmcp-test-')
        
        # Create user.js with extension settings and test configuration
        user_js_content = f'''
// Extension installation settings
user_pref("xpinstall.signatures.required", false);
user_pref("extensions.autoDisableScopes", 0);
user_pref("extensions.enabledScopes", 15);
user_pref("dom.disable_open_during_load", false);
user_pref("browser.tabs.remote.autostart", false);

// Disable various Firefox features for faster testing
user_pref("browser.startup.homepage", "about:blank");
user_pref("startup.homepage_welcome_url", "");
user_pref("startup.homepage_welcome_url.additional", "");
user_pref("browser.newtabpage.enabled", false);
user_pref("browser.newtab.url", "about:blank");

// Disable Firefox updates and telemetry for testing
user_pref("app.update.enabled", false);
user_pref("app.update.auto", false);
user_pref("toolkit.telemetry.enabled", false);
user_pref("datareporting.healthreport.uploadEnabled", false);

// Speed up for testing
user_pref("dom.max_script_run_time", 0);
user_pref("dom.max_chrome_script_run_time", 0);
'''
        
        with open(os.path.join(self.profile_dir, 'user.js'), 'w') as f:
            f.write(user_js_content)
            
        # Create extension storage with test configuration
        self.setup_extension_test_config()
        
        return self.profile_dir
    
    def setup_extension_test_config(self):
        """Pre-configure extension storage with test server settings"""
        # Use coordination file if available, otherwise use test_port
        if self.coordination_file:
            try:
                self.test_port = FirefoxPortCoordinator.create_extension_config(
                    self.coordination_file, self.profile_dir
                )
                print(f"✓ Extension configured from coordination file for port {self.test_port}")
                return
            except Exception as e:
                print(f"⚠ Failed to use coordination file: {e}, falling back to direct config")
        
        # Fallback to direct configuration
        # Create extension storage directory structure
        extensions_dir = os.path.join(self.profile_dir, 'extensions')
        os.makedirs(extensions_dir, exist_ok=True)
        
        # Create storage directory for extension settings
        storage_dir = os.path.join(self.profile_dir, 'browser-extension-data', 'foxmcp@codemud.org')
        os.makedirs(storage_dir, exist_ok=True)
        
        # Pre-configure extension with test server settings
        extension_config = {
            'hostname': 'localhost',
            'port': self.test_port,
            'retryInterval': 1000,  # Faster retry for testing
            'maxRetries': 5,        # Limited retries for faster test failures
            'pingTimeout': 2000     # Shorter timeout for testing
        }
        
        # Save configuration that extension will load
        config_file = os.path.join(storage_dir, 'config.json')
        with open(config_file, 'w') as f:
            json.dump(extension_config, f)
            
        print(f"✓ Pre-configured extension for test server port {self.test_port}")
    
    def install_extension(self, extension_path):
        """Install extension to the test profile"""
        if not self.profile_dir:
            raise ValueError("Test profile not created. Call create_test_profile() first.")
            
        extensions_dir = os.path.join(self.profile_dir, 'extensions')
        os.makedirs(extensions_dir, exist_ok=True)
        
        # Copy extension XPI to extensions directory
        if os.path.exists(extension_path):
            extension_name = 'foxmcp@codemud.org.xpi'
            dest_path = os.path.join(extensions_dir, extension_name)
            shutil.copy2(extension_path, dest_path)
            print(f"✓ Extension installed to test profile: {extension_name}")
            return True
        else:
            print(f"✗ Extension not found: {extension_path}")
            return False
    
    def start_firefox(self, headless=True, wait_for_startup=True):
        """Start Firefox with the test profile and extension"""
        if not self.profile_dir:
            raise ValueError("Test profile not created. Call create_test_profile() first.")
        
        # Expand Firefox path
        firefox_path = os.path.expanduser(self.firefox_path)
        
        # Firefox command
        firefox_cmd = [
            firefox_path,
            '-profile', self.profile_dir,
            '-no-remote',
        ]
        
        if headless:
            firefox_cmd.append('-headless')
        
        try:
            self.firefox_process = subprocess.Popen(
                firefox_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            if wait_for_startup:
                time.sleep(FIREFOX_TEST_CONFIG['firefox_startup_wait'])
                
                # Check if process is still running
                if self.firefox_process.poll() is not None:
                    raise Exception(f"Firefox process exited immediately (code: {self.firefox_process.returncode})")
                    
            print(f"✓ Firefox started with test profile (PID: {self.firefox_process.pid})")
            return True
            
        except Exception as e:
            print(f"✗ Failed to start Firefox: {e}")
            return False
    
    def wait_for_extension_connection(self, timeout=10.0):
        """Wait for extension to connect to test server"""
        print(f"Waiting up to {timeout}s for extension to connect to port {self.test_port}...")
        
        # This would typically involve checking server connection status
        # For now, just wait the expected connection time
        time.sleep(FIREFOX_TEST_CONFIG['extension_install_wait'])
        
        if self.firefox_process and self.firefox_process.poll() is None:
            print("✓ Firefox process running, extension should be connected")
            return True
        else:
            print("✗ Firefox process not running")
            return False
    
    def stop_firefox(self):
        """Stop the Firefox process"""
        if self.firefox_process:
            try:
                self.firefox_process.terminate()
                self.firefox_process.wait(timeout=5)
                print("✓ Firefox stopped gracefully")
            except subprocess.TimeoutExpired:
                self.firefox_process.kill()
                self.firefox_process.wait()
                print("⚠ Firefox force killed")
            except Exception as e:
                print(f"⚠ Error stopping Firefox: {e}")
            finally:
                self.firefox_process = None
    
    def cleanup(self):
        """Clean up test profile and stop Firefox"""
        self.stop_firefox()
        
        if self.profile_dir and os.path.exists(self.profile_dir):
            try:
                shutil.rmtree(self.profile_dir)
                print("✓ Test profile cleaned up")
            except Exception as e:
                print(f"⚠ Error cleaning up profile: {e}")
            finally:
                self.profile_dir = None
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()

def get_extension_xpi_path():
    """Get path to built extension XPI file"""
    # Try multiple possible project root locations
    current_file = Path(__file__)
    
    # First try: assume we're in tests/firefox_test_utils.py
    project_root = current_file.parent.parent
    xpi_path = project_root / 'dist' / 'packages' / 'foxmcp@codemud.org.xpi'
    
    if xpi_path.exists():
        return str(xpi_path)
    
    # Second try: search upward for the dist directory
    search_path = current_file.parent
    while search_path != search_path.parent:  # Stop at filesystem root
        potential_xpi = search_path / 'dist' / 'packages' / 'foxmcp@codemud.org.xpi'
        if potential_xpi.exists():
            return str(potential_xpi)
        search_path = search_path.parent
    
    # Third try: alternative location in extension directory
    project_root = current_file.parent.parent
    alt_path = project_root / 'extension' / 'foxmcp@codemud.org.xpi'
    if alt_path.exists():
        return str(alt_path)
    
    return None