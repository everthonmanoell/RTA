"""
MarkerDetector: Detects and processes fiducial markers in images.

This module handles ArUco marker detection, refinement, and geometric calculations.
It's designed to work with the robot-mounted camera for visual feedback control.
"""
import cv2
import logging
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


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
    median_dimension: float


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
        marker_dict = None
        if marker_dict is None:
            marker_dict = cv2.aruco.getPredefinedDictionary(
                cv2.aruco.DICT_APRILTAG_36h11)

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
        # 1. Tentativa no detector principal
        corners, ids, _ = self.detector.detectMarkers(image)

        # 2. Se falhar, tenta nos fallbacks
        if ids is None or len(ids) == 0:
            for idx, fallback_detector in enumerate(self.fallback_detectors, start=1):
                corners, ids, _ = fallback_detector.detectMarkers(image)
                if ids is not None and len(ids) > 0:
                    self.logger.info(
                        "Markers detected using fallback dictionary #%s", idx)
                    break

        if ids is None or len(ids) == 0:
            if log_missing:
                self.logger.warning("No markers detected")
            return None, None

        return ids, corners

    def detect_single_marker_by_id(
        self,
        image: np.ndarray,
        target_id: int
    ) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """
        Search for a specific marker by ID across the entire image.
        """
        ids, corners = self.detect_markers(image)

        if ids is not None:
            ids_flat = ids.flatten()
            indices = np.where(ids_flat == target_id)[0]

            if len(indices) > 0:
                idx = indices[0]
# Returns the ID and corners for that specific marker
                return ids[idx], corners[idx]

        return None, None

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

        criteria = (cv2.TERM_CRITERIA_EPS +
                    cv2.TERM_CRITERIA_MAX_ITER, 100, 0.001)
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

        if corners.ndim == 3:
            corners = corners[0]

        centroid = self.calculate_centroid(corners)
        area = cv2.contourArea(corners)
        perimeter = self.calculate_perimeter(corners)

        # Calculate width and height
        width = np.linalg.norm(corners[0] - corners[1])
        height = np.linalg.norm(corners[1] - corners[2])

        dimension = np.median([width, height, perimeter/4, area**0.5])

        return MarkerInfo(
            marker_id=marker_id,
            corners=corners,
            centroid=centroid,
            area=area,
            perimeter=perimeter,
            width_px=width,
            height_px=height,
            median_dimension=dimension,
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
        discrepancies = [(abs(m.area - median_area), i)
                         for i, m in enumerate(marker_infos)]
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

        distances = [np.linalg.norm(m.centroid - image_center)
                     for m in marker_infos]
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

        top_left, top_right, bottom_right, bottom_left = corners[0]
        rec_width = np.linalg.norm(top_left - top_right)
        rec_height = np.linalg.norm(bottom_right - top_right)

        return rec_width, rec_height, [top_left, top_right, bottom_right, bottom_left]


# TODO doing the detector aruco and util area


    def get_aruco_union_rectangle(self, marker_infos: List[MarkerInfo]) -> Optional[Tuple[int, int, int, int]]:
        """Return the bounding rectangle that encloses all detected markers."""
        if not marker_infos:
            return None

        all_corners = np.vstack(
            [np.asarray(marker.corners, dtype=np.float32) for marker in marker_infos])
        x_min = int(np.floor(np.min(all_corners[:, 0])))
        y_min = int(np.floor(np.min(all_corners[:, 1])))
        x_max = int(np.ceil(np.max(all_corners[:, 0])))
        y_max = int(np.ceil(np.max(all_corners[:, 1])))
        return x_min, y_min, x_max, y_max

    def get_aruco_screen_offsets(
        self,
        image: np.ndarray,
        union_rect: Tuple[int, int, int, int],
    ) -> dict:
        """Return the pixel offsets from the marker union rectangle to the image borders."""
        height, width = image.shape[:2]
        x_min, y_min, x_max, y_max = union_rect
        return {
            "left": float(max(0, x_min)),
            "top": float(max(0, y_min)),
            "right": float(max(0, width - x_max)),
            "bottom": float(max(0, height - y_max)),
            "image_width": float(width),
            "image_height": float(height),
        }

    def get_useful_screen_rectangle(
        self,
        image: np.ndarray,
        marker_infos: List[MarkerInfo],
    ) -> Optional[Tuple[int, int, int, int]]:
        """Estimate the useful screen rectangle from the bright screen area in the image."""
        quad = self.get_useful_screen_quad(image, marker_infos)
        if quad is None:
            return None
        return self.useful_quad_to_bbox(quad)

    def get_useful_screen_quad(self, image: np.ndarray, marker_infos: List[MarkerInfo]) -> Optional[np.ndarray]:
        """Detect the main bright screen region inside the marker cluster."""
        if image is None or len(marker_infos) < 4:
            return None

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 180, 255, cv2.THRESH_BINARY)
        kernel = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) <= 0:
            return None

        rect = cv2.minAreaRect(largest)
        box = cv2.boxPoints(rect)
        return box.astype(np.float32)

    def estimate_useful_screen_quad(
        self,
        marker_infos: List[MarkerInfo],
        screen_width_px: float,
        screen_height_px: float,
        margin_px: float,
        tag_size_px: float,
    ) -> Optional[np.ndarray]:
        """Project the app's useful screen area into image coordinates.

        The app places the four markers at known device-space locations.
        We use those correspondences to build a homography from device-space
        to image-space and then project the inner usable rectangle.
        """
        if len(marker_infos) < 4:
            return None
        if screen_width_px <= 0 or screen_height_px <= 0 or tag_size_px <= 0:
            return None

        marker_by_id = {marker.marker_id: marker for marker in marker_infos}
        required_ids = (1, 2, 3, 4)
        if any(marker_id not in marker_by_id for marker_id in required_ids):
            return None

        left = float(margin_px)
        top = float(margin_px)
        right = float(screen_width_px - margin_px - tag_size_px)
        bottom = float(screen_height_px - margin_px - tag_size_px)

        if right <= left or bottom <= top:
            return None

        device_pts = []
        image_pts = []

        layout_points = {
            1: (left, top),
            4: (right, top),
            2: (right, bottom),
            3: (left, bottom),
        }

        for marker_id, (device_x, device_y) in layout_points.items():
            marker = marker_by_id[marker_id]
            # Corners come in [top-left, top-right, bottom-right, bottom-left]
            marker_device_pts = np.array(
                [
                    [device_x, device_y],
                    [device_x + tag_size_px, device_y],
                    [device_x + tag_size_px, device_y + tag_size_px],
                    [device_x, device_y + tag_size_px],
                ],
                dtype=np.float32,
            )
            device_pts.append(marker_device_pts)
            image_pts.append(np.asarray(marker.corners, dtype=np.float32))

        src = np.vstack(device_pts).reshape((-1, 1, 2))
        dst = np.vstack(image_pts).reshape((-1, 1, 2))

        h_mat, status = cv2.findHomography(src, dst, method=0)
        if h_mat is None or status is None:
            return None

        usable_device_quad = np.array(
            [
                [left + tag_size_px, top + tag_size_px],
                [right, top + tag_size_px],
                [right, bottom],
                [left + tag_size_px, bottom],
            ],
            dtype=np.float32,
        ).reshape((-1, 1, 2))

        projected = cv2.perspectiveTransform(
            usable_device_quad, h_mat).reshape((-1, 2))
        return projected

    def useful_quad_to_bbox(self, useful_quad: np.ndarray) -> Tuple[int, int, int, int]:
        x_min = int(np.floor(np.min(useful_quad[:, 0])))
        y_min = int(np.floor(np.min(useful_quad[:, 1])))
        x_max = int(np.ceil(np.max(useful_quad[:, 0])))
        y_max = int(np.ceil(np.max(useful_quad[:, 1])))
        return x_min, y_min, x_max, y_max

    def get_rect_gap(self, outer_rect: Tuple[int, int, int, int], inner_rect: Tuple[int, int, int, int]) -> dict:
        """Return the gap in pixels between two axis-aligned rectangles."""
        outer_left, outer_top, outer_right, outer_bottom = outer_rect
        inner_left, inner_top, inner_right, inner_bottom = inner_rect
        return {
            "left": float(max(0, inner_left - outer_left)),
            "top": float(max(0, inner_top - outer_top)),
            "right": float(max(0, outer_right - inner_right)),
            "bottom": float(max(0, outer_bottom - inner_bottom)),
        }

    def get_safe_interaction_zone(
        self,
        image: np.ndarray,
        marker_infos: List[MarkerInfo]
    ) -> Optional[dict]:
        """
        Calculate safe zone for robot movement (swipe).
        The safe zone is the intermediate rectangle between the external edge
        of ArUcos and the edge of the screen's useful area.

        Args:
            image: Camera image.
            marker_infos: List of detected markers.

        Returns:
            Dict with original rectangles and 4 safe swipe points,
            or None if calculation fails.
        """
        if len(marker_infos) < 4:
            self.logger.warning(
                "Less than 4 markers detected. Unable to calculate safe zone.")
            return None

        # 1. Get rectangle enclosing all 4 ArUcos
        union_rect = self.get_aruco_union_rectangle(marker_infos)
        if union_rect is None:
            return None

        # 2. Get rectangle of bright useful screen area
        useful_rect = self.get_useful_screen_rectangle(image, marker_infos)
        if useful_rect is None:
            self.logger.warning(
                "Useful screen area not detected by brightness.")
            return None

        # Unpack coordinates
        x_min, y_min, x_max, y_max = union_rect
        u_x_min, u_y_min, u_x_max, u_y_max = useful_rect

        # 3. Calculate Middle Rectangle (Gap between ArUco and Screen Edge)
        mid_x_min = (x_min + u_x_min) / 2.0
        mid_y_min = (y_min + u_y_min) / 2.0
        mid_x_max = (x_max + u_x_max) / 2.0
        mid_y_max = (y_max + u_y_max) / 2.0

        # 4. Pack points in target sequence: 1 -> 4 -> 2 -> 3
        return {
            "aruco_rect": union_rect,
            "screen_rect": useful_rect,
            "safe_swipe_points": {
                "pt_1": (mid_x_min, mid_y_max),  # Near ID 1 (Bottom-Left)
                "pt_4": (mid_x_min, mid_y_min),  # Near ID 4 (Top-Left)
                "pt_2": (mid_x_max, mid_y_min),  # Near ID 2 (Top-Right)
                "pt_3": (mid_x_max, mid_y_max)  # Near ID 3 (Bottom-Right)
            }
        }

    def is_alignment_passed(
        self,
        image: np.ndarray,

    ) -> bool:

        marker_success_id = 14
        marker_failed_id = 15

        id, corners = self.detect_markers(image)
        if id is None or corners is None:
            self.logger.warning(
                "No markers detected for alignment evaluation.")
            return False
        marker_info = self.get_marker_info(int(id[0]), corners[0])
        if marker_info is None:
            self.logger.warning(
                "Unable to extract marker information for alignment evaluation.")
            return False

        if marker_info.marker_id == marker_success_id:
            self.logger.info("Success marker detected. Alignment passed.")
            return True
        else:
            self.logger.info("Failure marker detected. Alignment failed.")
            return False


def _draw_rect(image: np.ndarray, rect: Tuple[int, int, int, int], color: Tuple[int, int, int], thickness: int) -> np.ndarray:
    annotated = image.copy()
    x_min, y_min, x_max, y_max = rect
    cv2.rectangle(annotated, (x_min, y_min), (x_max, y_max), color, thickness)
    return annotated


def _draw_union_rectangle(image: np.ndarray, union_rect: Tuple[int, int, int, int]) -> np.ndarray:
    return _draw_rect(image, union_rect, (0, 255, 255), 3)


def _draw_quad(image: np.ndarray, quad: np.ndarray, color: Tuple[int, int, int], thickness: int) -> np.ndarray:
    annotated = image.copy()
    polygon = np.round(quad).astype(np.int32).reshape((-1, 1, 2))
    cv2.polylines(annotated, [polygon], isClosed=True,
                  color=color, thickness=thickness)
    return annotated
