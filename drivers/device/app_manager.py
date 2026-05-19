"""
DeviceAppManager: Manages the RTA application on the mobile device.

Controls the RTA_app lifecycle, starts it with configuration,
and coordinates visual feedback with the alignment system.
"""

import logging
import subprocess
import time
from typing import List, Optional


class DeviceAppManager:
    """
    Manages the RTA application on the mobile device.

    Responsibilities:
    - Start RTA_app with configuration (device_type)
    - Wait for marker rendering
    - Monitor screen state
    - Capture app feedback
    """

    # RTA_app package name
    APP_PACKAGE = "com.example.rta"
    APP_ACTIVITY = "com.example.rta.MainActivity"

    # Supported device types
    DEVICE_TYPES = {
        "flat": 4,      # 4 markers in the corners
        "foldable": 8,  # 8 markers (4 on each screen)
        "one": 1,
        "two": 2,
        "three": 3,
        "six": 6,
        "seven": 7,
    }

    def __init__(self, device_interface=None):
        """
        Initialize DeviceAppManager.

        Args:
            device_interface: Device interface (for ADB commands).
        """
        self.device = device_interface
        self.logger = logging.getLogger(__name__)
        self.current_device_type = "flat"
        self.expected_marker_count = self.DEVICE_TYPES["flat"]

    def install_app(self) -> bool:
        """
        Install RTA_app on the device.

        Runs: ./gradlew installDebug (from RTA_app/)

        Returns:
            bool: True if installation succeeds.
        """
        try:
            self.logger.info("Installing RTA_app...")
            # Assuming we are in the project root directory
            result = subprocess.run(
                ["gradlew.bat", "installDebug"],
                cwd="RTA_app",
                capture_output=True,
                timeout=120,
                text=True
            )

            if result.returncode == 0:
                self.logger.info("RTA_app installed successfully")
                return True
            else:
                self.logger.error(f"Installation failed: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Error installing app: {e}")
            return False

    def start_app(self, device_type: str = "flat") -> bool:
        """
        Start RTA_app with the specified configuration.

        Args:
            device_type (str): Device type (flat, foldable, etc.).

        Returns:
            bool: True if the app starts successfully.
        """
        if device_type not in self.DEVICE_TYPES:
            self.logger.error(f"Invalid device type: {device_type}")
            return False

        self.current_device_type = device_type
        self.expected_marker_count = self.DEVICE_TYPES[device_type]

        try:
            self.logger.info(
                f"Starting RTA_app with device_type='{device_type}'")

            cmd = [
                "adb", "shell", "am", "start",
                "-n", f"{self.APP_PACKAGE}/.MainActivity",
                "--es", "device_type", device_type
            ]

            result = subprocess.run(
                cmd, capture_output=True, timeout=10, text=True)

            if result.returncode == 0:
                self.logger.info(
                    f"App started with {self.expected_marker_count} markers")
                # Wait for rendering
                time.sleep(2)
                return True
            else:
                self.logger.error(f"Failed to start app: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Error starting app: {e}")
            return False

    def stop_app(self) -> bool:
        """
        Stop the RTA application.

        Returns:
            bool: True if the app stops successfully.
        """
        try:
            self.logger.info("Stopping RTA_app...")
            cmd = ["adb", "shell", "am", "force-stop", self.APP_PACKAGE]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5, text=True)

            if result.returncode == 0:
                self.logger.info("App stopped")
                return True
            else:
                self.logger.error(f"Failed to stop app: {result.stderr}")
                return False

        except Exception as e:
            self.logger.error(f"Error stopping app: {e}")
            return False

    def get_expected_marker_count(self) -> int:
        """
        Return the expected number of markers for the current configuration.

        Returns:
            int: Number of markers.
        """
        return self.expected_marker_count

    def take_screenshot(self, filename: str = "rta_screen.png") -> Optional[str]:
        """
        Capture a screenshot of the device's current screen.

        Args:
            filename (str): File name to save.

        Returns:
            Optional[str]: Saved file path or None if it fails.
        """
        try:
            self.logger.debug(f"Capturing screenshot: {filename}")

            # Save on the device
            device_path = f"/sdcard/{filename}"
            cmd_cap = ["adb", "shell", "screencap", "-p", device_path]

            result = subprocess.run(
                cmd_cap, capture_output=True, timeout=5, text=True)
            if result.returncode != 0:
                self.logger.error("Failed to capture screenshot")
                return None

            # Pull to local machine
            local_path = f"log_images/{filename}"
            cmd_pull = ["adb", "pull", device_path, local_path]

            result = subprocess.run(
                cmd_pull, capture_output=True, timeout=5, text=True)
            if result.returncode == 0:
                self.logger.debug(f"Screenshot saved: {local_path}")
                return local_path
            else:
                self.logger.error("Failed to download screenshot")
                return None

        except Exception as e:
            self.logger.error(f"Error capturing screenshot: {e}")
            return None

    def is_app_running(self) -> bool:
        """
        Check whether RTA_app is running.

        Returns:
            bool: True if the app is running.
        """
        try:
            cmd = ["adb", "shell", "pidof", self.APP_PACKAGE]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5, text=True)
            return result.returncode == 0

        except Exception as e:
            self.logger.error(f"Error checking app status: {e}")
            return False

    def reset_screen(self) -> bool:
        """
        Reset the marker screen (click the app's RESET button).

        Simulates a click on the RESET button to restore all visible markers.

        Returns:
            bool: True if the reset succeeds.
        """
        try:
            self.logger.info("Resetting marker screen...")
            # The RESET button is at the center of the screen
            # Approximate coordinates for a standard screen (1080x2400)
            x, y = 540, 1200

            cmd = ["adb", "shell", "input", "tap", str(x), str(y)]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5, text=True)

            time.sleep(1)  # Wait for redraw
            return result.returncode == 0

        except Exception as e:
            self.logger.error(f"Error resetting screen: {e}")
            return False

    def bring_to_foreground(self) -> bool:
        """
        Bring the application to the foreground.

        Returns:
            bool: True if successful.
        """
        try:
            cmd = [
                "adb", "shell", "am", "start",
                "-n", f"{self.APP_PACKAGE}/.MainActivity"
            ]
            result = subprocess.run(
                cmd, capture_output=True, timeout=5, text=True)
            return result.returncode == 0

        except Exception as e:
            self.logger.error(f"Error bringing app to foreground: {e}")
            return False

    def wait_for_app_ready(self, timeout: int = 10) -> bool:
        """
        Wait until the app is ready (fully rendered).

        Args:
            timeout (int): Maximum number of seconds to wait.

        Returns:
            bool: True if the app becomes ready.
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.is_app_running():
                self.logger.info("App is ready")
                return True

            time.sleep(0.5)

        self.logger.warning("Timed out waiting for the app to become ready")
        return False
