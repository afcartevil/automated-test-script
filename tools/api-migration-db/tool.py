"""API Migration Database - 迁移规则库管理"""
import yaml, os

class APIMigrationDB:
    RULES_DIR = "constraints/shared/api-migration-rules"

    def __init__(self, repo_root="."):
        self.rules_dir = os.path.join(repo_root, self.RULES_DIR)

    def list_rules(self, module=None) -> dict:
        rules = []
        if os.path.exists(self.rules_dir):
            for f in os.listdir(self.rules_dir):
                if f.endswith("-migration.yaml"):
                    with open(os.path.join(self.rules_dir, f), "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh)
                        if data and "rules" in data:
                            for r in data["rules"]:
                                if module is None or data.get("metadata", {}).get("module") == module:
                                    rules.append(r)
        return {"rules": rules, "total": len(rules)}

    def search(self, old_api: str) -> dict:
        result = self.list_rules()
        matched = [r for r in result["rules"] if old_api.lower() in r.get("old_api", "").lower()]
        return {"rules": matched, "total": len(matched)}

    def add_rule(self, rule: dict, module="telephony") -> dict:
        filepath = os.path.join(self.rules_dir, f"{module}-migration.yaml")
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as fh: data = yaml.safe_load(fh) or {}
        else: data = {"metadata": {"module": module, "total_rules": 0}, "rules": []}
        data["rules"].append(rule); data["metadata"]["total_rules"] = len(data["rules"])
        os.makedirs(self.rules_dir, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as fh: yaml.dump(data, fh, allow_unicode=True, default_flow_style=False)
        return {"status": "ok", "rule_id": rule.get("id"), "total": len(data["rules"])}

def handle_query(params: dict) -> dict:
    db = APIMigrationDB()
    action = params.get("action", "list")
    if action == "list": return db.list_rules(params.get("module"))
    elif action == "search": return db.search(params.get("old_api", ""))
    elif action == "add": return db.add_rule(params.get("rule", {}), params.get("module", "telephony"))
    else: return {"error": f"Unknown action: {action}"}
