set func=%~f0
set "func=%func:install.bat=TneDecompress.exe%"

reg add HKEY_CLASSES_ROOT\AllFilesystemObjects\shell\[transsion]TneDecompress /ve /d [transsion]TneDecompress
reg add HKEY_CLASSES_ROOT\AllFilesystemObjects\shell\[transsion]TneDecompress\command /ve /d "%func% /k cd %%1"

pause