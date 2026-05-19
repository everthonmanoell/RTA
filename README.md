# Robot Touch Alignment (RTA)

<div align="center">
  <img width="340" src="docs/rta_logo.png" alt="RTA logo">
  <h3 align="center">A Visuomotor Alignment System for Test Automation on Touch-Sensitive Devices</h3>
</div>

<div align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/Poetry-Dependency%20Management-60A5FA?logo=poetry&logoColor=white" alt="Poetry">
  <img src="https://img.shields.io/badge/OpenCV-Computer%20Vision-5C3EE8?logo=opencv&logoColor=white" alt="OpenCV">
  <img src="https://img.shields.io/badge/FSM-State%20Machine-111827" alt="FSM">
  <img src="https://img.shields.io/badge/DENSO-Robotics-0F766E" alt="DENSO">
</div>

## Overview

O projeto **Robot Touch Alignment (RTA)** e um módulo visuomotor para automacao de interacao com dispositivos touchscreen usando manipulador robotico DENSO, visao computacional e calibracao orientada por feedback de toque.

O sistema combina:

- controle robotico;
- alinhamento visual por marcadores;
- integracao com aplicativo Android;
- feedback de eventos de toque;
- e orquestracao por maquina de estados finitos (FSM),

para criar um fluxo de calibracao repetivel e portavel para testes automatizados em dispositivos moveis.

O **RTA** é um projeto para alinhamento, calibração e execução de toques em dispositivos móveis usando um robô Denso, câmera acoplada ao braço robótico e um fluxo automático baseado em visão computacional.

O sistema combina uma máquina de estados, drivers de câmera, drivers de dispositivo, alinhamento visual e integração com a aplicação Android para permitir execução repetível em diferentes máquinas.

Esta documentação apresenta a visão geral do projeto, a motivação, a instalação via Poetry, a instalação do app Android, o uso principal e a estrutura dos módulos.

- [Robot Touch Alignment (RTA)](#robot-touch-alignment-rta)
  - [Overview](#overview)
  - [Introdução](#introdução)
  - [Motivação](#motivação)
  - [Arquitetura do sistema](#arquitetura-do-sistema)
  - [Máquina de estados finitos (FSM)](#máquina-de-estados-finitos-fsm)
  - [Requisitos de hardware](#requisitos-de-hardware)
  - [Requisitos de software](#requisitos-de-software)
  - [Workspace Calibration](#workspace-calibration)
  - [Initial Physical Setup](#initial-physical-setup)
    - [End-Effector Offset Calibration](#end-effector-offset-calibration)
    - [Touch Convergence Height](#touch-convergence-height)
    - [ROI and Camera Calibration](#roi-and-camera-calibration)
      - [ROI Setup](#roi-setup)
      - [Camera Setup](#camera-setup)
  - [Region of Interest (ROI)](#region-of-interest-roi)
  - [Closed-Loop Touch Validation](#closed-loop-touch-validation)
  - [Spatial Interpolation Mapping](#spatial-interpolation-mapping)
  - [Device Orientation Support](#device-orientation-support)
  - [Operational Constraints and Recommendations](#operational-constraints-and-recommendations)
  - [Experimentally Validated Features](#experimentally-validated-features)
  - [Setup Assets](#setup-assets)
  - [Instalação](#instalação)
    - [Configuração do Ambiente](#configuração-do-ambiente)
    - [Instalação no projeto](#instalação-no-projeto)
    - [Aplicativo RTA](#aplicativo-rta)
    - [Aether SDK (dependência via Poetry)](#aether-sdk-dependência-via-poetry)
  - [Quick Start](#quick-start)
  - [Uso principal](#uso-principal)
  - [Referência dos módulos](#referência-dos-módulos)
    - [Camada de orquestração](#camada-de-orquestração)
    - [Camada de alinhamento](#camada-de-alinhamento)
    - [Camada de device e app](#camada-de-device-e-app)
    - [Camada de visão](#camada-de-visão)
    - [Utilitários](#utilitários)
  - [Troubleshooting](#troubleshooting)
    - [Problemas de conexão com o robô](#problemas-de-conexão-com-o-robô)
    - [Erro de múltiplos dispositivos no ADB](#erro-de-múltiplos-dispositivos-no-adb)
    - [Instabilidade na detecção de marcadores](#instabilidade-na-detecção-de-marcadores)
  - [Demonstrações visuais](#demonstrações-visuais)
  - [Boas Práticas](#boas-práticas)
  - [Conclusão](#conclusão)

## Introdução

O RTA foi desenvolvido para automatizar o alinhamento do robô em relação ao dispositivo móvel, usando a câmera acoplada para detectar marcadores visuais, estimar a pose do alvo e conduzir a rotina de toques que gera o mapa final do workspace. A proposta é transformar uma sessão física de calibração em um processo reproduzível, com validação visual, feedback do Android e persistência do mapa para uso futuro.

O fluxo principal do sistema envolve:

- inicialização da aplicação Android de teste;
- detecção de marcadores com a câmera do robô;
- alinhamento de rotação e posição;
- execução sequencial de toques;
- validação visual do resultado;
- geração de mapas e relatórios.

## Motivação

Este projeto surgiu para reduzir o atrito operacional de testes com dispositivos móveis utilizando da automações com robôs. Em vez de espalhar lógica de controle, visão e device management em scripts soltos, o RTA concentra essas responsabilidades em uma estrutura reutilizável e previsível.

Os principais objetivos são:

- facilitar a reprodução do setup em novas máquinas;
- simplificar a execução do fluxo principal com um único comando;
- manter o código organizado para integração com outros projetos;
- esconder complexidades do ORiN2 SDK e do DCOM atrás de módulos locais reutilizáveis;
- permitir que o processo de instalação seja feito com `poetry install`.

## Arquitetura do sistema

```text
Android App
  |
  v
ADB + Comunicação Socket
  |
  v
FSM em Python (RTA)
  |
  v
Camada de Visão + Alinhamento
  |
  v
Controlador do Robô DENSO
  |
  v
Execução de Toques
```

## Máquina de estados finitos (FSM)

Fluxo principal da FSM:

```text
idle
-> connect_robot
-> motor_on
-> move_to_roi
-> camera_on
-> detect_markers
-> calibrate_z_touches
-> generate_map
-> swipe_borders
-> safe_pose
-> read_final_marker
-> save_map
-> motor_off
-> done
```

Qualquer falha irrecuperável direciona o sistema para o estado `error`.

## Requisitos de hardware

- Robô DENSO com controladora acessível na rede;
- Dispositivo Android para execução do app RTA;
- Modelo 3D do end-effector, para encaixe da camera BRIO e do atuador final (disponíveis em `docs/rta_endeffector_model_3d/`);
- Câmera acoplada ao cabeçote ou ao end-effector do robô, com visão clara da área de trabalho;
- Suporte impresso em 3D, fixado no robô;
- Cabo USB para conexão do Android via ADB;
- Iluminação adequada para detecção confiável dos marcadores.

## Requisitos de software

- Python 3.11 ou superior;
- Poetry;
- ADB disponível no sistema (`adb` no PATH);
- ORiN2 SDK instalado e configurado;
- Dependência Aether já declarada no `pyproject.toml`.

## Workspace Calibration

Before executing the full calibration routine, an initial workspace calibration must be performed for each robot and physical setup.

This setup stage defines:

- the Region of Interest (ROI) where the device is expected to be positioned;
- the safe approach height for the end-effector;
- the touch convergence height used during the contact search routine;
- the camera framing area;
- and the alignment offsets of the custom end-effector.

These parameters significantly improve:

- touch convergence speed;
- alignment stability;
- marker detection reliability;
- and operational safety.

The calibration only needs to be repeated when:

- changing the robot;
- modifying the physical bench;
- replacing the end-effector;
- changing the camera mounting;
- or altering the workspace geometry.

## Initial Physical Setup

Before running the RTA workflow, the physical setup of the robot and end-effector must be calibrated.

Due to:

- 3D printing tolerances;
- camera mounting variations;
- actuator positioning differences;
- and workspace geometry,

some configuration parameters must be manually adjusted for each physical setup.

This calibration is fundamental to:

- improve touch convergence speed;
- reduce alignment residual error;
- improve operational safety;
- and preserve repeatability across executions.

The setup calibration is typically performed only once per:

- robot;
- end-effector;
- camera mount;
- or workspace geometry.

**Important:** The 3D models for the end-effector components are located in `docs/rta_endeffector_model_3d/`. You will need to download, review, and 3D-print these parts before proceeding with the physical setup. The recommendation is print in PETG or PLA filament type for better durability and precision.

### End-Effector Offset Calibration

The system assumes a fixed spatial offset between:

- the camera optical center;
- and the physical touch actuator.

These offsets are configured inside:

```python
config.py
```

Main parameters:

```python
TOUCH_FINGER_OFFSET_X = -30.1
TOUCH_FINGER_OFFSET_Y = 0.0
```

The nominal CAD-modeled distance between the camera center and the actuator is approximately:

```text
31.5 mm
```

However, due to:

- FDM 3D printing tolerances;
- assembly variations;
- mechanical deformation;
- and camera positioning differences,

**the real offset must be experimentally calibrated for every physical setup.**

The offset values are expressed in the robot Cartesian reference frame and represent the displacement between the camera optical center and the physical touch actuator tip.

This calibration is mandatory whenever:

- a new end-effector is installed;
- the camera mount changes;
- the actuator position changes;
- the robot setup changes;
- or the workspace geometry is modified.

Incorrect X/Y offset calibration may cause:

- systematic touch displacement;
- marker alignment drift;
- unstable convergence behavior;
- or inaccurate interpolation mapping.

### Touch Convergence Height

The approach height before physical contact is configured through:

```python
Z_OFFSET_BEFORE_TOUCH = 20.0
```

The calibrated touch plane is defined by:

```python
Z_TOUCH = 260.98
```

**The `Z_TOUCH` value must be calibrated for every robot and workspace setup.**

This calibration is mandatory because the physical contact plane varies according to:

- workspace height;
- device thickness;
- support geometry;
- bench inclination;
- actuator assembly;
- and end-effector mounting.

These parameters directly affect:

- touch convergence stability;
- touch detection speed;
- and screen safety.

Incorrect values may cause:

- failed capacitive touches;
- excessive pressure on the display;
- unstable touch detection;
- or mechanical damage to the device surface.

### ROI and Camera Calibration

**Camera and ROI calibration are both mandatory for every physical setup.**

#### ROI Setup

The Region of Interest (ROI) must be defined for each robot and workspace:

The ROI defines:

- where the device is expected to appear;
- the initial robot approach region;
- and the visual acquisition area.

The smartphone must remain fully visible inside the ROI during execution.

#### Camera Setup

Camera calibration depends on the camera hardware:

**For BRIO cameras:**

1. Download and install Logi Tune (or equivalent software for your camera).
2. Use Logi Tune to calibrate focus, exposure, white balance, and other optical parameters.
3. Once tuned, run the configuration extraction script:

```bash
python utils/get_camera_configurations.py
```

4. This script reads the camera's current settings and outputs them.
5. Copy the output values to `config.py` and update:

```python
CAMERA_CALIBRATION_CONFIG = {
    "auto_focus": <value>,
    "fixed_focus": <value>,
    "auto_exposure": <value>,
    "fixed_exposure": <value>,
    "auto_white_balance": <value>,
    "white_balance_temperature": <value>,
}
```

**For other cameras:**

Calibrate according to your camera's software or control API, and update `CAMERA_CALIBRATION_CONFIG` with the resulting values.

This calibration is mandatory whenever:

- a new camera is installed;
- the camera lens is changed;
- environmental lighting conditions change significantly;
- or the camera mounting position changes.

## Region of Interest (ROI)

The Region of Interest (ROI) represents the predefined physical workspace where the smartphone is expected to be positioned during calibration.

The robot initially moves to this region before starting:

- visual detection;
- alignment;
- touch convergence;
- and interpolation mapping.

Correct ROI configuration is critical for:

- stable marker detection;
- collision avoidance;
- and touch convergence performance.

## Closed-Loop Touch Validation

The RTA system validates physical interactions using Android touch events as ground truth.

While the robot performs physical contact on the screen, the Android operating system reports the exact touch coordinates through ADB (`getevent`).

This creates a deterministic closed-loop validation mechanism capable of:

- confirming physical contact;
- validating touch precision;
- detecting capacitive failures;
- and improving operational safety.

## Spatial Interpolation Mapping

Instead of relying exclusively on projective computer vision, the RTA system generates a physical interpolation map from real touch-contact points.

The robot performs validated touches on fiducial markers and records the exact Cartesian coordinates of each contact.

Using these anchors, the system reconstructs a 3D interpolation mesh capable of:

- compensating device inclinations;
- compensating uneven surfaces;
- preserving touch precision;
- and improving repeatability during future interactions.

## Device Orientation Support

The current RTA implementation supports multiple physical device orientations.

The device orientation is configured through:

```powershell
-DeviceSide "portrait"
```

or

```powershell
-DeviceSide "landscape"
```

Unlike previous versions of the system, the smartphone orientation is no longer fixed relative to the robot.

The only requirement is that:

- the device remains fully visible inside the ROI;
- the fiducial markers remain detectable by the camera;
- and the selected orientation matches the physical placement of the device.

## Operational Constraints and Recommendations

The RTA system depends on stable visual and mechanical conditions to ensure reliable alignment.

For best results:

- avoid direct perpendicular lighting on the device screen;
- avoid strong reflections on glossy displays;
- maintain the device fully inside the camera ROI;
- ensure the end-effector remains perpendicular to the screen surface;
- verify that the custom touch actuator preserves capacitive conductivity.

The system was experimentally validated under:

- multiple Android devices;
- tilted surfaces;
- curved-edge displays;
- and varying screen dimensions.

However, extreme reflective conditions and excessive workspace inclination may reduce marker detection reliability.

## Experimentally Validated Features

The current RTA implementation was experimentally validated with:

- multiple Android devices;
- curved-edge displays;
- tilted surfaces;
- dynamic ArUco generation;
- closed-loop touch validation via ADB;
- sub-millimeter repeatability;
- and automatic interpolation-based calibration.

The system also demonstrated:

- successful operation under surface inclinations;
- repeatable touch convergence;
- and reproducible calibration workflows.

## Setup Assets

For clearer onboarding and calibration documentation, it is recommended to keep setup assets under:

```text
docs/setup/
```

Suggested files:

```text
docs/setup/
  roi_example.png
  touch_offset.png
  end_effector_measurement.png
  workspace_example.png
```

These assets help document the physical setup, the ROI framing, and the measured end-effector offsets for each robot/workspace combination.

## Instalação

Com os requisitos atendidos, siga os passos abaixo para preparar o ambiente.

### Configuração do Ambiente

O repositório já está preparado para instalação via Poetry. O Aether é uma dependência declarada no `pyproject.toml`, então ele é resolvido automaticamente junto com as demais dependências do projeto.

Isso significa que, ao rodar `poetry install`, o Poetry instalará tudo o que o projeto precisa sem etapas manuais adicionais para essa dependência.

### Instalação no projeto

```bash
poetry install
```

Após a instalação, o ambiente estará pronto para executar o fluxo principal do projeto.

### Aplicativo RTA

O app Android do RTA também precisa estar instalado no celular para que a máquina de estados execute corretamente.

O projeto já inclui um script dedicado para fazer o build do APK e instalá-lo no dispositivo via ADB:

```powershell
.\scripts\install_rta_app.ps1
```

Esse script:

- compila o APK do app Android;
- instala o APK no celular conectado;
- deixa o artefato disponível em `RTA_app/app/build/outputs/apk/debug/app-debug.apk`.

Se preferir fazer manualmente, o equivalente é:

```bash
cd RTA_app
./gradlew installDebug
```

Depois disso, basta executar o fluxo principal do RTA.

### Aether SDK (dependência via Poetry)

O Aether SDK é uma dependência já declarada no `pyproject.toml` e é resolvida automaticamente pelo Poetry durante a instalação do projeto.

Em outras palavras, não há nenhuma etapa adicional de empacotamento ou cópia manual: basta executar `poetry install`.

Se a versão da dependência mudar, a atualização deve ser feita no `pyproject.toml` e, quando aplicável, no `poetry.lock`.

## Quick Start

1. Conecte o dispositivo Android via USB.
2. Conecte a controladora DENSO na rede.
3. Verifique a conexão ADB.
4. Instale as dependências com Poetry.
5. Execute o script principal da FSM.

Comandos sugeridos:

```powershell
adb devices
poetry install
.\scripts\install_rta_app.ps1
.\scripts\run_fsm.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -DeviceType "flat" -DeviceSide "portrait" -MaxSteps 120
```

## Uso principal

Depois de instalar as dependências e o app RTA, o fluxo de uso mais comum é executar a máquina de estados principal.

Exemplo usando o script PowerShell do projeto:

```powershell
.\scripts\run_fsm.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -DeviceType "flat" -DeviceSide "portrait" -MaxSteps 120
```

Antes de executar, ajuste estes dois parâmetros para o seu cenário:

- `-RobotServerIp`: IP do robô Denso que você realmente vai usar;
- `-DeviceSide`: orientação do celular em relação ao robô, com valores como `portrait` ou `landscape`.

Você também pode executar diretamente o módulo principal com Poetry:

```bash
poetry run python state_machine/run_rta_fsm.py \
  --workspace RTA_WORKSPACE \
  --control rta \
  --device-type flat \
  --device-side portrait \
  --options "Server=192.168.160.225" \
  --max-steps 120
```

No comando acima, o valor de `Server=...` precisa ser o IP do Denso em uso, e `--device-side` precisa refletir a orientação física do celular em relação ao robô.

O mapa gerado pelo RTA é o produto final da execução. Por padrão, ele fica em:

```text
test_results/<device_model_ou_device_type>/physical_calibration_map_<timestamp>_<epoch>.json
```

Se `DEVICE_MODEL` não estiver definido, a pasta usa o `device_type`. Esse caminho pode ser alterado com `--metrics-dir`.

Em geral, o fluxo esperado é:

1. iniciar o aplicativo Android;
2. conectar ao robô;
3. ligar os motores;
4. mover para ROI;
5. detectar marcadores;
6. alinhar rotação e posição;
7. executar a sequência de toques;
8. salvar o mapa final;
9. desligar o robô com segurança.

## Referência dos módulos

O projeto é organizado em módulos/camadas para manter a responsabilidade de cada parte clara.

### Camada de orquestração

- `state_machine/`: contém a máquina de estados principal do RTA;
- `state_machine/run_rta_fsm.py`: ponto de entrada para a execução completa.

### Camada de alinhamento

- `drivers/alignment/marker_detector.py`: detecção e análise de marcadores;
- `drivers/alignment/rotation_alignment.py`: alinhamento de rotação (RZ);
- `drivers/alignment/auto_alignment.py`: alinhamento automático de XYZ.

### Camada de device e app

- `drivers/device/app_manager.py`: controle da aplicação Android;
- `drivers/device/mobile.py`: leitura de eventos de toque e validações de device;
- `drivers/device/rta_integrated_controller.py`: orquestra a sessão completa.

### Camada de visão

- `drivers/vision/robot_camera.py`: captura da câmera do robô;
- `drivers/vision/vision.py`: utilitários e scripts de visão.

### Utilitários

- `utils/coordinate_transform.py`: conversões entre coordenadas de câmera e robô;
- `utils/marker_touch_controller.py`: apoio para execução de toques;
- `utils/calibration_map_exporter.py`: exportação de mapas de calibração.

## Troubleshooting

### Problemas de conexão com o robô

```powershell
ping <robot_ip>
```

Confirme que o IP usado em `-RobotServerIp` e em `Server=...` corresponde ao DENSO em uso.

### Erro de múltiplos dispositivos no ADB

```powershell
adb disconnect
adb devices
```

Use apenas um dispositivo USB ativo durante a sessão de calibração.

### Instabilidade na detecção de marcadores

- verifique as condições de iluminação;
- verifique o foco da câmera;
- verifique o posicionamento de ROI;
- confirme se o celular está na orientação correta (`DeviceSide`).

## Demonstrações visuais

Para elevar a legibilidade técnica do projeto, recomenda-se adicionar nesta seção:

- GIF do sistema completo em execução (robô + app + toques);
- screenshot da tela de marcadores ArUco;
- screenshot do app Android RTA;
- imagem da ROI detectada;
- diagrama visual da FSM.

Exemplo de estrutura sugerida:

```text
docs/images/
  system_run.gif
  aruco_detection.png
  rta_app_screen.png
  roi_debug.png
  fsm_diagram.png
```

## Boas Práticas

- Sempre desligue os motores e desconecte o robô ao final da execução.
- Mantenha a dependência Aether alinhada com o `pyproject.toml`.
- Use `poetry install` para reproduzir o ambiente em outras máquinas.
- Antes de rodar uma sessão real, valide ADB, câmera e conexão com a controladora.
- Se o app Android travar, reinicie a aplicação antes de iniciar uma nova sessão.
- Mantenha o `DeviceSide` correto para o dispositivo em uso (`portrait` ou `landscape`).

## Conclusão

O RTA fornece um módulo reproduzível e modular para interação robótica com dispositivos sensíveis ao toque.

Ao combinar visão computacional, alinhamento robótico, feedback de toque e máquina de estados finitos, o projeto viabiliza fluxos de automação mais confiáveis e portáteis para cenários de teste em dispositivos móveis.