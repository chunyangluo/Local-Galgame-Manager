# Switch to the script's directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

$RUN_KEY_PATH = "Software\Microsoft\Windows\CurrentVersion\Run"
$RUN_VALUE_NAME = "LocalGalgameManager"
$desktopPath = [Environment]::GetFolderPath("Desktop")

function Test-Dependencies {
    param(
        [string[]]$RequiredModules
    )
    $missing = @()
    foreach ($mod in $RequiredModules) {
        $result = python -c "import $mod; print('OK')" 2>&1
        if ($LASTEXITCODE -ne 0) {
            $missing += $mod
        }
    }
    return $missing
}

try {
    Stop-Process -Name "LocalGalgameManager" -ErrorAction Stop
    Write-Host "Stopped running LocalGalgameManager process."
    Start-Sleep -Milliseconds 800
}
catch {
    Write-Host "No running LocalGalgameManager process found."
}

$buildId = Get-Date -Format "yyyyMMdd-HHmmss"
$distRoot = Join-Path $PSScriptRoot "dist\builds"
$workRoot = Join-Path $PSScriptRoot "build\pyinstaller"
$distPath = Join-Path $distRoot $buildId
$workPath = Join-Path $workRoot $buildId

New-Item -ItemType Directory -Path $distPath -Force | Out-Null
New-Item -ItemType Directory -Path $workPath -Force | Out-Null

Write-Host "Installing dependencies from requirements.txt..."
python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    exit $LASTEXITCODE
}

Write-Host "Verifying critical dependencies..."
$requiredModules = @(
    "PySide6", "requests", "loguru", "watchdog", "yaml", 
    "pyzipper", "lz4", "rich", "pydantic", "pydantic_settings",
    "fastapi", "uvicorn", "python_multipart", "cryptography"
)
$missing = Test-Dependencies -RequiredModules $requiredModules
if ($missing.Count -gt 0) {
    Write-Error "Missing required dependencies: $($missing -join ', ')"
    exit 1
}
Write-Host "All dependencies verified successfully."

$integrationsPath = Join-Path $PSScriptRoot "integrations"
if (-not (Test-Path $integrationsPath)) {
    Write-Error "Missing integrations directory: $integrationsPath"
    exit 1
}
Write-Host "Integrations directory found: $integrationsPath"

$iconPath = Join-Path $PSScriptRoot "app\assets\app_icon.ico"
if (-not (Test-Path $iconPath)) {
    Write-Error "Missing app icon: $iconPath"
    exit 1
}

$integrationsPath = Join-Path $PSScriptRoot "integrations"
python -m PyInstaller --noconfirm --windowed --name LocalGalgameManager `
    --icon "$iconPath" `
    --add-data "${iconPath};app/assets" `
    --add-data "${integrationsPath};integrations" `
    --collect-all loguru `
    --collect-all watchdog `
    --collect-all pyzipper `
    --collect-all lz4 `
    --collect-all pydantic `
    --collect-all pydantic_settings `
    --collect-all pyyaml `
    --collect-all fastapi `
    --collect-all uvicorn `
    --collect-all python_multipart `
    --collect-all cryptography `
    --collect-all rich `
    --collect-all starlette `
    --collect-all anyio `
    --collect-all httptools `
    --collect-all watchfiles `
    --collect-all websockets `
    --collect-all click `
    app/main.py --distpath "$distPath" --workpath "$workPath"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit $LASTEXITCODE
}

$builtDir = Join-Path $distPath "LocalGalgameManager"
$exePath = Join-Path $builtDir "LocalGalgameManager.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build output not found: $exePath"
    exit 1
}

# Stable output for shortcuts / manual launches (always points to the latest successful build).
$latestDir = Join-Path $distRoot "latest\LocalGalgameManager"
if (Test-Path (Split-Path $latestDir -Parent)) {
    Remove-Item (Split-Path $latestDir -Parent) -Recurse -Force
}
New-Item -ItemType Directory -Path $latestDir -Force | Out-Null
Copy-Item -Path (Join-Path $builtDir "*") -Destination $latestDir -Recurse -Force
$stableExePath = Join-Path $latestDir "LocalGalgameManager.exe"
$workingDirectory = $latestDir
Write-Host "Latest build copied to: $stableExePath"

$shortcutNames = @(
    "Local Galgame Manager.lnk",
    "本地 Galgame 管理器.lnk"
)
try {
    $shell = New-Object -ComObject WScript.Shell
    foreach ($name in $shortcutNames) {
        $shortcutPath = Join-Path $desktopPath $name
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $stableExePath
        $shortcut.WorkingDirectory = $workingDirectory
        $shortcut.IconLocation = "$stableExePath,0"
        $shortcut.Save()
        Write-Host "Desktop shortcut updated: $shortcutPath"
    }
}
catch {
    Write-Host "Note: Build succeeded but failed to create desktop shortcut (may be permission issue)."
    Write-Host "You can manually create a shortcut to: $stableExePath"
}

try {
    $regPath = "HKCU:\$RUN_KEY_PATH"
    if (Test-Path $regPath) {
        $existingValue = Get-ItemProperty -Path $regPath -Name $RUN_VALUE_NAME -ErrorAction SilentlyContinue
        if ($null -ne $existingValue) {
            Set-ItemProperty -Path $regPath -Name $RUN_VALUE_NAME -Value "`"$stableExePath`""
            Write-Host "Startup registry updated: $stableExePath"
        }
    }
}
catch {
    Write-Host "Note: Could not update startup registry (may not be enabled)"
}

Write-Host "Build output (timestamped): $exePath"
Write-Host "Build output (latest):       $stableExePath"
