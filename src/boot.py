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
    # Check for interrupted update first
    system.log.info("Boot sequence started with SystemManager.")
    #if main.py exists and is not empty, and SYS.FIRMWARE.UPDATE_ON_BOOT is false, skip the firmware update check
    try:
        stat_result = uos.stat("main.py")
        main_file_size = stat_result[6]  # Size is at index 6 of the stat result tuple
        if not system.config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", False) and main_file_size > 0:
            system.log.info("Boot: Skipping firmware update check on startup.")
            return
    except OSError:
        # File doesn't exist or can't be accessed, continue with update check
        pass
    
    try:
        if '__updating' in uos.listdir('/'):
            # Read counter from file
            with open('/__updating', 'r') as f:
                counter_str = f.read().strip()
                counter = int(counter_str or '0') + 1
                
            system.log.warning(f"Boot: Detected interrupted update (attempt {counter})")
                
            if counter >= 3:
                system.log.error("Boot: Too many update failures, disabling auto-updates")
                # Disable auto-updates to prevent boot loops
                try:
                    # Update config to disable auto-updates
                    # First get the existing configuration
                    _ = system.config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", False)
                    # Then explicitly set it to False
                    system.config.set("SYS.FIRMWARE", "UPDATE_ON_BOOT", False)
                    system.log.info("Boot: Disabled auto-updates to prevent boot loops")
                except Exception as e:
                    system.log.error(f"Boot: Failed to disable auto-updates: {e}")
                
                # Remove update flag file
                uos.remove('/__updating')
                
                # Restore from backup if available
                system.log.info("Boot: Attempting to restore from backup...")
                try:
                    # Initialize firmware updater if not already initialized
                    if system.firmware.init():
                        # Attempt restoration
                        restore_success = await system.firmware.restore_from_backup()
                        if restore_success:
                            system.log.info("Boot: System successfully restored from backup")
                            # Reboot the system to apply the restored state
                            system.log.info("Boot: Rebooting to apply restored system...")
                            await asyncio.sleep(1)  # Brief pause for logs to flush
                            machine.reset()
                        else:
                            system.log.error(f"Boot: Failed to restore from backup: {system.firmware.error}")
                    else:
                        system.log.error("Boot: Could not initialize firmware manager for restoration")
                except Exception as e:
                    system.log.error(f"Boot: Error during restoration attempt: {e}")
                
                # Continue with boot even if restore failed
                return
            else:
                # Update counter for next attempt
                with open('/__updating', 'w') as f:
                    f.write(str(counter))
                
                # Continue with update process
                system.log.info(f"Boot: Retrying update (attempt {counter})")
    except Exception as e:
        system.log.error(f"Boot: Error handling interrupted update: {e}")
    
    # Check if firmware updates on startup are enabled
    

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
            # Create update flag file
            with open('/__updating', 'w') as f:
                f.write('0')  # Initial counter
                
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
                    # Remove update flag file to indicate successful completion
                    uos.remove('/__updating')
                    
                    machine.reset()
                else:
                    system.log.error("Boot: Firmware download failed.")
                    # Remove update flag file since we failed before the critical phase
                    uos.remove('/__updating')
            else:
                system.log.info(f"Boot: Firmware is already up-to-date.")
                # Remove update flag file since no update was needed
                uos.remove('/__updating')

        except Exception as e:
            system.log.error(f"Boot: An exception occurred during firmware update check: {e}")
            # Do not remove the update flag file on unexpected errors
            # It will trigger the recovery on next boot
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