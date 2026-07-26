Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strPath

If Not fso.FolderExists(strPath & "\.venv") Then
    WshShell.Run "cmd /c run.bat", 0, True
Else
    WshShell.Run """" & strPath & "\.venv\Scripts\pythonw.exe"" -m saipenview", 0, False
End If
