import json
from pathlib import Path
from datetime import datetime
from src.utils.adb.adb_utils import getprop


class ReportCollector:
    def __init__(self, output_path):
        self.output_path = Path(output_path)
        self.start_time = datetime.now()
        # nodeid -> 用例最终结果；重跑时后写覆盖先写，保证以最后一次执行为准
        self.results = {}
        # nodeid -> 最近一次执行收集到的 warning 文案列表（每次执行开始时重置）
        self.warnings_map = {}
        self._init_data()

    def _init_data(self):
        """初始化报告数据结构"""
        self.data = {
            "AlltestCase": [],
            "failed": [],
            "ignore": [],
            "warning": [],
            "status": "ok",
            "versionNum": "",
            "detail": "success",
            "summary": {
                "totalTime": "0s",
                "totalNum": 0,
                "ignored": 0,
                "warning": 0,
                "failedCount": 0,
                "passRate": "0%",
            },
        }

    def finalize(self):
        """将按 nodeid 暂存的结果与 warning 汇总进最终报告数据结构。

        统一在 session 结束时汇总，可天然兼容 pytest-rerunfailures：
        重跑时同一 nodeid 的结果会被最后一次执行覆盖，warning 也只保留最后一次执行的内容。
        """
        for nodeid, record in self.results.items():
            base = {
                "testCaseName": record["testCaseName"],
                "excuteTime": record["excuteTime"],
            }
            self.data["AlltestCase"].append(base)
            self.data["summary"]["totalNum"] += 1

            outcome = record.get("outcome")
            if outcome == "failed":
                self.data["failed"].append({**base, "reason": record.get("reason", "")})
                self.data["summary"]["failedCount"] += 1
            elif outcome == "skipped":
                self.data["ignore"].append({**base, "reason": record.get("reason", "")})
                self.data["summary"]["ignored"] += 1

            # warning 与最终通过/失败状态相互独立：passed 用例同样可能携带 warning
            for message in self.warnings_map.get(nodeid, []):
                self.data["warning"].append({**base, "reason": message})
                self.data["summary"]["warning"] += 1


def pytest_unconfigure(config):
    """生成最终报告文件"""
    collector = config._report
    collector.finalize()
    device_serial = config.getoption("--device-serial", None)
    elapsed = int((datetime.now() - collector.start_time).total_seconds())
    summary = collector.data["summary"]

    # 计算统计指标
    passed = summary["totalNum"] - summary["failedCount"] - summary["ignored"]
    summary.update(
        {
            "totalTime": f"{elapsed}s",
            "passRate": (
                f"{passed / summary['totalNum'] * 100:.0f}%"
                if summary["totalNum"]
                else "0%"
            ),
        }
    )
    collector.data["versionNum"] = getprop("ro.build.display.id", device_serial)
    # 设置状态
    if summary["failedCount"] > 0:
        collector.data.update(
            {"status": "failed", "detail": f"{summary['failedCount']} tests failed"}
        )

    # 确保目录存在
    collector.output_path.parent.mkdir(parents=True, exist_ok=True)

    # 写入文件
    with open(collector.output_path, "w", encoding="utf-8") as f:
        json.dump(collector.data, f, indent=2, ensure_ascii=False)
