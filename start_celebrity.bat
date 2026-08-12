@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8

echo ============================================
echo   Celebrity - 轻量 Agent（默认 DeepSeek）
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python 3.10+ 并勾选 Add to PATH
    pause
    exit /b 1
)

echo [检查] 核心依赖 (不会自动安装) ...
python -c "import httpx,yaml,rich,dotenv,PIL,numpy,imagehash" >nul 2>nul
if errorlevel 1 (
    echo [提示] 缺少核心依赖，请先手动执行：
    echo.
    echo     pip install -e .
    echo.
    echo 安装完成后重新运行本脚本。
    pause
    exit /b 1
)

echo [启动] python -m celebrity
echo.
python -m celebrity

echo.
echo 按任意键退出...
pause >nul
endlocal
