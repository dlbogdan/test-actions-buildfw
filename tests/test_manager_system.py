"""
Tests for SystemManager and NetworkManager classes.
"""
import pytest
import asyncio
import sys
import os
from unittest.mock import patch, MagicMock, AsyncMock

# Add src to path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.coresys.manager_system import SystemManager, NetworkManager
from lib.coresys.manager_tasks import TaskEvent


class TestNetworkManager:
    """Test cases for NetworkManager class"""
    
    def setup_method(self):
        """Set up fresh SystemManager and NetworkManager for each test."""
        # Reset SystemManager singleton
        SystemManager._instance = None
        SystemManager._initialized = False
        
        self.system_manager = SystemManager(
            device_name="test-device",
            wifi_ssid="test-network",
            wifi_password="test-password",
            debug_level=1
        )
        self.network_manager = self.system_manager.network
    
    def test_network_manager_initialization(self):
        """Test NetworkManager initialization."""
        assert self.network_manager._system is self.system_manager
        assert self.network_manager._log is self.system_manager.log
        assert self.network_manager._task_manager is self.system_manager.task_manager
        assert self.network_manager._wifi_task_id == "wifi_update_task"
        assert not self.network_manager._is_up_called
    
    def test_network_up_with_wifi_credentials(self):
        """Test bringing network up with WiFi credentials."""
        # Mock WiFi manager
        mock_wifi = MagicMock()
        self.system_manager._services['wifi'] = mock_wifi
        
        result = self.network_manager.up()
        
        assert result is True
        assert self.network_manager._is_up_called is True
        
        # Should have started WiFi update task
        task_info = self.system_manager.task_manager.get_task_info("wifi_update_task")
        assert task_info is not None
        assert task_info['description'] == "WiFi Update Loop"
    
    def test_network_up_without_wifi_credentials(self):
        """Test bringing network up without WiFi credentials."""
        # Create system manager without WiFi credentials
        SystemManager._instance = None
        SystemManager._initialized = False
        
        system_manager = SystemManager(device_name="test-device")
        network_manager = system_manager.network
        
        result = network_manager.up()
        
        assert result is False
        assert not network_manager._is_up_called
    
    def test_network_up_task_already_running(self):
        """Test bringing network up when task is already running."""
        # Mock WiFi manager
        mock_wifi = MagicMock()
        self.system_manager._services['wifi'] = mock_wifi
        
        # Start network first time
        self.network_manager.up()
        
        # Start again - should not create duplicate task
        result = self.network_manager.up()
        
        assert result is True
        
        # Should still only have one task
        all_tasks = self.system_manager.task_manager.get_all_tasks()
        wifi_tasks = [t for t in all_tasks.keys() if "wifi" in t]
        assert len(wifi_tasks) == 1
    
    def test_network_down_with_wifi(self):
        """Test bringing network down with WiFi connected."""
        # Mock WiFi manager
        mock_wifi = MagicMock()
        mock_wifi.is_connected.return_value = True
        self.system_manager._services['wifi'] = mock_wifi
        
        # Bring network up first
        self.network_manager.up()
        
        # Bring network down
        result = self.network_manager.down()
        
        assert result is True
        assert not self.network_manager._is_up_called
        
        # Should have disconnected WiFi
        mock_wifi.disconnect.assert_called_once()
        
        # Task should be stopped
        assert not self.system_manager.task_manager.is_task_running("wifi_update_task")
    
    def test_network_down_without_wifi(self):
        """Test bringing network down without WiFi service."""
        result = self.network_manager.down()
        assert result is False
    
    @pytest.mark.asyncio
    async def test_wait_until_up_success(self):
        """Test waiting for network to come up successfully."""
        # Mock WiFi manager
        mock_wifi = MagicMock()
        mock_wifi.is_connected.side_effect = [False, False, True]  # Connected on third check
        mock_wifi.get_ip.return_value = "192.168.1.100"
        self.system_manager._services['wifi'] = mock_wifi
        
        with patch('time.ticks_ms', side_effect=[0, 100, 200]):
            with patch('time.ticks_diff', side_effect=[100, 200]):
                result = await self.network_manager.wait_until_up(timeout_ms=5000)
        
        assert result is True
        assert self.network_manager._is_up_called is True
    
    @pytest.mark.asyncio
    async def test_wait_until_up_timeout(self):
        """Test waiting for network times out."""
        # Mock WiFi manager that never connects
        mock_wifi = MagicMock()
        mock_wifi.is_connected.return_value = False
        self.system_manager._services['wifi'] = mock_wifi
        
        with patch('time.ticks_ms', side_effect=[0, 1000, 2000, 3000]):
            with patch('time.ticks_diff', side_effect=[1000, 2000, 3000]):
                result = await self.network_manager.wait_until_up(timeout_ms=2500)
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_wait_until_up_without_wifi(self):
        """Test waiting for network without WiFi credentials."""
        # Create system manager without WiFi credentials
        SystemManager._instance = None
        SystemManager._initialized = False
        
        system_manager = SystemManager(device_name="test-device")
        network_manager = system_manager.network
        
        result = await network_manager.wait_until_up()
        
        assert result is False
    
    def test_is_up_with_connected_wifi(self):
        """Test checking if network is up with connected WiFi."""
        mock_wifi = MagicMock()
        mock_wifi.is_connected.return_value = True
        self.system_manager._services['wifi'] = mock_wifi
        
        result = self.network_manager.is_up()
        assert result is True
    
    def test_is_up_with_disconnected_wifi(self):
        """Test checking if network is up with disconnected WiFi."""
        mock_wifi = MagicMock()
        mock_wifi.is_connected.return_value = False
        self.system_manager._services['wifi'] = mock_wifi
        
        result = self.network_manager.is_up()
        assert result is False
    
    def test_is_up_without_wifi(self):
        """Test checking if network is up without WiFi service."""
        result = self.network_manager.is_up()
        assert result is False
    
    def test_get_ip_with_connected_wifi(self):
        """Test getting IP address with connected WiFi."""
        mock_wifi = MagicMock()
        mock_wifi.is_connected.return_value = True
        mock_wifi.get_ip.return_value = "192.168.1.100"
        self.system_manager._services['wifi'] = mock_wifi
        
        ip = self.network_manager.get_ip()
        assert ip == "192.168.1.100"
    
    def test_get_ip_without_wifi(self):
        """Test getting IP address without WiFi service."""
        ip = self.network_manager.get_ip()
        assert ip is None
    
    def test_wifi_property(self):
        """Test direct access to WiFi manager."""
        # Should initialize WiFi service on access
        wifi = self.network_manager.wifi
        
        assert wifi is not None
        assert 'wifi' in self.system_manager._services


class TestSystemManager:
    """Test cases for SystemManager class"""
    
    def setup_method(self):
        """Reset SystemManager singleton before each test."""
        SystemManager._instance = None
        SystemManager._initialized = False
    
    def test_system_manager_singleton(self):
        """Test that SystemManager implements singleton pattern correctly."""
        sm1 = SystemManager(device_name="device1", debug_level=1)
        sm2 = SystemManager(device_name="device2", debug_level=2)
        
        # Should be the same instance
        assert sm1 is sm2
        # Should keep original configuration
        assert sm1._device_name == "device1"
        assert sm1.log.get_level() == 1
    
    def test_system_manager_initialization(self):
        """Test SystemManager initialization with all parameters."""
        sm = SystemManager(
            device_name="test-device",
            wifi_ssid="test-network",
            wifi_password="test-password",
            debug_level=2
        )
        
        assert sm._device_name == "test-device"
        assert sm._wifi_ssid == "test-network"
        assert sm._wifi_password == "test-password"
        assert sm.log.get_level() == 2
        assert not sm._initialized
        
        # Should have basic services
        assert 'log' in sm._services
        assert 'task_manager' in sm._services
        assert sm._network_manager is not None
    
    def test_system_manager_initialization_minimal(self):
        """Test SystemManager initialization with minimal parameters."""
        sm = SystemManager()
        
        assert sm._device_name == "Unnamed Device"
        assert sm._wifi_ssid is None
        assert sm._wifi_password is None
        assert sm.log.get_level() == 0
    
    def test_on_task_event_handling(self, capsys):
        """Test task event handling."""
        sm = SystemManager(debug_level=3)  # Enable debug logging
        
        # Test different event types
        from lib.coresys.manager_tasks import TaskEvent, TaskManager
        
        # Task failed event
        failed_event = TaskEvent("test_task", TaskEvent.TASK_FAILED, TaskManager.TASK_ONESHOT, error=Exception("Test error"))
        sm._on_task_event(failed_event)
        
        # Task completed event
        completed_event = TaskEvent("test_task", TaskEvent.TASK_COMPLETED, TaskManager.TASK_ONESHOT)
        sm._on_task_event(completed_event)
        
        # Task started event
        started_event = TaskEvent("test_task", TaskEvent.TASK_STARTED, TaskManager.TASK_ONESHOT)
        sm._on_task_event(started_event)
        
        # Task stopped event
        stopped_event = TaskEvent("test_task", TaskEvent.TASK_STOPPED, TaskManager.TASK_ONESHOT)
        sm._on_task_event(stopped_event)
        
        captured = capsys.readouterr()
        assert "Task test_task failed with error" in captured.out
        assert "Task test_task completed" in captured.out
        assert "Task test_task started" in captured.out
        assert "Task test_task stopped" in captured.out
    
    def test_register_service(self, capsys):
        """Test registering a service."""
        sm = SystemManager(debug_level=2)
        mock_service = MagicMock()
        
        result = sm.register_service("test_service", mock_service)
        
        assert result is mock_service
        assert sm._services["test_service"] is mock_service
        
        captured = capsys.readouterr()
        assert "Registered service 'test_service'" in captured.out
    
    def test_get_service_existing(self):
        """Test getting an existing service."""
        sm = SystemManager()
        mock_service = MagicMock()
        sm._services["test_service"] = mock_service
        
        result = sm.get_service("test_service")
        assert result is mock_service
    
    def test_get_service_nonexistent(self):
        """Test getting a non-existent service."""
        sm = SystemManager()
        
        result = sm.get_service("nonexistent")
        assert result is None
    
    def test_ensure_service_existing(self):
        """Test ensuring an existing service."""
        sm = SystemManager()
        mock_service = MagicMock()
        sm._services["test_service"] = mock_service
        
        result = sm.ensure_service("test_service")
        assert result is mock_service
    
    def test_ensure_service_wifi_with_credentials(self, capsys):
        """Test ensuring WiFi service with credentials."""
        sm = SystemManager(
            device_name="test-device",
            wifi_ssid="test-network",
            wifi_password="test-password",
            debug_level=2
        )
        
        with patch('lib.coresys.manager_system.WiFiManager') as mock_wifi_class:
            mock_wifi_instance = MagicMock()
            mock_wifi_class.return_value = mock_wifi_instance
            
            result = sm.ensure_service("wifi")
        
        assert result is mock_wifi_instance
        assert sm._services["wifi"] is mock_wifi_instance
        mock_wifi_class.assert_called_once_with("test-network", "test-password", "test-device")
        
        captured = capsys.readouterr()
        assert "WiFi manager initialized" in captured.out
    
    def test_ensure_service_wifi_without_credentials(self, capsys):
        """Test ensuring WiFi service without credentials."""
        sm = SystemManager(device_name="test-device", debug_level=2)
        
        result = sm.ensure_service("wifi")
        
        assert result is None
        assert "wifi" not in sm._services
        
        captured = capsys.readouterr()
        assert "WiFi not initialized (no credentials)" in captured.out
    
    def test_ensure_service_unknown(self):
        """Test ensuring an unknown service."""
        sm = SystemManager()
        
        result = sm.ensure_service("unknown_service")
        assert result is None
    
    def test_init_first_time(self, capsys):
        """Test system initialization for the first time."""
        sm = SystemManager(device_name="test-device", debug_level=2)
        
        result = sm.init()
        
        assert result is sm
        assert sm._initialized is True
        
        captured = capsys.readouterr()
        assert "Device name: test-device" in captured.out
        assert "Initialization complete" in captured.out
    
    def test_init_already_initialized(self, capsys):
        """Test system initialization when already initialized."""
        sm = SystemManager(debug_level=2)
        sm._initialized = True
        
        result = sm.init()
        
        assert result is sm
        
        captured = capsys.readouterr()
        assert "Already initialized, skipping" in captured.out
    
    def test_create_task(self):
        """Test creating a task through SystemManager."""
        sm = SystemManager()
        
        async def test_coro():
            return "result"
        
        task_id = sm.create_task(test_coro(), task_id="test_task", description="Test task")
        
        assert task_id == "test_task"
        assert sm.task_manager.get_task_info(task_id) is not None
    
    def test_create_periodic_task(self):
        """Test creating a periodic task through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        task_id = sm.create_periodic_task(test_update, interval_ms=100, task_id="periodic_test")
        
        assert task_id == "periodic_test"
        assert sm.task_manager.is_task_running(task_id)
        
        # Clean up
        sm.stop_task(task_id)
    
    def test_ensure_task_running_new(self):
        """Test ensuring a task is running when it doesn't exist."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        task_id = sm.ensure_task_running("ensure_test", test_update, interval_ms=100)
        
        assert task_id == "ensure_test"
        assert sm.task_manager.is_task_running(task_id)
        
        # Clean up
        sm.stop_task(task_id)
    
    def test_ensure_task_running_existing(self):
        """Test ensuring a task is running when it already exists."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        # Create initial task
        task_id1 = sm.create_periodic_task(test_update, task_id="ensure_existing")
        
        # Ensure same task
        task_id2 = sm.ensure_task_running("ensure_existing", test_update)
        
        assert task_id1 == task_id2 == "ensure_existing"
        
        # Clean up
        sm.stop_task(task_id1)
    
    def test_stop_task(self):
        """Test stopping a task through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        task_id = sm.create_periodic_task(test_update, task_id="stop_test")
        
        result = sm.stop_task(task_id)
        
        assert result is True
        assert not sm.task_manager.is_task_running(task_id)
    
    def test_restart_task(self):
        """Test restarting a task through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        task_id = sm.create_periodic_task(test_update, task_id="restart_test")
        
        result = sm.restart_task(task_id)
        
        assert result is True
        assert sm.task_manager.is_task_running(task_id)
        
        # Clean up
        sm.stop_task(task_id)
    
    def test_cancel_all_tasks(self):
        """Test cancelling all tasks through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        # Create multiple tasks
        task1 = sm.create_periodic_task(test_update, task_id="task1")
        task2 = sm.create_periodic_task(test_update, task_id="task2")
        
        sm.cancel_all_tasks()
        
        assert not sm.task_manager.is_task_running(task1)
        assert not sm.task_manager.is_task_running(task2)
    
    def test_get_task_info(self):
        """Test getting task info through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        task_id = sm.create_periodic_task(test_update, task_id="info_test", description="Test task")
        
        info = sm.get_task_info(task_id)
        
        assert info is not None
        assert info['description'] == "Test task"
        
        # Clean up
        sm.stop_task(task_id)
    
    def test_get_all_tasks(self):
        """Test getting all tasks through SystemManager."""
        sm = SystemManager()
        
        def test_update():
            pass
        
        # Create tasks
        task1 = sm.create_periodic_task(test_update, task_id="task1")
        task2 = sm.create_periodic_task(test_update, task_id="task2")
        
        all_tasks = sm.get_all_tasks()
        
        assert len(all_tasks) == 2
        assert "task1" in all_tasks
        assert "task2" in all_tasks
        
        # Clean up
        sm.cancel_all_tasks()
    
    def test_log_property(self):
        """Test log property access."""
        sm = SystemManager(debug_level=3)
        
        log = sm.log
        
        assert log is sm._log
        assert log.get_level() == 3
    
    def test_network_property(self):
        """Test network property access."""
        sm = SystemManager()
        
        network = sm.network
        
        assert network is sm._network_manager
        assert isinstance(network, NetworkManager)
    
    def test_device_name_property(self):
        """Test device_name property access."""
        sm = SystemManager(device_name="test-device")
        
        device_name = sm.device_name
        
        assert device_name == "test-device"
    
    def test_task_manager_property(self):
        """Test task_manager property access."""
        sm = SystemManager()
        
        task_manager = sm.task_manager
        
        assert task_manager is sm._task_manager


class TestSystemManagerIntegration:
    """Integration tests for SystemManager functionality."""
    
    def setup_method(self):
        """Reset SystemManager singleton before each test."""
        SystemManager._instance = None
        SystemManager._initialized = False
    
    @pytest.mark.asyncio
    async def test_complete_system_workflow(self):
        """Test complete system workflow with network and tasks."""
        # Create system manager with WiFi credentials
        sm = SystemManager(
            device_name="integration-test",
            wifi_ssid="test-network",
            wifi_password="test-password",
            debug_level=2
        )
        
        # Initialize system
        sm.init()
        
        # Mock WiFi manager for network operations
        mock_wifi = MagicMock()
        mock_wifi.is_connected.side_effect = [False, True, True]  # Connect on second check
        mock_wifi.get_ip.return_value = "192.168.1.100"
        sm.register_service("wifi", mock_wifi)
        
        # Test network operations
        network_up_result = sm.network.up()
        assert network_up_result is True
        
        # Wait for network (should succeed quickly due to mock)
        with patch('time.ticks_ms', side_effect=[0, 100]):
            with patch('time.ticks_diff', return_value=100):
                network_ready = await sm.network.wait_until_up(timeout_ms=1000)
        
        assert network_ready is True
        assert sm.network.is_up() is True
        assert sm.network.get_ip() == "192.168.1.100"
        
        # Create some tasks
        task_calls = 0
        def periodic_task():
            nonlocal task_calls
            task_calls += 1
        
        task_id = sm.create_periodic_task(periodic_task, interval_ms=10, description="Integration test task")
        
        # Let task run
        await asyncio.sleep(0.05)
        
        # Check task is working
        assert task_calls >= 3
        assert sm.is_task_running(task_id)
        
        # Get system status
        all_tasks = sm.get_all_tasks()
        assert len(all_tasks) >= 2  # Our task + WiFi update task
        
        # Clean up
        sm.network.down()
        sm.cancel_all_tasks()
        
        assert not sm.network.is_up()
        assert len(sm.get_all_tasks()) == 0
    
    def test_system_manager_service_lifecycle(self):
        """Test complete service lifecycle management."""
        sm = SystemManager(device_name="service-test", debug_level=1)
        
        # Test service registration
        mock_service1 = MagicMock()
        mock_service2 = MagicMock()
        
        sm.register_service("service1", mock_service1)
        sm.register_service("service2", mock_service2)
        
        # Test service retrieval
        assert sm.get_service("service1") is mock_service1
        assert sm.get_service("service2") is mock_service2
        assert sm.get_service("nonexistent") is None
        
        # Test service ensuring
        assert sm.ensure_service("service1") is mock_service1
        assert sm.ensure_service("nonexistent") is None
        
        # Test built-in services
        assert sm.get_service("log") is not None
        assert sm.get_service("task_manager") is not None
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self):
        """Test system error handling and recovery."""
        sm = SystemManager(debug_level=1)
        
        # Test task failure handling
        failure_count = 0
        def failing_task():
            nonlocal failure_count
            failure_count += 1
            if failure_count <= 2:
                raise RuntimeError(f"Failure {failure_count}")
        
        task_id = sm.create_periodic_task(failing_task, interval_ms=10, description="Failing task")
        
        # Let it fail a few times
        await asyncio.sleep(0.05)
        
        # Task should still be running despite failures
        assert sm.is_task_running(task_id)
        assert failure_count > 2  # Should have continued after failures
        
        # Clean up
        sm.stop_task(task_id)
        
        # Test network error handling
        sm_no_wifi = SystemManager(device_name="no-wifi-test")
        
        # Should handle missing WiFi gracefully
        assert sm_no_wifi.network.up() is False
        assert sm_no_wifi.network.is_up() is False
        assert sm_no_wifi.network.get_ip() is None
        
        network_ready = await sm_no_wifi.network.wait_until_up(timeout_ms=100)
        assert network_ready is False 