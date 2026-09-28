echo "=== QoS VCOREFS script ==="
adb -s %1 push qos_stress_select_mix_test.sh /data/local/tmp/qos_stress_select_mix_test.sh
adb -s %1 shell chmod 777 /data/local/tmp/qos_stress_select_mix_test.sh

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "=== run DVFS ==="
adb -s %1 shell sh /data/local/tmp/qos_stress_select_mix_test.sh