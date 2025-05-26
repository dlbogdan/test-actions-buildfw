#!/usr/bin/env python3
"""
Example usage of the singleton FirmwareUpdater with progress callback support.
"""

import asyncio
from src.lib.coresys.manager_firmware import FirmwareUpdater

def progress_callback(stage, progress_percent, message, **kwargs):
    """Example progress callback function."""
    print(f"[{stage.upper()}] {progress_percent:3d}% - {message}")
    
    # Handle additional information
    if 'current_version' in kwargs and 'latest_version' in kwargs:
        print(f"    Current: {kwargs['current_version']}, Latest: {kwargs['latest_version']}")
    
    if 'bytes_downloaded' in kwargs and 'total_bytes' in kwargs:
        print(f"    Downloaded: {kwargs['bytes_downloaded']}/{kwargs['total_bytes']} bytes")
    
    if 'error' in kwargs:
        print(f"    ERROR: {kwargs['error']}")

async def main():
    """Example usage of FirmwareUpdater singleton."""
    
    # First initialization - creates the singleton
    print("=== Creating FirmwareUpdater (first time) ===")
    updater1 = FirmwareUpdater(
        device_model="example-device",
        github_repo="user/firmware-repo",
        github_token="your-token-here",
        progress_callback=progress_callback
    )
    print(f"Updater1 ID: {id(updater1)}")
    
    # Second initialization - returns the same instance (parameters ignored except progress_callback)
    print("\n=== Getting FirmwareUpdater (second time) ===")
    def second_callback(stage, progress_percent, message, **kwargs):
        print(f"SECOND CALLBACK: [{stage}] {progress_percent}% - {message}")
    
    updater2 = FirmwareUpdater(
        device_model="different-device",  # This will be ignored
        github_repo="different/repo",     # This will be ignored
        progress_callback=second_callback # This will be updated
    )
    print(f"Updater2 ID: {id(updater2)}")
    print(f"Same instance: {updater1 is updater2}")
    print(f"Device model: {updater2.device_model}")  # Still "example-device"
    print("Progress callback has been updated to second_callback")
    
    # Using get_instance() method
    print("\n=== Using get_instance() method ===")
    updater3 = FirmwareUpdater.get_instance()
    if updater3:
        print(f"Updater3 ID: {id(updater3)}")
        print(f"Same instance: {updater1 is updater3}")
    else:
        print("No instance exists yet")
    
    # Updating progress callback
    print("\n=== Updating progress callback ===")
    def new_callback(stage, progress_percent, message, **kwargs):
        print(f"NEW CALLBACK: [{stage}] {progress_percent}% - {message}")
    
    updater1.set_progress_callback(new_callback)
    
    # Example of checking for updates (would trigger progress callbacks)
    print("\n=== Example update check (simulated) ===")
    try:
        # This would normally check for real updates
        # is_available, version, release = await updater1.check_update()
        print("Update check would happen here with progress callbacks")
    except Exception as e:
        print(f"Update check failed: {e}")
    
    # Reset instance for testing
    print("\n=== Resetting singleton instance ===")
    FirmwareUpdater.reset_instance()
    
    # After reset, get_instance returns None
    updater4 = FirmwareUpdater.get_instance()
    print(f"After reset, get_instance(): {updater4}")
    
    # New instance can be created after reset
    updater5 = FirmwareUpdater(
        device_model="new-device",
        direct_base_url="https://firmware.example.com"
    )
    print(f"New instance after reset: {id(updater5)}")
    print(f"Device model: {updater5.device_model}")

if __name__ == "__main__":
    asyncio.run(main()) 