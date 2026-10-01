@echo off
setlocal
echo ==================================================
echo   CREATE VENV FOR XPU (FOR INTEL ARC)
echo ==================================================

cd /d "%~dp0"
set VENV_NAME=.xpu_venv
set PYTHON_PATH=%VENV_NAME%\Scripts\python.exe

:: --- OPTION: XOA HOAC GIU VENV CU ---
if not exist %VENV_NAME% goto :CREATE_VENV

echo [?] Tim thay moi truong %VENV_NAME% dang ton tai.
echo [1] Xoa di tao lai tu dau (Clean Install)
echo [2] Giu lai va chi cap nhat thu vien (Update)
set /p opt="Chon (1 hoac 2): "

if "%opt%"=="1" (
    echo [+] Dang xoa moi truong cu...
    rmdir /s /q %VENV_NAME%
    goto :CREATE_VENV
) else (
    echo [!] Dang giu lai venv cu, tien hanh kiem tra thu vien...
    goto :INSTALL_STUFF
)

:CREATE_VENV
echo [+] Dang tao venv moi bang uv (Python 3.12)...
uv venv %VENV_NAME% --python 3.12

:INSTALL_STUFF
:: --- CAI DAT THU VIEN ---
echo [+] Dang cai dat requirements tu file...
uv pip install -r requirements_xpu.txt --python %PYTHON_PATH%

echo [+] Dang don dep cac ban Torch cu (neu co)...
uv pip uninstall torch torchvision torchaudio intel-extension-for-pytorch --python %PYTHON_PATH%

echo [+] Dang cai dat PyTorch Nightly cho Intel XPU...
uv pip install --pre torch torchvision torchaudio ^
    --index-url https://download.pytorch.org/whl/nightly/xpu ^
    --python %PYTHON_PATH%

:: --- KIEM TRA KET QUA ---
echo.
echo ==================================================
echo          KET QUA KIEM TRA HE THONG
echo ==================================================
echo import torch, torchvision, torchaudio > check_xpu.py
echo print('='*30) >> check_xpu.py
echo print(f'Torch:      {torch.__version__}') >> check_xpu.py
echo print(f'Vision:     {torchvision.__version__}') >> check_xpu.py
echo print(f'Audio:      {torchaudio.__version__}') >> check_xpu.py
echo is_xpu = torch.xpu.is_available() if hasattr(torch, 'xpu') else False >> check_xpu.py
echo print(f'XPU Status: {is_xpu}') >> check_xpu.py
echo if is_xpu: print(f'Device:     {torch.xpu.get_device_name(0)}') >> check_xpu.py
echo print('='*30) >> check_xpu.py

:: Chạy file tạm
"%PYTHON_PATH%" check_xpu.py

:: Xóa file tạm sau khi xong
del check_xpu.py
pause