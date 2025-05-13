import uasyncio as asyncio
# import network # No longer directly used here
import usocket
import ure
import ssl
import hashlib
import gc
import ujson
import uos
import deflate # Added for decompression
import utarfile  # Added for tar extraction
import utime # Added for update log timestamps
import machine # Added for machine.reset()

# async def async_connect_wifi(ssid, password): # REMOVED - WiFiManager will handle this
#     wlan = network.WLAN(network.STA_IF)
#     wlan.active(True)
#     if not wlan.isconnected():
#         print('Connecting to network...')
#         wlan.connect(ssid, password)
#         while not wlan.isconnected():
#             await asyncio.sleep(1)
#     print('Network config:', wlan.ifconfig())

class FirmwareUpdater:
    def __init__(self, device_model, base_url, github_token="", chunk_size=2048, max_redirects=10):
        self.base_url = base_url
        self.github_token = github_token
        self.device_model = device_model
        self.current_version = self._read_version()
        self.chunk_size = chunk_size
        self.max_redirects = max_redirects
        
        self.total_size = 0
        self.bytes_read = 0
        self.download_done = False
        self.error = None
        self.download_started = False
        self.firmware_download_path = '/update.tar.zlib'
        # self._temp_metadata_path = '/releases.tmp.json' # No longer strictly needed for metadata
        self.update_log_path = '/update.log'
        self.update_log_active = False

    # def _read_base_url(self): # REMOVED - base_url and token now passed via __init__
    #     """Read the base_url from a firmware.json file."""
    #     try:
    #         with open('/firmware.json', 'r') as f:
    #             config = ujson.load(f)
    #             self.github_token = config.get('github_token', '') # Now set in __init__
    #             return config.get('base_url', 'https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases')
    #     except Exception as e:
    #         print(f"Error reading firmware config: {e}")
    #         self.github_token = '' # Now set in __init__
    #         return 'https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases'

    def _read_version(self):
        """Read the current version from a version file."""
        try:
            with open('/version.txt', 'r') as f:
                return f.read().strip()
        except Exception as e:
            print(f"Error reading version file: {e}")
            return "0.0.0"  # Default to a low version if file not found

    def _parse_semver(self, version):
        """Parse SemVer string into tuple for comparison."""
        try:
            major, minor, patch = map(int, version.split("."))
            return (major, minor, patch)
        except ValueError:
            raise ValueError(f"Invalid version format: {version}")

    async def _download_file(self, url, target_path, store_in_memory: bool = False):
        """Core download logic, assuming HTTPS. Optionally stores in memory."""
        self.total_size = 0
        self.bytes_read = 0
        self.download_done = False
        self.error = None
        self.download_started = False
        redirects = self.max_redirects
        current_url = url 
        redirect_count = 0
        
        mem_buffer = bytearray() if store_in_memory else None
        file_handle = None

        try:
            while redirects > 0:
                if not isinstance(current_url, str):
                    raise ValueError(f"Invalid URL type: {type(current_url)}")

                if not current_url.startswith("https://"):
                    print(f"Warning: URL does not start with https:// - {current_url}")
                
                url_no_proto = current_url[8:]
                host_end_index = url_no_proto.find('/')
                if host_end_index == -1:
                    host = url_no_proto
                    path = "/"
                else:
                    host = url_no_proto[:host_end_index]
                    path = url_no_proto[host_end_index:]

                if not host:
                    raise ValueError(f"Could not extract host from URL: {current_url}")

                port = 443
                
                print(f'Connecting to {host}:{port} for {target_path if not store_in_memory else "memory buffer"} (URL: {current_url[:70]}...)')
                reader, writer = await asyncio.open_connection(host, port, ssl=True)
                
                headers = f'GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: MicroPython-Firmware-Updater/1.0\r\nConnection: close\r\n'
                if hasattr(self, 'github_token') and self.github_token:
                    headers += f'Authorization: token {self.github_token}\r\n'
                headers += '\r\n'
                request = headers
                writer.write(request.encode())
                await writer.drain()

                status_line = await reader.readline()
                
                if status_line.startswith(b'HTTP/1.1 301') or status_line.startswith(b'HTTP/1.1 302'):
                    location = None
                    temp_header_line = b''
                    while True:
                        temp_header_line = await reader.readline()
                        if temp_header_line == b'\r\n': break
                        if temp_header_line.startswith(b'Location:'):
                            location = temp_header_line.split(b': ')[1].decode().strip()
                    writer.close()
                    await writer.wait_closed()
                    redirect_count += 1
                    current_url = location 
                    redirects -= 1
                    if redirects == 0:
                        raise ValueError("Maximum redirects reached during redirect handling")
                    continue 
                elif not status_line.startswith(b'HTTP/1.1 200 OK'):
                    writer.close()
                    await writer.wait_closed()
                    raise ValueError(f'Unexpected response: {status_line.decode().strip()}')

                content_length = 0
                temp_header_line = b''
                while True:
                    temp_header_line = await reader.readline()
                    if temp_header_line == b'\r\n': break 
                    if temp_header_line.startswith(b'Content-Length:'):
                        content_length = int(temp_header_line.split(b':')[1].strip())
                        self.total_size = content_length
                
                if content_length == 0 and not (status_line.startswith(b'HTTP/1.1 204')):
                    is_metadata_download = store_in_memory
                    if not is_metadata_download:
                        writer.close()
                        await writer.wait_closed()
                        raise ValueError('Empty content length received for firmware file')

                self.download_started = True
                gc.collect()
                hash_obj = hashlib.sha256()

                def hexdigest(data):
                    try: return data.hexdigest()
                    except Exception: return ''.join('{:02x}'.format(byte) for byte in data.digest())

                if not store_in_memory:
                    if not target_path or not isinstance(target_path, str):
                        raise ValueError("Invalid target_path for file download")
                    file_handle = open(target_path, 'wb')
                
                remaining = content_length
                while remaining > 0:
                    chunk = await reader.read(min(self.chunk_size, remaining))
                    if not chunk: break
                    hash_obj.update(chunk)
                    if store_in_memory and mem_buffer is not None:
                        mem_buffer.extend(chunk)
                    elif file_handle:
                        file_handle.write(chunk)
                    self.bytes_read += len(chunk)
                    remaining -= len(chunk)
                    gc.collect()
                    await asyncio.sleep(0)
                
                if file_handle:
                    file_handle.close()
                    file_handle = None

                writer.close()
                await writer.wait_closed()
                self.download_done = True
                
                computed_hash = hexdigest(hash_obj) if content_length > 0 else "NO_CONTENT_HASH"
                
                content_str = None
                if store_in_memory and mem_buffer is not None:
                    content_str = mem_buffer.decode('utf-8')
                
                return content_str, computed_hash

            if redirects == 0:
                 raise ValueError('Maximum redirects exceeded after loop completion')

        except Exception as e:
            self.error = f"Download failed for {url}: {str(e)}"
            print(self.error)
            if file_handle: 
                file_handle.close()
            try:
                if 'writer' in locals() and not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception: pass 
            return None, None 

    def _log_to_update_file(self, message):
        if not self.update_log_active:
            return
        try:
            timestamp = utime.ticks_ms()
            with open(self.update_log_path, 'a') as f:
                f.write(f"{timestamp} - {message}\\n")
        except Exception: # Catch all, pass silently
            pass # Don't disrupt main flow if logging fails

    def percent_complete(self):
        if not self.download_started or self.total_size == 0:
            return 0
        return int((self.bytes_read / self.total_size) * 100)

    def is_download_done(self):
        return self.download_done

    async def check_and_update(self):
        self.error = None 
        release_to_download = None 
        new_firmware_version = None
        
        print("Step 1: Fetching latest release metadata...")
        metadata_url = self.base_url
        
        # Safely unpack result from _download_file
        metadata_content_str, metadata_hash = None, None # Initialize
        download_result = await self._download_file(metadata_url, target_path=None, store_in_memory=True)
        if download_result is not None: # Check if the result itself is not None
            metadata_content_str, metadata_hash = download_result
        # If download_result was None (should not happen with current _download_file error handling, but defensive)
        # or if metadata_content_str is None after unpacking, the next check will catch it.
        
        if self.error or not metadata_content_str:
            print(f"Failed to download latest release metadata: {self.error if self.error else 'No content or download error'}")
            # No update log active yet, so no log write here
            return False
        
        print("Step 2: Parsing latest release metadata and checking version...")
        try:
            latest_release = ujson.loads(metadata_content_str) 

            if not isinstance(latest_release, dict):
                self.error = "Latest release metadata is not a valid JSON object."
                print(self.error)
                return False
            
            if not latest_release: 
                self.error = "No latest release found (empty or invalid response)."
                print(self.error)
                return False

            latest_version_str = latest_release.get("tag_name", "0.0.0")
            if not latest_version_str or latest_version_str == "0.0.0":
                 self.error = "Latest release is missing version info (tag_name)."
                 print(self.error)
                 return False
                 
            if latest_version_str.startswith('v'):
                latest_version_str = latest_version_str[1:]

            current_semver = self._parse_semver(self.current_version)
            latest_semver = self._parse_semver(latest_version_str)

            if latest_semver <= current_semver:
                print(f"Device is up-to-date. Current: {self.current_version}, Latest available: {latest_version_str}")
                return True 

            print(f"Update available: {latest_version_str} (current: {self.current_version})")
            new_firmware_version = latest_version_str 
            release_to_download = latest_release

            # --- START Update Log ---
            self.update_log_active = True
            try:
                uos.remove(self.update_log_path) # Clear old log
            except OSError:
                pass # File didn't exist, that's fine
            self._log_to_update_file(f"Update available: Local v{self.current_version} -> Remote v{latest_version_str}")
            self._log_to_update_file(f"Release Name: {release_to_download.get('name', 'N/A')}, Tag: {release_to_download.get('tag_name', 'N/A')}")
            # --- END Update Log ---

        except Exception as e:
            self.error = f"Latest release metadata processing error: {str(e)}"
            print(self.error)
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            return False

        if release_to_download:
            assets = release_to_download.get("assets", [])
            firmware_url = None
            firmware_filename = None

            for asset in assets:
                if asset.get("name", "").endswith("firmware.tar.zlib"):
                    firmware_url = asset.get("browser_download_url")
                    firmware_filename = asset.get("name")
                    break

            if not firmware_url:
                 self.error = "No firmware asset (firmware.tar.zlib) found in the latest release."
                 print(self.error)
                 if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
                 return False

            print(f"Step 3: Downloading firmware '{firmware_filename}' to {self.firmware_download_path}...")
            
            self.download_done = False 
            self.download_started = False
            self.bytes_read = 0
            self.total_size = 0
            
            firmware_download_result = await self._download_file(firmware_url, self.firmware_download_path, store_in_memory=False)
            firmware_content_str, computed_sha256 = None, None 
            if firmware_download_result is not None:
                firmware_content_str, computed_sha256 = firmware_download_result

            if self.error or not computed_sha256:
                errmsg = f"Firmware download failed: {self.error if self.error else 'No hash or download error'}"
                print(errmsg)
                if self.update_log_active: self._log_to_update_file(f"ERROR: {errmsg}")
                return False
            self._log_to_update_file("Firmware download successful.")

            self._log_to_update_file("Step 4: Skipping checksum verification (not provided by GitHub API).")
            print("Step 4: Skipping checksum verification (not provided by GitHub API).")

            if new_firmware_version:
                self._log_to_update_file(f"Step 5: Updating version file to {new_firmware_version}...")
                print(f"Step 5: Updating version file to {new_firmware_version}...")
                try:
                    with open('/version.txt', 'w') as vf:
                        vf.write(new_firmware_version) 
                    self._log_to_update_file("Version file updated successfully.")
                    print("Version file updated successfully.")
                    self.current_version = new_firmware_version
                except Exception as e:
                    self.error = f"Failed to update version file: {str(e)}"
                    print(self.error)
                    if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            
            self._log_to_update_file(f"Firmware update downloaded successfully to {self.firmware_download_path}")
            print(f"Firmware update downloaded successfully to {self.firmware_download_path}")
            return True 
        
        return False

    def _mkdirs(self, path):
        current_path = ""
        if path.startswith('/'): 
            current_path = "/"
            parts = path.strip('/').split('/')
        else: 
            parts = path.split('/')
        for part in parts:
            if not part: continue
            if current_path == "/" and part: current_path += part
            elif current_path and part: current_path += "/" + part
            elif not current_path and part: current_path = part
            try: uos.mkdir(current_path)
            except OSError as e:
                if e.args[0] != 17: raise 

    async def apply_update(self):
        self.error = None
        compressed_file_path = self.firmware_download_path
        decompressed_tar_path = "/update.tmp.tar"
        extract_to_dir = "/update"
        update_count = 0
        error_count = 0 # For tar extraction errors

        self._log_to_update_file(f"Step 6: Applying update from {compressed_file_path}...")
        print(f"Step 6: Applying update from {compressed_file_path}...")
        try: self._mkdirs(extract_to_dir)
        except Exception as e: 
            self.error = f"Directory creation failed for {extract_to_dir}: {str(e)}"; print(self.error)
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            return False

        # Decompression step
        self._log_to_update_file(f"Decompressing {compressed_file_path} to {decompressed_tar_path}...")
        print(f"Decompressing {compressed_file_path} to {decompressed_tar_path}...")
        f_zlib = None
        d_stream = None
        f_tar_out = None
        decompression_success = False
        try:
            f_zlib = open(compressed_file_path, "rb")
            # Using positional arguments for DeflateIO: stream, format, wbits
            # format=deflate.ZLIB, wbits=0 (for auto window size from header)
            d_stream = deflate.DeflateIO(f_zlib, deflate.ZLIB, 0) 
            f_tar_out = open(decompressed_tar_path, "wb")
            chunk_size = 512 
            while True:
                chunk = d_stream.read(chunk_size)
                if not chunk: break
                f_tar_out.write(chunk)
                await asyncio.sleep(0) 
            decompression_success = True
            self._log_to_update_file("Decompression successful.")
            print("Decompression successful.")
        except Exception as e:
            self.error = f"Decompression failed: {str(e)}"; print(self.error)
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
        finally:
            if d_stream: 
                try: d_stream.close() 
                except Exception as e_close: print(f"Error closing d_stream: {e_close}")
            if f_tar_out:
                try: f_tar_out.close()
                except Exception as e_close: print(f"Error closing f_tar_out: {e_close}")
            if f_zlib:
                try: f_zlib.close()
                except Exception as e_close: print(f"Error closing f_zlib: {e_close}")
        
        if not decompression_success:
            try: uos.remove(decompressed_tar_path) 
            except OSError: pass
            if self.update_log_active: self._log_to_update_file("Decompression failed, cannot proceed to extraction.")
            return False

        # Extraction step (using logic from user's provided example)
        self._log_to_update_file(f"Extracting {decompressed_tar_path} to {extract_to_dir}...")
        print(f"Extracting {decompressed_tar_path} to {extract_to_dir}...")
        tar = None
        try:
            tar = utarfile.TarFile(name=decompressed_tar_path)
            for entry in tar: # Iterate through members
                try:
                    if not entry: continue
                        
                    file_name = entry.name
                    
                    # Silently skip PaxHeader entries
                    if "@PaxHeader" in file_name:
                        continue
                        
                    self._log_to_update_file(f"Processing tar entry: {file_name}")
                    print(f"Processing tar entry: {file_name}")
                    
                    if file_name.startswith('/') or '..' in file_name or file_name.startswith('.'):
                        self._log_to_update_file(f"Skipping potentially unsafe path: {file_name}")
                        print(f"Skipping potentially unsafe path: {file_name}")
                        continue
                        
                    target_path = f"{extract_to_dir}/{file_name}"
                    
                    if entry.type == utarfile.DIRTYPE:
                        self._mkdirs(target_path)
                        self._log_to_update_file(f"Created directory (from tar): {target_path}")
                        print(f"Created directory (from tar): {target_path}")
                    else: # Is a file
                        parent_dir = target_path.rpartition('/')[0]
                        if parent_dir: self._mkdirs(parent_dir) # Ensure parent dir exists
                                
                        f_entry = tar.extractfile(entry)
                        if f_entry:
                            with open(target_path, "wb") as outfile:
                                while True:
                                    chunk = f_entry.read(1024) # Read in chunks
                                    if not chunk: break
                                    outfile.write(chunk)
                            update_count += 1
                            self._log_to_update_file(f"Extracted file: {target_path}")
                            print(f"Extracted file: {target_path}")
                        else:
                            self._log_to_update_file(f"Could not extract file entry: {file_name}")
                            print(f"Could not extract file entry: {file_name}")
                            error_count +=1
                except Exception as e_entry:
                    errmsg_entry = f"Error processing tar entry '{entry.name if entry else "UNKNOWN"}': {e_entry}"
                    print(errmsg_entry)
                    if self.update_log_active: self._log_to_update_file(f"ERROR: {errmsg_entry}")
                    error_count += 1
            self._log_to_update_file(f"Extraction finished. Files extracted: {update_count}, Errors: {error_count}")
            print(f"Extraction finished. Files extracted: {update_count}, Errors: {error_count}")
        except Exception as e:
            self.error = f"Tar extraction failed: {str(e)}"; print(self.error)
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            error_count +=1 # Count this as a major error too
        # finally:
        #     if tar: 
        #         try: tar.close() 
        #         except Exception as e_close: print(f"Error closing tar object: {e_close}")
        #     try: uos.remove(decompressed_tar_path) 
        #     except OSError as e_remove: print(f"Warn: Failed to remove {decompressed_tar_path}: {e_remove}")

        if error_count > 0 or self.error: # If any errors occurred during extraction or main tar processing
             if not self.error: self.error = f"{error_count} errors during tar extraction."
             # If error_count > 0 and self.error was not previously set, log the new error.
             # If self.error was already set, it should have been logged at its occurrence.
             if self.update_log_active and error_count > 0 and str(error_count) in self.error: # self.error just set
                 self._log_to_update_file(f"ERROR: {self.error}")
             return False
        if update_count == 0 and not self.error:
            self.error = "No files were extracted from the tar archive."
            print(self.error)
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            return False

        self._log_to_update_file(f"Firmware successfully extracted to {extract_to_dir}.")
        print(f"Firmware successfully extracted to {extract_to_dir}.")
        
        # --- Step 7: Backup existing files ---
        self._log_to_update_file("Proceeding to Step 7: Backup existing files.")
        print("Proceeding to Step 7: Backup existing files.")
        if not await self._backup_existing_files():
            # Error already logged by _backup_existing_files
            # self.error would be set by the helper
            if self.update_log_active: self._log_to_update_file(f"Update aborted due to backup failure: {self.error}")
            print(f"Update aborted due to backup failure: {self.error}")
            return False

        # --- Step 8: Overwrite root with updated files ---
        self._log_to_update_file("Proceeding to Step 8: Apply update from /update to /.")   
        print("Proceeding to Step 8: Apply update from /update to /.")
        if not await self._move_from_update_to_root():
            # Error already logged by _move_from_update_to_root
            # self.error would be set by the helper
            if self.update_log_active: self._log_to_update_file(f"Update aborted due to overwrite failure: {self.error}")
            print(f"Update aborted due to overwrite failure: {self.error}")
            return False
            
        # --- Step 9: Reboot ---
        self._log_to_update_file("Step 9: System update successfully applied. Rebooting device...")
        print("Step 9: System update successfully applied. Rebooting device...")
        await asyncio.sleep(1) # Brief pause for logs to potentially flush
        machine.reset()
        
        return True # This line will not be reached due to reset

    async def _copy_item_recursive(self, source_path, dest_path):
        # Ensure parent of dest_path exists for the current item being copied
        dest_parent_dir = dest_path.rpartition('/')[0]
        if dest_parent_dir and dest_parent_dir != "/": # Avoid trying to mkdir "/" or empty string
            self._mkdirs(dest_parent_dir) # _mkdirs handles existing dirs

        s_stat = uos.stat(source_path)
        is_dir = (s_stat[0] & 0x4000) != 0 # S_IFDIR check

        if is_dir:
            self._mkdirs(dest_path) # Create the directory itself in destination
            log_msg = f"Copying dir: {source_path} to {dest_path}"
            if self.update_log_active: self._log_to_update_file(log_msg)
            print(log_msg)
            for item_name in uos.listdir(source_path):
                await self._copy_item_recursive(f"{source_path.rstrip('/')}/{item_name}", f"{dest_path.rstrip('/')}/{item_name}")
                await asyncio.sleep(0) # Yield during directory iteration
        else: # Is a file
            log_msg = f"Copying file: {source_path} to {dest_path}"
            if self.update_log_active: self._log_to_update_file(log_msg)
            print(log_msg)
            try:
                with open(source_path, 'rb') as src_f, open(dest_path, 'wb') as dst_f:
                    while True:
                        chunk = src_f.read(self.chunk_size) 
                        if not chunk: break
                        dst_f.write(chunk)
                        # Yield more frequently for very large files if chunk_size is small
                        # For now, yielding per chunk might be too much, let's do it after file completion or in dir loop.
                    await asyncio.sleep(0) # Yield after file copy
            except Exception as e:
                raise Exception(f"Failed to copy file {source_path} to {dest_path}: {str(e)}")

    async def _remove_dir_recursive(self, dir_path):
        log_msg = f"Recursively removing directory: {dir_path}"
        if self.update_log_active: self._log_to_update_file(log_msg)
        print(log_msg)
        
        # Ensure dir_path is not root, as a safeguard
        if dir_path == '/' or not dir_path:
            err_msg = "Attempted to remove root directory or empty path."
            if self.update_log_active: self._log_to_update_file(f"CRITICAL ERROR: {err_msg}")
            print(f"CRITICAL ERROR: {err_msg}")
            self.error = err_msg
            raise Exception(err_msg)
            
        for item_name in uos.listdir(dir_path):
            item_path = f"{dir_path.rstrip('/')}/{item_name}"
            try:
                s_stat = uos.stat(item_path)
                is_dir = (s_stat[0] & 0x4000) != 0
                if is_dir:
                    await self._remove_dir_recursive(item_path)
                else:
                    uos.remove(item_path)
            except OSError as e:
                 # If stat fails (e.g. broken symlink or non-existent during concurrent modification)
                 # or remove fails. Log and continue if possible, or re-raise if critical.
                 err_msg_item = f"Error processing {item_path} during recursive delete of {dir_path}: {e}"
                 if self.update_log_active: self._log_to_update_file(f"WARNING: {err_msg_item}")
                 print(f"WARNING: {err_msg_item}") # Continue, to try and remove as much as possible
            await asyncio.sleep(0) # Yield
        uos.rmdir(dir_path)

    async def _backup_existing_files(self):
        step_msg = "Step 7: Backing up existing system files..." 
        if self.update_log_active: self._log_to_update_file(step_msg)
        print(step_msg)
        
        backup_dir = "/backup"
        # Exclude backup dir, update dir, temp files, logs, and sensitive configs
        excluded_top_level_items = [
            backup_dir, 
            "/update", 
            self.firmware_download_path, # /update.tar.zlib
            "/update.tmp.tar", 
            self.update_log_path,      # /update.log
            "/lasterror.json",
            "/log.txt",
            # "/config.json" # User might want to backup config, or manage separately. Let's include it by default for now.
        ]
        try:
            self._mkdirs(backup_dir) # Ensure backup_dir itself exists
            
            root_items = uos.listdir("/")
            for item_name in root_items:
                # Construct full source path from root
                source_path = f"/{item_name.lstrip('/')}"
                
                if source_path in excluded_top_level_items:
                    skip_msg = f"Backup: Skipping excluded top-level item: {source_path}"
                    if self.update_log_active: self._log_to_update_file(skip_msg)
                    print(skip_msg)
                    continue

                # Construct full destination path within backup_dir
                dest_path = f"{backup_dir.rstrip('/')}{source_path}" 
                # Example: item_name="main.py" -> source="/main.py", dest="/backup/main.py"
                # Example: item_name="lib"     -> source="/lib",     dest="/backup/lib"

                try:
                    await self._copy_item_recursive(source_path, dest_path)
                except Exception as e_copy:
                    self.error = f"Backup error for {source_path} to {dest_path}: {str(e_copy)}"
                    if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
                    print(f"ERROR: {self.error}")
                    return False # Abort backup on first error
                await asyncio.sleep(0) # Yield between top-level items
            
            success_msg = "Backup completed successfully."
            if self.update_log_active: self._log_to_update_file(success_msg)
            print(success_msg)
            return True
        except Exception as e_main:
            self.error = f"Backup process failed: {str(e_main)}"
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}")
            print(f"ERROR: {self.error}")
            return False

    async def _move_from_update_to_root(self):
        step_msg = "Step 8: Moving updated files from /update to / ..." 
        if self.update_log_active: self._log_to_update_file(step_msg)
        print(step_msg)
        
        update_source_dir = "/update"
        try:
            if not update_source_dir in uos.listdir('/'): # Check if /update exists
                 warn_msg = f"Warning: Update source directory '{update_source_dir}' not found. Nothing to move."
                 if self.update_log_active: self._log_to_update_file(warn_msg)
                 print(warn_msg)
                 # This might be an error or an acceptable state if the tar was empty (already handled)
                 # For now, let's consider it a success for this step if /update is not there.
                 return True 
                 
            items_to_move = uos.listdir(update_source_dir)
            for item_name in items_to_move:
                source_item_path = f"{update_source_dir.rstrip('/')}/{item_name.lstrip('/')}"
                dest_item_path = f"/{item_name.lstrip('/')}"

                # If destination exists, remove it first
                try:
                    uos.stat(dest_item_path) # Check existence, raises OSError if not found
                    # Item exists at destination, determine if file or directory
                    s_stat_dest = uos.stat(dest_item_path) # Re-stat, first one was just for existence
                    is_dir_dest = (s_stat_dest[0] & 0x4000) != 0
                    if is_dir_dest:
                        rm_msg = f"Removing existing directory at root: {dest_item_path}"
                        if self.update_log_active: self._log_to_update_file(rm_msg); print(rm_msg)
                        await self._remove_dir_recursive(dest_item_path)
                    else:
                        rm_msg = f"Removing existing file at root: {dest_item_path}"
                        if self.update_log_active: self._log_to_update_file(rm_msg); print(rm_msg)
                        uos.remove(dest_item_path)
                except OSError as e:
                    if e.args[0] == 2: # ENOENT (Error Number 2): File/dir not found
                        pass # Destination doesn't exist, good to go for rename
                    else:
                        self.error = f"Error checking/removing destination {dest_item_path}: {str(e)}"
                        if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}"); print(f"ERROR: {self.error}")
                        return False # Critical error

                # Now attempt to rename/move the item
                mv_msg = f"Moving: {source_item_path} to {dest_item_path}"
                if self.update_log_active: self._log_to_update_file(mv_msg); print(mv_msg)
                try:
                    uos.rename(source_item_path, dest_item_path)
                except Exception as e_rename:
                    self.error = f"Failed to move {source_item_path} to {dest_item_path}: {str(e_rename)}"
                    if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}"); print(f"ERROR: {self.error}")
                    return False # Critical error
                await asyncio.sleep(0) # Yield between items

            # Cleanup: Remove the now-empty /update directory and other temp files
            cleanup_msg = "Cleaning up temporary update files and /update directory..."
            if self.update_log_active: self._log_to_update_file(cleanup_msg); print(cleanup_msg)
            
            await self._remove_dir_recursive(update_source_dir) # remove /update directory
            
            try: 
                uos.remove(self.firmware_download_path) # /update.tar.zlib
                if self.update_log_active: self._log_to_update_file(f"Removed {self.firmware_download_path}")
            except OSError: pass # May have already been removed or failed silently
            try: 
                uos.remove("/update.tmp.tar")
                if self.update_log_active: self._log_to_update_file("Removed /update.tmp.tar")
            except OSError: pass
            
            final_msg = "Overwrite and cleanup completed successfully."
            if self.update_log_active: self._log_to_update_file(final_msg); print(final_msg)
            return True
        except Exception as e_main_move:
            self.error = f"File overwrite process failed: {str(e_main_move)}"
            if self.update_log_active: self._log_to_update_file(f"ERROR: {self.error}"); print(f"ERROR: {self.error}")
            return False

# Removed BinDownload class
# Removed FirmwareDownloader class

# async def main_async():
#     # This function would need significant changes to use ConfigManager and WiFiManager
#     # For now, it's commented out as boot.py will be the entry point.
#     # print("Attempting to connect to WiFi using placeholder credentials...")
#     # try:
#     #     # Placeholder for actual WiFi connection logic that would come from WiFiManager
#     #     # await async_connect_wifi('YOUR_SSID', 'YOUR_PASSWORD') 
#     #     print("WiFi connected (simulated for standalone test).")
#     # except Exception as e:
#     #     print(f"Failed to connect to WiFi: {e}")
#     #     return 

#     # Placeholder for ConfigManager to get these values
#     # device_model_val = 'device-model-A'
#     # base_url_val = 'https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases'
#     # github_token_val = '' # Potentially from config

#     # updater = FirmwareUpdater(
#     #     device_model=device_model_val,
#     #     base_url=base_url_val,
#     #     github_token=github_token_val
#     # )
    
#     # print("Starting firmware update check...")
#     # success = await updater.check_and_update() 
    
#     # if success:
#     #     if updater.error: 
#     #          print(f"Firmware check completed with message: {updater.error}")
#     #     elif not updater.is_download_done(): 
#     #          print("Firmware is already up-to-date.")
#     #     else:
#     #          print(f"Firmware update successful. New firmware at: {updater.firmware_download_path}")
#     # else:
#     #     print(f"Firmware update process failed: {updater.error}")

# if __name__ == "__main__":
#     # try:
#     #     asyncio.run(main_async())
#     # except KeyboardInterrupt:
#     #     print("Interrupted")
#     # finally:
#     #     asyncio.new_event_loop() 