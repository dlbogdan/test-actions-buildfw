import time
from lib.manager_logger import Logger
from lib.manager_config import ConfigManager
from lib.manager_wifi import WiFiManager
import uasyncio as asyncio

# Import the firmware updater if available
try:
    from check_fw_update import FirmwareUpdater
    _has_firmware_updater = True
except ImportError:
    _has_firmware_updater = False

class SystemManager:
    """Master system manager that coordinates all subsystems (Singleton)."""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_file="config.json", debug_level=0):
        if self._initialized:
            return  # Prevent re-initialization
        
        self._initialized = True
        self.config_file = config_file
        
        # Initialize components with defaults to avoid None issues
        self._log = Logger(debug_level)  # Initialize with default debug level
        self._config = None
        self._wifi = None
        self._firmware = None
        
        # Task management
        self._wifi_task = None
        self._is_running = False
        
        # Properties to expose components
        self._initialized_components = ['log']  # Logger already initialized

    def init(self):
        """Initialize all system components in the correct order."""
        # we cannot set debug_level here because the logger is a singleton
            
        self._log.info("SystemManager: Logger initialized")
        
        # 2. Initialize config manager
        self._config = ConfigManager(self.config_file)
        self._initialized_components.append('config')
        self._log.info("SystemManager: Config manager initialized")
        
        # 3. Initialize WiFi if credentials are available
        try:
            ssid = self._config.get("WIFI", "SSID")
            password = self._config.get("WIFI", "PASS")
            hostname = self._config.get("DEVICE", "HOSTNAME", "micropython-device")
            
            if ssid and password:
                self._wifi = WiFiManager(ssid, password, hostname)
                self._initialized_components.append('wifi')
                self._log.info("SystemManager: WiFi manager initialized")
                
                # Start WiFi background task
                self._start_wifi_task()
            else:
                self._log.info("SystemManager: WiFi not initialized (no credentials)")
        except ValueError as e:
            # Config key not found and no default provided
            self._log.info("SystemManager: WiFi not initialized (no credentials)")
        
        # 4. Initialize firmware updater if available
        if _has_firmware_updater:
            try:
                device_model = self._config.get("DEVICE", "MODEL", "generic")
                base_url = self._config.get("FIRMWARE", "BASE_URL")
                github_token = self._config.get("FIRMWARE", "GITHUB_TOKEN", "")
                
                if base_url:
                    self._firmware = FirmwareUpdater(device_model, base_url, github_token)
                    self._initialized_components.append('firmware')
                    self._log.info("SystemManager: Firmware updater initialized")
                else:
                    self._log.info("SystemManager: Firmware updater not initialized (no base URL)")
            except ValueError as e:
                self._log.info("SystemManager: Firmware updater not initialized (config error)")
        else:
            self._log.info("SystemManager: Firmware updater not available")
            
        self._log.info(f"SystemManager: Initialization complete. Components: {', '.join(self._initialized_components)}")
        return self
    
    def _start_wifi_task(self):
        """Start the WiFi update task."""
        if self._wifi and not self._wifi_task:
            self._is_running = True
            self._wifi_task = asyncio.create_task(self._wifi_update_loop())
            self._log.info("SystemManager: WiFi update task started")
    
    def _stop_wifi_task(self):
        """Stop the WiFi update task."""
        if self._wifi_task:
            self._is_running = False
            # The task will exit on next iteration
            self._log.info("SystemManager: WiFi update task stopping")
    
    async def _wifi_update_loop(self):
        """Background task to periodically update WiFi status."""
        self._log.info("SystemManager: WiFi update loop started")
        try:
            while self._is_running:
                if self._wifi:
                    self._wifi.update()
                await asyncio.sleep(0.5)  # Update every 500ms
        except Exception as e:
            self._log.error(f"SystemManager: WiFi update loop error: {e}")
        finally:
            self._log.info("SystemManager: WiFi update loop ended")
            self._wifi_task = None
    
    def connect_wifi(self):
        """Initiate WiFi connection if configured."""
        if 'wifi' not in self._initialized_components or not self._wifi:
            self._log.warning("SystemManager: Cannot connect WiFi - not initialized")
            return False
        
        # WiFi manager will handle connection in its update method
        self._start_wifi_task()  # Ensure task is running
        return True
    
    def disconnect_wifi(self):
        """Disconnect WiFi if connected."""
        if 'wifi' not in self._initialized_components or not self._wifi:
            return False
        
        self._stop_wifi_task()  # Stop updates
        
        if self._wifi.is_connected():
            self._wifi.disconnect()
            self._log.info("SystemManager: WiFi disconnected")
        
        return True
    
    async def wait_for_wifi(self, timeout_ms=60000):
        """Wait for WiFi to connect, with timeout."""
        if 'wifi' not in self._initialized_components or not self._wifi:
            self._log.warning("SystemManager: Cannot wait for WiFi - not initialized")
            return False
        
        self._log.info(f"SystemManager: Waiting for WiFi connection (timeout: {timeout_ms}ms)")
        
        # Ensure WiFi task is running
        self.connect_wifi()
        
        # Wait for connection with timeout
        start_time = time.ticks_ms()
        while not self._wifi.is_connected():
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                self._log.warning("SystemManager: WiFi connection timed out")
                return False
            await asyncio.sleep_ms(250)
        
        self._log.info(f"SystemManager: WiFi connected, IP: {self._wifi.get_ip()}")
        return True
    
    def update(self):
        """Update non-automated components."""
        # WiFi is now handled by background task
        pass
            
    async def check_firmware_update(self):
        """Check for firmware updates if the updater is available."""
        if 'firmware' in self._initialized_components and self._firmware:
            return await self._firmware.check_update()
        return False, "0.0.0", None
        
    async def download_firmware_update(self, release):
        """Download firmware update if the updater is available."""
        if 'firmware' in self._initialized_components and self._firmware:
            return await self._firmware.download_update(release)
        return False
        
    async def apply_firmware_update(self):
        """Apply downloaded firmware update if the updater is available."""
        if 'firmware' in self._initialized_components and self._firmware:
            return await self._firmware.apply_update()
        return False
    
    # Properties to access component instances
    @property
    def log(self):
        """Access the logger instance."""
        return self._log
        
    @property
    def config(self):
        """Access the config manager instance."""
        return self._config or ConfigManager(self.config_file)
        
    @property
    def wifi(self):
        """Access the WiFi manager instance."""
        return self._wifi
        
    @property
    def firmware(self):
        """Access the firmware updater instance."""
        return self._firmware 