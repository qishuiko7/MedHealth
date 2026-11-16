@echo off
chcp 936 >nul
cd /d "%~dp0"

echo ============================================
echo    医疗健康数据平台 - 启动可视化平台
echo ============================================
echo.

if not exist "..\.venv\Scripts\python.exe" (
  echo [错误] 未找到 Python 运行环境（..\.venv）。
  echo 请先按《操作指南.md》第 7 步创建环境并安装依赖。
  echo.
  pause
  exit /b 1
)

echo 平台启动后，请用浏览器访问：http://127.0.0.1:5000
echo 账号：admin / admin123
echo.
echo 关闭本窗口即可停止平台。
echo.

"..\.venv\Scripts\python.exe" app.py

echo.
echo 平台已停止。
pause
