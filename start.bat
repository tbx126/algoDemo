@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==================================================
echo   总部算法平台 - 一键启动脚本
echo ==================================================
echo.

:: 1. 检查前端依赖
if not exist "node_modules" (
  echo [1/4] 未检测到 node_modules，正在安装前端依赖...
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败，请检查 Node.js 环境。
    pause
    exit /b 1
  )
)

:: 2. 检查后端虚拟环境
if not exist "backend\.venv" (
  echo [2/4] 未检测到 backend\.venv，正在使用 uv 安装后端依赖...
  uv --directory backend sync
  if errorlevel 1 (
    echo [错误] uv sync 失败，请确认已安装 uv。
    pause
    exit /b 1
  )
)

:: 3. 启动真实后端服务 (FastAPI + PyTorch, 端口 8000)
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [3/4] 后端服务 (127.0.0.1:8000) 已在运行，跳过启动。
) else (
  echo [3/4] 正在启动后端服务 (127.0.0.1:8000)...
  start "总部算法平台 - 后端服务 (8000)" cmd /k "cd /d "%~dp0backend" && uv run uvicorn server:app --host 127.0.0.1 --port 8000"
)

:: 4. 启动前端开发服务 (Vite, 端口 5173)
netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [4/4] 前端服务 (127.0.0.1:5173) 已在运行，跳过启动。
) else (
  echo [4/4] 正在启动前端服务 (127.0.0.1:5173)...
  start "总部算法平台 - 前端服务 (5173)" cmd /k "cd /d "%~dp0" && npm run dev"
)

echo.
echo 等待服务就绪后自动打开浏览器...
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:5173/"

echo.
echo 启动完成：
echo   前端地址: http://127.0.0.1:5173/
echo   后端地址: http://127.0.0.1:8000/real-api/health
echo   关闭服务: 直接关闭弹出的两个命令行窗口即可
echo.
endlocal
