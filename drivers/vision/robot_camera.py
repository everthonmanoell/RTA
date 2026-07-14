"""
RobotCamera: Interface for the camera mounted on the robot arm.

This module provides an abstraction layer for capturing images from the robot's
camera, separate from the mobile device camera. It handles image acquisition,
preprocessing, and caching.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple
from drivers.alignment.marker_detector import MarkerDetector
from pygrabber.dshow_graph import FilterGraph
import config
from config import CAMERA_CONFIG

import cv2
import numpy as np

import config
from pathlib import Path


class RobotCamera:
    """
    Manages image acquisition from the robot-mounted camera.

    This camera provides a fixed perspective for fiducial marker detection
    and visual alignment, independent of mobile device screen orientation.
    """

    def __init__(self, output_dir: str = "log_images", show_preview: bool = False):
        """
        Initialize RobotCamera with OpenCV camera source.

        Args:
            camera_id (int): OpenCV camera index. Default 0 for primary camera.
            output_dir (str): Directory for storing captured images.
            show_preview (bool): If True, show the live camera frame in an OpenCV window.
        """
        self.camera_id = self._get_camera_id(CAMERA_CONFIG["camera_name"])
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.cap = None
        self.logger = logging.getLogger(__name__)
        self.show_preview = bool(show_preview)
        self.preview_window_name = "RTA Camera Preview"
        self.preview_overlay_fn: Optional[Callable[[
            np.ndarray], np.ndarray]] = None

        # Initialize camera on first use
        self._camera_opened = False

    def _get_camera_id(self, name) -> int:
        graph = FilterGraph()
        list_of_cameras = graph.get_input_devices()
        for camera_id, camera_name in enumerate(list_of_cameras):
            if name in camera_name:
                return camera_id

    def _ensure_camera_open(self) -> bool:
        """
        Ensure camera is open and ready to capture, applying hardware settings.

        Returns:
            bool: True if camera is ready, False otherwise.
        """
        if not self._camera_opened:
            # Try to open with DirectShow first (Better for injecting configs in Logitech on Windows)
            self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)

            # Safe fallback in case running on Linux, Mac or DSHOW fails
            if not self.cap.isOpened():
                self.cap = cv2.VideoCapture(self.camera_id)

            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_id}")
                return False

            # =================================================================
            # APPLY BRIO HARDWARE SETTINGS (via config.py)
            # =================================================================
            try:
                import config
                calib = getattr(config, "CAMERA_CALIBRATION_CONFIG", None)

                if calib:
                    self.logger.info(
                        "Injecting hardware settings into Brio...")

                    # Focus
                    if "auto_focus" in calib:
                        self.cap.set(cv2.CAP_PROP_AUTOFOCUS,
                                     calib["auto_focus"])
                    if "fixed_focus" in calib:
                        self.cap.set(cv2.CAP_PROP_FOCUS, calib["fixed_focus"])

                    # Exposure
                    if "auto_exposure" in calib:
                        self.cap.set(cv2.CAP_PROP_AUTO_EXPOSURE,
                                     calib["auto_exposure"])
                    if "fixed_exposure" in calib:
                        self.cap.set(cv2.CAP_PROP_EXPOSURE,
                                     calib["fixed_exposure"])

                    # White Balance
                    if "auto_white_balance" in calib:
                        self.cap.set(cv2.CAP_PROP_AUTO_WB,
                                     calib["auto_white_balance"])
                    if "white_balance_temperature" in calib:
                        self.cap.set(cv2.CAP_PROP_WB_TEMPERATURE,
                                     calib["white_balance_temperature"])

            except ImportError:
                self.logger.warning(
                    "File 'config' not found, ignoring camera hardware calibration.")

            self._camera_opened = True

        return True

    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from the robot's camera.

        Returns:
            Optional[np.ndarray]: Frame as BGR image, or None if capture failed.
        """
        if not self._ensure_camera_open():
            return None

        ret, frame = self.cap.read()
        if not ret:
            self.logger.error("Failed to capture frame")
            return None

        if self.show_preview:
            try:
                preview_frame = frame
                if self.preview_overlay_fn is not None:
                    preview_frame = self.preview_overlay_fn(frame.copy())
                cv2.imshow(self.preview_window_name, preview_frame)
                cv2.waitKey(1)
            except Exception as exc:
                self.logger.debug("Camera preview unavailable: %s", exc)

        return frame

    def capture_and_save(self, filename: str) -> Optional[np.ndarray]:
        """
        Capture frame and save to disk with timestamp.

        Args:
            filename (str): Image filename (without path).

        Returns:
            Optional[np.ndarray]: Captured frame, or None if failed.
        """
        frame = self.capture_frame()
        if frame is None:
            return None

        filepath = self.output_dir / filename
        success = cv2.imwrite(str(filepath), frame)
        if success:
            self.logger.info(f"Image saved: {filepath}")
        else:
            self.logger.error(f"Failed to save image: {filepath}")

        return frame

    def get_frame_shape(self) -> Optional[tuple]:
        """
        Get frame dimensions (height, width, channels).

        Returns:
            Optional[tuple]: (height, width, channels) or None if failed.
        """
        frame = self.capture_frame()
        if frame is None:
            return None
        return frame.shape

    def set_camera_property(self, prop_id: int, value: float) -> bool:
        """
        Set OpenCV camera property (brightness, contrast, etc).

        Args:
            prop_id (int): OpenCV camera property ID (e.g., cv2.CAP_PROP_BRIGHTNESS).
            value (float): Property value.

        Returns:
            bool: True if successful.
        """
        if not self._ensure_camera_open():
            return False

        success = self.cap.set(prop_id, value)
        if success:
            self.logger.info(f"Set camera property {prop_id} = {value}")
        else:
            self.logger.error(f"Failed to set camera property {prop_id}")
        return success

    def release(self):
        """Release camera resources."""
        if self.cap is not None:
            self.cap.release()
            self._camera_opened = False
            if self.show_preview:
                try:
                    cv2.destroyWindow(self.preview_window_name)
                except Exception:
                    pass
            self.logger.info("Camera released")

    def display_image(self, image_np: np.ndarray, window_name: str = "Image"):
        """
        Display an image in an OpenCV window.

        Args:
            image (np.ndarray): Image to display (BGR format).
            window_name (str): Name of the display window.
        """
        try:
            cv2.imshow(window_name, image_np)
            cv2.waitKey(0)
            cv2.destroyWindow(window_name)
        except Exception as exc:
            self.logger.debug("Image display unavailable: %s", exc)

    def image_with_middle_point(self, image_np: np.ndarray) -> dict[str, object]:
        """
        Draw a red point in the middle of the image for debugging.

        Args:
            image_np (np.ndarray): Input image (BGR format).
        returns:
            dict: Dictionary containing the modified image and center coordinates.
        """
        height, width = image_np.shape[:2]
        center_x, center_y = width // 2, height // 2
        cv2.circle(image_np, (center_x, center_y), radius=10,
                   color=(0, 0, 255), thickness=-1)
        return dict(image_np=image_np, center=(center_x, center_y))

    def save_frame_with_timestamp(self, frame: np.ndarray,  prefix: str = "capture", filename=str) -> Optional[np.ndarray]:
        """
        Save frame with a timestamped filename.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.jpg"
        filepath = self.output_dir / filename
        success = cv2.imwrite(str(filepath), frame)
        if success:
            self.logger.info(f"Image saved: {filepath}")
            return frame
        else:
            self.logger.error(f"Failed to save image: {filepath}")
            return None

    def center_point(self, image_np: np.ndarray) -> Tuple[int, int]:
        """
        Get the center point coordinates of the image.

        Args:
            image_np (np.ndarray): Input image (BGR format).

        Returns:
            Tuple[int, int]: (center_x, center_y) coordinates of the image center.
        """
        height, width = image_np.shape[:2]
        center_x, center_y = width // 2, height // 2
        return center_x, center_y

    def __del__(self):
        """Ensure camera is released on object destruction."""
        self.release()
