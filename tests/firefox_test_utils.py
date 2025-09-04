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
import sqlite3
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

        # Note: Extension configuration is now handled via SQLite storage
        # after installation in the _configure_extension_storage() method

        print(f"✓ Pre-configured extension for test server port {self.test_port}")

    def install_extension(self, extension_path):
        """Install extension to the test profile and initialize extensions.json"""
        if not self.profile_dir:
            raise ValueError("Test profile not created. Call create_test_profile() first.")

        extensions_dir = os.path.join(self.profile_dir, 'extensions')
        os.makedirs(extensions_dir, exist_ok=True)

        # Copy extension XPI to extensions directory
        if not os.path.exists(extension_path):
            print(f"✗ Extension not found: {extension_path}")
            return False

        extension_name = 'foxmcp@codemud.org.xpi'
        dest_path = os.path.join(extensions_dir, extension_name)
        shutil.copy2(extension_path, dest_path)
        print(f"✓ Extension copied to test profile: {extension_name}")

        # Run Firefox temporarily to initialize extensions.json
        if not self._initialize_extensions_json():
            return False

        # Enable the extension in extensions.json
        if not self._enable_extension_in_profile():
            return False

        # Configure extension storage with test settings
        if not self._configure_extension_storage():
            return False

        print(f"✓ Extension installed and enabled in test profile")
        return True

    def _initialize_extensions_json(self):
        """Run Firefox temporarily to create extensions.json"""
        firefox_path = os.path.expanduser(self.firefox_path)

        # Start Firefox temporarily with timeout
        firefox_cmd = [
            firefox_path,
            '-profile', self.profile_dir,
            '-no-remote',
            '-headless'
        ]

        print("⏳ Running Firefox temporarily to initialize extensions.json...")

        try:
            # Start Firefox process with timeout
            proc = subprocess.Popen(
                firefox_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            # Wait for extensions.json to be created (up to 20 seconds)
            extensions_json_path = os.path.join(self.profile_dir, 'extensions.json')
            timeout = 20
            waited = 0

            while not os.path.exists(extensions_json_path) and waited < timeout:
                time.sleep(1)
                waited += 1

            # Give it one more second after creation
            if os.path.exists(extensions_json_path):
                time.sleep(1)
                print("✓ extensions.json created")
            else:
                print(f"✗ extensions.json not created after {timeout} seconds")
                proc.terminate()
                proc.wait(timeout=5)
                return False

            # Kill the Firefox process
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()

            print("✓ Firefox initialization process stopped")
            return True

        except Exception as e:
            print(f"✗ Failed to initialize extensions.json: {e}")
            return False

    def _enable_extension_in_profile(self):
        """Enable the extension by modifying extensions.json"""
        extensions_json_path = os.path.join(self.profile_dir, 'extensions.json')

        if not os.path.exists(extensions_json_path):
            print("✗ extensions.json not found")
            return False

        try:
            # Check if jq is available
            result = subprocess.run(['which', 'jq'], capture_output=True, text=True)
            if result.returncode != 0:
                print("✗ jq command not found - required for enabling extension")
                return False

            # Use jq to enable the extension
            jq_command = [
                'jq',
                '.addons[] |= if .id == "foxmcp@codemud.org" then .userDisabled = false | .active = true else . end',
                extensions_json_path
            ]

            # Run jq and capture output
            result = subprocess.run(jq_command, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"✗ Failed to modify extensions.json with jq: {result.stderr}")
                return False

            # Write the modified JSON back to the file
            with open(extensions_json_path, 'w') as f:
                f.write(result.stdout)

            print("✓ Extension enabled in extensions.json")
            return True

        except Exception as e:
            print(f"✗ Failed to enable extension: {e}")
            return False

    def _configure_extension_storage(self):
        """Configure extension storage by updating the SQLite database directly"""
        try:
            # Path to the Firefox storage database
            storage_db_path = os.path.join(self.profile_dir, 'storage-sync-v2.sqlite')

            # Wait a moment and start Firefox briefly to ensure the storage database is created
            if not os.path.exists(storage_db_path):
                print("⏳ Starting Firefox briefly to create storage database...")
                firefox_path = os.path.expanduser(self.firefox_path)
                firefox_cmd = [
                    firefox_path,
                    '-profile', self.profile_dir,
                    '-no-remote',
                    '-headless'
                ]

                proc = subprocess.Popen(
                    firefox_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

                # Wait for storage to be created
                timeout = 15
                waited = 0
                while not os.path.exists(storage_db_path) and waited < timeout:
                    time.sleep(1)
                    waited += 1

                # Kill Firefox
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

                if not os.path.exists(storage_db_path):
                    print(f"✗ Storage database not created after {timeout} seconds")
                    return False

                print("✓ Storage database created")

            # Create the test configuration data
            test_config = {
                'hostname': 'localhost',
                'port': self.test_port,  # Use dynamic test port
                'retryInterval': 1000,
                'maxRetries': 5,
                'pingTimeout': 2000,
                # Test configuration overrides (extension will use these)
                'testPort': self.test_port,
                'testHostname': 'localhost'
            }

            config_json = json.dumps(test_config)

            # Update the SQLite database
            conn = sqlite3.connect(storage_db_path)
            try:
                cursor = conn.cursor()

                # Check if the extension entry exists
                cursor.execute(
                    "SELECT COUNT(*) FROM storage_sync_data WHERE ext_id = ?",
                    ("foxmcp@codemud.org",)
                )
                exists = cursor.fetchone()[0] > 0

                if exists:
                    # Update existing entry
                    cursor.execute(
                        "UPDATE storage_sync_data SET data = ?, sync_change_counter = sync_change_counter + 1 WHERE ext_id = ?",
                        (config_json, "foxmcp@codemud.org")
                    )
                    print("✓ Updated existing extension storage entry")
                else:
                    # Insert new entry
                    cursor.execute(
                        "INSERT INTO storage_sync_data (ext_id, data, sync_change_counter) VALUES (?, ?, 1)",
                        ("foxmcp@codemud.org", config_json)
                    )
                    print("✓ Created new extension storage entry")

                conn.commit()
                print(f"✓ Extension storage configured with test port {self.test_port}")
                return True

            finally:
                conn.close()

        except Exception as e:
            print(f"✗ Failed to configure extension storage: {e}")
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
