:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 shell "am start -n com.mediatek.screenflash/.MainActivity"

@echo off
FOR /L %%A IN (0,5,30) DO (
    ping -n 5 127.0.0.1>nul
    adb -s %1 shell "echo %%A All Test OK."
)