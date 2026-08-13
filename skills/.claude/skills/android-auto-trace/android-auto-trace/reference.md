# Android Auto Trace - SQL Reference

## Common Tables

| Table | Key Fields | Description |
|-------|-----------|-------------|
| `process` | `upid`, `name` | Running processes |
| `thread` | `utid`, `upid`, `name` | Threads belonging to processes |
| `slice` | `id`, `ts`, `dur`, `name`, `track_id` | Trace slices (atrace, track events) |
| `thread_track` | `id`, `utid` | Maps tracks to threads |
| `process_track` | `id`, `upid` | Maps tracks to processes |
| `sched_slice` | `ts`, `dur`, `utid`, `cpu` | CPU scheduling slices |
| `thread_state` | `ts`, `dur`, `utid`, `state` | Thread state changes |
| `trace_bounds` | `start_ts`, `end_ts`, `dur` | Total trace duration |

## Process CPU Query

```sql
SELECT
    p.name,
    COUNT(DISTINCT t.utid) AS threads,
    ROUND(SUM(sched.dur) / 1e6, 2) AS cpu_ms,
    ROUND((SELECT dur FROM trace_bounds) / 1e6, 2) AS trace_ms,
    ROUND(SUM(sched.dur) * 100.0 / (SELECT dur FROM trace_bounds), 2) AS cpu_pct
FROM process p
JOIN thread t ON t.upid = p.upid
JOIN sched_slice sched ON sched.utid = t.utid
WHERE p.name LIKE '%TARGET%'
GROUP BY p.upid;
```

## Slice Duration Query

```sql
SELECT
    name,
    COUNT(*) AS count,
    ROUND(SUM(dur) / 1e6, 2) AS total_ms,
    ROUND(AVG(dur) / 1e6, 2) AS avg_ms
FROM slice
WHERE name LIKE '%TARGET%'
GROUP BY name;
```

## Slice CPU Efficiency Query

CPU time actually spent running on core during each slice:

```sql
SELECT
    s.name,
    COUNT(*) AS count,
    ROUND(SUM(s.dur) / 1e6, 2) AS wall_ms,
    ROUND(SUM(cpu_dur) / 1e6, 2) AS cpu_ms,
    ROUND(SUM(cpu_dur) * 100.0 / NULLIF(SUM(s.dur), 0), 2) AS cpu_pct
FROM slice s
JOIN thread_track tt ON s.track_id = tt.id
JOIN thread t ON tt.utid = t.utid
LEFT JOIN (
    SELECT
        s.id,
        COALESCE(SUM(sched.dur), 0) AS cpu_dur
    FROM slice s
    JOIN thread_track tt ON s.track_id = tt.id
    JOIN thread t ON tt.utid = t.utid
    LEFT JOIN sched_slice sched
        ON sched.utid = t.utid
        AND sched.ts >= s.ts
        AND sched.ts + sched.dur <= s.ts + s.dur
    WHERE s.name LIKE '%TARGET%'
    GROUP BY s.id
) cpu ON cpu.id = s.id
WHERE s.name LIKE '%TARGET%'
GROUP BY s.name;
```

## Top CPU Consumers

```sql
SELECT
    p.name,
    ROUND(SUM(sched.dur) / 1e6, 2) AS cpu_ms,
    ROUND(SUM(sched.dur) * 100.0 / (SELECT dur FROM trace_bounds), 2) AS pct
FROM process p
JOIN thread t ON t.upid = p.upid
JOIN sched_slice sched ON sched.utid = t.utid
GROUP BY p.upid
ORDER BY cpu_ms DESC
LIMIT 20;
```

## Time Units

Perfetto stores time in **nanoseconds**:
- Divide by `1e6` for milliseconds
- Divide by `1e9` for seconds
