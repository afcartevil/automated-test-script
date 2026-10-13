import json
import os
import re
import shutil
import socket
import threading
import time
import pandas as pd

from datetime import datetime
from plugins.flash.flash import flash_rom
from powertrde.utils.trde import adb
from powertrde.framework.logs_protocol import logs_p
from powertrde.utils.wifiadb.wifi_adb_utils import check_device_to_link_wifi
from tests.current_analysis.table_task import TableTask
from tests.current_analysis.run_case import run_single_case
from tests.current_analysis.device import Device
from tests.current_analysis.phoneconfig import PhoneConfig
from powertrde.env import PROJ_DIR

# UI 场景模式完成信号：复杂待机 / 基础场景跑完后退出常驻循环
_scene_exit = threading.Event()


def resolve_power_scene_mode(raw=None):
    """Map Console --scene / TAHP_POWER_SCENE to scheduler mode.

    - standby: 仅定时/普通待机（wifi + data）
    - base: 仅 task_base（最多 3 轮）
    - full: 通用全域测试 / PFMMod（刷机 + 待机 + 基础，原全量调度）
    - unsupported: DOU 等暂不实现
    - '' : 无 UI 场景标签时的实验室常驻全量循环
    """
    text = (raw if raw is not None else os.environ.get("TAHP_POWER_SCENE") or "").strip()
    if text in ("复杂待机场景", "复杂待机", "待机"):
        return "standby"
    if text in ("系统基础场景", "基础体验场景", "基础场景"):
        return "base"
    if text in ("通用全域测试", "全域测试", "全量", "PFMMod"):
        return "full"
    if text == "DOU":
        return "unsupported"
    return ""


def task_proc_thread():
    device_threads = {}
    debug = False # 是否为测试环境
    tabletask = TableTask(debug)
    device = Device()
    scene_mode = resolve_power_scene_mode()
    _scene_exit.clear()
    if scene_mode == "unsupported":
        scene_label = (os.environ.get("TAHP_POWER_SCENE") or "").strip() or "未知场景"
        logs_p().log(f"{scene_label} 暂不实现，退出功耗环境")
        print(f"[TAHP] {scene_label} 暂不实现", flush=True)
        return
    if scene_mode:
        logs_p().log(f"功耗场景模式启动: {scene_mode} (TAHP_POWER_SCENE={os.environ.get('TAHP_POWER_SCENE', '')})")
    #device.test("default")
    # 补传日志
    out_dir = os.path.join(PROJ_DIR, "output")
    if os.path.exists(out_dir):
        files = os.listdir(out_dir)
        for file in files:
            if file.endswith('.zip'):
                print(f"upload_powercloud: {file.split('.zip')[0]}")
                if debug:
                    tabletask.add_upload_powercloud(f"debug_{file.split('-')[0].upper()}", f"{out_dir}/{file.split('.zip')[0]}")
                else:
                    tabletask.add_upload_powercloud(file.split('-')[0].upper(), f"{out_dir}/{file.split('.zip')[0]}")
    while True:
        tabletask.upload_powercloud()
        if scene_mode and _scene_exit.is_set():
            for thread in list(device_threads.values()):
                if thread.is_alive():
                    thread.join(timeout=30)
            tabletask.upload_powercloud()
            logs_p().log(f"场景模式({scene_mode})任务完成，退出功耗环境")
            return
        device_list = device.update()
        # 1. 移除已断开连接的设备线程
        for pmsn in list(device_threads.keys()):
            thread = device_threads[pmsn]
            if pmsn not in device_list:  # 设备已移除
                if thread.is_alive():
                    thread.join(timeout=5)  # 等待线程结束
                del device_threads[pmsn]
                logs_p().log(f"线程已移除:TPM={pmsn}")
            elif not thread.is_alive():
                del device_threads[pmsn]
                logs_p().log(f"线程异常退出:TPM={pmsn}")

        # 判断列表是否包含有效内容，如为{}是空
        if device_list == {}:
            time.sleep(1)
            continue
        
        # 2. 为新设备创建线程（场景完成后不再拉起）
        if not (scene_mode and _scene_exit.is_set()):
            for pmsn, device_info in device_list.items():
                if pmsn not in device_threads:  # 设备未创建线程
                    device.unlock(pmsn)
                    # 创建线程，目标函数为 device_task_loop，传入设备参数
                    thread = threading.Thread(
                        target=device_task_loop,
                        args=(pmsn, tabletask, debug),
                        daemon=True  # 主线程退出时自动结束子线程
                    )
                    thread.start()
                    device_threads[pmsn] = thread
        time.sleep(5 if scene_mode else 60)  # 场景模式加快轮询；实验室保持 1 分钟

def device_task_loop(pmsn, tabletask: TableTask, debug: bool):
    try:
        phone = PhoneConfig(pmsn)
        phone.powerref = tabletask.get_power_reference(phone.model)
    except Exception as e:
        logs_p().log(f"手机连接失败: {e}")
        time.sleep(60)
        return
    phone.device.lock(pmsn)
    phone.debug = debug
    version = phone.version
    initOK = False
    phone.loginfo(f"线程已启动: VER={version}")
    
    # 获取场景模式
    scene_mode = resolve_power_scene_mode()
    
    # 基础功耗测试（base）和待机测试都使用完整初始化（带容错）
    for i in range(3):
        try:
            phone.env_init()
            initOK = True
            phone.loginfo(f"手机初始化成功")
            break
        except Exception as e:
            phone.logerror(f"手机配置失败, 异常信息: {e}")
            continue
    if not initOK:
        phone.logerror(f"手机配置失败, 线程退出")
        return
    
    taskmanager = TaskManager(phone, tabletask)
    while True:
        if not adb.is_adb_connected(phone.serial):
            phone.device.usb_disconnect(pmsn)
            time.sleep(5)
            phone.device.usb_connect(pmsn)
            time.sleep(5)
            if adb.is_adb_connected(phone.serial):
                phone.loginfo(f"ADB重连成功")
                break
            else:
                phone.logerror(f"ADB重连失败, 线程退出")
                return
        # 基础功耗测试跳过 WiFi 检查
        if scene_mode != "base":
            try:
                phone.pre_phone_check_wifi_connection()
            except Exception as e:
                phone.logerror(f"WiFi连接检查失败(已跳过): {e}")
        try:
            taskmanager.run()
        except Exception as e:
            phone.logerror(f"任务执行失败, 异常信息: {e}")
        if taskmanager.reboot:
            break
        if taskmanager.scene_finished:
            phone.loginfo(f"场景任务完成({taskmanager.scene_mode})，结束本设备调度")
            _scene_exit.set()
            break
        time.sleep(5 if taskmanager.scene_mode else 60)

class TaskManager:
    def __init__(self, phone: PhoneConfig, tabletask: TableTask):
        self.phone = phone
        self.tabletask = tabletask
        self.weekday = -1
        self.reboot = False
        self.scene_mode = resolve_power_scene_mode()
        self.scene_finished = False
        
    def update_time(self):
        self.time = datetime.now().time()
        if self.weekday != datetime.now().weekday():
            self.weekday = datetime.now().weekday()
            self.weekstr = f"W{self.weekday + 1}"
            self.romupdate = True
            self.basetest = True
            self.basetestcnt = 0
            self.datastandby = True
            self.wifistandby = True
    
    def run(self): 
        self.plan = self.tabletask.get_test_plan(self.phone.model, self.phone.pmsn)
        assert self.plan is not None, "获取测试计划失败"
        self.update_time()
        mode = self.scene_mode
        if mode == "standby":
            # UI「复杂待机/待机」：只跑定时/普通待机 wifi+data，不刷机、不跑 task_base
            self.phone.loginfo("场景模式=待机：仅执行 wifi/data 待机任务")
            self.priority = 2
            self.run_ontime_standby_task()
            self.run_common_standby_task()
            if not self.datastandby and not self.wifistandby:
                self.scene_finished = True
            return
        if mode == "base":
            # UI「基础场景」：只跑 task_base，最多 3 轮
            self.phone.loginfo("场景模式=基础场景：仅执行 task_base（最多3轮）")
            self.priority = 2
            self.run_base_task()
            if not self.basetest:
                self.scene_finished = True
            elif not self.tabletask.get_tasks_base():
                self.phone.loginfo("task_base 为空，结束基础场景")
                self.basetest = False
                self.scene_finished = True
            return
        if mode == "full":
            # UI「通用全域测试 / PFMMod」：原全量调度（刷机 + 待机 + 基础）
            scene_label = (os.environ.get("TAHP_POWER_SCENE") or "").strip() or "通用全域测试"
            self.phone.loginfo(f"场景模式={scene_label}：执行全量调度")
            self.run_update_rom()
            if self.reboot:
                self.phone.loginfo(f"重启手机")
                adb.reboot_phone(self.phone.serial)
                return
            self.priority = 2
            self.run_ontime_standby_task()
            self.run_base_task()
            self.run_common_standby_task()
            if (
                not self.romupdate
                and not self.basetest
                and not self.datastandby
                and not self.wifistandby
            ):
                self.scene_finished = True
            return
        # 无 UI 场景标签：实验室常驻全量循环（不自动退出）
        self.run_update_rom()
        if self.reboot:
            self.phone.loginfo(f"重启手机")
            adb.reboot_phone(self.phone.serial)
            return
        self.priority = 2
        self.run_ontime_standby_task()
        self.run_base_task()
        self.run_common_standby_task()

    def run_update_rom(self):
        # 删除romdir下过时的文件
        def clean_romdir(romdir: str):
            if not os.path.exists(romdir):
                os.makedirs(romdir)
            for file in os.listdir(romdir):
                filepath = os.path.join(romdir, file)
                if os.path.isfile(filepath):
                    if time.time() - os.path.getmtime(filepath) > 15 * 24 * 60 * 60:
                        os.remove(filepath)
                elif os.path.isdir(filepath):
                    shutil.rmtree(filepath)
        if not self.romupdate:
            return
        if 'update' not in self.plan or self.weekstr not in self.plan['update']['week']:
            self.romupdate = False
            self.phone.loginfo(f"今日无ROM更新任务")
            return
        if self.plan['update']['updatefile'] == '':
            self.romupdate = False
            self.phone.loginfo(f"未配置ROM文件路径")
            return
        if(self.plan['update']['runtime_hour'] != ''):
                hour = int(self.plan['update']['runtime_hour'])
                if(self.time.hour < hour):
                    return
        romdir = "../rom"
        clean_romdir(romdir)
        expacktype = ''
        if 'root' in self.plan['update']['expack']:
            expacktype = '_user_root.zip'
        if 'fans' in self.plan['update']['expack']:
            expacktype = '_user_fans.zip'
        filelist = []
        if os.path.isfile(self.plan['update']['updatefile']):
            if not self.plan['update']['updatefile'].endswith('.zip'):
                self.romupdate = False
                self.phone.loginfo(f"ROM更新文件不是zip文件: {self.plan['update']['updatefile']}")
                return
            if os.path.getsize(self.plan['update']['updatefile']) < 3 * 1024 * 1024 * 1024:
                self.romupdate = False
                self.phone.loginfo(f"ROM更新文件小于3G: {self.plan['update']['updatefile']}")
                return
            filelist.append(self.plan['update']['updatefile'])
        elif os.path.isdir(self.plan['update']['updatefile']):
            for root, dirs, files in os.walk(self.plan['update']['updatefile']):
                if os.path.basename(root).lower() != "open":
                    continue
                for file in files:
                    if re.match(r'.*SP\d{2}.*', file):
                        continue
                    if not re.match(rf'.*{self.phone.model}.*\(OP.*\)\.zip', file, re.IGNORECASE):
                        continue
                    if expacktype != '':
                        if not os.path.exists(os.path.join(root, file.replace('.zip', expacktype))):
                            continue # 没有root/fans扩展zip文件
                    filelist.append(os.path.join(root, file))
        else:
            self.romupdate = False
            self.phone.loginfo(f"ROM更新文件路径不存在: {self.plan['update']['updatefile']}")
            return
        if not filelist:
            self.romupdate = False
            self.phone.loginfo(f"目录下没有符合条件的ROM更新文件: {self.plan['update']['updatefile']}")
        srczipfile = filelist[-1]
        self.phone.loginfo(f"选择升级的ROM文件: {srczipfile}")
        deszipfile = f"{romdir}/{os.path.basename(srczipfile)}"
        version = srczipfile.split('\\')[-1].split('(')[0]
        if version in self.phone.version:
            self.phone.loginfo(f"手机已经是最新版本:{version}")
            self.romupdate = False
            return
        if expacktype != '':
            srcexzipfile = srczipfile.replace('.zip', expacktype)
            desexzipfile = f"{romdir}/{os.path.basename(srcexzipfile)}"
        else:
            srcexzipfile = ''
            desexzipfile = ''
        for i in range(3):
            if os.path.isfile(deszipfile) and os.path.getsize(deszipfile) != os.path.getsize(srczipfile):
                try:
                    os.remove(deszipfile)
                except Exception as e:
                    pass
            if os.path.isfile(desexzipfile) and os.path.getsize(desexzipfile) != os.path.getsize(srcexzipfile):
                try:
                    os.remove(desexzipfile)
                except Exception as e:
                    pass
            clean_romdir(romdir)
            if not os.path.isfile(deszipfile):
                self.phone.loginfo(f"开始下载ROM文件: {srczipfile}")
                shutil.copy(srczipfile, deszipfile)
                self.phone.loginfo(f"ROM文件下载完成: {deszipfile}")
            if os.path.isfile(srcexzipfile):
                if not os.path.isfile(desexzipfile):
                    self.phone.loginfo(f"开始下载ROM 扩展包: {srcexzipfile}")
                    shutil.copy(srcexzipfile, desexzipfile)
                    self.phone.loginfo(f"ROM 扩展包下载完成: {desexzipfile}")
            else:
                desexzipfile = ''
            battery_level = adb.get_battery_percent(self.phone.serial)
            if(battery_level < 80):
                self.phone.loginfo(f"当前电量{battery_level},设置为80%")
                self.phone.u2d_helper.set_fake_battery_level(80)
            self.phone.loginfo(f"开始刷机: {deszipfile}")
            if not flash_rom(self.phone, deszipfile, expack=desexzipfile):
                self.phone.logerror(f"刷机失败: {deszipfile}")
                continue
            self.phone.loginfo(f"ROM更新完成: {deszipfile}")
            self.reboot = True
            break
    
    def run_base_task(self):
        if self.basetest:
            if 'base' not in self.plan or self.weekstr not in self.plan['base']['week']:
                self.basetest = False
                self.phone.loginfo(f"今日无基础功耗测试任务")
                return
            if 'p1' in self.plan['base']['task']:
                self.priority = 1
            elif 'p2' in self.plan['base']['task']:
                self.priority = 2
            else:
                self.priority = 3
            if(self.basetestcnt < 3):
                tasks_base = self.tabletask.get_tasks_base()
                if tasks_base:
                    selected_case_ids_str = os.environ.get("TAHP_POWER_CASE_IDS", "").strip()
                    self.phone.loginfo(f"[TAHP] TAHP_POWER_CASE_IDS='{selected_case_ids_str}'")
                    matched_case_ids = set()
                    if selected_case_ids_str:
                        selected_case_ids = [cid.strip() for cid in selected_case_ids_str.split(",") if cid.strip()]
                        # T01 这类是 task_base 的任务号，同一 case_id（如 C01_灭屏待机）下要能多选
                        selected_task_ids = {
                            cid.upper() for cid in selected_case_ids if re.fullmatch(r"T\d+", cid, re.IGNORECASE)
                        }
                        selected_prefixes = [
                            cid for cid in selected_case_ids if not re.fullmatch(r"T\d+", cid, re.IGNORECASE)
                        ]
                        filtered = {}
                        for tid, tdata in tasks_base.items():
                            task_key = str(tdata.get("id") or tid).strip().upper()
                            if task_key in selected_task_ids:
                                filtered[tid] = tdata
                                matched_case_ids.add(task_key)
                                continue
                            case_id = str(tdata.get("case_id", ""))
                            for cid in selected_prefixes:
                                if case_id.startswith(cid) and cid not in matched_case_ids:
                                    filtered[tid] = tdata
                                    matched_case_ids.add(cid)
                                    break
                        tasks_base = filtered
                        if not tasks_base:
                            self.phone.loginfo(f"选中的 case_id 无匹配任务：{selected_case_ids}")
                            self.basetest = False
                            self.scene_finished = True
                            return
                        self.phone.loginfo(f"已筛选 {len(tasks_base)} 个任务（case: {', '.join(sorted(matched_case_ids))}）")

                    if any(str(tdata.get("case_id", "")).startswith("C07") for tdata in tasks_base.values()):
                        try:
                            sim_state = adb.exec_cmd(self.phone.serial, "dumpsys telephony.registry | grep -E 'mState=CONNECTED|mState=DISCONNECTED'")
                            sim_count = len([line for line in sim_state.split("\n") if "mState=" in line]) if sim_state else 0
                            if sim_count == 0:
                                tasks_base = {tid: tdata for tid, tdata in tasks_base.items() if not str(tdata.get("case_id", "")).startswith("C07")}
                                matched_case_ids.discard("C07")
                                self.phone.loginfo("[TAHP] 无 SIM 卡，跳过 C07（离线通话）")
                        except Exception as e:
                            tasks_base = {tid: tdata for tid, tdata in tasks_base.items() if not str(tdata.get("case_id", "")).startswith("C07")}
                            matched_case_ids.discard("C07")
                            self.phone.loginfo(f"[TAHP] SIM 卡检查失败，跳过 C07: {e}")
                        if not tasks_base:
                            self.phone.loginfo(f"选中的 case_id 无匹配任务：{selected_case_ids_str}")
                            self.basetest = False
                            self.scene_finished = True
                            return

                    self.basetestcnt += 1
                    self.phone.loginfo(f"基础功耗测试第{self.basetestcnt}轮开始")
                    self.task = tasks_base
                    battery_level = adb.get_battery_percent(self.phone.serial)
                    if(battery_level < 80):
                        self.phone.loginfo(f"当前电量{battery_level},设置为80%")
                        self.phone.u2d_helper.set_fake_battery_level(80)
                    self.run_task()
                    self.phone.loginfo(f"基础功耗测试第{self.basetestcnt}轮结束")
                    # 选中 case_ids 时只测 1 轮，否则测 3 轮
                    max_rounds = 1 if selected_case_ids_str else 3
                    if self.phone.debug or self.basetestcnt >= max_rounds:
                        self.basetest = False
                        self.phone.loginfo(f"今日基础功耗测试任务已完成")
                    return

    def run_ontime_standby_task(self):
        self.standbyconf = self.tabletask.get_standby_tasks()
        assert self.standbyconf is not None, "获取待机任务失败"
        
        # 获取选中的 case_ids
        selected_case_ids_str = os.environ.get("TAHP_POWER_CASE_IDS", "").strip()
        selected_standby_ids = set()
        if selected_case_ids_str:
            selected_standby_ids = set(cid.strip().upper() for cid in selected_case_ids_str.split(",") if cid.strip())
        
        if self.datastandby:
            # 检查是否选中了 S01
            if selected_standby_ids and 'S01' not in selected_standby_ids:
                self.phone.loginfo(f"S01(数据待机)未选中，跳过")
                self.datastandby = False
            elif 'data' not in self.plan or self.weekstr not in self.plan['data']['week']:
                self.datastandby = False
                self.phone.loginfo(f"今日无数据待机测试任务")
            elif(self.plan['data']['runtime_hour'] != ''):
                hour = int(self.plan['data']['runtime_hour'])
                if(self.time.hour >= hour):
                    for task_id, task_data in self.standbyconf.items():
                        if(task_data['id'] == 'S01'):
                            self.task = {'S01':task_data}
                            while True:
                                battery_level = adb.get_battery_percent(self.phone.serial)
                                if(battery_level >= 70):
                                    break
                                self.phone.loginfo(f"当前电量{battery_level},待机测试需等待电量到达70%以")
                                time.sleep(600)
                            self.phone.loginfo(f"定时执行开始：{task_data['task']}")
                            self.run_task()
                            self.phone.loginfo(f"定时执行完成：{task_data['task']}")
                            self.datastandby = False
                            self.phone.loginfo(f"今日数据待机测试任务已完成")
                            break
        if self.wifistandby:
            # 检查是否选中了 S02
            if selected_standby_ids and 'S02' not in selected_standby_ids:
                self.phone.loginfo(f"S02(WIFI待机)未选中，跳过")
                self.wifistandby = False
            elif 'wifi' not in self.plan or self.weekstr not in self.plan['wifi']['week']:
                self.wifistandby = False
                self.phone.loginfo(f"今日无WiFi待机测试任务")
            elif(self.plan['wifi']['runtime_hour'] != ''):
                hour = int(self.plan['wifi']['runtime_hour'])
                if(self.time.hour >= hour):
                    for task_id, task_data in self.standbyconf.items():
                        if(task_data['id'] == 'S02'):
                            self.task = {'S02':task_data}
                            while True:
                                battery_level = adb.get_battery_percent(self.phone.serial)
                                if(battery_level >= 70):
                                    break
                                self.phone.loginfo(f"当前电量{battery_level},待机测试需等待电量到达70%以")
                                time.sleep(600)
                            self.phone.loginfo(f"开始执行：{task_data['task']}")
                            self.run_task()
                            self.phone.loginfo(f"执行完成：{task_data['task']}")
                            self.wifistandby = False
                            self.phone.loginfo(f"今日WiFi待机测试任务已完成")
                            break

    def run_common_standby_task(self):
        self.standbyconf = self.tabletask.get_standby_tasks()
        assert self.standbyconf is not None, "获取待机任务失败"
        
        # 获取选中的 case_ids
        selected_case_ids_str = os.environ.get("TAHP_POWER_CASE_IDS", "").strip()
        selected_standby_ids = set()
        if selected_case_ids_str:
            selected_standby_ids = set(cid.strip().upper() for cid in selected_case_ids_str.split(",") if cid.strip())
        
        if self.datastandby:
            # 检查是否选中了 S01
            if selected_standby_ids and 'S01' not in selected_standby_ids:
                self.phone.loginfo(f"S01(数据待机)未选中，跳过")
                self.datastandby = False
            elif 'data' not in self.plan or self.weekstr not in self.plan['data']['week']:
                self.datastandby = False
                self.phone.loginfo(f"今日无数据待机测试任务")
            elif(self.plan['data']['runtime_hour'] == ''):
                for task_id, task_data in self.standbyconf.items():
                    if(task_data['id'] == 'S01'):
                        self.task = {'S01':task_data}
                        while True:
                            battery_level = adb.get_battery_percent(self.phone.serial)
                            if(battery_level >= 70):
                                break
                            self.phone.loginfo(f"当前电量{battery_level},待机测试需等待电量到达70%以")
                            time.sleep(600)
                        self.phone.loginfo(f"开始执行：{task_data['task']}")
                        self.run_task()
                        self.phone.loginfo(f"执行完成：{task_data['task']}")
                        self.datastandby = False
                        self.phone.loginfo(f"今日数据待机测试任务已完成")
                        break
        if self.wifistandby:
            # 检查是否选中了 S02
            if selected_standby_ids and 'S02' not in selected_standby_ids:
                self.phone.loginfo(f"S02(WIFI待机)未选中，跳过")
                self.wifistandby = False
            elif 'wifi' not in self.plan or self.weekstr not in self.plan['wifi']['week']:
                self.wifistandby = False
                self.phone.loginfo(f"今日无WiFi待机测试任务")
            elif(self.plan['wifi']['runtime_hour'] == ''):
                for task_id, task_data in self.standbyconf.items():
                    if(task_data['id'] == 'S02'):
                        while True:
                            battery_level = adb.get_battery_percent(self.phone.serial)
                            if(battery_level >= 70):
                                break
                            self.phone.loginfo(f"当前电量{battery_level},待机测试需等待电量到达70%以")
                            time.sleep(600)
                        self.task = {'S02':task_data}
                        self.phone.loginfo(f"开始执行：{task_data['task']}")
                        self.run_task()
                        self.phone.loginfo(f"执行完成：{task_data['task']}")
                        self.wifistandby = False
                        self.phone.loginfo(f"今日WiFi待机测试任务已完成")
                        break

    def run_task(self):
        datestr = f"{time.strftime('%m%d_%H%M', time.localtime())}"
        self.phone.logsubdir = f"{self.phone.version}_{datestr}"
        adb.reset_batterystats_for_bugreport(self.phone.serial)  # 重置bugreport
        xlsx_path = f"{self.phone.logrootdir}/{self.phone.logsubdir}.xlsx"
        
        # 清空 JSON 结果文件，避免累积之前的测试结果
        json_path = f"{self.phone.logrootdir}/power_results.json"
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump([], f)
        except Exception as e:
            self.phone.logwarning(f"清空 JSON 结果文件失败: {e}")
        
        for task_id, task_data in self.task.items():
            if(task_data['priority'] == ''):
                continue
            priority = int(task_data['priority'])
            if(priority == 0 or priority > self.priority):
                continue
            self.phone.loginfo(f"{task_id}_{task_data['task']} 测试开始")
            data_dict = self.phone.dict_excel
            data_dict['model'] = self.phone.model
            data_dict['version'] = self.phone.version
            data_dict['test_date'] = time.strftime('%Y/%m/%d', time.localtime())
            data_dict['test_time'] = time.strftime('%H:%M:%S', time.localtime())
            data_dict['task_id'] = task_id
            data_dict['current'] = None
            data_dict['refresh_min'] = None
            data_dict['refresh_max'] = None
            data_dict['brightness_actual'] = None
            data_dict['ntc_end'] = None
            data_dict['camara'] = ""
            data_dict['log'] = self.phone.logsubdir
            data_dict['test_host'] = socket.gethostname()
            data_dict['analysis'] = ""
            for k,v in task_data.items():
                if k == '_i' or k == '_ori_id' or k == 'id' or k == 'priority':
                    continue
                data_dict[k] = v
            result = False
            for j in range(3):
                try:
                    result = run_single_case(self.phone)
                except (Exception) as e:
                    self.phone.logerror(f"任务执行失败:{e}")
                    result = False
                if result:
                    break
                self.phone.logerror(f"{task_id}_{task_data['task']} 测试失败，重试第{j+1}次")
            if result:
                existing_df = pd.DataFrame()
                if os.path.exists(xlsx_path):
                    if os.path.getsize(xlsx_path) > 0:
                        try:
                            # 尝试读取Excel文件
                            existing_df = pd.read_excel(xlsx_path, engine="openpyxl")
                        except (Exception) as e:
                            self.phone.logwarning(f"警告: 无法读取Excel文件 {xlsx_path}, 错误: {str(e)}")
                            existing_df = pd.DataFrame()
                new_row = pd.DataFrame([data_dict])
                combined_df = pd.concat([existing_df, new_row], ignore_index=True)
                combined_df.to_excel(xlsx_path, index=False, engine="openpyxl")
                
                # 同时将结果写入 JSON 文件（实时结果，供报告展示）
                json_path = f"{self.phone.logrootdir}/power_results.json"
                power_result = {
                    "task_id": data_dict.get("task_id", ""),
                    "task": data_dict.get("task", ""),
                    "case_id": data_dict.get("case_id", ""),
                    "current_mA": data_dict.get("current"),
                    "timestamp": data_dict.get("test_time", ""),
                }
                # 读取现有结果或创建新文件
                results_list = []
                if os.path.exists(json_path):
                    try:
                        with open(json_path, 'r', encoding='utf-8') as f:
                            results_list = json.load(f)
                    except Exception:
                        results_list = []
                results_list.append(power_result)
                with open(json_path, 'w', encoding='utf-8') as f:
                    json.dump(results_list, f, ensure_ascii=False, indent=2)
        if not os.path.exists(xlsx_path):
            return False
        self.phone.loginfo(f"开始生成bugreport,大约需要5分钟")
        adb.get_bugreport(self.phone.serial, f"{self.phone.logrootdir}/{self.phone.logsubdir}/")
        time.sleep(10)
        # 压缩日志目录
        if os.path.exists(f"{self.phone.logrootdir}/{self.phone.logsubdir}"):
            shutil.make_archive(f"{self.phone.logrootdir}/{self.phone.logsubdir}", 'zip', f"{self.phone.logrootdir}/{self.phone.logsubdir}")
            shutil.rmtree(f"{self.phone.logrootdir}/{self.phone.logsubdir}")
            if self.phone.debug:
                self.tabletask.add_upload_powercloud(f"debug_{self.phone.model}", f"{self.phone.logrootdir}/{self.phone.logsubdir}")
            else :
                self.tabletask.add_upload_powercloud(self.phone.model, f"{self.phone.logrootdir}/{self.phone.logsubdir}")
            self.phone.loginfo(f"日志路径已添加到上传列表: {f'{self.phone.logrootdir}/{self.phone.logsubdir}'}")
        else :
            self.phone.logerror(f"日志路径不存在: {f'{self.phone.logrootdir}/{self.phone.logsubdir}'}")
            return False
        return True
