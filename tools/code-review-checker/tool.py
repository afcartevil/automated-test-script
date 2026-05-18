"""Code Review Checker - 自动化代码审查"""
import re

class CodeReviewChecker:
    P0_RULES = [
        {"id": "P0-001", "name": "Scope合规", "pattern": r"forbidden_paths", "severity": "critical"},
        {"id": "P0-002", "name": "安全红线", "pattern": r"hardcoded.*(key|token|password)", "severity": "critical"},
        {"id": "P0-003", "name": "API真实性", "pattern": r"TODO.*verify.*API", "severity": "critical"},
    ]
    P1_RULES = [
        {"id": "P1-001", "name": "编码风格", "pattern": r"checkpatch", "severity": "warning"},
        {"id": "P1-002", "name": "废弃API", "pattern": r"@Deprecated", "severity": "warning"},
        {"id": "P1-003", "name": "TODO关联", "pattern": r"TODO(?!.*\d{4,})", "severity": "warning"},
    ]

    def check(self, patch_content: str, check_level: str = "P0", custom_rules: list = None) -> dict:
        violations = []
        rules = list(self.P0_RULES)
        if check_level in ("P1", "P2"): rules.extend(self.P1_RULES)
        if custom_rules: rules.extend(custom_rules)
        for line_num, line in enumerate(patch_content.split("\n"), 1):
            if not line.startswith("+"): continue
            for rule in rules:
                if re.search(rule["pattern"], line, re.IGNORECASE):
                    violations.append({"rule_id": rule["id"], "rule_name": rule["name"], "line": line_num, "content": line.strip()[:100], "severity": rule["severity"]})
        critical = sum(1 for v in violations if v["severity"] == "critical")
        warning = sum(1 for v in violations if v["severity"] == "warning")
        return {"result": "fail" if critical else ("warning" if warning > 2 else "pass"), "violations": violations,
                "score": max(0, 100 - critical * 30 - warning * 5), "critical_count": critical, "warning_count": warning}

def handle_check(params: dict) -> dict:
    return CodeReviewChecker().check(params.get("patch_content", ""), params.get("check_level", "P0"), params.get("rules"))
