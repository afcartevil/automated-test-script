import json
import os
import os.path
import shutil
import zipfile
import subprocess
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path

from powertrde.framework.tran_logger import t_log
from powertrde.utils import yaml_utils, json_utils
from powertrde.utils.feishu.feishu_api_helper import FeishuApiHelper
from tpytest.resource_provider import FeishuProvider
from powertrde.env import PROJ_DIR


@dataclass
class VersionMeta:
    version: str
    update_level: int
    is_patch: bool
    upgrade_path: list[str]
    total_update_level_weight: int
    manifest: dict
    patch_list: dict[str, list[str]]
    publish_date: str
    support_mode_idx: int = 0  # 0=国内标准, 1=海外标准, 2=双模式


class FeiShuUpdater:
    ...

    """
    download_file_auto 下载文件夹或者文件
    """

    def __init__(self, team=None, name=None, on_progress=None):
        self.team = team
        self.name = name
        self.on_progress = on_progress
        self._remote_manifest_data = None
        self._local_manifest_data = None
        self._local_version = None
        self._remote_version = None
        self.remote_version_url = ""
        self.enabled = False
        self.is_overseas = False

        # 加载配置
        self._load_config()

        if self.enabled:
            self._root_dir = 'tpytest_publish'
            self._feishu_api_helper = FeishuApiHelper('cli_a88b4d15dc70100b', 'nTOW0ZolI9RssVN8gact5eVcLVtljJC2')
            self._feishu_api_helper.register_root_folder_token(self._root_dir, 'PxRzfCm43li8ttdFTxec2Pznnxc')
            self._progress_stage = None
            try:
                self._feishu_api_helper.progress_callback = self._on_api_progress
            except Exception:
                pass
            self._feishu_provider = FeishuProvider(self._feishu_api_helper, self._root_dir)
            self.version_file = self._get_version_file_path()
            self._remote_meta = None
        else:
            self.version_file = None
            self._feishu_provider = None
    
    def _load_config(self):
        """从配置文件加载飞书更新相关配置"""
        try:
            from powertrde.env import CONFIG_DIR
            from powertrde import env
            config_file = os.path.join(CONFIG_DIR, self.team, self.name, 'base_config.yaml')
            
            if not os.path.exists(config_file):
                t_log.info(f"未找到配置文件，飞书更新已禁用: {config_file}")
                self.enabled = False
                return
            
            from powertrde.utils import yaml_utils
            config = yaml_utils.read_yaml(config_file, ignore_yaml_error=False)
            
            if not config or 'feishu_updater' not in config:
                t_log.info("配置文件中缺少 feishu_updater 配置，飞书更新已禁用")
                self.enabled = False
                return
            
            feishu_config = config['feishu_updater']
            config_enabled = feishu_config.get('enabled', False)
            
            # 检查 PUBLISH_MODE，飞书更新仅在 odm 或 overseas 模式下可用
            publish_mode = getattr(env, 'PUBLISH_MODE', '')
            
            if config_enabled and publish_mode not in ('odm', 'overseas'):
                t_log.info(f"飞书更新配置已启用，但 PUBLISH_MODE='{publish_mode}' 不是 odm/overseas，飞书更新已禁用")
                self.enabled = False
                self.is_overseas = False
                return
            
            self.enabled = config_enabled
            self.is_overseas = (publish_mode == 'overseas')
            
            if self.enabled:
                t_log.info(f"飞书更新已启用 (PUBLISH_MODE={publish_mode}, is_overseas={self.is_overseas})")
            else:
                t_log.info("飞书更新已禁用")
                
        except Exception as e:
            t_log.warning(f"加载飞书更新配置失败: {e}")
            self.enabled = False

    def _on_api_progress(self, event: str, current: int, total: int):
        try:
            if callable(getattr(self, "on_progress", None)):
                if self._progress_stage == "meta":
                    if event == "download":
                        self.on_progress("meta", current, total or 0)
                    elif event == "complete":
                        self.on_progress("meta_downloaded", current, total or 0)
                    return
                if self._progress_stage == "zip_local":
                    self.on_progress("download", current, total or 0)
                    return
                if self._progress_stage == "zip_overseas":
                    self.on_progress("download_overseas", current, total or 0)
                    return
                if event == "download":
                    self.on_progress("download", current, total or 0)
                elif event == "complete":
                    self.on_progress("complete", current, total or 0)
        except Exception:
            pass

    # 获取本地版本文件路径
    def _get_version_file_path(self) -> str:

        self.file_path = f"{self.name}_version.yaml"
        return os.path.join(PROJ_DIR, self.file_path)

    # 获取本地版本号
    def get_local_version(self) -> str:
        """
        优先从 YAML 读取 version 字段；若不存在则兼容旧的 TXT 文件。
        """
        if not self.version_file:
            return "0.0.0"
        try:
            if os.path.exists(self.version_file):
                data = yaml_utils.read_yaml(self.version_file, ignore_yaml_error=False)
                if isinstance(data, dict) and "version" in data:
                    print(str(data["version"]).strip())
                    return str(data["version"]).strip()
        except Exception as e:
            t_log.warning(f"读取 YAML 版本文件失败: {e}")
        return "0.0.0"

    # 获取远端版本信息
    def get_remote_meta(self) -> str:
        """获取并解析远端 YAML 版本元信息，回退兼容纯文本"""

        try:
            remote_file_path = self._feishu_provider.download(
                f"{self.name}/a_{self.name}.meta",
                os.path.join(PROJ_DIR, f'a_{self.name}.meta'), overwrite=True)
            remote_meta = yaml_utils.read_yaml(remote_file_path, ignore_yaml_error=False)
            version_value = remote_meta.get("latest")
            print(f"远端版本: {version_value}")
            return version_value
        except Exception as e:
            raise RuntimeError(f"无法获取远程版本元信息: {e}")

    def has_update(self):
        """判断是否有新版本"""
        return self.get_local_version() != self.get_remote_meta()


    def get_remote_Specify_version(self, version: str | None = None) -> dict:
        target_version = version or self.get_remote_meta()
        version_underscore = target_version.replace(".", "_")
        remote_meta_filename = f"{self.name}/tpytest_{self.team}_{self.name}_{version_underscore}.meta"
        local_meta_filename = f"tpytest_{self.team}_{self.name}_{version_underscore}.meta"
        local_meta_path = os.path.join(PROJ_DIR, local_meta_filename)

        success = self._feishu_provider.download(
            remote_path=remote_meta_filename,
            local_path=local_meta_path,
            overwrite=True
        )
        if not success or not os.path.exists(local_meta_path):
            raise RuntimeError(f"Failed to download remote meta: {remote_meta_filename}")

        with open(local_meta_path, "r", encoding="utf-8") as f:
            remote_meta = json.load(f)

        if version is None:
            VersionMeta.version = remote_meta.get("version")
            VersionMeta.update_level = remote_meta.get("update_level", 0)
            VersionMeta.is_patch = remote_meta.get("is_patch", False)
            VersionMeta.total_update_level_weight = remote_meta.get("total_update_level_weight", 0)
            VersionMeta.publish_date = remote_meta.get("publish_date")
            VersionMeta.manifest = remote_meta.get("manifest", {})
            VersionMeta.patch_list = remote_meta.get("patch_list", {})
            VersionMeta.support_mode_idx = remote_meta.get("support_mode_idx", 0)
        return remote_meta


    def backup_project(self, backup_dir: str = None):
        """备份项目根目录到 .backup_version 下（跳过以 . 开头的目录和若干临时/无关目录）"""
        local_version = self.get_local_version()
        backup_dir = backup_dir or os.path.join(PROJ_DIR, ".backup_version")
        os.makedirs(backup_dir, exist_ok=True)
        back_file_prefix = str(self.file_path).split(".")[0]
        zip_path = os.path.join(backup_dir, f"{back_file_prefix}_{local_version}.zip")
        skip_dirs = {".backup_version", "_tmp_extract", ".git", "__pycache__", ".runtime", ".idea"}

        t_log.info(f"开始备份到: {zip_path}")
        with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
            for folder, subdirs, files in os.walk(PROJ_DIR):
                if ".runtime" in folder.split(os.sep):
                    subdirs[:] = []
                    continue
                rel_root = os.path.relpath(folder, PROJ_DIR)
                parts = [] if rel_root in (".", "") else rel_root.split(os.sep)
                # 跳过以 . 开头的目录或在排除列表中的目录
                if any(p.startswith(".") or p in skip_dirs for p in parts):
                    subdirs[:] = []  # 不再深入
                    continue
                # 精确跳过当前层级的排除目录
                subdirs[:] = [d for d in subdirs if not (d.startswith(".") or d in skip_dirs)]
                for fname in files:
                    abs_path = os.path.join(folder, fname)
                    rel_path = os.path.relpath(abs_path, PROJ_DIR)
                    top = rel_path.split(os.sep)[0]
                    if top in skip_dirs or top.startswith("."):
                        continue
                    zf.write(abs_path, arcname=rel_path)
        t_log.info(f"备份完成: {zip_path}")

    def download_new_version_zip(self,is_overseas:bool = False):
        """
        仅下载最新版本的 .zip 包到 PROJ_DIR，不执行解压或更新。
        返回下载后的本地 zip 文件完整路径。
        """
        if not self.has_update():
            raise RuntimeError("当前已是最新版本，无需下载。")

        latest_version = self.get_remote_meta()
        zip_name = f"tpytest_{self.team}_{self.name}_{latest_version.replace('.', '_')}.zip"
        remote_zip_path = f"{self.name}/{zip_name}"  # 在飞书 dou3/ 目录下
        local_zip_path = os.path.join(PROJ_DIR, zip_name)

        # 3. 使用带重试的下载（你已有 FeishuManager 支持）
        self._progress_stage = "zip_local"
        success = self._feishu_provider.download(
            remote_path=remote_zip_path,
            local_path=local_zip_path
        )
        self._progress_stage = None
        overseas_local_zip_path = None



        if not success or not os.path.exists(local_zip_path):
            raise RuntimeError(f"下载失败或文件不存在: {local_zip_path}")

        if is_overseas:
            zip_name = f"tpytest_{self.team}_{self.name}_{latest_version.replace('.', '_')}_overseas.zip"
            remote_zip_path = f"{self.name}/{zip_name}"  # 在飞书 dou3/ 目录下
            overseas_local_zip_path = os.path.join(PROJ_DIR, zip_name)
            self._progress_stage = "zip_overseas"
            success = self._feishu_provider.download(
                remote_path=remote_zip_path,
                local_path=overseas_local_zip_path
            )
            self._progress_stage = None
            if not success or not os.path.exists(overseas_local_zip_path):
                raise RuntimeError(f"下载失败或文件不存在: {overseas_local_zip_path}")  
                  
        t_log.info(f"✅ 新版本 zip 已下载: {local_zip_path}")
        return local_zip_path,overseas_local_zip_path


    def _extract_zip_to_project_root(self, zip_path: str):
        """将 zip 解压到临时目录后，覆盖拷贝到项目根目录，最后清理临时目录"""
        tmp_dir = os.path.join(PROJ_DIR, "_tmp_extract")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        os.makedirs(tmp_dir, exist_ok=True)

        t_log.info(f"开始解压: {zip_path} -> {tmp_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)
        try:
            os.remove(zip_path)
        except Exception:
            pass

        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            src_root = os.path.join(tmp_dir, entries[0])
        else:
            src_root = tmp_dir

        for item in os.listdir(src_root):
            if item == ".backup_version":
                continue
            src = os.path.join(src_root, item)
            dst = os.path.join(PROJ_DIR, item)
            if os.path.isdir(src):
                if os.path.exists(dst):
                    shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        shutil.rmtree(tmp_dir, ignore_errors=True)
        t_log.info("远程代码解压并覆盖完成")

    def _prepare_extract_root(self, zip_path: str) -> str:
        tmp_dir = os.path.join(PROJ_DIR, "_tmp_extract")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        os.makedirs(tmp_dir, exist_ok=True)
        t_log.info(f"开始解压: {zip_path} -> {tmp_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)
        try:
            os.remove(zip_path)
        except Exception:
            pass
        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            return os.path.join(tmp_dir, entries[0])
        return tmp_dir

    def _prepare_extract_root_to(self, zip_path: str, target_tmp_dir: str) -> str:
        if os.path.exists(target_tmp_dir):
            shutil.rmtree(target_tmp_dir, ignore_errors=True)
        os.makedirs(target_tmp_dir, exist_ok=True)
        t_log.info(f"开始解压: {zip_path} -> {target_tmp_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(target_tmp_dir)
        try:
            os.remove(zip_path)
        except Exception:
            pass
        entries = os.listdir(target_tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(target_tmp_dir, entries[0])):
            return os.path.join(target_tmp_dir, entries[0])
        return target_tmp_dir

    def _create_post_update_bat(self, src_root: str, remote_v: str, update_level: int, backup_zip: str) -> str:
        dst_root = PROJ_DIR
        bat_path = os.path.join(PROJ_DIR, "_post_update.bat")
        last_run_bat = os.path.join(PROJ_DIR, "last_run.bat")
        update_level_str = str(update_level)
        bat_content = textwrap.dedent(f"""\
        @echo off
        setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

        set "PROJECT_ROOT={dst_root}"
        set "EXTRACT_DIR={src_root}"
        set "VERSION_FILE={self.version_file}"
        set "VERSION_STR={remote_v}"
        set "FORCE_UPDATE_STR={update_level_str}"
        set "LAST_RUN_BAT={last_run_bat}"
        set "LOG_FILE=%PROJECT_ROOT%\post_update.log"
        set "BACKUP_ZIP={backup_zip}"

        echo ===== POST UPDATE START: %DATE% %TIME% =====>>"%LOG_FILE%"

        rem 确保工作目录在项目根
        cd /d "%PROJECT_ROOT%"

        rem 等待进程彻底退出，释放文件句柄
        ping -n 2 127.0.0.1 >nul

        rem 主动结束可能占用复制文件的进程，避免报错 32
        for %%P in (adb.exe fastboot.exe scrcpy.exe) do (
            taskkill /F /IM %%P >nul 2>nul
        )
        rem 再次等待句柄释放
        ping -n 2 127.0.0.1 >nul

        echo Robocopy 进行镜像同步...>>"%LOG_FILE%"
        robocopy "%EXTRACT_DIR%" "%PROJECT_ROOT%" /MIR /COPY:DAT /R:2 /W:1 /NFL /NDL /NP ^
            /XD   "_tmp_extract" ".backup_version" ".runtime" ^
            /XF "_post_update.bat" "post_update.log" "_remote_version.yaml" "last_run.bat"
        set RC=%ERRORLEVEL%
        echo Robocopy 退出码: %RC%>>"%LOG_FILE%"
        if %RC% GEQ 8 (
            echo Robocopy 失败，将跳过写版本与重启，仅做清理。>>"%LOG_FILE%"
            goto CLEANUP_ONLY
        )

        echo 写入版本文件(YAML)...>>"%LOG_FILE%"
        if exist "%PROJECT_ROOT%\_remote_version.yaml" (
            copy /Y "%PROJECT_ROOT%\_remote_version.yaml" "%VERSION_FILE%" >nul
            del /f /q "%PROJECT_ROOT%\_remote_version.yaml" >nul 2>nul
        ) else (
            rem 如果临时版本文件不存在，手动写入基本字段（fallback）
            >"%VERSION_FILE%" echo version: %VERSION_STR%
            >>"%VERSION_FILE%" echo force_update: %FORCE_UPDATE_STR%
            >>"%VERSION_FILE%" echo updated_at: %DATE% %TIME%
            >>"%VERSION_FILE%" echo total_update_level_weight: 0
            >>"%VERSION_FILE%" echo is_patch: false
            >>"%VERSION_FILE%" echo support_mode_idx: 0
        )
        rem 额外等待文件系统刷新，避免 GUI 读取旧版本
        ping -n 2 127.0.0.1 >nul

        :CLEANUP_ONLY
        echo 清理临时目录...>>"%LOG_FILE%"
        if exist "%EXTRACT_DIR%" (
            attrib -r -h -s /s /d "%EXTRACT_DIR%" >nul 2>nul
            rd /s /q "%EXTRACT_DIR%" 2>nul
            if exist "%EXTRACT_DIR%" powershell -NoProfile -Command "Remove-Item -Force -Recurse \"%EXTRACT_DIR%\"" >nul 2>nul
        )
        if exist "%PROJECT_ROOT%\_tmp_extract" (
            attrib -r -h -s /s /d "%PROJECT_ROOT%\_tmp_extract" >nul 2>nul
            rd /s /q "%PROJECT_ROOT%\_tmp_extract" 2>nul
            if exist "%PROJECT_ROOT%\_tmp_extract" powershell -NoProfile -Command "Remove-Item -Force -Recurse \"%PROJECT_ROOT%\_tmp_extract\"" >nul 2>nul
        )

        if %RC% GEQ 8 (
            echo 因拷贝失败，已完成清理，不执行重启。>>"%LOG_FILE%"
            goto END
        )

        rem 校验版本文件已生成，否则取消重启
        if not exist "%VERSION_FILE%" (
            echo 版本文件未生成，取消重启以避免读取旧版本。>>"%LOG_FILE%"
            goto END
        )

        echo 尝试重启 GUI...>>"%LOG_FILE%"
        if exist "%LAST_RUN_BAT%" (
            echo 使用 LAST_RUN_BAT 启动>>"%LOG_FILE%"
            start "" "%LAST_RUN_BAT%"
            goto END
        )
        echo 未找到可用的重启脚本，无法重启 GUI。>>"%LOG_FILE%"

        :END
        echo ===== POST UPDATE END: %DATE% %TIME% =====>>"%LOG_FILE%"
        exit
        """)
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        return bat_path

    def _run_post_update_and_exit(self, bat_path: str) -> None:
        try:
            try:
                if callable(getattr(self, "on_progress", None)):
                    self.on_progress("complete", 1, 1)
                    time.sleep(0.1)
            except Exception:
                pass
            subprocess.Popen(f'start "" "{bat_path}"', shell=True, cwd=PROJ_DIR)
        except Exception as e:
            t_log.error(f"启动更新脚本失败: {e}")
        finally:
            os._exit(0)
    def _create_post_patch_update_bat(self, src_root: str, remote_v: str, update_level: int, backup_zip: str) -> str:
        dst_root = PROJ_DIR
        bat_path = os.path.join(PROJ_DIR, "_post_update.bat")
        last_run_bat = os.path.join(PROJ_DIR, "last_run.bat")
        update_level_str = str(update_level)
        bat_content = textwrap.dedent(f"""\
        @echo off
        setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

        set "PROJECT_ROOT={dst_root}"
        set "EXTRACT_DIR={src_root}"
        set "VERSION_FILE={self.version_file}"
        set "VERSION_STR={remote_v}"
        set "FORCE_UPDATE_STR={update_level_str}"
        set "LAST_RUN_BAT={last_run_bat}"
        set "LOG_FILE=%PROJECT_ROOT%\post_update.log"
        set "BACKUP_ZIP={backup_zip}"

        echo ===== POST UPDATE START: %DATE% %TIME% =====>>"%LOG_FILE%"

        cd /d "%PROJECT_ROOT%"
        ping -n 2 127.0.0.1 >nul
        for %%P in (adb.exe fastboot.exe scrcpy.exe) do (
            taskkill /F /IM %%P >nul 2>nul
        )
        ping -n 2 127.0.0.1 >nul

        echo Robocopy 进行增量同步...>>"%LOG_FILE%"
        robocopy "%EXTRACT_DIR%" "%PROJECT_ROOT%" /E /COPY:DAT /R:2 /W:1 /NFL /NDL /NP ^
            /XD   "_tmp_extract" ".backup_version" ".runtime" ^
            /XF "_post_update.bat" "post_update.log" "_remote_version.yaml" "last_run.bat"
        set RC=%ERRORLEVEL%
        echo Robocopy 退出码: %RC%>>"%LOG_FILE%"
        if %RC% GEQ 8 (
            echo Robocopy 失败，将跳过写版本与重启，仅做清理。>>"%LOG_FILE%"
            goto CLEANUP_ONLY
        )

        echo 写入版本文件(YAML)...>>"%LOG_FILE%"
        if exist "%PROJECT_ROOT%\_remote_version.yaml" (
            copy /Y "%PROJECT_ROOT%\_remote_version.yaml" "%VERSION_FILE%" >nul
            del /f /q "%PROJECT_ROOT%\_remote_version.yaml" >nul 2>nul
        ) else (
            >"%VERSION_FILE%" echo version: %VERSION_STR%
            >>"%VERSION_FILE%" echo force_update: %FORCE_UPDATE_STR%
            >>"%VERSION_FILE%" echo updated_at: %DATE% %TIME%
            >>"%VERSION_FILE%" echo total_update_level_weight: 0
            >>"%VERSION_FILE%" echo is_patch: true
            >>"%VERSION_FILE%" echo support_mode_idx: 0
        )
        ping -n 2 127.0.0.1 >nul

        :CLEANUP_ONLY
        echo 清理临时目录...>>"%LOG_FILE%"
        if exist "%EXTRACT_DIR%" (
            attrib -r -h -s /s /d "%EXTRACT_DIR%" >nul 2>nul
            rd /s /q "%EXTRACT_DIR%" 2>nul
            if exist "%EXTRACT_DIR%" powershell -NoProfile -Command "Remove-Item -Force -Recurse \"%EXTRACT_DIR%\"" >nul 2>nul
        )
        if exist "%PROJECT_ROOT%\_tmp_extract" (
            attrib -r -h -s /s /d "%PROJECT_ROOT%\_tmp_extract" >nul 2>nul
            rd /s /q "%PROJECT_ROOT%\_tmp_extract" 2>nul
            if exist "%PROJECT_ROOT%\_tmp_extract" powershell -NoProfile -Command "Remove-Item -Force -Recurse \"%PROJECT_ROOT%\_tmp_extract\"" >nul 2>nul
        )

        if %RC% GEQ 8 (
            echo 因拷贝失败，已完成清理，不执行重启。>>"%LOG_FILE%"
            goto END
        )

        if not exist "%VERSION_FILE%" (
            echo 版本文件未生成，取消重启以避免读取旧版本。>>"%LOG_FILE%"
            goto END
        )

        echo 尝试重启 GUI...>>"%LOG_FILE%"
        if exist "%LAST_RUN_BAT%" (
            start "" "%LAST_RUN_BAT%"
            goto END
        )
        echo 未找到可用的重启脚本，无法重启 GUI。>>"%LOG_FILE%"

        :END
        echo ===== POST UPDATE END: %DATE% %TIME% =====>>"%LOG_FILE%"
        exit
        """
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)
        return bat_path
        
    def apply_patch_update(self):
        try:
            self._progress_stage = "meta"
            remote_meta = self.get_remote_Specify_version()
        except Exception as e:
            t_log.warning(f"获取远端指定版本信息失败: {e}")
            return
        finally:
            try:
                self._progress_stage = None
            except Exception:
                pass
        local_v = self.get_local_version()
        remote_v = str(remote_meta.get("version", "0.0.0"))
        if local_v == remote_v:
            t_log.info("当前已是最新版本，暂无更新")
            return
        route = remote_meta.get("upgrade_path") or remote_meta.get("version_route") or []
        if not isinstance(route, list):
            route = []
        if remote_v not in route:
            route.append(remote_v)
        need_baseline_full = False
        pending_versions = []
        if local_v in route:
            try:
                idx = route.index(local_v)
                pending_versions = route[idx + 1:]
            except Exception:
                pending_versions = route
        else:
            need_baseline_full = True
            pending_versions = route
        patch_list = remote_meta.get("patch_list") or {}
        final_root = None
        baseline_version = remote_v
        if need_baseline_full:
            try:
                baseline_version = route[0] if route else remote_v
            except Exception:
                baseline_version = remote_v
            try:
                if self.on_progress:
                    try:
                        self.on_progress("extract", 0, 0)
                    except Exception:
                        pass
                base_zip = f"tpytest_{self.team}_{self.name}_{str(baseline_version).replace('.', '_')}.zip"
                base_remote = f"{self.name}/{base_zip}"
                base_local = os.path.join(PROJ_DIR, base_zip)
                self._feishu_provider.download(base_remote, base_local)
                base_root = self._prepare_extract_root(base_local)
                final_root = os.path.join(PROJ_DIR, "_tmp_patch_accum")
                try:
                    if os.path.exists(final_root):
                        shutil.rmtree(final_root, ignore_errors=True)
                    os.makedirs(final_root, exist_ok=True)
                except Exception:
                    pass
                for item in os.listdir(base_root):
                    s = os.path.join(base_root, item)
                    d = os.path.join(final_root, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(d), exist_ok=True)
                        shutil.copy2(s, d)
                try:
                    shutil.rmtree(base_root, ignore_errors=True)
                except Exception:
                    pass
                if self.is_overseas:
                    zip_name_os = f"tpytest_{self.team}_{self.name}_{str(baseline_version).replace('.', '_')}_overseas.zip"
                    remote_os = f"{self.name}/{zip_name_os}"
                    local_os = os.path.join(PROJ_DIR, zip_name_os)
                    self._feishu_provider.download(remote_os, local_os)
                    if not os.path.exists(local_os):
                        raise RuntimeError("海外模式需要标准包与海外包同时存在")
                    overlay_tmp = os.path.join(PROJ_DIR, "_tmp_extract_overseas_patch_base")
                    os_root = self._prepare_extract_root_to(local_os, overlay_tmp)
                    for item in os.listdir(os_root):
                        s = os.path.join(os_root, item)
                        d = os.path.join(final_root, item)
                        if os.path.isdir(s):
                            shutil.copytree(s, d, dirs_exist_ok=True)
                        else:
                            os.makedirs(os.path.dirname(d), exist_ok=True)
                            shutil.copy2(s, d)
                    try:
                        shutil.rmtree(overlay_tmp, ignore_errors=True)
                    except Exception:
                        pass
            except Exception as e:
                t_log.error(f"更新失败: {e}")
                return
            try:
                pending_versions = [v for v in pending_versions if v != baseline_version]
            except Exception:
                pass
        else:
            final_root = os.path.join(PROJ_DIR, "_tmp_patch_accum")
            try:
                if os.path.exists(final_root):
                    shutil.rmtree(final_root, ignore_errors=True)
                os.makedirs(final_root, exist_ok=True)
            except Exception:
                pass
        try:
            if self.on_progress:
                try:
                    self.on_progress("merge", 0, 0)
                except Exception:
                    pass
            for v in pending_versions:
                artifacts = []
                try:
                    entry = patch_list.get(v)
                    if isinstance(entry, list):
                        artifacts = entry
                except Exception:
                    artifacts = []
                if not artifacts:
                    try:
                        zip_name = f"tpytest_{self.team}_{self.name}_{str(v).replace('.', '_')}.zip"
                        remote_path = f"{self.name}/{zip_name}"
                        local_path = os.path.join(PROJ_DIR, zip_name)
                        self._feishu_provider.download(remote_path, local_path)
                        root = self._prepare_extract_root(local_path)
                        for item in os.listdir(root):
                            s = os.path.join(root, item)
                            d = os.path.join(final_root, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d, dirs_exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(d), exist_ok=True)
                                shutil.copy2(s, d)
                        if self.is_overseas:
                            zip_name_os = f"tpytest_{self.team}_{self.name}_{str(v).replace('.', '_')}_overseas.zip"
                            remote_os = f"{self.name}/{zip_name_os}"
                            local_os = os.path.join(PROJ_DIR, zip_name_os)
                            self._feishu_provider.download(remote_os, local_os)
                            if not os.path.exists(local_os):
                                raise RuntimeError("海外模式需要标准包与海外包同时存在")
                            overlay_tmp = os.path.join(PROJ_DIR, "_tmp_extract_overseas_patch")
                            os_root = self._prepare_extract_root_to(local_os, overlay_tmp)
                            for item in os.listdir(os_root):
                                s = os.path.join(os_root, item)
                                d = os.path.join(final_root, item)
                                if os.path.isdir(s):
                                    shutil.copytree(s, d, dirs_exist_ok=True)
                                else:
                                    os.makedirs(os.path.dirname(d), exist_ok=True)
                                    shutil.copy2(s, d)
                            try:
                                shutil.rmtree(overlay_tmp, ignore_errors=True)
                            except Exception:
                                pass
                        try:
                            shutil.rmtree(root, ignore_errors=True)
                        except Exception:
                            pass
                    except Exception as e:
                        t_log.error(f"更新失败: {e}")
                        return
                    continue
                for art in artifacts:
                    try:
                        remote_path = f"{self.name}/{art}"
                        local_zip = os.path.join(PROJ_DIR, os.path.basename(art))
                        self._feishu_provider.download(remote_path, local_zip)
                        patch_root = self._prepare_extract_root(local_zip)
                        for item in os.listdir(patch_root):
                            s = os.path.join(patch_root, item)
                            d = os.path.join(final_root, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d, dirs_exist_ok=True)
                            else:
                                os.makedirs(os.path.dirname(d), exist_ok=True)
                                shutil.copy2(s, d)
                        try:
                            shutil.rmtree(patch_root, ignore_errors=True)
                        except Exception:
                            pass
                    except Exception as e:
                        t_log.error(f"更新失败: {e}")
                        return
        except Exception as e:
            t_log.error(f"更新失败: {e}")
            return
        tmp_yaml_path = os.path.join(PROJ_DIR, "_remote_version.yaml")
        remote_weight = 0
        local_weight = 0
        try:
            remote_weight = int(remote_meta.get("total_update_level_weight", 0))
        except Exception:
            remote_weight = 0
        try:
            local_meta = self.get_remote_Specify_version(local_v)
            local_weight = int(local_meta.get("total_update_level_weight", 0))
        except Exception:
            local_weight = 0
        effective_update_level = 0
        try:
            effective_update_level = int(remote_meta.get("update_level", 0))
        except Exception:
            effective_update_level = 0
        try:
            if remote_weight - local_weight >= 10000:
                effective_update_level = 2
        except Exception:
            pass
        try:
            remote_support_mode = remote_meta.get("support_mode_idx", None)
            if remote_support_mode is not None:
                support_mode_idx = remote_support_mode
            else:
                support_mode_idx = 1 if self.is_overseas else 0
            version_data = {
                "version": remote_v,
                "force_update": effective_update_level,
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total_update_level_weight": remote_weight,
                "is_patch": True,
                "support_mode_idx": support_mode_idx,
            }
            yaml_utils.write_yaml(version_data, tmp_yaml_path, ignore_yaml_error=False)
        except Exception:
            pass
        if self.on_progress:
            try:
                self.on_progress("finalize", 0, 0)
                self.on_progress("complete", 1, 1)
            except Exception:
                pass
        bat_path = self._create_post_patch_update_bat(final_root, remote_v, effective_update_level, "")
        self._run_post_update_and_exit(bat_path)



    def apply_update(self, do_backup: bool = False, is_overseas: bool = False):
        """更新逻辑"""
        try:
            self._progress_stage = "meta"
            self.get_remote_Specify_version()
        except Exception as e:
            t_log.warning(f"获取远端指定版本信息失败: {e}")
        finally:
            self._progress_stage = None
        if not self.has_update():
            t_log.info("当前已是最新版本，暂无更新")
            return
        if getattr(VersionMeta, "is_patch", False):
            t_log.info("🔄 Patch更新模式 → 不备份，仅合并变更")
            return self.apply_patch_update()
        try:
            zip_local, zip_overseas = self.download_new_version_zip(is_overseas=is_overseas)

            # 通知下载完成
            if self.on_progress:
                try:
                    self.on_progress("complete", 1, 1)
                except Exception:
                    pass

            if is_overseas:
                if not (zip_local and os.path.exists(zip_local)) or not (zip_overseas and os.path.exists(zip_overseas)):
                    raise RuntimeError("海外模式需要标准包与海外包同时存在")

                # 解压和合并阶段
                if self.on_progress:
                    try:
                        self.on_progress("extract", 0, 0)
                    except Exception:
                        pass

                base_root = self._prepare_extract_root(zip_local)
                overlay_tmp = os.path.join(PROJ_DIR, "_tmp_extract_overseas")
                overseas_root = self._prepare_extract_root_to(zip_overseas, overlay_tmp)

                # 合并海外包
                if self.on_progress:
                    try:
                        self.on_progress("merge", 0, 0)
                    except Exception:
                        pass

                for item in os.listdir(overseas_root):
                    s = os.path.join(overseas_root, item)
                    d = os.path.join(base_root, item)
                    shutil.copytree(s, d, dirs_exist_ok=True)
                try:
                    shutil.rmtree(overlay_tmp, ignore_errors=True)
                except Exception:
                    pass
                src_root = base_root
            else:
                # 解压阶段
                if self.on_progress:
                    try:
                        self.on_progress("extract", 0, 0)
                    except Exception:
                        pass
                src_root = self._prepare_extract_root(zip_local)
            tmp_yaml_path = os.path.join(PROJ_DIR, "_remote_version.yaml")
            remote_weight = int(getattr(VersionMeta, "total_update_level_weight", 0))
            local_weight = 0
            try:
                local_ver = self.get_local_version()
                local_meta = self.get_remote_Specify_version(local_ver)
                local_weight = int(local_meta.get("total_update_level_weight", 0))
            except Exception:
                pass
            effective_update_level = int(getattr(VersionMeta, "update_level", 0))
            try:
                if remote_weight - local_weight >= 10000:
                    effective_update_level = 2
            except Exception:
                pass
            try:
                # 准备版本信息，包含所有必要字段
                # support_mode_idx: 0=国内标准, 1=海外标准, 2=双模式
                # 优先使用远程元数据中的值，如果没有则根据is_overseas参数推断
                remote_support_mode = getattr(VersionMeta, "support_mode_idx", None)
                if remote_support_mode is not None:
                    support_mode_idx = remote_support_mode
                else:
                    support_mode_idx = 1 if is_overseas else 0

                version_data = {
                    "version": getattr(VersionMeta, "version", self.get_remote_meta()),
                    "force_update": effective_update_level,
                    "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total_update_level_weight": remote_weight,
                    "is_patch": getattr(VersionMeta, "is_patch", False),
                    "support_mode_idx": support_mode_idx,
                }
                yaml_utils.write_yaml(version_data, tmp_yaml_path, ignore_yaml_error=False)
            except Exception:
                pass
            backup_zip = ""
            try:
                if do_backup or effective_update_level >= 2:
                    # 备份阶段
                    if self.on_progress:
                        try:
                            self.on_progress("backup", 0, 0)
                        except Exception:
                            pass
                    backup_zip = self.backup_project()
            except Exception:
                pass

            # 最终化阶段
            if self.on_progress:
                try:
                    self.on_progress("finalize", 0, 0)
                except Exception:
                    pass

            bat_path = self._create_post_update_bat(src_root, getattr(VersionMeta, "version", self.get_remote_meta()), effective_update_level, backup_zip)
            self._run_post_update_and_exit(bat_path)
        except Exception as e:
            t_log.error(f"更新失败: {e}")




if __name__ == '__main__':
    _feishu_updater = FeiShuUpdater("dzppt", "dou3")
    # _feishu_updater._extract_zip_to_project_root(r"E:\WorkSpace\pro\tpytest_dzppt_dou3\tpytest_dzppt_dou3_2_1_20.zip")
    _feishu_updater.apply_patch_update()

