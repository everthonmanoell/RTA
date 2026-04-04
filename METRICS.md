# Métricas de Teste - RTA

## Visão Geral

O sistema agora coleta automaticamente métricas de cada erro de teste, incluindo:

- **Tempo de resposta** ⏱️: duração de cada transição de estado
- **Precisão (posição)**: distância entre posição esperada e tocada
- **Área/pixels tocados**: área do marcador e cobertura de swipe

As métricas são salvas em arquivos JSON na pasta `test_results/` com timestamp.

---

## Como Usar

### 1. Executar com Coleta de Métricas

Por padrão, as métricas são salvas em `test_results/`:

```bash
python state_machine/run_rta_fsm.py \
  --workspace YOUR_WORKSPACE \
  --control YOUR_CONTROL \
  --num-markers 4 \
  --metrics-dir test_results
```

### 2. Customizar Diretório de Saída

```bash
python state_machine/run_rta_fsm.py \
  --workspace YOUR_WORKSPACE \
  --control YOUR_CONTROL \
  --metrics-dir /caminho/customizado
```

Arquivo gerado: `/caminho/customizado/test_YYYYMMDD_HHMMSS.json`

---

## Estrutura das Métricas

### JSON de Saída

```json
{
  "test_id": "test_20260404_143200",
  "start_time": "2026-04-04T14:32:00.123456",
  "end_time": "2026-04-04T14:32:45.654321",
  "total_duration_sec": 45.53,
  "total_steps": 250,
  "error_touches": 2,
  "final_result": "success",
  "touch_events": [
    {
      "marker_index": 0,
      "target_x": 512.5,
      "target_y": 768.2,
      "actual_x": 512.3,
      "actual_y": 768.5,
      "area_px": 1024.0,
      "timestamp": 1733354520.123
    }
  ],
  "state_transitions": [
    {
      "from_state": "move_to_roi",
      "to_state": "camera_on",
      "duration_sec": 2.134,
      "timestamp": 1733354520.456
    }
  ],
  "swipe_events": [
    {
      "num_points": 12,
      "duration_sec": 3.45,
      "success": true,
      "timestamp": 1733354530.789
    }
  ],
  "statistics": {
    "total_area_touched_px": 4096.0,
    "avg_touch_precision_px": 0.45,
    "num_touches": 4,
    "num_state_transitions": 15
  }
}
```

---

## Métricas Coletadas

### 1. Tempo de Resposta (⏱️ `state_transitions`)

**O que é**: Duração em segundos de cada transição de estado da FSM.

**Exemplo**:
```json
{
  "from_state": "detect_markers",
  "to_state": "align_with_markers",
  "duration_sec": 1.234,
  "timestamp": 1733354520.456
}
```

**Uso**: Identificar gargalos operacionais.
- `move_to_roi` → `camera_on`: quanto tempo leva a câmera ativar
- `align_with_markers` → `touch_marker`: quanto tempo leva o alinhamento

---

### 2. Precisão de Posição (📍 `touch_events`)

**O que é**: Para cada toque, o sistema registra:
- `target_x`, `target_y`: posição esperada (centroid do marcador)
- `actual_x`, `actual_y`: posição real tocada (quando capturada)
- **`precision_mm`** (calculada): distância Euclidiana em pixels

**Exemplo**:
```json
{
  "marker_index": 0,
  "target_x": 512.5,
  "target_y": 768.2,
  "actual_x": 512.3,
  "actual_y": 768.5,
  "area_px": 1024.0
}
```

**Cálculo**:
```
precision = sqrt((target_x - actual_x)² + (target_y - actual_y)²)
```

**Usar para**: 
- Avaliar acurácia do alinhamento da câmera e robô
- Detectar desvios sistemáticos

**Agregação**:
```json
"statistics": {
  "avg_touch_precision_px": 0.45
}
```

---

### 3. Área / Pixels Tocados (📐 `touch_events`)

**O que é**: 
- `area_px`: área do marcador tocado (em pixels quadrados)
- **`total_area_touched_px`** (agregada): soma total de pixels de todos os toques + swipes

**Exemplo**:
```json
{
  "marker_index": 0,
  "area_px": 1024.0
},
{
  "marker_index": 1,
  "area_px": 1024.0
}
```

**Agregação**:
```json
"statistics": {
  "total_area_touched_px": 2048.0,
  "num_touches": 2
}
```

**Usar para**:
- Validar que marcadores foram realmente tocados
- Estimar cobertura de toque em testes de border swipe

---

### 4. Swipe (bordas)

**O que é**: Cada swipe contínuo nas bordas é registrado.

**Exemplo**:
```json
{
  "num_points": 12,
  "duration_sec": 3.45,
  "success": true,
  "timestamp": 1733354530.789
}
```

**Usar para**:
- Validar tempo de swipe contínuo
- Detectar falhas na sequência de toque

---

## Exemplos de Análise

### Encontrar gargalos de tempo

```bash
jq '.state_transitions | map({from: .from_state, to: .to_state, duration: .duration_sec}) | max_by(.duration)' test_results/test_20260404_143200.json
```

**Saída**:
```json
{
  "from": "detect_markers",
  "to": "align_with_markers",
  "duration": 5.234
}
```

---

### Precisão média por teste

```bash
jq '.statistics.avg_touch_precision_px' test_results/test_20260404_143200.json
```

**Saída**: `0.45` pixels de desvio médio

---

### Total de pixels tocados

```bash
jq '.statistics.total_area_touched_px' test_results/test_20260404_143200.json
```

**Saída**: `4096.0` pixels

---

## Integração em Suite de Teste

Para integrar as métricas em uma suite automatizada:

```python
import json
from pathlib import Path

metrics_file = Path("test_results/test_20260404_143200.json")
with open(metrics_file) as f:
    metrics = json.load(f)

# Verificar resultado
assert metrics["final_result"] == "success", "Teste falhou"

# Verificar precisão
avg_precision = metrics["statistics"]["avg_touch_precision_px"]
assert avg_precision < 1.0, f"Precisão ruim: {avg_precision}px"

# Verificar tempo máximo de estado
max_duration = max(t["duration_sec"] for t in metrics["state_transitions"])
assert max_duration < 10.0, f"Transição muito lenta: {max_duration}s"

print(f"✓ Teste passou | Precisão: {avg_precision}px | Área: {metrics['statistics']['total_area_touched_px']}px")
```

---

## Notas de Implementação

1. **Posição Real Tocada**: Atualmente, `actual_x` e `actual_y` são inicializados com o mesmo valor de `target_x` e `target_y`. Para capturar a posição *real* tocada, seria necessário adicionar feedback do dispositivo Android (ex.: via evento de toque ou sensor).

2. **Timestamp**: Todos os eventos usam `time.time()` (Unix timestamp em segundos).

3. **Arquivo de Log**: Cada teste gera um arquivo JSON único com timestamp no nome.

4. **Diretório Padrão**: `test_results/` é criado automaticamente se não existir.

---

## Próximas Melhorias

- [ ] Capturar posição real do toque do dispositivo (integração com Android)
- [ ] Adicionar logs de erro/exceção em cada estado
- [ ] Calcular velocidade média de manipulação
- [ ] Plotar gráficos de tempo vs estado
- [ ] Comparar métricas entre testes (trending)

