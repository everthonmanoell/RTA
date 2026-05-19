param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot),

    [Parameter(Mandatory = $false)]
    [ValidateSet('Debug')]
    [string]$BuildVariant = 'Debug',

    [Parameter(Mandatory = $false)]
    [switch]$Clean,

    [Parameter(Mandatory = $false)]
    [switch]$Reinstall
)

$ErrorActionPreference = 'Stop'

$appDir = Join-Path $ProjectRoot 'RTA_app'
$gradlew = if ($IsWindows) { 'gradlew.bat' } else { './gradlew' }
$apkPath = Join-Path $appDir "app/build/outputs/apk/$($BuildVariant.ToLower())/app-$($BuildVariant.ToLower()).apk"

Write-Host '======================================================================' -ForegroundColor Cyan
Write-Host " Building and installing RTA app ($BuildVariant)" -ForegroundColor Cyan
Write-Host '======================================================================' -ForegroundColor Cyan

if ($Clean) {
    Write-Host '[1/4] Cleaning Android project...'
    Push-Location $appDir
    try {
        & $gradlew clean
    } finally {
        Pop-Location
    }
}

Write-Host '[2/4] Building APK...'
Push-Location $appDir
try {
    & $gradlew "assemble$BuildVariant"
} finally {
    Pop-Location
}

if (-not (Test-Path $apkPath)) {
    throw "APK not found at: $apkPath"
}

Write-Host "[3/4] Installing APK from: $apkPath"
$installArgs = @('install')
if ($Reinstall) {
    $installArgs += '-r'
}
$installArgs += $apkPath

& adb @installArgs

Write-Host '[4/4] Installation finished successfully.' -ForegroundColor Green
Write-Host "APK path: $apkPath" -ForegroundColor Green