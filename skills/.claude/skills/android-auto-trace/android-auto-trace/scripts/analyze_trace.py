#!/usr/bin/env python3
"""Analyze Perfetto trace: process CPU usage and slice durations."""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path


# Workspace root: D:\AI2D\android-auto-trace (scripts live two levels deeper)
WORKSPACE_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = WORKSPACE_ROOT / "tools"

# Pinned Perfetto prebuilt (native binary only — no C: cache under ~/.local or ~/.lingma)
PERFETTO_VERSION = "v57.2"
TP_ARTIFACTS = {
    ("win32", "amd64"): (
        f"https://commondatastorage.googleapis.com/perfetto-luci-artifacts/"
        f"{PERFETTO_VERSION}/windows-amd64/trace_processor_shell.exe",
        "100334b6091596fbc97f872556849a5747bf47a7f7190c485ba8cea8d2409c7b",
        "trace_processor_shell.exe",
    ),
    ("linux", "x86_64"): (
        f"https://commondatastorage.googleapis.com/perfetto-luci-artifacts/"
        f"{PERFETTO_VERSION}/linux-amd64/trace_processor_shell",
        None,
        "trace_processor_shell",
    ),
    ("darwin", "x86_64"): (
        f"https://commondatastorage.googleapis.com/perfetto-luci-artifacts/"
        f"{PERFETTO_VERSION}/mac-amd64/trace_processor_shell",
        None,
        "trace_processor_shell",
    ),
    ("darwin", "arm64"): (
        f"https://commondatastorage.googleapis.com/perfetto-luci-artifacts/"
        f"{PERFETTO_VERSION}/mac-arm64/trace_processor_shell",
        None,
        "trace_processor_shell",
    ),
}


def escape_sql(value):
    """Escape single quotes for SQLite LIKE queries."""
    return value.replace("'", "''")


def _platform_key():
    plat = sys.platform.lower()
    machine = platform.machine().lower()
    if machine in ("amd64", "x86_64"):
        machine = "amd64" if plat == "win32" else "x86_64"
    elif machine in ("aarch64",):
        machine = "arm64"
    return plat, machine


def _download_file(url, dest):
    """Download url to dest; prefer urllib, fall back to curl --ssl-no-revoke on Windows."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=120) as response, open(tmp, "wb") as f:
            shutil.copyfileobj(response, f)
    except Exception:
        curl = ["curl", "-f", "-L", "-o", str(tmp), url]
        if sys.platform == "win32":
            curl.insert(1, "--ssl-no-revoke")
        subprocess.check_call(curl)
    os.replace(tmp, dest)


def get_trace_processor():
    """Return argv prefix that invokes native trace_processor under WORKSPACE/tools."""
    found = shutil.which("trace_processor_shell") or shutil.which("trace_processor")
    if found and Path(found).is_absolute():
        # Only accept PATH hits that already live under the workspace tools dir
        try:
            if Path(found).resolve().is_relative_to(TOOLS_DIR.resolve()):
                return [found]
        except (ValueError, AttributeError):
            pass

    plat, machine = _platform_key()
    artifact = TP_ARTIFACTS.get((plat, machine))
    if artifact is None and plat == "win32" and machine == "x86_64":
        artifact = TP_ARTIFACTS.get(("win32", "amd64"))
    if artifact is None:
        print(
            f"No prebuilt trace_processor for {plat}-{machine}. "
            f"Place the binary under {TOOLS_DIR}",
            file=sys.stderr,
        )
        sys.exit(1)

    url, sha256, file_name = artifact
    tp = TOOLS_DIR / file_name
    if not tp.exists():
        print(f"Downloading trace_processor to {tp} ...")
        try:
            _download_file(url, tp)
        except Exception as e:
            print(f"Download failed: {e}", file=sys.stderr)
            sys.exit(1)
        if sha256:
            digest = hashlib.sha256(tp.read_bytes()).hexdigest()
            if digest != sha256:
                tp.unlink(missing_ok=True)
                print(f"Checksum mismatch for {tp}", file=sys.stderr)
                sys.exit(1)
        os.chmod(tp, 0o755)
        print(f"trace_processor installed to {tp}")

    return [str(tp)]


def _run_query(tp, trace, sql):
    """Run a query; return (ok, stdout, stderr) without exiting."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as f:
        f.write(sql)
        sql_file = f.name
    try:
        # tp is argv prefix (list); support legacy string path too
        prefix = tp if isinstance(tp, list) else [tp]
        cmd = prefix + [trace, "-q", sql_file]
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    finally:
        os.unlink(sql_file)


def query(tp, trace, sql):
    ok, stdout, stderr = _run_query(tp, trace, sql)
    if not ok:
        print(f"Query failed: {stderr}", file=sys.stderr)
        sys.exit(1)
    return stdout


def query_soft(tp, trace, sql):
    """Run a query, returning stdout on success or None on failure (no exit)."""
    ok, stdout, _ = _run_query(tp, trace, sql)
    return stdout if ok else None


def analyze_process(tp, trace, name):
    safe = escape_sql(name)

    summary_sql = f"""
    SELECT
        p.name AS process_name,
        COUNT(DISTINCT t.utid) AS threads,
        ROUND(SUM(ts.dur) / 1e6, 2) AS cpu_ms,
        ROUND((SELECT end_ts - start_ts FROM trace_bounds) / 1e6, 2) AS trace_ms,
        ROUND(SUM(ts.dur) * 100.0 / NULLIF((SELECT SUM(dur) FROM thread_state WHERE state = 'Running'), 0), 2) AS cpu_pct
    FROM process p
    JOIN thread t ON t.upid = p.upid
    JOIN thread_state ts ON ts.utid = t.utid AND ts.state = 'Running'
    WHERE p.name LIKE '%{safe}%'
    GROUP BY p.upid
    ORDER BY cpu_ms DESC;
    """

    thread_sql = f"""
    SELECT
        t.name AS thread_name,
        ROUND(SUM(ts.dur) / 1e6, 2) AS cpu_ms,
        ROUND(SUM(ts.dur) * 100.0 / NULLIF(
            (SELECT SUM(ts2.dur)
             FROM thread_state ts2
             JOIN thread t2 ON t2.utid = ts2.utid
             JOIN process p2 ON p2.upid = t2.upid
             WHERE p2.name LIKE '%{safe}%' AND ts2.state = 'Running'), 0), 2) AS cpu_pct
    FROM process p
    JOIN thread t ON t.upid = p.upid
    JOIN thread_state ts ON ts.utid = t.utid AND ts.state = 'Running'
    WHERE p.name LIKE '%{safe}%'
    GROUP BY t.utid, t.name
    ORDER BY cpu_ms DESC;
    """

    top_slices_sql = f"""
    SELECT
        s.name AS slice_name,
        COUNT(DISTINCT s.id) AS count,
        ROUND(SUM(COALESCE(cpu.cpu_dur, 0)) / 1e6, 2) AS total_cpu_ms,
        ROUND(AVG(COALESCE(cpu.cpu_dur, 0)) / 1e6, 2) AS avg_cpu_ms
    FROM slice s
    JOIN thread_track tt ON s.track_id = tt.id
    JOIN thread t ON tt.utid = t.utid
    JOIN process p ON t.upid = p.upid
    LEFT JOIN (
        SELECT
            s.id AS slice_id,
            COALESCE(SUM(
                MIN(s.ts + s.dur, ts.ts + ts.dur) - MAX(s.ts, ts.ts)
            ), 0) AS cpu_dur
        FROM slice s
        JOIN thread_track tt ON s.track_id = tt.id
        JOIN thread t ON tt.utid = t.utid
        JOIN process p ON t.upid = p.upid
        JOIN thread_state ts ON ts.utid = t.utid
            AND ts.ts < s.ts + s.dur
            AND ts.ts + ts.dur > s.ts
            AND ts.state = 'Running'
        WHERE p.name LIKE '%{safe}%'
        GROUP BY s.id
    ) cpu ON cpu.slice_id = s.id
    WHERE p.name LIKE '%{safe}%'
    GROUP BY s.name
    ORDER BY SUM(COALESCE(cpu.cpu_dur, 0)) DESC
    LIMIT 10;
    """

    summary = query(tp, trace, summary_sql)
    threads = query(tp, trace, thread_sql)
    top_slices = query(tp, trace, top_slices_sql)
    return summary + "\n=== Per-Thread Breakdown ===\n" + threads + "\n=== Top 10 Slices by CPU Time ===\n" + top_slices


def analyze_slice(tp, trace, name):
    safe = escape_sql(name)

    summary_sql = f"""
    SELECT
        s.name AS slice_name,
        COUNT(DISTINCT s.id) AS count,
        ROUND(SUM(cpu.cpu_dur) / 1e6, 2) AS total_cpu_ms,
        ROUND(AVG(cpu.cpu_dur) / 1e6, 2) AS avg_cpu_ms,
        ROUND(SUM(cpu.cpu_dur) * 100.0 / (SELECT end_ts - start_ts FROM trace_bounds), 2) AS cpu_pct
    FROM slice s
    JOIN thread_track tt ON s.track_id = tt.id
    JOIN thread t ON tt.utid = t.utid
    LEFT JOIN (
        SELECT
            s.id AS slice_id,
            COALESCE(SUM(
                MIN(s.ts + s.dur, ts.ts + ts.dur) - MAX(s.ts, ts.ts)
            ), 0) AS cpu_dur
        FROM slice s
        JOIN thread_track tt ON s.track_id = tt.id
        JOIN thread t ON tt.utid = t.utid
        JOIN thread_state ts ON ts.utid = t.utid
            AND ts.ts < s.ts + s.dur
            AND ts.ts + ts.dur > s.ts
            AND ts.state = 'Running'
        WHERE s.name LIKE '%{safe}%'
        GROUP BY s.id
    ) cpu ON cpu.slice_id = s.id
    WHERE s.name LIKE '%{safe}%'
    GROUP BY s.name
    ORDER BY total_cpu_ms DESC;
    """

    top10_sql = f"""
    SELECT
        s.ts AS timestamp,
        p.name AS process_name,
        t.name AS thread_name,
        ROUND(COALESCE(cpu.cpu_dur, 0) / 1e6, 2) AS cpu_ms
    FROM slice s
    JOIN thread_track tt ON s.track_id = tt.id
    JOIN thread t ON tt.utid = t.utid
    JOIN process p ON t.upid = p.upid
    LEFT JOIN (
        SELECT
            s.id AS slice_id,
            COALESCE(SUM(
                MIN(s.ts + s.dur, ts.ts + ts.dur) - MAX(s.ts, ts.ts)
            ), 0) AS cpu_dur
        FROM slice s
        JOIN thread_track tt ON s.track_id = tt.id
        JOIN thread t ON tt.utid = t.utid
        JOIN thread_state ts ON ts.utid = t.utid
            AND ts.ts < s.ts + s.dur
            AND ts.ts + ts.dur > s.ts
            AND ts.state = 'Running'
        WHERE s.name LIKE '%{safe}%'
        GROUP BY s.id
    ) cpu ON cpu.slice_id = s.id
    WHERE s.name LIKE '%{safe}%'
    ORDER BY COALESCE(cpu.cpu_dur, 0) DESC
    LIMIT 10;
    """

    summary = query(tp, trace, summary_sql)
    top10 = query(tp, trace, top10_sql)
    return summary + "\n=== Top 10 Instances by CPU Time ===\n" + top10


def _fps_sql(frames_cte):
    """Build FPS summary SQL given a `frames(ts)` CTE body."""
    return f"""
    WITH bounds AS (SELECT start_ts AS s, end_ts AS e FROM trace_bounds),
    frames AS ({frames_cte}),
    bucket AS (
        SELECT CAST((f.ts - (SELECT s FROM bounds)) / 1000000000 AS INT) AS sec,
               COUNT(*) AS n
        FROM frames f
        GROUP BY sec
    )
    SELECT
        (SELECT COUNT(*) FROM frames) AS frames,
        ROUND((SELECT (e - s) FROM bounds) / 1e9, 3) AS trace_s,
        ROUND((SELECT COUNT(*) FROM frames) * 1e9
              / NULLIF((SELECT (e - s) FROM bounds), 0), 2) AS avg_fps,
        (SELECT MIN(n) FROM bucket) AS min_fps_1s,
        (SELECT MAX(n) FROM bucket) AS max_fps_1s;
    """


def _fps_frame_count(csv_text):
    """Extract the frame count (first column of the single data row) from FPS CSV."""
    if not csv_text:
        return 0
    lines = [ln for ln in csv_text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        return 0
    first = lines[1].split(",")[0].strip().strip('"')
    try:
        return int(float(first))
    except ValueError:
        return 0


def analyze_fps(tp, trace, name):
    safe = escape_sql(name)

    # Preferred source: SurfaceFlinger FrameTimeline (accurate per-app presented frames).
    frametimeline_cte = f"""
        SELECT af.ts AS ts
        FROM actual_frame_timeline_slice af
        JOIN process p ON p.upid = af.upid
        WHERE p.name LIKE '%{safe}%'
    """

    def slice_cte(name_clause):
        return f"""
            SELECT s.ts AS ts
            FROM slice s
            JOIN thread_track tt ON s.track_id = tt.id
            JOIN thread t ON tt.utid = t.utid
            JOIN process p ON p.upid = t.upid
            WHERE p.name LIKE '%{safe}%' AND ({name_clause})
        """

    # Fallback per-frame markers, tried in priority order (first with frames wins).
    # Different builds/activities emit different markers; these each fire once per
    # produced app frame, so we never combine them (would double-count).
    fallback_markers = [
        ("Choreographer#doFrame", "s.name = 'Choreographer#doFrame'"),
        ("DrawFrame (RenderThread)", "s.name GLOB 'DrawFrame*'"),
        ("draw-VRI (ViewRootImpl draw)", "s.name LIKE 'draw-VRI[%'"),
        ("renderFrameImpl (RenderThread)", "s.name = 'renderFrameImpl'"),
    ]

    # 1) Try FrameTimeline first.
    out = query_soft(tp, trace, _fps_sql(frametimeline_cte))
    if out is not None and _fps_frame_count(out) > 0:
        return "source: FrameTimeline (actual_frame_timeline_slice)\n" + out

    # 2) Fall back to per-frame slice markers.
    for label, clause in fallback_markers:
        out = query_soft(tp, trace, _fps_sql(slice_cte(clause)))
        if out is not None and _fps_frame_count(out) > 0:
            return (f"source: {label} (fallback; capture with FrameTimeline "
                    f"for best accuracy)\n" + out)

    return (f"No frames found for '{name}'. Tried FrameTimeline and slice markers "
            f"(Choreographer#doFrame, DrawFrame, draw-VRI, renderFrameImpl). "
            f"Re-capture with the default config (FrameTimeline enabled) and ensure "
            f"the app was on-screen/rendering.")


def analyze_cpufreq(tp, trace):
    # Time-weighted average CPU frequency per CPU from power/cpu_frequency counter.
    sql = """
    WITH freq AS (
        SELECT
            c.ts,
            c.value,
            c.track_id,
            COALESCE(
                LEAD(c.ts) OVER (PARTITION BY c.track_id ORDER BY c.ts),
                (SELECT end_ts FROM trace_bounds)
            ) - c.ts AS dur
        FROM counter c
        JOIN cpu_counter_track ct ON ct.id = c.track_id
        WHERE ct.name = 'cpufreq'
    )
    SELECT
        ct.cpu AS cpu,
        ROUND(SUM(freq.value * freq.dur) / NULLIF(SUM(freq.dur), 0) / 1000.0, 2) AS avg_mhz,
        ROUND(MIN(freq.value) / 1000.0, 2) AS min_mhz,
        ROUND(MAX(freq.value) / 1000.0, 2) AS max_mhz
    FROM freq
    JOIN cpu_counter_track ct ON ct.id = freq.track_id
    GROUP BY ct.cpu
    ORDER BY ct.cpu;
    """
    out = query_soft(tp, trace, sql)
    if out is None or len([ln for ln in out.strip().splitlines() if ln.strip()]) < 2:
        return ("No CPU frequency data found. Capture with the 'power/cpu_frequency' "
                "ftrace event enabled (default config already includes it).")
    return out


def _weighted_freq_query(where_clause, min_max_raw=0):
    """Time-weighted avg/min/max per matching counter_track, auto-normalized to MHz.

    Frequency counters come in different units across SoCs (Hz for devfreq,
    kHz for power/*_frequency, sometimes MHz). Normalize by magnitude of the
    average so the report is always in MHz. `min_max_raw` drops tracks whose
    peak value is too small to be a real frequency (e.g. 0/1 boolean counters).
    """
    return f"""
    WITH tracks AS (
        SELECT t.id AS tid, t.name AS name
        FROM counter_track t
        WHERE {where_clause}
    ),
    samples AS (
        SELECT
            c.track_id AS tid,
            c.value AS value,
            COALESCE(
                LEAD(c.ts) OVER (PARTITION BY c.track_id ORDER BY c.ts),
                (SELECT end_ts FROM trace_bounds)
            ) - c.ts AS dur
        FROM counter c
        WHERE c.track_id IN (SELECT tid FROM tracks)
    ),
    agg AS (
        SELECT
            s.tid AS tid,
            SUM(s.value * s.dur) / NULLIF(SUM(s.dur), 0) AS avg_raw,
            MIN(s.value) AS min_raw,
            MAX(s.value) AS max_raw
        FROM samples s
        GROUP BY s.tid
    )
    SELECT
        tr.name AS track,
        CASE WHEN a.avg_raw >= 1e7 THEN ROUND(a.avg_raw / 1e6, 2)
             WHEN a.avg_raw >= 1e4 THEN ROUND(a.avg_raw / 1e3, 2)
             ELSE ROUND(a.avg_raw, 2) END AS avg_mhz,
        CASE WHEN a.avg_raw >= 1e7 THEN ROUND(a.min_raw / 1e6, 2)
             WHEN a.avg_raw >= 1e4 THEN ROUND(a.min_raw / 1e3, 2)
             ELSE ROUND(a.min_raw, 2) END AS min_mhz,
        CASE WHEN a.avg_raw >= 1e7 THEN ROUND(a.max_raw / 1e6, 2)
             WHEN a.avg_raw >= 1e4 THEN ROUND(a.max_raw / 1e3, 2)
             ELSE ROUND(a.max_raw, 2) END AS max_mhz
    FROM agg a
    JOIN tracks tr ON tr.tid = a.tid
    WHERE a.avg_raw IS NOT NULL AND a.max_raw > {min_max_raw}
    ORDER BY tr.name;
    """


def analyze_gpufreq(tp, trace):
    # GPU frequency counters: must reference a clock/freq to avoid matching
    # GPU memory / completion counters.
    where = (
        "(lower(t.name) LIKE '%gpu%' AND ("
        "lower(t.name) LIKE '%freq%' OR lower(t.name) LIKE '%clk%' "
        "OR lower(t.name) LIKE '%clock%')) "
        "OR lower(t.name) = 'gpufreq' "
        "OR (lower(t.name) LIKE '%mali%' AND ("
        "lower(t.name) LIKE '%freq%' OR lower(t.name) LIKE '%clk%'))"
    )
    out = query_soft(tp, trace, _weighted_freq_query(where))
    if out is None or len([ln for ln in out.strip().splitlines() if ln.strip()]) < 2:
        return ("No GPU frequency data found. Re-capture with the default config "
                "(now includes 'power/gpu_frequency' and 'devfreq/devfreq_frequency').")
    return out


def analyze_ddrfreq(tp, trace):
    # DDR/DRAM/EMI memory-bus frequency counters (exclude CPU/GPU clocks).
    # 'emi'/'mem' are only accepted alongside a freq/clk/bw token to avoid
    # false positives like "PrevFrameMissed" (contains "emi").
    where = (
        "("
        "lower(t.name) LIKE '%ddr%' OR lower(t.name) LIKE '%dram%' "
        "OR lower(t.name) LIKE '%dvfsrc%' OR lower(t.name) LIKE '%bimc%' "
        "OR (lower(t.name) LIKE '%emi%' AND ("
        "lower(t.name) LIKE '%freq%' OR lower(t.name) LIKE '%clk%' "
        "OR lower(t.name) LIKE '%bw%')) "
        "OR (lower(t.name) LIKE '%devfreq%' AND lower(t.name) NOT LIKE '%gpu%') "
        "OR (lower(t.name) LIKE '%mem%' AND lower(t.name) LIKE '%freq%')"
        ") "
        "AND lower(t.name) NOT LIKE '%gpu%' AND lower(t.name) NOT LIKE '%mali%' "
        "AND lower(t.name) NOT LIKE '%cpu%' "
        "AND lower(t.name) NOT LIKE '%miss%' AND lower(t.name) NOT LIKE '%frame%'"
    )
    # DDR/DRAM frequency counters are always kHz/Hz (large); require a sizable
    # peak to filter out any residual boolean/count counters.
    out = query_soft(tp, trace, _weighted_freq_query(where, min_max_raw=1000))
    if out is None or len([ln for ln in out.strip().splitlines() if ln.strip()]) < 2:
        return ("No DDR/DRAM frequency data found. Re-capture with the default config "
                "(now includes 'devfreq/devfreq_frequency' and 'power/clock_set_rate'). "
                "Note: some SoCs do not expose DDR frequency to ftrace at all.")
    return out


def main():
    parser = argparse.ArgumentParser(description="Analyze Perfetto trace")
    parser.add_argument("trace", help="Path to .perfetto-trace file")
    parser.add_argument("-p", "--process", help="Process name to analyze (CPU usage)")
    parser.add_argument("-s", "--slice", help="Slice name to analyze (CPU time)")
    parser.add_argument("-f", "--fps", help="Process/Activity name to compute FPS for")
    parser.add_argument("--cpufreq", action="store_true",
                        help="Report time-weighted average CPU frequency per CPU")
    parser.add_argument("--gpufreq", action="store_true",
                        help="Report time-weighted average GPU frequency")
    parser.add_argument("--ddrfreq", action="store_true",
                        help="Report time-weighted average DDR/DRAM frequency")
    args = parser.parse_args()

    if not os.path.exists(args.trace):
        print(f"File not found: {args.trace}", file=sys.stderr)
        sys.exit(1)

    tp = get_trace_processor()

    if args.process:
        print(f"\n=== Process CPU: '{args.process}' ===")
        print(analyze_process(tp, args.trace, args.process))

    if args.slice:
        print(f"\n=== Slice CPU: '{args.slice}' ===")
        print(analyze_slice(tp, args.trace, args.slice))

    if args.fps:
        print(f"\n=== FPS: '{args.fps}' ===")
        print(analyze_fps(tp, args.trace, args.fps))

    if args.cpufreq:
        print(f"\n=== CPU Frequency (avg per CPU) ===")
        print(analyze_cpufreq(tp, args.trace))

    if args.gpufreq:
        print(f"\n=== GPU Frequency (avg, MHz) ===")
        print(analyze_gpufreq(tp, args.trace))

    if args.ddrfreq:
        print(f"\n=== DDR/DRAM Frequency (avg, MHz) ===")
        print(analyze_ddrfreq(tp, args.trace))

    if not any([args.process, args.slice, args.fps, args.cpufreq, args.gpufreq, args.ddrfreq]):
        print("Specify at least one of --process / --slice / --fps / --cpufreq / --gpufreq / --ddrfreq",
              file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
