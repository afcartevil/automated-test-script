"""AOSP Diff Analyzer - 对比Android版本framework差异"""
import re
from typing import Optional

class AOSPDiffAnalyzer:
    DEPRECATED_PATTERN = r"@Deprecated"
    REMOVED_PATTERN = r"-.*(?:public|protected)\s+"
    ADDED_PATTERN = r"\+.*(?:public|protected)\s+"

    def analyze(self, diff_content: str, source_version: str, target_version: str, module_filter: Optional[str] = None) -> dict:
        deprecated_apis, removed_apis, added_apis = [], [], []
        files = self._split_files(diff_content)
        for fpath, fdiff in files:
            if module_filter and module_filter not in fpath:
                continue
            if not fpath.endswith(".java"):
                continue
            for line in fdiff.split("\n"):
                if "@Deprecated" in line and line.startswith("+"):
                    deprecated_apis.append({"file": fpath, "content": line.strip(), "version": target_version})
                if re.match(self.REMOVED_PATTERN, line):
                    removed_apis.append({"file": fpath, "content": line.strip(), "change_type": "removed"})
                if re.match(self.ADDED_PATTERN, line):
                    added_apis.append({"file": fpath, "content": line.strip(), "change_type": "added"})
        return {"deprecated_apis": deprecated_apis, "removed_apis": removed_apis, "added_apis": added_apis,
                "summary": {"source_version": source_version, "target_version": target_version,
                            "total_deprecated": len(deprecated_apis), "total_removed": len(removed_apis), "total_added": len(added_apis)}}

    def _split_files(self, diff_content: str) -> list:
        files, cur_file, cur_diff = [], None, []
        for line in diff_content.split("\n"):
            if line.startswith("diff --git"):
                if cur_file: files.append((cur_file, "\n".join(cur_diff)))
                cur_file = line.split(" b/")[-1]; cur_diff = []
            elif cur_file: cur_diff.append(line)
        if cur_file: files.append((cur_file, "\n".join(cur_diff)))
        return files

def handle_analyze(params: dict) -> dict:
    return AOSPDiffAnalyzer().analyze(params.get("diff_content", ""), params.get("source_version", ""), params.get("target_version", ""), params.get("module_filter"))
