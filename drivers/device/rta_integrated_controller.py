"""
RTA_IntegratedController: Orquestrador completo do sistema RTA.

Integra:
- RTA_app (app Android com markers)
- Câmera do robô
- Alinhamento visual (XYZ + RZ)
- Toque em markers
- Feedback visual
"""

import logging
import time
from typing import List, Optional

import numpy as np

from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.marker_detector import MarkerDetector, MarkerInfo
from drivers.alignment.rotation_alignment import RotationAlignment
from drivers.device.app_manager import DeviceAppManager
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import CoordinateTransform


class RTAIntegratedController:
    """
    Orquestrador completo do sistema RTA.
    
    Fluxo:
    1. Iniciar RTA_app com configuração
    2. Detectar markers via câmera do robô
    3. Alinhar robô (RZ + XYZ)
    4. Tocar sequencialmente em cada marker
    5. Verificar feedback visual (marker desaparece)
    6. Repetir ou avançar
    """
    
    def __init__(self, robot_arm, device_interface, camera: RobotCamera,
                 app_manager: Optional[DeviceAppManager] = None,
                 auto_align: Optional[AutoAlignment] = None,
                 rot_align: Optional[RotationAlignment] = None,
                 detector: Optional[MarkerDetector] = None):
        """
        Initialize RTAIntegratedController.
        
        Args:
            robot_arm: Interface com robô Denso.
            device_interface: Interface com dispositivo (ADB).
            camera (RobotCamera): Câmera acoplada ao robô.
            app_manager (Optional[DeviceAppManager]): Gerenciador do app.
            auto_align (Optional[AutoAlignment]): Controlador XYZ.
            rot_align (Optional[RotationAlignment]): Controlador RZ.
            detector (Optional[MarkerDetector]): Detector de markers.
        """
        self.robot_arm = robot_arm
        self.device = device_interface
        self.camera = camera
        
        self.app_manager = app_manager or DeviceAppManager(device_interface)
        self.detector = detector or MarkerDetector()
        self.auto_align = auto_align or AutoAlignment(robot_arm, camera, self.detector)
        self.rot_align = rot_align or RotationAlignment(robot_arm, camera, self.detector)
        
        self.logger = logging.getLogger(__name__)
        
        # Configuration
        self.approach_distance_mm = 150.0
        self.touch_delay = 0.5
        self.verification_delay = 1.0
        self.max_retries_per_marker = 3
        
        # State tracking
        self.touched_markers = set()
        self.current_session_id = None
    
    def setup_session(self, device_type: str = "flat", install_if_needed: bool = False) -> bool:
        """
        Configura uma nova sessão.
        
        Args:
            device_type (str): Tipo de dispositivo (flat, foldable, etc.)
            install_if_needed (bool): Instalar app se não estiver.
            
        Returns:
            bool: True se sessão configurada com sucesso.
        """
        self.logger.info(f"Configurando sessão com device_type='{device_type}'")
        
        # Verificar/instalar app
        if not self.app_manager.is_app_running():
            if install_if_needed:
                self.logger.info("App não instalado, instalando...")
                if not self.app_manager.install_app():
                    self.logger.error("Falha ao instalar app")
                    return False
            else:
                self.logger.error("App não está em execução")
                return False
        
        # Parar app anterior se estava rodando
        self.app_manager.stop_app()
        time.sleep(1)
        
        # Iniciar nova sessão
        if not self.app_manager.start_app(device_type):
            self.logger.error("Falha ao iniciar app")
            return False
        
        # Aguardar app ficar pronto
        if not self.app_manager.wait_for_app_ready():
            self.logger.warning("App pode não estar totalmente pronto")
        
        self.current_session_id = f"{device_type}_{int(time.time())}"
        self.touched_markers = set()
        
        self.logger.info(f"Sessão configurada: {self.current_session_id}")
        return True
    
    def detect_markers_from_app_screen(self) -> Optional[List[MarkerInfo]]:
        """
        Detecta markers na tela do app via câmera do robô.
        
        Returns:
            Optional[List[MarkerInfo]]: Lista de markers detectados.
        """
        frame = self.camera.capture_frame()
        if frame is None:
            self.logger.error("Falha ao capturar frame")
            return None
        
        ids, corners = self.detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            self.logger.warning("Nenhum marker detectado")
            return None
        
        corners = self.detector.refine_corners(frame, corners)
        marker_infos = [
            self.detector.get_marker_info(int(ids[i][0]), corners[i])
            for i in range(len(ids))
        ]
        
        self.logger.info(f"Detectados {len(marker_infos)} markers")
        return marker_infos
    
    def perform_full_alignment(self) -> bool:
        """
        Realiza alinhamento completo (RZ + XYZ).
        
        Returns:
            bool: True se alinhamento bem-sucedido.
        """
        self.logger.info("Iniciando alinhamento completo")
        
        # 1. Alinhamento de rotação (RZ)
        self.logger.info("Etapa 1: Alinhamento de rotação")
        if not self.rot_align.run_alignment_loop(max_iterations=10):
            self.logger.error("Falha no alinhamento RZ")
            return False
        
        time.sleep(1)
        
        # 2. Calibração de distância (se necessário)
        if self.auto_align.reference_marker_area is None:
            self.logger.info("Etapa 2a: Calibração de distância")
            if not self.auto_align.calibrate_distance():
                self.logger.error("Falha na calibração")
                return False
        
        # 3. Alinhamento XYZ
        self.logger.info("Etapa 2b: Alinhamento XYZ")
        if not self.auto_align.approach_marker(self.approach_distance_mm):
            self.logger.error("Falha no alinhamento XYZ")
            return False
        
        self.logger.info("Alinhamento completo bem-sucedido")
        return True
    
    def verify_marker_touched(self, marker_id: int, retries: int = 2) -> bool:
        """
        Verifica se um marker foi efetivamente tocado (visual feedback).
        
        Captura nova imagem e verifica se o marker desapareceu.
        
        Args:
            marker_id (int): ID do marker tocado.
            retries (int): Número de tentativas de verificação.
            
        Returns:
            bool: True se marker desapareceu (foi tocado).
        """
        for attempt in range(retries):
            time.sleep(self.verification_delay)
            
            # Capturar nova imagem
            frame = self.camera.capture_frame()
            if frame is None:
                continue
            
            # Detectar markers
            ids, _ = self.detector.detect_markers(frame)
            if ids is None:
                return True  # Sem markers pode significar sucesso
            
            # Verificar se marker foi tocado
            id_list = [int(id_val[0]) for id_val in ids]
            if marker_id not in id_list:
                self.logger.info(f"Marker {marker_id} confirmado tocado (visual feedback)")
                return True
            
            if attempt < retries - 1:
                self.logger.debug(f"Verificação: marker ainda visível, tentativa {attempt + 1}/{retries}")
        
        self.logger.warning(f"Marker {marker_id} ainda visível após toque")
        return False
    
    def touch_marker_sequence(self, markers: List[MarkerInfo]) -> dict:
        """
        Toca markers sequencialmente com feedback visual.
        
        Args:
            markers (List[MarkerInfo]): Markers a tocar.
            
        Returns:
            dict: { marker_id: (success, details) }
        """
        results = {}
        
        for i, marker in enumerate(markers):
            self.logger.info(f"Tocando marker {i + 1}/{len(markers)} (ID: {marker.marker_id})")
            
            # Pular se já tocado
            if marker.marker_id in self.touched_markers:
                self.logger.debug(f"Marker {marker.marker_id} já foi tocado, pulando")
                results[marker.marker_id] = (True, "already_touched")
                continue
            
            success = False
            retries = 0
            
            # Tentar tocar com retries
            while retries < self.max_retries_per_marker:
                # Toque
                touch_x, touch_y = int(marker.centroid[0]), int(marker.centroid[1])
                try:
                    self.device.touch(touch_x, touch_y)
                    self.logger.info(f"Toque executado em ({touch_x}, {touch_y})")
                except Exception as e:
                    self.logger.error(f"Erro ao tocar: {e}")
                    retries += 1
                    continue
                
                time.sleep(self.touch_delay)
                
                # Verificar feedback visual
                if self.verify_marker_touched(marker.marker_id):
                    self.touched_markers.add(marker.marker_id)
                    results[marker.marker_id] = (True, "verified")
                    success = True
                    break
                
                retries += 1
                self.logger.warning(f"Toque não confirmado, tentativa {retries}/{self.max_retries_per_marker}")
            
            if not success:
                results[marker.marker_id] = (False, f"failed_after_{retries}_retries")
                self.logger.error(f"Falha ao tocar marker {marker.marker_id}")
        
        return results
    
    def run_complete_session(self, device_type: str = "flat") -> dict:
        """
        Executa sessão completa: setup → detect → align → touch.
        
        Args:
            device_type (str): Tipo de dispositivo.
            
        Returns:
            dict: Resultado da sessão { 'session_id': ..., 'markers_touched': {...}, ... }
        """
        self.logger.info(f"Iniciando sessão completa com device_type='{device_type}'")
        
        result = {
            "session_id": None,
            "status": "failed",
            "device_type": device_type,
            "markers_expected": 0,
            "markers_detected": 0,
            "markers_touched": {},
            "errors": []
        }
        
        try:
            # 1. Setup
            if not self.setup_session(device_type, install_if_needed=True):
                result["errors"].append("Failed to setup session")
                return result
            
            result["session_id"] = self.current_session_id
            result["markers_expected"] = self.app_manager.get_expected_marker_count()
            
            # 2. Detectar markers
            markers = self.detect_markers_from_app_screen()
            if not markers:
                result["errors"].append("No markers detected")
                return result
            
            result["markers_detected"] = len(markers)
            
            # 3. Alinhamento
            if not self.perform_full_alignment():
                result["errors"].append("Alignment failed")
                return result
            
            # 4. Tocar markers
            touch_results = self.touch_marker_sequence(markers)
            result["markers_touched"] = touch_results
            
            # 5. Validação
            successful_touches = sum(1 for success, _ in touch_results.values() if success)
            if successful_touches == len(markers):
                result["status"] = "success"
                self.logger.info(f"Sessão completada com sucesso: {successful_touches}/{len(markers)}")
            else:
                result["status"] = "partial"
                self.logger.warning(f"Sessão parcial: {successful_touches}/{len(markers)} markers tocados")
        
        except Exception as e:
            self.logger.error(f"Erro na sessão: {e}")
            result["errors"].append(str(e))
        
        finally:
            # Limpeza
            try:
                self.app_manager.stop_app()
            except:
                pass
        
        return result
    
    def cleanup(self):
        """Limpa recursos."""
        self.logger.info("Limpando recursos")
        try:
            self.app_manager.stop_app()
            self.camera.release()
            self.logger.info("Recursos liberados")
        except Exception as e:
            self.logger.error(f"Erro na limpeza: {e}")
