from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from web_app.failure_triage import parse_failure_triage


class FailureTriageParseTests(unittest.TestCase):
    def test_parse_retry_yaml(self):
        text = """
verdict: retry
reason: 把整个 GKI 函数贴进了 vendor 文件
advice: 若再失败，对照 .rej 只合 +/-
retry_hint: 不要整段替换 mtk_i2c_transfer，只把 .rej 的 +/- 合进现有函数
"""
        t = parse_failure_triage(text)
        self.assertEqual(t.verdict, "retry")
        self.assertIn("GKI 函数", t.reason)
        self.assertIn("mtk_i2c_transfer", t.retry_hint)

    def test_parse_manual_and_drop_hint(self):
        text = """```yaml
verdict: manual
reason: 本地映射盘不可达
advice: 检查 Z: 映射是否与编译目录一致
retry_hint: 应被忽略
```"""
        t = parse_failure_triage(text)
        self.assertEqual(t.verdict, "manual")
        self.assertEqual(t.retry_hint, "")
        self.assertIn("Z:", t.advice)

    def test_retry_without_hint_uses_reason(self):
        t = parse_failure_triage("verdict: retry\nreason: diff 上下文对不上\nadvice: 对照磁盘重试")
        self.assertEqual(t.verdict, "retry")
        self.assertEqual(t.retry_hint, "diff 上下文对不上")

    def test_unknown_verdict_is_manual(self):
        t = parse_failure_triage("verdict: maybe\nreason: 不清楚")
        self.assertEqual(t.verdict, "manual")
