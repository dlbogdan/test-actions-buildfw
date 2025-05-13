import uasyncio as asyncio
import network

from check_fw_update import FirmwareUpdater

async def async_connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to network...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            await asyncio.sleep(1)
    print('Network config:', wlan.ifconfig())

async def check_update_on_boot():
    # WARNING: Replace with your actual Wi-Fi credentials
    try:
        await async_connect_wifi('Skynet', 'Nightshift!9')
    except Exception as e:
        print(f"Failed to connect to WiFi: {e}")
        return  # Exit if WiFi connection fails
    
    updater = FirmwareUpdater(
        device_model='device-model-A'
    )
    print("Checking for firmware updates on boot...")
    success = await updater.check_and_update()
    if success:
        if updater.error:
            print(f"Firmware check completed: {updater.error}")
        elif not updater.is_download_done():
            print("Firmware is already up-to-date.")
        else:
            print(f"Firmware update successful. New firmware at: {updater.firmware_download_path}")
    else:
        print(f"Firmware update process failed: {updater.error}")

# Run the update check on boot
asyncio.run(check_update_on_boot()) 