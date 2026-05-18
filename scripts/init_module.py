#!/usr/bin/env python3
"""
TAHP 模块初始化脚本

从模板创建新的模块约束结构，生成标准目录和初始约束文件。
支持交互式和命令行两种模式。

用法:
  交互式: python init_module.py
  命令行: python init_module.py --name display-driver --owner zhangsan --scope "显示驱动"
  CI模式: python init_module.py --non-interactive --name display-driver --owner zhangsan
"""

import sys
import os
import re
import shutil
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional


# 模块名称验证: kebab-case
MODULE_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9-]{1,30}[a-z0-9]$|^[a-z]$")


def validate_module_name(name: str) -> bool:
    """验证模块名称格式（kebab-case）"""
    return bool(MODULE_NAME_PATTERN.match(name))


def get_module_dirs(root: Path) -> list[str]:
    """获取已有模块列表"""
    constraints_dir = root / "constraints"
    if not constraints_dir.exists():
        return []
    return [
        d.name for d in constraints_dir.iterdir()
        if d.is_dir() and d.name != "shared"
        and not d.name.startswith(".")
    ]


def generate_module_yaml(name: str, display_name: str, owner: str,
                         description: str, team: str, android_version: str,
                         domains: list[str]) -> str:
    """生成module.yaml内容"""
    now = datetime.now().strftime("%Y-%m-%d")
    domain_lines = "\n".join(f"  - {d}" for d in domains)

    return f"""# 模块: {name}
# 描述: {description}
# 由 init_module.py 自动生成于 {now}

module:
  name: "{name}"
  display_name: "{display_name}"
  version: "1.0.0"
  description: >
    {description}
  owner: "{owner}"
  team: "{team}"
  created: "{now}"
  updated: "{now}"

scope:
  includes: []
  excludes:
    - "vendor/*/proprietary/"
    - "out/"
    - "test/"
  dependencies: []

dependencies:
  modules: []
  platforms:
    - "Android {android_version}"

domains:
{domain_lines}

safety_redlines:
  - "禁止修改 scope.excludes 中列出的任何文件"
  - "禁止绕过或禁用安全验证机制"
  - "不在未验证API存在性的情况下生成代码"
  - "不硬编码密钥、Token或设备标识"
  - "涉及安全相关的变更必须经过安全评审"
  - "所有代码修改必须通过编译门禁"
"""


def generate_bug_analysis_yaml(name: str) -> str:
    """生成bug-analysis.yaml初始内容"""
    return f"""# Bug分析约束: {name}
# 由 init_module.py 自动生成

preconditions:
  required_info:
    - name: "android_version"
      description: "Android版本号"
      how_to_get: "getprop ro.build.version.release"
      required: true
      error_msg: "缺少Android版本信息，无法确定目标平台约束。"
    - name: "device_model"
      description: "设备型号"
      how_to_get: "getprop ro.product.model"
      required: true
      error_msg: "缺少设备型号信息。"
    - name: "repro_steps"
      description: "问题复现步骤"
      how_to_get: "由用户或Bug报告提供"
      required: true
      error_msg: "未提供复现步骤，请补充。"
    - name: "logcat"
      description: "完整logcat日志"
      how_to_get: "adb logcat -d -b main,system"
      required: true
      error_msg: "缺少日志数据。"

analysis_rules:
  layer_detection_order: {{}}
  prohibited:
    - "在未确认复现步骤的情况下给出修复代码"
    - "修改 scope.excludes 中排除范围内的代码"
    - "忽略安全相关标记"
  required_outputs:
    - name: "root_cause_layer"
      type: "enum"
      values: ["Application", "Framework", "HAL", "Kernel", "Driver", "Unknown"]
      description: "根因所属层级"
    - name: "severity"
      type: "enum"
      values: ["critical", "high", "medium", "low"]
      description: "严重程度"
    - name: "root_cause_description"
      type: "text"
      min_length: 50
      description: "根因详细描述（不少于50字）"

security_gates:
  - condition: "可能导致数据泄露或隐私侵犯"
    action: "标记为critical，立即通知安全团队"

evaluation:
  bug_analysis_accuracy_target: 0.85
  required_artifacts:
    - root_cause_report
    - affected_components
  test_dataset: eval-data/
"""


def create_module(
    root: Path,
    name: str,
    display_name: str,
    owner: str,
    description: str = "",
    team: str = "",
    android_version: str = "14",
    domains: Optional[list[str]] = None,
    use_templates: bool = True
) -> bool:
    """创建新模块目录结构

    Args:
        root: 项目根目录
        name: 模块名称（kebab-case）
        display_name: 显示名称
        owner: 负责人
        description: 模块描述
        team: 所属团队
        android_version: 目标Android版本
        domains: 支持的约束域列表
        use_templates: 是否从模板复制（如果模板存在）

    Returns:
        True表示创建成功
    """
    if domains is None:
        domains = ["bug-analysis"]

    module_dir = root / "constraints" / name

    # 检查是否已存在
    if module_dir.exists():
        print(f"[ERROR] 模块 '{name}' 已存在: {module_dir}")
        return False

    # 创建目录结构
    dirs_to_create = [
        module_dir,
        module_dir / "eval-data" / "cases",
        module_dir / "eval-data" / "expected",
    ]
    for d in dirs_to_create:
        d.mkdir(parents=True, exist_ok=True)

    # 检查是否有可用模板
    template_dir = root / "templates" / "module-template"
    template_available = template_dir.exists() and use_templates

    # 生成约束文件
    module_yaml_content = generate_module_yaml(
        name, display_name, owner, description, team, android_version, domains
    )
    (module_dir / "module.yaml").write_text(module_yaml_content, encoding="utf-8")

    if "bug-analysis" in domains:
        if template_available and (template_dir / "bug-analysis.yaml.template").exists():
            template_content = (template_dir / "bug-analysis.yaml.template").read_text(
                encoding="utf-8"
            )
            # 简单的变量替换
            for var, val in [
                ("{{ module_name }}", name),
                ("{{ log_buffer }}", "radio"),
            ]:
                template_content = template_content.replace(var, val)
            (module_dir / "bug-analysis.yaml").write_text(
                template_content, encoding="utf-8"
            )
        else:
            (module_dir / "bug-analysis.yaml").write_text(
                generate_bug_analysis_yaml(name), encoding="utf-8"
            )

    # 为其他域创建占位文件
    domain_templates = {
        "code-adaptation": "code-adaptation.yaml.template",
        "version-adaptation": "version-adaptation.yaml.template",
        "carrier-porting": "carrier-porting.yaml.template",
    }
    for domain in domains:
        if domain == "bug-analysis":
            continue
        template_file = domain_templates.get(domain)
        if template_available and template_file and (template_dir / template_file).exists():
            shutil.copy2(template_dir / template_file, module_dir / f"{domain}.yaml")
            print(f"  [从模板] {domain}.yaml")

    # 创建eval-data占位文件
    for subdir in ["cases", "expected"]:
        gitkeep = module_dir / "eval-data" / subdir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.touch()

    return True


def interactive_init(root: Path) -> bool:
    """交互式模块初始化"""
    print("=" * 50)
    print("TAHP 模块初始化向导")
    print("=" * 50)

    # 显示已有模块
    existing = get_module_dirs(root)
    if existing:
        print(f"\n已有模块: {', '.join(existing)}")

    # 收集信息
    print()
    name = input("模块名称 (kebab-case，如 display-driver): ").strip()
    if not validate_module_name(name):
        print(f"[ERROR] 模块名称 '{name}' 不符合kebab-case格式")
        return False

    display_name = input("显示名称 (如 '显示驱动'): ").strip() or name
    owner = input("负责人: ").strip()
    if not owner:
        print("[ERROR] 负责人不能为空")
        return False

    description = input("模块描述 (可选): ").strip() or f"{display_name}模块约束"
    team = input("所属团队 (可选): ").strip()

    print("\n支持的约束域 (回车选择，空行结束):")
    available_domains = ["bug-analysis", "code-adaptation", "version-adaptation", "carrier-porting"]
    domains = []
    for i, domain in enumerate(available_domains, 1):
        select = input(f"  [{i}] {domain}? [Y/n]: ").strip().lower()
        if select != "n":
            domains.append(domain)
    if not domains:
        domains = ["bug-analysis"]
        print(f"  默认启用: {domains[0]}")

    return create_module(
        root, name, display_name, owner, description, team,
        domains=domains
    )


def main():
    parser = argparse.ArgumentParser(
        description="TAHP 模块初始化 — 从模板创建新的模块约束结构",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  交互式:   python init_module.py
  命令行:   python init_module.py --name display-driver --owner zhangsan
  指定域:   python init_module.py --name nfc --owner lisi --domains bug-analysis code-adaptation
  CI模式:   python init_module.py --non-interactive --name nfc --owner lisi --team nfc-team
        """
    )
    parser.add_argument("--name", type=str, help="模块名称 (kebab-case)")
    parser.add_argument("--display-name", type=str, help="显示名称")
    parser.add_argument("--owner", type=str, help="模块负责人")
    parser.add_argument("--description", type=str, default="", help="模块描述")
    parser.add_argument("--team", type=str, default="", help="所属团队")
    parser.add_argument("--android-version", type=str, default="14", help="目标Android版本")
    parser.add_argument(
        "--domains", type=str, nargs="+",
        default=["bug-analysis"],
        choices=["bug-analysis", "code-adaptation", "version-adaptation", "carrier-porting"],
        help="支持的约束域 (默认: bug-analysis)"
    )
    parser.add_argument(
        "--non-interactive", action="store_true",
        help="非交互模式（CI/CD使用）"
    )
    parser.add_argument(
        "--project-root", type=str, default=None,
        help="项目根目录（默认自动检测）"
    )

    args = parser.parse_args()
    root = Path(args.project_root) if args.project_root else Path(__file__).parent.parent

    if args.non_interactive or args.name:
        # 命令行模式
        if not args.name:
            parser.error("非交互模式需要 --name 参数")
        if not validate_module_name(args.name):
            print(f"[ERROR] 模块名称 '{args.name}' 不符合kebab-case格式")
            sys.exit(1)
        if not args.owner:
            parser.error("非交互模式需要 --owner 参数")

        display_name = args.display_name or args.name.replace("-", " ").title()
        success = create_module(
            root, args.name, display_name, args.owner,
            args.description, args.team, args.android_version, args.domains
        )
    else:
        # 交互式模式
        success = interactive_init(root)

    if success:
        print("\n[DONE] 模块初始化完成")
        print("下一步:")
        print("  1. 编辑 constraints/<module>/module.yaml 填写scope信息")
        print("  2. 编辑约束文件添加具体规则")
        print("  3. 在 eval-data/ 下添加测试用例")
        print("  4. 运行 python scripts/validate_constraints.py 验证约束文件")
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
