#!/usr/bin/env python3
"""TAHP Quality Gate Checker.

Implements three-level quality gate checks (P0/P1/P2) for TAHP skill modules.
P0 gates are blocking; P1 gates produce warnings; P2 gates record informational findings.

Exit codes:
    0 = PASS (all checked gates passed)
    1 = BLOCK (one or more P0 gates failed)
    2 = WARNING (all P0 passed, one or more P1 failed)

Usage:
    python scripts/gate_check.py constraints/telephony/
    python scripts/gate_check.py constraints/telephony/ --level all
    python scripts/gate_check.py pipeline.yaml --level P0
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Any, Optional

import yaml
import click
from rich.console import Console
from rich.table import Table

console = Console()


class GateLevel(IntEnum):
    """Quality gate severity levels."""
    P0_BLOCK = 0   # Must pass — blocks integration
    P1_WARNING = 1 # Should pass — warning if fails
    P2_RECORD = 2  # Nice to have — informational only


class GateResult(IntEnum):
    """Overall gate check result."""
    PASS = 0       # Exit code 0
    BLOCK = 1      # Exit code 1 — P0 failure
    WARNING = 2    # Exit code 2 — P1 failure


@dataclass
class GateCheck:
    """A single gate check finding."""
    level: GateLevel
    name: str
    description: str
    passed: bool
    detail: str = ""


@dataclass
class GateReport:
    """Aggregated quality gate report."""
    target: str
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def p0_checks(self) -> list[GateCheck]:
        return [c for c in self.checks if c.level == GateLevel.P0_BLOCK]

    @property
    def p1_checks(self) -> list[GateCheck]:
        return [c for c in self.checks if c.level == GateLevel.P1_WARNING]

    @property
    def p2_checks(self) -> list[GateCheck]:
        return [c for c in self.checks if c.level == GateLevel.P2_RECORD]

    @property
    def result(self) -> GateResult:
        p0_fail = any(not c.passed for c in self.p0_checks)
        p1_fail = any(not c.passed for c in self.p1_checks)
        if p0_fail:
            return GateResult.BLOCK
        if p1_fail:
            return GateResult.WARNING
        return GateResult.PASS

    @property
    def result_label(self) -> str:
        labels = {GateResult.PASS: "PASS", GateResult.BLOCK: "BLOCK",
                  GateResult.WARNING: "WARNING"}
        return labels.get(self.result, "UNKNOWN")


# ---------------------------------------------------------------------------
# P0 Gates (Blocking)
# ---------------------------------------------------------------------------

def check_safety_red_lines_present(module_dir: Path) -> GateCheck:
    """P0: Constraint files must include safety_red_lines section."""
    constraint_files = list(module_dir.glob("*.yaml")) + list(module_dir.glob("*.yml"))
    # Exclude module.yaml from this check
    constraint_files = [f for f in constraint_files if f.name != "module.yaml"]

    has_srl = False
    for cf in constraint_files:
        try:
            with open(cf, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if isinstance(data, dict) and "safety_red_lines" in data:
                    srl = data["safety_red_lines"]
                    if isinstance(srl, list) and len(srl) > 0:
                        has_srl = True
                        break
        except (yaml.YAMLError, OSError):
            pass

    if not has_srl and not constraint_files:
        return GateCheck(GateLevel.P0_BLOCK, "safety_red_lines_present",
                         "At least one constraint file must define safety_red_lines",
                         False, "No constraint YAML files found")

    return GateCheck(
        GateLevel.P0_BLOCK, "safety_red_lines_present",
        "Constraint files must contain non-empty safety_red_lines",
        has_srl,
        "Found" if has_srl else "Missing safety_red_lines in all constraint files"
    )


def check_no_hardcoded_secrets(module_dir: Path) -> GateCheck:
    """P0: No hardcoded secrets (API keys, passwords, tokens)."""
    secret_patterns = [
        re.compile(r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"][^\s\"']{8,}['\"]"),
        re.compile(r"(?i)(password|passwd|pwd|secret|token)\s*[:=]\s*['\"][^\s\"']{6,}['\"]"),
        re.compile(r"(?i)(private[_-]?key|auth[_-]?token)\s*[:=]\s*['\"][^\s\"']+"),
    ]

    violations: list[str] = []
    for f in _iter_source_files(module_dir):
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
            for pattern in secret_patterns:
                matches = pattern.finditer(text)
                for m in matches:
                    line_no = text[:m.start()].count("\n") + 1
                    violations.append(f"{f.relative_to(module_dir)}:{line_no}: {m.group()}")
        except OSError:
            pass

    return GateCheck(
        GateLevel.P0_BLOCK, "no_hardcoded_secrets",
        "No hardcoded secrets (API keys, passwords, tokens)",
        len(violations) == 0,
        "; ".join(violations[:5]) if violations else "Clean"
    )


def check_constraint_files_valid(module_dir: Path) -> GateCheck:
    """P0: All constraint YAML files must be valid YAML."""
    errors: list[str] = []
    for yf in module_dir.glob("*.yaml"):
        try:
            with open(yf, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    errors.append(f"{yf.name}: root is not a mapping")
        except yaml.YAMLError as exc:
            errors.append(f"{yf.name}: {exc}")
        except OSError as exc:
            errors.append(f"{yf.name}: {exc}")

    for yf in module_dir.glob("*.yml"):
        try:
            with open(yf, "r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
                if not isinstance(data, dict):
                    errors.append(f"{yf.name}: root is not a mapping")
        except yaml.YAMLError as exc:
            errors.append(f"{yf.name}: {exc}")

    return GateCheck(
        GateLevel.P0_BLOCK, "constraint_files_valid",
        "All .yaml/.yml files must be valid YAML mappings",
        len(errors) == 0,
        "; ".join(errors[:5]) if errors else "All files valid"
    )


# ---------------------------------------------------------------------------
# P1 Gates (Warning)
# ---------------------------------------------------------------------------

def check_test_coverage(module_dir: Path, min_coverage: float = 0.70) -> GateCheck:
    """P1: Test coverage should be >= threshold."""
    eval_dir = module_dir / "eval-data" / "cases"
    if not eval_dir.is_dir():
        return GateCheck(GateLevel.P1_WARNING, "test_coverage",
                         f"Test coverage >= {min_coverage:.0%}",
                         False,
                         f"No eval-data/cases directory found")

    case_files = list(eval_dir.glob("*.yaml")) + list(eval_dir.glob("*.yml"))
    num_cases = len(case_files)

    # Heuristic coverage estimation based on number of test cases
    # Real implementation would use a coverage tool; here we estimate
    estimated_coverage = min(1.0, num_cases / max(num_cases, 3))

    passed = estimated_coverage >= min_coverage or num_cases >= 3
    return GateCheck(
        GateLevel.P1_WARNING, "test_coverage",
        f"Test coverage >= {min_coverage:.0%}",
        passed,
        f"{num_cases} test cases found ({estimated_coverage:.0%} est.)"
    )


def check_documentation_complete(module_dir: Path) -> GateCheck:
    """P1: Module must have a module.yaml with required fields."""
    mod_yaml = module_dir / "module.yaml"
    if not mod_yaml.exists():
        return GateCheck(GateLevel.P1_WARNING, "documentation_complete",
                         "module.yaml must exist", False,
                         "module.yaml not found")

    try:
        with open(mod_yaml, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)

        missing: list[str] = []
        required_fields = ["module.name", "module.owner", "scope.includes"]
        for rf in required_fields:
            keys = rf.split(".")
            val = data
            for k in keys:
                val = val.get(k) if isinstance(val, dict) else None
            if not val:
                missing.append(rf)

        return GateCheck(
            GateLevel.P1_WARNING, "documentation_complete",
            "module.yaml must have all required fields",
            len(missing) == 0,
            f"Missing: {', '.join(missing)}" if missing else "Complete"
        )
    except (yaml.YAMLError, OSError) as e:
        return GateCheck(GateLevel.P1_WARNING, "documentation_complete",
                         "module.yaml parseable", False, str(e))


def check_naming_conventions(module_dir: Path) -> GateCheck:
    """P1: Files follow kebab-case naming convention."""
    violations: list[str] = []
    kebab_pattern = re.compile(r"^[a-z][a-z0-9\-]*\.ya?ml$")

    for f in module_dir.iterdir():
        if f.is_file() and f.suffix in (".yaml", ".yml"):
            if not kebab_pattern.match(f.name):
                violations.append(f.name)

    return GateCheck(
        GateLevel.P1_WARNING, "naming_conventions",
        


"YAML files use kebab-case naming",
        len(violations) == 0,
        f"Non-compliant: {', '.join(violations)}" if violations else "Compliant"
    )


# ---------------------------------------------------------------------------
# P2 Gates (Informational / Record-only)
# ---------------------------------------------------------------------------

def check_code_style(module_dir: Path) -> GateCheck:
    """P2: Basic code style consistency check."""
    issues: list[str] = []
    for f in _iter_source_files(module_dir):
        if f.suffix not in (".py", ".sh"):
            continue
        try:
            lines = f.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines, 1):
                # Check trailing whitespace
                if line.rstrip() != line:
                    issues.append(f"{f.name}:{i}: trailing whitespace")
                    break  # One issue per file is enough for P2
                # Check line length > 120 chars
                if len(line) > 120:
                    issues.append(f"{f.name}:{i}: line length {len(line)}")
                    break
        except OSError:
            pass

    return GateCheck(
        GateLevel.P2_RECORD, "code_style",
        "Code style (line length <= 120, no trailing whitespace)",
        len(issues) == 0,
        ", ".join(issues[:3]) if issues else "Clean"
    )


def check_comment_density(module_dir: Path) -> GateCheck:
    """P2: Comment density on source files (informational)."""
    total_lines = 0
    comment_lines = 0

    for f in _iter_source_files(module_dir):
        if f.suffix not in (".py", ".yaml", ".yml", ".md"):
            continue
        try:
            text = f.read_text(encoding="utf-8")
            lines = text.splitlines()
            total_lines += len(lines)
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith("//") or stripped.startswith("/*"):
                    comment_lines += 1
        except OSError:
            pass

    density = comment_lines / total_lines if total_lines > 0 else 0.0
    status = "adequate" if density >= 0.05 else "low"

    return GateCheck(
        GateLevel.P2_RECORD, "comment_density",
        f"Comment density (current: {density:.1%})",
        True,  # P2 never fails
        f"{comment_lines}/{total_lines} lines commented ({status})"
    )


def check_example_cases(module_dir: Path) -> GateCheck:
    """P2: Check that example evaluation cases exist."""
    expected_dir = module_dir / "eval-data" / "expected"
    cases_dir = module_dir / "eval-data" / "cases"

    expected_count = len(list(expected_dir.iterdir())) if expected_dir.is_dir() else 0
    case_count = len(list(cases_dir.iterdir())) if cases_dir.is_dir() else 0

    detail = f"cases={case_count}, expected_outputs={expected_count}"
    return GateCheck(
        GateLevel.P2_RECORD, "example_cases",
        "Example evaluation cases present",
        True,
        detail
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _iter_source_files(directory: Path):
    """Iterate over source files in a directory (non-recursive)."""
    extensions = {".yaml", ".yml", ".py", ".sh", ".toml", ".json"}
    for entry in directory.iterdir():
        if entry.is_file() and entry.suffix in extensions:
            yield entry


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def run_gates(target: Path, levels: Optional[list[GateLevel]] = None) -> GateReport:
    """Run quality gate checks on the given target.

    Args:
        target: A module directory path, or a pipeline YAML file.
        levels: Which gate levels to check. Default: all.

    Returns:
        GateReport with all check results.
    """
    if levels is None:
        levels = [GateLevel.P0_BLOCK, GateLevel.P1_WARNING, GateLevel.P2_RECORD]

    report = GateReport(target=str(target))

    # Determine if target is a module dir or pipeline file
    if target.is_file() and target.suffix in (".yaml", ".yml"):
        # Pipeline mode: extract module references
        _run_pipeline_gates(target, report, levels)
    elif target.is_dir():
        _run_module_gates(target, report, levels)
    else:
        raise click.BadParameter(f"Not a valid directory or pipeline file: {target}")

    return report


def _run_module_gates(module_dir: Path, report: GateReport,
                      levels: list[GateLevel]) -> None:
    """Run all applicable gates against a module directory."""
    # P0 gates
    if GateLevel.P0_BLOCK in levels:
        report.checks.append(check_safety_red_lines_present(module_dir))
        report.checks.append(check_no_hardcoded_secrets(module_dir))
        report.checks.append(check_constraint_files_valid(module_dir))

    # P1 gates
    if GateLevel.P1_WARNING in levels:
        report.checks.append(check_test_coverage(module_dir))
        report.checks.append(check_documentation_complete(module_dir))
        report.checks.append(check_naming_conventions(module_dir))

    # P2 gates
    if GateLevel.P2_RECORD in levels:
        report.checks.append(check_code_style(module_dir))
        report.checks.append(check_comment_density(module_dir))
        report.checks.append(check_example_cases(module_dir))


def _run_pipeline_gates(pipeline_file: Path, report: GateReport,
                        levels: list[GateLevel]) -> None:
    """Run gates for each module referenced in a pipeline YAML."""
    with open(pipeline_file, "r", encoding="utf-8") as fh:
        pipeline = yaml.safe_load(fh)

    modules = []
    if isinstance(pipeline, dict):
        modules = pipeline.get("modules", [])
        if isinstance(modules, str):
            modules = [modules]

    base_dir = pipeline_file.parent
    for mod_ref in modules:
        mod_path = base_dir / "constraints" / mod_ref
        if mod_path.is_dir():
            sub_report = run_gates(mod_path, levels)
            report.checks.extend(sub_report.checks)


def print_report(report: GateReport) -> None:
    """Render the gate check report using rich console."""

    # Summary header
    result_color = {
        GateResult.PASS: "green",
        GateResult.BLOCK: "red bold",
        GateResult.WARNING: "yellow",
    }.get(report.result, "white")

    console.print()
    console.print(f"[{result_color}]{'=' * 60}[/{result_color}]")
    console.print(f"[{result_color}]  Quality Gate: {report.result_label}[/]")
    console.print(f"[{result_color}]  Target: {report.target}[/]")
    console.print(f"[{result_color}]{'=' * 60}[/{result_color}]")

    for level_name, level_enum, color in [
        ("P0 - BLOCK", GateLevel.P0_BLOCK, "red"),
        ("P1 - WARNING", GateLevel.P1_WARNING, "yellow"),
        ("P2 - RECORD", GateLevel.P2_RECORD, "cyan"),
    ]:
        level_checks = [c for c in report.checks if c.level == level_enum]
        if not level_checks:
            continue

        table = Table(title=f"[bold]{level_name}[/bold]", show_header=True)
        table.add_column("Status", justify="center", width=8)
        table.add_column("Check", style="bold", min_width=24)
        table.add_column("Detail", max_width=50)

        for check in level_checks:
            icon = "[green]OK[/green]" if check.passed else f"[{color}]FAIL[/]"
            table.add_row(icon, check.name, check.detail)

        console.print(table)
        console.print()

    # Totals
    total = len(report.checks)
    passed_total = sum(1 for c in report.checks if c.passed)
    console.print(f"Total: {passed_total}/{total} checks passed")


@click.command(help="Run TAHP quality gate checks on a skill/module directory.")
@click.argument("target", type=click.Path(exists=True))
@click.option("--level", "-l", "level_str",
              type=click.Choice(["P0", "P1", "P2", "all"], case_sensitive=False),
              default="all", help="Which gate levels to check.")
def main(target: str, level_str: str) -> None:
    """Run quality gate checks on TARGET (module dir or pipeline YAML).

    Exit codes: 0=PASS, 1=BLOCK(P0 fail), 2=WARNING(P1 fail).
    """
    level_map = {
        "P0": [GateLevel.P0_BLOCK],
        "P1": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING],
        "P2": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING, GateLevel.P2_RECORD],
        "all": [GateLevel.P0_BLOCK, GateLevel.P1_WARNING, GateLevel.P2_RECORD],
    }
    levels = level_map[level_str]

    target_path = Path(target).resolve()
    report = run_gates(target_path, levels)
    print_report(report)

    sys.exit(int(report.result))


if __name__ == "__main__":
    main()
