"""
MarkerDetector: Detects and processes fiducial markers in images.

This module handles ArUco marker detection, refinement, and geometric calculations.
It's designed to work with the robot-mounted camera for visual feedback control.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

import cv2
import numpy as np


@dataclass
class MarkerInfo:
    """Information about a detected marker."""
    marker_id: int
    corners: np.ndarray  # 4x2 array of corner coordinates
    centroid: np.ndarray  # (x, y) position
    area: float
    perimeter: float
    width_px: float  # width in pixels
    height_px: float  # height in pixels


class MarkerDetector:
    """
    Detects and processes ArUco markers in images.
    
    Provides methods for marker detection, refinement, filtering, and
    geometric calculations.
    """
    
    def __init__(self, marker_dict=None, fallback_dicts: Optional[Sequence] = None):
        """
        Initialize MarkerDetector.
        
        Args:
            marker_dict: ArUco dictionary to use for detection.
            fallback_dicts: Optional additional dictionaries to try when
                detection fails in the primary dictionary.
        """
        if marker_dict is None:
            marker_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)

        self.detector = cv2.aruco.ArucoDetector(marker_dict)
        self.fallback_detectors = [
            cv2.aruco.ArucoDetector(curr_dict)
            for curr_dict in (fallback_dicts or [])
        ]
        self.logger = logging.getLogger(__name__)
    
    def detect_markers(
        self,
        image: np.ndarray,
        *,
        log_missing: bool = True,
    ) -> Tuple[Optional[np.ndarray], Optional[List]]:
        """
        Detect all ArUco markers in image.
        
        Args:
            image (np.ndarray): Input image (BGR or Grayscale).
            
        Returns:
            Tuple[Optional[np.ndarray], Optional[List]]: 
                - marker_ids: Detected marker IDs (Nx1)
                - marker_corners: List of corner arrays (N x 4x2)
                Returns (None, None) if no markers detected.
        """
        corners, ids, rejected = self.detector.detectMarkers(image)
        print(f"ids from detect_markers: {ids}")
        if ids is not None and len(ids) > 0:
            for i in len(ids):
                if ids[i]== 1:
                    return ids[i], corners[0][i]
            # return ids, corners

        for idx, fallback_detector in enumerate(self.fallback_detectors, start=1):
            corners, ids, rejected = fallback_detector.detectMarkers(image)
            if ids is not None and len(ids) > 0:
                self.logger.info("Markers detected using fallback dictionary #%s", idx)
                return ids, corners
        
        # if ids is None or len(ids) == 0:
        #     if not log_missing:
        #         return None, None
        #     self.logger.warning("No markers detected")
        #     return None, None
        
        # print(f'corners from detect_markers: {corners}')
        
        # return ids, corners
    
    def refine_corners(self, image: np.ndarray, corners: List[np.ndarray]) -> List[np.ndarray]:
        """
        Refine marker corners to sub-pixel accuracy.
        
        Args:
            image (np.ndarray): Input image.
            corners (List[np.ndarray]): Detected corner arrays.
            
        Returns:
            List[np.ndarray]: Refined corners.
        """
        if image.ndim == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
        
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
        refined = []
        
        for corner in corners:
            corner_2d = corner[0].astype(np.float32)
            cv2.cornerSubPix(gray, corner_2d, (5, 5), (-1, -1), criteria)
            refined.append(corner_2d)
        
        return refined
    
    def calculate_perimeter(self, corners: np.ndarray) -> float:
        """
        Calculate marker perimeter from corners.
        
        Args:
            corners (np.ndarray): 4x2 array of corner coordinates.
            
        Returns:
            float: Perimeter in pixels.
        """
        p0, p1, p2, p3 = corners
        d1 = np.linalg.norm(p0 - p1)
        d2 = np.linalg.norm(p1 - p2)
        d3 = np.linalg.norm(p2 - p3)
        d4 = np.linalg.norm(p3 - p0)
        return d1 + d2 + d3 + d4
    
    def calculate_centroid(self, corners: np.ndarray) -> np.ndarray:
        """
        Calculate marker centroid from corners.
        
        Args:
            corners (np.ndarray): 4x2 array of corner coordinates.
            
        Returns:
            np.ndarray: (x, y) centroid position.
        """
        return np.mean(corners, axis=0)
    
    def get_marker_info(self, marker_id: int, corners: np.ndarray) -> MarkerInfo:
        """
        Extract full marker information.
        
        Args:
            marker_id (int): Marker ID.
            corners (np.ndarray): 4x2 corner array.
            
        Returns:
            MarkerInfo: Complete marker information object.
        """
        centroid = self.calculate_centroid(corners)
        area = cv2.contourArea(corners)
        perimeter = self.calculate_perimeter(corners)
        
        # Calculate width and height
        width = np.linalg.norm(corners[0] - corners[1])
        height = np.linalg.norm(corners[1] - corners[2])
        
        return MarkerInfo(
            marker_id=marker_id,
            corners=corners,
            centroid=centroid,
            area=area,
            perimeter=perimeter,
            width_px=width,
            height_px=height
        )
    
    def filter_closest_n_markers(self, image: np.ndarray, marker_infos: List[MarkerInfo], 
                                  n: int = 4) -> List[MarkerInfo]:
        """
        Filter to keep n markers closest to image center by area consistency.
        
        Args:
            image (np.ndarray): Input image (for dimension reference).
            marker_infos (List[MarkerInfo]): List of detected markers.
            n (int): Number of markers to keep.
            
        Returns:
            List[MarkerInfo]: Filtered markers.
        """
        if len(marker_infos) <= n:
            return marker_infos
        
        # Get median area
        areas = [m.area for m in marker_infos]
        median_area = np.median(areas)
        
        # Sort by closeness to median area
        discrepancies = [(abs(m.area - median_area), i) for i, m in enumerate(marker_infos)]
        discrepancies.sort(key=lambda x: x[0])
        
        best_indices = [idx for _, idx in discrepancies[:n]]
        return [marker_infos[i] for i in best_indices]
    
    def split_markers_by_image_center(self, image: np.ndarray, 
                                     marker_infos: List[MarkerInfo]) -> Tuple[List[MarkerInfo], List[MarkerInfo]]:
        """
        Split markers into left and right groups by image center.
        
        Args:
            image (np.ndarray): Input image.
            marker_infos (List[MarkerInfo]): List of markers to split.
            
        Returns:
            Tuple[List[MarkerInfo], List[MarkerInfo]]: (left_markers, right_markers)
        """
        height, width = image.shape[:2]
        center_x = width / 2
        
        left_markers = [m for m in marker_infos if m.centroid[0] < center_x]
        right_markers = [m for m in marker_infos if m.centroid[0] >= center_x]
        
        return left_markers, right_markers
    
    def find_closest_to_center(self, image: np.ndarray, 
                               marker_infos: List[MarkerInfo]) -> Optional[MarkerInfo]:
        """
        Find marker closest to image center.
        
        Args:
            image (np.ndarray): Input image.
            marker_infos (List[MarkerInfo]): List of markers.
            
        Returns:
            Optional[MarkerInfo]: Closest marker or None.
        """
        if not marker_infos:
            return None
        
        height, width = image.shape[:2]
        image_center = np.array([width / 2, height / 2])
        
        distances = [np.linalg.norm(m.centroid - image_center) for m in marker_infos]
        closest_idx = np.argmin(distances)
        
        return marker_infos[closest_idx]
    
    def rectangle_from_aruco_detection(self, image: np.ndarray,
                                         ) -> tuple[float, float, list] | tuple[None, None, None]:
        """
            Detects the ArUco marker closest to the image top left and extracts its geometric properties.

            This method processes the input image to identify ArUco markers. It filters for the
            marker nearest to the top left image point and calculates its pixel dimensions and corner
            coordinates.

            Args:
                image (np.ndarray): The input image array (typically from OpenCV) containing the ArUco marker.

            Returns:
                tuple[float, float, list] | tuple[None, None, None]: A tuple containing:
                    - width (float): The Euclidean distance between the top-left and top-right corners in pixels.
                    - height (float): The Euclidean distance between the top-right and bottom-right corners in pixels.
                    - corners (list): A list of four (x, y) coordinates representing the marker's vertices
                      [top_left, top_right, bottom_right, bottom_left].

                    Returns (None, None, None) if no marker is detected or selected.
        """
        ids, corners = self.detect_markers(image)

        print(f'corners from detect_markers: {corners}')

        if ids is not None and len(corners) > 0:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)

            for corner in corners:
                cv2.cornerSubPix(gray, corner, (5, 5), (-1, -1), criteria)

        
        top_left, top_right, bottom_right, bottom_left = corners[0]
        rec_width = np.linalg.norm(top_left - top_right)
        rec_height = np.linalg.norm(bottom_right - top_right)

        return rec_width, rec_height, [top_left, top_right, bottom_right, bottom_left]

