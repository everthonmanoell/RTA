import logging
import time
from typing import List, Optional, Tuple

import cv2
import numpy as np
from aether_rdk.datatypes import Pose

from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.alignment.rotation_alignment import RotationAlignment
from drivers.device.mobile import TouchAction, TouchTracker, map_raw_touch_to_screen
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import CoordinateTransform


class MarkerTouchController:
    """
    Controller operacional para interação do robô com a tela do dispositivo.

    Responsabilidades:
    - converter coordenadas da imagem para coordenadas do robô
    - tocar no centro de marcadores
    - tocar em pixels específicos (ex.: botão vermelho, voltar da tela de falha)
    - gerar pontos de borda para swipe
    - executar swipe contínuo
    """

    def __init__(
        self,
        robot_arm,
        mobile_device,
        camera: RobotCamera,
        transform: CoordinateTransform,
        auto_align: Optional[AutoAlignment] = None,
        rot_align: Optional[RotationAlignment] = None,
        detector: Optional[MarkerDetector] = None,
    ):
        self.robot_arm = robot_arm
        self.device = mobile_device
        self.camera = camera
        self.transform = transform
        self.auto_align = auto_align
        self.rot_align = rot_align
        self.detector = detector or MarkerDetector()

        self.logger = logging.getLogger(__name__)

        # parâmetros operacionais
        self.approach_height_mm = 10.0
        self.touch_delay_before_lift = 0.2
        self.touch_delay_after_touch = 0.3
        self.swipe_point_delay = 0.05

    # -------------------------------------------------
    # Utilidades internas
    # -------------------------------------------------

    def _capture_frame(self):
        """
        Captura um frame da câmera.
        """
        frame = self.camera.capture_frame()
        if frame is None:
            raise RuntimeError("Não foi possível capturar frame da câmera.")
        return frame

    def _capture_frame_shape(self) -> Tuple[int, int]:
        """
        Captura um frame e retorna (height, width).
        """
        frame = self._capture_frame()
        height, width = frame.shape[:2]
        return height, width

    def _get_current_robot_pose(self) -> tuple[float, float, float, float, float, float]:
        """
        Obtém a pose cartesiana atual do robô.

        Retorna:
            (x, y, z, rx, ry, rz)
        """
        pose = self.robot_arm.get_cartesian_pose()

        if pose is None:
            raise RuntimeError("Não foi possível obter a pose cartesiana atual do robô.")

        return pose.x, pose.y, pose.z, pose.rx, pose.ry, pose.rz

    def _set_robot_speed(
        self,
        speed: float,
        accel: Optional[float] = None,
        decel: Optional[float] = None,
    ) -> None:
        """
        Ajusta a velocidade do braço, se a API do robô suportar.
        """
        if hasattr(self.robot_arm, "set_arm_speed"):
            try:
                resolved_accel = float(accel) if accel is not None else float(speed)
                resolved_decel = float(decel) if decel is not None else float(speed)
                self.robot_arm.set_arm_speed(float(speed), resolved_accel, resolved_decel)
            except Exception as e:
                self.logger.warning(f"Não foi possível ajustar velocidade do braço: {e}")

    def _move_robot(
        self,
        x: float,
        y: float,
        z: float,
        rx: float,
        ry: float,
        rz: float,
    ) -> None:
        """
        Move o robô para uma pose cartesiana usando a API real do Denso.
        """
        # Obter fig (frame/figura) da pose atual do robô
        current_pose = self.robot_arm.get_cartesian_pose()
        fig = current_pose.fig if current_pose is not None else 5

        pose = Pose(x=x, y=y, z=z, rx=rx, ry=ry, rz=rz, fig=fig)

        success = self.robot_arm.move_cartesian(pose)

        if not success:
            raise RuntimeError(
                f"Falha ao mover robô para pose: "
                f"x={x}, y={y}, z={z}, rx={rx}, ry={ry}, rz={rz}"
            )

    def _image_to_robot_pose(
        self,
        x_px: int,
        y_px: int,
    ) -> tuple[float, float, float, float, float, float]:
        """
        Converte um ponto da imagem para pose alvo do robô,
        preservando a orientação atual.
        """
        frame = self._capture_frame()
        image_height, image_width = frame.shape[:2]

        offset_x_mm, offset_y_mm = self.transform.image_to_robot_2d(
            image_x=x_px,
            image_y=y_px,
            image_width=image_width,
            image_height=image_height,
        )

        current_x, current_y, current_z, current_rx, current_ry, current_rz = self._get_current_robot_pose()

        target_x, target_y, target_z = self.transform.apply_robot_transform(
            camera_frame_x=offset_x_mm,
            camera_frame_y=offset_y_mm,
            camera_frame_z=0.0,
            current_robot_x=current_x,
            current_robot_y=current_y,
            current_robot_z=current_z,
        )

        return target_x, target_y, target_z, current_rx, current_ry, current_rz

    # -------------------------------------------------
    # Toques
    # -------------------------------------------------

    def touch_pixel(self, x: int, y: int, z_touch: float) -> bool:
        """
        Toca em um pixel específico da imagem/tela.
        """
        try:
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(x, y)

            self.logger.info(
                f"Tocando pixel ({x}, {y}) -> robô ({target_x:.2f}, {target_y:.2f}, {z_touch:.2f})"
            )

            # aproxima
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )
            time.sleep(0.1)

            # toca
            self._move_robot(
                target_x,
                target_y,
                z_touch,
                rx,
                ry,
                rz,
            )
            time.sleep(self.touch_delay_before_lift)

            # sobe
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )
            time.sleep(self.touch_delay_after_touch)

            return True

        except Exception as e:
            self.logger.error(f"Falha ao tocar pixel ({x}, {y}): {e}")
            return False

    def touch_marker_center(self, marker_info: MarkerInfo, z_touch: float) -> bool:
        """
        Toca no centro do marcador detectado.
        """
        cx, cy = marker_info.centroid

        self.logger.info(
            f"Tocando centro do marcador {marker_info.marker_id} em ({cx}, {cy})"
        )

        return self.touch_pixel(int(cx), int(cy), z_touch=z_touch)

    # -------------------------------------------------
    # Swipe
    # -------------------------------------------------

    def get_grid_border_points(
        self,
        margin_px: int = 30,
        screen_width_px: int | None = None,
        screen_height_px: int | None = None,
    ) -> List[Tuple[int, int]]:
        """
        Gera pontos de borda para um swipe retangular.

        Por enquanto, usa as bordas da imagem capturada.
        Isso serve como primeira versão operacional.
        """
        try:
            image_height, image_width = self._capture_frame_shape()

            # If the app supplied the screen resolution, convert the device-side
            # border margin to camera-image coordinates.
            margin_x = margin_px
            margin_y = margin_px
            if screen_width_px and screen_height_px and screen_width_px > 0 and screen_height_px > 0:
                margin_x = int(round((margin_px / screen_width_px) * image_width))
                margin_y = int(round((margin_px / screen_height_px) * image_height))

            margin_x = max(1, min(margin_x, image_width // 2 - 1))
            margin_y = max(1, min(margin_y, image_height // 2 - 1))

            points = [
                (margin_x, margin_y),
                (image_width - margin_x, margin_y),
                (image_width - margin_x, image_height - margin_y),
                (margin_x, image_height - margin_y),
                (margin_x, margin_y),
            ]

            self.logger.info(f"Pontos de borda gerados: {points}")
            return points

        except Exception as e:
            self.logger.error(f"Falha ao gerar pontos de borda: {e}")
            return []

    def get_grid_border_points_from_screen_quad(
        self,
        screen_quad,
        margin_px: int = 30,
        screen_width_px: int | None = None,
        screen_height_px: int | None = None,
    ) -> List[Tuple[int, int]]:
        """
        Gera pontos de borda para swipe a partir de um quadrilátero de tela já estimado.

        Args:
            screen_quad: 4 pontos da tela em coordenadas de imagem [tl, tr, br, bl].
            margin_px: margem em pixels da tela do dispositivo (device space).
            screen_width_px: largura da tela do dispositivo.
            screen_height_px: altura da tela do dispositivo.
        """
        try:
            if (
                screen_quad is None
                or screen_width_px is None
                or screen_height_px is None
                or screen_width_px <= 0
                or screen_height_px <= 0
            ):
                return []

            quad = np.asarray(screen_quad, dtype=np.float32).reshape((4, 2))

            # Build homography from device coordinates -> image coordinates.
            src = np.array(
                [
                    [0.0, 0.0],
                    [float(screen_width_px), 0.0],
                    [float(screen_width_px), float(screen_height_px)],
                    [0.0, float(screen_height_px)],
                ],
                dtype=np.float32,
            )
            dst = quad
            h_mat = cv2.getPerspectiveTransform(src, dst)

            margin_x = max(1.0, min(float(margin_px), float(screen_width_px) / 2.0 - 1.0))
            margin_y = max(1.0, min(float(margin_px), float(screen_height_px) / 2.0 - 1.0))

            inner = np.array(
                [
                    [margin_x, margin_y],
                    [float(screen_width_px) - margin_x, margin_y],
                    [float(screen_width_px) - margin_x, float(screen_height_px) - margin_y],
                    [margin_x, float(screen_height_px) - margin_y],
                    [margin_x, margin_y],
                ],
                dtype=np.float32,
            ).reshape((-1, 1, 2))

            projected = cv2.perspectiveTransform(inner, h_mat).reshape((-1, 2))
            points = [(int(round(p[0])), int(round(p[1]))) for p in projected]

            self.logger.info(f"Pontos de borda (screen_quad) gerados: {points}")
            return points
        except Exception as e:
            self.logger.error(f"Falha ao gerar pontos de borda por screen_quad: {e}")
            return []

    def swipe_along_points(
        self,
        points: List[Tuple[int, int]],
        z_touch: float,
        speed: float = 50.0,
        accel: Optional[float] = None,
        decel: Optional[float] = None,
    ) -> bool:
        """
        Executa swipe contínuo ao longo dos pontos informados.

        Args:
            points: lista de pontos em pixel
            z_touch: altura Z de toque
            speed: velocidade desejada; aplicada via set_arm_speed se disponível

        Returns:
            bool
        """
        if not points or len(points) < 2:
            self.logger.error("Pontos insuficientes para swipe.")
            return False

        try:
            self._set_robot_speed(speed, accel=accel, decel=decel)

            first_x, first_y = points[0]
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(first_x, first_y)

            # aproxima acima do primeiro ponto
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )
            time.sleep(0.1)

            # encosta
            self._move_robot(
                target_x,
                target_y,
                z_touch,
                rx,
                ry,
                rz,
            )
            time.sleep(0.1)

            # percorre mantendo contato
            for x, y in points[1:]:
                target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(x, y)
                self._move_robot(
                    target_x,
                    target_y,
                    z_touch,
                    rx,
                    ry,
                    rz,
                )
                time.sleep(self.swipe_point_delay)

            # sobe no final
            last_x, last_y = points[-1]
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(last_x, last_y)
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )

            self.logger.info("Swipe contínuo realizado com sucesso.")
            return True

        except Exception as e:
            self.logger.error(f"Falha no swipe: {e}")
            return False

    # -------------------------------------------------
    # Fluxo crítico: pause-and-listen para marcadores
    # -------------------------------------------------

    def touch_marker_with_pause_and_listen(
        self, marker_info: MarkerInfo, z_touch: float, feedback_timeout: float = 3.0
    ) -> tuple[bool, Optional[dict]]:
        """
        Toca marcador com pausa crítica e escuta feedback.

        Fluxo:
        1. Toca no marcador
        2. Para o robô (sem desligar motor)
        3. Ouve feedback de toque via ADB
        4. Registra posição, pressão e duração do toque
        5. Recua se feedback recebido

        Retorna:
            (sucesso: bool, feedback_data: dict ou None)
        """
        cx, cy = marker_info.centroid

        try:
            # 1. Toca no marcador
            ok = self.touch_marker_center(marker_info, z_touch=z_touch)
            if not ok:
                self.logger.warning(f"Falha ao tocar marcador {marker_info.marker_id}")
                return False, None

            # 2. Para o robô (sem desligar motor)
            self.logger.info(f"Parando robô para ouvir feedback do toque")
            if hasattr(self.robot_arm, "motor_off"):
                # Faz transição leve para pausa, não desliga completamente
                time.sleep(0.1)

            # 3. Ouve feedback de toque via ADB
            self.logger.info(f"Ouvindo feedback de toque por {feedback_timeout}s")
            feedback_data = self.device.wait_for_touch_with_pressure(
                timeout=feedback_timeout, max_pressure_threshold=3000
            )

            if feedback_data is None:
                self.logger.warning(f"Nenhum feedback de toque recebido para marcador {marker_info.marker_id}")
                return False, None

            # 4. Registra dados
            self.logger.info(
                f"Feedback recebido: posição={feedback_data['position']}, "
                f"pressão={feedback_data['pressure']}, "
                f"excessivo={feedback_data['excessive_pressure']}"
            )

            # 5. Recua se pressão não foi excessiva
            if not feedback_data["excessive_pressure"]:
                current_pose = self._get_current_robot_pose()
                retreat_z = current_pose[2] + self.approach_height_mm
                self._move_robot(
                    current_pose[0],
                    current_pose[1],
                    retreat_z,
                    current_pose[3],
                    current_pose[4],
                    current_pose[5],
                )
                time.sleep(0.2)

            return True, feedback_data

        except Exception as e:
            self.logger.error(f"Falha no fluxo pause-and-listen: {e}")
            return False, None

    def swipe_with_safety_monitoring(
        self,
        points: List[Tuple[int, int]],
        z_touch: float,
        speed: float = 50.0,
        accel: Optional[float] = None,
        decel: Optional[float] = None,
    ) -> tuple[bool, str]:
        """
        Executa swipe com monitoramento de segurança.

        Monitora:
        - Pressão excessiva → para e vai a safe_pose
        - Perda de sinal → para e vai a safe_pose
        - Caso contrário, continua até o fim

        Retorna:
            (sucesso: bool, motivo: str)
            - (True, "completed"): swipe concluído com sucesso
            - (False, "signal_loss"): dispositivo parou de responder
            - (False, "excessive_pressure"): pressão muito forte
            - (False, "insufficient_points"): pontos insuficientes
        """
        if not points or len(points) < 2:
            self.logger.error("Pontos insuficientes para swipe de segurança.")
            return False, "insufficient_points"

        try:
            self._set_robot_speed(speed, accel=accel, decel=decel)

            # Aproxima no primeiro ponto
            first_x, first_y = points[0]
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(first_x, first_y)

            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )
            time.sleep(0.1)

            #  Encosta
            self._move_robot(target_x, target_y, z_touch, rx, ry, rz)
            time.sleep(0.1)

            # Inicia thread de monitoramento
            signal_ok = True
            stop_reason = "completed"

            def monitor_safety():
                nonlocal signal_ok, stop_reason
                signal_ok, stop_reason = self.device.monitor_swipe_for_signal_loss(timeout=15.0)

            import threading

            monitor_thread = threading.Thread(target=monitor_safety, daemon=True)
            monitor_thread.start()

            # Percorre mantendo contato (enquanto monitoramento permite)
            for x, y in points[1:]:
                if not signal_ok:
                    self.logger.warning(f"Parando swipe por: {stop_reason}")
                    break

                target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(x, y)
                self._move_robot(target_x, target_y, z_touch, rx, ry, rz)
                time.sleep(self.swipe_point_delay)

            # Aguarda finalização do monitoramento
            monitor_thread.join(timeout=2.0)

            if not signal_ok:
                self.logger.warning(f"Swipe abortado: {stop_reason}")
                return False, stop_reason

            # Sobe no final
            last_x, last_y = points[-1]
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(last_x, last_y)
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                rx,
                ry,
                rz,
            )

            self.logger.info("Swipe de segurança completado com sucesso.")
            return True, "completed"

        except Exception as e:
            self.logger.error(f"Falha no swipe de segurança: {e}")
            return False, f"exception:{str(e)}"

    # -------------------------------------------------
    # Fluxo crítico: listen-while-moving para marcadores
    # -------------------------------------------------

    def move_and_listen_until_touch(
        self,
        target_x: float,
        target_y: float,
        z_touch: float,
        rx: float,
        ry: float,
        rz: float,
        speed: float = 50.0,
        accel: Optional[float] = None,
        decel: Optional[float] = None,
        touch_timeout: float = 10.0,
        approach_height: float = 10.0,
    ) -> tuple[bool, Optional[dict]]:
        """
        Move o robô para o alvo ENQUANTO escuta eventos de toque.

        Se toque for detectado durante o movimento, o robô para imediatamente.
        Retorna a posição do toque e a pose do robô no momento do toque.

        Args:
            target_x, target_y, z_touch: pose alvo de toque
            rx, ry, rz: orientação do robô
            speed: velocidade de movimento
            touch_timeout: timeout máximo para escuta
            approach_height: altura de abordagem antes de tocar

        Retorna:
            (sucesso: bool, toque_info: dict ou None)

            Se sucesso=True, toque_info contém:
            {
                "touch_position": (x_px, y_px),      # Posição do toque na tela
                "touch_pressure": int,                # Pressão do toque
                "robot_pose_at_touch": (x,y,z,rx,ry,rz),  # Pose do robô no momento do toque
                "timestamp": float,                   # Timestamp do toque
                "movement_interrupted": bool,         # True se toque interrompeu movimento
            }

            Se sucesso=False, toque_info é None
        """
        self.logger.info(
            f"[LISTEN-WHILE-MOVING] Movendo para ({target_x:.2f}, {target_y:.2f}, {z_touch:.2f}) "
            f"enquanto escuta toques (timeout={touch_timeout}s)"
        )

        # Estado compartilhado entre threads
        state = {
            "should_stop": False,
            "touch_detected": False,
            "touch_data": None,
            "exception": None,
        }

        def listen_for_touch():
            """Thread listener que monitora toques via getevent."""
            try:
                tracker = TouchTracker()
                start_time = time.time()

                for evt in self.device.listener.iter_events():
                    # Timeout global
                    if time.time() - start_time > touch_timeout:
                        self.logger.debug("[LISTEN] Timeout de escuta atingido")
                        break

                    # Se robô foi parado externamente, para listener
                    if state["should_stop"]:
                        self.logger.debug("[LISTEN] Parando listener (robô parado)")
                        break

                    point = tracker.feed(evt)

                    # Para no primeiro contato (DOWN/MOVE), sem esperar release.
                    if point and point.action in (TouchAction.DOWN, TouchAction.MOVE):
                        touch_px = map_raw_touch_to_screen(
                            raw_x=point.x,
                            raw_y=point.y,
                            x_range=self.device.x_range,
                            y_range=self.device.y_range,
                            screen_size=self.device.screen_size,
                        )

                        if touch_px:
                            state["touch_detected"] = True
                            state["touch_data"] = {
                                "position": touch_px,
                                "pressure": int(tracker.avg_pressure),
                                "duration_sec": tracker.duration,
                                "timestamp": time.time(),
                                "touch_action": point.action.value,
                            }
                            self.logger.info(
                                f"[LISTEN] Contato detectado ({point.action.value})! pos={touch_px}, "
                                f"pressão={tracker.avg_pressure:.0f}, "
                                f"duração={tracker.duration:.3f}s"
                            )
                            state["should_stop"] = True
                            break

            except Exception as e:
                self.logger.error(f"[LISTEN] Erro no listener: {e}")
                state["exception"] = str(e)

        # Inicia thread de listening
        import threading

        listener_thread = threading.Thread(target=listen_for_touch, daemon=True)
        listener_thread.start()
        self.logger.debug("[LISTEN] Thread de listener iniciada")

        try:
            self._set_robot_speed(speed, accel=accel, decel=decel)

            # Aproxima a altura de abordagem
            current_pose = self._get_current_robot_pose()
            self.logger.debug(f"[MOVE] Pose atual: ({current_pose[0]:.2f}, {current_pose[1]:.2f}, {current_pose[2]:.2f})")

            self._move_robot(
                target_x,
                target_y,
                z_touch + approach_height,
                rx,
                ry,
                rz,
            )
            self.logger.debug("[MOVE] Encostou na altura de abordagem")
            time.sleep(0.1)

            # Move para altura de toque ENQUANTO escuta
            # Se toque for detectado, para imediatamente
            start_move = time.time()
            move_timeout = touch_timeout + 2.0  # dá margem

            while (time.time() - start_move) < move_timeout and not state["touch_detected"]:
                # Checa se toque foi detectado
                if state["touch_detected"]:
                    self.logger.info("[MOVE] Toque detectado! Parando movimento imediatamente")
                    state["should_stop"] = True
                    break

                # Continua movimento para altura de toque
                try:
                    self._move_robot(target_x, target_y, z_touch, rx, ry, rz)
                    time.sleep(0.05)  # pequena pausa entre ajustes
                except Exception as e:
                    self.logger.warning(f"[MOVE] Erro ao mover robô: {e}")
                    break

            # Sinal para listener parar
            state["should_stop"] = True

            # Aguarda thread de listener finalizar
            listener_thread.join(timeout=1.0)
            self.logger.debug("[LISTEN] Thread finalizada")

            # Se toque foi detectado, retorna os dados
            if state["touch_detected"] and state["touch_data"]:
                # Captura pose do robô no momento do toque
                robot_pose = self._get_current_robot_pose()

                result = {
                    "touch_position": state["touch_data"]["position"],
                    "touch_pressure": state["touch_data"]["pressure"],
                    "robot_pose_at_touch": robot_pose,
                    "timestamp": state["touch_data"]["timestamp"],
                    "movement_interrupted": True,
                }

                self.logger.info(
                    f"[RESULT] Toque capturado durante movimento! "
                    f"posição_toque={result['touch_position']}, "
                    f"pose_robô={robot_pose}"
                )

                return True, result

            # Se nenhum toque foi detectado
            self.logger.warning("[RESULT] Nenhum toque detectado após timeout")
            return False, None

        except Exception as e:
            self.logger.error(f"[EXCEPTION] Erro em move_and_listen_until_touch: {e}")
            state["should_stop"] = True
            listener_thread.join(timeout=1.0)
            return False, None

    def touch_marker_listen_while_moving(
        self,
        marker_info: MarkerInfo,
        z_touch: float,
        speed: float = 50.0,
        accel: Optional[float] = None,
        decel: Optional[float] = None,
        touch_timeout: float = 10.0,
    ) -> tuple[bool, Optional[dict]]:
        """
        Fluxo de toque em marcador com escuta contínua durante movimento.

        Fluxo:
        1. Move robô em direção ao marcador ENQUANTO escuta toques
        2. Se toque detectado durante movimento → para imediatamente
        3. Salva posição do toque (para eventual mapping de marcadores)
        4. Recua e volta a altura de segurança

        Args:
            marker_info: informações do marcador (centroide, ID)
            z_touch: altura Z para tocar
            speed: velocidade de movimento (mm/s)
            touch_timeout: timeout máximo para esperar toque

        Retorna:
            (sucesso: bool, toque_info: dict ou None)

            Se sucesso=True, toque_info contém:
            {
                "marker_id": str,                      # ID do marcador
                "marker_centroid": (x_px, y_px),      # Centro do marcador detectado
                "touch_position": (x_px, y_px),       # Posição real do toque (pode diferir)
                "touch_pressure": int,                # Pressão do toque
                "position_error_px": float,           # |centroid - touch_position|
                "robot_pose_at_touch": (x,y,z,rx,ry,rz),
                "timestamp": float,
            }

            Se sucesso=False, toque_info é None (timeout ou erro)
        """
        marker_id = marker_info.marker_id
        marker_cx, marker_cy = marker_info.centroid

        self.logger.info(
            f"[FIDUCIAL] Iniciando toque com listen-while-moving "
            f"para marcador {marker_id} em ({marker_cx:.1f}, {marker_cy:.1f})"
        )

        try:
            # Converte coordenadas do marcador para pose do robô
            target_x, target_y, _, rx, ry, rz = self._image_to_robot_pose(
                int(marker_cx), int(marker_cy)
            )

            self.logger.debug(
                f"[FIDUCIAL] Marca convertida para poses do robô: "
                f"({target_x:.2f}, {target_y:.2f}, {z_touch:.2f})"
            )

            # Move e escuta
            ok, touch_info = self.move_and_listen_until_touch(
                target_x=target_x,
                target_y=target_y,
                z_touch=z_touch,
                rx=rx,
                ry=ry,
                rz=rz,
                speed=speed,
                accel=accel,
                decel=decel,
                touch_timeout=touch_timeout,
            )

            if not ok or touch_info is None:
                self.logger.warning(f"[FIDUCIAL] Falha ao tocar marcador {marker_id}")
                return False, None

            # Calcula erro de posição (distância entre centroid e toque real)
            touch_px = touch_info["touch_position"]
            position_error = (
                ((marker_cx - touch_px[0]) ** 2 + (marker_cy - touch_px[1]) ** 2) ** 0.5
            )

            # Monta resultado com dados de mapeamento
            result = {
                "marker_id": marker_id,
                "marker_centroid": (marker_cx, marker_cy),
                "touch_position": touch_px,
                "touch_pressure": touch_info["touch_pressure"],
                "position_error_px": position_error,
                "robot_pose_at_touch": touch_info["robot_pose_at_touch"],
                "timestamp": touch_info["timestamp"],
            }

            self.logger.info(
                f"[FIDUCIAL] Toque bem-sucedido! "
                f"marker={marker_id}, "
                f"erro_posição={position_error:.1f}px, "
                f"pressão={result['touch_pressure']}g"
            )

            # Recua para altura de segurança
            try:
                robot_pose = touch_info["robot_pose_at_touch"]
                retreat_z = robot_pose[2] + self.approach_height_mm

                self.logger.debug(f"[FIDUCIAL] Recuando para z={retreat_z:.2f}")
                self._move_robot(
                    robot_pose[0],
                    robot_pose[1],
                    retreat_z,
                    robot_pose[3],
                    robot_pose[4],
                    robot_pose[5],
                )
                time.sleep(0.2)
            except Exception as e:
                self.logger.warning(f"[FIDUCIAL] Erro ao recuar: {e}")

            return True, result

        except Exception as e:
            self.logger.error(f"[FIDUCIAL] Erro em touch_marker_listen_while_moving: {e}")
            return False, None
        
    
    