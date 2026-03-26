"""
AutoAlignment: Automatic XYZ alignment based on fiducial markers.

Adapted from FOV's auto_distance.py but uses the robot-mounted camera
and provides control for approaching and touching marker targets.
"""

import logging
import math
import time
from typing import Optional, Tuple

import numpy as np

from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import CoordinateTransform


class AutoAlignment:
    """
    Manages automatic XYZ alignment of the robot towards fiducial markers.
    
    Uses visual feedback from the robot-mounted camera to:
    1. Keep markers centered in the image (XY plane)
    2. Maintain a target distance from the markers (Z axis)
    3. Approach markers for interaction (touching screen)
    """
    
    # Control parameters
    CENTRALIZE_TOLERANCE = 5.0  # pixels
    DEPTH_TOLERANCE = 10.0  # mm
    TARGET_DISTANCE_MM = 200.0  # Default approach distance
    
    # Safety limits
    Z_MAX = 600.0  # Maximum Z position (mm)
    Z_MIN = 100.0  # Minimum Z position (mm)
    APPROACH_SPEED = 5.0  # mm per iteration
    
    # Control gains
    XY_GAIN = 0.3  # Proportional gain for XY correction
    Z_GAIN = 0.2   # Proportional gain for Z correction
    
    MAX_ITERATIONS = 20
    ITERATION_DELAY = 0.5  # seconds
    
    def __init__(self, robot_arm, camera: RobotCamera, 
                 detector: Optional[MarkerDetector] = None,
                 transform: Optional[CoordinateTransform] = None):
        """
        Initialize AutoAlignment controller.
        
        Args:
            robot_arm: Robot interface (must have get_cartesian_pose, move_cartesian).
            camera (RobotCamera): Robot camera interface.
            detector (Optional[MarkerDetector]): Marker detector (auto-created if None).
            transform (Optional[CoordinateTransform]): Coordinate transformer (auto-created if None).
        """
        self.robot_arm = robot_arm
        self.camera = camera
        self.detector = detector or MarkerDetector()
        self.transform = transform or CoordinateTransform()
        self.logger = logging.getLogger(__name__)
        
        # State tracking
        self.reference_marker_area = None
        self.current_target_distance = self.TARGET_DISTANCE_MM
    
    def calibrate_distance(self) -> bool:
        """
        Calibrate reference distance by capturing current marker area.
        
        Establishes the reference area used for inverse square law calculations.
        
        Returns:
            bool: True if calibration successful.
        """
        frame = self.camera.capture_frame()
        if frame is None:
            self.logger.error("Failed to capture frame for calibration")
            return False
        
        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            self.logger.error("No markers detected for calibration")
            return False
        
        # Refine and get info
        corners = self.detector.refine_corners(frame, corners)
        marker_info = self.detector.get_marker_info(int(ids[0][0]), corners[0])
        
        self.reference_marker_area = marker_info.area
        self.logger.info(f"Distance calibration: Reference area = {self.reference_marker_area:.1f} px²")
        
        return True
    
    def get_markers_from_frame(self, frame: np.ndarray) -> Optional[list]:
        """
        Detect and process markers in a frame.
        
        Args:
            frame (np.ndarray): Input frame.
            
        Returns:
            Optional[list]: List of MarkerInfo objects, or None if detection failed.
        """
        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            self.logger.warning("No markers detected")
            return None
        
        # Refine corners
        corners = self.detector.refine_corners(frame, corners)
        
        # Build marker info list
        marker_infos = []
        for i, marker_id in enumerate(ids):
            info = self.detector.get_marker_info(int(marker_id[0]), corners[i])
            marker_infos.append(info)
        
        return marker_infos
    
    def calculate_centering_correction(self, frame: np.ndarray, 
                                      marker_info: MarkerInfo) -> Tuple[float, float]:
        """
        Calculate XY correction needed to center marker.
        
        Args:
            frame (np.ndarray): Current frame.
            marker_info (MarkerInfo): Detected marker.
            
        Returns:
            Tuple[float, float]: (correction_x_mm, correction_y_mm)
        """
        height, width = frame.shape[:2]
        offset_x_mm, offset_y_mm = self.transform.image_center_offset_mm(
            marker_info.centroid[0], marker_info.centroid[1],
            width, height,
            marker_info.width_px, marker_info.height_px
        )
        return offset_x_mm, offset_y_mm
    
    def calculate_depth_correction(self, marker_info: MarkerInfo) -> float:
        """
        Calculate Z correction to reach target distance.
        
        Uses inverse square law: distance ∝ sqrt(reference_area / current_area)
        
        Args:
            marker_info (MarkerInfo): Detected marker.
            
        Returns:
            float: Z correction in mm (positive = move closer).
        """
        if self.reference_marker_area is None:
            self.logger.warning("Reference area not calibrated")
            return 0.0
        
        estimated_distance = self.transform.marker_size_to_depth(
            marker_info.area,
            self.reference_marker_area,
            self.current_target_distance
        )
        
        error = self.current_target_distance - estimated_distance
        return error
    
    def apply_correction(self, correction_x: float, correction_y: float, 
                        correction_z: float) -> bool:
        """
        Apply XYZ correction to robot position.
        
        Args:
            correction_x (float): X correction in mm.
            correction_y (float): Y correction in mm.
            correction_z (float): Z correction in mm.
            
        Returns:
            bool: True if successful.
        """
        current_pose = self.robot_arm.get_cartesian_pose()
        if current_pose is None:
            self.logger.error("Failed to get robot pose")
            return False
        
        # Apply gains and limits
        new_x = current_pose.x - correction_x * self.XY_GAIN
        new_y = current_pose.y - correction_y * self.XY_GAIN
        new_z = current_pose.z + correction_z * self.Z_GAIN
        
        # Apply safety limits
        if new_z > self.Z_MAX:
            new_z = self.Z_MAX
        elif new_z < self.Z_MIN:
            new_z = self.Z_MIN
        
        current_pose.x = new_x
        current_pose.y = new_y
        current_pose.z = new_z
        
        success = self.robot_arm.move_cartesian(current_pose)
        if not success:
            self.logger.error("Failed to move robot")
            return False
        
        self.logger.debug(f"Applied correction: X={correction_x:.2f}, Y={correction_y:.2f}, Z={correction_z:.2f}")
        return True
    
    def run_centering_loop(self, max_iterations: int = None) -> bool:
        """
        Run XY centering control loop.
        
        Centers the closest marker in the image frame.
        
        Args:
            max_iterations (int): Maximum iterations (uses class default if None).
            
        Returns:
            bool: True if centering successful.
        """
        max_iterations = max_iterations or self.MAX_ITERATIONS
        iteration = 0
        
        self.logger.info("Starting centering loop")
        
        while iteration < max_iterations:
            frame = self.camera.capture_frame()
            if frame is None:
                self.logger.error("Failed to capture frame")
                return False
            
            marker_infos = self.get_markers_from_frame(frame)
            if not marker_infos:
                self.logger.warning("No markers in frame")
                return False
            
            # Find closest to center
            target = self.detector.find_closest_to_center(frame, marker_infos)
            if target is None:
                return False
            
            # Calculate correction
            corr_x, corr_y = self.calculate_centering_correction(frame, target)
            
            self.logger.info(f"Iteration {iteration}: X offset={corr_x:.2f}mm, Y offset={corr_y:.2f}mm")
            
            # Check convergence
            if abs(corr_x) < self.CENTRALIZE_TOLERANCE and abs(corr_y) < self.CENTRALIZE_TOLERANCE:
                self.logger.info("Centering successful")
                return True
            
            # Apply correction
            if not self.apply_correction(corr_x, corr_y, 0.0):
                return False
            
            time.sleep(self.ITERATION_DELAY)
            iteration += 1
        
        self.logger.warning("Centering loop reached max iterations")
        return False
    
    def run_depth_loop(self, target_distance_mm: float = None, 
                      max_iterations: int = None) -> bool:
        """
        Run Z depth control loop.
        
        Approaches/maintains target distance from markers.
        
        Args:
            target_distance_mm (float): Target distance in mm (uses default if None).
            max_iterations (int): Maximum iterations.
            
        Returns:
            bool: True if depth control successful.
        """
        if target_distance_mm is None:
            target_distance_mm = self.current_target_distance
        
        self.current_target_distance = target_distance_mm
        max_iterations = max_iterations or self.MAX_ITERATIONS
        iteration = 0
        
        self.logger.info(f"Starting depth control loop (target={target_distance_mm}mm)")
        
        # Ensure we have reference
        if self.reference_marker_area is None:
            if not self.calibrate_distance():
                return False
        
        while iteration < max_iterations:
            frame = self.camera.capture_frame()
            if frame is None:
                return False
            
            marker_infos = self.get_markers_from_frame(frame)
            if not marker_infos:
                return False
            
            # Use marker closest to center
            target = self.detector.find_closest_to_center(frame, marker_infos)
            if target is None:
                return False
            
            # Calculate correction
            corr_z = self.calculate_depth_correction(target)
            
            self.logger.info(f"Iteration {iteration}: Depth error={corr_z:.2f}mm")
            
            # Check convergence
            if abs(corr_z) < self.DEPTH_TOLERANCE:
                self.logger.info("Depth control successful")
                return True
            
            # Apply correction
            if not self.apply_correction(0.0, 0.0, corr_z):
                return False
            
            time.sleep(self.ITERATION_DELAY)
            iteration += 1
        
        self.logger.warning("Depth control reached max iterations")
        return False
    
    def approach_marker(self, target_distance_mm: float) -> bool:
        """
        Approach markers to a specific distance.
        
        Runs combined centering and depth control to position for interaction.
        
        Args:
            target_distance_mm (float): Distance to approach to.
            
        Returns:
            bool: True if approach successful.
        """
        self.logger.info(f"Approaching markers to {target_distance_mm}mm")
        
        # First center the markers
        if not self.run_centering_loop():
            self.logger.error("Centering failed")
            return False
        
        # Then adjust depth
        if not self.run_depth_loop(target_distance_mm):
            self.logger.error("Depth control failed")
            return False
        
        self.logger.info("Approach successful")
        return True
