import time
import network
import lib.coresys.logger as logger

# logger = Logger()

# --- WiFi Management ---
# class WiFiManager: ... (NO CHANGES NEEDED, connection check is non-blocking) ...
class WiFiManager:
    """Handles non-blocking Wi-Fi connection and status monitoring."""
    STATUS_DISCONNECTED = 0
    STATUS_CONNECTING = 1
    STATUS_CONNECTED = 2
    STATUS_ERROR = 3 # E.g., WLAN interface init failed

    def __init__(self, ssid, password, hostname,retry_interval_ms=10000):
        self.ssid = ssid
        self.password = password
        self.hostname = hostname
        self.retry_interval_ms = retry_interval_ms
        # self._wlan = None
        self._status = WiFiManager.STATUS_DISCONNECTED
        self._last_attempt_time = 0
        self._ip_address = None

        try:
            self._wlan = network.WLAN(network.STA_IF)
            self._wlan.active(False) # Start inactive
            network.hostname(self.hostname)
            logger.info("WiFiManager: WLAN interface initialized.")
            # Set an initial status based on whether credentials are provided
            if self.ssid:
                 self._status = WiFiManager.STATUS_DISCONNECTED
                 logger.info("WiFiManager: Ready to connect.")
            else:
                 self._status = WiFiManager.STATUS_DISCONNECTED # Or maybe a dedicated NO_CREDS status?
                 logger.error("WiFiManager: No SSID configured, will remain disconnected.")

        except Exception as e:
            logger.fatal("WiFiManager Error: Failed to initialize WLAN interface", e, reset_machine=True)
            self._status = WiFiManager.STATUS_ERROR

    def _can_attempt_connect(self):
        """Checks if enough time has passed since the last connection attempt."""
        return time.ticks_diff(time.ticks_ms(), self._last_attempt_time) > self.retry_interval_ms

    def update(self):
        """Should be called periodically in the main loop to manage connection."""
        if self._status == WiFiManager.STATUS_ERROR or not self.ssid:
            return # Cannot proceed if WLAN failed or no SSID

        # Check the current physical connection status
        is_physically_connected = self._wlan.isconnected()

        if self._status == WiFiManager.STATUS_CONNECTED:
            if not is_physically_connected:
                logger.error("WiFiManager: Connection lost.")
                self._status = WiFiManager.STATUS_DISCONNECTED
                self._ip_address = None
                self._wlan.active(False) # Deactivate to ensure clean reconnect
                self._last_attempt_time = time.ticks_ms() # Start retry timer
            # else: still connected, no need to log

        elif self._status == WiFiManager.STATUS_CONNECTING:
            if is_physically_connected:
                self._ip_address = self._wlan.ifconfig()[0]
                self._status = WiFiManager.STATUS_CONNECTED
            elif self._wlan.status() < 0 or self._wlan.status() >= 3: # Error codes like WRONG_PASSWORD, NO_AP_FOUND, CONN_FAIL
                logger.error(f"WiFiManager: Connection failed. Status code: {self._wlan.status()}.")
                self._status = WiFiManager.STATUS_DISCONNECTED
                self._wlan.active(False) # Deactivate
                self._last_attempt_time = time.ticks_ms() # Start retry timer
            # else: still connecting, no need to log

        elif self._status == WiFiManager.STATUS_DISCONNECTED:
            if self._can_attempt_connect():
                self._last_attempt_time = time.ticks_ms()
                try:
                    self._wlan.active(True)
                    self._wlan.connect(self.ssid, self.password)
                    self._status = WiFiManager.STATUS_CONNECTING
                except Exception as e:
                    logger.error(f"WiFiManager Error: Exception during connect initiation: {e}")
                    self._status = WiFiManager.STATUS_DISCONNECTED # Stay disconnected, retry later
                    self._wlan.active(False) # Ensure it's off if connect failed badly

    def is_connected(self):
        """Returns True if the Wi-Fi is connected, False otherwise."""
        return self._status == WiFiManager.STATUS_CONNECTED

    def get_status(self):
        """Returns a string representation of the current status."""
        if self._status == WiFiManager.STATUS_CONNECTED: return "Connected"
        if self._status == WiFiManager.STATUS_CONNECTING: return "Connecting"
        if self._status == WiFiManager.STATUS_DISCONNECTED: return "Disconnected"
        if self._status == WiFiManager.STATUS_ERROR: return "Error"
        return "Unknown"

    def get_ip(self):
        """Returns the current IP address if connected, otherwise None."""
        return self._ip_address if self.is_connected() else None

    def disconnect(self):
        """Disconnects the Wi-Fi connection."""
        if self._wlan:
            self._wlan.disconnect()
            self._wlan.active(False)

    def connection_failed(self):
        """Check if the last connection attempt failed.

        Returns:
            bool: True if connection failed, False otherwise
        """
        # Connection has failed if:
        # 1. We were in a CONNECTING state, but now we're in DISCONNECTED state
        # 2. We have attempted at least once (_last_attempt_time > 0)
        # 3. We're in ERROR state
        return (self._status == WiFiManager.STATUS_DISCONNECTED and 
                self._last_attempt_time > 0 and 
                self._wlan.status() >= 3)  # Status codes 3+ indicate connection failure

    def reconnect(self):
        """Force a reconnection attempt by resetting the retry timer.

        This allows immediate retry instead of waiting for the normal interval.
        """
        if self._status == WiFiManager.STATUS_DISCONNECTED:
            self._last_attempt_time = 0  # Reset timer to allow immediate attempt
            logger.info("WiFiManager: Reconnection requested")

    def get_signal_strength(self):
        """Get the current signal strength (RSSI) if connected.

        Returns:
            int: Signal strength in dBm or None if not available
        """
        if not self.is_connected() or not self._wlan:
            return None

        try:
            # Try the standard MicroPython approach first
            rssi = self._wlan.status('rssi')
            return rssi
        except (ValueError, TypeError):
            pass

        return None

    def get_ssid(self):
        """Get the current connected SSID.

        Returns:
            str: The SSID of the connected network or None if not connected
        """
        if self.is_connected():
            return self.ssid
        return None
