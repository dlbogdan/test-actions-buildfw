"""
Tests for ConfigManager class.
"""
import pytest
import json
import sys
import os
from unittest.mock import patch, mock_open

# Add src to path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.coresys.manager_config import ConfigManager


class TestConfigManager:
    """Test cases for ConfigManager"""
    
    def test_config_manager_singleton(self, temp_config_file):
        """Test that ConfigManager implements singleton pattern correctly."""
        config1 = ConfigManager(temp_config_file)
        config2 = ConfigManager(temp_config_file)
        
        # Should be the same instance
        assert config1 is config2
    
    def test_config_manager_different_files(self, tmp_path):
        """Test that different config files create different instances."""
        config_file1 = tmp_path / "config1.json"
        config_file2 = tmp_path / "config2.json"
        
        config_file1.write_text('{"test": "value1"}')
        config_file2.write_text('{"test": "value2"}')
        
        config1 = ConfigManager(str(config_file1))
        config2 = ConfigManager(str(config_file2))
        
        # Should be different instances
        assert config1 is not config2
    
    def test_load_existing_config(self, temp_config_file):
        """Test loading an existing configuration file."""
        config = ConfigManager(temp_config_file)
        
        # Should load the test data
        assert config.get("SYS.DEVICE", "NAME") == "test-device"
        assert config.get("SYS.WIFI", "SSID") == "test-network"
    
    def test_load_nonexistent_config(self, tmp_path):
        """Test behavior when config file doesn't exist."""
        nonexistent_file = tmp_path / "nonexistent.json"
        config = ConfigManager(str(nonexistent_file))
        
        # Should create empty config
        assert config.config == {}
    
    def test_get_with_default(self, temp_config_file):
        """Test getting values with defaults."""
        config = ConfigManager(temp_config_file)
        
        # Existing value
        assert config.get("SYS.DEVICE", "NAME") == "test-device"
        
        # Non-existing value with default
        default_value = "default-name"
        result = config.get("SYS.DEVICE", "NONEXISTENT", default_value)
        assert result == default_value
        
        # Should have saved the default
        assert config.config["SYS.DEVICE"]["NONEXISTENT"] == default_value
    
    def test_get_without_default_raises_error(self, temp_config_file):
        """Test that getting non-existent value without default raises error."""
        config = ConfigManager(temp_config_file)
        
        with pytest.raises(ValueError, match="Config key.*not found"):
            config.get("NONEXISTENT", "KEY")
    
    def test_set_value(self, temp_config_file):
        """Test setting configuration values."""
        config = ConfigManager(temp_config_file)
        
        # Set a new value
        config.set("TEST", "KEY", "new_value")
        
        # Should be able to retrieve it
        assert config.get("TEST", "KEY") == "new_value"
        
        # Should be in the config dict
        assert config.config["TEST"]["KEY"] == "new_value"
    
    def test_set_value_creates_section(self, temp_config_file):
        """Test that setting a value creates the section if it doesn't exist."""
        config = ConfigManager(temp_config_file)
        
        config.set("NEW_SECTION", "KEY", "value")
        
        assert "NEW_SECTION" in config.config
        assert config.config["NEW_SECTION"]["KEY"] == "value"
    
    def test_observer_pattern(self, temp_config_file):
        """Test the observer pattern for configuration changes."""
        config = ConfigManager(temp_config_file)
        
        # Track callback calls
        callback_calls = []
        
        def test_callback(new_value):
            callback_calls.append(new_value)
        
        # Subscribe to changes
        config.subscribe("TEST.KEY", test_callback)
        
        # Set a value - should trigger callback
        config.set("TEST", "KEY", "value1")
        assert callback_calls == ["value1"]
        
        # Set same value - should not trigger callback
        config.set("TEST", "KEY", "value1")
        assert callback_calls == ["value1"]  # No new calls
        
        # Set different value - should trigger callback
        config.set("TEST", "KEY", "value2")
        assert callback_calls == ["value1", "value2"]
    
    def test_unsubscribe(self, temp_config_file):
        """Test unsubscribing from configuration changes."""
        config = ConfigManager(temp_config_file)
        
        callback_calls = []
        
        def test_callback(new_value):
            callback_calls.append(new_value)
        
        # Subscribe and then unsubscribe
        config.subscribe("TEST.KEY", test_callback)
        config.unsubscribe("TEST.KEY", test_callback)
        
        # Set a value - should not trigger callback
        config.set("TEST", "KEY", "value1")
        assert callback_calls == []
    
    def test_save_config_error_handling(self, tmp_path):
        """Test error handling when saving config fails."""
        # Create a config file in a directory that will be removed
        config_dir = tmp_path / "config_dir"
        config_dir.mkdir()
        config_file = config_dir / "config.json"
        config_file.write_text('{"test": "value"}')
        
        config = ConfigManager(str(config_file))
        
        # Remove the directory to cause save to fail
        import shutil
        shutil.rmtree(str(config_dir))
        
        # Setting a value should handle the save error gracefully
        config.set("TEST", "KEY", "value")
        
        # The value should still be set in memory
        assert config.config["TEST"]["KEY"] == "value"
    
    def test_type_preservation(self, temp_config_file):
        """Test that data types are preserved correctly."""
        config = ConfigManager(temp_config_file)
        
        # Test different data types
        test_values = [
            ("STRING", "test_string"),
            ("INTEGER", 42),
            ("FLOAT", 3.14),
            ("BOOLEAN", True),
            ("LIST", [1, 2, 3]),
            ("DICT", {"nested": "value"})
        ]
        
        for key, value in test_values:
            config.set("TYPES", key, value)
            retrieved = config.get("TYPES", key)
            assert retrieved == value
            assert type(retrieved) == type(value)
    
    @pytest.mark.asyncio
    async def test_config_with_async_context(self, temp_config_file):
        """Test that ConfigManager works in async contexts."""
        import asyncio
        
        config = ConfigManager(temp_config_file)
        
        # Test async operations
        await asyncio.sleep(0.001)  # Simulate async work
        
        config.set("ASYNC", "TEST", "async_value")
        result = config.get("ASYNC", "TEST")
        
        assert result == "async_value"


class TestConfigManagerEdgeCases:
    """Test edge cases and error conditions."""
    
    def test_invalid_json_file(self, tmp_path):
        """Test handling of invalid JSON files."""
        invalid_json_file = tmp_path / "invalid.json"
        invalid_json_file.write_text('{"invalid": json}')  # Invalid JSON
        
        config = ConfigManager(str(invalid_json_file))
        
        # Should create empty config when JSON is invalid
        assert config.config == {}
    
    def test_non_dict_json_file(self, tmp_path):
        """Test handling of JSON files that don't contain a dictionary."""
        non_dict_file = tmp_path / "non_dict.json"
        non_dict_file.write_text('["this", "is", "a", "list"]')
        
        config = ConfigManager(str(non_dict_file))
        
        # Should create empty config when JSON is not a dict
        assert config.config == {}
    
    def test_callback_exception_handling(self, temp_config_file):
        """Test that exceptions in callbacks don't break the system."""
        config = ConfigManager(temp_config_file)
        
        def failing_callback(new_value):
            raise Exception("Callback failed!")
        
        def working_callback(new_value):
            working_callback.called = True
        
        working_callback.called = False
        
        # Subscribe both callbacks
        config.subscribe("TEST.KEY", failing_callback)
        config.subscribe("TEST.KEY", working_callback)
        
        # Set a value - failing callback should not prevent working callback
        config.set("TEST", "KEY", "value")
        
        # Working callback should still be called
        assert working_callback.called
        
        # Value should still be set
        assert config.get("TEST", "KEY") == "value" 