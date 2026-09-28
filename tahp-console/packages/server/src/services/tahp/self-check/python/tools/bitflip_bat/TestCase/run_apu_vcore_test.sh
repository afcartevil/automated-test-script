#!/system/bin/sh

pattern=MaxPower
apu_vcore_test=/data/local/tmp/apu_vcore_test
MDLA_PLAYER_PATH=/vendor/bin/mdla_player
EDPA_TEST_PATH=/vendor/bin/edpa_test64
MVPU_TEST_PATH=/vendor/bin/mvpu_ptn_player64_30

rm -rf $apu_vcore_test
mkdir -p $apu_vcore_test
cd $apu_vcore_test

echo "Test apu vcore start.."

if [ -f $MDLA_PLAYER_PATH ]; then
	##force disable camera app, avoid APU usage conflicts
	am force-stop com.android.camera
	am force-stop com.oplus.camera
	am force-stop com.vivo.camera
	am force-stop com.hihonor.camera

	##TODO maybe need disable more app to avoid APU usage conflicts
else 
	## no test binaray, default test pass.
	echo "VCORE-APU TEST PASS"
	exit 0
fi

$EDPA_TEST_PATH -l 1000 -t 1 -b -1 -c 0 &>test_edpa_c0.txt &
$EDPA_TEST_PATH -l 1000 -b -1 -c 1 &>test_edpa_c1.txt &

$MVPU_TEST_PATH -t 8 -l 1500 --session_reused  &> test_result_mvpu.txt &

$MDLA_PLAYER_PATH -f $pattern -l 400 -o 60 -c 1 &> test_result_c1.txt &
$MDLA_PLAYER_PATH -f $pattern -l 400 -o 60 -c 2 &> test_result_c2.txt &
$MDLA_PLAYER_PATH -f $pattern -l 400 -o 60 -c 4 &> test_result_c4.txt &
$MDLA_PLAYER_PATH -f $pattern -l 400 -o 60 -c 8 &> test_result_c8.txt

## wait max 10s for other test thread exit.
count=20
while [ $count -ne 0 ]
do
	if pgrep -x "mdla_player" > /dev/null 2>&1; then
		echo "Process mdla_player is still running."
	elif pgrep -x "edpa_test64" > /dev/null 2>&1; then
		echo "Process edpa_test64 is still running."
	elif pgrep -x "mvpu_ptn_player64_30" > /dev/null 2>&1; then
		echo "Process mvpu_ptn_player64_30 is still running."
	else
		echo "Process all NPU test process has exited."
		break
	fi
	sleep 0.5
	count=$(($count-1))
done

if [ $(grep -i "Compare golden Fail" test_result_c1.txt test_result_c2.txt test_result_c4.txt test_result_c8.txt | wc -l) -eq 0 ]; then
	if [ $(grep -i "Fail: src" test_edpa_c0.txt test_edpa_c1.txt | wc -l) -eq 0 ]; then
		if [ $(grep -i fail test_result_mvpu.txt | wc -l) -eq 0 ]; then
			echo "VCORE-APU TEST PASS"
		else
			echo "VCORE-APU TEST FAIL, this is new bitfip pattern, Please contact yanghui.li to confirm details"
		fi
	else
		echo "VCORE-APU TEST FAIL, this is new bitfip pattern, Please contact yanghui.li to confirm details"
	fi
else
	echo "VCORE AVS TEST FAIL, this is new bitflip pattern, Please contact yanghui.li to confirm details"
fi

echo "Test end.."