# MuMuAINovel启动脚本 (PowerShell)

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "    MuMuAINovel启动中..." -ForegroundColor Yellow
Write-Host "========================================" -ForegroundColor Cyan

# 切换到backend目录
Set-Location -Path "$PSScriptRoot\backend"

# 设置UTF-8编码模式
$env:PYTHONUTF8 = "1"

# 检查数据库文件
$dbPath = "..\data\mumuai_novel.db"
if (Test-Path $dbPath) {
    Write-Host "✅ 数据库文件存在: $dbPath" -ForegroundColor Green
} else {
    Write-Host "⚠️  数据库文件不存在，将自动创建..." -ForegroundColor Yellow
}

# 启动应用
Write-Host "正在启动应用..." -ForegroundColor Cyan
try {
    uvicorn app.main:app --host 0.0.0.0 --port 8000
} catch {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "启动失败，请检查:" -ForegroundColor Red
    Write-Host "1. 是否已安装依赖: pip install -r requirements.txt" -ForegroundColor Yellow
    Write-Host "2. 端口8000是否被占用" -ForegroundColor Yellow
    Write-Host "========================================" -ForegroundColor Red
    Read-Host "按回车键退出..."
}