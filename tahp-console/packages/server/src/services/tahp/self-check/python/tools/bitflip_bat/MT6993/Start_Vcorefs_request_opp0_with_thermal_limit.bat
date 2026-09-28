echo "=== QoS VCOREFS script ==="
adb -s %1 push qos_request_opp0_with_thermal_limit.sh /data/local/tmp/qos_request_opp0_with_thermal_limit.sh
adb -s %1 shell chmod 777 /data/local/tmp/qos_request_opp0_with_thermal_limit.sh

echo "=== modem shutdon ==="
adb -s %1 shell muxreport 3

@echo off
ping -n 2 127.0.0.1>nul

@echo on
adb -s %1 shell cat /sys/kernel/ccci/boot

echo "=== run DVFS ==="
adb -s %1 shell sh /data/local/tmp/qos_request_opp0_with_thermal_limit.sh