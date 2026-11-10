@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在启动个性化学习路径推荐演示平台...
python server.py
pause
