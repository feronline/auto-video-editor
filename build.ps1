# AutoEditer .exe build script
# Kullanim: .\build.ps1

$ErrorActionPreference = "Stop"

Write-Host "[1/4] venv aktif ediliyor..." -ForegroundColor Cyan
& .\venv\Scripts\Activate.ps1

Write-Host "[2/4] PyInstaller yukleniyor..." -ForegroundColor Cyan
pip install --upgrade pyinstaller -q

Write-Host "[3/4] Eski build temizleniyor..." -ForegroundColor Cyan
if (Test-Path "build")  { Remove-Item -Recurse -Force "build" }
if (Test-Path "dist")   { Remove-Item -Recurse -Force "dist" }
if (Test-Path "AutoEditer.spec") { Remove-Item -Force "AutoEditer.spec" }

Write-Host "[4/4] AutoEditer.exe derleniyor (1-3 dk surebilir)..." -ForegroundColor Cyan
pyinstaller `
    --name AutoEditer `
    --windowed `
    --noconfirm `
    --collect-all faster_whisper `
    --collect-all ctranslate2 `
    --collect-all onnxruntime `
    --collect-all tokenizers `
    --collect-all huggingface_hub `
    --collect-submodules PyQt6 `
    --hidden-import av `
    run.py

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "BASARILI" -ForegroundColor Green
    Write-Host "Calistirmak icin: .\dist\AutoEditer\AutoEditer.exe" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "NOT: ffmpeg.exe PATH'inde olmali (zaten var)." -ForegroundColor Gray
    Write-Host "NOT: Whisper modeli ilk calistirmada models\ klasorune iner (~1.5 GB)." -ForegroundColor Gray
} else {
    Write-Host "HATA: derleme basarisiz" -ForegroundColor Red
    exit 1
}
