import logging
import time
from typing import List, Optional, Tuple

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
    - tocar em pixels específicos (ex.: botão vermelho)
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

        # alturas e tempos operacionais
        self.approach_height_mm = 10.0
        self.touch_delay_before_lift = 0.2
        self.touch_delay_after_touch = 0.3

    # -------------------------------------------------
    # Utilidades internas
    # -------------------------------------------------

    def _capture_frame_shape(self) -> Tuple[int, int]:
        """
        Captura um frame e retorna (height, width).
        """
        frame = self.camera.capture_frame()
        if frame is None:
            raise RuntimeError("Não foi possível capturar frame da câmera.")
        height, width = frame.shape[:2]
        return height, width

    def _get_current_robot_pose(self) -> Tuple[float, float, float]:
        """
        Obtém a pose atual do robô.

        Ajuste este método se a sua classe Denso usar outro nome de método
        para retornar posição.
        """
        if hasattr(self.robot_arm, "get_position"):
            pose = self.robot_arm.get_position()
            if len(pose) >= 3:
                return pose[0], pose[1], pose[2]

        raise AttributeError(
            "robot_arm não possui método compatível para obter posição atual "
            "(esperado: get_position)."
        )

    def _move_robot(self, x: float, y: float, z: float, speed: Optional[float] = None) -> None:
        """
        Wrapper para movimento do robô.

        Ajuste este método se a sua classe Denso usar outro nome/assinatura
        para movimentação.
        """
        if hasattr(self.robot_arm, "move_to"):
            if speed is not None:
                self.robot_arm.move_to(x, y, z, speed=speed)
            else:
                self.robot_arm.move_to(x, y, z)
            return

        raise AttributeError(
            "robot_arm não possui método compatível para mover "
            "(esperado: move_to)."
        )

    def _image_to_robot_pose(self, x_px: int, y_px: int) -> Tuple[float, float, float]:
        """
        Converte um ponto da imagem para pose alvo do robô usando o
        CoordinateTransform real do seu projeto.

        Fluxo:
        1. ponto da imagem
        2. deslocamento no frame da câmera
        3. aplicação no frame atual do robô
        """
        image_height, image_width = self._capture_frame_shape()

        offset_x_mm, offset_y_mm = self.transform.image_to_robot_2d(
            image_x=x_px,
            image_y=y_px,
            image_width=image_width,
            image_height=image_height,
        )

        current_robot_x, current_robot_y, current_robot_z = self._get_current_robot_pose()

        target_x, target_y, target_z = self.transform.apply_robot_transform(
            camera_frame_x=offset_x_mm,
            camera_frame_y=offset_y_mm,
            camera_frame_z=0.0,
            current_robot_x=current_robot_x,
            current_robot_y=current_robot_y,
            current_robot_z=current_robot_z,
        )

        return target_x, target_y, target_z

    # -------------------------------------------------
    # Toques
    # -------------------------------------------------

    def touch_pixel(self, x: int, y: int, z_touch: float) -> bool:
        """
        Toca em um pixel específico da imagem/tela.

        Args:
            x: coordenada X em pixel
            y: coordenada Y em pixel
            z_touch: altura Z de toque

        Returns:
            bool
        """
        try:
            target_x, target_y, _ = self._image_to_robot_pose(x, y)

            self.logger.info(
                f"Tocando pixel ({x}, {y}) -> robô ({target_x:.2f}, {target_y:.2f}, {z_touch:.2f})"
            )

            # aproxima
            self._move_robot(target_x, target_y, z_touch + self.approach_height_mm)
            time.sleep(0.1)

            # toca
            self._move_robot(target_x, target_y, z_touch)
            time.sleep(self.touch_delay_before_lift)

            # sobe
            self._move_robot(target_x, target_y, z_touch + self.approach_height_mm)
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
        Isso é útil como primeira versão operacional.

        Args:
            margin_px: margem interna para evitar tocar exatamente no limite

        Returns:
            Lista de pontos (x, y)
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
            speed: velocidade de movimento

        Returns:
            bool
        """
        if not points or len(points) < 2:
            self.logger.error("Pontos insuficientes para swipe.")
            return False

        try:
            first_x, first_y = points[0]
            target_x, target_y, _ = self._image_to_robot_pose(first_x, first_y)

            # aproxima
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                speed=speed,
            )
            time.sleep(0.1)

            # encosta
            self._move_robot(
                target_x,
                target_y,
                z_touch,
                speed=speed,
            )
            time.sleep(0.1)

            # percorre
            for x, y in points[1:]:
                target_x, target_y, _ = self._image_to_robot_pose(x, y)
                self._move_robot(target_x, target_y, z_touch, speed=speed)
                time.sleep(0.05)

            # sobe no final
            last_x, last_y = points[-1]
            target_x, target_y, _ = self._image_to_robot_pose(last_x, last_y)
            self._move_robot(
                target_x,
                target_y,
                z_touch + self.approach_height_mm,
                speed=speed,
            )

            self.logger.info("Swipe contínuo realizado com sucesso.")
            return True

        except Exception as e:
            self.logger.error(f"Falha no swipe: {e}")
            return False