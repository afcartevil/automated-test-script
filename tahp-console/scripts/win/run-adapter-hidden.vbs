' 托盘「更新并重启」：单进程无闪窗执行 run_adapter.bat
' 由 tray-actions spawnFullRestart 通过 wscript //B 调用

Dim fso, shell, scriptDir, repoRoot, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(scriptDir)))
batPath = fso.BuildPath(repoRoot, "run_adapter.bat")

If Not fso.FileExists(batPath) Then
  WScript.Quit 1
End If

shell.Environment("PROCESS").Item("TAHP_SILENT") = "1"
shell.Environment("PROCESS").Item("TAHP_TRAY") = "1"
' 0 = 隐藏窗口, False = 不等待进程结束
shell.Run """" & batPath & """", 0, False
