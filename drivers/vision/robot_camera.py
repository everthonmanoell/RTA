"""
RobotCamera: Interface for the camera mounted on the robot arm.

This module provides an abstraction layer for capturing images from the robot's
camera, separate from the mobile device camera. It handles image acquisition,
preprocessing, and caching.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, Tuple
from drivers.alignment.marker_detector import MarkerDetector

import cv2
import numpy as np

import config
from pathlib import Path

class RobotCamera:
    """
    Manages image acquisition from the robot-mounted camera.
    
    This camera provides a fixed perspective for fiducial marker detection
    and visual alignment, independent of mobile device screen orientation.
    """
    
    def __init__(self, camera_id: int = 0, output_dir: str = "log_images", show_preview: bool = False):
        """
        Initialize RobotCamera with OpenCV camera source.
        
        Args:
            camera_id (int): OpenCV camera index. Default 0 for primary camera.
            output_dir (str): Directory for storing captured images.
            show_preview (bool): If True, show the live camera frame in an OpenCV window.
        """
        self.camera_id = camera_id
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.cap = None
        self.logger = logging.getLogger(__name__)
        self.show_preview = bool(show_preview)
        self.preview_window_name = "RTA Camera Preview"
        self.preview_overlay_fn: Optional[Callable[[np.ndarray], np.ndarray]] = None
        
        # Initialize camera on first use
        self._camera_opened = False
    
    def _ensure_camera_open(self) -> bool:
        """
        Ensure camera is open and ready to capture.
        
        Returns:
            bool: True if camera is ready, False otherwise.
        """
        if not self._camera_opened:
            self.cap = cv2.VideoCapture(self.camera_id)
            if not self.cap.isOpened():
                self.logger.error(f"Failed to open camera {self.camera_id}")
                return False
            self._camera_opened = True
        return True
    
    def capture_frame(self) -> Optional[np.ndarray]:
        """
        Capture a single frame from the robot's camera.
        
        Returns:
            Optional[np.ndarray]: Frame as BGR image, or None if capture failed.
        """
        if not self._ensure_camera_open():
            return None
        
        ret, frame = self.cap.read()
        if not ret:
            self.logger.error("Failed to capture frame")
            return None

        if self.show_preview:
            try:
                preview_frame = frame
                if self.preview_overlay_fn is not None:
                    preview_frame = self.preview_overlay_fn(frame.copy())
                cv2.imshow(self.preview_window_name, preview_frame)
                cv2.waitKey(1)
            except Exception as exc:
                self.logger.debug("Camera preview unavailable: %s", exc)
        
        return frame
    
    def capture_and_save(self, filename: str) -> Optional[np.ndarray]:
        """
        Capture frame and save to disk with timestamp.
        
        Args:
            filename (str): Image filename (without path).
            
        Returns:
            Optional[np.ndarray]: Captured frame, or None if failed.
        """
        frame = self.capture_frame()
        if frame is None:
            return None
        
        filepath = self.output_dir / filename
        success = cv2.imwrite(str(filepath), frame)
        if success:
            self.logger.info(f"Image saved: {filepath}")
        else:
            self.logger.error(f"Failed to save image: {filepath}")
        
        return frame

    
    def get_frame_shape(self) -> Optional[tuple]:
        """
        Get frame dimensions (height, width, channels).
        
        Returns:
            Optional[tuple]: (height, width, channels) or None if failed.
        """
        frame = self.capture_frame()
        if frame is None:
            return None
        return frame.shape
    
    def set_camera_property(self, prop_id: int, value: float) -> bool:
        """
        Set OpenCV camera property (brightness, contrast, etc).
        
        Args:
            prop_id (int): OpenCV camera property ID (e.g., cv2.CAP_PROP_BRIGHTNESS).
            value (float): Property value.
            
        Returns:
            bool: True if successful.
        """
        if not self._ensure_camera_open():
            return False
        
        success = self.cap.set(prop_id, value)
        if success:
            self.logger.info(f"Set camera property {prop_id} = {value}")
        else:
            self.logger.error(f"Failed to set camera property {prop_id}")
        return success
    
    def release(self):
        """Release camera resources."""
        if self.cap is not None:
            self.cap.release()
            self._camera_opened = False
            if self.show_preview:
                try:
                    cv2.destroyWindow(self.preview_window_name)
                except Exception:
                    pass
            self.logger.info("Camera released")

    def display_image(self, image_np: np.ndarray, window_name: str = "Image"):
        """
        Display an image in an OpenCV window.
        
        Args:
            image (np.ndarray): Image to display (BGR format).
            window_name (str): Name of the display window.
        """
        try:
            cv2.imshow(window_name, image_np)
            cv2.waitKey(0)
            cv2.destroyWindow(window_name)
        except Exception as exc:
            self.logger.debug("Image display unavailable: %s", exc)
        
    def image_with_middle_point(self, image_np: np.ndarray) -> dict[str, object]:
        """
        Draw a red point in the middle of the image for debugging.
        
        Args:
            image_np (np.ndarray): Input image (BGR format).
        returns:
            dict: Dictionary containing the modified image and center coordinates.
        """
        height, width = image_np.shape[:2]
        center_x, center_y = width // 2, height // 2
        cv2.circle(image_np, (center_x, center_y), radius=10, color=(0, 0, 255), thickness=-1)
        return dict(image_np=image_np, center=(center_x, center_y))

    def save_frame_with_timestamp(self, frame: np.ndarray,  prefix: str = "capture", filename = str ) -> Optional[np.ndarray]:
        """
        Save frame with a timestamped filename.
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{prefix}_{timestamp}.jpg"
        filepath = self.output_dir / filename
        success = cv2.imwrite(str(filepath), frame)
        if success:
            self.logger.info(f"Image saved: {filepath}")
            return frame
        else:
            self.logger.error(f"Failed to save image: {filepath}")
            return None
        

    def center_point(self, image_np: np.ndarray) -> Tuple[int, int]:
        """
        Get the center point coordinates of the image.
        
        Args:
            image_np (np.ndarray): Input image (BGR format).
        
        Returns:
            Tuple[int, int]: (center_x, center_y) coordinates of the image center.
        """
        height, width = image_np.shape[:2]
        center_x, center_y = width // 2, height // 2
        return center_x, center_y
        
    
                
    

    def __del__(self):
        """Ensure camera is released on object destruction."""
        self.release()


if __name__ == "__main__":
    aruco_width_real_mm = 15
    aruco_height_real_mm = 15

    camera = RobotCamera(show_preview=True)
    md = MarkerDetector()

    image_path = Path("log_images/test_capture_0.jpg")
    frame = cv2.imread(str(image_path))
    target_id = 1

    # 1. Detectar o aruco com id 1
    id_found, corners = md.detect_single_marker_by_id(frame, target_id)

    # print(f"corners from id_target {target_id}: {corners}")

    if id_found is not None:
        # 2. Pegar informações (Largura, Altura, Centroide)
        marker_info = md.get_marker_info(target_id, corners)

        width_aruco_pixel = marker_info.width_px
        height_aruco_pixel = marker_info.height_px

        # 3. Escala mm/px (Quanto cada pixel vale em milímetros)
        scale_x = aruco_width_real_mm / width_aruco_pixel
        scale_y = aruco_height_real_mm / height_aruco_pixel

        # 4. Centroides e Erro
        center_x_img, center_y_img = camera.center_point(frame)
        center_aruco_x, center_aruco_y = marker_info.centroid

        error_px_x = center_aruco_x - center_x_img
        error_px_y = center_aruco_y - center_y_img

        # 5. Converter erro para mm
        error_mm_x = error_px_x * scale_x
        error_mm_y = error_px_y * scale_y

        # ... (seu código anterior até o cálculo de erro_mm_y) ...

        print(f"Erro X: {error_mm_x:.2f} mm")
        print(f"Erro Y: {error_mm_y:.2f} mm")

        # 1. Bolinha no Centro da Imagem (Azul)
        # Coordenadas: (x, y) como inteiros
        centro_imagem = (int(center_x_img), int(center_y_img))
        raio = 5
        cor_azul = (255, 0, 0) # BGR
        espessura_preenchido = -1 # -1 preenche o círculo

        cv2.circle(frame, centro_imagem, raio, cor_azul, espessura_preenchido)

        # 2. Bolinha no Centro do ArUco (Vermelha)
        # Coordenadas: (x, y) como inteiros
        centro_aruco = (int(center_aruco_x), int(center_aruco_y))
        raio = 5
        cor_vermelha = (0, 0, 255) # BGR
        
        cv2.circle(frame, centro_aruco, raio, cor_vermelha, espessura_preenchido)

        # Opcional: Desenhar uma linha unindo os dois centros (Ciano)
        cv2.line(frame, centro_imagem, centro_aruco, (255, 255, 0), 2)


        pos_x_texto = int(center_aruco_x) + 15 
        pos_y_texto = int(center_aruco_y) - 15

        cv2.putText(
            frame,
            f"Erro: X={error_mm_x:.1f} Y={error_mm_y:.1f} mm",
            (pos_x_texto, pos_y_texto),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 255, 0),
            2
        )
        
        # ... (resto do seu código) ...

        # 2. Texto do Centroide da Imagem
        cv2.putText(
            frame,
            f'Image Center: ({int(center_x_img)}, {int(center_y_img)})',
            (int(center_x_img) + 10, int(center_y_img) - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (255, 0, 0),
            2
        )

        # 3. Texto do Centroide do Marcador
        cv2.putText(
            frame,
            f'Marker: ({int(center_aruco_x)}, {int(center_aruco_y)})',
            (int(center_aruco_x) + 10, int(center_aruco_y) + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.5,
            (0, 0, 255),
            2
        )

        camera.display_image(frame, window_name="Marker Detection Result")


    else:
        print(f"Marcador {target_id} não encontrado!")



    

