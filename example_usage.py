"""
Exemplo de Uso: Alinhamento e Toque em Markers

Este script demonstra como usar a integração FOV/RTA para:
1. Detectar markers fiduciais na tela do celular
2. Alinhar o robô para uma posição perpendicular
3. Aproximar do alvo
4. Executar toques nos markers
"""

import logging

from drivers.device.mobile import Mobile
from drivers.robot.denso_aether import Denso
from drivers.vision.robot_camera import RobotCamera
from utils.coordinate_transform import (
    CameraCalibration,
    CoordinateTransform,
    RobotFrameConfig,
)
from utils.marker_touch_controller import MarkerTouchController


def setup_logging():
    """Configure logging para debug."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def initialize_components():
    """Inicializar componentes do sistema."""
    
    # Conectar ao robô
    print("Conectando ao robô Denso...")
    robot = Denso(
        workspace_name="YOUR_WORKSPACE",
        control_name="YOUR_CONTROL",
        options=""
    )
    
    if not robot.connect():
        raise RuntimeError("Falha ao conectar ao robô")
    
    robot.motor_on()
    print("Robô conectado e motor ligado")
    
    # Conectar ao dispositivo móvel
    print("Conectando ao dispositivo móvel...")
    device = Mobile()  # Assume que seus credentials estão configurados
    print("Dispositivo conectado")
    
    # Inicializar câmera do robô
    print("Inicializando câmera do robô...")
    camera = RobotCamera(camera_id=0, output_dir="log_images")
    print("Câmera inicializada")
    
    return robot, device, camera


def configure_coordinate_transform():
    """Configurar transformação de coordenadas específica para seu setup."""
    
    # Calibração de câmera (agora usando valores dinâmicos de config.py)
    import config
    camera_cal = CameraCalibration(
        focal_length_x=500.0,
        focal_length_y=500.0,
        principal_point_x=0.5,
        principal_point_y=0.5,
        marker_real_width_mm=config.MARKER_REAL_WIDTH_MM,  # Tamanho real do marker
        marker_real_height_mm=config.MARKER_REAL_HEIGHT_MM
    )
    
    # Configuração de mapeamento de eixos
    # Ajustar conforme a orientação de sua câmera e robô
    robot_config = RobotFrameConfig(
        image_x_to_robot_axis="X",  # Eixo X da imagem mapeia para X do robô
        image_y_to_robot_axis="Z",  # Eixo Y da imagem mapeia para Z do robô
        scale_x=0.1,
        scale_y=0.1
    )
    
    transform = CoordinateTransform(camera_cal, robot_config)
    return transform


def example_basic_touch():
    """Exemplo simples: tocar todos os markers detectados."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Inicializar componentes
        robot, device, camera = initialize_components()
        
        # Criar controlador
        controller = MarkerTouchController(
            robot_arm=robot,
            mobile_device=device,
            camera=camera
        )
        
        # Configurar distância de aproximação
        controller.approach_distance_mm = 200.0
        
        # Executar sequência completa
        logger.info("Iniciando sequência de toque em markers...")
        success = controller.run_full_sequence()
        
        if success:
            logger.info("Todos os markers foram tocados com sucesso!")
        else:
            logger.warning("Alguns markers falharam ao tocar")
        
    except Exception as e:
        logger.error(f"Erro: {e}")
    
    finally:
        # Limpar recursos
        try:
            robot.motor_off()
            robot.disconnect()
            camera.release()
            logger.info("Recursos liberados")
        except:
            pass


def example_targeted_markers():
    """Exemplo: tocar markers específicos por ID."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        robot, device, camera = initialize_components()
        controller = MarkerTouchController(
            robot_arm=robot,
            mobile_device=device,
            camera=camera
        )
        
        # Tocar apenas markers 0, 1, 2
        target_ids = [0, 1, 2]
        logger.info(f"Tocando markers alvo: {target_ids}")
        
        success = controller.run_full_sequence(target_marker_ids=target_ids)
        
        if success:
            logger.info(f"Markers {target_ids} tocados com sucesso")
        else:
            logger.warning("Falha ao tocar markers alvo")
        
    except Exception as e:
        logger.error(f"Erro: {e}")
    
    finally:
        try:
            robot.motor_off()
            robot.disconnect()
            camera.release()
        except:
            pass


def example_manual_alignment():
    """Exemplo: Controle manual de cada etapa de alinhamento."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        robot, device, camera = initialize_components()
        
        # Detectar markers
        from drivers.alignment.marker_detector import MarkerDetector
        detector = MarkerDetector()
        
        logger.info("Detectando markers...")
        frame = camera.capture_frame()
        
        ids, corners = detector.detect_markers(frame)
        if ids is None or len(ids) == 0:
            logger.error("Nenhum marker detectado!")
            return
        
        logger.info(f"Detectados {len(ids)} markers")
        
        # Alinhamento de rotação (RZ)
        from drivers.alignment.rotation_alignment import RotationAlignment
        rot_align = RotationAlignment(robot, camera, detector)
        
        logger.info("Executando alinhamento de rotação...")
        if not rot_align.run_alignment_loop(max_iterations=10):
            logger.error("Falha no alinhamento de rotação")
            return
        
        # Alinhamento XYZ
        from drivers.alignment.auto_alignment import AutoAlignment
        auto_align = AutoAlignment(robot, camera, detector)
        
        logger.info("Calibrando distância...")
        if not auto_align.calibrate_distance():
            logger.error("Falha na calibração de distância")
            return
        
        logger.info("Centralizando markers...")
        if not auto_align.run_centering_loop(max_iterations=15):
            logger.warning("Falha na centralização (continuando)")
        
        logger.info("Aproximando ao alvo...")
        if not auto_align.run_depth_loop(target_distance_mm=200.0, max_iterations=15):
            logger.warning("Falha na aproximação (continuando)")
        
        # Tocar markers
        logger.info("Tocando markers...")
        from utils.marker_touch_controller import MarkerTouchController
        controller = MarkerTouchController(robot, device, camera, auto_align, rot_align)
        
        markers = controller.detect_markers_in_screen()
        if markers:
            for marker in markers:
                logger.info(f"Tocando marker ID {marker.marker_id}...")
                controller.touch_marker_on_screen(marker)
        
        logger.info("Sequência manual completada")
        
    except Exception as e:
        logger.error(f"Erro: {e}")
    
    finally:
        try:
            robot.motor_off()
            robot.disconnect()
            camera.release()
        except:
            pass


def example_inspect_markers():
    """Exemplo: Inspecionar propriedades dos markers detectados."""
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        camera = RobotCamera()
        detector = MarkerDetector()
        
        logger.info("Capturando frame...")
        frame = camera.capture_frame()
        
        if frame is None:
            logger.error("Falha ao capturar frame")
            return
        
        # Detectar e processar
        ids, corners = detector.detect_markers(frame)
        if ids is None:
            logger.warning("Nenhum marker detectado")
            return
        
        corners = detector.refine_corners(frame, corners)
        
        logger.info(f"Detectados {len(ids)} markers:")
        logger.info("-" * 70)
        
        for i, marker_id in enumerate(ids):
            info = detector.get_marker_info(int(marker_id[0]), corners[i])
            
            logger.info(f"Marker {info.marker_id}:")
            logger.info(f"  Centroid: ({info.centroid[0]:.1f}, {info.centroid[1]:.1f})")
            logger.info(f"  Area: {info.area:.1f} px²")
            logger.info(f"  Perimeter: {info.perimeter:.1f} px")
            logger.info(f"  Dimensions: {info.width_px:.1f}x{info.height_px:.1f} px")
            logger.info("")
        
        # Dividir por lado
        marker_infos = [detector.get_marker_info(int(ids[i][0]), corners[i]) 
                       for i in range(len(ids))]
        left, right = detector.split_markers_by_image_center(frame, marker_infos)
        
        logger.info(f"Distribuição: {len(left)} esquerda, {len(right)} direita")
        
    except Exception as e:
        logger.error(f"Erro: {e}")
    
    finally:
        camera.release()


if __name__ == "__main__":
    import sys

    # Escolher exemplo
    if len(sys.argv) > 1:
        example = sys.argv[1]
    else:
        example = "inspect"  # default
    
    if example == "basic":
        example_basic_touch()
    elif example == "targeted":
        example_targeted_markers()
    elif example == "manual":
        example_manual_alignment()
    elif example == "inspect":
        example_inspect_markers()
    else:
        print("Uso: python example_usage.py [basic|targeted|manual|inspect]")
        print("  basic    - Tocar todos os markers (sequência completa)")
        print("  targeted - Tocar markers específicos")
        print("  manual   - Controle manual de cada etapa")
        print("  inspect  - Inspecionar markers detectados")
