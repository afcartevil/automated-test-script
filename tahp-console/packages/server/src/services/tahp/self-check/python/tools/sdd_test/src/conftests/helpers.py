from datetime import datetime


def _extract_error(report) -> str:
    """提取断言错误信息"""
    if not (traceback := getattr(report, "longrepr", None)):
        return "Assertion failed"

    for line in reversed(str(traceback).split("\n")):
        if "AssertionError:" in line:
            return line.split("AssertionError:", 1)[-1].strip()
        if "AssertionError" in line:
            return line.split("AssertionError", 1)[-1].strip()

    return line.strip() if (line := str(traceback).split("\n")[-1]) else "Unknown error"


def _get_skip_reason(item, report=None) -> str:
    """获取跳过原因（优先 marker，其次 report 输出）"""
    if marker := item.get_closest_marker("skip"):
        if reason := marker.kwargs.get("reason", ""):
            return reason
    if report is not None and report.longrepr is not None:
        text = str(report.longrepr).strip()
        if text.startswith("Skipped:"):
            return text.removeprefix("Skipped:").strip()
        if text.startswith("SKIPPED"):
            for line in text.splitlines():
                if line.startswith("Skipped:"):
                    return line.removeprefix("Skipped:").strip()
    return ""


def _record_test_result(item, report, collector) -> None:
    """暂存单条用例结果，重跑场景下后写覆盖先写，以最后一次执行结果为准。

    不再做 session 内累加，统一交由 ReportCollector.finalize() 汇总，
    这样 pytest-rerunfailures 重跑成功后能正确翻正之前记录的失败。
    """
    record = {
        "testCaseName": item.nodeid.split("::")[-1],
        "excuteTime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "outcome": report.outcome,
    }

    if report.outcome == "failed":
        record["reason"] = _extract_error(report)
    elif report.outcome == "skipped":
        record["reason"] = _get_skip_reason(item, report)

    collector.results[item.nodeid] = record


def _record_warning(nodeid, message, collector) -> None:
    """记录某个用例本次执行产生的一条 warning 文案。"""
    if not nodeid:
        return
    collector.warnings_map.setdefault(nodeid, []).append(message)


def _reset_warnings(nodeid, collector) -> None:
    """在用例（含重跑）开始执行时清空已暂存的 warning，仅保留最后一次执行的内容。"""
    if not nodeid:
        return
    collector.warnings_map.pop(nodeid, None)
