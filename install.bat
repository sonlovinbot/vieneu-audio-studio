@echo off
REM ============================================================
REM  AI Audio Studio (Coachio Edition) - Bo cai Windows
REM  Nhap dup file nay de cai. Moi thu tu dong.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "APPDIR=%cd%"
if "%VIENEU_PORT%"=="" set "VIENEU_PORT=8001"
set "URL=http://127.0.0.1:%VIENEU_PORT%"

echo ============================================================
echo   AI AUDIO STUDIO (Coachio Edition) - CAI DAT
echo ============================================================
echo   Thu muc: %APPDIR%
echo.

REM 1) Cai uv neu chua co
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo - [1/3] Cai trinh quan ly uv...
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
) else (
  echo - [1/3] uv da co san.
)

REM 2) Cai thu vien (CPU/ONNX mac dinh)
echo - [2/3] Cai thu vien (co the mat vai phut lan dau)...
call uv sync
if errorlevel 1 ( echo LOI: uv sync that bai. & pause & exit /b 1 )

REM 3) Tao loi tat (shortcut .lnk) tren Desktop
echo - [3/3] Tao loi tat tren Desktop...
REM 3a) Launcher dat trong thu muc app (khong vut file .bat ra Desktop)
set "LAUNCHER=%APPDIR%\VieNeu-Studio-launcher.bat"
(
  echo @echo off
  echo cd /d "%APPDIR%"
  echo set "PATH=%%USERPROFILE%%\.local\bin;%%USERPROFILE%%\.cargo\bin;%%PATH%%"
  echo set "VIENEU_PORT=%VIENEU_PORT%"
  echo start "" cmd /c "ping -n 9 127.0.0.1 ^>nul ^& start %URL%"
  echo uv run vieneu-studio
) > "%LAUNCHER%"

REM 3b) Tao shortcut ".lnk" ten sach "AI Audio Studio" tren Desktop THAT.
REM     Dung [Environment]::GetFolderPath('Desktop') de bat dung ca khi Desktop
REM     bi OneDrive chuyen huong (loi pho bien khien khong thay icon).
REM Mot lenh PowerShell duy nhat: tao .lnk, neu loi thi tu copy .bat (fallback).
set "ICON=%APPDIR%\webapp\static\favicon.ico"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $d=[Environment]::GetFolderPath('Desktop'); try { $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'AI Audio Studio.lnk')); $s.TargetPath='%LAUNCHER%'; $s.WorkingDirectory='%APPDIR%'; if (Test-Path '%ICON%') { $s.IconLocation='%ICON%' }; $s.Description='AI Audio Studio - Vietnamese TTS'; $s.Save(); Write-Host ('   OK: Da tao loi tat AI Audio Studio tai ' + $d) } catch { Copy-Item '%LAUNCHER%' (Join-Path $d 'AI Audio Studio.bat') -Force; Write-Host '   OK: Da tao ban .bat tren Desktop (fallback).' }"

REM Autostart (tuy chon luc cai)
echo.
set /p AUTO="Ban co muon TU CHAY khi mo may? (y/N): "
if /i "%AUTO%"=="y" (
  set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
  set "BOOT=!STARTUP!\AI Audio Studio (autostart).bat"
  (
    echo @echo off
    echo cd /d "%APPDIR%"
    echo set "PATH=%%USERPROFILE%%\.local\bin;%%USERPROFILE%%\.cargo\bin;%%PATH%%"
    echo set "VIENEU_PORT=%VIENEU_PORT%"
    echo uv run vieneu-studio
  ) > "!BOOT!"
  echo    OK: Da bat tu chay khi mo may.
  echo    Tat tu chay: xoa file "!BOOT!"
)

echo.
echo ============================================================
echo   CAI DAT XONG!
echo   - Mo app: nhap icon "AI Audio Studio" tren Desktop
echo   - Hoac chay: uv run vieneu-studio
echo   - Giao dien: %URL%
echo ============================================================
echo.
set /p RUN="Khoi chay ngay bay gio? (Y/n): "
if /i not "%RUN%"=="n" (
  start "" cmd /c "ping -n 9 127.0.0.1 >nul & start %URL%"
  call uv run vieneu-studio
)
endlocal
