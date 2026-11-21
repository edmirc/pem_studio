@echo off
reg delete "HKCU\Software\Classes\pemstudio" /f >nul 2>&1
rmdir /S /Q "%LOCALAPPDATA%\PEMStudio" 2>nul
echo Atalho do PEM Studio removido deste computador.
pause
