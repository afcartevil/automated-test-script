import shutil
import subprocess
import os
import textwrap
import time
import zipfile
import requests
from powertrde.framework.tran_logger import t_log
from powertrde.env import CONFIG_DIR, PROJ_DIR
from powertrde.utils import yaml_utils,encryption_utils


class GitUpdater:
    def __init__(self, team=None, name=None, on_progress=None):
        self.team = team
        self.name = name
        self._local_version = None
        self._remote_version = None
        self.enabled = False
        self.on_progress = on_progress
        self._load_config()

        # 构建远程版本URL
        if self.enabled:
            # 动态获取版本文件路径
            self.version_file = self._get_version_file_path()
            self.remote_version_url = f"http://gitlab.transsion.com/api/v4/projects/{self.project_id}/repository/files/{self.file_path}/raw?ref={self.branch}"
        else:
            self.remote_version_url = None
            self.version_file = None
            self.remote_version_url = None
            self.headers = {}
        self._remote_meta = None
        self._remote_yaml_bytes = None

    def _load_config(self):
        """从配置文件加载Git更新相关配置；若缺失则禁用自动更新而不抛异常"""
        config_file = os.path.join(CONFIG_DIR, self.team, self.name, 'base_config.yaml')

        if not os.path.exists(config_file):
            t_log.info(f"未找到配置文件，自动更新已禁用: {config_file}")
            self.enabled = False
            return

        config = yaml_utils.read_yaml(config_file, ignore_yaml_error=False)
        if not config or 'git_updater' not in config:
            t_log.info("配置文件中缺少 git_updater 配置，自动更新已禁用")
            self.enabled = False
            return

        git_config = config['git_updater']

        # 关键字段检查，不完整即禁用
        required_keys = ['project_id', 'file_path', 'branch', 'namespace', 'project', 'encrypt_token']
        missing = [k for k in required_keys if not git_config.get(k)]
        if missing:
            t_log.warning(f"git_updater 配置缺少关键字段 {missing}，自动更新已禁用")
            self.enabled = False
            return

        # 配置完整则启用自动更新
        self.repo_url = git_config.get('repo_url')
        self.branch = git_config['branch']
        self.project_id = git_config['project_id']
        self.file_path = git_config['file_path']
        self.token_md5 = git_config['encrypt_token']
        self.project = git_config['project']
        self.namespace = git_config['namespace']
        self.token = self._get_original_token(self.token_md5)
        self.headers = {"PRIVATE-TOKEN": self.token}
        self.enabled = True

    def _get_original_token(self, token_md5: str) -> str:
        """获取原始token - 这里需要根据实际安全需求实现"""
        token = encryption_utils.decrypt(token_md5)
        return token

    def _get_version_file_path(self) -> str:

        if not hasattr(self, "file_path") or not self.file_path:
            return None
        return os.path.join(PROJ_DIR, self.file_path)

    def _run_cmd(self, cmd: str, cwd: str = None) -> str:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, shell=True)
        if result.returncode != 0:
            raise RuntimeError(f"命令执行失败: {cmd}\n错误: {result.stderr}")
        return result.stdout.strip()

    def download_new_version(self):
        """下载远程 zip 包并解压到临时目录，随后交由外部 .bat 完成覆盖与重启"""
        if not self.enabled:
            t_log.info("自动更新未配置或已禁用，跳过下载。")
            return
        download_url = f"http://gitlab.transsion.com/{self.namespace}/{self.project}/-/archive/{self.branch}/{self.project}-{self.branch}.zip"
        t_log.info(f"开始下载: {download_url}")
        resp = requests.get(download_url, headers=self.headers, timeout=300, stream=True)
        if resp.status_code != 200:
            raise RuntimeError(f"下载失败: HTTP {resp.status_code}")
        try:
            total_size = int(resp.headers.get("Content-Length", "0"))
        except Exception:
            total_size = 0
        if total_size > 0:
            t_log.info(f"远程压缩包大小: {total_size / 1024 / 1024:.2f} MB ({total_size} bytes)")
        zip_path = os.path.join(PROJ_DIR, f"{self.project}-{self.branch}.zip")
        downloaded = 0
        last_ts = 0
        with open(zip_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 1024):
               if not chunk:
                   continue
               f.write(chunk)
               downloaded += len(chunk)
               #回调下载进度
               if self.on_progress:
                   now = time.time()
                   if (now - last_ts) >= 0.1 or downloaded % (5 * 1024 * 1024) == 0:
                       try:
                           self.on_progress("download",downloaded,total_size)
                       except Exception as e:
                           t_log.warning(f"进度回调失败：{str(e)}")
                       last_ts = now
        #下载完成后再回调一次
        if self.on_progress:
            try:
                # 若 total_size 为 0，total 也传实际大小以便 GUI 显示完整
                actual_size = os.path.getsize(zip_path)
                final_total = total_size if total_size > 0 else actual_size
                self.on_progress("download", actual_size, final_total)
            except Exception as e:
                t_log.warning(f"获取本地压缩包大小失败: {e}")

        # 新增：输出本地实际下载后的文件大小
        try:
            final_size = os.path.getsize(zip_path)
            t_log.info(f"实际下载大小: {final_size/1024/1024:.2f} MB ({final_size} bytes)")
        except Exception as e:
            t_log.warning(f"获取本地压缩包大小失败: {e}")
        # 解压前，先预清理项目根目录（保留运行与更新相关项），同时保留压缩包本身
        try:
            zip_name = os.path.basename(zip_path)
            self._preclean_project_root(extra_preserve_files=[zip_name])
            t_log.info("已预清理项目根目录")
        except Exception as e:
            t_log.warning(f"预清理项目根目录失败: {e}")
        # 解压到临时目录，得到实际根目录
        src_root = self._prepare_extract_root(zip_path)
        # 删除下载的压缩包
        try:
            os.remove(zip_path)
            t_log.debug(f"已删除下载包: {zip_path}")
        except Exception as e:
            t_log.warning(f"删除下载包失败: {e}")
        meta = self._remote_meta or self.get_remote_meta()
        # 生成 .bat 并退出，由 .bat 完成覆盖与重启
        remote_v = self._remote_version or self.get_remote_version()
        update_level = int(meta.get("update_level", 0))
        try:
            tmp_yaml_path = os.path.join(PROJ_DIR, "_remote_version.yaml")
            if self._remote_yaml_bytes:
                with open(tmp_yaml_path, "wb") as yf:
                    yf.write(self._remote_yaml_bytes)
                t_log.debug(f"已写入远端版本临时文件: {tmp_yaml_path}")
            else:
                if os.path.exists(tmp_yaml_path):
                    os.remove(tmp_yaml_path)
        except Exception as e:
            t_log.warning(f"写入远端版本临时文件失败: {e}")
        #通过gui下载结束
        if self.on_progress:
            try:
                self.on_progress("complete", 1, 1)
            except Exception as e:
                t_log.warning(f"完成回调失败: {e}")
        bat_path = self._create_post_update_bat(src_root, remote_v, update_level)
        self._run_post_update_and_exit(bat_path)

    def get_local_version(self) -> str:
        """
        优先从 YAML 读取 version 字段；若不存在则兼容旧的 TXT 文件。
        """
        if not self.enabled or not self.version_file:
            return "0.0.0"
        try:
            if os.path.exists(self.version_file):
                data = yaml_utils.read_yaml(self.version_file, ignore_yaml_error=False)
                if isinstance(data, dict) and "version" in data:
                    return str(data["version"]).strip()
        except Exception as e:
            t_log.warning(f"读取 YAML 版本文件失败: {e}")
        return "0.0.0"

    def get_remote_meta(self) -> dict:
        """获取并解析远端 YAML 版本元信息，回退兼容纯文本"""
        if not self.enabled or not self.remote_version_url:
            return {"version": "0.0.0", "update_level": 0, "release_notes": None}
        if self._remote_meta is not None:
            return self._remote_meta
        try:
            resp = requests.get(self.remote_version_url, headers=self.headers, timeout=10)
            if resp.status_code != 200:
                raise RuntimeError(f"无法获取远程版本元信息: {resp.status_code}")
            self._remote_yaml_bytes = resp.content
            text = resp.text
            # 去除可能的 BOM
            if text and text[:1] == '\ufeff':
                text = text[1:]
            text = text.strip()
            data = None
            try:
                import yaml
                data = yaml.safe_load(text)
            except Exception as e:
                t_log.warning(f"远端版本文件 YAML 解析失败，回退正则解析: {e}")
                data = None

            # 提取版本号
            version_value = None
            if isinstance(data, dict) and "version" in data:
                version_value = str(data.get("version")).strip()
            else:
                # 尝试从纯文本中正则提取第一个 x.y.z
                import re
                m = re.search(r'(\d+)\.(\d+)\.(\d+)', text)
                if m:
                    version_value = ".".join(m.groups())
                else:
                    # 最后兜底：直接用文本（可能是旧格式）
                    version_value = text

            # 提取 update_level 和 release_notes（若存在）
            update_level_value = 0
            if isinstance(data, dict) and "update_level" in data:
                try:
                    update_level_value = int(data.get("update_level", 0))
                except Exception:
                    update_level_value = 0
            release_notes_value = data.get("release_notes") if isinstance(data, dict) else None

            meta = {
                "version": version_value,
                "update_level": update_level_value,
                "release_notes": release_notes_value,
            }
            self._remote_meta = meta
            self._remote_version = meta["version"]
            return meta
        except Exception as e:
            raise RuntimeError(f"无法获取远程版本元信息: {e}")

    def get_remote_version(self) -> str:
        """通过 HTTP 请求拉取远程 YAML 版本文件，解析 version 字段；若远端仍是旧 TXT，则回退为纯文本。"""
        if not self.enabled:
            return "0.0.0"
        return self.get_remote_meta()["version"]

    def _version_to_tuple(self, v: str):
        """版本字符串转换为元组用于比较（容错：从任意文本中提取第一个 x.y.z）"""
        import re
        s = str(v or "").strip()
        m = re.search(r'(\d+)\.(\d+)\.(\d+)', s)
        if not m:
            t_log.warning(f"版本字符串非法，使用默认版本 0.0.0: {s}")
            return (0, 0, 0)
        try:
            return tuple(map(int, m.groups()))
        except Exception as e:
            t_log.warning(f"版本解析失败，使用默认版本 0.0.0: {s}，错误: {e}")
            return (0, 0, 0)

    def _fetch_versions(self, force_refresh=False):
        """获取本地和远程版本，支持缓存"""
        if force_refresh or self._local_version is None:
            self._local_version = self.get_local_version()

        if force_refresh or self._remote_version is None:
            self._remote_version = self.get_remote_version()

        return self._local_version, self._remote_version

    def has_update(self) -> bool:
        """检查是否有更新"""
        if not self.enabled:
            return False
        local_version, remote_version = self._fetch_versions()
        if local_version == '0.0.0':
            return False
        current = self._version_to_tuple(local_version)
        t_log.debug(f"当前版本为：{current}")
        latest = self._version_to_tuple(remote_version)
        t_log.debug(f"服务器版本为：{latest}")
        return current < latest

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


    def _extract_zip_to_project_root(self, zip_path: str):
        """将 zip 解压到临时目录后，覆盖拷贝到项目根目录，最后清理临时目录"""
        tmp_dir = os.path.join(PROJ_DIR, "_tmp_extract")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        os.makedirs(tmp_dir, exist_ok=True)

        t_log.info(f"开始解压: {zip_path} -> {tmp_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)

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
                shutil.copytree(src, dst)
            else:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.copy2(src, dst)

        shutil.rmtree(tmp_dir, ignore_errors=True)
        t_log.info("远程代码解压并覆盖完成")

    def update_repo(self):
        """强制同步远程代码"""
        if not self.enabled:
            t_log.info("自动更新未配置或已禁用，跳过更新。")
            return
        t_log.info("开始更新代码...")
        self.download_new_version()
        try:
            meta = self._remote_meta or self.get_remote_meta()
            yaml_data = {
                "version": meta.get("version", self._remote_version or "0.0.0"),
                "update_level": int(meta.get("update_level", 0)),
                "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            yaml_utils.write_yaml(yaml_data, self.version_file, ignore_yaml_error=False)
            t_log.info(f"已更新本地版本文件(YAML): {yaml_data}")
        except Exception as e:
            t_log.warning(f"写入本地 YAML 版本文件失败: {e}")

    def _create_post_update_bat(self, src_root: str, remote_v: str, update_level: int) -> str:
        """生成在进程退出后执行覆盖的 .bat 脚本（优先使用 last_run.bat 进行重启）"""
        dst_root = PROJ_DIR
        bat_path = os.path.join(PROJ_DIR, "_post_update.bat")
        last_run_bat = os.path.join(PROJ_DIR, "last_run.bat")
        update_level_str = str(update_level)
        # 统一使用“路径”而不是“内容”，并把版本文件写为 YAML
        bat_content = textwrap.dedent(f"""\
        @echo off
        setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION

        set "PROJECT_ROOT={dst_root}"
        set "EXTRACT_DIR={src_root}"
        set "VERSION_FILE={self.version_file}"
        set "VERSION_STR={remote_v}"
        set "FORCE_UPDATE_STR={update_level_str}"
        set "LAST_RUN_BAT={last_run_bat}"
        set "LOG_FILE=%PROJECT_ROOT%\\post_update.log"

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
        if exist "%PROJECT_ROOT%\\_remote_version.yaml" (
            copy /Y "%PROJECT_ROOT%\\_remote_version.yaml" "%VERSION_FILE%" >nul
            del /f /q "%PROJECT_ROOT%\\_remote_version.yaml" >nul 2>nul
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
        )
        if exist "%PROJECT_ROOT%\\_tmp_extract" (
            attrib -r -h -s /s /d "%PROJECT_ROOT%\\_tmp_extract" >nul 2>nul
            rd /s /q "%PROJECT_ROOT%\\_tmp_extract" 2>nul
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
        import subprocess, os
        try:
            # 使用 start 新开会话执行 .bat，避免继承当前进程句柄
            subprocess.Popen(f'start "" "{bat_path}"', shell=True, cwd=PROJ_DIR)
        except Exception as e:
            t_log.error(f"启动更新脚本失败: {e}")
        finally:
            # 直接退出当前 Python 进程，让外部脚本接管
            os._exit(0)

    def _preclean_project_root(self, extra_preserve_files=None,extra_preserve_dirs=None):
        """清理项目根目录中上个版本的文件，保留运行与更新相关项。
        可通过 extra_preserve_files 额外保留指定文件（例如当前下载的 zip）。"""
        root = PROJ_DIR
        preserve_dirs = {".runtime",".backup_version"}
        preserve_files = {
            "_post_update.bat",
            "post_update.log",
            "_remote_version.yaml",
            "last_run.bat",
        }
        if extra_preserve_files:
            try:
                preserve_files.update(set(extra_preserve_files))
            except Exception:
                pass
        if extra_preserve_dirs:
            try:
                preserve_dirs.update(set(extra_preserve_dirs))
            except Exception:
                pass

        for name in os.listdir(root):
            path = os.path.join(root, name)
            if os.path.isdir(path):
                if name in preserve_dirs:
                    continue
                t_log.info(f"开始删除目录: {path}")
                shutil.rmtree(path, ignore_errors=True)
            else:
                if name not in preserve_files:
                    t_log.info(f"开始删除文件: {path}")
                    try:
                        os.remove(path)
                    except Exception:
                        pass

    def _prepare_extract_root(self, zip_path: str) -> str:
        """将 zip 解压到临时目录并返回实际根目录（兼容 GitLab 顶级目录包裹）"""
        tmp_dir = os.path.join(PROJ_DIR, "_tmp_extract")
        if os.path.exists(tmp_dir):
            shutil.rmtree(tmp_dir, ignore_errors=True)
        os.makedirs(tmp_dir, exist_ok=True)

        t_log.info(f"开始解压: {zip_path} -> {tmp_dir}")
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(tmp_dir)

        entries = os.listdir(tmp_dir)
        if len(entries) == 1 and os.path.isdir(os.path.join(tmp_dir, entries[0])):
            src_root = os.path.join(tmp_dir, entries[0])
        else:
            src_root = tmp_dir
        return src_root

