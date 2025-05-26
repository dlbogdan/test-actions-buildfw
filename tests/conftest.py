"""
Pytest configuration for MicroPython testing.
This file automatically sets up mocks for MicroPython modules.
"""
import sys
import pytest
from unittest.mock import patch
from tests.mocks.micropython_mocks import (
    MockUOS, MockMachine, MockNetwork, MockGC, MockUAsyncio,
    MockURequests, MockUTime, MockUJson, MockUsocket
)


@pytest.fixture(autouse=True)
def mock_micropython_modules():
    """Automatically mock all MicroPython modules for every test."""
    
    # Create a dictionary of all the modules we want to mock
    mock_modules = {
        'uos': MockUOS(),
        'machine': MockMachine(),
        'network': MockNetwork(),
        'gc': MockGC(),
        'uasyncio': MockUAsyncio(),
        'urequests': MockURequests(),
        'utime': MockUTime(),
        'ujson': MockUJson(),
        'usocket': MockUsocket(),
        # Also mock the 'u' prefixed versions that might be imported
        'time': MockUTime(),  # Some code might import time instead of utime
    }
    
    # Patch sys.modules to include our mocks
    with patch.dict(sys.modules, mock_modules):
        yield


@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file for testing."""
    config_file = tmp_path / "test_config.json"
    config_data = {
        "SYS": {
            "DEVICE": {
                "NAME": "test-device",
                "MODEL": "test-model"
            },
            "WIFI": {
                "SSID": "test-network",
                "PASS": "test-password"
            },
            "FIRMWARE": {
                "GITHUB_REPO": "test/repo",
                "UPDATE_ON_BOOT": False
            }
        }
    }
    
    import json
    config_file.write_text(json.dumps(config_data, indent=2))
    return str(config_file)


@pytest.fixture
def mock_file_system(tmp_path):
    """Create a mock file system for testing file operations."""
    # Create some test directories and files
    (tmp_path / "lib").mkdir()
    (tmp_path / "lib" / "coresys").mkdir()
    
    # Create a test version file
    version_file = tmp_path / "version.txt"
    version_file.write_text("1.0.0")
    
    return tmp_path


@pytest.fixture
def mock_network_responses():
    """Fixture to provide mock network responses for testing."""
    responses = {
        'github_release': {
            'tag_name': 'v1.1.0',
            'name': 'Test Release',
            'assets': [
                {
                    'name': 'firmware.tar.zlib',
                    'browser_download_url': 'https://example.com/firmware.tar.zlib'
                }
            ]
        },
        'firmware_data': b'mock firmware data'
    }
    return responses


# Configure pytest to handle async tests
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    import asyncio
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close() 