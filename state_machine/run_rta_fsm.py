import argparse
import json
import logging
import os
import time
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

# Configure logging once at module import time so handlers persist across
# repeated calls to `main()` (e.g. when running `for ...: main()`).
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)


# =============================================================================
# INFRA — ARGS E STACK
# =============================================================================

def parse_args() -> argparse.Namespace:
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
    return parser.parse_args()


def _configure_tool_from_config(robot: Denso) -> bool:
    tool_cfg = getattr(config, "TOOL_CONFIG", {})
    if not isinstance(tool_cfg, dict):
        logging.error("TOOL_CONFIG inválido: esperado dict.")
        return False

    if not tool_cfg.get("enabled", False):
        logging.info("TOOL_CONFIG desabilitado; seguindo sem trocar tool.")
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
        logging.error("Falha ao criar referência de tool '%s'.", tag)
        return False

    if not robot.set_current_tool_by_tag(tag):
        logging.error("Falha ao selecionar tool '%s'.", tag)
        return False

    logging.info("Tool '%s' configurada e ativada com sucesso.", tag)
    return True


def _build_operational_stack(robot: Denso):
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
# FASE 1 — CONEXÃO E POSICIONAMENTO INICIAL
# =============================================================================

def _connect_and_home(robot: Denso) -> bool:
    """
    Conecta o robô, liga o motor e move para a ROI.
    Retorna False em caso de falha.
    """
    logging.info("Conectando robô para teste isolado de centralização...")

    if not robot.connect():
        logging.error("Falha ao conectar com o robô.")
        return False

    if not robot.motor_on():
        logging.error("Falha ao ligar o motor do robô.")
        robot.disconnect()
        return False

    robot.set_arm_speed(10, 5, 5)

    try:
        if hasattr(robot, "move_to_roi"):
            bool(robot.move_to_roi())
        else:
            robot.move_to_roi()
    except Exception as exc:
        logging.warning("Falha ao mover para ROI/safe pose: %s", exc)

    logging.info("Teste manual de movimento cartesiano...")

    pose0 = robot.get_cartesian_pose()
    if pose0 is None:
        logging.error("Não foi possível ler pose inicial do robô.")
        robot.disconnect()
        return False

    logging.info(
        "Pose inicial: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
        float(pose0.x), float(pose0.y), float(pose0.z),
        float(pose0.rx), float(pose0.ry), float(pose0.rz),
    )

    time.sleep(0.5)

    # TODO TEM QUE MORRER ESSE TRECHO
    pose1 = robot.get_cartesian_pose()
    if pose1 is not None:
        logging.info(
            "Pose após teste manual: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
            float(pose1.x), float(pose1.y), float(pose1.z),
            float(pose1.rx), float(pose1.ry), float(pose1.rz),
        )

    return True


# =============================================================================
# FASE 2 — VISÃO GLOBAL (ROBÔ NO ROI)
# =============================================================================

def _detect_markers_from_roi(robot: Denso, camera: RobotCamera, detector: MarkerDetector):
    """
    Move para a ROI, captura frame e detecta os 4 marcadores ArUco.

    Retorna:
        (frame, ids, corners, marker_infos, safe_zone_data)  — em caso de sucesso
        None                                                  — em caso de falha
    """
    logging.info(
        "Capturando imagem a partir da ROI para calcular área de swipe...")

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
                f"Tentativa {tentativa + 1}: Frame nulo retornado pela câmera.")
            time.sleep(0.5)
            continue

        height_px, width_px = frame.shape[:2]
        ids, corners = detector.detect_markers(frame, log_missing=False)

        if ids is not None and len(ids) >= 4:
            logging.info(
                f"Sucesso! Os 4 marcadores foram detectados na tentativa {tentativa + 1}.")
            detected_successfully = True
            break
        else:
            qtd_encontrada = len(ids) if ids is not None else 0
            logging.warning(
                f"Tentativa {tentativa + 1}/{max_tentativas}: Encontrados apenas {qtd_encontrada} marcadores. "
                "Aguardando a tela do app abrir..."
            )
            time.sleep(0.5)

    if not detected_successfully:
        logging.error(
            "Erro Fatal: Não foi possível detectar os 4 marcadores na ROI após 10 tentativas.")
        return None

    marker_infos = [
        detector.get_marker_info(int(marker_id[0]), corners[idx])
        for idx, marker_id in enumerate(ids)
    ]

    safe_zone_data = detector.get_safe_interaction_zone(frame, marker_infos)
    if safe_zone_data is None:
        logging.error("Erro ao calcular a zona segura de swipe.")
        return None

    return frame, ids, corners, marker_infos, safe_zone_data


# =============================================================================
# FASE 3 — CALIBRAÇÃO DO PLANO Z (TOQUE NOS 4 ARUCOS)
# =============================================================================

def _move_to_return_touched_place(robot: Denso, pose) -> bool:
    """
    Move o robô de volta para a posição de toque registrada, com offset de segurança no Z.
    MÁGICA: Cria uma cópia da pose isolada na memória para não corromper a pose salva na lista de homografia.
    """
    if pose is None:
        logging.error(
            "Pose de toque é None. Não é possível mover para posição de toque.")
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
        "Movendo para posição de recuo (com offset): x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
        safe_pose.x, safe_pose.y, safe_pose.z,
        safe_pose.rx, safe_pose.ry, safe_pose.rz,
    )

    success = robot.move_cartesian(safe_pose)
    if not success:
        logging.error("Falha ao mover para posição de recuo.")
    return success


def _calibrate_z_touches(
    robot: Denso,
    camera: RobotCamera,
    detector: MarkerDetector,
    device: Mobile,
    session_recorder: TouchSessionRecorder,
) -> list | None:
    """
    Alinha o robô a cada um dos 4 ArUcos e registra a pose de toque.

    Usa o session_recorder (TouchSessionRecorder) para monitorar os eventos de toque
    do dispositivo — exatamente como no fluxo original.

    Retorna:
        interpolation_position (list[Pose])  — lista com as 4 poses de toque
        None                              — se não conseguiu tocar todos os 4 marcadores
    """
    logging.info(
        "Iniciando rotina de toque nos ArUcos para mapear o Plano 3D (Z)...")

    interpolation_position = []
    rotation_aligment = RotationAlignment(robot, camera, detector)

    ALIGNMENT_TOLERANCE = config.ALIGMENT_TOLERANCE_MM
    Z_TOUCH = config.Z_TOUCH
    Z_LIMIT = config.Z_LIMIT
    TOUCH_FINGER_OFFSET_X = config.TOUCH_FINGER_OFFSET_X

    max_interations = 400

    try:
        for id in range(1, 5):
            logging.info(f"####### Alinhando para o ArUco ID {id}... #######")
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

                # Se AMBOS os eixos estão alinhados, paramos. Está no centro exato!
                if abs(error_mm_x) < ALIGNMENT_TOLERANCE and abs(error_mm_y) < ALIGNMENT_TOLERANCE:
                    logging.info(
                        f"ArUco {id} perfeitamente alinhado. Parando.")
                    break

                # Se QUALQUER UM dos eixos (X ou Y) estiver fora, ajusta.
                if abs(error_mm_x) >= ALIGNMENT_TOLERANCE or abs(error_mm_y) >= ALIGNMENT_TOLERANCE:
                    # "first attempt" = primeira vez que recebemos um diff válido, não simplesmente iteração 1.
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
                    "Pose final após alinhamento: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
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
                # TODO essa parte 1 está dando duplo mergulho - fix the config.Z_OFFSET_BEFORE_TOUCH
                current_position.z = Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH
                ok = robot.move_cartesian(current_position)
                logging.info(
                    "Move para pré-toque (offset + z inicial): %s", ok)
                if not ok:
                    logging.error("Falha ao mover para posição de pré-toque.")
                    return None

                step = 1

                while True:
                    current_position = robot.get_cartesian_pose()
                    if current_position is None:
                        logging.error(
                            "Falha ao obter pose atual do robô durante descida para toque.")
                        robot.move_to_roi()
                        break

                    # 1) Disparo da Thread Global — prioridade máxima
                    if touch_detected_event.is_set():
                        logging.info(
                            "Toque detectado pelo celular em %s. Parando descida do robô.",
                            touch_feedback_holder["value"]
                        )
                        current_position = robot.get_cartesian_pose()
                        interpolation_position.append(current_position)
                        logging.info(
                            "Pose registrada para interpolação: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(
                                current_position.y), float(current_position.z),
                            float(current_position.rx), float(
                                current_position.ry), float(current_position.rz),
                        )
                        _move_to_return_touched_place(robot, current_position)
                        robot.move_to_roi()
                        break

                    # 2) Se chegou na faixa de toque desejada, para e salva posição
                    if current_position.z <= Z_LIMIT:
                        logging.info(
                            "Faixa de toque atingida com o Z_TOUCH: %.2f mm. Parando o robô.",
                            float(current_position.z)
                        )
                        interpolation_position.append(current_position)
                        logging.info(
                            "Pose registrada para interpolação: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(
                                current_position.y), float(current_position.z),
                            float(current_position.rx), float(
                                current_position.ry), float(current_position.rz),
                        )
                        # TODO essa parte2 está dando duplo mergulho
                        _move_to_return_touched_place(robot, current_position)
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    logging.info(
                        "Descendo para toque: passo %d, pose atual z=%.2f mm",
                        step,
                        float(current_position.z),
                    )

                    # 3) Descida controlada até o Z_TOUCH
                    if current_position.z > Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH:
                        current_position.z -= 5.0
                    elif current_position.z > Z_TOUCH + 5.0:
                        current_position.z -= 0.2
                    else:
                        current_position.z -= 0.1

                    ok = robot.move_cartesian(current_position)
                    logging.info(
                        "Resultado do move_cartesian na descida: %s", ok)

                    if not ok:
                        logging.error(
                            "Falha no move_cartesian durante descida para toque.")
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    step += 1
                    time.sleep(0.2)

    finally:
        logging.info(
            "Alinhamento e toque finalizados. Realizando limpeza segura.")

    if len(interpolation_position) < 4:
        logging.error("O robô falhou em tocar todos os 4 marcadores.")
        return None

    return interpolation_position


# =============================================================================
# FASE 4 — SWIPE NA TELA ÚTIL
# =============================================================================

def _build_swipe_params(interpolation_position: list, marker_infos: list, safe_zone_data: dict) -> dict:
    """
    Calcula e retorna todos os parâmetros necessários para o swipe.

    Pontos de swipe: quinas EXATAS da tela útil (sem tirar médias),
    com offset de margem (OFF_SET_SWIPE) para entrar dentro da borda.
    """
    touch_poses_dict = {}
    for idx, target_id in enumerate([1, 2, 3, 4]):
        touch_poses_dict[target_id] = interpolation_position[idx]

    # Referência de escala: limite dos centros dos ArUcos (não a borda externa)
    c_x_min = min(m.centroid[0] for m in marker_infos)
    c_y_min = min(m.centroid[1] for m in marker_infos)
    c_x_max = max(m.centroid[0] for m in marker_infos)
    c_y_max = max(m.centroid[1] for m in marker_infos)
    centroid_rect_px = (c_x_min, c_y_min, c_x_max, c_y_max)

    # Pontos de swipe: quinas exatas da tela útil com offset de margem
    u_x_min, u_y_min, u_x_max, u_y_max = safe_zone_data["screen_rect"]

    OFF_SET_SWIPE = 7
    u_x_min += OFF_SET_SWIPE
    u_y_max -= OFF_SET_SWIPE
    u_x_max -= OFF_SET_SWIPE
    u_y_min += OFF_SET_SWIPE

    perfect_swipe_points = {
        "pt_1": (u_x_min, u_y_max),  # Quina Inferior Esquerda da Tela Útil
        "pt_4": (u_x_min, u_y_min),  # Quina Superior Esquerda da Tela Útil
        "pt_2": (u_x_max, u_y_min),  # Quina Superior Direita da Tela Útil
        "pt_3": (u_x_max, u_y_max),  # Quina Inferior Direita da Tela Útil
    }

    # Congela a orientação do momento em que o Z foi medido (Anti-Pêndulo)
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
        "marker_infos": marker_infos,  # todo adicionei isso
    }


def _execute_swipe(robot: Denso, swipe_params: dict) -> bool:
    """
    Executa o swipe perimetral na tela útil usando breadcrumbs.
    Retorna True em caso de sucesso.
    """
    logging.info(
        "Calculando X,Y via Bilinear e Z via Bilinear na Tela Útil...")

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

    # TODO ajustar trajeto conforme a orientação do device. precisa deixar dinâmico
    trajeto = ["pt_1", "pt_4", "pt_2", "pt_3", "pt_1"]
    logging.info("Preparando para executar o Swipe na Zona Segura...")

    for i in range(len(trajeto) - 1):
        pt_start_name = trajeto[i]
        pt_end_name = trajeto[i + 1]

        px_start, py_start = perfect_swipe_points[pt_start_name]
        px_end, py_end = perfect_swipe_points[pt_end_name]

        logging.info(
            f"Traçando reta alinhada de {pt_start_name} para {pt_end_name}...")

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

    logging.info("Swipe perimetral finalizado com sucesso!")
    robot.move_to_roi()
    return True


# =============================================================================
# VERIFICAÇÃO FINAL DE DETECÇÃO
# =============================================================================

def _check_calibration_success(
    camera: RobotCamera,
    detector: MarkerDetector,
    max_attempts: int = 10,
    attempt_delay_s: float = 0.5,
) -> bool:
    """
    Verifica se a calibração foi bem-sucedida detectando o marcador de sucesso/falha na ROI.
    Tenta até max_attempts vezes antes de desistir.
    Replica exatamente a lógica de __is_marker_detection_successful_in_roi do original.
    """
    success_marker_id = int(getattr(config, "FINAL_SUCCESS_MARKER_ID", 14))
    failure_marker_id = int(getattr(config, "FINAL_FAILURE_MARKER_ID", 15))

    for attempt in range(1, max_attempts + 1):
        frame_ = camera.capture_frame()
        if frame_ is None:
            logging.warning(
                "ROI final marker check attempt %d/%d: frame nulo.",
                attempt, max_attempts,
            )
            time.sleep(attempt_delay_s)
            continue

        marker_ids, _ = detector.detect_markers(frame_, log_missing=False)
        if marker_ids is None or len(marker_ids) == 0:
            logging.warning(
                "ROI final marker check attempt %d/%d: nenhum marcador detectado.",
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
            logging.info("Marcador de sucesso detectado na ROI final.")
            print(f'detected_ids [true]={detected_ids}')
            return True

        if failure_marker_id in detected_ids:
            logging.error("Marcador de falha detectado na ROI final.")
            print(f'detected_ids [false]={detected_ids}')
            return False

        time.sleep(attempt_delay_s)

    logging.error(
        "ROI final marker check esgotou %d tentativas sem detectar o marcador de sucesso (%d).",
        max_attempts, success_marker_id,
    )
    return False


def _is_marker_detection_successful_in_roi(
    camera: RobotCamera,
    detector: MarkerDetector,
) -> bool:
    """Compatibility wrapper used by the FSM callback layer."""
    return _check_calibration_success(camera, detector)


# =============================================================================
# FASE 5 — SALVAR MAPA DE CALIBRAÇÃO
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
    """
    Para o gravador, gera e salva o mapa de calibração via CalibrationMapExporter.
    Replica exatamente a Fase 5 do original, incluindo:
      - session_recorder.stop()
      - device_touch_interaction = session_recorder.get_interaction_data()
      - execution_duration_s
      - calibration_succeed
      - dir_separation
    """
    # Para o gravador para não adicionar mais pontos
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
        device_touch_interaction=session_recorder.get_interaction_data(),
        execution_duration_s=(time.time() - run_start_ts),
        calibration_succeed=is_calibration_succeed,
        dir_separation=True,
    )
    if not export_ok:
        logging.error("Falha ao exportar o mapa de calibração.")


# =============================================================================
# FASE 6 — CLEANUP
# =============================================================================

def _cleanup(device: Mobile, camera: RobotCamera, robot: Denso, session_recorder=None) -> int:
    """Para o device, libera a câmera e desconecta o robô. Sempre retorna 0."""
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
# MAIN — orquestra as fases na mesma ordem do fluxo original
# =============================================================================

def main() -> int:
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

    # --- Instancia model e robot ---
    model = RtaModel(num_markers=args.num_markers)
    robot = Denso(
        workspace_name=args.workspace,
        control_name=args.control,
        options=args.options,
    )

    # --- Desliga debugger de toque ---
    def __turn_on_or_turn_off_debugger_touch(enable: bool):
        toggle_android_setting(setting_name="show_touches", enable=enable)
        toggle_android_setting(setting_name="pointer_location", enable=enable)

    __turn_on_or_turn_off_debugger_touch(enable=False)

    # --- Injeta motor_on com tool no model ---
    def _turn_motor_on_action_with_tool(self):
        """Liga motor e configura tool automaticamente ao entrar em operação."""
        self.motor_on_attempt += 1
        if not self.robot_connected_flag or self.denso_robot is None:
            self.motor_on_flag = False
            return
        try:
            self.motor_on_flag = bool(self.denso_robot.motor_on())
            if self.motor_on_flag:
                if _configure_tool_from_config(robot):
                    robot.set_arm_speed(10, 5, 5)
                    self.motor_on_attempt = 0
                else:
                    self.motor_on_flag = False
                    self.motor_on_attempt = 0
        except Exception:
            self.motor_on_flag = False

    model.turn_motor_on_action = MethodType(
        _turn_motor_on_action_with_tool, model)

    # --- Monta stack operacional ---
    device, camera, detector, auto_align, controller, transform = _build_operational_stack(
        robot)

    # --- Inicializa o gravador global modular ---
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
        try:
            return bool(robot.move_to_roi())
        except Exception as exc:
            logging.error("Falha ao mover para ROI: %s", exc)
            return False

    def camera_on_fn() -> bool:
        try:
            frame = camera.capture_frame()
            return frame is not None
        except Exception as exc:
            logging.error("Falha ao validar camera: %s", exc)
            return False

    def detect_markers_fn() -> bool:
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
        try:
            runtime["swipe_params"] = _build_swipe_params(
                interpolation_position=runtime["interpolation_position"],
                marker_infos=runtime["marker_infos"],
                safe_zone_data=runtime["safe_zone_data"],
            )
            return True
        except Exception as exc:
            logging.error("Falha ao gerar parametros de mapa/swipe: %s", exc)
            return False

    def swipe_borders_fn() -> bool:
        return bool(_execute_swipe(robot, runtime["swipe_params"]))

    def safe_pose_fn() -> bool:
        try:
            robot.move_to_roi()
            time.sleep(3)
            return True
        except Exception as exc:
            logging.error("Falha ao voltar para ROI/safe pose: %s", exc)
            return False

    def read_final_marker_fn() -> str:
        ok = _is_marker_detection_successful_in_roi(camera, detector)
        runtime["is_calibration_succeed"] = bool(ok)

        if ok:
            return model.RESULT_SUCCESS

        return model.RESULT_FAILURE

    def save_map_fn() -> bool:
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
            logging.error("Falha ao salvar mapa de calibracao: %s", exc)
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
    finally:
        _cleanup(device, camera, robot, session_recorder)

    return 0 if machine.state == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
