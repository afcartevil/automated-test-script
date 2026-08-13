# Code Review Check Items

Use when analyzing Gerrit diffs. Prioritize findings by severity.

## Critical

- Null pointer / use-after-free / buffer overflow
- Array index out of bounds
- Race conditions on shared state without synchronization
- Resource leaks (fd, memory, lock)
- Security issues (auth bypass, injection, sensitive data exposure)
- Boot/kernel crash paths in early-stage code (preloader, lk, kernel init)

## High

- Incorrect condition logic or inverted flags
- Missing error handling on failure paths
- API contract breakage without migration
- State machine transitions incomplete
- GPIO/DTS/clock/regulator misconfiguration affecting hardware

## Medium

- Edge cases not handled (empty input, timeout, unplugged device)
- Performance regression in hot paths
- Duplicated logic that should be centralized
- Missing logging on failure paths
- Incomplete validation of external input

## Low

- Naming/style inconsistencies
- Missing comments on non-obvious business rules
- Minor refactor opportunities
- Test gap for non-critical paths

## Functional Correctness

Cross-check against commit subject and project context:

- Does the change match the stated intent?
- Are all affected projects/platforms covered?
- Regression risk to related modules?
- Backward compatibility impact?

## When to Expand Reading Scope

Re-fetch file content (`--expand-files` or `fetch_file_content`) when:

- Diff hunk context is too small to identify the target (e.g. GPIO node name)
- Change touches public headers, HAL interfaces, or Kconfig
- Logic depends on macros/constants defined elsewhere in the file
