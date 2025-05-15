import machine
import utime
import uasyncio as asyncio
from lib.manager_system import SystemManager

# Onboard LED (typically GP25 for Pico, or 'LED' for Pico W)
led_pin = machine.Pin('LED', machine.Pin.OUT)

async def main():
    try:
        # Initialize the system manager as a singleton
        print("Main: Initializing system components...")
        system = SystemManager(config_file="/config.json", debug_level=3)
        system.init()
        
        if system.network:
            system.log.info("Main: Waiting for WiFi connection...")
            
            # Wait for WiFi with timeout
            if await system.wait_for_network(timeout_ms=60000):
                system.log.info(f"Main: WiFi connected with IP: {system.network.get_ip()}")
                
                # Check for firmware updates if WiFi is connected
                if system.firmware:
                    system.log.info("Main: Checking for firmware updates...")
                    update_available, new_version, release_info = await system.check_firmware_update()
                    
                    if update_available:
                        system.log.info(f"Main: Firmware update available: {new_version}")
                        
                        # Download the update
                        # system.log.info("Main: Downloading firmware update...")
                        # download_success = await system.download_firmware_update(release_info)
                        
                        # if download_success:
                        #     system.log.info("Main: Firmware download complete. Ready to apply.")
                            
                            # Apply the update (uncomment to enable)
                            # system.log.info("Main: Applying firmware update...")
                            # await system.apply_firmware_update()
                    else:
                        system.log.info("Main: Firmware is up to date")
            else:
                system.log.warning("Main: Could not connect to WiFi")
        
        # Main application loop
        system.log.info("Main: Entering main application loop")
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