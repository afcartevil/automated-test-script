:: Qualcomm variant: reduced memory footprint (fixed 1536M instead of %3), camera + SAT.
:: See run-google-stressapptest-qcom.bat for the reason.
:: argument list: usb_serial osbit memory cpu log_save_path
adb -s %1 push stressapptest%2 /data/local/tmp/stressapptest
adb -s %1 shell chmod 755 /data/local/tmp/stressapptest

@echo off
SET /A all_cpu=%4
SET /A m_cpu=%all_cpu%
SET /A i_cpu=%all_cpu%/2
SET /A c_cpu=%all_cpu%/2

@echo all_cpu=%all_cpu%,m_cpu=%m_cpu%,i_cpu=%i_cpu%,c_cpu=%c_cpu%

@echo on
adb -s %1 shell "am start -a android.media.action.IMAGE_CAPTURE"
adb -s %1 shell /data/local/tmp/stressapptest -s 60 -M 1536 -m 0 -i %i_cpu% -C %c_cpu% --cc_test
adb -s %1 shell "am start -a android.intent.action.MAIN -c android.intent.category.HOME"
