"""Patch Generator - 根据适配规则批量生成patch"""
class PatchGenerator:
    def generate(self, migration_rules: list, target_files: list, source_code_paths: list = None) -> dict:
        patches, stats = [], {"generated": 0, "skipped": 0, "errors": 0}
        for rule in migration_rules:
            old_api, new_api = rule.get("old_api", ""), rule.get("new_api", "")
            if not old_api or not new_api: stats["errors"] += 1; continue
            affected = []
            if source_code_paths:
                pattern = rule.get("affected_files_pattern", "")
                for p in source_code_paths:
                    if all(part in p for part in pattern.replace("**", "").split("/") if part):
                        affected.append(p)
            if affected:
                patches.append({"rule_id": rule.get("id"), "old_api": old_api, "new_api": new_api,
                               "change_type": rule.get("change_type"), "confidence": rule.get("confidence", 0),
                               "auto": rule.get("auto", False), "affected_files": affected})
                stats["generated"] += 1
            else: stats["skipped"] += 1
        return {"patches": patches, "statistics": stats}

def handle_generate(params: dict) -> dict:
    return PatchGenerator().generate(params.get("migration_rules", []), params.get("target_files", []), params.get("source_code_paths"))
