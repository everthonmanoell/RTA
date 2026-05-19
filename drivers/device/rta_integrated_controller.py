"""
RTA_IntegratedController: Complete orchestrator for the RTA system.

Integrates:
- RTA_app (Android app with markers)
- Robot camera
- Visual alignment (XYZ + RZ)
- Marker touch interactions
- Visual feedback
"""

import logging
import time
from typing import List, Optional

import numpy as np

from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.alignment.rotation_alignment import RotationAlignment
from drivers.device.app_manager import DeviceAppManager
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import CoordinateTransform


class RTAIntegratedController:
    """
    Complete orchestrator for the RTA system.

    Flow:
    1. Start RTA_app with configuration
    2. Detect markers through the robot camera
    3. Align the robot (RZ + XYZ)
    4. Touch each marker sequentially
    5. Verify visual feedback (marker disappears)
    6. Repeat or continue
    """

    def __init__(self, robot_arm, device_interface, camera: RobotCamera,
                 app_manager: Optional[DeviceAppManager] = None,
                 auto_align: Optional[AutoAlignment] = None,
                 rot_align: Optional[RotationAlignment] = None,
                 detector: Optional[MarkerDetector] = None):
        """
        Initialize RTAIntegratedController.

        Args:
            robot_arm: Denso robot interface.
            device_interface: Device interface (ADB).
            camera (RobotCamera): Camera mounted on the robot.
            app_manager (Optional[DeviceAppManager]): App manager.
            auto_align (Optional[AutoAlignment]): XYZ controller.
            rot_align (Optional[RotationAlignment]): RZ controller.
            detector (Optional[MarkerDetector]): Marker detector.
        """
        self.robot_arm = robot_arm
        self.device = device_interface
        self.camera = camera

        self.app_manager = app_manager or DeviceAppManager(device_interface)
        self.detector = detector or MarkerDetector()
        self.auto_align = auto_align or AutoAlignment(
            robot_arm, camera, self.detector)
        self.rot_align = rot_align or RotationAlignment(
            robot_arm, camera, self.detector)

        self.logger = logging.getLogger(__name__)

        # Configuration
        self.approach_distance_mm = 150.0
        self.touch_delay = 0.5
        self.verification_delay = 1.0
        self.max_retries_per_marker = 3

        # State tracking
        self.touched_markers = set()
        self.current_session_id = None

    def setup_session(self, device_type: str = "flat", install_if_needed: bool = False) -> bool:
        """
        Set up a new session.

        Args:
            device_type (str): Device type (flat, foldable, etc.).
            install_if_needed (bool): Install the app if it is not available.

        Returns:
            bool: True if the session is configured successfully.
        """
        self.logger.info(
            f"Setting up session with device_type='{device_type}'")

        # Check/install app
        if not self.app_manager.is_app_running():
            if install_if_needed:
                self.logger.info("App not installed, installing...")
                if not self.app_manager.install_app():
                    self.logger.error("Failed to install app")
                    return False
            else:
                self.logger.error("App is not running")
                return False

        # Stop any previous app instance if it was running
        self.app_manager.stop_app()
        time.sleep(1)

        # Start a new session
        if not self.app_manager.start_app(device_type):
            self.logger.error("Failed to start app")
            return False

        # Wait for the app to be ready
        if not self.app_manager.wait_for_app_ready():
            self.logger.warning("App may not be fully ready")

        self.current_session_id = f"{device_type}_{int(time.time())}"
        self.touched_markers = set()

        self.logger.info(f"Session configured: {self.current_session_id}")
        return True

    def detect_markers_from_app_screen(self) -> Optional[List[MarkerInfo]]:
        """
        Detect markers on the app screen using the robot camera.

        Returns:
            Optional[List[MarkerInfo]]: List of detected markers.
        """
        frame = self.camera.capture_frame()
        if frame is None:
            self.logger.error("Failed to capture frame")
            return None

        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            self.logger.warning("No markers detected")
            return None

        corners = self.detector.refine_corners(frame, corners)
        marker_infos = [
            self.detector.get_marker_info(int(ids[i][0]), corners[i])
            for i in range(len(ids))
        ]

        self.logger.info(f"Detected {len(marker_infos)} markers")
        return marker_infos

    def perform_full_alignment(self) -> bool:
        """
        Perform full alignment (RZ + XYZ).

        Returns:
            bool: True if alignment succeeds.
        """
        self.logger.info("Starting full alignment")

        # 1. Rotation alignment (RZ)
        self.logger.info("Step 1: Rotation alignment")
        if not self.rot_align.run_alignment_loop(max_iterations=10):
            self.logger.error("RZ alignment failed")
            return False

        time.sleep(1)

        # 2. Distance calibration (if needed)
        if self.auto_align.reference_marker_area is None:
            self.logger.info("Step 2a: Distance calibration")
            if not self.auto_align.calibrate_distance():
                self.logger.error("Calibration failed")
                return False

        # 3. XYZ alignment
        self.logger.info("Step 2b: XYZ alignment")
        if not self.auto_align.approach_marker(self.approach_distance_mm):
            self.logger.error("XYZ alignment failed")
            return False

        self.logger.info("Full alignment completed successfully")
        return True

    def verify_marker_touched(self, marker_id: int, retries: int = 2) -> bool:
        """
        Verify whether a marker was actually touched (visual feedback).

        Captures a new image and checks whether the marker disappeared.

        Args:
            marker_id (int): ID of the touched marker.
            retries (int): Number of verification attempts.

        Returns:
            bool: True if the marker disappeared (was touched).
        """
        for attempt in range(retries):
            time.sleep(self.verification_delay)

            # Capture a new image
            frame = self.camera.capture_frame()
            if frame is None:
                continue

            # Detect markers
            ids, _ = self.detector.detect_markers(frame)
            if ids is None:
                return True  # No markers may mean success

            # Check whether the marker was touched
            id_list = [int(id_val[0]) for id_val in ids]
            if marker_id not in id_list:
                self.logger.info(
                    f"Marker {marker_id} confirmed touched (visual feedback)")
                return True

            if attempt < retries - 1:
                self.logger.debug(
                    f"Verification: marker still visible, attempt {attempt + 1}/{retries}")

        self.logger.warning(f"Marker {marker_id} still visible after touch")
        return False

    def touch_marker_sequence(self, markers: List[MarkerInfo]) -> dict:
        """
        Touch markers sequentially with visual feedback.

        Args:
            markers (List[MarkerInfo]): Markers to touch.

        Returns:
            dict: { marker_id: (success, details) }
        """
        results = {}

        for i, marker in enumerate(markers):
            self.logger.info(
                f"Touching marker {i + 1}/{len(markers)} (ID: {marker.marker_id})")

            # Skip if already touched
            if marker.marker_id in self.touched_markers:
                self.logger.debug(
                    f"Marker {marker.marker_id} was already touched, skipping")
                results[marker.marker_id] = (True, "already_touched")
                continue

            success = False
            retries = 0

            # Try touching with retries
            while retries < self.max_retries_per_marker:
                # Touch
                touch_x, touch_y = int(
                    marker.centroid[0]), int(marker.centroid[1])
                try:
                    self.device.touch(touch_x, touch_y)
                    self.logger.info(
                        f"Touch executed at ({touch_x}, {touch_y})")
                except Exception as e:
                    self.logger.error(f"Error while touching: {e}")
                    retries += 1
                    continue

                time.sleep(self.touch_delay)

                # Verify visual feedback
                if self.verify_marker_touched(marker.marker_id):
                    self.touched_markers.add(marker.marker_id)
                    results[marker.marker_id] = (True, "verified")
                    success = True
                    break

                retries += 1
                self.logger.warning(
                    f"Touch not confirmed, attempt {retries}/{self.max_retries_per_marker}")

            if not success:
                results[marker.marker_id] = (
                    False, f"failed_after_{retries}_retries")
                self.logger.error(f"Failed to touch marker {marker.marker_id}")

        return results

    def run_complete_session(self, device_type: str = "flat") -> dict:
        """
        Run a complete session: setup → detect → align → touch.

        Args:
            device_type (str): Device type.

        Returns:
            dict: Session result { 'session_id': ..., 'markers_touched': {...}, ... }
        """
        self.logger.info(
            f"Starting complete session with device_type='{device_type}'")

        result = {
            "session_id": None,
            "status": "failed",
            "device_type": device_type,
            "markers_expected": 0,
            "markers_detected": 0,
            "markers_touched": {},
            "errors": []
        }

        try:
            # 1. Setup
            if not self.setup_session(device_type, install_if_needed=True):
                result["errors"].append("Failed to setup session")
                return result

            result["session_id"] = self.current_session_id
            result["markers_expected"] = self.app_manager.get_expected_marker_count()

            # 2. Detect markers
            markers = self.detect_markers_from_app_screen()
            if not markers:
                result["errors"].append("No markers detected")
                return result

            result["markers_detected"] = len(markers)

            # 3. Alignment
            if not self.perform_full_alignment():
                result["errors"].append("Alignment failed")
                return result

            # 4. Touch markers
            touch_results = self.touch_marker_sequence(markers)
            result["markers_touched"] = touch_results

            # 5. Validation
            successful_touches = sum(
                1 for success, _ in touch_results.values() if success)
            if successful_touches == len(markers):
                result["status"] = "success"
                self.logger.info(
                    f"Session completed successfully: {successful_touches}/{len(markers)}")
            else:
                result["status"] = "partial"
                self.logger.warning(
                    f"Partial session: {successful_touches}/{len(markers)} markers touched")

        except Exception as e:
            self.logger.error(f"Session error: {e}")
            result["errors"].append(str(e))

        finally:
            # Cleanup
            try:
                self.app_manager.stop_app()
            except:
                pass

        return result

    def cleanup(self):
        """Clean up resources."""
        self.logger.info("Cleaning up resources")
        try:
            self.app_manager.stop_app()
            self.camera.release()
            self.logger.info("Resources released")
        except Exception as e:
            self.logger.error(f"Cleanup error: {e}")
