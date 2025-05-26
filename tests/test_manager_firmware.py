"""
Tests for FirmwareUpdater class.
"""
import pytest
import asyncio
import sys
import os
import tempfile
import json
from unittest.mock import patch, MagicMock, AsyncMock, mock_open

# Add src to path so we can import the modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from lib.coresys.manager_firmware import FirmwareUpdater


class TestFirmwareUpdater:
    """Test cases for FirmwareUpdater class"""
    
    def setup_method(self):
        """Set up fresh FirmwareUpdater for each test."""
        self.updater = FirmwareUpdater(
            device_model="test-device",
            github_repo="test/repo",
            github_token="test-token",
            chunk_size=1024,
            max_redirects=5,
            update_on_boot=True,
            max_failure_attempts=3
        )
    
    def test_firmware_updater_initialization_github_mode(self):
        """Test FirmwareUpdater initialization in GitHub mode."""
        updater = FirmwareUpdater(
            device_model="test-device",
            github_repo="test/repo",
            github_token="test-token"
        )
        
        assert updater.device_model == "test-device"
        assert updater.github_repo == "test/repo"
        assert updater.github_token == "test-token"
        assert not updater.is_direct_mode
        assert updater.base_url == "https://api.github.com/repos/test/repo/releases/latest"
        assert updater.chunk_size == 2048  # Default
        assert updater.max_redirects == 10  # Default
    
    def test_firmware_updater_initialization_direct_mode(self):
        """Test FirmwareUpdater initialization in direct mode."""
        updater = FirmwareUpdater(
            device_model="test-device",
            direct_base_url="https://firmware.example.com"
        )
        
        assert updater.device_model == "test-device"
        assert updater.is_direct_mode
        assert updater.direct_base_url == "https://firmware.example.com/"
        assert updater.metadata_url == "https://firmware.example.com/metadata.json"
    
    def test_firmware_updater_initialization_no_repo_or_url(self):
        """Test FirmwareUpdater initialization without repo or URL raises error."""
        with pytest.raises(ValueError, match="Either github_repo or direct_base_url must be provided"):
            FirmwareUpdater(device_model="test-device")
    
    @patch('builtins.open', new_callable=mock_open, read_data='1.2.3')
    def test_read_version_success(self, mock_file):
        """Test reading version from file successfully."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        
        version = updater._read_version()
        
        assert version == "1.2.3"
        mock_file.assert_called_once_with('/version.txt', 'r')
    
    @patch('builtins.open', side_effect=OSError("File not found"))
    def test_read_version_file_not_found(self, mock_file):
        """Test reading version when file doesn't exist."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        
        version = updater._read_version()
        
        assert version == "0.0.0"
    
    def test_parse_semver_valid(self):
        """Test parsing valid semantic version strings."""
        updater = self.updater
        
        assert updater._parse_semver("1.2.3") == (1, 2, 3)
        assert updater._parse_semver("0.0.1") == (0, 0, 1)
        assert updater._parse_semver("10.20.30") == (10, 20, 30)
    
    def test_parse_semver_invalid(self):
        """Test parsing invalid semantic version strings."""
        updater = self.updater
        
        with pytest.raises(ValueError, match="Invalid version format"):
            updater._parse_semver("1.2")
        
        with pytest.raises(ValueError, match="Invalid version format"):
            updater._parse_semver("1.2.3.4")
        
        with pytest.raises(ValueError, match="Invalid version format"):
            updater._parse_semver("a.b.c")
    
    def test_parse_url_valid_https(self):
        """Test parsing valid HTTPS URLs."""
        updater = self.updater
        
        host, port, path = updater._parse_url("https://api.github.com/repos/test/repo")
        assert host == "api.github.com"
        assert port == 443
        assert path == "/repos/test/repo"
        
        host, port, path = updater._parse_url("https://example.com:8443/path/to/resource")
        assert host == "example.com"
        assert port == 8443
        assert path == "/path/to/resource"
        
        host, port, path = updater._parse_url("https://example.com")
        assert host == "example.com"
        assert port == 443
        assert path == "/"
    
    def test_parse_url_invalid(self):
        """Test parsing invalid URLs."""
        updater = self.updater
        
        with pytest.raises(ValueError, match="Invalid or non-HTTPS URL"):
            updater._parse_url("http://example.com")
        
        with pytest.raises(ValueError, match="Invalid or non-HTTPS URL"):
            updater._parse_url("ftp://example.com")
        
        with pytest.raises(ValueError, match="Could not extract host from URL"):
            updater._parse_url("https:///path")
        
        with pytest.raises(ValueError):
            updater._parse_url("https://example.com:invalid_port/path")
    
    def test_compare_versions_newer_available(self):
        """Test version comparison when newer version is available."""
        updater = self.updater
        updater.current_version = "1.0.0"
        
        result = updater._compare_versions("1.1.0")
        assert result is True
        
        result = updater._compare_versions("2.0.0")
        assert result is True
        
        result = updater._compare_versions("1.0.1")
        assert result is True
    
    def test_compare_versions_same_or_older(self):
        """Test version comparison when same or older version."""
        updater = self.updater
        updater.current_version = "1.1.0"
        
        result = updater._compare_versions("1.1.0")
        assert result is False
        
        result = updater._compare_versions("1.0.0")
        assert result is False
        
        result = updater._compare_versions("0.9.0")
        assert result is False
    
    def test_compare_versions_invalid_format(self):
        """Test version comparison with invalid version format."""
        updater = self.updater
        updater.current_version = "1.0.0"
        
        with pytest.raises(ValueError, match="Invalid version format"):
            updater._compare_versions("invalid.version")
    
    def test_percent_complete_calculation(self):
        """Test download progress percentage calculation."""
        updater = self.updater
        
        # No download started
        assert updater.percent_complete() == 0
        
        # Download in progress
        updater.total_size = 1000
        updater.bytes_read = 250
        assert updater.percent_complete() == 25
        
        updater.bytes_read = 500
        assert updater.percent_complete() == 50
        
        updater.bytes_read = 1000
        assert updater.percent_complete() == 100
        
        # Edge case: total_size is 0
        updater.total_size = 0
        assert updater.percent_complete() == 0
    
    def test_is_download_done(self):
        """Test download completion status."""
        updater = self.updater
        
        assert not updater.is_download_done()
        
        updater.download_done = True
        assert updater.is_download_done()
    
    @patch('builtins.open', new_callable=mock_open)
    def test_check_applying_flag_exists(self, mock_file):
        """Test checking if applying flag file exists."""
        updater = self.updater
        
        # File exists
        result = updater.check_applying_flag_exists()
        assert result is True
        mock_file.assert_called_once_with(updater.applying_flag_path, 'r')
    
    @patch('builtins.open', side_effect=OSError("File not found"))
    def test_check_applying_flag_not_exists(self, mock_file):
        """Test checking applying flag when file doesn't exist."""
        updater = self.updater
        
        result = updater.check_applying_flag_exists()
        assert result is False
    
    @patch('uos.remove')
    def test_remove_applying_flag_success(self, mock_remove):
        """Test removing applying flag successfully."""
        updater = self.updater
        
        updater.remove_applying_flag()
        
        mock_remove.assert_called_once_with(updater.applying_flag_path)
    
    @patch('uos.remove', side_effect=OSError("File not found"))
    def test_remove_applying_flag_failure(self, mock_remove):
        """Test removing applying flag when file doesn't exist."""
        updater = self.updater
        
        # Should not raise exception
        updater.remove_applying_flag()
        
        mock_remove.assert_called_once_with(updater.applying_flag_path)
    
    @patch('builtins.open', new_callable=mock_open, read_data='2')
    def test_read_failure_counter_success(self, mock_file):
        """Test reading failure counter successfully."""
        updater = self.updater
        
        count = updater._read_failure_counter()
        
        assert count == 2
        mock_file.assert_called_once_with('/__update_failures', 'r')
    
    @patch('builtins.open', side_effect=OSError("File not found"))
    def test_read_failure_counter_file_not_found(self, mock_file):
        """Test reading failure counter when file doesn't exist."""
        updater = self.updater
        
        count = updater._read_failure_counter()
        
        assert count == 0
    
    @patch('builtins.open', new_callable=mock_open)
    def test_write_failure_counter(self, mock_file):
        """Test writing failure counter."""
        updater = self.updater
        
        updater._write_failure_counter(3)
        
        mock_file.assert_called_once_with('/__update_failures', 'w')
        mock_file().write.assert_called_once_with('3')
    
    def test_should_attempt_update_within_limit(self):
        """Test should attempt update when within failure limit."""
        updater = self.updater
        
        with patch.object(updater, '_read_failure_counter', return_value=2):
            result = updater.should_attempt_update()
        
        assert result is True
    
    def test_should_attempt_update_exceeded_limit(self):
        """Test should attempt update when failure limit exceeded."""
        updater = self.updater
        
        with patch.object(updater, '_read_failure_counter', return_value=3):
            result = updater.should_attempt_update()
        
        assert result is False
    
    def test_should_attempt_update_disabled(self):
        """Test should attempt update when update on boot is disabled."""
        updater = FirmwareUpdater(
            device_model="test",
            github_repo="test/repo",
            update_on_boot=False
        )
        
        result = updater.should_attempt_update()
        
        assert result is False
    
    def test_parse_release_metadata_github_format(self):
        """Test parsing GitHub release metadata format."""
        updater = self.updater
        
        metadata_json = {
            "tag_name": "v1.2.0",
            "name": "Release 1.2.0",
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.2.0/firmware.tar.zlib"
                },
                {
                    "name": "other-file.txt",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.2.0/other-file.txt"
                }
            ]
        }
        
        result = updater._parse_release_metadata(json.dumps(metadata_json))
        
        assert result["version"] == "1.2.0"
        assert result["name"] == "Release 1.2.0"
        assert len(result["assets"]) == 1  # Only firmware.tar.zlib should be included
        assert result["assets"][0]["name"] == "firmware.tar.zlib"
    
    def test_parse_release_metadata_direct_format(self):
        """Test parsing direct server metadata format."""
        updater = FirmwareUpdater(
            device_model="test",
            direct_base_url="https://firmware.example.com"
        )
        
        metadata_json = {
            "tag_name": "v1.3.0",
            "name": "Direct Release 1.3.0",
            "url": "https://firmware.example.com/",
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://firmware.example.com/firmware.tar.zlib"
                }
            ]
        }
        
        result = updater._parse_release_metadata(json.dumps(metadata_json))
        
        assert result["version"] == "1.3.0"
        assert result["name"] == "Direct Release 1.3.0"
        assert len(result["assets"]) == 1
    
    def test_parse_release_metadata_no_firmware_asset(self):
        """Test parsing metadata when no firmware asset is found."""
        updater = self.updater
        
        metadata_json = {
            "tag_name": "v1.2.0",
            "name": "Release 1.2.0",
            "assets": [
                {
                    "name": "other-file.txt",
                    "browser_download_url": "https://example.com/other-file.txt"
                }
            ]
        }
        
        with pytest.raises(ValueError, match="No firmware asset found"):
            updater._parse_release_metadata(json.dumps(metadata_json))
    
    def test_get_firmware_url_github_mode(self):
        """Test getting firmware URL in GitHub mode."""
        updater = self.updater
        
        release_data = {
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.2.0/firmware.tar.zlib"
                }
            ]
        }
        
        url = updater._get_firmware_url(release_data)
        
        assert url == "https://github.com/test/repo/releases/download/v1.2.0/firmware.tar.zlib"
    
    def test_get_firmware_url_direct_mode(self):
        """Test getting firmware URL in direct mode."""
        updater = FirmwareUpdater(
            device_model="test",
            direct_base_url="https://firmware.example.com"
        )
        
        release_data = {
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://firmware.example.com/firmware.tar.zlib"
                }
            ]
        }
        
        url = updater._get_firmware_url(release_data)
        
        assert url == "https://firmware.example.com/firmware.tar.zlib"
    
    @patch('uos.mkdir')
    def test_mkdirs_success(self, mock_mkdir):
        """Test creating directories successfully."""
        updater = self.updater
        
        updater._mkdirs("/test/path")
        
        mock_mkdir.assert_called_once_with("/test/path")
    
    @patch('uos.mkdir', side_effect=OSError("Directory exists"))
    def test_mkdirs_already_exists(self, mock_mkdir):
        """Test creating directories when they already exist."""
        updater = self.updater
        
        # Should not raise exception
        updater._mkdirs("/test/path")
        
        mock_mkdir.assert_called_once_with("/test/path")
    
    @patch('uos.stat')
    def test_check_update_archive_exists_valid(self, mock_stat):
        """Test checking update archive when file exists and is valid."""
        updater = self.updater
        
        # Mock file stats (size > 0)
        mock_stat.return_value = type('MockStat', (), {'st_size': 1024})()
        
        result = updater._check_update_archive_exists("/test/archive.tar.zlib")
        
        assert result is True
        mock_stat.assert_called_once_with("/test/archive.tar.zlib")
    
    @patch('uos.stat')
    def test_check_update_archive_exists_empty(self, mock_stat):
        """Test checking update archive when file exists but is empty."""
        updater = self.updater
        
        # Mock file stats (size = 0)
        mock_stat.return_value = type('MockStat', (), {'st_size': 0})()
        
        result = updater._check_update_archive_exists("/test/archive.tar.zlib")
        
        assert result is False
    
    @patch('uos.stat', side_effect=OSError("File not found"))
    def test_check_update_archive_not_exists(self, mock_stat):
        """Test checking update archive when file doesn't exist."""
        updater = self.updater
        
        result = updater._check_update_archive_exists("/test/archive.tar.zlib")
        
        assert result is False
    
    @pytest.mark.asyncio
    async def test_make_http_request_success(self):
        """Test making HTTP request successfully."""
        updater = self.updater
        
        # Mock asyncio connection
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        mock_status_line = b"HTTP/1.1 200 OK\r\n"
        
        mock_reader.readline.return_value = mock_status_line
        
        with patch('uasyncio.open_connection', return_value=(mock_reader, mock_writer)):
            reader, writer, status_line = await updater._make_http_request("api.github.com", 443, "/test")
        
        assert reader is mock_reader
        assert writer is mock_writer
        assert status_line == mock_status_line
        
        # Check that request was written
        mock_writer.write.assert_called_once()
        mock_writer.drain.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_make_http_request_with_auth_token(self):
        """Test making HTTP request with authentication token."""
        updater = self.updater
        
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        
        with patch('uasyncio.open_connection', return_value=(mock_reader, mock_writer)):
            await updater._make_http_request("api.github.com", 443, "/test")
        
        # Check that authorization header was included
        written_data = mock_writer.write.call_args[0][0].decode()
        assert "Authorization: token test-token" in written_data
    
    @pytest.mark.asyncio
    async def test_handle_redirect(self):
        """Test handling HTTP redirect response."""
        updater = self.updater
        
        mock_reader = AsyncMock()
        mock_writer = MagicMock()
        
        # Mock redirect response headers
        mock_reader.readline.side_effect = [
            b"Location: https://example.com/new-location\r\n",
            b"Content-Type: text/html\r\n",
            b"\r\n"  # End of headers
        ]
        
        location = await updater._handle_redirect(mock_reader, mock_writer)
        
        assert location == "https://example.com/new-location"
        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_process_response_headers(self):
        """Test processing HTTP response headers."""
        updater = self.updater
        
        mock_reader = AsyncMock()
        
        # Mock response headers
        mock_reader.readline.side_effect = [
            b"Content-Type: application/octet-stream\r\n",
            b"Content-Length: 2048\r\n",
            b"Server: nginx\r\n",
            b"\r\n"  # End of headers
        ]
        
        content_length = await updater._process_response_headers(mock_reader)
        
        assert content_length == 2048


class TestFirmwareUpdaterIntegration:
    """Integration tests for FirmwareUpdater functionality."""
    
    @pytest.mark.asyncio
    async def test_download_content_to_memory(self):
        """Test downloading content to memory."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        
        # Mock reader with test data
        test_data = b"Hello, World! This is test firmware data."
        mock_reader = AsyncMock()
        mock_reader.read.side_effect = [
            test_data[:20],  # First chunk
            test_data[20:],  # Second chunk
            b""  # End of data
        ]
        
        with patch('machine.Pin') as mock_pin_class:
            mock_led = MagicMock()
            mock_pin_class.return_value = mock_led
            
            content, computed_hash = await updater._download_content(
                mock_reader, 
                store_in_memory=True, 
                target_path=None, 
                content_length=len(test_data)
            )
        
        assert content == test_data.decode('utf-8')
        assert computed_hash is not None
        assert len(computed_hash) > 0  # Should have computed a hash
        
        # LED should have been toggled
        assert mock_led.toggle.call_count >= 2
    
    @pytest.mark.asyncio
    async def test_download_content_to_file(self):
        """Test downloading content to file."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        
        test_data = b"Test firmware file content"
        mock_reader = AsyncMock()
        mock_reader.read.side_effect = [test_data, b""]
        
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_path = temp_file.name
        
        try:
            with patch('machine.Pin'):
                content, computed_hash = await updater._download_content(
                    mock_reader,
                    store_in_memory=False,
                    target_path=temp_path,
                    content_length=len(test_data)
                )
            
            assert content is None  # Should not return content when saving to file
            assert computed_hash is not None
            
            # Check file was written
            with open(temp_path, 'rb') as f:
                file_content = f.read()
            assert file_content == test_data
            
        finally:
            os.unlink(temp_path)
    
    def test_check_core_files_exist_all_present(self):
        """Test checking core files when all are present."""
        updater = FirmwareUpdater(
            device_model="test",
            github_repo="test/repo",
            core_system_files=["main.py", "boot.py", "lib/config.py"]
        )
        
        with patch('uos.stat') as mock_stat:
            # All files exist
            mock_stat.return_value = type('MockStat', (), {'st_size': 100})()
            
            result = updater._check_core_files_exist("/test/extract")
        
        assert result is True
        assert mock_stat.call_count == 3
    
    def test_check_core_files_exist_missing_file(self):
        """Test checking core files when one is missing."""
        updater = FirmwareUpdater(
            device_model="test",
            github_repo="test/repo",
            core_system_files=["main.py", "boot.py", "missing.py"]
        )
        
        def mock_stat_side_effect(path):
            if "missing.py" in path:
                raise OSError("File not found")
            return type('MockStat', (), {'st_size': 100})()
        
        with patch('uos.stat', side_effect=mock_stat_side_effect):
            result = updater._check_core_files_exist("/test/extract")
        
        assert result is False
    
    def test_check_core_files_exist_no_core_files(self):
        """Test checking core files when none are specified."""
        updater = FirmwareUpdater(
            device_model="test",
            github_repo="test/repo",
            core_system_files=[]
        )
        
        result = updater._check_core_files_exist("/test/extract")
        
        assert result is True  # Should return True when no core files specified
    
    @pytest.mark.asyncio
    async def test_check_update_newer_version_available(self):
        """Test checking for updates when newer version is available."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        updater.current_version = "1.0.0"
        
        # Mock successful metadata fetch
        mock_metadata = {
            "tag_name": "v1.1.0",
            "name": "Release 1.1.0",
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.1.0/firmware.tar.zlib"
                }
            ]
        }
        
        with patch.object(updater, '_fetch_release_metadata', return_value=json.dumps(mock_metadata)):
            result = await updater.check_update()
        
        assert result is not None
        assert result["version"] == "1.1.0"
        assert result["name"] == "Release 1.1.0"
    
    @pytest.mark.asyncio
    async def test_check_update_no_newer_version(self):
        """Test checking for updates when no newer version is available."""
        updater = FirmwareUpdater(device_model="test", github_repo="test/repo")
        updater.current_version = "1.1.0"
        
        # Mock metadata with same version
        mock_metadata = {
            "tag_name": "v1.1.0",
            "name": "Release 1.1.0",
            "assets": [
                {
                    "name": "firmware.tar.zlib",
                    "browser_download_url": "https://github.com/test/repo/releases/download/v1.1.0/firmware.tar.zlib"
                }
            ]
        }
        
        with patch.object(updater, '_fetch_release_metadata', return_value=json.dumps(mock_metadata)):
            result = await updater.check_update()
        
        assert result is None 