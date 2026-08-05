"""Parse MTK perf-statistic.html (Bokeh embedded JSON) into structured tables."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_CLUSTER_TITLE_RE = re.compile(
    r"cluster(?P<cluster>\d+)\s*\(\s*cpu(?P<cpu>\d+)\s*\)\s*frequency\s+histogram\s*\(MHz\)",
    re.I,
)
_JSON_SCRIPT_RE = re.compile(
    r'<script\s+type=["\']application/json["\'][^>]*>(.*?)</script>',
    re.I | re.S,
)


def _map_entries(data: Any) -> dict[str, Any]:
    if isinstance(data, dict) and data.get("type") == "map":
        entries = data.get("entries") or []
        out: dict[str, Any] = {}
        for item in entries:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out[str(item[0])] = item[1]
        return out
    if isinstance(data, dict):
        return dict(data)
    return {}


def _ndarray_to_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict) and value.get("type") == "ndarray":
        arr = value.get("array")
        if isinstance(arr, list):
            return arr
        # Binary ndarray (e.g. index) — skip payload, keep shape metadata only.
        return []
    return []


def _cds_columns(cds_attrs: dict[str, Any]) -> dict[str, list[Any]]:
    data = _map_entries(cds_attrs.get("data"))
    return {k: _ndarray_to_list(v) for k, v in data.items()}


def _walk(obj: Any, visit: Any) -> None:
    if isinstance(obj, dict):
        visit(obj)
        for v in obj.values():
            _walk(v, visit)
    elif isinstance(obj, list):
        for v in obj:
            _walk(v, visit)


def extract_bokeh_docs(html_text: str) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for m in _JSON_SCRIPT_RE.finditer(html_text):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            for doc in payload.values():
                if isinstance(doc, dict):
                    docs.append(doc)
    return docs


def _figure_title(figure_attrs: dict[str, Any]) -> str:
    title = figure_attrs.get("title")
    if isinstance(title, dict):
        return str((title.get("attributes") or {}).get("text") or "").strip()
    return ""


def _collect_figure_cds(figure_attrs: dict[str, Any]) -> list[dict[str, list[Any]]]:
    found: list[dict[str, list[Any]]] = []

    def visit(node: dict[str, Any]) -> None:
        if node.get("name") != "ColumnDataSource":
            return
        cols = _cds_columns(node.get("attributes") or {})
        if cols:
            found.append(cols)

    _walk(figure_attrs, visit)
    return found


def _collect_datatables(doc: dict[str, Any]) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []

    def visit(node: dict[str, Any]) -> None:
        if node.get("name") != "DataTable":
            return
        attrs = node.get("attributes") or {}
        source = attrs.get("source")
        cols_meta = attrs.get("columns") or []
        field_titles: dict[str, str] = {}
        for col in cols_meta:
            if not isinstance(col, dict):
                continue
            ca = col.get("attributes") or {}
            field = str(ca.get("field") or "")
            title = str(ca.get("title") or field)
            if field:
                field_titles[field] = title
        columns: dict[str, list[Any]] = {}
        if isinstance(source, dict) and source.get("name") == "ColumnDataSource":
            columns = _cds_columns(source.get("attributes") or {})
        tables.append({"fields": field_titles, "columns": columns})

    _walk(doc, visit)
    return tables


def parse_perf_statistic_html(path: Path | str) -> dict[str, Any]:
    """Parse MTK PerformanceTools `perf-statistic.html` into typed sections."""
    html_path = Path(path)
    text = html_path.read_text(encoding="utf-8", errors="replace")
    docs = extract_bokeh_docs(text)
    if not docs:
        return {
            "status": "failed",
            "error": "no_bokeh_application_json",
            "source_path": str(html_path),
        }

    cpu_loading: list[dict[str, Any]] = []
    clusters: list[dict[str, Any]] = []
    figures: list[dict[str, Any]] = []

    for doc in docs:
        def visit_figure(node: dict[str, Any]) -> None:
            if node.get("name") != "Figure":
                return
            attrs = node.get("attributes") or {}
            title = _figure_title(attrs)
            cds_list = _collect_figure_cds(attrs)
            figures.append({"title": title, "cds_count": len(cds_list)})

            if title == "CPU Loading Analysis" and cds_list:
                cols = cds_list[0]
                names = [str(x) for x in cols.get("x_names") or []]
                loading = cols.get("loading") or []
                idle = cols.get("idle") or []
                for i, name in enumerate(names):
                    cpu_loading.append(
                        {
                            "cpu": name,
                            "loading_pct": float(loading[i]) if i < len(loading) else None,
                            "idle_pct": float(idle[i]) if i < len(idle) else None,
                        }
                    )
                return

            m = _CLUSTER_TITLE_RE.search(title or "")
            if not m or not cds_list:
                return
            cols = cds_list[0]
            freqs = [int(float(x)) for x in (cols.get("x_names") or [])]
            running = [float(x) for x in (cols.get("running") or [])]
            residency = [
                {"freq_mhz": freqs[i], "ratio_pct": running[i]}
                for i in range(min(len(freqs), len(running)))
            ]
            clusters.append(
                {
                    "cluster": int(m.group("cluster")),
                    "anchor_cpu": int(m.group("cpu")),
                    "title": title,
                    "residency": residency,
                }
            )

        _walk(doc, visit_figure)

    tables = []
    for doc in docs:
        tables.extend(_collect_datatables(doc))

    raw_threads = _table_rows(
        tables,
        prefer_fields=("tid", "tname", "pid", "pname", "loading"),
        limit=0,
        score_cluster_cols=True,
    )
    threads = normalize_thread_rows(raw_threads)
    threads_sorted = sorted(
        threads,
        key=lambda t: -(float(t.get("loading_pct") or 0)),
    )
    top_threads = threads_sorted[:100]

    top_processes = _table_rows(
        tables,
        prefer_fields=("pid", "pname", "loading"),
        limit=20,
        require_missing=("tid", "tname"),
    )

    status = "ok" if (cpu_loading or clusters) else "failed"
    return {
        "status": status,
        "source_path": str(html_path),
        "format": "mtk_perf_statistic_bokeh",
        "figures": figures,
        "cpu_loading": cpu_loading,
        "clusters": sorted(clusters, key=lambda c: c["cluster"]),
        "threads": threads_sorted,
        "top_threads": top_threads,
        "thread_cluster_stats": summarize_thread_placement(threads_sorted),
        "top_processes": top_processes,
        "error": None if status == "ok" else "no_cpu_or_cluster_charts",
    }


def _to_float(val: Any) -> float | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace("%", "")
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_cluster_pair(
    row: dict[str, Any],
) -> tuple[float | None, float | None]:
    """Parse little(C0) / big(C1) placement % from perf-statistic By Thread table."""
    l0 = _to_float(row.get("c_loading_0"))
    l1 = _to_float(row.get("c_loading_1"))
    if l0 is not None and l1 is not None:
        return l0, l1
    raw = row.get("c_loading")
    if raw is None:
        return None, None
    s = str(raw).strip()
    if "/" in s:
        a, b = s.split("/", 1)
        return _to_float(a), _to_float(b)
    return None, None


def _placement_label(little_pct: float | None, big_pct: float | None) -> str | None:
    if little_pct is None or big_pct is None:
        return None
    if big_pct >= 95.0:
        return "big_only"
    if little_pct >= 95.0:
        return "little_only"
    if big_pct >= 60.0:
        return "big_majority"
    if little_pct >= 60.0:
        return "little_majority"
    return "mixed"


def normalize_thread_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize By Thread row: loading + little/big cluster placement."""
    loading = _to_float(row.get("loading"))
    little_pct, big_pct = _parse_cluster_pair(row)
    c0_run = _to_float(row.get("C0_running"))
    c1_run = _to_float(row.get("C1_running"))
    runnable_s = _to_float(row.get("Runnable"))
    runnable_pct = _to_float(row.get("Runnable(%)"))

    loading_on_little = None
    loading_on_big = None
    if loading is not None and little_pct is not None:
        loading_on_little = round(loading * little_pct / 100.0, 3)
    if loading is not None and big_pct is not None:
        loading_on_big = round(loading * big_pct / 100.0, 3)

    tid = row.get("tid")
    pid = row.get("pid")
    try:
        tid = int(tid) if tid is not None else None
    except (TypeError, ValueError):
        pass
    try:
        pid = int(pid) if pid is not None else None
    except (TypeError, ValueError):
        pass

    out: dict[str, Any] = {
        "tid": tid,
        "tname": row.get("tname"),
        "pid": pid,
        "pname": row.get("pname"),
        "loading_pct": round(loading, 3) if loading is not None else None,
        "little_cluster_pct": round(little_pct, 2) if little_pct is not None else None,
        "big_cluster_pct": round(big_pct, 2) if big_pct is not None else None,
        "loading_on_little_pct": loading_on_little,
        "loading_on_big_pct": loading_on_big,
        "little_running_s": round(c0_run, 6) if c0_run is not None else None,
        "big_running_s": round(c1_run, 6) if c1_run is not None else None,
        "runnable_s": round(runnable_s, 6) if runnable_s is not None else None,
        "runnable_pct": round(runnable_pct, 3) if runnable_pct is not None else None,
        "placement": _placement_label(little_pct, big_pct),
        "c_loading": row.get("c_loading"),
    }
    return out


def normalize_thread_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_thread_row(r) for r in rows]


def summarize_thread_placement(threads: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate thread little/big placement + loading rollups."""
    with_placement = [t for t in threads if t.get("little_cluster_pct") is not None]
    total_loading = sum(float(t.get("loading_pct") or 0) for t in threads)
    total_on_little = sum(float(t.get("loading_on_little_pct") or 0) for t in threads)
    total_on_big = sum(float(t.get("loading_on_big_pct") or 0) for t in threads)
    by_placement: dict[str, int] = {}
    for t in with_placement:
        label = t.get("placement") or "unknown"
        by_placement[label] = by_placement.get(label, 0) + 1
    top_big = sorted(
        with_placement,
        key=lambda t: -(float(t.get("loading_on_big_pct") or 0)),
    )[:10]
    top_little = sorted(
        with_placement,
        key=lambda t: -(float(t.get("loading_on_little_pct") or 0)),
    )[:10]
    return {
        "thread_count": len(threads),
        "threads_with_cluster_pct": len(with_placement),
        "total_loading_pct": round(total_loading, 2),
        "loading_on_little_sum_pct": round(total_on_little, 2),
        "loading_on_big_sum_pct": round(total_on_big, 2),
        "placement_counts": by_placement,
        "top_by_loading_on_big": [
            {
                "tname": t.get("tname"),
                "tid": t.get("tid"),
                "loading_pct": t.get("loading_pct"),
                "big_cluster_pct": t.get("big_cluster_pct"),
                "loading_on_big_pct": t.get("loading_on_big_pct"),
            }
            for t in top_big
        ],
        "top_by_loading_on_little": [
            {
                "tname": t.get("tname"),
                "tid": t.get("tid"),
                "loading_pct": t.get("loading_pct"),
                "little_cluster_pct": t.get("little_cluster_pct"),
                "loading_on_little_pct": t.get("loading_on_little_pct"),
            }
            for t in top_little
        ],
        "note": (
            "little_cluster_pct/big_cluster_pct 来自 HTML C0/C1(%)，表示线程运行时间落核分布；"
            "loading_on_* = loading_pct × cluster_pct/100，为对各簇 loading 贡献的估算"
        ),
    }


def _table_rows(
    tables: list[dict[str, Any]],
    *,
    prefer_fields: tuple[str, ...],
    limit: int,
    require_missing: tuple[str, ...] = (),
    score_cluster_cols: bool = False,
) -> list[dict[str, Any]]:
    best: list[dict[str, Any]] = []
    best_score = -1
    for table in tables:
        cols = table.get("columns") or {}
        if require_missing and any(f in cols and cols[f] for f in require_missing):
            continue
        if not all(f in cols for f in prefer_fields):
            continue
        n = min(len(cols[f]) for f in prefer_fields)
        score = n
        if score_cluster_cols and "c_loading_0" in cols and "c_loading_1" in cols:
            score += 100_000
        if score < best_score:
            continue
        rows: list[dict[str, Any]] = []
        for i in range(n):
            row: dict[str, Any] = {}
            for f in prefer_fields:
                val = cols[f][i]
                if f in ("loading", "Runnable", "Runnable(%)", "C0_running", "C1_running", "us"):
                    val = _to_float(val)
                if f in ("tid", "pid"):
                    try:
                        val = int(val) if val is not None and val != "" else val
                    except (TypeError, ValueError):
                        pass
                row[f] = val
            for extra in (
                "c_loading",
                "c_loading_0",
                "c_loading_1",
                "C0_running",
                "C1_running",
                "Runnable",
                "Runnable(%)",
                "us",
            ):
                if extra in cols and i < len(cols[extra]):
                    val = cols[extra][i]
                    if extra in ("C0_running", "C1_running", "Runnable", "Runnable(%)", "us"):
                        val = _to_float(val)
                    row[extra] = val
            rows.append(row)
        if score > best_score or (score == best_score and len(rows) > len(best)):
            best = rows
            best_score = score
    if limit and limit > 0:
        return best[:limit]
    return best
