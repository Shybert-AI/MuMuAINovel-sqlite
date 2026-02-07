@echo off
chcp 65001 >nul
REM MuMuAINovel startup script (Windows)

echo ========================================
echo     Starting MuMuAINovel...
echo ========================================
cd frontend
npm run dev 
pause