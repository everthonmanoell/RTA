"""
Configurações de Calibração Recomendadas para Integração FOV/RTA

Este arquivo fornece valores de exemplo e orientações para calibrar
o sistema de alinhamento visual para seu setup específico.
"""

# ============================================================================
# CONFIGURAÇÃO DE CÂMERA
# ============================================================================

CAMERA_CONFIG = {
    "camera_id": 0,  # ID da câmera no OpenCV (0 = primária)
    "output_dir": "log_images",  # Diretório para salvar frames
    "frame_width": 640,  # Resolução recomendada
    "frame_height": 480,
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
# Agora pode ser definido dinamicamente via socket (ver utils/receive_marker_params.py)
try:
    from utils.receive_marker_params import receive_marker_params
    _marker_params = receive_marker_params()
    MARKER_REAL_WIDTH_MM = _marker_params["MARKER_REAL_WIDTH_MM"]
    MARKER_REAL_HEIGHT_MM = _marker_params["MARKER_REAL_HEIGHT_MM"]
    MARKER_X_DISTANCE_MM = _marker_params["MARKER_X_DISTANCE_MM"]
except Exception as e:
    print(f"[config.py] Erro ao carregar parâmetros dinâmicos: {e}. Usando valores padrão.")
    MARKER_REAL_WIDTH_MM = 100.0
    MARKER_REAL_HEIGHT_MM = 100.0
    MARKER_X_DISTANCE_MM = 500.0

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
    "image_y_to_robot_axis": "Z",  # ou "Y"
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
# PARÂMETROS DE ALINHAMENTO XYZ (AutoAlignment)
# ============================================================================

AUTO_ALIGNMENT_CONFIG = {
    # Tolerâncias de convergência
    "centralize_tolerance": 5.0,  # pixels
    "depth_tolerance": 10.0,  # mm
    
    # Distâncias alvo
    "target_distance_mm": 200.0,  # Distância padrão de aproximação
    
    # Ganhos de controle proporcional (PID simplificado)
    "xy_gain": 0.3,  # Quanto da correção XY aplicar por iteração
    "z_gain": 0.2,   # Quanto da correção Z aplicar por iteração
    
    # Limites de segurança para eixo Z do robô
    "z_max": 600.0,  # mm
    "z_min": 100.0,  # mm
    
    # Limites de iteração e tempo
    "max_iterations": 20,
    "iteration_delay": 0.5,  # segundos entre iterações
    
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
    # Distância de aproximação para toque
    "approach_distance_mm": 150.0,  # Mais perto para maior precisão
    
    # Timings de toque
    "touch_delay_before_lift": 0.5,  # segundos (pressionado)
    "touch_delay_after_touch": 0.5,  # segundos (aguardar resposta)
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
