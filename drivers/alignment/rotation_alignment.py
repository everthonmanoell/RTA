"""
RotationAlignment: Automatic rotation alignment (RZ axis) based on marker symmetry.

Adapted from FOV's z_aligner.py but tailored for approaching and touching markers.
Ensures the robot is perpendicular to the marker plane for accurate touching.
"""

import logging
import time
from typing import List, Optional, Tuple
import config

import numpy as np

from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.vision.robot_camera import RobotCamera


class RotationAlignment:
    """
    Manages automatic rotation (RZ) alignment of the robot.
    
    Ensures the robot approaches markers perpendicularly by maintaining
    symmetry in the detected marker perimeters (left vs right groups).
    """
    
    # Control parameters
    
    RZ_GAIN = 0.5

    MAX_ITERATIONS = 400
    interaction = 0

    ITERATION_DELAY = 0.5
    MAX_ROTATION_STEP = 5.0
    
    
    
    
    # Marker configuration
    MARKERS_PER_SIDE = 2
    MARKERS_TOTAL = 4

    detector = MarkerDetector()
    
    def __init__(self, robot_arm, camera: RobotCamera,
                 detector: Optional[MarkerDetector] = None):
        self.robot_arm = robot_arm
        self.camera = camera
        self.detector = detector or MarkerDetector()
        self.logger = logging.getLogger(__name__)
        self.aruco_widht_real_mm = config.MARKER_REAL_WIDTH_MM
        self.aruco_hight_real_mm = config.MARKER_REAL_HEIGHT_MM
        self.aligment_tolerance = config.ALIGMENT_TOLERANCE_MM
        self.touch_finger_offset_x = config.TOUCH_FINGER_OFFSET_X
        self.z_touch = config.Z_TOUCH
        self.z_limit = config.Z_LIMIT
    
    def get_frame_with_markers(self, required_count: int = 4) -> Tuple[Optional[np.ndarray], Optional[List[MarkerInfo]]]:
        frame = self.camera.capture_frame()
        if frame is None:
            return None, None
        
        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) < required_count:
            self.logger.warning(f"Expected {required_count} markers, got {len(ids) if ids is not None else 0}")
            return frame, None
        
        if len(ids) > required_count:
            corners = self.detector.refine_corners(frame, corners)
            marker_infos = [self.detector.get_marker_info(int(ids[i][0]), corners[i]) 
                           for i in range(len(ids))]
            marker_infos = self.detector.filter_closest_n_markers(frame, marker_infos, required_count)
        else:
            corners = self.detector.refine_corners(frame, corners)
            marker_infos = [self.detector.get_marker_info(int(ids[i][0]), corners[i]) 
                           for i in range(len(ids))]
        
        return frame, marker_infos
    
    def split_markers_left_right(self, frame: np.ndarray, 
                                marker_infos: List[MarkerInfo]) -> Tuple[List[MarkerInfo], List[MarkerInfo]]:
        return self.detector.split_markers_by_image_center(frame, marker_infos)
    
    def calculate_correction_angle(self) -> Optional[float]:
        frame, marker_infos = self.get_frame_with_markers(self.MARKERS_TOTAL)
        if marker_infos is None or len(marker_infos) < self.MARKERS_TOTAL:
            self.logger.error("Failed to get required markers")
            return None
        
        left_markers, right_markers = self.split_markers_left_right(frame, marker_infos)
        
        if len(left_markers) != self.MARKERS_PER_SIDE or len(right_markers) != self.MARKERS_PER_SIDE:
            self.logger.error(f"Invalid split: left={len(left_markers)}, right={len(right_markers)}")
            return None
        
        left_perimeter = sum(m.perimeter for m in left_markers)
        right_perimeter = sum(m.perimeter for m in right_markers)
        total_perimeter = left_perimeter + right_perimeter
        
        if total_perimeter == 0:
            self.logger.error("Total perimeter is zero")
            return None
        
        diff_index = (left_perimeter - right_perimeter) / total_perimeter
        sensitivity = 0.5
        angle_deg = sensitivity * diff_index * 90.0
        angle_deg = max(-45.0, min(45.0, angle_deg))
        
        self.logger.info(
            f"Perimeters: L={left_perimeter:.1f}, R={right_perimeter:.1f} | "
            f"Diff={diff_index:.4f} | Angle={angle_deg:.2f} deg"
        )
        
        return angle_deg
    
    def apply_rz_correction(self, angle_degrees: float) -> bool:
        if abs(angle_degrees) > self.MAX_ROTATION_STEP:
            angle_degrees = self.MAX_ROTATION_STEP * (1 if angle_degrees > 0 else -1)
        
        current_pose = self.robot_arm.get_cartesian_pose()
        if current_pose is None:
            self.logger.error("Failed to get robot pose")
            return False
        
        new_rz = current_pose.rz + angle_degrees * self.RZ_GAIN
        current_pose.rz = new_rz
        
        success = self.robot_arm.move_cartesian(current_pose)
        if not success:
            self.logger.error("Failed to move robot")
            return False
        
        self.logger.info(f"Applied RZ correction: {angle_degrees:.2f} deg (gain applied)")
        return True
    
    def run_alignment_loop(self, max_iterations: int = None) -> bool:
        max_iterations = max_iterations or self.MAX_ITERATIONS
        iteration = 0
        
        self.logger.info("Starting RZ alignment loop")
        
        while iteration < max_iterations:
            angle_error = self.calculate_correction_angle()
            if angle_error is None:
                self.logger.error("Failed to calculate correction angle")
                return False
            
            self.logger.info(f"Iteration {iteration}: Angle error = {angle_error:.2f} deg")
            
            if abs(angle_error) < self.ALIGNMENT_TOLERANCE:
                self.logger.info("RZ alignment successful")
                return True
            
            if not self.apply_rz_correction(angle_error):
                return False
            
            time.sleep(self.ITERATION_DELAY)
            iteration += 1
        
        self.logger.warning("RZ alignment reached max iterations")
        return False
    


    #todo doing
    def error_diff_between_single_marker_and_image_center_on_mm(
    self,
    id_target: int
    ) -> Optional[Tuple[float, float]]:
        frame = self.camera.capture_frame()
        if frame is None:
            self.logger.error("Failed to capture frame for error calculation")
            return None

        id_found, corners = self.detector.detect_single_marker_by_id(frame, id_target)
        if id_found is None or corners is None:
            self.logger.warning(f"Marker ID {id_target} not found for error calculation")
            return None

        marker_info = self.detector.get_marker_info(id_target, corners)

        width_aruco_pixel = marker_info.width_px
        height_aruco_pixel = marker_info.height_px

        if width_aruco_pixel <= 0 or height_aruco_pixel <= 0:
            self.logger.warning(
                "Invalid marker dimensions for error calculation: width=%.2f, height=%.2f",
                width_aruco_pixel, height_aruco_pixel
            )
            return None

        scale_x = self.aruco_widht_real_mm / width_aruco_pixel
        scale_y = self.aruco_hight_real_mm / height_aruco_pixel

        center_x_img, center_y_img = self.camera.center_point(frame)
        center_aruco_x, center_aruco_y = marker_info.centroid

        error_px_x = center_aruco_x - center_x_img
        error_px_y = center_aruco_y - center_y_img

        error_mm_x = error_px_x * scale_x
        error_mm_y = error_px_y * scale_y

        self.logger.info(
            "Erro de alinhamento: x=%.2f mm, y=%.2f mm",
            error_mm_x,
            error_mm_y,
        )

        return (error_mm_x, error_mm_y)

    #### adding new methods to align the robot with the center of the marker ###
    #TODO verify if this works
    def adjust_robot_to_marker_center(
        self,
        error_diff: tuple[float, float],
        first_attempt: bool = False
    ) -> bool:
        current_pose = self.robot_arm.get_cartesian_pose()
        if current_pose is None:
            self.logger.error("Failed to get robot pose for center alignment")
            return False

        error_x = error_diff[0]  # erro visual em X
        error_y = error_diff[1]  # erro visual em Y

        # =================================================================
        # LÓGICA DE CONVERGÊNCIA RÁPIDA
        # =================================================================
        if first_attempt:
            gain_x = 1.0  # Anda 100% do erro
            gain_y = 1.0  # Anda 100% do erro
            error_y = (error_y / 4.0) * 3.0
            error_x = (error_x / 4.0) * 3.0
            self.logger.info("FIRST ATTEMPT: Aplicando ganho de 100% para convergência rápida e 3/4 do erro.")
        else:
            min_step_mm = 0.4
            gain_x = min_step_mm if abs(error_y) <= 2 else 0.10
            gain_y = min_step_mm if abs(error_x) <= 2 else 0.10

        # Note o cruzamento de eixos (X do robô recebe Y da câmera e vice-versa)
        adjustment_x = gain_x * error_y
        adjustment_y = gain_y * error_x

        current_pose.x += adjustment_x
        current_pose.y += adjustment_y

        self.logger.info(
            f"Ajuste aplicado: dx={adjustment_x:.2f} mm, dy={adjustment_y:.2f} mm | "
            f"erro_x={error_x:.2f} mm, erro_y={error_y:.2f} mm"
        )
        
        # self.robot_arm.set_arm_speed(10, 5, 5)
        success = self.robot_arm.move_cartesian(current_pose)
        if not success:
            self.logger.error("Failed to move robot for center alignment")
            return False

        return True
    
    
    
    # def auto_adjust_robot_to_marker_center(self, marker_infos: List[MarkerInfo]) -> bool:
        
