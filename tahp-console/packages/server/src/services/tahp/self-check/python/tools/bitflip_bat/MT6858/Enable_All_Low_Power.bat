rem bypass usb
adb -s %1 shell "echo bypass 2 > /proc/mtk_lpm/spm/spm_resource_req"