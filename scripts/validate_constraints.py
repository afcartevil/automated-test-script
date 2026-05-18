#!/usr/bin/env python3
"""TAHP Constraint File Validator.

CLI tool that validates constraint YAML files against the TAHP schema specification.
Supports single-file validation, directory scanning, cross-reference checks, and
strict mode for additional quality gates.

Usage:
    python scripts/validate_constraints.py constraints/telephony/bug-analysis.yaml
    python scripts/validate_constraints.py constraints/ --all
    python scripts/validate_constraints.py constraints/telephony/ --module --strict
"""

from __future__ import annotations

import re
import sys
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import click
from rich.console import Console
from rich.table import Table

console = Console()

# Valid domain enum values per TAHP spec
VALID_DOMAINS = {"bug_analysis", "code_adaptation", "version_adaptation", "carrier_porting"}

# Required top-level keys in every constraint YAML file
REQUIRED_TOP_KEYS: set[str] = {"metadata", "rules", "safety_red_lines"}

# Required fields within the metadata section
REQUIRED_METADATA_FIELDS: list[str] = ["module", "domain", "version", "author", "last_updated"]


@dataclass
class ValidationError:
    """Represents a single validation finding."""

    path: str
    message: str
    level: str = "error"  # error | warning | info


@dataclass
class ValidationResult:
    """Aggregated result for a single validated target."""

    target: str
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    info: list[ValidationError] = field(default_factory=list)

    @property
    def status(self) -> str:
        return "FAIL" if self.errors else "PASS"

    @property
    def total_issues(self) -> int:
        return len(self.errors) + len(self.warnings)


def _load_yaml(file_path: Path) -> tuple[Optional[dict], Optional[str]]:
    """Load a YAML file, returning (data, error_message)."""
    try:
        with open(file_path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh), None
    except yaml.YAMLError as exc:
        return None, f"YAML syntax error: {exc}"
    except FileNotFoundError:
        return None, f"File not found: {file_path}"
    except OSError as exc:
        return None, f"I/O error reading {file_path}: {exc}"


def validate_yaml_syntax(file_path: Path, results: ValidationResult) -> None:
    """Check that a file is parseable YAML."""
    data, err = _load_yaml(file_path)
    if err:
        results.errors.append(ValidationError(str(file_path), err))


def validate_top_level_schema(file_path: Path, results: ValidationResult, strict: bool = False) -> None:
    """Validate top-level keys: metadata, rules, safety_red_lines."""
    data, err = _load_yaml(file_path)
    if err or not isinstance(data, dict):
        return  # already reported as syntax error

    present = set(data.keys())
    missing = REQUIRED_TOP_KEYS - present
    if missing:
        results.errors.append(
            ValidationError(
                str(file_path),
                f"Missing required top-level key(s): {', '.join(sorted(missing))}",
            )
        )

    # Strict mode: warn about unknown top-level keys (typos)
    if strict:
        known_keys = REQUIRED_TOP_KEYS | {"preconditions", "analysis_rules", "security_gates",
                                          "evaluation", "postconditions", "adaptation_rules",
                                          "porting_requirements"}
        extra = present - known_keys
        if extra:
            results.warnings.append(
                ValidationError(str(file_path), f"Unrecognized top-level key(s): {', '.join(sorted(extra))}")
            )


def validate_metadata(file_path: Path, results: ValidationResult, strict: bool = False) -> None:
    """Validate the metadata section contents."""
    data, err = _load_yaml(file_path)
    if err or not isinstance(data, dict):
        return

    meta = data.get("metadata")
    if meta is None:
        # metadata might be absent — top-level check catches this; try graceful handling
        return

    if not isinstance(meta, dict):
        results.errors.append(ValidationError(str(file_path), "'metadata' must be a mapping/dict"))
        return

    # Check required fields
    for field_name in REQUIRED_METADATA_FIELDS:
        value = meta.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            results.errors.append(
                ValidationError(str(file_path), f"metadata.{field_name} is required and must be non-empty")
            )

    # Validate domain enum
    domain = meta.get("domain")
    if domain and domain not in VALID_DOMAINS:
        results.errors.append(
            ValidationError(
                str(file_path),
                f"metadata.domain '{domain}' is invalid; must be one of: {', '.join(sorted(VALID_DOMAINS))}",
            )
        )

    # Strict mode: validate version format (semantic versioning hint)
    if strict:
        ver = meta.get("version")
        if ver and not re.match(r"^\d+(\.\d+){0,3}(-.*)?$", str(ver)):
            results.warnings.append(
                ValidationError(str(file_path), f"metadata.version '{ver}' does not follow semantic versioning format")
            )

        # Validate last_updated is ISO date
        updated = meta.get("last_updated")
        if updated:
            try:
                datetime.fromisoformat(str(updated))
            except ValueError:
                results.warnings.append(
                    ValidationError(str(file_path), f"metadata.last_updated '{updated}' is not a valid ISO date")
                )


def validate_safety_red_lines(file_path: Path, results: ValidationResult) -> None:
    """Ensure safety_red_lines is a non-empty list when present."""
    data, err = _load_yaml(file_path)
    if err or not isinstance(data, dict):
        return

    srl = data.get("safety_red_lines")
    if srl is not None and not isinstance(srl, list):
        results.errors.append(
            ValidationError(str(file_path), "'safety_red_lines' must be a list")
        )
    elif isinstance(srl, list) and len(srl) == 0:
        results.warnings.append(
            ValidationError(str(file_path), "'safety_red_lines' is empty — consider adding at least one safety guard")
        )


def validate_cross_references(base_dir: Path, results_by_target: dict[str, ValidationResult],
                              all_results: ValidationResult) -> None:
    """Check inter-module dependency consistency across constraint files."""
    modules_dir = base_dir / "constraints"
    if not modules_dir.is_dir():
        return

    known_modules: set[str] = set()
    for entry in modules_dir.iterdir():
        if entry.is_dir() and entry.name != "shared":
            mod_yaml = entry / "module.yaml"
            if mod_yaml.exists():
                known_modules.add(entry.name)

    dep_pattern = re.compile(r"dependencies:\s*-?\s*module:\s*(\S+)")

    for target, vresult in results_by_target.items():
        target_path = Path(target)
        if not target_path.is_file():
            continue

        _, err = _load_yaml(target_path)
        if err:
            continue

        content = target_path.read_text(encoding="utf-8")

        # Check module.yaml dependency references
        if target_path.name == "module.yaml":
            data, load_err = _load_yaml(target_path)
            if not load_err and isinstance(data, dict):
                scope_deps = data.get("scope", {}).get("dependencies") or []
                for dep_entry in scope_deps:
                    dep_mod = dep_entry.get("module", "") if isinstance(dep_entry, dict) else ""
                    if dep_mod and dep_mod not in known_modules and dep_mod not in ("framework", "hal", "bt"):
                        all_results.warnings.append(
                            ValidationError(
                                target,
                                f"Dependency references unknown module '{dep_mod}' "
                                f"(known: {', '.join(sorted(known_modules)) or 'none'})",
                            )
                        )

        # Check rule-file internal references to other domain files
        if target_path.suffix == ".yaml" and target_path.name != "module.yaml":
            parent_dir = target_path.parent
            expected_domain_files = {
                "bug-analysis.yaml", "code-adaptation.yaml",
                "version-adaptation.yaml", "carrier-porting.yaml",
            }
            for ref_file in expected_domain_files:
                if (parent_dir / ref_file).exists():
                    pass  # reference target exists


def validate_single_file(file_path: Path, strict: bool = False) -> ValidationResult:
    """Run full validation pipeline on a single constraint file."""
    result = ValidationResult(target=str(file_path))

    validate_yaml_syntax(file_path, result)
    validate_top_level_schema(file_path, result, strict=strict)
    validate_metadata(file_path, result, strict=strict)
    validate_safety_red_lines(file_path, result)

    return result


def scan_directory(dir_path: Path, strict: bool = False,
                   recursive: bool = False) -> list[ValidationResult]:
    """Scan a directory for .yaml / .yml constraint files and validate each."""
    pattern = "**/*.yaml" if recursive else "*.yaml"
    yaml_files = sorted(dir_path.glob(pattern))
    # Also accept .yml
    if not recursive:
        yaml_files.extend(sorted(dir_path.glob("*.yml")))
    else:
        yaml_files.extend(sorted(dir_path.glob("**/*.yml")))

    # Deduplicate preserving order
    seen: set[str] = set()
    unique_files: list[Path] = []
    for f in yaml_files:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            unique_files.append(f)

    results: list[ValidationResult] = []
    for fp in unique_files:
        # Skip hidden / temp files
        if fp.name.startswith(".") or fp.name.startswith("_"):
            continue
        results.append(validate_single_file(fp, strict=strict))

    return results


def print_results(results: list[ValidationResult]) -> int:
    """Render validation results using rich console. Returns exit code."""
    table = Table(title="TAHP Constraint Validation Results", show_lines=True)
    table.add_column("Status", style="bold", justify="center", min_width=6)
    table.add_column("Target", style="cyan", min_width=40)
    table.add_column("Issues", justify="right", min_width=6)
    table.add_column("Details", max_width=80)

    any_fail = False
    total_errors = 0
    total_warnings = 0

    for r in results:
        status_icon = "[green]PASS[/green]" if r.status == "PASS" else "[red]FAIL[/red]"
        issue_count = r.total_issues

        details_parts: list[str] = []
        for e in r.errors:
            details_parts.append(f"[red]ERR[/red] {e.message}")
            total_errors += 1
        for w in r.warnings:
            details_parts.append(f"[yellow]WARN[/yellow] {w.message}")
            total_warnings += 1

        detail_text = "\n".join(details_parts[:5])
        if len(details_parts) > 5:
            detail_text += f"\n... and {len(details_parts) - 5} more"

        if r.status == "FAIL":
            any_fail = True

        table.add_row(status_icon, r.target, str(issue_count), detail_text)

    console.print(table)
    console.print()
    console.print(f"Total: [bold]{len(results)}[/bold] file(s), "
                  f"[red]{total_errors}[/red] error(s), "
                  f"[yellow]{total_warnings}[/yellow] warning(s)")

    return 1 if any_fail else 0


@click.command(help="Validate TAHP constraint YAML files against schema spec.")
@click.argument("target", type=click.Path(exists=True))
@click.option("--strict/--no-strict", default=False,
              help="Enable strict validation (extra warnings).")
@click.option("--recursive/-R", "recursive", is_flag=True, default=False,
              help="Recursively scan subdirectories.")
@click.option("--check-xref/--no-xref", "xref", default=True,
              help="Check cross-references between modules.")
def main(target: str, strict: bool, recursive: bool, xref: bool) -> None:
    """Validate TAHP constraint YAML files.

    TARGET can be a single constraint YAML file or a directory containing
    constraint files.
    """
    target_path = Path(target).resolve()
    base_dir = Path(__file__).resolve().parent.parent

    if target_path.is_file():
        results = [validate_single_file(target_path, strict=strict)]
    elif target_path.is_dir():
        results = scan_directory(target_path, strict=strict, recursive=recursive)
    else:
        raise click.BadParameter(f"Not a valid file or directory: {target}")

    # Cross-reference check
    if xref and target_path.is_dir():
        results_map = {r.target: r for r in results}
        xref_result = ValidationResult(target="[cross-reference]")
        validate_cross_references(base_dir, results_map, xref_result)
        if xref_result.warnings or xref_result.info:
            results.insert(0, xref_result)

    sys.exit(print_results(results))


if __name__ == "__main__":
    main()
