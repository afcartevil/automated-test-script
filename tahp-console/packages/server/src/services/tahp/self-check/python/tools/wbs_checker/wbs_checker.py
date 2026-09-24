"""功耗特性自检工具（WBS PowerChecker）。

由 AI 自检用例 cases/power_feature/wbs/case1.py 调用。
资源目录: tools/wbs_checker/res/
"""
import subprocess
import re
import os
import threading
import time

class PowerChecker:
    """功耗特性自检（WBS）。project_root 指向 tools/wbs_checker（含 res/）。"""

    def __init__(self, serial: str, on_step=None):
        if not serial or not str(serial).strip():
            raise ValueError("device serial is required")
        self.serial = str(serial).strip()
        self.results = {}
        self.on_step = on_step
        self.project_root = os.path.dirname(os.path.abspath(__file__))

    def _emit(self, message: str) -> None:
        if self.on_step:
            try:
                self.on_step(message)
            except Exception:
                pass

    def run_adb(self, command, timeout=10):
        try:
            if command.startswith('adb '):
                command = command[4:]
            full_command = f'adb -s {self.serial} {command}'
            process = subprocess.Popen(full_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                stdout_bytes, stderr_bytes = process.communicate(timeout=timeout)
                stdout = stdout_bytes.decode('utf-8', errors='ignore')
                stderr = stderr_bytes.decode('utf-8', errors='ignore')
                return stdout.strip(), stderr.strip()
            except subprocess.TimeoutExpired:
                process.kill()
                stdout_bytes, stderr_bytes = process.communicate()
                return stdout_bytes.decode('utf-8', errors='ignore').strip(), "Timeout expired"
        except Exception as e:
            return "", str(e)

    def check_device(self):
        stdout, _ = self.run_adb("get-state")
        return stdout.strip() == "device"

    def check_gift(self):
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''
        
        if major_ver == '17':
            res, info = "Pass", "gift功能已在Android 17上去除"
            self.results["gift"] = {"res": res, "info": info}
            return res, info
        
        #print("\n正在执行 gift 检测...")
        apk_path = os.path.join(self.project_root, 'res', 'pvzfree_row.apk')
        if not os.path.exists(apk_path):
            res, info = "Fail", f"APK 文件不存在: {apk_path}"
            self.results["gift"] = {"res": res, "info": info}
            return res, info

        #print(f"正在安装 APK: {apk_path}...")
        self.run_adb(f'install -r "{apk_path}"', timeout=300)
        
        # 清理旧日志
        self.run_adb('logcat -c')
        
        captured_logs = []
        stop_logging = threading.Event()

        def log_reader():
            # 使用二进制读取并手动解码，确保稳定
            cmd = ['adb', '-s', self.serial, 'logcat', '-v', 'threadtime']
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            while not stop_logging.is_set():
                line = proc.stdout.readline()
                if line:
                    try:
                        decoded_line = line.decode('utf-8', errors='ignore')
                        captured_logs.append(decoded_line)
                    except:
                        pass
                else:
                    break
            proc.terminate()
            proc.wait()

        # 1. 启动异步日志线程
        log_thread = threading.Thread(target=log_reader)
        log_thread.daemon = True
        log_thread.start()

        # 2. 尝试获取包名并启动应用
        #print("正在查找包名并启动应用...")
        stdout, _ = self.run_adb('shell "pm list packages | grep pvz"')
        pkg_name = ""
        if stdout:
            # 取第一行匹配的包名
            for line in stdout.splitlines():
                if 'pvz' in line:
                    pkg_name = line.replace('package:', '').strip()
                    break
        
        if pkg_name:
            #print(f"检测到包名: {pkg_name}, 正在通过 monkey 启动...")
            self.run_adb(f'shell monkey -p {pkg_name} -c android.intent.category.LAUNCHER 1')
            time.sleep(5) # 等待弹窗显示
            
            # 自动点击年龄确认界面的“确认”按钮
            # 获取屏幕分辨率，横屏状态下(如 2400x1080)
            size_out, _ = self.run_adb('shell wm size')
            width, height = 2400, 1080 # 默认值，假设为横屏
            if 'Physical size:' in size_out:
                try:
                    dims = size_out.split(':')[1].strip().split('x')
                    w, h = int(dims[0]), int(dims[1])
                    # 横屏游戏，宽应该大于高
                    width, height = max(w, h), min(w, h)
                except:
                    pass
            
            # 根据截图分析，确认按钮位于屏幕水平正中，垂直偏下（约70%-75%的高度）
            # 年龄横条滑块位于确认按钮上方，大约在屏幕垂直中间（约50%的高度）
            bar_click_x = int(width * 0.5)
            bar_click_y = int(height * 0.5)
            #print(f"尝试点击年龄横条，坐标: ({bar_click_x}, {bar_click_y})")
            self.run_adb(f'shell input tap {bar_click_x} {bar_click_y}')
            time.sleep(1) # 等待滑动/点击响应
            
            click_x = int(width * 0.5)
            click_y = int(height * 0.72)
            #print(f"尝试点击确认按钮，坐标: ({click_x}, {click_y})")
            self.run_adb(f'shell input tap {click_x} {click_y}')
            
            #print("应用已启动并尝试点击确认，等待 15s 抓取日志...")
            time.sleep(15)
            # 测试完成后返回桌面
            self.run_adb('shell input keyevent 3')
        else:
            print("未检测到相关包名，请确认 APK 是否安装成功。")
            time.sleep(5)
            
        # 3. 停止日志线程
        stop_logging.set()
        log_thread.join(timeout=5)
        
        full_log = "".join(captured_logs)
        
        if 'libMEOW_gift: open' in full_log:
            res, info = "Pass", "Found libMEOW_gift: open"
        else:
            res, info = "Fail", "libMEOW_gift: open not found in logcat"
            
        self.results["gift"] = {"res": res, "info": info}
        return res, info

    def check_short_video(self):
        v1, _ = self.run_adb('shell getprop ro.tran.powerhub.support')
        v2, _ = self.run_adb('shell getprop persist.tran.layercontrol.support')
        # 添加前提设置命令
        self.run_adb('shell setprop debug.product.viewlog.support 1')
        
        # 安装 weibo.apk 并打开
        apk_path = os.path.join(self.project_root, "res", "weibo.apk")
        if os.path.exists(apk_path):
            self.run_adb(f'install -g -r "{apk_path}"', timeout=300)
            self.run_adb('shell monkey -p com.sina.weibo -c android.intent.category.LAUNCHER 1')
            time.sleep(5) # 等待应用启动显示弹窗
            
            # 自动点击同意用户协议 (尝试点击屏幕下方中间位置和右下角可能的位置)
            # 根据常见的屏幕分辨率(如 1080x2400 或 720x1600)，协议同意按钮通常在底部区域
            # 获取屏幕分辨率
            size_out, _ = self.run_adb('shell wm size')
            width, height = 1080, 2400 # 默认值
            if 'Physical size:' in size_out:
                try:
                    dims = size_out.split(':')[1].strip().split('x')
                    width, height = int(dims[0]), int(dims[1])
                except:
                    pass
            
            # 根据提供的截图，“同意并继续”按钮位于屏幕中央偏下的弹窗内，右侧位置
            # X轴大约在 75% 的位置，Y轴大约在 65% 的位置
            click_x = int(width * 0.75)
            click_y = int(height * 0.65)
            self.run_adb(f'shell input tap {click_x} {click_y}')
            
            time.sleep(8) # 等待应用完全进入
            
            # 增加3次界面滑动操作
            #print("正在进行界面滑动以触发短视频优化日志...")
            start_x = int(width * 0.5)
            start_y = int(height * 0.8)
            end_y = int(height * 0.2)
            for _ in range(3):
                self.run_adb(f'shell input swipe {start_x} {start_y} {start_x} {end_y} 500')
                time.sleep(2) # 每次滑动后稍作停顿
                
            time.sleep(5) # 等待日志打印完成
            
            # 测试完成后返回桌面
            self.run_adb('shell input keyevent 3')

        stdout, _ = self.run_adb('shell "logcat -d -b all | grep -Ei \'delayTime:30\'"')
        if v1 == '1' and v2 == '1' and stdout:
            res, info = "Pass", "props OK, logcat found delayTime:30"
        else:
            res, info = "Fail", f"v1:{v1}, v2:{v2}, logcat:{'Found' if stdout else 'Not Found'}"
        self.results["短视频优化"] = {"res": res, "info": info}
        return res, info

    def check_tp_rate(self):
        v1, _ = self.run_adb('shell getprop ro.tr_game.report_rate.support')
        
        # 尝试获取包名并启动 pvz 游戏
        #print("正在查找包名并启动 pvz 游戏以检测 TP 报点率...")
        stdout, _ = self.run_adb('shell "pm list packages | grep pvz"')
        pkg_name = ""
        if stdout:
            # 取第一行匹配的包名
            for line in stdout.splitlines():
                if 'pvz' in line:
                    pkg_name = line.replace('package:', '').strip()
                    break
        
        if pkg_name:
            #print(f"检测到包名: {pkg_name}, 正在通过 monkey 启动...")
            self.run_adb(f'shell monkey -p {pkg_name} -c android.intent.category.LAUNCHER 1')
            time.sleep(5) # 等待弹窗显示
            
            # 获取屏幕分辨率，横屏状态下(如 2400x1080)
            size_out, _ = self.run_adb('shell wm size')
            width, height = 2400, 1080 # 默认值，假设为横屏
            if 'Physical size:' in size_out:
                try:
                    dims = size_out.split(':')[1].strip().split('x')
                    w, h = int(dims[0]), int(dims[1])
                    # 横屏游戏，宽应该大于高
                    width, height = max(w, h), min(w, h)
                except:
                    pass
            
            # 点击年龄横条滑块
            bar_click_x = int(width * 0.5)
            bar_click_y = int(height * 0.5)
            #print(f"尝试点击年龄横条，坐标: ({bar_click_x}, {bar_click_y})")
            self.run_adb(f'shell input tap {bar_click_x} {bar_click_y}')
            time.sleep(1) # 等待滑动/点击响应
            
            # 点击确认按钮
            click_x = int(width * 0.5)
            click_y = int(height * 0.72)
            #print(f"尝试点击确认按钮，坐标: ({click_x}, {click_y})")
            self.run_adb(f'shell input tap {click_x} {click_y}')
            
            #print("应用已启动，等待 10s 抓取日志...")
            time.sleep(10)
            # 测试完成后返回桌面
            self.run_adb('shell input keyevent 3')
        else:
            print("未检测到 pvz 相关包名，将直接尝试获取日志。")
            
        stdout, _ = self.run_adb('shell "logcat -d | grep -i \'TranTp/TranTpSwitchManagerimpl\'"')
        logcat_found = bool(re.search(r'is tp rate to \[?360\]?', stdout, re.IGNORECASE))
        if logcat_found or v1 == '1':
            res, info = "Pass", "logcat: Found" if logcat_found else f"v1:{v1}"
        else:
            res, info = "Fail", f"v1:{v1}, logcat: Not Found"
        self.results["TP报点率优化"] = {"res": res, "info": info}
        return res, info

    def check_video_chat(self):
        # 尝试 OS16 和 OS15 的两种 dumpsys 命令
        cmd1 = 'shell dumpsys activity service com.transsion.usf.UsfMainService -videocallsave -package com.google.android.apps.meetings -activity com.google.android.libraries.communications.conference.ui.greenroom.GreenroomActivity'
        cmd2 = 'shell dumpsys tran_bootstrap_service_manager tran_usf -videocallsave -package com.google.android.apps.meetings -activity com.google.android.libraries.communications.conference.ui.greenroom.GreenroomActivity'
        
        stdout1, _ = self.run_adb(cmd1)
        stdout2, _ = self.run_adb(cmd2)
        stdout = stdout1 + stdout2
        
        if stdout and ('fps' in stdout.lower() or 'package' in stdout.lower() or 'videocallsave' in stdout.lower()):
            res, info = "Pass", "Found output in dumpsys"
        else:
            res, info = "Fail", "No relevant output"
        self.results["视频畅聊场景"] = {"res": res, "info": info}
        return res, info

    def check_sleep_standby(self):
        stdout, _ = self.run_adb('shell dumpsys activity service com.transsion.usf.UsfMainService -ainet state')
        patterns = [r'SUPPORT\s*[:=]\s*true', r'UiSwitch\s*[:=]\s*true', r'mIsOtaAllowPolicy\s*[:=]\s*true']
        if all(re.search(p, stdout, re.IGNORECASE) for p in patterns):
            res, info = "Pass", "All flags true"
        else:
            res, info = "Fail", "Flags missing or false"
        self.results["睡眠待机优化"] = {"res": res, "info": info}
        return res, info

    def check_health_standard(self):
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''
        
        if major_ver == '17':
            stdout, _ = self.run_adb('shell dumpsys activity service com.transsion.usf.UsfMainService -power_healthstandard support')
        else:
            stdout, _ = self.run_adb('shell dumpsys activity healthstandard support')
        
        if '1' in stdout or 'true' in stdout.lower():
            res, info = "Pass", "Found support indicators"
        else:
            res, info = "Fail", "Not supported"
        self.results["软硬件资源管控"] = {"res": res, "info": info}
        return res, info

    def check_hiber(self):
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''
        
        v1, _ = self.run_adb('shell getprop ro.tran.hiber.support')
        stdout1, _ = self.run_adb('shell "dumpsys activity hiber dump | grep enabled"')
        stdout2, _ = self.run_adb('shell "dumpsys tran_bootstrap_service_manager tran_usf-hiber | grep enabled"')
        stdout3, _ = self.run_adb('shell "dumpsys activity service com.transsion.usf.UsfMainService -hiber dump | grep enable"')
        stdout = stdout1 + stdout2 + stdout3
        
        if major_ver == '17':
            if re.search(r'enable[d]?[:=]\s*true', stdout, re.IGNORECASE):
                res, info = "Pass", "Android 17: enabled=true"
            else:
                res, info = "Fail", "Android 17: dump missing enabled=true"
        else:
            if v1 == '1' and re.search(r'enable[d]?[:=]\s*true', stdout, re.IGNORECASE):
                res, info = "Pass", "v1=1 and enabled=true"
            else:
                res, info = "Fail", f"v1:{v1}, dump missing enabled=true"
        self.results["应用冻结"] = {"res": res, "info": info}
        return res, info

    def check_aal_strategy(self):
        # 获取 Android 版本
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''

        # 根据 Android 版本选择命令
        if major_ver >= '16':
            cmd = 'shell "dumpsys vendor.mediatek.hardware.pq_aidl.IPictureQuality_AIDL/default --aal --function"'
        else:
            cmd = 'shell "lshal debug vendor.mediatek.hardware.pq@2.6::IPictureQuality --aal --function"'

        stdout, _ = self.run_adb(cmd)

        # 从命令返回值中获取屏幕类型 (例如: ESS Version : 3.1(LCD))
        screen_type = ''
        ess_match = re.search(r'ESS Version\s*:\s*[\d.]+\((\w+)\)', stdout, re.IGNORECASE)
        if ess_match:
            screen_type = ess_match.group(1).upper()
        else:
            res, info = "Fail", "Cannot find screen type in ESS Version"
            self.results["AAL strategy optimize"] = {"res": res, "info": info}
            return res, info

        # 根据屏幕类型判断期望的 setting 值
        if 'LCD' in screen_type:
            expected = ['setting(0x2)', 'setting(0x6)']
        elif 'OLED' in screen_type:
            expected = ['setting(0x0)', 'setting(0x4)']
        else:
            res, info = "Fail", f"Unknown Screen Type: {screen_type}"
            self.results["AAL strategy optimize"] = {"res": res, "info": info}
            return res, info

        matched = [s for s in expected if s in stdout]
        if matched:
            res, info = "Pass", f"ScreenType:{screen_type}, matched:{matched[0]}"
        else:
            res, info = "Fail", f"ScreenType:{screen_type}, expected:{expected}, not found in output"
        self.results["AAL strategy optimize"] = {"res": res, "info": info}
        return res, info

    def check_aal_whitelist(self):
        stdout, _ = self.run_adb('shell "cat /system/etc/ams_aal_config.xml | grep -I launcher"')
        if stdout:
            res, info = "Pass", "launcher found in ams_aal_config.xml"
        else:
            res, info = "Fail", "launcher not found in ams_aal_config.xml"
        self.results["AAL APP whitelist"] = {"res": res, "info": info}
        return res, info

    def check_transched(self):
        stdout, _ = self.run_adb('shell "getprop | grep transched"')
        required = [
            '[ro.product.transched.support]: [1]',
            '[ro.product.transchedmetrics.support]: [1]',
            '[ro.vendor.transched.support]: [1]',
            '[ro.vendor.transched.version]: [v2.0]'
        ]
        missing = [prop for prop in required if prop not in stdout]
        if not missing:
            res, info = "Pass", "All transched properties found"
        else:
            res, info = "Fail", f"Missing: {', '.join(missing)}"
        self.results["感知调度1.0 & 2.0"] = {"res": res, "info": info}
        return res, info

    def check_standby_handler(self):
        # 获取 Android 版本
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''

        # Android 17 使用新的检测方法
        if major_ver == '17':
            dump_stdout, _ = self.run_adb('shell "dumpsys activity service com.transsion.usf.UsfMainService -standbyhandler state"')
            dump_ok = 'true' in dump_stdout.lower()
            if dump_ok:
                res, info = "Pass", "Android 17: dumpsys contains 'true'"
            else:
                res, info = "Fail", "Android 17: dumpsys missing 'true'"
        else:
            # 根据 Android 版本选择 getprop 命令
            if major_ver == '16':
                prop_cmd = 'shell getprop ro.tr_power.standby_handler.support'
            else:
                prop_cmd = 'shell getprop ro.transsion.standby_handler'

            prop_val, _ = self.run_adb(prop_cmd)
            dump_stdout, _ = self.run_adb('shell "dumpsys activity standbyhandler state"')

            # 根据 Android 版本使用不同的判断标准
            if major_ver == '16':
                prop_ok = prop_val.strip().lower() in ('true', '1')
                dump_ok = 'Enabled: true' in dump_stdout
                expected_prop = 'true or 1'
                expected_dump = 'Enabled: true'
            else:
                prop_ok = prop_val.strip() == '1'
                dump_ok = 'true' in dump_stdout.lower()
                expected_prop = '1'
                expected_dump = 'true'

            if prop_ok and dump_ok:
                res, info = "Pass", f"prop={prop_val}, dumpsys contains '{expected_dump}'"
            else:
                res, info = "Fail", f"prop={prop_val}(expected {expected_prop}), dumpsys={'pass' if dump_ok else 'fail'}(expected '{expected_dump}')"
        
        self.results["应用异常管控设计"] = {"res": res, "info": info}
        return res, info

    def check_app_brightness_limit_v2(self):
        # 获取 Android 版本
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''

        # 根据 Android 版本选择属性命令
        if major_ver >= '16':
            prop_cmd = 'shell getprop ro.tr_light.app_brightness_limit_v2.feature.support'
        else:
            prop_cmd = 'shell getprop ro.tran_app_brightness_limit_V2.support'

        prop_val, _ = self.run_adb(prop_cmd)

        if prop_val.strip() == '1':
            res, info = "Pass", f"prop={prop_val}"
        else:
            res, info = "Fail", f"prop={prop_val}(expected 1)"
        self.results["应用自适应背光2.0"] = {"res": res, "info": info}
        return res, info

    def check_mute_power_save(self):
        # 推送音频文件到手机
        mp3_path = os.path.join(self.project_root, 'res', 'Nana-Lonely.mp3')
        if not os.path.exists(mp3_path):
            res, info = "Fail", f"文件不存在: {mp3_path}"
            self.results["静音省功耗(静音关PA)"] = {"res": res, "info": info}
            return res, info

        self.run_adb(f'push "{mp3_path}" /sdcard/Nana-Lonely.mp3')

        # 扫描文件到媒体库，解决高版本 Android file:// URI 限制
        self.run_adb('shell "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d file:///sdcard/Nana-Lonely.mp3"')
        time.sleep(2)

        # 查询媒体库获取 content URI
        content_stdout, _ = self.run_adb('shell "content query --uri content://media/external/audio/media --projection _id:_data --where \\"_data LIKE \'%Nana-Lonely%\'\""')
        content_uri = None
        match = re.search(r'_id=(\d+)', content_stdout)
        if match:
            content_uri = f"content://media/external/audio/media/{match.group(1)}"

        # 清空 logcat 缓存
        self.run_adb('shell logcat -c')

        # 播放音乐（优先使用 content URI）
        if content_uri:
            self.run_adb(f'shell "am start -a android.intent.action.VIEW -d {content_uri} -t audio/mpeg"')
        else:
            # 备用：直接使用 file URI
            self.run_adb('shell "am start -a android.intent.action.VIEW -d file:///sdcard/Nana-Lonely.mp3 -t audio/mpeg"')

        # 等待音乐开始播放
        time.sleep(3)

        # 设置音量为静音（在播放后设置，避免播放器恢复音量）
        # Android 16 上 media 命令已移除，使用其他方式
        # 方式1: 通过按键事件降低音量到最小
        for _ in range(16):  # 按16次音量减键确保到最小
            self.run_adb('shell input keyevent 25')  # KEYCODE_VOLUME_DOWN
            time.sleep(0.05)
        
        # 方式2: settings 命令设置音乐音量
        self.run_adb('shell settings put system volume_music_speaker 0')
        time.sleep(1)

        # 等待一段时间让日志产生
        time.sleep(5)

        # 读取 logcat 中 mute 相关日志（在设备端 grep，避免 Windows 管道问题）
        stdout, _ = self.run_adb('shell "logcat -d | grep -iE \'mute value 1\'"')

        # 恢复音量并停止播放
        self.run_adb('shell settings put system volume_music_speaker 10')
        # 通过 media_session 查找正在播放的媒体应用包名
        session_stdout, _ = self.run_adb('shell "dumpsys media_session | grep -B5 \'state=Active\'"')
        pkg_match = re.search(r'owner=(\S+)', session_stdout)
        if pkg_match:
            self.run_adb(f'shell am force-stop {pkg_match.group(1)}')
        else:
            # 备用：通过 media_session 查找所有会话
            session_stdout2, _ = self.run_adb('shell "dumpsys media_session | grep -E \'Sessions Stack|owner=\'"')
            for m in re.finditer(r'owner=(\S+)', session_stdout2):
                self.run_adb(f'shell am force-stop {m.group(1)}')
        # 发送暂停按键
        self.run_adb('shell input keyevent 85')  # KEYCODE_MEDIA_PAUSE
        time.sleep(0.5)
        self.run_adb('shell input keyevent 3')

        if 'mute value 1' in stdout.lower():
            res, info = "Pass", "logcat: Found 'mute value 1'"
        else:
            res, info = "Fail", "logcat: Not Found 'mute value 1'"
        self.results["静音省功耗(静音关PA)"] = {"res": res, "info": info}
        return res, info

    def check_thermal_backlight(self):
        # 获取 Android 版本
        android_ver, _ = self.run_adb('shell getprop ro.build.version.release')
        major_ver = android_ver.split('.')[0] if android_ver else ''

        # 清空 logcat
        self.run_adb('shell logcat -c')

        if major_ver == '17':
            # Android 17: dumpsys display 检查
            dump_stdout, _ = self.run_adb('shell "dumpsys display"')
            has_thermal_modifier = 'ThermalBacklightModifier' in dump_stdout
            has_config_enabled = 'Config Enabled: true' in dump_stdout
            has_light_limits = 'lightLimits: {' in dump_stdout

            if has_thermal_modifier and has_config_enabled and has_light_limits:
                res, info = "Pass", "Android 17: ThermalBacklightModifier, Config Enabled: true, lightLimits found"
            else:
                details = []
                if not has_thermal_modifier:
                    details.append("missing 'ThermalBacklightModifier'")
                if not has_config_enabled:
                    details.append("missing 'Config Enabled: true'")
                if not has_light_limits:
                    details.append("missing 'lightLimits: {'")
                res, info = "Fail", f"Android 17: {', '.join(details)}"
        elif major_ver == '16':
            # Android 16: dumpsys 检查
            dump_stdout, _ = self.run_adb('shell "dumpsys activity thermal_light state"')
            has_max_nits = 'Max Nits' in dump_stdout

            # 清空 logcat 后切换应用触发日志
            self.run_adb('shell logcat -c')
            time.sleep(0.5)
            
            # 使用 monkey 打开设置应用（更可靠）
            self.run_adb('shell monkey -p com.android.settings -c android.intent.category.LAUNCHER 1')
            time.sleep(5)
            # 回到桌面
            self.run_adb('shell input keyevent 3')
            time.sleep(5)

            # logcat 检查
            logcat_stdout, _ = self.run_adb('shell "logcat -d | grep -i thermalLight"')
            has_logcat = bool(logcat_stdout.strip())

            if has_max_nits and has_logcat:
                res, info = "Pass", f"dumpsys: Max Nits found, logcat: Found"
            else:
                details = []
                if not has_max_nits:
                    details.append("missing 'Max Nits'")
                if not has_logcat:
                    details.append("logcat: Not Found")
                res, info = "Fail", ", ".join(details)
        else:
            # Android 15: dumpsys 检查
            dump_stdout, _ = self.run_adb('shell "dumpsys activity thermal_backlight thermal_back_state"')
            has_enable = 'Enable = true' in dump_stdout

            # logcat 检查（有返回值即可）
            logcat_stdout, _ = self.run_adb('shell "logcat -d | grep TranThermalBacklightCtrl"')
            has_logcat = bool(logcat_stdout.strip())

            if has_enable and has_logcat:
                res, info = "Pass", f"Enable=true, logcat: Found"
            else:
                details = []
                if not has_enable:
                    details.append("missing 'Enable = true'")
                if not has_logcat:
                    details.append("logcat: Not Found")
                res, info = "Fail", ", ".join(details)

        self.results["高温背光检测"] = {"res": res, "info": info}
        return res, info

    def check_network_disconnect(self):
        s1, _ = self.check_hiber()
        s2, _ = self.check_sleep_standby()
        if s1 == "Pass" and s2 == "Pass":
            res, info = "Pass", "Hiber and SleepStandby both Pass"
        else:
            res, info = "Fail", f"Hiber:{s1}, SleepStandby:{s2}"
        self.results["应用断网"] = {"res": res, "info": info}
        return res, info

    
    AUTO_CHECKS = (
        ("gift", "check_gift"),
        ("TP报点率优化", "check_tp_rate"),
        ("视频畅聊", "check_video_chat"),
        ("睡眠待机优化", "check_sleep_standby"),
        ("软硬件资源管控", "check_health_standard"),
        ("应用冻结", "check_hiber"),
        ("应用断网", "check_network_disconnect"),
        ("AAL strategy optimize", "check_aal_strategy"),
        ("AAL APP whitelist", "check_aal_whitelist"),
        ("感知调度1.0 & 2.0", "check_transched"),
        ("应用异常管控设计", "check_standby_handler"),
        ("应用自适应背光2.0", "check_app_brightness_limit_v2"),
        ("静音省功耗(静音关PA)", "check_mute_power_save"),
        ("高温背光", "check_thermal_backlight"),
    )

    def run_all(self):
        """执行全部自动化检测项，返回结构化结果。"""
        if not self.check_device():
            msg = f"设备未就绪或不在线: {self.serial}"
            self._emit(msg)
            return {
                "ok": False,
                "error": msg,
                "items": [],
                "passed": 0,
                "failed": 0,
                "total": 0,
            }

        items = []
        passed = 0
        failed = 0
        self._emit(f"开始功耗特性自检，设备: {self.serial}，共 {len(self.AUTO_CHECKS)} 项")

        for name, method_name in self.AUTO_CHECKS:
            self._emit(f"执行: {name}")
            func = getattr(self, method_name)
            try:
                status, info = func()
            except Exception as e:
                status, info = "Fail", str(e)
            ok = str(status).lower() == "pass"
            if ok:
                passed += 1
            else:
                failed += 1
            items.append({"name": name, "status": "Pass" if ok else "Fail", "info": info})
            self._emit(f"{name}: {'通过' if ok else '失败'} — {info}")

        return {
            "ok": failed == 0,
            "error": "",
            "items": items,
            "passed": passed,
            "failed": failed,
            "total": len(items),
        }


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(description="功耗特性自检 (WBS checker)")
    parser.add_argument("-s", "--serial", required=True, help="ADB device serial")
    parser.add_argument("--json", action="store_true", help="print JSON summary")
    args = parser.parse_args(argv)

    checker = PowerChecker(serial=args.serial)
    result = checker.run_all()
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
        return 0 if result.get("ok") else 1

    if result.get("error") and not result.get("items"):
        print(result["error"])
        return 2

    print(f"{'特性名称':<24} | {'结果':<8} | {'详细信息'}")
    print("-" * 80)
    for item in result.get("items") or []:
        print(f"{item['name']:<24} | {item['status']:<8} | {item['info']}")
    print("-" * 80)
    print(f"合计: {result.get('passed', 0)} 通过 / {result.get('failed', 0)} 失败 / 共 {result.get('total', 0)} 项")
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
