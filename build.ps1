# Switch to the script's directory
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath

$RUN_KEY_PATH = "Software\Microsoft\Windows\CurrentVersion\Run"
$RUN_VALUE_NAME = "LocalGalgameManager"
$desktopPath = [Environment]::GetFolderPath("Desktop")

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

python -m pip install -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Error "Dependency installation failed."
    exit $LASTEXITCODE
}

$iconPath = Join-Path $PSScriptRoot "app\assets\app_icon.ico"
if (-not (Test-Path $iconPath)) {
    Write-Error "Missing app icon: $iconPath"
    exit 1
}

python -m PyInstaller --noconfirm --windowed --name LocalGalgameManager `
    --icon "$iconPath" `
    --add-data "${iconPath};app/assets" `
    app/main.py --distpath "$distPath" --workpath "$workPath"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit $LASTEXITCODE
}

$exePath = Join-Path $distPath "LocalGalgameManager\LocalGalgameManager.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build output not found: $exePath"
    exit 1
}

$shortcutPath = Join-Path $desktopPath "本地 Galgame 管理器.lnk"
$workingDirectory = Split-Path $exePath -Parent

try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $exePath
    $shortcut.WorkingDirectory = $workingDirectory
    $shortcut.IconLocation = "$exePath,0"
    $shortcut.Save()
    Write-Host "Desktop shortcut created/updated: $shortcutPath"
}
catch {
    Write-Host "Note: Build succeeded but failed to create desktop shortcut (may be permission issue)."
    Write-Host "You can manually create a shortcut to: $exePath"
}

try {
    $regPath = "HKCU:\$RUN_KEY_PATH"
    if (Test-Path $regPath) {
        $existingValue = Get-ItemProperty -Path $regPath -Name $RUN_VALUE_NAME -ErrorAction SilentlyContinue
        if ($null -ne $existingValue) {
            Set-ItemProperty -Path $regPath -Name $RUN_VALUE_NAME -Value "`"$exePath`""
            Write-Host "Startup registry updated: $exePath"
        }
    }
}
catch {
    Write-Host "Note: Could not update startup registry (may not be enabled)"
}

Write-Host "Build output: $exePath"
