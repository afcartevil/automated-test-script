from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

PYTHON_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TOOL_DIRNAME = "gms_{suite}"
TRADEFED_SCRIPT = {
    "cts": "cts-tradefed",
    "gts": "gts-tradefed",
    "vts": "vts-tradefed",
}

TRADEFED_END_MARKERS = (
    "============== End of Results ==============",
    "=================== End ====================",
)

TRADEFED_REAP_TIMEOUT_SEC = 15.0

_SUMMARY_FAILED_RE = re.compile(r"FAILED\s*:\s*(\d+)", re.IGNORECASE)
_SUMMARY_PASSED_RE = re.compile(r"PASSED\s*:\s*(\d+)", re.IGNORECASE)
_MODULE_RUN_FAILURE_RE = re.compile(r"Module\(s\) with run failure", re.IGNORECASE)
_MODULES_COMPLETED_RE = re.compile(r"(\d+)/(\d+)\s+modules completed", re.IGNORECASE)
_XML_FAILED_ATTR_RE = re.compile(
    r'\b(?:failed|failures)\s*=\s*["\'](\d+)["\']', re.IGNORECASE
)


_RESULT_DIR_RE = re.compile(r"RESULT\s+DIRECTORY\s*:\s*(.+)", re.IGNORECASE)
_LOG_DIR_RE = re.compile(r"LOG\s+DIRECTORY\s*:\s*(.+)", re.IGNORECASE)


@dataclass(frozen=True)
class TradefedArtifactPaths:
    result_dir: str | None = None
    log_dir: str | None = None
    test_result_html: str | None = None
    test_result_xml: str | None = None
    console_log: str | None = None


@dataclass(frozen=True)
class TradefedLogAnalysis:
    finished: bool
    passed: bool | None
    reason: str
    failed_count: int | None = None
    passed_count: int | None = None
    has_module_run_failure: bool = False


def tradefed_log_finished(log_text: str) -> bool:
    return any(marker in log_text for marker in TRADEFED_END_MARKERS)


def _summary_block(log_text: str) -> str:
    start = log_text.find("=============== Summary ===============")
    if start >= 0:
        return log_text[start:]
    start = log_text.find("================= Results ==================")
    if start >= 0:
        return log_text[start:]
    return log_text


def _parse_xml_failed_count(log_text: str) -> int | None:
    if "<" not in log_text:
        return None
    matches = [int(value) for value in _XML_FAILED_ATTR_RE.findall(log_text)]
    if matches:
        return max(matches)
    try:
        root = ET.fromstring(log_text)
    except ET.ParseError:
        return None
    for element in root.iter():
        for attr in ("failed", "failures", "fail"):
            raw = element.attrib.get(attr)
            if raw is not None and str(raw).isdigit():
                return int(raw)
    return None


def analyze_tradefed_log(log_text: str) -> TradefedLogAnalysis:
    text = log_text or ""
    finished = tradefed_log_finished(text)
    summary = _summary_block(text)

    failed_match = _SUMMARY_FAILED_RE.search(summary)
    passed_match = _SUMMARY_PASSED_RE.search(summary)
    failed_count = int(failed_match.group(1)) if failed_match else None
    passed_count = int(passed_match.group(1)) if passed_match else None
    has_module_failure = bool(_MODULE_RUN_FAILURE_RE.search(summary))

    modules_completed = None
    modules_total = None
    modules_match = _MODULES_COMPLETED_RE.search(summary)
    if modules_match:
        modules_completed = int(modules_match.group(1))
        modules_total = int(modules_match.group(2))

    if failed_count is None and "<" in text:
        xml_failed = _parse_xml_failed_count(text)
        if xml_failed is not None:
            failed_count = xml_failed

    if not finished:
        return TradefedLogAnalysis(
            finished=False,
            passed=None,
            reason="未检测到 Tradefed 结束标记（End of Results）",
            failed_count=failed_count,
            passed_count=passed_count,
            has_module_run_failure=has_module_failure,
        )

    if failed_count is None and not has_module_failure and modules_completed is None:
        return TradefedLogAnalysis(
            finished=True,
            passed=None,
            reason="已结束但未解析到 Summary 统计",
            failed_count=failed_count,
            passed_count=passed_count,
            has_module_run_failure=has_module_failure,
        )

    if failed_count is not None and failed_count > 0:
        return TradefedLogAnalysis(
            finished=True,
            passed=False,
            reason=f"FAILED={failed_count}",
            failed_count=failed_count,
            passed_count=passed_count,
            has_module_run_failure=has_module_failure,
        )

    if has_module_failure:
        return TradefedLogAnalysis(
            finished=True,
            passed=False,
            reason="存在 Module(s) with run failure",
            failed_count=failed_count,
            passed_count=passed_count,
            has_module_run_failure=True,
        )

    if (
        modules_completed is not None
        and modules_total is not None
        and modules_completed < modules_total
    ):
        return TradefedLogAnalysis(
            finished=True,
            passed=False,
            reason=f"仅 {modules_completed}/{modules_total} modules completed",
            failed_count=failed_count,
            passed_count=passed_count,
            has_module_run_failure=has_module_failure,
        )

    return TradefedLogAnalysis(
        finished=True,
        passed=True,
        reason=(
            f"PASSED={passed_count if passed_count is not None else '?'}"
            f", FAILED={failed_count if failed_count is not None else 0}"
        ),
        failed_count=failed_count,
        passed_count=passed_count,
        has_module_run_failure=has_module_failure,
    )


def _resolve_artifact_paths(
    suite_root: Path, stdout_log: str, console_log: Path
) -> TradefedArtifactPaths:
    _ = suite_root  # 保留签名，避免大范围改调用处
    result_dir = None
    log_dir = None

    result_match = _RESULT_DIR_RE.search(stdout_log)
    if result_match:
        result_dir = result_match.group(1).strip()

    log_match = _LOG_DIR_RE.search(stdout_log)
    if log_match:
        log_dir = log_match.group(1).strip()

    result_dir_path: Path | None = None
    if result_dir:
        candidate = Path(result_dir).expanduser()
        if candidate.is_dir():
            result_dir_path = candidate

    test_result_html = None
    test_result_xml = None
    if result_dir_path is not None:
        html_path = result_dir_path / "test_result.html"
        xml_path = result_dir_path / "test_result.xml"
        if html_path.is_file():
            test_result_html = str(html_path)
        if xml_path.is_file():
            test_result_xml = str(xml_path)

    console_log_path = str(console_log) if console_log.is_file() else None
    return TradefedArtifactPaths(
        result_dir=result_dir,
        log_dir=log_dir,
        test_result_html=test_result_html,
        test_result_xml=test_result_xml,
        console_log=console_log_path,
    )


def _format_artifact_paths(paths: TradefedArtifactPaths) -> str:
    lines: list[str] = ["测试产物:"]
    if paths.log_dir:
        lines.append(f"- 日志目录: {paths.log_dir}")
    if paths.test_result_html:
        lines.append(f"- HTML 报告: {paths.test_result_html}")
    return "\n".join(lines) if len(lines) > 1 else ""


class _GmsStepReporter:
    """GMS 子步骤输出，与其他自检用例保持 begin/on_step 风格一致。"""

    def __init__(self, step_update) -> None:
        self._step_update = step_update
        self._committed = ""

    def _emit(self, preview: str | None = None) -> None:
        if not callable(self._step_update):
            return
        text = preview if preview is not None else self._committed
        self._step_update(text.strip())

    def note(self, text: str) -> None:
        self._committed += f"\n{text}"
        self._emit()

    def begin(self, text: str) -> None:
        self._emit(self._committed + f"\n{text}")

    def complete(self, text: str, ok: bool) -> None:
        self._committed += f"\n{text}{'-成功' if ok else '-失败'}"
        self._emit()

def _reap_tradefed_process(
    proc: subprocess.Popen[str], timeout_sec: float = TRADEFED_REAP_TIMEOUT_SEC
) -> None:
    """Tradefed 打印结束标记后子进程可能长期不退出，限时回收避免阻塞。"""
    if proc.stdout and not proc.stdout.closed:
        proc.stdout.close()
    if proc.poll() is not None:
        return
    try:
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def _device_serial(device_info: dict) -> str:
    dut = device_info.get("DUT") if isinstance(device_info, dict) else None
    if isinstance(dut, list) and dut:
        serial = dut[0].get("device_id") or dut[0].get("deviceId")
        if serial:
            return str(serial)
    if isinstance(device_info, dict):
        serial = device_info.get("deviceId") or device_info.get("device_id")
        if serial:
            return str(serial)
    raise ValueError("缺少测试机设备序列号")


def _bundled_tool_root(suite: str) -> Path:
    return PYTHON_ROOT / "tools" / DEFAULT_TOOL_DIRNAME.format(suite=suite)


def _launcher_candidates_in_tools_dir(tools_dir: Path, suite: str) -> list[Path]:
    script_name = TRADEFED_SCRIPT.get(suite, f"{suite}-tradefed")
    return [tools_dir / script_name]


def _resolve_launcher_file(path: Path, suite: str) -> Path | None:
    resolved = path.expanduser()
    if resolved.is_dir():
        for candidate in _launcher_candidates_in_tools_dir(resolved / "tools", suite):
            if candidate.is_file():
                return candidate.resolve()
        return None

    if resolved.is_file():
        return resolved.resolve()
    return None


def resolve_launcher(suite: str, device_info: dict | None) -> Path | None:
    info = device_info or {}
    configured_paths = info.get("gmsTradefedPath")
    if not isinstance(configured_paths, dict):
        configured_paths = info.get("gmsTradefedRoot")
    if isinstance(configured_paths, dict):
        custom = configured_paths.get(suite)
        if custom:
            launcher = _resolve_launcher_file(Path(str(custom)), suite)
            if launcher is not None:
                return launcher

    tools_dir = _bundled_tool_root(suite) / "tools"
    for candidate in _launcher_candidates_in_tools_dir(tools_dir, suite):
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_suite_root(launcher: Path) -> Path:
    if launcher.parent.name == "tools":
        return launcher.parent.parent
    return launcher.parent


def _bundled_subplans_dir(suite: str) -> Path:
    return _bundled_tool_root(suite) / "subplans"


def _ensure_subplan(suite_root: Path, suite: str, subplan: str) -> Path | None:
    """确保 subplan XML 存在于套件根目录 subplans/ 下。"""
    subplan_file = f"{subplan}.xml" if not subplan.endswith(".xml") else subplan
    target = suite_root / "subplans" / subplan_file
    if target.is_file():
        return target

    bundled = _bundled_subplans_dir(suite) / subplan_file
    if bundled.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled, target)
        return target
    return None


def _infer_suite_from_plan(plan: str) -> str | None:
    name = plan.strip().lower()
    if name.endswith(".xml"):
        name = name[:-4]
    for suite in TRADEFED_SCRIPT:
        if name.endswith(f"-{suite}-plan"):
            return suite
    return None


def _build_tradefed_cmd(
    launcher: Path, subplan_name: str, serial: str
) -> list[str]:
    args = ["run", subplan_name, "-s", serial]
    return [str(launcher), *args]


def run_gms_subplan(
    subplan: str,
    device_info: dict | None = None,
    step_update=None,
) -> dict:
    subplan = str(subplan).strip()
    suite = _infer_suite_from_plan(subplan)
    if suite is None:
        return {
            "status": "fail",
            "message": f"无法从 plan 名称推断 GMS 套件: {subplan}",
            "full_automation": True,
        }

    info = device_info or {}
    serial = _device_serial(info)
    launcher = resolve_launcher(suite, info)
    if launcher is None:
        script_name = TRADEFED_SCRIPT[suite]
        return {
            "status": "fail",
            "message": (
                f"未配置或未找到 {script_name}，请在 GMS 测试设置中填写 "
                f"gmsTradefedPath.{suite}（Linux 环境下 {script_name} 的完整路径）"
            ),
            "full_automation": True,
        }

    suite_root = resolve_suite_root(launcher)
    subplan_path = _ensure_subplan(suite_root, suite, subplan)
    if subplan_path is None:
        return {
            "status": "fail",
            "message": (
                f"subplan 不存在: {subplan}（期望 {suite_root / 'subplans'}，"
                f"或仓库内置 {_bundled_subplans_dir(suite)})"
            ),
            "full_automation": True,
        }

    steps = _GmsStepReporter(step_update)

    subplan_name = subplan[:-4] if subplan.endswith(".xml") else subplan
    steps.note("运行信息:")
    steps.note(f"- Plan: {subplan_name}")
    steps.note(f"- 设备: {serial}")
    cmd = _build_tradefed_cmd(launcher, subplan_name, serial)

    log_dir = suite_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{suite}_{subplan_name}_{serial}.log"

    log_chunks: list[str] = []
    steps.begin("执行 Tradefed")

    try:
        with log_path.open("w", encoding="utf-8") as log_file:
            proc = subprocess.Popen(
                cmd,
                cwd=str(suite_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            assert proc.stdout is not None
            for line in proc.stdout:
                log_file.write(line)
                log_chunks.append(line)
                if tradefed_log_finished("".join(log_chunks)):
                    break
            _reap_tradefed_process(proc)
    except Exception as exc:
        steps.complete("执行 Tradefed", False)
        steps.note(f"异常: {exc}")
        return {
            "status": "fail",
            "message": str(exc),
            "full_automation": True,
        }

    steps.complete("执行 Tradefed", True)

    stdout_log = "".join(log_chunks)
    combined_log = stdout_log

    artifact_paths = _resolve_artifact_paths(suite_root, combined_log, log_path)
    analysis = analyze_tradefed_log(combined_log)
    path_text = _format_artifact_paths(artifact_paths)

    steps.begin("解析测试结果")
    if not analysis.finished:
        steps.complete("解析测试结果", False)
        steps.note(f"判定: {analysis.reason}")
        if path_text:
            steps.note(path_text)
        return {
            "status": "fail",
            "message": _join_message(analysis.reason, path_text),
            "full_automation": True,
        }

    steps.complete("解析测试结果", True)
    if analysis.passed_count is not None or analysis.failed_count is not None:
        passed_text = analysis.passed_count if analysis.passed_count is not None else "?"
        failed_text = analysis.failed_count if analysis.failed_count is not None else "?"
        steps.note(f"统计: PASSED={passed_text}, FAILED={failed_text}")

    if analysis.passed is True:
        steps.complete("测试判定", True)
        steps.note(f"判定: {analysis.reason}")
        if path_text:
            steps.note(path_text)
        return {
            "status": "pass",
            "message": _join_message(analysis.reason, path_text),
            "full_automation": True,
        }

    if analysis.passed is False:
        steps.complete("测试判定", False)
        steps.note(f"判定: {analysis.reason}")
        if path_text:
            steps.note(path_text)
        return {
            "status": "fail",
            "message": _join_message(analysis.reason, path_text),
            "full_automation": True,
        }

    steps.complete("测试判定", False)
    steps.note(f"判定: {analysis.reason}")
    if path_text:
        steps.note(path_text)
    return {
        "status": "fail",
        "message": _join_message(analysis.reason, path_text),
        "full_automation": True,
    }


def _join_message(*parts: str) -> str:
    chunks = [part.strip() for part in parts if part and part.strip()]
    return "\n\n".join(chunks)