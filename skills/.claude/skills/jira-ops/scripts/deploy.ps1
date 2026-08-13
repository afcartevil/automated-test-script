# PowerShell wrapper for api_jira.py (Windows)
# Usage:
#   .\deploy.ps1 config show
#   .\deploy.ps1 copy-log-from-description --issue X6873OS162-1079

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Cli = Join-Path $ScriptDir "api_jira.py"
python $Cli @args
exit $LASTEXITCODE
