# Bugfix AI CLI wrapper (PowerShell)
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python "$ScriptDir\api_bugfix.py" @args
exit $LASTEXITCODE
