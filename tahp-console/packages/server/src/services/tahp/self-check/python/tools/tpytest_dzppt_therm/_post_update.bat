@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

set "PROJECT_ROOT=D:\Tools\MTK\tpytest_dzppt_therm\tpytest_dzppt_therm"
set "EXTRACT_DIR=D:\Tools\MTK\tpytest_dzppt_therm\tpytest_dzppt_therm\_tmp_extract\tpytest_dzppt_therm-master"
set "VERSION_FILE=D:\Tools\MTK\tpytest_dzppt_therm\tpytest_dzppt_therm\therm_version.yaml"
set "VERSION_STR=1.0.4"
set "FORCE_UPDATE_STR=2"
set "LAST_RUN_BAT=D:\Tools\MTK\tpytest_dzppt_therm\tpytest_dzppt_therm\last_run.bat"
set "LOG_FILE=%PROJECT_ROOT%\post_update.log"

echo ===== POST UPDATE START: %DATE% %TIME% =====>>"%LOG_FILE%"

rem 确保工作目录在项目根
cd /d "%PROJECT_ROOT%"

rem 等待进程彻底退出，释放文件句柄
ping -n 2 127.0.0.1 >nul

rem 主动结束可能占用复制文件的进程，避免报错 32
for %%P in (adb.exe fastboot.exe scrcpy.exe) do (
    taskkill /F /IM %%P >nul 2>nul
)
rem 再次等待句柄释放
ping -n 2 127.0.0.1 >nul

echo Robocopy 进行镜像同步...>>"%LOG_FILE%"
robocopy "%EXTRACT_DIR%" "%PROJECT_ROOT%" /MIR /COPY:DAT /R:2 /W:1 /NFL /NDL /NP ^
    /XD   "_tmp_extract" ".backup_version" ".runtime" ^
    /XF "_post_update.bat" "post_update.log" "_remote_version.yaml" "last_run.bat"
set RC=%ERRORLEVEL%
echo Robocopy 退出码: %RC%>>"%LOG_FILE%"
if %RC% GEQ 8 (
    echo Robocopy 失败，将跳过写版本与重启，仅做清理。>>"%LOG_FILE%"
    goto CLEANUP_ONLY
)

echo 写入版本文件(YAML)...>>"%LOG_FILE%"
if exist "%PROJECT_ROOT%\_remote_version.yaml" (
    copy /Y "%PROJECT_ROOT%\_remote_version.yaml" "%VERSION_FILE%" >nul
    del /f /q "%PROJECT_ROOT%\_remote_version.yaml" >nul 2>nul
) else (
    >"%VERSION_FILE%" echo version: %VERSION_STR%
    >>"%VERSION_FILE%" echo force_update: %FORCE_UPDATE_STR%
    >>"%VERSION_FILE%" echo updated_at: %DATE% %TIME%
)
rem 额外等待文件系统刷新，避免 GUI 读取旧版本
ping -n 2 127.0.0.1 >nul

:CLEANUP_ONLY
echo 清理临时目录...>>"%LOG_FILE%"
if exist "%EXTRACT_DIR%" (
    attrib -r -h -s /s /d "%EXTRACT_DIR%" >nul 2>nul
    rd /s /q "%EXTRACT_DIR%" 2>nul
)
if exist "%PROJECT_ROOT%\_tmp_extract" (
    attrib -r -h -s /s /d "%PROJECT_ROOT%\_tmp_extract" >nul 2>nul
    rd /s /q "%PROJECT_ROOT%\_tmp_extract" 2>nul
)

if %RC% GEQ 8 (
    echo 因拷贝失败，已完成清理，不执行重启。>>"%LOG_FILE%"
    goto END
)

rem 校验版本文件已生成，否则取消重启
if not exist "%VERSION_FILE%" (
    echo 版本文件未生成，取消重启以避免读取旧版本。>>"%LOG_FILE%"
    goto END
)

echo 尝试重启 GUI...>>"%LOG_FILE%"
if exist "%LAST_RUN_BAT%" (
    echo 使用 LAST_RUN_BAT 启动>>"%LOG_FILE%"
    start "" "%LAST_RUN_BAT%"
    goto END
)
echo 未找到可用的重启脚本，无法重启 GUI。>>"%LOG_FILE%"

:END
echo ===== POST UPDATE END: %DATE% %TIME% =====>>"%LOG_FILE%"
exit
