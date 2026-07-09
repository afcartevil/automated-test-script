' 静默启动 EasyAdapter（无命令行窗口）
' 由 tahp-console\scripts\win\开机自启-注册.bat 通过任务计划程序调用

Dim fso, shell, scriptDir, repoRoot, batPath
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoRoot = fso.GetParentFolderName(fso.GetParentFolderName(fso.GetParentFolderName(scriptDir)))
batPath = fso.BuildPath(repoRoot, "run_adapter.bat")

If Not fso.FileExists(batPath) Then
  WScript.Quit 1
End If

' 0 = 隐藏窗口, False = 不等待进程结束
shell.Run """" & batPath & """", 0, False
