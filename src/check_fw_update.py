import uasyncio as asyncio
import network
import usocket
import ure
import ssl
import hashlib
import gc
import ujson
import uos

async def async_connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            await asyncio.sleep(1)
    print('Network config:', wlan.ifconfig())

# Combined class replacing BinDownload and FirmwareDownloader
class FirmwareUpdater:
    def __init__(self, device_model, chunk_size=2048, max_redirects=3):
        self.base_url = self._read_base_url()
        self.device_model = device_model
        self.current_version = self._read_version()
        self.chunk_size = chunk_size
        self.max_redirects = max_redirects
        
        self.total_size = 0
        self.bytes_read = 0
        self.download_done = False # Renamed from 'done'
        self.error = None
        self.download_started = False # Renamed from 'started'
        self.firmware_download_path = '/update.bin' # Path for the final firmware file
        self._temp_metadata_path = '/releases.tmp.json' # Temporary path for metadata

    def _read_base_url(self):
        """Read the base_url from a firmware.json file."""
        try:
            with open('/firmware.json', 'r') as f:
                config = ujson.load(f)
                return config.get('base_url', 'https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases')
        except Exception as e:
            print(f"Error reading firmware config: {e}")
            return 'https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases'  # Default if file not found or error

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

    async def _download_file(self, url, target_path):
        """Core download logic, adapted from BinDownload.__call__."""
        self.total_size = 0
        self.bytes_read = 0
        self.download_done = False
        self.error = None
        self.download_started = False
        redirects = self.max_redirects
        current_url = url

        try:
            while redirects > 0:
                match = ure.match(r'(http|https)://([^/]+)(/.*)', current_url)
                if not match:
                    raise ValueError(f'Invalid URL format: {current_url}')
                proto = match.group(1)
                host = match.group(2)
                path = match.group(3)
                port = 443 if proto == 'https' else 80
                
                print(f'Connecting to {host}:{port} for {target_path}...')
                reader, writer = await asyncio.open_connection(host, port, ssl=(proto == 'https'))
                
                request = f'GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n'
                print('Sending request:', request)
                writer.write(request.encode())
                await writer.drain()

                status_line = await reader.readline()
                print('Server response:', status_line)
                
                if status_line.startswith(b'HTTP/1.1 301') or status_line.startswith(b'HTTP/1.1 302'):
                    location = None
                    while True:
                        line = await reader.readline()
                        if line == b'\r\n': break
                        if line.startswith(b'Location:'):
                            location = line.split(b': ')[1].decode().strip()
                    writer.close()
                    await writer.wait_closed()
                    print(f'Redirecting to {location}')
                    current_url = location
                    redirects -= 1
                    continue # Retry with the new URL
                elif not status_line.startswith(b'HTTP/1.1 200 OK'):
                    writer.close()
                    await writer.wait_closed()
                    raise ValueError(f'Unexpected response: {status_line.decode().strip()}')

                # --- Headers ---
                content_length = 0
                while True:
                    line = await reader.readline()
                    # print('Header:', line.decode().strip()) # Optional: Reduce verbosity
                    if line == b'\r\n': break
                    if line.startswith(b'Content-Length:'):
                        content_length = int(line.split(b':')[1].strip())
                        self.total_size = content_length
                
                if content_length == 0:
                    writer.close()
                    await writer.wait_closed()
                    raise ValueError('Empty content length received')

                self.download_started = True
                gc.collect()
                print(f'Starting download of {content_length} bytes to {target_path}...')
                hash_obj = hashlib.sha256()

                # Hexdigest compatibility
                def hexdigest(data):
                    try: return data.hexdigest()
                    except AttributeError: return ''.join('{:02x}'.format(byte) for byte in data.digest())

                # --- Body ---
                with open(target_path, 'wb') as f:
                    remaining = content_length
                    while remaining > 0:
                        chunk = await reader.read(min(self.chunk_size, remaining))
                        if not chunk: break
                        hash_obj.update(chunk)
                        f.write(chunk)
                        self.bytes_read += len(chunk)
                        remaining -= len(chunk)
                        gc.collect()
                        await asyncio.sleep(0)
                
                writer.close()
                await writer.wait_closed()
                self.download_done = True
                print(f'Finished downloading to {target_path}.')
                print(f'SHA256: {hexdigest(hash_obj)}')
                return hexdigest(hash_obj) # Return computed hash

            # If loop finishes without returning (too many redirects)
            raise ValueError('Too many redirects')

        except Exception as e:
            self.error = f"Download failed for {url}: {str(e)}"
            print(self.error)
            # Clean up partially downloaded file on error? Optional.
            try:
                if 'writer' in locals() and not writer.is_closing():
                    writer.close()
                    await writer.wait_closed()
            except Exception as close_err:
                print(f"Error closing writer: {close_err}")
            return None # Indicate failure

    def percent_complete(self):
        if not self.download_started or self.total_size == 0:
            return 0
        return int((self.bytes_read / self.total_size) * 100)

    def is_download_done(self):
        return self.download_done

    async def check_and_update(self):
        """Main method to check for updates and download if necessary."""
        self.error = None # Reset error state
        release_to_download = None
        
        # 1. Fetch Metadata
        print("Step 1: Fetching release metadata...")
        metadata_url = self.base_url
        await self._download_file(metadata_url, self._temp_metadata_path)
        
        if self.error:
            print(f"Failed to download metadata: {self.error}")
            return False # Stop if metadata download failed
        
        # 2. Parse Metadata and Check Version
        print("Step 2: Parsing metadata and checking version...")
        try:
            with open(self._temp_metadata_path, 'r') as f:
                releases = ujson.load(f)

            # GitHub API returns a list of releases, latest is usually first
            latest_release = None
            if releases and isinstance(releases, list) and len(releases) > 0:
                latest_release = releases[0]  # First entry is the latest release
            
            # Clean up temporary metadata file
            try:
                uos.remove(self._temp_metadata_path) 
            except NameError: # uos might not be imported if removed previously
                 pass # Ignore if uos or remove is not available
            except OSError:
                 pass # Ignore if file doesn't exist

            if not latest_release:
                self.error = "No releases found in GitHub API response"
                print(self.error)
                return False

            latest_version_str = latest_release.get("tag_name", "0.0.0")
            if not latest_version_str:
                 self.error = "Latest release is missing version info (tag_name)."
                 print(self.error)
                 return False
                 
            # Clean up version string if it starts with 'v'
            if latest_version_str.startswith('v'):
                latest_version_str = latest_version_str[1:]

            current_semver = self._parse_semver(self.current_version)
            latest_semver = self._parse_semver(latest_version_str)

            if latest_semver <= current_semver:
                print(f"Device is up-to-date. Current: {self.current_version}, Latest: {latest_version_str}")
                return True # Indicate success, but no download needed

            print(f"Update available: {latest_version_str} (current: {self.current_version})")
            release_to_download = latest_release

        except Exception as e:
            self.error = f"Metadata processing error: {str(e)}"
            print(self.error)
             # Clean up temporary metadata file even on error
            try: uos.remove(self._temp_metadata_path) 
            except: pass
            return False

        # 3. Download Firmware
        if release_to_download:
            # Extract download URL from assets
            assets = release_to_download.get("assets", [])
            firmware_url = None
            expected_sha256 = None
            firmware_filename = None

            for asset in assets:
                if asset.get("name", "").endswith("firmware.tar.zlib"):
                    firmware_url = asset.get("browser_download_url")
                    firmware_filename = asset.get("name")
                    # GitHub API doesn't provide SHA256 directly, we'll skip checksum or handle differently
                    break

            if not firmware_url:
                 self.error = "No firmware asset found in the latest release."
                 print(self.error)
                 return False

            print(f"Step 3: Downloading firmware '{firmware_filename}'...")
            
            # Reset download status before firmware download
            self.download_done = False 
            self.download_started = False
            self.bytes_read = 0
            self.total_size = 0
            
            computed_sha256 = await self._download_file(firmware_url, self.firmware_download_path)

            if self.error or not computed_sha256:
                print(f"Firmware download failed: {self.error}")
                # Optionally remove partially downloaded firmware file
                # try: uos.remove(self.firmware_download_path)
                # except: pass
                return False

            # 4. Verify Checksum (optional, since GitHub API doesn't provide SHA256)
            print("Step 4: Skipping checksum verification (not provided by GitHub API).")
            # If you have a way to include SHA256 in release description or elsewhere, you can implement it here

            print(f"Firmware update downloaded successfully to {self.firmware_download_path}")
            return True # Indicate success, download completed
        
        # Should not be reached if logic is correct, but acts as a fallback
        return False

# Removed BinDownload class
# Removed FirmwareDownloader class

# async def main_async():
#     # WARNING: Replace with your actual Wi-Fi credentials
#     try:
#         await async_connect_wifi('YOUR_SSID', 'YOUR_PASSWORD') 
#     except Exception as e:
#         print(f"Failed to connect to WiFi: {e}")
#         return # Exit if WiFi connection fails

#     updater = FirmwareUpdater( # Use the new class
#         device_model='device-model-A'
#     )
    
#     print("Starting firmware update check...")
#     success = await updater.check_and_update() # Call the main update method
    
#     if success:
#         if updater.error: # Check if success was just "up-to-date"
#              print(f"Firmware check completed: {updater.error}")
#         elif not updater.is_download_done(): # Check if it was just an "up-to-date" success
#              print("Firmware is already up-to-date.")
#         else:
#              print(f"Firmware update successful. New firmware at: {updater.firmware_download_path}")
#     else:
#         print(f"Firmware update process failed: {updater.error}")

# if __name__ == "__main__":
#     try:
#         asyncio.run(main_async())
#     except KeyboardInterrupt:
#         print("Interrupted")
#     finally:
#         asyncio.new_event_loop() # Clear the loop state