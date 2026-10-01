@echo off
REM ============================================================
REM  Tao lai loi tat "AI Audio Studio" tren Desktop
REM  Dung khi da cai xong nhung CHUA thay icon tren Desktop
REM  (vd Desktop bi OneDrive chuyen huong). Nhap dup file nay.
REM ============================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"
set "APPDIR=%cd%"
if "%VIENEU_PORT%"=="" set "VIENEU_PORT=8001"
set "URL=http://127.0.0.1:%VIENEU_PORT%"

echo Tao loi tat tren Desktop...

REM 1) Launcher trong thu muc app
set "LAUNCHER=%APPDIR%\VieNeu-Studio-launcher.bat"
(
  echo @echo off
  echo cd /d "%APPDIR%"
  echo set "PATH=%%USERPROFILE%%\.local\bin;%%USERPROFILE%%\.cargo\bin;%%PATH%%"
  echo set "VIENEU_PORT=%VIENEU_PORT%"
  echo start "" cmd /c "ping -n 9 127.0.0.1 ^>nul ^& start %URL%"
  echo uv run vieneu-studio
) > "%LAUNCHER%"

REM 2) Shortcut .lnk tren Desktop THAT (ho tro OneDrive). Loi thi tu copy .bat.
set "ICON=%APPDIR%\webapp\static\favicon.ico"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $d=[Environment]::GetFolderPath('Desktop'); try { $w=New-Object -ComObject WScript.Shell; $s=$w.CreateShortcut((Join-Path $d 'AI Audio Studio.lnk')); $s.TargetPath='%LAUNCHER%'; $s.WorkingDirectory='%APPDIR%'; if (Test-Path '%ICON%') { $s.IconLocation='%ICON%' }; $s.Description='AI Audio Studio - Vietnamese TTS'; $s.Save(); Write-Host ('   OK: Da tao loi tat tai ' + $d) } catch { Copy-Item '%LAUNCHER%' (Join-Path $d 'AI Audio Studio.bat') -Force; Write-Host '   OK: Da tao ban .bat tren Desktop (fallback).' }"

echo.
echo Xong! Kiem tra icon "AI Audio Studio" tren Desktop.
pause
endlocal
