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

def task_proc_thread():
    device_threads = {}
    debug = False # 是否为测试环境
    tabletask = TableTask(debug)
    device = Device()
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
        
        # 2. 为新设备创建线程
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
        time.sleep(60)  # 确保扫描间隔不低于1分钟

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
        try:
            phone.pre_phone_check_wifi_connection()
        except Exception as e:
            phone.logerror(f"WiFi连接失败, 异常信息: {e}")
            time.sleep(60)
            continue
        try:
            taskmanager.run()
        except Exception as e:
            phone.logerror(f"任务执行失败, 异常信息: {e}")
        if taskmanager.reboot:
            break
        time.sleep(60)

class TaskManager:
    def __init__(self, phone: PhoneConfig, tabletask: TableTask):
        self.phone = phone
        self.tabletask = tabletask
        self.weekday = -1
        self.reboot = False
        
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
                    self.basetestcnt += 1
                    self.phone.loginfo(f"基础功耗测试第{self.basetestcnt}轮开始")
                    self.task = tasks_base
                    battery_level = adb.get_battery_percent(self.phone.serial)
                    if(battery_level < 80):
                        self.phone.loginfo(f"当前电量{battery_level},设置为80%")
                        self.phone.u2d_helper.set_fake_battery_level(80)
                    self.run_task()
                    self.phone.loginfo(f"基础功耗测试第{self.basetestcnt}轮结束")
                    if self.phone.debug or self.basetestcnt >= 3: #DEBUG 只测一次
                        self.basetest = False
                        self.phone.loginfo(f"今日基础功耗测试任务已完成")
                    return

    def run_ontime_standby_task(self):
        self.standbyconf = self.tabletask.get_standby_tasks()
        assert self.standbyconf is not None, "获取待机任务失败"
        if self.datastandby:
            if 'data' not in self.plan or self.weekstr not in self.plan['data']['week']:
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
            if 'wifi' not in self.plan or self.weekstr not in self.plan['wifi']['week']:
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
        if self.datastandby:
            if 'data' not in self.plan or self.weekstr not in self.plan['data']['week']:
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
            if 'wifi' not in self.plan or self.weekstr not in self.plan['wifi']['week']:
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
