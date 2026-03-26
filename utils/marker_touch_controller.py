"""
MarkerTouchController: Manages interaction with fiducial markers.

Coordinates the sequence of alignment and touch operations to interact
with markers on the mobile device screen via the robot arm.
"""

import logging
import time
from typing import List, Optional

import numpy as np

from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.alignment.rotation_alignment import RotationAlignment
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import CoordinateTransform


class MarkerTouchController:
    """
    Coordinates visual alignment and touching of fiducial markers.
    
    Orchestrates the sequence:
    1. Detect markers in the mobile screen (via robot camera)
    2. Align robot position (RZ rotation for parallelism)
    3. Approach markers (XYZ positioning)
    4. Execute touch action at marker centers
    """
    
    def __init__(self, robot_arm, mobile_device, camera: RobotCamera,
                 auto_align: Optional[AutoAlignment] = None,
                 rot_align: Optional[RotationAlignment] = None,
                 detector: Optional[MarkerDetector] = None):
        """
        Initialize MarkerTouchController.
        
        Args:
            robot_arm: Robot interface.
            mobile_device: Mobile device interface (for touch commands).
            camera (RobotCamera): Robot camera interface.
            auto_align (Optional[AutoAlignment]): Auto-alignment controller.
            rot_align (Optional[RotationAlignment]): Rotation alignment controller.
            detector (Optional[MarkerDetector]): Marker detector.
        """
        self.robot_arm = robot_arm
        self.device = mobile_device
        self.camera = camera
        self.detector = detector or MarkerDetector()
        self.auto_align = auto_align or AutoAlignment(robot_arm, camera, self.detector)
        self.rot_align = rot_align or RotationAlignment(robot_arm, camera, self.detector)
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.approach_distance_mm = 200.0
        self.touch_delay_before_lift = 0.5
        self.touch_delay_after_touch = 0.5
        self.target_marker_ids = None
    
    def detect_markers_in_screen(self) -> Optional[List[MarkerInfo]]:
        """
        Detect fiducial markers currently visible in device screen.
        
        Uses robot camera to detect markers on mobile device screen.
        
        Returns:
            Optional[List[MarkerInfo]]: Detected markers or None if failed.
        """
        frame = self.camera.capture_frame()
        if frame is None:
            self.logger.error("Failed to capture frame for marker detection")
            return None
        
        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            self.logger.warning("No markers detected in screen")
            return None
        
        corners = self.detector.refine_corners(frame, corners)
        marker_infos = [self.detector.get_marker_info(int(ids[i][0]), corners[i]) 
                       for i in range(len(ids))]
        
        self.logger.info(f"Detected {len(marker_infos)} markers")
        return marker_infos
    
    def set_target_markers(self, marker_ids: Optional[List[int]] = None):
        """
        Set which markers to target (by ID).
        
        Args:
            marker_ids (Optional[List[int]]): List of marker IDs to touch.
                If None, will touch all detected markers.
        """
        self.target_marker_ids = marker_ids
        self.logger.info(f"Target markers set to: {marker_ids}")
    
    def align_for_markers(self) -> bool:
        """
        Perform full alignment sequence for marker interaction.
        
        1. Rotate (RZ) to achieve parallelism
        2. Center and approach markers
        
        Returns:
            bool: True if alignment successful.
        """
        self.logger.info("Starting alignment sequence")
        
        # Step 1: Rotation alignment (RZ)
        self.logger.info("Step 1: Performing rotation alignment")
        if not self.rot_align.run_alignment_loop():
            self.logger.error("Rotation alignment failed")
            return False
        
        time.sleep(1.0)
        
        # Step 2: Calibrate distance (if not already done)
        if self.auto_align.reference_marker_area is None:
            self.logger.info("Step 2a: Calibrating distance reference")
            if not self.auto_align.calibrate_distance():
                self.logger.error("Distance calibration failed")
                return False
        
        # Step 3: Approach to target distance
        self.logger.info(f"Step 2b: Approaching to {self.approach_distance_mm}mm")
        if not self.auto_align.approach_marker(self.approach_distance_mm):
            self.logger.error("Approach failed")
            return False
        
        self.logger.info("Alignment sequence completed successfully")
        return True
    
    def get_marker_screen_position(self, marker_info: MarkerInfo) -> tuple:
        """
        Get the screen coordinates of a marker for touch.
        
        Args:
            marker_info (MarkerInfo): Detected marker.
            
        Returns:
            tuple: (x, y) in device screen coordinates.
        """
        return (int(marker_info.centroid[0]), int(marker_info.centroid[1]))
    
    def touch_marker_on_screen(self, marker_info: MarkerInfo) -> bool:
        """
        Touch a marker on the device screen via robot.
        
        Args:
            marker_info (MarkerInfo): Marker to touch.
            
        Returns:
            bool: True if touch executed.
        """
        screen_x, screen_y = self.get_marker_screen_position(marker_info)
        
        self.logger.info(f"Touching marker at screen coords ({screen_x}, {screen_y})")
        
        # Execute touch on device
        try:
            # Assuming device has a touch method
            if hasattr(self.device, 'touch'):
                result = self.device.touch(screen_x, screen_y)
            else:
                self.logger.error("Device does not support touch interface")
                return False
            
            time.sleep(self.touch_delay_after_touch)
            return True
        
        except Exception as e:
            self.logger.error(f"Touch execution failed: {e}")
            return False
    
    def touch_all_detected_markers(self) -> List[bool]:
        """
        Touch all detected markers in sequence.
        
        Returns:
            List[bool]: Success status for each marker touched.
        """
        markers = self.detect_markers_in_screen()
        if not markers:
            self.logger.error("No markers to touch")
            return []
        
        results = []
        for i, marker in enumerate(markers):
            # Check if should touch this marker
            if self.target_marker_ids and marker.marker_id not in self.target_marker_ids:
                self.logger.debug(f"Skipping marker {marker.marker_id}")
                continue
            
            self.logger.info(f"Touching marker {i+1}/{len(markers)} (ID: {marker.marker_id})")
            success = self.touch_marker_on_screen(marker)
            results.append(success)
            
            if not success:
                self.logger.warning(f"Failed to touch marker {marker.marker_id}")
        
        return results
    
    def run_full_sequence(self, target_marker_ids: Optional[List[int]] = None) -> bool:
        """
        Execute complete sequence: detect, align, and touch markers.
        
        Args:
            target_marker_ids (Optional[List[int]]): Specific markers to touch.
            
        Returns:
            bool: True if sequence completed successfully.
        """
        self.logger.info("Starting full marker touch sequence")
        
        # Set targets
        if target_marker_ids:
            self.set_target_markers(target_marker_ids)
        
        # Detect markers
        markers = self.detect_markers_in_screen()
        if not markers:
            self.logger.error("No markers detected")
            return False
        
        # Align
        if not self.align_for_markers():
            self.logger.error("Alignment failed")
            return False
        
        # Touch markers
        results = self.touch_all_detected_markers()
        
        if all(results):
            self.logger.info("All markers touched successfully")
            return True
        else:
            self.logger.warning(f"Some touches failed: {sum(1 for r in results if not r)}/{len(results)}")
            return False
