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
    CENTRALIZE_TOLERANCE = 5.0  # mm
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
    MAX_XY_STEP_MM = 5.0
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
        self.target_marker_id: Optional[int] = None
        self.last_error_px: Optional[float] = None

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

    def set_target_marker_id(self, marker_id: int) -> None:
        self.target_marker_id = int(marker_id)
        self.logger.info("Target marker set to ID=%d", self.target_marker_id)

    def _select_target_marker(
        self,
        frame: np.ndarray,
        marker_infos: list[MarkerInfo],
    ) -> Optional[MarkerInfo]:
        """
        Select the target marker.

        If target_marker_id is set, use that ID.
        Otherwise, use the marker closest to the center.
        """
        if not marker_infos:
            return None

        if self.target_marker_id is not None:
            for marker in marker_infos:
                if int(marker.marker_id) == int(self.target_marker_id):
                    return marker

            self.logger.warning(
                "Target marker ID=%d not found in the current frame",
                self.target_marker_id,
            )
            return None

        return self.detector.find_closest_to_center(frame, marker_infos)

    def compute_adaptive_gain(self, error_px: float) -> float:
        """
        Simple adaptive gain:
        - large error -> larger gain
        - small error -> smaller gain
        """
        if error_px > 40.0:
            return 0.35
        if error_px > 20.0:
            return 0.22
        if error_px > 8.0:
            return 0.12
        return 0.06

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
            marker_infos.append(self.detector.get_marker_info(
                int(marker_id[0]), corners[i]))

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
                closest = self.detector.find_closest_to_center(
                    frame, marker_infos)
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
                closest = self.detector.find_closest_to_center(
                    frame, marker_infos)
                if closest:
                    return self.calculate_centering_correction(frame, closest)
            return 0.0, 0.0

        height, width = frame.shape[:2]
        marker_centers = np.array(
            [m.centroid for m in marker_infos], dtype=np.float32)

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
        dev_center = np.array(
            [[[screen_width_px/2.0, screen_height_px/2.0]]], dtype=np.float32)

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
    
    def move_to_marker(self, erro_x: float, erro_y: float):
        pose_before = self.robot_arm.get_cartesian_pose()

        new_x = pose_before.x - erro_y
        new_y = pose_before.y - erro_x
        
        target_pose = pose_before
        target_pose.x = new_x
        target_pose.y = new_y
        
        success = self.robot_arm.move_cartesian(target_pose)
        if not success:
            self.logger.error("Failed to move robot")
            return False
        return True


    def apply_correction(
        self,
        correction_x: float,
        correction_y: float,
        correction_z: float,
    ) -> bool:
        """
        Apply XYZ correction to the robot's current pose.

        In this mode, correction_x / correction_y are already robot steps in mm.
        """
        pose_before = self.robot_arm.get_cartesian_pose()
        if pose_before is None:
            self.logger.error("Failed to get robot pose before correction")
            return False

        current_x = float(pose_before.x)
        current_y = float(pose_before.y)
        current_z = float(pose_before.z)

        # correction_x / correction_y are already steps in mm
        delta_x = correction_x
        delta_y = correction_y
        delta_z = correction_z

        delta_x = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, delta_x))
        delta_y = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, delta_y))
        delta_z = max(-self.MAX_Z_STEP_MM, min(self.MAX_Z_STEP_MM, delta_z))

        new_x, new_y, new_z = self.transform.apply_robot_transform(
            camera_frame_x=delta_x,
            camera_frame_y=delta_y,
            camera_frame_z=delta_z,
            current_robot_x=current_x,
            current_robot_y=current_y,
            current_robot_z=current_z,
        )

        if new_z > self.Z_MAX:
            new_z = self.Z_MAX
        elif new_z < self.Z_MIN:
            new_z = self.Z_MIN

        target_pose = pose_before
        target_pose.x = new_x
        target_pose.y = new_y
        target_pose.z = new_z

        self.logger.info(
            "apply_correction BEFORE move | atual=(%.2f, %.2f, %.2f) | target=(%.2f, %.2f, %.2f) | delta=(%.2f, %.2f, %.2f)",
            current_x,
            current_y,
            current_z,
            new_x,
            new_y,
            new_z,
            new_x - current_x,
            new_y - current_y,
            new_z - current_z,
        )

        success = self.robot_arm.move_cartesian(target_pose)
        if not success:
            self.logger.error("Failed to move robot")
            return False

        time.sleep(0.4)

        pose_after = self.robot_arm.get_cartesian_pose()
        if pose_after is None:
            self.logger.warning(
                "Move command sent, but could not read pose after move")
            return True

        after_x = float(pose_after.x)
        after_y = float(pose_after.y)
        after_z = float(pose_after.z)

        self.logger.info(
            "apply_correction AFTER move | pose=(%.2f, %.2f, %.2f) | real_delta=(%.2f, %.2f, %.2f)",
            after_x,
            after_y,
            after_z,
            after_x - current_x,
            after_y - current_y,
            after_z - current_z,
        )

        return True

    def run_centering_loop(self, max_iterations: int = None) -> bool:
        """
        Closed-loop centering using one marker.

        Captures a frame, detects the target marker, computes the error to the
        image center, moves the robot, and repeats until convergence.
        """
        resolved_max_iterations = int(
            max_iterations) if max_iterations is not None else int(self.MAX_ITERATIONS)
        best_error_px = float("inf")
        no_improvement_iters = 0

        start_pose = self.robot_arm.get_cartesian_pose()
        if start_pose is None:
            self.logger.error(
                "Failed to get initial robot pose for centering loop")
            return False

        start_x = float(start_pose.x)
        start_y = float(start_pose.y)

        self.logger.info(
            "Starting centering loop for target marker ID=%s | max_iterations=%d",
            str(self.target_marker_id) if self.target_marker_id is not None else "AUTO",
            resolved_max_iterations,
        )

        for iteration in range(resolved_max_iterations):
            frame = self.camera.capture_frame()
            if frame is None:
                self.logger.error("Failed to capture frame")
                return False

            marker_infos = self.get_markers_from_frame(frame)
            if not marker_infos:
                self.logger.warning("No markers in frame")
                return False

            target = self._select_target_marker(frame, marker_infos)
            if target is None:
                self.logger.warning("No target marker available for centering")
                return False

            error_x_px, error_y_px = self.calculate_centering_error_pixels(
                frame, target)
            corr_x, corr_y = self.pixel_error_to_robot_step(
                error_x_px, error_y_px)
            error_px = math.hypot(error_x_px, error_y_px)

            self.logger.info(
                "Iter %d/%d | marker=%d | centroid=(%.1f, %.1f) | erro_px=(%.2f, %.2f) | norma_px=%.2f | passo_mm=(%.2f, %.2f)",
                iteration,
                resolved_max_iterations - 1,
                int(target.marker_id),
                float(target.centroid[0]),
                float(target.centroid[1]),
                error_x_px,
                error_y_px,
                error_px,
                corr_x,
                corr_y,
            )

            if error_px + self.MIN_IMPROVEMENT_MM < best_error_px:
                best_error_px = error_px
                no_improvement_iters = 0
            else:
                no_improvement_iters += 1

            current_pose = self.robot_arm.get_cartesian_pose()
            if current_pose is not None:
                drift_xy = math.hypot(
                    float(current_pose.x) - start_x,
                    float(current_pose.y) - start_y,
                )
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
                    best_error_px,
                )
                return False

            if error_px < 20.0:
                self.logger.info(
                    "Centering successful for marker %d | final_error=%.2f mm",
                    int(target.marker_id),
                    error_px,
                )
                self.last_error_px = error_px
                return True

            moved = self.apply_correction(corr_x, corr_y, 0.0)
            if not moved:
                self.logger.warning(
                    "Failed to apply correction at iteration %d", iteration)
                return False

            self.last_error_px = error_px
            time.sleep(self.ITERATION_DELAY)

        self.logger.warning(
            "Centering loop reached max iterations | best_error=%.2f mm | last_error=%.2f mm",
            best_error_px,
            self.last_error_px if self.last_error_px is not None else -1.0,
        )
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

        self.logger.info(
            f"Starting depth control loop (target={target_distance_mm}mm)")

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

            self.logger.info(
                f"Iteration {iteration}: Depth error={corr_z:.2f}mm")

            # Check convergence
            if abs(corr_z) < self.DEPTH_TOLERANCE:
                self.logger.info("Depth control successful")
                return True

            # Apply correction
            if not self.apply_correction(0.0, 0.0, corr_z):
                return False

            # FOV-like strategy: recenter after each depth step to avoid drift.
            if not self.run_centering_loop(max_iterations=recenter_iters):
                self.logger.error(
                    "Depth loop aborted: re-centering failed after depth step")
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
        Return the ideal Z height for touch based on the robot's current post-alignment pose.

        This can be adjusted according to your system's safety/calibration logic.
        """
        # Use the robot's current Z position as the touch reference
        pose = self.robot_arm.get_cartesian_pose()
        if pose is not None:
            return pose.z
        # Fallback to the default approach height
        return self.TARGET_DISTANCE_MM

    def get_current_pose(self) -> Optional[tuple]:
        """
        Return the robot's current Cartesian pose as a tuple (x, y, z, rx, ry, rz).

        Useful for storing the exact pose after a successful alignment.

        Returns:
            Optional[tuple]: (x, y, z, rx, ry, rz) or None if retrieval fails.
        """
        pose = self.robot_arm.get_cartesian_pose()
        if pose is not None:
            return (pose.x, pose.y, pose.z, pose.rx, pose.ry, pose.rz)
        return None

    def calculate_centering_error_pixels(
        self,
        frame: np.ndarray,
        marker_info: MarkerInfo,
    ) -> tuple[float, float]:
        """
        Calculate the error in pixels between the image center and the marker center.

        Returns (error_x_px, error_y_px).
        """
        frame_h, frame_w = frame.shape[:2]
        image_cx = frame_w / 2.0
        image_cy = frame_h / 2.0

        marker_cx = float(marker_info.centroid[0])
        marker_cy = float(marker_info.centroid[1])

        error_x_px = image_cx - marker_cx
        error_y_px = image_cy - marker_cy

        return error_x_px, error_y_px

    def pixel_error_to_robot_step(
        self,
        error_x_px: float,
        error_y_px: float,
    ) -> tuple[float, float]:
        """
        Convert pixel error into robot step values in mm.

        Small gains are used to avoid overshoot.
        """
        gain_x = 0.03
        gain_y = 0.03

        step_x = error_x_px * gain_x
        step_y = error_y_px * gain_y

        # step_x = error_x_px * gain_x
        # step_y = 0.0

        # step_x = 0.0
        # step_y = error_y_px * gain_y

        step_x = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, step_x))
        step_y = max(-self.MAX_XY_STEP_MM, min(self.MAX_XY_STEP_MM, step_y))

        return step_x, step_y
    
    def calculate_single_marker_centering_correction(
                                                        self,
                                                        frame,
                                                        height,
                                                        width,
                                                        marker: MarkerInfo,
                                                    ) -> tuple[float, float]:
        """
        Calculate the XY correction required to align the image center
        with the centroid of a single ArUco marker.

        Args:
            marker: Detected marker.

        Returns:
            (dx_mm, dy_mm)
        """
        real_dimensions_mm = 54 # Isso deverá ser obtido 1 vez apenas por setup de câmera
        dimensions_px = marker[0].median_dimension 
        conversion_factor = dimensions_px/real_dimensions_mm # Valor aproximado

        frame_cx = width / 2
        frame_cy = height / 2

        marker_cx = marker[0].centroid[0]
        marker_cy = marker[0].centroid[1]

        error_px_x = marker_cx - frame_cx
        error_px_y = marker_cy - frame_cy

        dx_mm = error_px_x / conversion_factor
        dy_mm = error_px_y / conversion_factor

        return dx_mm, dy_mm
    
    def align_to_single_marker(self):
        iterations = 0
        while self.MAX_ITERATIONS > iterations: 
            frame = self.camera.capture_frame()
            if iterations % 2 == 0:
                if frame is None:
                    continue
                height, width, c = frame.shape
                marker = self.get_markers_from_frame(frame)

                if marker is None:
                    continue
                
                dx, dy = self.calculate_single_marker_centering_correction(frame, height, width, marker)
                
                if abs(dx) < 0.1:
                    dx = 0
                if abs(dy) < 0.1:
                    dy = 0

                if abs(dx) < 0.1 and abs(dy) < 0.1:
                    self.logger.info("Centered with successfull!")
                    return True
                
                if iterations > 6:
                    attenuation = 1 - np.exp(-abs(dx))
                    dx = dx * - attenuation
                    dy = dy * - attenuation

                self.move_to_marker(dx, dy)
            iterations+=1

        self.logger.warning("Maximum number of iterations reached without centering.")
        return False