import json
import os
import shutil
import time
from typing import Optional
import certifi
import requests


class FeishuApiHelper:
    def __init__(self, app_id: str, app_secret: str):
        """
        初始化 Feishu 类，设置 app_id 和 app_secret。
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self._access_token = None
        self._table_group_tokens = {}
        self._root_folder_tokens = {}
        self._token_issue_time = 0

    @property
    def access_token(self):
        # 每小时更新一次 access_token
        if self._access_token is None or time.time() - self._token_issue_time > 3600:
            self._access_token = self._get_tenant_access_token()
            self._token_issue_time = time.time()
        return self._access_token

    def _get_tenant_access_token(self):
        """
        通过 app_id 和 app_secret 获取飞书 API 的访问令牌。
        """
        # 参数是飞书的token获取接口
        url = 'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal'
        headers = {
            'Content-Type': 'application/json; charset=utf-8'
        }
        data = json.dumps({'app_id': self.app_id, 'app_secret': self.app_secret})
        response = requests.request('POST', url, headers=headers, data=data)
        res = json.loads(response.text)
        if res.get('code') == 0:
            return res['tenant_access_token']
        else:
            raise Exception(f"Failed to get tenant access token: {res.get('msg')}")

    def list_groups(self):
        """
        获取有权限访问的群组列表（chat_id 和 name）。
        """
        url = "https://open.feishu.cn/open-apis/im/v1/chats?page_size=100"
        headers = {
            'Authorization': f'Bearer {self.access_token}'
        }
        response = requests.get(url, headers=headers)
        res = response.json()
        if res.get('code') == 0:
            chat_list = [(i['name'], i['chat_id']) for i in res['data']['items']]
            for c in chat_list:
                print(c)
            return chat_list
        else:
            raise Exception(f"Failed to list groups: {res.get('msg')}")

    def _get_folder_contents(self, folder_token, file_token=None, name=None, mtype=None, owner_id=None):
        """
        根据某个条件返回该文件的所有信息(token, name, type, parent_token, url, created_time, modified_time, owner_id)
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/files"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "folder_token": folder_token,
            "direction": "ASC"
        }
        response = requests.get(url, headers=headers, params=params)
        res = response.json()

        if res.get("code") == 0:
            files = res.get("data", {}).get("files", [])
            # 根据传入的 condition 进行筛选
            filtered_files = []
            for file in files:
                if file_token and file.get("token") == file_token:
                    return [file]
                if name and file.get("name") != name:
                    continue
                if mtype and file.get("type") != mtype:
                    continue
                if owner_id and file.get("owner_id") != owner_id:
                    continue
                filtered_files.append(file)
        else:
            raise Exception(f"Failed to get folder contents: {res.get('msg')} (code: {res.get('code')})")

    def search_folder(self, parent_token: str, folder_name: Optional[str] = None, file_token: Optional[str] = None,
                      mtype: Optional[str] = None, owner_id: Optional[str] = None, only_first_file=True):
        """
        :param parent_token: 父文件夹的 token。
        :param folder_name: 目标文件/文件夹的名称，精确匹配。
        :param file_token: 指定文件的 token（一般用于直接查找）。
        :param mtype: 目标的类型，例如 "doc"。
        :param owner_id: 目标文件/文件夹所有者的用户 ID。
        :param only_first_file: 是否只返回第一个匹配的文件，默认 True。如果 False，返回所有符合条件的文件列表。
        按指定条件查找返回该文件夹信息，默认返回文件夹下所有文件夹信息
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/files"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        params = {
            "folder_token": parent_token
        }
        response = requests.get(url, headers=headers, params=params)
        res = response.json()
        if res.get("code") == 0:
            files = res.get("data", {}).get("files", [])
            # 根据传入的 condition 进行筛选
            filtered_files = []
            for file in files:
                if file_token and file.get("token") != file_token:
                    continue
                if folder_name and file.get("name") != folder_name:
                    continue
                if mtype and file.get("type") != mtype:
                    continue
                if owner_id and file.get("owner_id") != owner_id:
                    continue
                filtered_files.append(file)

            if only_first_file:
                if filtered_files:
                    return filtered_files[0]
                else:
                    return None
            else:
                return filtered_files
        else:
            return None

    def create_folder(self, folder_name: str, parent_token: str):
        """
        在当前文件夹下建立一个新的文件夹，并返回该文件夹信息
        """
        # 验证文件夹名称是否符合规则
        invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
        if any(char in folder_name for char in invalid_chars):
            raise ValueError(f"Folder name '{folder_name}' contains invalid characters.")

        if len(folder_name) > 255:
            raise ValueError(f"Folder name '{folder_name}' exceeds 255 characters.")

        url = "https://open.feishu.cn/open-apis/drive/v1/files/create_folder"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        json_data = {
            "name": folder_name,
            "folder_token": parent_token,
            "type": "folder"
        }
        response = requests.post(url, headers=headers, json=json_data)
        res = response.json()
        if res.get("code") == 0:
            return res
        else:
            raise Exception(f"Create folder failed: {res.get('msg')}")

    def get_or_creat_folder_token(self, folder_name: str, parent_token: str):
        # 检查文件夹是否存在，存在则直接返回token，否则创建文件夹并返回token
        folder = self.search_folder(parent_token=parent_token, folder_name=folder_name)
        if folder:
            return folder["token"]
        return self.create_folder(folder_name, parent_token)["data"]["token"]

    def search_folder_recursive(self, parent_token, folder_path):
        """
        递归查询文件夹路径并返回目标文件夹的 token
        :param parent_token: str, 父文件夹 token
        :param folder_path: str, 文件夹路径，例如 "dou3/1234"

        :return str, 最终目标文件夹的全部信息
        """
        folders = folder_path.split("/")  # 分割路径
        current_token = parent_token
        final_folder = None

        for folder_name in folders:
            file = self.search_folder(current_token, folder_name)
            if file:
                current_token = file["token"]  # 更新当前文件夹 token
                final_folder = file
                continue
            else:
                print(f"Folder '{folder_name}' not found.")
                return None

        return final_folder

    def _upload_file(self, folder_token, file_path, file_name):
        """
        上传单个文件(单个文件不超过20MB，且网络稳定)

        :param folder_token: 上传该文件夹的token
        :param file_path: 本地文件路径
        :param file_name: 文件取名

        :return 上传文件的token
        """
        url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_all"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        file_size = os.path.getsize(file_path)

        with open(file_path, "rb") as f:
            files = {
                "file": (file_name, f, "application/octet-stream"),
            }
            data = {
                "file_name": file_name,
                "parent_type": "explorer",
                "parent_node": folder_token,
                "size": str(file_size)
            }

            response = requests.post(url, headers=headers, files=files, data=data)
        res = response.json()
        if res.get("code") == 0:
            return res["data"]["file_token"]
        else:
            raise Exception(f"Failed to upload file: {res.get('msg')}")

    def _upload_large_file(self, folder_token: str, file_path: str, file_name: str):
        """
        上传大文件(单个文件超过20MB建议分片)

        :param folder_token: 上传该文件夹的token
        :param file_path: 本地文件路径
        :param file_name: 文件取名

        :return 上传文件的token
        """
        file_size = os.path.getsize(file_path)

        # Step 1: 预上传，获取 upload_id 和分片信息
        url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_prepare"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        json_data = {
            "parent_type": "explorer",
            "parent_node": folder_token,
            "file_name": file_name,
            "size": file_size
        }
        response = requests.post(url, headers=headers, json=json_data)
        res = response.json()
        if res.get("code") == 0:
            upload_id, block_num, block_size = res["data"]["upload_id"], res["data"]["block_num"], res["data"][
                "block_size"]
        else:
            raise Exception(f"Failed to prepare upload: {res.get('msg')} (code: {res.get('code')})")

        # Step 2: 上传分片
        offset = 0
        url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_part"
        for part_number in range(0, block_num):
            part_size = min(block_size, file_size - offset)
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                # "Content-Type": "multipart/form-data; boundary=---7MA4YWxkTrZu0gW"
            }
            with open(file_path, "rb") as f:
                f.seek(offset)
                file = f.read(part_size)
            data = {
                "upload_id": upload_id,
                "seq": str(part_number),
                "size": str(part_size)
            }

            files = {
                "file": ("blob", file)
            }
            for attempt in range(3):  # 重试机制
                response = requests.post(
                    url, headers=headers, data=data, files=files, timeout=30, verify=certifi.where())
                res = response.json()
                if res.get("code") == 0:
                    break
                elif attempt == 2:
                    raise Exception(f"Failed to upload part {part_number}: {res.get('msg')} (code: {res.get('code')})")

            offset += part_size

        # Step 3: 完成上传
        url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_finish"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        json_data = {
            "upload_id": upload_id,
            "block_num": block_num
        }
        response = requests.post(url, headers=headers, json=json_data)
        res = response.json()
        if res.get("code") == 0:
            return res["data"]["file_token"]
        else:
            raise Exception(f"Failed to finish upload: {res.get('msg')} (code: {res.get('code')})")

    def upload_file_auto(self, local_path, remote_token):
        if not os.path.isfile(local_path):
            return None
        file_size = os.path.getsize(local_path)
        file_name = os.path.basename(local_path)
        # 判断文件大小，选择合适的上传方式
        if file_size > 20 * 1024 * 1024:  # 文件大于20MB使用分片上传
            file_token = self._upload_large_file(remote_token, local_path, file_name)
        else:
            # 小文件直接上传
            file_token = self._upload_file(remote_token, local_path, file_name)
        return file_token
    
    def upload_folder_auto(self, local_path, remote_token):
        """
        递归上传本地文件夹/本地大小文件到云端
        :param local_path: 需要上传的本地文件夹路径
        :param remote_token: 上传的远端文件夹token(文件夹路径可配合search_folder_recursive使用)

        :return 上传文件的token
        """
        # 如果 local_path 是一个文件，直接上传
        if os.path.isfile(local_path):
            return self.upload_file_auto(local_path, remote_token)  # 处理完文件后直接返回，不再继续执行递归

        try:
            entries = os.listdir(local_path)
        except Exception as _err:
            raise Exception(f"Cannot list directory {local_path}: {_err}")

        # 如果目录为空，直接返回
        if not entries:
            print(f"Directory {local_path} is empty, skipping.")
            return

        for entry in entries:
            full_path = os.path.join(local_path, entry)
            try:
                if os.path.isdir(full_path):
                    sub_folder_token = self.get_or_creat_folder_token(entry, remote_token)
                    if not sub_folder_token:
                        print(f"Failed to create folder token for: {entry}")
                        continue
                    self.upload_folder_auto(full_path, sub_folder_token)
                else:
                    file_size = os.path.getsize(full_path)
                    # 判断文件大小，如果大于 20MB，使用大文件上传
                    if file_size > 20 * 1024 * 1024:  # 20MB
                        self._upload_large_file(remote_token, full_path, entry)
                    else:
                        # 正常上传小文件
                        self._upload_file(remote_token, full_path, entry)
            except Exception as _err:
                raise Exception(f"Error processing {entry}: {_err}")

    def delete_file_or_folder(self, file_token, file_type):
        """
        删除文件或文件夹
        :param file_token: 需要删除的文件夹token(文件夹路径可配合search_folder_recursive使用)
        :param file_type: 被删除文件的类型
            (可选值有：
                file：文件类型
                docx：新版文档类型
                bitable：多维表格类型
                folder：文件夹类型
                doc：文档类型
                sheet：电子表格类型
                mindnote：思维笔记类型
                shortcut：快捷方式类型
                slides：幻灯片)

        :return 上传文件的token
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "type": file_type
        }
        response = requests.delete(url, headers=headers, params=params)
        res = response.json()
        if res.get("code") == 0:
            print(f"Deleted {file_type}: {file_token}")
        else:
            raise Exception(f"Failed to delete {file_type}: {res.get('msg')} (code: {res.get('code')})")

    def compress_and_upload_folder(self, local_folder_path, cloud_folder_token):
        """
        将文件夹打包为zip上传
        """
        # 检查路径是否为文件夹
        if not os.path.isdir(local_folder_path):
            raise Exception(f"{local_folder_path} is not a folder.")

        # 压缩文件夹为 ZIP 文件
        zip_file_path = f"{local_folder_path}.zip"
        shutil.make_archive(local_folder_path, 'zip', local_folder_path)

        # 上传 ZIP 文件
        file_name = os.path.basename(zip_file_path)
        try:
            file_token = self._upload_file(cloud_folder_token, zip_file_path, file_name)
        except Exception as _err:
            raise Exception(f"File failed to upload: {_err}")

        # 删除本地 ZIP 文件
        os.remove(zip_file_path)

    def read_sheet_data(self, sheets_token: str, sheet_id: str):
        """
        return 数据的二维数据，datap[行][列]
        """
        url = f"https://open.feishu.cn/open-apis/sheets/v2/spreadsheets/{sheets_token}/values/{sheet_id}"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        response = requests.get(url, headers=headers)
        res = response.json()
        if res.get("code") == 0:
            return res["data"]["valueRange"]["values"]
        else:
            raise Exception(f"Failed to read sheet data: {res.get('msg')}")

    def get_table_token_by_name(self, table_token: str, table_name: str):
        """
        根据{table_token}飞书表格中的表名 获取该表格的token
        """
        url = f"https://open.feishu.cn/open-apis/sheets/v3/spreadsheets/{table_token}/sheets/query"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        response = requests.get(url, headers=headers)
        try:
            res = response.json()
        except json.JSONDecodeError as _err:
            raise Exception(f"Failed to parse response JSON: {_err}. Response text: {response.text}")
        if res.get("code") != 0:
            raise Exception(f"Failed to list sheets: {res.get('msg')}")

        sheets = res.get('data', {}).get('sheets', [])
        for sheet in sheets:
            if sheet.get('title') == table_name:
                return sheet.get('sheet_id')

        return None

    def getref_bitable_records(self, table_token: str, table_id: str, filter_model: str):
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables/{table_id}/records/search"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        data = {
            "field_names": [
                "task_id",
                "current",
                "filtermin"
            ],
            "filter": {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "model",
                        "operator": "is",
                        "value": [filter_model]
                    }
                ]
            },
            "automatic_fields": False
        }
        response = requests.post(url, headers=headers, json=data)
        res = response.json()
        if res.get("code") == 0:
            return res["data"]["items"]
        else:
            raise Exception(f"Failed to search records: {res.get('msg')}")

    def write_bitable_datalist(self, table_token: str, table_id: str, record_list: list):
        """
        添加飞书多维表格记录
        参数:
        :params table_token: str, 飞书多维表格的 token
        :params table_id: str, 飞书多维表格的 id,
        :params record_list: list, 要添加的记录列表，每个记录为一个字典，格式为 {字段名: 字段值}
        """
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables/{table_id}/records/batch_create"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        data = {
            "records": [{"fields": record} for record in record_list]
        }
        res = requests.post(url, headers=headers, json=data).json()
        if res.get("code") != 0:
            raise Exception(f"Failed to add record: {res.get('msg')} (code: {res.get('code')})")
        return True
    def write_bitable_data(self, table_token: str, table_id: str, record: dict):
        """
        添加飞书多维表格记录
        参数:
        :params table_token: str, 飞书多维表格的 token
        :params table_id: str, 飞书多维表格的 id,
        :params record: dict, 要添加的记录，格式为 {字段名: 字段值}
        """
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables/{table_id}/records"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }

        data = {
            "fields": record
        }
        res = requests.post(url, headers=headers, json=data).json()
        if res.get("code") != 0:
            raise Exception(f"Failed to add record: {res.get('msg')} (code: {res.get('code')})")
        return True

    def get_bitable_token_by_name(self, table_token: str, table_name: str):
        """
        根据{table_token}飞书表格中的表名 获取该表格的token
        """
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{table_token}/tables"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        response = requests.get(url, headers=headers)
        try:
            res = response.json()
        except json.JSONDecodeError as _err:
            raise Exception(f"Failed to parse response JSON: {_err}. Response text: {response.text}")
        if res.get("code") != 0:
            raise Exception(f"Failed to list tables: {res.get('msg')}")

        tables = res.get('data', {}).get('items', [])
        for table in tables:
            if table.get('name') == table_name:
                return table.get('table_id')

        return None

    def _download_file(self, file_token, save_path, save_name):
        """
        下载文件到本地,如果 save_path 是一个文件夹，则自动从响应中提取文件名保存
        参数:
        :params file_token: str, 飞书文件的 token
        :params save_path: str, 本地保存文件的路径
        :params save_name: str, 本地保存文件的名字
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "token": file_token,
        }

        # 创建上层目录（防止路径不存在）
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        save_path = os.path.join(save_path, save_name)

        try:
            response = requests.get(url, headers=headers, params=params, stream=True)
            if response.status_code == 200:
                with open(save_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                print(f"File downloaded successfully to {save_path}")
            else:
                raise Exception(f"Failed to download file: {response.json().get('msg')} (code: {response.status_code})")
        except Exception as err:
            raise Exception(e)

    def download_file_auto(self, file_token, save_path, save_name):
        """
        下载文件或者文件夹到本地, 如果 save_path 是一个文件夹，则自动从响应中提取文件名保存
        参数:
        :params file_token: str, 飞书文件的 token
        :params save_path: str, 本地保存文件的路径
        :params save_name: str, 本地保存文件的名字
        """
        folder_files = self.search_folder(parent_token=file_token, only_first_file=False)
        if folder_files:
            # 是文件夹：递归下载其中所有内容
            folder_local_path = os.path.join(save_path, save_name)
            os.makedirs(folder_local_path, exist_ok=True)

            for item in folder_files:
                self.download_file_auto(
                    file_token=item["token"],
                    save_path=folder_local_path,
                    save_name=item["name"]
                )
        else:
            # 是文件：保存路径与文件名
            self._download_file(file_token, save_path, save_name)

    def download_sheets(self, file_token, file_type, save_path, save_name=None, save_extension="xlsx"):
        """
        下载表格到本地
        参数:
        :params file_token: str, 飞书文件的 token
        :params file_type: str, 文件的类型(
            可选值有：
                sheet：飞书电子表格。支持导出扩展名为 xlsx 和 csv 的文件。
                bitable：飞书多维表格。支持导出扩展名为 xlsx 和 csv 格式的文件。
                docx：新版飞书文档。支持导出扩展名为 docx 和 pdf 格式的文件。)
        :params save_path: str, 本地保存文件的路径
        :params save_extension: str 本地保存文件的拓展名(
            可选值有：
                docx：Microsoft Word 格式
                pdf：PDF 格式
                xlsx：Microsoft Excel 格式
                csv：CSV 格式)
        """
        # step1: 创建导出任务
        url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        data = {
            "file_extension": save_extension,
            "token": file_token,
            "type": file_type
        }

        res1 = requests.post(url, headers=headers, json=data).json()
        if res1.get("code") != 0:
            raise Exception(f"Failed to create export task: {res1.get('msg')} (code: {res1.get('code')})")

        task_id = res1["data"]["ticket"]

        # step2: 查询导出任务结果
        url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks/{task_id}"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            "token": file_token
        }
        download_token = ""
        for i in range(5):
            res2 = requests.get(url, headers=headers, params=params).json()
            if res2.get("code") != 0:
                raise Exception(f"Failed to create export task: {res1.get('msg')} (code: {res1.get('code')})")

            status = res2["data"]["result"]["job_status"]
            if status == 0:  # 成功
                download_token = res2["data"]["result"]["file_token"]
                if not save_name:
                    save_name = res2["data"]["result"]["file_name"]
                break
            elif status in [1, 2]:  # 初始化或处理中
                time.sleep(3)
            else:  # 失败
                raise Exception(f"Export task failed: {res2['data']['result']['job_error_msg']}")


        # step3： 下载导出任务
        url = f"https://open.feishu.cn/open-apis/drive/v1/export_tasks/file/{download_token}/download"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        res3 = requests.get(url, headers=headers, stream=True)
        if res3.status_code == 200:
            os.makedirs(save_path, exist_ok=True)
            file_full_path = os.path.join(save_path, f"{save_name}.{save_extension}")
            with open(file_full_path, "wb") as f:
                for chunk in res3.iter_content(chunk_size=8192):
                    f.write(chunk)
            print(f"File downloaded successfully to {file_full_path}")
        else:
            raise Exception(f"Failed to download file: {res3.json().get('msg')} (code: {res3.status_code})")

    def register_table_group_token(self, table_group_name: str, table_group_token: str):
        self._table_group_tokens[table_group_name] = table_group_token

    def register_root_folder_token(self, root_folder_name: str, root_folder_token: str):
        self._root_folder_tokens[root_folder_name] = root_folder_token

    def get_table_group_token(self, table_group_name: str):
        return self._table_group_tokens.get(table_group_name, '')

    def get_root_folder_token(self, root_folder_name: str):
        return self._root_folder_tokens.get(root_folder_name, '')


if __name__ == '__main__':
    _app_id = 'cli_a88b4d15dc70100b'
    _app_secret = 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2'
    _feishu = FeishuApiHelper(_app_id, _app_secret)

    # 本地文件夹路径
    _local_folder_path = "C:\\Users\\tingting.yao1\\Desktop\\report.mp4"
    # 云盘文件夹 token
    _cloud_folder_token = "YrS8fQ630lE9KBdXpFbcWqh1nee"
    try:
        # _feishu._upload_large_file(cloud_folder_token, local_folder_path, '1.mp4')
        # d = _feishu.get_table_token_by_name('STlAs1HDZhqLG4tMB4xcIrtunSb', 'table_dou3_products')
        # feishu.delete_file_or_folder('W2A0f26MUlVZGCdkeepc1UEbnEc', "folder")
        # _feishu.download_file_auto('ASh0f02UNlnI3EdvDeecJfEinme', "C:\\Users\\tingting.yao1\\Desktop", "1")
        # _feishu.download_sheets('WbRxsI5uahP45Ntl8aTcXu2Anec', file_type='sheet', save_path = "C:\\Users\\tingting.yao1\\Desktop", save_name="1", save_extension="xlsx")
        f = _feishu.search_folder('XyGKfLvEGlkM7sdmyLacIHjsn9e', "apk_res")
        print(f)
    except Exception as e:
        print(str(e))
