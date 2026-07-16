# Android Auto Trace

A toolkit for capturing and analyzing Android Perfetto traces via `adb`. It automates trace capture from connected devices and provides precise CPU usage analysis for processes and named trace slices.

## When to Use This Skill

Use this skill when a user wants to:

- **Diagnose high CPU usage** — "App X is using too much CPU", "my app is laggy", "CPU profiling"
- **Capture an Android trace** — "help me grab a perfetto trace", "I need to trace my app"
- **Analyze process CPU** — "how much CPU does this process use?"
- **Analyze specific functions/slices** — "how expensive is Choreographer#doFrame?", "find the hottest trace slices"

## Agent Decision Flow

When the user mentions performance or CPU issues, the agent follows this workflow:

1. **Determine intent**
   - Process-level CPU question → use `--process`
   - Specific function/slice question → use `--slice`
   - Just "capture a trace" → run capture only
2. **Capture** (if no trace file exists)
   - Default: basic capture with standard atrace categories
   - Custom instrumentation needed → add `--categories <tag1> <tag2> ...`
   - Fully custom tracing setup → use `--config <path>`
3. **Analyze** with the appropriate flag
4. **Summarize** results clearly for the user

## Why This Approach

### CPU Time, Not Wall Time

All metrics report **actual CPU time** — the precise duration a thread was scheduled on a CPU core. This is computed by intersecting slice/thread durations with `thread_state.state = 'Running'`. Wall time would include idle periods (sleep, I/O wait), which is misleading for performance analysis.

### Aggregate Slices by Name

Individual slice instances are aggregated by name to surface the most expensive operations. The top 10 hottest slices are included in process analysis to quickly identify bottlenecks.

### Dynamic Configuration

- **Buffer sizing** scales with capture duration (~8 MB/s, clamped 64–512 MB) to avoid lost events or excessive memory use
- **Custom atrace categories** are injected into the `ftrace_config` section without requiring full config overrides
- **Config templates** support `{duration_ms}` and `{buffer_size_kb}` placeholders for flexible reuse

## Project Structure

```
android-auto-trace/
├── scripts/
│   ├── capture_trace.py      # Trace capture via adb + perfetto
│   └── analyze_trace.py      # CPU analysis with trace_processor
├── configs/
│   └── default_config.txt    # Default Perfetto text-proto config
├── SKILL.md                  # Agent-facing usage guide and workflow
├── reference.md              # Perfetto SQL reference for developers
└── README.md                 # This file
```

## Technical Usage

### Capture a Trace

```bash
# Basic 10-second capture
python scripts/capture_trace.py --duration 10 --output trace.perfetto-trace

# Capture with custom atrace categories
python scripts/capture_trace.py --duration 10 --output trace.perfetto-trace \
  --categories dalvik binder_driver my_custom_tag

# Use a custom Perfetto config
python scripts/capture_trace.py --duration 10 --output trace.perfetto-trace \
  --config configs/my_custom_config.txt
```

### Analyze Process CPU

```bash
python scripts/analyze_trace.py trace.perfetto-trace --process "com.example.app"
```

Output includes:
- Process summary (total CPU ms, trace duration, CPU percentage)
- Per-thread CPU breakdown
- Top 10 named slices by CPU time

### Analyze a Specific Slice

```bash
python scripts/analyze_trace.py trace.perfetto-trace --slice "Choreographer#doFrame"
```

Output includes:
- Aggregate stats (count, total CPU ms, average CPU ms, CPU percentage of trace)
- Top 10 individual instances by CPU time

Slice names support `%` as a SQL `LIKE` wildcard.

## Custom Config Templates

Config files are text-proto Perfetto configs with optional placeholders:

- `{duration_ms}` — replaced with capture duration in milliseconds
- `{buffer_size_kb}` — replaced with computed buffer size in kilobytes

Example:

```protobuf
buffers {
  size_kb: {buffer_size_kb}
  fill_policy: RING_BUFFER
}
duration_ms: {duration_ms}
write_into_file: true
output_path: "/data/misc/perfetto-traces/trace"
```

## Prerequisites

- Android device connected via USB with `adb` enabled
- `adb` in your system PATH
- Python 3.7+

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `perfetto failed` | Ensure the config file uses `--txt` flag syntax (text-proto, not binary) |
| Empty trace file | Verify the device has enough storage and the buffer size is not too large |
| `trace_processor not found` | The script auto-downloads it to `<workspace>/tools/` on first run (never C: home cache) |

## License

MIT
