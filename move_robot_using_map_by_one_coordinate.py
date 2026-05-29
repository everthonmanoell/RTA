"""Move the robot using a previously saved calibration map."""

from __future__ import annotations

import argparse
from pathlib import Path

from drivers.robot.denso_aether import Denso
from utils.calibration_map import CalibrationMap


DEFAULT_MAP_PATH = (
    r"test_results/motorola_edge_50_fusion/"
    r"physical_calibration_map_20260506_112926_1778077766.json"
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for a map-driven robot move."""
    parser = argparse.ArgumentParser(
        description="Load a saved calibration map and move the robot to an interpolated pose.")
    parser.add_argument(
        "--json-path",
        "--map-path",
        default=DEFAULT_MAP_PATH,
        dest="map_path",
        help="Path to the physical_calibration_map JSON file to load.",
    )
    parser.add_argument(
        "--workspace",
        required=True,
        help="Denso workspace name.",
    )
    parser.add_argument(
        "--control",
        required=True,
        help="Denso control name.",
    )
    parser.add_argument(
        "--options",
        default="",
        help="Denso options string, for example Server=192.168.160.225.",
    )
    parser.add_argument(
        "--pixel-x",
        type=float,
        default=250.0,
        help="Target pixel X used for interpolation.",
    )
    parser.add_argument(
        "--pixel-y",
        type=float,
        default=180.0,
        help="Target pixel Y used for interpolation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the interpolated pose without moving the robot.",
    )
    return parser.parse_args()


def _validate_pixel_inside_useful_rect(cal_map: CalibrationMap, pixel_x: float, pixel_y: float) -> None:
    """Raise an error when the requested pixel is outside the saved useful area."""
    if len(cal_map.useful_rect_px) != 4:
        raise ValueError(
            "Invalid calibration map: useful_rect_px is missing or incomplete.")

    x_min, y_min, x_max, y_max = cal_map.useful_rect_px
    if not (x_min <= pixel_x <= x_max and y_min <= pixel_y <= y_max):
        raise ValueError(
            f"Target pixel ({pixel_x}, {pixel_y}) is outside the useful screen area "
            f"[{x_min}, {y_min}, {x_max}, {y_max}]."
        )


def main() -> int:
    """Load a calibration map and move the robot to the interpolated pose."""
    args = parse_args()

    map_path = Path(args.map_path)
    if not map_path.exists():
        raise FileNotFoundError(f"Calibration map not found: {map_path}")

    cal_map = CalibrationMap.from_file(map_path)
    _validate_pixel_inside_useful_rect(cal_map, args.pixel_x, args.pixel_y)
    target_pose = cal_map.to_pose_data(args.pixel_x, args.pixel_y)

    print(
        "Target pixel and interpolated pose:",
        {
            "pixel_x": args.pixel_x,
            "pixel_y": args.pixel_y,
            "x": target_pose.x,
            "y": target_pose.y,
            "z": target_pose.z,
            "rx": target_pose.rx,
            "ry": target_pose.ry,
            "rz": target_pose.rz,
            "fig": target_pose.fig,
        },
    )

    if args.dry_run:
        return 0

    robot = Denso(
        workspace_name=args.workspace,
        control_name=args.control,
        options=args.options,
    )

    try:
        if not robot.connect():
            raise RuntimeError("Failed to connect to the robot.")

        if not robot.motor_on():
            raise RuntimeError("Failed to enable robot motor.")

        current_pose = robot.get_cartesian_pose()
        if current_pose is None:
            raise RuntimeError("Failed to read current robot pose.")

        pose_class = current_pose.__class__
        fig = int(getattr(current_pose, "fig", 5))

        touch_z_offset_mm = 2.0
        touch_lift_offset_mm = 18.0

        approach_pose = pose_class(
            x=target_pose.x,
            y=target_pose.y,
            z=target_pose.z + touch_lift_offset_mm,
            rx=target_pose.rx,
            ry=target_pose.ry,
            rz=target_pose.rz,
            fig=fig,
        )
        touch_pose = pose_class(
            x=target_pose.x,
            y=target_pose.y,
            z=target_pose.z - touch_z_offset_mm,
            rx=target_pose.rx,
            ry=target_pose.ry,
            rz=target_pose.rz,
            fig=fig,
        )

        print(
            "Moving robot to:",
            {
                "x": touch_pose.x,
                "y": touch_pose.y,
                "z": touch_pose.z,
                "rx": touch_pose.rx,
                "ry": touch_pose.ry,
                "rz": touch_pose.rz,
                "fig": touch_pose.fig,
            },
        )

        if not robot.move_cartesian(approach_pose):
            raise RuntimeError("Failed to move above touch point.")

        if not robot.move_cartesian(touch_pose):
            raise RuntimeError("Failed to touch target point.")

        if not robot.move_cartesian(approach_pose):
            raise RuntimeError("Failed to retreat from touch point.")

        return 0
    finally:
        try:
            robot.move_to_roi()
            robot.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
