"""
Estrutura Atualizada do Projeto RTA - Integração com FOV

Arquivos criados para reutilizar funcionalidades de alinhamento do FOV
sem modificar a pasta FOV original.
"""

# ============================================================================
# ESTRUTURA DO PROJETO
# ============================================================================

"""
RTA/
├── core_logic.py
├── pyproject.toml
├── README.md
│
├── abstract/
│   └── abstract_robot.py
│
├── drivers/
│   ├── __init__.py
│   │
│   ├── device/
│   │   ├── __init__.py
│   │   ├── mobile.py
│   │   ├── terminal.py
│   │   └── ...
│   │
│   ├── robot/
│   │   ├── __init__.py
│   │   └── denso_aether.py
│   │
│   ├── vision/                          # ✨ NOVO
│   │   ├── __init__.py
│   │   └── robot_camera.py              # Gerencia câmera acoplada
│   │
│   └── alignment/                       # ✨ NOVO
│       ├── __init__.py
│       ├── marker_detector.py           # Detecção e geom. de markers
│       ├── auto_alignment.py            # Adaptação: auto_distance.py
│       └── rotation_alignment.py        # Adaptação: z_aligner.py
│
├── utils/
│   ├── math_transform.py
│   ├── coordinate_transform.py          # ✨ NOVO - Transf. imagem→robô
│   ├── marker_touch_controller.py       # ✨ NOVO - Orquestração
│   ...
│
├── FOV/                                 # (Não modificado)
│   └── ...
│
├── RTA_app/
│   └── ...
│
├── INTEGRATION_GUIDE.md                 # ✨ NOVO - Documentação
├── config.py                            # ✨ NOVO - Calibração
├── example_usage.py                     # ✨ NOVO - Exemplos
│
└── tags/, test_results/, ...
"""

# ============================================================================
# COMPONENTES CRIADOS
# ============================================================================

COMPONENTS = {
    "drivers/vision/robot_camera.py": {
        "classe": "RobotCamera",
        "responsabilidade": "Interface com câmera acoplada ao robô",
        "métodos": [
            "capture_frame() → np.ndarray",
            "capture_and_save(filename) → np.ndarray",
            "set_camera_property(prop_id, value) → bool",
            "release()",
        ],
        "dependências": ["cv2", "numpy", "pathlib"],
    },
    
    "drivers/alignment/marker_detector.py": {
        "classe": "MarkerDetector",
        "responsabilidade": "Detecção e processamento de markers ArUco",
        "métodos": [
            "detect_markers(image) → (ids, corners)",
            "refine_corners(image, corners) → refined_corners",
            "get_marker_info(id, corners) → MarkerInfo",
            "filter_closest_n_markers(image, infos, n) → filtered",
            "split_markers_by_image_center(image, infos) → (left, right)",
            "find_closest_to_center(image, infos) → closest",
        ],
        "dataclass": "MarkerInfo(id, corners, centroid, area, perimeter, ...)",
    },
    
    "drivers/alignment/auto_alignment.py": {
        "classe": "AutoAlignment",
        "responsabilidade": "Controle automático XYZ baseado em visual feedback",
        "adaptado_de": "FOV/auto_fov/cycle/auto_distance.py",
        "métodos": [
            "calibrate_distance() → bool",
            "run_centering_loop() → bool",
            "run_depth_loop(target_distance) → bool",
            "approach_marker(distance) → bool",
        ],
        "parâmetros": [
            "CENTRALIZE_TOLERANCE, DEPTH_TOLERANCE",
            "XY_GAIN, Z_GAIN",
            "Z_MAX, Z_MIN",
            "MAX_ITERATIONS, ITERATION_DELAY",
        ],
    },
    
    "drivers/alignment/rotation_alignment.py": {
        "classe": "RotationAlignment",
        "responsabilidade": "Controle automático de rotação RZ",
        "adaptado_de": "FOV/auto_fov/cycle/z_aligner.py",
        "métodos": [
            "calculate_correction_angle() → float",
            "run_alignment_loop() → bool",
        ],
        "parâmetros": [
            "ALIGNMENT_TOLERANCE, RZ_GAIN",
            "MAX_ROTATION_STEP",
            "MARKERS_PER_SIDE, MARKERS_TOTAL",
        ],
    },
    
    "utils/coordinate_transform.py": {
        "classe": "CoordinateTransform",
        "responsabilidade": "Transformação de coordenadas imagem ↔ robô",
        "dataclasses": [
            "CameraCalibration(focal_length_x/y, principal_point_x/y, marker_real_width/height)",
            "RobotFrameConfig(image_x_to_robot_axis, image_y_to_robot_axis, scale_x/y, ...)",
        ],
        "métodos": [
            "image_to_robot_2d(image_x, image_y, ...) → (robot_x, robot_y)",
            "image_center_offset_mm(x, y, ...) → (offset_x_mm, offset_y_mm)",
            "marker_size_to_depth(area, ref_area, ref_depth) → depth",
            "apply_robot_transform(...) → (new_x, new_y, new_z)",
            "calibrate_from_reference(marker_width, marker_height)",
        ],
    },
    
    "utils/marker_touch_controller.py": {
        "classe": "MarkerTouchController",
        "responsabilidade": "Orquestração da sequência completa de toque",
        "métodos": [
            "detect_markers_in_screen() → List[MarkerInfo]",
            "set_target_markers(marker_ids)",
            "align_for_markers() → bool",
            "touch_marker_on_screen(marker_info) → bool",
            "touch_all_detected_markers() → List[bool]",
            "run_full_sequence(target_ids) → bool",
        ],
        "sequência": [
            "1. Detectar markers via câmera do robô",
            "2. Alinhar rotação (RZ) para paralelismo",
            "3. Calibrar distância (inverse square law)",
            "4. Centralizar markers (XY)",
            "5. Aproximar a distância alvo (Z)",
            "6. Executar toques nos markers",
        ],
    },
}

# ============================================================================
# COMO FOV É REUTILIZADO (SEM MODIFICAÇÕES)
# ============================================================================

"""
┌─────────────────────────────────────────────────────────────┐
│ FOV é REUTILIZADA por:                                      │
└─────────────────────────────────────────────────────────────┘

1. Lógica de Detecção ArUco (marker_detector.py)
   - Reusa os conceitos: detecção, refinamento, filtragem

2. Lógica de Alinhamento XYZ (auto_alignment.py)
   - Reusa os conceitos: inverse square law, centralização, loop de controle

3. Lógica de Alinhamento RZ (rotation_alignment.py)
   - Reusa os conceitos: divisão left/right, comparação de perímetros

┌─────────────────────────────────────────────────────────────┐
│ O que é DIFERENTE em RTA:                                  │
└─────────────────────────────────────────────────────────────┘

1. CÂMERA:
   FOV: Câmera DO CELULAR (dispositivo móvel)
   RTA: Câmera DO ROBÔ (acoplada no manipulador)

2. OBJETIVO:
   FOV: Calibrar câmera do celular em relação ao robô
   RTA: Usar câmera do robô para TOCAR markers na TELA do celular

3. INTERFACE:
   FOV: Usa arquitetura FOV (Aether RDK, específica de lá)
   RTA: Usa interfaces genéricas (robot_arm, device, camera)

4. ADICIONAL EM RTA:
   - Transformação de coordenadas (imagem → robô)
   - Orquestração automática de toque
   - Suporte a múltiplos targets
"""

# ============================================================================
# QUICK START
# ============================================================================

"""
# Instalação de dependências (já presentes no FOV)
pip install numpy opencv-python

# Exemplo mais simples
from drivers.robot.denso_aether import Denso
from drivers.device.mobile import Mobile
from drivers.vision.robot_camera import RobotCamera
from utils.marker_touch_controller import MarkerTouchController

robot = Denso("ws", "ctrl", "")
robot.connect()
robot.motor_on()

device = Mobile()
camera = RobotCamera()

controller = MarkerTouchController(robot, device, camera)
success = controller.run_full_sequence()

robot.motor_off()
robot.disconnect()
camera.release()
"""

# ============================================================================
# CONFIGURAÇÕES CRÍTICAS
# ============================================================================

"""
ANTES DE USAR, CONFIGURE:

1. config.py:
   - MARKER_REAL_WIDTH_MM, HEIGHT_MM (seu marker real)
   - MARKER_X_DISTANCE_MM (espaçamento entre markers)
   - COORDINATE_MAPPING (orientação da câmera)
   
2. AutoAlignment:
   - CENTRALIZE_TOLERANCE (precisão centralização)
   - DEPTH_TOLERANCE (precisão profundidade)
   - XY_GAIN, Z_GAIN (resposta do controle)

3. RotationAlignment:
   - ALIGNMENT_TOLERANCE (precisão rotação)
   - MARKERS_PER_SIDE (número por lado)

4. CoordinateTransform:
   - CameraCalibration (focal length, principal point)
   - RobotFrameConfig (mapeamento de eixos)
"""

# ============================================================================
# ARQUIVOS DE REFERÊNCIA
# ============================================================================

"""
📖 Consultar para mais detalhes:

1. INTEGRATION_GUIDE.md
   - Uso de cada componente
   - Exemplos práticos
   - Troubleshooting

2. config.py
   - Valores padrão recomendados
   - Guia de calibração
   - Explicação de cada parâmetro

3. example_usage.py
   - Exemplos funcionais
   - Diferentes padrões de uso
   - Inspeção de markers

4. Arquivos de código
   - Docstrings completas em cada classe/método
   - Comentários explicativos
   - Type hints para clareza
"""
