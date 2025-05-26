"""
Mock implementations of MicroPython modules for testing in standard Python.
"""
import os
import time
import json
import asyncio
from unittest.mock import Mock, MagicMock
from typing import Any, Dict, List, Optional, Union


# Mock uos module
class MockUOS:
    """Mock implementation of MicroPython's uos module"""
    
    @staticmethod
    def listdir(path='.'):
        return os.listdir(path)
    
    @staticmethod
    def stat(path):
        return os.stat(path)
    
    @staticmethod
    def remove(path):
        return os.remove(path)
    
    @staticmethod
    def rename(old, new):
        return os.rename(old, new)
    
    @staticmethod
    def mkdir(path):
        return os.mkdir(path)
    
    @staticmethod
    def rmdir(path):
        return os.rmdir(path)
    
    @staticmethod
    def getcwd():
        return os.getcwd()
    
    @staticmethod
    def chdir(path):
        return os.chdir(path)


# Mock machine module
class MockPin:
    """Mock implementation of machine.Pin"""
    OUT = 1
    IN = 0
    
    def __init__(self, pin, mode=None, pull=None):
        self.pin = pin
        self.mode = mode
        self.pull = pull
        self._value = 0
    
    def on(self):
        self._value = 1
    
    def off(self):
        self._value = 0
    
    def toggle(self):
        self._value = 1 - self._value
    
    def value(self, val=None):
        if val is not None:
            self._value = val
        return self._value


class MockMachine:
    """Mock implementation of MicroPython's machine module"""
    Pin = MockPin
    
    @staticmethod
    def reset():
        print("Mock: Machine reset called")
    
    @staticmethod
    def freq():
        return 125000000  # Mock frequency
    
    @staticmethod
    def unique_id():
        return b'\x01\x02\x03\x04'


# Mock network module
class MockWLAN:
    """Mock implementation of network.WLAN"""
    STA_IF = 0
    AP_IF = 1
    
    def __init__(self, interface):
        self.interface = interface
        self._active = False
        self._connected = False
        self._config = {}
    
    def active(self, state=None):
        if state is not None:
            self._active = state
        return self._active
    
    def connect(self, ssid, password=None):
        print(f"Mock: Connecting to {ssid}")
        self._connected = True
    
    def disconnect(self):
        self._connected = False
    
    def isconnected(self):
        return self._connected
    
    def ifconfig(self, config=None):
        if config:
            return config
        return ('192.168.1.100', '255.255.255.0', '192.168.1.1', '8.8.8.8')
    
    def config(self, **kwargs):
        self._config.update(kwargs)
        return self._config
    
    def scan(self):
        return [
            (b'TestNetwork', b'\x00\x01\x02\x03\x04\x05', 6, -50, 3, 0),
            (b'AnotherNetwork', b'\x06\x07\x08\x09\x0a\x0b', 11, -60, 4, 0)
        ]


class MockNetwork:
    """Mock implementation of MicroPython's network module"""
    WLAN = MockWLAN


# Mock gc module
class MockGC:
    """Mock implementation of MicroPython's gc module"""
    
    @staticmethod
    def collect():
        print("Mock: Garbage collection triggered")
    
    @staticmethod
    def mem_free():
        return 50000  # Mock free memory
    
    @staticmethod
    def mem_alloc():
        return 10000  # Mock allocated memory


# Mock uasyncio module
class MockTask:
    """Mock asyncio task for testing"""
    def __init__(self, coro):
        self.coro = coro
        self._cancelled = False
        self._done = False
    
    def cancel(self):
        self._cancelled = True
        return True
    
    def cancelled(self):
        return self._cancelled
    
    def done(self):
        return self._done or self._cancelled


class MockUAsyncio:
    """Mock implementation of MicroPython's uasyncio module"""
    
    # Re-export standard asyncio functions as static methods
    @staticmethod
    def sleep(*args, **kwargs):
        return asyncio.sleep(*args, **kwargs)
    
    @staticmethod
    def run(*args, **kwargs):
        return asyncio.run(*args, **kwargs)
    
    @staticmethod
    def create_task(coro, *args, **kwargs):
        """Create a mock task that doesn't require a running event loop"""
        try:
            # Try to use real asyncio if we have a running loop
            return asyncio.create_task(coro, *args, **kwargs)
        except RuntimeError:
            # No running event loop, return a mock task
            return MockTask(coro)
    
    @staticmethod
    def gather(*args, **kwargs):
        return asyncio.gather(*args, **kwargs)
    
    @staticmethod
    def wait_for(*args, **kwargs):
        return asyncio.wait_for(*args, **kwargs)
    
    # Classes
    Event = asyncio.Event
    Lock = asyncio.Lock
    Queue = asyncio.Queue
    Task = MockTask
    
    @staticmethod
    async def sleep_ms(ms):
        await asyncio.sleep(ms / 1000.0)


# Mock urequests module
class MockResponse:
    """Mock HTTP response"""
    
    def __init__(self, status_code=200, text="", json_data=None, headers=None):
        self.status_code = status_code
        self.text = text
        self._json_data = json_data or {}
        self.headers = headers or {}
    
    def json(self):
        return self._json_data
    
    def close(self):
        pass


class MockURequests:
    """Mock implementation of MicroPython's urequests module"""
    
    @staticmethod
    def get(url, headers=None, timeout=None):
        print(f"Mock: GET request to {url}")
        return MockResponse()
    
    @staticmethod
    def post(url, data=None, json=None, headers=None, timeout=None):
        print(f"Mock: POST request to {url}")
        return MockResponse()


# Mock utime module
class MockUTime:
    """Mock implementation of MicroPython's utime module"""
    
    @staticmethod
    def time():
        return int(time.time())
    
    @staticmethod
    def sleep(seconds):
        time.sleep(seconds)
    
    @staticmethod
    def sleep_ms(ms):
        time.sleep(ms / 1000.0)
    
    @staticmethod
    def sleep_us(us):
        time.sleep(us / 1000000.0)
    
    @staticmethod
    def ticks_ms():
        return int(time.time() * 1000)
    
    @staticmethod
    def ticks_us():
        return int(time.time() * 1000000)
    
    @staticmethod
    def ticks_diff(new, old):
        return new - old


# Mock ujson module (just use standard json)
class MockUJson:
    """Mock implementation of MicroPython's ujson module"""
    loads = json.loads
    dumps = json.dumps


# Mock socket module for MicroPython
class MockSocket:
    """Mock socket implementation"""
    AF_INET = 2
    SOCK_STREAM = 1
    SOL_SOCKET = 1
    SO_REUSEADDR = 2
    
    def __init__(self, family=None, type=None):
        self.family = family
        self.type = type
        self._bound = False
        self._listening = False
    
    def bind(self, address):
        self._bound = True
        print(f"Mock: Socket bound to {address}")
    
    def listen(self, backlog=5):
        self._listening = True
        print(f"Mock: Socket listening with backlog {backlog}")
    
    def accept(self):
        mock_client = MockSocket()
        return mock_client, ('127.0.0.1', 12345)
    
    def connect(self, address):
        print(f"Mock: Socket connected to {address}")
    
    def send(self, data):
        return len(data)
    
    def recv(self, bufsize):
        return b"Mock response data"
    
    def close(self):
        print("Mock: Socket closed")
    
    def setsockopt(self, level, optname, value):
        print(f"Mock: Socket option set: {level}, {optname}, {value}")


class MockUsocket:
    """Mock implementation of MicroPython's usocket module"""
    socket = MockSocket
    AF_INET = MockSocket.AF_INET
    SOCK_STREAM = MockSocket.SOCK_STREAM
    SOL_SOCKET = MockSocket.SOL_SOCKET
    SO_REUSEADDR = MockSocket.SO_REUSEADDR


# Mock deflate module for MicroPython compression
class MockDeflate:
    """Mock implementation of MicroPython's deflate module"""
    
    @staticmethod
    def DeflateIO(stream, format=0, wbits=0):
        """Mock deflate decompression"""
        # Return a simple mock that can be read from
        class MockDeflateStream:
            def __init__(self, data):
                self.data = data
                self.pos = 0
            
            def read(self, size=-1):
                if size == -1:
                    result = self.data[self.pos:]
                    self.pos = len(self.data)
                else:
                    result = self.data[self.pos:self.pos + size]
                    self.pos += len(result)
                return result
            
            def close(self):
                pass
        
        # For testing, just return the original stream wrapped
        return MockDeflateStream(b"Mock decompressed data")


# Mock utarfile module for MicroPython tar file handling
class MockTarInfo:
    """Mock tar file info"""
    def __init__(self, name="mock_file.txt", size=100):
        self.name = name
        self.size = size
        self.type = 0  # Regular file


class MockTarFile:
    """Mock tar file implementation"""
    def __init__(self, fileobj=None, mode='r'):
        self.fileobj = fileobj
        self.mode = mode
        self._members = [
            MockTarInfo("main.py", 500),
            MockTarInfo("boot.py", 300),
            MockTarInfo("lib/config.py", 200)
        ]
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
    
    def getmembers(self):
        return self._members
    
    def extractfile(self, member):
        # Return a mock file-like object
        class MockFile:
            def read(self):
                return b"Mock file content"
            def close(self):
                pass
        return MockFile()
    
    def extractall(self, path="."):
        print(f"Mock: Extracting tar to {path}")
    
    def close(self):
        pass


class MockUTarFile:
    """Mock implementation of MicroPython's utarfile module"""
    TarFile = MockTarFile
    TarInfo = MockTarInfo
    
    @staticmethod
    def open(name=None, mode='r', fileobj=None):
        return MockTarFile(fileobj=fileobj, mode=mode)


# Export all mocks
__all__ = [
    'MockUOS', 'MockMachine', 'MockNetwork', 'MockGC', 'MockUAsyncio',
    'MockURequests', 'MockUTime', 'MockUJson', 'MockUsocket', 'MockDeflate', 'MockUTarFile',
    'MockPin', 'MockWLAN', 'MockResponse', 'MockTask', 'MockTarFile', 'MockTarInfo'
] 