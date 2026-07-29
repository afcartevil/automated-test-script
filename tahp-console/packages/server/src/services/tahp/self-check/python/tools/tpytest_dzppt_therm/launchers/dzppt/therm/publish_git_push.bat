@echo off
call %~dp0publish_config.bat
cd /d %~dp0..\..\base_publisher

call publish_git_push.bat
