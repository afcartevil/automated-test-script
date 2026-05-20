#!/usr/bin/env python3
"""Tests for scripts/validate_constraints.py

测试约束文件校验器：正常通过、缺少metadata、domain枚举错误、YAML语法错误。
"""
import sys
import tempfile
import os
from pathlib import Path

import pytest

# Add project root to path so we can import the validator
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validate_constraints import validate_single_file, ValidationResult


def _write_temp_yaml(content: str, suffix: str = ".yaml") -> Path:
    """Write content to a temporary YAML file, return its Path."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return Path(tmp.name)


class TestValidateSingleFile:
    """Tests for validate_single_file — the core validation function."""

    def test_valid_constraint_file_passes(self):
        """A correctly structured constraint file should pass with 0 errors."""
        content = """metadata:
  module: telephony
  domain: bug_analysis
  version: "1.0"
  author: "test"
  last_updated: "2026-05-20"

safety_red_lines:
  - "不修改 scope.excludes 中列出的任何文件"

rules:
  preconditions:
    required_info: []
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            assert result.status == "PASS", f"Expected PASS, got errors: {result.errors}"
            assert len(result.errors) == 0
        finally:
            os.unlink(fpath)

    def test_missing_top_level_keys_fails(self):
        """Missing 'metadata', 'rules', or 'safety_red_lines' should produce errors."""
        content = """some_key:
  data: "no metadata, no rules, no safety_red_lines"
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            assert result.status == "FAIL"
            assert any("Missing required top-level key" in e.message for e in result.errors)
        finally:
            os.unlink(fpath)

    def test_missing_metadata_fields_fails(self):
        """Missing required metadata fields should produce errors."""
        content = """metadata:
  module: telephony

safety_red_lines:
  - "test"

rules:
  test: true
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            assert result.status == "FAIL"
            # Should complain about missing domain, version, author, last_updated
            assert any("metadata.domain" in e.message for e in result.errors)
        finally:
            os.unlink(fpath)

    def test_invalid_domain_enum_fails(self):
        """domain value outside the valid enum should fail."""
        content = """metadata:
  module: telephony
  domain: invalid_domain_xyz
  version: "1.0"
  author: "test"
  last_updated: "2026-05-20"

safety_red_lines:
  - "test"

rules:
  test: true
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            assert result.status == "FAIL"
            assert any("metadata.domain" in e.message and "invalid" in e.message for e in result.errors)
        finally:
            os.unlink(fpath)

    def test_yaml_syntax_error_fails(self):
        """Invalid YAML syntax should be caught."""
        content = """metadata:
  module: telephony
 domain: bug_analysis  # <-- bad indentation causes YAML error
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            assert result.status == "FAIL"
            # It should report syntax error or missing top-level keys
            assert len(result.errors) > 0
        finally:
            os.unlink(fpath)

    def test_empty_safety_red_lines_warns(self):
        """Empty safety_red_lines should produce a warning (not error)."""
        content = """metadata:
  module: telephony
  domain: bug_analysis
  version: "1.0"
  author: "test"
  last_updated: "2026-05-20"

safety_red_lines: []

rules:
  test: true
"""
        fpath = _write_temp_yaml(content)
        try:
            result = validate_single_file(fpath)
            # Empty list is a warning, not an error — should still pass
            assert result.status == "PASS"
            assert any("empty" in w.message for w in result.warnings)
        finally:
            os.unlink(fpath)

    def test_all_valid_domains_pass(self):
        """All four valid domains should pass validation."""
        for domain in ["bug_analysis", "code_adaptation", "version_adaptation", "carrier_porting"]:
            content = f"""metadata:
  module: test
  domain: {domain}
  version: "1.0"
  author: "test"
  last_updated: "2026-05-20"

safety_red_lines:
  - "test"

rules:
  test: true
"""
            fpath = _write_temp_yaml(content)
            try:
                result = validate_single_file(fpath)
                assert result.status == "PASS", f"Domain '{domain}' should pass but got: {result.errors}"
            finally:
                os.unlink(fpath)

    def test_module_yaml_skipped(self):
        """module.yaml files should be skipped (module registry, not constraint)."""
        content = """module:
  name: test
  owner: "someone"

scope:
  includes: []
"""
        fpath = _write_temp_yaml(content, suffix="module.yaml")
        # Rename to module.yaml
        dirpath = tempfile.mkdtemp()
        final_path = Path(dirpath) / "module.yaml"
        Path(fpath).rename(final_path)
        try:
            result = validate_single_file(final_path)
            assert result.status == "PASS"
            assert len(result.errors) == 0
        finally:
            import shutil
            shutil.rmtree(dirpath, ignore_errors=True)
