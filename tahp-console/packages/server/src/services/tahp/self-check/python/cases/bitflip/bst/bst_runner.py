"""bitflip 压测（MTK Bitflip Analysis Tool）运行器。

职责：
1. 校验 java/adb/工具目录，启动 ``java -jar BitflipAnalysisTool.jar`` 并流式跟踪输出；
2. 运行结束后定位新生成的 ``BAT-Data_<时间戳>/`` 目录；
3. 解析 ``<项目>-<序列号>--BST.xlsx`` 结果表（仅依赖标准库），
   输出每一轮每一项的结果、整体结论与日志路径，供自检报告展示。
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

XLSX_MAIN_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
XLSX_REL_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
PKG_REL_NS = "{http://schemas.openxmlformats.org/package/2006/relationships}"

DEFAULT_REPEAT_COUNT = 5
MIN_REPEAT_COUNT = 1
MAX_REPEAT_COUNT = 100

JAR_NAME = "BitflipAnalysisTool.jar"
BAT_DATA_PREFIX = "BAT-Data_"
BST_XLSX_SUFFIX = "--BST.xlsx"
BST_LOG_NAME = "BST_Log.txt"

TOOL_DIR = Path(__file__).resolve().parents[3] / "tools" / "bitflip_bat"

# 仅上屏里程碑日志，避免数小时长跑把子步骤刷爆
MILESTONE_RE = re.compile(
    r"(Phase#\d+\s+Loop\s+\d+|TestCaseResult|result\s*=\s*false|Read Config from|"
    r"Find a device|Force select platform|Wait device boot completed|"
    r"bit\s*flip|corruption|panic|cleanup\.bat)",
    re.IGNORECASE,
)
# 错误/异常行：即时上屏（BAT 常把关键错误打到 stderr 且以 0 退出，必须透出）
ERROR_LINE_RE = re.compile(
    r"(error|can\s*not|cannot|fail|exception|not match|unauthorized|offline|"
    r"denied|distory|disconnected|unable)",
    re.IGNORECASE,
)
MAX_STEPS = 80
HEARTBEAT_SEC = 300
CONSOLE_TAIL_LINES = 8
ADB_CHECK_TIMEOUT_SEC = 30


def normalize_repeat_count(raw) -> int:
    """遍历条件下每项重复测试次数（-r 参数），默认 5；非法/非正数回默认。"""
    try:
        n = int(str(raw).strip())
    except (TypeError, ValueError):
        return DEFAULT_REPEAT_COUNT
    if n < MIN_REPEAT_COUNT:
        return DEFAULT_REPEAT_COUNT
    return min(MAX_REPEAT_COUNT, n)


def _column_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + (ord(ch.upper()) - 64)
    return idx - 1


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    return [
        "".join(t.text or "" for t in si.iter(f"{XLSX_MAIN_NS}t"))
        for si in root.findall(f"{XLSX_MAIN_NS}si")
    ]


def _first_sheet_path(zf: zipfile.ZipFile) -> str:
    workbook = ET.fromstring(zf.read("xl/workbook.xml"))
    sheet = workbook.find(f".//{XLSX_MAIN_NS}sheet")
    if sheet is None:
        raise ValueError("结果表中没有工作表")
    rid = sheet.attrib[f"{XLSX_REL_NS}id"]
    rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
    for rel in rels.findall(f"{PKG_REL_NS}Relationship"):
        if rel.attrib.get("Id") == rid:
            target = rel.attrib["Target"]
            return target if target.startswith("xl/") else f"xl/{target.lstrip('/')}"
    raise ValueError("未找到工作表关系")


def parse_bst_xlsx(path: Path) -> list[list]:
    """解析 xlsx 首个 sheet 为二维表（int/bool/str/''，空单元格为 ''）。"""
    with zipfile.ZipFile(path) as zf:
        shared = _read_shared_strings(zf)
        sheet_path = _first_sheet_path(zf)
        root = ET.fromstring(zf.read(sheet_path))
        grid: list[list] = []
        for row in root.findall(f".//{XLSX_MAIN_NS}sheetData/{XLSX_MAIN_NS}row"):
            cells: dict[int, object] = {}
            max_idx = -1
            for cell in row.findall(f"{XLSX_MAIN_NS}c"):
                ref = cell.attrib.get("r", "")
                idx = _column_index(ref) if ref else max_idx + 1
                cell_type = cell.attrib.get("t", "n")
                value_node = cell.find(f"{XLSX_MAIN_NS}v")
                raw = value_node.text if value_node is not None else None
                if cell_type == "s":
                    value = shared[int(raw)] if raw else ""
                elif cell_type == "b":
                    value = (raw or "0").strip() in ("1", "true", "TRUE")
                elif cell_type in ("str", "inlineStr"):
                    if raw is not None:
                        value = raw
                    else:
                        inline = cell.find(f"{XLSX_MAIN_NS}is/{XLSX_MAIN_NS}t")
                        value = inline.text if inline is not None and inline.text else ""
                elif raw is None or raw == "":
                    value = ""
                elif re.fullmatch(r"-?\d+", raw):
                    value = int(raw)
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        value = raw
                cells[idx] = value
                max_idx = max(max_idx, idx)
            if max_idx >= 0:
                grid.append([cells.get(i, "") for i in range(max_idx + 1)])
        return grid


def _cell_is_true(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "pass", "passed")


def _round_item_text(value) -> str:
    """Item 列（轮次序号）规范化；非正整数序号返回 ''（空行/备注行）。"""
    if isinstance(value, bool):
        return ""
    if isinstance(value, (int, float)):
        number = float(value)
        return str(int(number)) if number.is_integer() and number > 0 else ""
    text = str(value).strip()
    return text if text.isdigit() and int(text) > 0 else ""


def _display_cell(value):
    """xlsx 数值常为 1.0，展示时归一为 int；其余类型原样保留。"""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def parse_bst_result(xlsx_path: Path) -> dict:
    """解析 --BST.xlsx：表头、数据行（跳过空行/备注行）、按 Result 列汇总。"""
    grid = parse_bst_xlsx(xlsx_path)
    if not grid:
        raise ValueError("结果表为空")
    header = [str(c).strip() for c in grid[0]]
    data_rows: list[list] = []
    for raw in grid[1:]:
        item_text = _round_item_text(raw[0] if raw else "")
        if not item_text:
            continue  # 空行或备注行（如 "No need analysis root cause."）
        row = [_display_cell(c) for c in raw] + [""] * (len(header) - len(raw))
        row = row[: len(header)]
        row[0] = int(item_text)
        data_rows.append(row)

    result_col = next((i for i, name in enumerate(header) if name.lower() == "result"), None)
    comment_col = next((i for i, name in enumerate(header) if name.lower() == "comment"), None)

    passed = 0
    failure_comments: list[str] = []
    for row in data_rows:
        ok = _cell_is_true(row[result_col]) if result_col is not None else False
        if ok:
            passed += 1
        else:
            comment = str(row[comment_col]).strip() if comment_col is not None else ""
            failure_comments.append(f"第{row[0]}轮" + (f": {comment}" if comment else ""))

    failed = len(data_rows) - passed
    return {
        "columns": header,
        "rows": data_rows,
        "totalRounds": len(data_rows),
        "passedRounds": passed,
        "failedRounds": failed,
        "overallResult": "PASS" if data_rows and failed == 0 else "FAIL",
        "failureComments": failure_comments,
    }


def _parse_adb_devices(output: str) -> dict[str, str]:
    """解析 `adb devices` 输出：{serial: state}（state 如 device/offline/unauthorized）。"""
    devices: dict[str, str] = {}
    for line in (output or "").splitlines():
        text = line.strip()
        if not text or text.startswith("List of devices") or text.startswith("*"):
            continue
        parts = text.split()
        if len(parts) >= 2:
            devices[parts[0]] = parts[1]
    return devices


def _check_device_visible(serial: str) -> str | None:
    """启动前校验 adb 可见性；返回 None 表示通过，否则为中文错误消息。"""
    adb = shutil.which("adb")
    if not adb:
        return "未找到 adb，请将 Android platform-tools 加入 PATH 后重试"
    try:
        result = subprocess.run(
            [adb, "devices"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=ADB_CHECK_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"执行 adb devices 失败: {exc}"

    devices = _parse_adb_devices((result.stdout or "") + "\n" + (result.stderr or ""))
    state = devices.get(serial)
    if state == "device":
        return None
    visible = "、".join(f"{s}({st})" for s, st in devices.items()) or "无"
    if state:
        return (
            f"设备 {serial} 当前 adb 状态为 {state}（非在线 device 状态）。"
            f"请重新插拔/授权设备后重试；当前 adb 可见: {visible}"
        )
    return (
        f"adb 设备列表中未找到 {serial}（当前可见: {visible}）。"
        "请确认被测设备已 USB 连接且 adb 在线，并在 EA 设备列表刷新后重试"
    )


def _newest_bat_data_dir(tool_dir: Path, exclude: set[Path]) -> Path | None:
    candidates = [
        p for p in tool_dir.glob(f"{BAT_DATA_PREFIX}*")
        if p.is_dir() and p not in exclude
    ]
    if not candidates:
        candidates = [p for p in tool_dir.glob(f"{BAT_DATA_PREFIX}*") if p.is_dir()]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _archive_artifacts(result_dir: str | None, xlsx_path: Path | None, bst_log: Path | None) -> dict:
    """把结果表与主日志复制进自检报告目录，工具目录清理后报告仍可查。"""
    archived = {"archivedXlsxPath": "", "archivedBstLogPath": ""}
    if not result_dir:
        return archived
    try:
        dest = Path(result_dir) / "bitflip"
        dest.mkdir(parents=True, exist_ok=True)
        if xlsx_path and xlsx_path.is_file():
            target = dest / xlsx_path.name
            shutil.copy2(xlsx_path, target)
            archived["archivedXlsxPath"] = str(target)
        if bst_log and bst_log.is_file():
            target = dest / bst_log.name
            shutil.copy2(bst_log, target)
            archived["archivedBstLogPath"] = str(target)
    except OSError:
        pass
    return archived


def run_bitflip_test(serial: str, repeat_count: int, on_step=None, result_dir: str | None = None) -> dict:
    """同步执行 BAT bitflip 压测，返回自检用例结果（status/message/detail.bitflip）。"""
    steps: list[str] = []

    def add_step(text: str) -> None:
        steps.append(text)
        if len(steps) > MAX_STEPS:
            del steps[10:20]  # 保留开头与最新，丢弃中段
        if on_step:
            on_step("\n".join(steps))

    tool_dir = TOOL_DIR
    jar_path = tool_dir / JAR_NAME
    if not jar_path.is_file():
        return {"status": "fail", "message": f"BAT 工具不存在: {jar_path}", "full_automation": True}
    java = shutil.which("java")
    if not java:
        return {
            "status": "fail",
            "message": "未找到 java，请安装 JRE/JDK 并加入 PATH 后重试",
            "full_automation": True,
        }

    # 启动前校验：jar 在设备不可见时仅以 stderr 打印错误并以 0 退出，必须先拦下
    preflight_error = _check_device_visible(serial)
    if preflight_error:
        add_step(f"设备 adb 校验失败: {preflight_error}-失败")
        return {"status": "fail", "message": preflight_error, "full_automation": True}

    # 完整控制台输出落盘（BAT 的关键错误常打到 stderr 且以 0 退出，仅存 stdout 会丢诊断）
    if result_dir:
        console_log = Path(result_dir) / "bitflip" / "bat_console.log"
    else:
        console_log = tool_dir / "bat_console_latest.log"
    try:
        console_log.parent.mkdir(parents=True, exist_ok=True)
        console_fp = open(console_log, "w", encoding="utf-8", errors="replace")
    except OSError:
        console_fp = None

    console_tail: list[str] = []

    def record_console(text: str) -> None:
        console_tail.append(text)
        if len(console_tail) > CONSOLE_TAIL_LINES * 4:
            del console_tail[: len(console_tail) - CONSOLE_TAIL_LINES * 4]
        if console_fp:
            try:
                console_fp.write(text + "\n")
                console_fp.flush()
            except OSError:
                pass

    def console_tail_text() -> str:
        return " | ".join(console_tail[-CONSOLE_TAIL_LINES:])

    repeat_count = normalize_repeat_count(repeat_count)
    cmd = [
        java, "-jar", str(jar_path),
        "-o", "true",
        "-i", "30",
        "-r", str(repeat_count),
        "-s", serial,
    ]
    add_step(f"启动 BAT bitflip 压测，设备: {serial}，每项重复: {repeat_count} 次")
    add_step(f"命令: java -jar {JAR_NAME} -o true -i 30 -r {repeat_count} -s {serial}")
    add_step(f"控制台日志: {console_log}")

    existing_dirs = {p for p in tool_dir.glob(f"{BAT_DATA_PREFIX}*") if p.is_dir()}
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=str(tool_dir),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except OSError as exc:
        if console_fp:
            try:
                console_fp.close()
            except OSError:
                pass
        return {"status": "fail", "message": f"启动 java 失败: {exc}", "full_automation": True}

    last_heartbeat = time.monotonic()
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.strip()
        if text:
            record_console(text)
            brief = re.sub(r"^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\s+", "", text)[:200]
            if ERROR_LINE_RE.search(text):
                add_step(f"工具输出异常: {brief}-失败")
            elif MILESTONE_RE.search(text):
                add_step(brief)
        now = time.monotonic()
        if now - last_heartbeat >= HEARTBEAT_SEC:
            last_heartbeat = now
            add_step(f"压测运行中… 已持续 {int((now - start) // 60)} 分钟")
    exit_code = proc.wait()
    if console_fp:
        try:
            console_fp.close()
        except OSError:
            pass
    duration_sec = int(time.monotonic() - start)

    bat_dir = _newest_bat_data_dir(tool_dir, existing_dirs)
    xlsx_path = None
    bst_log = None
    if bat_dir:
        xlsx_candidates = sorted(
            (p for p in bat_dir.glob(f"*{BST_XLSX_SUFFIX}") if not p.name.startswith("~$")),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        xlsx_path = xlsx_candidates[0] if xlsx_candidates else None
        candidate_log = bat_dir / BST_LOG_NAME
        bst_log = candidate_log if candidate_log.is_file() else None

    base_detail = {
        "logDir": str(bat_dir) if bat_dir else "",
        "xlsxPath": str(xlsx_path) if xlsx_path else "",
        "bstLogPath": str(bst_log) if bst_log else "",
        "consoleLogPath": str(console_log),
        "repeatCount": repeat_count,
        "javaExitCode": exit_code,
        "durationSec": duration_sec,
    }

    if not bat_dir or not xlsx_path:
        tail = console_tail_text()
        message = (
            f"BAT 未生成结果表（java 退出码 {exit_code}，运行 {duration_sec}s）。"
            f"控制台日志: {console_log}"
            + (f"；末尾输出: {tail}" if tail else "")
        )
        add_step("未找到 BAT-Data 结果目录/结果表-失败")
        return {
            "status": "fail",
            "message": message,
            "full_automation": True,
            "detail": {"bitflip": {**base_detail, "columns": [], "rows": [], "totalRounds": 0,
                                   "passedRounds": 0, "failedRounds": 0, "overallResult": "FAIL"}},
        }

    try:
        parsed = parse_bst_result(xlsx_path)
    except (ValueError, KeyError, OSError, zipfile.BadZipFile, ET.ParseError) as exc:
        add_step(f"解析结果表失败: {exc}-失败")
        return {
            "status": "fail",
            "message": f"解析结果表失败: {exc}；结果表: {xlsx_path}",
            "full_automation": True,
            "detail": {"bitflip": {**base_detail, "columns": [], "rows": [], "totalRounds": 0,
                                   "passedRounds": 0, "failedRounds": 0, "overallResult": "FAIL"}},
        }

    archived = _archive_artifacts(result_dir, xlsx_path, bst_log)
    bitflip = {**base_detail, **parsed, **archived}

    total = parsed["totalRounds"]
    passed = parsed["passedRounds"]
    failed = parsed["failedRounds"]
    overall = parsed["overallResult"]
    if total == 0:
        message = f"结果表无有效轮次（java 退出码 {exit_code}）；结果表: {xlsx_path}"
        add_step("结果表无有效轮次-失败")
        return {"status": "fail", "message": message, "full_automation": True,
                "detail": {"bitflip": bitflip}}

    message = f"共 {total} 轮：通过 {passed}、失败 {failed}；整体 {overall}"
    if parsed["failureComments"]:
        shown = parsed["failureComments"][:5]
        message += "；" + "；".join(shown)
        if len(parsed["failureComments"]) > 5:
            message += f" …等共 {len(parsed['failureComments'])} 轮失败"
    message += f"；日志: {bat_dir}"

    if overall == "PASS":
        add_step(f"bitflip 压测通过 — {total} 轮全部 PASS-成功")
    else:
        add_step(f"bitflip 压测失败 — {failed}/{total} 轮 FAIL-失败")

    return {
        "status": "pass" if overall == "PASS" else "fail",
        "message": message,
        "full_automation": True,
        "detail": {"bitflip": bitflip},
    }
