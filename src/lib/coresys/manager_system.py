import time
from .manager_logger import Logger
from .manager_config import ConfigManager
from .manager_wifi import WiFiManager
from .manager_tasks import TaskManager, TaskEvent
import uasyncio as asyncio

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



class SystemManager:
    """Master system manager that coordinates all subsystems (Singleton)."""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, device_name="Unnamed Device", wifi_ssid=None, wifi_password=None, debug_level=0):
        # We only want to initialize instance variables once
        if not hasattr(self, '_instance_vars_initialized'):
            self._instance_vars_initialized = True
            
            # Initialize components with defaults to avoid None issues
            self._log = Logger(debug_level)  # Initialize with default debug level
            
            # Store injected configuration values
            self._device_name = device_name
            self._wifi_ssid = wifi_ssid
            self._wifi_password = wifi_password
            
            # Services registry  
            self._services = {}
            self._services['log'] = self._log
            
            # Initialize task manager
            self._task_manager = TaskManager()
            self._task_manager.add_listener(self._on_task_event)
            self._services['task_manager'] = self._task_manager
            
            # Network manager (always initialized)
            self._network_manager = NetworkManager(self)
            
            # Task IDs for managed components
            self._wifi_task_id = "wifi_update_task"
        
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
        if self._wifi_ssid and self._wifi_password:
            self._services['wifi'] = WiFiManager(self._wifi_ssid, self._wifi_password, self._device_name)
            self._log.info("SystemManager: WiFi manager initialized")
            return self._services['wifi']
        else:
            self._log.info("SystemManager: WiFi not initialized (no credentials)")
            return None
            
    def init(self):
        """Initialize system components. With the new design, this is lighter weight."""
        # Prevent re-initialization of components
        if self._initialized:
            self._log.info("SystemManager: Already initialized, skipping")
            return self
            
        # Log device name
        self._log.info(f"SystemManager: Device name: {self._device_name}")
        
        self._log.info(f"SystemManager: Initialization complete. Available services: {', '.join(self._services.keys())}")
        self._initialized = True
        return self
   
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
    
    # Properties to access component instances
    @property
    def log(self):
        """Access the logger instance."""
        return self._log
        
    @property
    def network(self):
        """Access the network manager."""
        return self._network_manager
        
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