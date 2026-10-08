"""稳定性 Checklist 自检工具（TAHP / AI 自检，MTK / Qcom）。

由 cases/kernel_feature/stability/caseN.py 调用，风格对齐 wbs_checker：
- 入口类 StabilityChecker(serial, on_step=...)
- 每项 run_item(id) → Pass / Fail / NA / Pending（缺 code_dir 需源码验证时）

对齐飞书「稳定性checklist」A17（MTK）与 Qcom：
- 工具默认内置在本目录（Dispatcher / aee_extract / tne_parser / tdsm / tran_pdfs / qcom_dump）
- code_dir（Android 源码根）经 stability.config.json / 环境变量 / Console 配置
- adb 一律带 -s <serial>，适配 Console 多设备
- 高通：user_root 开机后 dload 默认回 full；每次用例开始及每次 wait-for-device 后
  须 adb root，并重写 dload_mode（默认 mini；仅 case24 用 both）
"""
from __future__ import annotations

import json
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_TOOL_DIR = Path(__file__).resolve().parent
if str(_TOOL_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOL_DIR))

from code_analysis import (  # noqa: E402
    analyze_case10_tne_artifacts,
    analyze_mrdump_key,
    check_boot_reason_enums,
    check_dispatcher_sysrq,
    code_file_contains,
    find_analysis_dir,
    search_earlycon_in_tree,
)

CheckFn = Callable[["StabilityChecker"], Tuple[str, str]]

TOOL_ROOT = _TOOL_DIR

CHECKLIST_ITEMS: List[Dict[str, str]] = [
    {"id": "1", "name": "log配置", "mode": "code"},
    {"id": "2", "name": "三键uart和console功能配置", "mode": "manual"},
    {"id": "3", "name": "检查Kernel panic前串口打印", "mode": "adb"},
    {"id": "4", "name": "长按power key软重启", "mode": "manual"},
    {"id": "5", "name": "检查user版本默认uart是否关闭", "mode": "manual"},
    {"id": "6", "name": "下载模式DA返回清除异常状态", "mode": "adb"},
    {"id": "7", "name": "双键触发hang", "mode": "manual"},
    {"id": "8", "name": "db文件检查", "mode": "tools"},
    {"id": "9", "name": "root版本开机完成停止串口log", "mode": "adb"},
    {"id": "10", "name": "关闭RT_RUNTIME_SHARE", "mode": "code"},
    {"id": "12", "name": "SODI移除检查", "mode": "code"},
    {"id": "13", "name": "不开机log_store[TDFS]检查", "mode": "tools"},
    {"id": "14", "name": "关闭mrdump_key功能", "mode": "adb"},
    {"id": "15", "name": "mt6789平台晶振patch检查", "mode": "code"},
    {"id": "16", "name": "OCP埋点", "mode": "manual"},
    {"id": "17", "name": "器件稳定性埋点", "mode": "tools"},
    {"id": "18", "name": "fec2.0方案", "mode": "adb"},
    {"id": "19", "name": "黑屏定屏类故障检测", "mode": "tools"},
    {"id": "11", "name": "解析expdb/tranpdb", "mode": "tools"},
    {"id": "20", "name": "重启检查", "mode": "manual"},
    {"id": "21", "name": "cpu中sram bitflip导致的黑屏问题", "mode": "code"},
    {"id": "22", "name": "kernel-5.10 s2idle hwt patch检查", "mode": "code"},
    {"id": "23", "name": "MTK平台检查pl/lk的boot_reason枚举定义顺序保持一致", "mode": "code"},
    {"id": "24", "name": "minidump && fulldump转存", "mode": "tools"},
    {"id": "25", "name": "kasan适配", "mode": "manual"},
    {"id": "26", "name": "启动日志保存", "mode": "adb"},
    {"id": "27", "name": "crash界面优化", "mode": "manual"},
]

QCOM_MINIDUMP_DIR = "/data/vendor/debuglogger/minidump"
QCOM_BOOT_LOG_DIR = "/data/vendor/debuglogger/stability"
QCOM_DLOAD_MODE_PATH = "/sys/kernel/dload/dload_mode"
QCOM_KCONSOLE_NAME = "md_KCONSOLE.BIN"

# case8 db：sysrq 触发 fulldump，需较长固定等待（可通过环境变量覆盖）
def _env_positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = int(raw)
        return val if val > 0 else default
    except ValueError:
        return default


CASE8_FULLDUMP_WAIT_SEC = _env_positive_int("TAHP_STABILITY_CASE8_FULLDUMP_WAIT_SEC", 600)
CASE8_WAIT_DEVICE_TIMEOUT_SEC = _env_positive_int("TAHP_STABILITY_CASE8_WAIT_DEVICE_SEC", 1200)
CASE8_POST_BOOT_WAIT_SEC = _env_positive_int("TAHP_STABILITY_CASE8_POST_BOOT_WAIT_SEC", 300)
# case11 已 output-set none，无 fulldump，开机很快；勿用 case8 那套长超时
CASE11_WAIT_DEVICE_TIMEOUT_SEC = _env_positive_int("TAHP_STABILITY_CASE11_WAIT_DEVICE_SEC", 180)
CASE11_POST_BOOT_WAIT_SEC = _env_positive_int("TAHP_STABILITY_CASE11_POST_BOOT_WAIT_SEC", 60)
CASE24_SAHARA_TIMEOUT_SEC = _env_positive_int("TAHP_STABILITY_CASE24_SAHARA_SEC", 900)
CASE24_WAIT_DEVICE_TIMEOUT_SEC = _env_positive_int("TAHP_STABILITY_CASE24_WAIT_DEVICE_SEC", 600)
CASE24_POST_BOOT_WAIT_SEC = _env_positive_int("TAHP_STABILITY_CASE24_POST_BOOT_WAIT_SEC", 90)

# caseIndex → platforms（来自 case_config；缺省不限制）
_CASE_PLATFORMS: Dict[int, List[str]] = {}


def _load_case_platforms() -> Dict[int, List[str]]:
    global _CASE_PLATFORMS
    if _CASE_PLATFORMS:
        return _CASE_PLATFORMS
    cfg_path = TOOL_ROOT.parents[2] / "case_config" / "kernel_feature_stability.json"
    out: Dict[int, List[str]] = {}
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
            for row in raw.get("cases") or []:
                idx = int(row.get("caseIndex") or 0)
                plats = row.get("platforms")
                if idx and isinstance(plats, list) and plats:
                    out[idx] = [str(p).strip().lower() for p in plats if str(p).strip()]
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            out = {}
    _CASE_PLATFORMS = out
    return out


def checklist_item_name(item_id: int) -> str:
    for row in CHECKLIST_ITEMS:
        if int(row["id"]) == int(item_id):
            return str(row["name"])
    return f"稳定性检查项 {item_id}"


def _load_config(overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    cfg_path = TOOL_ROOT / "stability.config.json"
    raw: Dict[str, Any] = {}
    if cfg_path.is_file():
        try:
            raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            raw = {}
    paths = dict(raw.get("paths") or {})
    if overrides:
        for key in ("code_dir", "tools_root", "work_dir", "product_name"):
            if overrides.get(key):
                if key in ("code_dir", "tools_root", "work_dir"):
                    paths[key] = overrides[key]
                else:
                    raw[key] = overrides[key]
        if overrides.get("case2_reboot") is not None:
            raw["case2_reboot"] = bool(overrides["case2_reboot"])

    code_dir = (
        os.environ.get("TAHP_STABILITY_CODE_DIR", "").strip()
        or str(paths.get("code_dir") or "").strip()
    )
    # 默认使用本目录内置工具（Dispatcher / aee_extract / tne_parser / tdsm / tran_pdfs）
    tools_root = (
        os.environ.get("TAHP_STABILITY_TOOLS_ROOT", "").strip()
        or str(paths.get("tools_root") or "").strip()
        or str(TOOL_ROOT)
    )
    # 优先：调用方传入 / 环境变量（Console 用例目录）；否则脚本旁 workspace（仅本地手跑）
    work_rel = (
        (str(overrides.get("work_dir")).strip() if overrides and overrides.get("work_dir") else "")
        or os.environ.get("TAHP_STABILITY_WORK_DIR", "").strip()
        or str(paths.get("work_dir") or "workspace").strip()
        or "workspace"
    )
    work_dir = Path(work_rel)
    if not work_dir.is_absolute():
        work_dir = (TOOL_ROOT / work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)

    case10 = dict(raw.get("case10") or {})
    return {
        "code_dir": Path(code_dir).expanduser() if code_dir else None,
        "tools_root": Path(tools_root).expanduser(),
        "work_dir": work_dir,
        "product_name": str(raw.get("product_name") or "").strip(),
        "tdsm_sequence": str(raw.get("tdsm_sequence") or "no1").strip(),
        "case2_reboot": bool(raw.get("case2_reboot", False)),
        "adb_after_root_sec": float(raw.get("adb_after_root_sec", 5)),
        "case10_tne_focus_prefix": str(case10.get("tne_focus_dir_prefix") or "0xffffff35"),
        "case10_tne_remote_dir": str(case10.get("tne_remote_dir") or "/data/TNE"),
        # hung dump 落盘常晚于 hung 检测；固定 60s 后仍可能没有 0xffffff35*.tne
        "case10_tne_appear_timeout_sec": int(case10.get("tne_appear_timeout_sec") or 180),
        "case10_tne_poll_sec": int(case10.get("tne_poll_sec") or 15),
    }


class StabilityChecker:
    """稳定性 checklist 执行器（Console AI 自检）。"""

    def __init__(
        self,
        serial: str,
        on_step: Optional[Callable[[str], None]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        if not serial or not str(serial).strip():
            raise ValueError("device serial is required")
        self.serial = str(serial).strip()
        self.on_step = on_step
        self.cfg = _load_config(config)
        self.results: Dict[int, Dict[str, str]] = {}
        self.project_root = str(TOOL_ROOT)
        self._chip_platform: Optional[str] = None
        # 高通 dload_mode 不持久：user_root 开机默认回 full；记录当前期望，每次开机后重写
        self._qcom_dload_desired: str = "mini"

    def _emit(self, message: str) -> None:
        if self.on_step:
            try:
                self.on_step(message)
            except Exception:
                pass

    # ── adb / shell ─────────────────────────────────────────────

    def run_adb(self, command: str, timeout: int = 30) -> Tuple[str, str]:
        try:
            cmd = command.strip()
            if cmd.startswith("adb "):
                cmd = cmd[4:].strip()
            if cmd.startswith("shell "):
                shell_arg = cmd[len("shell ") :].strip()
                # 去掉外层引号，避免 list 传参时把 " 当成远程命令的一部分
                if (shell_arg.startswith('"') and shell_arg.endswith('"')) or (
                    shell_arg.startswith("'") and shell_arg.endswith("'")
                ):
                    shell_arg = shell_arg[1:-1]
                # 与手动 `adb shell "echo c > …"` 一致：整串作为唯一参数交给设备默认 shell。
                # 不要拆成 echo/c/>/path（重定向会失效）；也不强制套一层 sh -c（部分机型行为不一致）。
                args = ["adb", "-s", self.serial, "shell", shell_arg]
            elif cmd.startswith("shell"):
                args = ["adb", "-s", self.serial, "shell"]
            else:
                args = ["adb", "-s", self.serial, *cmd.split()]
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out_b, err_b = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                out_b, err_b = proc.communicate()
                return (out_b or b"").decode("utf-8", errors="ignore").strip(), "Timeout expired"
            return (
                (out_b or b"").decode("utf-8", errors="ignore").strip(),
                (err_b or b"").decode("utf-8", errors="ignore").strip(),
            )
        except Exception as exc:
            return "", str(exc)

    def run_adb_argv(self, argv: List[str], timeout: int = 30) -> Tuple[str, str]:
        """直接按 argv 调 adb（已含 -s 时不要重复加）。"""
        try:
            args = list(argv)
            if not args:
                return "", "empty argv"
            if args[0] != "adb":
                args = ["adb", *args]
            # 自动补 -s serial（若调用方未带）
            if "-s" not in args:
                args[1:1] = ["-s", self.serial]
            proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                out_b, err_b = proc.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                out_b, err_b = proc.communicate()
                return (out_b or b"").decode("utf-8", errors="ignore").strip(), "Timeout expired"
            return (
                (out_b or b"").decode("utf-8", errors="ignore").strip(),
                (err_b or b"").decode("utf-8", errors="ignore").strip(),
            )
        except Exception as exc:
            return "", str(exc)

    def run_host(self, args: List[str], cwd: Optional[Path] = None, timeout: int = 600) -> Tuple[int, str]:
        try:
            proc = subprocess.run(
                args,
                cwd=str(cwd or self.cfg["work_dir"]),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
            return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
        except subprocess.TimeoutExpired:
            return 1, "Timeout expired"
        except Exception as exc:
            return 1, str(exc)

    def ensure_root(self) -> None:
        """打开 adb root。高通默认无 root，重启后每次都需重新 adb root。"""
        self.run_adb("root", timeout=30)
        self.run_adb("wait-for-device", timeout=90)
        wait = float(self.cfg.get("adb_after_root_sec") or 0)
        if wait > 0:
            time.sleep(wait)
        uid, _ = self.run_adb("shell id", timeout=10)
        if "uid=0" not in (uid or ""):
            # 再试一次（部分机型 root 后需多等一会）
            time.sleep(2)
            self.run_adb("root", timeout=30)
            self.run_adb("wait-for-device", timeout=90)
            if wait > 0:
                time.sleep(wait)

    def detect_chip_platform(self) -> str:
        """返回 mtk / qcom / unisoc / unknown（缓存）。"""
        if self._chip_platform:
            return self._chip_platform
        props = [
            "ro.hardware",
            "ro.board.platform",
            "ro.soc.manufacturer",
            "ro.product.board",
        ]
        blob = ""
        for prop in props:
            out, _ = self.run_adb(f"shell getprop {prop}", timeout=10)
            blob += f" {out or ''}"
        low = blob.lower()
        if any(k in low for k in ("qcom", "qualcomm", "msm", "sdm", "sm8", "sm7", "kona", "lahaina", "taro", "kalama", "pineapple")):
            self._chip_platform = "qcom"
        elif any(k in low for k in ("mt", "mediatek")):
            self._chip_platform = "mtk"
        elif any(k in low for k in ("unisoc", "sprd", "ums", "udx")):
            self._chip_platform = "unisoc"
        else:
            self._chip_platform = "unknown"
        self._emit(f"检测到芯片平台: {self._chip_platform}（props={blob.strip()[:160]}）")
        return self._chip_platform

    def set_qcom_dload_mode(self, mode: str) -> Tuple[bool, str]:
        """设置高通 dump 模式：mini / full / both（须已 adb root；不持久）。"""
        mode = (mode or "").strip().lower()
        if mode not in ("mini", "full", "both"):
            return False, f"非法 dload_mode: {mode}"
        out, err = self.run_adb(
            f'shell "echo {mode} > {QCOM_DLOAD_MODE_PATH}"',
            timeout=15,
        )
        cur, cur_err = self.run_adb(f"shell cat {QCOM_DLOAD_MODE_PATH}", timeout=10)
        cur_text = (cur or "").strip().lower()
        try:
            (self.cfg["work_dir"] / "evidence").mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        detail = f"set={mode} out={out!r} err={err!r} current={cur_text or cur_err}"
        ok = mode in cur_text or (not cur_err and mode == cur_text)
        # 部分机型 cat 为空但仍写入成功
        if not ok and not (err or "").strip() and not (cur_err or "").strip():
            ok = True
        return ok, detail

    def prepare_qcom_dload(self, mode: str = "mini") -> None:
        """用例开始或开机后：adb root + 写入 dload_mode（每次都写，不依赖「已设置」缓存）。"""
        if self.detect_chip_platform() != "qcom":
            return
        mode = (mode or "mini").strip().lower()
        if mode not in ("mini", "full", "both"):
            mode = "mini"
        self._qcom_dload_desired = mode
        self.ensure_root()
        self._emit(f"高通：设置 dload_mode={mode}（开机后需重设）…")
        ok, detail = self.set_qcom_dload_mode(mode)
        self._emit(f"高通 dload_mode={mode} → {'ok' if ok else 'warn'}: {detail}")

    def after_boot(self, *, dload_mode: Optional[str] = None) -> None:
        """设备重新上线后调用：adb root；高通再按期望重写 dload_mode。"""
        self.ensure_root()
        if self.detect_chip_platform() != "qcom":
            return
        mode = (dload_mode or self._qcom_dload_desired or "mini").strip().lower()
        if mode not in ("mini", "full", "both"):
            mode = "mini"
        self.prepare_qcom_dload(mode)

    def early_crash_after_adb_online(
        self,
        label: str = "early-sysrq",
        wait_offline_sec: int = 45,
    ) -> Tuple[bool, str]:
        """不开机场景：``wait-for-device`` 后尽快 root(+高通重写 dload) 并 sysrq。

        刻意跳过 ensure_root 长 sleep、平台诊断与多次重试，争取在进桌面前触发 dump。
        对齐手工：``adb wait-for-device`` → ``adb root`` → ``echo c > /proc/sysrq-trigger``。
        """
        self._emit(f"{label}: 早触发 — adb root（不等 boot_completed）…")
        self.run_adb("root", timeout=20)
        self.run_adb("wait-for-device", timeout=60)
        if self.detect_chip_platform() == "qcom":
            mode = (self._qcom_dload_desired or "mini").strip().lower()
            if mode not in ("mini", "full", "both"):
                mode = "mini"
            self._emit(f"{label}: 高通快速重设 dload_mode={mode} …")
            self.run_adb(
                f'shell "echo {mode} > {QCOM_DLOAD_MODE_PATH}"',
                timeout=8,
            )
        # 打开 sysrq 后立刻造障，不做 id/ls 诊断
        self.run_adb('shell "echo 1 > /proc/sys/kernel/sysrq"', timeout=5)
        argv = ["adb", "-s", self.serial, "shell", "echo c > /proc/sysrq-trigger"]
        self._emit(f"{label}: 立刻下发 echo c > /proc/sysrq-trigger")
        out, err = self.run_adb_argv(argv, timeout=15)
        self._emit(f"{label}: 返回 out={out[:120]!r} err={err[:120]!r}；等待掉线…")
        offline, elapsed = self._wait_device_offline(label, wait_offline_sec)
        if offline:
            return True, f"早触发 sysrq 成功（约 {elapsed}s 掉线）"
        # 一次快路径回退
        self._emit(f"{label}: 未掉线，stdin→cat 再试一次…")
        try:
            proc = subprocess.Popen(
                ["adb", "-s", self.serial, "shell", "sh", "-c", "cat > /proc/sysrq-trigger"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                proc.communicate(input=b"c", timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
        except Exception as exc:
            return False, f"早触发 sysrq 失败且回退异常: {exc}"
        offline, elapsed = self._wait_device_offline(label, min(20, wait_offline_sec))
        if offline:
            return True, f"早触发 sysrq 成功（stdin-cat，约 {elapsed}s）"
        return False, f"早触发 sysrq 后 {wait_offline_sec}s 内未掉线（可能已进桌面）"

    def _find_md_kconsole(self, root: Path) -> Optional[Path]:
        if not root.exists():
            return None
        exact = list(root.rglob(QCOM_KCONSOLE_NAME))
        if exact:
            return exact[0]
        # 大小写不敏感兜底
        for p in root.rglob("*"):
            if p.is_file() and p.name.lower() == QCOM_KCONSOLE_NAME.lower():
                return p
        return None

    def _text_has_sysrq_keyword(self, text: str) -> bool:
        t = (text or "").lower()
        if "sysrq triggered crash" in t or "sysrq: trigger a crash" in t:
            return True
        return "sysrq" in t and any(k in t for k in ("trigger", "panic", "sysrq_handle_crash"))

    def pull_qcom_sahara_dump(self, out_dir: Path) -> Tuple[bool, str]:
        """用内置 qcom_dump/QSaharaServer.exe 导出 fulldump（设备停在 XBL / 90EE）。

        COM 检测与调用逻辑见 qcom_dump/sahara_pull.py（对齐原 bat 参数）。
        """
        qs = self._resolve_tool("qcom_dump/QSaharaServer.exe", "QSaharaServer.exe")
        if not qs:
            return False, (
                "未找到 qcom_dump/QSaharaServer.exe；"
                "请将工具放到 tools/stability_checker/qcom_dump/"
            )
        out_dir.mkdir(parents=True, exist_ok=True)
        pull_mod = TOOL_ROOT / "qcom_dump" / "sahara_pull.py"
        if not pull_mod.is_file():
            return False, f"未找到 {pull_mod}"
        spec = importlib.util.spec_from_file_location("qcom_sahara_pull", pull_mod)
        if spec is None or spec.loader is None:
            return False, f"无法加载 {pull_mod}"
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.pull_sahara_dump(
            out_dir,
            qs_exe=qs,
            timeout_sec=CASE24_SAHARA_TIMEOUT_SEC,
            on_log=lambda m: self._emit(f"case24: {m}"),
        )

    def check_device(self) -> bool:
        stdout, _ = self.run_adb("get-state", timeout=15)
        return stdout.strip() == "device"

    def _wait_device_offline(self, label: str, wait_sec: int) -> Tuple[bool, int]:
        wait_sec = max(5, int(wait_sec))
        for elapsed in range(1, wait_sec + 1):
            time.sleep(1)
            if not self.check_device():
                return True, elapsed
            if elapsed % 5 == 0:
                self._emit(f"{label}: 仍在等待掉线（已等 {elapsed}s / {wait_sec}s）…")
        return False, wait_sec

    def trigger_sysrq_crash(
        self,
        label: str = "sysrq",
        wait_offline_sec: int = 45,
    ) -> Tuple[bool, str]:
        """触发 kernel sysrq crash：与手动一致 ``adb shell "echo c > /proc/sysrq-trigger"``。

        设备通常需数秒才掉线；以掉线为成功判据。
        """
        self.ensure_root()
        uid, _ = self.run_adb("shell id", timeout=10)
        sysrq_mask, sysrq_err = self.run_adb("shell cat /proc/sys/kernel/sysrq", timeout=10)
        trigger_meta, _ = self.run_adb("shell ls -l /proc/sysrq-trigger", timeout=10)
        self._emit(
            f"{label}: 诊断 id={uid or '?'} sysrq={sysrq_mask or sysrq_err or '?'} "
            f"trigger={trigger_meta or '?'}"
        )
        # 尽力打开（部分机型 mask=0 仍可 crash，不作为硬门禁）
        self.run_adb('shell "echo 1 > /proc/sys/kernel/sysrq"', timeout=10)

        before = self.check_device()
        # 候选调用方式：与手动 adb shell "…" 对齐，避免多余 sh -c
        attempts: List[Tuple[str, List[str]]] = [
            (
                'adb shell "echo c > /proc/sysrq-trigger"',
                ["adb", "-s", self.serial, "shell", "echo c > /proc/sysrq-trigger"],
            ),
            (
                "adb shell printf c >/proc/sysrq-trigger (via sh -c)",
                ["adb", "-s", self.serial, "shell", "sh", "-c", "printf c > /proc/sysrq-trigger"],
            ),
        ]

        last_detail = ""
        for idx, (desc, argv) in enumerate(attempts):
            if not self.check_device():
                self._emit(f"{label}: 设备已掉线（上一命令生效）")
                return True, "设备已掉线，sysrq crash 已触发"
            wait_this = wait_offline_sec if idx == 0 else min(20, wait_offline_sec)
            self._emit(f"{label}: 下发 {desc}")
            self._emit(f"{label}: argv={argv!r}")
            out, err = self.run_adb_argv(argv, timeout=20)
            last_detail = f"out={out[:160]!r} err={err[:160]!r}"
            self._emit(f"{label}: 返回 {last_detail}；等待掉线（最多 {wait_this}s）…")
            offline, elapsed = self._wait_device_offline(label, wait_this)
            if offline:
                self._emit(f"{label}: 设备已掉线（约 {elapsed}s），sysrq 已生效")
                return True, f"设备已掉线，sysrq crash 已触发（约 {elapsed}s，{desc}）"

        # 最后一试：主机侧把 'c' 通过 stdin 喂给设备 cat（不依赖设备 echo）
        if self.check_device():
            self._emit(f"{label}: 回退 stdin→cat >/proc/sysrq-trigger")
            try:
                proc = subprocess.Popen(
                    ["adb", "-s", self.serial, "shell", "sh", "-c", "cat > /proc/sysrq-trigger"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                try:
                    out_b, err_b = proc.communicate(input=b"c", timeout=20)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    out_b, err_b = proc.communicate()
                last_detail = (
                    f"stdin-cat out={(out_b or b'')[:120]!r} err={(err_b or b'')[:120]!r}"
                )
                self._emit(f"{label}: {last_detail}；等待掉线…")
                offline, elapsed = self._wait_device_offline(label, wait_offline_sec)
                if offline:
                    return True, f"设备已掉线，sysrq crash 已触发（stdin-cat，约 {elapsed}s）"
            except Exception as exc:
                last_detail = f"stdin-cat error={exc}"

        if before and self.check_device():
            return False, (
                f"已按手动同等方式下发 echo c >/proc/sysrq-trigger，但设备在 "
                f"{wait_offline_sec}s 内未掉线。{last_detail}"
            )
        return True, "设备状态已变化（可能正在重启）"

    def _evidence(self, case_id: int) -> Path:
        d = self.cfg["work_dir"] / "evidence" / str(case_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _resolve_tool(self, *candidates: str) -> Optional[Path]:
        roots: List[Path] = []
        cfg_root = self.cfg.get("tools_root")
        if cfg_root:
            roots.append(Path(cfg_root))
        if TOOL_ROOT not in roots:
            roots.append(TOOL_ROOT)
        for root in roots:
            if not root.is_dir():
                continue
            for rel in candidates:
                p = root / rel
                if p.is_file():
                    return p
        return None

    def _require_code_dir(self) -> Tuple[Optional[Path], str]:
        code_dir = self.cfg.get("code_dir")
        if not code_dir:
            return None, "未配置 code_dir（stability.config.json 或 TAHP_STABILITY_CODE_DIR）"
        code_dir = Path(code_dir)
        if not code_dir.is_dir():
            return None, f"code_dir 不存在或不可访问: {code_dir}"
        return code_dir, ""

    def _pending_need_code_dir(self, detail: str = "") -> Tuple[str, str]:
        """缺源码路径且本项必须代码验证 → 待确认（报告补录，不阻断后续自动项）。"""
        base = "未配置 code_dir，无法完成源码侧验证；请在测试报告中补录结果"
        return "Pending", f"{detail}；{base}" if detail else base

    def _require_tools(self, *names: str) -> Tuple[Dict[str, Path], str]:
        found: Dict[str, Path] = {}
        mapping = {
            "dispatcher": ("SpOfflineDebugSuite/Dispatcher.exe", "Dispatcher.exe"),
            "aee_extract": ("aee_extract.exe",),
            "tne_parser": ("tne_parser.py",),
            "tran_pdfs": ("tran_pdfs.py",),
            "tdsm": ("tdsm.py",),
        }
        for name in names:
            path = self._resolve_tool(*mapping.get(name, (name,)))
            if not path:
                return {}, (
                    f"未找到内置工具 {name}（期望位于 tools/stability_checker/"
                    f"{mapping.get(name, (name,))[0]}）"
                )
            found[name] = path
        return found, ""

    # ── 单项检查（对齐飞书 A17 / MTK 稳定性 checklist）──────────

    _CODE_SKIP_DIRS = {
        ".git",
        ".repo",
        ".ccache",
        "__pycache__",
        "node_modules",
        ".gradle",
        "prebuilts",
        "out",
        "out_vnd",
        "OUT",
    }

    def _iter_code_files(
        self,
        code_dir: Path,
        *,
        file_names: Optional[Tuple[str, ...]] = None,
        name_suffix: Optional[str] = None,
        path_substr: Optional[str] = None,
        max_files: int = 40,
        max_visit: int = 12000,
    ) -> List[Path]:
        """在 code_dir 内做有界查找，避免整仓 rglob 卡死。"""
        found: List[str] = []
        hits: List[Path] = []
        visited = 0
        self._emit(f"源码扫描: {code_dir}（最多访问 {max_visit} 个目录项）…")
        for root, dirs, files in os.walk(code_dir):
            dirs[:] = [d for d in dirs if d not in self._CODE_SKIP_DIRS and not d.startswith(".")]
            visited += 1
            if visited % 2000 == 0:
                self._emit(f"源码扫描进行中…已访问 {visited} 项，命中 {len(hits)}")
            if visited > max_visit:
                self._emit(f"源码扫描达到上限 {max_visit}，停止继续深入")
                break
            for name in files:
                matched = False
                if file_names and name in file_names:
                    matched = True
                if name_suffix and name.endswith(name_suffix):
                    matched = True
                if not matched:
                    continue
                fp = Path(root) / name
                if path_substr and path_substr not in fp.as_posix().replace("\\", "/"):
                    continue
                hits.append(fp)
                if len(hits) >= max_files:
                    return hits
        return hits

    def _read_text_limited(self, path: Path, max_bytes: int = 2_000_000) -> str:
        try:
            if path.stat().st_size > max_bytes:
                return ""
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def check_log_config(self) -> Tuple[str, str]:
        """A17#1 log配置：只校验 cmdline 含 log_buf_len=2M。"""
        self.ensure_root()
        self._emit("case1: 检查 /proc/cmdline log_buf_len=2M …")
        cmdline, cmd_err = self.run_adb('shell "cat /proc/cmdline"', timeout=20)
        if re.search(r"log_buf_len=2[mM]\b", cmdline or ""):
            return "Pass", "cmdline 含 log_buf_len=2M"
        return "Fail", f"cmdline 无 log_buf_len=2M ({cmd_err or cmdline or 'empty'})"

    def check_earlycon(self) -> Tuple[str, str]:
        work = self.cfg["work_dir"] / "mobilelog"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        self.ensure_root()
        code, out = self.run_host(
            ["adb", "-s", self.serial, "pull", "/data/debuglogger/mobilelog", str(work)],
            cwd=self.cfg["work_dir"],
            timeout=600,
        )
        self._evidence(3).joinpath("adb_pull.txt").write_text(f"exit={code}\n{out}\n", encoding="utf-8")
        if code != 0 and not any(work.rglob("*")):
            return "Fail", "pull mobilelog 失败"
        ok, msg = search_earlycon_in_tree(work)
        return ("Pass" if ok else "Fail"), msg

    def check_manual_placeholder(self) -> Tuple[str, str]:
        return "NA", "本项为人工按键/串口项，请按用例步骤操作后确认"

    def check_user_uart_default_off(self) -> Tuple[str, str]:
        """A17#5：pl_lk 中 disable_uart 关闭证据。"""
        self.ensure_root()
        out, err = self.run_adb('shell "cat /proc/pl_lk"', timeout=30)
        text = out or ""
        if not text:
            return "Fail", f"读取 /proc/pl_lk 失败: {err or '(empty)'}"
        if re.search(r"disable_uart\s*=\s*1\b", text) or "mtk_printk_ctrl.disable_uart=1" in text:
            return "Pass", "pl_lk 含 disable_uart=1"
        if "disable_uart" in text:
            snippet = " | ".join(ln.strip() for ln in text.splitlines() if "disable_uart" in ln)[:240]
            return "Fail", f"见到 disable_uart 但未确认为关闭: {snippet}"
        return "Fail", "pl_lk 中未找到 mtk_printk_ctrl.disable_uart（请用 user 版本+mobilelog 复验）"

    def check_download_mode(self) -> Tuple[str, str]:
        self.ensure_root()
        out, err = self.run_adb('shell "cat /proc/pl_lk"', timeout=30)
        text = out or ""
        hit = [ln for ln in text.splitlines() if "rst from" in ln.lower()]
        snippet = " | ".join(hit[:3]) if hit else (text[:200] or err or "(empty)")
        if re.search(r"\[RGU\]\s*rst from:\s*DA", text, re.IGNORECASE):
            return "Pass", snippet
        if not text and err:
            return "Fail", f"读取 /proc/pl_lk 失败: {err}"
        return "Fail", f"未找到 [RGU] rst from: DA；相关输出: {snippet}"

    def _sleep_with_progress(self, total_sec: int, label: str, tick_sec: int = 30) -> None:
        """长等待时定期刷新子步骤，避免 UI 看起来像卡死。"""
        total_sec = max(0, int(total_sec))
        if total_sec <= 0:
            return
        tick = max(5, int(tick_sec))
        deadline = time.time() + total_sec
        while True:
            remaining = int(round(deadline - time.time()))
            if remaining <= 0:
                break
            self._emit(f"{label}（剩余约 {remaining}s / 共 {total_sec}s）…")
            time.sleep(min(tick, remaining))

    def check_db_sysrq(self) -> Tuple[str, str]:
        """A17#8：sysrq → fulldump(≥10min) → wait-for-device → 开机后再等 5min → pull aee_exp。"""
        tools, err = self._require_tools("aee_extract", "dispatcher")
        if err:
            tools, err2 = self._require_tools("dispatcher")
            if err2:
                return "NA", err
        work = self.cfg["work_dir"] / "case8"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(8)
        self.ensure_root()
        self._emit("case8: 清理 aee_exp/TNE 后触发 sysrq …")
        self.run_adb('shell "rm -rf /data/vendor/aee_exp/*"', timeout=30)
        self.run_adb('shell "rm -rf /data/TNE/*"', timeout=30)
        ok_sysrq, sysrq_msg = self.trigger_sysrq_crash("case8")
        if not ok_sysrq:
            return "Fail", sysrq_msg
        self._sleep_with_progress(
            CASE8_FULLDUMP_WAIT_SEC,
            "case8: 等待 fulldump 完成（sysrq 后）",
            tick_sec=30,
        )
        self._emit(f"case8: adb wait-for-device（超时 {CASE8_WAIT_DEVICE_TIMEOUT_SEC}s）…")
        wcode, wout = self.run_host(
            ["adb", "-s", self.serial, "wait-for-device"],
            timeout=CASE8_WAIT_DEVICE_TIMEOUT_SEC,
        )
        (ev / "wait_for_device.txt").write_text(f"exit={wcode}\n{wout}\n", encoding="utf-8")
        if wcode != 0:
            return "Fail", f"wait-for-device 失败或超时: {wout.strip() or wcode}"
        self.after_boot()
        self._sleep_with_progress(
            CASE8_POST_BOOT_WAIT_SEC,
            "case8: 开机后等待 aee_exp 落盘",
            tick_sec=30,
        )
        aee_dest = work / "aee_exp"
        if aee_dest.exists():
            shutil.rmtree(aee_dest, ignore_errors=True)
        code, out = self.run_host(
            ["adb", "-s", self.serial, "pull", "/data/vendor/aee_exp", str(aee_dest)],
            cwd=work,
            timeout=600,
        )
        (ev / "pull_aee.txt").write_text(f"exit={code}\n{out}\n", encoding="utf-8")
        dbgs = sorted(aee_dest.rglob("*.dbg")) if aee_dest.is_dir() else []
        if dbgs and "aee_extract" in tools:
            fatal = [p for p in dbgs if "db.fatal" in p.as_posix()]
            dbg = fatal[0] if fatal else dbgs[0]
            (ev / "dbg_used.txt").write_text(str(dbg), encoding="utf-8")
            acode, aout = self.run_host([str(tools["aee_extract"]), str(dbg)], cwd=work, timeout=600)
            (ev / "aee_extract.out").write_text(f"exit={acode}\n{aout}\n", encoding="utf-8")
            dec_dir = dbg.parent / f"{dbg.name}.DEC"
            if not dec_dir.is_dir():
                found = [p for p in work.rglob("*.dbg.DEC") if p.is_dir()]
                dec_dir = found[0] if found else None
            if dec_dir and dec_dir.is_dir():
                dcode, dout = self.run_host(
                    [str(tools["dispatcher"]), "-ext", "51", str(dec_dir)],
                    cwd=work,
                    timeout=600,
                )
                (ev / "dispatcher.out").write_text(f"exit={dcode}\n{dout}\n", encoding="utf-8")
                ok, msg = check_dispatcher_sysrq(dec_dir, dout)
                return ("Pass" if ok else "Fail"), msg
        temp_db = work / "temp_db"
        if temp_db.exists():
            shutil.rmtree(temp_db, ignore_errors=True)
        pcode, pout = self.run_host(
            ["adb", "-s", self.serial, "pull", "/data/TNE/temp_db", str(temp_db)],
            cwd=work,
            timeout=300,
        )
        (ev / "pull_temp_db.txt").write_text(f"exit={pcode}\n{pout}\n", encoding="utf-8")
        if not temp_db.exists():
            return "Fail", "aee_exp 无 .dbg 且未 pull 到 /data/TNE/temp_db"
        dcode, dout = self.run_host(
            [str(tools["dispatcher"]), "-ext", "51", str(temp_db)],
            cwd=work,
            timeout=600,
        )
        (ev / "dispatcher.out").write_text(f"exit={dcode}\n{dout}\n", encoding="utf-8")
        analysis = find_analysis_dir(work, temp_db)
        if analysis is None:
            return "Fail", "Dispatcher 后未找到分析报告 / SYS_KERNEL_LOG"
        ok, msg = check_dispatcher_sysrq(analysis, dout)
        return ("Pass" if ok else "Fail"), msg

    def check_mtprintk_uart_off(self) -> Tuple[str, str]:
        """A17#9 root 开机完成停止串口 log。"""
        self.ensure_root()
        out, err = self.run_adb('shell "cat /proc/mtprintk"', timeout=15)
        text = out or ""
        if re.search(r"printk uart enable:\s*0\b", text, re.I):
            return "Pass", text.strip()[:200] or "printk uart enable: 0"
        if not text:
            return "Fail", f"读取 /proc/mtprintk 失败: {err or '(empty)'}"
        return "Fail", f"期望 printk uart enable: 0，实际: {text.strip()[:200]}"

    def check_rt_runtime_share_off(self) -> Tuple[str, str]:
        """A17#10。"""
        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)
        self._emit("case10: 查找 kernel/sched/features.h …")
        candidates: List[Path] = []
        for ker in sorted(code_dir.glob("kernel-*")):
            p = ker / "kernel" / "sched" / "features.h"
            if p.is_file():
                candidates.append(p)
        direct = code_dir / "kernel" / "sched" / "features.h"
        if direct.is_file():
            candidates.append(direct)
        if not candidates:
            candidates = self._iter_code_files(
                code_dir,
                file_names=("features.h",),
                path_substr="kernel/sched",
                max_files=10,
                max_visit=8000,
            )
        for p in candidates:
            text = self._read_text_limited(p)
            if re.search(r"SCHED_FEAT\s*\(\s*RT_RUNTIME_SHARE\s*,\s*false\s*\)", text):
                return "Pass", f"命中 {p.relative_to(code_dir)}"
            if "RT_RUNTIME_SHARE" in text and re.search(
                r"SCHED_FEAT\s*\(\s*RT_RUNTIME_SHARE\s*,\s*true\s*\)", text
            ):
                return "Fail", f"仍为 true: {p.relative_to(code_dir)}"
        return "Fail", "未在 kernel/sched/features.h 找到 SCHED_FEAT(RT_RUNTIME_SHARE, false)"

    def _remote_path_exists(self, remote_path: str) -> bool:
        """检查设备上路径是否存在（文件或目录）。"""
        # 用 test -e，避免 ls 在部分机型对目录/权限输出不一致
        out, err = self.run_adb(
            f'shell "if [ -e {remote_path} ]; then echo EXISTS; else echo MISSING; fi"',
            timeout=15,
        )
        text = f"{out}\n{err}"
        if "EXISTS" in text:
            return True
        if "MISSING" in text:
            return False
        # 兜底：ls 成功且非 No such file
        ls_out, ls_err = self.run_adb(f'shell "ls -ld {remote_path}"', timeout=15)
        blob = f"{ls_out}\n{ls_err}".lower()
        return bool(ls_out.strip()) and "no such file" not in blob

    def _remote_temp_db_reusable(self, remote_path: str) -> Tuple[bool, str]:
        """temp_db 可复用：路径存在且有实质内容（非空文件，或目录下至少有一个文件）。"""
        out, err = self.run_adb(
            "shell "
            f'"'
            f"p={remote_path}; "
            f"if [ ! -e \"$p\" ]; then echo STATUS=MISSING; "
            f"elif [ -f \"$p\" ]; then "
            f"  sz=$(wc -c < \"$p\" 2>/dev/null || echo 0); "
            f"  echo STATUS=FILE; echo SIZE=$sz; "
            f"elif [ -d \"$p\" ]; then "
            f"  echo STATUS=DIR; "
            f"  find \"$p\" -type f 2>/dev/null | head -20; "
            f"else echo STATUS=OTHER; fi"
            f'"',
            timeout=30,
        )
        text = (out or "").strip()
        detail = text or (err or "").strip() or "(empty)"
        if "STATUS=MISSING" in text or "STATUS=OTHER" in text:
            return False, detail
        if "STATUS=FILE" in text:
            m = re.search(r"SIZE=(\d+)", text)
            size = int(m.group(1)) if m else 0
            return (size > 0, detail)
        if "STATUS=DIR" in text:
            # 去掉 STATUS 行后仍有路径行 → 目录下有文件
            lines = [
                ln.strip()
                for ln in text.splitlines()
                if ln.strip() and not ln.strip().startswith("STATUS=")
            ]
            return (len(lines) > 0, detail)
        # 解析失败时保守：不可复用
        return False, detail

    def check_tranpdb(self) -> Tuple[str, str]:
        """A17#11 / Qcom：解析 expdb/tranpdb。

        MTK：Dispatcher 解析 temp_db。
        高通：前序步骤相同（mini dump + sysrq），导出后直接检查 md_KCONSOLE.BIN 关键字，不再走 Dispatcher。
        """
        if self.detect_chip_platform() == "qcom":
            return self.check_tranpdb_qcom()
        return self.check_tranpdb_mtk()

    def check_tranpdb_mtk(self) -> Tuple[str, str]:
        """MTK：解析 expdb / temp_db。

        优先复用前序项已产生的 /data/TNE/temp_db（须目录下有文件或非空文件）；
        否则先 mrdump_tool output-set none（关 fulldump）→ sysrq →
        wait-for-device（默认 180s）→ 开机后再等约 1min → pull → Dispatcher。
        """
        tools, err = self._require_tools("dispatcher")
        if err:
            return "NA", err
        work = self.cfg["work_dir"] / "case11"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(11)
        self.ensure_root()
        # 关闭 fulldump，避免 sysrq 走完整 dump 过久/占满；与手工 checklist 一致
        self._emit("case11: mrdump_tool output-set none（关闭 fulldump）…")
        md_out, md_err = self.run_adb("shell mrdump_tool output-set none", timeout=20)
        (ev / "mrdump_output_set_none.txt").write_text(
            f"out={md_out}\nerr={md_err}\n",
            encoding="utf-8",
        )

        remote_temp_db = "/data/TNE/temp_db"
        self._emit(f"case11: 检查 {remote_temp_db} 是否有可复用内容 …")
        reusable, probe = self._remote_temp_db_reusable(remote_temp_db)
        (ev / "temp_db_probe.txt").write_text(
            f"path={remote_temp_db}\nreusable={reusable}\n{probe}\n",
            encoding="utf-8",
        )

        if reusable:
            self._emit("case11: temp_db 已有文件，复用前序 dump，跳过 sysrq")
        else:
            self._emit("case11: temp_db 不存在或为空，清理后触发 sysrq …")
            self.run_adb('shell "rm -rf /data/vendor/aee_exp/*"', timeout=30)
            self.run_adb('shell "rm -rf /data/TNE/*"', timeout=30)
            ok_sysrq, sysrq_msg = self.trigger_sysrq_crash("case11")
            if not ok_sysrq:
                return "Fail", sysrq_msg
            # 已关 fulldump：无需等 10min+，仅等正常重启
            self._emit(
                f"case11: adb wait-for-device（超时 {CASE11_WAIT_DEVICE_TIMEOUT_SEC}s，无 fulldump）…"
            )
            wcode, wout = self.run_host(
                ["adb", "-s", self.serial, "wait-for-device"],
                timeout=CASE11_WAIT_DEVICE_TIMEOUT_SEC,
            )
            (ev / "wait_for_device.txt").write_text(f"exit={wcode}\n{wout}\n", encoding="utf-8")
            if wcode != 0:
                return "Fail", f"wait-for-device 失败或超时: {wout.strip() or wcode}"
            self.after_boot()
            self._sleep_with_progress(
                CASE11_POST_BOOT_WAIT_SEC,
                "case11: 开机后等待 temp_db 落盘",
                tick_sec=15,
            )

        temp_db = work / "temp_db"
        if temp_db.exists():
            shutil.rmtree(temp_db, ignore_errors=True)
            if temp_db.exists():
                try:
                    temp_db.unlink()
                except OSError:
                    pass
        self._emit(f"case11: pull {remote_temp_db} …")
        code, pull_out = self.run_host(
            ["adb", "-s", self.serial, "pull", remote_temp_db, str(temp_db)],
            cwd=work,
            timeout=300,
        )
        (ev / "adb_pull_temp_db.txt").write_text(f"exit={code}\n{pull_out}\n", encoding="utf-8")
        if not temp_db.exists():
            return "Fail", "未 pull 到 /data/TNE/temp_db"
        # 拉下来后仍校验本地有实质内容
        local_ok = (
            (temp_db.is_file() and temp_db.stat().st_size > 0)
            or (temp_db.is_dir() and any(p.is_file() for p in temp_db.rglob("*")))
        )
        if not local_ok:
            return "Fail", "pull 到的 temp_db 为空（无文件）"
        disp = tools["dispatcher"]
        self._emit("case11: Dispatcher 分析 temp_db …")
        dcode, dout = self.run_host([str(disp), "-ext", "51", str(temp_db)], cwd=work, timeout=600)
        (ev / "dispatcher.out").write_text(f"exit={dcode}\n{dout}\n", encoding="utf-8")
        analysis = find_analysis_dir(work, temp_db)
        if analysis is None:
            return "Fail", "Dispatcher 后未找到分析报告 / SYS_KERNEL_LOG"
        ok, msg = check_dispatcher_sysrq(analysis, dout)
        reused = "复用已有 temp_db" if reusable else "sysrq 新生成 temp_db"
        return ("Pass" if ok else "Fail"), f"{msg}（{reused}）"

    def check_tranpdb_qcom(self) -> Tuple[str, str]:
        """高通 tranpdb：sysrq 后 pull minidump，检查 md_KCONSOLE.BIN 关键字（不走 Dispatcher）。"""
        work = self.cfg["work_dir"] / "case11_qcom"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(11)
        self.ensure_root()
        self.prepare_qcom_dload("mini")
        ok_mode, mode_detail = True, "via prepare_qcom_dload"
        (ev / "dload_mode.txt").write_text(f"ok={ok_mode}\n{mode_detail}\n", encoding="utf-8")

        remote = QCOM_MINIDUMP_DIR
        self._emit(f"case11(qcom): 检查已有 {remote} …")
        ls_out, _ = self.run_adb(f'shell "ls -la {remote}"', timeout=20)
        (ev / "minidump_ls_before.txt").write_text(ls_out or "(empty)\n", encoding="utf-8")

        # 若目录已有 md_KCONSOLE.BIN 则可复用；否则造障
        probe_dir = work / "probe"
        if probe_dir.exists():
            shutil.rmtree(probe_dir, ignore_errors=True)
        reusable = False
        if "No such file" not in (ls_out or "") and (ls_out or "").strip():
            code, pout = self.run_host(
                ["adb", "-s", self.serial, "pull", remote, str(probe_dir)],
                cwd=work,
                timeout=300,
            )
            (ev / "adb_pull_probe.txt").write_text(f"exit={code}\n{pout}\n", encoding="utf-8")
            if self._find_md_kconsole(probe_dir):
                reusable = True
                self._emit("case11(qcom): 复用已有 minidump 中的 md_KCONSOLE.BIN")

        if not reusable:
            self._emit("case11(qcom): 清理后触发 sysrq …")
            self.run_adb(f'shell "rm -rf {remote}/*"', timeout=30)
            ok_sysrq, sysrq_msg = self.trigger_sysrq_crash("case11-qcom")
            if not ok_sysrq:
                return "Fail", sysrq_msg
            self._emit(
                f"case11(qcom): wait-for-device（超时 {CASE11_WAIT_DEVICE_TIMEOUT_SEC}s）…"
            )
            wcode, wout = self.run_host(
                ["adb", "-s", self.serial, "wait-for-device"],
                timeout=CASE11_WAIT_DEVICE_TIMEOUT_SEC,
            )
            (ev / "wait_for_device.txt").write_text(f"exit={wcode}\n{wout}\n", encoding="utf-8")
            if wcode != 0:
                return "Fail", f"wait-for-device 失败或超时: {wout.strip() or wcode}"
            self.after_boot(dload_mode="mini")
            self._sleep_with_progress(
                CASE11_POST_BOOT_WAIT_SEC,
                "case11(qcom): 开机后等待 minidump 落盘",
                tick_sec=15,
            )

        local = work / "minidump"
        if local.exists():
            shutil.rmtree(local, ignore_errors=True)
        self._emit(f"case11(qcom): pull {remote} …")
        code, pull_out = self.run_host(
            ["adb", "-s", self.serial, "pull", remote, str(local)],
            cwd=work,
            timeout=300,
        )
        (ev / "adb_pull_minidump.txt").write_text(f"exit={code}\n{pull_out}\n", encoding="utf-8")
        if not local.exists():
            return "Fail", f"未 pull 到 {remote}"
        kcon = self._find_md_kconsole(local)
        if not kcon:
            return "Fail", f"导出的 minidump 中未找到 {QCOM_KCONSOLE_NAME}"
        try:
            raw = kcon.read_bytes()
            text = raw.decode("utf-8", errors="ignore")
        except OSError as exc:
            return "Fail", f"读取 {kcon.name} 失败: {exc}"
        (ev / "md_KCONSOLE_snippet.txt").write_text(text[:4000], encoding="utf-8", errors="replace")
        if self._text_has_sysrq_keyword(text):
            reused = "复用已有 minidump" if reusable else "sysrq 新生成 minidump"
            return "Pass", f"{QCOM_KCONSOLE_NAME} 含 sysrq 关键字（{reused}）"
        return "Fail", f"{QCOM_KCONSOLE_NAME} 未命中 sysrq 相关关键字"

    def _kernel_roots(self, code_dir: Path) -> List[Path]:
        """返回 code_dir 下的 kernel / kernel-* 目录（以及 code_dir 本身若已是 kernel 树）。"""
        roots: List[Path] = []
        seen: set[str] = set()

        def add(p: Path) -> None:
            try:
                key = str(p.resolve())
            except OSError:
                key = str(p)
            if key in seen or not p.is_dir():
                return
            seen.add(key)
            roots.append(p)

        # Android 源码根：kernel、kernel-4.19、kernel-5.10 …
        for child in sorted(code_dir.iterdir()) if code_dir.is_dir() else []:
            name = child.name
            if name == "kernel" or name.startswith("kernel-"):
                add(child)
        # code_dir 本身就是 kernel 树（用户直接配到 kernel 目录）
        if (code_dir / "drivers").is_dir() and (
            code_dir.name == "kernel" or code_dir.name.startswith("kernel-")
        ):
            add(code_dir)
        return roots

    def check_sodi_removed(self) -> Tuple[str, str]:
        """A17#12 SODI 移除：仅在 kernel / kernel-* 目录下查找 mt_idle.c。"""
        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)

        kernel_roots = self._kernel_roots(code_dir)
        if not kernel_roots:
            return "NA", f"code_dir 下未找到 kernel/kernel-* 目录: {code_dir}"

        rel_idle = Path("drivers/misc/mediatek/base/power/spm_v1/mt_idle.c")
        candidates: List[Path] = []
        for ker in kernel_roots:
            p = ker / rel_idle
            if p.is_file():
                candidates.append(p)

        if not candidates:
            self._emit(f"case12: 在 {len(kernel_roots)} 个 kernel 目录下搜索 mt_idle.c …")
            for ker in kernel_roots:
                found = self._iter_code_files(
                    ker,
                    file_names=("mt_idle.c",),
                    path_substr="spm",
                    max_files=5,
                    max_visit=6000,
                )
                candidates.extend(found)
                if candidates:
                    break

        if not candidates:
            return "NA", "kernel 目录下未找到 mt_idle.c（本平台不支持 SODI 项）"

        fp = candidates[0]
        text = fp.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"idle_switch\s*\[\s*NR_TYPES\s*\]\s*=\s*\{(?P<body>.*?)\};", text, re.S)
        if not m:
            return "Fail", f"未解析到 idle_switch 数组: {fp}"
        body = m.group("body")
        so_ok = bool(re.search(r"\b0\s*,\s*/\*\s*soidle", body, re.I))
        sl_ok = bool(re.search(r"\b0\s*,\s*/\*\s*slidle", body, re.I))
        try:
            rel = fp.relative_to(code_dir)
        except ValueError:
            rel = fp
        if so_ok and sl_ok:
            return "Pass", f"soidle/slidle 为 0 @ {rel}"
        return "Fail", f"soidle/slidle 未确认为 0，请人工核对 {rel}"

    def check_tdfs_stucklogo(self) -> Tuple[str, str]:
        """不开机 log_store[TDFS]：adb 一上线就 sysrq，不等进桌面。

        MTK / 高通共用早触发路径；高通仅在 root 后极速重写 dload_mode。
        解析产物：MTK 查 last_kmsg；高通查 xbl.bin + kernel.bin。
        """
        tools, err = self._require_tools("tran_pdfs")
        if err:
            return "NA", err
        work = self.cfg["work_dir"] / "case13"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(13)
        chip = self.detect_chip_platform()
        self.ensure_root()
        # case11 可能已 output-set none；本项需要 fulldump，先恢复 internal-storage（MTK）
        if chip != "qcom":
            self._emit("case13: mrdump_tool output-set internal-storage（打开 fulldump）…")
            md_out, md_err = self.run_adb(
                "shell mrdump_tool output-set internal-storage",
                timeout=20,
            )
            (ev / "mrdump_output_set_internal.txt").write_text(
                f"out={md_out}\nerr={md_err}\n",
                encoding="utf-8",
            )
        ls_out, _ = self.run_adb('shell "ls -l /dev/block/by-name/tdfs"', timeout=15)
        if "No such file" in (ls_out or "") or "No such" in (ls_out or ""):
            return "Fail", "不存在 /dev/block/by-name/tdfs，请存储同事加入分区"
        self._emit(
            "case13: reboot 后多次「wait-for-device → 立刻 root(+dload) → sysrq」"
            "（赶在进桌面前）…"
        )
        self.run_adb("reboot", timeout=30)
        for i in range(3):
            self.run_adb("wait-for-device", timeout=180)
            ok_sysrq, sysrq_msg = self.early_crash_after_adb_online(f"case13#{i + 1}")
            if not ok_sysrq:
                return "Fail", sysrq_msg
            # 已掉线则无需再 sleep；给 USB 枚举一点余量即可
            time.sleep(2)
        self.run_adb("wait-for-device", timeout=180)
        # 最终 pull 阶段需要稳定 root（可等开机完成）
        self.after_boot()
        time.sleep(60)
        tdfs_img = work / "tdfs"
        code, out = self.run_host(
            ["adb", "-s", self.serial, "pull", "/dev/block/by-name/tdfs", str(tdfs_img)],
            cwd=work,
            timeout=300,
        )
        (ev / "adb_pull_tdfs.txt").write_text(f"exit={code}\n{out}\n", encoding="utf-8")
        if not tdfs_img.is_file():
            return "Fail", "pull tdfs 失败"
        parse_plat = "auto"
        pcode, pout = self.run_host(
            [
                sys.executable,
                str(tools["tran_pdfs"]),
                str(tdfs_img),
                "--platform",
                parse_plat,
            ],
            cwd=work,
            timeout=600,
        )
        (ev / "tran_pdfs.out").write_text(f"exit={pcode}\n{pout}\n", encoding="utf-8")
        dirs = sorted(work.glob("tdfs-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not dirs:
            dirs = sorted(self.cfg["work_dir"].glob("tdfs-*"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not dirs:
            return "Fail", "tran_pdfs 未生成 tdfs-* 目录"
        latest = dirs[0]
        needle = "Kernel panic - not syncing: sysrq triggered crash"

        if chip == "qcom":
            return self._judge_tdfs_qcom(latest, needle, pcode, pout)

        hits = 0
        for kmsg in latest.rglob("*"):
            if not kmsg.is_file():
                continue
            if kmsg.suffix.lower() not in (".txt", ".log", "") and "last_kmsg" not in kmsg.name.lower():
                continue
            if kmsg.stat().st_size >= 5_000_000:
                continue
            try:
                if needle in kmsg.read_text(encoding="utf-8", errors="replace"):
                    hits += 1
            except OSError:
                pass
        if hits:
            return "Pass", f"tdfs 产物中命中 sysrq last_kmsg（{hits}）"
        if pcode == 0:
            return "Fail", f"已解析 {latest.name}，未找到 sysrq last_kmsg 关键字"
        return "Fail", f"tran_pdfs 失败: {pout[:200]}"

    def _judge_tdfs_qcom(
        self,
        latest: Path,
        needle: str,
        pcode: int,
        pout: str,
    ) -> Tuple[str, str]:
        """高通：tran_pdfs 产物为 xbl.bin + kernel.bin（无 last_kmsg）。

        兼容旧脚本把 type0 写成 unknown_type_0 的情况。
        """
        def _collect(*names: str) -> List[Path]:
            out: List[Path] = []
            for name in names:
                out.extend(
                    p for p in latest.rglob(name) if p.is_file() and p.stat().st_size > 0
                )
            return out

        xbl_files = _collect("xbl.bin", "unknown_type_0")
        kernel_files = _collect("kernel.bin")
        if not xbl_files or not kernel_files:
            missing = []
            if not xbl_files:
                missing.append("xbl.bin")
            if not kernel_files:
                missing.append("kernel.bin")
            if pcode != 0:
                return "Fail", f"tran_pdfs 失败且缺 {','.join(missing)}: {pout[:200]}"
            return "Fail", f"已解析 {latest.name}，缺少高通产物: {','.join(missing)}"

        hits = 0
        for kpath in kernel_files:
            if kpath.stat().st_size >= 5_000_000:
                continue
            try:
                text = kpath.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if needle in text or "sysrq" in text.lower():
                hits += 1
        if hits:
            return (
                "Pass",
                f"tdfs 含 xbl×{len(xbl_files)} + kernel.bin×{len(kernel_files)}，"
                f"且 kernel.bin 命中 sysrq（{hits}）",
            )
        if pcode == 0:
            return (
                "Fail",
                f"已解析 {latest.name}，有 xbl/kernel 但未命中 sysrq 关键字",
            )
        return "Fail", f"tran_pdfs 失败: {pout[:200]}"
    def check_mrdump_key(self) -> Tuple[str, str]:
        """A17#14：sysfs compatible；若配置了 code_dir 则必须再结合源码判定。"""
        self.ensure_root()
        pass_keys = ("disable_mrdump_key", "mrdump_ext_rst-disable-eint")
        paths = [
            "/sys/devices/platform/soc/soc:mrdump_ext_rst/of_node/compatible",
            "/sys/firmware/devicetree/base/soc/mrdump_ext_rst/compatible",
        ]

        sysfs_hit = ""
        sysfs_fail = ""
        for remote in paths:
            out, err = self.run_adb(f'shell "cat {remote}"', timeout=15)
            text = (out or "").replace("\x00", " ").strip()
            if any(k in text for k in pass_keys):
                sysfs_hit = f"{remote} => {text[:120]}"
                break
            if text and "No such" not in text and "Permission" not in (err or ""):
                sysfs_fail = (
                    f"{remote} => {text[:160]}（期望含 disable_mrdump_key "
                    f"或 mrdump_ext_rst-disable-eint）"
                )
                break

        code_dir, code_err = self._require_code_dir()
        if code_dir:
            # 已配置源码路径：默认必须结合源码，不能仅靠 sysfs 提前 Pass
            if sysfs_fail:
                return "Fail", sysfs_fail
            out, _ = self.run_adb(
                'shell "cat /proc/pl_lk | grep mrdump_key_fdt_init"', timeout=30
            )
            rel = (
                "vendor/mediatek/proprietary/bootable/bootloader/lk2/platform/mediatek/"
                "common/aee/mrdump_key_setup.c"
            )
            fp = code_dir / rel
            if not fp.is_file():
                prefix = f"sysfs: {sysfs_hit}；" if sysfs_hit else ""
                return "Fail", f"{prefix}源码文件不存在: {fp}"
            source = fp.read_text(encoding="utf-8", errors="replace")
            ok, msg = analyze_mrdump_key(source, out)
            sysfs_part = f"sysfs {sysfs_hit}" if sysfs_hit else "sysfs 未读到关闭关键字"
            detail = f"{sysfs_part}；{msg}"
            return ("Pass" if ok else "Fail"), detail

        # 未配置 code_dir：能靠 sysfs 判定则自动出结果，否则待确认（报告补录）
        if sysfs_hit:
            return "Pass", sysfs_hit
        if sysfs_fail:
            return "Fail", sysfs_fail
        return self._pending_need_code_dir(code_err)

    def check_mt6789_xtal(self) -> Tuple[str, str]:
        plat, _ = self.run_adb("shell getprop ro.board.platform", timeout=15)
        plat = plat.strip()
        if "mt6789" not in plat.lower():
            return "NA", f"平台非 mt6789: {plat or '(empty)'}"
        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)
        rel = (
            "vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/"
            "mt6789/src/drivers/pmic_initial_setting.c"
        )
        ok, msg = code_file_contains(
            code_dir,
            rel,
            ["0x790, 0x380, 0x780, 0", "0x792, 0x7C0, 0x7C0, 0"],
        )
        return ("Pass" if ok else "Fail"), msg

    def check_ocp_tne(self) -> Tuple[str, str]:
        """A17#16：检查 OCP 产物 0xffffff15_*.tne。"""
        self.ensure_root()
        out, err = self.run_adb('shell "ls /data/TNE"', timeout=20)
        text = out or ""
        if re.search(r"0xffffff15_\S+\.tne", text, re.I):
            hits = re.findall(r"0xffffff15_\S+\.tne", text, re.I)
            return "Pass", f"命中 {', '.join(hits[:5])}"
        if "No such" in text or not text.strip():
            return "NA", "无 /data/TNE 或为空；请先按专项制造 OCP reboot 后再测"
        return "NA", f"未找到 0xffffff15_*.tne（现有: {text.strip()[:160] or err}）；请先造障"

    def check_tdsm(self) -> Tuple[str, str]:
        """A17#17 器件稳定性埋点：对齐旧 checklist case09。

        写 /proc/tran_devmsg（格式 ``{product} tdsm test {date} {seq}``）→ sysrq →
        pull 分区 → tdsm 解析；adb/tdsm 两侧均需命中 product + date。

        MTK：log_store 节点 + mrdump none + pull expdb
        高通：tran_devmsg 节点 + dload_mode=mini + pull tdfs
        """
        tools, err = self._require_tools("tdsm")
        if err:
            return "NA", err
        work = self.cfg["work_dir"] / "case17"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(17)
        chip = self.detect_chip_platform()
        product = str(self.cfg.get("product_name") or self._guess_product()).strip() or "UNKNOWN"
        date_str = datetime.now().strftime("%Y%m%d")
        seq = str(self.cfg.get("tdsm_sequence") or "no1").strip() or "no1"
        # 与旧 checklist build_tdsm_devmsg 一致（成功用例格式）
        devmsg = f"{product} tdsm test {date_str} {seq}"
        (ev / "devmsg_expected.txt").write_text(
            f"devmsg={devmsg}\nproduct={product}\ndate={date_str}\nchip={chip}\n",
            encoding="utf-8",
        )
        self.ensure_root()
        self._emit(f"case17: 写入埋点 {devmsg} 并触发 sysrq …")
        if chip == "qcom":
            self.run_adb(
                'shell "echo 1 > /sys/module/tran_devmsg/parameters/dev_id"',
                timeout=15,
            )
            self.run_adb(
                'shell "echo 1 > /sys/module/tran_devmsg/parameters/msg_type"',
                timeout=15,
            )
        else:
            self.run_adb(
                'shell "echo 1 > /sys/module/log_store/parameters/dev_id"',
                timeout=15,
            )
            self.run_adb(
                'shell "echo 1 > /sys/module/log_store/parameters/msg_type"',
                timeout=15,
            )
        # 写入 /proc/tran_devmsg（勿写 sysfs dev_msg；否则 cat/tdsm 都匹配不到）
        safe = devmsg.replace("'", "'\"'\"'")
        for _ in range(3):
            self.run_adb(f"shell \"echo '{safe}' > /proc/tran_devmsg\"", timeout=15)
        adb_cat, adb_err = self.run_adb('shell "cat /proc/tran_devmsg"', timeout=20)
        (ev / "tran_devmsg.txt").write_text(
            f"out={adb_cat}\nerr={adb_err}\n",
            encoding="utf-8",
        )
        if chip == "qcom":
            self._emit("case17: 高通设置 dload_mode=mini …")
            self.prepare_qcom_dload("mini")
        else:
            self.run_adb("shell mrdump_tool output-set none", timeout=20)
        ok_sysrq, sysrq_msg = self.trigger_sysrq_crash("case17")
        if not ok_sysrq:
            return "Fail", sysrq_msg
        time.sleep(30)
        self.run_adb("wait-for-device", timeout=180)
        self.after_boot(dload_mode="mini" if chip == "qcom" else None)
        if chip == "qcom":
            remote_part = "/dev/block/by-name/tdfs"
            local_img = work / "tdfs"
            pull_log = "adb_pull_tdfs.txt"
            pull_fail = "pull tdfs 失败"
        else:
            remote_part = "/dev/block/by-name/expdb"
            local_img = work / "expdb"
            pull_log = "adb_pull_expdb.txt"
            pull_fail = "pull expdb 失败"
        code, pout = self.run_host(
            ["adb", "-s", self.serial, "pull", remote_part, str(local_img)],
            cwd=work,
            timeout=600,
        )
        (ev / pull_log).write_text(f"exit={code}\n{pout}\n", encoding="utf-8")
        if code != 0 and not local_img.exists():
            return "Fail", pull_fail
        tcode, tout = self.run_host(
            [
                sys.executable,
                str(tools["tdsm"]),
                str(local_img),
                "--platform",
                "qcom" if chip == "qcom" else "mtk",
            ],
            cwd=work,
            timeout=300,
        )
        (ev / "tdsm.out").write_text(f"exit={tcode}\n{tout}\n", encoding="utf-8")
        ok_adb = product in (adb_cat or "") and date_str in (adb_cat or "")
        ok_tdsm = product in (tout or "") and date_str in (tout or "")
        msg = f"adb_match={ok_adb} tdsm_match={ok_tdsm} part={remote_part}"
        if not ok_adb:
            msg += f"；tran_devmsg={((adb_cat or adb_err) or '(empty)')[:120]}"
        if not ok_tdsm:
            # 常见失败：只有 panic notifier 栈，没有 type=1 自定义埋点行
            msg += "；tdsm 产物未含产品名/日期"
        return ("Pass" if ok_adb and ok_tdsm else "Fail"), msg

    def _guess_product(self) -> str:
        out, _ = self.run_adb("shell getprop ro.product.device", timeout=15)
        return (out or "UNKNOWN").strip() or "UNKNOWN"

    def check_fec20(self) -> Tuple[str, str]:
        """A17#18 fec2.0：pl_lk 搜 otaenablefec。"""
        self.ensure_root()
        ver, _ = self.run_adb("shell uname -r", timeout=15)
        if "5.10" in (ver or ""):
            return "NA", f"kernel 5.10 通常不支持 fec2.0（uname={ver.strip()}）"
        out, err = self.run_adb('shell "cat /proc/pl_lk"', timeout=30)
        text = out or ""
        if re.search(r"otaenablefec", text, re.I):
            hits = [ln.strip() for ln in text.splitlines() if "otaenablefec" in ln.lower()]
            return "Pass", " | ".join(hits[:3]) or "命中 otaenablefec"
        if not text:
            return "Fail", f"读取 /proc/pl_lk 失败: {err or '(empty)'}"
        return "Fail", "pl_lk 未找到 otaenablefec"

    def _pidof_kill19(self, process: str) -> Tuple[bool, str]:
        """pidof + kill -19（SIGSTOP），对齐旧 checklist 黑屏定屏造障。"""
        out, err = self.run_adb(f"shell pidof {process}", timeout=15)
        pid = next((t for t in (out or "").split() if t.isdigit()), None)
        if not pid:
            return False, f"pidof {process} 未得到 PID: {(out or err or '').strip()!r}"
        kout, kerr = self.run_adb(f"shell kill -19 {pid}", timeout=15)
        if kerr and "No such process" in kerr:
            return False, f"kill -19 {pid} 失败: {kerr}"
        # adb shell kill 常无输出；以进程仍存在/命令未报错为准
        return True, pid

    def _list_remote_tne_matches(
        self, remote_dir: str, focus_prefix: str
    ) -> Tuple[List[str], str]:
        """在设备上查找 focus_prefix*.tne；返回 (匹配路径列表, ls/find 原文)。"""
        remote_base = remote_dir.rstrip("/") or "/data/TNE"
        pref = (focus_prefix or "0xffffff35").strip()
        find_out, find_err = self.run_adb(
            f'shell "find {remote_base} -type f -name \'{pref}*.tne\' 2>/dev/null"',
            timeout=30,
        )
        matches = [
            ln.strip()
            for ln in (find_out or "").splitlines()
            if ln.strip().lower().endswith(".tne")
        ]
        ls_out, ls_err = self.run_adb(
            f'shell "ls -laR {remote_base} 2>/dev/null"',
            timeout=30,
        )
        listing = (ls_out or "").strip() or (find_out or "").strip() or (find_err or ls_err or "")
        return matches, listing

    def _wait_remote_tne(
        self,
        remote_dir: str,
        focus_prefix: str,
        timeout_sec: int,
        poll_sec: int,
    ) -> Tuple[List[str], str]:
        """轮询等待设备侧出现 focus_prefix*.tne（hung dump 落盘常晚于 60s）。"""
        timeout_sec = max(0, int(timeout_sec))
        poll_sec = max(5, int(poll_sec))
        deadline = time.time() + timeout_sec
        last_listing = ""
        while True:
            matches, listing = self._list_remote_tne_matches(remote_dir, focus_prefix)
            last_listing = listing
            if matches:
                return matches, listing
            remaining = deadline - time.time()
            if remaining <= 0:
                return [], last_listing
            self._emit(
                f"case19: 尚未出现 {focus_prefix}*.tne，继续等待"
                f"（剩余约 {int(remaining)}s / 共 {timeout_sec}s）…"
            )
            time.sleep(min(poll_sec, remaining))

    def _pull_tne_for_hung(self, work: Path, focus_prefix: str, remote_dir: str) -> List[Path]:
        """整目录 pull remote_dir（默认 /data/TNE），再筛选 focus 前缀的 .tne。"""
        remote_base = remote_dir.rstrip("/") or "/data/TNE"
        local_root = work / "TNE"
        if local_root.exists():
            shutil.rmtree(local_root, ignore_errors=True)
        local_root.mkdir(parents=True, exist_ok=True)

        self._emit(f"case19: adb pull {remote_base} → {local_root} …")
        code, out = self.run_host(
            ["adb", "-s", self.serial, "pull", remote_base, str(local_root)],
            cwd=work,
            timeout=600,
        )
        (work / "pull_tne_dir.txt").write_text(f"exit={code}\n{out}\n", encoding="utf-8")

        # adb pull /data/TNE <local> 常落成 local/TNE/...
        search_roots = [local_root]
        nested = local_root / Path(remote_base).name
        if nested.is_dir():
            search_roots.append(nested)

        pref = focus_prefix.lower()
        matched: List[Path] = []
        all_tne: List[str] = []
        for root in search_roots:
            if not root.is_dir():
                continue
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                name = p.name.lower()
                if name.endswith(".tne"):
                    all_tne.append(p.name)
                if name.startswith(pref) and name.endswith(".tne"):
                    matched.append(p)
        (work / "local_tne_names.txt").write_text(
            "\n".join(sorted(set(all_tne))) or "(no .tne under pull root)\n",
            encoding="utf-8",
        )
        return sorted(set(matched))

    def check_hung_black_screen(self) -> Tuple[str, str]:
        """黑屏定屏类故障检测（旧 checklist #10）：SF hung + system_server hung panic。"""
        tools, err = self._require_tools("tne_parser")
        if err:
            return "NA", err
        work = self.cfg["work_dir"] / "case19_hung"
        if work.exists():
            shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(19)
        focus_prefix = str(self.cfg.get("case10_tne_focus_prefix") or "0xffffff35")
        remote_dir = str(self.cfg.get("case10_tne_remote_dir") or "/data/TNE")
        appear_timeout = int(self.cfg.get("case10_tne_appear_timeout_sec") or 180)
        poll_sec = int(self.cfg.get("case10_tne_poll_sec") or 15)

        self.ensure_root()
        self._emit("case19: 清理 TNE 后造障 surfaceflinger hung …")
        self.run_adb('shell "rm -rf /data/TNE/*"', timeout=30)
        self.run_adb('shell "echo 30 > /proc/sys/kernel/hung_task_timeout_secs"', timeout=15)
        ok_sf, sf_msg = self._pidof_kill19("surfaceflinger")
        if not ok_sf:
            return "Fail", sf_msg
        self._sleep_with_progress(60, "case19: kill surfaceflinger 后等待", tick_sec=15)
        dmesg_hung, _ = self.run_adb('shell "dmesg | grep hung"', timeout=30)
        (ev / "dmesg_grep_hung.txt").write_text(
            dmesg_hung if (dmesg_hung or "").strip() else "(dmesg | grep hung 无输出)\n",
            encoding="utf-8",
        )

        self._emit(
            f"case19: 轮询等待设备侧 {focus_prefix}*.tne（最长 {appear_timeout}s）…"
        )
        remote_hits, remote_listing = self._wait_remote_tne(
            remote_dir, focus_prefix, appear_timeout, poll_sec
        )
        (ev / "remote_tne_ls.txt").write_text(
            remote_listing if (remote_listing or "").strip() else "(empty)\n",
            encoding="utf-8",
        )
        (ev / "remote_tne_matches.txt").write_text(
            "\n".join(remote_hits) or "(no match yet)\n",
            encoding="utf-8",
        )

        self._emit(f"case19: 整目录 pull {remote_dir}，查找 {focus_prefix}*.tne …")
        pulled = self._pull_tne_for_hung(work, focus_prefix, remote_dir)
        pull_meta = work / "pull_tne_dir.txt"
        if pull_meta.is_file():
            (ev / "pull_tne_dir.txt").write_text(
                pull_meta.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
        local_names = work / "local_tne_names.txt"
        if local_names.is_file():
            (ev / "local_tne_names.txt").write_text(
                local_names.read_text(encoding="utf-8", errors="replace"),
                encoding="utf-8",
            )
        (ev / "tne_pulled.txt").write_text(
            "\n".join(str(p) for p in pulled) or "(no .tne pulled)\n",
            encoding="utf-8",
        )
        if not pulled:
            seen = ""
            if local_names.is_file():
                seen = local_names.read_text(encoding="utf-8", errors="replace").strip()
            hint = f"；当时已有: {seen}" if seen and seen != "(no .tne under pull root)" else ""
            return (
                "Fail",
                f"整目录 {remote_dir} 下未找到 {focus_prefix}*.tne"
                f"（已轮询 {appear_timeout}s）{hint}",
            )

        # 用内置 tne_parser 解压（兼容无 TneDecompress.exe）
        self._emit(f"case19: tne_parser 解压 {len(pulled)} 个 .tne …")
        parser = tools["tne_parser"]
        dec_outs: List[str] = []
        for tne in pulled:
            # 仅处理 .tne 文件
            if tne.suffix.lower() != ".tne":
                continue
            out_dir = tne.parent / f"{tne.stem}_extracted"
            code, pout = self.run_host(
                [sys.executable, str(parser), str(tne), "-o", str(out_dir)],
                cwd=work,
                timeout=600,
            )
            dec_outs.append(f"=== {tne.name} exit={code} ===\n{pout}\n")
        (ev / "tne_decompress.out").write_text("\n".join(dec_outs) or "(no decompress)\n", encoding="utf-8")

        self._emit("case19: 造障 system_server hung → 读 pstore …")
        self.run_adb('shell "echo 2 > /sys/module/thd/parameters/hung_task_maxdeath_count"', timeout=15)
        ok_ss, ss_msg = self._pidof_kill19("system_server")
        if not ok_ss:
            return "Fail", ss_msg
        self._sleep_with_progress(60, "case19: kill system_server 后等待", tick_sec=15)
        wcode, wout = self.run_host(
            ["adb", "-s", self.serial, "wait-for-device"],
            timeout=180,
        )
        (ev / "wait_for_device.txt").write_text(f"exit={wcode}\n{wout}\n", encoding="utf-8")
        self.after_boot()
        self._sleep_with_progress(60, "case19: root 后等待 pstore 可读", tick_sec=15)
        pstore_out, pstore_err = self.run_adb(
            'shell "cat /sys/fs/pstore/console-ramoops-0"',
            timeout=30,
        )
        (ev / "pstore_console.txt").write_text(
            pstore_out or pstore_err or "(empty)\n",
            encoding="utf-8",
        )

        ok_kernel, ok_pstore, detail = analyze_case10_tne_artifacts(
            work,
            pstore_out or "",
            focus_prefix=focus_prefix,
            ev=ev,
        )
        (ev / "case19_check_detail.txt").write_text(detail + "\n", encoding="utf-8")
        msg = (
            f"hung_surfaceflinger={ok_kernel} pstore_panic={ok_pstore} "
            f"tne_files={len(pulled)}"
        )
        return ("Pass" if ok_kernel and ok_pstore else "Fail"), msg

    def check_sram_bitflip_ram_console(self) -> Tuple[str, str]:
        """cpu中sram bitflip导致的黑屏问题：ram_console.c 须含 off_pl 校验。"""
        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)
        rel = (
            "vendor/mediatek/proprietary/bootable/bootloader/preloader/platform/"
            "common/ram_console.c"
        )
        self._emit(f"case21: 检查 {rel} …")
        ok, msg = code_file_contains(
            code_dir,
            rel,
            ["ram_console->off_pl == sizeof(struct ram_console_buffer)"],
        )
        return ("Pass" if ok else "Fail"), msg

    def check_s2idle_hwt_patch(self) -> Tuple[str, str]:
        """kernel-5.10 s2idle hwt patch：mtk_s2idle_state_enable 须不存在或已注释。"""
        # 与旧 checklist 一致：优先 ro.kernel.version，回退 uname -r
        ver_out, _ = self.run_adb('shell "getprop ro.kernel.version"', timeout=15)
        ver = (ver_out or "").strip()
        m = re.search(r"\[ro\.kernel\.version\]:\s*\[([^\]]+)\]", ver)
        if m:
            ver = m.group(1).strip()
        if not ver or ver.startswith("["):
            uname, _ = self.run_adb("shell uname -r", timeout=15)
            ver = (uname or "").strip()
        ev = self._evidence(22)
        (ev / "kernel_version.txt").write_text(ver + "\n", encoding="utf-8")
        if "5.10" not in ver:
            return "NA", f"kernel 非 5.10: {ver or '(empty)'}"

        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)
        rel = (
            "kernel-5.10/drivers/misc/mediatek/lpm/modules/platform/"
            "suspend_v1/lpm_plat_suspend.c"
        )
        self._emit(f"case22: 检查 {rel} 中 mtk_s2idle_state_enable …")
        ok, msg = code_file_contains(
            code_dir,
            rel,
            ["mtk_s2idle_state_enable"],
            pass_if_missing_or_commented=True,
        )
        # pass_if_missing：True=不存在/已注释；False=仍存在未注释
        return ("Pass" if ok else "Fail"), msg

    def check_minidump_fulldump(self) -> Tuple[str, str]:
        """Qcom#24：minidump && fulldump 转存。

        - 切 dload_mode=both
        - sysrq 后 fulldump 停在 XBL（主机出现 90EE），用 qcom_dump/QSaharaServer 导出
        - 重启后检查 /data/vendor/debuglogger/minidump
        - 结束后恢复 mini
        """
        if self.detect_chip_platform() != "qcom":
            return "NA", "本项仅适用于高通平台"
        work = self.cfg["work_dir"] / "case24"
        work.mkdir(parents=True, exist_ok=True)
        ev = self._evidence(24)
        self.prepare_qcom_dload("both")
        (ev / "dload_mode_both.txt").write_text(
            f"desired=both\n",
            encoding="utf-8",
        )

        self._emit("case24: 触发 sysrq（期望进入 fulldump / 90EE）…")
        ok_sysrq, sysrq_msg = self.trigger_sysrq_crash("case24", wait_offline_sec=60)
        if not ok_sysrq:
            # 设备若仍在线则尝试恢复 mini
            try:
                self.prepare_qcom_dload("mini")
            except Exception:
                pass
            return "Fail", sysrq_msg

        # 给 Sahara 端口枚举一点时间
        self._sleep_with_progress(15, "case24: 等待 90EE 端口出现", tick_sec=5)
        sahara_dir = work / "fulldump_sahara"
        if sahara_dir.exists():
            shutil.rmtree(sahara_dir, ignore_errors=True)
        ok_sahara, sahara_msg = self.pull_qcom_sahara_dump(sahara_dir)
        (ev / "sahara_result.txt").write_text(
            f"ok={ok_sahara}\n{sahara_msg}\n",
            encoding="utf-8",
        )
        if not ok_sahara:
            self._emit(f"case24: Sahara 自动导出失败 — {sahara_msg}")
            return "Fail", f"fulldump Sahara 导出失败: {sahara_msg}"

        self._emit(
            f"case24: fulldump 已导出，wait-for-device（超时 {CASE24_WAIT_DEVICE_TIMEOUT_SEC}s）…"
        )
        # fulldump 导出后设备常需重启才回 adb；等待即可，不弹人工确认
        wcode, wout = self.run_host(
            ["adb", "-s", self.serial, "wait-for-device"],
            timeout=CASE24_WAIT_DEVICE_TIMEOUT_SEC,
        )
        (ev / "wait_for_device.txt").write_text(f"exit={wcode}\n{wout}\n", encoding="utf-8")
        if wcode != 0:
            return (
                "Fail",
                "fulldump 已导出，但 wait-for-device 超时（设备未回到 adb）；"
                "请确认导出后已重启再复测",
            )

        # 开机后：root + 恢复 mini（再查 minidump）
        self.after_boot(dload_mode="mini")
        self._sleep_with_progress(
            CASE24_POST_BOOT_WAIT_SEC,
            "case24: 开机后等待 minidump 落盘",
            tick_sec=15,
        )
        local_mini = work / "minidump"
        if local_mini.exists():
            shutil.rmtree(local_mini, ignore_errors=True)
        self._emit(f"case24: pull {QCOM_MINIDUMP_DIR} …")
        code, pull_out = self.run_host(
            ["adb", "-s", self.serial, "pull", QCOM_MINIDUMP_DIR, str(local_mini)],
            cwd=work,
            timeout=300,
        )
        (ev / "adb_pull_minidump.txt").write_text(f"exit={code}\n{pull_out}\n", encoding="utf-8")
        ls_out, _ = self.run_adb(f'shell "ls -la {QCOM_MINIDUMP_DIR}"', timeout=20)
        (ev / "minidump_ls.txt").write_text(ls_out or "(empty)\n", encoding="utf-8")

        mini_ok = local_mini.exists() and (
            (local_mini.is_dir() and any(p.is_file() for p in local_mini.rglob("*")))
            or (local_mini.is_file() and local_mini.stat().st_size > 0)
        )
        if not mini_ok:
            return (
                "Fail",
                f"fulldump 已导出，但未在 {QCOM_MINIDUMP_DIR} 拉到 minidump 文件",
            )
        return "Pass", f"fulldump(Sahara) + minidump({QCOM_MINIDUMP_DIR}) 均已确认"

    def check_boot_log_save(self) -> Tuple[str, str]:
        """Qcom#26：启动日志保存在 /data/vendor/debuglogger/stability。"""
        if self.detect_chip_platform() != "qcom":
            return "NA", "本项仅适用于高通平台"
        ev = self._evidence(26)
        self.prepare_qcom_dload("mini")
        remote = QCOM_BOOT_LOG_DIR
        self._emit(f"case26: 检查 {remote} …")
        ls_out, ls_err = self.run_adb(f'shell "ls -la {remote}"', timeout=20)
        (ev / "stability_ls.txt").write_text(
            f"out={ls_out}\nerr={ls_err}\n",
            encoding="utf-8",
        )
        text = (ls_out or "").strip()
        if "No such file" in text or "No such file" in (ls_err or ""):
            return "Fail", f"不存在目录 {remote}"
        if not text:
            return "Fail", f"无法列出 {remote}: {ls_err or '(empty)'}"
        # 目录存在且非空（至少有 . 以外的条目）
        lines = [
            ln for ln in text.splitlines()
            if ln.strip() and not ln.strip().endswith(" .") and not ln.strip().endswith(" ..")
        ]
        # ls -la 至少有 total 行；再看是否有真实文件行
        file_lines = [
            ln for ln in lines
            if not ln.lower().startswith("total") and "Permission denied" not in ln
        ]
        if len(file_lines) <= 0:
            return "Fail", f"{remote} 存在但为空"
        work = self.cfg["work_dir"] / "case26"
        work.mkdir(parents=True, exist_ok=True)
        local = work / "stability_logs"
        if local.exists():
            shutil.rmtree(local, ignore_errors=True)
        code, pout = self.run_host(
            ["adb", "-s", self.serial, "pull", remote, str(local)],
            cwd=work,
            timeout=300,
        )
        (ev / "adb_pull.txt").write_text(f"exit={code}\n{pout}\n", encoding="utf-8")
        if local.exists() and any(p.is_file() for p in local.rglob("*")):
            return "Pass", f"{remote} 存在且已 pull 到本地证据"
        return "Pass", f"{remote} 目录非空（pull 可忽略）: {file_lines[0][:120]}"

    def check_pl_lk_boot_reason(self) -> Tuple[str, str]:
        """MTK：preloader platform.h 与 lk boot_mode.h 的 boot_reason 枚举一致。"""
        plat_out, _ = self.run_adb("shell getprop ro.board.platform", timeout=15)
        plat = (plat_out or "").strip()
        m = re.search(r"\[ro\.board\.platform\]:\s*\[([^\]]+)\]", plat)
        if m:
            plat = m.group(1).strip()
        ev = self._evidence(23)
        (ev / "platform.txt").write_text(plat + "\n", encoding="utf-8")
        if not plat:
            return "Fail", "未获取到 ro.board.platform"

        code_dir, err = self._require_code_dir()
        if err:
            return self._pending_need_code_dir(err)
        self._emit(f"case23: 比对平台 {plat} 的 pl/lk boot_reason 枚举 …")
        ok, msg = check_boot_reason_enums(code_dir, plat)
        (ev / "result.txt").write_text(
            f"{'pass' if ok else 'fail'}: {msg}\n",
            encoding="utf-8",
        )
        return ("Pass" if ok else "Fail"), msg

    def _fn_for(self, item_id: int) -> CheckFn:
        mapping: Dict[int, CheckFn] = {
            1: StabilityChecker.check_log_config,
            2: StabilityChecker.check_manual_placeholder,
            3: StabilityChecker.check_earlycon,
            4: StabilityChecker.check_manual_placeholder,
            5: StabilityChecker.check_manual_placeholder,
            6: StabilityChecker.check_download_mode,
            7: StabilityChecker.check_manual_placeholder,
            8: StabilityChecker.check_db_sysrq,
            9: StabilityChecker.check_mtprintk_uart_off,
            10: StabilityChecker.check_rt_runtime_share_off,
            11: StabilityChecker.check_tranpdb,
            12: StabilityChecker.check_sodi_removed,
            13: StabilityChecker.check_tdfs_stucklogo,
            14: StabilityChecker.check_mrdump_key,
            15: StabilityChecker.check_mt6789_xtal,
            16: StabilityChecker.check_manual_placeholder,
            17: StabilityChecker.check_tdsm,
            18: StabilityChecker.check_fec20,
            19: StabilityChecker.check_hung_black_screen,
            20: StabilityChecker.check_manual_placeholder,
            21: StabilityChecker.check_sram_bitflip_ram_console,
            22: StabilityChecker.check_s2idle_hwt_patch,
            23: StabilityChecker.check_pl_lk_boot_reason,
            24: StabilityChecker.check_minidump_fulldump,
            25: StabilityChecker.check_manual_placeholder,
            26: StabilityChecker.check_boot_log_save,
            27: StabilityChecker.check_manual_placeholder,
        }
        return mapping[item_id]

    def run_item(self, item_id: int) -> Dict[str, Any]:
        item_id = int(item_id)
        name = checklist_item_name(item_id)
        total = len(CHECKLIST_ITEMS)
        if not self.check_device():
            return {
                "id": item_id,
                "name": name,
                "status": "Fail",
                "info": f"设备不可用或未连接: {self.serial}",
            }
        # 高通：每次用例开始重设 dload（mini；#24 用 both）；开机后由 after_boot 再写
        try:
            chip = self.detect_chip_platform()
            platforms = _load_case_platforms().get(item_id) or []
            if platforms and chip != "unknown" and chip not in platforms:
                status_norm = "NA"
                info = f"非本机平台用例（设备={chip}，用例适用={','.join(platforms)}）"
                row = {"id": item_id, "name": name, "status": status_norm, "info": info}
                self.results[item_id] = row
                self._emit(f"[{item_id}/{total}] {name} → {status_norm}: {info}")
                return row
            if chip == "qcom":
                # 每次用例都重设：user_root 开机后 dload 会回到 full
                mode = "both" if item_id == 24 else "mini"
                self.prepare_qcom_dload(mode)
        except Exception as exc:
            self._emit(f"平台预处理警告: {exc}")
        self._emit(f"[{item_id}/{total}] {name} …")
        try:
            status, info = self._fn_for(item_id)(self)
        except Exception as exc:
            status, info = "Fail", str(exc)
        low = str(status).strip().lower()
        if low == "pass":
            status_norm = "Pass"
        elif low in ("na", "skip"):
            status_norm = "NA"
        elif low in ("pending", "待确认"):
            status_norm = "Pending"
        else:
            status_norm = "Fail"
        row = {"id": item_id, "name": name, "status": status_norm, "info": info}
        self.results[item_id] = row
        self._emit(f"[{item_id}/{total}] {name} → {status_norm}: {info}")
        return row

    def run_all(self) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        passed = failed = na = pending = 0
        for row in CHECKLIST_ITEMS:
            result = self.run_item(int(row["id"]))
            items.append(result)
            low = str(result.get("status") or "").lower()
            if low == "pass":
                passed += 1
            elif low == "na":
                na += 1
            elif low == "pending":
                pending += 1
            else:
                failed += 1
        return {
            "items": items,
            "total": len(items),
            "passed": passed,
            "failed": failed,
            "na": na,
            "pending": pending,
        }
