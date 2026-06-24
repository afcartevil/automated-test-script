"""
高通 Modem Log 导出工具
将 .qmdl2 / .qdss 文件中的 Diag 数据包导出为可读 txt 文件

依赖：已安装 QUTS（默认路径 C:/Program Files (x86)/Qualcomm/QUTS）

用法：
    # 导出所有类型
    python export_modem_log.py mdlog/
    
    # 导出指定单个类型
    python export_modem_log.py mdlog/ --type log
    python export_modem_log.py mdlog/ --type event --id 1001
    
    # 导出多个类型（可多次使用 --type，或用逗号分隔）
    python export_modem_log.py mdlog/ --type log --type qtrace
    python export_modem_log.py mdlog/ --type log,qtrace,event
    
    # 只对 Log 类型指定具体 ID
    python export_modem_log.py mdlog/ --type log --id 0xB111
    python export_modem_log.py mdlog/ --type log,qtrace --id 0xB111  # 仅对 log 生效

    # 内容搜索
    python export_modem_log.py mdlog/ --search vsim_dbg
    python export_modem_log.py mdlog/ --type log --search "connection established"

支持的 Item Type：
    - all (默认)        : 所有类型
    - diag-request      : Diag Requests (Command Requests)
    - diag-response     : Diag Responses (Command Responses)
    - subsys-request    : Subsystem Requests
    - subsys-response   : Subsystem Responses
    - event             : Event Reports
    - log               : Log Packets
    - debug-msg         : Debug Messages / F3 Messages
    - qtrace            : QTrace 数据
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import Any

# QUTS 新版本（约 2025+）将 Python API 装在 64 位目录；旧版在 x86 下。
QUTS_PYTHON_CANDIDATES = (
    r"C:\Program Files\Qualcomm\QUTS\Support\python",
    r"C:\Program Files (x86)\Qualcomm\QUTS\Support\python",
)
DEFAULT_QUTS_PYTHON_PATH = QUTS_PYTHON_CANDIDATES[0]


def qcom_export_single_line() -> bool:
    """默认单行导出，便于 log-search-read 按行匹配；QCOM_EXPORT_MULTILINE=1 恢复多行。"""
    return os.environ.get("QCOM_EXPORT_MULTILINE", "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )


def collapse_log_text(text: str) -> str:
    """将 Summary / Parsed 内的换行压成一行（保留词间空格）。"""
    return " ".join((text or "").split())


def resolve_quts_python_path(explicit: str | None = None) -> str | None:
    """解析 QUTS Support/python：显式参数 > QUTS_PYTHON_PATH > 常见安装路径。"""
    for path in (explicit, os.environ.get("QUTS_PYTHON_PATH") or ""):
        path = (path or "").strip()
        if path and os.path.isdir(path):
            return os.path.abspath(path)
    for path in QUTS_PYTHON_CANDIDATES:
        if os.path.isdir(path):
            return os.path.abspath(path)
    return None

# QUTS 模块延迟加载，便于 pipeline 在无 QUTS 机器上 import 本模块（仅 SKIP 路径）
_quts_ready = False
CommonTypes = None  # type: ignore
DeviceManagerTypes = None  # type: ignore
LogSessionConstants = None  # type: ignore
LogSessionTypes = None  # type: ignore
QutsClient = None  # type: ignore
QutsServiceConstants = None  # type: ignore
PACKET_TYPE_NAMES: dict = {}
ITEM_TYPE_MAP: dict = {}


def ensure_quts_imported(quts_python_path: str | None = None) -> None:
    """加载 QUTS Python API（可重复调用）。"""
    global _quts_ready, CommonTypes, DeviceManagerTypes, LogSessionConstants
    global LogSessionTypes, QutsClient, QutsServiceConstants
    global PACKET_TYPE_NAMES, ITEM_TYPE_MAP

    if _quts_ready:
        return

    path = resolve_quts_python_path(quts_python_path)
    if not path:
        tried = ", ".join(repr(p) for p in QUTS_PYTHON_CANDIDATES)
        raise RuntimeError(
            f"QUTS Support/python 未找到，请安装 QUTS 或设置 QUTS_PYTHON_PATH。已尝试: {tried}"
        )
    if path not in sys.path:
        sys.path.insert(0, path)

    try:
        import Common.ttypes as _CommonTypes
        import DeviceManager.ttypes as _DeviceManagerTypes
        import LogSession.constants as _LogSessionConstants
        import LogSession.ttypes as _LogSessionTypes
        import QutsClient as _QutsClient
        import QutsService.constants as _QutsServiceConstants
    except ImportError as exc:
        raise RuntimeError(
            f"无法导入 QUTS 模块：{exc}。请安装 QUTS 或设置 QUTS_PYTHON_PATH={path!r}"
        ) from exc

    CommonTypes = _CommonTypes
    DeviceManagerTypes = _DeviceManagerTypes
    LogSessionConstants = _LogSessionConstants
    LogSessionTypes = _LogSessionTypes
    QutsClient = _QutsClient
    QutsServiceConstants = _QutsServiceConstants

    PACKET_TYPE_NAMES.clear()
    PACKET_TYPE_NAMES.update(
        {
            CommonTypes.DiagPacketType.LOG_PACKET: "LOG",
            CommonTypes.DiagPacketType.EVENT: "EVENT",
            CommonTypes.DiagPacketType.DEBUG_MSG: "MSG",
            CommonTypes.DiagPacketType.QTRACE: "QTRACE",
            CommonTypes.DiagPacketType.QSH_METRIC: "QSH_METRIC",
            CommonTypes.DiagPacketType.QSH_EVENT: "QSH_EVENT",
            CommonTypes.DiagPacketType.REQUEST: "REQUEST",
            CommonTypes.DiagPacketType.RESPONSE: "RESPONSE",
            CommonTypes.DiagPacketType.SUBSYS_REQUEST: "SUBSYS_REQ",
            CommonTypes.DiagPacketType.SUBSYS_RESPONSE: "SUBSYS_RESP",
            CommonTypes.DiagPacketType.SUBSYSV2_REQUEST: "SUBSYSV2_REQ",
            CommonTypes.DiagPacketType.SUBSYSV2_IMMEDIATE_RESPONSE: "SUBSYSV2_IRESP",
            CommonTypes.DiagPacketType.SUBSYSV2_DELAYED_RESPONSE: "SUBSYSV2_DRESP",
            CommonTypes.DiagPacketType.UNKNOWN_PACKET_TYPE: "UNKNOWN",
        }
    )
    ITEM_TYPE_MAP.clear()
    ITEM_TYPE_MAP.update(
        {
            "all": None,
            "diag-request": (CommonTypes.DiagPacketType.REQUEST, "Diag Requests"),
            "diag-response": (CommonTypes.DiagPacketType.RESPONSE, "Diag Responses"),
            "subsys-request": (CommonTypes.DiagPacketType.SUBSYS_REQUEST, "Subsystem Requests"),
            "subsys-response": (CommonTypes.DiagPacketType.SUBSYS_RESPONSE, "Subsystem Responses"),
            "subsysv2-request": (CommonTypes.DiagPacketType.SUBSYSV2_REQUEST, "SubsystemV2 Requests"),
            "subsysv2-response": (
                CommonTypes.DiagPacketType.SUBSYSV2_IMMEDIATE_RESPONSE,
                "SubsystemV2 Responses",
            ),
            "subsysv2-dresp": (
                CommonTypes.DiagPacketType.SUBSYSV2_DELAYED_RESPONSE,
                "SubsystemV2 Delayed Responses",
            ),
            "event": (CommonTypes.DiagPacketType.EVENT, "Event Reports"),
            "log": (CommonTypes.DiagPacketType.LOG_PACKET, "Log Packets"),
            "debug-msg": (CommonTypes.DiagPacketType.DEBUG_MSG, "Debug Messages"),
            "qtrace": (CommonTypes.DiagPacketType.QTRACE, "QTrace"),
            "qsh-metric": (CommonTypes.DiagPacketType.QSH_METRIC, "QSH Metrics"),
            "qsh-event": (CommonTypes.DiagPacketType.QSH_EVENT, "QSH Events"),
        }
    )
    _quts_ready = True


# ── 配置类 ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Config:
    """导出工具配置常量。"""
    STEP_SIZE: int = 5000  # 每批次拉取数据包数量
    VIEW_NAME: str = "diag_export_view"
    TIMEOUT_SECONDS: int = 600

    @property
    def return_flags(self) -> int:
        """配置需要从 QUTS API 返回的字段。"""
        ensure_quts_imported()
        return (
            CommonTypes.DiagReturnFlags.PACKET_ID
            | CommonTypes.DiagReturnFlags.PACKET_NAME
            | CommonTypes.DiagReturnFlags.PACKET_TYPE
            | CommonTypes.DiagReturnFlags.TIME_STAMP_STRING
            | CommonTypes.DiagReturnFlags.RECEIVE_TIME_STRING
            | CommonTypes.DiagReturnFlags.SUMMARY_TEXT
            | CommonTypes.DiagReturnFlags.PARSED_TEXT
            | CommonTypes.DiagReturnFlags.SUBSCRIPTION_ID
        )


CONFIG = Config()

# ── DataView 回调 ─────────────────────────────────────────────────────────────
class DataViewWatcher:
    """监视 DataView 构建状态的回调处理器。"""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.view_size = 0
        self.finished = False

    def callback(self, view_name: str, view_size: int, is_finished: bool) -> None:
        """QUTS DataView 更新回调。"""
        self.view_size = view_size
        if is_finished:
            self.finished = True
            self._event.set()

    def wait(self, timeout: int = 300) -> bool:
        """等待 DataView 构建完成。"""
        return self._event.wait(timeout=timeout)


# ── 工具函数 ──────────────────────────────────────────────────────────────────
def collect_log_files(input_path: str, *, strict: bool = True) -> list[str]:
    """
    扫描并返回 .qmdl2 / .qdss 文件列表，保持 .qmdl2 在前。

    Args:
        input_path: 输入文件或目录路径
        strict: False 时路径不存在返回 []（供 pipeline 调用）；True 时 CLI 行为

    Returns:
        符合条件的文件路径列表
    """
    p = Path(input_path)
    if p.is_file():
        if p.suffix.lower() in (".qmdl2", ".qdss"):
            return [str(p)]
        print(f"[警告] 文件 {p} 不是受支持的格式（.qmdl2 / .qdss），已跳过")
        return []
    if p.is_dir():
        files = sorted(p.rglob("*.qmdl2")) + sorted(p.rglob("*.qdss"))
        return [str(f) for f in files]
    msg = f"输入路径不存在：{input_path}"
    if strict:
        print(f"[错误] {msg}")
        sys.exit(1)
    return []


def open_log_session(quts_client: Any, file_path: str) -> Any:
    """
    根据文件类型选择合适的方式打开 LogSession。

    Args:
        quts_client: QUTS 客户端实例
        file_path: 日志文件路径

    Returns:
        LogSession 实例
    """
    ext = Path(file_path).suffix.lower()

    if ext == ".qdss":
        # .qdss 需要指定 QdssOpenFileOptions 以生成 Diag HDF
        qdss_opts = DeviceManagerTypes.QdssOpenFileOptions(
            generateDiagHDF=True,
            generateQdssHDF=True,
            waitForSyncPacket=True
        )
        adpl_opts = DeviceManagerTypes.AdplOpenFileOptions(
            generateDiagHDF=True,
            generateAdplHDF=True
        )
        ftype_opts = DeviceManagerTypes.FileTypeOpenOptions(adpl_opts, qdss_opts)
        open_opts = DeviceManagerTypes.OpenFileOptions(ftype_opts)
        return quts_client.openLogSessionWithAdvanceOptions({file_path}, open_opts)
    return quts_client.openLogSession([file_path])


# ── 类型别名 ──────────────────────────────────────────────────────────────────
TypeIdPair = tuple[str, list[str] | None]


# ── 过滤与格式化 ────────────────────────────────────────────────────────────────
def build_packet_filter(
    log_session: Any,
    type_id_pairs: list[TypeIdPair] | None = None
) -> tuple[Any, list[Any], list[TypeIdPair]]:
    """
    构建带过滤条件的 DataPacketFilter。

    Args:
        log_session: LogSession 实例
        type_id_pairs: 类型和ID的配对列表，如 [("log", ["0xB111"]), ("qtrace", ["107/1"])]

    Returns:
        (packet_filter, diag_handles, type_id_pairs)
    """
    device_list = log_session.getDeviceList()
    if not device_list:
        raise RuntimeError("LogSession 中未找到设备信息")

    proto_list = log_session.getProtocolList(device_list[0].deviceHandle)
    print(f"  [.] 协议列表: {[(p.protocolType, p.protocolHandle) for p in proto_list]}")

    diag_handles = [
        p.protocolHandle
        for p in proto_list
        if p.protocolType == CommonTypes.ProtocolType.PROT_DIAG
    ]
    if not diag_handles:
        raise RuntimeError("LogSession 中未找到 Diag 协议句柄")

    # 处理默认情况
    if type_id_pairs is None or len(type_id_pairs) == 0:
        type_id_pairs = [("all", None)]

    is_all_mode = any(t == "all" for t, _ in type_id_pairs)

    # 构建 DiagPacketFilter
    diag_filter = CommonTypes.DiagPacketFilter()
    diag_filter.idOrNameMask = {}

    if is_all_mode:
        # 导出所有类型
        all_types = [
            CommonTypes.DiagPacketType.LOG_PACKET,
            CommonTypes.DiagPacketType.EVENT,
            CommonTypes.DiagPacketType.DEBUG_MSG,
            CommonTypes.DiagPacketType.QTRACE,
            CommonTypes.DiagPacketType.REQUEST,
            CommonTypes.DiagPacketType.RESPONSE,
            CommonTypes.DiagPacketType.SUBSYS_REQUEST,
            CommonTypes.DiagPacketType.SUBSYS_RESPONSE,
        ]
        match_all = CommonTypes.DiagIdFilterItem(regexFilter=".*")
        for pkt_type in all_types:
            diag_filter.idOrNameMask[pkt_type] = [match_all]
        print("  [.] 过滤: 所有类型, 所有 ID")
    else:
        # 导出指定类型，每个类型有自己的 ID 列表
        filter_info = []
        for type_key, id_list in type_id_pairs:
            type_config = ITEM_TYPE_MAP.get(type_key)
            if not type_config:
                print(f"  [警告] 未知的 type: {type_key}，已忽略")
                continue

            target_type, type_desc = type_config

            if id_list:
                id_filter_items = [CommonTypes.DiagIdFilterItem(idOrName=id_str) for id_str in id_list]
                diag_filter.idOrNameMask[target_type] = id_filter_items
                filter_info.append(f"{type_desc}(ID={id_list})")
            else:
                match_all = CommonTypes.DiagIdFilterItem(regexFilter=".*")
                diag_filter.idOrNameMask[target_type] = [match_all]
                filter_info.append(f"{type_desc}(所有)")

        print(f"  [.] 过滤: {', '.join(filter_info)}")

    pkt_filter = LogSessionTypes.DataPacketFilter()
    pkt_filter.protocolHandleList = diag_handles
    pkt_filter.diagFilter = diag_filter

    return pkt_filter, diag_handles, type_id_pairs


def format_packet(
    pkt: Any,
    search_text: str | None = None,
    use_regex: bool = False,
    *,
    single_line: bool | None = None,
) -> str:
    """
    将单个 DiagPacket 格式化为文本。

    Args:
        pkt: 数据包对象
        search_text: 搜索关键词（可选）
        use_regex: 是否以正则表达式模式匹配（默认普通子字符串匹配）
        single_line: True 时一条 Diag 包占一行（供 log-search-read）；None 读环境变量

    Returns:
        格式化后的字符串，如果不匹配搜索条件则返回空字符串
    """
    if single_line is None:
        single_line = qcom_export_single_line()
    dp = pkt.diagPacket
    if dp is None:
        return ""

    # 获取原始文本用于搜索匹配
    raw_text_parts = []
    if dp.summaryText:
        raw_text_parts.append(dp.summaryText)
    if dp.parsedText:
        raw_text_parts.append(dp.parsedText)
    if dp.packetName:
        raw_text_parts.append(dp.packetName)
    raw_text = "\n".join(raw_text_parts)

    # 如果指定了搜索文本，检查是否匹配
    if search_text:
        if use_regex:
            if not re.search(search_text, raw_text, re.IGNORECASE):
                return ""
        else:
            if search_text.lower() not in raw_text.lower():
                return ""

    ptype_str = PACKET_TYPE_NAMES.get(dp.packetType, str(dp.packetType))
    pid_str = dp.packetId or ""
    pname_str = dp.packetName or ""
    ts_str = dp.timeStampString or dp.receiveTimeString or ""

    # 获取 subscriptionId (sub ID)
    sub_id = dp.subscriptionId if dp.subscriptionId is not None else -1
    sub_id_str = f" Sub={sub_id}" if sub_id >= 0 else ""

    header = f"[{ptype_str}] [{ts_str}] ID={pid_str}{sub_id_str}  {pname_str}"

    if single_line:
        parts = [header]
        if dp.summaryText and dp.summaryText.strip():
            parts.append(f"Summary: {collapse_log_text(dp.summaryText)}")
        if dp.parsedText and dp.parsedText.strip():
            parts.append(collapse_log_text(dp.parsedText))
        return " | ".join(parts)

    lines = [header]
    if dp.summaryText and dp.summaryText.strip():
        lines.append(f"  Summary: {dp.summaryText.strip()}")
    if dp.parsedText and dp.parsedText.strip():
        for ln in dp.parsedText.strip().splitlines():
            lines.append(f"  {ln}")
    lines.append("")  # 空行分隔
    return "\n".join(lines)


# ── 核心导出逻辑 ──────────────────────────────────────────────────────────────
def export_file(
    quts_client: Any,
    file_path: str,
    output_dir: str,
    type_id_pairs: list[TypeIdPair] | None = None,
    search_text: str | None = None,
    use_regex: bool = False,
    *,
    single_line: bool | None = None,
) -> str:
    """
    打开单个 log 文件，提取指定类型的 Diag 包并写入 txt。

    Args:
        quts_client: QUTS 客户端实例
        file_path: 日志文件路径
        output_dir: 输出目录
        type_id_pairs: 类型和ID的配对列表
        search_text: 搜索关键词（可选）
        use_regex: 是否以正则表达式模式匹配 search_text

    Returns:
        输出文件路径
    """
    if single_line is None:
        single_line = qcom_export_single_line()

    file_stem = Path(file_path).stem

    # 根据过滤条件构建输出文件名后缀
    if type_id_pairs is None or len(type_id_pairs) == 0:
        type_id_pairs = [("all", None)]

    is_all_mode = any(t == "all" for t, _ in type_id_pairs)

    if is_all_mode:
        type_suffix = ""
    else:
        type_parts = []
        id_parts = []

        for type_key, id_list in type_id_pairs:
            type_parts.append(type_key)
            if id_list:
                if len(id_list) == 1:
                    id_parts.append(id_list[0].replace("/", "_").replace("\\", "_"))
                else:
                    id_parts.append(f"{len(id_list)}ids")

        if len(type_parts) <= 3:
            type_abbr = "_".join(type_parts)
        else:
            type_abbr = "_".join(type_parts[:3]) + f"_etc{len(type_parts)}"

        type_suffix = f"_{type_abbr}"

        if id_parts:
            if len(id_parts) == 1:
                type_suffix += f"_{id_parts[0]}"
            else:
                type_suffix += "_ids"

    if search_text:
        safe_search = search_text.replace(" ", "_").replace("/", "_").replace("\\", "_")[:30]
        prefix = "re_" if use_regex else ""
        type_suffix += f"_search_{prefix}{safe_search}"

    output_path = str(Path(output_dir) / f"{file_stem}{type_suffix}.txt")

    print(f"\n{'='*70}")
    print(f"  输入: {file_path}")
    print(f"  输出: {output_path}")
    print(f"{'='*70}")

    t0 = time.time()

    log_session = open_log_session(quts_client, file_path)
    if not log_session or log_session == 0:
        raise RuntimeError(f"无法打开 LogSession：{file_path}")
    print(f"  [OK] LogSession 已加载  ({time.time()-t0:.1f}s)")

    pkt_filter, _, _ = build_packet_filter(log_session, type_id_pairs)

    # 配置返回字段
    diag_ret_cfg = CommonTypes.DiagReturnConfig()
    diag_ret_cfg.flags = CONFIG.return_flags
    diag_ret_cfg.diagTimeSorted = True

    pkt_ret_cfg = LogSessionTypes.PacketReturnConfig()
    pkt_ret_cfg.diagConfig = diag_ret_cfg

    # DataView 回调
    watcher = DataViewWatcher()
    quts_client.setOnDataViewUpdatedCallback(watcher.callback)

    log_session.createDataView(CONFIG.VIEW_NAME, pkt_filter, pkt_ret_cfg)

    print("  [..] 等待 DataView 构建完成...")
    if not watcher.wait(timeout=CONFIG.TIMEOUT_SECONDS):
        print("  [警告] DataView 等待超时，将尝试读取已有数据")

    # 用 getDataViewItemCount 取最终计数（比回调的 view_size 更准确）
    total = log_session.getDataViewItemCount(CONFIG.VIEW_NAME)
    print(f"  [OK] 共匹配 {total} 个数据包  ({time.time()-t0:.1f}s)")

    if total == 0:
        print("  [警告] 未找到任何数据包，请检查文件内容")
        log_session.removeDataView(CONFIG.VIEW_NAME)
        log_session.destroyLogSession()
        Path(output_path).write_text("(no packets found)\n", encoding="utf-8")
        return output_path

    # 分批读取并写入文件
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    matched_count = 0
    with open(output_path, "w", encoding="utf-8") as fout:
        fout.write("# 高通 Modem Log 导出\n")
        fout.write(f"# 源文件  : {file_path}\n")
        fout.write(f"# 数据包数: {total}\n")
        if search_text:
            mode_str = "正则" if use_regex else "普通"
            fout.write(f"# 搜索关键词: {search_text} ({mode_str}匹配)\n")
        fout.write(f"# 导出时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        if single_line:
            fout.write("# 格式: 每条 Diag 包一行（Summary/Parsed 内换行已合并，供 log-search-read 按行搜索）\n")
        fout.write("=" * 70 + "\n\n")

        pkt_range = LogSessionTypes.PacketRange()
        pkt_range.indexType = LogSessionTypes.IndexType.DATA_VIEW_INDEX
        written = 0

        while written < total:
            pkt_range.beginIndex = written
            pkt_range.endIndex = min(written + CONFIG.STEP_SIZE, total)
            packets = log_session.getDataViewItems(CONFIG.VIEW_NAME, pkt_range)
            if not packets:
                print(f"\n  [警告] getDataViewItems 返回空列表（beginIndex={written}），停止迭代")
                break
            for pkt in packets:
                line = format_packet(
                    pkt,
                    search_text=search_text,
                    use_regex=use_regex,
                    single_line=single_line,
                )
                if line:
                    fout.write(line + "\n")
                    matched_count += 1
            written += len(packets)
            pct = written / total * 100
            print(f"\r  [..] 导出进度: {written}/{total}  ({pct:.1f}%)", end="", flush=True)

        if search_text:
            fout.write(f"\n# 搜索完成: 共 {matched_count} 个数据包匹配 '{search_text}'\n")

    print(f"\n  [OK] 写入完成  ({time.time()-t0:.1f}s)", end="")
    if search_text:
        print(f"，匹配 {matched_count} 个包含 '{search_text}' 的数据包")

    log_session.removeDataView(CONFIG.VIEW_NAME)
    log_session.destroyLogSession()
    return output_path


# ── 参数解析 ───────────────────────────────────────────────────────────────────
def parse_type_id_pairs(
    type_list: list[str] | None,
    id_list: list[str] | None
) -> list[TypeIdPair]:
    """
    解析 type 和 id 的配对关系。

    关键规则：
      - --type 可以展开（逗号分隔），如 --type log,qtrace 展开为 2 个 type
      - --id 参数与 --type 参数按出现顺序一一对应
      - 每个 --id 可以是逗号分隔的多个 ID，这些 ID 都属于对应的 type

    Args:
        type_list: --type 参数列表，每个元素支持逗号分隔
        id_list: --id 参数列表，每个元素支持逗号分隔

    Returns:
        类型和ID的配对列表
    """
    if type_list or id_list:
        ensure_quts_imported()

    # 第一步：展开所有 type
    if not type_list:
        expanded_types = ["all"]
    else:
        expanded_types = []
        for type_str in type_list:
            for t in type_str.split(","):
                t = t.strip()
                if t:
                    if t not in ITEM_TYPE_MAP:
                        print(f"[警告] 未知的 type: '{t}'，将被忽略")
                        continue
                    expanded_types.append(t)
        if not expanded_types:
            expanded_types = ["all"]

    # 第二步：解析 id 参数
    if not id_list:
        id_groups = None
    else:
        id_groups = []
        for id_str in id_list:
            if id_str:
                ids = [s.strip() for s in id_str.split(",") if s.strip()]
                if ids:
                    id_groups.append(ids)
        if not id_groups:
            id_groups = None

    # 第三步：构建配对
    if "all" in expanded_types:
        if id_groups:
            print("[错误] 使用 --id 参数时必须指定具体的 --type，不能是 'all'")
            print("       例如: --type log --id 0xB111")
            sys.exit(1)
        return [("all", None)]

    # 指定了具体类型
    if id_groups is None:
        return [(t, None) for t in expanded_types]
    if len(expanded_types) == 1:
        all_ids = []
        for group in id_groups:
            all_ids.extend(group)
        return [(expanded_types[0], all_ids)]
    if len(id_groups) == 1:
        return [(t, id_groups[0]) for t in expanded_types]
    if len(expanded_types) == len(id_groups):
        return list(zip(expanded_types, id_groups))

    print("[错误] --type 和 --id 的数量不匹配")
    print(f"       类型数量: {len(expanded_types)} ({expanded_types})")
    print(f"       ID 参数数量: {len(id_groups)}")
    sys.exit(1)


# ── 主程序 ─────────────────────────────────────────────────────────────────────
def create_argument_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="将高通 modem log（.qmdl2 / .qdss）导出为 txt 文件",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
支持的 Item Type (--type):
  all (默认)           - 所有类型
  diag-request         - Diag Requests
  diag-response        - Diag Responses
  subsys-request       - Subsystem Requests
  subsys-response      - Subsystem Responses
  event                - Event Reports
  log                  - Log Packets
  debug-msg            - Debug Messages / F3 Messages
  qtrace               - QTrace 数据

示例：
  # 导出所有
  python export_modem_log.py mdlog/

  # 导出单个类型
  python export_modem_log.py mdlog/ --type log

  # 导出单个类型并指定 ID
  python export_modem_log.py mdlog/ --type log --id 0xB111

  # 导出多个类型，每个类型指定不同的 ID
  python export_modem_log.py mdlog/ --type log --id 0x184E,0xB132 --type qtrace --id 107/1

  # 内容搜索
  python export_modem_log.py mdlog/ --search vsim_dbg
        """
    )
    parser.add_argument("input", help="输入的 .qmdl2 / .qdss 文件或目录")
    parser.add_argument("output", nargs="?", default=None, help="输出目录")
    parser.add_argument(
        "--type",
        dest="item_type",
        action="append",
        default=None,
        help="要导出的 Item Type（可多次使用，或与 --id 配对使用）"
    )
    parser.add_argument(
        "--id",
        dest="item_ids",
        action="append",
        default=None,
        help="指定要过滤的 ID（与 --type 配对使用）"
    )
    parser.add_argument(
        "--search",
        dest="search_text",
        default=None,
        help="搜索关键词（可选），只导出包含该关键词的数据包（不区分大小写）"
    )
    parser.add_argument(
        "--regex",
        dest="use_regex",
        action="store_true",
        default=False,
        help="将 --search 的关键词作为正则表达式处理（不区分大小写）"
    )
    parser.add_argument(
        "--quts-path",
        default=None,
        help="手动指定 QUTS Support/python 路径"
    )
    parser.add_argument(
        "--multiline",
        action="store_true",
        default=False,
        help="每条 Diag 包多行输出（默认单行，便于 log-search-read）",
    )
    return parser


def run_batch_export(
    input_path: str,
    output_dir: str,
    *,
    type_id_pairs: list[TypeIdPair] | None = None,
    search_text: str | None = None,
    use_regex: bool = False,
    quts_python_path: str | None = None,
    single_line: bool | None = None,
) -> dict:
    """
    批量导出 .qmdl2 / .qdss 为 txt（供 pipeline 进程内直接调用）。

    Returns:
        {
          "success": bool,
          "output_dir": str,
          "txt_files": [str, ...],
          "errors": [{"file": str, "error": str}, ...],
        }
    """
    ensure_quts_imported(quts_python_path)

    input_path = os.path.abspath(input_path)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if type_id_pairs is None:
        type_id_pairs = [("all", None)]

    log_files = collect_log_files(input_path, strict=False)
    if not log_files:
        return {
            "success": False,
            "output_dir": output_dir,
            "txt_files": [],
            "errors": [{"error": "未找到任何 .qmdl2 / .qdss 文件"}],
        }

    quts_client = QutsClient.QutsClient(
        "ModemLogExporter",
        "127.0.0.1",
        QutsServiceConstants.QUTS_REGISTRATION_PORT,
        False,
        False,
        CommonTypes.QutsOperatingMode.POST_PROCESSING,
    )

    txt_files: list[str] = []
    errors: list[dict] = []
    for file_path in log_files:
        try:
            out_path = export_file(
                quts_client,
                file_path,
                output_dir,
                type_id_pairs,
                search_text=search_text,
                use_regex=use_regex,
                single_line=single_line,
            )
            if out_path and os.path.isfile(out_path):
                txt_files.append(os.path.abspath(out_path))
        except Exception as exc:
            errors.append({"file": file_path, "error": str(exc)})

    try:
        quts_client.stop()
    except Exception:
        pass

    return {
        "success": bool(txt_files),
        "output_dir": output_dir,
        "txt_files": txt_files,
        "errors": errors,
    }


def main() -> None:
    """主入口函数。"""
    parser = create_argument_parser()
    parser.add_argument(
        "--worker-json",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--input",
        dest="worker_input",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--output",
        dest="worker_output",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args()

    if args.worker_json:
        input_path = args.worker_input or args.input
        output_dir = args.worker_output or args.output
        if not input_path:
            print(json.dumps({"success": False, "error": "missing --input"}, ensure_ascii=False))
            sys.exit(1)
        try:
            ensure_quts_imported(args.quts_path)
        except RuntimeError as exc:
            print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
            sys.exit(1)
        type_id_pairs = parse_type_id_pairs(args.item_type, args.item_ids)
        if args.use_regex and not args.search_text:
            payload = {"success": False, "error": "--regex 必须与 --search 一起使用"}
            print(json.dumps(payload, ensure_ascii=False))
            sys.exit(1)
        if not output_dir:
            input_abs = os.path.abspath(input_path)
            output_dir = (
                input_abs.rstrip("/\\") + "_output"
                if os.path.isdir(input_abs)
                else str(Path(input_abs).parent / "output")
            )
        single_line = not args.multiline
        payload = run_batch_export(
            input_path,
            output_dir,
            type_id_pairs=type_id_pairs,
            search_text=args.search_text,
            use_regex=args.use_regex,
            quts_python_path=args.quts_path,
            single_line=single_line,
        )
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        sys.exit(0 if payload.get("success") else 1)

    # 解析 type 和 id 的配对关系
    type_id_pairs = parse_type_id_pairs(args.item_type, args.item_ids)

    # 验证：--regex 必须配合 --search 使用
    if args.use_regex and not args.search_text:
        print("[错误] --regex 必须与 --search 一起使用")
        sys.exit(1)

    # 统计信息
    config_info = f"[配置] 类型-ID 配对: {[(t, ids if ids else '所有') for t, ids in type_id_pairs]}"
    if args.search_text:
        mode = "正则" if args.use_regex else "普通"
        config_info += f"\n       搜索关键词: '{args.search_text}' ({mode}匹配)"
    print(config_info)

    try:
        ensure_quts_imported(args.quts_path)
    except RuntimeError as exc:
        print(f"[错误] {exc}")
        sys.exit(1)

    # 确定输出目录
    input_path = os.path.abspath(args.input)
    if args.output:
        output_dir = os.path.abspath(args.output)
    else:
        if os.path.isdir(input_path):
            output_dir = input_path.rstrip("/\\") + "_output"
        else:
            output_dir = str(Path(input_path).parent / "output")

    log_files = collect_log_files(input_path)
    if not log_files:
        print("[错误] 未找到任何 .qmdl2 / .qdss 文件")
        sys.exit(1)

    print(f"找到 {len(log_files)} 个 log 文件，输出目录：{output_dir}")

    # 初始化 QUTS 客户端
    quts_client = QutsClient.QutsClient(
        "ModemLogExporter",
        "127.0.0.1",
        QutsServiceConstants.QUTS_REGISTRATION_PORT,
        False,
        False,
        CommonTypes.QutsOperatingMode.POST_PROCESSING
    )
    print("[OK] QUTS 客户端已初始化（后处理模式）")

    single_line = not args.multiline
    results = []
    errors = []
    for f in log_files:
        try:
            out = export_file(
                quts_client,
                f,
                output_dir,
                type_id_pairs,
                search_text=args.search_text,
                use_regex=args.use_regex,
                single_line=single_line,
            )
            results.append(out)
        except Exception as e:
            print(f"\n[错误] 处理 {f} 时出现异常：{e}")
            traceback.print_exc()
            errors.append(f)

    quts_client.stop()

    print(f"\n{'='*70}")
    print(f"导出完成：成功 {len(results)} 个，失败 {len(errors)} 个")
    for r in results:
        print(f"  [OK] {r}")
    for e in errors:
        print(f"  [FAIL] {e}")


if __name__ == "__main__":
    main()
