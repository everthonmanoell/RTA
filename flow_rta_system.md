# Fluxo Completo do Sistema RTA

## 1. Objetivo
Este documento descreve o fluxo completo da maquina de estados RTA, como ela e executada e como se integra com os componentes reais de robo, camera, deteccao de marcadores e feedback de toque.

O sistema executa, em alto nivel:
1. Conexao com o robo.
2. Ligamento do motor.
3. Posicionamento na regiao de interesse.
4. Deteccao e alinhamento por marcadores.
5. Toques sequenciais.
6. Swipe final de bordas.
7. Leitura de resultado final.
8. Encerramento com sucesso ou retentativa/falha.

## 2. Estrutura em Camadas

### 2.1 Grafo da FSM
Arquivo: state_machine/rta.py

Responsabilidade:
- Declarar estados.
- Declarar transicoes.
- Declarar guards (conditions/unless).
- Declarar callbacks de entrada em estados (on_enter).
- Executar a primeira transicao valida por ciclo via metodo next_state.

### 2.2 Modelo de Estado e Acoes
Arquivo: state_machine/rta_model.py

Responsabilidade:
- Guardar flags e contadores da FSM.
- Implementar guards de transicao.
- Implementar acoes de hardware (conectar robo, ligar/desligar motor).
- Implementar acoes de estado via hooks injetaveis.

### 2.3 Bootstrap de Execucao
Arquivo: state_machine/run_rta_fsm.py

Responsabilidade:
- Ler argumentos de execucao.
- Instanciar componentes reais.
- Injetar hooks no modelo.
- Criar a maquina Rta(model).
- Rodar loop principal ate done ou error.
- Limpar recursos no final.

## 3. Componentes Reais Integrados
Arquivo: state_machine/run_rta_fsm.py

Instanciados no bootstrap:
1. Denso (adaptador do robo).
2. Mobile (feedback de toque via ADB).
3. RobotCamera (captura de frame).
4. MarkerDetector (deteccao ArUco).
5. CoordinateTransform (transformacao imagem -> robo).
6. AutoAlignment (alinhamento XY/Z).
7. MarkerTouchController (toque e swipe).

## 4. Variaveis de Estado Principais
Arquivo: state_machine/rta_model.py

Flags:
- robot_connected_flag
- motor_on_flag
- camera_on_flag
- markers_found_flag
- aligned_flag
- touch_ok_flag
- swipe_executed_flag

Contadores:
- detect_markers_attempts
- error_touch
- final_result_failures
- connect_robot_attempt
- motor_on_attempt

Controle de sequencia:
- marker_index
- num_markers
- final_result (none/success/failure)

## 5. Estados da FSM
Arquivo: state_machine/rta.py

Estados declarados:
1. idle
2. connect_robot
3. motor_on
4. move_to_r_o_i
5. camera_on
6. detect_markers
7. align_with_markers
8. touch_marker
9. check_touch
10. reset_markers
11. generate_map
12. swipe_borders
13. safe_pose
14. read_final_marker
15. return_to_start
16. save_map
17. motor_off
18. done
19. error

## 6. Callbacks on_enter por Estado
Arquivo: state_machine/rta.py

Estados com acao de entrada:
- connect_robot -> connect_robot_action
- motor_on -> turn_motor_on_action
- move_to_r_o_i -> move_to_roi_action
- camera_on -> camera_on_action
- detect_markers -> detect_markers_action
- align_with_markers -> align_with_markers_action
- touch_marker -> touch_marker_action
- check_touch -> check_touch_action
- reset_markers -> reset_markers_action
- generate_map -> generate_map_action
- swipe_borders -> swipe_borders_action
- safe_pose -> safe_pose_action
- read_final_marker -> read_final_marker_action
- return_to_start -> return_to_start_action
- save_map -> save_map_action
- motor_off -> turn_motor_off_action

## 7. Fluxo Detalhado de Transicoes
Arquivo: state_machine/rta.py

### 7.1 Inicializacao e preparo
1. idle -> connect_robot
2. connect_robot -> motor_on se robot_connected for true.
3. connect_robot -> connect_robot (self-loop) enquanto nao conectar e nao atingir maximo.
4. connect_robot -> error se connect_robot_attempts_gte_max.
5. motor_on -> move_to_r_o_i se motor_on for true.
6. motor_on -> motor_on (self-loop) enquanto nao ligar e nao atingir maximo.
7. motor_on -> error se motor_on_attempts_gte_max.

### 7.2 Visao e alinhamento
1. move_to_r_o_i -> camera_on se motor_on for true.
2. camera_on -> detect_markers.
3. detect_markers -> align_with_markers se camera_on and markers_found.
4. detect_markers -> detect_markers enquanto camera_on and not markers_found.
5. detect_markers -> error se detect_markers_attempts_gte_twenty.
6. align_with_markers -> touch_marker se markers_found.

### 7.3 Toques e validacao
1. touch_marker -> check_touch se aligned and marker_index < num_markers.
2. check_touch -> touch_marker se touch_ok and marker_index < num_markers - 1.
3. check_touch -> generate_map se touch_ok and marker_index == num_markers - 1.
4. check_touch -> reset_markers se not touch_ok.
5. check_touch -> error se error_touch_gte_fifteen.
6. reset_markers -> move_to_r_o_i.

### 7.4 Finalizacao
1. generate_map -> swipe_borders se marker_index == num_markers.
2. swipe_borders -> safe_pose.
3. safe_pose -> read_final_marker se swipe_executed.
4. read_final_marker -> save_map se final_result_is_success.
5. read_final_marker -> return_to_start se final_result_is_failure.
6. read_final_marker -> error se final_result_failures_gte_fifteen.
7. return_to_start -> move_to_r_o_i (com reset de flags e indice).
8. save_map -> motor_off.
9. motor_off -> done.

## 8. Como o Bootstrap Liga Mundo Real com FSM
Arquivo: state_machine/run_rta_fsm.py

Hooks injetados no modelo:
- camera_on_fn
- detect_markers_fn
- align_with_markers_fn
- touch_marker_fn
- check_touch_fn
- reset_markers_fn
- swipe_borders_fn
- safe_pose_fn
- read_final_marker_fn
- return_to_start_fn

Resumo do que cada hook faz:
1. camera_on_fn: valida captura de frame.
2. detect_markers_fn: detecta ids/corners, refina corners e monta marker_infos.
3. align_with_markers_fn: calibra distancia quando necessario e executa approach.
4. touch_marker_fn: executa toque no marcador de marker_index.
5. check_touch_fn: aguarda feedback real de toque do dispositivo.
6. reset_markers_fn: toca no centro da tela e limpa cache de runtime.
7. swipe_borders_fn: gera pontos de borda e executa swipe continuo.
8. safe_pose_fn: move o robo para safe pose.
9. read_final_marker_fn: le marcador final e converte em success/failure.
10. return_to_start_fn: toca no centro para voltar e limpa runtime.

## 9. Runtime Compartilhado no Bootstrap
Arquivo: state_machine/run_rta_fsm.py

Estrutura runtime:
- markers: lista de marcadores detectados no ciclo atual.
- z_touch: altura de toque calculada no alinhamento.

Uso:
- detect_markers_fn atualiza runtime markers.
- align_with_markers_fn atualiza runtime z_touch.
- touch_marker_fn, swipe_borders_fn, reset_markers_fn e return_to_start_fn consomem runtime.

## 10. Regras de Tentativa e Falha
Arquivo: state_machine/rta_model.py e state_machine/rta.py

Conexao:
- max_connect_robot_attempts define limite.
- self-loop em connect_robot incrementa tentativa.
- ao sucesso, contador reseta.

Motor:
- max_motor_on_attempts define limite.
- self-loop em motor_on incrementa tentativa.
- ao sucesso, contador reseta.

Deteccao:
- detect_markers_attempts cresce na transicao de repeticao.
- limite de erro em 20 tentativas.

Toque:
- error_touch cresce quando check_touch falha e vai para reset_markers.
- limite de erro em 15 falhas.

Resultado final:
- final_result_failures cresce em falha final e retentativa.
- limite global de falhas finais em 15.

## 11. Loop Principal de Execucao
Arquivo: state_machine/run_rta_fsm.py

Sequencia:
1. machine = Rta(model)
2. while state not in done/error:
3. machine.next_state()
4. aguarda loop_delay
5. interrompe se max_steps for atingido

Saida:
- retorna 0 para done.
- retorna 1 para error ou interrupcao por max_steps.

## 12. Limpeza de Recursos
Arquivo: state_machine/run_rta_fsm.py

No final da execucao:
1. device.stop()
2. camera.release()
3. robot.disconnect()

Cada chamada e protegida por try/except para evitar falha de cleanup.

## 13. Parametros de Execucao (CLI)
Arquivo: state_machine/run_rta_fsm.py

Argumentos:
- --workspace
- --control
- --options
- --num-markers
- --loop-delay
- --max-steps
- --touch-timeout

Exemplo:
python state_machine/run_rta_fsm.py --workspace YOUR_WORKSPACE --control YOUR_CONTROL --options "" --num-markers 4 --loop-delay 0.05 --max-steps 5000 --touch-timeout 3

## 14. Dependencias de Configuracao
Arquivo: config.py

Lidos pelo bootstrap:
- CAMERA_CONFIG
- CAMERA_INTRINSICS
- COORDINATE_MAPPING
- COORDINATE_SCALE
- TOUCH_CONFIG
- FINAL_SUCCESS_MARKER_ID
- FINAL_FAILURE_MARKER_ID

## 15. Checklist de Validacao em Campo

Antes de rodar:
1. Robo responde a connect/motor_on/motor_off.
2. Camera retorna frame valido.
3. ADB conectado e feedback de toque funcional.
4. IDs finais configurados corretamente.

Durante o teste:
1. Confirmar transicao idle -> connect_robot.
2. Confirmar connect_robot -> motor_on dentro do limite.
3. Confirmar deteccao de marcadores no estado detect_markers.
4. Confirmar incremento de marker_index apos toques validados.
5. Confirmar execucao de swipe e ida para safe_pose.
6. Confirmar leitura de resultado final.

Em falha:
1. Verificar qual limite foi atingido (connect, motor, detect, touch, final).
2. Verificar logs de hooks reais no bootstrap.
3. Verificar alinhamento/calibracao de camera e transformacao.

## 16. Resumo Executivo
A FSM esta corretamente separada em:
1. Regras de navegacao (rta.py).
2. Estado e comportamento (rta_model.py).
3. Integracao operacional e runtime (run_rta_fsm.py).

Com isso, o sistema permite evoluir comportamento fisico sem alterar o grafo principal da FSM e facilita depuracao por camada.
