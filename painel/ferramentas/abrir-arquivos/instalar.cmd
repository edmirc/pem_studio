@echo off
chcp 65001 >nul
rem PEM Studio - instala o atalho que abre arquivos 3D a partir do sistema (so para este usuario).
set "DEST=%LOCALAPPDATA%\PEMStudio"
if not exist "%DEST%" mkdir "%DEST%"
copy /Y "%~dp0abrir.ps1" "%DEST%\abrir.ps1" >nul || goto erro
copy /Y "%~dp0abrir.vbs" "%DEST%\abrir.vbs" >nul || goto erro
reg add "HKCU\Software\Classes\pemstudio" /ve /d "URL:PEM Studio" /f >nul || goto erro
reg add "HKCU\Software\Classes\pemstudio" /v "URL Protocol" /d "" /f >nul || goto erro
reg add "HKCU\Software\Classes\pemstudio\shell\open\command" /ve /d "wscript.exe \"%DEST%\abrir.vbs\" \"%%1\"" /f >nul || goto erro
echo.
echo Pronto! Agora os botoes "Abrir pasta" e "Abrir no fatiador" do sistema funcionam neste computador.
echo Na primeira vez o navegador pergunta se pode abrir o PEM Studio: marque "Sempre permitir" e clique em Abrir.
echo.
pause
exit /b 0
:erro
echo.
echo Algo deu errado na instalacao. Tente de novo ou fale com quem cuida do sistema.
pause
exit /b 1
