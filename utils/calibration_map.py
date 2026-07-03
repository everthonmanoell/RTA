"""Helpers to load and use saved physical calibration maps.

The exporter stores a JSON with the four physical screen corners, marker samples,
and safe robot orientation. This module turns that JSON back into a reusable
object for external callers.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import copy

from utils.coordinate_transform import interpolate_robot_pose


@dataclass(frozen=True)
class CalibrationMarkerInfo:
    """Minimal marker description required by interpolate_robot_pose."""

    marker_id: int
    centroid: Tuple[float, float]


@dataclass(frozen=True)
class RobotPose:
    """Pose data reconstructed from the saved calibration map."""

    x: float
    y: float
    z: float
    rx: float = 0.0
    ry: float = 0.0
    rz: float = 0.0
    fig: int = 1

    def as_dict(self) -> Dict[str, float]:
        """Return a plain dictionary representation."""
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "rx": self.rx,
            "ry": self.ry,
            "rz": self.rz,
            "fig": self.fig,
        }


@dataclass(frozen=True)
class SafeOrientation:
    """Robot orientation snapshot stored in the calibration map."""

    rx: float
    ry: float
    rz: float
    fig: int = 1

    def as_dict(self) -> Dict[str, float]:
        """Return a plain dictionary representation."""
        return {
            "rx": self.rx,
            "ry": self.ry,
            "rz": self.rz,
            "fig": self.fig,
        }


class CalibrationMap:
    """Runtime helper for a previously exported calibration map."""

    def __init__(
        self,
        raw_data: Dict[str, Any],
        source_path: Path | None = None,
    ) -> None:
        self.raw_data = raw_data
        self.source_path = source_path
        self.device_type = str(raw_data.get("device_type", "unknown"))
        self.calibration_mode = str(
            raw_data.get("calibration_mode", "unknown"))
        self.calibration_succeed = bool(
            raw_data.get("calibration_succeed", False))
        self.useful_rect_px = tuple(raw_data.get("useful_rect_px", []))
        self._touch_poses_dict = self._build_touch_poses_dict(
            raw_data.get("markers", []))
        self._marker_infos = self._build_marker_infos(
            raw_data.get("markers", []))
        self._safe_orientation = self._build_safe_orientation(
            raw_data.get("safe_orientation", {}))
        self.physical_screen_corners_mm = raw_data.get(
            "physical_screen_corners_mm", {})

    @classmethod
    def from_file(cls, file_path: str | Path) -> "CalibrationMap":
        """Load a calibration map from a JSON file."""
        path = Path(file_path)
        with path.open("r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)
            raw_data = dict(raw_data)
            raw_data = cls._data_adjustes(raw_data)
        return cls(raw_data=raw_data, source_path=path)

    @classmethod
    def from_dict(cls, raw_data: Dict[str, Any]) -> "CalibrationMap":
        """Create a calibration map from an in-memory dictionary."""
        return cls(raw_data=raw_data, source_path=None)

    @staticmethod
    def _build_touch_poses_dict(markers: Iterable[Dict[str, Any]]) -> Dict[int, RobotPose]:
        touch_poses_dict: Dict[int, RobotPose] = {}
        for marker in markers:
            marker_id = int(marker["marker_id"])
            touch_poses_dict[marker_id] = RobotPose(
                x=float(marker["robot_x"]),
                y=float(marker["robot_y"]),
                z=float(marker["robot_z"]),
            )
        return touch_poses_dict

    @staticmethod
    def _build_marker_infos(markers: Iterable[Dict[str, Any]]) -> List[CalibrationMarkerInfo]:
        marker_infos: List[CalibrationMarkerInfo] = []
        for marker in markers:
            marker_infos.append(
                CalibrationMarkerInfo(
                    marker_id=int(marker["marker_id"]),
                    centroid=(float(marker["pixel_x"]),
                              float(marker["pixel_y"])),
                )
            )
        return marker_infos

    @staticmethod
    def _build_safe_orientation(safe_orientation: Dict[str, Any]) -> SafeOrientation:
        return SafeOrientation(
            rx=float(safe_orientation.get("rx", 0.0)),
            ry=float(safe_orientation.get("ry", 0.0)),
            rz=float(safe_orientation.get("rz", 0.0)),
            fig=int(safe_orientation.get("fig", 1)),
        )

    @property
    def touch_poses_dict(self) -> Dict[int, RobotPose]:
        """Return the touch poses keyed by marker ID."""
        return self._touch_poses_dict

    @property
    def marker_infos(self) -> List[CalibrationMarkerInfo]:
        """Return the marker centroids used by the interpolation routine."""
        return self._marker_infos

    @property
    def safe_orientation(self) -> SafeOrientation:
        """Return the stored safe robot orientation."""
        return self._safe_orientation

    def to_robot_pose(self, target_px: float, target_py: float) -> Tuple[float, float, float]:
        """Convert a pixel coordinate into a robot pose using the saved map."""
        if len(self.useful_rect_px) != 4:
            raise ValueError(
                "Invalid calibration map: useful_rect_px is missing or incomplete.")

        return interpolate_robot_pose(
            target_px=target_px,
            target_py=target_py,
            union_rect_px=tuple(self.useful_rect_px),
            touch_poses_dict=self.touch_poses_dict,
            marker_infos=self.marker_infos,
        )

    def to_robot_pose_with_orientation(
        self,
        target_px: float,
        target_py: float,
    ) -> RobotPose:
        """Convert a pixel coordinate into a reconstructed robot pose.

        The returned pose keeps the stored safe orientation and uses the
        interpolated XYZ from the saved calibration map.
        """
        robot_x, robot_y, robot_z = self.to_robot_pose(target_px, target_py)
        return RobotPose(
            x=robot_x,
            y=robot_y,
            z=robot_z,
            rx=self.safe_orientation.rx,
            ry=self.safe_orientation.ry,
            rz=self.safe_orientation.rz,
            fig=self.safe_orientation.fig,
        )

    def to_pose_kwargs(self, target_px: float, target_py: float) -> Dict[str, float]:
        """Return keyword arguments ready to build a robot Pose.

        External callers can pass the returned dictionary directly to the
        robot pose constructor used by their runtime, for example:

            pose = Pose(**cal_map.to_pose_kwargs(px, py))
        """
        pose = self.to_robot_pose_with_orientation(target_px, target_py)
        return pose.as_dict()

    def to_pose_data(self, target_px: float, target_py: float) -> RobotPose:
        """Alias for the fully reconstructed robot pose."""
        return self.to_robot_pose_with_orientation(target_px, target_py)

    def get_corner(self, name: str) -> Dict[str, float]:
        """Return one of the physical screen corners from the saved JSON."""
        corners = self.physical_screen_corners_mm
        if name not in corners:
            raise KeyError(f"Corner '{name}' not found in calibration map.")
        return corners[name]

    def to_dict(self) -> Dict[str, Any]:
        """Return the original raw calibration payload."""
        return dict(self.raw_data)
    
    def _data_adjustes(raw_data: dict) -> dict:
        dados_atualizados = copy.deepcopy(raw_data)
        
        useful_rect = dados_atualizados.get("useful_rect_px", [])
        corners = dados_atualizados.get("physical_screen_corners_mm", {})
        
        if len(useful_rect) < 4 or not corners:
            return dados_atualizados

        for marker in dados_atualizados.get("markers", []):
            m_id = marker.get("marker_id")
            
            if m_id in (1, 3):
                marker["pixel_x"] = float(useful_rect[0])
            elif m_id in (2, 4):
                marker["pixel_x"] = float(useful_rect[2])
                
            if m_id in (1, 4):
                marker["pixel_y"] = float(useful_rect[1])
            elif m_id in (2, 3):
                marker["pixel_y"] = float(useful_rect[3])

            corner_key = None
            if m_id == 1:
                corner_key = "top_left"
            elif m_id == 2:
                corner_key = "bottom_right"
            elif m_id == 3:
                corner_key = "bottom_left"
            elif m_id == 4:
                corner_key = "top_right"
                
            if corner_key and corner_key in corners:
                marker["robot_x"] = corners[corner_key]["x"]
                marker["robot_y"] = corners[corner_key]["y"]
                marker["robot_z"] = corners[corner_key]["z"]

        return dados_atualizados
