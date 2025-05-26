"""
Tests for Logger manager class.
"""
import pytest
import json
import sys
import os
import tempfile
from unittest.mock import patch, mock_open, MagicMock

# Add src to path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.coresys.manager_logger import Logger


class TestLogger:
    """Test cases for Logger manager"""
    
    def setup_method(self):
        """Reset Logger singleton before each test."""
        # Reset the singleton instance
        Logger._instance = None
        Logger._initialized = False
    
    def test_logger_singleton(self):
        """Test that Logger implements singleton pattern correctly."""
        logger1 = Logger(debug_level=1)
        logger2 = Logger(debug_level=2)
        
        # Should be the same instance
        assert logger1 is logger2
        # Debug level should remain from first initialization
        assert logger1.get_level() == 1
    
    def test_logger_initialization_with_debug_level(self):
        """Test logger initialization with different debug levels."""
        logger = Logger(debug_level=3)
        assert logger.get_level() == 3
        assert logger._initialized is True
    
    def test_logger_initialization_without_debug_level(self, capsys):
        """Test logger initialization without debug level uses default."""
        logger = Logger()
        captured = capsys.readouterr()
        
        assert logger.get_level() == 0
        assert "No debug level provided, using default 0" in captured.out
        assert "Logger initialized with debug level 0" in captured.out
    
    def test_set_message_server(self, capsys):
        """Test setting message server for network logging."""
        logger = Logger()
        mock_server = MagicMock()
        
        logger.set_message_server(mock_server)
        captured = capsys.readouterr()
        
        assert logger._message_server is mock_server
        assert "MessageServer instance linked" in captured.out
    
    def test_set_message_server_none(self):
        """Test setting None message server."""
        logger = Logger()
        logger.set_message_server(None)
        assert logger._message_server is None
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_fatal_error_new_error(self, mock_json_dump, mock_file, capsys):
        """Test fatal error logging with new error."""
        logger = Logger()
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        with patch('time.time', return_value=1234567890):
            with patch('machine.reset') as mock_reset:
                logger.fatal("TestError", "Test fatal message", resetmachine=True)
        
        # Check network message was sent
        mock_server.send.assert_called_once_with("FATAL: TestError - Test fatal message")
        
        # Check file was written
        mock_file.assert_called_with(Logger.ERROR_FILE, 'w')
        expected_error = {
            "timestamp": 1234567890,
            "type": "TestError",
            "message": "Test fatal message"
        }
        mock_json_dump.assert_called_once_with(expected_error, mock_file())
        
        # Check machine reset was called
        mock_reset.assert_called_once()
        
        # Check last error was stored
        assert logger._last_error == expected_error
    
    @patch('builtins.open', new_callable=mock_open)
    @patch('json.dump')
    def test_fatal_error_same_error_not_written(self, mock_json_dump, mock_file):
        """Test that same fatal error is not written twice."""
        logger = Logger()
        
        # Set up existing error
        existing_error = {
            "timestamp": 1234567890,
            "type": "TestError",
            "message": "Test fatal message"
        }
        logger._last_error = existing_error
        
        with patch('time.time', return_value=1234567890):
            with patch('machine.reset'):
                logger.fatal("TestError", "Test fatal message", resetmachine=False)
        
        # File should not be written since error is the same
        mock_json_dump.assert_not_called()
    
    @patch('builtins.open', side_effect=OSError("File write failed"))
    def test_fatal_error_file_write_failure(self, mock_file, capsys):
        """Test fatal error handling when file write fails."""
        logger = Logger()
        
        with patch('time.time', return_value=1234567890):
            with patch('machine.reset'):
                logger.fatal("TestError", "Test message", resetmachine=False)
        
        captured = capsys.readouterr()
        # Should log the file write failure
        assert "Failed to write error log" in captured.out
    
    def test_error_logging(self, capsys):
        """Test error logging functionality."""
        logger = Logger()
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        with patch.object(logger, '_log_to_file') as mock_log_file:
            with patch.object(logger, '_track_error_rate') as mock_track:
                with patch.object(logger, '_add_to_history') as mock_history:
                    logger.error("Test error message")
        
        captured = capsys.readouterr()
        assert "ERROR: Test error message" in captured.out
        
        # Check network message
        mock_server.send.assert_called_once_with("ERROR: Test error message")
        
        # Check file logging
        mock_log_file.assert_called_once_with("ERROR", "Test error message")
        
        # Check error tracking
        mock_track.assert_called_once()
        mock_history.assert_called_once_with("ERROR", "Test error message")
    
    def test_error_logging_no_file(self, capsys):
        """Test error logging without file logging."""
        logger = Logger()
        
        with patch.object(logger, '_log_to_file') as mock_log_file:
            logger.error("Test error", log_to_file=False)
        
        captured = capsys.readouterr()
        assert "ERROR: Test error" in captured.out
        mock_log_file.assert_not_called()
    
    def test_warning_logging_debug_level_0(self, capsys):
        """Test warning logging with debug level 0 (should not print)."""
        logger = Logger(debug_level=0)
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        with patch.object(logger, '_add_to_history') as mock_history:
            logger.warning("Test warning")
        
        captured = capsys.readouterr()
        # Should not print at debug level 0
        assert "WARNING: Test warning" not in captured.out
        
        # Should not send network message at debug level 0
        mock_server.send.assert_not_called()
        
        # Should still add to history
        mock_history.assert_called_once_with("WARNING", "Test warning")
    
    def test_warning_logging_debug_level_1(self, capsys):
        """Test warning logging with debug level 1 (should print)."""
        logger = Logger(debug_level=1)
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        logger.warning("Test warning")
        
        captured = capsys.readouterr()
        assert "WARNING: Test warning" in captured.out
        mock_server.send.assert_called_once_with("WARNING: Test warning")
    
    def test_info_logging_debug_levels(self, capsys):
        """Test info logging at different debug levels."""
        # Debug level 1 - should not print
        logger = Logger(debug_level=1)
        logger.info("Test info level 1")
        captured = capsys.readouterr()
        assert "INFO: Test info level 1" not in captured.out
        
        # Reset singleton for new debug level
        Logger._instance = None
        Logger._initialized = False
        
        # Debug level 2 - should print
        logger = Logger(debug_level=2)
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        logger.info("Test info level 2")
        captured = capsys.readouterr()
        assert "INFO: Test info level 2" in captured.out
        mock_server.send.assert_called_once_with("INFO: Test info level 2")
    
    def test_debug_logging_debug_levels(self, capsys):
        """Test debug logging at different debug levels."""
        # Debug level 2 - should not print
        logger = Logger(debug_level=2)
        logger.debug("Test debug level 2")
        captured = capsys.readouterr()
        assert "DEBUG: Test debug level 2" not in captured.out
        
        # Reset singleton for new debug level
        Logger._instance = None
        Logger._initialized = False
        
        # Debug level 3 - should print
        logger = Logger(debug_level=3)
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        logger.debug("Test debug level 3")
        captured = capsys.readouterr()
        assert "DEBUG: Test debug level 3" in captured.out
        mock_server.send.assert_called_once_with("DEBUG: Test debug level 3")
    
    def test_trace_logging_debug_levels(self, capsys):
        """Test trace logging at different debug levels."""
        # Debug level 3 - should not print
        logger = Logger(debug_level=3)
        logger.trace("Test trace level 3")
        captured = capsys.readouterr()
        assert "TRACE: Test trace level 3" not in captured.out
        
        # Reset singleton for new debug level
        Logger._instance = None
        Logger._initialized = False
        
        # Debug level 4 - should print
        logger = Logger(debug_level=4)
        mock_server = MagicMock()
        logger.set_message_server(mock_server)
        
        logger.trace("Test trace level 4")
        captured = capsys.readouterr()
        assert "TRACE: Test trace level 4" in captured.out
        mock_server.send.assert_called_once_with("TRACE: Test trace level 4")
    
    @patch('builtins.open', new_callable=mock_open)
    def test_log_to_file_success(self, mock_file):
        """Test successful file logging."""
        logger = Logger()
        
        with patch('time.time', return_value=1234567890):
            logger._log_to_file("INFO", "Test message")
        
        mock_file.assert_called_once_with(Logger.LOG_FILE, 'a')
        mock_file().write.assert_called_once_with("1234567890 - INFO: Test message\n")
    
    @patch('builtins.open', side_effect=OSError("File write failed"))
    def test_log_to_file_failure(self, mock_file, capsys):
        """Test file logging failure handling."""
        logger = Logger()
        
        logger._log_to_file("ERROR", "Test message")
        
        captured = capsys.readouterr()
        assert "Failed to write to log file" in captured.out
    
    def test_track_error_rate_normal(self):
        """Test error rate tracking under normal conditions."""
        logger = Logger()
        
        with patch('time.time', return_value=1000):
            logger._track_error_rate()
            logger._track_error_rate()
            logger._track_error_rate()
        
        # Should not trigger rate limiter with 3 errors
        assert not logger.error_rate_limiter_reached
        assert len(logger._error_timestamps) == 3
    
    def test_track_error_rate_exceeded(self):
        """Test error rate tracking when limit is exceeded."""
        logger = Logger()
        
        with patch('time.time', return_value=1000):
            # Add 4 errors (exceeds limit of 3)
            for _ in range(4):
                logger._track_error_rate()
        
        # Should trigger rate limiter
        assert logger.error_rate_limiter_reached
    
    def test_track_error_rate_old_timestamps_removed(self):
        """Test that old error timestamps are removed."""
        logger = Logger()
        
        # Add errors at different times
        with patch('time.time', return_value=1000):
            logger._track_error_rate()
        
        with patch('time.time', return_value=1030):  # 30 seconds later
            logger._track_error_rate()
        
        with patch('time.time', return_value=1070):  # 70 seconds from first (>60s)
            logger._track_error_rate()
        
        # Should only have 2 recent timestamps (1030 and 1070)
        assert len(logger._error_timestamps) == 2
        assert 1000 not in logger._error_timestamps
    
    def test_reset_error_rate_limiter(self):
        """Test resetting the error rate limiter."""
        logger = Logger()
        
        # Trigger rate limiter
        logger.error_rate_limiter_reached = True
        logger._error_timestamps = [1000, 1010, 1020, 1030]
        
        logger.reset_error_rate_limiter()
        
        assert not logger.error_rate_limiter_reached
        assert logger._error_timestamps == []
    
    def test_add_to_history(self):
        """Test adding messages to error history."""
        logger = Logger()
        
        with patch('time.time', return_value=1234567890):
            logger._add_to_history("ERROR", "Test error 1")
            logger._add_to_history("WARNING", "Test warning 1")
        
        history = logger.get_error_warning_history()
        assert len(history) == 2
        assert history[0]["level"] == "ERROR"
        assert history[0]["message"] == "Test error 1"
        assert history[0]["timestamp"] == 1234567890
        assert history[1]["level"] == "WARNING"
        assert history[1]["message"] == "Test warning 1"
    
    def test_add_to_history_max_limit(self):
        """Test that error history respects maximum limit."""
        logger = Logger()
        
        # Add more than max history items
        for i in range(15):  # More than _max_error_history (10)
            logger._add_to_history("ERROR", f"Error {i}")
        
        history = logger.get_error_warning_history()
        assert len(history) == logger._max_error_history
        # Should keep the most recent ones
        assert history[-1]["message"] == "Error 14"
        assert history[0]["message"] == "Error 5"  # Oldest kept
    
    @patch('builtins.open', new_callable=mock_open, read_data='{"type": "TestError", "message": "Test message", "timestamp": 1234567890}')
    @patch('json.load')
    def test_get_last_error_success(self, mock_json_load, mock_file):
        """Test getting last error successfully."""
        logger = Logger()
        expected_error = {"type": "TestError", "message": "Test message", "timestamp": 1234567890}
        mock_json_load.return_value = expected_error
        
        result = logger.get_last_error()
        
        mock_file.assert_called_once_with(Logger.ERROR_FILE, 'r')
        mock_json_load.assert_called_once()
        assert result == expected_error
    
    @patch('builtins.open', side_effect=OSError("File not found"))
    def test_get_last_error_file_not_found(self, mock_file):
        """Test getting last error when file doesn't exist."""
        logger = Logger()
        
        result = logger.get_last_error()
        
        assert result is None
    
    @patch('builtins.open', new_callable=mock_open, read_data='Log line 1\nLog line 2\nLog line 3\n')
    def test_get_current_log_success(self, mock_file):
        """Test getting current log successfully."""
        logger = Logger()
        
        result = logger.get_current_log()
        
        mock_file.assert_called_once_with(Logger.LOG_FILE, 'r')
        assert result == 'Log line 1\nLog line 2\nLog line 3\n'
    
    @patch('builtins.open', side_effect=OSError("File not found"))
    def test_get_current_log_file_not_found(self, mock_file):
        """Test getting current log when file doesn't exist."""
        logger = Logger()
        
        result = logger.get_current_log()
        
        assert result == ""
    
    @patch('builtins.open', new_callable=mock_open)
    def test_clear_error_log_success(self, mock_file):
        """Test clearing error log successfully."""
        logger = Logger()
        logger._last_error = {"type": "TestError", "message": "Test"}
        
        logger.clear_error_log()
        
        mock_file.assert_called_once_with(Logger.ERROR_FILE, 'w')
        mock_file().write.assert_called_once_with("")
        assert logger._last_error is None
    
    @patch('builtins.open', side_effect=OSError("File write failed"))
    def test_clear_error_log_failure(self, mock_file):
        """Test clearing error log when write fails."""
        logger = Logger()
        
        with patch.object(logger, '_log_to_file') as mock_log_file:
            logger.clear_error_log()
        
        # Should log the failure
        mock_log_file.assert_called_once()
        assert "Failed to clear error log" in str(mock_log_file.call_args)


class TestLoggerIntegration:
    """Integration tests for Logger functionality."""
    
    def setup_method(self):
        """Reset Logger singleton before each test."""
        Logger._instance = None
        Logger._initialized = False
    
    def test_complete_error_workflow(self, tmp_path):
        """Test complete error logging workflow."""
        # Use temporary files
        error_file = tmp_path / "test_error.json"
        log_file = tmp_path / "test_log.txt"
        
        logger = Logger(debug_level=2)
        logger.ERROR_FILE = str(error_file)
        logger.LOG_FILE = str(log_file)
        
        # Test various logging levels
        logger.error("Test error message")
        logger.warning("Test warning message")
        logger.info("Test info message")
        
        # Check log file was created and contains entries
        assert log_file.exists()
        log_content = log_file.read_text()
        assert "ERROR: Test error message" in log_content
        assert "WARNING: Test warning message" in log_content
        assert "INFO: Test info message" in log_content
        
        # Check error history
        history = logger.get_error_warning_history()
        assert len(history) == 2  # Error and warning (info not added to history)
        assert any(h["level"] == "ERROR" for h in history)
        assert any(h["level"] == "WARNING" for h in history)
    
    @pytest.mark.asyncio
    async def test_logger_with_async_context(self):
        """Test that Logger works in async contexts."""
        import asyncio
        
        logger = Logger(debug_level=3)
        
        # Test async operations
        await asyncio.sleep(0.001)
        
        logger.debug("Async debug message")
        logger.info("Async info message")
        
        # Should work without issues
        assert logger.get_level() == 3 