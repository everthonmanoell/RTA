<#
Script de teste rápido da FSM até um estado alvo (padrão: move_to_roi).

Como usar (na raiz do repositório):
    .\scripts\run_move_to_roi_test.ps1

Quando o IP mudar, atualize estes parâmetros:
    -RobotServerIp  : IP do controlador/robô Denso (usado em --options "Server=...")
    -PythonServerIp : IP que o app Android usa para enviar parâmetros para o Python.
                      Com `adb reverse`, deixe 127.0.0.1.

Exemplo completo:
    .\scripts\run_move_to_roi_test.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.17.128" -PythonServerIp "127.0.0.1"
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$WorkspaceName = "RTA_WORKSPACE",

    [Parameter(Mandatory = $false)]
    [string]$ControlName = "rta",

    [Parameter(Mandatory = $false)]
    # IP do Denso virtual/real (lado Python -> robô)
    [string]$RobotServerIp = "192.168.160.225",

    [Parameter(Mandatory = $false)]
    [ValidateSet("flat", "foldable", "one", "two", "three", "six", "seven", "eight")]
    [string]$DeviceType = "flat",

    [Parameter(Mandatory = $false)]
    # IP que o Android usa para conectar no listener Python (lado app -> Python)
    [string]$PythonServerIp = "127.0.0.1",

    [Parameter(Mandatory = $false)]
    # Porta do listener Python em utils/receive_marker_params.py
    [int]$PythonServerPort = 50605,

    [Parameter(Mandatory = $false)]
    [ValidateSet("connect_robot", "motor_on", "move_to_roi", "camera_on", "detect_markers", "align_with_markers", "touch_marker", "check_touch", "generate_map")]
    [string]$StopAtState = "align_with_markers",

    [Parameter(Mandatory = $false)]
    [int]$MaxSteps = 120,

    [Parameter(Mandatory = $false)]
    [double]$LoopDelay = 0.05,

    [Parameter(Mandatory = $false)]
    [switch]$ShowCameraPreview
)

if ($args -contains '--show-camera-preview' -or $args -contains '-show-camera-preview') {
    $ShowCameraPreview = $true
}

$ShowCameraPreview = [bool]$ShowCameraPreview

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "[1/5] Limpando ADB e detectando dispositivo USB..."
# 1. Mata conexões wireless/TCP pendentes que causam o erro "more than one device"
adb disconnect | Out-Null
Start-Sleep -Seconds 1

# 2. Pega o serial correto
$devicesOutput = adb devices
$lines = $devicesOutput -split "`r`n"
$targetSerial = ""

foreach ($line in $lines) {
    if ($line -match "^([^\s]+)\s+device$") {
        $serial = $matches[1]
        # Ignora conexões IP/Wireless (que têm ":" ou começam com "adb-")
        if (-not ($serial -match ":" -or $serial -match "^adb-")) {
            $targetSerial = $serial
            break
        }
    }
}

if ($targetSerial -eq "") {
    Write-Error "Erro: Nenhum dispositivo Android detectado via USB!"
    exit 1
}

Write-Host "--> Dispositivo alvo selecionado: $targetSerial"

Write-Host "[2/5] Configurando adb reverse para tcp:$PythonServerPort..."
# Usa o serial específico (-s) para evitar qualquer ambiguidade
adb -s $targetSerial reverse "tcp:$PythonServerPort" "tcp:$PythonServerPort"

Write-Host "[3/5] Forçando restart do app RTA..."
adb -s $targetSerial shell am force-stop com.example.rta

# Inicia o app em background passando o Serial
$startAppJob = Start-Job -ScriptBlock {
    param($appIp, $appPort, $deviceType, $serial)
    Start-Sleep -Seconds 1
    adb -s $serial shell am start -S -n com.example.rta/.MainActivity --es python_server_ip $appIp --ei python_server_port $appPort --es device_type $deviceType
} -ArgumentList $PythonServerIp, $PythonServerPort, $DeviceType, $targetSerial

Write-Host "[4/5] Executando FSM até '$StopAtState'..."
$markerCountByDeviceType = @{
    "flat" = 4
    "foldable" = 8
    "one" = 1
    "two" = 2
    "three" = 3
    "six" = 6
    "seven" = 7
    "eight" = 8
}
$numMarkers = 4
if ($markerCountByDeviceType.ContainsKey($DeviceType)) {
    $numMarkers = [int]$markerCountByDeviceType[$DeviceType]
}

$env:RTA_DEVICE_TYPE = $DeviceType
$env:RTA_NUM_MARKERS = "$numMarkers"

$cmd = @(
    "run",
    "python",
    "state_machine/run_rta_fsm.py",
    "--workspace", $WorkspaceName,
    "--control", $ControlName,
    "--device-type", $DeviceType,
    "--num-markers", "$numMarkers",
    "--options", "Server=$RobotServerIp",
    "--stop-at-state", $StopAtState,
    "--max-steps", "$MaxSteps",
    "--loop-delay", "$LoopDelay"
)

if ($ShowCameraPreview) {
    $cmd += "--show-camera-preview"
}

& poetry @cmd
$pythonExitCode = $LASTEXITCODE

Write-Host "[5/5] Resultado do start do app:"
Receive-Job -Job $startAppJob -Wait | Out-String | Write-Host
Remove-Job -Job $startAppJob -Force

if ($pythonExitCode -ne 0) {
    Write-Error "FSM finalizou com exit code $pythonExitCode"
}

Write-Host "Teste finalizado com sucesso (exit code 0)."