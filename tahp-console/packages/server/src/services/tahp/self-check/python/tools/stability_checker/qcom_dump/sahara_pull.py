"""高通 Sahara fulldump 导出（对齐原 pull_dump.bat 用法）。

仅依赖同目录 QSaharaServer.exe：
1) 枚举本机 COM，优先 90EE / Diagnostics / Sahara / Qualcomm
2) 调用: QSaharaServer.exe -p \\\\.\\COMx -m -v 1 -w <out>\\\\ -R
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Callable, List, Optional, Tuple

TOOL_DIR = Path(__file__).resolve().parent
QS_NAME = "QSaharaServer.exe"

_COM_RE = re.compile(r"\((COM\d+)\)", re.I)
_PREF_RE = re.compile(
    r"Qualcomm|QDLoader|QHSUSB|90EE|900E|9008|Diagnostics|Memory\s*Dump|Sahara",
    re.I,
)
_BEST_RE = re.compile(r"90EE|900E|Diagnostics|Memory\s*Dump|Sahara", re.I)


def _list_com_devices() -> List[Tuple[str, str]]:
    """返回 [(COMx, friendly_name), ...]。"""
    devices: List[Tuple[str, str]] = []

    # 1) pyserial（若环境已装）
    try:
        from serial.tools import list_ports  # type: ignore

        for p in list_ports.comports():
            port = (p.device or "").strip().upper()
            if not port.startswith("COM"):
                # 有的环境是 \\.\COMx
                m = re.search(r"(COM\d+)", port, re.I)
                if not m:
                    continue
                port = m.group(1).upper()
            name = (p.description or p.hwid or port).strip()
            devices.append((port, name))
        if devices:
            return _dedupe_ports(devices)
    except Exception:
        pass

    # 2) WMI（Windows，标准库 subprocess + CIM，无 .ps1 文件）
    if sys.platform.startswith("win"):
        try:
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_PnPEntity | "
                "Where-Object { $_.Name -match 'COM\\d+' } | "
                "ForEach-Object { $_.Name }",
            ]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
            )
            for line in (proc.stdout or "").splitlines():
                line = line.strip()
                if not line:
                    continue
                m = _COM_RE.search(line)
                if not m:
                    continue
                devices.append((m.group(1).upper(), line))
            if devices:
                return _dedupe_ports(devices)
        except Exception:
            pass

    return _dedupe_ports(devices)


def _dedupe_ports(devices: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    seen = set()
    out: List[Tuple[str, str]] = []
    for port, name in devices:
        key = port.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append((key, name))
    return out


def pick_qcom_dump_port(
    devices: Optional[List[Tuple[str, str]]] = None,
) -> Tuple[Optional[str], Optional[str], List[Tuple[str, str]]]:
    """优先选 90EE/Diagnostics/Sahara，否则其它 Qualcomm 口。

    返回 (com_port, friendly_name, all_candidates)。
    """
    all_devs = devices if devices is not None else _list_com_devices()
    pref = [(p, n) for p, n in all_devs if _PREF_RE.search(n)]
    if not pref:
        pref = [
            (p, n)
            for p, n in all_devs
            if re.search(r"Qualcomm|QDLoader|QHSUSB", n, re.I)
        ]
    if not pref:
        return None, None, all_devs

    best = [(p, n) for p, n in pref if _BEST_RE.search(n)]
    ordered = best + [(p, n) for p, n in pref if (p, n) not in best]
    port, name = ordered[0]
    return port, name, ordered


def resolve_qsahara(exe: Optional[Path] = None) -> Optional[Path]:
    if exe and Path(exe).is_file():
        return Path(exe)
    candidate = TOOL_DIR / QS_NAME
    return candidate if candidate.is_file() else None


def pull_sahara_dump(
    out_dir: Path,
    *,
    qs_exe: Optional[Path] = None,
    timeout_sec: int = 900,
    on_log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """检测 COM 并调用 QSaharaServer 导出 fulldump。"""

    def log(msg: str) -> None:
        if on_log:
            try:
                on_log(msg)
            except Exception:
                pass

    qs = resolve_qsahara(qs_exe)
    if not qs:
        return False, f"未找到 {QS_NAME}（期望位于 {TOOL_DIR / QS_NAME}）"

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log("检测 90EE / Qualcomm COM 口…")
    port, name, candidates = pick_qcom_dump_port()
    detect_txt = "\n".join(f"{p}|{n}" for p, n in candidates) or "(none)"
    (out_dir / "detect_com.txt").write_text(detect_txt + "\n", encoding="utf-8")
    if not port:
        return False, (
            "未检测到 Qualcomm/90EE COM 口。"
            "请确认设备已进入 crash dump / Sahara（主机出现 90EE），然后重试。"
            f"\n当前候选:\n{detect_txt[:400]}"
        )

    # 与 bat 一致: -p \\.\COMx -m -v 1 -w "<out>\\" -R
    port_arg = f"\\\\.\\{port}"
    # QSaharaServer 要求 -w 目录以 \ 结尾
    out_arg = str(out_dir.resolve())
    if not out_arg.endswith("\\"):
        out_arg = out_arg + "\\"

    args = [str(qs), "-p", port_arg, "-m", "-v", "1", "-w", out_arg, "-R"]
    log(f"使用端口 {port} ({name})；运行 QSaharaServer …")
    try:
        proc = subprocess.run(
            args,
            cwd=str(qs.parent),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_sec,
        )
        scode = proc.returncode
        sout = (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return False, f"QSaharaServer 超时（>{timeout_sec}s）"
    except Exception as exc:
        return False, f"启动 QSaharaServer 失败: {exc}"

    (out_dir / "qsahara.out").write_text(
        f"exit={scode}\ncmd={' '.join(args)}\nport={port}\nname={name}\n{sout}\n",
        encoding="utf-8",
    )
    skip = {"detect_com.txt", "qsahara.out"}
    files = [p for p in out_dir.iterdir() if p.is_file() and p.name not in skip]
    if scode != 0 and not files:
        return False, f"QSaharaServer 失败(exit={scode}): {sout[:300]}"
    if not files:
        return False, "QSaharaServer 结束但输出目录无 dump 文件"
    return True, f"已导出 {len(files)} 个文件到 {out_dir}（{port}）"


if __name__ == "__main__":
    # 手工调试: python sahara_pull.py [out_dir]
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else (TOOL_DIR / "dump" / "manual")
    ok, msg = pull_sahara_dump(target, on_log=print)
    print(("OK" if ok else "FAIL"), msg)
    sys.exit(0 if ok else 1)
