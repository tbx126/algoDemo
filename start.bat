@echo off
chcp 65001 >nul
setlocal EnableExtensions
title 总部算法平台 ^(前端 5173 / 后端 8000^)

set "ROOT=%~dp0"
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
cd /d "%ROOT%"

echo ==================================================
echo   总部算法平台 - 一键启动 ^(单窗口模式^)
echo ==================================================
echo.

rem 1. 检查前端依赖
if not exist "%ROOT%\node_modules" (
  echo [1/4] 未检测到 node_modules，正在安装前端依赖...
  call npm install
  if errorlevel 1 (
    echo [错误] npm install 失败，请检查 Node.js 环境。
    pause
    exit /b 1
  )
) else (
  echo [1/4] 前端依赖已就绪。
)

rem 2. 检查后端虚拟环境
if not exist "%ROOT%\backend\.venv\Scripts\python.exe" (
  echo [2/4] 未检测到 backend\.venv，正在使用 uv 安装后端依赖...
  uv --directory "%ROOT%\backend" sync
  if errorlevel 1 (
    echo [错误] uv sync 失败，请确认已安装 uv 并配置好网络。
    pause
    exit /b 1
  )
) else (
  echo [2/4] 后端虚拟环境已就绪。
)

rem 3. 在当前窗口后台启动真实后端服务 (8000)
netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [3/4] 后端服务 ^(127.0.0.1:8000^) 已在运行，跳过启动。
) else (
  echo [3/4] 正在启动后端服务 ^(127.0.0.1:8000^)...
  start "" /D "%ROOT%\backend" /B "%ROOT%\backend\.venv\Scripts\python.exe" -m uvicorn server:app --host 127.0.0.1 --port 8000
)

rem 4. 启动前端开发服务 (5173) 并在就绪后自动打开浏览器
netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo [4/4] 前端服务 ^(127.0.0.1:5173^) 已在运行，直接打开浏览器。
  start "" "http://127.0.0.1:5173/"
  echo.
  echo   前端地址: http://127.0.0.1:5173/
  echo   后端地址: http://127.0.0.1:8000/real-api/health
  echo   关闭本窗口即可退出。
  pause >nul
  exit /b 0
)

echo [4/4] 正在启动前端服务 ^(127.0.0.1:5173^)...
echo   前端地址: http://127.0.0.1:5173/
echo   后端地址: http://127.0.0.1:8000/real-api/health
echo   关闭本窗口即可同时停止前后端服务。
echo.

rem 后台静默等待 5173 就绪后自动打开浏览器（不弹新窗口）
start "" /B powershell -NoProfile -Command "for($i=0;$i -lt 30;$i++){try{$c=New-Object Net.Sockets.TcpClient('127.0.0.1',5173);$c.Close();Start-Process 'http://127.0.0.1:5173/';break}catch{Start-Sleep -Milliseconds 500}}"

call npm run dev
endlocal
