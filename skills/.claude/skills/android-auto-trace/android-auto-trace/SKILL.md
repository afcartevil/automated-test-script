---
name: android-auto-trace
description: Capture and analyze Android Perfetto traces via adb. Automatically grabs trace files from connected devices and analyzes process CPU usage, FPS, CPU/GPU/DDR frequency, and named slice durations. When diagnosing a process's CPU usage, it reports CPU, FPS, and CPU/GPU frequency together. Use when the user wants to capture an Android trace, diagnose high CPU usage, analyze CPU usage of a process, measure FPS or CPU/GPU frequency, or find the total execution time of named trace slices.
---

# Android Auto Trace

## Overview

Automates Android Perfetto trace capture and analysis via `adb`.

## Quick Start

1. **Capture trace**: Run the capture script
2. **Analyze**: Run the analyze script with target process or slice name

## Capture Trace

### Basic Capture

```bash
python scripts/capture_trace.py --duration 10
```

If no `--output` is specified, each capture is saved in the same directory as this skill package with a unique timestamp (e.g., `android-auto-trace/trace_20260518_143022.perfetto-trace`). Previous captures are kept.

### With Custom Output Path

```bash
python scripts/capture_trace.py --duration 10 --output mytrace.perfetto-trace
```

### With Custom Atrace Categories

**Only use `--categories` when you need additional atrace categories beyond the default config.** The default config already includes standard tracing categories.

```bash
python scripts/capture_trace.py --duration 10 --categories dalvikviktime my_custom_tag
```

### With Custom Config

```bash
python scripts/capture_trace.py --duration 10 --config configs/my_custom_config.txt
```

**Environment Checks:**
- The script automatically checks if `adb` is installed and in PATH
- Verifies that a device is connected (USB or via `adb connect`)
- Validates the output directory exists and is writable
- Displays the device serial number before capturing

## Analyze Trace

All time metrics reported are **CPU time** — actual time the thread was scheduled on CPU, computed via precise intersection with `thread_state`. CPU percentages for processes must use **total system CPU time** (`SUM(dur) FROM thread_state WHERE state = 'Running'`) as the denominator to match Perfetto UI.

### Process CPU + Thread Breakdown

Shows total process CPU time, per-thread breakdown, and top 10 named slices by CPU time.

**Implementation requirements:**
- Use `thread_state` table with `state = 'Running'` filter for all CPU time calculations. Do **not** use `sched_slice` — it produces different totals than Perfetto UI.
- Process CPU percentage denominator: `SUM(dur) FROM thread_state WHERE state = 'Running'` (total system CPU time), not trace duration.
- Slice CPU time: compute via intersection of `slice` duration with overlapping `thread_state = 'Running'` intervals.
- Slice aggregation: group by `slice.name`, use `LIMIT 10` (show fewer only if <10 distinct names exist).
- Present results in a clean, readable format (tables or lists) — raw CSV is acceptable for script output but should be formatted for the user.

```bash
python scripts/analyze_trace.py mytrace.perfetto-trace --process "com.example.app"
```

Output:
- Process summary: total CPU time (ms), trace duration (ms), CPU percentage (relative to total system CPU time)
- Per-thread breakdown: each thread's CPU time (ms) and percentage within the process
- **Top 10 slices by CPU time**: aggregate CPU of the hottest named slices (count, total CPU, avg CPU)
  - Use `LIMIT 10`; if fewer than 10 distinct slice names exist, show all
  - **Important**: slice times can overlap (nested calls), so the sum of top slices may exceed total process CPU

### Slice CPU Summary + Top 10 Instances

Shows aggregate CPU stats for all slices matching a name, plus the top 10 individual instances by CPU time:

```bash
python scripts/analyze_trace.py mytrace.perfetto-trace --slice "Choreographer#doFrame"
```

Output:
- Summary: total count, total CPU time (ms), average CPU time (ms), CPU percentage of trace
- Top 10 instances: timestamp, process name, thread name, CPU time (ms)

### FPS (frame rate) of a Process / Activity

Computes frame rate for an app or activity from the trace:

```bash
python scripts/analyze_trace.py mytrace.perfetto-trace --fps "com.whatsapp"
```

Output columns: `frames`, `trace_s`, `avg_fps`, `min_fps_1s`, `max_fps_1s`, plus a `source:` line.
- **avg_fps** = total presented frames / trace duration.
- **min_fps_1s / max_fps_1s** = min/max frames counted in any 1-second bucket (instantaneous low/high).
- **Frame source priority**:
  1. `actual_frame_timeline_slice` (SurfaceFlinger FrameTimeline) — accurate per-app presented frames. Requires the `android.surfaceflinger.frametimeline` data source, which is now in the default capture config (Android 11+).
  2. Fallback: `Choreographer#doFrame` slices on the process threads (works on older traces but only counts UI-thread frames; less accurate for SurfaceView/video like a video call).
- The printed `source:` line tells you which method was used.

### CPU Frequency (average per CPU)

Reports the time-weighted average frequency of each CPU core:

```bash
python scripts/analyze_trace.py mytrace.perfetto-trace --cpufreq
```

Output columns: `cpu`, `avg_mhz`, `min_mhz`, `max_mhz`.
- Time-weighted average from the `power/cpu_frequency` ftrace counter (each frequency value weighted by how long it was held), then converted kHz → MHz.
- Included in the default config, so any capture supports this.

### GPU / DDR Frequency (average)

Reports time-weighted average frequency of the GPU and the DDR/DRAM memory bus:

```bash
python scripts/analyze_trace.py mytrace.perfetto-trace --gpufreq --ddrfreq
```

Output columns: `track`, `avg_mhz`, `min_mhz`, `max_mhz` (one row per matching counter track).
- **GPU**: matches counter tracks that reference a GPU clock/frequency (e.g. `gpufreq`, `power/gpu_frequency`, Mali devfreq).
- **DDR**: matches DDR/DRAM/EMI/DVFSRC/devfreq memory-bus frequency tracks (CPU/GPU clocks and non-frequency counters are excluded).
- Units are auto-normalized to MHz (source counters may be in Hz, kHz, or MHz depending on SoC).
- **Requires the extra ftrace events** now in the default config (`power/gpu_frequency`, `devfreq/devfreq_frequency`, `power/clock_set_rate`). Traces captured before this was added, or SoCs that don't expose these to ftrace, will report "No … frequency data found".

Flags can be combined, e.g. `--process com.whatsapp --fps com.whatsapp --cpufreq --gpufreq --ddrfreq`.

## Agent Workflow

When the user asks to capture and analyze a trace:

1. Determine the user's intent:
   - If asking about **process CPU** ("app X is using too much CPU") → use `--process` **and always add `--fps <process> --cpufreq --gpufreq`** in the same command so CPU usage, frame rate, and CPU/GPU frequency are reported together.
   - If asking about **specific function/slice** ("how much CPU does Y use?") → use `--slice`
2. **Always capture and save** when the user asks to capture or analyze live CPU:
   - Run `capture_trace.py` (do **not** skip capture just because an older `.perfetto-trace` already exists)
   - Each run must leave a **new** file on disk under the skill package directory (`trace_<timestamp>.perfetto-trace`); never overwrite or delete previous captures
   - Use the path printed by the script for subsequent `analyze_trace.py`
   - **Root is auto-detected** and the capture method is chosen accordingly (no manual `adb root` needed):
     - **Has root** (already root, or userdebug/eng/debuggable → script runs `adb root`): uses the **original** on-device file + `adb pull` method, auto-setting SELinux permissive during capture and restoring it afterward.
     - **No root** (production/user build): uses the **new** streaming method (`adb exec-out perfetto -o -`), which needs no root and works on Android 10+.
     - Each method automatically falls back to the other if it fails/returns empty.
   - If the user mentions **custom app instrumentation**, **missing trace events**, or needs additional atrace categories, add `--categories <tag1> <tag2> ...` to the capture command
   - If the user needs a **fully custom tracing config**, use `--config <path>` instead of the default
3. Run `analyze_trace.py` on the **newly saved** trace. For a process-CPU request, always analyze **CPU + FPS + CPU/GPU frequency together**:

```bash
python scripts/analyze_trace.py <trace> --process "<pkg>" --fps "<pkg>" --cpufreq --gpufreq
```

   - Include `--ddrfreq` too only if the user explicitly asks for DDR (many MTK SoCs do not expose DDR frequency to ftrace, so it often reports "No DDR frequency data").
4. Summarize using the **fixed report format** below (do not change its structure), then append FPS and CPU/GPU frequency sections, and report the saved trace path.

## Process CPU Report Format (keep unchanged)

When summarizing a process-CPU analysis, always produce this exact structure (in Chinese, tables as shown). This layout is intentional and must be preserved across runs:

1. **结论** — one line: sampling window (e.g. 20s), process, approx `占系统 CPU` %, and the dominant scenario (e.g. 视频通话 / 纯聊天) with where the CPU went and that business/background threads barely use CPU.
2. **进程总览** — a two-column table (`指标` / `值`) with rows: 进程 (name + pid + thread count), Trace 时长 (ms), 进程 CPU 时间 (ms), 占系统 CPU (%).
3. **线程热点（占系统 CPU）** — a table with columns `线程 | CPU (ms) | 占比 | 说明`, listing the top threads and a short role note (e.g. rec_clock=录制/采集时钟, VideoPort_*=视频编解码/传输, RenderThread=UI/视频渲染, Front camera=前置摄像头采集, mali-*=Mali GPU 驱动, binder:pid_*=与相机/媒体系统服务 IPC). Add the line: 「百分比为『线程 CPU / 系统总 CPU』，各线程相加约等于进程的 X%。」
4. **Top Slice（按 CPU）** — one line listing the hottest slices with their counts (queueBuffer(n)、eglSwapBuffers(n)、Drawing...(n)、binder reply(n) 等).
5. **解读与对比** — a table `时间 | 场景 | CPU` accumulating this and previous captures for trend, followed by a short interpretation (main cost = video pipeline; WhatsApp Worker ≤ ~0.04% so business logic is negligible; high usage is normal for video scenarios).
6. End with: 本次 trace 已保存：`<absolute path>`.

Then append the **FPS** result (frames, avg_fps, min/max per second, and the `source:` line) and **CPU / GPU 频率** tables. Offer DDR (sysfs) or per-slice deep-dive as optional next steps.

## Notes

- Default capture duration is 20 seconds; increase for rare events
- **Root-aware capture**: the script detects root and picks the method automatically —
  - **With root** (userdebug/eng/debuggable, or already rooted): original on-device file + `adb pull`; SELinux is temporarily set permissive and then restored.
  - **Without root** (production/user build, Android 10+): streaming via `adb exec-out perfetto -o -`, no root / no `setenforce 0` needed (`traced`/`traced_probes` are on by default).
  - Whichever path is chosen falls back to the other if it fails or returns an empty trace.
- **Output location**: Every capture is saved in the same directory as this skill package as a unique `trace_<timestamp>.perfetto-trace` (never overwrite previous captures)
- **Environment validation**: The script checks adb availability, device connection, and output directory before capturing
- **Categories**: Only specify `--categories` when you need additional atrace tags beyond the default config
- Slice names support `%` wildcard (SQL LIKE pattern)
- `trace_processor` is auto-downloaded on first run to `<workspace>/tools/` (e.g. `D:\AI2D\android-auto-trace\tools\`)
- Custom atrace categories are injected into the ftrace_config section
- Config files support `{duration_ms}` placeholder for dynamic duration
- Slice times can overlap due to nested calls; the sum of top slice CPU may exceed total process CPU
- For detailed SQL reference, see [reference.md](reference.md)

## Troubleshooting

### Perfetto Cannot Start or Hangs

**Symptom**: `perfetto` command fails to start, hangs indefinitely, or returns errors about traced/traced_probes

**Root Cause**: Stale perfetto or simpleperf processes from previous capture sessions blocking new instances

**Solution**: Kill all running tracing processes before capturing:

```bash
adb shell pkill -9 simpleperf
adb shell pkill -9 perfetto
adb shell pkill -9 traced
adb shell pkill -9 traced_probes
# Wait a moment for processes to fully terminate
sleep 2
# Now run the capture script
python scripts/capture_trace.py --duration 10
```

**When to Use**: Apply this fix when:
- Perfetto command hangs or doesn't respond
- Previous trace capture was interrupted or failed
- Device shows errors about traced service being unavailable
- Multiple capture attempts fail without clear error messages

### Capturing on User (Production) Builds

**Symptom**: `adb root` / `adb shell setenforce 0` fail (`adbd cannot run as root in production builds`, `Permission denied`), and the old flow could not create/pull `/data/misc/perfetto-traces/trace`.

**Root Cause**: Production (`ro.build.type=user`) builds do not allow root or disabling SELinux, and the on-device trace directory is not shell-writable/readable.

**Solution**: The script now captures by **streaming** the trace off-device, which needs no root:

```bash
# What the script runs internally (no root, works on user builds, Android 10+):
adb exec-out perfetto -c /data/local/tmp/perfetto_config.txt --txt -o - > trace.perfetto-trace

# Just run the capture script normally:
python scripts/capture_trace.py --duration 20
```

**Important Notes:**
- `adb exec-out` (not `adb shell`) is used so binary stdout is not corrupted (critical on Windows/PowerShell; the script writes bytes directly in Python).
- Requires Android 10+ with system tracing enabled by default (`persist.traced.enable=1`), which is the norm on user builds.
- No `setenforce 0`, no `adb root`, no re-enabling SELinux afterwards.
- The on-device file + `adb pull` method is kept only as an automatic fallback for devices where streaming returns empty; that fallback needs a rootable/userdebug build.

**When to Use**: This is now the default. If capture still fails on a user build, verify Android version ≥ 10 and that no stale tracing processes are running (see the section above).

### Permission Denied on the Fallback Path (rootable builds)

**Symptom**: Streaming succeeded is preferred; only if the fallback runs and `perfetto` reports "Permission denied" writing `/data/misc/perfetto-traces/trace`.

**Solution** (rootable/userdebug builds only): temporarily disable SELinux enforcement, then capture:

```bash
adb root
adb shell setenforce 0
python scripts/capture_trace.py --duration 20
adb shell setenforce 1   # re-enable afterwards
```

- `setenforce 0` requires root (`adb root`); temporary, resets on reboot.
- Not available on production/user devices — use the streaming path instead.
