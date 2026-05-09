# Stop running app if it's still active.
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

python -m PyInstaller --noconfirm --windowed --name LocalGalgameManager app/main.py --distpath "$distPath" --workpath "$workPath"
if ($LASTEXITCODE -ne 0) {
    Write-Error "PyInstaller build failed."
    exit $LASTEXITCODE
}

$exePath = Join-Path $distPath "LocalGalgameManager\LocalGalgameManager.exe"
if (-not (Test-Path $exePath)) {
    Write-Error "Build output not found: $exePath"
    exit 1
}

$desktopPath = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopPath "Local Galgame Manager.lnk"
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
    Write-Error "Build succeeded but failed to create desktop shortcut."
    exit 1
}

Write-Host "Build output: $exePath"
