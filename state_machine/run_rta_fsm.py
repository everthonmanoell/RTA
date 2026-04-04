import argparse
import logging
import time

from rta import Rta
from rta_model import RtaModel

import config
from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector
from drivers.device.mobile import Mobile
from drivers.robot.denso_aether import Denso
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import (
    CameraCalibration,
    CoordinateTransform,
    RobotFrameConfig,
)
from utils.marker_touch_controller import MarkerTouchController


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RTA state machine bootstrap")
    parser.add_argument("--workspace", required=True, help="Denso workspace name")
    parser.add_argument("--control", required=True, help="Denso control name")
    parser.add_argument("--options", default="", help="Denso options string")
    parser.add_argument("--num-markers", type=int, default=4, help="Expected marker count")
    parser.add_argument("--loop-delay", type=float, default=0.05, help="Delay between FSM steps")
    parser.add_argument("--max-steps", type=int, default=5000, help="Safety max number of FSM steps")
    parser.add_argument("--touch-timeout", type=float, default=3.0, help="Seconds waiting touch feedback")
    return parser.parse_args()


def _build_operational_stack(robot: Denso):
    device = Mobile()
    camera = RobotCamera(
        camera_id=config.CAMERA_CONFIG["camera_id"],
        output_dir=config.CAMERA_CONFIG["output_dir"],
    )
    detector = MarkerDetector()

    camera_cal = CameraCalibration(
        focal_length_x=config.CAMERA_INTRINSICS["focal_length_x"],
        focal_length_y=config.CAMERA_INTRINSICS["focal_length_y"],
        principal_point_x=config.CAMERA_INTRINSICS["principal_point_x"],
        principal_point_y=config.CAMERA_INTRINSICS["principal_point_y"],
        marker_real_width_mm=config.MARKER_REAL_WIDTH_MM,
        marker_real_height_mm=config.MARKER_REAL_HEIGHT_MM,
    )
    robot_config = RobotFrameConfig(
        image_x_to_robot_axis=config.COORDINATE_MAPPING["image_x_to_robot_axis"],
        image_y_to_robot_axis=config.COORDINATE_MAPPING["image_y_to_robot_axis"],
        scale_x=config.COORDINATE_SCALE["scale_x"],
        scale_y=config.COORDINATE_SCALE["scale_y"],
    )
    transform = CoordinateTransform(camera_cal, robot_config)

    auto_align = AutoAlignment(robot, camera, detector, transform)
    controller = MarkerTouchController(
        robot_arm=robot,
        mobile_device=device,
        camera=camera,
        transform=transform,
        detector=detector,
        auto_align=auto_align,
    )

    return device, camera, detector, auto_align, controller


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    model = RtaModel(num_markers=args.num_markers)
    robot = Denso(
        workspace_name=args.workspace,
        control_name=args.control,
        options=args.options,
    )
    device, camera, detector, auto_align, controller = _build_operational_stack(robot)

    runtime = {
        "markers": [],
        "z_touch": None,
    }

    def camera_on_fn() -> bool:
        return camera.capture_frame() is not None

    def detect_markers_fn() -> bool:
        frame = camera.capture_frame()
        if frame is None:
            return False

        marker_ids, marker_corners = detector.detect_markers(frame)
        if marker_ids is None or marker_corners is None:
            runtime["markers"] = []
            return False

        refined_corners = detector.refine_corners(frame, marker_corners)
        marker_infos = [
            detector.get_marker_info(int(marker_ids[idx][0]), refined_corners[idx])
            for idx in range(len(marker_ids))
        ]
        runtime["markers"] = marker_infos
        return bool(marker_infos)

    def align_with_markers_fn() -> bool:
        if not runtime["markers"]:
            return False

        if auto_align.reference_marker_area is None and not auto_align.calibrate_distance():
            return False

        target_distance = config.TOUCH_CONFIG.get("approach_distance_mm", 150.0)
        ok = auto_align.approach_marker(target_distance)
        if ok:
            runtime["z_touch"] = auto_align.get_touch_z()
        return ok

    def touch_marker_fn(index: int) -> bool:
        markers = runtime["markers"]
        if index < 0 or index >= len(markers):
            return False

        z_touch = runtime["z_touch"]
        if z_touch is None:
            z_touch = auto_align.get_touch_z()
            runtime["z_touch"] = z_touch

        return controller.touch_marker_center(markers[index], z_touch=z_touch)

    def check_touch_fn(_index: int) -> bool:
        return device.wait_for_touch_feedback(timeout=args.touch_timeout) is not None

    def reset_markers_fn() -> None:
        frame = camera.capture_frame()
        if frame is None:
            runtime["markers"] = []
            return

        height, width = frame.shape[:2]
        center_x = width // 2
        center_y = height // 2

        z_touch = runtime["z_touch"]
        if z_touch is None:
            z_touch = auto_align.get_touch_z()
            runtime["z_touch"] = z_touch

        controller.touch_pixel(center_x, center_y, z_touch=z_touch)
        runtime["markers"] = []
        runtime["z_touch"] = None

    def swipe_borders_fn() -> bool:
        z_touch = runtime["z_touch"]
        if z_touch is None:
            z_touch = auto_align.get_touch_z()
            runtime["z_touch"] = z_touch

        points = controller.get_grid_border_points()
        if not points:
            return False

        return controller.swipe_along_points(points, z_touch=z_touch)

    def safe_pose_fn() -> None:
        robot.move_safe(preserve_orientation=True)

    def read_final_marker_fn() -> str:
        frame = camera.capture_frame()
        if frame is None:
            return model.RESULT_FAILURE

        marker_ids, _ = detector.detect_markers(frame)
        if marker_ids is None:
            return model.RESULT_FAILURE

        detected = {int(curr[0]) for curr in marker_ids}
        if config.FINAL_SUCCESS_MARKER_ID in detected:
            return model.RESULT_SUCCESS
        if config.FINAL_FAILURE_MARKER_ID in detected:
            return model.RESULT_FAILURE
        return model.RESULT_FAILURE

    def return_to_start_fn() -> None:
        frame = camera.capture_frame()
        if frame is None:
            return

        height, width = frame.shape[:2]
        center_x = width // 2
        center_y = height // 2

        z_touch = runtime["z_touch"]
        if z_touch is None:
            z_touch = auto_align.get_touch_z()
            runtime["z_touch"] = z_touch

        controller.touch_pixel(center_x, center_y, z_touch=z_touch)
        runtime["markers"] = []
        runtime["z_touch"] = None

    # Inject optional hooks to implement operational behavior for states.
    model.camera_on_fn = camera_on_fn
    model.detect_markers_fn = detect_markers_fn
    model.align_with_markers_fn = align_with_markers_fn
    model.touch_marker_fn = touch_marker_fn
    model.check_touch_fn = check_touch_fn
    model.reset_markers_fn = reset_markers_fn
    model.swipe_borders_fn = swipe_borders_fn
    model.safe_pose_fn = safe_pose_fn
    model.read_final_marker_fn = read_final_marker_fn
    model.return_to_start_fn = return_to_start_fn

    # Inject robot adapter so model callbacks can call connect/motor actions.
    model.denso_robot = robot
    machine = Rta(model)

    logging.info("FSM started at state: %s", machine.state)

    steps = 0
    while machine.state not in ["done", "error"]:
        machine.next_state()
        steps += 1

        if steps >= args.max_steps:
            logging.error("Max steps reached (%s). Stopping.", args.max_steps)
            break

        time.sleep(args.loop_delay)

    logging.info("FSM stopped at state: %s (steps=%s)", machine.state, steps)

    try:
        device.stop()
    except Exception:
        pass

    try:
        camera.release()
    except Exception:
        pass

    try:
        robot.disconnect()
    except Exception:
        pass

    return 0 if machine.state == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
