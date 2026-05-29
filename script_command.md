.\scripts\run_fsm.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -DeviceType "flat" -StopAtState "align_with_markers" -MaxSteps 120


new execute command:
.\scripts\run_fsm.ps1 `
-WorkspaceName "RTA_WORKSPACE" `
-ControlName "rta" `
-RobotServerIp "192.168.160.225" `
-DeviceType "flat" `
-StopAtState "calibrate_z_touches" `
-MaxSteps 120


other comamand to run the fsm until the end:
.\scripts\run_fsm.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -DeviceType "flat" -MaxSteps 120

.\scripts\run_fsm.ps1 -WorkspaceName "RTA_WORKSPACE" -ControlName "rta" -RobotServerIp "192.168.160.225" -DeviceType flat -DeviceSide landscape