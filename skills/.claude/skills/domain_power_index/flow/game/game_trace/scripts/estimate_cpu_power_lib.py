"""CPU dynamic power estimate from perf-statistic loading × freq residency × energy workbook.

Ported from aitools/trace_compare/scripts/estimate_power.py for game_trace (HTML-only input).

Workbook (references/energy_efficiency.xlsx):
  * Sheet "项目": platform columns (D7300 / 25Ms / …) list device models.
  * Platform sheets: cpu,frep,power,specint,core
      cpu=c0(little)/c1(big), frep=MHz, power=active mW @100% busy per core.

Formula (idle/leakage ignored):
  P_i ≈ L_i * Σ_f P_act(c, f) * r_{c,f}
  P_CPU = Σ cores ;  I_mA = P_mW / VDD (default 4.0 V).
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
DEFAULT_VDD_V = 4.0
_SCRIPT_DIR = Path(__file__).resolve().parent
_DEFAULT_XLSX = _SCRIPT_DIR.parent / "references" / "energy_efficiency.xlsx"


class EnergyModelError(ValueError):
    """Raised when workbook / model / OPP lookup fails."""


def _mw_to_ma(mw: float, vdd: float = DEFAULT_VDD_V) -> float | None:
    return round(float(mw) / vdd, 2) if vdd else None


def _col_row(ref: str) -> tuple[int, int]:
    m = re.match(r"([A-Z]+)(\d+)", ref)
    if not m:
        return 0, 0
    col, row = m.group(1), int(m.group(2))
    n = 0
    for ch in col:
        n = n * 26 + (ord(ch) - 64)
    return n - 1, row - 1


def _xlsx_shared(z: zipfile.ZipFile) -> list[str]:
    try:
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    out: list[str] = []
    for si in root.findall("m:si", NS):
        texts = [t.text or "" for t in si.findall(".//m:t", NS)]
        out.append("".join(texts))
    return out


def _xlsx_sheet_rows(z: zipfile.ZipFile, sheet_path: str, shared: list[str]) -> list[list[Any]]:
    root = ET.fromstring(z.read(sheet_path))
    rows: dict[int, dict[int, Any]] = {}
    for c in root.findall(".//m:sheetData/m:row/m:c", NS):
        ref = c.get("r")
        if not ref:
            continue
        col, row = _col_row(ref)
        t = c.get("t")
        v = c.find("m:v", NS)
        if v is None or v.text is None:
            val: Any = None
        elif t == "s":
            val = shared[int(v.text)]
        else:
            try:
                val = float(v.text) if "." in v.text else int(v.text)
            except ValueError:
                val = v.text
        rows.setdefault(row, {})[col] = val
    if not rows:
        return []
    max_r = max(rows)
    max_c = max(max(r) for r in rows.values())
    return [[rows.get(r, {}).get(c) for c in range(max_c + 1)] for r in range(max_r + 1)]


def _xlsx_sheet_map(z: zipfile.ZipFile) -> dict[str, str]:
    wb = ET.fromstring(z.read("xl/workbook.xml"))
    rels = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    rid_to_target: dict[str, str] = {}
    for rel in rels:
        rid = rel.get("Id")
        if not rid:
            continue
        tgt = rel.get("Target") or ""
        if not tgt.startswith("xl/"):
            tgt = f"xl/{tgt.lstrip('/')}"
        rid_to_target[rid] = tgt
    out: dict[str, str] = {}
    for sh in wb.findall("m:sheets/m:sheet", NS):
        name = sh.get("name")
        rid = sh.get(
            "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
        )
        if name and rid and rid in rid_to_target:
            out[name] = rid_to_target[rid]
    return out


def load_workbook_tables(path: Path | str) -> dict[str, list[list[Any]]]:
    with zipfile.ZipFile(path, "r") as z:
        shared = _xlsx_shared(z)
        smap = _xlsx_sheet_map(z)
        return {name: _xlsx_sheet_rows(z, spath, shared) for name, spath in smap.items()}


def _norm(s: Any) -> str:
    if s is None:
        return ""
    return re.sub(r"[^A-Za-z0-9+]", "", str(s)).upper()


def load_project_map(tables: dict[str, list[list[Any]]]) -> tuple[dict[str, list[str]], dict[str, str]]:
    proj = None
    for name, rows in tables.items():
        if not rows:
            continue
        hdr = [str(c).strip() if c is not None else "" for c in rows[0]]
        if any(h in ("D7300", "25Ms", "25Ms+", "D8400") for h in hdr):
            proj = rows
            if name == "项目":
                break
    if proj is None:
        raise EnergyModelError('workbook missing "项目" sheet (device→platform map)')
    platforms = [str(c).strip() for c in proj[0] if c]
    plat_models = {p: [] for p in platforms}
    for row in proj[1:]:
        for i, p in enumerate(platforms):
            if i < len(row) and row[i]:
                plat_models[p].append(str(row[i]).strip())
    model_to_plat: dict[str, str] = {}
    for p, models in plat_models.items():
        for m in models:
            model_to_plat[_norm(m)] = p
    return plat_models, model_to_plat


def resolve_platform(model: str, model_to_plat: dict[str, str]) -> str:
    key = _norm(model)
    if key in model_to_plat:
        return model_to_plat[key]
    hits = [(m, p) for m, p in model_to_plat.items() if m and (m in key or key in m)]
    if len(hits) == 1:
        return hits[0][1]
    if len(hits) > 1:
        hits.sort(key=lambda x: -len(x[0]))
        return hits[0][1]
    raise EnergyModelError(
        f"model {model!r} not found in 项目 sheet; known: {', '.join(sorted(model_to_plat))}"
    )


def load_platform_opps(
    tables: dict[str, list[list[Any]]], platform: str
) -> dict[str, list[tuple[float, float, float | None]]]:
    if platform not in tables:
        raise EnergyModelError(f"platform sheet {platform!r} missing; have {list(tables)}")
    rows = tables[platform]
    if not rows:
        raise EnergyModelError(f"empty platform sheet {platform!r}")
    hdr = [str(c).strip().lower() if c is not None else "" for c in rows[0]]

    def idx(*names: str) -> int | None:
        for n in names:
            if n in hdr:
                return hdr.index(n)
        return None

    ic, ifr, ipw, isp = idx("cpu"), idx("frep", "freq", "frequency"), idx("power"), idx("specint")
    if ifr is None or ipw is None:
        raise EnergyModelError(f"sheet {platform!r} needs frep/power columns, got {hdr}")
    last_cpu = "c0"
    opps: dict[str, list[tuple[float, float, float | None]]] = {"c0": [], "c1": []}
    for row in rows[1:]:
        if not row or all(c is None or c == "" for c in row):
            continue
        cpu = row[ic] if ic is not None and ic < len(row) and row[ic] else last_cpu
        cpu = str(cpu).strip().lower()
        if cpu not in ("c0", "c1"):
            cpu = last_cpu
        last_cpu = cpu
        try:
            mhz = float(row[ifr])
            pw = float(row[ipw])
        except (TypeError, ValueError, IndexError):
            continue
        sp: float | None = None
        if isp is not None and isp < len(row) and row[isp] is not None:
            try:
                sp = float(row[isp])
            except (TypeError, ValueError):
                sp = None
        opps[cpu].append((mhz, pw, sp))
    for k in opps:
        opps[k].sort(key=lambda x: x[0])
        if not opps[k]:
            raise EnergyModelError(f"sheet {platform!r} has no OPPs for {k}")
    return opps


def nearest_opp(
    opps: list[tuple[float, float, float | None]], mhz: float
) -> tuple[float, float, float | None]:
    return min(opps, key=lambda o: abs(o[0] - mhz))


def resolve_energy_xlsx(xlsx: Path | str | None = None) -> Path:
    if xlsx:
        p = Path(xlsx)
        if p.is_file():
            return p.resolve()
        raise EnergyModelError(f"energy workbook not found: {p}")
    if _DEFAULT_XLSX.is_file():
        return _DEFAULT_XLSX.resolve()
    # Fallback: sibling aitools checkout
    alt = Path(r"e:/aitools/energy_efficiency.xlsx")
    if alt.is_file():
        return alt.resolve()
    raise EnergyModelError(
        f"energy workbook not found: {_DEFAULT_XLSX} (pass --xlsx)"
    )


def _parse_cpu_index(name: Any) -> int | None:
    s = str(name or "").strip().lower()
    m = re.search(r"(\d+)$", s)
    if m:
        return int(m.group(1))
    if s.isdigit():
        return int(s)
    return None


def assign_cluster_cpus(
    clusters: list[dict[str, Any]],
    cpu_loading: list[dict[str, Any]],
) -> list[list[int]]:
    """Map HTML cluster anchors → contiguous CPU id lists (little → big)."""
    n_cpus = 0
    for row in cpu_loading:
        idx = _parse_cpu_index(row.get("cpu"))
        if idx is not None:
            n_cpus = max(n_cpus, idx + 1)
    if n_cpus <= 0:
        n_cpus = max((int(c.get("anchor_cpu") or 0) for c in clusters), default=0) + 1

    ordered = sorted(clusters, key=lambda c: int(c.get("cluster") or 0))
    anchors = [int(c.get("anchor_cpu") or 0) for c in ordered]
    if not anchors:
        return []
    # Ensure anchors are non-decreasing; fall back to even split if weird.
    if any(anchors[i] > anchors[i + 1] for i in range(len(anchors) - 1)):
        step = max(1, n_cpus // len(anchors))
        anchors = [i * step for i in range(len(anchors))]

    cpu_lists: list[list[int]] = []
    for i, start in enumerate(anchors):
        end = anchors[i + 1] if i + 1 < len(anchors) else n_cpus
        cpu_lists.append(list(range(start, max(start + 1, end))))
    return cpu_lists


def build_trace_like_from_html(
    *,
    cpu_loading: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    duration_s: float = 0.0,
) -> dict[str, Any]:
    """Build a minimal trace-compare-shaped dict for estimate()."""
    cpu_lists = assign_cluster_cpus(clusters, cpu_loading)
    ordered = sorted(clusters, key=lambda c: int(c.get("cluster") or 0))

    max_cpu = -1
    busy_by_id: dict[int, float] = {}
    for row in cpu_loading:
        idx = _parse_cpu_index(row.get("cpu"))
        if idx is None:
            continue
        loading = row.get("loading_pct")
        if loading is None and row.get("idle_pct") is not None:
            loading = 100.0 - float(row["idle_pct"])
        busy_by_id[idx] = float(loading or 0.0)
        max_cpu = max(max_cpu, idx)
    for ids in cpu_lists:
        if ids:
            max_cpu = max(max_cpu, max(ids))

    cpus = [{"busy_pct": busy_by_id.get(i, 0.0)} for i in range(max_cpu + 1)]

    out_clusters: list[dict[str, Any]] = []
    for i, cl in enumerate(ordered):
        residency = cl.get("residency") or []
        # Prefer already-normalized game_trace cluster fields.
        if not residency and cl.get("top_residency"):
            residency = cl["top_residency"]
        residency_pct: dict[str, float] = {}
        for r in residency:
            mhz = int(float(r.get("freq_mhz") or 0))
            pct = float(r.get("ratio_pct") or 0.0)
            if mhz <= 0:
                continue
            # estimate() expects khz keys when reading residency_pct from trace
            residency_pct[str(mhz * 1000)] = pct
        core_ids = cpu_lists[i] if i < len(cpu_lists) else []
        busy = None
        if core_ids and cpus:
            vals = [float(cpus[cid]["busy_pct"]) for cid in core_ids if cid < len(cpus)]
            if vals:
                busy = round(sum(vals) / len(vals), 2)
        out_clusters.append(
            {
                "name": cl.get("name") or f"cluster{cl.get('cluster', i)}",
                "cpus": core_ids,
                "busy_pct": busy,
                "residency_pct": residency_pct,
            }
        )

    return {
        "duration_s": float(duration_s or 0.0),
        "cpu": cpus,
        "clusters": out_clusters,
    }


def estimate(
    trace: dict[str, Any],
    opps: dict[str, list[tuple[float, float, float | None]]],
    *,
    vdd_v: float = DEFAULT_VDD_V,
) -> dict[str, Any]:
    clusters = trace.get("clusters") or []
    cpus = trace.get("cpu") or []
    duration_s = float(trace.get("duration_s") or trace.get("window_s") or 0)

    result_clusters: list[dict[str, Any]] = []
    per_cpu: list[dict[str, Any]] = []
    total_mw = 0.0
    unmatched: list[dict[str, Any]] = []
    little_mw = big_mw = 0.0

    for ci, cl in enumerate(clusters):
        key = "c0" if ci == 0 else "c1"
        if len(clusters) == 1:
            key = "c0"
        plat_opps = opps[key]

        hist: dict[int, float] = {}
        for k, v in (cl.get("residency_pct") or {}).items():
            hist[int(int(k) / 1000)] = float(v)
        s = sum(hist.values()) or 1.0
        frac = {f: v / s for f, v in hist.items()}

        w_power = 0.0
        w_spec = 0.0
        detail: list[dict[str, Any]] = []
        for mhz, pct in sorted(frac.items()):
            omhz, pw, sp = nearest_opp(plat_opps, mhz)
            if abs(omhz - mhz) > 150:
                unmatched.append(
                    {"cluster": cl.get("name"), "trace_mhz": mhz, "table_mhz": omhz}
                )
            w_power += pw * pct
            if sp is not None:
                w_spec += sp * pct
            detail.append(
                {
                    "trace_mhz": mhz,
                    "table_mhz": omhz,
                    "residency_pct": round(pct * 100, 2),
                    "power_mW": pw,
                    "specint": sp,
                }
            )

        core_ids = cl.get("cpus") or []
        cluster_mw = 0.0
        core_rows: list[dict[str, Any]] = []
        for cpu_id in core_ids:
            if cpu_id >= len(cpus):
                continue
            L = float(cpus[cpu_id].get("busy_pct", 0)) / 100.0
            p_i = L * w_power
            cluster_mw += p_i
            row = {
                "cpu": cpu_id,
                "busy_pct": round(L * 100, 2),
                "avg_active_power_mW": round(w_power, 2),
                "est_power_mW": round(p_i, 2),
                "est_current_mA": _mw_to_ma(p_i, vdd_v),
            }
            core_rows.append(row)
            per_cpu.append(row)

        eta = (w_spec / w_power) if w_power > 0 and w_spec > 0 else None
        result_clusters.append(
            {
                "name": cl.get("name"),
                "platform_cpu": key,
                "cpus": core_ids,
                "busy_pct": cl.get("busy_pct"),
                "weighted_active_power_mW": round(w_power, 2),
                "weighted_specint": round(w_spec, 3) if w_spec else None,
                "efficiency_specint_per_mW": round(eta, 4) if eta else None,
                "est_power_mW": round(cluster_mw, 2),
                "est_current_mA": _mw_to_ma(cluster_mw, vdd_v),
                "opp_mix": detail,
                "cores": core_rows,
            }
        )
        total_mw += cluster_mw
        if key == "c0":
            little_mw = cluster_mw
        else:
            big_mw = cluster_mw

    energy_mJ = total_mw * duration_s
    return {
        "duration_s": round(duration_s, 3),
        "vdd_v": vdd_v,
        "little_cluster_mW": round(little_mw, 2),
        "little_cluster_mA": _mw_to_ma(little_mw, vdd_v),
        "big_cluster_mW": round(big_mw, 2),
        "big_cluster_mA": _mw_to_ma(big_mw, vdd_v),
        "est_cpu_power_mW": round(total_mw, 2),
        "est_cpu_current_mA": _mw_to_ma(total_mw, vdd_v),
        "est_cpu_energy_mJ": round(energy_mJ, 1),
        "clusters": result_clusters,
        "per_cpu": per_cpu,
        "freq_match_warnings": unmatched,
        "note": (
            "Dynamic CPU power = sum of all cores (little+big). "
            f"I_mA = P_mW / {vdd_v:.1f}V (battery-referred). "
            "Idle/leakage, GPU, DDR, display not included. "
            "HTML sample window has no duration → energy_mJ may be 0."
        ),
    }


def estimate_cpu_power_from_html(
    *,
    cpu_loading: list[dict[str, Any]],
    clusters: list[dict[str, Any]],
    soc_model: str,
    xlsx: Path | str | None = None,
    vdd_v: float = DEFAULT_VDD_V,
    duration_s: float = 0.0,
) -> dict[str, Any]:
    """Estimate CPU dynamic power from game_trace HTML fields + device model."""
    model = (soc_model or "").strip()
    if not model:
        return {
            "status": "skipped",
            "reason": "soc_model_missing",
            "note": "未提供 --soc-model，跳过能效表功耗估算",
        }
    if not cpu_loading or not clusters:
        return {
            "status": "skipped",
            "reason": "missing_loading_or_freq",
            "note": "缺少 cpu_loading 或频率分布，无法估算功耗",
        }

    xlsx_path = resolve_energy_xlsx(xlsx)
    tables = load_workbook_tables(xlsx_path)
    _, model_to_plat = load_project_map(tables)
    platform = resolve_platform(model, model_to_plat)
    opps = load_platform_opps(tables, platform)
    trace_like = build_trace_like_from_html(
        cpu_loading=cpu_loading,
        clusters=clusters,
        duration_s=duration_s,
    )
    est = estimate(trace_like, opps, vdd_v=vdd_v)
    est["status"] = "ok"
    est["model"] = model
    est["platform"] = platform
    est["xlsx"] = str(xlsx_path)
    est["source"] = "perf_statistic_html"
    return est
