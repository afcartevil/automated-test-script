@echo off
:: Check for administrative privileges
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo 请求管理员权限重新运行此脚本...
    powershell -Command "Start-Process -FilePath '%~0' -Verb RunAs"
    exit
)

:: Check if the firewall rule already exists
netsh advfirewall firewall show rule name="Allow TCP 51515" >nul 2>&1
if %errorLevel% neq 0 (
    echo 规则不存在，正在创建规则...
    netsh advfirewall firewall add rule name="Allow TCP 51515" dir=in action=allow protocol=TCP localport=51515
    echo 规则已创建。
) else (
    echo 规则已存在，无需创建。
)

timeout /T 2
exit
