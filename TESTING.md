# Testing MicroPython Firmware

This document explains how to test MicroPython code that isn't directly compatible with standard Python.

## The Challenge

MicroPython uses different modules (`uos`, `machine`, `uasyncio`, etc.) that don't exist in standard Python, making traditional testing difficult. Here are several approaches to solve this:

## Approach 1: Mock-based Testing (Recommended for CI/CD)

This approach uses mocks to simulate MicroPython modules in standard Python.

### Setup

1. **Install development dependencies:**
   ```bash
   pip install -r dev-requirements.txt
   ```

2. **Run tests:**
   ```bash
   # Run all tests
   pytest

   # Run with coverage
   pytest --cov=src --cov-report=html

   # Run only unit tests
   pytest -m unit

   # Run tests in parallel
   pytest -n auto
   ```

### How it works

- **Automatic mocking**: `tests/conftest.py` automatically mocks all MicroPython modules
- **Comprehensive mocks**: `tests/mocks/micropython_mocks.py` provides realistic implementations
- **Test fixtures**: Pre-configured test data and temporary files

### Example Test

```python
def test_config_manager(temp_config_file):
    """Test ConfigManager with mocked MicroPython modules."""
    config = ConfigManager(temp_config_file)
    
    # This works because uos is mocked automatically
    config.set("WIFI", "SSID", "test-network")
    assert config.get("WIFI", "SSID") == "test-network"
```

### Pros
- ✅ Fast execution
- ✅ Works in CI/CD
- ✅ No hardware required
- ✅ Easy to mock network/hardware interactions
- ✅ Good for unit testing

### Cons
- ❌ Mocks might not perfectly match MicroPython behavior
- ❌ Can't test hardware-specific code
- ❌ Requires maintaining mock implementations

## Approach 2: MicroPython Unix Port

Run tests directly in MicroPython using the Unix port.

### Setup

1. **Install MicroPython Unix port:**
   ```bash
   # On Ubuntu/Debian
   sudo apt-get install micropython

   # On macOS with Homebrew
   brew install micropython

   # Or build from source
   git clone https://github.com/micropython/micropython.git
   cd micropython/ports/unix
   make
   ```

2. **Create MicroPython test runner:**
   ```python
   # tests/micropython_runner.py
   import sys
   import os

   # Add src to path
   sys.path.insert(0, 'src')

   # Import and run tests
   from lib.coresys.manager_config import ConfigManager

   def test_config_basic():
       config = ConfigManager("/tmp/test_config.json")
       config.set("TEST", "KEY", "value")
       assert config.get("TEST", "KEY") == "value"
       print("✓ Config test passed")

   if __name__ == "__main__":
       test_config_basic()
   ```

3. **Run tests:**
   ```bash
   micropython tests/micropython_runner.py
   ```

### Pros
- ✅ Real MicroPython environment
- ✅ Exact behavior matching
- ✅ Can test most MicroPython-specific features

### Cons
- ❌ No hardware simulation (machine.Pin, etc.)
- ❌ Limited testing framework features
- ❌ Harder to set up in CI/CD

## Approach 3: Hardware-in-the-Loop Testing

Test on actual hardware or emulators.

### Setup with Raspberry Pi Pico

1. **Install development tools:**
   ```bash
   pip install mpremote thonny
   ```

2. **Create hardware test script:**
   ```python
   # tests/hardware_tests.py
   import machine
   import time
   from lib.coresys.manager_config import ConfigManager

   def test_led_toggle():
       led = machine.Pin('LED', machine.Pin.OUT)
       led.on()
       time.sleep(0.1)
       led.off()
       print("✓ LED test passed")

   def test_config_on_device():
       config = ConfigManager("/config.json")
       config.set("TEST", "HARDWARE", True)
       assert config.get("TEST", "HARDWARE") == True
       print("✓ Hardware config test passed")

   if __name__ == "__main__":
       test_led_toggle()
       test_config_on_device()
   ```

3. **Run on device:**
   ```bash
   # Copy test to device and run
   mpremote cp tests/hardware_tests.py :
   mpremote exec "import hardware_tests"
   ```

### Pros
- ✅ Real hardware testing
- ✅ Tests actual device behavior
- ✅ Can test hardware-specific features

### Cons
- ❌ Slow execution
- ❌ Requires physical hardware
- ❌ Hard to automate
- ❌ Limited debugging capabilities

## Approach 4: Emulation with QEMU

Use QEMU to emulate MicroPython devices.

### Setup

1. **Install QEMU and build MicroPython for emulation:**
   ```bash
   # Install QEMU
   sudo apt-get install qemu-system-arm

   # Build MicroPython for QEMU
   git clone https://github.com/micropython/micropython.git
   cd micropython/ports/qemu-arm
   make
   ```

2. **Run tests in emulator:**
   ```bash
   # Copy your code to the emulator filesystem
   # Run emulated MicroPython
   qemu-system-arm -M versatilepb -nographic -kernel build/firmware.elf
   ```

### Pros
- ✅ Real MicroPython environment
- ✅ Reproducible
- ✅ Can simulate hardware to some extent

### Cons
- ❌ Complex setup
- ❌ Limited hardware simulation
- ❌ Slow execution

## Approach 5: Hybrid Testing Strategy (Recommended)

Combine multiple approaches for comprehensive testing:

```bash
# 1. Fast unit tests with mocks (for development)
pytest tests/test_*.py -m unit

# 2. Integration tests with MicroPython Unix port
micropython tests/integration_tests.py

# 3. Hardware tests on actual device (for releases)
mpremote exec tests/hardware_tests.py

# 4. Build system tests (standard Python)
pytest tests/test_build_system.py
```

## Test Organization

```
tests/
├── conftest.py              # Pytest configuration and fixtures
├── mocks/                   # MicroPython mocks
│   ├── __init__.py
│   └── micropython_mocks.py
├── unit/                    # Unit tests with mocks
│   ├── test_config_manager.py
│   ├── test_logger.py
│   └── test_wifi_manager.py
├── integration/             # Integration tests
│   ├── test_system_manager.py
│   └── test_firmware_update.py
├── hardware/                # Hardware-specific tests
│   ├── test_gpio.py
│   └── test_sensors.py
└── build/                   # Build system tests
    ├── test_local_builder.py
    └── test_firmware_server.py
```

## Continuous Integration

Add to your GitHub Actions workflow:

```yaml
# .github/workflows/test.yml
name: Test

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r dev-requirements.txt
      
      - name: Run unit tests
        run: |
          pytest tests/unit/ --cov=src --cov-report=xml
      
      - name: Install MicroPython
        run: |
          sudo apt-get update
          sudo apt-get install micropython
      
      - name: Run MicroPython integration tests
        run: |
          micropython tests/integration/micropython_runner.py
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Best Practices

1. **Start with mocked unit tests** for fast development
2. **Use MicroPython Unix port** for integration testing
3. **Test on real hardware** before releases
4. **Mock external dependencies** (network, sensors) consistently
5. **Use fixtures** for common test data and setup
6. **Test error conditions** and edge cases
7. **Keep tests fast** and independent

## Debugging Tips

1. **Use print statements** liberally in MicroPython tests
2. **Test incrementally** - start with simple functions
3. **Mock network calls** to avoid external dependencies
4. **Use temporary files** for file system tests
5. **Test async code** with proper event loop handling

This multi-layered approach gives you confidence that your code works correctly across different environments while maintaining fast development cycles. 