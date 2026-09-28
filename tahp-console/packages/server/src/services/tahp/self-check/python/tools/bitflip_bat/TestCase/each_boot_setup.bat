rem show dconfig status
adb -s %1 shell "dconfig status"
rem enable cpuhvfs node to test cpu dvfs stress
adb -s %1 shell "insmod /vendor_dlkm/lib/modules/cpu_hwtest.ko"
adb -s %1 shell "echo 0 > /sys/class/usb_boost/vcore/enable"