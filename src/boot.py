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
    system.log.info("Boot: check_update_on_boot sequence started.",log_to_file=True)
    update_flag_path = '/__updating'
    applying_flag_path = '/__applying'
    # check if the applying flag file exists
    try:
        if uos.stat(applying_flag_path):
            system.log.info("Boot: Applying update flag found. Restoring from backup.",log_to_file=True)
            if system.firmware.init():
                restore_success = await system.firmware.restore_from_backup()
                if restore_success:
                    system.log.info("Boot: System successfully restored from backup. Rebooting...",log_to_file=True)
                    await asyncio.sleep(1)
                    # remove the applying flag file
                else:
                    system.log.error(f"Boot: Failed to restore from backup: {system.firmware.error}",log_to_file=True)
            else:
                system.log.error("Boot: Firmware manager init failed for restoration.",log_to_file=True)
            # remove the applying flag file
            system.log.info("Boot: Removing applying flag file...",log_to_file=True)
            try:
                uos.remove(applying_flag_path)
            except OSError:
                pass
            return
    except Exception as e:
        system.log.info("Boot: No applying flag file found. Proceeding with update check.",log_to_file=True)
    # 1. Check if updates are globally enabled by config.
    # Default to True if UPDATE_ON_BOOT is not explicitly set or main.py is missing.
    perform_update_check_based_on_config = True
    # try:
    #     uos.stat("main.py") # Check if main.py exists
    #     if not system.config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", True):
    #         system.log.info("Boot: SYS.FIRMWARE.UPDATE_ON_BOOT is False (main.py exists). Skipping update check.",log_to_file=True)
    #         perform_update_check_based_on_config = False
    # except OSError: # main.py doesn't exist
    #     system.log.info("Boot: main.py not found.",log_to_file=True)
    #     if not system.config.get("SYS.FIRMWARE", "UPDATE_ON_BOOT", True):
    #         # This case is unusual: main.py missing AND updates disabled.
    #         # For safety, respect the "disabled" flag if explicitly set.
    #         system.log.warning("Boot: main.py missing AND SYS.FIRMWARE.UPDATE_ON_BOOT is False. Skipping update check.",log_to_file=True)
    #         perform_update_check_based_on_config = False
    #     else:
    #         system.log.info("Boot: main.py missing, SYS.FIRMWARE.UPDATE_ON_BOOT is True or not set. Proceeding with update logic.",log_to_file=True)
    #         perform_update_check_based_on_config = True


    if not perform_update_check_based_on_config:
        try: # Cleanup any old flag if updates are now disabled.
            if update_flag_path[1:] in uos.listdir('/'):
                uos.remove(update_flag_path)
                system.log.info(f"Boot: Removed old update flag '{update_flag_path}' as updates are disabled.",log_to_file=True)
        except Exception: # OSError if not found, or other errors during listdir/remove
            pass
        return

    # 2. Handle update attempt counter
    failure_counter = 0
    read_success = False # Flag to track if counter was successfully read from file
    try:
        # uos.stat() will raise OSError if file doesn't exist
        stat_info = uos.stat(update_flag_path)
        # File exists, now check size
        if stat_info[6] > 0: # Index 6 is st_size
            with open(update_flag_path, 'r') as f:
                content = f.read().strip()
                if content: # Ensure content is not empty after stripping
                    try:
                        failure_counter = int(content)
                        system.log.info(f"Boot: Successfully read update flag '{update_flag_path}'. Value: {failure_counter}")
                        read_success = True
                    except ValueError:
                        system.log.warning(f"Boot: Content of '{update_flag_path}' ('{content}') is not a valid integer. Resetting to 0.")
                        failure_counter = 0 # Default to 0 if content is not int
                else: # File was present and stat'd size > 0, but read as empty/whitespace
                    system.log.warning(f"Boot: Update flag '{update_flag_path}' contained no parsable content after read/strip. Resetting to 0.")
                    failure_counter = 0 
        else: # File exists but is empty (size 0 according to stat)
            system.log.warning(f"Boot: Update flag '{update_flag_path}' exists but is empty (size 0). Resetting to 0 failures.")
            failure_counter = 0
            # Optional: Clean up empty flag file
            # try:
            #     uos.remove(update_flag_path)
            #     system.log.info(f"Boot: Removed empty update flag '{update_flag_path}'.")
            # except OSError:
            #     pass

    except OSError as e_stat:
        if e_stat.args[0] == 2: # ENOENT (No such file or directory) for uos.stat
            system.log.info(f"Boot: Update flag '{update_flag_path}' not found via uos.stat. Starting with 0 failures.")
            # failure_counter remains 0, read_success remains False
        else: # Other OSError during stat (e.g., permission denied, I/O error)
            system.log.warning(f"Boot: OSError ({e_stat.args[0]}) checking update flag '{update_flag_path}' with uos.stat: {e_stat}. Resetting to 0 failures.")
            failure_counter = 0
    except Exception as e_generic: # Catch any other unexpected errors during open/read if stat passed
        system.log.warning(f"Boot: Generic error processing update counter file '{update_flag_path}' (after stat): {e_generic}. Resetting to 0.")
        failure_counter = 0

    # For debugging, explicitly log if we are proceeding with a default 0 when no successful read occurred.
    # This helps distinguish "not found" (which is fine for first run) from "found but failed to parse".
    if not read_success and failure_counter == 0 :
        # This log will appear if the file wasn't found, or if it was found but was empty or unparseable, leading to counter = 0.
        system.log.info(f"Boot: Proceeding with failure_counter = 0 (flag not found, empty, or unreadable).")
    # --- End of revised counter reading ---

    # 3. Check if max failure attempts reached
    if failure_counter >= 3:
        system.log.error(f"Boot: Max update failure attempts ({failure_counter}) reached.",log_to_file=True)
        try:
            system.config.set("SYS.FIRMWARE", "UPDATE_ON_BOOT", False)
            system.log.info("Boot: SYS.FIRMWARE.UPDATE_ON_BOOT set to False to prevent further attempts.",log_to_file=True)
        except Exception as e:
            system.log.error(f"Boot: Failed to set UPDATE_ON_BOOT to False in config: {e}",log_to_file=True)
        
        try:
            uos.remove(update_flag_path)
            system.log.info(f"Boot: Removed update flag file '{update_flag_path}'.",log_to_file=True)
        except OSError:
            system.log.warning(f"Boot: Could not remove update flag '{update_flag_path}' (may not exist).",log_to_file=True)

        # system.log.info("Boot: Attempting to restore from backup due to repeated update failures...",log_to_file=True)
        # if system.firmware.init():
        #     restore_success = await system.firmware.restore_from_backup()
        #     if restore_success:
        #         system.log.info("Boot: System successfully restored from backup. Rebooting...",log_to_file=True)
        #         await asyncio.sleep(1)
        #         machine.reset()
        #     else:
        #         err_msg = system.firmware.error if hasattr(system.firmware, 'error') and system.firmware.error else 'Unknown error'
        #         system.log.error(f"Boot: Failed to restore from backup: {err_msg}",log_to_file=True)
        # else:
        #     system.log.error("Boot: Firmware manager init failed for restoration.",log_to_file=True)
        system.log.info("Boot: Continuing regular boot after max update attempts / restoration attempt.",log_to_file=True)
        return

    # --- START OF AN UPDATE ATTEMPT (failure_counter < 3) ---
    # Increment counter for THIS attempt and write to file.
    # This signifies that an update *process* is starting.
    current_attempt_failure_count_for_next_boot = failure_counter + 1
    try:
        with open(update_flag_path, 'w') as f:
            f.write(str(current_attempt_failure_count_for_next_boot))
        system.log.info(f"Boot: Starting update attempt. Failure counter for next boot set to {current_attempt_failure_count_for_next_boot} in '{update_flag_path}'.",log_to_file=True)
    except Exception as e:
        system.log.error(f"Boot: Critical error writing update counter to '{update_flag_path}': {e}. Aborting update for this boot.",log_to_file=True)
        return 

    update_journey_successful = False # True if this boot cycle's update actions were successful
    
    # Variables to track specific stages for final decision making
    _is_available = False
    _download_ok = False
    _apply_ok = False

    # Network Connection
    system.log.info("Boot: Connecting to network for update...",log_to_file=True)
    led_pin.on()
    system.network.up()
    network_connected = await system.network.wait_until_up(timeout_ms=60000)
    led_pin.off()

    if not network_connected:
        system.log.error("Boot: Network connection failed. Update attempt failed.",log_to_file=True)
        # update_journey_successful remains False
    else:
        ip_address = system.network.get_ip()
        system.log.info(f"Boot: Network connected. IP: {ip_address}",log_to_file=True)

        if not system.firmware.init():
            system.log.warning("Boot: Firmware updater init failed. Update attempt failed.",log_to_file=True)
            # update_journey_successful remains False
        else:
            try:
                system.log.info("Boot: Checking for firmware updates...",log_to_file=True)
                _is_available, version_str, release_info = await system.firmware.check_update()

                if system.firmware.error:
                    system.log.error(f"Boot: check_update failed: {system.firmware.error}.",log_to_file=True)
                elif version_str is None and not _is_available: # Indicates server was likely unreachable
                    system.log.error("Boot: Server unreachable or no metadata during check_update.",log_to_file=True)
                elif _is_available:
                    system.log.info(f"Boot: Update to version {version_str} available. Downloading...",log_to_file=True)
                    _download_ok = await system.firmware.download_update(release_info)
                    if _download_ok:
                        system.log.info("Boot: Download successful. Applying update...",log_to_file=True)
                        _apply_ok = await system.firmware.apply_update() # Returns True on success
                        if _apply_ok:
                            system.log.info("Boot: apply_update successful.",log_to_file=True)
                            update_journey_successful = True # SUCCESSFUL UPDATE APPLIED
                        else:
                            system.log.error(f"Boot: apply_update failed: {system.firmware.error}.",log_to_file=True)
                            # we keep the applying flag file to trigger the restoration from backup
                            machine.reset()
                    else: # Download failed
                        system.log.error(f"Boot: Firmware download failed: {system.firmware.error}.",log_to_file=True)
                else: # Not _is_available and version_str is not None (confirmed up-to-date)
                    system.log.info(f"Boot: Firmware is up-to-date (current: {system.firmware._updater.current_version if hasattr(system.firmware, '_updater') and system.firmware._updater else 'N/A'}, server confirmed: {version_str}).")
                    update_journey_successful = True # SUCCESSFUL (no action needed, confirmed up-to-date)
            
            except Exception as e:
                system.log.error(f"Boot: Exception during firmware update operations: {e}.")
                # update_journey_successful remains False

    # Post-attempt actions based on update_journey_successful
    if update_journey_successful:
        system.log.info(f"Boot: Update attempt successful or confirmed up-to-date. Removing flag '{update_flag_path}'.",log_to_file=True)
        try:
            uos.remove(update_flag_path)
        except OSError: # File might not exist or already removed
            system.log.warning(f"Boot: Could not remove update flag '{update_flag_path}' (may already be gone).",log_to_file=True)
        
        if _is_available and _download_ok and _apply_ok: # Check if an actual update was applied
            system.log.info("Boot: Firmware update applied. Rebooting device...",log_to_file=True)
            await asyncio.sleep(1) # Brief pause for logs
            machine.reset()
        # Else (if up-to-date), no reboot needed, just continue normal boot.
    else: # update_journey_successful is False
        system.log.warning(f"Boot: Update attempt failed. Flag '{update_flag_path}' (value: {current_attempt_failure_count_for_next_boot}) retained for next boot cycle.",log_to_file=True)

    system.log.info("Boot: check_update_on_boot sequence finished.",log_to_file=True)

# Run the update check on boot (main execution part)
if __name__ == "__main__":
    try:
        # Initialize system services like network if they are not auto-started by SystemManager
        # This depends on your SystemManager's __init__ or a dedicated setup method.
        # For this script, assuming network.up() is handled within check_update_on_boot as needed.
        asyncio.run(check_update_on_boot())
    except KeyboardInterrupt:
        system.log.info("Boot: Process interrupted by user.",log_to_file=True)
    except Exception as e:
        # Use system.log.fatal if it includes tracebacks or more detailed error info
        system.log.error(f"Boot MAIN: Unhandled exception in boot sequence: {e}",log_to_file=True)
        # Consider if a reset is safe here or if it could cause a loop with certain errors.
        # For now, log and let it proceed to whatever MicroPython does after boot.py.
    finally:
        system.log.info("Boot: Main execution of boot.py finished.",log_to_file=True)
        # Consider if network.down() or other cleanup is needed here.
        # It's generally good to leave network up if other parts of the app might need it immediately. 