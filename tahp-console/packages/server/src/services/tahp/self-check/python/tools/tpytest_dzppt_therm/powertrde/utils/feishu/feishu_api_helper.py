import hashlib
import json
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional
import certifi
import requests

from powertrde.framework.tran_logger import t_log


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
        self._access_token_expire_time = 0
        self.progress_callback = None

    @staticmethod
    def wash_hyperlink_texts_to_plain_text(oig_text: str) -> str:
        """
        将类似 "[{'cellPosition'": "None, 'link': 'mailto:doredia.lilligant@gmail.com', 'text': 'doredia.lilligant@gmail.com', 'type': 'url'}, {'text': '\\n', 'type': 'text'}, {'text': 'xxx', 'type': 'text'}]" 这样的飞书返回的超链接字符串清洗为正常字符串如：
        "doredia.lilligant@gmail.com\nxxx"
        如果本身传入的不是超链接类型字符串，则直接原封不动返回
        """
        s = (oig_text or '').strip()
        if not s:
            return oig_text

        # 简单判定是否为超链接类型（包含 text 字段，且整体像列表/字典结构）
        looks_structured = ('text' in s) and (s.startswith('[') or s.startswith('{'))
        if not looks_structured:
            return oig_text

        def collect_texts(obj) -> list[str]:
            texts: list[str] = []
            if isinstance(obj, list):
                for item in obj:
                    if isinstance(item, dict):
                        t = item.get('text')
                        if isinstance(t, str):
                            texts.append(t)
            elif isinstance(obj, dict):
                t = obj.get('text')
                if isinstance(t, str):
                    texts.append(t)
            return texts

        parsed_texts: list[str] | None = None

        # 1) 尝试按 JSON 解析（飞书部分接口返回标准 JSON）
        try:
            import json
            obj = json.loads(s)
            texts = collect_texts(obj)
            if texts:
                parsed_texts = texts
        except Exception:
            pass

        # 2) 回退到 Python 字面量解析（接口可能返回单引号的 repr 文本）
        if parsed_texts is None:
            try:
                import ast
                obj = ast.literal_eval(s)
                texts = collect_texts(obj)
                if texts:
                    parsed_texts = texts
            except Exception:
                pass

        # 3) 最后回退到正则扫描，直接提取 text 字段内容
        if parsed_texts is None:
            # 同时支持单引号与双引号形式
            pattern = r"'text':\s*'([^']*)'|\"text\":\s*\"([^\"]*)\""
            matches = re.findall(pattern, s)
            texts = []
            for m in matches:
                t = m[0] if m[0] else m[1]
                if t:
                    texts.append(t)
            if texts:
                parsed_texts = texts

        if parsed_texts is None:
            # 不符合预期结构，直接原样返回
            return oig_text

        # 解码转义序列（如 \n 等），保持可读性
        decoded: list[str] = []
        for t in parsed_texts:
            try:
                decoded.append(bytes(t, 'utf-8').decode('unicode_escape'))
            except Exception:
                decoded.append(t)

        return ''.join(decoded)

    @property
    def access_token(self):
        if self._access_token is None or time.time() > self._access_token_expire_time:
            self.refresh_access_token()
        return self._access_token
    
    def refresh_access_token(self):
        """强制刷新访问令牌"""
        self._access_token = self._get_tenant_access_token()
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
        self._access_token_expire_time = time.time() + res.get('expire', 0)
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
        
        filtered_files = []
        page_token = None
        has_more = True
        
        # 分页获取所有文件
        while has_more:
            params = {
                "folder_token": parent_token,
                "page_size": 200  # 每页最多200条
            }
            if page_token:
                params["page_token"] = page_token
            
            response = requests.get(url, headers=headers, params=params)
            res = response.json()
            
            if res.get("code") != 0:
                return None
            
            data = res.get("data", {})
            files = data.get("files", [])
            
            # 根据传入的条件进行筛选
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
                
                # 如果只需要第一个匹配的文件，找到后立即返回
                if only_first_file:
                    return filtered_files[0]
            
            # 检查是否还有更多数据
            has_more = data.get("has_more", False)
            page_token = data.get("next_page_token")
            
            # 防御性检查：如果has_more为True但page_token为空，终止循环
            if has_more and not page_token:
                break
        
        return filtered_files if filtered_files else None

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
        
        # 输出详细的请求和响应信息以便调试
        import logging
        logging.debug(f"Create folder request: name='{folder_name}', parent_token='{parent_token}'")
        logging.debug(f"Create folder response: {res}")
        
        if res.get("code") == 0:
            return res
        else:
            # 输出完整的错误信息以便调试
            error_detail = {
                'code': res.get('code'),
                'msg': res.get('msg'),
                'data': res.get('data'),
                'folder_name': folder_name,
                'parent_token': parent_token
            }
            logging.error(f"Create folder failed: {error_detail}")
            raise Exception(f"Create folder failed: code={res.get('code')}, msg={res.get('msg')}, folder_name='{folder_name}'")

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
                # print(f"Folder '{folder_name}' not found.")
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
            
            token_refreshed = False
            for attempt in range(3):  # 重试机制
                headers = {
                    "Authorization": f"Bearer {self.access_token}",
                }
                response = requests.post(
                    url, headers=headers, data=data, files=files, timeout=30, verify=certifi.where())
                res = response.json()
                
                if res.get("code") == 0:
                    break
                elif res.get("code") == 99991663:  # Invalid access token
                    if not token_refreshed:
                        # 令牌过期，刷新后重试
                        print(f"Token expired during part {part_number}, refreshing...")
                        self.refresh_access_token()
                        token_refreshed = True
                        continue  # 不计入重试次数，立即重试
                    elif attempt == 2:
                        raise Exception(f"Failed to upload part {part_number} after token refresh: {res.get('msg')} (code: {res.get('code')})")
                elif attempt == 2:
                    raise Exception(f"Failed to upload part {part_number}: {res.get('msg')} (code: {res.get('code')})")
                
                # 其他错误，等待后重试
                time.sleep(0.5 * (attempt + 1))

            offset += part_size

        # Step 3: 完成上传
        url = "https://open.feishu.cn/open-apis/drive/v1/files/upload_finish"
        json_data = {
            "upload_id": upload_id,
            "block_num": block_num
        }
        
        # 完成上传也可能遇到token过期，添加重试机制
        for attempt in range(2):
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json; charset=utf-8"
            }
            response = requests.post(url, headers=headers, json=json_data)
            res = response.json()
            
            if res.get("code") == 0:
                return res["data"]["file_token"]
            elif res.get("code") == 99991663 and attempt == 0:  # Invalid access token
                print("Token expired during upload finish, refreshing...")
                self.refresh_access_token()
                continue
            else:
                raise Exception(f"Failed to finish upload: {res.get('msg')} (code: {res.get('code')})")
        
        raise Exception("Failed to finish upload after token refresh")

    def upload_folder_auto(self, local_path, remote_token):
        """
        递归上传本地文件夹/本地大小文件到云端
        :param local_path: 需要上传的本地文件夹路径
        :param remote_token: 上传的远端文件夹token(文件夹路径可配合search_folder_recursive使用)

        :return 上传文件的token
        """
        # 如果 local_path 是一个文件，直接上传
        if os.path.isfile(local_path):
            file_size = os.path.getsize(local_path)
            file_name = os.path.basename(local_path)
            # 判断文件大小，选择合适的上传方式
            if file_size > 20 * 1024 * 1024:  # 文件大于20MB使用分片上传
                self._upload_large_file(remote_token, local_path, file_name)
            else:
                # 小文件直接上传
                self._upload_file(remote_token, local_path, file_name)
            return  # 处理完文件后直接返回，不再继续执行递归

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

    def download_sheet_pic(self, file_token: str, save_path: str):
        """
        下载素材：
            下载云文档中的图片和附件
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/medias/{file_token}/download"

        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        with open(save_path, 'wb') as file:
            file.write(response.content)

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

    def _download_file(self,
                       file_token: str,
                       save_dir: str,
                       save_name: str = None,
                       max_workers: int = 4,
                       min_chunk_size: int = 4 * 1024 * 1024,
                       overall_timeout: int = 0,
                       retries: int = 3,
                       backoff_factor: float = 0.5,
                       expected_sha256: str = None) -> str:
        """
        下载文件到本地（针对飞书 download endpoint：不使用 Range，单线程流式下载）
        返回最终保存的本地路径（字符串）。

        已优化点：
          - 去除 Range / 分片相关逻辑（飞书不支持 Range）
          - 较大 chunk_size（默认 256KiB）以减少系统调用/网络包开销
          - 重试与指数退避（遇到临时网络错误）
          - overall_timeout（总超时）与 per-request 超时
          - 下载进度打印（节流）
          - 完成后可校验 expected_sha256
        """
        # logger helper (优先使用 self.logger)
        _log = t_log.logger().classical_logger

        def _info(msg, *a, **k):
            if _log:
                _log.info(msg, *a, **k)
            else:
                print(msg % a if a else msg)

        def _debug(msg, *a, **k):
            if _log:
                _log.debug(msg, *a, **k)
            else:
                # 默认不打印 debug
                pass

        # --- prepare target dir/name ---
        save_dir = os.fspath(save_dir)
        if os.path.isdir(save_dir):
            final_dir = save_dir
        else:
            # caller might pass a file path
            parent = os.path.dirname(save_dir) or "."
            os.makedirs(parent, exist_ok=True)
            if save_name is None:
                save_name = os.path.basename(save_dir)
                final_dir = parent
            else:
                final_dir = parent

        os.makedirs(final_dir, exist_ok=True)

        # build URL and session
        url = f"https://open.feishu.cn/open-apis/drive/v1/files/{file_token}/download"
        headers = {"Authorization": f"Bearer {self.access_token}"}
        params = {"token": file_token}

        session = requests.Session()
        session.headers.update(headers)

        # deadline for overall timeout
        deadline = time.time() + overall_timeout if overall_timeout and overall_timeout > 0 else None

        # helper: per-request with retries
        def _request_with_retries(method, *args, **kwargs):
            last_exc = None
            for attempt in range(1, max(1, retries) + 1):
                if deadline and time.time() > deadline:
                    raise TimeoutError("Overall download timeout reached before request attempt")
                try:
                    # ensure reasonable per-request timeout (connect, read)
                    # caller can tweak if needed. use (10, 60) as default (connect 10s, read 60s)
                    kwargs.setdefault("timeout", (10, 60))
                    resp = session.request(method, *args, **kwargs)
                    return resp
                except Exception as e:
                    last_exc = e
                    sleep_for = backoff_factor * (2 ** (attempt - 1))
                    _debug("Request attempt %s failed: %s; backoff %.2fs", attempt, e, sleep_for)
                    # if deadline will be exceeded after sleep, break early
                    if deadline and time.time() + sleep_for > deadline:
                        break
                    time.sleep(sleep_for)
            # no success
            raise last_exc

        # try HEAD first to obtain headers (some servers may not fully support HEAD)
        try:
            head_resp = _request_with_retries("HEAD", url, params=params, allow_redirects=True)
        except Exception:
            # fallback to GET with stream=True to read headers without reading body here
            head_resp = None

        # If HEAD failed or returned non-200, do a light GET to fetch headers
        if head_resp is None or head_resp.status_code not in (200, 204, 206):
            try:
                tmp_head = _request_with_retries("GET", url, params=params, stream=True, allow_redirects=True)
                head_resp = tmp_head
            except Exception as e:
                raise RuntimeError(f"Failed to query remote headers: {e}")

        # determine filename from content-disposition if not provided
        if not save_name:
            disp = head_resp.headers.get("Content-Disposition", "") if head_resp is not None else ""
            import re as _re
            m = _re.search(r'filename\*?=(?:UTF-8\'\')?"?([^\";]+)"?', disp)
            if m:
                save_name = m.group(1).strip()
            else:
                # fallback to token-based name
                save_name = f"{file_token}.bin"

        final_path = Path(final_dir) / save_name
        tmp_path = final_path.with_suffix(final_path.suffix + ".part")

        # content length (may be None)
        cl = head_resp.headers.get("Content-Length") if head_resp is not None else None
        total_size = int(cl) if cl and str(cl).isdigit() else None

        _info("Starting download: %s -> %s (size=%s)", file_token, final_path, total_size)

        # chunk size: larger chunk to reduce overhead (256 KiB)
        chunk_size = 256 * 1024

        # progress state
        last_print = 0.0
        print_interval = 0.5  # seconds between progress prints

        def _sha256_of_file(path: Path) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    h.update(chunk)
            return h.hexdigest()

        # actual download attempts (retries outer loop for whole transfer)
        last_exception = None
        for attempt in range(1, max(1, retries) + 1):
            if deadline and time.time() > deadline:
                raise TimeoutError("Overall download timeout reached before starting attempt")
            try:
                resp = _request_with_retries("GET", url, params=params, stream=True, allow_redirects=True)
                if resp.status_code != 200:
                    # try extract JSON error message
                    try:
                        j = resp.json()
                        raise RuntimeError(f"Download failed: {j.get('msg') or resp.status_code}")
                    except Exception:
                        raise RuntimeError(f"Download failed: HTTP {resp.status_code}")

                # write stream to tmp file
                downloaded = 0
                start_time = time.time()
                with tmp_path.open("wb") as f:
                    for chunk in resp.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            try:
                                if callable(getattr(self, "progress_callback", None)):
                                    self.progress_callback("download", downloaded, total_size or 0)
                            except Exception:
                                pass
                        # progress print (throttle to print_interval)
                        now = time.time()
                        if now - last_print >= print_interval:
                            last_print = now
                            if total_size:
                                pct = downloaded * 100.0 / total_size
                                _info("Downloading %s: %.2f%% (%d / %d bytes)", save_name, pct, downloaded, total_size)
                            else:
                                _info("Downloading %s: %d bytes", save_name, downloaded)

                        # check overall deadline
                        if deadline and time.time() > deadline:
                            raise TimeoutError("Download overall timeout reached during transfer")

                # verify basic size if content-length known
                if total_size is not None and tmp_path.stat().st_size != total_size:
                    raise RuntimeError(f"Downloaded size mismatch: {tmp_path.stat().st_size} != {total_size}")

                # optional sha256 check
                if expected_sha256:
                    got_sha = _sha256_of_file(tmp_path)
                    if got_sha.lower() != expected_sha256.lower():
                        # remove corrupt tmp
                        try:
                            tmp_path.unlink()
                        except Exception:
                            pass
                        raise RuntimeError(f"SHA256 mismatch: expected {expected_sha256}, got {got_sha}")

                # atomic replace
                tmp_path.replace(final_path)
                try:
                    if callable(getattr(self, "progress_callback", None)):
                        final_total = total_size if total_size is not None else final_path.stat().st_size
                        self.progress_callback("complete", final_total, final_total)
                except Exception:
                    pass
                # final progress print
                if total_size:
                    _info("Download complete: %s (%d bytes)", final_path, total_size)
                else:
                    _info("Download complete: %s (%d bytes)", final_path, final_path.stat().st_size)
                return str(final_path)

            except Exception as e:
                last_exception = e
                _debug("Attempt %s failed: %s", attempt, e)
                # cleanup tmp file if exists
                try:
                    if tmp_path.exists():
                        tmp_path.unlink()
                except Exception:
                    pass
                # backoff
                sleep_for = backoff_factor * (2 ** (attempt - 1))
                if deadline and time.time() + sleep_for > deadline:
                    # no point in sleeping if deadline will be exceeded
                    break
                time.sleep(sleep_for)
                continue

        # all attempts failed
        raise RuntimeError(f"Download failed after {retries} attempts: {last_exception}")

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

    def get_file_info(self, token_file: str, doc_type: str):
        """
        云盘的单个文件信息获取（其实可以多个文件获取，自行拓展）
        return:
        "data": {
        "metas": [
            {
                "doc_token": "doccnfYZzTlvXqZIGTdAHKabcef",
                "doc_type": "doc",
                "title": "sampletitle",
                "owner_id": "ou_b13d41c02edc52ce66aaae67bf1abcef",
                "create_time": "1652066345",
                "latest_modify_user": "ou_b13d41c02edc52ce66aaae67bf1abcef",
                "latest_modify_time": "1652066345",
                "url": "https://sample.feishu.cn/docs/doccnfYZzTlvXqZIGTdAHKabcef",
                "sec_label_name": "L2-内部"
            }
        ],
        "failed_list": [
            {
                "token": "boxcnrHpsg1QDqXAAAyachabcef",
                "code": 970005
            }
        ]
        """
        url = f"https://open.feishu.cn/open-apis/drive/v1/metas/batch_query"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        body = {"request_docs":[{
            "doc_token": token_file,
            "doc_type": doc_type}]
        }
        response = requests.request("POST", url, headers=headers, json=body)
        res = json.loads(response.text)
        if res.get("code", 200) == 0 and res.get("msg", "").lower() == "success":
            return res["data"]
        else:
            raise Exception(f"failed to send message: {res.get('message')}")

    def _send_message(self, msg_type:str, msg:str, id_type:str, contact_id:str):
        """
        参数类型和定义参考 https://open.feishu.cn/document/server-docs/im-v1/message/create?appId=cli_a88b4d15dc70100b
        机器人给指定联系人(前提是已经有权限了)发消息
        """
        assert (id_type in ('open_id', 'union_id', 'user_id', 'email', 'chat_id') and
                msg_type in ('text', 'post', 'image', 'file', 'audio', 'media', 'sticker',
                             'interactive', 'share_chat', 'share_user', 'system'))

        url = "https://open.feishu.cn/open-apis/im/v1/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }

        params = {"receive_id_type": id_type}
        msgContent = {
            "text": msg,
        }
        req = {
            "receive_id": contact_id,
            "msg_type": msg_type,
            "content": json.dumps(msgContent)
        }
        payload = json.dumps(req)

        response = requests.request("POST", url, params=params, headers=headers, data=payload)
        res = json.loads(response.text)
        if res.get("code", 200) == 0 and res.get("msg", "") == "success":
            return True
        else:
            raise Exception(f"failed to send message: {res.get('message')}")

    def send_text_to_group(self, group_name, text):
        """
        向机器人已经有权限的群组发送消息
        """
        chat_id = self.get_chat_id_of_the_group(group_name)
        self._send_message('text', text, 'chat_id', chat_id)

    def send_text_to_user(self, email:str, text):
        """
        给固定邮箱的用户发送信息
        """
        assert email.endswith('@transsion.com'), "email 必须以 @transsion.com 结尾"
        self._send_message('text', text, 'email', email)

    def get_chat_id_of_the_group(self, group_name):
        """
        根据关键词搜索当前机器人可见的群，且返回该群的chat_id。 该接口也可以搜索用户的，后期可拓展。
        """
        url = "https://open.feishu.cn/open-apis/im/v1/chats/search"
        headers = {
            "Authorization": f"Bearer {self.access_token}"
        }
        params = {
            'query': group_name,
            'page_size': 20
        }
        response = requests.request("GET", url, headers=headers, params=params)
        res = json.loads(response.text)
        if res.get("code", 0) == 0:
            items = res.get("data", {}).get("items", [])
            if items:
                # 如果搜索到多个群，自动取第一个
                return items[0].get("chat_id")
            else:
                raise Exception(f"No group found with name: {group_name}")
        else:
            raise Exception(f"Failed to search group: {res.get('msg', res.get('message', 'Unknown error'))}")

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
        # f = _feishu.search_folder('XyGKfLvEGlkM7sdmyLacIHjsn9e', "apk_res")
        # print(_feishu.send_text_to_group('FAST自动化error告警', '测试'))
        print(_feishu.get_file_info("FBonb8HLNocaeexAGpic6s3UnnJ", "file"))
    except Exception as e:
        print(str(e))
