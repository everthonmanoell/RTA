import logging
import time
from typing import List, Optional, Tuple

from aether_rdk.datatypes import Pose

from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.alignment.rotation_alignment import RotationAlignment
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

    def _set_robot_speed(self, speed: float) -> None:
        """
        Ajusta a velocidade do braço, se a API do robô suportar.
        """
        if hasattr(self.robot_arm, "set_arm_speed"):
            try:
                self.robot_arm.set_arm_speed(speed, speed, speed)
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
        pose = Pose(x=x, y=y, z=z, rx=rx, ry=ry, rz=rz)

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

    def get_grid_border_points(self, margin_px: int = 30) -> List[Tuple[int, int]]:
        """
        Gera pontos de borda para um swipe retangular.

        Por enquanto, usa as bordas da imagem capturada.
        Isso serve como primeira versão operacional.
        """
        try:
            image_height, image_width = self._capture_frame_shape()

            points = [
                (margin_px, margin_px),
                (image_width - margin_px, margin_px),
                (image_width - margin_px, image_height - margin_px),
                (margin_px, image_height - margin_px),
                (margin_px, margin_px),
            ]

            self.logger.info(f"Pontos de borda gerados: {points}")
            return points

        except Exception as e:
            self.logger.error(f"Falha ao gerar pontos de borda: {e}")
            return []

    def swipe_along_points(
        self,
        points: List[Tuple[int, int]],
        z_touch: float,
        speed: float = 50.0,
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
            self._set_robot_speed(speed)

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