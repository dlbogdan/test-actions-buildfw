import uasyncio as asyncio
import machine
import uos

from lib.coresys.manager_system import SystemManager
from lib.coresys.manager_firmware import FirmwareUpdater
from lib.coresys.manager_config import ConfigManager
import lib.coresys.logger as logger

logger.initialize(debug_level=3)
sys_config = ConfigManager("/system-config.json")
device_model = sys_config.get("DEVICE", "MODEL", "generic")
device_name = sys_config.get("DEVICE", "NAME", "micropython-device")
wifi_ssid = sys_config.get("WIFI", "SSID", None)
wifi_password = sys_config.get("WIFI", "PASS", None)
network_timeout_ms = sys_config.get("FIRMWARE", "NETWORK_TIMEOUT_MS", 60000)
# return device_model, device_name, wifi_ssid, wifi_password, network_timeout_ms
system = SystemManager(
    device_name=device_name,
    wifi_ssid=wifi_ssid, 
    wifi_password=wifi_password
    )
    # return system

# Initialize the system manager with injected values

# led_pin = machine.Pin('LED', machine.Pin.OUT)

def create_firmware_updater():
    """Create and initialize firmware updater based on configuration"""
    try:
        # Extract all firmware config values
        core_system_files = sys_config.get("FIRMWARE", "CORE_SYSTEM_FILES", [])
        direct_base_url = sys_config.get("FIRMWARE", "DIRECT_BASE_URL", None)
        github_repo = sys_config.get("FIRMWARE", "GITHUB_REPO", None)
        github_token = sys_config.get("FIRMWARE", "GITHUB_TOKEN", "")
        chunk_size = sys_config.get("FIRMWARE", "CHUNK_SIZE", 2048)
        max_redirects = sys_config.get("FIRMWARE", "MAX_REDIRECTS", 10)
        update_on_boot = sys_config.get("FIRMWARE", "UPDATE_ON_BOOT", True)
        max_failure_attempts = sys_config.get("FIRMWARE", "MAX_FAILURE_ATTEMPTS", 3)
        
        # Define progress callback for boot process
        def boot_progress_callback(stage, progress_percent, message, **kwargs):
            logger.info(f"Progress_CB: [{stage.upper()}] {progress_percent}% - {message}", log_to_file=True)
            if kwargs.get('error'):
                logger.error(f"Progress_CB: Error in {stage}: {kwargs['error']}", log_to_file=True)
        
        # Create updater with all injected values (singleton handles existing instance automatically)
        updater = FirmwareUpdater(
            device_model=device_model,
            github_repo=github_repo,
            github_token=github_token,
            chunk_size=chunk_size,
            max_redirects=max_redirects,
            direct_base_url=direct_base_url,
            core_system_files=core_system_files,
            update_on_boot=update_on_boot,
            max_failure_attempts=max_failure_attempts,
            progress_callback=boot_progress_callback
        )
        
        if direct_base_url:
            logger.info(f"Boot: Firmware updater initialized with direct base URL: {direct_base_url}")
        elif github_repo:
            logger.info(f"Boot: Firmware updater initialized with GitHub repo: {github_repo}")
        else:
            logger.info("Boot: Firmware updater not initialized (no configuration for update source)")
            return None
            
        return updater
        
    except ValueError as e:
        logger.info(f"Boot: Firmware updater not initialized (config error): {e}")
    
    return None

async def restore_system_from_backup(updater):
    """Restore system from backup after failed update"""
    logger.info("Boot: Applying update flag found. Restoring from backup.", log_to_file=True)
    
    if not updater:
        logger.error("Boot: Firmware updater not available for restoration.", log_to_file=True)
        return False
        
    success = await updater.restore_from_backup()
    if success:
        logger.info("Boot: System successfully restored from backup.", log_to_file=True)
    else:
        logger.error(f"Boot: Failed to restore from backup: {updater.error}", log_to_file=True)
    
    return success

async def connect_to_network():
    """Connect to network for update operations"""
    logger.info("Boot: Connecting to network for update...", log_to_file=True)
    
    # led_pin.on()
    system.network.up()
    connected = await system.network.wait_until_up(timeout_ms=network_timeout_ms)
    # led_pin.off()

    if connected:
        ip_address = system.network.get_ip()
        logger.info(f"Boot: Network connected. IP: {ip_address}", log_to_file=True)
    else:
        logger.error("Boot: Network connection failed.", log_to_file=True)
    
    return connected

async def perform_firmware_update_check(updater):
    """Check for available firmware updates"""
    logger.info("Boot: Checking for firmware updates...", log_to_file=True)
    
    is_available, version_str, release_info = await updater.check_update()
    
    if updater.error:
        logger.error(f"Boot: Update check failed: {updater.error}", log_to_file=True)
        return False, None, None
    
    return is_available, version_str, release_info

async def download_and_apply_update(updater, release_info, version_str):
    """Download and apply firmware update"""
    logger.info(f"Boot: Update to version {version_str} available. Downloading...", log_to_file=True)
    
    download_success = await updater.download_update(release_info)
    if not download_success:
        logger.error(f"Boot: Download failed: {updater.error}", log_to_file=True)
        return False
    
    logger.info("Boot: Download successful. Applying update...", log_to_file=True)
    apply_success = await updater.apply_update()
    
    if not apply_success:
        logger.error(f"Boot: Apply failed: {updater.error}", log_to_file=True)
        machine.reset()  # Trigger restoration on next boot
        
    return apply_success

async def reboot_after_update():
    """Reboot device after successful update"""
    logger.info("Boot: Firmware update applied. Rebooting device...", log_to_file=True)
    await asyncio.sleep(1)
    machine.reset()

async def check_update_on_boot():
    """
    Main update check routine - simplified pseudocode-like flow
    
    This function implements a clean, step-by-step update process:
    1. Create firmware updater
    2. Check if system needs restoration from backup
    3. Check if update should be attempted (handles flags internally)
    4. Connect to network
    5. Check for available updates
    6. Download and apply updates if needed
    7. Reboot if successful
    
    All flag management is handled automatically by FirmwareUpdater
    """
    logger.info("Boot: check_update_on_boot sequence started.", log_to_file=True)
    
    # Step 1: Create firmware updater
    logger.info("Boot: Step 1 - Creating firmware updater...", log_to_file=True)
    updater = create_firmware_updater()
    if not updater:
        logger.error("Boot: Firmware updater not available.", log_to_file=True)
        return
    
    # Step 2: Check if system was interrupted during update application
    logger.info("Boot: Step 2 - Checking for interrupted update...", log_to_file=True)
    if updater.check_applying_flag_exists():
        await restore_system_from_backup(updater)
        return
    
    # Step 3: Check if update should be attempted (handles all flag logic internally)
    logger.info("Boot: Step 3 - Checking if update should be attempted...", log_to_file=True)
    should_attempt, message = updater.should_attempt_update()
    if not should_attempt:
        logger.info(f"Boot: {message}", log_to_file=True)
        return

    logger.info(f"Boot: {message}", log_to_file=True)
    
    # Step 4: Connect to network
    logger.info("Boot: Step 4 - Connecting to network...", log_to_file=True)
    if not await connect_to_network():
        return
    
    # Step 5: Check for available updates
    logger.info("Boot: Step 5 - Checking for available updates...", log_to_file=True)
    is_available, version_str, release_info = await perform_firmware_update_check(updater)
    if updater.error and not version_str:
        return  # Check failed completely
    
    update_applied = False
    
    # Step 6: Download and apply update if available
    if is_available:
        logger.info("Boot: Step 6 - Downloading and applying update...", log_to_file=True)
        update_applied = await download_and_apply_update(updater, release_info, version_str)
    else:
        logger.info(f"Boot: Firmware is up-to-date (version: {version_str})", log_to_file=True)
    
    # Step 7: Reboot if update was applied
    if update_applied:
        logger.info("Boot: Step 7 - Rebooting after successful update...", log_to_file=True)
        await reboot_after_update()
    
    logger.info("Boot: check_update_on_boot sequence finished.", log_to_file=True)

# Run the update check on boot (main execution part)
if __name__ == "__main__":
    try:
        # logger.initialize(debug_level=3)
        # system.init()
        asyncio.run(check_update_on_boot())
    except KeyboardInterrupt:
        logger.info("Boot: Process interrupted by user.", log_to_file=True)
    except Exception as e:
        logger.error(f"Boot: Unhandled exception in boot sequence: {e}", log_to_file=True)
    finally:
        logger.info("Boot: Main execution of boot.py finished.", log_to_file=True) 