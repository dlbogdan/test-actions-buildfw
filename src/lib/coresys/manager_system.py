import time
from .manager_logger import Logger
from .manager_config import ConfigManager
from .manager_wifi import WiFiManager
from .manager_tasks import TaskManager, TaskEvent
import uasyncio as asyncio

from .manager_firmware import FirmwareUpdater


class NetworkManager:
    """Wrapper for network connectivity with simplified interface."""
    
    def __init__(self, system_manager):
        self._system = system_manager
        self._log = system_manager.log
        self._task_manager = system_manager.task_manager
        self._wifi_task_id = "wifi_update_task"
        self._is_up_called = False
        
    def up(self):
        """Bring network connection up."""
        wifi = self._system.ensure_service('wifi')
        if not wifi:
            self._log.warning("NetworkManager: Cannot connect - WiFi configuration missing")
            return False
            
        # Only start the task if not already running
        if not self._task_manager.get_task_info(self._wifi_task_id):
            # Start WiFi update task
            self._task_manager.ensure_periodic_task(
                self._wifi_task_id,
                wifi.update,
                interval_ms=500,
                description="WiFi Update Loop",
                is_coroutine=False
            )
            self._log.info("NetworkManager: WiFi update task running")
        
        self._is_up_called = True
        return True
        
    def down(self):
        """Bring network connection down."""
        wifi = self._system.get_service('wifi')  # Only get, don't initialize
        if not wifi:
            return False
            
        # Stop WiFi update task
        self._task_manager.stop_task(self._wifi_task_id)
        self._is_up_called = False
        
        # Disconnect WiFi interface
        if wifi.is_connected():
            wifi.disconnect()
            self._log.info("NetworkManager: WiFi disconnected")
        return True
        
    async def wait_until_up(self, timeout_ms=60000):
        """Wait for network to come up with timeout."""
        wifi = self._system.ensure_service('wifi')
        if not wifi:
            self._log.warning("NetworkManager: Cannot wait - WiFi configuration missing")
            return False
            
        self._log.info(f"NetworkManager: Waiting for network connection (timeout: {timeout_ms}ms)")
        
        # Ensure WiFi task is running
        if not self._is_up_called:
            self.up()
        
        # Wait for connection with timeout
        start_time = time.ticks_ms()
        while not wifi.is_connected():
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                self._log.warning("NetworkManager: Connection timed out")
                return False
            await asyncio.sleep_ms(250)
        
        self._log.info(f"NetworkManager: Connected, IP: {wifi.get_ip()}")
        return True
        
    def is_up(self):
        """Check if network is connected."""
        wifi = self._system.get_service('wifi')  # Only get, don't initialize
        return wifi and wifi.is_connected()
        
    def get_ip(self):
        """Get current IP address if connected."""
        wifi = self._system.get_service('wifi')  # Only get, don't initialize
        if wifi and wifi.is_connected():
            return wifi.get_ip()
        return None
        
    @property
    def wifi(self):
        """Direct access to WiFi manager if needed."""
        return self._system.ensure_service('wifi')

class FirmwareManager:
    """Wrapper for firmware update capabilities with explicit initialization."""
    
    def __init__(self, system_manager):
        self._system = system_manager
        self._log = system_manager.log
        self._updater = None
        
    def init(self):
        """Initialize the firmware updater."""
        if self._updater:
            return True  # Already initialized
            
        try:
            config = self._system.config
            device_model = config.get("SYS.DEVICE", "MODEL", "generic")
            core_system_files = config.get("SYS.FIRMWARE", "CORE_SYSTEM_FILES", []) # Get core files
            
            # Check if using direct base URL mode
            direct_base_url = config.get("SYS.FIRMWARE", "DIRECT_BASE_URL", None)
            
            if direct_base_url:
                # Initialize with direct base URL
                self._updater = FirmwareUpdater(
                    device_model=device_model, 
                    direct_base_url=direct_base_url,
                    core_system_files=core_system_files # Pass core files
                )
                self._log.info(f"FirmwareManager: Updater initialized with direct base URL: {direct_base_url}")
                return True
            else:
                # Try GitHub mode
                github_repo = config.get("SYS.FIRMWARE", "GITHUB_REPO")
                github_token = config.get("SYS.FIRMWARE", "GITHUB_TOKEN", "")
                    
                if github_repo:
                    self._updater = FirmwareUpdater(
                        device_model=device_model, 
                        github_repo=github_repo, 
                        github_token=github_token,
                        core_system_files=core_system_files # Pass core files
                    )
                    self._log.info(f"FirmwareManager: Updater initialized with GitHub repo: {github_repo}")
                    return True
                else:
                    self._log.info("FirmwareManager: Not initialized (no configuration for update source)")
        except ValueError as e:
            self._log.info(f"FirmwareManager: Not initialized (config error): {e}")
        
        return False
        
    def is_available(self):
        """Check if firmware updater is available and initialized."""
        return self._updater is not None
        
    async def check_update(self):
        """Check for firmware updates if the updater is available."""
        if not self._updater:
            if not self.init():
                return False, "0.0.0", None
                
        if isinstance(self._updater, FirmwareUpdater):
            return await self._updater.check_update()
        return False, "0.0.0", None
        
    async def download_update(self, release):
        """Download firmware update if the updater is available."""
        if not self._updater:
            if not self.init():
                return False
                
        if isinstance(self._updater, FirmwareUpdater):
            return await self._updater.download_update(release)
        return False
        
    async def apply_update(self):
        """Apply downloaded firmware update if the updater is available."""
        if not self._updater:
            if not self.init():
                return False
                
        if isinstance(self._updater, FirmwareUpdater):
            return await self._updater.apply_update()
        return False
        
    async def restore_from_backup(self):
        """Restore system from backup after failed update."""
        if not self._updater:
            if not self.init():
                self._log.error("FirmwareManager: Cannot restore from backup - updater not initialized")
                return False
                
        if isinstance(self._updater, FirmwareUpdater):
            return await self._updater.restore_from_backup()
            
        self._log.error("FirmwareManager: Cannot restore from backup - unexpected updater type")
        return False
        
    @property
    def error(self):
        """Get the last error from the firmware updater."""
        if self._updater and isinstance(self._updater, FirmwareUpdater):
            return self._updater.error
        return "Firmware updater not initialized"

class SystemManager:
    """Master system manager that coordinates all subsystems (Singleton)."""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, config_file="config.json", debug_level=0):
        # We only want to initialize instance variables once
        if not hasattr(self, '_instance_vars_initialized'):
            self._instance_vars_initialized = True
            self.config_file = config_file
            
            # Initialize components with defaults to avoid None issues
            self._log = Logger(debug_level)  # Initialize with default debug level
            self._config = ConfigManager(self.config_file)  # Initialize config right away to avoid None issues
            
            # Services registry
            self._services = {
                'log': self._log,
                'config': self._config
            }
            
            # Initialize task manager
            self._task_manager = TaskManager()
            self._task_manager.add_listener(self._on_task_event)
            self._services['task_manager'] = self._task_manager
            
            # Network manager (always initialized)
            self._network_manager = NetworkManager(self)
            
            # Firmware manager (always initialized)
            self._firmware_manager = FirmwareManager(self)
            
            # Task IDs for managed components
            self._wifi_task_id = "wifi_update_task"
            
            # Device information
            self._device_name = "Unnamed Device"
        
        # The full initialization is deferred to init()
        self._initialized = False
        
    def _on_task_event(self, event):
        """Handle task lifecycle events."""
        if event.event_type == TaskEvent.TASK_FAILED:
            self._log.error(f"SystemManager: Task {event.task_id} failed with error: {event.error}")
        elif event.event_type == TaskEvent.TASK_COMPLETED:
            self._log.debug(f"SystemManager: Task {event.task_id} completed")
        elif event.event_type == TaskEvent.TASK_STARTED:
            self._log.debug(f"SystemManager: Task {event.task_id} started")
        elif event.event_type == TaskEvent.TASK_STOPPED:
            self._log.debug(f"SystemManager: Task {event.task_id} stopped")
        
    def register_service(self, name, service_instance):
        """Register a service with the system manager."""
        self._services[name] = service_instance
        self._log.info(f"SystemManager: Registered service '{name}'")
        return service_instance
        
    def get_service(self, name):
        """Get a service by name. Returns None if not initialized."""
        return self._services.get(name)
        
    def ensure_service(self, name):
        """Ensure a service is initialized and return it."""
        # Return if already exists
        service = self.get_service(name)
        if service:
            return service
            
        # Initialize built-in services
        if name == 'wifi':
            service = self._initialize_wifi()
        
        return service
        
    def _initialize_wifi(self):
        """Initialize WiFi service on demand."""
        try:
            ssid = self._config.get("SYS.WIFI", "SSID")
            password = self._config.get("SYS.WIFI", "PASS")
            hostname = self._config.get("SYS.DEVICE", "NAME", "micropython-device")
            
            if ssid and password:
                self._services['wifi'] = WiFiManager(ssid, password, hostname)
                self._log.info("SystemManager: WiFi manager initialized")
                return self._services['wifi']
            else:
                self._log.info("SystemManager: WiFi not initialized (no credentials)")
        except ValueError as e:
            self._log.info(f"SystemManager: WiFi not initialized (no credentials): {e}")
        return None
            
    def init(self):
        """Initialize system components. With the new design, this is lighter weight."""
        # Prevent re-initialization of components
        if self._initialized:
            self._log.info("SystemManager: Already initialized, skipping")
            return self
            
        # Get device name and log it
        self._device_name = self._config.get("SYS.DEVICE", "NAME", "Unnamed Device")
        self._log.info(f"SystemManager: Device name: {self._device_name}")
        
        self._log.info(f"SystemManager: Initialization complete. Available services: {', '.join(self._services.keys())}")
        self._initialized = True
        return self
        
    # def connect_network(self):
    #     """Legacy method - use network.up() instead."""
    #     if not self._initialized:
    #         self.init()
    #     return self._network_manager.up()
    
    # def disconnect_network(self):
    #     """Legacy method - use network.down() instead."""
    #     return self._network_manager.down()
    
    # async def wait_for_network(self, timeout_ms=60000):
    #     """Legacy method - use await network.wait_until_up() instead."""
    #     if not self._initialized:
    #         self.init()
    #     return await self._network_manager.wait_until_up(timeout_ms)
    
    # def update(self):
    #     """Update legacy components that don't use the task manager."""
    #     # This is kept for backward compatibility - most components now use the task manager
    #     pass
    
    # Task management methods
    def create_task(self, coro, task_id=None, description=""):
        """Create a new task from a coroutine."""
        return self._task_manager.create_task(coro, task_id, description)
    
    def create_periodic_task(self, update_func, interval_ms=500, task_id=None, description="", is_coroutine=None):
        """Create a periodic task that runs a function at intervals."""
        return self._task_manager.create_periodic_task(update_func, interval_ms, task_id, description, is_coroutine)
    
    def ensure_task_running(self, task_id, update_func, interval_ms=500, description="", is_coroutine=None):
        """Ensure a task is running - create it if needed or restart if stopped."""
        return self._task_manager.ensure_periodic_task(task_id, update_func, interval_ms, description, is_coroutine)
    
    def stop_task(self, task_id):
        """Stop a task by ID."""
        return self._task_manager.stop_task(task_id)
    
    def restart_task(self, task_id):
        """Restart a stopped periodic task."""
        return self._task_manager.restart_task(task_id)
    
    def cancel_all_tasks(self):
        """Cancel all running tasks."""
        self._task_manager.cancel_all_tasks()
    
    def get_task_info(self, task_id):
        """Get information about a task."""
        return self._task_manager.get_task_info(task_id)
    
    def get_all_tasks(self):
        """Get a list of all task IDs."""
        return self._task_manager.get_all_tasks()
    
    # Updated firmware update methods to use the firmware manager
    # async def check_firmware_update(self):
    #     """Check for firmware updates (legacy method)."""
    #     # Ensure initialization is complete
    #     if not self._initialized:
    #         self.init()
    #     return await self._firmware_manager.check_update()
        
    # async def download_firmware_update(self, release):
    #     """Download firmware update (legacy method)."""
    #     # Ensure initialization is complete
    #     if not self._initialized:
    #         self.init()
    #     return await self._firmware_manager.download_update(release)
        
    # async def apply_firmware_update(self):
    #     """Apply downloaded firmware update (legacy method)."""
    #     # Ensure initialization is complete
    #     if not self._initialized:
    #         self.init()
    #     return await self._firmware_manager.apply_update()
    
    # Properties to access component instances
    @property
    def log(self):
        """Access the logger instance."""
        return self._log
        
    @property
    def config(self):
        """Access the config manager instance."""
        return self._config
        
    @property
    def network(self):
        """Access the network manager."""
        return self._network_manager
        
    @property
    def firmware(self):
        """Access the firmware manager."""
        return self._firmware_manager
        
    @property
    def device_name(self):
        """Access the device name."""
        if not self._initialized:
            self.init()
        return self._device_name
        
    @property
    def task_manager(self):
        """Access the task manager instance."""
        return self._task_manager 