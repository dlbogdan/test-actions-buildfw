import time
import lib.coresys.logger as logger
from manager_wifi import WiFiManager
from manager_tasks import TaskManager, TaskEvent
import uasyncio as asyncio

class NetworkManager:
    """Wrapper for network connectivity with a simplified interface."""
    
    # Connection states
    STATE_DISCONNECTED = 0  # Not connected
    STATE_CONNECTING = 1    # Connection in progress
    STATE_CONNECTED = 2     # Successfully connected
    STATE_FAILED = 3        # Connection failed

    def __init__(self, system_manager):
        # self._is_up_called = None
        self._system = system_manager
        self._task_manager = system_manager.task_manager
        self._wifi_task_id = "wifi_update_task"
        self._connection_state = self.STATE_DISCONNECTED
        self._max_retries = 3
        self._retry_count = 0
        self._last_error = None
        self._wifi_instance = None  # Store Wi-Fi instance to reduce lookups

    def up(self):
        """Bring network connection up."""
        # Get Wi-Fi instance using service factory to avoid circular dependencies
        if not self._wifi_instance:
            # Use a factory pattern instead of direct service access
            self._wifi_instance = self._system.get_or_create_service('wifi')

        if not self._wifi_instance:
            logger.warning("NetworkManager: Cannot connect - WiFi configuration missing")
            self._connection_state = self.STATE_FAILED
            self._last_error = "WiFi configuration missing"
            return False

        # Only start the task if not already running

        if not self._task_manager.get_task_info(self._wifi_task_id):
            # Start WiFi update task
            self._task_manager.ensure_periodic_task(
                self._wifi_task_id,
                self._wifi_instance.update,
                interval_ms=500,
                description="WiFi Update Loop",
                is_coroutine=False
            )

            logger.info("NetworkManager: WiFi update task running")

        self._connection_state = self.STATE_CONNECTING
        return True
        
    def down(self):
        """Bring network connection down."""
        wifi = self._system.get_service('wifi')  # Only get, don't initialize
        if not wifi:
            return False
            
        # Stop WiFi update task
        self._task_manager.stop_task(self._wifi_task_id)
        # self._is_up_called = False
        
        # Disconnect Wi-Fi interface
        if wifi.is_connected():
            wifi.disconnect()
            logger.info("NetworkManager: WiFi disconnected")
        return True
        
    async def wait_until_up(self, timeout_ms=60000):
        """Wait for the network to come up with timeout."""
        if not self._wifi_instance:
            # Use a cached instance or get it now
            self._wifi_instance = self._system.get_or_create_service('wifi')

        if not self._wifi_instance:
            logger.warning("NetworkManager: Cannot wait - WiFi configuration missing")
            self._connection_state = self.STATE_FAILED
            self._last_error = "WiFi configuration missing"
            return False

        logger.info(f"NetworkManager: Waiting for network connection (timeout: {timeout_ms}ms)")

        # Ensure WiFi task is running
        if self._connection_state == self.STATE_DISCONNECTED:
            self.up()

        # Reset retry counter and state
        self._retry_count = 0
        self._connection_state = self.STATE_CONNECTING

        # Wait for connection with timeout
        start_time = time.ticks_ms()
        while not self._wifi_instance.is_connected():
            if time.ticks_diff(time.ticks_ms(), start_time) > timeout_ms:
                logger.warning("NetworkManager: Connection timed out")
                self._connection_state = self.STATE_FAILED
                self._last_error = "Connection timeout"
                return False

            # Check if we should retry on failure
            if self._wifi_instance.has_connection_failed() and self._retry_count < self._max_retries:
                self._retry_count += 1
                logger.info(f"NetworkManager: Connection attempt failed, retrying ({self._retry_count}/{self._max_retries})")
                self._wifi_instance.reconnect()

            await asyncio.sleep_ms(250)

        # Connection successful
        self._connection_state = self.STATE_CONNECTED
        self._last_error = None
        logger.info(f"NetworkManager: Connected, IP: {self._wifi_instance.get_ip()}")
        return True
        
    def is_up(self):
        """Check if the network is connected."""
        # Use cached instance instead of repeated lookups
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_service('wifi')
        return self._wifi_instance and self._wifi_instance.is_connected()
        
    def get_ip(self):
        """Get the current IP address if connected."""
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_service('wifi')

        if self._wifi_instance and self._wifi_instance.is_connected():
            return self._wifi_instance.get_ip()
        return None

    def get_connection_status(self):
        """Get detailed connection status information."""
        status = {
            'state': self._connection_state,
            'state_name': {self.STATE_DISCONNECTED: 'disconnected', 
                          self.STATE_CONNECTING: 'connecting',
                          self.STATE_CONNECTED: 'connected', 
                          self.STATE_FAILED: 'failed'}[self._connection_state],
            'ip_address': self.get_ip(),
            'retries': self._retry_count,
            'last_error': self._last_error
        }

        # Add Wi-Fi specific info if available
        if self._wifi_instance:
            status.update({
                'signal_strength': getattr(self._wifi_instance, 'get_signal_strength', lambda: None)(),
                'ssid': getattr(self._wifi_instance, 'get_ssid', lambda: None)()
            })

        return status

    def cleanup(self):
        """Clean up network resources."""
        if self._task_manager.get_task_info(self._wifi_task_id):
            self._task_manager.stop_task(self._wifi_task_id)

        # Disconnect Wi-Fi if connected
        if self._wifi_instance and self._wifi_instance.is_connected():
            self._wifi_instance.disconnect()

        self._connection_state = self.STATE_DISCONNECTED
        return True

    @property
    def wifi(self):
        """Direct access to a Wi-Fi manager if needed."""
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_or_create_service('wifi')
        return self._wifi_instance


def _on_task_event(event):
    """Handle task lifecycle events."""
    if event.event_type == TaskEvent.TASK_FAILED:
        logger.error(f"SystemManager: Task {event.task_id} failed with error: {event.error}")
    elif event.event_type == TaskEvent.TASK_COMPLETED:
        logger.debug(f"SystemManager: Task {event.task_id} completed")
    elif event.event_type == TaskEvent.TASK_STARTED:
        logger.debug(f"SystemManager: Task {event.task_id} started")
    elif event.event_type == TaskEvent.TASK_STOPPED:
        logger.debug(f"SystemManager: Task {event.task_id} stopped")


class SystemManager:
    """Master system manager that coordinates all subsystems (Singleton)."""
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, device_name="Unnamed Device", wifi_ssid=None, wifi_password=None):
        # We only want to initialize instance variables once
        if not hasattr(self, '_instance_vars_initialized'):
            self._instance_vars_initialized = True
            
            # Initialize components with defaults to avoid None issues
            # self._log = Logger(debug_level)  # Initialize with default debug level
            
            # Store injected configuration values
            self._device_name = device_name
            self._wifi_ssid = wifi_ssid
            self._wifi_password = wifi_password
            
            # Services registry  
            self._services = {}
            # self._services['log'] = logger # ??
            
            # Initialize task manager
            self._task_manager = TaskManager()
            self._task_manager.add_listener(_on_task_event)
            self._services['task_manager'] = self._task_manager
            
            # Network manager (always initialized)
            self._network_manager = NetworkManager(self)
            
            # Remove redundant task ID - NetworkManager already has it
            # self._wifi_task_id = "wifi_update_task"  # REMOVE: Duplicate
        
        # The full initialization is deferred to init()
        self._initialized = False

    def register_service(self, name, service_instance):
        """Register a service with the system manager."""
        self._services[name] = service_instance
        logger.info(f"SystemManager: Registered service '{name}'")
        return service_instance
        
    def get_service(self, name):
        """Get a service by name. Returns None if not initialized."""
        return self._services.get(name)
        
    def get_or_create_service(self, name, factory=None):
        """Get an existing service or create it using the provided factory.

        Args:
            name: Service name to get or create
            factory: Optional factory function to create service if missing

        Returns:
            Service instance or None if service cannot be created
        """
        # Return if already exists
        service = self.get_service(name)
        if service:
            return service

        # Use the provided factory function if available
        if factory:
            try:
                service = factory()
                if service:
                    return self.register_service(name, service)
                return None
            except Exception as e:
                logger.error(f"SystemManager: Failed to create service '{name}': {e}")
                return None

        # Use built-in service creation if no factory provided
        return self._get_builtin_service(name)

    def _get_builtin_service(self, name):
        """Initialize built-in services by name."""
        if name == 'wifi':
            return self._initialize_wifi()
        return None
        
    def _initialize_wifi(self):
        """Initialize Wi-Fi service on demand."""
        if self._wifi_ssid and self._wifi_password:
            self._services['wifi'] = WiFiManager(self._wifi_ssid, self._wifi_password, self._device_name)
            logger.info("SystemManager: WiFi manager initialized")
            return self._services['wifi']
        else:
            logger.info("SystemManager: WiFi not initialized (no credentials)")
            return None
            
    def init(self):
        """Initialize system components. With the new design, this is a lighter weight."""
        # Prevent re-initialization of components
        if self._initialized:
            logger.info("SystemManager: Already initialized, skipping")
            return self
            
        # Validate configuration
        self._validate_config()

        # Log device name
        logger.info(f"SystemManager: Device name: {self._device_name}")

        logger.info(f"SystemManager: Initialization complete. Available services: {', '.join(self._services.keys())}")
        self._initialized = True
        return self

    # TODO: make this more useful
    def _validate_config(self):
        """Validate the required configuration early."""
        issues = []
        if not self._device_name:
            issues.append("Device name not set")
        if self._wifi_ssid and not self._wifi_password:
            issues.append("WiFi SSID set but password missing")
        if issues:
            logger.warning(f"SystemManager: Configuration issues: {', '.join(issues)}")
        return len(issues) == 0

    def get_service_status(self):
        """Get health status of all services."""
        status = {}
        for name, service in self._services.items():
            if hasattr(service, 'is_healthy'):
                status[name] = service.is_healthy()
            else:
                status[name] = service is not None
        return status
   
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
    
    def restart_service(self, name):
        """Restart a service by cleaning it up and reinitializing."""
        service = self.get_service(name)
        if not service:
            logger.warning(f"SystemManager: Cannot restart service '{name}' - not found")
            return False

        # Clean up the service if it has a cleanup method
        try:
            if hasattr(service, 'cleanup'):
                service.cleanup()
            # Remove from the service registry
            del self._services[name]
            logger.info(f"SystemManager: Service '{name}' removed for restart")
        except Exception as e:
            logger.error(f"SystemManager: Error cleaning up service '{name}': {e}")

        # Recreate the service
        new_service = self.get_or_create_service(name)
        return new_service is not None

    def cleanup(self):
        """Clean up all services and prepare for shutdown."""
        logger.info("SystemManager: Cleaning up all services")

        # First, stop all tasks
        self.cancel_all_tasks()

        # Clean up each service that supports cleanup
        for name, service in list(self._services.items()):
            try:
                if hasattr(service, 'cleanup'):
                    service.cleanup()
                    logger.debug(f"SystemManager: Service '{name}' cleaned up")
            except Exception as e:
                logger.error(f"SystemManager: Error cleaning up service '{name}': {e}")

        # Clear services registry
        self._services.clear()
        self._initialized = False

        return True

    # Properties to access component instances
    # @property
    # def log(self):
    #     """Access the logger instance."""
    #     return logger
        
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