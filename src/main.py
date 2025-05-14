import os
import machine
import utime
import uasyncio as asyncio

# Ensure your lib modules are accessible
# import sys
# sys.path.append('lib') # Or adjust as per your project structure
from lib.manager_logger import Logger 
logger = Logger(3)

from lib.manager_config import ConfigManager
from check_fw_update import FirmwareUpdater
# Logger can be useful, initialize if needed or rely on FirmwareUpdater's prints

from lib.manager_wifi import WiFiManager



# Onboard LED is typically GP25 for Pico, or 'LED' for Pico W
# Use Pin.board.LED if available and targeting Pico W, otherwise use 25
# led_pin = machine.Pin('LED', machine.Pin.OUT) # For Pico W
led_pin = machine.Pin('LED', machine.Pin.OUT)    # For Pico standard

async def connect_to_wifi():
    config_manager = ConfigManager("/config.json") # Assuming config.json is in root
    wifi_ssid = config_manager.get("WIFI", "SSID") # Provide a default SSID
    wifi_password = config_manager.get("WIFI", "PASS") # Provide a default password
    device_hostname = config_manager.get("DEVICE", "HOSTNAME")
    print(f"device_hostname: {device_hostname}") 
    wifi_manager = WiFiManager(wifi_ssid, wifi_password, device_hostname)

    logger.info("Boot: Attempting to connect to WiFi...")
    connect_timeout_ms = 60000  # 60 seconds timeout for connection
    start_connect_time = utime.ticks_ms()

    while not wifi_manager.is_connected():
        wifi_manager.update() # Let WiFiManager handle its non-blocking connection logic
        if utime.ticks_diff(utime.ticks_ms(), start_connect_time) > connect_timeout_ms:
            logger.error("Boot: WiFi connection timed out.")
            break 
        await asyncio.sleep_ms(250) # Yield control, check status periodically

    if not wifi_manager.is_connected():
        logger.error("Boot: Failed to connect to WiFi. Skipping firmware update check.")
        return # Exit if WiFi connection fails
    
    logger.info(f"Boot: WiFi connected. IP: {wifi_manager.get_ip()}")

async def check_firmware_update_status():
    print("Main: Initializing configuration for update check...")
    config_manager = ConfigManager("/config.json") # Assuming config.json is in root

    # Get FirmwareUpdater settings from ConfigManager
    # Provide sensible defaults if config might be missing these
    device_model = config_manager.get("DEVICE", "MODEL")
    base_url = config_manager.get("FIRMWARE", "BASE_URL")
    github_token = config_manager.get("FIRMWARE", "GITHUB_TOKEN") # Optional


    updater = FirmwareUpdater(
        device_model=device_model,
        base_url=base_url,
        github_token=github_token
    )

    print("Main: Checking for firmware update availability...")
    try:
        is_update_available, new_version, _ = await updater.check_update() # Unpack release_info, not used here
        if updater.error:
            print(f"Main: Error during update check: {updater.error}")
        elif is_update_available:
            print(f"Main: An update to version {new_version} is available.")
            # You can add any logic here based on this information
            # e.g., notify user, set a flag, etc.
        else:
            print(f"Main: Firmware is up-to-date (or no newer version found). Latest checked: {new_version}")

    except Exception as e:
        print(f"Main: An exception occurred during the update check: {e}")

# Example of how to run the check (e.g., once at startup)
# You might integrate this differently depending on your application flow.
async def main():
    try:
        # Run the check once
        await connect_to_wifi()
        await check_firmware_update_status()
        print("Main: Proceeding with main application logic (LED blinking)...")
        while True:
            led_pin.toggle()
            utime.sleep(1) # Wait for 1 second
    except Exception as e:
        print(f"Main: Error running async update check: {e}")


if __name__ == "__main__":
    asyncio.run(main())


