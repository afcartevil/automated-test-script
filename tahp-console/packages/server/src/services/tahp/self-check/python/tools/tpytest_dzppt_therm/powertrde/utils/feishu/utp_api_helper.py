import concurrent.futures
import json
import os
import time
import uuid
import zipfile
from datetime import datetime

import requests
import hashlib

from powertrde.framework.tran_logger import t_log
from powertrde.utils import misc_utils


class UTPApiHelper:
    def __init__(self, access_key: str = '679d854d', secret_key: str = 'e521b58beebf4f509a847c151a0b9a79'):
        self.access_key = access_key
        self.secret_key = secret_key
        self._uat = 'pfgatewayuat.transsion.com:9199/utp-task'
        self._production = 'pfgatewaysz.transsion.com:9199/utp-task'
        self.dou_name = {"PPT_Power_UserScenario_00676": "asia_30",
                         "PPT_Power_UserScenario_00828": "asia_33",
                         "PPT_Power_UserScenario_00827": "africa_31",
                         "PPT_Power_UserScenario_00831": "manual", # 加了三条手动填
                         "PPT_overseas_Power_test_0705": "asia_33",
                         "PPT_overseas_Power_test_0856": "africa_31",
                         "nana_tesssssst123": "mock"}

    def _generate_utp_token(self) -> str:
        version = "v1"
        _timestamp = str(int(time.time()))
        _nonce = uuid.uuid4().hex
        plain_text = f"{version}|{_timestamp}|{self.access_key}|{_nonce}|{self.secret_key}"

        _sign = hashlib.md5(plain_text.encode('utf-8')).hexdigest()
        token = f"{version}|{_timestamp}|{self.access_key}|{_nonce}|{_sign}"
        return token

        # secret_key = base64.b64decode(self.secret_key)
        # iv = os.urandom(12)
        # cipher = AES.new(secret_key, AES.MODE_GCM, nonce=iv)
        # ciphertext, tag = cipher.encrypt_and_digest(token.encode("utf-8"))
        # result = iv + ciphertext + tag
        # return base64.b64encode(result).decode("utf-8")

    def _get_tcids_and_project(self, task_id: int):
        """
        获取tcids和project
        """
        # url = f'https://{self._uat}/openapi/dataCenter/queryTaskInfo'
        url = f'https://{self._production}/openapi/dataCenter/queryTaskInfo'

        utp_token = self._generate_utp_token()
        headers = {
            "Content-Type": "application/json",
            "UTP-TOKEN": utp_token
        }
        data = {
            "taskId": task_id
        }
        response = requests.request('POST', url, headers=headers, json=data)
        res = json.loads(response.text)
        if res.get('success'):
            data = res.get('data')
            if data is not None:
                return data.get('tcids'), data.get('project')
            else:
                return []
        else:
            raise Exception(f"Failed to check out: {res.get('message')}")

    def check_out_dou(self, task_id, mode_name):
        tcids, project = self._get_tcids_and_project(task_id)
        sort_tcids = sorted(tcids)[:-5]
        if self.dou_name[sort_tcids[-1]] == mode_name:
            return project
        elif self.dou_name[sort_tcids[-1]] == "manual":
            if self.dou_name[sort_tcids[-4]] == mode_name:
                return project
        else:
            raise Exception(
                f"the current test is {mode_name}, which is not match {self.dou_name[tcids[-1]]} for {task_id}")

    def verify_taskid(self, task_id: int):
        try:
            tcids, project = self._get_tcids_and_project(int(task_id))
            ok = bool(tcids)
            return ok, (project or '')
        except Exception:
            return False, ''

    def _upload_utp(self, bizNo: str, data: list,extend_data:list=None):
        """
        数据上传

        :param bizNo: 所有任务都需要唯一的bizNo
        """
        # url = f'https://{self._uat}/openapi/dataCenter/dataUpload'
        url = f'https://{self._production}/openapi/dataCenter/dataUpload'

        utp_token = self._generate_utp_token()
        headers = {
            "Content-Type": "application/json",
            "UTP-TOKEN": utp_token
        }

        result = {
            "bizNo": bizNo,
            "appId": self.access_key,
            "data": data,
            "douExtendData": extend_data
        }
        response = requests.request('POST', url, headers=headers, json=result)
        res = json.loads(response.text)
        if res.get('success'):
            return True
        else:
            raise Exception(f"Failed to upload utp data: {res.get('message')}")

    def _search_package(self, package_list:list):
        """
        根据包查询包名
        """
        url = f'https://{self._production}/openapi/artifactory/apk/package/version/search'

        utp_token = self._generate_utp_token()
        # 定义请求头，包括UTP-TOKEN
        headers = {
            'UTP-TOKEN': utp_token
        }

        # 定义请求体数据
        # data_json = [
        #     "com.facebook.orca",
        #     "video.like",
        #     "com.mxtech.videoplayer.ad"
        # ]

        # 发送POST请求到JSON接口
        response = requests.post(url, headers=headers, json=package_list)

        # 处理JSON响应
        ct = response.headers.get('Content-Type', '')
        if ct.startswith('application/json'):
            decoded = response.content.decode('utf-8')
            parsed = json.loads(decoded)
            data_list = parsed.get('data', [])

            # # 从返回的 data 中提取所有 packageName
            # returned_packages = {str(item['packageName']).lower() for item in data_list if 'packageName' in item}
            #
            # # 找出 package_list 中没有出现在返回里的包名
            # missing_packages = [pkg for pkg in package_list if pkg.lower() not in returned_packages]
            #
            # print(f"返回结果总数: {len(data_list)}")
            # print(f"缺失的包名有 ({len(missing_packages)} 个):")
            # print(missing_packages)
            # apkInfoExtralist = []
            # not_int_list = []
            # for d in data_list:
            #     if d.get('apkInfoExtra', '').startswith("zygote"):
            #         apkInfoExtralist.append((d['packageName'], d['apkInfoExtra']))
            #     else:
            #         not_int_list.append(d['packageName'])
            #
            # print(f"有位数的:{apkInfoExtralist}")
            # print(f"没有位数的:{not_int_list}")

            return data_list
        else:
            raise Exception(f"Unexpected Content-Type: {ct}")

    def find_missing_packages(self, package_list: list):
        """
        查找缺失的包（在package_list中但API未返回的包）

        :param package_list: 要搜索的包名列表
        :return: 缺失的包名列表
        """
        data_list = self._search_package(package_list)

        # 从返回的 data 中提取所有 packageName
        returned_packages = {str(item['packageName']).lower() for item in data_list if 'packageName' in item}

        # 找出 package_list 中没有出现在返回里的包名
        missing_packages = [pkg for pkg in package_list if pkg.lower() not in returned_packages]

        return missing_packages

    def get_package_versions(self, package_list: list):
        """
        获取包的版本信息

        :param package_list: 要搜索的包名列表
        :return: 包含版本信息的字典，格式为 {packageName: {version: str, updateTime: str, apkInfoExtra: str}}
        """
        data_list = self._search_package(package_list)

        version_info = {}
        for item in data_list:
            package_name = item.get('packageName')
            if package_name:
                version_info[package_name] = {
                    'latestVersion': item.get('latestVersion', ''),
                    'updateTime': item.get('updateTime', '')
                }

        return version_info

    def _download_apk(self, package, save_place=r'D:\dz_auto_env_configs\app_res'):
        """
        下载单个apk,目前默认下载64位包
        """
        url = f'https://{self._production}/openapi/artifactory/apk/package/download'

        utp_token = self._generate_utp_token()
        headers = {
            "Content-Type": "application/json",
            "UTP-TOKEN": utp_token
        }

        data_octet_stream = {
            "packageName": package,
            "bit": "zygote64_32"
        }

        response = requests.request('POST', url, headers=headers, json=data_octet_stream)
        if response.headers['Content-Type'] == 'application/zip':
            filename = f"{package}.zip"

            if os.path.exists(rf"{save_place}\{filename}"):
                print(f"{filename} already exists")
                return

            # 保存文件
            with open(rf"{save_place}\{filename}", 'wb') as file:
                file.write(response.content)

            print(f"Octet-stream response saved as {filename}")
        else:
            print("Status Code:", response.status_code)
            print("Response Headers:", response.headers)
            print("Response Content:", response.text)
            print("Unexpected Content-Type for octet-stream response")

    def multiple_download_apk(self, package_list, save_place):
        MAX_WORKERS = 50

        # 使用线程池执行任务
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [executor.submit(self._download_apk, pkg, save_place) for pkg in package_list]
            concurrent.futures.wait(futures)

    def _upload_package(self, package_list:list):
        """
        根据包查询包名
        """
        url = f'http://10.150.154.193/cats/topapk/upload3rdApk'

        utp_token = self._generate_utp_token()
        # 定义请求头，包括UTP-TOKEN
        headers = {
            'UTP-TOKEN': utp_token
        }

        # 发送POST请求到JSON接口
        response = requests.post(url, headers=headers, json=package_list)

        # 处理JSON响应
        ct = response.headers.get('Content-Type', '')
        if ct.startswith('application/json'):
            decoded = response.content.decode('utf-8')
            parsed = json.loads(decoded)
            data_list = parsed.get('data', [])

            # 从返回的 data 中提取所有 packageName
            returned_packages = {str(item['packageName']).lower() for item in data_list if 'packageName' in item}

            # 找出 package_list 中没有出现在返回里的包名
            missing_packages = [pkg for pkg in package_list if pkg.lower() not in returned_packages]

            print(f"返回结果总数: {len(data_list)}")
            print(f"缺失的包名有 ({len(missing_packages)} 个):")
            print(missing_packages)
            apkInfoExtralist = []
            not_int_list = []
            for d in data_list:
                if d.get('apkInfoExtra', '').startswith("zygote"):
                    apkInfoExtralist.append((d['packageName'], d['apkInfoExtra']))
                else:
                    not_int_list.append(d['packageName'])

            print(f"有位数的:{apkInfoExtralist}")
            print(f"没有位数的:{not_int_list}")

            return (missing_packages)
        else:
            raise Exception("Unexpected Content-Type:", ct)

    def install_apps_from_zip(self, package_list, local_dir, sn):
        """从zip文件安装应用 - zip是从utp上拉的，其他的不保证能 用"""
        from powertrde.utils.trde import adb
        import os
        import zipfile
        import tempfile

        for package_name in package_list:
            zip_path = os.path.join(local_dir, f"{package_name}.zip")
            if not os.path.exists(zip_path):
                continue

            try:
                with zipfile.ZipFile(zip_path, 'r') as zf:
                    # 提取所有APK文件到临时位置
                    apk_files = [f for f in zf.namelist() if f.endswith('.apk')]

                    if not apk_files:
                        t_log.error(f"zip中无APK文件: {package_name}")
                        continue

                    temp_apks = []
                    for apk_file in apk_files:
                        temp_apk = tempfile.mktemp(suffix='.apk')
                        with open(temp_apk, 'wb') as f:
                            f.write(zf.read(apk_file))
                        temp_apks.append(temp_apk)

                    try:
                        # 安装APK
                        if len(temp_apks) == 1:
                            success = adb.install_apk(sn, temp_apks[0])
                        else:
                            # 多APK安装
                            cmd_parts = ['adb', '-s', sn, 'install-multiple'] + temp_apks
                            import subprocess
                            result = subprocess.run(cmd_parts, capture_output=True, text=True)
                            success = result.returncode == 0

                        if success:
                            t_log.info(f"已安装: {package_name}")
                        else:
                            t_log.error(f"安装失败: {package_name}")

                    finally:
                        for temp_apk in temp_apks:
                            if os.path.exists(temp_apk):
                                os.unlink(temp_apk)

            except Exception as e:
                t_log.error(f"安装异常 {package_name}: {e}")

    def get_zip_version(self, zip_path):
        """
        从zip文件中提取apk版本信息（可以获取本地的，utp上的直接从search里拉取）
        """
        try:
            with zipfile.ZipFile(zip_path) as zf:
                apk = next((f for f in zf.namelist() if f.endswith('.apk')), None)
                if apk:
                    import tempfile
                    tmp = tempfile.mktemp('.apk')
                    with open(tmp, 'wb') as f: f.write(zf.read(apk))
                    ver = misc_utils.get_apk_file_version(tmp)
                    os.unlink(tmp)
                    return ver
        except:
            pass
        return None

    def upload_perf_data(self, file_path, record_time=None):
        """
        上传性能数据看板

        Args:
            file_path: 要上传的文件路径
            data_source: 数据源标识
            record_time: 记录时间，如果为None则使用当前时间
        """
        # url = f"https://{self._production}/openapi/performance/upload"
        url = f"https://{self._uat}/openapi/performance/upload"

        if not os.path.exists(file_path):
            return {
                "success": False,
                "message": f"文件不存在: {file_path}"
            }

        if record_time is None:
            record_time = datetime.now().strftime("%Y-%m-%d 00:00:00")
        else:
            record_time = "2027-00-00 00:00:00"

        try:
            # 生成token
            token = self._generate_utp_token()

            # 设置请求头
            headers = {
                "UTP-TOKEN": token,
            }

            # 准备multipart/form-data数据
            with open(file_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(file_path), f, 'application/json')
                }

                data = {
                    'file': file_path,
                    'dataSource': "TEST_DATA",
                    'recordTime': record_time
                }


                # 发送POST请求
                response = requests.post(
                    url,
                    files=files,
                    data=data,
                    headers=headers,
                    verify=False,
                    timeout=30
                )

            # 解析响应
            if response.status_code == 200:
                result = response.json()
                is_success = (result.get("code") == "200" or
                              result.get("success") == True or
                              response.status_code == 200)

                return {
                    "success": is_success,
                    "code": result.get("code", ""),
                    "message": result.get("message", ""),
                    "detail_message": result.get("detailMessage", ""),
                    "data": result.get("data", {}),
                    "raw_response": result
                }
            else:
                return {
                    "success": False,
                    "message": f"HTTP错误: {response.status_code}",
                    "detail_message": response.text
                }

        except Exception as e:
            return {
                "success": False,
                "message": f"上传过程中发生错误: {str(e)}"
            }

def get_utp_taskid_manual_window(title='The taskId from UTP', tips='Input the taskid:',
                                 default_number='', timeout=10):
    """
    弹出一个Tkinter窗口，要求用户utp的taskID。
    输入框限制只能输入数字。

    Returns:
        int: taskid。
    """
    import tkinter as tk
    # 创建主窗口
    root = tk.Tk()
    root.title(title)
    root.geometry("300x150")  # 设置窗口大小

    taskid = tk.StringVar(value=default_number)  # 用于存储用户输入的电话号码，并设置默认值
    has_interacted = [False if default_number else True]  # 用于检测用户是否与输入框交互

    def validate_input(*args):
        """
        限制输入框中只能输入数字。
        如果输入合法，启用OK按钮；否则禁用OK按钮。
        """
        valid_chars = "0123456789"
        current_text = taskid.get()

        # 检查是否所有字符都合法
        if all(char in valid_chars for char in current_text):
            ok_button.config(state="normal")
        else:
            ok_button.config(state="disabled")

        # 如果检测到用户手动修改输入框内容，则取消自动超时关闭
        has_interacted[0] = True

    def on_ok():
        """
        点击OK按钮时退出主窗口。
        """
        root.destroy()

    def auto_close():
        """
        如果达到超时时间且用户未进行任何操作，则自动点击OK按钮。
        """
        if not has_interacted[0]:  # 检测是否有用户交互
            on_ok()

    # 提示文字
    label = tk.Label(root, text=tips, font=("Arial", 12))
    label.pack(pady=10)

    # 输入框
    entry = tk.Entry(root, textvariable=taskid, font=("Arial", 12))
    entry.pack(pady=5)

    # 绑定输入框的变化事件
    taskid.trace_add("write", validate_input)

    # OK按钮
    ok_button = tk.Button(root, text="OK", font=("Arial", 12), command=on_ok, state="normal")
    ok_button.pack(pady=10)

    # 启动超时机制
    if default_number:
        root.after(timeout * 1000, auto_close)

    # 进入主事件循环，显示窗口
    root.mainloop()

    # 返回电话号码
    return int(taskid.get())


if __name__ == '__main__':
    # utp = UTPApiHelper('679d854d', 'e521b58beebf4f509a847c151a0b9a79')
    # 下载包
    # utp = UTPApiHelper('ru9k74pa', '8noZHKdTZAkPt0igiAFkJawHgGu4t5u4')
    # try:
    #     utp._search_package()
    #     # utp._download_apk("com.facebook.katana")
    # except Exception as e:
    #     print(str(e))
    from pathlib import Path
    directory = Path(r'E:\try_dou3')
    processed_names = []

    for file_path in directory.rglob('*'):
        if file_path.is_file() and file_path.stat().st_size == 0:
            filename = file_path.name
            # 去掉-zygote64_32.zip后缀
            processed_name = filename.replace('-zygote64_32.zip', '') if filename.endswith(
                '-zygote64_32.zip') else filename
            processed_names.append(processed_name)
            print(f"原始: {filename} -> 处理后: {processed_name}")

    print(processed_names)
