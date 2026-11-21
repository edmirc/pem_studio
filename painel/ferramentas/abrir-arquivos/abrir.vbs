' PEM Studio - recebe o link do navegador e chama o abrir.ps1 sem mostrar janela preta.
If WScript.Arguments.Count = 0 Then WScript.Quit 1
url = WScript.Arguments(0)
If InStr(url, """") > 0 Or Len(url) > 4000 Then WScript.Quit 1
pasta = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & pasta & "\abrir.ps1"" """ & url & """", 0, False
