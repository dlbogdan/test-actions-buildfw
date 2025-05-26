"""
Tests for the build system (local_builder.py and related tools).
These test the Python-based build tools, not the MicroPython code.
"""
import pytest
import os
import tempfile
import json
import tarfile
import zlib
from unittest.mock import patch, mock_open, MagicMock
import sys

# Add the project root to path to import local_builder
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import local_builder


class TestLocalBuilder:
    """Test cases for the local firmware builder."""
    
    def test_ensure_directory_creates_missing_dir(self, tmp_path):
        """Test that ensure_directory creates missing directories."""
        test_dir = tmp_path / "test_build"
        assert not test_dir.exists()
        
        local_builder.ensure_directory(str(test_dir))
        
        assert test_dir.exists()
        assert test_dir.is_dir()
    
    def test_ensure_directory_handles_existing_dir(self, tmp_path):
        """Test that ensure_directory handles existing directories gracefully."""
        test_dir = tmp_path / "existing_dir"
        test_dir.mkdir()
        
        # Should not raise an error
        local_builder.ensure_directory(str(test_dir))
        
        assert test_dir.exists()
    
    def test_calculate_file_sha256(self, tmp_path):
        """Test SHA256 calculation for files."""
        test_file = tmp_path / "test.txt"
        test_content = b"Hello, World!"
        test_file.write_bytes(test_content)
        
        result = local_builder.calculate_file_sha256(str(test_file))
        
        # Expected SHA256 for "Hello, World!"
        expected = "dffd6021bb2bd5b0af676290809ec3a53191dd81c7f70a4b28688a362182986f"
        assert result == expected
    
    def test_get_version_from_file(self, tmp_path):
        """Test version extraction from version.txt file."""
        # Create a mock source directory with version.txt
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        version_file = src_dir / "version.txt"
        version_file.write_text("1.2.3")
        
        with patch.object(local_builder, 'SOURCE_DIR', str(src_dir)):
            version = local_builder.get_version()
        
        assert version == "v1.2.3"
    
    def test_get_version_from_git(self, tmp_path):
        """Test version extraction from git when version.txt doesn't exist."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        with patch.object(local_builder, 'SOURCE_DIR', str(src_dir)):
            with patch('subprocess.check_output') as mock_git:
                mock_git.return_value = b"v2.0.0-5-g1234567\n"
                
                version = local_builder.get_version()
        
        assert version == "v2.0.0-5-g1234567"
    
    def test_get_version_fallback_to_default(self, tmp_path):
        """Test version fallback to default when git and file both fail."""
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        
        with patch.object(local_builder, 'SOURCE_DIR', str(src_dir)):
            with patch('subprocess.check_output', side_effect=Exception("Git failed")):
                version = local_builder.get_version()
        
        assert version == f"v{local_builder.DEFAULT_VERSION}"
    
    def test_create_metadata(self):
        """Test metadata creation for GitHub-like format."""
        test_data = b"test firmware data"
        version = "v1.0.0"
        repo = "test/repo"
        port = 8443
        
        with patch('local_builder.get_local_ip', return_value='192.168.1.100'):
            metadata = local_builder.create_metadata(test_data, version, repo, port)
        
        assert metadata["tag_name"] == version
        assert metadata["name"] == f"Firmware {version}"
        assert "192.168.1.100:8443" in metadata["url"]
        assert len(metadata["assets"]) == 2  # firmware.tar.zlib and metadata.json
    
    @patch('subprocess.run')
    def test_compile_to_mpy_success(self, mock_subprocess, tmp_path):
        """Test successful compilation of Python files to .mpy."""
        # Setup source directory with Python files
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        
        # Create test Python files
        (source_dir / "test_module.py").write_text("print('test')")
        (source_dir / "main.py").write_text("print('main')")  # Should be skipped
        (source_dir / "boot.py").write_text("print('boot')")  # Should be skipped
        
        lib_dir = source_dir / "lib"
        lib_dir.mkdir()
        (lib_dir / "library.py").write_text("def func(): pass")
        
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        
        # Mock successful mpy-cross execution
        mock_subprocess.return_value = MagicMock(returncode=0)
        
        local_builder.compile_to_mpy(str(source_dir), str(temp_dir))
        
        # Should have called mpy-cross for non-main/boot files
        assert mock_subprocess.call_count == 2  # test_module.py and library.py
        
        # Check that the calls were made correctly
        calls = mock_subprocess.call_args_list
        assert any('test_module.py' in str(call) for call in calls)
        assert any('library.py' in str(call) for call in calls)
    
    @patch('subprocess.run')
    def test_compile_to_mpy_failure(self, mock_subprocess, tmp_path):
        """Test handling of mpy-cross compilation failure."""
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        (source_dir / "test.py").write_text("print('test')")
        
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        
        # Mock failed mpy-cross execution
        mock_subprocess.side_effect = subprocess.CalledProcessError(1, 'mpy-cross')
        
        with pytest.raises(subprocess.CalledProcessError):
            local_builder.compile_to_mpy(str(source_dir), str(temp_dir))
    
    def test_create_tar_archive(self, tmp_path):
        """Test creation of tar archive with hash file."""
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        
        # Create test files
        (source_dir / "main.py").write_text("print('main')")
        (source_dir / "boot.py").write_text("print('boot')")
        
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()
        
        # Create a compiled .mpy file
        mpy_file = temp_dir / "test.mpy"
        mpy_file.write_bytes(b"fake mpy content")
        
        tar_path = tmp_path / "test.tar"
        
        local_builder.create_tar_archive(str(source_dir), str(tar_path), str(temp_dir))
        
        # Verify tar file was created and contains expected files
        assert tar_path.exists()
        
        with tarfile.open(str(tar_path), 'r') as tar:
            names = tar.getnames()
            assert 'integrity.json' in names  # Hash file should be first
            assert 'main.py' in names
            assert 'boot.py' in names
            assert 'test.mpy' in names
    
    def test_compress_zlib(self, tmp_path):
        """Test zlib compression of tar file."""
        # Create a test tar file
        tar_path = tmp_path / "test.tar"
        test_data = b"test tar file content"
        tar_path.write_bytes(test_data)
        
        output_path = tmp_path / "test.tar.zlib"
        
        compressed_data = local_builder.compress_zlib(str(tar_path), str(output_path))
        
        # Verify compressed file was created
        assert output_path.exists()
        
        # Verify we can decompress it back
        decompressed = zlib.decompress(compressed_data)
        assert decompressed == test_data
    
    def test_get_local_ip(self):
        """Test local IP address detection."""
        with patch('socket.socket') as mock_socket:
            mock_sock = MagicMock()
            mock_sock.getsockname.return_value = ('192.168.1.100', 0)
            mock_socket.return_value = mock_sock
            
            ip = local_builder.get_local_ip()
            
            assert ip == '192.168.1.100'
    
    def test_get_local_ip_fallback(self):
        """Test local IP address detection fallback to localhost."""
        with patch('socket.socket', side_effect=Exception("Network error")):
            ip = local_builder.get_local_ip()
            assert ip == '127.0.0.1'


class TestBuildIntegration:
    """Integration tests for the complete build process."""
    
    @pytest.mark.integration
    def test_full_build_process(self, tmp_path):
        """Test the complete build process end-to-end."""
        # Setup directory structure
        source_dir = tmp_path / "src"
        source_dir.mkdir()
        build_dir = tmp_path / "build"
        
        # Create test source files
        (source_dir / "main.py").write_text("print('Hello from main')")
        (source_dir / "boot.py").write_text("print('Hello from boot')")
        (source_dir / "version.txt").write_text("1.0.0")
        
        lib_dir = source_dir / "lib"
        lib_dir.mkdir()
        (lib_dir / "test_lib.py").write_text("def test_function(): return 'test'")
        
        # Mock the global variables
        with patch.object(local_builder, 'SOURCE_DIR', str(source_dir)):
            with patch.object(local_builder, 'BUILD_DIR', str(build_dir)):
                with patch('subprocess.run') as mock_subprocess:
                    # Mock successful mpy-cross
                    mock_subprocess.return_value = MagicMock(returncode=0)
                    
                    # Mock mpy-cross to create fake .mpy files
                    def create_mpy_file(*args, **kwargs):
                        # Extract output path from mpy-cross arguments
                        cmd_args = args[0]
                        if '-o' in cmd_args:
                            output_idx = cmd_args.index('-o') + 1
                            output_path = cmd_args[output_idx]
                            # Create a fake .mpy file
                            os.makedirs(os.path.dirname(output_path), exist_ok=True)
                            with open(output_path, 'wb') as f:
                                f.write(b'fake mpy content')
                        return MagicMock(returncode=0)
                    
                    mock_subprocess.side_effect = create_mpy_file
                    
                    # Run the main build function
                    with patch('local_builder.get_local_ip', return_value='127.0.0.1'):
                        local_builder.main()
        
        # Verify build outputs
        firmware_file = build_dir / "firmware.tar.zlib"
        metadata_file = build_dir / "metadata.json"
        
        assert firmware_file.exists()
        assert metadata_file.exists()
        
        # Verify metadata content
        with open(metadata_file, 'r') as f:
            metadata = json.load(f)
        
        assert metadata["tag_name"] == "v1.0.0"
        assert len(metadata["assets"]) == 2 