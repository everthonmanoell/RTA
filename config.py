"""
Configurações de Calibração Recomendadas para Integração FOV/RTA

Este arquivo fornece valores de exemplo e orientações para calibrar
o sistema de alinhamento visual para seu setup específico.
"""

import os

# ============================================================================
# CONFIGURAÇÃO DE CÂMERA
# ============================================================================

CAMERA_CONFIG = {
    "camera_id": 0,  # ID da câmera no OpenCV (0 = primária)
    "output_dir": "log_images",  # Diretório para salvar frames
    "frame_width": 1080,  # Resolução recomendada
    "frame_height": 720,
}

# Propriedades OpenCV para sua câmera
# cv2.CAP_PROP_BRIGHTNESS, etc.
CAMERA_PROPERTIES = {
    # "brightness": 0.5,  # 0-1
    # "contrast": 0.5,
    # "saturation": 0.5,
    # "exposure": -5,  # negativo para auto
}

## id marcador de falha/sucesso final (na tela do app)
#TODO colocar os ids
FINAL_SUCCESS_MARKER_ID = 100
FINAL_FAILURE_MARKER_ID = 200

# ============================================================================
# CALIBRAÇÃO DE MARKERS
# ============================================================================


# Tamanho real dos seus markers ArUco em milímetros e espaçamento
# Carregamento priorizado:
# 1. ADB: Obtém DisplayMetrics direto do device (resoluçao, DPI, tag_size, offset).
#    → Rápido, confiável, não depende do app.
# 2. Socket: Tenta receber DisplayMetrics + insets do app Android (opcional, para refinar).
# 3. Cache: Último payload válido se ADB e socket falharem.
# 4. Defaults: Fallback final se tudo falhar.

_marker_params = None
DEVICE_TYPE = str(os.getenv("RTA_DEVICE_TYPE", "flat")).strip().lower() or "flat"
_adb_device_type = "foldable" if DEVICE_TYPE == "foldable" else "flat"

# CAMADA 1: Tenta ADB first (mais rápido e confiável)
try:
    # 1. FORÇA O HEALTH CHECK E A AUTO-CURA ANTES DE TUDO
    from drivers.device.mobile import list_adb_devices
    list_adb_devices() # Se o ADB estiver travado, ele reinicia o daemon aqui mesmo em 2 segundos!
    
    # 2. Agora sim, busca as métricas com o cabo já desengasgado
    from utils.adb_device_metrics import get_device_metrics_via_adb
    _marker_params = get_device_metrics_via_adb(device_type=_adb_device_type)
    
    if _marker_params and _marker_params.get("screen_width_px", 0.0) > 0:
        print("[config.py] DisplayMetrics via ADB: OK")
    else:
        print("[config.py] ADB retornou dados inválidos. Tentando socket...")
        _marker_params = None
except Exception as adb_err:
    print(f"[config.py] ADB falhou: {adb_err}. Tentando socket...")
    _marker_params = None

# CAMADA 2: Se ADB falhou, tenta socket (insets opcionais)
if _marker_params is None:
    try:
        from utils.receive_marker_params import receive_marker_params
        socket_params = receive_marker_params(timeout_seconds=12.0)
        if socket_params and socket_params.get("screen_width_px", 0.0) > 0:
            _marker_params = socket_params
            print("[config.py] DisplayMetrics via socket: OK")
        else:
            print("[config.py] Socket retornou dados inválidos.")
    except Exception as socket_err:
        print(f"[config.py] Socket falhou: {socket_err}.")

# CAMADA 3: Se ADB e socket falharam, tenta cache
if _marker_params is None:
    try:
        from utils.receive_marker_params import _load_cached_params
        cached = _load_cached_params()
        if cached:
            _marker_params = cached
            print("[config.py] DisplayMetrics via cache: OK")
    except Exception as cache_err:
        print(f"[config.py] Cache falhou: {cache_err}.")

# CAMADA 4: Se tudo falhou, defaults
if _marker_params and _marker_params.get("screen_width_px", 0.0) > 0:
    MARKER_REAL_WIDTH_MM = _marker_params["MARKER_REAL_WIDTH_MM"]
    MARKER_REAL_HEIGHT_MM = _marker_params["MARKER_REAL_HEIGHT_MM"]
    MARKER_X_DISTANCE_MM = _marker_params["MARKER_X_DISTANCE_MM"]
    MARKER_MARGIN_PX = _marker_params.get("MARKER_MARGIN_PX", 30.0)
    MARKER_TAG_SIZE_PX = _marker_params.get("tag_size_px", 0.0)
    DEVICE_DENSITY = _marker_params.get("density", 0.0)
    DEVICE_DENSITY_DPI = _marker_params.get("density_dpi", 0.0)
    DEVICE_XDPI = _marker_params.get("xdpi", 0.0)
    DEVICE_YDPI = _marker_params.get("ydpi", 0.0)
    SCREEN_WIDTH_PX = _marker_params.get("screen_width_px", 0.0)
    SCREEN_HEIGHT_PX = _marker_params.get("screen_height_px", 0.0)
    DEVICE_ORIENTATION = _marker_params.get("orientation", "unknown")
    DEVICE_ROTATION = _marker_params.get("rotation", 0)
    SYSTEM_INSET_LEFT_PX = _marker_params.get("inset_left_px", 0.0)
    SYSTEM_INSET_TOP_PX = _marker_params.get("inset_top_px", 0.0)
    SYSTEM_INSET_RIGHT_PX = _marker_params.get("inset_right_px", 0.0)
    SYSTEM_INSET_BOTTOM_PX = _marker_params.get("inset_bottom_px", 0.0)
    METADATA_TIMESTAMP_MS = _marker_params.get("timestamp_ms", 0.0)
    METADATA_ELAPSED_REALTIME_MS = _marker_params.get("elapsed_realtime_ms", 0.0)
    DEVICE_MODEL = str(_marker_params.get("device_model", "unknown")).strip() or "unknown"
    print(f"[config.py] Screen: {SCREEN_WIDTH_PX:.0f}x{SCREEN_HEIGHT_PX:.0f} @ {DEVICE_DENSITY_DPI} DPI, tag_size_px={MARKER_TAG_SIZE_PX:.1f}, margin_px={MARKER_MARGIN_PX:.1f}, model={DEVICE_MODEL}")
else:
    print("[config.py] Nenhuma fonte válida de DisplayMetrics. Usando DEFAULTS.")
    MARKER_REAL_WIDTH_MM = 15.0
    MARKER_REAL_HEIGHT_MM = 15.0
    MARKER_X_DISTANCE_MM = 500.0
    MARKER_MARGIN_PX = 30.0
    MARKER_TAG_SIZE_PX = 300.0
    DEVICE_DENSITY = 0.0
    DEVICE_DENSITY_DPI = 0.0
    DEVICE_XDPI = 0.0
    DEVICE_YDPI = 0.0
    SCREEN_WIDTH_PX = 0.0
    SCREEN_HEIGHT_PX = 0.0
    DEVICE_ORIENTATION = "unknown"
    DEVICE_ROTATION = 0
    SYSTEM_INSET_LEFT_PX = 0.0
    SYSTEM_INSET_TOP_PX = 0.0
    SYSTEM_INSET_RIGHT_PX = 0.0
    SYSTEM_INSET_BOTTOM_PX = 0.0
    METADATA_TIMESTAMP_MS = 0.0
    METADATA_ELAPSED_REALTIME_MS = 0.0
    DEVICE_MODEL = "unknown"

# Profundidade de referência para calibração de distância
# (distância em que você quer calibrar)
REFERENCE_DEPTH_MM = 300.0

# ============================================================================
# TRANSFORMAÇÃO DE COORDENADAS
# ============================================================================

# Mapeamento de eixos: como a imagem da câmera mapeia para o robô
# Ajustar conforme a orientação de sua câmera nomotor
COORDINATE_MAPPING = {
    "image_x_to_robot_axis": "X",  # ou "Y"
    "image_y_to_robot_axis": "Y",  # ou "Y"
    # Significado:
    # - image_x_to_robot_axis = "X" → movimento horizontal da imagem = movimento em X do robô
    # - image_y_to_robot_axis = "Z" → movimento vertical da imagem = movimento em Z do robô
}

# Escalas de conversão (pixels/mm)
# Ajustar após calibração real
COORDINATE_SCALE = {
    "scale_x": 0.1,  # pixels por mm em X
    "scale_y": 0.1,  # pixels por mm em Y
}

# ============================================================================
# CALIBRAÇÃO DE GANHOS E TOLERÂNCIAS
# ============================================================================
TRANSLATION_GAIN = 0.1  # Quanto da correção aplicar por iteração (ajustar para estabilidade)
ALIGMENT_TOLERANCE_MM = 0.5  # Tolerância de alinhamento final (ajustar conforme precisão desejada)
Z_TOUCH = 260.98
Z_LIMIT = 260.98
TOUCH_FINGER_OFFSET_X = -30.1
Z_OFFSET_BEFORE_TOUCH = 20.0
# TOUCH_FINGER_OFFSET_X = -40.5


# ============================================================================
# PARÂMETROS DE ALINHAMENTO XYZ (AutoAlignment)
# ============================================================================

AUTO_ALIGNMENT_CONFIG = {
    # Tolerâncias de convergência
    "centralize_tolerance": 5.0,  # pixels
    "depth_tolerance": 10.0,  # mm
    
    # Distâncias alvo
    "target_distance_mm": 200.0,  # Distância padrão de aproximação
    
    # Ganhos de controle proporcional (PID simplificado)
    "xy_gain": 0.08,  # Reduzido drasticamente para evitar oscilação
    "z_gain": 0.1,   # Quanto da correção Z aplicar por iteração
    
    # Limites de segurança para eixo Z do robô
    "z_max": 600.0,  # mm
    "z_min": 100.0,  # mm
    
    # Limites de iteração e tempo
    "max_iterations": 20,  # Aumentado pois os ganhos agora são menores
    "iteration_delay": 0.35,  # segundos entre iterações
    "max_xy_step_mm": 4.0,  # Reduzido para movimentos mais suaves
    "max_z_step_mm": 4.0,    # limite por iteração em profundidade
    "max_xy_drift_mm": 120.0,  # distância máxima permitida a partir do início do align
    "max_no_improvement_iters": 6,  # aumentado para dar mais chances de convergência
    "min_improvement_mm": 0.5,  # melhora mínima mais agressiva
    "min_markers_for_align": 2,  # inspirado no FOV: permite pré-align com conjunto parcial
    
    # Velocidade de aproximação
    "approach_speed": 5.0,  # mm por iteração
}

# ============================================================================
# PARÂMETROS DE ALINHAMENTO DE ROTAÇÃO (RotationAlignment)
# ============================================================================

ROTATION_ALIGNMENT_CONFIG = {
    # Tolerância de alinhamento RZ
    "alignment_tolerance": 2.0,  # graus
    "rz_gain": 0.5,
    
    # Limites de segurança
    "max_rotation_step": 5.0,  # graus máximos por iteração
    
    # Expectativas do padrão de markers
    "markers_per_side": 2,
    "markers_total": 4,
    
    # Limites de iteração
    "max_iterations": 10,
    "iteration_delay": 0.5,  # segundos
    
    # Sensibilidade do cálculo de ângulo (ajustar conforme FOV da câmera)
    "angle_sensitivity": 0.5,  # graus por unidade de diferença
}

# ============================================================================
# PARÂMETROS DE TOQUE
# ============================================================================

TOUCH_CONFIG = {
    "enabled": True,
    "approach_distance_mm": 150.0,  # Mais perto para maior precisão
    "offset_x": 88.0,
    # Timings de toque
    "offset_z": 75.0,
    "touch_delay_after_touch": 0.5,  # segundos (aguardar resposta)
}

# ============================================================================
# VELOCIDADES DE MOVIMENTACAO DO ROBO
# ============================================================================

ROBOT_MOTION_CONFIG = {
    # Velocidade base para movimentos gerais (ROI, safe_pose, alinhamento, etc.)
    "general_speed": 12.0,
    "general_accel": 12.0,
    "general_decel": 12.0,

    # Velocidade dedicada para toques
    "touch_speed": 8.0,
    "touch_accel": 8.0,
    "touch_decel": 8.0,

    # Velocidade dedicada para swipe
    "swipe_speed": 6.0,
    "swipe_accel": 6.0,
    "swipe_decel": 6.0,
}

# ============================================================================
# CONFIGURAÇÃO DE TOOL (TCP)
# ============================================================================

# Configure aqui o TCP da ferramenta (ex.: caneta) em relação ao flange.
# O bootstrap do FSM usa esses valores automaticamente quando o motor liga.
TOOL_CONFIG = {
    "enabled": True,
    "tag": "pen_tool",
    "offset_x": 88.0,
    "offset_y": 0.0,
    "offset_z": 75.0,
    "offset_rx": 0.0,
    "offset_ry": 0.0,
    "offset_rz": 0.0,
}

# ============================================================================
# CALIBRAÇÃO DE CÂMERA INTRÍNSECA (Opcional, mais avançado)
# ============================================================================

# Se você executar calibração de câmera OpenCV, use estes valores:
CAMERA_INTRINSICS = {
    "focal_length_x": 500.0,  # fx (pixels)
    "focal_length_y": 500.0,  # fy (pixels)
    "principal_point_x": 0.5,  # cx/width
    "principal_point_y": 0.5,  # cy/height
    "distortion": [0, 0, 0, 0, 0],  # k1, k2, p1, p2, k3
}

CAMERA_CALIBRATION_CONFIG = {
    "auto_focus": 2.0,
    "fixed_focus": 20.0,
    "auto_exposure": -1.0,
    "fixed_exposure": -7.0,
    "auto_white_balance": 1.0,
    "white_balance_temperature": -1.0,
}

# ============================================================================
# DICCIONÁRIO ARUCO
# ============================================================================

# Qual dicionário de markers você está usando
ARUCO_DICT = "DICT_6X6_250"  # 6x6 com 250 variações
# Alternativas: DICT_4X4_50, DICT_5X5_100, DICT_7X7_250, etc.

# ============================================================================
# GUIA DE CALIBRAÇÃO
# ============================================================================

"""
1. CALIBRAÇÃO DE CÂMERA INTRÍNSECA (uma vez):
   - Execute calibração OpenCV ChessBoard para sua câmera
   - Atualize CAMERA_INTRINSICS com valores reais
   - Isso melhora precisão de transformação de coordenadas

2. CALIBRAÇÃO DE MARKERS:
   - Imprima markers ArUco com tamanho conhecido
   - Meça dimensões reais em mm
   - Atualize MARKER_REAL_WIDTH_MM, MARKER_REAL_HEIGHT_MM

3. CALIBRAÇÃO DE DISTÂNCIA:
   - Posicione robô a distância conhecida dos markers
   - Chame auto_align.calibrate_distance()
   - Isso estabelece referência para inverse-square-law

4. CALIBRAÇÃO DE MAPEAMENTO DE EIXOS:
   - Mova robô em X → observe qual eixo muda na imagem
   - Mova robô em Y → observe qual eixo muda na imagem
   - Atualize COORDINATE_MAPPING conforme observado

5. CALIBRAÇÃO DE ESCALAS:
   - Após mapeamento, usar valores aproximados
   - Afinar COORDINATE_SCALE iterativamente
   - Testar com pequenos comandos de toque

6. TUNING DE GANHOS:
   - Começar com valores baixos (0.1-0.3)
   - Aumentar gradualmente até conseguir resposta rápida sem oscilação
   - Ajustar DRIFT: se sistema "passa" do alvo, reduzir gain

7. TUNING DE TOLERÂNCIAS:
   - Mais rigoroso (menor tolerance) = mais iterações, mais time
   - Menos rigoroso (maior tolerance) = mais rápido mas menos preciso
   - Balancear conforme sua aplicação
"""

# ============================================================================
# EXEMPLO DE USO
# ============================================================================

"""
from config import AUTO_ALIGNMENT_CONFIG
from drivers.alignment.auto_alignment import AutoAlignment

auto_align = AutoAlignment(robot, camera)
auto_align.CENTRALIZE_TOLERANCE = AUTO_ALIGNMENT_CONFIG["centralize_tolerance"]
auto_align.DEPTH_TOLERANCE = AUTO_ALIGNMENT_CONFIG["depth_tolerance"]
auto_align.XY_GAIN = AUTO_ALIGNMENT_CONFIG["xy_gain"]
auto_align.Z_GAIN = AUTO_ALIGNMENT_CONFIG["z_gain"]

# Usar...
auto_align.approach_marker(AUTO_ALIGNMENT_CONFIG["target_distance_mm"])
"""
