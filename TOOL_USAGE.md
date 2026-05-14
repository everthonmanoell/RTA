# Guia de Uso da Ferramenta RTA

## Visao Geral

Este guia mostra como operar a ferramenta RTA ponta a ponta:

1. O app Android renderiza os ArUcos e envia parametros fisicos.
2. O Python recebe os parametros e monta a calibracao.
3. A FSM executa o fluxo do robo com visao, toque e validacao final.

Arquivos principais:

- [state_machine/run_rta_fsm.py](state_machine/run_rta_fsm.py)
- [state_machine/rta.py](state_machine/rta.py)
- [state_machine/rta_model.py](state_machine/rta_model.py)
- [utils/receive_marker_params.py](utils/receive_marker_params.py)
- [RTA_app/app/src/main/java/com/example/rta/MainActivity.kt](RTA_app/app/src/main/java/com/example/rta/MainActivity.kt)

## Pre-requisitos

1. Python configurado no ambiente do projeto.
2. Dependencias instaladas:
   - `transitions`
   - `opencv-python`
   - bibliotecas do projeto, como `aether_rdk`
3. ADB disponivel no PATH.
4. Device Android conectado na mesma rede do servidor Python.
5. Robo Denso acessivel pelos parametros `workspace` e `control`.

## Como o Fluxo Funciona

1. O app calcula o tamanho real do ArUco usando `dp` + `DPI` da tela.
2. O app envia os parametros via socket para o Python, junto com metadados da tela e do device.
3. O Python carrega esses parametros em `config.py` por meio de `utils/receive_marker_params.py`.
4. O bootstrap `state_machine/run_rta_fsm.py` inicia a FSM e injeta os hooks reais.
5. A FSM roda ate o estado `done` ou `error`.
6. A validacao final do alinhamento acontece com um swipe continuo nas bordas da tela.
7. O app decide o resultado final com base no marcador de sucesso ou falha exibido ao final do swipe.

## Configurar IP do Servidor Python Sem Recompilar

O app aceita o endpoint dinamico por `Intent` e salva em `SharedPreferences`.

Prioridade de leitura no app:

1. Extras de `Intent` (`python_server_ip`, `python_server_port`)
2. Ultimo valor salvo em `SharedPreferences`
3. Fallback padrao

Comando recomendado de start via suite ou ADB:

```bash
adb shell am start -n com.example.rta/.MainActivity \
  --es python_server_ip 192.168.1.45 \
  --ei python_server_port 50505 \
  --es device_type flat
```

Observacao:

- Depois da primeira execucao com extras, os valores ficam persistidos no app.

## Sequencia Recomendada de Operacao

1. Iniciar o backend Python ou a ferramenta que importa `config.py`.
2. Iniciar o `RTA_app` com o comando ADB acima, passando o IP e a porta corretos.
3. Executar a FSM:

```bash
python state_machine/run_rta_fsm.py \
  --workspace YOUR_WORKSPACE \
  --control YOUR_CONTROL \
  --options "" \
  --num-markers 4 \
  --loop-delay 0.05 \
  --max-steps 5000 \
  --touch-timeout 3
```

4. Acompanhar os logs de transicao ate `done` ou `error`.

## Parametros Importantes

App Android:

- `python_server_ip`
- `python_server_port`
- `device_type` (`flat`, `foldable`, etc.)

FSM Python:

- `--num-markers`: quantidade esperada
- `--touch-timeout`: timeout de feedback de toque
- `--max-steps`: protecao contra loop infinito

## Resultado Esperado

### Sucesso

1. A FSM termina em `done`.
2. O motor desliga e a conexao e encerrada no cleanup.
3. O app exibe o marcador de sucesso depois de validar o swipe nas bordas.

### Falha

1. A FSM termina em `error`.
2. Verificar os contadores de limite no modelo:
   - `connect_robot_attempts`
   - `motor_on_attempts`
   - `detect_markers_attempts`
   - `error_touch`
   - `final_result_failures`
3. O app exibe o marcador de falha ou a validacao das bordas nao e concluida.

## Troubleshooting Rapido

### 1. App nao envia parametros

- Confirmar IP e porta da maquina Python no comando ADB.
- Confirmar firewall liberando TCP `50505`.

### 2. Python nao recebe parametros

- Verificar se `utils/receive_marker_params.py` foi chamado antes da execucao principal.
- Verificar timeout e logs de conexao.

### 3. Nao detecta ArUco

- Validar iluminacao e foco da camera.
- Confirmar tamanho do marker e DPI recebidos do app.

### 4. Toque nao confirma

- Validar ADB e permissao de leitura de eventos no device.
- Ajustar `--touch-timeout`.

### 5. Cai em error cedo

- Checar conectividade do robo e o estado do motor.

## Integracao em Suite de Teste Existente

Para acoplar na sua suite atual:

1. Adicione a etapa de start do app com extras de IP e porta.
2. Adicione a etapa de start da FSM com argumentos padronizados.
3. Capture logs e estado final (`done` ou `error`) como criterio de teste.
4. Considere o teste de swipe nas bordas como criterio funcional do alinhamento final.
5. Em ambientes com rede variavel, atualize somente os extras ADB, sem recompilar o APK.

## Checklist de Campo

1. ADB conectado.
2. IP e porta corretos enviados para o app.
3. Backend Python ouvindo porta `50505`.
4. Camera capturando frame.
5. Robo responde a `connect_robot` e `motor_on`.
6. FSM conclui `done` em pelo menos um ciclo de validacao.
