#!/usr/bin/env python3
"""TAHP Skill Evaluation Tool.

Evaluates AI skills against test datasets per the TAHP evaluation metrics specification.
Calculates accuracy, completeness, safety_compliance, and time_efficiency metrics,
producing structured JSON reports with per-case and aggregate results.

Usage:
    python scripts/evaluate.py skills/telephony-bug-analyzer/ eval-data/telephony/
    python scripts/evaluate.py skills/telephony-bug-analyzer/ eval-data/ --output report.json
    python scripts/evaluate.py skills/telephony-bug-analyzer/ eval-data/ --model claude-4
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


@dataclass
class TestCase:
    """A single evaluation case loaded from YAML."""
    case_id: str
    input_data: dict[str, Any]
    expected_output: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0


@dataclass
class CaseResult:
    """Result of evaluating a single test case."""
    case_id: str
    passed: bool
    accuracy_score: float
    completeness_score: float
    safety_score: float
    execution_time_sec: float
    actual_output: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvaluationReport:
    """Aggregate evaluation report."""
    skill_name: str
    model: str
    timestamp: str
    total_cases: int
    passed_cases: int
    failed_cases: str
    accuracy: float
    completeness: float
    safety_compliance: float
    time_efficiency: float  # inverse of avg exec time, normalized
    avg_execution_time_sec: float
    cases: list[CaseResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_evaluation_dataset(dataset_path: Path) -> list[TestCase]:
    """Load evaluation cases from a dataset directory or file.

    Expected structure:
      eval-data/
        cases/
          case_001.yaml   # contains input + expected_output
          case_002.yaml
        config.yaml       # optional global config
    """
    cases_dir = dataset_path / "cases"
    if not cases_dir.is_dir():
        # Try loading a single YAML file directly
        if dataset_path.is_file() and dataset_path.suffix in (".yaml", ".yml"):
            return _load_single_case(dataset_path)
        raise click.ClickException(
            f"Evaluation dataset not found at {dataset_path}. "
            f"Expected a directory with 'cases/' subfolder or a single YAML file."
        )

    cases: list[TestCase] = []
    for case_file in sorted(cases_dir.glob("*.yaml")):
        if case_file.name.startswith("_") or case_file.name.startswith("."):
            continue
        case = _load_single_case(case_file)
        if case:
            cases.append(case)

    # Also handle yml extension
    for case_file in sorted(cases_dir.glob("*.yml")):
        if case_file.name.startswith("_") or case_file.name.startswith("."):
            continue
        case = _load_single_case(case_file)
        if case:
            cases.append(case)

    return cases


def _load_single_case(case_path: Path) -> Optional[TestCase]:
    """Parse a single evaluation case YAML file."""
    with open(case_path, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)

    if not isinstance(raw, dict):
        console.print(f"[yellow]Skipping malformed case: {case_path.name}[/yellow]")
        return None

    return TestCase(
        case_id=raw.get("case_id", case_path.stem),
        input_data=raw.get("input", {}),
        expected_output=raw.get("expected_output", raw.get("expected", {})),
        metadata=raw.get("metadata", {}),
        weight=float(raw.get("weight", 1.0)),
    )


def execute_skill(skill_path: Path, test_input: dict[str, Any],
                  model: str, timeout_sec: int = 300) -> tuple[Optional[dict], Optional[str], float]:
    """Execute the skill CLI tool against a test input.

    Returns (output_dict_or_None, error_message_or_None, elapsed_seconds).
    """
    # Build the command based on what's available in skill_path
    skill_script = skill_path / "skill.py"
    skill_cmd = skill_path / "run.sh"

    input_json = json.dumps(test_input, ensure_ascii=False)

    cmd: list[str]
    if skill_script.exists():
        cmd = [sys.executable, str(skill_script)]
    elif skill_cmd.exists():
        cmd = ["bash", str(skill_cmd)]
    else:
        # Default: use Claude Code CLI if available
        prompt = test_input.get("prompt", json.dumps(test_input, ensure_ascii=False))
        cmd = [
            "claude",
            "-p", prompt,
            "--model", model,
            "--output-format", "json",
        ]

    start_time = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            input=input_json,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            cwd=str(skill_path),
        )
        elapsed = time.monotonic() - start_time

        if result.returncode != 0:
            stderr_text = result.stderr.strip() or "(no stderr)"
            return None, f"Skill exited with code {result.returncode}: {stderr_text}", elapsed

        # Parse JSON output
        output_str = result.stdout.strip()
        if not output_str:
            return None, "Skill produced no output", elapsed

        try:
            output_data = json.loads(output_str)
            if isinstance(output_data, dict):
                return output_data, None, elapsed
            return {"raw": output_data}, None, elapsed
        except json.JSONDecodeError:
            return {"raw": output_str}, None, elapsed

    except subprocess.TimeoutExpired:
        elapsed = time.monotonic() - start_time
        return None, f"Execution timed out after {timeout_sec}s", elapsed
    except FileNotFoundError:
        return None, f"Executable not found: {cmd[0]}", time.monotonic() - start_time
    except Exception as exc:
        return None, f"Execution error: {exc}", time.monotonic() - start_time


def compare_output(actual: dict, expected: dict) -> dict[str, float]:
    """Compare actual output against expected output, returning metric scores.

    Returns dict with accuracy, completeness, safety scores (each 0.0–1.0).
    """
    if not actual and not expected:
        return {"accuracy": 1.0, "completeness": 1.0, "safety": 1.0}

    if not actual:
        return {"accuracy": 0.0, "completeness": 0.0, "safety": 1.0}

    # Accuracy: exact match on expected fields
    matched = 0
    total_expected = len(expected) if expected else 1

    for key, exp_val in expected.items():
        act_val = actual.get(key)
        if act_val is not None:
            # String-based fuzzy match for text outputs
            if isinstance(exp_val, str) and isinstance(act_val, str):
                similarity = _string_similarity(exp_val, act_val)
                if similarity >= 0.7:
                    matched += similarity
                # Partial credit for some overlap
                elif similarity >= 0.3:
                    matched += similarity * 0.5
            elif act_val == exp_val:
                matched += 1.0
            elif isinstance(exp_val, list) and isinstance(act_val, list):
                # List overlap scoring
                common = set(str(x) for x in exp_val) & set(str(x) for x in act_val)
                matched += len(common) / max(len(exp_val), 1)
            elif isinstance(exp_val, dict) and isinstance(act_val, dict):
                sub_scores = compare_output(act_val, exp_val)
                matched += sub_scores["accuracy"]

    accuracy = min(matched / total_expected, 1.0) if total_expected > 0 else 1.0

    # Completeness: how many expected fields are actually present in output
    present = sum(1 for key in expected if key in actual and actual[key] is not None)
    completeness = present / total_expected if total_expected > 0 else 1.0

    # Safety compliance: check for safety red line violations
    safety = _check_safety(actual, expected)

    return {
        "accuracy": round(accuracy, 4),
        "completeness": round(completeness, 4),
        "safety": round(safety, 4),
    }


def _string_similarity(a: str, b: str) -> float:
    """Simple token-overlap similarity between two strings."""
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    union = words_a | words_b
    return len(intersection) / len(union)


def _check_safety(actual: dict, expected: dict) -> float:
    """Check output for safety violations.

    Returns 1.0 (safe) or 0.0 (violation detected).
    """
    # If expected has safety markers, check them
    if "safety_violation" in expected:
        expected_safe = expected["safety_violation"]
        actual_safe = actual.get("safety_violation")
        if expected_safe and actual_safe != expected_safe:
            return 0.0

    # Heuristic: detect potential secrets in output
    output_str = json.dumps(actual, ensure_ascii=False)
    secret_patterns = [
        r"(?i)(api[_-]?key|apikey)\s*[:=]\s*['\"]?\w+",
        r"(?i)(password|passwd|pwd)\s*[:=]\s*['\"]?\S+",
        r"(?i)(secret|token)\s*[:=]\s*['\"]?\S{10,}",
    ]
    import re
    for pattern in secret_patterns:
        if re.search(pattern, output_str):
            return 0.5  # Partial penalty

    return 1.0


def run_evaluation(skill_path: Path, dataset_path: Path,
                   model: str, output_path: Optional[Path] = None) -> EvaluationReport:
    """Execute full evaluation pipeline."""
    skill_name = skill_path.name
    console.print(f"\n[bold]Evaluating skill:[/bold] [cyan]{skill_name}[/cyan]")
    console.print(f"[bold]Model:[/bold] {model}")
    console.print(f"[bold]Dataset:[/bold] {dataset_path}\n")

    # Load test cases
    cases = load_evaluation_dataset(dataset_path)
    if not cases:
        raise click.ClickException(f"No evaluation cases found in {dataset_path}")

    console.print(f"Loaded [bold]{len(cases)}[/bold] test case(s)")

    # Execute each case
    case_results: list[CaseResult] = []

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  console=console) as progress:
        task = progress.add_task("Evaluating cases...", total=len(cases))

        for tc in cases:
            progress.update(task, description=f"Running {tc.case_id}...")
            actual_output, error, elapsed = execute_skill(skill_path, tc.input_data, model)

            if error:
                case_results.append(CaseResult(
                    case_id=tc.case_id,
                    passed=False,
                    accuracy_score=0.0,
                    completeness_score=0.0,
                    safety_score=1.0,
                    execution_time_sec=elapsed,
                    error_message=error,
                ))
            else:
                scores = compare_output(actual_output, tc.expected_output)
                passed = scores["accuracy"] >= 0.7 and scores["completeness"] >= 0.7
                case_results.append(CaseResult(
                    case_id=tc.case_id,
                    passed=passed,
                    accuracy_score=scores["accuracy"],
                    completeness_score=scores["completeness"],
                    safety_score=scores["safety"],
                    execution_time_sec=elapsed,
                    actual_output=actual_output,
                ))

            progress.advance(task)

    # Compute aggregate metrics
    passed_count = sum(1 for cr in case_results if cr.passed)
    failed_count = len(case_results) - passed_count
    weights = [tc.weight for tc in cases]

    def weighted_avg(scores: list[float], wts: list[float]) -> float:
        if not scores:
            return 0.0
        total_w = sum(wts)
        return sum(s * w for s, w in zip(scores, wts)) / total_w if total_w > 0 else 0.0

    avg_accuracy = weighted_avg([cr.accuracy_score for cr in case_results], weights)
    avg_completeness = weighted_avg([cr.completeness_score for cr in case_results], weights)
    avg_safety = weighted_avg([cr.safety_score for cr in case_results], weights)
    avg_time = weighted_avg([cr.execution_time_sec for cr in case_results], weights)
    # Time efficiency: higher is better, normalize around 60s baseline
    time_efficiency = max(0.0, min(1.0, 60.0 / max(avg_time, 1.0)))

    report = EvaluationReport(
        skill_name=skill_name,
        model=model,
        timestamp=datetime.utcnow().isoformat(),
        total_cases=len(case_results),
        passed_cases=passed_count,
        failed_cases=failed_count,
        accuracy=round(avg_accuracy, 4),
        completeness=round(avg_completeness, 4),
        safety_compliance=round(avg_safety, 4),
        time_efficiency=round(time_efficiency, 4),
        avg_execution_time_sec=round(avg_time, 2),
        cases=case_results,
    )

    # Print summary table
    _print_report_summary(report)

    # Write report to file
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False, default=str)
        console.print(f"\nReport written to: [cyan]{output_path}[/cyan]")

    return report


def _print_report_summary(report: EvaluationReport) -> None:
    """Print a formatted evaluation summary to console."""
    table = Table(title=f"Evaluation Report: {report.skill_name}")
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")
    table.add_column("Status")

    status_pass = "[green]PASS[/green]" if report.accuracy >= 0.75 else (
        "[yellow]MARGINAL[/yellow]" if report.accuracy >= 0.6 else "[red]FAIL[/red]")

    table.add_row("Model", report.model, "")
    table.add_row("Test Cases", f"{report.passed_cases}/{report.total_cases} passed", "")
    table.add_row("Accuracy", f"{report.accuracy:.1%}", status_pass)
    table.add_row("Completeness", f"{report.completeness:.1%}",
                  "[green]OK[/green]" if report.completeness >= 0.8 else "[yellow]LOW[/yellow]")
    table.add_row("Safety Compliance", f"{report.safety_compliance:.1%}",
                  "[green]OK[/green]" if report.safety_compliance >= 0.95 else "[red]ISSUE[/red]")
    table.add_row("Time Efficiency", f"{report.time_efficiency:.1%}", "")
    table.add_row("Avg Execution Time", f"{report.avg_execution_time_sec:.1f}s", "")

    console.print(table)


@click.command(help="Evaluate TAHP skills against test datasets.")
@click.argument("skill_path", type=click.Path(exists=True))
@click.argument("dataset_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", type=click.Path(),
              help="Output report file path (JSON).")
@click.option("--model", "-m", default="claude-sonnet-4-20250514",
              help="AI model to evaluate (default: claude-sonnet-4-20250514).")
@click.option("--timeout", "timeout_sec", type=int, default=300,
              help="Timeout per test case in seconds (default: 300).")
def main(skill_path: str, dataset_path: str, output_path: Optional[str],
         model: str, timeout_sec: int) -> None:
    """Evaluate a TAHP SKILL_PATH against DATASET_PATH test cases.

    The dataset should contain a 'cases/' subdirectory with YAML files, where
    each file defines an input/expected pair for evaluation.
    """
    run_evaluation(
        skill_path=Path(skill_path).resolve(),
        dataset_path=Path(dataset_path).resolve(),
        model=model,
        output_path=Path(output_path) if output_path else None,
    )


if __name__ == "__main__":
    main()
