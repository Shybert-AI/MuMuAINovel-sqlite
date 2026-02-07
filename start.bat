@echo off
chcp 65001 >nul
REM MuMuAINovel startup script (Windows)

echo ========================================
echo     Starting MuMuAINovel...
echo ========================================

REM Change to backend directory
cd /d "%~dp0backend"

REM Set UTF-8 encoding mode for Python
set PYTHONUTF8=1

REM Start application
echo Starting application...
uvicorn app.main:app --host 0.0.0.0 --port 8000

REM If uvicorn fails, show error message
if errorlevel 1 (
    echo.
    echo ========================================
    echo     Startup failed, please check:
    echo     1. Dependencies installed: pip install -r requirements.txt
    echo     2. Database file exists: ..\data\mumuai_novel.db
    echo     3. Port 8000 is available
    echo ========================================
    pause
)