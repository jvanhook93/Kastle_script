# -----------------------------
# KastleApp Build Script (Safe)
# -----------------------------

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$distFolder = Join-Path $projectRoot "dist\KastleApp-win32-x64"
$backendScript = Join-Path $projectRoot "backend\app.py"
$backendDist = Join-Path $projectRoot "backend\dist"

Write-Host "🚀 Starting build process..." -ForegroundColor Cyan

# -----------------------------
# 1. Kill running processes
# -----------------------------
Write-Host "Stopping running KastleApp/Electron processes..." -ForegroundColor Yellow
Get-Process KastleApp,electron -ErrorAction SilentlyContinue | Stop-Process -Force

# -----------------------------
# 2. Delete old dist folder
# -----------------------------
if (Test-Path $distFolder) {
    Write-Host "Deleting old dist folder..." -ForegroundColor Yellow
    try {
        Remove-Item -Recurse -Force $distFolder
        Write-Host "✅ Dist folder deleted." -ForegroundColor Green
    } catch {
        Write-Host "⚠️ Could not delete dist folder. Check that no process is using it!" -ForegroundColor Red
        exit 1
    }
} else {
    Write-Host "No existing dist folder found." -ForegroundColor Green
}

# -----------------------------
# 3. Build backend EXE
# -----------------------------
Write-Host "Building backend EXE..." -ForegroundColor Yellow
if (-Not (Test-Path $backendDist)) { New-Item -ItemType Directory -Path $backendDist }

pyinstaller --onefile $backendScript --distpath $backendDist --workpath "$projectRoot\backend\build" --specpath "$projectRoot\backend\build"

Write-Host "✅ Backend EXE built at $backendDist" -ForegroundColor Green

# -----------------------------
# 4. Package Electron app
# -----------------------------
Write-Host "Packaging Electron app..." -ForegroundColor Yellow
npx electron-packager $projectRoot KastleApp --platform=win32 --arch=x64 --out $projectRoot\dist --overwrite

Write-Host "✅ Electron app packaged at $distFolder" -ForegroundColor Green
Write-Host "🎉 Build process complete!" -ForegroundColor Cyan
