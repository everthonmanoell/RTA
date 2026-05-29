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


def _build_touch_path(cal_map: CalibrationMap) -> list[tuple[float, float]]:
    """Build a small zig-zag path that covers part of the useful screen area."""
    if len(cal_map.useful_rect_px) != 4:
        raise ValueError(
            "Invalid calibration map: useful_rect_px is missing or incomplete.")

    x_min, y_min, x_max, y_max = cal_map.useful_rect_px
    x_margin = max(8.0, (x_max - x_min) * 0.08)
    y_margin = max(8.0, (y_max - y_min) * 0.08)

    inner_x_min = x_min + x_margin
    inner_x_max = x_max - x_margin
    inner_y_min = y_min + y_margin
    inner_y_max = y_max - y_margin

    if inner_x_min >= inner_x_max or inner_y_min >= inner_y_max:
        raise ValueError(
            "Useful screen area is too small to build a touch path.")

    x_levels = [
        inner_x_min,
        inner_x_min + (inner_x_max - inner_x_min) * 0.33,
        inner_x_min + (inner_x_max - inner_x_min) * 0.66,
        inner_x_max,
    ]
    y_levels = [
        inner_y_min,
        inner_y_min + (inner_y_max - inner_y_min) * 0.5,
        inner_y_max,
    ]

    path: list[tuple[float, float]] = []
    left_to_right = True
    for y_value in y_levels:
        row_x_values = x_levels if left_to_right else list(reversed(x_levels))
        for x_value in row_x_values:
            path.append((float(x_value), float(y_value)))
        left_to_right = not left_to_right

    return path


def main() -> int:
    """Load a calibration map and move the robot to the interpolated pose."""
    args = parse_args()

    map_path = Path(args.map_path)
    if not map_path.exists():
        raise FileNotFoundError(f"Calibration map not found: {map_path}")

    cal_map = CalibrationMap.from_file(map_path)
    _validate_pixel_inside_useful_rect(cal_map, args.pixel_x, args.pixel_y)
    touch_path = _build_touch_path(cal_map)

    print("Touch path (pixels):", touch_path)

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

        x_target_list = [point[0] for point in touch_path]
        y_target_list = [point[1] for point in touch_path]

        for index, (pixel_x, pixel_y) in enumerate(zip(x_target_list, y_target_list), start=1):
            target_pose = cal_map.to_pose_data(pixel_x, pixel_y)
            print(
                f"[{index}/{len(x_target_list)}] Touching pixel ({pixel_x:.1f}, {pixel_y:.1f}) -> "
                f"XYZ({target_pose.x:.2f}, {target_pose.y:.2f}, {target_pose.z:.2f})"
            )

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

            if not robot.move_cartesian(approach_pose):
                raise RuntimeError(
                    f"Failed to move above touch point {index}.")

            if not robot.move_cartesian(touch_pose):
                raise RuntimeError(f"Failed to touch point {index}.")

            if not robot.move_cartesian(approach_pose):
                raise RuntimeError(
                    f"Failed to retreat from touch point {index}.")

        return 0
    finally:
        try:
            robot.move_to_roi()
            robot.disconnect()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
