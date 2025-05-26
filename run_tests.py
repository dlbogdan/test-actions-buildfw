#!/usr/bin/env python3
"""
Simple test runner to demonstrate MicroPython testing approaches.
Run this to see the mock-based testing in action.
"""
import sys
import os
import subprocess
import tempfile
import json

def setup_test_environment():
    """Set up the test environment with mock modules."""
    # Add the tests directory to Python path
    test_dir = os.path.join(os.path.dirname(__file__), 'tests')
    if test_dir not in sys.path:
        sys.path.insert(0, test_dir)
    
    # Add src directory to Python path
    src_dir = os.path.join(os.path.dirname(__file__), 'src')
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

def run_mock_based_tests():
    """Run tests using the mock-based approach."""
    print("🧪 Running Mock-based Tests")
    print("=" * 50)
    
    # Set up the environment
    setup_test_environment()
    
    # Import the mocks and set them up
    from tests.mocks.micropython_mocks import (
        MockUOS, MockMachine, MockNetwork, MockGC, MockUAsyncio
    )
    
    # Patch sys.modules to include our mocks
    mock_modules = {
        'uos': MockUOS(),
        'machine': MockMachine(),
        'network': MockNetwork(),
        'gc': MockGC(),
        'uasyncio': MockUAsyncio(),
    }
    
    # Save original modules
    original_modules = {}
    for name in mock_modules:
        if name in sys.modules:
            original_modules[name] = sys.modules[name]
    
    try:
        # Install mocks
        sys.modules.update(mock_modules)
        
        # Now we can import and test MicroPython code
        from lib.coresys.manager_config import ConfigManager
        
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            test_config = {
                "SYS": {
                    "DEVICE": {"NAME": "test-device"},
                    "WIFI": {"SSID": "test-network", "PASS": "test-password"}
                }
            }
            json.dump(test_config, f)
            config_file = f.name
        
        try:
            # Test 1: Basic configuration loading
            print("Test 1: Loading configuration...")
            config = ConfigManager(config_file)
            device_name = config.get("SYS", "DEVICE")["NAME"]
            print(f"  ✓ Device name: {device_name}")
            
            # Test 2: Setting and getting values
            print("Test 2: Setting and getting values...")
            config.set("TEST", "KEY", "test_value")
            retrieved_value = config.get("TEST", "KEY")
            assert retrieved_value == "test_value"
            print(f"  ✓ Set and retrieved: {retrieved_value}")
            
            # Test 3: Default values
            print("Test 3: Default values...")
            default_value = config.get("TEST", "NONEXISTENT", "default")
            assert default_value == "default"
            print(f"  ✓ Default value: {default_value}")
            
            # Test 4: Observer pattern
            print("Test 4: Observer pattern...")
            callback_called = []
            
            def test_callback(value):
                callback_called.append(value)
            
            config.subscribe("TEST.OBSERVER", test_callback)
            config.set("TEST", "OBSERVER", "observed_value")
            assert len(callback_called) == 1
            assert callback_called[0] == "observed_value"
            print(f"  ✓ Observer called with: {callback_called[0]}")
            
            print("\n🎉 All mock-based tests passed!")
            
        finally:
            # Clean up temp file
            os.unlink(config_file)
    
    finally:
        # Restore original modules
        for name, module in original_modules.items():
            sys.modules[name] = module
        for name in mock_modules:
            if name not in original_modules:
                sys.modules.pop(name, None)

def run_build_system_tests():
    """Run tests for the build system (standard Python)."""
    print("\n🔨 Running Build System Tests")
    print("=" * 50)
    
    setup_test_environment()
    
    # Import build system
    import local_builder
    
    # Test 1: Version detection
    print("Test 1: Version detection...")
    version = local_builder.get_version("v1.0.0")
    assert version == "v1.0.0"
    print(f"  ✓ Version: {version}")
    
    # Test 2: SHA256 calculation
    print("Test 2: SHA256 calculation...")
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("Hello, World!")
        temp_file = f.name
    
    try:
        sha256 = local_builder.calculate_file_sha256(temp_file)
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert sha256 == expected
        print(f"  ✓ SHA256: {sha256[:16]}...")
    finally:
        os.unlink(temp_file)
    
    # Test 3: Directory creation
    print("Test 3: Directory creation...")
    with tempfile.TemporaryDirectory() as temp_dir:
        test_dir = os.path.join(temp_dir, "test_build")
        local_builder.ensure_directory(test_dir)
        assert os.path.exists(test_dir)
        print(f"  ✓ Directory created: {os.path.basename(test_dir)}")
    
    print("\n🎉 All build system tests passed!")

def run_logger_tests():
    """Run tests for the Logger manager."""
    print("\n📝 Running Logger Manager Tests")
    print("=" * 50)
    
    setup_test_environment()
    
    # Set up mocks
    from tests.mocks.micropython_mocks import MockMachine, MockUTime
    sys.modules['machine'] = MockMachine()
    sys.modules['time'] = MockUTime()
    
    try:
        from lib.coresys.manager_logger import Logger
        
        # Reset singleton for clean test
        Logger._instance = None
        Logger._initialized = False
        
        # Test 1: Logger initialization
        print("Test 1: Logger initialization...")
        logger = Logger(debug_level=2)
        assert logger.get_level() == 2
        print(f"  ✓ Logger initialized with debug level: {logger.get_level()}")
        
        # Test 2: Different log levels
        print("Test 2: Testing log levels...")
        logger.error("Test error message")
        logger.warning("Test warning message")
        logger.info("Test info message")
        print("  ✓ All log levels working")
        
        # Test 3: Error history
        print("Test 3: Error history...")
        history = logger.get_error_warning_history()
        assert len(history) >= 2  # Error and warning
        print(f"  ✓ Error history contains {len(history)} entries")
        
        print("\n🎉 Logger tests passed!")
        
    finally:
        sys.modules.pop('machine', None)
        sys.modules.pop('time', None)

def run_task_manager_tests():
    """Run tests for the TaskManager."""
    print("\n⚙️ Running TaskManager Tests")
    print("=" * 50)
    
    setup_test_environment()
    
    # Set up mocks
    from tests.mocks.micropython_mocks import MockUAsyncio, MockUTime
    sys.modules['uasyncio'] = MockUAsyncio()
    sys.modules['time'] = MockUTime()
    
    try:
        from lib.coresys.manager_tasks import TaskManager, TaskEvent
        
        # Test 1: TaskManager initialization
        print("Test 1: TaskManager initialization...")
        task_manager = TaskManager()
        assert task_manager._next_task_id == 1
        print("  ✓ TaskManager initialized")
        
        # Test 2: Task events
        print("Test 2: Task events...")
        event = TaskEvent("test_task", TaskEvent.TASK_STARTED, TaskManager.TASK_ONESHOT)
        assert event.task_id == "test_task"
        assert event.event_type == TaskEvent.TASK_STARTED
        print("  ✓ Task events working")
        
        # Test 3: Event listeners
        print("Test 3: Event listeners...")
        events_received = []
        
        def test_listener(event):
            events_received.append(event)
        
        task_manager.add_listener(test_listener)
        
        # Create a simple periodic task
        call_count = 0
        def test_update():
            nonlocal call_count
            call_count += 1
        
        task_id = task_manager.create_periodic_task(test_update, interval_ms=100, task_id="test_task")
        assert task_id == "test_task"
        print(f"  ✓ Task created with ID: {task_id}")
        
        # Stop the task
        task_manager.stop_task(task_id)
        print("  ✓ Task stopped successfully")
        
        print("\n🎉 TaskManager tests passed!")
        
    finally:
        sys.modules.pop('uasyncio', None)
        sys.modules.pop('time', None)

def run_system_manager_tests():
    """Run tests for the SystemManager."""
    print("\n🖥️ Running SystemManager Tests")
    print("=" * 50)
    
    setup_test_environment()
    
    # Set up mocks
    from tests.mocks.micropython_mocks import (
        MockMachine, MockUTime, MockUAsyncio, MockNetwork
    )
    sys.modules['machine'] = MockMachine()
    sys.modules['time'] = MockUTime()
    sys.modules['uasyncio'] = MockUAsyncio()
    sys.modules['network'] = MockNetwork()
    
    try:
        from lib.coresys.manager_system import SystemManager
        
        # Reset singleton for clean test
        SystemManager._instance = None
        SystemManager._initialized = False
        
        # Test 1: SystemManager initialization
        print("Test 1: SystemManager initialization...")
        sm = SystemManager(
            device_name="test-device",
            wifi_ssid="test-network",
            wifi_password="test-password",
            debug_level=1
        )
        assert sm.device_name == "test-device"
        print(f"  ✓ SystemManager initialized for device: {sm.device_name}")
        
        # Test 2: Service registration
        print("Test 2: Service registration...")
        mock_service = object()
        result = sm.register_service("test_service", mock_service)
        assert result is mock_service
        assert sm.get_service("test_service") is mock_service
        print("  ✓ Service registration working")
        
        # Test 3: Network manager
        print("Test 3: Network manager...")
        network = sm.network
        assert network is not None
        print("  ✓ Network manager accessible")
        
        # Test 4: Task management
        print("Test 4: Task management...")
        def test_task():
            pass
        
        task_id = sm.create_periodic_task(test_task, interval_ms=100, task_id="system_test")
        assert task_id == "system_test"
        
        # Stop the task
        sm.stop_task(task_id)
        print("  ✓ Task management working")
        
        print("\n🎉 SystemManager tests passed!")
        
    finally:
        sys.modules.pop('machine', None)
        sys.modules.pop('time', None)
        sys.modules.pop('uasyncio', None)
        sys.modules.pop('network', None)

def run_firmware_updater_tests():
    """Run tests for the FirmwareUpdater."""
    print("\n🔄 Running FirmwareUpdater Tests")
    print("=" * 50)
    
    setup_test_environment()
    
    # Set up mocks
    from tests.mocks.micropython_mocks import (
        MockUOS, MockMachine, MockUAsyncio, MockURequests, MockUJson, MockUsocket, MockDeflate, MockUTarFile
    )
    sys.modules['uos'] = MockUOS()
    sys.modules['machine'] = MockMachine()
    sys.modules['uasyncio'] = MockUAsyncio()
    sys.modules['urequests'] = MockURequests()
    sys.modules['ujson'] = MockUJson()
    sys.modules['usocket'] = MockUsocket()
    sys.modules['deflate'] = MockDeflate()
    sys.modules['utarfile'] = MockUTarFile()
    
    try:
        from lib.coresys.manager_firmware import FirmwareUpdater
        
        # Test 1: FirmwareUpdater initialization (GitHub mode)
        print("Test 1: FirmwareUpdater initialization (GitHub mode)...")
        updater = FirmwareUpdater(
            device_model="test-device",
            github_repo="test/repo",
            github_token="test-token"
        )
        assert updater.device_model == "test-device"
        assert updater.github_repo == "test/repo"
        assert not updater.is_direct_mode
        print("  ✓ GitHub mode initialization working")
        
        # Test 2: Direct mode initialization
        print("Test 2: Direct mode initialization...")
        updater_direct = FirmwareUpdater(
            device_model="test-device",
            direct_base_url="https://firmware.example.com"
        )
        assert updater_direct.is_direct_mode
        assert updater_direct.direct_base_url == "https://firmware.example.com/"
        print("  ✓ Direct mode initialization working")
        
        # Test 3: Version parsing
        print("Test 3: Version parsing...")
        version_tuple = updater._parse_semver("1.2.3")
        assert version_tuple == (1, 2, 3)
        print(f"  ✓ Version parsing: 1.2.3 -> {version_tuple}")
        
        # Test 4: Version comparison
        print("Test 4: Version comparison...")
        updater.current_version = "1.0.0"
        is_newer = updater._compare_versions("1.1.0")
        assert is_newer is True
        print("  ✓ Version comparison working")
        
        # Test 5: URL parsing
        print("Test 5: URL parsing...")
        host, port, path = updater._parse_url("https://api.github.com/repos/test/repo")
        assert host == "api.github.com"
        assert port == 443
        assert path == "/repos/test/repo"
        print(f"  ✓ URL parsing: {host}:{port}{path}")
        
        print("\n🎉 FirmwareUpdater tests passed!")
        
    finally:
        sys.modules.pop('uos', None)
        sys.modules.pop('machine', None)
        sys.modules.pop('uasyncio', None)
        sys.modules.pop('urequests', None)
        sys.modules.pop('ujson', None)
        sys.modules.pop('usocket', None)
        sys.modules.pop('deflate', None)
        sys.modules.pop('utarfile', None)

def demonstrate_micropython_compatibility():
    """Demonstrate how the mocks make MicroPython code work in standard Python."""
    print("\n🔄 Demonstrating MicroPython Compatibility")
    print("=" * 50)
    
    setup_test_environment()
    
    # Set up mocks
    from tests.mocks.micropython_mocks import MockMachine, MockGC
    sys.modules['machine'] = MockMachine()
    sys.modules['gc'] = MockGC()
    
    try:
        # This code looks like MicroPython but runs in standard Python
        import machine
        import gc
        
        print("Creating LED pin...")
        led = machine.Pin('LED', machine.Pin.OUT)
        
        print("Toggling LED...")
        led.on()
        print(f"  LED value: {led.value()}")
        led.toggle()
        print(f"  LED value after toggle: {led.value()}")
        
        print("Checking memory...")
        free_mem = gc.mem_free()
        print(f"  Free memory: {free_mem} bytes")
        
        print("Triggering garbage collection...")
        gc.collect()
        
        print("\n✨ MicroPython code ran successfully in standard Python!")
        
    finally:
        # Clean up
        sys.modules.pop('machine', None)
        sys.modules.pop('gc', None)

def main():
    """Run all test demonstrations."""
    print("🚀 MicroPython Testing Demonstration")
    print("=" * 60)
    print("This script demonstrates how to test MicroPython code")
    print("using mocks that make it compatible with standard Python.")
    print()
    
    try:
        # Core system tests
        run_mock_based_tests()
        run_build_system_tests()
        
        # Manager module tests
        run_logger_tests()
        run_task_manager_tests()
        run_system_manager_tests()
        run_firmware_updater_tests()
        
        # Compatibility demonstration
        demonstrate_micropython_compatibility()
        
        print("\n" + "=" * 60)
        print("🎊 All demonstrations completed successfully!")
        print()
        print("✨ Test Coverage Summary:")
        print("  • ConfigManager - Configuration management and observer pattern")
        print("  • Logger - Logging system with multiple levels and error tracking")
        print("  • TaskManager - Async task management and event system")
        print("  • SystemManager - System coordination and service management")
        print("  • FirmwareUpdater - Firmware update system with version control")
        print("  • Build System - Local firmware building and SHA256 verification")
        print()
        print("Next steps:")
        print("1. Install dev dependencies: pip install -r dev-requirements.txt")
        print("2. Run full test suite: pytest")
        print("3. Check coverage: pytest --cov=src --cov-report=html")
        print("4. See TESTING.md for more approaches")
        
    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 