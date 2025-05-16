import uasyncio as asyncio
import machine
import uos
# Ensure your lib modules are accessible, e.g., if src/lib/ then:
# import sys
# sys.path.append('lib') # Or adjust as per your project structure if MicroPython needs it

from lib.coresys.manager_system import SystemManager

# Initialize the system manager
system = SystemManager(config_file="/config.json",debug_level=3)

led_pin = machine.Pin('LED', machine.Pin.OUT)

async def check_update_on_boot():
    # Start boot sequence
    system.log.info("Boot sequence started with SystemManager.")
    
    # Check if updates on boot are disabled and main.py exists
    try:
        stat_result = uos.stat("main.py")
        main_file_size = stat_result[6]  # Size is at index 6 of the stat result tuple
        if not system.config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", False) and main_file_size > 0:
            system.log.info("Boot: Skipping firmware update check on startup.")
            return
    except OSError:
        # File doesn't exist or can't be accessed, continue with update check
        pass
    
    # Connect to network
    system.log.info("Boot: Bringing up network connection...")
    led_pin.on()

    system.network.up()
    
    # Wait for network connection with timeout
    if not await system.network.wait_until_up(timeout_ms=60000):
        system.log.error("Boot: Network connection failed. Skipping firmware update check.")
        return
    
    # Continue only if network is connected
    ip_address = system.network.get_ip()
    system.log.info(f"Boot: Network connected. IP: {ip_address}")
    led_pin.off()
    
    # Check for firmware updates
    system.log.info("Boot: Initializing firmware updater...")
    if system.firmware.init():
        system.log.info("Boot: Starting firmware update check...")
        try:
            is_available, version_str, release_info = await system.firmware.check_update()

            if is_available:
                system.log.info(f"Boot: Update to version {version_str} is available. Proceeding to download.")
                
                # Download update
                download_success = await system.firmware.download_update(release_info)
                
                if download_success:
                    system.log.info("Boot: Firmware download successful. Proceeding to apply.")
                    
                    # Apply update (this may reboot the device)
                    await system.firmware.apply_update()
                    
                    # If we reach here, the update was successful
                    system.log.info("Boot: Firmware update applied successfully.")
                    machine.reset()
                else:
                    system.log.error("Boot: Firmware download failed.")
            else:
                system.log.info(f"Boot: Firmware is already up-to-date.")

        except Exception as e:
            system.log.error(f"Boot: An exception occurred during firmware update check: {e}")
            # FirmwareUpdater will handle the update flag internally
    else:
        system.log.warning("Boot: Firmware updater not available - check configuration")

# Run the update check on boot
if __name__ == "__main__":
    try:
        asyncio.run(check_update_on_boot())
    except KeyboardInterrupt:
        system.log.info("Boot: Process interrupted by user.")
    except Exception as e:
        system.log.fatal("Boot MAIN", f"Unhandled exception in boot sequence: {e}", resetmachine=False)
    finally:
        system.log.info("Boot: Main execution finished.")
        # Disconnect network if needed
        # system.disconnect_network() 