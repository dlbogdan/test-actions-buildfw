import time
import gc
import lib.coresys.logger as logger
from lib.coresys.manager_wifi import WiFiManager
from lib.coresys.manager_tasks import TaskManager
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
            self._last_error = "Wi-Fi configuration missing"
            return False

        # Only start the task if not already running

        if not self._task_manager.get_task_info(self._wifi_task_id):
            # Start WiFi update task
            self._task_manager.ensure_periodic_task(
                self._wifi_task_id,
                self._wifi_instance.update,
                interval_ms=500,
                description="Wi-Fi Update Loop",
                is_coroutine=False
            )

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
            if self._wifi_instance.connection_failed() and self._retry_count < self._max_retries:
                self._retry_count += 1
                self._wifi_instance.reconnect()

            await asyncio.sleep_ms(250)

        # Connection successful
        self._connection_state = self.STATE_CONNECTED
        self._last_error = None
        return True
        
    def is_up(self):
        """Check if the network is connected."""
        # Use cached instance instead of repeated lookups
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_service('wifi')

        if not self._wifi_instance:
            # No Wi-Fi service available - we can't be connected
            return False

        return self._wifi_instance.is_connected()
        
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
            'connected': self.is_up(),
            'ip_address': self.get_ip(),
            'network_quality': self.get_network_quality(),
            'network_name': self.get_network_name(),
            'retries': self._retry_count,
            'last_error': self._last_error
        }
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

    def get_network_quality(self):
        """Get current network connection quality (0-100% or None).

        For Wi-Fi, this is derived from signal strength.
        For other connection types, implementation-specific metrics will be used.

        Returns:
            int: Connection quality as percentage (0-100) or None if not available
        """
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_service('wifi')

        if not self._wifi_instance or not self.is_up():
            return None

        # For Wi-Fi: Get signal strength and convert to quality percentage
        rssi = self._wifi_instance.get_signal_strength()
        if rssi is not None:
            # Convert RSSI (typically -100 to 0) to quality percentage
            # -50 or better is excellent (100%), -100 or worse is poor (0%)
            if rssi >= -50:
                return 100
            elif rssi <= -100:
                return 0
            else:
                return int((rssi + 100) * 2)  # Linear scale from 0-100%

        return None

    def get_network_name(self):
        """Get the name of the current network connection.

        For Wi-Fi, this is the SSID.
        For other connection types, implementation-specific identifiers will be used.

        Returns:
            str: Network name or None if not connected/available
        """
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_service('wifi')

        if not self._wifi_instance or not self.is_up():
            return None

        # For Wi-Fi: Get SSID
        return self._wifi_instance.get_ssid()

    @property
    def wifi(self):
        """Direct access to a Wi-Fi manager if needed."""
        if not self._wifi_instance:
            self._wifi_instance = self._system.get_or_create_service('wifi')
        return self._wifi_instance


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

            # Record initialization timestamp
            self._init_time = time.time()
            
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
            self._services['task_manager'] = self._task_manager
            
            # Network manager (always initialized)
            self._network_manager = NetworkManager(self)
            
            # Remove a redundant task ID - NetworkManager already has it
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

    def configure_wifi(self, ssid, password):
        """Configure Wi-Fi parameters and reinitialize if needed.

        Args:
            ssid: Wi-Fi network SSID
            password: WiFi network password

        Returns:
            bool: True if configuration was successful, False otherwise
        """
        if not ssid or not password:
            logger.warning("SystemManager: Invalid WiFi configuration parameters")
            return False

        # Store new credentials
        self._wifi_ssid = ssid
        self._wifi_password = password

        # Disconnect existing Wi-Fi if active
        if 'wifi' in self._services and self._services['wifi']:
            self._services['wifi'].disconnect()

        # Reinitialize WiFi with new credentials
        wifi_service = self._initialize_wifi()

        # If a network manager exists, restart it to use a new configuration
        if hasattr(self, '_network_manager') and self._network_manager:
            self._network_manager._wifi_instance = wifi_service

        return wifi_service is not None
            
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
            try:
                status[name] = service.is_healthy()
            except AttributeError:
                status[name] = service is not None
        return status

    def get_system_status(self):
        """Get comprehensive system status including all subsystems.

        Returns:
            dict: Dictionary containing system status information
        """
        # Collect memory information
        gc.collect()
        mem_free = gc.mem_free()
        mem_alloc = gc.mem_alloc() if hasattr(gc, 'mem_alloc') else None

        status = {
            'device': {
                'name': self._device_name,
                'initialized': self._initialized,
                'uptime': time.time() - self._init_time if hasattr(self, '_init_time') else None,
            },
            'memory': {
                'free': mem_free,
                'allocated': mem_alloc,
                'total': (mem_free + mem_alloc) if mem_alloc is not None else None
            },
            'services': self.get_service_status(),
            'tasks': {
                'count': len(self._task_manager.get_all_tasks()) if self._task_manager else 0
            }
        }

        # Add network status if available
        if hasattr(self, '_network_manager') and self._network_manager:
            status['network'] = self._network_manager.get_connection_status()

        return status

    def get_tasks_info(self):
        """Get detailed information about all tasks.

        Returns:
            list: List of dictionaries with task information
        """
        result = []
        for task_id in self._task_manager.get_all_tasks():
            task_info = self._task_manager.get_task_info(task_id)
            if task_info:
                # Copy the task info and add the ID
                task_data = dict(task_info)
                task_data['id'] = task_id
                result.append(task_data)
        return result
    
    def restart_service(self, name):
        """Restart a service by cleaning it up and reinitializing."""
        service = self.get_service(name)
        if not service:
            logger.warning(f"SystemManager: Cannot restart service '{name}' - not found")
            return False

        # Clean up the service
        try:
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
        self._task_manager.cancel_all_tasks()

        # Clean up each service
        for name, service in list(self._services.items()):
            try:
                service.cleanup()
                logger.debug(f"SystemManager: Service '{name}' cleaned up")
            except Exception as e:
                logger.error(f"SystemManager: Error cleaning up service '{name}': {e}")

        # Clear services registry
        self._services.clear()
        self._initialized = False

        return True

    def generate_status_report(self):
        """Generate a comprehensive status report suitable for diagnostics.

        Returns:
            dict: Status report with system info, services, tasks, and network status
        """
        report = {
            'timestamp': time.time(),
            'system': self.get_system_status(),
            'tasks': self.get_tasks_info()
        }

        # Add the version if available
        try:
            with open('/version.txt', 'r') as f:
                report['version'] = f.read().strip()
        except OSError:
            report['version'] = int('nan')

        return report
        
    @property
    def network(self):
        """Access the network manager."""
        return self._network_manager
        
    @property
    def device_name(self):
        """Access the device name."""
        return self._device_name
        
    @property
    def task_manager(self):
        """Access the task manager instance."""
        return self._task_manager