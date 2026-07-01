import subprocess
from abc import ABC
from typing import Optional

from data_collector.data_collect_node import DataCollectNode
from powertrde.framework.tran_logger import t_log
from powertrde.utils.trde.trde_utils import ADB_EXE


class AndroidCollectNode(DataCollectNode, ABC):
    """
    Android 平台数据采集节点：
      - 继承自 DataCollectNode
      - 支持以完整字符串形式执行 adb shell 或 adb 命令
      - 可指定 device_id 与 adb_path
    """

    def __init__(
        self,
        name: str,
        params: dict,
        device_id: Optional[str] = None,
        adb_path: str = ADB_EXE
    ):
        super().__init__(name, params)
        self.device_id = device_id
        self.adb_path = adb_path

    def _build_base_cmd(self) -> str:
        cmd = f'"{self.adb_path}"'
        if self.device_id:
            cmd += f" -s {self.device_id}"
        return cmd

    def run_shell(
        self,
        shell_cmd: str,
        capture: bool = True,
        check: bool = True
    ) -> str:
        """
        执行一条完整的 adb shell 命令字符串，
        例如 shell_cmd="dumpsys battery --history"
        """
        full = f"{self._build_base_cmd()} shell {shell_cmd}"
        proc = subprocess.run(
            full,
            shell=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
            encoding='utf-8',
            check=check
        )
        if proc.stderr:
            t_log.warning(f'AndroidCollectNode run_shell has error message: {proc.stderr}')
        return proc.stdout or ""

    def run_cmd(
        self,
        cmd_suffix: str,
        capture: bool = True,
        check: bool = True
    ) -> str:
        """
        执行一条完整的 adb 命令字符串，
        例如 cmd_suffix="logcat -d"
        """
        full = f"{self._build_base_cmd()} {cmd_suffix}"
        proc = subprocess.run(
            full,
            shell=True,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE if capture else None,
            text=True,
            encoding='utf-8',
            check=check
        )
        if proc.stderr:
            t_log.warning(f'AndroidCollectNode run_cmd has error message: {proc.stderr}')
        return proc.stdout or ""

    def run_pull(
        self,
        remote: str,
        local: str,
        check: bool = True
    ) -> None:
        """
        执行 adb pull remote local
        """
        full = f"{self._build_base_cmd()} pull {remote} {local}"
        subprocess.run(full, shell=True, check=check)
