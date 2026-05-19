# -*- coding: utf-8 -*-
"""知识投喂脚本

解析 Markdown/PDF/Word 文件为 KnowledgeEntry，
存入 Git 管理的 knowledge-base/ 目录和 ChromaDB。

用法:
    python scripts/feed_knowledge.py --module telephony --docs ./my-docs/*.md
    python scripts/feed_knowledge.py --module telephony --cases ./cases/*.md
    python scripts/feed_knowledge.py --module telephony --dir ./feed-dir/
    python scripts/feed_knowledge.py --module telephony --incremental
"""

from __future__ import annotations

import glob
import sys
from pathlib import Path

import click
import yaml
from rich.console import Console
from rich.table import Table

# 将项目根目录加入 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.config import KnowledgeBaseConfig
from db.knowledge_db import KnowledgeDB
from db.models import KnowledgeEntry

console = Console()


def _collect_files(*patterns: str) -> list[Path]:
    """收集匹配 glob 模式的文件"""
    files = []
    for pattern in patterns:
        # 支持 glob 通配符
        matched = glob.glob(pattern, recursive=True)
        for m in matched:
            p = Path(m)
            if p.is_file():
                files.append(p)
    return sorted(set(files))


def _parse_file(filepath: Path, module: str) -> KnowledgeEntry | None:
    """解析单个文件为 KnowledgeEntry

    支持 Markdown (含 YAML frontmatter)，PDF/Word 如果安装了对应库则解析，否则跳过。
    """
    suffix = filepath.suffix.lower()

    if suffix == ".md":
        return _parse_markdown(filepath, module)
    elif suffix == ".pdf":
        return _parse_pdf(filepath, module)
    elif suffix in (".docx", ".doc"):
        return _parse_docx(filepath, module)
    else:
        console.print(f"  [yellow]不支持的文件格式: {filepath.name}[/yellow]")
        return None


def _parse_markdown(filepath: Path, module: str) -> KnowledgeEntry | None:
    """解析 Markdown 文件"""
    try:
        # 尝试从 YAML frontmatter 解析
        entry = KnowledgeEntry.from_markdown(filepath)
        # 覆盖模块名
        entry.module = module
        return entry
    except ValueError:
        # 没有 frontmatter，创建新条目
        content = filepath.read_text(encoding="utf-8")
        return KnowledgeEntry.create(
            module=module,
            title=filepath.stem,
            entry_type="tech_doc",
            category="api_reference",
            content=content,
            source="manual_feed",
        )
    except Exception as e:
        console.print(f"  [red]解析 Markdown 失败 {filepath.name}: {e}[/red]")
        return None


def _parse_pdf(filepath: Path, module: str) -> KnowledgeEntry | None:
    """解析 PDF 文件（如果安装了 PyPDF2 或 pdfplumber）"""
    try:
        import pdfplumber  # type: ignore
        text_parts = []
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    text_parts.append(t)
        content = "\n\n".join(text_parts)
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
            reader = PdfReader(str(filepath))
            content = "\n\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            console.print(f"  [yellow]跳过 PDF (未安装 pdfplumber 或 PyPDF2): {filepath.name}[/yellow]")
            return None

    if not content.strip():
        console.print(f"  [yellow]PDF 内容为空: {filepath.name}[/yellow]")
        return None

    return KnowledgeEntry.create(
        module=module,
        title=filepath.stem,
        entry_type="tech_doc",
        category="api_reference",
        content=content,
        source="manual_feed",
    )


def _parse_docx(filepath: Path, module: str) -> KnowledgeEntry | None:
    """解析 Word 文件（如果安装了 python-docx）"""
    try:
        import docx  # type: ignore
        doc = docx.Document(str(filepath))
        content = "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
    except ImportError:
        console.print(f"  [yellow]跳过 Word (未安装 python-docx): {filepath.name}[/yellow]")
        return None

    if not content.strip():
        console.print(f"  [yellow]Word 内容为空: {filepath.name}[/yellow]")
        return None

    return KnowledgeEntry.create(
        module=module,
        title=filepath.stem,
        entry_type="tech_doc",
        category="api_reference",
        content=content,
        source="manual_feed",
    )


def _save_to_knowledge_base(entry: KnowledgeEntry, data_dir: Path, subdir: str = "docs") -> Path:
    """将知识条目保存为 Markdown 文件到 knowledge-base/ 目录"""
    module_dir = data_dir / entry.module / subdir
    module_dir.mkdir(parents=True, exist_ok=True)
    filepath = module_dir / f"{entry.id}.md"
    filepath.write_text(entry.to_markdown(), encoding="utf-8")
    return filepath


def _update_module_index(data_dir: Path, module: str, entry_id: str, subdir: str):
    """更新模块的 index.yaml"""
    index_path = data_dir / module / "index.yaml"
    if not index_path.exists():
        return

    try:
        with open(index_path, "r", encoding="utf-8") as f:
            index = yaml.safe_load(f) or {}
    except Exception:
        return

    entries = index.get("entries", {})
    sub_key = subdir
    if sub_key not in entries:
        entries[sub_key] = []

    if entry_id not in entries[sub_key]:
        entries[sub_key].append(entry_id)
        index["entries"] = entries
        index["updated"] = _now_date()

        with open(index_path, "w", encoding="utf-8") as f:
            yaml.dump(index, f, allow_unicode=True, default_flow_style=False)


def _now_date() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _is_already_indexed(db: KnowledgeDB, filepath: Path) -> bool:
    """增量模式：检查文件是否已被索引（基于文件名匹配标题）"""
    # 简单策略：如果文件内容哈希与已有条目匹配则跳过
    # 这里用文件修改时间作为简单判断
    return False


@click.command("feed_knowledge", help="投喂知识条目到知识库")
@click.option("--module", "-m", required=True, help="目标模块名")
@click.option("--docs", multiple=True, help="投喂技术文档 (支持 glob 模式)")
@click.option("--cases", multiple=True, help="投喂经验案例 (支持 glob 模式)")
@click.option("--dir", "feed_dir", help="投喂整个目录下的文件")
@click.option("--incremental", is_flag=True, help="增量模式：跳过已存在的条目")
@click.option("--type", "entry_type", default="tech_doc",
              type=click.Choice(["tech_doc", "experience_case", "analysis_log", "correction", "error_pattern"]),
              help="知识条目类型 (默认: tech_doc)")
@click.option("--category", "category", default="api_reference",
              type=click.Choice(["bug_analysis", "code_adaptation", "version_adaptation",
                                 "carrier_porting", "architecture", "api_reference",
                                 "protocol", "vendor_guide"]),
              help="知识条目分类 (默认: api_reference)")
def main(module: str, docs: tuple, cases: tuple, feed_dir: str | None,
         incremental: bool, entry_type: str, category: str):
    """投喂知识条目"""
    console.print(f"[bold]TAHP 知识投喂 — 模块: {module}[/bold]\n")

    config = KnowledgeBaseConfig.from_yaml()
    data_dir = config.data_dir

    # 确保 knowledge-base/{module}/ 目录存在
    module_dir = data_dir / module
    module_dir.mkdir(parents=True, exist_ok=True)

    # 初始化数据库
    db = KnowledgeDB(config=config)

    # 收集文件
    doc_files = _collect_files(*docs) if docs else []
    case_files = _collect_files(*cases) if cases else []

    if feed_dir:
        feed_path = Path(feed_dir)
        if feed_path.exists():
            doc_files.extend(feed_path.rglob("*.md"))
            doc_files.extend(feed_path.rglob("*.pdf"))
            doc_files.extend(feed_path.rglob("*.docx"))
            doc_files = list(set(doc_files))

    if not doc_files and not case_files:
        console.print("[yellow]未指定任何文件，使用 --docs / --cases / --dir 指定[/yellow]")
        return

    # 处理文档文件
    results = {"success": 0, "skipped": 0, "failed": 0}
    table = Table(title="投喂报告", show_header=True, header_style="bold")
    table.add_column("文件", style="cyan")
    table.add_column("条目 ID", style="green")
    table.add_column("状态", style="green")
    table.add_column("说明")

    for filepath in doc_files:
        entry = _parse_file(filepath, module)
        if entry is None:
            results["failed"] += 1
            table.add_row(filepath.name, "", "[red]失败[/red]", "解析失败")
            continue

        # 覆盖类型和分类（如果命令行指定了）
        entry.type = entry_type
        entry.category = category

        # 增量模式检查
        if incremental:
            existing = db.get_entry(entry.id)
            if existing:
                results["skipped"] += 1
                table.add_row(filepath.name, entry.id, "[yellow]跳过[/yellow]", "已存在")
                continue

        try:
            # 保存到 knowledge-base 目录
            saved_path = _save_to_knowledge_base(entry, data_dir, "docs")

            # 存入 ChromaDB
            db.add_entry(entry)

            # 更新 index.yaml
            _update_module_index(data_dir, module, entry.id, "docs")

            results["success"] += 1
            table.add_row(filepath.name, entry.id, "[green]成功[/green]", str(saved_path))
        except Exception as e:
            results["failed"] += 1
            table.add_row(filepath.name, "", "[red]失败[/red]", str(e))

    # 处理案例文件
    for filepath in case_files:
        entry = _parse_file(filepath, module)
        if entry is None:
            results["failed"] += 1
            table.add_row(filepath.name, "", "[red]失败[/red]", "解析失败")
            continue

        entry.type = "experience_case"

        try:
            saved_path = _save_to_knowledge_base(entry, data_dir, "cases")
            db.add_entry(entry)
            _update_module_index(data_dir, module, entry.id, "cases")

            results["success"] += 1
            table.add_row(filepath.name, entry.id, "[green]成功[/green]", str(saved_path))
        except Exception as e:
            results["failed"] += 1
            table.add_row(filepath.name, "", "[red]失败[/red]", str(e))

    console.print(table)

    # 汇总
    console.print(f"\n[bold]投喂汇总[/bold]")
    console.print(f"  成功: {results['success']}")
    console.print(f"  跳过: {results['skipped']}")
    console.print(f"  失败: {results['failed']}")

    # 最终统计
    stats = db.get_stats()
    console.print(f"\n  知识库总条目数: {stats['total']}")


if __name__ == "__main__":
    main()
