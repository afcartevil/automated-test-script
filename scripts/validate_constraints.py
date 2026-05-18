#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TAHP 约束文件验证器 (validate_constraints.py)

功能: 验证约束文件的格式和内容完整性
来源: TAHP-评估与质量门禁规范 §7

此脚本负责检查约束文件的:
1. YAML 语法正确性
2. 必填字段完整性 (module_name, scope, version, owner)
3. 安全红线字段 (safety_redlines)
4. 域约束文件结构 (前置条件、分析规则等)

用法:
    python validate_constraints.py --path constraints/telephony/
    python validate_constraints.py --file constraints/telephony/bug-analysis.yaml
"""

import sys
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

# 全局控制台实例
console = Console()

# 必填字段定义
REQUIRED_FIELDS = {
    "module_name": "模块名称",
    "scope": "作用域",
    "version": "版本号",
    "owner": "负责人",
}

# 顶层可选字段
OPTIONAL_FIELDS = {
    "description": "模块描述",
    "tags": "标签列表",
    "created_at": "创建时间",
    "updated_at": "更新时间",
}

# 安全红线相关字段
SAFETY_REDLINES_FIELDS = {
    "critical_checks": "关键检查项",
    "forbidden_patterns": "禁止模式",
    "warning_patterns": "警告模式",
}

# 域约束文件特定字段 (用于检查子约束文件)
DOMAIN_CONSTRAINT_FIELDS = {
    "prerequisites": "前置条件",
    "analysis_rules": "分析规则",
    "output_format": "输出格式",
    "examples": "示例",
}


class ConstraintValidationError(Exception):
    """约束文件验证错误"""
    pass


class ConstraintValidator:
    """约束文件验证器类"""

    def __init__(self, verbose: bool = False):
        """
        初始化验证器

        Args:
            verbose: 是否输出详细日志
        """
        self.verbose = verbose
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.info: List[str] = []

    def _log_info(self, message: str):
        """记录信息日志"""
        self.info.append(message)
        if self.verbose:
            console.print(f"[blue]INFO:[/blue] {message}")

    def _log_warning(self, message: str):
        """记录警告日志"""
        self.warnings.append(message)
        console.print(f"[yellow]WARNING:[/yellow] {message}")

    def _log_error(self, message: str):
        """记录错误日志"""
        self.errors.append(message)
        console.print(f"[red]ERROR:[/red] {message}")

    def validate_yaml_syntax(self, file_path: Path) -> Optional[Dict]:
        """
        验证YAML语法正确性

        Args:
            file_path: YAML文件路径

        Returns:
            解析后的字典对象，失败返回None
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            self._log_info(f"✓ YAML语法正确: {file_path.name}")
            return data
        except yaml.YAMLError as e:
            self._log_error(f"YAML语法错误: {e}")
            return None
        except Exception as e:
            self._log_error(f"文件读取失败: {e}")
            return None

    def validate_required_fields(self, data: Dict, file_path: Path) -> bool:
        """
        检查必填字段完整性

        Args:
            data: 解析后的YAML数据
            file_path: 文件路径

        Returns:
            是否通过验证
        """
        all_passed = True
        for field, description in REQUIRED_FIELDS.items():
            if field not in data or not data[field]:
                self._log_error(f"缺少必填字段 '{field}' ({description})")
                all_passed = False
            else:
                self._log_info(f"✓ 必填字段 '{field}' 存在: {data[field]}")

        return all_passed

    def validate_safety_redlines(self, data: Dict) -> bool:
        """
        检查安全红线字段

        Args:
            data: 解析后的YAML数据

        Returns:
            是否通过验证
        """
        if "safety_redlines" not in data:
            self._log_warning("缺少 'safety_redlines' 字段，建议添加安全红线配置")
            return True  # 安全红线不是强制要求

        safety = data["safety_redlines"]
        if not isinstance(safety, dict):
            self._log_error("'safety_redlines' 必须是字典类型")
            return False

        has_content = False
        for field, description in SAFETY_REDLINES_FIELDS.items():
            if field in safety and safety[field]:
                self._log_info(f"✓ 安全红线字段 '{field}' 存在")
                has_content = True

        if not has_content:
            self._log_warning("'safety_redlines' 内容为空")

        return True

    def validate_domain_constraints(self, data: Dict, file_path: Path) -> bool:
        """
        检查域约束文件结构

        Args:
            data: 解析后的YAML数据
            file_path: 文件路径

        Returns:
            是否通过验证
        """
        # 检查是否为域约束文件（通常在子目录中）
        is_domain_file = any(
            keyword in file_path.name.lower()
            for keyword in ['bug', 'analysis', 'rule', 'constraint']
        )

        if not is_domain_file:
            return True

        # 域约束文件的特定字段检查
        for field in ["prerequisites", "analysis_rules"]:
            if field not in data:
                self._log_warning(f"域约束文件建议包含 '{field}' 字段")

        return True

    def validate_file(self, file_path: Path) -> Tuple[bool, int, int]:
        """
        验证单个约束文件

        Args:
            file_path: 文件路径

        Returns:
            (是否通过, 错误数, 警告数)
        """
        self._log_info(f"\n验证文件: {file_path}")
        console.print(f"\n[bold cyan]验证文件:[/bold cyan] {file_path}")

        # 重置日志
        errors_before = len(self.errors)
        warnings_before = len(self.warnings)

        # 1. 验证YAML语法
        data = self.validate_yaml_syntax(file_path)
        if data is None:
            return False, 1, 0

        # 2. 检查必填字段
        self.validate_required_fields(data, file_path)

        # 3. 检查安全红线
        self.validate_safety_redlines(data)

        # 4. 检查域约束结构
        self.validate_domain_constraints(data, file_path)

        errors_count = len(self.errors) - errors_before
        warnings_count = len(self.warnings) - warnings_before

        passed = errors_count == 0
        return passed, errors_count, warnings_count

    def validate_directory(self, dir_path: Path, recursive: bool = True) -> Dict:
        """
        验证目录中的所有约束文件

        Args:
            dir_path: 目录路径
            recursive: 是否递归扫描子目录

        Returns:
            验证结果统计
        """
        # 查找所有YAML文件
        if recursive:
            yaml_files = list(dir_path.rglob("*.yaml")) + list(dir_path.rglob("*.yml"))
        else:
            yaml_files = list(dir_path.glob("*.yaml")) + list(dir_path.glob("*.yml"))

        # 排除templates目录
        yaml_files = [f for f in yaml_files if "templates" not in str(f)]

        if not yaml_files:
            self._log_warning(f"目录中未找到YAML文件: {dir_path}")
            return {
                "total": 0,
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "warnings": 0,
            }

        self._log_info(f"找到 {len(yaml_files)} 个YAML文件")

        total_passed = 0
        total_failed = 0
        total_errors = 0
        total_warnings = 0

        for yaml_file in yaml_files:
            passed, errors, warnings = self.validate_file(yaml_file)
            if passed:
                total_passed += 1
            else:
                total_failed += 1
            total_errors += errors
            total_warnings += warnings

        return {
            "total": len(yaml_files),
            "passed": total_passed,
            "failed": total_failed,
            "errors": total_errors,
            "warnings": total_warnings,
        }


def create_validation_report(result: Dict, path: str) -> str:
    """
    创建验证报告摘要

    Args:
        result: 验证结果
        path: 验证路径

    Returns:
        格式化的报告字符串
    """
    report = []
    report.append("\n" + "=" * 60)
    report.append("约束文件验证报告")
    report.append("=" * 60)
    report.append(f"验证路径: {path}")
    report.append(f"总文件数: {result['total']}")
    report.append(f"通过: {result['passed']}")
    report.append(f"失败: {result['failed']}")
    report.append(f"总错误数: {result['errors']}")
    report.append(f"总警告数: {result['warnings']}")

    if result['failed'] == 0 and result['errors'] == 0:
        report.append("\n✓ 验证通过! 所有约束文件格式正确。")
    elif result['failed'] == 0:
        report.append("\n⚠ 验证通过，但有警告信息。")
    else:
        report.append("\n✗ 验证失败，请修复上述错误。")

    report.append("=" * 60)
    return "\n".join(report)


def main():
    """主入口函数"""
    parser = argparse.ArgumentParser(
        description="TAHP 约束文件验证器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python validate_constraints.py --path constraints/telephony/
  python validate_constraints.py --file constraints/telephony/bug-analysis.yaml
  python validate_constraints.py --path constraints/ --recursive
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--path", type=str, help="验证目录路径")
    group.add_argument("--file", type=str, help="验证单个文件路径")

    parser.add_argument(
        "--recursive", "-r",
        action="store_true",
        default=True,
        help="递归扫描子目录 (默认开启)"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细日志"
    )

    args = parser.parse_args()

    # 创建验证器
    validator = ConstraintValidator(verbose=args.verbose)

    # 执行验证
    if args.file:
        file_path = Path(args.file)
        if not file_path.exists():
            console.print(f"[red]错误: 文件不存在: {file_path}[/red]")
            sys.exit(1)

        passed, errors, warnings = validator.validate_file(file_path)
        result = {
            "total": 1,
            "passed": 1 if passed else 0,
            "failed": 0 if passed else 1,
            "errors": errors,
            "warnings": warnings,
        }
    else:
        dir_path = Path(args.path)
        if not dir_path.exists():
            console.print(f"[red]错误: 目录不存在: {dir_path}[/red]")
            sys.exit(1)

        result = validator.validate_directory(dir_path, recursive=args.recursive)

    # 输出报告
    report = create_validation_report(result, args.path or args.file)
    print(report)

    # 返回状态码
    if result["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
