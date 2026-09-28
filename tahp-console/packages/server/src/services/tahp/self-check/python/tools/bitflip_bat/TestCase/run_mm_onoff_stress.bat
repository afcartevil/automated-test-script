:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push mm_quick_test.sh /data/local/tmp/
adb -s %1 shell chmod 0755 /data/local/tmp/mm_quick_test.sh
:: need disable system suspend test
adb -s %1 shell /data/local/tmp/mm_quick_test.sh
@echo off
adb -s %1 shell "echo All Test OK."