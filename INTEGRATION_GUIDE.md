# Integração com FOV: Alinhamento Visual e Toque em Markers

## Visão Geral

Sua estrutura RTA foi estendida para reutilizar a lógica de alinhamento visual do projeto FOV, adaptada especificamente para:

- **Câmera do Robô**: Usar a câmera acoplada no robô (não a do celular)
- **Alinhamento Visual**: Alinhar o robô para tocar markers fiduciais na tela do celular
- **Transformação de Coordenadas**: Converter detecções de imagem → posições do robô
- **Interação com Dispositivo**: Executar toques nos markers via manipulador

## Estrutura de Módulos

### 1. Vision (`drivers/vision/`)
- **`robot_camera.py`**: Interface com a câmera acoplada ao robô
  - Captura frames
  - Gerencia propriedades da câmera (brilho, contraste, etc.)
  - Salva imagens em timestamp

### 2. Alignment (`drivers/alignment/`)

#### `marker_detector.py`
Detecção e processamento de markers ArUco:
- Detecta markers na imagem
- Refina cantos (sub-pixel)
- Calcula área, perímetro, centroide
- Filtra melhores N markers
- Divide markers em grupos (esquerda/direita)

#### `auto_alignment.py` (Adaptação de `auto_distance.py`)
Alinhamento XYZ automático:
- Mantém markers centralizados (XY)
- Calibra distância usando área de marker (Lei do inverso quadrado)
- Aborda markers a distância alvo
- Loops de controle com ganhos proporcionais

#### `rotation_alignment.py` (Adaptação de `z_aligner.py`)
Alinhamento de rotação (RZ):
- Detecta 4 markers (2 esquerda, 2 direita)
- Compara perímetros de cada lado
- Rota robô para alcançar simetria (paralelismo ao plano dos markers)

### 3. Utils (`utils/`)

#### `coordinate_transform.py`
Transformação de coordenadas imagem → robô:
- Calibração de câmera
- Mapeamento de eixos (imagem → robô)
- Transformação de profundidade (área marker → distância)
- Aplicação de transformações 3D

#### `marker_touch_controller.py`
Orquestração da sequência completa:
1. Detecta markers
2. Alinha robô (RZ + XYZ)
3. Executa toques nos markers

## Como Usar

### Exemplo Básico

```python
from drivers.robot.denso_aether import Denso
from drivers.device.mobile import Mobile
from drivers.vision.robot_camera import RobotCamera
from utils.marker_touch_controller import MarkerTouchController

# Inicializar componentes
robot = Denso("workspace", "control", "options")
device = Mobile()  # Interface com dispositivo móvel
camera = RobotCamera(camera_id=0)

# Criar controlador
controller = MarkerTouchController(
    robot_arm=robot,
    mobile_device=device,
    camera=camera
)

# Configurar distância de aproximação
controller.approach_distance_mm = 200.0

# Executar sequência completa
success = controller.run_full_sequence(
    target_marker_ids=[0, 1, 2, 3]  # IDs dos 4 markers
)

if success:
    print("Markers tocados com sucesso!")
else:
    print("Falha no processo de toque")
```

### Uso Modular

```python
# Usar componentes independentemente
from drivers.alignment.auto_alignment import AutoAlignment
from drivers.alignment.rotation_alignment import RotationAlignment

# Alinhamento de rotação
rot_align = RotationAlignment(robot, camera)
rot_align.run_alignment_loop()

# Alinhamento XYZ
auto_align = AutoAlignment(robot, camera)
auto_align.calibrate_distance()
auto_align.run_centering_loop()
auto_align.run_depth_loop(target_distance_mm=200.0)

# Centering apenas
auto_align.run_centering_loop(max_iterations=10)

# Depth apenas
auto_align.run_depth_loop(target_distance_mm=250.0)
```

### Detecção de Markers

```python
from drivers.alignment.marker_detector import MarkerDetector
from drivers.vision.robot_camera import RobotCamera

detector = MarkerDetector()
camera = RobotCamera()

# Capturar frame
frame = camera.capture_frame()

# Detectar markers
ids, corners = detector.detect_markers(frame)

# Processar
corners = detector.refine_corners(frame, corners)

# Obter informações
for i, marker_id in enumerate(ids):
    info = detector.get_marker_info(int(marker_id[0]), corners[i])
    print(f"Marker {info.marker_id}: area={info.area:.1f}px2, "
          f"center=({info.centroid[0]:.1f}, {info.centroid[1]:.1f})")

# Filtrar melhores 4 markers
marker_infos = [detector.get_marker_info(int(ids[i][0]), corners[i]) 
                for i in range(len(ids))]
best_4 = detector.filter_closest_n_markers(frame, marker_infos, n=4)

# Dividir em esquerda/direita
left, right = detector.split_markers_by_image_center(frame, best_4)
```

## Parâmetros de Calibração

### AutoAlignment
- `CENTRALIZE_TOLERANCE`: Tolerância de centralização (pixels)
- `DEPTH_TOLERANCE`: Tolerância de profundidade (mm)
- `TARGET_DISTANCE_MM`: Distância padrão de aproximação
- `XY_GAIN`, `Z_GAIN`: Ganhos de controle proporcional
- `Z_MAX`, `Z_MIN`: Limites de segurança do eixo Z

### RotationAlignment
- `ALIGNMENT_TOLERANCE`: Tolerância de alinhamento (graus)
- `RZ_GAIN`: Ganho de rotação
- `MAX_ROTATION_STEP`: Limite de rotação por iteração

### CoordinateTransform
- `marker_real_width_mm`, `marker_real_height_mm`: Dimensões reais do marker
- `image_x_to_robot_axis`, `image_y_to_robot_axis`: Mapeamento de eixos
- `scale_x`, `scale_y`: Escalas de conversão (pixels/mm)

## Configuração do Mapeamento de Eixos

A transformação de coordenadas permite flexibilidade na orientação:

```python
from utils.coordinate_transform import CoordinateTransform, RobotFrameConfig

config = RobotFrameConfig(
    image_x_to_robot_axis="X",  # Eixo X da imagem → X do robô
    image_y_to_robot_axis="Z",  # Eixo Y da imagem → Z do robô
    scale_x=0.1,  # Conversão pixel para mm
    scale_y=0.1
)

transform = CoordinateTransform(robot_config=config)
```

## Fluxo de Execução Recomendado

1. **Inicialização**
   ```python
   robot.connect()
   robot.motor_on()
   ```

2. **Calibração**
   ```python
   controller.auto_align.calibrate_distance()
   ```

3. **Alinhamento de Rotação** (garante perpendicularidade)
   ```python
   controller.rot_align.run_alignment_loop()
   ```

4. **Centralização** (posiciona markers no centro)
   ```python
   controller.auto_align.run_centering_loop()
   ```

5. **Aproximação** (move para distância alvo)
   ```python
   controller.auto_align.run_depth_loop(target_distance_mm=150.0)
   ```

6. **Toque**
   ```python
   markers = controller.detect_markers_in_screen()
   for marker in markers:
       controller.touch_marker_on_screen(marker)
   ```

7. **Limpeza**
   ```python
   robot.motor_off()
   robot.disconnect()
   camera.release()
   ```

## Troubleshooting

### Nenhum marker detectado
- Verificar iluminação da câmera
- Garantir markers bem visíveis
- Testar `camera.capture_and_save()` para inspecionar frames

### Alinhamento não converge
- Aumentar `MAX_ITERATIONS` em AutoAlignment/RotationAlignment
- Ajustar limites de tolerância
- Verificar calibração de câmera

### Toque impreciso
- Calibrar distância novamente com `calibrate_distance()`
- Validar mapeamento de eixos em CoordinateTransform
- Diminuir `approach_distance_mm` para maior precisão

## Não Modificar FOV

Este projeto foi estruturado para:
✓ Reutilizar lógica de FOV sem modificações
✓ Adaptar conceitos para sua aplicação RTA específica
✓ Permitir futuras atualizações de FOV independentes
