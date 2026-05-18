#!/usr/bin/env python3
"""TAHP 模块初始化脚本"""
import os, sys, shutil, re, argparse
from pathlib import Path

def init_module(module_name, owner):
    base = Path(__file__).parent.parent
    md = base / "constraints" / module_name
    if md.exists(): print(f"Error: Module '{module_name}' already exists"); sys.exit(1)
    md.mkdir(parents=True); (md / "eval-data" / "cases").mkdir(parents=True); (md / "eval-data" / "expected").mkdir(parents=True)
    (md / "module.yaml").write_text(f"module:\n  name: {module_name}\n  owner: {owner}\n  version: \"1.0\"\n  created: \"2026-05-18\"\nscope:\n  includes:\n    - component: \"\"\n      path: \"\"\n      description: \"\"\n  excludes:\n    - \"\"\n  dependencies: []\n", encoding="utf-8")
    print(f"Module '{module_name}' initialized. Next: edit constraint files and add eval-data.")

def main():
    parser = argparse.ArgumentParser(description="Initialize TAHP module")
    parser.add_argument("--module", required=True); parser.add_argument("--owner", required=True)
    args = parser.parse_args()
    if not re.match(r"^[a-z][a-z0-9-]*$", args.module): print("Error: Module name must be kebab-case"); sys.exit(1)
    init_module(args.module, args.owner)

if __name__ == "__main__": main()
