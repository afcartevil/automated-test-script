# -*- coding: utf-8 -*-
"""知识查询脚本

语义搜索知识条目、跨模块搜索、知识库统计。

用法:
    python scripts/query_knowledge.py --module telephony --query "WiFi Calling crash"
    python scripts/query_knowledge.py --query "IMS null pointer" --cross-module
    python scripts/query_knowledge.py --module telephony --stats
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.config import KnowledgeBaseConfig
from db.knowledge_db import KnowledgeDB
from db.models import KnowledgeEntry

console = Console()


def _display_entry(entry: KnowledgeEntry, show_content: bool = False, index: int = 0):
    """显示单个知识条目"""
    similarity = entry.metadata.get("_similarity", None)

    # 标题行
    title_text = Text()
    if index > 0:
        title_text.append(f"#{index} ", style="bold cyan")
    title_text.append(entry.title, style="bold")
    if similarity is not None:
        title_text.append(f"  (相关度: {similarity:.2%})", style="green")

    console.print(title_text)

    # 元数据行
    meta_parts = [
        f"ID: {entry.id}",
        f"模块: {entry.module}",
        f"类型: {entry.type}",
        f"分类: {entry.category}",
        f"置信度: {entry.confidence:.0%}",
        f"来源: {entry.source}",
    ]
    console.print("  " + " | ".join(meta_parts), style="dim")

    # 标签
    if entry.tags:
        console.print(f"  标签: {', '.join(entry.tags)}", style="dim")

    # 摘要（内容前 200 字符）
    if entry.content:
        preview = entry.content[:200].replace("\n", " ")
        if len(entry.content) > 200:
            preview += "..."
        console.print(f"  摘要: {preview}", style="dim italic")

    console.print()


def _display_stats(stats: dict):
    """显示知识库统计信息"""
    console.print(Panel("知识库统计", style="bold blue"))

    console.print(f"\n[bold]总条目数: {stats['total']}[/bold]\n")

    # Collection 分布
    if stats["collections"]:
        table = Table(title="Collection 分布", show_header=True, header_style="bold")
        table.add_column("Collection", style="cyan")
        table.add_column("条目数", style="green")
        for name, count in stats["collections"].items():
            table.add_row(name, str(count))
        console.print(table)

    # 按模块分布
    if stats["by_module"]:
        table = Table(title="按模块分布", show_header=True, header_style="bold")
        table.add_column("模块", style="cyan")
        table.add_column("条目数", style="green")
        for module, count in sorted(stats["by_module"].items(), key=lambda x: -x[1]):
            table.add_row(module, str(count))
        console.print(table)

    # 按类型分布
    if stats["by_type"]:
        table = Table(title="按类型分布", show_header=True, header_style="bold")
        table.add_column("类型", style="cyan")
        table.add_column("条目数", style="green")
        for t, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            table.add_row(t, str(count))
        console.print(table)

    # 按来源分布
    if stats["by_source"]:
        table = Table(title="按来源分布", show_header=True, header_style="bold")
        table.add_column("来源", style="cyan")
        table.add_column("条目数", style="green")
        for s, count in sorted(stats["by_source"].items(), key=lambda x: -x[1]):
            table.add_row(s, str(count))
        console.print(table)


@click.command("query_knowledge", help="查询知识库")
@click.option("--module", "-m", help="指定模块")
@click.option("--query", "-q", help="搜索查询文本")
@click.option("--cross-module", is_flag=True, help="跨模块搜索")
@click.option("--type", "entry_type", help="按类型过滤")
@click.option("--category", help="按分类过滤")
@click.option("--top-k", default=5, help="返回结果数量 (默认: 5)")
@click.option("--stats", "show_stats", is_flag=True, help="显示知识库统计")
@click.option("--recent", type=int, default=None, help="显示最近 N 天的条目")
def main(module: str | None, query: str | None, cross_module: bool,
         entry_type: str | None, category: str | None, top_k: int,
         show_stats: bool, recent: int | None):
    """查询知识库"""
    config = KnowledgeBaseConfig.from_yaml()

    try:
        db = KnowledgeDB(config=config)
    except Exception as e:
        console.print(f"[red]数据库初始化失败: {e}[/red]")
        sys.exit(1)

    # 显示统计
    if show_stats:
        stats = db.get_stats()
        _display_stats(stats)
        return

    # 显示最近条目
    if recent is not None:
        entries = db.get_recent_entries(days=recent, module=module, limit=top_k)
        if not entries:
            console.print("[yellow]未找到最近条目[/yellow]")
            return
        console.print(f"[bold]最近 {recent} 天的条目 ({len(entries)} 条)[/bold]\n")
        for i, entry in enumerate(entries, 1):
            _display_entry(entry, index=i)
        return

    # 语义搜索
    if query:
        if cross_module:
            entries = db.cross_module_search(
                query=query,
                exclude_module=module,
                n_results=top_k,
            )
            console.print(f"[bold]跨模块搜索: "{query}"[/bold]\n")
        else:
            entries = db.search(
                query=query,
                module=module,
                entry_type=entry_type,
                category=category,
                n_results=top_k,
            )
            scope = f"模块 {module}" if module else "全库"
            console.print(f"[bold]语义搜索 ({scope}): "{query}"[/bold]\n")

        if not entries:
            console.print("[yellow]未找到匹配的知识条目[/yellow]")
            return

        for i, entry in enumerate(entries, 1):
            _display_entry(entry, index=i)
        return

    # 如果只指定了模块，列出模块条目
    if module:
        entries = db.get_module_entries(module, entry_type=entry_type, limit=top_k)
        if not entries:
            console.print(f"[yellow]模块 '{module}' 暂无知识条目[/yellow]")
            return
        console.print(f"[bold]模块 {module} 的知识条目 ({len(entries)} 条)[/bold]\n")
        for i, entry in enumerate(entries, 1):
            _display_entry(entry, index=i)
        return

    # 无参数时显示统计
    stats = db.get_stats()
    _display_stats(stats)


if __name__ == "__main__":
    main()
