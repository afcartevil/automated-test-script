:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push memtester%2 /data/local/tmp/memtester
adb -s %1 shell chmod 777 /data/local/tmp/memtester
adb -s %1 shell "am start -n com.android.gpu_emulation_stress_test/.MainActivity --ez stress true --ei glesApiLevel 3 --ei numObjects 2000"
adb -s %1 shell /data/local/tmp/memtester -m %4 -s 60 256m
adb -s %1 shell "am start -a android.intent.action.MAIN -c android.intent.category.HOME"