:: only clean up when tool run end.
adb -s %1 shell locksettings set-disabled false
adb -s %1 shell setprop persist.vendor.dbg.anrflow 0
adb -s %1 uninstall com.mediatek.screenflash
adb -s %1 uninstall com.android.gpu_emulation_stress_test
adb -s %1 shell "dconfig list | grep \"switch fps to 60\" | awk {'print $1'} | xargs dconfig clear $1"
adb -s %1 shell setprop persist.vendor.usb.vcore_boost 1
adb -s %1 shell "settings delete secure location_mode"
