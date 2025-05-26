# Development Setup for MicroPython Firmware

This guide will help you set up a complete development environment for testing and developing MicroPython firmware.

## Quick Start

1. **Clone and setup:**
   ```bash
   git clone <your-repo>
   cd test-actions-buildfw
   pip install -r dev-requirements.txt
   ```

2. **Run the demonstration:**
   ```bash
   python run_tests.py
   ```

3. **Run full test suite:**
   ```bash
   pytest
   ```

## The Testing Challenge

MicroPython uses modules like `uos`, `machine`, `uasyncio` that don't exist in standard Python. This project solves that with **comprehensive mocking** that makes MicroPython code testable in standard Python environments.

## What We've Built

### 🧪 Mock-based Testing System

**Files created:**
- `tests/mocks/micropython_mocks.py` - Complete MicroPython module mocks
- `tests/conftest.py` - Automatic mock setup for pytest
- `tests/test_config_manager.py` - Example comprehensive tests
- `pytest.ini` - Test configuration

**What it does:**
- Automatically mocks all MicroPython modules (`uos`, `machine`, `network`, etc.)
- Provides realistic behavior simulation
- Enables fast unit testing in CI/CD
- Supports async testing with `uasyncio`

### 🔨 Build System Testing

**Files created:**
- `tests/test_build_system.py` - Tests for Python build tools
- Integration with existing `local_builder.py`

**What it tests:**
- Firmware compilation process
- SHA256 integrity checking
- Version management
- Archive creation and compression

### 🚀 Development Tools

**Files created:**
- `dev-requirements.txt` - Development dependencies
- `run_tests.py` - Interactive demonstration script
- `.github/workflows/test.yml` - CI/CD pipeline
- `TESTING.md` - Comprehensive testing guide

## How It Works

### 1. Automatic Mocking

When you run tests, `conftest.py` automatically patches `sys.modules`:

```python
# This MicroPython code now works in standard Python!
import machine
import uos
import gc

led = machine.Pin('LED', machine.Pin.OUT)  # Uses MockPin
led.toggle()  # Works perfectly

files = uos.listdir('/')  # Uses MockUOS
gc.collect()  # Uses MockGC
```

### 2. Realistic Behavior

The mocks aren't just stubs - they provide realistic behavior:

```python
# Network simulation
wlan = network.WLAN(network.WLAN.STA_IF)
wlan.active(True)
wlan.connect("MyNetwork", "password")
assert wlan.isconnected()  # Returns True

# GPIO simulation
pin = machine.Pin(2, machine.Pin.OUT)
pin.on()
assert pin.value() == 1
pin.toggle()
assert pin.value() == 0
```

### 3. Test Organization

```
tests/
├── conftest.py              # Auto-mock setup
├── mocks/                   # Mock implementations
├── test_config_manager.py   # Example unit tests
├── test_build_system.py     # Build system tests
└── run_tests.py            # Demo script
```

## Running Tests

### Unit Tests (Fast - for development)
```bash
# Run all tests
pytest

# With coverage
pytest --cov=src --cov-report=html

# Only unit tests
pytest -m unit

# Watch mode for development
pytest-watch
```

### Integration Tests
```bash
# Test with actual MicroPython
micropython -c "import sys; sys.path.append('src'); from lib.coresys.manager_config import ConfigManager"

# Run demonstration
python run_tests.py
```

### Build System Tests
```bash
# Test firmware building
pytest tests/test_build_system.py

# Test actual build
python local_builder.py --version v1.0.0-test
```

## Example Test

Here's how easy it is to test MicroPython code now:

```python
def test_config_manager_with_hardware_simulation(temp_config_file):
    """Test configuration with simulated hardware."""
    # This imports MicroPython modules that are automatically mocked
    from lib.coresys.manager_config import ConfigManager
    import machine
    import gc
    
    # Test configuration
    config = ConfigManager(temp_config_file)
    config.set("HARDWARE", "LED_PIN", 25)
    
    # Test hardware simulation
    led_pin = config.get("HARDWARE", "LED_PIN")
    led = machine.Pin(led_pin, machine.Pin.OUT)
    led.on()
    
    # Test memory management
    gc.collect()
    free_mem = gc.mem_free()
    
    # All of this works in standard Python!
    assert led.value() == 1
    assert free_mem > 0
```

## CI/CD Integration

The GitHub Actions workflow (`.github/workflows/test.yml`) runs:

1. **Linting** - Code quality checks
2. **Unit tests** - Fast mock-based tests
3. **MicroPython compatibility** - Real MicroPython import tests
4. **Build verification** - Test firmware building
5. **Coverage reporting** - Track test coverage

## Development Workflow

### 1. Write Code
```python
# src/lib/coresys/my_new_module.py
import uos
import machine

def my_function():
    files = uos.listdir('/')
    led = machine.Pin('LED', machine.Pin.OUT)
    return len(files)
```

### 2. Write Tests
```python
# tests/test_my_new_module.py
def test_my_function():
    # MicroPython modules are automatically mocked
    from lib.coresys.my_new_module import my_function
    
    result = my_function()
    assert isinstance(result, int)
```

### 3. Run Tests
```bash
pytest tests/test_my_new_module.py -v
```

### 4. Check Coverage
```bash
pytest --cov=src --cov-report=html
open htmlcov/index.html
```

## Advanced Features

### Async Testing
```python
@pytest.mark.asyncio
async def test_async_function():
    import uasyncio as asyncio
    
    await asyncio.sleep(0.1)  # Uses standard asyncio
    # Test your async MicroPython code here
```

### Network Mocking
```python
def test_network_functionality(mock_network_responses):
    import urequests
    
    # HTTP requests are automatically mocked
    response = urequests.get("https://api.github.com/releases")
    assert response.status_code == 200
```

### Hardware Simulation
```python
def test_gpio_operations():
    import machine
    
    # Create multiple pins
    pins = [machine.Pin(i, machine.Pin.OUT) for i in range(5)]
    
    # Test pin operations
    for pin in pins:
        pin.on()
        assert pin.value() == 1
```

## Benefits

✅ **Fast Development** - No hardware needed for most testing
✅ **CI/CD Ready** - Runs in GitHub Actions out of the box  
✅ **Comprehensive** - Tests both MicroPython and Python code
✅ **Realistic** - Mocks behave like real MicroPython modules
✅ **Maintainable** - Easy to extend and modify
✅ **Educational** - Clear examples and documentation

## Next Steps

1. **Extend mocks** - Add more MicroPython modules as needed
2. **Add hardware tests** - Use real devices for final validation
3. **Performance testing** - Add benchmarks for critical code
4. **Documentation** - Generate API docs from tests
5. **Integration** - Connect with hardware-in-the-loop testing

This setup gives you the best of both worlds: fast development with mocks and confidence through real hardware testing when needed! 