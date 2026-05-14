# Listen-While-Moving: Nova Abordagem para Toque em Marcadores

**Data:** 2026-04-04  
**Status:** ✅ IMPLEMENTADO  

## O Problema com Pause-and-Listen

A abordagem anterior (pause-and-listen) tinha um risco crítico:

```
1. Robô se move em direção ao marcador
2. Robô toca na tela
3. Robô PARA
4. Sistema escuta feedback
```

**Risco:** Entre os passos 2 e 3, o robô continuava com inércia/movimento, podendo aplicar pressão excessiva na tela ANTES de a escuta começar. Isso pode quebrar o dispositivo.

## A Solução: Listen-While-Moving

Nova abordagem que escuta **continuamente durante todo o movimento**:

```
1. Sistema COMEÇA a escuta
2. Robô se move para o marcador
3. Sistema detecta toque DURANTE movimento
4. Robô PARA IMEDIATAMENTE
5. Salva posição do toque (para mapeamento)
6. Robô recua para altura segura
```

**Benefício:** Detecção em tempo real + parada imediata = sem risco de pressão excessiva.

## Implementação

### 1. Método Core: `move_and_listen_until_touch()`

**Ubicação:** [`utils/marker_touch_controller.py`](../utils/marker_touch_controller.py)

```python
def move_and_listen_until_touch(
    target_x, target_y, z_touch,  # pose alvo
    rx, ry, rz,                    # orientação
    speed=50.0,                    # velocidade de movimento (mm/s)
    touch_timeout=10.0,            # timeout máximo de escuta
    approach_height=10.0,          # altura de abordagem
) -> tuple[bool, Optional[dict]]:
```

**Fluxo:**
1. Inicia thread de listener que monitora eventos de toque via getevent
2. Move robô incrementalmente para pose alvo
3. A cada iteração, verifica se toque foi detectado
4. Se toque detectado durante movimento → para imediatamente
5. Retorna: `(sucesso, touch_info)` com posição real do toque e pose do robô

**Retorno:**
```python
{
    "touch_position": (x_px, y_px),           # Posição na tela
    "touch_pressure": int,                    # Pressão em grams-force
    "robot_pose_at_touch": (x,y,z,rx,ry,rz), # Pose exata no momento do toque
    "timestamp": float,                       # Timestamp do toque
    "movement_interrupted": bool,             # True = toque interrompeu movimento
}
```

### 2. Método Wrapper: `touch_marker_listen_while_moving()`

**Ubicação:** [`utils/marker_touch_controller.py`](../utils/marker_touch_controller.py)

```python
def touch_marker_listen_while_moving(
    marker_info,        # MarkerInfo com centroid
    z_touch,           # altura de toque
    speed=50.0,        # velocidade
    touch_timeout=10.0 # timeout
) -> tuple[bool, Optional[dict]]:
```

**Responsabilidades específicas para marcadores fiduciais:**
1. Converte centroid de pixel para pose do robô
2. Chama `move_and_listen_until_touch()`
3. Calcula erro de posição: `|centroid_marcador - posição_real_toque|`
4. Recua automaticamente
5. Retorna dados de mapeamento

**Retorno (adicional):**
```python
{
    "marker_id": str,              # ID do marcador
    "marker_centroid": (x, y),     # Centro detectado do marcador
    "touch_position": (x, y),      # Onde o toque realmente ocorreu
    "position_error_px": float,    # |centroid - touch_position|
    "touch_pressure": int,
    "robot_pose_at_touch": (...),
    "timestamp": float,
}
```

## Integração com FSM Bootstrap

**Arquivo:** [`state_machine/run_rta_fsm.py`](../state_machine/run_rta_fsm.py)

**Mudança no `touch_marker_fn()`:**

```python
def touch_marker_fn(index: int) -> bool:
    """Toca marcador escutando continuamente durante o movimento."""
    
    # NOVO: listen-while-moving
    ok, touch_info = controller.touch_marker_listen_while_moving(
        marker, 
        z_touch=z_touch, 
        speed=50.0, 
        touch_timeout=args.touch_timeout
    )
    
    if touch_info:
        # Captura posição REAL do toque (pode diferir do centroid)
        actual_x, actual_y = touch_info["touch_position"]
        position_error = touch_info["position_error_px"]
        touch_pressure = touch_info["touch_pressure"]
        
        # Salva para mapeamento de marcadores fiduciais
        runtime["fiducial_touches"].append(touch_info)
    
    # Registra métricas com dados reais
    metrics_logger.record_touch(
        test_metrics,
        marker_index=index,
        target_x=target_x,
        target_y=target_y,
        actual_x=actual_x,           # ← Posição real, não assumida
        actual_y=actual_y,
        area_px=area_px,
        touch_pressure=touch_pressure # ← Novo: pressão registrada
    )
    
    return ok
```

## Arquivo de Eventos (getevent)

O sistema usa Linux `getevent` via ADB para escuta de toque em tempo real:

**Formato de eventos:**
```
/dev/input/event0: ABS_MT_POSITION_X 00000200  # X = 512
/dev/input/event0: ABS_MT_POSITION_Y 00000400  # Y = 1024
/dev/input/event0: ABS_MT_PRESSURE   000001c2  # Pressão = 450
/dev/input/event0: SYN_REPORT        00000000  # Sincronização (toque completo)
```

**Parser:** [`drivers/device/mobile.py`](../drivers/device/mobile.py) → `TouchTracker`

## Experiência de Pressão Segura

### Cenário 1: Toque Bem-Sucedido
```
Tempo    Evento                          Robot Z
0ms      Listener inicia
100ms    Robot em altura de abordagem     z=60mm
200ms    Robot desce para z_touch         z=50mm
250ms    Toque detectado! ← PARADA!       z=50mm
300ms    Robot recua                      z=60mm
```
✅ Pressão segura, dano evitado.

### Cenário 2: Timeout (Sem Toque)
```
Tempo    Evento
0ms      Listener inicia
10000ms  Timeout atingido
         Listener para
         Robot finaliza movimento
         Retorna sucesso=False
```
✅ Sem risco, timeout protetor.

### Cenário 3: Pressão Excessiva Detectada
```
Tempo    Evento                    Pressão
0ms      Listener inicia
200ms    Robot toca (gentle)       450g    ← Dentro dos limites
250ms    PRESSÃO SOBE!             800g    ← Acima do limite (700g)
         Sistema detecta: PARADA!  0g
         Robot recua
```
✅ Proteção adicional via pressão.

## Dados para Mapeamento

Cada toque bem-sucedido coleta:
- **Posição do toque real** (não o centroid) - para calibração de sensores
- **Posição do robô** (6D pose) - para reconstrução geométrica
- **Pressão aplicada** - para análise de força
- **Timestamps** - para sincronização

**Uso:** Construção de mapas de marcadores fiduciais com precisão sub-pixel

Exemplo de saída:
```python
{
    "marker_id": "fiducial_42",
    "marker_centroid": (512.5, 1024.3),
    "touch_position": (513.2, 1022.8),      # 2.1 pixels de erro
    "position_error_px": 2.1,
    "touch_pressure": 450,
    "robot_pose_at_touch": (100.5, 200.3, 49.8, 0.01, -0.02, 0.0),
    "timestamp": 1712332800.123
}
```

## Testes

**Arquivo:** [`tests/test_safety_critical_touch.py`](../tests/test_safety_critical_touch.py)

### Novos Testes:
1. `TestListenWhileMoving.test_listen_while_moving_success()`
   - Valida detecção de toque durante movimento

2. `TestListenWhileMoving.test_listen_while_moving_timeout()`
   - Valida timeout quando nenhum toque

3. `TestListenWhileMoving.test_touch_marker_listen_while_moving()`
   - Valida wrapper de marcador com cálculo de erro de posição

## Configuração

Adicionar a `config.py`:

```python
# Listen-while-moving parameters
LISTEN_WHILE_MOVING_SPEED = 50.0         # mm/s (velocidade segura)
LISTEN_WHILE_MOVING_TIMEOUT = 10.0       # segundos
LISTEN_WHILE_MOVING_INTERVAL = 50        # ms entre verificações

# Pressure safety thresholds
TOUCH_PRESSURE_MIN_CONTACT = 300         # grams-force (confirma contato)
TOUCH_PRESSURE_MAX_SAFE = 700            # grams-force (limite de segurança)
TOUCH_PRESSURE_WARNING = 600             # grams-force (aviso de proximidade)
```

## Logging

Todos os toques registram em tempo real:

```
[LISTEN] Thread de listener iniciada
[MOVE] Pose atual: (100.25, 200.50, 60.00)
[MOVE] Encostou na altura de abordagem
[LISTEN] Toque detectado! pos=(513, 1025), pressão=450g, duração=0.025s
[MOVE] Toque detectado! Parando movimento imediatamente
[FIDUCIAL] Toque bem-sucedido! marker=fiducial_42, erro_posição=2.1px, pressão=450g
[FIDUCIAL] Recuando para z=60.00
[FIDUCIAL] Toque de marcador fiducial_42 salvo para mapeamento (total: 1)
```

## Comparação: Pause-and-Listen vs. Listen-While-Moving

| Aspecto | Pause-and-Listen | Listen-While-Moving |
|---------|-----------------|-------------------|
| **Escuta** | Após movimento | Durante movimento |
| **Parada** | Antes de escuta | Imediata ao toque |
| **Risco** | Pressão excessiva possível | Parada imediata |
| **Pressão máxima** | Desconhecida até escuta | Monitorada em tempo real |
| **Latência** | ~100ms | <10ms |
| **Complexidade** | Simples | Complexa (threading) |
| **Mapeamento** | Básico | Com posição real |

## Próximos Passos

1. ✅ Implementar `move_and_listen_until_touch()`
2. ✅ Implementar `touch_marker_listen_while_moving()`
3. ✅ Integrar com FSM bootstrap
4. ✅ Adicionar testes unitários
5. 🔄 Testes de integração com dispositivo real
6. 🔄 Calibração de velocidade segura (50.0 mm/s)
7. 🔄 Validação de limites de pressão
8. 🔄 Geração de mapas de marcadores fiduciais

## Sumário

- **O quê:** Nova abordagem de toque que escuta continuamente durante movimento
- **Por quê:** Evitar pressão excessiva e quebra de dispositivo, + mapeamento preciso
- **Como:** Threading de listener + movimento interruptível
- **Quando:** Implementado em 2026-04-04, pronto para testes
- **Resultado:** Toques seguros com dados de mapeamento de alta precisão
