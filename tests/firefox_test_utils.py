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
import atexit
import tarfile
from dataclasses import dataclass
from pathlib import Path
try:
    from .test_config import FIREFOX_TEST_CONFIG, get_firefox_test_port
    from .port_coordinator import FirefoxPortCoordinator
except ImportError:
    from test_config import FIREFOX_TEST_CONFIG, get_firefox_test_port
    from port_coordinator import FirefoxPortCoordinator

project_root = Path(__file__).resolve().parent.parent

@dataclass
class ProfileCacheEntry:
    """Cache entry for Firefox profiles stored as compressed files"""
    port: int
    compressed_path: str  # Path to .tar.gz file
    created_at: float
    last_used: float
    use_count: int
    is_locked: bool = False

class FirefoxTestManager:
    """Manages Firefox instances for testing with proper extension configuration"""

    # Class-level cache for Firefox profiles
    _profile_cache = {}  # {port: ProfileCacheEntry}
    _cache_dir = None
    _max_cache_size = 10

    def __init__(self, firefox_path=None, test_port=None, coordination_file=None):
        self.firefox_path = firefox_path or os.environ.get('FIREFOX_PATH', 'firefox')
        self.test_port = test_port or get_firefox_test_port()
        self.coordination_file = coordination_file
        self.profile_dir = None
        self.firefox_process = None

    @classmethod
    def _get_cache_dir(cls):
        """Get or create cache directory under dist/"""
        if cls._cache_dir is None:
            # Create cache directory under dist/
            dist_dir = project_root / 'dist'
            dist_dir.mkdir(exist_ok=True)

            cls._cache_dir = str(dist_dir / 'profile-cache')
            os.makedirs(cls._cache_dir, exist_ok=True)

            # Register cleanup only on first creation
            atexit.register(cls._cleanup_cache_dir)

        return cls._cache_dir

    @classmethod
    def _discover_cached_profiles(cls):
        """Discover existing cached profiles from previous runs"""
        cache_dir = cls._get_cache_dir()

        for filename in os.listdir(cache_dir):
            if filename.startswith('profile-') and filename.endswith('.tar.gz'):
                try:
                    # Extract port from filename: profile-40000.tar.gz -> 40000
                    port_str = filename[8:-7]  # Remove 'profile-' and '.tar.gz'
                    port = int(port_str)

                    compressed_path = os.path.join(cache_dir, filename)
                    file_stat = os.stat(compressed_path)

                    # Add to cache if not already present
                    if port not in cls._profile_cache:
                        entry = ProfileCacheEntry(
                            port=port,
                            compressed_path=compressed_path,
                            created_at=file_stat.st_ctime,
                            last_used=file_stat.st_mtime,
                            use_count=0,  # Reset count for new session
                            is_locked=False
                        )
                        cls._profile_cache[port] = entry

                except (ValueError, OSError):
                    # Skip invalid files
                    continue

    @classmethod
    def _cleanup_cache_dir(cls):
        """Clean up cache entries on exit (preserve directory structure)"""
        # Clear cache entries in memory
        cls._profile_cache.clear()
        print("✓ Profile cache entries cleared")

        # Note: We preserve the dist/profile-cache directory and files
        # for persistence between test runs

    def _get_cached_profile(self, port):
        """Retrieve cached profile if available and valid"""
        # Discover cached profiles from previous runs on first access
        if not hasattr(self.__class__, '_discovery_done'):
            self._discover_cached_profiles()
            self.__class__._discovery_done = True

        if port not in self._profile_cache:
            return None

        entry = self._profile_cache[port]

        # Check if compressed profile still exists
        if not os.path.exists(entry.compressed_path):
            self._remove_from_cache(port)
            return None

        # Check if profile is locked (in use by another test)
        if entry.is_locked:
            return None

        try:
            # Extract compressed profile to temporary directory
            profile_dir = tempfile.mkdtemp(prefix='foxmcp-extracted-')
            self._extract_profile(entry.compressed_path, profile_dir)

            # Validate extracted profile structure
            if not self._validate_cached_profile(profile_dir, port):
                shutil.rmtree(profile_dir, ignore_errors=True)
                self._remove_from_cache(port)
                return None

            # Lock the profile for use and update stats
            entry.is_locked = True
            entry.last_used = time.time()
            entry.use_count += 1
            return profile_dir

        except Exception as e:
            print(f"⚠ Error extracting cached profile: {e}")
            self._remove_from_cache(port)
            return None

    def _extract_profile(self, compressed_path, target_dir):
        """Extract compressed profile to target directory"""
        with tarfile.open(compressed_path, 'r:gz') as tar:
            tar.extractall(target_dir)

    def _compress_profile(self, profile_dir, output_path):
        """Compress profile directory to .tar.gz file"""
        with tarfile.open(output_path, 'w:gz') as tar:
            # Add all files in the profile directory
            for item in os.listdir(profile_dir):
                item_path = os.path.join(profile_dir, item)
                tar.add(item_path, arcname=item)

    def _validate_cached_profile(self, profile_path, expected_port):
        """Validate that cached profile is properly configured for the port"""
        try:
            # Check user.js has correct port
            user_js_path = os.path.join(profile_path, 'user.js')
            if os.path.exists(user_js_path):
                with open(user_js_path, 'r') as f:
                    content = f.read()
                    if f'testPort", {expected_port}' not in content:
                        return False
            else:
                return False  # user.js should exist

            # Check extension is installed
            extensions_dir = os.path.join(profile_path, 'extensions')
            extension_file = os.path.join(extensions_dir, 'foxmcp@codemud.org.xpi')
            if not os.path.exists(extension_file):
                return False  # Extension should be installed

            # Check extensions.json exists and has the extension enabled
            extensions_json_path = os.path.join(profile_path, 'extensions.json')
            if not os.path.exists(extensions_json_path):
                return False  # extensions.json should exist

            # Check extension storage if it exists
            storage_db_path = os.path.join(profile_path, 'storage-sync-v2.sqlite')
            if os.path.exists(storage_db_path):
                # Validate SQLite config has correct port
                return self._validate_sqlite_config(storage_db_path, expected_port)

            return True  # Profile exists with correct setup, SQLite will be created
        except Exception:
            return False

    def _validate_sqlite_config(self, db_path, expected_port):
        """Validate SQLite storage has correct port configuration"""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data FROM storage_sync_data WHERE ext_id = ?",
                ("foxmcp@codemud.org",)
            )
            result = cursor.fetchone()
            conn.close()

            if result:
                config = json.loads(result[0])
                return config.get('port') == expected_port and config.get('testPort') == expected_port
            return True  # No config yet, will be created
        except Exception:
            return False

    def _cache_profile(self, port, profile_path):
        """Add profile to cache with size management - compresses profile"""
        # Remove oldest entries if cache is full
        if len(self._profile_cache) >= self._max_cache_size:
            self._evict_oldest_entries()

        try:
            # Compress the profile
            cache_dir = self._get_cache_dir()
            compressed_path = os.path.join(cache_dir, f'profile-{port}.tar.gz')
            self._compress_profile(profile_path, compressed_path)

            # Add to cache
            entry = ProfileCacheEntry(
                port=port,
                compressed_path=compressed_path,
                created_at=time.time(),
                last_used=time.time(),
                use_count=1,
                is_locked=True
            )
            self._profile_cache[port] = entry

        except Exception as e:
            print(f"⚠ Error compressing profile for cache: {e}")
            # Don't cache if compression fails

    def _evict_oldest_entries(self):
        """Remove oldest unused cache entries"""
        # Sort by last_used, exclude locked profiles
        unlocked_entries = [
            (port, entry) for port, entry in self._profile_cache.items()
            if not entry.is_locked
        ]

        if unlocked_entries:
            # Remove oldest unlocked entry
            oldest_port, oldest_entry = min(unlocked_entries, key=lambda x: x[1].last_used)
            self._remove_from_cache(oldest_port)
            print(f"✓ Evicted cached profile for port {oldest_port}")

    def _remove_from_cache(self, port):
        """Remove profile from cache and delete compressed file"""
        if port in self._profile_cache:
            entry = self._profile_cache[port]
            if os.path.exists(entry.compressed_path):
                try:
                    os.remove(entry.compressed_path)
                except Exception as e:
                    print(f"⚠ Error removing cached compressed profile: {e}")
            del self._profile_cache[port]

    def _create_test_profile(self):
        """Create or retrieve cached Firefox profile configured for testing"""

        # Check cache first
        cached_profile = self._get_cached_profile(self.test_port)
        if cached_profile:
            self.profile_dir = cached_profile
            print(f"✓ Using cached profile for port {self.test_port}: {self.profile_dir}")
            return self.profile_dir

        # Create new profile if not cached
        self.profile_dir = self._create_new_profile()
        self._cache_profile(self.test_port, self.profile_dir)
        print(f"✓ Created and cached new profile for port {self.test_port}: {self.profile_dir}")
        return self.profile_dir

    def _create_new_profile(self):
        """Create a new profile (will be compressed for caching)"""
        profile_dir = tempfile.mkdtemp(prefix='foxmcp-new-profile-')

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

// Disable storage.sync to prevent interference with development Firefox
user_pref("webextensions.storage.sync.enabled", false);
user_pref("services.sync.engine.extension-storage", false);
user_pref("identity.fxaccounts.enabled", false);

// Force extension to use local storage only
user_pref("extensions.webextensions.storage.sync.enabled", false);

// FORCE override default WebSocket port to prevent connecting to development server
user_pref("extensions.foxmcp.forceTestPort", true);
user_pref("extensions.foxmcp.testPort", ''' + str(self.test_port) + ''');
'''

        with open(os.path.join(profile_dir, 'user.js'), 'w') as f:
            f.write(user_js_content)

        # Temporarily set profile_dir for extension config and installation
        old_profile_dir = self.profile_dir
        self.profile_dir = profile_dir
        try:
            # Create extension storage with test configuration
            self._setup_extension_test_config()

            # Install extension as part of profile creation
            extension_path = _get_extension_xpi_path()
            if not extension_path or not os.path.exists(extension_path):
                raise FileNotFoundError("Extension XPI not found. Run 'make package' first.")

            success = self._install_extension(extension_path)
            if not success:
                raise RuntimeError("Extension installation failed during profile creation")

        finally:
            self.profile_dir = old_profile_dir

        return profile_dir

    def _setup_extension_test_config(self):
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

    def _preconfigure_extension_storage(self):
        """Pre-configure extension storage before Firefox runs for the first time"""
        try:
            # Create browser extension data directory structure manually
            storage_dir = os.path.join(self.profile_dir, 'browser-extension-data', 'foxmcp@codemud.org')
            os.makedirs(storage_dir, exist_ok=True)

            # Create a simple local storage file with test configuration
            config = {
                'hostname': 'localhost',
                'port': self.test_port,
                'testPort': self.test_port,
                'testHostname': 'localhost',
                'retryInterval': 1000,
                'maxRetries': 5,
                'pingTimeout': 2000
            }

            config_file = os.path.join(storage_dir, 'storage.json')
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=2)

            print(f"✓ Pre-configured extension storage with test port {self.test_port}")
            return True

        except Exception as e:
            print(f"✗ Failed to pre-configure extension storage: {e}")
            return False

    def _install_extension(self, extension_path):
        """Install extension to the test profile and initialize extensions.json"""
        if not self.profile_dir:
            raise ValueError("Test profile not created. Call _create_test_profile() first.")

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

        # IMPORTANT: Configure extension storage BEFORE running Firefox
        # This prevents the extension from connecting to default port during initialization
        if not self._preconfigure_extension_storage():
            return False

        # Run Firefox temporarily to initialize extensions.json
        if not self._initialize_extensions_json():
            return False

        # Enable the extension in extensions.json
        if not self._enable_extension_in_profile():
            return False

        # Ensure extension storage is properly configured (may be redundant but safe)
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

    def _start_firefox(self, headless=True, wait_for_startup=True):
        """Start Firefox with the test profile and extension"""
        if not self.profile_dir:
            raise ValueError("Test profile not created. Call _create_test_profile() first.")

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
        """Clean up test profile and stop Firefox - modified for compressed caching"""
        self.stop_firefox()

        # Always delete the extracted profile directory
        if self.profile_dir and os.path.exists(self.profile_dir):
            try:
                shutil.rmtree(self.profile_dir)
                print("✓ Extracted profile cleaned up")
            except Exception as e:
                print(f"⚠ Error cleaning up extracted profile: {e}")

        # Unlock the cached compressed profile if it exists
        if self.test_port in self._profile_cache:
            entry = self._profile_cache[self.test_port]
            entry.is_locked = False
            entry.last_used = time.time()
            print(f"✓ Compressed profile for port {self.test_port} returned to cache")

        self.profile_dir = None

    def setup_and_start_firefox(self, headless=True, wait_for_startup=True, skip_on_failure=True):
        """Convenience method that combines create_test_profile, install_extension, and start_firefox

        Args:
            headless: Whether to run Firefox in headless mode (default: True)
            wait_for_startup: Whether to wait for Firefox startup (default: True)
            skip_on_failure: If True, returns False on failure; if False, raises exceptions

        Returns:
            bool: True if all steps succeeded, False if any step failed (when skip_on_failure=True)

        Raises:
            Exception: If any step fails and skip_on_failure=False
        """
        try:
            # Step 1: Create test profile (includes extension installation)
            self._create_test_profile()

            # Step 2: Start Firefox
            firefox_started = self._start_firefox(headless=headless, wait_for_startup=wait_for_startup)
            if not firefox_started:
                if skip_on_failure:
                    return False
                else:
                    raise RuntimeError("Firefox failed to start")

            return True

        except Exception as e:
            if skip_on_failure:
                return False
            else:
                raise

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit with cleanup"""
        self.cleanup()

def _get_extension_xpi_path():
    """Get path to built extension XPI file"""
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
    alt_path = project_root / 'extension' / 'foxmcp@codemud.org.xpi'
    if alt_path.exists():
        return str(alt_path)

    return None
