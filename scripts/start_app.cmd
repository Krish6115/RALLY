@echo off
setlocal
cd /d "%~dp0.."

echo Starting Rally Demo Server...
start "Rally Backend" cmd /k "py src\rally\api\server.py"

echo Starting Vite Frontend...
cd /d "%~dp0..\frontend"
start "Rally Frontend" cmd /k "npm run dev"

echo Both services started!

