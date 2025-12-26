@echo off
cd /d "%~dp0"
start RobertoAI.exe
call ./services/WakeOnCallService/start_service.bat