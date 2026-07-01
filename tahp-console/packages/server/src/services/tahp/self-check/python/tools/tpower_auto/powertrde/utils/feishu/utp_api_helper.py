import concurrent.futures
import json
import time
import uuid

import requests
import hashlib


class UTPApiHelper:
    def __init__(self, access_key: str = '679d854d', secret_key: str = 'e521b58beebf4f509a847c151a0b9a79'):
        self.access_key = access_key
        self.secret_key = secret_key
        self._uat = 'pfgatewayuat.transsion.com:9199/utp-task'
        self._production = 'pfgatewaysz.transsion.com:9199/utp-task'
        self.dou_name = {"PPT_Power_UserScenario_00676": "asia_30",
                         "PPT_Power_UserScenario_00828": "asia_31",
                         "PPT_Power_UserScenario_00827": "africa_31",
                         "PPT_Power_UserScenario_00831": "manual", # 加了三条手动填
                         "PPT_overseas_Power_test_0705": "asia_31",
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
        sort_tcids = sorted(tcids)
        if self.dou_name[sort_tcids[-1]] == mode_name:
            return project
        elif self.dou_name[sort_tcids[-1]] == "manual":
            if self.dou_name[sort_tcids[-4]] == mode_name:
                return project
        else:
            raise Exception(
                f"the current test is {mode_name}, which is not match {self.dou_name[tcids[-1]]} for {task_id}")

    def _upload_utp(self, bizNo: str, data: list):
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
            "data": data
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

            return missing_packages
        else:
            raise Exception("Unexpected Content-Type:", ct)

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
            # 提取 Content-Disposition 头中的 filename
            content_disposition = response.headers.get('Content-Disposition', '')
            filename = f"{package}.zip"  # 默认文件名

            if 'filename=' in content_disposition:
                filename = content_disposition.split('filename=')[1].strip(' "')
            import os
            if os.path.exists(rf"E:\try_dou3\{filename}"):
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
