import json
import time
from machine import reset

class Logger: #singleton
    """Manages error logging with minimal flash writes."""
    _instance = None
    _initialized = False  # Flag to ensure __init__ runs only once

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    ERROR_FILE = "lasterror.json"
    LOG_FILE = "log.txt"

    def __init__(self, debug_level=0):
        if self._initialized:
            return  # Already initialized, do nothing
        self._initialized = True

        self._last_error = None
        self._debug_level = debug_level
        self._error_history = []  # Stores the last 3 errors and warnings
        self._error_timestamps = []  # Tracks timestamps of recent errors for rate limiting
        self._max_error_history = 10
        self._error_rate_limit = 3
        self.error_rate_limiter_reached = False
        self._message_server = None # Add placeholder for the server instance
        print(f"Logger initialized with debug level {self._debug_level}")

    def set_message_server(self, server_instance):
        """Injects the MessageServer instance for network logging."""
        self._message_server = server_instance
        if self._message_server:
            print("Logger: MessageServer instance linked.")

    def get_level(self):
        return self._debug_level
    
    def fatal(self, error_type, message, resetmachine:bool):
        """Logs a fatal error to flash. Only writes if different from last error."""
        # Network send first (if configured)
        if self._message_server:
            self._message_server.send(f"FATAL: {error_type} - {message}")
        
        new_error = {
            "timestamp": time.time(),
            "type": error_type,
            "message": message,
        }

        # Only write if error is different from last one
        if self._last_error != new_error:
            try:
                with open(self.ERROR_FILE, 'w') as f:
                    json.dump(new_error, f)
                self._last_error = new_error
            except Exception as e:
                self._log_to_file(f"Failed to write error log: {e}", "ERROR")

        # Log to log.txt
        self._log_to_file(f"FATAL: {error_type} - {message}", "ERROR")
        if resetmachine:
            reset()

    def error(self, message, log_to_file:bool=True):
        """Logs a non-fatal error to log.txt and tracks it for rate limiting."""
        print(f"ERROR: {message}")
        if self._message_server:
            self._message_server.send(f"ERROR: {message}")
        if log_to_file:
            self._log_to_file("ERROR", f"{message}")
        self._track_error_rate()
        self._add_to_history("ERROR", message)

    def warning(self, message, log_to_file:bool=False):
        """Logs a warning message to the history."""
        if self._debug_level>=1:
            print(f"WARNING: {message}")
            if self._message_server:
                 self._message_server.send(f"WARNING: {message}")
        if log_to_file:
            self._log_to_file("WARNING", f"{message}")
        self._add_to_history("WARNING", message)

    def info(self, message, log_to_file:bool=False):
        """Logs an informational message."""
        if self._debug_level>=2:
            print(f"INFO: {message}")
            if self._message_server:
                self._message_server.send(f"INFO: {message}")
        if log_to_file:
            self._log_to_file("INFO", f"{message}")
        #self._add_to_history("INFO", message) 

    def debug(self, message, log_to_file:bool=False):
        """Logs a debug message."""
        if self._debug_level>=3:
            print(f"DEBUG: {message}")
            if self._message_server:
                self._message_server.send(f"DEBUG: {message}")
        if log_to_file:
            self._log_to_file("DEBUG", f"{message}")

    def trace(self, message, log_to_file:bool=False):
        """Logs a trace message."""
        if self._debug_level>=4:
            print(f"TRACE: {message}")
            if self._message_server:
                self._message_server.send(f"TRACE: {message}")
        if log_to_file:
            self._log_to_file("TRACE", f"{message}")


    def _log_to_file(self,level, message):
        """Logs a message to the log file."""
        try:
            with open(self.LOG_FILE, 'a') as f:
                f.write(f"{time.time()} - {level}: {message}\n")
        except Exception as e:
            print(f"Failed to write to log file: {e}")

    def _track_error_rate(self):
        """Tracks the rate of errors and sets the rate limiter flag if exceeded."""
        current_time = time.time()
        self._error_timestamps.append(current_time)

        # Remove timestamps older than 1 minute
        self._error_timestamps = [t for t in self._error_timestamps if current_time - t <= 60]

        # Check if rate limit is exceeded
        if len(self._error_timestamps) > self._error_rate_limit:  # More than 1 error per minute
            self.error_rate_limiter_reached = True
            self._log_to_file("ERROR", f"Error rate limiter triggered: {len(self._error_timestamps)} errors in the last minute")

    def reset_error_rate_limiter(self):
        """Resets the error rate limiter flag."""
        self.error_rate_limiter_reached = False
        self._error_timestamps = []

    def _add_to_history(self, level, message):
        """Adds an error or warning to the history, keeping only the last 3."""
        self._error_history.append({"level": level, "message": message, "timestamp": time.time()})
        if len(self._error_history) > self._max_error_history:
            self._error_history.pop(0)

    def get_last_error(self):
        """Returns the last fatal error if it exists."""
        try:
            with open(self.ERROR_FILE, 'r') as f:
                return json.load(f)
        except:
            return None

    def get_current_log(self):
        """Returns the current log as a string."""
        try:
            with open(self.LOG_FILE, 'r') as f:
                return f.read()
        except:
            return ""

    def get_error_warning_history(self):
        """Returns the last 3 errors and warnings."""
        return self._error_history

    def clear_error_log(self):
        """Clears the error log file."""
        try:
            with open(self.ERROR_FILE, 'w') as f:
                f.write("")
            self._last_error = None
        except Exception as e:
            self._log_to_file(f"Failed to clear error log: {e}", "ERROR")

