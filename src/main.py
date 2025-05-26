import machine
import utime
import uasyncio as asyncio
import gc
from lib.coresys.manager_system import SystemManager
from lib.coresys.manager_firmware import FirmwareUpdater
from lib.coresys.manager_config import ConfigManager

# Onboard LED (typically GP25 for Pico, or 'LED' for Pico W)
led_pin = machine.Pin('LED', machine.Pin.OUT)

def create_firmware_updater():
    """Create and initialize firmware updater based on configuration"""
    try:
        # Initialize configuration
        config = ConfigManager("/config.json")
        
        # Extract all firmware config values
        device_model = config.get("SYS.DEVICE", "MODEL", "generic")
        core_system_files = config.get("SYS.FIRMWARE", "CORE_SYSTEM_FILES", [])
        direct_base_url = config.get("SYS.FIRMWARE", "DIRECT_BASE_URL", None)
        github_repo = config.get("SYS.FIRMWARE", "GITHUB_REPO", None)
        github_token = config.get("SYS.FIRMWARE", "GITHUB_TOKEN", "")
        chunk_size = config.get("SYS.FIRMWARE", "CHUNK_SIZE", 2048)
        max_redirects = config.get("SYS.FIRMWARE", "MAX_REDIRECTS", 10)
        update_on_boot = config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", True)
        max_failure_attempts = config.get("SYS.FIRMWARE", "MAX_FAILURE_ATTEMPTS", 3)
        
        # Create updater with all injected values
        updater = FirmwareUpdater(
            device_model=device_model,
            github_repo=github_repo,
            github_token=github_token,
            chunk_size=chunk_size,
            max_redirects=max_redirects,
            direct_base_url=direct_base_url,
            core_system_files=core_system_files,
            update_on_boot=update_on_boot,
            max_failure_attempts=max_failure_attempts
        )
        
        if direct_base_url:
            print(f"Main: Firmware updater initialized with direct base URL: {direct_base_url}")
        elif github_repo:
            print(f"Main: Firmware updater initialized with GitHub repo: {github_repo}")
        else:
            print("Main: Firmware updater not initialized (no configuration for update source)")
            return None
            
        return updater
        
    except ValueError as e:
        print(f"Main: Firmware updater not initialized (config error): {e}")
    
    return None

async def main():
    try:
        # Initialize the system manager as a singleton
        print("Main: Initializing system components...")
        print(f"free memory: {gc.mem_free()}")

        # Initialize configuration first
        config = ConfigManager("/config.json")
        
        # Extract config values for injection
        device_name = config.get("SYS.DEVICE", "NAME", "micropython-device")
        wifi_ssid = config.get("SYS.WIFI", "SSID", None)
        wifi_password = config.get("SYS.WIFI", "PASS", None)
        
        # Initialize the system manager with injected values
        system = SystemManager(
            device_name=device_name,
            wifi_ssid=wifi_ssid, 
            wifi_password=wifi_password,
            debug_level=3
        )
        
        # Bring up network and wait for connection
        system.log.info("Main: Starting network connection...")
        system.network.up()
        
        # Wait for WiFi with timeout
        if await system.network.wait_until_up(timeout_ms=60000):
            system.log.info(f"Main: Network connected with IP: {system.network.get_ip()}")
            
            # Check for firmware updates if network is connected
            system.log.info("Main: Initializing firmware updater...")
            firmware_updater = create_firmware_updater()
            
            if firmware_updater:
                system.log.info("Main: Checking for firmware updates...")
                update_available, new_version, release_info = await firmware_updater.check_update()
                
                if firmware_updater.error:
                    system.log.error(f"Main: Update check failed: {firmware_updater.error}")
                elif update_available:
                    system.log.info(f"Main: Firmware update available: {new_version}")
                else:
                    system.log.info(f"Main: Firmware is up to date (version: {new_version})")
            else:
                system.log.warning("Main: Firmware updater not available - check configuration")
        else:
            system.log.warning("Main: Could not connect to network")
        
        # Main application loop
        system.log.info("Main: Entering main application loop")
        print(f"free memory: {gc.mem_free()}")
        while True:
            # No need to call system.update() anymore, WiFi is managed in background
            
            # Toggle LED as a heartbeat
            led_pin.toggle()
            
            # Wait a bit
            await asyncio.sleep(1)
            
    except Exception as e:
        print(f"Error: {e}")
        # Don't try to use system.log here as it might be None if initialization failed

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Fatal error: {e}")
        machine.reset() 