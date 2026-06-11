# 脚本自动管理员提权
#Requires -RunAsAdministrator
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

function Test-ReleaseIntegrationTemplates {
    param(
        [string]$IntegrationsPath
    )

    $autoExtractTool = Get-ChildItem -Path $IntegrationsPath -Directory |
        Where-Object {
            (Test-Path (Join-Path $_.FullName "config\config.yaml")) -and
            (Test-Path (Join-Path $_.FullName "bin\7za.exe"))
        } |
        Select-Object -First 1
    if ($null -eq $autoExtractTool) {
        Write-Error "Missing auto-extract integration under: $IntegrationsPath"
        exit 1
    }

    $autoExtractConfigDir = Join-Path $autoExtractTool.FullName "config"
    $configPath = Join-Path $autoExtractConfigDir "config.yaml"
    $passwordsPath = Join-Path $autoExtractConfigDir "passwords.json"

    if (-not (Test-Path $configPath)) {
        Write-Error "Missing auto-extract config template: $configPath"
        exit 1
    }
    if (-not (Test-Path $passwordsPath)) {
        Write-Error "Missing auto-extract passwords template: $passwordsPath"
        exit 1
    }

    $configText = Get-Content $configPath -Raw -Encoding UTF8
    if ($configText -match '[A-Za-z]:\\') {
        Write-Error "Release config template contains local Windows paths: $configPath"
        exit 1
    }

    try {
        $passwordData = Get-Content $passwordsPath -Raw -Encoding UTF8 | ConvertFrom-Json
    }
    catch {
        Write-Error "Invalid passwords template JSON: $passwordsPath"
        exit 1
    }

    $passwordCount = @($passwordData.passwords).Count
    $successMapCount = @($passwordData.success_map.PSObject.Properties).Count
    $successCountsCount = @($passwordData.success_counts.PSObject.Properties).Count
    if ($passwordCount -gt 0 -or $successMapCount -gt 0 -or $successCountsCount -gt 0) {
        Write-Error "Release passwords template must be empty: $passwordsPath"
        exit 1
    }
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
Test-ReleaseIntegrationTemplates -IntegrationsPath $integrationsPath

$iconPath = Join-Path $PSScriptRoot "app\assets\app_icon.ico"
if (-not (Test-Path $iconPath)) {
    Write-Error "Missing app icon: $iconPath"
    exit 1
}

$helpImgPath = Join-Path $PSScriptRoot "app\assets\help-main-window.png"
$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--noconfirm",
    "--windowed",
    "--name", "LocalGalgameManager",
    "--icon", $iconPath,
    "--add-data", "${iconPath};app/assets"
)
if (Test-Path $helpImgPath) {
    $pyInstallerArgs += @("--add-data", "${helpImgPath};app/assets")
}

$pyInstallerArgs += @(
    "--add-data", "${integrationsPath};integrations",
    "--collect-all", "PySide6",
    "--collect-all", "PIL",
    "--collect-all", "requests",
    "--collect-all", "loguru",
    "--collect-all", "watchdog",
    "--collect-all", "pyzipper",
    "--collect-all", "lz4",
    "--collect-all", "pydantic",
    "--collect-all", "pydantic_settings",
    "--collect-all", "pyyaml",
    "--collect-all", "fastapi",
    "--collect-all", "uvicorn",
    "--collect-all", "python_multipart",
    "--collect-all", "cryptography",
    "--collect-all", "rich",
    "--collect-all", "starlette",
    "--collect-all", "anyio",
    "--collect-all", "httptools",
    "--collect-all", "watchfiles",
    "--collect-all", "websockets",
    "--collect-all", "click",
    "app/main.py",
    "--distpath", $distPath,
    "--workpath", $workPath
)

python @pyInstallerArgs

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

$latestDir = Join-Path $distRoot "latest\LocalGalgameManager"
if (Test-Path (Split-Path $latestDir -Parent)) {
    Remove-Item (Split-Path $latestDir -Parent) -Recurse -Force
}
New-Item -ItemType Directory -Path $latestDir -Force | Out-Null
Copy-Item -Path (Join-Path $builtDir "*") -Destination $latestDir -Recurse -Force
$stableExePath = Join-Path $latestDir "LocalGalgameManager.exe"
$workingDirectory = $latestDir
Write-Host "Latest build copied to: $stableExePath"

# ======================
# 快捷方式创建（已修复）
# ======================
try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcutPath = Join-Path $desktopPath "Local Galgame Manager.lnk"
    
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force -ErrorAction Stop
    }

    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $stableExePath
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.IconLocation = $stableExePath
    $shortcut.Save()

    Write-Host "✅ Desktop shortcut created successfully: $shortcutPath" -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Could not create desktop shortcut: $_" -ForegroundColor Yellow
    Write-Host "You can manually create a shortcut to: $stableExePath"
}

# ======================
# 开机自启（已修复）
# ======================
try {
    $regPath = "HKCU:\$RUN_KEY_PATH"
    if (!(Test-Path $regPath)) {
        New-Item -Path $regPath -Force | Out-Null
    }
    Set-ItemProperty -Path $regPath -Name $RUN_VALUE_NAME -Value "`"$stableExePath`""
    Write-Host "✅ Startup registry updated: $stableExePath" -ForegroundColor Green
}
catch {
    Write-Host "⚠️ Could not update startup registry: $_" -ForegroundColor Yellow
}

Write-Host "`n🎉 BUILD FULLY SUCCESSFUL!" -ForegroundColor Cyan
Write-Host "Timestamped build: $exePath"
Write-Host "Latest stable:    $stableExePath"