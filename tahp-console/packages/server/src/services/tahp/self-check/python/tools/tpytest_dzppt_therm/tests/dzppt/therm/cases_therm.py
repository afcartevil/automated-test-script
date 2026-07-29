import shutil
import chardet
from tests.dzppt.cases_dzppt import CasesDzPpt
from tests.dzppt.therm.therm_config import ThermConfig
from tests.dzppt.therm.therm_env import ThermEnv
from powertrde.env import GET_RES_SCHEME_DIR
import base64
import os
import subprocess
import time
from typing import cast

from powertrde.utils import misc_utils
from powertrde.utils.trde import adb


class CasesTherm(CasesDzPpt):
    def __init__(self):
        super().__init__()
        ...

    @property
    def scheme_env(self) -> ThermEnv:
        return self.get_scheme_env()

    @property
    def user_config(self) -> ThermConfig:
        return self.get_scheme_env().user_config

    @classmethod
    def get_scheme_env(cls) -> ThermEnv:
        return cast(ThermEnv, super().get_scheme_env())

    @property
    def runtime_dir(self):
        return os.path.dirname(self.meta_report_dir)

    @property
    def target_encode_file(self):
        return os.path.join(self.runtime_dir, 'power_app_cfg.xml')

    @property
    def target_decode_file(self):
        return os.path.join(self.runtime_dir, 'power_app_cfg_decoded.xml')

    def log_result(self, result):
        self.logger.info(f"- result：【{result}】", ext_event=True)

    @staticmethod
    def encode(infile, outfile):
        fd = open(infile)
        try:
            buf = fd.read()
        finally:
            fd.close()

        b = bytearray(base64.b64encode(buf.encode('utf-8')))
        for i in range(len(b)):
            b[i] += 33

        open(outfile, 'wb').write(b)

    @staticmethod
    def decode(infile, outfile):
        b = bytearray(open(infile, 'rb').read())
        for i in range(len(b)):
            b[i] -= 33

        d = bytes.decode(base64.b64decode(b))
        open(outfile, 'w', encoding='utf-8').write(d)

    @staticmethod
    def click_screen_by_percentage(sn, x_percent, y_percent):
        """
        在安卓设备上按照屏幕百分比坐标点击屏幕。
        :param sn: 设备的序列号
        :param x_percent: 点击位置的X轴百分比（0到100之间的浮点数）
        :param y_percent: 点击位置的Y轴百分比（0到100之间的浮点数）
        """
        # 获取设备屏幕分辨率
        size_command = f"adb -s {sn} shell wm size"
        output = subprocess.check_output(size_command.split()).decode('utf-8')
        # 输出示例：Physical size: 1080x1920
        resolution = output.strip().split(": ")[-1].split("x")
        width, height = int(resolution[0]), int(resolution[1])

        # 计算点击位置的实际坐标
        x = int(width * (x_percent / 100.0))
        y = int(height * (y_percent / 100.0))

        # 执行点击操作
        tap_command = f"adb -s {sn} shell input tap {x} {y}"
        subprocess.run(tap_command.split())

    @staticmethod
    def swipe_left_or_right(sn, is_left: bool):
        """
        在安卓设备上执行从左向右的滑动操作。

        :param sn: 设备的序列号
        :param is_left: 是否向左划
        """
        # 获取设备屏幕分辨率
        size_command = f"adb -s {sn} shell wm size"
        output = subprocess.check_output(size_command.split()).decode('utf-8')
        # 输出示例：Physical size: 1080x1920
        resolution = output.strip().split(": ")[-1].split("x")
        width, height = int(resolution[0]), int(resolution[1])

        # 计算滑动起始和结束位置
        if is_left:
            start_x = int(width * 0.8)  # 从屏幕宽度的10%开始
            end_x = int(width * 0.2)  # 滑动到屏幕宽度的90%
        else:
            start_x = int(width * 0.2)  # 从屏幕宽度的10%开始
            end_x = int(width * 0.8)  # 滑动到屏幕宽度的90%
        y = int(height * 0.5)  # 在屏幕高度的中间滑动

        # 执行滑动操作
        swipe_command = f"adb -s {sn} shell input swipe {start_x} {y} {end_x} {y}"
        subprocess.run(swipe_command.split())

    def find_mtk_feature(self, policy="", feature_tag=""):
        """
        查找MTK特性标签在指定policy文件中的内容。

        参数:
            policy (str): 要查找的policy标识。如果为空字符串，则使用默认 thermal.conf 文件。
            feature_tag (str): 要查找的特性标签（如 "[mtk-skin-control]"）。

        返回:
            str: 如果找到特性标签，返回其对应的内容；否则返回空字符串。
                 若文件未找到或发生异常，返回对应的错误信息。
        """
        # 获取policy文件路径
        policy_file = 'thermal.conf' if policy == "" else f'thermal_policy_{policy}.conf'
        policy_dir = os.path.join(self.runtime_dir, 'thermal', 'plain', policy_file)

        if not os.path.exists(policy_dir):
            self.policy_encrypt()

        try:
            with open(policy_dir, 'r', encoding='utf-8') as file:
                content = file.read()
            if policy == "":
                return content

            lines = content.splitlines()
            result = []
            inside_block = False

            for line in lines:
                line = line.strip()
                if line == feature_tag:
                    inside_block = True
                    result.append(line)
                elif inside_block:
                    if line.startswith("[") and line.endswith("]"):
                        break
                    result.append(line)
            return result if result else ""

        except Exception as e:
            self.logger.info(f"{e}", ext_event=True)
            return ''

    def find_mtk_skin_control(self, policy):
        """动态调频"""
        return self.find_mtk_feature(policy, "[mtk-skin-control]")

    def find_mtk_cpu_table_mapping(self, policy):
        """阶梯调频"""
        return self.find_mtk_feature(policy, "[mtk-cpu-table-mapping]")

    def find_mtk_cpu_isolate(self, policy):
        """核心隔离"""
        return self.find_mtk_feature(policy, "[mtk-cpu-isolate]")

    def powerhal_encrypt(self):
        """解密power_app_cfg.xml至power_app_cfg_decoded.xml"""
        for file in [self.target_encode_file, self.target_decode_file]:
            if os.path.exists(file):
                os.remove(file)

        adb.pull_file(self.device_id, "vendor/etc/power_app_cfg.xml", self.target_encode_file)
        self.decode(self.target_encode_file, self.target_decode_file)  # 解密power_app_cfg.xml

    def _get_tool_cryptography_exe(self):
        exe_tool = os.path.join(GET_RES_SCHEME_DIR(), 'toolCryptography.exe')
        if not os.path.isfile(exe_tool):
            raise Exception(
                f'解密工具不存在: {exe_tool}，请确认已复制 assets/dzppt/therm/toolCryptography.exe')
        return exe_tool

    def _ensure_plain_thermal_dir(self):
        if os.path.isdir('plain'):
            return

        exe_tool = self._get_tool_cryptography_exe()
        process = subprocess.Popen(
            exe_tool,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        tool_output = ''
        try:
            stdout, stderr = process.communicate(input=b'2\n', timeout=30)
            tool_output = ((stdout or b'') + (stderr or b'')).decode('utf-8', errors='replace').strip()
        except subprocess.TimeoutExpired:
            process.kill()
            stdout, stderr = process.communicate()
            tool_output = ((stdout or b'') + (stderr or b'')).decode('utf-8', errors='replace').strip()
            raise Exception(f'toolCryptography 运行超时: {exe_tool}')

        if os.path.isdir('plain'):
            return

        conf_files = [name for name in os.listdir('.') if name.endswith('.conf') and os.path.isfile(name)]
        if conf_files:
            os.makedirs('plain', exist_ok=True)
            for name in conf_files:
                shutil.copy2(name, os.path.join('plain', name))
            return

        raise Exception(
            '工具没有生成 plain 解密文件夹！'
            f' toolCryptography={exe_tool}, exit={process.returncode}, detail={tool_output or "无输出"}'
        )

    def policy_encrypt(self):
        """policy策略解密方法"""
        thermal_dir = os.path.join(self.runtime_dir, 'thermal')
        if os.path.exists(thermal_dir):
            shutil.rmtree(thermal_dir)
        os.makedirs(thermal_dir, exist_ok=True)
        for thermal_path in ["vendor/etc/thermal", "/odm/etc/thermal"]:
            adb.pull_file(self.device_id, thermal_path, self.runtime_dir)

        if not os.listdir(thermal_dir):
            raise Exception(f'未能从手机拉取 thermal 配置，请检查 vendor/etc/thermal 或 /odm/etc/thermal 是否存在')

        with misc_utils.temp_working_directory(thermal_dir):
            self._ensure_plain_thermal_dir()

    def find_sqrt_feature(self, policy="", feature_tag=""):
        """
        查找sqrt特性标签在指定therm.conf文件中的内容。
        """
        # TODO：无法解密
        if not os.path.exists(os.path.join(self.runtime_dir, 'thermal.conf')):
            adb.pull_file(self.device_id, "/odm/etc/thermal.conf", self.runtime_dir)

        with misc_utils.temp_working_directory(self.runtime_dir):
            self._ensure_plain_thermal_dir()

        file_path = os.path.join(self.runtime_dir, 'plain', 'thermal.conf')
        with open(file_path, 'rb') as file:
            raw_data = file.read()
            result = chardet.detect(raw_data)
            encoding = result['encoding']

        # 使用检测到的编码读取文件
        with open(file_path, 'r', encoding=encoding, errors='replace') as file:
            content = file.read()
        print(content)
        return str(content)
