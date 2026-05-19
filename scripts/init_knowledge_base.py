# -*- coding: utf-8 -*-
"""知识库初始化脚本

初始化 ChromaDB collections、创建模块目录结构、
从 constraints/ 提取现有知识。

用法:
    python scripts/init_knowledge_base.py --module telephony
    python scripts/init_knowledge_base.py --all
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.config import KnowledgeBaseConfig
from db.knowledge_db import KnowledgeDB

console = Console()


def _get_registered_modules() -> list[str]:
    """从 constraints/ 目录获取已注册的模块列表"""
    constraints_dir = PROJECT_ROOT / "constraints"
    modules = []
    if constraints_dir.exists():
        for item in constraints_dir.iterdir():
            if item.is_dir() and item.name != "shared":
                modules.append(item.name)
    return sorted(modules)


def _create_module_dirs(data_dir: Path, module: str) -> dict[str, Path]:
    """创建模块目录结构

    knowledge-base/{module}/docs/, cases/, auto/
    """
    module_dir = data_dir / module
    dirs = {
        "root": module_dir,
        "docs": module_dir / "docs",
        "cases": module_dir / "cases",
        "auto": module_dir / "auto",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)
    return dirs


def _create_module_index(data_dir: Path, module: str):
    """创建模块的 index.yaml"""
    index_path = data_dir / module / "index.yaml"
    if index_path.exists():
        return

    index_data = {
        "version": "1.0",
        "module": module,
        "updated": _now_date(),
        "entries": {
            "docs": [],
            "cases": [],
            "auto": [],
        },
    }
    index_path.write_text(yaml.dump(index_data, allow_unicode=True, default_flow_style=False), encoding="utf-8")


def _now_date() -> str:
    """当前日期字符串"""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _extract_from_constraints(data_dir: Path, module: str) -> int:
    """从 constraints/{module}/ 提取现有知识

    如果约束文件存在，提取为知识条目存入知识库。
    """
    constraints_dir = PROJECT_ROOT / "constraints" / module
    if not constraints_dir.exists():
        return 0

    count = 0
    from db.models import KnowledgeEntry

    # 遍历约束目录下的 Markdown 文件
    for md_file in constraints_dir.rglob("*.md"):
        try:
            entry = KnowledgeEntry.create(
                module=module,
                title=md_file.stem,
                entry_type="tech_doc",
                category="architecture",
                content=md_file.read_text(encoding="utf-8"),
                source="source_analyzed",
                author="system",
                tags=["constraint", module],
            )

            # 保存到 knowledge-base 目录
            dest = data_dir / module / "docs" / f"{entry.id}.md"
            dest.write_text(entry.to_markdown(), encoding="utf-8")
            count += 1
        except Exception as e:
            console.print(f"  [yellow]跳过 {md_file.name}: {e}[/yellow]")

    # 遍历 YAML 约束文件
    for yaml_file in constraints_dir.rglob("*.yaml"):
        if yaml_file.name == "index.yaml":
            continue
        try:
            content = yaml_file.read_text(encoding="utf-8")
            entry = KnowledgeEntry.create(
                module=module,
                title=yaml_file.stem,
                entry_type="tech_doc",
                category="architecture",
                content=f"```yaml\n{content}\n```",
                source="source_analyzed",
                author="system",
                tags=["constraint", module, "yaml"],
            )
            dest = data_dir / module / "docs" / f"{entry.id}.md"
            dest.write_text(entry.to_markdown(), encoding="utf-8")
            count += 1
        except Exception as e:
            console.print(f"  [yellow]跳过 {yaml_file.name}: {e}[/yellow]")

    return count


def _verify_database(db: KnowledgeDB) -> bool:
    """验证数据库连通性"""
    try:
        stats = db.get_stats()
        return True
    except Exception as e:
        console.print(f"[red]数据库连通性验证失败: {e}[/red]")
        return False


@click.command("init_knowledge_base", help="初始化知识库数据库和目录结构")
@click.option("--module", "-m", "module_name", help="初始化指定模块的知识库")
@click.option("--all", "init_all", is_flag=True, help="初始化所有已注册模块的知识库")
@click.option("--skip-extract", is_flag=True, help="跳过从 constraints/ 提取知识")
def main(module_name: str | None, init_all: bool, skip_extract: bool):
    """初始化知识库"""
    if not module_name and not init_all:
        console.print("[red]请指定 --module <名称> 或 --all[/red]")
        sys.exit(1)

    console.print(Panel("TAHP 知识库初始化", style="bold blue"))

    # 加载配置
    config = KnowledgeBaseConfig.from_yaml()
    data_dir = config.data_dir
    data_dir.mkdir(parents=True, exist_ok=True)

    # 初始化 ChromaDB
    console.print("\n[bold]1. 初始化 ChromaDB[/bold]")
    try:
        db = KnowledgeDB(config=config)
        console.print("  [green]ChromaDB 持久化客户端已初始化[/green]")
        console.print(f"  持久化目录: {config.chroma_persist_dir}")
    except Exception as e:
        console.print(f"  [red]ChromaDB 初始化失败: {e}[/red]")
        sys.exit(1)

    # 验证数据库连通性
    if _verify_database(db):
        console.print("  [green]数据库连通性验证通过[/green]")
    else:
        sys.exit(1)

    # 确定要初始化的模块
    modules = []
    if init_all:
        modules = _get_registered_modules()
        console.print(f"\n[bold]2. 已注册模块: {', '.join(modules) or '无'}[/bold]")
    else:
        modules = [module_name]

    # 初始化每个模块
    table = Table(title="模块初始化结果", show_header=True, header_style="bold")
    table.add_column("模块", style="cyan")
    table.add_column("目录结构", style="green")
    table.add_column("index.yaml", style="green")
    table.add_column("提取条目", style="yellow")

    for module in modules:
        # 创建目录结构
        dirs = _create_module_dirs(data_dir, module)

        # 创建 index.yaml
        _create_module_index(data_dir, module)

        # 从 constraints 提取
        extracted = 0
        if not skip_extract:
            extracted = _extract_from_constraints(data_dir, module)

        # 同步提取的条目到 ChromaDB
        if extracted > 0:
            docs_dir = dirs["docs"]
            from db.models import KnowledgeEntry
            for md_file in docs_dir.glob("*.md"):
                try:
                    entry = KnowledgeEntry.from_markdown(md_file)
                    db.add_entry(entry)
                except Exception:
                    pass

        table.add_row(
            module,
            "[green]已创建[/green]",
            "[green]已创建[/green]" if (data_dir / module / "index.yaml").exists() else "[yellow]已存在[/yellow]",
            str(extracted),
        )

    console.print(table)

    # 显示最终统计
    stats = db.get_stats()
    console.print(f"\n[bold]3. 知识库统计[/bold]")
    console.print(f"  总条目数: {stats['total']}")
    for coll_name, count in stats["collections"].items():
        console.print(f"  {coll_name}: {count} 条")

    console.print("\n[bold green]知识库初始化完成[/bold green]")


if __name__ == "__main__":
    main()
