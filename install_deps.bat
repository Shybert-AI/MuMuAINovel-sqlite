@echo off
chcp 65001 >nul
REM MuMuAINovel dependency installation script

echo ========================================
echo     Installing MuMuAINovel dependencies...
echo ========================================

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found, please install Python 3.8+
    pause
    exit /b 1
)

echo [OK] Python is installed

REM Change to backend directory
cd /d "%~dp0backend"

REM Check requirements.txt
if not exist "requirements.txt" (
    echo [ERROR] requirements.txt not found
    pause
    exit /b 1
)

echo [OK] Found requirements.txt

REM Install dependencies
echo Installing dependencies, please wait...
pip install -r requirements.txt

if errorlevel 1 (
    echo [ERROR] Dependency installation failed
    echo Trying to use Chinese mirror source...
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
)

if errorlevel 1 (
    echo [ERROR] Dependency installation still failed, please check network connection
    pause
    exit /b 1
)

echo [OK] Dependencies installed successfully
echo.
echo ========================================
echo     Next steps:
echo     1. Run start.bat to start application
echo     2. Visit http://localhost:8000
echo ========================================

pause