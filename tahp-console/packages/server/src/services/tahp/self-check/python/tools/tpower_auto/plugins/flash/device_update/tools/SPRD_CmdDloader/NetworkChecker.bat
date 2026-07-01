@echo off
setlocal
chcp 65001 > nul

set "url1=https://cn-tool-auth.transsion-os.com/device/mtk-download-verify-v2"
set "url2=https://tool-auth.transsion-os.com/device/mtk-download-verify-v2"
set "url3=https://pfgateway.transsion.com:9199/uac-auth-service/v2/api/uac-auth/crypto/rsaKeyPair?operateType=login"
set "url4=https://api-tones.transsion.com/api/after-tool-authentication/tool/get"
set "url5=https://api-tones-hk.transsion.com/api/after-tool-authentication/tool/get"
set "url6=spug.transsion.com"

REM

REM 使用powershell发送HTTP请求并获取响应
for /f "delims=" %%I in ('powershell -Command "(Invoke-WebRequest -Uri '%url1%').StatusCode"') do (
    set "status1=%%I"
)

for /f "delims=" %%J in ('powershell -Command "(Invoke-WebRequest -Uri '%url2%').StatusCode"') do (
    set "status2=%%J"
)

for /f "delims=" %%K in ('powershell -Command "(Invoke-WebRequest -Uri '%url3%').StatusCode"') do (
    set "status3=%%K"
)

for /f "delims=" %%L in ('powershell -Command "(Invoke-WebRequest -Uri '%url4%').StatusCode"') do (
    set "status4=%%L"
)

for /f "delims=" %%M in ('powershell -Command "(Invoke-WebRequest -Uri '%url5%').StatusCode"') do (
    set "status5=%%M"
) 

for /f "delims=" %%N in ('powershell -Command "(Invoke-WebRequest -Uri '%url6%').StatusCode"') do (
    set "status6=%%N"
)

REM 检查状态码是否为200
if "%status1%"=="200" (
    echo 1.下载鉴权国内网络通过.^.

) else (
    echo 1.下载鉴权国内网络失败.
    echo 检查是否可以ping cn-tool-auth.transsion-os.com.^.
)

if "%status2%"=="200" (
    echo 2.下载鉴权国外网络通过.^.
) else (
    echo 2.下载鉴权国外网络失败.
    echo 检查是否可以ping tool-auth.transsion-os.com.^.
)

if "%status3%"=="200" (
    echo 3.账号登录系统网络通过.^. 
) else (
    echo 3.账号登录系统网络失败.
    echo 检查是否可以ping pfgateway.transsion.com.^.
)

if "%status4%"=="200" (
    echo 4.特征码鉴权国内网络通过.^.
) else (
    echo 4.特征码鉴权国内网络失败.
    echo 检查是否可以ping api-tones.transsion.com.^. 
)

if "%status5%"=="200" (
    echo 5.特征码鉴权国外网络通过.^. 
) else (
    echo 5.特征码鉴权国外网络失败.
    echo 检查是否可以ping api-tones-hk.transsion.com.^.
)

if "%status6%"=="200" (
    echo 6.研发版本内网鉴权网络通过.^.
) else (
    echo 6.研发版本内网鉴权网络失败.
    echo 检查是否可以ping spug.transsion.com.^.
)

REM 在控制台等待用户按下任意键
pause

endlocal
