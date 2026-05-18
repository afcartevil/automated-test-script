#!/usr/bin/env python3
"""TAHP EvoSkill Evolution Runner.

Orchestrates iterative skill evolution: generate variants, evaluate, select best,
record feedback, and repeat. Supports parallel evaluation, configurable iteration
counts, dry-run preview mode, and feedback history tracking via Claude Code.

Usage:
    python scripts/run_evolution.py skills/telephony-bug-analyzer/
    python scripts/run_evolution.py skills/telephony-bug-analyzer/ --iterations 10 --dry-run
    python scripts/run_evolution.py skills/telephony-bug-analyzer/ --concurrency 4
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich.table import Table

console = Console()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "evolution": {
        "max_iterations": 20,
        "concurrency": 2,
        "selection_strategy": "highest_score",
        "mutation_rate": 0.15,
        "stagnation_threshold": 3,
    },
    "evaluation": {
        "dataset_path": "",
        "metrics_weights": {
            "accuracy": 0.35,
            "completeness": 0.25,
            "safety_compliance": 0.25,
            "time_efficiency": 0.15,
        },
        "pass_threshold": 0.72,
    },
    "generation": {
        "model": "claude-sonnet-4-20250514",
        "variant_template": "",
        "max_variants_per_iteration": 3,
    },
}


def load_config(skill_dir: Path) -> dict[str, Any]:
    """Load evolution configuration from .evoskill/config.toml, falling back to defaults."""
    config_path = skill_dir / ".evoskill" / "config.toml"
    if config_path.exists():
        with open(config_path, "rb") as fh:
            user_config = tomllib.load(fh)
        # Deep merge with defaults
        merged = copy.deepcopy(DEFAULT_CONFIG)
        _deep_merge(merged, user_config)
        return merged
    console.print("[yellow]No .evoskill/config.toml found, using default configuration.[/yellow]")
    return copy.deepcopy(DEFAULT_CONFIG)


def _deep_merge(base: dict, override: dict) -> None:
    """Recursively merge override into base (mutates base)."""
    for key, val in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(val, dict):
            _deep_merge(base[key], val)
        else:
            base[key] = val


@dataclass
class EvolutionIteration:
    """Record of a single evolution iteration."""
    iteration_number: int
    variant_ids: list[str]
    scores: list[dict[str, float]]
    best_variant_id: str
    best_score: float
    selected_action: str  # keep | mutate | replace
    duration_sec: float
    timestamp: str
    notes: str = ""


@dataclass
class EvolutionReport:
    """Complete evolution run report."""
    skill_name: str
    start_time: str
    end_time: str
    total_iterations: int
    final_best_variant: str
    final_best_score: float
    improvement_delta: float
    iterations: list[EvolutionIteration] = field(default_factory=list)

    def to_dict(self) -> dict:
        from dataclasses import asdict
        return asdict(self)


# ---------------------------------------------------------------------------
# Core Evolution Steps
# ---------------------------------------------------------------------------

def generate_variants(skill_dir: Path, config: dict, iteration: int,
                      dry_run: bool = False) -> list[tuple[str, Path]]:
    """Generate candidate skill variants for this iteration.

    Returns list of (variant_id, variant_dir_path) tuples.
    """
    gen_cfg = config.get("generation", {})
    num_variants = gen_cfg.get("max_variants_per_iteration", 3)
    model = gen_cfg.get("model", "claude-sonnet-4-20250514")

    variants_dir = skill_dir / ".evoskill" / "variants" / f"iter_{iteration:03d}"
    if not dry_run:
        variants_dir.mkdir(parents=True, exist_ok=True)

    variants: list[tuple[str, Path]] = []
    for i in range(num_variants):
        variant_id = f"v{i+1}_iter{iteration}"
        variant_path = variants_dir / variant_id

        if dry_run:
            variants.append((variant_id, variant_path))
            continue

        variant_path.mkdir(parents=True, exist_ok=True)
        # Copy base skill files into variant directory
        _copy_skill_files(skill_dir, variant_path)

        # Apply mutation instructions via AI generation
        mutation_prompt = _build_mutation_prompt(config, iteration, i, num_variants)
        _apply_ai_mutation(variant_path, mutation_prompt, model)

        variants.append((variant_id, variant_path))

    return variants


def _copy_skill_files(src: Path, dst: Path) -> None:
    """Copy skill source files (excluding .evoskill/, reports/, etc.) to destination."""
    skip_dirs = {".evoskill", ".git", "__pycache__", "reports", "node_modules"}
    for item in src.iterdir():
        if item.name.startswith(".") or item.name in skip_dirs:
            continue
        if item.is_file():
            shutil.copy2(item, dst / item.name)
        elif item.is_dir():
            shutil.copytree(item, dst / item.name, dirs_exist_ok=True)


def _build_mutation_prompt(config: dict, iteration: int, variant_idx: int,
                           total_variants: int) -> str:
    """Construct the mutation/generation prompt for the AI model."""
    evo_cfg = config.get("evolution", {})
    mutation_rate = evo_cfg.get("mutation_rate", 0.15)
    strategy = evo_cfg.get("selection_strategy", "highest_score")

    prompt = f"""You are evolving a TAHP AI skill. Generate an improved variant.

Context:
- Iteration: {iteration}
- Variant index: {variant_idx + 1}/{total_variants}
- Target mutation intensity: {mutation_rate * 100:.0f}%
- Selection strategy: {strategy}

Instructions:
1. Read the current skill files in this directory.
2. Identify the most likely areas for improvement based on typical failure modes:
   - Incomplete root cause analysis
   - Missing edge-case handling
   - Overly generic recommendations
   - Insufficient safety checks
3. Apply focused mutations (do NOT rewrite everything — change ~{mutation_rate * 100:.0f}% of logic).
4. Preserve the existing interface and output format.
5. Write the modified files back in place.
6. Create or update a CHANGELOG.md describing what changed.

Output your changes directly to the files. Be precise and targeted."""

    # Append feedback context if available
    fb_path = Path(".claude/feedback_history.md")
    if fb_path.exists():
        recent_feedback = _read_recent_feedback(fb_path, max_entries=3)
        if recent_feedback:
            prompt += f"\n\nRecent feedback to incorporate:\n{recent_feedback}\n"

    return prompt


def _apply_ai_mutation(variant_path: Path, prompt: str, model: str) -> subprocess.CompletedProcess:
    """Use Claude Code CLI to apply mutations to a skill variant."""
    cmd = [
        "claude",
        "-p", prompt,
        "--model", model,
        "--allowedTools", "Edit,Write,Bash",
        "--cwd", str(variant_path),
    ]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=600)


def evaluate_variants(variant_paths: list[tuple[str, Path]], config: dict,
                      concurrency: int, dry_run: bool = False) -> list[dict[str, Any]]:
    """Evaluate all variants in parallel (up to concurrency limit).

    Returns list of result dicts with variant_id and scores.
    """
    if dry_run:
        # Simulate evaluation results
        import random
        random.seed(42)
        results = []
        for vid, _ in variant_paths:
            results.append({
                "variant_id": vid,
                "scores": {
                    "accuracy": round(random.uniform(0.55, 0.92), 4),
                    "completeness": round(random.uniform(0.50, 0.90), 4),
                    "safety_compliance": round(random.uniform(0.85, 1.0), 4),
                    "time_efficiency": round(random.uniform(0.40, 0.95), 4),
                },
                "composite_score": round(random.uniform(0.55, 0.90), 4),
            })
        return results

    eval_cfg = config.get("evaluation", {})
    dataset_path = eval_cfg.get("dataset_path", "")
    if not dataset_path:
        console.print("[yellow]Warning: No dataset_path configured. Using dummy evaluation.[/yellow]")
        return [(v, _dummy_evaluate(v)) for v in variant_paths]

    # Run evaluate.py for each variant
    results: list[dict[str, Any]] = []
    model = config.get("generation", {}).get("model", "claude-sonnet-4-20250514")
    script_dir = Path(__file__).resolve().parent

    for vid, vpath in variant_paths:
        eval_script = script_dir / "evaluate.py"
        cmd = [
            sys.executable, str(eval_script),
            str(vpath), dataset_path,
            "--model", model,
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            # Parse output JSON if available
            score = _parse_eval_output(proc.stdout, proc.returncode)
            results.append({
                "variant_id": vid,
                "scores": score,
                "composite_score": _weighted_composite(score, eval_cfg.get("metrics_weights", {})),
            })
        except subprocess.TimeoutExpired:
            results.append({"variant_id": vid, "scores": {}, "composite_score": 0.0})
        except Exception as exc:
            console.print(f"[red]Evaluation error for {vid}: {exc}[/red]")
            results.append({"variant_id": vid, "scores": {}, "composite_score": 0.0})

    return results


def _parse_eval_output(stdout: str, returncode: int) -> dict[str, float]:
    """Extract scores from evaluate.py output."""
    try:
        # Look for JSON in stdout
        lines = stdout.strip().split("\n")
        for line in reversed(lines):
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                return {
                    "accuracy": data.get("accuracy", 0.0),
                    "completeness": data.get("completeness", 0.0),
                    "safety_compliance": data.get("safety_compliance", 0.0),
                    "time_efficiency": data.get("time_efficiency", 0.0),
                }
    except (json.JSONDecodeError, ValueError):
        pass
    return {"accuracy": 0.0, "completeness": 0.0, "safety_compliance": 1.0, "time_efficiency": 0.0}


def _weighted_composite(scores: dict[str, float],
                        weights: dict[str, float]) -> float:
    """Calculate weighted composite score from individual metrics."""
    default_weights = {"accuracy": 0.35, "completeness": 0.25,
                       "safety_compliance": 0.25, "time_efficiency": 0.15}
    w = default_weights | weights
    composite = sum(scores.get(k, 0.0) * w.get(k, 0.0) for k in default_weights)
    return round(composite, 4)


def _dummy_evaluate(variant_info: tuple[str, Path]) -> dict[str, Any]:
    """Return placeholder evaluation for dry-run mode."""
    vid, _ = variant_info
    return {
        "variant_id": vid,
        "scores": {
            "accuracy": 0.70,
            "completeness": 0.65,
            "safety_compliance": 1.0,
            "time_efficiency": 0.80,
        },
        "composite_score": 0.73,
    }


def select_best(evaluation_results: list[dict[str, Any]],
                strategy: str = "highest_score") -> Optional[dict[str, Any]]:
    """Select the best variant from evaluation results."""
    if not evaluation_results:
        return None
    if strategy == "highest_score":
        return max(evaluation_results, key=lambda r: r.get("composite_score", 0.0))
    # Future strategies: epsilon-greedy, tournament, etc.
    return max(evaluation_results, key=lambda r: r.get("composite_score", 0.0))


def record_feedback(best_result: dict, iteration_num: int, skill_dir: Path,
                    action: str, dry_run: bool = False) -> None:
    """Append iteration result to .claude/feedback_history.md."""
    fb_path = skill_dir / ".claude" / "feedback_history.md"
    if dry_run:
        console.print(f"  [dim](Would append feedback to {fb_path})[/dim]")
        return

    fb_path.parent.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().isoformat()
    scores = best_result.get("scores", {})
    composite = best_result.get("composite_score", 0.0)

    entry = (
        f"\n## Iteration {iteration_num} — {timestamp}\n\n"
        f"- **Best Variant:** `{best_result.get('variant_id', 'unknown')}`\n"
        f"- **Composite Score:** {composite:.4f}\n"
        f"- **Accuracy:** {scores.get('accuracy', 0):.4f}\n"
        f"- **Completeness:** {scores.get('completeness', 0):.4f}\n"
        f"- **Safety:** {scores.get('safety_compliance', 0):.4f}\n"
        f"- **Time Efficiency:** {scores.get('time_efficiency', 0):.4f}\n"
        f"- **Action:** {action}\n"
    )

    mode = "a" if fb_path.exists() else "w"
    header = "# EvoSkill Feedback History\n\nAuto-generated by `run_evolution.py`.\n\n"
    with open(fb_path, mode, encoding="utf-8") as fh:
        if mode == "w":
            fh.write(header)
        fh.write(entry)


def save_evolution_report(report: EvolutionReport, skill_dir: Path) -> Path:
    """Persist the complete evolution report to disk."""
    report_dir = skill_dir / "reports" / "evolution-reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"evolution_{report.skill_name}_{ts}.json"
    report_path = report_dir / filename

    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report.to_dict(), fh, indent=2, ensure_ascii=False, default=str)

    return report_path


# ---------------------------------------------------------------------------
# Feedback History Utilities
# ---------------------------------------------------------------------------

def _read_recent_feedback(fb_path: Path, max_entries: int = 3) -> Optional[str]:
    """Read the most recent N entries from the feedback history markdown."""
    if not fb_path.exists():
        return None
    try:
        content = fb_path.read_text(encoding="utf-8")
        # Split by ## headers (entry separators)
        entries = content.split("\n## ")[-max_entries:]
        return "\n## ".join(entries[-max_entries:]) if entries else None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Main Evolution Loop
# ---------------------------------------------------------------------------

def run_evolution(skill_dir: Path, iterations: Optional[int] = None,
                  concurrency: int = 2, dry_run: bool = False) -> EvolutionReport:
    """Execute the full evolution cycle."""
    skill_dir = skill_dir.resolve()
    config = load_config(skill_dir)

    max_iters = iterations or config["evolution"]["max_iterations"]
    concurrency = min(concurrency, config["evolution"].get("concurrency", 2))
    strategy = config["evolution"]["selection_strategy"]

    console.print(Panel(
        f"[bold]TAHP EvoSkill Evolution[/bold]\n\n"
        f"Skill: [cyan]{skill_dir.name}[/cyan]\n"
        f"Max iterations: {max_iters}\n"
        f"Concurrency: {concurrency}\n"
        f"Strategy: {strategy}\n"
        f"Dry-run: {'Yes' if dry_run else 'No'}",
        title="Evolution Configuration",
    ))

    report = EvolutionReport(
        skill_name=skill_dir.name,
        start_time=datetime.utcnow().isoformat(),
        end_time="",
        total_iterations=max_iters,
        final_best_variant="",
        final_best_score=0.0,
        improvement_delta=0.0,
    )

    prev_best_score: float = 0.0
    stagnation_counter: int = 0
    stagnation_threshold = config["evolution"].get("stagnation_threshold", 3)

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                  BarColumn(), console=console) as progress:
        task = progress.add_task("Evolution progress...", total=max_iters)

        for it in range(1, max_iters + 1):
            iter_start = datetime.utcnow()
            progress.update(task, description=f"Iteration {it}/{max_iters} ...")

            # Step 1: Generate variants
            console.print(f"\n[bold cyan]--- Iteration {it}/{max_iters} ---[/bold cyan]")
            variants = generate_variants(skill_dir, config, it, dry_run=dry_run)
            console.print(f"  Generated {len(variants)} variant(s): {[v[0] for v in variants]}")

            # Step 2: Evaluate
            eval_results = evaluate_variants(variants, config, concurrency, dry_run=dry_run)
            for er in eval_results:
                console.print(f"  [er['variant_id']]: composite={er.get('composite_score', 0):.4f}")

            # Step 3: Select best
            best = select_best(eval_results, strategy)
            if best is None:
                console.print("[red]No valid evaluation results. Stopping.[/red]")
                break

            best_score = best.get("composite_score", 0.0)
            best_vid = best.get("variant_id", "unknown")

            # Determine action
            if best_score > prev_best_score + 0.01:
                action = "replace (improved)"
                stagnation_counter = 0
            elif best_score >= prev_best_score:
                action = "keep (stable)"
                stagnation_counter += 1
            else:
                action = "keep (regression avoided)"
                stagnation_counter += 1

            elapsed = (datetime.utcnow() - iter_start).total_seconds()

            # Record iteration
            it_record = EvolutionIteration(
                iteration_number=it,
                variant_ids=[v[0] for v in variants],
                scores=[er.get("scores", {}) for er in eval_results],
                best_variant_id=best_vid,
                best_score=best_score,
                selected_action=action,
                duration_sec=round(elapsed, 2),
                timestamp=datetime.utcnow().isoformat(),
            )
            report.iterations.append(it_record)

            # Update tracking
            improvement = best_score - prev_best_score
            if best_score > prev_best_score:
                report.final_best_variant = best_vid
                report.final_best_score = best_score
                report.improvement_delta = improvement
            prev_best_score = max(prev_best_score, best_score)

            console.print(f"  Best: [green]{best_vid}[/green] @ {best_score:.4f} ({action})")

            # Record feedback
            record_feedback(best, it, skill_dir, action, dry_run=dry_run)

            # Early termination on stagnation
            if stagnation_counter >= stagnation_threshold and stagnation_threshold > 0:
                console.print(f"\n[yellow]Stagnation threshold ({stagnation_threshold}) reached. "
                              f"Stopping early at iteration {it}.[/yellow]")
                break

            progress.advance(task)

    report.end_time = datetime.utcnow().isoformat()
    report.total_iterations = len(report.iterations)

    # Save report
    if not dry_run:
        report_path = save_evolution_report(report, skill_dir)
        console.print(f"\nEvolution report saved to: [cyan]{report_path}[/cyan]")

    # Final summary table
    _print_evolution_summary(report)
    return report


def _print_evolution_summary(report: EvolutionReport) -> None:
    """Print final evolution summary table."""
    table = Table(title="Evolution Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Skill", report.skill_name)
    table.add_row("Iterations Completed", str(report.total_iterations))
    table.add_row("Final Best Variant", report.final_best_variant)
    table.add_row("Final Best Score", f"{report.final_best_score:.4f}")
    table.add_row("Total Improvement", f"{report.improvement_delta:+.4f}")
    console.print(table)


@click.command(help="Run TAHP EvoSkill evolution loop for a skill directory.")
@click.argument("skill_dir", type=click.Path(exists=True))
@click.option("--iterations", "-n", type=int, default=None,
              help="Override max iteration count from config.")
@click.option("--concurrency", "-c", type=int, default=2,
              help="Parallel evaluation concurrency (default: 2).")
@click.option("--dry-run", is_flag=True, default=False,
              help="Preview evolution plan without executing.")
def main(skill_dir: str, iterations: Optional[int], concurrency: int, dry_run: bool) -> None:
    """Run EvoSkill evolution for the skill at SKILL_DIR.

    Reads .evoskill/config.toml for configuration and iteratively generates,
    evaluates, selects, and records improved skill variants.
    """
    run_evolution(
        skill_dir=Path(skill_dir),
        iterations=iterations,
        concurrency=concurrency,
        dry_run=dry_run,
    )


if __name__ == "__main__":
    main()
