import os
import threading
import time
import pandas as pd
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from powertrde.framework.table.feishu_static_table_loader import FeishuStaticTableLoader
from powertrde.framework.logs_protocol import logs_p

class TableTask:
    def __init__(self, debug: bool = False):
        if debug:   # 测试环境
            token_table = 'HuHesx88vhMwwYtCdRYcJDtjnUh'         # https://transsioner.feishu.cn/sheets/HuHesx88vhMwwYtCdRYcJDtjnUh
            self.token_bitable = 'GQfdbXIsAaswYtsxCC0cxyFYnBd'  # https://transsioner.feishu.cn/base/GQfdbXIsAaswYtsxCC0cxyFYnBd
        else:       # 正式环境
            token_table = 'HQl0sE40dhBFvctZCP9cv5uHnYc'         # https://transsioner.feishu.cn/sheets/HQl0sE40dhBFvctZCP9cv5uHnYc
            self.token_bitable = 'UH7tbDb1Gaj8MhscygWcCv1QnRh'  # https://transsioner.feishu.cn/base/UH7tbDb1Gaj8MhscygWcCv1QnRh
        self.token_logs = 'PXaaf4AhQlf7nUds39qcyivznBb'         # https://transsioner.feishu.cn/drive/folder/PXaaf4AhQlf7nUds39qcyivznBb
        powercloud_app_id = 'cli_a81049d61c2c900e'
        powercloud_app_secret = 'foH623pzGZeYOaVJB8POedMDQxQP0qb4'
        self.feishu_ins = FeishuApiHelper(powercloud_app_id, powercloud_app_secret)
        self.feishu_ins.register_table_group_token('powercloudcfg', token_table)
        self.table_loader = FeishuStaticTableLoader(self.feishu_ins)
        self.bitable_database_id = self.feishu_ins.get_bitable_token_by_name(self.token_bitable, 'database')
        self.bitable_reference_id = self.feishu_ins.get_bitable_token_by_name(self.token_bitable, 'reference')
        self.uploadlist: list = []
        self._lock = threading.Lock()
        self.plan: dict = None
        self.plan_uptime = 0
        self.base: dict = None
        self.base_uptime = 0
        self.standby: dict = None
        self.standby_uptime = 0

    def add_upload_powercloud(self, model: str, filename: str):
        with self._lock:
            self.uploadlist.append((model, filename))
    
    def upload_powercloud(self):
        with self._lock:
            for model, filename in list(self.uploadlist):
                file_token = self._upload_file(f"{filename}.zip", model)
                if file_token is None:
                    logs_p().log_error(f"{filename}.zip 日志上传失败, 稍后重试")
                    return
                try:
                    df = pd.read_excel(f"{filename}.xlsx", engine="openpyxl")
                    data_list = df.to_dict(orient='records')
                    data_list = [{k: v for k, v in item.items() if pd.notna(v)} for item in data_list]
                    for item in data_list:
                        item['log'] = f"https://transsioner.feishu.cn/file/{file_token}"
                    if not self._save_bitable_datalist(data_list):
                        raise Exception("数据上传失败")
                except (Exception) as e:
                    self.feishu_ins.delete_file_or_folder(file_token,"file")
                    logs_p().log_error(f"{filename}.xlsx 数据上传失败, 稍后重试: {str(e)}")
                    continue
                try:
                    os.remove(f"{filename}.xlsx")
                    os.remove(f"{filename}.zip")
                except (Exception) as e:
                    logs_p().log_error(f"删除文件失败, 错误: {str(e)}")
                logs_p().log_debug(f"{filename} 数据上传成功")
                self.uploadlist.remove((model, filename))

    def _save_bitable_datalist(self, data_list: list):
        for item in data_list:
            for k, v in item.items():
                if v is False:
                    item[k] = 'False'
                elif v is True:
                    item[k] = 'True'
        try:
            if not self.bitable_database_id:
                self.bitable_database_id = self.feishu_ins.get_bitable_token_by_name(self.token_bitable, 'database')
        except Exception as e:
            logs_p().log_error(f"[database]Get token failed: {e}")
            return False
        
        if not self.bitable_database_id:
            logs_p().log_error(f"[database]: database id is empty")
            return False
        try:
            self.feishu_ins.write_bitable_datalist(self.token_bitable, self.bitable_database_id, data_list)
            time.sleep(2)
        except Exception as e:
            logs_p().log_error(f"[database]Save failed: {e}")
            logs_p().log_error(f"[database]data: {data_list}")
            return False
        return True
    
    def _upload_file(self, file_path: str, savefolder: str):
        try:
            folder_token = self.feishu_ins.get_or_creat_folder_token(savefolder, self.token_logs)
            file_token = self.feishu_ins.upload_file_auto(file_path, folder_token)
            time.sleep(2)
        except Exception as e:
            logs_p().log_error(f"[database]Upload file failed: {e}")
            logs_p().log_error(f"[database]file: {file_path}")
            return None
        return file_token
    
    def get_power_reference(self, model: str) -> dict:
        power_reference = self.feishu_ins.getref_bitable_records(self.token_bitable, self.bitable_reference_id, model)
        output_data = {}
        for item in power_reference:
            fields = item.get('fields', {})
            # 提取 task_id 列表中的 text 作为键 (例如 'T01')
            task_ids = fields.get('task_id', [])
            if task_ids:
                key_name = task_ids[0].get('text')
                value_data = {}
                if 'current' in fields:
                    value_data['current'] = fields['current']
                if 'filtermin' in fields:
                    value_data['filtermin'] = fields['filtermin']
                output_data[key_name] = value_data
        #print(output_data)
        return output_data

    def get_test_plan(self, model: str, pmsn: int):
        import time
        try:
            with self._lock:
                t_h = int(time.time())
                if (self.plan_uptime < t_h - 3600):
                    self.plan_uptime = t_h
                    self.plan = self.table_loader.load_table('powercloudcfg/test_plan')
                    #logs_p().log("[powercloudcfg/test_plan]Sync success")
        except Exception as e:
            logs_p().log_error(f"[powercloudcfg/test_plan]Scan failed: {e}")
        
        if not self.plan:
            return None
        modelisvalid = False
        for plan_id, plan in self.plan.items():
            if plan['model'].upper() != model.upper():
                continue
            if plan['tpm_sn'] != 0 and plan['tpm_sn'] != int(pmsn):
                continue
            modelisvalid = True
        if not modelisvalid:
            #logs_p().log_warning(f"[powercloudcfg/test_plan]No plan found for model {model}, use default plan")
            model = 'default'
        
        modelplan:dict = {}
        for plan_id, plan in self.plan.items():
            if plan['model'].upper() != model.upper():
                continue
            if plan['tpm_sn'] != 0 and plan['tpm_sn'] != int(pmsn):
                continue
            if 'base' in plan['task']:
                modelplan['base'] = plan
            elif 'wifi' in plan['task']:
                modelplan['wifi'] = plan
            elif 'data' in plan['task']:
                modelplan['data'] = plan
            elif 'update' in plan['task']:
                modelplan['update'] = plan

        return modelplan
    
    def get_tasks_base(self):
        import time
        try:
            with self._lock:
                t_h = int(time.time())
                if (self.base_uptime < t_h - 3600):
                    self.base_uptime = t_h
                    self.base = self.table_loader.load_table('powercloudcfg/task_base')
                    #logs_p().log("[powercloudcfg/task_base]Sync success")
            return self.base
        except Exception as e:
            logs_p().log_error(f"[powercloudcfg/task_base]Scan failed: {e}")
            return self.base

    def get_standby_tasks(self):
        import time
        try:
            with self._lock:
                t_h = int(time.time())
                if (self.standby_uptime < t_h - 3600):
                    self.standby_uptime = t_h
                    self.standby = self.table_loader.load_table('powercloudcfg/task_standby')
                    #logs_p().log("[powercloudcfg/task_standby]Sync success")
            return self.standby
        except Exception as e:
            logs_p().log_error(f"[powercloudcfg/task_standby]Scan failed: {e}")
            return self.standby