# ============================================================
#  AI Audio Studio — cài bằng 1 lệnh (Windows 10/11)
#
#    irm https://raw.githubusercontent.com/sonlovinbot/vieneu-audio-studio/main/install-online.ps1 | iex
#
#  Tải bộ cài mới nhất từ GitHub Releases về %USERPROFILE%\AI-Audio-Studio
#  rồi chạy install.bat. Tải bằng PowerShell nên không bị SmartScreen chặn.
#  Chạy lại lệnh này = cập nhật.
# ============================================================
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # tắt thanh tiến trình chậm của Invoke-WebRequest

$Repo = "sonlovinbot/vieneu-audio-studio"
$Dest = if ($env:VIENEU_INSTALL_DIR) { $env:VIENEU_INSTALL_DIR } else { Join-Path $HOME "AI-Audio-Studio" }
$Url  = "https://github.com/$Repo/releases/latest/download/AI-Audio-Studio-Windows.zip"
$Tmp  = Join-Path ([IO.Path]::GetTempPath()) ("aias-" + [guid]::NewGuid())

Write-Host "============================================================"
Write-Host "  AI Audio Studio - cai dat tu dong (Windows)"
Write-Host "  Phat trien boi Dang Huu Son - model VieNeu-TTS"
Write-Host "============================================================"
New-Item -ItemType Directory -Force -Path $Tmp | Out-Null
try {
    Write-Host "-> Tai bo cai moi nhat..."
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $Url -OutFile (Join-Path $Tmp "app.zip") -UseBasicParsing

    Write-Host "-> Giai nen vao: $Dest"
    Expand-Archive -Path (Join-Path $Tmp "app.zip") -DestinationPath $Tmp -Force
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Copy-Item -Path (Join-Path $Tmp "AI-Audio-Studio-Windows\*") -Destination $Dest -Recurse -Force
    Get-ChildItem -Path $Dest -Recurse -File | Unblock-File
} finally {
    Remove-Item -Recurse -Force $Tmp -ErrorAction SilentlyContinue
}

if ($env:VIENEU_NO_RUN) { Write-Host "OK: da giai nen (VIENEU_NO_RUN)."; return }
Write-Host ""
Push-Location $Dest
try { & cmd.exe /c "install.bat" } finally { Pop-Location }
