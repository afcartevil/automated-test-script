#!/usr/bin/env python3
"""Tests for scripts/gate_check.py

测试质量门禁检查器：安全红线、硬编码密钥检测、约束文件有效性、module.yaml 完整性。
"""
import sys
import tempfile
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from gate_check import (
    check_safety_red_lines_present,
    check_no_hardcoded_secrets,
    check_constraint_files_valid,
    check_documentation_complete,
    GateCheck,
    GateLevel,
)


def _make_temp_dir(files: dict[str, str]) -> Path:
    """Create a temporary directory with the given files (name → content)."""
    tmpdir = Path(tempfile.mkdtemp())
    for fname, content in files.items():
        (tmpdir / fname).write_text(content, encoding="utf-8")
    return tmpdir


class TestCheckSafetyRedLinesPresent:
    """Tests for P0 check: safety_red_lines_present."""

    def test_has_safety_red_lines_passes(self):
        """At least one constraint file with safety_red_lines → PASS."""
        d = _make_temp_dir({
            "bug-analysis.yaml": """
metadata:
  module: test
  domain: bug_analysis
  version: "1.0"
  author: "x"
  last_updated: "2026-05-20"
safety_red_lines:
  - "rule 1"
  - "rule 2"
rules:
  test: true
"""
        })
        try:
            result = check_safety_red_lines_present(d)
            assert result.passed is True
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_no_constraint_files_fails(self):
        """Directory with no constraint YAML files → FAIL."""
        d = _make_temp_dir({"README.md": "# just a readme"})
        try:
            result = check_safety_red_lines_present(d)
            assert result.passed is False
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)


class TestCheckNoHardcodedSecrets:
    """Tests for P0 check: no_hardcoded_secrets."""

    def test_no_secrets_passes(self):
        """Directory with clean files → PASS."""
        d = _make_temp_dir({
            "config.yaml": "api_endpoint: https://example.com\nkey_ref: ${API_KEY}\n"
        })
        try:
            result = check_no_hardcoded_secrets(d)
            assert result.passed is True
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_hardcoded_api_key_fails(self):
        """File with hardcoded api_key → FAIL."""
        d = _make_temp_dir({
            "config.yaml": 'api_key: "sk-1234567890abcdef"\n'
        })
        try:
            result = check_no_hardcoded_secrets(d)
            assert result.passed is False
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_hardcoded_password_fails(self):
        """File with hardcoded password → FAIL."""
        d = _make_temp_dir({
            "settings.yaml": 'password: "admin123456"\n'
        })
        try:
            result = check_no_hardcoded_secrets(d)
            assert result.passed is False
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)


class TestCheckConstraintFilesValid:
    """Tests for P0 check: constraint_files_valid."""

    def test_valid_yaml_passes(self):
        """Directory with valid YAML files → PASS."""
        d = _make_temp_dir({
            "bug-analysis.yaml": "metadata:\n  module: test\ndomain: bug_analysis\n"
        })
        try:
            result = check_constraint_files_valid(d)
            assert result.passed is True
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_invalid_yaml_fails(self):
        """Directory with invalid YAML → FAIL."""
        d = _make_temp_dir({
            "broken.yaml": "key: [unclosed\n"
        })
        try:
            result = check_constraint_files_valid(d)
            assert result.passed is False
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)


class TestCheckDocumentationComplete:
    """Tests for P1 check: documentation_complete."""

    def test_complete_module_yaml_passes(self):
        """module.yaml with all required fields → PASS."""
        d = _make_temp_dir({
            "module.yaml": """module:
  name: test-module
  owner: "test-owner"
  display_name: "Test Module"
scope:
  includes:
    - component: "Test"
      path: "test/"
"""
        })
        try:
            result = check_documentation_complete(d)
            assert result.passed is True, f"Expected PASS but got: {result.detail}"
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_missing_owner_fails(self):
        """module.yaml with empty owner → FAIL."""
        d = _make_temp_dir({
            "module.yaml": """module:
  name: test-module
  owner: ""
scope:
  includes: []
"""
        })
        try:
            result = check_documentation_complete(d)
            assert result.passed is False, f"Expected FAIL due to empty owner"
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)

    def test_missing_module_yaml_fails(self):
        """No module.yaml file → FAIL."""
        d = _make_temp_dir({"other.yaml": "key: value"})
        try:
            result = check_documentation_complete(d)
            assert result.passed is False
        finally:
            import shutil; shutil.rmtree(d, ignore_errors=True)
