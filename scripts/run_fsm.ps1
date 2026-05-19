<#
Quick FSM test script to a target state (default: move_to_roi).

How to use (at repository root):
    .\scripts\run_move_to_roi_test.ps1

When the IP changes, update these parameters:
    -RobotServerIp  : IP of Denso virtual/real controller (used in --options "Server=...")
    -PythonServerIp : IP that Android app uses to send parameters to Python.
                      With `adb reverse`, leave 127.0.0.1.
    -RunCount       : Number of times the test should be executed in loop.

Complete example running 5 times:
    .\scripts\run_move_to_roi_test.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -RunCount 5
#>

param(
    [Parameter(Mandatory = $false)]
    [string]$WorkspaceName = "RTA_WORKSPACE",

    [Parameter(Mandatory = $false)]
    [string]$ControlName = "rta",

    [Parameter(Mandatory = $false)]
    # IP of Denso virtual/real (Python side -> robot)
    [string]$RobotServerIp = "192.168.160.225",

    [Parameter(Mandatory = $false)]
    [ValidateSet("flat", "foldable", "one", "two", "three", "six", "seven", "eight")]
    [string]$DeviceType = "flat",

    [Parameter(Mandatory = $false)]
    [ValidateSet("portrait", "landscape")]
    [string]$DeviceSide = "portrait",

    [Parameter(Mandatory = $false)]
    # IP that Android uses to connect to Python listener (app side -> Python)
    [string]$PythonServerIp = "127.0.0.1",

    [Parameter(Mandatory = $false)]
    # Port of Python listener in utils/receive_marker_params.py
    [int]$PythonServerPort = 50605,

    [Parameter(Mandatory = $false)]
    [ValidateSet("connect_robot", "motor_on", "move_to_roi", "camera_on", "detect_markers", "calibrate_z_touches", "generate_map", "swipe_borders", "safe_pose", "read_final_marker", "save_map")]
    [string]$StopAtState = "",

    [Parameter(Mandatory = $false)]
    [int]$MaxSteps = 120,

    [Parameter(Mandatory = $false)]
    [double]$LoopDelay = 0.05,

    [Parameter(Mandatory = $false)]
    [switch]$ShowCameraPreview,

    [Parameter(Mandatory = $false)]
    # New parameter: Number of times the script should run (Default: 1)
    [int]$RunCount = 1
)

if ($args -contains '--show-camera-preview' -or $args -contains '-show-camera-preview') {
    $ShowCameraPreview = $true
}

$ShowCameraPreview = [bool]$ShowCameraPreview

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

# Start the execution loop
for ($i = 1; $i -le $RunCount; $i++) {
    
    Write-Host "`n======================================================================" -ForegroundColor Cyan
    Write-Host " STARTING EXECUTION $i OF $RunCount" -ForegroundColor Cyan
    Write-Host "======================================================================" -ForegroundColor Cyan

    Write-Host "[1/5] Cleaning ADB and detecting USB device..."
    # 1. Kills pending wireless/TCP connections that cause "more than one device" error
    adb disconnect | Out-Null
    Start-Sleep -Seconds 1

    # 2. Get the correct serial
    $devicesOutput = adb devices
    $lines = $devicesOutput -split "`r`n"
    $targetSerial = ""

    foreach ($line in $lines) {
        if ($line -match "^([^\s]+)\s+device$") {
            $serial = $matches[1]
            # Ignore IP/Wireless connections (which have ":" or start with "adb-")
            if (-not ($serial -match ":" -or $serial -match "^adb-")) {
                $targetSerial = $serial
                break
            }
        }
    }

    if ($targetSerial -eq "") {
        Write-Error "Error: No Android device detected via USB!"
        exit 1
    }

    Write-Host "--> Target device selected: $targetSerial"

    Write-Host "[2/5] Configuring adb reverse for tcp:$PythonServerPort..."
    # Use specific serial (-s) to avoid any ambiguity
    adb -s $targetSerial reverse "tcp:$PythonServerPort" "tcp:$PythonServerPort"

    Write-Host "[3/5] Force restarting RTA app..."
    adb -s $targetSerial shell am force-stop com.example.rta

    # Start app in background passing the Serial
    $startAppJob = Start-Job -ScriptBlock {
        param($appIp, $appPort, $deviceType, $serial)
        Start-Sleep -Seconds 1
        adb -s $serial shell am start -S -n com.example.rta/.MainActivity --es python_server_ip $appIp --ei python_server_port $appPort --es device_type $deviceType
    } -ArgumentList $PythonServerIp, $PythonServerPort, $DeviceType, $targetSerial

    Write-Host "[4/5] Executing FSM until '$StopAtState'..."
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
        "--device-side", "$DeviceSide",
        "--options", "Server=$RobotServerIp",
        "--max-steps", "$MaxSteps",
        "--loop-delay", "$LoopDelay"
    )

    if ($ShowCameraPreview) {
        $cmd += "--show-camera-preview"
    }

    if ($StopAtState -ne "") {
        $cmd += @("--stop-at-state", $StopAtState)
    }

    & poetry @cmd
    $pythonExitCode = $LASTEXITCODE

    Write-Host "[5/5] App start result:"
    Receive-Job -Job $startAppJob -Wait | Out-String | Write-Host
    Remove-Job -Job $startAppJob -Force

    if ($pythonExitCode -ne 0) {
        Write-Error "FSM finished with exit code $pythonExitCode on execution $i of $RunCount"
    }

    Write-Host "Execution $i completed successfully." -ForegroundColor Green
    
    # Quick pause between executions for robot/camera to breathe (optional)
    if ($i -lt $RunCount) {
        Start-Sleep -Seconds 2
    }
}

Write-Host "`nAll $RunCount executions completed successfully!" -ForegroundColor Green