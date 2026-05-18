#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAHP Skill 评估器 (evaluate.py)

功能: Skill执行评估——运行测试用例并对比预期结果
来源: TAHP-评估与质量门禁规范 §4-§6

此脚本负责:
1. 从 constraints/<module>/eval-data/cases/ 读取测试用例
2. 从 constraints/<module>/eval-data/expected/ 读取预期输出
3. 执行Skill并对比实际输出与预期
4. 计算评估指标（准确率、通过率等）
5. 输出评估报告到 reports/quality-metrics/

评估策略 (三级自动/半自动/人工):
- 全自动 (准确率 > 95%): 自动通过
- 半自动 (准确率 70-95%): 需人工复核
- 人工 (准确率 < 70%): 需人工介入

用法:
    python evaluate.py --module telephony --domain bug-analysis
    python evaluate.py --module display --domain code-adapter --strategy auto
"""

import sys
import argparse
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.syntax import Syntax

# 全局控制台实例
console = Console()


class EvaluationStrategy(Enum):
    """评估策略枚举"""
    FULL_AUTO = "full_auto"      # 全自动 (准确率 > 95%)
    SEMI_AUTO = "semi_auto"      # 半自动 (准确率 70-95%)
    MANUAL = "manual"            # 人工 (准确率 < 70%)


@dataclass
class TestCase:
    """测试用例数据类"""
    id: str
    name: str
    input_data: Dict[str, Any]
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, file_path: Path) -> 'TestCase':
        """从文件加载测试用例"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls(
            id=data.get('id', file_path.stem),
            name=data.get('name', file_path.stem),
            input_data=data.get('input', data),
            metadata=data.get('metadata', {})
        )


@dataclass
class ExpectedOutput:
    """预期输出数据类"""
    id: str
    expected: Dict[str, Any]
    tolerance: float = 0.0  # 容差（用于浮点数比较）

    @classmethod
    def from_file(cls, file_path: Path) -> 'ExpectedOutput':
        """从文件加载预期输出"""
        with open(file_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        return cls(
            id=data.get('id', file_path.stem),
            expected=data.get('expected', data),
            tolerance=data.get('tolerance', 0.0)
        )


@dataclass
class EvaluationResult:
    """评估结果数据类"""
    case_id: str
    passed: bool
    actual_output: Any
    expected_output: Any
    similarity: float  # 相似度 0.0 - 1.0
    execution_time: float
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class SkillExecutor:
    """Skill执行器基类"""

    def __init__(self, module: str, domain: str):
        """
        初始化执行器

        Args:
            module: 模块名称
            domain: 领域名称
        """
        self.module = module
        self.domain = domain

    def execute(self, case: TestCase) -> Dict[str, Any]:
        """
        执行测试用例

        Args:
            case: 测试用例

        Returns:
            执行结果字典
        """
        # 这里是模拟执行，实际应该调用真实的Skill
        # 在真实场景中，这里会调用实际的Skill代码
        return {
            "status": "success",
            "result": {
                "diagnosis": f"模拟诊断结果 for case {case.id}",
                "confidence": 0.85,
            },
            "timestamp": datetime.now().isoformat()
        }


class ResultComparator:
    """结果比较器"""

    @staticmethod
    def compare(
        actual: Any,
        expected: Any,
        tolerance: float = 0.0
    ) -> Tuple[bool, float, str]:
        """
        比较实际输出与预期输出

        Args:
            actual: 实际输出
            expected: 预期输出
            tolerance: 容差

        Returns:
            (是否通过, 相似度, 差异描述)
        """
        if actual is None and expected is None:
            return True, 1.0, ""

        if actual is None or expected is None:
            return False, 0.0, "其中一个输出为None"

        # 类型检查
        if type(actual) != type(expected):
            return False, 0.0, f"类型不匹配: {type(actual)} vs {type(expected)}"

        # 字典比较
        if isinstance(actual, dict):
            return ResultComparator._compare_dict(actual, expected, tolerance)

        # 列表比较
        if isinstance(actual, list):
            return ResultComparator._compare_list(actual, expected, tolerance)

        # 字符串比较
        if isinstance(actual, str):
            return ResultComparator._compare_string(actual, expected)

        # 数值比较
        if isinstance(actual, (int, float)):
            return ResultComparator._compare_number(actual, expected, tolerance)

        # 直接比较
        if actual == expected:
            return True, 1.0, ""
        else:
            return False, 0.0, f"值不匹配: {actual} vs {expected}"

    @staticmethod
    def _compare_dict(
        actual: Dict,
        expected: Dict,
        tolerance: float
    ) -> Tuple[bool, float, str]:
        """比较两个字典"""
        all_keys = set(actual.keys()) | set(expected.keys())
        match_keys = set(actual.keys()) & set(expected.keys())
        mismatch_keys = []

        for key in match_keys:
            matched, _, _ = ResultComparator.compare(
                actual[key], expected[key], tolerance
            )
            if not matched:
                mismatch_keys.append(key)

        similarity = len(match_keys - set(mismatch_keys)) / len(all_keys) if all_keys else 1.0

        if not mismatch_keys:
            return True, similarity, ""
        else:
            return False, similarity, f"不匹配字段: {mismatch_keys}"

    @staticmethod
    def _compare_list(
        actual: List,
        expected: List
    ) -> Tuple[bool, float, str]:
        """比较两个列表"""
        if len(actual) != len(expected):
            return False, len(set(actual) & set(expected)) / max(len(actual), len(expected)), \
                   f"长度不匹配: {len(actual)} vs {len(expected)}"

        matches = sum(1 for a, e in zip(actual, expected) if a == e)
        similarity = matches / len(actual) if actual else 1.0

        if matches == len(actual):
            return True, similarity, ""
        else:
            return False, similarity, f"{matches}/{len(actual)} 元素匹配"

    @staticmethod
    def _compare_string(actual: str, expected: str) -> Tuple[bool, float, str]:
        """比较两个字符串"""
        if actual == expected:
            return True, 1.0, ""

        # 计算编辑距离相似度
        max_len = max(len(actual), len(expected))
        if max_len == 0:
            return True, 1.0, ""

        # 简化: 使用公共子串比例
        common = sum(1 for a, e in zip(actual, expected) if a == e)
        similarity = common / max_len

        return similarity >= 0.8, similarity, f"相似度: {similarity:.2%}"

    @staticmethod
    def _compare_number(
        actual: float,
        expected: float,
        tolerance: float
    ) -> Tuple[bool, float, str]:
        """比较两个数值"""
        diff = abs(actual - expected)
        max_val = max(abs(actual), abs(expected))

        if max_val == 0:
            return True, 1.0, ""

        relative_diff = diff / max_val

        if relative_diff <= tolerance:
            return True, 1.0 - relative_diff, ""
        else:
            return False, 1.0 - relative_diff, f"差异: {relative_diff:.2%}"


class SkillEvaluator:
    """Skill评估器"""

    def __init__(
        self,
        module: str,
        domain: str,
        base_path: Path = None
    ):
        """
        初始化评估器

        Args:
            module: 模块名称
            domain: 领域名称
            base_path: 基础路径
        """
        self.module = module
        self.domain = domain
        self.base_path = base_path or Path("E:/TAHP/tahp")

        self.cases_path = self.base_path / "constraints" / module / "eval-data" / "cases"
        self.expected_path = self.base_path / "constraints" / module / "eval-data" / "expected"
        self.reports_path = self.base_path / "reports" / "quality-metrics"

        self.executor = SkillExecutor(module, domain)
        self.comparator = ResultComparator()

    def _load_test_cases(self) -> List[TestCase]:
        """加载测试用例"""
        if not self.cases_path.exists():
            console.print(f"[yellow]警告: 测试用例目录不存在: {self.cases_path}[/yellow]")
            return []

        cases = []
        for case_file in self.cases_path.rglob("*.yaml"):
            try:
                case = TestCase.from_file(case_file)
                cases.append(case)
            except Exception as e:
                console.print(f"[red]加载测试用例失败: {case_file}, 错误: {e}[/red]")

        return cases

    def _load_expected_outputs(self) -> Dict[str, ExpectedOutput]:
        """加载预期输出"""
        if not self.expected_path.exists():
            console.print(f"[yellow]警告: 预期输出目录不存在: {self.expected_path}[/yellow]")
            return {}

        outputs = {}
        for expected_file in self.expected_path.rglob("*.yaml"):
            try:
                output = ExpectedOutput.from_file(expected_file)
                outputs[output.id] = output
            except Exception as e:
                console.print(f"[red]加载预期输出失败: {expected_file}, 错误: {e}[/red]")

        return outputs

    def _evaluate_case(
        self,
        case: TestCase,
        expected: Optional[ExpectedOutput]
    ) -> EvaluationResult:
        """
        评估单个测试用例

        Args:
            case: 测试用例
            expected: 预期输出

        Returns:
            评估结果
        """
        start_time = time.time()

        try:
            # 执行Skill
            actual_output = self.executor.execute(case)
            execution_time = time.time() - start_time

            if expected is None:
                # 没有预期输出，只检查执行成功
                return EvaluationResult(
                    case_id=case.id,
                    passed=True,
                    actual_output=actual_output,
                    expected_output=None,
                    similarity=1.0,
                    execution_time=execution_time,
                    metadata=case.metadata
                )

            # 比较结果
            passed, similarity, diff = self.comparator.compare(
                actual_output.get('result', {}),
                expected.expected,
                expected.tolerance
            )

            return EvaluationResult(
                case_id=case.id,
                passed=passed,
                actual_output=actual_output,
                expected_output=expected.expected,
                similarity=similarity,
                execution_time=execution_time,
                error_message=diff if not passed else None,
                metadata=case.metadata
            )

        except Exception as e:
            execution_time = time.time() - start_time
            return EvaluationResult(
                case_id=case.id,
                passed=False,
                actual_output=None,
                expected_output=expected.expected if expected else None,
                similarity=0.0,
                execution_time=execution_time,
                error_message=str(e),
                metadata=case.metadata
            )

    def evaluate(
        self,
        strategy: EvaluationStrategy = EvaluationStrategy.SEMI_AUTO
    ) -> Dict[str, Any]:
        """
        执行评估

        Args:
            strategy: 评估策略

        Returns:
            评估报告
        """
        console.print(f"\n[bold cyan]开始评估模块: {self.module}, 领域: {self.domain}[/bold cyan]")
        console.print(f"评估策略: {strategy.value}")

        # 加载测试用例和预期输出
        cases = self._load_test_cases()
        expected_outputs = self._load_expected_outputs()

        if not cases:
            console.print("[yellow]没有找到测试用例[/yellow]")
            return {
                "module": self.module,
                "domain": self.domain,
                "strategy": strategy.value,
                "total_cases": 0,
                "passed": 0,
                "failed": 0,
                "accuracy": 0.0,
                "results": [],
            }

        console.print(f"加载了 {len(cases)} 个测试用例")

        # 执行评估
        results = []
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("[cyan]评估测试用例...", total=len(cases))

            for case in cases:
                expected = expected_outputs.get(case.id)
                result = self._evaluate_case(case, expected)
                results.append(result)
                progress.update(task, advance=1)

        # 计算统计信息
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        accuracy = passed / total if total > 0 else 0.0
        avg_similarity = sum(r.similarity for r in results) / total if total > 0 else 0.0
        avg_execution_time = sum(r.execution_time for r in results) / total if total > 0 else 0.0

        # 确定推荐策略
        if accuracy > 0.95:
            recommended_strategy = EvaluationStrategy.FULL_AUTO
        elif accuracy > 0.70:
            recommended_strategy = EvaluationStrategy.SEMI_AUTO
        else:
            recommended_strategy = EvaluationStrategy.MANUAL

        report = {
            "module": self.module,
            "domain": self.domain,
            "strategy": strategy.value,
            "recommended_strategy": recommended_strategy.value,
            "timestamp": datetime.now().isoformat(),
            "total_cases": total,
            "passed": passed,
            "failed": failed,
            "accuracy": accuracy,
            "avg_similarity": avg_similarity,
            "avg_execution_time": avg_execution_time,
            "results": [
                {
                    "case_id": r.case_id,
                    "passed": r.passed,
                    "similarity": r.similarity,
                    "execution_time": r.execution_time,
                    "error": r.error_message,
                }
                for r in results
            ]
        }

        return report

    def save_report(self, report: Dict) -> Path:
        """
        保存评估报告

        Args:
            report: 评估报告

        Returns:
            报告文件路径
        """
        # 确保目录存在
        self.reports_path.mkdir(parents=True, exist_ok=True)

        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"eval_{self.module}_{self.domain}_{timestamp}.json"
        report_file = self.reports_path / filename

        # 保存报告
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        return report_file


def print_evaluation_table(report: Dict):
    """
    打印评估结果表格

    Args:
        report: 评估报告
    """
    table = Table(title="评估结果详情")
    table.add_column("用例ID", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("相似度", justify="right")
    table.add_column("执行时间", justify="right")
    table.add_column("备注", style="yellow")

    for result in report["results"]:
        status = "✓ 通过" if result["passed"] else "✗ 失败"
        status_style = "green" if result["passed"] else "red"
        similarity = f"{result['similarity']:.1%}"
        exec_time = f"{result['execution_time']:.3f}s"
        error = result.get("error", "") or ""

        table.add_row(
            result["case_id"],
            f"[{status_style}]{status}[/{status_style}]",
            similarity,
            exec_time,
            error
        )

    console.print(table)


def print_summary(report: Dict):
    """
    打印评估摘要

    Args:
        report: 评估报告
    """
    accuracy = report["accuracy"]
    strategy = report.get("recommended_strategy", report["strategy"])

    # 颜色标记
    if accuracy > 0.95:
        accuracy_style = "green"
        level = "全自动"
    elif accuracy > 0.70:
        accuracy_style = "yellow"
        level = "半自动"
    else:
        accuracy_style = "red"
        level = "人工介入"

    summary = f"""
[bold]评估摘要[/bold]
模块: {report['module']} / {report['domain']}
测试用例: {report['total_cases']}
通过: {report['passed']} | 失败: {report['failed']}
准确率: [{accuracy_style}]{accuracy:.1%}[/{accuracy_style}]
平均相似度: {report['avg_similarity']:.1%}
平均执行时间: {report['avg_execution_time']:.3f}s
推荐策略: {level} ({strategy})
"""

    console.print(Panel(summary.strip(), title="评估报告", border_style="cyan"))


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description="TAHP Skill 评估器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
评估策略:
  full_auto  - 全自动 (准确率 > 95%)
  semi_auto  - 半自动 (准确率 70-95%)
  manual     - 人工 (准确率 < 70%)

示例:
  python evaluate.py --module telephony --domain bug-analysis
  python evaluate.py --module display --domain code-adapter --strategy full_auto
        """
    )

    parser.add_argument("--module", "-m", required=True, help="模块名称")
    parser.add_argument("--domain", "-d", required=True, help="领域名称")
    parser.add_argument(
        "--strategy", "-s",
        choices=["full_auto", "semi_auto", "manual"],
        default="semi_auto",
        help="评估策略 (默认: semi_auto)"
    )
    parser.add_argument(
        "--base-path",
        type=str,
        default="E:/TAHP/tahp",
        help="基础路径"
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="不保存报告"
    )

    args = parser.parse_args()

    # 创建评估器
    evaluator = SkillEvaluator(
        module=args.module,
        domain=args.domain,
        base_path=Path(args.base_path)
    )

    # 执行评估
    strategy = EvaluationStrategy(args.strategy)
    report = evaluator.evaluate(strategy)

    # 输出结果
    print_summary(report)
    print_evaluation_table(report)

    # 保存报告
    if not args.no_save:
        report_file = evaluator.save_report(report)
        console.print(f"\n[green]报告已保存: {report_file}[/green]")

    # 返回状态码
    if report["accuracy"] < 0.70:
        sys.exit(2)  # 需要人工介入
    elif report["accuracy"] < 0.95:
        sys.exit(1)  # 有警告
    sys.exit(0)


if __name__ == "__main__":
    main()
