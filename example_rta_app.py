"""
EXEMPLO PRÁTICO: Usando RTA com RTA_app

Demonstra o fluxo completo de toque em markers
considerando a aplicação Android.
"""

import logging
import sys
from datetime import datetime
from typing import Optional


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def example_complete_workflow(device_type: str = "flat", verbose: bool = False):
    """
    Exemplo completo: Iniciar app, detectar, alinhar, tocar markers.
    
    Args:
        device_type (str): "flat" (4 markers) ou "foldable" (8 markers)
        verbose (bool): Ativar debug logging
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    # Imports
    from drivers.device.mobile import Mobile
    from drivers.device.rta_integrated_controller import RTAIntegratedController
    from drivers.robot.denso_aether import Denso
    from drivers.vision.robot_camera import RobotCamera
    
    logger.info(f"Iniciando exemplo: device_type='{device_type}'")
    
    try:
        # ====================================================================
        # ETAPA 1: INICIALIZAR COMPONENTES
        # ====================================================================
        logger.info("Etapa 1: Inicializando componentes...")
        
        # Robô
        logger.debug("Conectando ao robô Denso...")
        robot = Denso(
            workspace_name="YOUR_WORKSPACE",
            control_name="YOUR_CONTROL",
            options=""
        )
        
        if not robot.connect():
            raise RuntimeError("Falha ao conectar ao robô")
        
        robot.motor_on()
        logger.info("✓ Robô conectado e motor ligado")
        
        # Dispositivo mobile
        logger.debug("Conectando ao dispositivo mobile...")
        device = Mobile()
        logger.info("✓ Dispositivo mobile conectado")
        
        # Câmera do robô
        logger.debug("Inicializando câmera do robô...")
        camera = RobotCamera(camera_id=0, output_dir="log_images")
        logger.info("✓ Câmera do robô inicializada")
        
        # Controlador integrado
        logger.debug("Criando controlador integrado...")
        controller = RTAIntegratedController(robot, device, camera)
        
        # Configurar parâmetros (opcional)
        controller.approach_distance_mm = 150.0
        controller.touch_delay = 0.5
        controller.max_retries_per_marker = 3
        
        logger.info("✓ Controlador integrado pronto")
        logger.info("")
        
        # ====================================================================
        # ETAPA 2: CONFIGURAR SESSÃO COM RTA_APP
        # ====================================================================
        logger.info("Etapa 2: Configurando sessão RTA_app...")
        
        success = controller.setup_session(
            device_type=device_type,
            install_if_needed=True
        )
        
        if not success:
            raise RuntimeError("Falha ao configurar sessão RTA_app")
        
        logger.info(f"✓ Sessão configurada com device_type='{device_type}'")
        logger.info(f"  Esperado: {controller.app_manager.get_expected_marker_count()} markers")
        logger.info("")
        
        # ====================================================================
        # ETAPA 3: DETECTAR MARKERS
        # ====================================================================
        logger.info("Etapa 3: Detectando markers via câmera do robô...")
        
        markers = controller.detect_markers_from_app_screen()
        if not markers:
            raise RuntimeError("Nenhum marker detectado")
        
        logger.info(f"✓ Detectados {len(markers)} markers:")
        for i, marker in enumerate(markers):
            logger.info(
                f"  {i + 1}. ID {marker.marker_id} @ "
                f"({marker.centroid[0]:.0f}, {marker.centroid[1]:.0f}) "
                f"- Área: {marker.area:.0f}px²"
            )
        logger.info("")
        
        # ====================================================================
        # ETAPA 4: ALINHAR ROBÔ
        # ====================================================================
        logger.info("Etapa 4: Alinhando robô (RZ + XYZ)...")
        
        success = controller.perform_full_alignment()
        if not success:
            raise RuntimeError("Falha no alinhamento")
        
        logger.info("✓ Alinhamento completo bem-sucedido")
        logger.info("")
        
        # ====================================================================
        # ETAPA 5: TOCAR MARKERS COM FEEDBACK VISUAL
        # ====================================================================
        logger.info("Etapa 5: Tocando markers com feedback visual...")
        logger.info("")
        
        results = controller.touch_marker_sequence(markers)
        
        logger.info("Resultado dos toques:")
        successful = 0
        for marker_id, (success, details) in results.items():
            status = "✓ SUCESSO" if success else "✗ FALHA"
            logger.info(f"  Marker {marker_id}: {status} ({details})")
            if success:
                successful += 1
        
        logger.info("")
        logger.info(f"Resumo: {successful}/{len(markers)} markers tocados com sucesso")
        logger.info("")
        
        # ====================================================================
        # RESULTADO FINAL
        # ====================================================================
        logger.info("=" * 70)
        if successful == len(markers):
            logger.info("✓ SUCESSO: Todos os markers foram tocados!")
        elif successful > 0:
            logger.info(f"⚠ PARCIAL: {successful}/{len(markers)} markers tocados")
        else:
            logger.info("✗ FALHA: Nenhum marker foi tocado")
        logger.info("=" * 70)
        
        return {
            "success": successful == len(markers),
            "markers_total": len(markers),
            "markers_touched": successful,
            "results": results,
            "device_type": device_type,
            "session_id": controller.current_session_id,
        }
    
    except Exception as e:
        logger.error(f"Erro: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}
    
    finally:
        # ====================================================================
        # LIMPEZA
        # ====================================================================
        logger.info("")
        logger.info("Limpando recursos...")
        
        try:
            controller.cleanup()
            robot.motor_off()
            robot.disconnect()
            logger.info("✓ Recursos liberados")
        except Exception as e:
            logger.error(f"Erro na limpeza: {e}")


def example_step_by_step(verbose: bool = False):
    """
    Exemplo passo-a-passo com controle manual de cada etapa.
    
    Útil para debug e entendimento do fluxo.
    """
    setup_logging(verbose)
    logger = logging.getLogger(__name__)
    
    from drivers.alignment.auto_alignment import AutoAlignment
    from drivers.alignment.marker_detector import MarkerDetector
    from drivers.alignment.rotation_alignment import RotationAlignment
    from drivers.device.app_manager import DeviceAppManager
    from drivers.device.mobile import Mobile
    from drivers.robot.denso_aether import Denso
    from drivers.vision.robot_camera import RobotCamera
    
    try:
        logger.info("Iniciando exemplo passo-a-passo...")
        
        # Setup
        robot = Denso("workspace", "control", "")
        robot.connect()
        robot.motor_on()
        
        device = Mobile()
        camera = RobotCamera()
        
        # Componentes individuais
        app_mgr = DeviceAppManager(device)
        detector = MarkerDetector()
        auto_align = AutoAlignment(robot, camera, detector)
        rot_align = RotationAlignment(robot, camera, detector)
        
        # PASSO 1: Iniciar app
        logger.info("\n--- PASSO 1: Iniciar RTA_app ---")
        if not app_mgr.start_app("flat"):
            raise RuntimeError("Falha ao iniciar app")
        logger.info("✓ App iniciado")
        
        # PASSO 2: Detectar
        logger.info("\n--- PASSO 2: Detectar markers ---")
        while True:
            frame = camera.capture_frame()
            ids, corners = detector.detect_markers(frame)
            
            if ids and len(ids) >= 4:
                logger.info(f"✓ {len(ids)} markers detectados")
                break
            
            logger.warning("Aguardando markers visíveis...")
            import time
            time.sleep(1)
        
        # PASSO 3: Alinhamento RZ
        logger.info("\n--- PASSO 3: Alinhamento RZ ---")
        if not rot_align.run_alignment_loop(max_iterations=5):
            logger.warning("Alinhamento RZ incompleto")
        logger.info("✓ RZ alinhado")
        
        # PASSO 4: Calibração de distância
        logger.info("\n--- PASSO 4: Calibrar distância ---")
        if not auto_align.calibrate_distance():
            raise RuntimeError("Falha na calibração")
        logger.info("✓ Distância calibrada")
        
        # PASSO 5: Centralização XY
        logger.info("\n--- PASSO 5: Centralizar XY ---")
        if not auto_align.run_centering_loop(max_iterations=10):
            logger.warning("Centralização incompleta")
        logger.info("✓ Centralizado")
        
        # PASSO 6: Aproximação Z
        logger.info("\n--- PASSO 6: Aproximar (Z) ---")
        if not auto_align.run_depth_loop(target_distance_mm=150, max_iterations=10):
            logger.warning("Aproximação incompleta")
        logger.info("✓ Posicionado para toque")
        
        # PASSO 7: Toque manual
        logger.info("\n--- PASSO 7: Toque nos markers ---")
        
        # Detectar novo para obter posições atualizadas
        frame = camera.capture_frame()
        ids, corners = detector.detect_markers(frame)
        corners = detector.refine_corners(frame, corners)
        
        marker_infos = [
            detector.get_marker_info(int(ids[i][0]), corners[i])
            for i in range(len(ids))
        ]
        
        for i, marker in enumerate(marker_infos[:4]):  # Primeiros 4
            x, y = int(marker.centroid[0]), int(marker.centroid[1])
            logger.info(f"  Tocando marker {i+1} @ ({x}, {y})")
            device.touch(x, y)
            import time
            time.sleep(0.5)
        
        logger.info("✓ Toques executados")
        logger.info("\n✓ Exemplo passo-a-passo completado")
    
    except Exception as e:
        logger.error(f"Erro: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        try:
            robot.motor_off()
            robot.disconnect()
            camera.release()
        except:
            pass


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Exemplos de uso do RTA com RTA_app"
    )
    parser.add_argument(
        "--mode",
        choices=["complete", "step", "test"],
        default="complete",
        help="Modo de execução"
    )
    parser.add_argument(
        "--device-type",
        choices=["flat", "foldable"],
        default="flat",
        help="Tipo de dispositivo (número de markers)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Ativar logging detalhado"
    )
    
    args = parser.parse_args()
    
    if args.mode == "complete":
        result = example_complete_workflow(args.device_type, args.verbose)
        sys.exit(0 if result.get("success") else 1)
    
    elif args.mode == "step":
        example_step_by_step(args.verbose)
        sys.exit(0)
    
    elif args.mode == "test":
        print("Teste: Verificar conexões...")
        from drivers.device.app_manager import DeviceAppManager
        
        app_mgr = DeviceAppManager()
        if app_mgr.is_app_running():
            print("✓ App está rodando")
        else:
            print("✗ App não está rodando")
        
        sys.exit(0)


# ============================================================================
# USO
# ============================================================================

"""
python example_usage.py --mode complete --device-type flat
  → Executa sequência completa com 4 markers

python example_usage.py --mode complete --device-type foldable
  → Executa sequência completa com 8 markers

python example_usage.py --mode step --verbose
  → Executa passo-a-passo com debug logging

python example_usage.py --mode test
  → Apenas testa se app está rodando
"""
