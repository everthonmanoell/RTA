"""
CoordinateTransform: Transforms image coordinates to robot coordinates.

Handles the calibration and transformation from 2D image space (where markers are
detected) to 3D robot space (where actions are executed).
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import numpy as np


@dataclass
class CameraCalibration:
    """Camera calibration parameters."""
    focal_length_x: float = 1.0
    focal_length_y: float = 1.0
    principal_point_x: float = 0.5
    principal_point_y: float = 0.5
    marker_real_width_mm: float = 100.0  # Real-world marker size in mm
    marker_real_height_mm: float = 100.0


@dataclass
class RobotFrameConfig:
    """Configuration for mapping image to robot coordinates."""
    # Image axis to robot axis mapping
    image_x_to_robot_axis: str = "X"  # or "Y"
    image_y_to_robot_axis: str = "Z"  # or "Y"
    
    # Scale factors (pixels to mm)
    scale_x: float = 1.0  # pixels/mm for X
    scale_y: float = 1.0  # pixels/mm for Y
    
    # Offset (reference points)
    image_center_x_mm: float = 0.0
    image_center_y_mm: float = 0.0
    
    # Robot reference position
    robot_ref_x: float = 0.0
    robot_ref_y: float = 0.0
    robot_ref_z: float = 0.0


class CoordinateTransform:
    """
    Transforms between image and robot coordinate systems.
    
    Handles calibration-based transformation from 2D image coordinates
    (from robot camera) to 3D robot Cartesian coordinates.
    """
    
    def __init__(self, camera_cal: Optional[CameraCalibration] = None,
                 robot_config: Optional[RobotFrameConfig] = None):
        """
        Initialize CoordinateTransform.
        
        Args:
            camera_cal (Optional[CameraCalibration]): Camera calibration parameters.
            robot_config (Optional[RobotFrameConfig]): Robot frame mapping configuration.
        """
        self.camera_cal = camera_cal or CameraCalibration()
        self.robot_config = robot_config or RobotFrameConfig()
        self.logger = logging.getLogger(__name__)
    
    def image_to_robot_2d(self, image_x: float, image_y: float, 
                         image_width: int, image_height: int) -> Tuple[float, float]:
        """
        Transform 2D image coordinates to 2D robot space.
        
        Args:
            image_x (float): X coordinate in image (pixels).
            image_y (float): Y coordinate in image (pixels).
            image_width (int): Image width in pixels.
            image_height (int): Image height in pixels.
            
        Returns:
            Tuple[float, float]: Corresponding (robot_x, robot_y) in mm relative to camera frame.
        """
        # Normalize to [-0.5, 0.5] range centered at image center
        norm_x = (image_x / image_width) - 0.5
        norm_y = (image_y / image_height) - 0.5
        
        # Apply scale (normalize to metric/metric units)
        mm_x = norm_x * image_width / self.robot_config.scale_x
        mm_y = norm_y * image_height / self.robot_config.scale_y
        
        return mm_x, mm_y
    
    def image_center_offset_mm(self, image_x: float, image_y: float,
                               image_width: int, image_height: int,
                               marker_width_px: float, marker_height_px: float) -> Tuple[float, float]:
        """
        Calculate offset in mm from image center.
        
        Uses the known marker size to calibrate pixel-to-mm conversion.
        
        Args:
            image_x (float): Marker X center in pixels.
            image_y (float): Marker Y center in pixels.
            image_width (int): Image width.
            image_height (int): Image height.
            marker_width_px (float): Detected marker width in pixels.
            marker_height_px (float): Detected marker height in pixels.
            
        Returns:
            Tuple[float, float]: (offset_x_mm, offset_y_mm) from image center.
        """
        # Calculate pixel-to-mm scale from detected marker
        scale_x = marker_width_px / self.camera_cal.marker_real_width_mm
        scale_y = marker_height_px / self.camera_cal.marker_real_height_mm
        
        # Calculate offset from image center in pixels
        center_x_px = image_width / 2
        center_y_px = image_height / 2
        
        offset_x_px = center_x_px - image_x
        offset_y_px = center_y_px - image_y
        
        # Convert to mm
        offset_x_mm = offset_x_px / scale_x
        offset_y_mm = offset_y_px / scale_y
        
        return offset_x_mm, offset_y_mm
    
    def marker_size_to_depth(self, marker_area_px: float, 
                            reference_area_px: float,
                            reference_depth_mm: float) -> float:
        """
        Estimate depth using inverse square law relationship.
        
        Args:
            marker_area_px (float): Current detected marker area.
            reference_area_px (float): Reference marker area at known distance.
            reference_depth_mm (float): Reference depth (distance) in mm.
            
        Returns:
            float: Estimated current depth in mm.
        """
        if marker_area_px <= 0:
            return reference_depth_mm
        
        # Inverse square law: Area ∝ 1/distance²
        # distance = reference_distance * sqrt(reference_area / current_area)
        estimated_depth = reference_depth_mm * np.sqrt(reference_area_px / marker_area_px)
        return estimated_depth
    
    def apply_robot_transform(self, camera_frame_x: float, camera_frame_y: float, 
                             camera_frame_z: float, 
                             current_robot_x: float, current_robot_y: float, 
                             current_robot_z: float) -> Tuple[float, float, float]:
        """
        Apply complete transformation from camera frame to new robot position.
        
        Args:
            camera_frame_x (float): X offset in camera frame (mm).
            camera_frame_y (float): Y offset in camera frame (mm).
            camera_frame_z (float): Z offset in camera frame (mm).
            current_robot_x (float): Current robot X position.
            current_robot_y (float): Current robot Y position.
            current_robot_z (float): Current robot Z position.
            
        Returns:
            Tuple[float, float, float]: New (robot_x, robot_y, robot_z).
        """
        new_x = current_robot_x
        new_y = current_robot_y
        new_z = current_robot_z
        
        # Map image axes to robot axes based on configuration
        if self.robot_config.image_x_to_robot_axis == "X":
            new_x = current_robot_x - camera_frame_x
        elif self.robot_config.image_x_to_robot_axis == "Y":
            new_y = current_robot_y + camera_frame_x
        
        if self.robot_config.image_y_to_robot_axis == "Z":
            new_z = current_robot_z + camera_frame_y
        elif self.robot_config.image_y_to_robot_axis == "Y":
            new_y = current_robot_y + camera_frame_y
        
        # Apply Z depth if provided
        if camera_frame_z != 0:
            new_x = current_robot_x + camera_frame_z
        
        return new_x, new_y, new_z
    
    def calibrate_from_reference(self, reference_marker_width_mm: float,
                                reference_marker_height_mm: float):
        """
        Calibrate transformation using a reference marker.
        
        Args:
            reference_marker_width_mm (float): Known marker width in mm.
            reference_marker_height_mm (float): Known marker height in mm.
        """
        self.camera_cal.marker_real_width_mm = reference_marker_width_mm
        self.camera_cal.marker_real_height_mm = reference_marker_height_mm
        self.logger.info(f"Calibration updated: {reference_marker_width_mm}x{reference_marker_height_mm}mm")

    def image_point_to_robot_pose(
        self,
        image_x: float,
        image_y: float,
        image_width: int,
        image_height: int,
        current_robot_x: float,
        current_robot_y: float,
        current_robot_z: float,
    ) -> tuple[float, float, float]:
        offset_x_mm, offset_y_mm = self.image_to_robot_2d(
            image_x=image_x,
            image_y=image_y,
            image_width=image_width,
            image_height=image_height,
        )

        return self.apply_robot_transform(
            camera_frame_x=offset_x_mm,
            camera_frame_y=offset_y_mm,
            camera_frame_z=0.0,
            current_robot_x=current_robot_x,
            current_robot_y=current_robot_y,
            current_robot_z=current_robot_z,
        )
