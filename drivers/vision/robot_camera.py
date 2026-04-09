"""
RobotCamera: Interface for the camera mounted on the robot arm.

This module provides an abstraction layer for capturing images from the robot's
camera, separate from the mobile device camera. It handles image acquisition,
preprocessing, and caching.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import cv2
import numpy as np


class RobotCamera:
    """
    Manages image acquisition from the robot-mounted camera.
    
    This camera provides a fixed perspective for fiducial marker detection
    and visual alignment, independent of mobile device screen orientation.
    """
    
    def __init__(self, camera_id: int = 0, output_dir: str = "log_images", show_preview: bool = False):
        """
        Initialize RobotCamera with OpenCV camera source.
        
        Args:
            camera_id (int): OpenCV camera index. Default 0 for primary camera.
            output_dir (str): Directory for storing captured images.
            show_preview (bool): If True, show the live camera frame in an OpenCV window.
        """
        self.camera_id = camera_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.cap = None
        self.logger = logging.getLogger(__name__)
        self.show_preview = bool(show_preview)
        self.preview_window_name = "RTA Camera Preview"
        self.preview_overlay_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None
        
        # Initialize camera on first use
        self._camera_opened = False
    
    def _ensure_camera_open(self) -> bool:
        """
        Ensure camera is open and ready to capture.
        
        Returns:
            bool: True if camera is ready, False otherwise.
        """
        if not self._camera_opened:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_id}")
                return False
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
    
    def __del__(self):
        """Ensure camera is released on object destruction."""
        self.release()
