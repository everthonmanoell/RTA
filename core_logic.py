import logging
import time

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

from state_machine import RobotFSM, State


# --- Inicialização dos componentes ---
def initialize_components():
    robot = Denso(
        workspace_name="YOUR_WORKSPACE",
        control_name="YOUR_CONTROL",
        options=""
    )
    if not robot.connect():
        raise RuntimeError("Falha ao conectar ao robô")

    robot.motor_on()

    device = Mobile()

    camera = RobotCamera(
        camera_id=config.CAMERA_CONFIG["camera_id"],
        output_dir=config.CAMERA_CONFIG["output_dir"]
    )

    return robot, device, camera


# --- Função para detectar botão vermelho ---
def detect_red_button_center(frame):
    import cv2
    import numpy as np

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower_red1 = np.array([0, 70, 50])
    upper_red1 = np.array([10, 255, 255])

    lower_red2 = np.array([170, 70, 50])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = mask1 | mask2

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    c = max(contours, key=cv2.contourArea)
    M = cv2.moments(c)

    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])

    return (cx, cy)


# --- Função principal ---
def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )

    robot, device, camera = initialize_components()

    try:
        # --- Configuração de transformação ---
        camera_cal = CameraCalibration(
            focal_length_x=500.0,
            focal_length_y=500.0,
            principal_point_x=0.5,
            principal_point_y=0.5,
            marker_real_width_mm=config.MARKER_REAL_WIDTH_MM,
            marker_real_height_mm=config.MARKER_REAL_HEIGHT_MM
        )

        robot_config = RobotFrameConfig(
            image_x_to_robot_axis=config.COORDINATE_MAPPING["image_x_to_robot_axis"],
            image_y_to_robot_axis=config.COORDINATE_MAPPING["image_y_to_robot_axis"],
            scale_x=config.COORDINATE_SCALE["scale_x"],
            scale_y=config.COORDINATE_SCALE["scale_y"]
        )

        transform = CoordinateTransform(camera_cal, robot_config)

        # --- Componentes de visão e alinhamento ---
        detector = MarkerDetector()
        auto_align = AutoAlignment(robot, camera, detector, transform)

        # --- Controller operacional ---
        controller = MarkerTouchController(
            robot_arm=robot,
            mobile_device=device,
            camera=camera,
            transform=transform,
            detector=detector,
            auto_align=auto_align,
        )

        # --- Máquina de estados ---
        fsm = RobotFSM(
            robot=robot,
            device=device,
            camera=camera,
            detector=detector,
            controller=controller,
            auto_align=auto_align,
            detect_red_button_fn=detect_red_button_center
        )

        # --- Loop principal ---
        while fsm.state not in [State.SUCCESS, State.ERROR]:
            fsm.run_step()
            time.sleep(0.1)

        logging.info(f"Processo finalizado com estado: {fsm.state.name}")

    finally:
        device.stop()


if __name__ == "__main__":
    main()