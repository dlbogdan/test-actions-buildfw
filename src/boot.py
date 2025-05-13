import uasyncio as asyncio
import time
# Ensure your lib modules are accessible, e.g., if src/lib/ then:
# import sys
# sys.path.append('lib') # Or adjust as per your project structure if MicroPython needs it

from lib.manager_config import ConfigManager
from lib.manager_wifi import WiFiManager
from lib.manager_logger import Logger # Logger is used by other managers
from check_fw_update import FirmwareUpdater # Assuming check_fw_update.py is in the same dir or accessible

# Initialize logger first as other managers might use it
# Logger() is a singleton, so this gets/creates the instance
logger = Logger() 
logger.info("Boot sequence started.")

CONFIG_FILE = "/config.json" # Standard config file name
config_manager = ConfigManager(CONFIG_FILE)

# async def async_connect_wifi(ssid, password): # REMOVED - WiFiManager will handle this
#     wlan = network.WLAN(network.STA_IF)
#     wlan.active(True)
#     if not wlan.isconnected():
#         print('Connecting to network...')
#         wlan.connect(ssid, password)
#         while not wlan.isconnected():
#             await asyncio.sleep(1)
#     print('Network config:', wlan.ifconfig())

async def check_update_on_boot():
    logger.info("Boot: Initializing WiFi connection process...")
    
    # Get WiFi credentials and device settings from ConfigManager
    wifi_ssid = config_manager.get("WIFI", "SSID", "YOUR_SSID_DEFAULT") # Provide a default SSID
    wifi_password = config_manager.get("WIFI", "PASS", "YOUR_PASSWORD_DEFAULT") # Provide a default password
    device_hostname = config_manager.get("device", "hostname", "MicroPythonDevice")

    if wifi_ssid == "YOUR_SSID_DEFAULT":
        logger.warning("Boot: Using default SSID. Please configure WiFi credentials in config.json.")

    wifi_manager = WiFiManager(wifi_ssid, wifi_password, device_hostname)

    logger.info("Boot: Attempting to connect to WiFi...")
    connect_timeout_ms = 60000  # 60 seconds timeout for connection
    start_connect_time = time.ticks_ms()

    while not wifi_manager.is_connected():
        wifi_manager.update() # Let WiFiManager handle its non-blocking connection logic
        if time.ticks_diff(time.ticks_ms(), start_connect_time) > connect_timeout_ms:
            logger.error("Boot: WiFi connection timed out.")
            break 
        await asyncio.sleep_ms(250) # Yield control, check status periodically

    if not wifi_manager.is_connected():
        logger.error("Boot: Failed to connect to WiFi. Skipping firmware update check.")
        return # Exit if WiFi connection fails
    
    logger.info(f"Boot: WiFi connected. IP: {wifi_manager.get_ip()}")

    # Get FirmwareUpdater settings from ConfigManager
    device_model = config_manager.get("DEVICE", "MODEL", "device-model-A")
    base_url = config_manager.get("FIRMWARE", "BASE_URL", "https://api.github.com/repos/dlbogdan/test-actions-buildfw/releases")
    github_token = config_manager.get("FIRMWARE", "GITHUB_TOKEN", "")
    
    updater = FirmwareUpdater(
        device_model=device_model,
        base_url=base_url,
        github_token=github_token
    )

    logger.info("Boot: Starting firmware update check...")
    try:
        success = await updater.check_and_update()
        if success:
            if updater.error:
                logger.info(f"Boot: Firmware check completed with message: {updater.error}")
            elif not updater.is_download_done():
                logger.info("Boot: Firmware is already up-to-date.")
            else:
                logger.info(f"Boot: Firmware download successful. New firmware at: {updater.firmware_download_path}")
                await updater.apply_update()
                logger.info("Boot: Consider restarting the device to apply the update if not done automatically.")
        else:
            logger.error(f"Boot: Firmware update process failed: {updater.error if updater.error else 'Unknown reason'}")
    except Exception as e:
        logger.error(f"Boot: An exception occurred during firmware update check: {e}")

# Run the update check on boot
if __name__ == "__main__":
    try:
        asyncio.run(check_update_on_boot())
    except KeyboardInterrupt:
        logger.info("Boot: Process interrupted by user.")
    except Exception as e:
        logger.fatal("Boot MAIN", f"Unhandled exception in boot sequence: {e}", resetmachine=False) # Or True if desired
    finally:
        logger.info("Boot: Main execution finished. Consider asyncio.new_event_loop() if issues persist after interrupts.")
        # For MicroPython, explicit new_event_loop might not always be needed after run completes
        # or if the script ends here. 