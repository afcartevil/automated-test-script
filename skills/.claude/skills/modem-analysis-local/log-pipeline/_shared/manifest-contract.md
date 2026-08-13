# Job Manifest Contract

Use a shared `job_manifest.json` to pass state between atomic skills.

## Required top-level fields

- `issue_key`: Jira issue key or other case identifier.
- `workspace_root`: Working directory for this case.
- `final_log_root`: Packaged directory that later analysis skills should read.
- `jira`: Issue metadata and extracted box URLs.
- `downloads`: Download directories and per-link results.
- `extraction`: Archive extraction and directory filtering results.
- `trace_exports`: ELT/NLT export results and packaged txt outputs.
- `analysis`: Layered downstream analysis outputs, including L0 baseline, L1 business judgement, L2 domain analysis, L3 conclusion, and final report.
- `db_cache`: Database cache read/write states (`db-result-checker` and `db-result-writer` outputs).
- `publish`: Jira comment posting state.

## Rules

1. Keep paths absolute once they are written into the manifest.
2. Each skill may add fields, but it should not remove sibling sections that another skill may need.
3. Treat missing sections as empty objects instead of failing immediately.
4. Record partial failures in `results` arrays so the orchestrator can decide whether to continue.
5. Write back the manifest after every side-effecting step.
6. Validity gate: if `analysis.l0_baseline` marks the case invalid, L1/L2 may be intentionally skipped (and therefore absent/empty).
7. Cache-first flow: run `db-result-checker` before full analysis; on hit, short-circuit and use cached final report. Run `db-result-writer` after full analysis.

## Suggested layered analysis shape

```json
{
  "analysis": {
    "l0_baseline": {
      "validity_gate": {
        "status": "valid|invalid|unknown"
      },
      "decision": "continue|skip_to_l3|unknown",
      "should_continue": true
    },
    "l1_business": {
      "primary_domain": "call|data|sim|other"
    },
    "l2_domains": {
      "call": {},
      "data": {},
      "sim": {}
    },
    "l3_conclusion": {},
    "final_report": ""
  }
}
```

Compatibility notes:

- `analysis.analysis_type` may still be written for older skills.
- `analysis.final_report` remains the publish boundary for `jira-comment-poster`.

## Minimum downstream expectations

- `box-log-download` expects `jira.box_urls`.
- `archive-recursive-extract` expects `downloads.download_dirs`.
- `modem-log-structure-filter` expects `extraction.extracted_dirs`（为空时回退 `downloads.download_dirs`）。
- `elt-nlt-export` expects `extraction.normalized_log_roots`.
- `trace-aggregate-and-package` expects `trace_exports.groups`.
- `modem-l0-baseline` expects `final_log_root`.
- `modem-l1-business-judge` expects `final_log_root` and `analysis.l0_baseline`, and MUST be skipped if L0 gate is invalid.
- `modem-l2-*` skills expect `final_log_root`, `analysis.l0_baseline`, and `analysis.l1_business`, and MUST be skipped if L0 gate is invalid.
- `modem-l3-conclusion` expects either (a) L0 gate marks invalid, or (b) one or more populated `analysis.l2_domains.*`.
