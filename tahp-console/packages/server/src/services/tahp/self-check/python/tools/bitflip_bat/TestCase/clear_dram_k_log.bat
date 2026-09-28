:: only clear once when tool run end.
adb -s %1 shell "dconfig list | grep \"DRAM Log to Storage Option Setting\" | awk {'print $1'} | xargs dconfig set -m $1 a0" 