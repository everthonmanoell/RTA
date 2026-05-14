import argparse
import logging
import os
import time
import threading
from types import MethodType

import random
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


# def annotate_aruco_centroids(frame, detector: MarkerDetector):
#     """Detecta ArUco no frame e desenha o centróide de cada marcador."""
#     if frame is None:
#         return None, [], []

#     ids, corners = detector.detect_markers(frame, log_missing=False)
#     annotated = frame.copy()

#     if ids is None or corners is None:
#         return annotated, [], []

#     refined_corners = detector.refine_corners(frame, corners)
#     marker_infos = []

#     for idx, marker_id in enumerate(ids):
#         marker_info = detector.get_marker_info(int(marker_id[0]), corners[idx])
#         marker_infos.append(marker_info)

#         marker_corners = np.asarray(marker_info.corners, dtype=np.int32).reshape((-1, 1, 2))
#         cv2.polylines(annotated, [marker_corners], isClosed=True, color=(0, 255, 0), thickness=2)

#         centroid_x, centroid_y = map(int, marker_info.centroid)
#         cv2.circle(annotated, (centroid_x, centroid_y), 6, (0, 0, 255), -1)
#         cv2.putText(
#             annotated,
#             f"ID {marker_info.marker_id}",
#             (centroid_x + 8, centroid_y - 8),
#             cv2.FONT_HERSHEY_SIMPLEX,
#             0.6,
#             (0, 0, 255),
#             2,
#             cv2.LINE_AA,
#         )

#     return annotated, ids, marker_infos


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run RTA state machine bootstrap")
    parser.add_argument("--workspace", required=True, help="Denso workspace name")
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
    parser.add_argument("--loop-delay", type=float, default=0.05, help="Delay between FSM steps")
    parser.add_argument("--max-steps", type=int, default=5000, help="Safety max number of FSM steps")
    parser.add_argument("--touch-timeout", type=float, default=3.0, help="Seconds waiting touch feedback")
    parser.add_argument("--metrics-dir", default="test_results", help="Output directory for metrics")
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


# def _build_marker_detector() -> MarkerDetector:
#     configured_dict_name = str(getattr(config, "ARUCO_DICT", "DICT_6X6_250"))
#     dict_name_priority = [
#         configured_dict_name,
#         "DICT_APRILTAG_36h11",
#         "DICT_APRILTAG_16h5",
#         "DICT_APRILTAG_25h9",
#         "DICT_APRILTAG_36h10",
#         "DICT_6X6_250",
#         "DICT_5X5_250",
#         "DICT_4X4_250",
#     ]

#     resolved_dicts = []
#     resolved_names = []
#     seen_names = set()

#     for dict_name in dict_name_priority:
#         if dict_name in seen_names:
#             continue
#         seen_names.add(dict_name)

#         dict_id = getattr(cv2.aruco, dict_name, None)
#         if dict_id is None:
#             continue

#         try:
#             resolved_dicts.append(cv2.aruco.getPredefinedDictionary(dict_id))
#             resolved_names.append(dict_name)
#         except Exception:
#             continue

#     if not resolved_dicts:
#         fallback_name = "DICT_6X6_250"
#         fallback_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_6X6_250)
#         logging.warning(
#             "Nenhum dicionário ArUco válido foi resolvido. Usando fallback: %s",
#             fallback_name,
#         )
#         return MarkerDetector(marker_dict=fallback_dict)

#     logging.info("Detector dictionaries (prioridade): %s", ", ".join(resolved_names))
#     return MarkerDetector(
#         marker_dict=None,
#         fallback_dicts=resolved_dicts[1:],
#     )


def _build_operational_stack(robot: Denso):
    device = Mobile()
    camera = RobotCamera(
        camera_id=config.CAMERA_CONFIG["camera_id"],
        output_dir=config.CAMERA_CONFIG["output_dir"],
        show_preview=False,
    )
    # detector = _build_marker_detector()
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

def _adjust_robot_to_see_the_marker(robot: Denso, current_pose: Pose):
    """Ajusta a posição do robô para tentar ver o marcador, baseado na pose atual."""
    # Estratégia simples: move o robô em um pequeno círculo para tentar trazer o marcador para o campo de visão da câmera
    choose = random.randint(0, 3)
    radius = 10.0  # mm
    angles_deg = [0, 90, 180, 270]  # Tenta em 4 direções: direita, frente, esquerda, trás

    angle_deg = angles_deg[choose]
    angle_rad = np.radians(angle_deg)
    offset_x = radius * np.cos(angle_rad)
    offset_y = radius * np.sin(angle_rad)

    target_pose = Pose(
        x=current_pose.x + offset_x,
        y=current_pose.y + offset_y,
        z=current_pose.z,
        rx=current_pose.rx,
        ry=current_pose.ry,
        rz=current_pose.rz,
        fig=int(getattr(current_pose, "fig", 1))
    )

    logging.info(
        "Tentando ajustar posição para ver marcador: movendo para x=%.2f y=%.2f (offset_x=%.2f offset_y=%.2f)",
        target_pose.x, target_pose.y, offset_x, offset_y
    )

    success = robot.move_cartesian(target_pose)
    if not success:
        logging.warning("Falha ao mover para posição de ajuste. Tentando próximo ângulo.")

    time.sleep(1.0)  # Espera um pouco para a câmera atualizar a visão após o movimento



def main() -> int:
    
    args = parse_args()
    run_start_ts = time.time()

    markers_by_device_type = {
        "flat": 4,
        "foldable": 8,
        "one": 1,
        "two": 2,
        "three": 3,
        "six": 6,
        "seven": 7,
        "eight": 8,
    }
    device_type = str(args.device_type).strip().lower()
    inferred_markers = markers_by_device_type.get(device_type, 4)
    resolved_num_markers = int(args.num_markers) if args.num_markers is not None else inferred_markers
    resolved_num_markers = max(1, resolved_num_markers)
    args.num_markers = resolved_num_markers

    logging.info(
        "Runtime marker target: device_type=%s, num_markers=%d",
        device_type,
        args.num_markers,
    )

    model = RtaModel(num_markers=args.num_markers)
    robot = Denso(
        workspace_name=args.workspace,
        control_name=args.control,
        options=args.options,
    )

    def __turn_on_or_turn_off_debugger_touch(enable: bool):
        toggle_android_setting(setting_name="show_touches", enable=enable)
        toggle_android_setting(setting_name="pointer_location", enable=enable)

    __turn_on_or_turn_off_debugger_touch(enable=False)

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
                    self.motor_on_attempt = 0
                else:
                    self.motor_on_flag = False
                    self.motor_on_attempt = 0
        except Exception:
            self.motor_on_flag = False

    model.turn_motor_on_action = MethodType(_turn_motor_on_action_with_tool, model)

    device, camera, detector, auto_align, controller, transform = _build_operational_stack(robot)

    # =========================================================================
    # INICIALIZA O GRAVADOR GLOBAL MODULAR
    # =========================================================================
    session_recorder = TouchSessionRecorder(device)
    session_recorder.start()

    def __is_marker_detection_successful_in_roi(
        max_attempts: int = 10,
        attempt_delay_s: float = 0.5,
    ) -> bool:
        success_marker_id = int(getattr(config, "FINAL_SUCCESS_MARKER_ID", 14))
        failure_marker_id = int(getattr(config, "FINAL_FAILURE_MARKER_ID", 15))

        for attempt in range(1, max_attempts + 1):
            frame_ = camera.capture_frame()
            if frame_ is None:
                logging.warning(
                    "ROI final marker check attempt %d/%d: frame nulo.",
                    attempt,
                    max_attempts,
                )
                time.sleep(attempt_delay_s)
                continue

            marker_ids, _ = detector.detect_markers(frame_, log_missing=False)
            if marker_ids is None or len(marker_ids) == 0:
                logging.warning(
                    "ROI final marker check attempt %d/%d: nenhum marcador detectado.",
                    attempt,
                    max_attempts,
                )
                time.sleep(attempt_delay_s)
                continue

            detected_ids = {int(curr[0]) for curr in marker_ids}
            logging.info(
                "ROI final marker check attempt %d/%d: detected_ids=%s",
                attempt,
                max_attempts,
                sorted(detected_ids),
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
            max_attempts,
            success_marker_id,
        )
        return False
        


    # ===== TESTE ISOLADO DE CENTRALIZAÇÃO EM 1 ARUCO =====
    logging.info("Conectando robô para teste isolado de centralização...")

    if not robot.connect():
        logging.error("Falha ao conectar com o robô.")
        return 1

    if not robot.motor_on():
        logging.error("Falha ao ligar o motor do robô.")
        robot.disconnect()
        return 1

    # if not _configure_tool_from_config(robot):
    #     logging.error("Falha ao configurar a tool.")
    #     robot.disconnect()
    #     return 1


    robot.set_arm_speed(10, 5, 5)  # Velocidade segura para alinhamento inicial
    
    # Opcional, mas recomendado: ir para ROI antes de procurar marcador
    try:
        if hasattr(robot, "move_to_roi"):
            moved = bool(robot.move_to_roi())
            
        else:
            robot.move_to_roi()
    except Exception as exc:
        logging.warning("Falha ao mover para ROI/safe pose: %s", exc)


    logging.info("Teste manual de movimento cartesiano...")

    pose0 = robot.get_cartesian_pose()
    if pose0 is None:
        logging.error("Não foi possível ler pose inicial do robô.")
        robot.disconnect()
        return 1

    logging.info(
        "Pose inicial: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
        float(pose0.x), float(pose0.y), float(pose0.z),
        float(pose0.rx), float(pose0.ry), float(pose0.rz),
    )

    # test_pose = Pose(
    #     x=float(pose0.x) - 10.0,
    #     y=float(pose0.y),
    #     z=float(pose0.z),
    #     rx=float(pose0.rx),
    #     ry=float(pose0.ry),
    #     rz=float(pose0.rz),
    #     fig=int(getattr(pose0, "fig", 5)),
    # )

    # # ok_move = robot.move_cartesian(test_pose)
    # logging.info("Resultado do move cartesiano manual: %s", ok_move)

    

    time.sleep(0.5)
    #==========================================
    #todo TEM QUE MORRER ESSE TRECHO
    pose1 = robot.get_cartesian_pose()
    if pose1 is not None:
        logging.info(
            "Pose após teste manual: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
            float(pose1.x), float(pose1.y), float(pose1.z),
            float(pose1.rx), float(pose1.ry), float(pose1.rz),
        )
    #===========================================

    def _safe_cleanup():
        try:
            camera.release()
        except Exception:
            pass

        try:
            robot.disconnect()
        except Exception:
            pass
        
        return 0
    
    def _move_to_return_touched_place(pose) -> bool:
        """Move o robô de volta para a posição de toque registrada, com um offset de segurança no Z."""
        if pose is None:
            logging.error("Pose de toque é None. Não é possível mover para posição de toque.")
            return False

        # MÁGICA: Cria uma cópia da pose isolada na memória!
        # Isso garante que a pose salva na lista de homografia continue intacta.
        safe_pose = Pose(
            x=float(pose.x),
            y=float(pose.y),
            z=float(pose.z) + config.Z_OFFSET_BEFORE_TOUCH, # O +20
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


## ======================== COM METÓDOS ENCAPSULADOS =========================================================
    #TODO VERIFY IF IT WORKS


    aruco_widht_real_mm = config.MARKER_REAL_WIDTH_MM
    aruco_hight_real_mm = config.MARKER_REAL_HEIGHT_MM


   # =====================================================================
    # FASE 1: VISÃO GLOBAL (ROBÔ NO ROI)
    # =====================================================================
    logging.info("Capturando imagem a partir da ROI para calcular área de swipe...")
    
    # 1. Garante que o robô está na ROI e pega a pose atual
    robot.move_to_roi()
    current_roi_pose = robot.get_cartesian_pose()
    
    # Variáveis para armazenar o resultado do loop
    detected_successfully = False
    ids, corners, frame = None, None, None
    height_px, width_px = 0, 0

    # 2. Tenta tirar a foto e detectar até 10 vezes
    max_tentativas = 10
    for tentativa in range(max_tentativas):
        # Tira a foto (verifique se o método no seu código é capture() ou capture_frame())
        frame = camera.capture_frame() # ou camera.capture_frame_frame()
        
        if frame is None:
            logging.warning(f"Tentativa {tentativa + 1}: Frame nulo retornado pela câmera.")
            time.sleep(0.5)
            continue

        height_px, width_px = frame.shape[:2]

        # 3. Detecta os marcadores
        ids, corners = detector.detect_markers(frame, log_missing=False) # log_missing=False evita floodar o terminal
        
        if ids is not None and len(ids) >= 4:
            logging.info(f"Sucesso! Os 4 marcadores foram detectados na tentativa {tentativa + 1}.")
            detected_successfully = True
            break  # Sai do loop imediatamente, pois já temos a foto boa!
        else:
            qtd_encontrada = len(ids) if ids is not None else 0
            logging.warning(f"Tentativa {tentativa + 1}/{max_tentativas}: Encontrados apenas {qtd_encontrada} marcadores. Aguardando a tela do app abrir...")
            time.sleep(0.5) # Espera meio segundo antes da próxima foto (dá tempo do app abrir e focar)

    # Verifica se o loop terminou sem sucesso
    if not detected_successfully:
        logging.error("Erro Fatal: Não foi possível detectar os 4 marcadores na ROI após 10 tentativas.")
        # Opcional: Salvar a última foto que a câmera viu para debugar por que falhou
        # cv2.imwrite("debug_falha_roi.jpg", frame) 
        return False
        
    # 4. Extrai as informações dos marcadores 
    marker_infos = [
        detector.get_marker_info(int(marker_id[0]), corners[idx])
        for idx, marker_id in enumerate(ids)
    ]

    # 5. Pega as coordenadas da Zona Segura em PIXELS
    safe_zone_data = detector.get_safe_interaction_zone(frame, marker_infos)
    if safe_zone_data is None:
        logging.error("Erro ao calcular a zona segura de swipe.")
        return False
    
    

    # =====================================================================
    # FASE 3: CALIBRAÇÃO DO PLANO Z (TOQUE NOS ARUCOS)
    # =====================================================================
    logging.info("Iniciando rotina de toque nos ArUcos para mapear o Plano 3D (Z)...")
    
    homography_position = [] # Lista que guardará as 4 Poses de toque
    
    
    rotation_aligment = RotationAlignment(robot, camera, detector)

    ALIGNMENT_TOLERANCE = config.ALIGMENT_TOLERANCE_MM
    # ID_TARGET = 1

    Z_TOUCH = config.Z_TOUCH
    Z_LIMIT = config.Z_LIMIT
    TOUCH_FINGER_OFFSET_X = config.TOUCH_FINGER_OFFSET_X

    max_interations = 400
    interation = 0

    touch_detected_event = threading.Event()
    touch_feedback_holder = {"value": None}

    try:
        for id in range(1, 5):
            logging.info(f"####### Alinhando para o ArUco ID {id}... #######")
            interation = 0
            first_valid_diff = False
            while interation < max_interations:
                interation += 1

                diff_error = rotation_aligment.error_diff_between_single_marker_and_image_center_on_mm(id)
                if diff_error is None:
                    time.sleep(0.3)
                    continue

                error_mm_x, error_mm_y = diff_error

                # Se AMBOS os eixos estão alinhados, paramos. Está no centro exato!
                if abs(error_mm_x) < ALIGNMENT_TOLERANCE and abs(error_mm_y) < ALIGNMENT_TOLERANCE:
                    logging.info(f"ArUco {id} perfeitamente alinhado. Parando.")
                    break

                # A MÁGICA DA CORREÇÃO:
                # Se QUALQUER UM dos eixos (X ou Y) estiver fora, ele é obrigado a ajustar!
                if abs(error_mm_x) >= ALIGNMENT_TOLERANCE or abs(error_mm_y) >= ALIGNMENT_TOLERANCE:
                    # Treat "first attempt" as the first time we get a valid diff (not simply iteration==1).
                    is_first_attempt = not first_valid_diff

                    rotation_aligment.adjust_robot_to_marker_center(
                        (error_mm_x, error_mm_y),
                        is_first_attempt,
                    )

                    # Mark that we've seen a valid diff for this marker so subsequent corrections are not first-attempt.
                    first_valid_diff = True

                time.sleep(0.3)

            current_position = robot.get_cartesian_pose()
            print(f'type of current_position: {type(current_position)}')


            if current_position is not None:
                logging.info(
                    "Pose final após alinhamento: x=%.2f y=%.2f z=%.2f rx=%.2f ry=%.2f rz=%.2f",
                    float(current_position.x), float(current_position.y), float(current_position.z),
                    float(current_position.rx), float(current_position.ry), float(current_position.rz),
                )



                # Armamos o "gatilho" da thread global modular
                touch_detected_event = threading.Event()
                touch_feedback_holder = {"value": None}
                session_recorder.arm_trigger("down", touch_feedback_holder, touch_detected_event)
                
                current_position.x += TOUCH_FINGER_OFFSET_X
                #TODO essa parte 1 está dando duplo mergulho - fix the config.Z_OFFSET_BEFORE_TOUCH 
                current_position.z = Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH # Posiciona o robô para o Z de pré-toque, que é um pouco acima do Z de toque real
                ok = robot.move_cartesian(current_position)
                logging.info("Move para pré-toque (offset + z inicial): %s", ok)
                if not ok:
                    logging.error("Falha ao mover para posição de pré-toque.")
                    return _safe_cleanup()
                        






                step = 1
                
                

                # def touch_listener():
                #     try:
                #         touch = device.wait_for_touch_feedback(timeout=999999)
                #         if touch is not None:
                #             touch_feedback_holder["value"] = touch
                #             touch_detected_event.set()
                #     except Exception as exc:
                #         logging.error("Erro no listener de toque: %s", exc)

                # touch_thread = threading.Thread(target=touch_listener, daemon=True)
                # touch_thread.start()

                while True:
                    current_position = robot.get_cartesian_pose()
                    if current_position is None:
                        logging.error("Falha ao obter pose atual do robô durante descida para toque.")
                        robot.move_to_roi()
                        break

                    # 1) Disparo da Thread Global
                    if touch_detected_event.is_set():
                        logging.info(
                            "Toque detectado pelo celular em %s. Parando descida do robô.",
                            touch_feedback_holder["value"]
                        )
                        current_position = robot.get_cartesian_pose() # Leitura extra para garantir que temos a pose mais recente no momento do toque
                        homography_position.append(current_position)
                        logging.info(
                            "Pose registrada para homografia: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(current_position.y), float(current_position.z),
                            float(current_position.rx), float(current_position.ry), float(current_position.rz),
                        )
                        _move_to_return_touched_place(current_position)
                        robot.move_to_roi()
                        break

                    # 2) se chegou na faixa de toque desejada, para e salva posição
                    if current_position.z <= Z_LIMIT:
                        logging.info(
                            "Faixa de toque atingida com o Z_TOUCH: %.2f mm. Parando o robô.",
                            float(current_position.z)
                        )
                        homography_position.append(current_position)
                        logging.info(
                            "Pose registrada para homografia: x=%.2f, y=%.2f, z=%.2f, rx=%.2f, ry=%.2f, rz=%.2f",
                            float(current_position.x), float(current_position.y), float(current_position.z),
                            float(current_position.rx), float(current_position.ry), float(current_position.rz),
                        )
                        _move_to_return_touched_place(current_position) #TODO essa parte2 está dando duplo mergulho
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    # 3) última camada de segurança
                    # if current_position.z <= Z_LIMIT:
                    #     logging.warning(
                    #         "Limite de segurança Z atingido (%.2f mm). Parando descida.",
                    #         float(current_position.z)
                    #     )
                    #     _move_to_return_touched_place(current_position)
                    #     robot.move_to_roi()
                    #     break

                    logging.info(
                        "Descendo para toque: passo %d, pose atual z=%.2f mm",
                        step,
                        float(current_position.z),
                    )

                    # 4) descida controlada até o Z_TOUCH
                    if current_position.z > Z_TOUCH + config.Z_OFFSET_BEFORE_TOUCH:
                        current_position.z -= 5.0
                    elif current_position.z > Z_TOUCH + 5.0:
                        current_position.z -= 0.2
                    else:
                        current_position.z -= 0.1

                    ok = robot.move_cartesian(current_position)
                    logging.info("Resultado do move_cartesian na descida: %s", ok)

                    if not ok:
                        logging.error("Falha no move_cartesian durante descida para toque.")
                        robot.move_to_roi()
                        session_recorder.disarm_trigger()
                        break

                    step += 1
                    time.sleep(0.2)
                

    finally:
        logging.info("Alinhamento e toque finalizados. Realizando limpeza segura.")
        # device.stop()
        # _safe_cleanup()
        
    # .....................................................
    
    if len(homography_position) < 4:
            logging.error("O robô falhou em tocar todos os 4 marcadores.")
            return False

# =====================================================================
    # FASE 4: SWIPE DIRETO NAS QUINAS DA TELA ÚTIL
    # =====================================================================
    logging.info("Calculando X,Y via Bilinear e Z via Bilinear na Tela Útil...")
    
    # 1. Dicionário das poses físicas de toque
    touch_poses_dict = {}
    for idx, target_id in enumerate([1, 2, 3, 4]):
        touch_poses_dict[target_id] = homography_position[idx]

    # 2. O GRANDE SEGREDO DA ESCALA (A CORREÇÃO):
    # A nossa referência do tamanho da tela continua sendo o limite dos centros
    c_x_min = min(m.centroid[0] for m in marker_infos)
    c_y_min = min(m.centroid[1] for m in marker_infos)
    c_x_max = max(m.centroid[0] for m in marker_infos)
    c_y_max = max(m.centroid[1] for m in marker_infos)
    centroid_rect_px = (c_x_min, c_y_min, c_x_max, c_y_max)

    # =========================================================================
    # PONTOS DE SWIPE: QUINAS EXATAS DA TELA ÚTIL
    # Usando os limites reais do display, sem tirar médias.
    # =========================================================================
    u_x_min, u_y_min, u_x_max, u_y_max = safe_zone_data["screen_rect"]

    OFF_SET_SWIPE = 7

    u_x_min += OFF_SET_SWIPE
    u_y_max -= OFF_SET_SWIPE
    u_x_max -= OFF_SET_SWIPE
    u_y_min += OFF_SET_SWIPE

    

    perfect_swipe_points = {
        "pt_1": (u_x_min, u_y_max), # Quina Inferior Esquerda da Tela Útil
        "pt_4": (u_x_min, u_y_min), # Quina Superior Esquerda da Tela Útil
        "pt_2": (u_x_max, u_y_min), # Quina Superior Direita da Tela Útil
        "pt_3": (u_x_max, u_y_max)  # Quina Inferior Direita da Tela Útil
    }

    # 3. Congela a orientação exata do momento em que o Z foi medido! (Anti-Pêndulo)
    pose_referencia = touch_poses_dict[1]
    safe_rx = float(pose_referencia.rx)
    safe_ry = float(pose_referencia.ry)
    safe_rz = float(pose_referencia.rz)
    safe_fig = int(getattr(pose_referencia, "fig", 1))

    #todo ajustar trajeto conforme a orientação do device. precisa deixar dinâmico
    # 4. Trajeto perimetral 
    trajeto = ["pt_1", "pt_4", "pt_2", "pt_3", "pt_1"]
    # trajeto = ["pt_4", "pt_2", "pt_3", "pt_1", "pt_4"] # Começa do superior esquerdo para dar um "puxão" inicial para o lado esquerdo da tela
    logging.info("Preparando para executar o Swipe na Zona Segura...")


    Z_SWIPE_OFFSET = -3.0  # Ajuste de pressão na tela
    PASSOS_POR_RETA = 15   # Quantidade de pontos intermediários (breadcrumbs)
    OFF_SET_SWIPE = 3

    # Percorre cada par de pontos (Ex: pt_1 -> pt_4)
    for i in range(len(trajeto) - 1):
        pt_start_name = trajeto[i]
        pt_end_name = trajeto[i+1]
        
        px_start, py_start = perfect_swipe_points[pt_start_name]
        px_end, py_end = perfect_swipe_points[pt_end_name]
        
        logging.info(f"Traçando reta alinhada de {pt_start_name} para {pt_end_name}...")
        
        # Cria as "migalhas de pão" para forçar o robô a andar em linha reta
        for step in range(PASSOS_POR_RETA + 1):
            # Calcula a porcentagem do caminho (0.0 até 1.0)
            fraction = step / float(PASSOS_POR_RETA)
            
            # Acha o pixel intermediário exato
            px_current = px_start + (px_end - px_start) * fraction
            py_current = py_start + (py_end - py_start) * fraction
            
            # PASSO ÚNICO: Resolve X, Y e Z para esse micro-ponto
            target_x, target_y, target_z = interpolate_robot_pose(
                target_px=px_current, 
                target_py=py_current, 
                union_rect_px=centroid_rect_px, 
                touch_poses_dict=touch_poses_dict,
                marker_infos=marker_infos
            )
            
            # Aplica o ajuste de pressão fina no Z
            target_z_afinado = target_z + Z_SWIPE_OFFSET
            target_x_afinado = target_x
            target_y_afinado = target_y

            # # se for a primeira etapa do swipe (pt_1 -> pt_4), aplica um pequeno offset no X para garantir que o robô "puxe" a tela para o lado esquerdo antes de descer
            # if i+1 == 1:
            #     target_y_afinado += -OFF_SET_SWIPE
            # elif i+1 == 2:
            #     target_x_afinado += -OFF_SET_SWIPE
            # elif i+1 == 3:
            #     target_y_afinado += OFF_SET_SWIPE
            # elif i+1 == 4:
            #     target_x_afinado += OFF_SET_SWIPE + 1

            # trajeto = ["pt_4", "pt_2", "pt_3", "pt_1", "pt_4"] # Começa do superior esquerdo para dar um "puxão" inicial para o lado esquerdo da tela
            # se for a primeira etapa do swipe (pt_1 -> pt_4), aplica um pequeno offset no X para garantir que o robô "puxe" a tela para o lado esquerdo antes de descer
            # if i+1 == 1:
            #     target_y_afinado += OFF_SET_SWIPE
            # elif i+1 == 2:
            #     target_x_afinado += +OFF_SET_SWIPE
            # elif i+1 == 3:
            #     target_y_afinado += OFF_SET_SWIPE
            # elif i+1 == 4:
            #     target_x_afinado += -OFF_SET_SWIPE + 1
            
            # Constrói a Pose
            swipe_pose = Pose(
                x=target_x_afinado,
                y=target_y_afinado,
                z=target_z_afinado,
                rx=safe_rx,
                ry=safe_ry,
                rz=safe_rz,
                fig=safe_fig
            )
            
            # Move para o micro-ponto (O robô vai seguir isso como se fosse um trilho)
            robot.move_cartesian(swipe_pose)
            
    logging.info("Swipe perimetral finalizado com sucesso!")
    robot.move_to_roi()
    time.sleep(3)  # Pequena pausa para estabilizar antes da última detecção

    # ... (seu código de detecção final)
    is_calibration_succeed = __is_marker_detection_successful_in_roi()
    if is_calibration_succeed:
        logging.info("Teste final de detecção de marcadores após o swipe: SUCESSO!")
    else:
        logging.error("Teste final de detecção de marcadores após o swipe: FALHA!")

# =====================================================================
    # FASE 5: SALVAR MAPA DE CALIBRAÇÃO (CARTESIANO DA ÁREA ÚTIL)
    # =====================================================================
    
    # Para o gravador para não adicionar mais pontos
    session_recorder.stop()

    # 1. Puxa os limites EXATOS da Área Útil (Tela cinza brilhante), ignorando a safe_zone
    useful_rect = detector.get_useful_screen_rectangle(frame, marker_infos)
    
    export_ok = CalibrationMapExporter.export(
        output_dir=args.metrics_dir,
        device_type=device_type,
        device_model=str(getattr(config, "DEVICE_MODEL", "unknown")).strip() or "unknown",
        useful_rect_px=useful_rect,
        centroid_rect_px=centroid_rect_px,
        marker_infos=marker_infos,
        touch_poses_dict=touch_poses_dict,
        safe_pose=pose_referencia,
        device_touch_interaction=session_recorder.get_interaction_data(),
        execution_duration_s=(time.time() - run_start_ts),
        calibration_succeed=is_calibration_succeed,
        dir_separation= True
    )
    if not export_ok:
        logging.error("Falha ao exportar o mapa de calibração.")

    # =====================================================================
    # FIM DA ROTINA
    # =====================================================================
    device.stop()
    _safe_cleanup()








### =========================================================================

    # auto_align.set_target_marker_id(1)

    # ok = auto_align.run_centering_loop(max_iterations=50)
    # logging.info("Resultado do alinhamento de 1 marcador: %s", ok)
    
    # return 0 if ok else 1
    # =====================================================

    # auto_cfg = getattr(config, "AUTO_ALIGNMENT_CONFIG", {})
    # if isinstance(auto_cfg, dict):
    #     auto_align.CENTRALIZE_TOLERANCE = float(auto_cfg.get("centralize_tolerance", auto_align.CENTRALIZE_TOLERANCE))
    #     auto_align.DEPTH_TOLERANCE = float(auto_cfg.get("depth_tolerance", auto_align.DEPTH_TOLERANCE))
    #     auto_align.XY_GAIN = float(auto_cfg.get("xy_gain", auto_align.XY_GAIN))
    #     auto_align.Z_GAIN = float(auto_cfg.get("z_gain", auto_align.Z_GAIN))
    #     auto_align.MAX_ITERATIONS = int(auto_cfg.get("max_iterations", auto_align.MAX_ITERATIONS))
    #     auto_align.ITERATION_DELAY = float(auto_cfg.get("iteration_delay", auto_align.ITERATION_DELAY))
    #     auto_align.MAX_XY_STEP_MM = float(auto_cfg.get("max_xy_step_mm", auto_align.MAX_XY_STEP_MM))
    #     auto_align.MAX_Z_STEP_MM = float(auto_cfg.get("max_z_step_mm", auto_align.MAX_Z_STEP_MM))
    #     auto_align.MAX_XY_DRIFT_MM = float(auto_cfg.get("max_xy_drift_mm", auto_align.MAX_XY_DRIFT_MM))
    #     auto_align.MAX_NO_IMPROVEMENT_ITERS = int(
    #         auto_cfg.get("max_no_improvement_iters", auto_align.MAX_NO_IMPROVEMENT_ITERS)
    #     )
    #     auto_align.MIN_IMPROVEMENT_MM = float(
    #         auto_cfg.get("min_improvement_mm", auto_align.MIN_IMPROVEMENT_MM)
    #     )
    #     logging.info(
    #         "AutoAlignment config: xy_gain=%.3f z_gain=%.3f max_xy_step=%.1f max_z_step=%.1f max_drift=%.1f",
    #         auto_align.XY_GAIN,
    #         auto_align.Z_GAIN,
    #         auto_align.MAX_XY_STEP_MM,
    #         auto_align.MAX_Z_STEP_MM,
    #         auto_align.MAX_XY_DRIFT_MM,
    #     )

    # motion_cfg = getattr(config, "ROBOT_MOTION_CONFIG", {})
    # if not isinstance(motion_cfg, dict):
    #     motion_cfg = {}

    # speed_profiles = {
    #     "general": {
    #         "speed": float(motion_cfg.get("general_speed", 12.0)),
    #         "accel": float(motion_cfg.get("general_accel", motion_cfg.get("general_speed", 12.0))),
    #         "decel": float(motion_cfg.get("general_decel", motion_cfg.get("general_speed", 12.0))),
    #     },
    #     "touch": {
    #         "speed": float(motion_cfg.get("touch_speed", 8.0)),
    #         "accel": float(motion_cfg.get("touch_accel", motion_cfg.get("touch_speed", 8.0))),
    #         "decel": float(motion_cfg.get("touch_decel", motion_cfg.get("touch_speed", 8.0))),
    #     },
    #     "swipe": {
    #         "speed": float(motion_cfg.get("swipe_speed", 6.0)),
    #         "accel": float(motion_cfg.get("swipe_accel", motion_cfg.get("swipe_speed", 6.0))),
    #         "decel": float(motion_cfg.get("swipe_decel", motion_cfg.get("swipe_speed", 6.0))),
    #     },
    # }

    # def _apply_speed_profile(profile_name: str) -> None:
    #     profile = speed_profiles.get(profile_name, speed_profiles["general"])
    #     try:
    #         robot.set_arm_speed(
    #             float(profile["speed"]),
    #             float(profile["accel"]),
    #             float(profile["decel"]),
    #         )
    #     except Exception as speed_err:
    #         logging.debug("Nao foi possivel aplicar profile de velocidade '%s': %s", profile_name, speed_err)

    # logging.info(
    #     "RobotMotion config: general=%.1f touch=%.1f swipe=%.1f",
    #     speed_profiles["general"]["speed"],
    #     speed_profiles["touch"]["speed"],
    #     speed_profiles["swipe"]["speed"],
    # )
    # _apply_speed_profile("general")

    # logging.info(
    #     "Metadata de tela recebida: screen_width_px=%.1f screen_height_px=%.1f margin_px=%.1f tag_size_px=%.1f",
    #     float(getattr(config, "SCREEN_WIDTH_PX", 0.0)),
    #     float(getattr(config, "SCREEN_HEIGHT_PX", 0.0)),
    #     float(getattr(config, "MARKER_MARGIN_PX", 0.0)),
    #     float(getattr(config, "MARKER_TAG_SIZE_PX", 0.0)),
    # )
    # if float(getattr(config, "SCREEN_WIDTH_PX", 0.0)) <= 0 or float(
    #     getattr(config, "SCREEN_HEIGHT_PX", 0.0)
    # ) <= 0:
    #     logging.warning(
    #         "screen_width_px/screen_height_px inválidos (<=0). "
    #         "A borda azul não representa a tela real; usando fallback proporcional da imagem."
    #     )

    # metrics_logger = MetricsLogger(output_dir=args.metrics_dir)
    # test_metrics = metrics_logger.create_test_session()
    # test_metrics.device_model = str(getattr(config, "DEVICE_MODEL", "unknown")).strip() or "unknown"

    # runtime = {
    #     "markers": [],
    #     "z_touch": None,
    #     "fiducial_touches": [],
    #     "last_touch_success": False,
    #     "screen_quad": None,
    #     "screen_estimate_mode": "raw",
    #     "aligned_screen_quad": None,
    #     "aligned_screen_estimate_mode": "raw",
    #     "generated_map": None,
    #     "saved_map_file": None,
    #     "partial_recovery_moves": 0,
    #     "detect_no_marker_streak": 0,
    #     "detect_low_marker_streak": 0,
    #     "lost_markers_in_align": False,
    #     "last_reacquire_ts": 0.0,
    #     "last_fov_backoff_ts": 0.0,
    #     "last_state": "idle",
    #     "state_enter_time": time.time(),
    # }

    # marker_debug_dir = None
    # if args.save_detect_debug:
    #     marker_debug_dir = Path(config.CAMERA_CONFIG["output_dir"]) / "marker_debug"
    #     marker_debug_dir.mkdir(parents=True, exist_ok=True)
    #     logging.info("DetectMarkers debug image saving enabled: %s", marker_debug_dir)
    # else:
    #     logging.info("DetectMarkers debug image saving disabled by CLI flag.")

    # def _estimate_screen_rect_from_markers(marker_infos: list):
    #     all_points = np.vstack([np.asarray(marker.corners, dtype=np.float32) for marker in marker_infos])
    #     marker_rect = cv2.minAreaRect(all_points)
    #     marker_centers = np.array([marker.centroid for marker in marker_infos], dtype=np.float32)
    #     center_rect = cv2.minAreaRect(marker_centers)

    #     (center_x, center_y), (marker_w, marker_h), angle = marker_rect
    #     (_, _), (center_w, center_h), _ = center_rect

    #     if marker_w <= 0 or marker_h <= 0:
    #         return marker_rect, marker_rect, "raw", None

    #     screen_width_px = float(getattr(config, "SCREEN_WIDTH_PX", 0.0))
    #     screen_height_px = float(getattr(config, "SCREEN_HEIGHT_PX", 0.0))
    #     margin_px = float(getattr(config, "MARKER_MARGIN_PX", 0.0))
    #     tag_size_px = float(getattr(config, "MARKER_TAG_SIZE_PX", 0.0))

    #     if (
    #         screen_width_px > 0
    #         and screen_height_px > 0
    #         and margin_px >= 0
    #         and tag_size_px > 0
    #         and max(screen_width_px, screen_height_px) > (2.0 * margin_px)
    #         and min(screen_width_px, screen_height_px) > (2.0 * margin_px)
    #         and center_w > 0
    #         and center_h > 0
    #     ):
    #         if len(marker_infos) >= 4:
    #             device_x_left = margin_px + (0.5 * tag_size_px)
    #             device_x_right = screen_width_px - margin_px - (0.5 * tag_size_px)
    #             device_y_top = margin_px + (0.5 * tag_size_px)
    #             device_y_bottom = screen_height_px - margin_px - (0.5 * tag_size_px)

    #             # Flat layout in app:
    #             # ID 1 -> top-left, ID 2 -> bottom-right, ID 3 -> bottom-left, ID 4 -> top-right.
    #             id_to_device_center = {
    #                 1: (device_x_left, device_y_top),
    #                 2: (device_x_right, device_y_bottom),
    #                 3: (device_x_left, device_y_bottom),
    #                 4: (device_x_right, device_y_top),
    #             }

    #             id_map_points = [
    #                 (id_to_device_center[curr.marker_id], curr.centroid)
    #                 for curr in marker_infos
    #                 if curr.marker_id in id_to_device_center
    #             ]

    #             if len(id_map_points) >= 4:
    #                 dev_centers = np.array([curr[0] for curr in id_map_points], dtype=np.float32)
    #                 img_centers = np.array([curr[1] for curr in id_map_points], dtype=np.float32)
    #             else:
    #                 sums = marker_centers[:, 0] + marker_centers[:, 1]
    #                 diffs = marker_centers[:, 1] - marker_centers[:, 0]

    #                 idx_tl = int(np.argmin(sums))
    #                 idx_br = int(np.argmax(sums))
    #                 idx_tr = int(np.argmin(diffs))
    #                 idx_bl = int(np.argmax(diffs))

    #                 if len({idx_tl, idx_tr, idx_bl, idx_br}) != 4:
    #                     dev_centers = None
    #                     img_centers = None
    #                 else:
    #                     img_centers = np.array(
    #                         [
    #                             marker_centers[idx_tl],
    #                             marker_centers[idx_tr],
    #                             marker_centers[idx_bl],
    #                             marker_centers[idx_br],
    #                         ],
    #                         dtype=np.float32,
    #                     )
    #                     dev_centers = np.array(
    #                         [
    #                             [device_x_left, device_y_top],
    #                             [device_x_right, device_y_top],
    #                             [device_x_left, device_y_bottom],
    #                             [device_x_right, device_y_bottom],
    #                         ],
    #                         dtype=np.float32,
    #                     )

    #             if dev_centers is not None and img_centers is not None:
    #                 homography, _ = cv2.findHomography(dev_centers, img_centers, method=0)
    #                 if homography is not None:
    #                     dev_corners = np.array(
    #                         [
    #                             [0.0, 0.0],
    #                             [screen_width_px, 0.0],
    #                             [0.0, screen_height_px],
    #                             [screen_width_px, screen_height_px],
    #                         ],
    #                         dtype=np.float32,
    #                     ).reshape((-1, 1, 2))
    #                     img_corners = cv2.perspectiveTransform(dev_corners, homography).reshape((-1, 2))

    #                     tl = img_corners[0]
    #                     tr = img_corners[1]
    #                     bl = img_corners[2]
    #                     br = img_corners[3]
    #                     screen_quad = np.array([tl, tr, br, bl], dtype=np.float32)

    #                     width_est = 0.5 * (
    #                         np.linalg.norm(tr - tl) + np.linalg.norm(br - bl)
    #                     )
    #                     height_est = 0.5 * (
    #                         np.linalg.norm(bl - tl) + np.linalg.norm(br - tr)
    #                     )
    #                     estimated_rect = (
    #                         (float(np.mean(screen_quad[:, 0])), float(np.mean(screen_quad[:, 1]))),
    #                         (float(width_est), float(height_est)),
    #                         angle,
    #                     )
    #                     mode = "homography_exact_ids" if len(id_map_points) >= 4 else "homography_exact"
    #                     return marker_rect, estimated_rect, mode, screen_quad

    #         # offset_exact depende de uma geometria completa/estável de centros.
    #         # Com menos de 4 marcadores a estimativa tende a distorcer bastante.
    #         if len(marker_infos) >= 4:
    #             center_long = max(center_w, center_h)
    #             center_short = min(center_w, center_h)
    #             screen_long = max(screen_width_px, screen_height_px)
    #             screen_short = min(screen_width_px, screen_height_px)

    #             edge_offset_device = margin_px + (0.5 * tag_size_px)
    #             center_span_long_device = screen_long - (2.0 * edge_offset_device)
    #             center_span_short_device = screen_short - (2.0 * edge_offset_device)

    #             if center_span_long_device <= 0 or center_span_short_device <= 0:
    #                 return marker_rect, marker_rect, "raw", None

    #             scale_long = screen_long / center_span_long_device
    #             scale_short = screen_short / center_span_short_device

    #             expanded_long = center_long * scale_long
    #             expanded_short = center_short * scale_short

    #             if center_w >= center_h:
    #                 expanded_w = expanded_long
    #                 expanded_h = expanded_short
    #             else:
    #                 expanded_w = expanded_short
    #                 expanded_h = expanded_long

    #             expanded_rect = (
    #                 (center_x, center_y),
    #                 (expanded_w, expanded_h),
    #                 angle,
    #             )
    #             return marker_rect, expanded_rect, "offset_exact", None

    #     if (
    #         screen_width_px > 0
    #         and screen_height_px > 0
    #         and margin_px >= 0
    #         and max(screen_width_px, screen_height_px) > (2.0 * margin_px)
    #         and min(screen_width_px, screen_height_px) > (2.0 * margin_px)
    #     ):
    #         marker_long = max(marker_w, marker_h)
    #         marker_short = min(marker_w, marker_h)
    #         screen_long = max(screen_width_px, screen_height_px)
    #         screen_short = min(screen_width_px, screen_height_px)

    #         marker_span_long_device = screen_long - (2.0 * margin_px)
    #         marker_span_short_device = screen_short - (2.0 * margin_px)

    #         scale_long = screen_long / marker_span_long_device
    #         scale_short = screen_short / marker_span_short_device

    #         expanded_long = marker_long * scale_long
    #         expanded_short = marker_short * scale_short

    #         if marker_w >= marker_h:
    #             expanded_w = expanded_long
    #             expanded_h = expanded_short
    #         else:
    #             expanded_w = expanded_short
    #             expanded_h = expanded_long

    #         expanded_rect = (
    #             (center_x, center_y),
    #             (expanded_w, expanded_h),
    #             angle,
    #         )
    #         return marker_rect, expanded_rect, "offset_corner_span", None

    #     if center_w > 0 and center_h > 0:
    #         observed_tag_size_px = float(
    #             np.median(
    #                 [
    #                     0.5 * (float(marker.width_px) + float(marker.height_px))
    #                     for marker in marker_infos
    #                 ]
    #             )
    #         )
    #         if observed_tag_size_px > 0:
    #             if tag_size_px > 0:
    #                 margin_to_tag_ratio = margin_px / tag_size_px
    #             else:
    #                 # Matches Android defaults: margin_dp=16, tag_size_dp=120.
    #                 margin_to_tag_ratio = 16.0 / 120.0

    #             edge_offset_img_px = observed_tag_size_px * (0.5 + margin_to_tag_ratio)
    #             expanded_w = center_w + (2.0 * edge_offset_img_px)
    #             expanded_h = center_h + (2.0 * edge_offset_img_px)

    #             expanded_rect = (
    #                 (center_x, center_y),
    #                 (expanded_w, expanded_h),
    #                 angle,
    #             )
    #             return marker_rect, expanded_rect, "offset_image_est", None

    #         return marker_rect, marker_rect, "raw", None

    #     return marker_rect, marker_rect, "raw", None

    # def _save_detect_markers_debug_image(
    #     frame: np.ndarray,
    #     marker_infos: list,
    #     status: str,
    # ) -> None:
    #     if not args.save_detect_debug or marker_debug_dir is None:
    #         return

    #     annotated = frame.copy()

    #     margin_px = int(getattr(config, "MARKER_MARGIN_PX", 30.0))
    #     screen_width_px = int(getattr(config, "SCREEN_WIDTH_PX", 0.0))
    #     screen_height_px = int(getattr(config, "SCREEN_HEIGHT_PX", 0.0))
    #     border_points = controller.get_grid_border_points(
    #         margin_px=margin_px,
    #         screen_width_px=screen_width_px,
    #         screen_height_px=screen_height_px,
    #     )

    #     if border_points:
    #         border_array = np.array(border_points, dtype=np.int32).reshape((-1, 1, 2))
    #         cv2.polylines(annotated, [border_array], isClosed=True, color=(255, 0, 0), thickness=2)
    #         first_x, first_y = border_points[0]
    #         cv2.putText(
    #             annotated,
    #             "SCREEN BORDER",
    #             (int(first_x) + 8, int(first_y) - 8),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.55,
    #             (255, 0, 0),
    #             2,
    #             cv2.LINE_AA,
    #         )

    #     for marker in marker_infos:
    #         corners = np.array(marker.corners, dtype=np.int32).reshape((-1, 1, 2))
    #         cv2.polylines(annotated, [corners], isClosed=True, color=(0, 255, 0), thickness=2)

    #         cx, cy = marker.centroid
    #         cv2.circle(annotated, (int(cx), int(cy)), 4, (0, 255, 255), -1)
    #         cv2.putText(
    #             annotated,
    #             f"ID:{marker.marker_id} A:{marker.area:.0f}",
    #             (int(cx) + 6, int(cy) - 6),
    #             cv2.FONT_HERSHEY_SIMPLEX,
    #             0.5,
    #             (0, 255, 0),
    #             2,
    #             cv2.LINE_AA,
    #         )

    #     if marker_infos:
    #         marker_rect, expanded_rect, estimate_mode, screen_quad = _estimate_screen_rect_from_markers(
    #             marker_infos
    #         )
    #         (rect_w, rect_h) = expanded_rect[1]
    #         if rect_w > 0 and rect_h > 0:
    #             if screen_quad is not None:
    #                 quad = screen_quad.astype(np.int32).reshape((-1, 1, 2))
    #                 cv2.polylines(annotated, [quad], isClosed=True, color=(0, 165, 255), thickness=2)
    #                 label_x = int(np.min(screen_quad[:, 0]))
    #                 label_y = int(np.min(screen_quad[:, 1])) - 10
    #             else:
    #                 box = cv2.boxPoints(expanded_rect).astype(np.int32).reshape((-1, 1, 2))
    #                 cv2.polylines(annotated, [box], isClosed=True, color=(0, 165, 255), thickness=2)
    #                 label_x = int(np.min(box[:, 0, 0]))
    #                 label_y = int(np.min(box[:, 0, 1])) - 10
    #             label_suffix_map = {
    #                 "homography_exact_ids": "(+offset homo ids)",
    #                 "homography_exact": "(+offset homo)",
    #                 "offset_exact": "(+offset exact)",
    #                 "offset_corner_span": "(+offset corner)",
    #                 "offset_image_est": "(+offset est)",
    #                 "raw": "(raw)",
    #             }
    #             label_suffix = label_suffix_map.get(estimate_mode, f"({estimate_mode})")
    #             cv2.putText(
    #                 annotated,
    #                 f"EST SCREEN {rect_w:.0f}x{rect_h:.0f}px {label_suffix}",
    #                 (max(4, label_x), max(20, label_y)),
    #                 cv2.FONT_HERSHEY_SIMPLEX,
    #                 0.55,
    #                 (0, 165, 255),
    #                 2,
    #                 cv2.LINE_AA,
    #             )

    #     cv2.putText(
    #         annotated,
    #         "GREEN=MARKERS | BLUE=CONFIG BORDER | ORANGE=EST SCREEN",
    #         (10, 24),
    #         cv2.FONT_HERSHEY_SIMPLEX,
    #         0.55,
    #         (255, 255, 255),
    #         2,
    #         cv2.LINE_AA,
    #     )

    #     device_model = str(getattr(config, "DEVICE_MODEL", "unknown")).strip() or "unknown"
    #     device_line = f"DEVICE MODEL: {device_model}"
    #     text_size, baseline = cv2.getTextSize(device_line, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    #     text_x = max(10, min(annotated.shape[1] - text_size[0] - 10, 10))
    #     text_y = max(text_size[1] + 10, annotated.shape[0] - 14)

    #     cv2.putText(
    #         annotated,
    #         device_line,
    #         (text_x, text_y),
    #         cv2.FONT_HERSHEY_SIMPLEX,
    #         0.6,
    #         (0, 0, 0),
    #         4,
    #         cv2.LINE_AA,
    #     )
    #     cv2.putText(
    #         annotated,
    #         device_line,
    #         (text_x, text_y),
    #         cv2.FONT_HERSHEY_SIMPLEX,
    #         0.6,
    #         (255, 255, 255),
    #         2,
    #         cv2.LINE_AA,
    #     )

    #     timestamp_ms = int(time.time() * 1000)
    #     output_path = marker_debug_dir / f"detect_markers_{status}_{timestamp_ms}.jpg"
    #     if cv2.imwrite(str(output_path), annotated):
    #         logging.info("DetectMarkers debug image salva: %s", output_path)
    #     else:
    #         logging.error("Falha ao salvar imagem debug de DetectMarkers: %s", output_path)

    # def move_to_roi_fn() -> None:
    #     _apply_speed_profile("general")
    #     before_pose = robot.get_cartesian_pose()
    #     moved = False
    #     if hasattr(robot, "move_to_roi"):
    #         moved = bool(robot.move_to_roi())

    #     if not moved:
    #         # Fallback keeps execution robust if ROI pose is not configured yet.
    #         logging.warning("move_to_roi() retornou False. Aplicando fallback move_safe().")
    #         robot.move_safe(preserve_orientation=True)

    #     after_pose = robot.get_cartesian_pose()
    #     if before_pose is not None and after_pose is not None:
    #         dx = after_pose.x - before_pose.x
    #         dy = after_pose.y - before_pose.y
    #         dz = after_pose.z - before_pose.z
    #         logging.info(
    #             "ROI delta de pose: dx=%.3f, dy=%.3f, dz=%.3f (moved=%s)",
    #             dx,
    #             dy,
    #             dz,
    #             moved,
    #         )
    #     else:
    #         logging.info("Não foi possível comparar pose antes/depois do move_to_roi (moved=%s)", moved)

    #     runtime["markers"] = []
    #     runtime["z_touch"] = None
    #     runtime["aligned_screen_quad"] = None
    #     runtime["aligned_screen_estimate_mode"] = "raw"

    # def _backoff_for_fov(reason: str, step_z_mm: float = 35.0) -> bool:
    #     """Recua em Z para aumentar campo de visão quando restam poucos marcadores."""
    #     try:
    #         _apply_speed_profile("general")
    #         current_pose = robot.get_cartesian_pose()
    #         if current_pose is None:
    #             return False

    #         target_pose = Pose(
    #             x=float(current_pose.x),
    #             y=float(current_pose.y),
    #             z=float(current_pose.z) + float(step_z_mm),
    #             rx=float(current_pose.rx),
    #             ry=float(current_pose.ry),
    #             rz=float(current_pose.rz),
    #             fig=int(getattr(current_pose, "fig", 5)),
    #         )

    #         if target_pose.z > float(getattr(robot, "SAFE_Z", target_pose.z)):
    #             target_pose.z = float(getattr(robot, "SAFE_Z", target_pose.z))

    #         moved = robot.move_cartesian(target_pose)
    #         if moved:
    #             logging.warning(
    #                 "FOV recovery (%s): recuo Z aplicado para %.2fmm (step=%.1fmm).",
    #                 reason,
    #                 float(target_pose.z),
    #                 float(step_z_mm),
    #             )
    #             runtime["z_touch"] = None
    #         return bool(moved)
    #     except Exception as exc:
    #         logging.warning("FOV recovery failed: %s", exc)
    #         return False

    # def camera_on_fn() -> bool:
    #     return camera.capture_frame_frame() is not None

    # def _capture_markers_once(*, silent_no_markers: bool = True) -> list:
    #     """Captura um frame e retorna marcadores deduplicados por ID."""
    #     frame = camera.capture_frame_frame()
    #     if frame is None:
    #         return []

    #     marker_ids, marker_corners = detector.detect_markers(frame, log_missing=not silent_no_markers)
    #     if marker_ids is None or marker_corners is None:
    #         return []

    #     refined_corners = detector.refine_corners(frame, marker_corners)
    #     marker_infos = [
    #         detector.get_marker_info(int(marker_ids[idx][0]), refined_corners[idx])
    #         for idx in range(len(marker_ids))
    #     ]

    #     marker_by_id = {}
    #     for marker in marker_infos:
    #         current = marker_by_id.get(marker.marker_id)
    #         if current is None or float(marker.area) > float(current.area):
    #             marker_by_id[marker.marker_id] = marker

    #     return sorted(marker_by_id.values(), key=lambda m: int(m.marker_id))

    # def _recover_partial_markers(frame: np.ndarray, marker_infos: list, required_markers: int) -> list:
    #     """FOV-style bounded recovery: centraliza marcador âncora e tenta reacquirir conjunto completo."""
    #     if len(marker_infos) < 2:
    #         return marker_infos

    #     recovery_iters = 5
    #     current_markers = marker_infos
    #     current_frame = frame

    #     for _ in range(recovery_iters):
    #         h, w = current_frame.shape[:2]

    #         # Prioriza ID 1 (top-left no layout flat); fallback para marcador mais próximo do centro.
    #         anchor = next((m for m in current_markers if int(m.marker_id) == 1), None)
    #         if anchor is None:
    #             image_center = np.array([w / 2.0, h / 2.0], dtype=np.float32)
    #             anchor = min(
    #                 current_markers,
    #                 key=lambda m: float(np.linalg.norm(np.array(m.centroid, dtype=np.float32) - image_center)),
    #             )

    #         corr_x, corr_y = auto_align.transform.image_center_offset_mm(
    #             float(anchor.centroid[0]),
    #             float(anchor.centroid[1]),
    #             w,
    #             h,
    #             float(anchor.width_px),
    #             float(anchor.height_px),
    #         )

    #         # Movimento conservador por iteração, no estilo loop curto do FOV.
    #         corr_x = max(-10.0, min(10.0, corr_x))
    #         corr_y = max(-10.0, min(10.0, corr_y))

    #         if abs(corr_x) < 1.0 and abs(corr_y) < 1.0:
    #             break

    #         if not auto_align.apply_correction(corr_x, corr_y, 0.0):
    #             break

    #         runtime["partial_recovery_moves"] += 1
    #         logging.info(
    #             "DetectMarkers recovery move #%d: anchor_id=%s visible=%d/%d corr=(%.2f,%.2f)",
    #             runtime["partial_recovery_moves"],
    #             anchor.marker_id,
    #             len(current_markers),
    #             required_markers,
    #             corr_x,
    #             corr_y,
    #         )

    #         time.sleep(0.08)

    #         next_frame = camera.capture_frame_frame()
    #         if next_frame is None:
    #             break
    #         current_frame = next_frame
    #         next_markers = _capture_markers_once()
    #         if next_markers:
    #             current_markers = next_markers
    #         if len(current_markers) >= required_markers:
    #             break

    #     return current_markers

    # def detect_markers_fn() -> bool:
    #     # Faz múltiplas tentativas rápidas para reduzir flutuação de foco/iluminação.
    #     best_frame = None
    #     best_marker_infos = []
    #     detect_attempts = 10
    #     required_markers = max(1, int(model.num_markers))
    #     min_markers_for_align = max(
    #         1,
    #         int(getattr(config, "AUTO_ALIGNMENT_CONFIG", {}).get("min_markers_for_align", 2)),
    #     )

    #     for _ in range(detect_attempts):
    #         frame = camera.capture_frame_frame()
    #         if frame is None:
    #             continue

    #         marker_ids, marker_corners = detector.detect_markers(frame, log_missing=False)
    #         if marker_ids is None or marker_corners is None:
    #             if best_frame is None:
    #                 best_frame = frame
    #             continue

    #         refined_corners = detector.refine_corners(frame, marker_corners)
    #         marker_infos = [
    #             detector.get_marker_info(int(marker_ids[idx][0]), refined_corners[idx])
    #             for idx in range(len(marker_ids))
    #         ]

    #         if len(marker_infos) > len(best_marker_infos):
    #             best_marker_infos = marker_infos
    #             best_frame = frame
    #             if len(best_marker_infos) >= required_markers:
    #                 break

    #         time.sleep(0.03)

    #     frame = best_frame
    #     marker_infos = best_marker_infos
    #     if frame is None:
    #         logging.warning("DetectMarkers: captura de frame falhou (frame=None).")
    #         runtime["markers"] = []
    #         model.markers_count = 0
    #         return False

    #     if not marker_infos:
    #         runtime["markers"] = []
    #         model.markers_count = 0
    #         runtime["detect_no_marker_streak"] = int(runtime.get("detect_no_marker_streak", 0)) + 1
    #         runtime["detect_low_marker_streak"] = 0
    #         logging.info("DetectMarkers: nenhum marcador detectado.")

    #         should_reacquire = (
    #             bool(runtime.get("lost_markers_in_align", False))
    #             or int(runtime.get("detect_no_marker_streak", 0)) >= 3
    #         )
    #         reacquire_cooldown = 0.8
    #         now_ts = time.time()
    #         can_reacquire = (now_ts - float(runtime.get("last_reacquire_ts", 0.0))) >= reacquire_cooldown

    #         if should_reacquire and can_reacquire:
    #             logging.warning(
    #                 "DetectMarkers: sem marcadores em sequência (streak=%d). Executando recuperação ativa para ROI.",
    #                 int(runtime.get("detect_no_marker_streak", 0)),
    #             )
    #             runtime["last_reacquire_ts"] = now_ts
    #             runtime["lost_markers_in_align"] = False

    #             try:
    #                 move_to_roi_fn()
    #             except Exception as rec_err:
    #                 logging.warning("DetectMarkers: falha na recuperação ativa para ROI: %s", rec_err)

    #             time.sleep(0.12)
    #             recovered_after_reacquire = _capture_markers_once(silent_no_markers=True)
    #             if len(recovered_after_reacquire) >= min_markers_for_align:
    #                 runtime["markers"] = recovered_after_reacquire
    #                 model.markers_count = len(recovered_after_reacquire)
    #                 runtime["detect_no_marker_streak"] = 0
    #                 recovered_ids = [m.marker_id for m in recovered_after_reacquire]
    #                 logging.info(
    #                     "DetectMarkers: recuperação ativa adquiriu %d marcador(es). IDs=%s",
    #                     len(recovered_after_reacquire),
    #                     recovered_ids,
    #                 )
    #                 return True

    #         _save_detect_markers_debug_image(frame, [], status="no_markers")
    #         return False

    #     runtime["detect_no_marker_streak"] = 0
    #     runtime["lost_markers_in_align"] = False

    #     # Mantém apenas um marcador por ID (maior área) para evitar duplicatas.
    #     marker_by_id = {}
    #     for marker in marker_infos:
    #         current = marker_by_id.get(marker.marker_id)
    #         if current is None or float(marker.area) > float(current.area):
    #             marker_by_id[marker.marker_id] = marker
    #     marker_infos = sorted(marker_by_id.values(), key=lambda m: int(m.marker_id))

    #     marker_ids_list = [marker.marker_id for marker in marker_infos]
    #     logging.info(
    #         "DetectMarkers: %d marcador(es) detectado(s). IDs=%s",
    #         len(marker_infos),
    #         marker_ids_list,
    #     )

    #     marker_rect, estimated_rect, estimate_mode, screen_quad = _estimate_screen_rect_from_markers(
    #         marker_infos
    #     )
    #     runtime["screen_quad"] = None if screen_quad is None else screen_quad.tolist()
    #     runtime["screen_estimate_mode"] = estimate_mode
    #     marker_span_w, marker_span_h = marker_rect[1]
    #     estimated_w, estimated_h = estimated_rect[1]
    #     logging.info(
    #         "DetectMarkers marker_span_px: width=%.1f height=%.1f",
    #         marker_span_w,
    #         marker_span_h,
    #     )
    #     logging.info(
    #         "DetectMarkers screen_estimate_px: width=%.1f height=%.1f (estimate_mode=%s)",
    #         estimated_w,
    #         estimated_h,
    #         estimate_mode,
    #     )
    #     if estimate_mode == "raw":
    #         logging.warning(
    #             "DetectMarkers offset_model desativado; metadados atuais: screen_width_px=%.1f "
    #             "screen_height_px=%.1f margin_px=%.1f tag_size_px=%.1f",
    #             float(getattr(config, "SCREEN_WIDTH_PX", 0.0)),
    #             float(getattr(config, "SCREEN_HEIGHT_PX", 0.0)),
    #             float(getattr(config, "MARKER_MARGIN_PX", 0.0)),
    #             float(getattr(config, "MARKER_TAG_SIZE_PX", 0.0)),
    #         )
    #     for marker in marker_infos:
    #         cx, cy = marker.centroid
    #         logging.info(
    #             "DetectMarkers detalhe: id=%s centroid=(%.1f, %.1f) area=%.1f px width=%.1f px height=%.1f px",
    #             marker.marker_id,
    #             cx,
    #             cy,
    #             marker.area,
    #             marker.width_px,
    #             marker.height_px,
    #         )

    #     _save_detect_markers_debug_image(frame, marker_infos, status="ok")
    #     if len(marker_infos) < required_markers:
    #         runtime["detect_low_marker_streak"] = int(runtime.get("detect_low_marker_streak", 0)) + 1
    #         recovered_markers = marker_infos
    #         try:
    #             recovered_markers = _recover_partial_markers(frame, marker_infos, required_markers)
    #         except Exception as rec_err:
    #             logging.warning(
    #                 "DetectMarkers: erro na recuperação parcial (%s). Seguindo com conjunto visível atual.",
    #                 rec_err,
    #             )

    #         if len(recovered_markers) >= required_markers:
    #             runtime["markers"] = recovered_markers
    #             model.markers_count = len(recovered_markers)
    #             recovered_ids = [m.marker_id for m in recovered_markers]
    #             logging.info(
    #                 "DetectMarkers: recuperação bem-sucedida (%d/%d). IDs=%s",
    #                 len(recovered_markers),
    #                 required_markers,
    #                 recovered_ids,
    #             )
    #             return True

    #         # Estratégia FOV-like: com conjunto parcial estável, entra no align para recuperar os faltantes.
    #         if len(recovered_markers) >= min_markers_for_align:
    #             runtime["markers"] = recovered_markers
    #             model.markers_count = len(recovered_markers)
    #             partial_ids = [m.marker_id for m in recovered_markers]
    #             logging.warning(
    #                 "DetectMarkers: conjunto parcial aceito para pré-alinhamento (%d/%d). IDs=%s",
    #                 len(recovered_markers),
    #                 required_markers,
    #                 partial_ids,
    #             )
    #             return True

    #         runtime["markers"] = []
    #         model.markers_count = 0
    #         # Se ficar preso em 1 marcador por várias iterações, recua em Z para abrir FOV.
    #         now_ts = time.time()
    #         low_streak = int(runtime.get("detect_low_marker_streak", 0))
    #         if len(recovered_markers) <= 1 and low_streak >= 3:
    #             if (now_ts - float(runtime.get("last_fov_backoff_ts", 0.0))) >= 1.2:
    #                 if _backoff_for_fov(reason=f"low_markers_{len(recovered_markers)}"):
    #                     runtime["last_fov_backoff_ts"] = now_ts

    #         logging.warning(
    #             "DetectMarkers: detectados %d/%d marcadores. Aguardando conjunto completo antes do AlignWithMarkers.",
    #             len(marker_infos),
    #             required_markers,
    #         )
    #         return False

    #     runtime["detect_low_marker_streak"] = 0
    #     runtime["markers"] = marker_infos
    #     model.markers_count = len(marker_infos)
    #     return True

    # def align_with_markers_fn() -> bool:
    #     _apply_speed_profile("general")
    #     required_markers = max(1, int(model.num_markers))
    #     min_markers_for_align = max(
    #         1,
    #         int(getattr(config, "AUTO_ALIGNMENT_CONFIG", {}).get("min_markers_for_align", 2)),
    #     )

    #     # Usa primeiro o snapshot produzido em DetectMarkers para respeitar o ciclo FSM
    #     # detect -> align -> touch. Se estiver vazio/insuficiente, tenta atualizar uma vez.
    #     visible_markers = list(runtime.get("markers", []))
    #     if len(visible_markers) < min_markers_for_align:
    #         visible_markers = _capture_markers_once()
    #     if len(visible_markers) < min_markers_for_align:
    #         runtime["markers"] = []
    #         model.markers_found_flag = False
    #         logging.warning(
    #             "AlignWithMarkers: visibilidade insuficiente (%d/%d mínimo). Voltando para DetectMarkers.",
    #             len(visible_markers),
    #             min_markers_for_align,
    #         )
    #         return False

    #     runtime["markers"] = visible_markers
    #     model.markers_count = len(visible_markers)
    #     model.markers_found_flag = True

    #     if auto_align.reference_marker_area is None and not auto_align.calibrate_distance():
    #         visible_after_calibration = _capture_markers_once()
    #         if len(visible_after_calibration) < min_markers_for_align:
    #             runtime["markers"] = []
    #             model.markers_found_flag = False
    #             logging.warning(
    #                 "AlignWithMarkers: calibração falhou e marcadores insuficientes (%d/%d mínimo). Voltando para DetectMarkers.",
    #                 len(visible_after_calibration),
    #                 min_markers_for_align,
    #             )
    #         return False

    #     target_distance = config.TOUCH_CONFIG.get("approach_distance_mm", 150.0)
    #     ok = auto_align.approach_marker(target_distance)
    #     if ok:
    #         # Só conclui alinhamento quando o conjunto completo reaparece.
    #         visible_after_align = _capture_markers_once()
    #         if len(visible_after_align) >= required_markers:
    #             runtime["markers"] = visible_after_align
    #             model.markers_found_flag = True
    #             runtime["z_touch"] = auto_align.get_touch_z()

    #             # Congela a geometria de tela do frame validado no alinhamento.
    #             try:
    #                 _, _, aligned_mode, aligned_quad = _estimate_screen_rect_from_markers(visible_after_align)
    #                 if aligned_quad is not None:
    #                     runtime["aligned_screen_quad"] = aligned_quad.tolist()
    #                     runtime["aligned_screen_estimate_mode"] = aligned_mode
    #                 else:
    #                     runtime["aligned_screen_quad"] = runtime.get("screen_quad")
    #                     runtime["aligned_screen_estimate_mode"] = runtime.get("screen_estimate_mode", "raw")
    #             except Exception as quad_err:
    #                 logging.warning("AlignWithMarkers: falha ao congelar screen_quad (%s)", quad_err)
    #                 runtime["aligned_screen_quad"] = runtime.get("screen_quad")
    #                 runtime["aligned_screen_estimate_mode"] = runtime.get("screen_estimate_mode", "raw")

    #             # Salva a pose cartesiana completa (x, y, z, rx, ry, rz) para uso no toque
    #             current_pose = auto_align.get_current_pose()
    #             if current_pose:
    #                 runtime["aligned_pose"] = current_pose
    #                 logging.info(
    #                     "AlignWithMarkers: pose salva para toque: (%.2f, %.2f, %.2f, %.2f, %.2f, %.2f)",
    #                     *current_pose
    #                 )
    #             logging.info(
    #                 "AlignWithMarkers: alinhado com sucesso e conjunto completo visível (%d/%d).",
    #                 len(visible_after_align),
    #                 required_markers,
    #             )
    #             return True

    #         # Mesmo com melhora parcial, volta para DetectMarkers para adquirir novo snapshot.
    #         runtime["markers"] = []
    #         model.markers_found_flag = False
    #         logging.warning(
    #             "AlignWithMarkers: alinhou geometria, mas conjunto completo ainda não visível (%d/%d). Voltando para DetectMarkers.",
    #             len(visible_after_align),
    #             required_markers,
    #         )
    #         return False
    #     else:
    #         visible_after_align = _capture_markers_once()
    #         if len(visible_after_align) < min_markers_for_align:
    #             runtime["markers"] = []
    #             model.markers_found_flag = False
    #             runtime["lost_markers_in_align"] = True
    #             logging.warning(
    #                 "AlignWithMarkers: perdeu marcadores durante alinhamento (%d/%d mínimo). Voltando para DetectMarkers.",
    #                 len(visible_after_align),
    #                 min_markers_for_align,
    #             )
    #         else:
    #             # Não alinhou ainda: força retorno para DetectMarkers para novo frame/snapshot.
    #             runtime["markers"] = []
    #             model.markers_found_flag = False
    #         logging.warning(
    #             "AlignWithMarkers: ainda não alinhado (tentativa %d/%d). Voltando para DetectMarkers.",
    #             int(getattr(model, "align_with_markers_attempt", 0)) + 1,
    #             int(getattr(model, "max_align_with_markers_attempts", 0)),
    #         )
    #     return ok

    # def generate_map_fn() -> None:
    #     markers = runtime.get("markers", [])
    #     touches = runtime.get("fiducial_touches", [])
    #     runtime["generated_map"] = {
    #         "test_id": test_metrics.test_id,
    #         "timestamp_epoch_s": time.time(),
    #         "device_model": str(getattr(config, "DEVICE_MODEL", "unknown")),
    #         "screen_width_px": float(getattr(config, "SCREEN_WIDTH_PX", 0.0)),
    #         "screen_height_px": float(getattr(config, "SCREEN_HEIGHT_PX", 0.0)),
    #         "margin_px": float(getattr(config, "MARKER_MARGIN_PX", 0.0)),
    #         "tag_size_px": float(getattr(config, "MARKER_TAG_SIZE_PX", 0.0)),
    #         "estimate_mode": runtime.get("screen_estimate_mode", "raw"),
    #         "screen_quad": runtime.get("screen_quad"),
    #         "markers": [
    #             {
    #                 "marker_id": int(m.marker_id),
    #                 "centroid": [float(m.centroid[0]), float(m.centroid[1])],
    #                 "area": float(m.area),
    #                 "width_px": float(m.width_px),
    #                 "height_px": float(m.height_px),
    #             }
    #             for m in markers
    #         ],
    #         "fiducial_touches": touches,
    #         "status": "ready" if len(markers) >= int(model.num_markers) else "incomplete",
    #     }
    #     logging.info(
    #         "GenerateMap: mapa gerado (markers=%d, touches=%d, mode=%s).",
    #         len(markers),
    #         len(touches),
    #         runtime.get("screen_estimate_mode", "raw"),
    #     )

    # def save_map_fn() -> None:
    #     map_payload = runtime.get("generated_map")
    #     if not isinstance(map_payload, dict):
    #         logging.warning("SaveMap: mapa indisponível; gerando on-demand.")
    #         generate_map_fn()
    #         map_payload = runtime.get("generated_map")

    #     if not isinstance(map_payload, dict):
    #         logging.error("SaveMap: falha ao gerar mapa para salvar.")
    #         return

    #     out_dir = Path(args.metrics_dir)
    #     out_dir.mkdir(parents=True, exist_ok=True)
    #     map_file = out_dir / f"map_{test_metrics.test_id}.json"
    #     map_file.write_text(json.dumps(map_payload, ensure_ascii=True, indent=2), encoding="utf-8")
    #     runtime["saved_map_file"] = str(map_file)
    #     logging.info("SaveMap: mapa salvo em %s", map_file)

    # def touch_marker_fn(index: int) -> bool:
    #     """Toca marcador escutando continuamente durante o movimento."""
    #     _apply_speed_profile("touch")
    #     markers = runtime["markers"]
    #     if index < 0 or index >= len(markers):
    #         runtime["last_touch_success"] = False
    #         return False

    #     z_touch = runtime["z_touch"]
    #     if z_touch is None:
    #         z_touch = auto_align.get_touch_z()
    #         runtime["z_touch"] = z_touch

    #     marker = markers[index]
    #     target_x, target_y = marker.centroid
    #     area_px = marker.area

    #     # Se há pose salva de alinhamento bem-sucedido, usa ela como base.
    #     # Isso evita re-converter imagem para robô (o que estava gerando X errado).
    #     aligned_pose = runtime.get("aligned_pose")
    #     if aligned_pose and len(aligned_pose) >= 6:
    #         try:
    #             # Use a pose exata do alinhamento, apenas ajustando Z para o toque
    #             pose_x, pose_y, pose_z, pose_rx, pose_ry, pose_rz = aligned_pose
    #             # Move usando a pose salva e o Z corrigido para toque
    #             controller.robot_arm.motor_on()
    #             ok, touch_info = controller.move_and_listen_until_touch(
    #                 target_x=float(pose_x),
    #                 target_y=float(pose_y),
    #                 z_touch=float(z_touch),
    #                 rx=float(pose_rx),
    #                 ry=float(pose_ry),
    #                 rz=float(pose_rz),
    #                 speed=float(speed_profiles["touch"]["speed"]),
    #                 accel=float(speed_profiles["touch"]["accel"]),
    #                 decel=float(speed_profiles["touch"]["decel"]),
    #                 touch_timeout=args.touch_timeout,
    #             )
    #         except Exception as pose_err:
    #             logging.warning(
    #                 "Touch usando aligned_pose falhou (%s); tentando via marker conversion.",
    #                 pose_err,
    #             )
    #             # Fallback: tenta conversão de imagem (original)
    #             ok, touch_info = controller.touch_marker_listen_while_moving(
    #                 marker,
    #                 z_touch=z_touch,
    #                 speed=float(speed_profiles["touch"]["speed"]),
    #                 accel=float(speed_profiles["touch"]["accel"]),
    #                 decel=float(speed_profiles["touch"]["decel"]),
    #                 touch_timeout=args.touch_timeout,
    #             )
    #     else:
    #         # Sem aligned_pose, usa conversão de imagem
    #         ok, touch_info = controller.touch_marker_listen_while_moving(
    #             marker,
    #             z_touch=z_touch,
    #             speed=float(speed_profiles["touch"]["speed"]),
    #             accel=float(speed_profiles["touch"]["accel"]),
    #             decel=float(speed_profiles["touch"]["decel"]),
    #             touch_timeout=args.touch_timeout,
    #         )

    #     if touch_info:
    #         actual_x, actual_y = touch_info.get("touch_position", (target_x, target_y))
    #         position_error = touch_info.get("position_error_px", 0.0)
    #         touch_pressure = touch_info.get("touch_pressure", 0)
    #         logging.info(
    #             f"Marcador {marker.marker_id}: toque em ({actual_x:.1f}, {actual_y:.1f}), "
    #             f"erro={position_error:.1f}px, pressão={touch_pressure}g"
    #         )
    #     else:
    #         actual_x, actual_y = target_x, target_y

    #     metrics_logger.record_touch(
    #         test_metrics,
    #         marker_index=index,
    #         target_x=target_x,
    #         target_y=target_y,
    #         actual_x=actual_x,
    #         actual_y=actual_y,
    #         area_px=area_px,
    #     )

    #     if ok and touch_info:
    #         runtime["fiducial_touches"].append(touch_info)

    #     runtime["last_touch_success"] = bool(ok)
    #     return ok

    # def check_touch_fn(_index: int) -> bool:
    #     # O toque já é validado dentro de touch_marker_fn via listen-while-moving.
    #     return bool(runtime.get("last_touch_success", False))

    # def reset_markers_fn() -> None:
    #     _apply_speed_profile("touch")
    #     frame = camera.capture_frame_frame()
    #     if frame is None:
    #         runtime["markers"] = []
    #         return

    #     height, width = frame.shape[:2]
    #     center_x = width // 2
    #     center_y = height // 2

    #     z_touch = runtime["z_touch"]
    #     if z_touch is None:
    #         z_touch = auto_align.get_touch_z()
    #         runtime["z_touch"] = z_touch

    #     controller.touch_pixel(center_x, center_y, z_touch=z_touch)
    #     runtime["markers"] = []
    #     runtime["z_touch"] = None

    # def swipe_borders_fn() -> bool:
    #     """Swipe com monitoramento de segurança (pressão, sinal)."""
    #     _apply_speed_profile("swipe")
    #     z_touch = runtime["z_touch"]
    #     if z_touch is None:
    #         z_touch = auto_align.get_touch_z()
    #         runtime["z_touch"] = z_touch

    #     margin_px = int(getattr(config, "MARKER_MARGIN_PX", 30.0))
    #     screen_width_px = int(getattr(config, "SCREEN_WIDTH_PX", 0.0))
    #     screen_height_px = int(getattr(config, "SCREEN_HEIGHT_PX", 0.0))

    #     points = []
    #     aligned_quad = runtime.get("aligned_screen_quad")
    #     if aligned_quad is not None:
    #         points = controller.get_grid_border_points_from_screen_quad(
    #             screen_quad=aligned_quad,
    #             margin_px=margin_px,
    #             screen_width_px=screen_width_px,
    #             screen_height_px=screen_height_px,
    #         )
    #         if points:
    #             logging.info(
    #                 "SwipeBorders: usando pontos baseados no aligned_screen_quad (mode=%s).",
    #                 runtime.get("aligned_screen_estimate_mode", "raw"),
    #             )

    #     if not points:
    #         points = controller.get_grid_border_points(
    #             margin_px=margin_px,
    #             screen_width_px=screen_width_px,
    #             screen_height_px=screen_height_px,
    #         )
    #         if points:
    #             logging.info("SwipeBorders: fallback para pontos retangulares da imagem.")
    #     if not points:
    #         return False

    #     swipe_start = time.time()
    #     # Use novo fluxo seguro: monitora pressão e sinal durante swipe
    #     ok, swipe_reason = controller.swipe_with_safety_monitoring(
    #         points,
    #         z_touch=z_touch,
    #         speed=float(speed_profiles["swipe"]["speed"]),
    #         accel=float(speed_profiles["swipe"]["accel"]),
    #         decel=float(speed_profiles["swipe"]["decel"]),
    #     )
    #     swipe_duration = time.time() - swipe_start

    #     # Se swipe falhou por motivos de segurança, ir a safe_pose para ler resultado
    #     if not ok and swipe_reason in ["signal_loss", "excessive_pressure"]:
    #         logging.warning(f"Swipe falhou por: {swipe_reason}. Movendo para safe_pose.")
    #         robot.move_safe(preserve_orientation=True)

    #     # Record swipe metric
    #     metrics_logger.record_swipe(
    #         test_metrics,
    #         num_points=len(points),
    #         duration_sec=swipe_duration,
    #         success=ok,
    #     )

    #     return ok

    # def safe_pose_fn() -> None:
    #     _apply_speed_profile("general")
    #     robot.move_safe(preserve_orientation=True)

    # def read_final_marker_fn() -> str:
    #     frame = camera.capture_frame_frame()
    #     if frame is None:
    #         return model.RESULT_FAILURE

    #     marker_ids, _ = detector.detect_markers(frame)
    #     if marker_ids is None:
    #         return model.RESULT_FAILURE

    #     detected = {int(curr[0]) for curr in marker_ids}
    #     if config.FINAL_SUCCESS_MARKER_ID in detected:
    #         return model.RESULT_SUCCESS
    #     if config.FINAL_FAILURE_MARKER_ID in detected:
    #         return model.RESULT_FAILURE
    #     return model.RESULT_FAILURE

    # def return_to_start_fn() -> None:
    #     _apply_speed_profile("touch")
    #     frame = camera.capture_frame_frame()
    #     if frame is None:
    #         return

    #     height, width = frame.shape[:2]
    #     center_x = width // 2
    #     center_y = height // 2

    #     z_touch = runtime["z_touch"]
    #     if z_touch is None:
    #         z_touch = auto_align.get_touch_z()
    #         runtime["z_touch"] = z_touch

    #     controller.touch_pixel(center_x, center_y, z_touch=z_touch)
    #     runtime["markers"] = []
    #     runtime["z_touch"] = None

    # # Inject optional hooks to implement operational behavior for states.
    # model.move_to_roi_fn = move_to_roi_fn
    # model.camera_on_fn = camera_on_fn
    # model.detect_markers_fn = detect_markers_fn
    # model.align_with_markers_fn = align_with_markers_fn
    # model.touch_marker_fn = touch_marker_fn
    # model.check_touch_fn = check_touch_fn
    # model.reset_markers_fn = reset_markers_fn
    # model.generate_map_fn = generate_map_fn
    # model.swipe_borders_fn = swipe_borders_fn
    # model.safe_pose_fn = safe_pose_fn
    # model.read_final_marker_fn = read_final_marker_fn
    # model.return_to_start_fn = return_to_start_fn
    # model.save_map_fn = save_map_fn

    # # Inject robot adapter so model callbacks can call connect/motor actions.
    # model.denso_robot = robot
    # machine = Rta(model)

    # if args.stop_at_state:
    #     stop_state = args.stop_at_state.strip().lower()
    #     states_attr = machine.states
    #     if hasattr(states_attr, "keys"):
    #         valid_states = {str(name) for name in states_attr.keys()}
    #     else:
    #         valid_states = {str(getattr(state, "name", state)) for state in states_attr}

    #     if stop_state not in valid_states:
    #         logging.error(
    #             "Estado inválido em --stop-at-state: '%s'. Estados válidos: %s",
    #             args.stop_at_state,
    #             ", ".join(sorted(valid_states)),
    #         )
    #         return 2

    #     args.stop_at_state = stop_state

    # logging.info("FSM started at state: %s", machine.state)

    # steps = 0
    # while machine.state not in ["done", "error"]:
    #     current_state = machine.state
    #     machine.next_state()
    #     next_state = machine.state
    #     steps += 1

    #     if args.stop_at_state and next_state == args.stop_at_state:
    #         logging.info("Stop target reached: %s", next_state)
    #         break

    #     # Record state transition timing
    #     if current_state != next_state:
    #         state_duration = time.time() - runtime["state_enter_time"]
    #         metrics_logger.record_state_transition(
    #             test_metrics, current_state, next_state, state_duration
    #         )
    #         runtime["state_enter_time"] = time.time()
    #         runtime["last_state"] = next_state

    #     if steps >= args.max_steps:
    #         logging.error("Max steps reached (%s). Stopping.", args.max_steps)
    #         break

    #     time.sleep(args.loop_delay)

    # logging.info("FSM stopped at state: %s (steps=%s)", machine.state, steps)

    # # Finalize and save metrics
    # final_result = "success" if machine.state == "done" else "error"
    # if args.stop_at_state and machine.state == args.stop_at_state:
    #     final_result = f"stopped_at_{args.stop_at_state}"
    # metrics_logger.finalize_test(
    #     test_metrics,
    #     final_result=final_result,
    #     total_steps=steps,
    #     error_touches=model.error_touch,
    # )
    # metrics_file = metrics_logger.save_metrics(test_metrics)
    # logging.info("Test metrics saved to: %s", metrics_file)

    # try:
    #     device.stop()
    # except Exception:
    #     pass

    # try:
    #     camera.release()
    # except Exception:
    #     pass

    # try:
    #     robot.disconnect()
    # except Exception:
    #     pass

    # if args.stop_at_state and machine.state == args.stop_at_state:
    #     return 0

    # return 0 if machine.state == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
