import argparse
import json
import logging
import os
import subprocess
import time
import sys
import threading
import random
from pathlib import Path
from types import MethodType

import cv2
import numpy as np
from aether_rdk.datatypes import Offset3D, Pose
from rta import Rta
from rta_model import RtaModel

import config
from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector
from drivers.device.mobile import Mobile, TouchTracker, TouchRecording, map_raw_touch_to_screen, toggle_android_setting
from utils.touch_session_recorder import TouchSessionRecorder
from utils.calibration_map_exporter import CalibrationMapExporter
from drivers.robot.denso_aether import Denso
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import (
    CameraCalibration,
    CoordinateTransform,
    RobotFrameConfig,
)
from utils.coordinate_transform import get_z_on_screen_plane, get_z_with_scipy_mesh, interpolate_robot_pose
from utils.marker_touch_controller import MarkerTouchController
from utils.metrics_logger import MetricsLogger
from drivers.alignment.rotation_alignment import RotationAlignment
# from move_robot_using_map_by_one_coordinate import execute_keyboard

# Configure logging once at module import time so handlers persist across
# repeated calls to `main()` (e.g. when running `for ...: main()`).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# =============================================================================
# INFRA — ARGS E STACK
# =============================================================================

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for RTA FSM execution.

    Returns:
        argparse.Namespace: Parsed arguments including workspace, control, device type,
            and FSM execution parameters.
    """
    parser = argparse.ArgumentParser(
        description="Run RTA state machine bootstrap")
    parser.add_argument("--workspace", required=True,
                        help="Denso workspace name")
    parser.add_argument("--control", required=True, help="Denso control name")
    parser.add_argument("--options", default="", help="Denso options string")
    parser.add_argument(
        "--num-markers",
        type=int,
        default=None,
        help="Expected marker count. If omitted, inferred from --device-type",
    )
    parser.add_argument(
        "--device-type",
        default=os.getenv("RTA_DEVICE_TYPE", "flat"),
        help="Device layout profile (flat, foldable, one, two, three, six, seven, eight)",
    )
    parser.add_argument(
        "--device-side",
        type=str,
        default="portrait",
        help="Device side orientation (portrait/landscape) used for swipe ordering",
    )
    parser.add_argument("--loop-delay", type=float,
                        default=0.05, help="Delay between FSM steps")
    parser.add_argument("--max-steps", type=int, default=5000,
                        help="Safety max number of FSM steps")
    parser.add_argument("--touch-timeout", type=float,
                        default=3.0, help="Seconds waiting touch feedback")
    parser.add_argument("--metrics-dir", default="test_results",
                        help="Output directory for metrics")
    parser.add_argument(
        "--save-detect-debug",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Enable/disable saving annotated detect_markers debug images",
    )
    parser.add_argument(
        "--show-camera-preview",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable/disable live camera preview window during FSM execution",
    )
    parser.add_argument(
        "--stop-at-state",
        default=None,
        help="Stop execution as soon as the FSM reaches this state (e.g. camera_on)",
    )
    args = parser.parse_args(argv)
    metrics_dir_args = argv if argv is not None else sys.argv[1:]
    args.metrics_dir_provided = any(
        arg == "--metrics-dir" or arg.startswith("--metrics-dir=")
        for arg in metrics_dir_args
    )
    return args


def _configure_tool_from_config(robot: Denso) -> bool:
    """Configure the robot tool from configuration settings.

    Args:
        robot (Denso): The Denso robot instance to configure.

    Returns:
        bool: True if tool configuration succeeded or was disabled, False otherwise.
    """
    tool_cfg = getattr(config, "TOOL_CONFIG", {})
    if not isinstance(tool_cfg, dict):
        logging.error("Invalid TOOL_CONFIG: expected dict.")
        return False

    if not tool_cfg.get("enabled", False):
        logging.info("TOOL_CONFIG disabled; proceeding without changing tool.")
        return True

    tag = str(tool_cfg.get("tag", "pen_tool"))
    offset = Offset3D(
        x=float(tool_cfg.get("offset_x", 0.0)),
        y=float(tool_cfg.get("offset_y", 0.0)),
        z=float(tool_cfg.get("offset_z", 0.0)),
        rx=float(tool_cfg.get("offset_rx", 0.0)),
        ry=float(tool_cfg.get("offset_ry", 0.0)),
        rz=float(tool_cfg.get("offset_rz", 0.0)),
    )

    if not robot.create_tool_reference(offset, tag):
        logging.error("Failed to create tool reference '%s'.", tag)
        return False

    if not robot.set_current_tool_by_tag(tag):
        logging.error("Failed to select tool '%s'.", tag)
        return False

    logging.info("Tool '%s' configured and activated successfully.", tag)
    return True


def _build_operational_stack(robot: Denso):
    """Build the operational stack with all required hardware and software components.

    Args:
        robot (Denso): The Denso robot instance.

    Returns:
        tuple: A tuple containing (device, camera, detector, auto_align, controller, transform).
    """
    device = Mobile()
    camera = RobotCamera(
        camera_id=config.CAMERA_CONFIG["camera_id"],
        output_dir=config.CAMERA_CONFIG["output_dir"],
        show_preview=False,
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

    return device, camera, detector, auto_align, controller, transform


# =============================================================================
# PHASE 1 — CONNECTION AND INITIAL POSITIONING
# =============================================================================

def _connect_and_home(robot: Denso) -> bool:
    """Connect robot, enable motor, and move to ROI.

    Args:
        robot (Denso): The Denso robot instance.

    Returns:
        bool: True if connection and homing succeeded, False otherwise.
    """
    logging.info("Connecting robot for isolated centralization test...")

    if not robot.connect():
        logging.error("Failed to connect with the robot.")
        return False

    if not robot.motor_on():
        logging.error("Failed to turn on the robot motor.")
        robot.disconnect()
        return False

    robot.set_arm_speed(10, 5, 5)

    try:
        if hasattr(robot, "move_to_roi"):
            bool(robot.move_to_roi())
        else:
            robot.move_to_roi()
    except Exception as exc:
        logging.warning("Failed to move to ROI/safe pose: %s", exc)

    logging.info("Manual Cartesian movement test...")

    pose0 = robot.get_cartesian_pose()
    if pose0 is None:
        logging.error("Could not read initial robot pose.")
        robot.disconnect()
        return False

    logging.info(
        "Initial pose: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
        float(pose0.x), float(pose0.y), float(pose0.z),
        float(pose0.rx), float(pose0.ry), float(pose0.rz),
    )

    time.sleep(0.5)

    # TODO TEM QUE MORRER ESSE TRECHO
    pose1 = robot.get_cartesian_pose()
    if pose1 is not None:
        logging.info(
            "Pose after manual test: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
            float(pose1.x), float(pose1.y), float(pose1.z),
            float(pose1.rx), float(pose1.ry), float(pose1.rz),
        )

    return True


# =============================================================================
# PHASE 2 — GLOBAL VISION (ROBOT AT ROI)
# =============================================================================

def _detect_markers_from_roi(robot: Denso, camera: RobotCamera, detector: MarkerDetector):
    """Move to ROI, capture frame, and detect ArUco markers.

    Args:
        robot (Denso): The Denso robot instance.
        camera (RobotCamera): The camera instance for frame capture.
        detector (MarkerDetector): The marker detector instance.

    Returns:
        tuple: (frame, ids, corners, marker_infos, safe_zone_data) on success,
               None on failure.
    """
    logging.info(
        "Capturing image from ROI to calculate swipe area...")

    robot.move_to_roi()
    current_roi_pose = robot.get_cartesian_pose()

    detected_successfully = False
    ids, corners, frame = None, None, None
    height_px, width_px = 0, 0

    max_tentativas = 10
    for tentativa in range(max_tentativas):
        frame = camera.capture_frame()

        if frame is None:
            logging.warning(
                f"Attempt {tentativa + 1}: Null frame returned by camera.")
            time.sleep(0.5)
            continue

        height_px, width_px = frame.shape[:2]
        ids, corners = detector.detect_markers(frame, log_missing=False)

        if ids is not None and len(ids) >= 4:
            logging.info(
                f"Success! The 4 markers were detected on attempt {tentativa + 1}.")
            detected_successfully = True
            break
        else:
            qtd_encontrada = len(ids) if ids is not None else 0
            logging.warning(
                f"Attempt {tentativa + 1}/{max_tentativas}: Only {qtd_encontrada} markers found. "
                "Waiting for the app screen to open..."
            )
            time.sleep(0.5)

    if not detected_successfully:
        logging.error(
            "Fatal Error: Could not detect 4 markers in ROI after 10 attempts.")
        return None

    marker_infos = [
        detector.get_marker_info(int(marker_id[0]), corners[idx])
        for idx, marker_id in enumerate(ids)
    ]

    safe_zone_data = detector.get_safe_interaction_zone(frame, marker_infos)
    if safe_zone_data is None:
        logging.error("Error calculating safe swipe zone.")
        return None

    return frame, ids, corners, marker_infos, safe_zone_data


# =============================================================================
# PHASE 3 — Z PLANE CALIBRATION (TOUCH ON 4 ARUCOS)
# =============================================================================

def _move_to_return_touched_place(robot: Denso, pose) -> bool:
    """Move robot back to touched position with safety Z offset.

    Creates a copy of the pose to avoid corrupting the original pose stored in the
    interpolation position list.

    Args:
        robot (Denso): The Denso robot instance.
        pose (Pose): The touch position pose to return to.

    Returns:
        bool: True if movement succeeded, False otherwise.
    """
    if pose is None:
        logging.error(
            "Touch pose is None. Cannot move to touch position.")
        return False

    safe_pose = Pose(
        x=float(pose.x),
        y=float(pose.y),
        z=float(pose.z) + config.Z_OFFSET_BEFORE_TOUCH,
        rx=float(pose.rx),
        ry=float(pose.ry),
        rz=float(pose.rz),
        fig=int(getattr(pose, "fig", 1))
    )

    logging.info(
        "Moving to retreat position (with offset): x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
        safe_pose.x, safe_pose.y, safe_pose.z,
        safe_pose.rx, safe_pose.ry, safe_pose.rz,
    )

    success = robot.move_cartesian(safe_pose)
    if not success:
        logging.error("Failed to move to retreat position.")
    return success


def _calibrate_z_touches(
    robot: Denso,
    camera: RobotCamera,
    detector: MarkerDetector,
    device: Mobile,
    session_recorder: TouchSessionRecorder,
) -> list | None:
    """Align robot to each ArUco marker and record touch positions for Z calibration.

    Uses session_recorder to monitor device touch events during the calibration process.
    Performs controlled descent until touch is detected or Z limit is reached.

    Args:
        robot (Denso): The Denso robot instance.
        camera (RobotCamera): The camera instance for marker detection.
        detector (MarkerDetector): The marker detector instance.
        device (Mobile): The mobile device instance.
        session_recorder (TouchSessionRecorder): The touch event recorder.

    Returns:
        list[Pose]: List of 4 touch position poses if successful, None if calibration failed.
    """
    logging.info(
        "Starting touch routine on ArUcos to map 3D Plane (Z)...")

    interpolation_position = []
    rotation_aligment = RotationAlignment(robot, camera, detector)

    ALIGNMENT_TOLERANCE = config.ALIGMENT_TOLERANCE_MM
    Z_TOUCH = config.Z_TOUCH
    Z_LIMIT = config.Z_LIMIT
    TOUCH_FINGER_OFFSET_X = config.TOUCH_FINGER_OFFSET_X
    TOUCH_FINGER_OFFSET_Y = config.TOUCH_FINGER_OFFSET_Y

    max_interations = 400

    try:
        for id in range(1, 5):
            logging.info(f"####### Aligning for ArUco ID {id}... #######")
            interation = 0
            first_valid_diff = False

            while interation < max_interations:
                interation += 1

                diff_error = rotation_aligment.error_diff_between_single_marker_and_image_center_on_mm(
                    id)
                if diff_error is None:
                    time.sleep(0.3)
                    continue

                error_mm_x, error_mm_y = diff_error

                # If BOTH axes are aligned, we stop. At exact center!
                if abs(error_mm_x) < ALIGNMENT_TOLERANCE and abs(error_mm_y) < ALIGNMENT_TOLERANCE:
                    logging.info(
                        f"ArUco {id} perfectly aligned. Stopping.")
                    break

                # If ANY of the axes (X or Y) is out, adjust.
                if abs(error_mm_x) >= ALIGNMENT_TOLERANCE or abs(error_mm_y) >= ALIGNMENT_TOLERANCE:
                    # "first attempt" = first time we receive a valid diff, not just iteration 1.
                    is_first_attempt = not first_valid_diff
                    rotation_aligment.adjust_robot_to_marker_center(
                        (error_mm_x, error_mm_y),
                        is_first_attempt,
                    )
                    first_valid_diff = True

                time.sleep(0.3)

            current_position = robot.get_cartesian_pose()
            print(f'type of current_position: {type(current_position)}')

            if current_position is not None:
                logging.info(
                    "Final pose after alignment: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
                    float(current_position.x), float(
                        current_position.y), float(current_position.z),
                    float(current_position.rx), float(
                        current_position.ry), float(current_position.rz),
                )

                # Arma o gatilho do gravador global modular
                touch_detected_event = threading.Event()
                touch_feedback_holder = {"value": None}
                session_recorder.arm_trigger(
                    "down", touch_feedback_holder, touch_detected_event)

                current_position.x += TOUCH_FINGER_OFFSET_X
                current_position.y += TOUCH_FINGER_OFFSET_Y
                # TODO this part 1 is causing double descent - fix the config.Z_OFFSET_BEFORE_TOUCH
                current_position.z = Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH
                ok = robot.move_cartesian(current_position)
                logging.info(
                    "Move to pre-touch (offset + initial z): %s", ok)
                if not ok:
                    logging.error("Failed to move to pre-touch position.")
                    return None

                step = 1

                while True:
                    current_position = robot.get_cartesian_pose()
                    if current_position is None:
                        logging.error(
                            "Failed to get current robot pose during descent to touch.")
                        robot.move_to_roi()
                        break

                    # 1) Global Thread trigger — maximum priority
                    if touch_detected_event.is_set():
                        logging.info(
                            "Touch detected by phone at %s. Stopping robot descent.",
                            touch_feedback_holder["value"]
                        )
                        current_position = robot.get_cartesian_pose()
                        interpolation_position.append(current_position)
                        logging.info(
                            "Pose registered for interpolation: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(
                                current_position.y), float(current_position.z),
                            float(current_position.rx), float(
                                current_position.ry), float(current_position.rz),
                        )
                        _move_to_return_touched_place(robot, current_position)
                        robot.move_to_roi()
                        break

                    # 2) If reached desired touch range, stop and save position
                    if current_position.z <= Z_LIMIT:
                        logging.info(
                            "Touch range reached with Z_TOUCH: %.2f mm. Stopping robot.",
                            float(current_position.z)
                        )
                        interpolation_position.append(current_position)
                        logging.info(
                            "Pose registered for interpolation: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(
                                current_position.y), float(current_position.z),
                            float(current_position.rx), float(
                                current_position.ry), float(current_position.rz),
                        )
                        # TODO this part 2 is causing double descent
                        _move_to_return_touched_place(robot, current_position)
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    logging.info(
                        "Descending to touch: step %d, current pose z=%.2f mm",
                        step,
                        float(current_position.z),
                    )

                    # 3) Controlled descent until Z_TOUCH
                    if current_position.z > Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH:
                        current_position.z -= 5.0
                    elif current_position.z > Z_TOUCH + 5.0:
                        current_position.z -= 0.2
                    else:
                        current_position.z -= 0.1

                    ok = robot.move_cartesian(current_position)
                    logging.info(
                        "Result of move_cartesian during descent: %s", ok)

                    if not ok:
                        logging.error(
                            "Failure in move_cartesian during descent to touch.")
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    step += 1
                    time.sleep(0.2)

    finally:
        logging.info(
            "Alignment and touch completed. Performing safe cleanup.")

    if len(interpolation_position) < 4:
        logging.error("The robot failed to touch all 4 markers.")
        return None

    return interpolation_position


# =============================================================================
# PHASE 4 — SWIPE ON USABLE SCREEN
# =============================================================================

def _build_swipe_params(interpolation_position: list, marker_infos: list, safe_zone_data: dict, device_side: str = "portrait") -> dict:
    """Build all swipe parameters from calibrated touch positions.

    Calculates swipe points at the exact corners of the usable screen area with margin
    offsets, using bilinear interpolation from the 4 calibrated touch positions.

    Args:
        interpolation_position (list): List of 4 calibrated Pose objects.
        marker_infos (list): List of marker information objects.
        safe_zone_data (dict): Dictionary containing safe zone screen rectangle.

    Returns:
        dict: Dictionary with touch_poses_dict, centroid_rect_px, perfect_swipe_points,
              pose_referencia, safe rotations, and marker_infos.
    """
    touch_poses_dict = {}
    for idx, target_id in enumerate([1, 2, 3, 4]):
        touch_poses_dict[target_id] = interpolation_position[idx]

    # Scale reference: limit of ArUco centers (not external border)
    c_x_min = min(m.centroid[0] for m in marker_infos)
    c_y_min = min(m.centroid[1] for m in marker_infos)
    c_x_max = max(m.centroid[0] for m in marker_infos)
    c_y_max = max(m.centroid[1] for m in marker_infos)
    centroid_rect_px = (c_x_min, c_y_min, c_x_max, c_y_max)

    # Swipe points: exact corners of usable screen with margin offset
    u_x_min, u_y_min, u_x_max, u_y_max = safe_zone_data["screen_rect"]

    OFF_SET_SWIPE = 7
    u_x_min += OFF_SET_SWIPE
    u_y_max -= OFF_SET_SWIPE
    u_x_max -= OFF_SET_SWIPE
    u_y_min += OFF_SET_SWIPE

    perfect_swipe_points = {
        "pt_1": (u_x_min, u_y_max),  # Bottom-Left Corner of Usable Screen
        "pt_4": (u_x_min, u_y_min),  # Top-Left Corner of Usable Screen
        "pt_2": (u_x_max, u_y_min),  # Top-Right Corner of Usable Screen
        "pt_3": (u_x_max, u_y_max),  # Bottom-Right Corner of Usable Screen
    }

    # Freeze orientation from the moment Z was measured (Anti-Pendulum)
    pose_referencia = touch_poses_dict[1]
    safe_rx = float(pose_referencia.rx)
    safe_ry = float(pose_referencia.ry)
    safe_rz = float(pose_referencia.rz)
    safe_fig = int(getattr(pose_referencia, "fig", 1))

    return {
        "touch_poses_dict":    touch_poses_dict,
        "centroid_rect_px":    centroid_rect_px,
        "perfect_swipe_points": perfect_swipe_points,
        "pose_referencia":     pose_referencia,
        "safe_rx":  safe_rx,
        "safe_ry":  safe_ry,
        "safe_rz":  safe_rz,
        "safe_fig": safe_fig,
        "device_side": device_side,
        "marker_infos": marker_infos,  # TODO added this
    }


def _orientation_device(side: str) -> list[str]:
    """Determine device orientation based on the device orientation.

    Args:
        side (str): The device orientation ("portrait" or "landscape").

    Returns:
        list[str]: List of orientation descriptors for the given orientation.
    """
    if side == "landscape":
        # landscape orientation
        return ["pt_1", "pt_4", "pt_2", "pt_3", "pt_1"]
    elif side == "portrait":
        return ["pt_3", "pt_1", "pt_4", "pt_2", "pt_3"]  # portrait orientation
    else:
        logging.warning(
            f"Invalid side {side} for device orientation. Defaulting to ['unknown'].")
        return ["unknown"]


def _execute_swipe(robot: Denso, swipe_params: dict) -> bool:
    """Execute perimetral swipe on screen using bilinear interpolation.

    Moves the robot along the perimeter of the usable screen area, calculating
    X, Y via bilinear interpolation and Z via bilinear interpolation.

    Args:
        robot (Denso): The Denso robot instance.
        swipe_params (dict): Dictionary containing swipe parameters from _build_swipe_params.

    Returns:
        bool: True if swipe execution succeeded, False otherwise.
    """
    logging.info(
        "Calculating X,Y via bilinear interpolation and Z via bilinear interpolation on usable screen...")

    touch_poses_dict = swipe_params["touch_poses_dict"]
    centroid_rect_px = swipe_params["centroid_rect_px"]
    perfect_swipe_points = swipe_params["perfect_swipe_points"]
    marker_infos = swipe_params["marker_infos"]
    safe_rx = swipe_params["safe_rx"]
    safe_ry = swipe_params["safe_ry"]
    safe_rz = swipe_params["safe_rz"]
    safe_fig = swipe_params["safe_fig"]

    Z_SWIPE_OFFSET = -3.0
    PASSOS_POR_RETA = 15
    OFF_SET_SWIPE = 3

    # Determine swipe trajectory according to device orientation side
    trajeto = _orientation_device(swipe_params.get("device_side", "portrait"))
    logging.info("Preparing to execute Swipe in Safe Zone...")

    for i in range(len(trajeto) - 1):
        pt_start_name = trajeto[i]
        pt_end_name = trajeto[i + 1]

        px_start, py_start = perfect_swipe_points[pt_start_name]
        px_end, py_end = perfect_swipe_points[pt_end_name]

        logging.info(
            f"Tracing aligned line from {pt_start_name} to {pt_end_name}...")

        for step in range(PASSOS_POR_RETA + 1):
            fraction = step / float(PASSOS_POR_RETA)
            px_current = px_start + (px_end - px_start) * fraction
            py_current = py_start + (py_end - py_start) * fraction

            target_x, target_y, target_z = interpolate_robot_pose(
                target_px=px_current,
                target_py=py_current,
                union_rect_px=centroid_rect_px,
                touch_poses_dict=touch_poses_dict,
                marker_infos=marker_infos,
            )

            target_z_afinado = target_z + Z_SWIPE_OFFSET
            target_x_afinado = target_x
            target_y_afinado = target_y

            swipe_pose = Pose(
                x=target_x_afinado,
                y=target_y_afinado,
                z=target_z_afinado,
                rx=safe_rx,
                ry=safe_ry,
                rz=safe_rz,
                fig=safe_fig,
            )

            robot.move_cartesian(swipe_pose)

    logging.info("Perimetral swipe completed successfully!")
    robot.move_to_roi()
    return True


# =============================================================================
# FINAL DETECTION VERIFICATION
# =============================================================================

def _check_calibration_success(
    camera: RobotCamera,
    detector: MarkerDetector,
    max_attempts: int = 10,
    attempt_delay_s: float = 0.5,
) -> bool:
    """Verify calibration success by detecting success/failure markers at ROI.

    Attempts multiple times to capture and detect the success or failure markers.
    Returns True if success marker detected, False if failure marker detected.

    Args:
        camera (RobotCamera): The camera instance for frame capture.
        detector (MarkerDetector): The marker detector instance.
        max_attempts (int): Maximum number of detection attempts. Defaults to 10.
        attempt_delay_s (float): Delay between attempts in seconds. Defaults to 0.5.

    Returns:
        bool: True if success marker detected, False if failure marker or timeout.
    """
    success_marker_id = int(getattr(config, "FINAL_SUCCESS_MARKER_ID", 14))
    failure_marker_id = int(getattr(config, "FINAL_FAILURE_MARKER_ID", 15))

    for attempt in range(1, max_attempts + 1):
        frame_ = camera.capture_frame()
        if frame_ is None:
            logging.warning(
                "ROI final marker check attempt %d/%d: null frame.",
                attempt, max_attempts,
            )
            time.sleep(attempt_delay_s)
            continue

        marker_ids, _ = detector.detect_markers(frame_, log_missing=False)
        if marker_ids is None or len(marker_ids) == 0:
            logging.warning(
                "ROI final marker check attempt %d/%d: no marker detected.",
                attempt, max_attempts,
            )
            time.sleep(attempt_delay_s)
            continue

        detected_ids = {int(curr[0]) for curr in marker_ids}
        logging.info(
            "ROI final marker check attempt %d/%d: detected_ids=%s",
            attempt, max_attempts, sorted(detected_ids),
        )

        if success_marker_id in detected_ids:
            logging.info("Success marker detected in final ROI.")
            print(f'detected_ids [true]={detected_ids}')
            return True

        if failure_marker_id in detected_ids:
            logging.error("Failure marker detected in final ROI.")
            print(f'detected_ids [false]={detected_ids}')
            return False

        time.sleep(attempt_delay_s)

    logging.error(
        "ROI final marker check exhausted %d attempts without detecting success marker (%d).",
        max_attempts, success_marker_id,
    )
    return False


def _is_marker_detection_successful_in_roi(
    camera: RobotCamera,
    detector: MarkerDetector,
) -> bool:
    """Check if calibration was successful (FSM callback wrapper).

    Compatibility wrapper that calls _check_calibration_success for use in FSM callbacks.

    Args:
        camera (RobotCamera): The camera instance for frame capture.
        detector (MarkerDetector): The marker detector instance.

    Returns:
        bool: True if success marker detected at ROI, False otherwise.
    """
    return _check_calibration_success(camera, detector)


# =============================================================================
# PHASE 5 — SAVE CALIBRATION MAP
# =============================================================================

def _save_calibration_map(
    args: argparse.Namespace,
    device_type: str,
    frame,
    marker_infos: list,
    swipe_params: dict,
    detector: MarkerDetector,
    session_recorder: TouchSessionRecorder,
    run_start_ts: float,
    is_calibration_succeed: bool,
) -> None:
    """Stop recorder, generate and save calibration map.

    Stops the touch session recorder, extracts calibration data, and exports the
    calibration map with touch interaction data and execution metrics.

    Args:
        args (argparse.Namespace): Parsed command-line arguments.
        device_type (str): The device type (e.g., 'flat', 'foldable').
        frame: The captured frame from camera.
        marker_infos (list): List of marker information objects.
        swipe_params (dict): Dictionary containing swipe parameters.
        detector (MarkerDetector): The marker detector instance.
        session_recorder (TouchSessionRecorder): The touch event recorder.
        run_start_ts (float): Timestamp when execution started.
        is_calibration_succeed (bool): Whether calibration was successful.

    Returns:
        None
    """
    # Stop recorder to not add more points
    session_recorder.stop()

    touch_poses_dict = swipe_params["touch_poses_dict"]
    centroid_rect_px = swipe_params["centroid_rect_px"]
    pose_referencia = swipe_params["pose_referencia"]

    useful_rect = detector.get_useful_screen_rectangle(frame, marker_infos)

    export_ok = CalibrationMapExporter.export(
        output_dir=args.metrics_dir,
        device_type=device_type,
        device_model=str(getattr(config, "DEVICE_MODEL",
                         "unknown")).strip() or "unknown",
        useful_rect_px=useful_rect,
        centroid_rect_px=centroid_rect_px,
        marker_infos=marker_infos,
        touch_poses_dict=touch_poses_dict,
        safe_pose=pose_referencia,
        execution_duration_s=(time.time() - run_start_ts),
        calibration_succeed=is_calibration_succeed,
        dir_separation=not bool(getattr(args, "metrics_dir_provided", False)),
    )
    if not export_ok:
        logging.error("Failed to export calibration map.")


# =============================================================================
# PHASE 6 — CLEANUP
# =============================================================================

def _cleanup(device: Mobile, camera: RobotCamera, robot: Denso, session_recorder=None) -> int:
    """Clean up hardware resources and gracefully disconnect.

    Stops the mobile device, releases camera, and disconnects the robot.
    Handles exceptions gracefully to ensure all resources are freed.

    Args:
        device (Mobile): The mobile device instance.
        camera (RobotCamera): The camera instance.
        robot (Denso): The Denso robot instance.
        session_recorder (TouchSessionRecorder, optional): The touch recorder to stop.
            Defaults to None.

    Returns:
        int: Always returns 0.
    """
    try:
        if session_recorder is not None:
            session_recorder.stop()
    except Exception:
        pass

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

    return 0


# =============================================================================
# MAIN — orchestrates phases in the same order as the original flow
# =============================================================================

def main() -> int:
    """Main entry point for RTA state machine execution.

    Orchestrates the complete RTA calibration workflow:
    1. Parses arguments and initializes hardware stack
    2. Creates FSM with callback-based architecture
    3. Executes state transitions until completion or error
    4. Cleans up resources and returns status

    Returns:
        int: 0 if FSM completed successfully, 1 if error or max steps reached.
    """
    args = parse_args()
    run_start_ts = time.time()

    # --- Resolve num_markers ---
    markers_by_device_type = {
        "flat": 4, "foldable": 8, "one": 1, "two": 2,
        "three": 3, "six": 6, "seven": 7, "eight": 8,
    }
    device_type = str(args.device_type).strip().lower()
    inferred_markers = markers_by_device_type.get(device_type, 4)
    resolved_num_markers = int(
        args.num_markers) if args.num_markers is not None else inferred_markers
    resolved_num_markers = max(1, resolved_num_markers)
    args.num_markers = resolved_num_markers

    logging.info(
        "Runtime marker target: device_type=%s, num_markers=%d",
        device_type,
        args.num_markers,
    )

    # --- Initialize model and robot ---
    model = RtaModel(num_markers=args.num_markers)
    robot = Denso(
        workspace_name=args.workspace,
        control_name=args.control,
        options=args.options,
    )

    # --- Disable touch debugger ---
    def __turn_on_or_turn_off_debugger_touch(enable: bool):
        """Toggle Android touch debugging visualization.

        Args:
            enable (bool): Whether to enable or disable touch debugging.
        """
        toggle_android_setting(setting_name="show_touches", enable=enable)
        toggle_android_setting(setting_name="pointer_location", enable=enable)

    __turn_on_or_turn_off_debugger_touch(enable=False)

    # --- Inject motor_on with tool into model ---
    def _turn_motor_on_action_with_tool(self):
        """Enable motor and configure tool automatically.

        Injected callback that turns on the robot motor and configures the tool
        from the TOOL_CONFIG settings. Resets attempt counter on success.
        """
        self.motor_on_attempt += 1
        if not self.robot_connected_flag or self.denso_robot is None:
            self.motor_on_flag = False
            return
        try:
            self.motor_on_flag = bool(self.denso_robot.motor_on())
            if self.motor_on_flag:
                if _configure_tool_from_config(robot):
                    robot.set_arm_speed(50, 25, 25)
                    self.motor_on_attempt = 0
                else:
                    self.motor_on_flag = False
                    self.motor_on_attempt = 0
        except Exception:
            self.motor_on_flag = False

    model.turn_motor_on_action = MethodType(
        _turn_motor_on_action_with_tool, model)

    # --- Build operational stack ---
    device, camera, detector, auto_align, controller, transform = _build_operational_stack(
        robot)

    # --- Initialize modular global recorder ---
    session_recorder = TouchSessionRecorder(device)
    session_recorder.start()

    runtime = {
        "frame": None,
        "ids": None,
        "corners": None,
        "marker_infos": None,
        "safe_zone_data": None,
        "interpolation_position": None,
        "swipe_params": None,
        "is_calibration_succeed": False,
    }

    def move_to_roi_fn() -> bool:
        """FSM callback: Move robot to region of interest.

        Returns:
            bool: True if movement succeeded, False otherwise.
        """
        try:
            return bool(robot.move_to_roi())
        except Exception as exc:
            logging.error("Failed to move to ROI: %s", exc)
            return False

    def camera_on_fn() -> bool:
        """FSM callback: Validate camera is operational.

        Returns:
            bool: True if camera capture succeeded, False otherwise.
        """
        try:
            frame = camera.capture_frame()
            return frame is not None
        except Exception as exc:
            logging.error("Failed to validate camera: %s", exc)
            return False

    def detect_markers_fn() -> bool:
        """FSM callback: Detect markers and populate runtime data.

        Returns:
            bool: True if marker detection succeeded, False otherwise.
        """
        result = _detect_markers_from_roi(robot, camera, detector)
        if result is None:
            model.markers_count = 0
            return False

        frame, ids, corners, marker_infos, safe_zone_data = result

        runtime["frame"] = frame
        runtime["ids"] = ids
        runtime["corners"] = corners
        runtime["marker_infos"] = marker_infos
        runtime["safe_zone_data"] = safe_zone_data

        model.markers_count = len(marker_infos)
        return True

    def calibrate_z_touches_fn() -> bool:
        """FSM callback: Calibrate Z positions via touch on markers.

        Returns:
            bool: True if all 4 markers were touched, False otherwise.
        """
        interpolation_position = _calibrate_z_touches(
            robot=robot,
            camera=camera,
            detector=detector,
            device=device,
            session_recorder=session_recorder,
        )

        if interpolation_position is None:
            runtime["interpolation_position"] = None
            return False

        runtime["interpolation_position"] = interpolation_position
        return True

    def generate_map_fn() -> bool:
        """FSM callback: Generate swipe parameters from calibration data.

        Returns:
            bool: True if parameter generation succeeded, False otherwise.
        """
        try:
            runtime["swipe_params"] = _build_swipe_params(
                interpolation_position=runtime["interpolation_position"],
                marker_infos=runtime["marker_infos"],
                safe_zone_data=runtime["safe_zone_data"],
                device_side=args.device_side,
            )
            return True
        except Exception as exc:
            logging.error("Failed to generate map/swipe parameters: %s", exc)
            return False

    def swipe_borders_fn() -> bool:
        """FSM callback: Execute perimetral swipe on screen.

        Returns:
            bool: True if swipe execution succeeded, False otherwise.
        """
        return bool(_execute_swipe(robot, runtime["swipe_params"]))

    def safe_pose_fn() -> bool:
        """FSM callback: Return robot to safe ROI position.

        Returns:
            bool: True if movement succeeded, False otherwise.
        """
        try:
            robot.move_to_roi()
            time.sleep(3)
            return True
        except Exception as exc:
            logging.error("Failed to return to ROI/safe pose: %s", exc)
            return False

    def read_final_marker_fn() -> str:
        """FSM callback: Check final calibration success marker.

        Returns:
            str: model.RESULT_SUCCESS or model.RESULT_FAILURE.
        """
        ok = _is_marker_detection_successful_in_roi(camera, detector)
        runtime["is_calibration_succeed"] = bool(ok)

        if ok:
            return model.RESULT_SUCCESS

        return model.RESULT_FAILURE

    def save_map_fn() -> bool:
        """FSM callback: Save calibration map and session data.

        Returns:
            bool: True if export succeeded, False otherwise.
        """
        try:
            _save_calibration_map(
                args=args,
                device_type=device_type,
                frame=runtime["frame"],
                marker_infos=runtime["marker_infos"],
                swipe_params=runtime["swipe_params"],
                detector=detector,
                session_recorder=session_recorder,
                run_start_ts=run_start_ts,
                is_calibration_succeed=runtime["is_calibration_succeed"],
            )
            return True
        except Exception as exc:
            logging.error("Failed to save calibration map: %s", exc)
            return False

    model.denso_robot = robot
    model.move_to_roi_fn = move_to_roi_fn
    model.camera_on_fn = camera_on_fn
    model.detect_markers_fn = detect_markers_fn
    model.calibrate_z_touches_fn = calibrate_z_touches_fn
    model.generate_map_fn = generate_map_fn
    model.swipe_borders_fn = swipe_borders_fn
    model.safe_pose_fn = safe_pose_fn
    model.read_final_marker_fn = read_final_marker_fn
    model.save_map_fn = save_map_fn

    machine = Rta(model)

    try:
        steps = 0
        while machine.state not in ["done", "error"]:
            logging.info("FSM CURRENT STATE: %s", machine.state)

            current_state = machine.state
            machine.next_state()
            next_state = machine.state
            steps += 1

            logging.info("FSM: %s -> %s", current_state, next_state)

            if args.stop_at_state and next_state == args.stop_at_state:
                logging.info("Stop target reached: %s", next_state)
                break

            if steps >= args.max_steps:
                logging.error(
                    "Max steps reached (%s). Stopping.", args.max_steps)
                break

            time.sleep(args.loop_delay)
            subprocess.run("adb shell input keyevent KEYCODE_HOME", shell=True)
            time.sleep(1)
            subprocess.run("adb shell input tap 590 900", shell=True)
            robot.disconnect()
            # execute_keyboard()
    finally:
        _cleanup(device, camera, robot, session_recorder)

    return 0 if machine.state == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
