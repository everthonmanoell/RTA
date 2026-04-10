"""
AutoAlignment: Automatic XYZ alignment based on fiducial markers.

Adapted from FOV's auto_distance.py but uses the robot-mounted camera
and provides control for approaching and touching marker targets.
"""

import logging
import math
import time
from typing import Optional, Tuple

import cv2
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
    XY_GAIN = 0.03  # Proportional gain for XY correction
    Z_GAIN = 0.2   # Proportional gain for Z correction
    
    MAX_ITERATIONS = 20
    ITERATION_DELAY = 0.5  # seconds
    MAX_XY_STEP_MM = 10.0
    MAX_Z_STEP_MM = 8.0
    MAX_XY_DRIFT_MM = 120.0
    MAX_NO_IMPROVEMENT_ITERS = 4
    MIN_IMPROVEMENT_MM = 1.0
    
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
        self.reference_marker_perimeter = None
        self.current_target_distance = self.TARGET_DISTANCE_MM

    def _find_top_leftest_marker(self, marker_infos: list[MarkerInfo]) -> Optional[MarkerInfo]:
        """
        Select marker closest to image origin (0,0), matching FOV behavior.

        In FOV this is the marker nearest to top-left; using the same strategy keeps
        calibration/alignment consistent between both projects.
        """
        if not marker_infos:
            return None

        best = None
        best_dist = float("inf")
        for marker in marker_infos:
            dist = float(np.linalg.norm(marker.centroid))
            if dist < best_dist:
                best_dist = dist
                best = marker
        return best
    
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
        marker_infos = []
        for i, marker_id in enumerate(ids):
            marker_infos.append(self.detector.get_marker_info(int(marker_id[0]), corners[i]))

        marker_info = self.detector.find_closest_to_center(frame, marker_infos)
        if marker_info is None:
            self.logger.error("No valid marker for calibration")
            return False
        
        self.reference_marker_area = marker_info.area
        self.reference_marker_perimeter = marker_info.perimeter
        self.logger.info(
            "Distance calibration: Reference area=%.1f px² perimeter=%.1f px",
            self.reference_marker_area,
            self.reference_marker_perimeter,
        )
        
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
        Calculate XY correction to center a single marker.
        
        Args:
            frame (np.ndarray): Current frame.
            marker_info (MarkerInfo): Detected marker.
            
        Returns:
            Tuple[float, float]: (offset_x_mm, offset_y_mm)
        """
        height, width = frame.shape[:2]
        offset_x_mm, offset_y_mm = self.transform.image_center_offset_mm(
            marker_info.centroid[0],
            marker_info.centroid[1],
            width,
            height,
            marker_info.width_px,
            marker_info.height_px,
        )
        return offset_x_mm, offset_y_mm
    
    def calculate_homography_centering_correction(self, frame: np.ndarray, marker_infos: list) -> Tuple[float, float]:
        """
        Calculate XY correction using homography from 4 markers to center screen.
        
        Maps screen device coordinates to image coordinates using the 4 markers as reference points.
        
        Args:
            frame (np.ndarray): Current frame.
            marker_infos (list): List of detected markers (expects 4+ markers).
            
        Returns:
            Tuple[float, float]: (offset_x_mm, offset_y_mm) to screen center
        """
        if len(marker_infos) < 4:
            # Fallback to closest marker if less than 4 markers
            if marker_infos:
                closest = self.detector.find_closest_to_center(frame, marker_infos)
                if closest:
                    return self.calculate_centering_correction(frame, closest)
            return 0.0, 0.0
        
        # Import config to get screen dimensions
        try:
            import config
            screen_width_px = float(getattr(config, "SCREEN_WIDTH_PX", 0.0))
            screen_height_px = float(getattr(config, "SCREEN_HEIGHT_PX", 0.0))
        except (ImportError, AttributeError):
            # Fallback if config not available
            screen_width_px = 0.0
            screen_height_px = 0.0
        
        # If we don't have screen dimensions, fallback
        if screen_width_px <= 0 or screen_height_px <= 0:
            if marker_infos:
                closest = self.detector.find_closest_to_center(frame, marker_infos)
                if closest:
                    return self.calculate_centering_correction(frame, closest)
            return 0.0, 0.0
        
        height, width = frame.shape[:2]
        marker_centers = np.array([m.centroid for m in marker_infos], dtype=np.float32)
        
        # Find the 4 corners: top-left, top-right, bottom-left, bottom-right
        sums = marker_centers[:, 0] + marker_centers[:, 1]
        diffs = marker_centers[:, 1] - marker_centers[:, 0]
        
        idx_tl = int(np.argmin(sums))    # top-left: min(x+y)
        idx_br = int(np.argmax(sums))    # bottom-right: max(x+y)
        idx_tr = int(np.argmin(diffs))   # top-right: min(y-x)
        idx_bl = int(np.argmax(diffs))   # bottom-left: max(y-x)
        
        # Verify we found 4 distinct indices
        if len({idx_tl, idx_tr, idx_bl, idx_br}) != 4:
            # Fallback
            closest = self.detector.find_closest_to_center(frame, marker_infos)
            if closest:
                return self.calculate_centering_correction(frame, closest)
            return 0.0, 0.0
        
        # Marker positions in image space
        img_corners = np.array([
            marker_centers[idx_tl],
            marker_centers[idx_tr],
            marker_centers[idx_bl],
            marker_centers[idx_br]
        ], dtype=np.float32)
        
        # **CRITICAL**: Device (screen) corners - NOT frame corners!
        # These are in the actual device/screen coordinate system
        dev_corners = np.array([
            [0.0, 0.0],                      # top-left
            [screen_width_px, 0.0],          # top-right (USE SCREEN WIDTH)
            [0.0, screen_height_px],         # bottom-left (USE SCREEN HEIGHT)
            [screen_width_px, screen_height_px]  # bottom-right
        ], dtype=np.float32)
        
        # Calculate homography: from device coords to image coords
        H, _ = cv2.findHomography(dev_corners, img_corners, method=0)
        if H is None:
            # Fallback
            closest = self.detector.find_closest_to_center(frame, marker_infos)
            if closest:
                return self.calculate_centering_correction(frame, closest)
            return 0.0, 0.0
        
        # The true screen center in device coordinates
        # This is the actual center of the device screen
        dev_center = np.array([[[screen_width_px/2.0, screen_height_px/2.0]]], dtype=np.float32)
        
        # Transform device screen center to image coordinates
        img_center = cv2.perspectiveTransform(dev_center, H)[0][0]
        
        # Calculate offset from screen center to image center
        offset_x_mm, offset_y_mm = self.transform.image_center_offset_mm(
            img_center[0],
            img_center[1],
            width,
            height,
            np.mean([m.width_px for m in marker_infos]),
            np.mean([m.height_px for m in marker_infos]),
        )
        
        self.logger.debug(
            "Homography centering: screen_center_device=(%.1f, %.1f), img_center=(%.1f, %.1f), offset=(%.2f, %.2f)mm",
            screen_width_px/2.0,
            screen_height_px/2.0,
            img_center[0],
            img_center[1],
            offset_x_mm,
            offset_y_mm,
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
        # FOV-like depth estimation (perimeter ratio) is the primary strategy.
        if self.reference_marker_perimeter is not None and marker_info.perimeter > 0:
            estimated_distance = (
                self.current_target_distance
                * (self.reference_marker_perimeter / marker_info.perimeter)
            )
            return estimated_distance - self.current_target_distance

        if self.reference_marker_area is None:
            self.logger.warning("Reference marker not calibrated")
            return 0.0
        
        estimated_distance = self.transform.marker_size_to_depth(
            marker_info.area,
            self.reference_marker_area,
            self.current_target_distance
        )
        
        error = estimated_distance - self.current_target_distance
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
        
        # Apply gains.
        delta_x = correction_x * self.XY_GAIN
        delta_y = correction_y * self.XY_GAIN
        delta_z = correction_z * self.Z_GAIN

        # Clamp per-step movement to avoid runaway behavior.
        delta_x = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, delta_x))
        delta_y = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, delta_y))
        delta_z = max(-self.MAX_Z_STEP_MM, min(self.MAX_Z_STEP_MM, delta_z))

        new_x = current_pose.x - delta_x
        new_y = current_pose.y - delta_y
        new_z = current_pose.z + delta_z
        
        # Apply safety limits
        if new_z > self.Z_MAX:
            new_z = self.Z_MAX
        elif new_z < self.Z_MIN:
            new_z = self.Z_MIN
        
        current_pose.x = new_x
        current_pose.y = -new_y
        current_pose.z = new_z
        
        success = self.robot_arm.move_cartesian(current_pose)
        if not success:
            self.logger.error("Failed to move robot")
            return False
        
        self.logger.debug(
            "Applied correction raw(mm): X=%.2f Y=%.2f Z=%.2f | step(mm): dX=%.2f dY=%.2f dZ=%.2f",
            correction_x,
            correction_y,
            correction_z,
            delta_x,
            delta_y,
            delta_z,
        )
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
        best_error_mm = float("inf")
        no_improvement_iters = 0

        start_pose = self.robot_arm.get_cartesian_pose()
        if start_pose is None:
            self.logger.error("Failed to get initial robot pose for centering loop")
            return False
        start_x = float(start_pose.x)
        start_y = float(start_pose.y)
        
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
            
            # With a full set of markers, center by homography; otherwise use the marker
            # closest to the image center as fallback.
            if len(marker_infos) >= 4:
                corr_x, corr_y = self.calculate_homography_centering_correction(frame, marker_infos)
            else:
                target = self.detector.find_closest_to_center(frame, marker_infos)
                if target is None:
                    return False
                corr_x, corr_y = self.calculate_centering_correction(frame, target)
            
            error_mm = math.hypot(corr_x, corr_y)
            
            self.logger.info(f"Iteration {iteration}: X offset={corr_x:.2f}mm, Y offset={corr_y:.2f}mm")

            if error_mm + self.MIN_IMPROVEMENT_MM < best_error_mm:
                best_error_mm = error_mm
                no_improvement_iters = 0
            else:
                no_improvement_iters += 1

            current_pose = self.robot_arm.get_cartesian_pose()
            if current_pose is not None:
                drift_xy = math.hypot(float(current_pose.x) - start_x, float(current_pose.y) - start_y)
                if drift_xy > self.MAX_XY_DRIFT_MM:
                    self.logger.warning(
                        "Centering aborted: XY drift %.2fmm exceeded limit %.2fmm",
                        drift_xy,
                        self.MAX_XY_DRIFT_MM,
                    )
                    return False

            if no_improvement_iters >= self.MAX_NO_IMPROVEMENT_ITERS:
                self.logger.warning(
                    "Centering aborted: no improvement for %d iterations (best_error=%.2fmm)",
                    no_improvement_iters,
                    best_error_mm,
                )
                return False
            
            # Check convergence
            if abs(corr_x) < self.CENTRALIZE_TOLERANCE and abs(corr_y) < self.CENTRALIZE_TOLERANCE:
                self.logger.info("Centering successful")
                return True

            # Apply progressive damping based on iteration count and no-improvement streak
            # With reduced xy_gain (0.08), damping helps prevent residual oscillations
            if no_improvement_iters >= 4:
                damping = 0.5  # Aggressive damping after 4 iterations without improvement
            elif no_improvement_iters >= 2:
                damping = 0.7  # Moderate damping after 2 iterations without improvement
            elif no_improvement_iters >= 1:
                damping = 0.85  # Light damping after 1 iteration without improvement
            else:
                damping = 1.0  # No damping on first few iterations with improvement
            
            corr_x *= damping
            corr_y *= damping
            if damping < 1.0:
                self.logger.info(
                    "Applying centering damping: factor=%.2f, no_impr_iters=%d, corr=(%.2f, %.2f)",
                    damping,
                    no_improvement_iters,
                    corr_x,
                    corr_y,
                )
            
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
        recenter_iters = max(1, min(5, max_iterations))
        
        self.logger.info(f"Starting depth control loop (target={target_distance_mm}mm)")
        
        # Ensure we have reference
        if self.reference_marker_area is None:
            if not self.calibrate_distance():
                return False

        # Keep the marker near image center before depth corrections.
        if not self.run_centering_loop(max_iterations=recenter_iters):
            self.logger.error("Depth loop aborted: pre-centering failed")
            return False
        
        while iteration < max_iterations:
            frame = self.camera.capture_frame()
            if frame is None:
                return False
            
            marker_infos = self.get_markers_from_frame(frame)
            if not marker_infos:
                return False
            
            # Depth uses the most stable marker near the image center.
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

            # FOV-like strategy: recenter after each depth step to avoid drift.
            if not self.run_centering_loop(max_iterations=recenter_iters):
                self.logger.error("Depth loop aborted: re-centering failed after depth step")
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
    
    def get_touch_z(self) -> float:
        """
        Retorna a altura Z ideal para o toque, baseada na posição atual do robô após alinhamento.
        Pode ser ajustado conforme a lógica de segurança/calibração do seu sistema.
        """
        # Usa a posição Z atual do robô como referência de toque
        pose = self.robot_arm.get_cartesian_pose()
        if pose is not None:
            return pose.z
        # Fallback para altura padrão de aproximação
        return self.TARGET_DISTANCE_MM

    def get_current_pose(self) -> Optional[tuple]:
        """
        Retorna a pose cartesiana atual do robô como tupla (x, y, z, rx, ry, rz).
        Útil para guardar a pose exata após alinhamento bem-sucedido.

        Returns:
            Optional[tuple]: (x, y, z, rx, ry, rz) ou None se falhar
        """
        pose = self.robot_arm.get_cartesian_pose()
        if pose is not None:
            return (pose.x, pose.y, pose.z, pose.rx, pose.ry, pose.rz)
        return None
