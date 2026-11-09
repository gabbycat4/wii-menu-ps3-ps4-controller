@echo off
rem Double-click this to add the PS3/PS4 Controller hack to your Wii SD card.
rem To remove it instead, run:  install.bat -Remove
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
pause
