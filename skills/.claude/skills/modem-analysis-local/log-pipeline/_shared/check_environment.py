import argparse
import importlib
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


PYTHON_PACKAGES = {
    "jira": "jira-issue-fetch,jira-comment-poster",
    "pygerrit2": "fetch_mddb_for_logs (Gerrit MDDB)",
    "playwright": "box-log-download",
}


def check_python_packages():
    results = []
    for module_name, skills in PYTHON_PACKAGES.items():
        try:
            importlib.import_module(module_name)
            ok = True
            detail = "installed"
        except Exception as e:
            ok = False
            detail = str(e)
        results.append(
            {
                "name": module_name,
                "skills": skills,
                "ok": ok,
                "detail": detail,
            }
        )
    return results


def find_browser():
    candidates = [
        os.environ.get("CHROME_BINARY"),
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        shutil.which("msedge"),
        shutil.which("msedge.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def find_playwright_chromium():
    root = Path.home() / "AppData" / "Local" / "ms-playwright"
    if not root.is_dir():
        return None
    for child in sorted(root.iterdir()):
        if child.name.startswith("chromium-") and child.is_dir():
            return str(child)
    return None


def find_7z():
    candidates = [
        os.environ.get("SEVEN_ZIP_EXE"),
        shutil.which("7z"),
        shutil.which("7z.exe"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        r"C:\Program Files\NanaZip\7z.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    return None


def has_mace_env_dir(path):
    path = Path(path)
    if not path.is_dir():
        return False
    if not (path / "mace.py").is_file():
        return False
    marker_names = {"env_check.py", "ELT.exe", "NLT.exe"}
    if any((path / marker).exists() for marker in marker_names):
        return True
    return any(child.name.lower().startswith("libmace") for child in path.iterdir())


def find_tool_home(env_var, fallback_dirs):
    env_home = os.environ.get(env_var)
    if env_home and has_mace_env_dir(env_home):
        return env_home
    for path in fallback_dirs:
        if has_mace_env_dir(path):
            return path
    return None


def list_python_interpreters():
    interpreters = []
    try:
        result = subprocess.run(
            ["py", "-0p"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            line = line.strip()
            if "C:\\" not in line and ":\\" not in line:
                continue
            if "*" in line:
                line = line.replace("*", "")
            parts = line.split()
            version = ""
            executable = ""
            for part in parts:
                if part.startswith("-V:") or part.startswith("-"):
                    version = part
                elif ":\\" in part:
                    executable = part
            if executable:
                interpreters.append({"version": version, "executable": executable})
    except Exception:
        pass
    return interpreters


def find_python_version(prefixes):
    prefixes = tuple(prefixes)
    for item in list_python_interpreters():
        if any(prefix in item["version"] for prefix in prefixes):
            return item["executable"]
    return None


def main():
    parser = argparse.ArgumentParser(description="Check Python and external runtime dependencies for the modem skills.")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of a human-readable summary.")
    args = parser.parse_args()

    report = {
        "python_packages": check_python_packages(),
        "external_tools": [
            {
                "name": "playwright_chromium",
                "skills": "box-log-download",
                "ok": bool(find_playwright_chromium()),
                "detail": find_playwright_chromium() or "not found",
            },
            {
                "name": "chrome_or_edge_fallback",
                "skills": "box-log-download",
                "ok": bool(find_browser()),
                "detail": find_browser() or "not found",
            },
            {
                "name": "7z",
                "skills": "archive-recursive-extract",
                "ok": bool(find_7z()),
                "detail": find_7z() or "optional for rar/7z only; not found",
            },
            {
                "name": "ELT_HOME",
                "skills": "elt-nlt-export",
                "ok": bool(find_tool_home("ELT_HOME", [r"C:\ELT", r"D:\ELT", r"E:\ELT"])),
                "detail": find_tool_home("ELT_HOME", [r"C:\ELT", r"D:\ELT", r"E:\ELT"]) or "not found",
            },
            {
                "name": "python3.7",
                "skills": "elt-nlt-export (ELT path)",
                "ok": bool(find_python_version(["3.7"])),
                "detail": find_python_version(["3.7"]) or "not found",
            },
            {
                "name": "NLT_HOME",
                "skills": "elt-nlt-export",
                "ok": bool(find_tool_home("NLT_HOME", [r"C:\NLT", r"D:\NLT", r"E:\NLT"])),
                "detail": find_tool_home("NLT_HOME", [r"C:\NLT", r"D:\NLT", r"E:\NLT"]) or "not found",
            },
            {
                "name": "python3.12",
                "skills": "elt-nlt-export (NLT path)",
                "ok": bool(find_python_version(["3.12", "Astral/CPython3.12"])),
                "detail": find_python_version(["3.12", "Astral/CPython3.12"]) or "not found",
            },
        ],
    }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    logger.info("Python packages:")
    for item in report["python_packages"]:
        status = "OK" if item["ok"] else "MISSING"
        logger.info(f"- [{status}] {item['name']} ({item['skills']}): {item['detail']}")

    logger.info("\nExternal tools:")
    for item in report["external_tools"]:
        status = "OK" if item["ok"] else "MISSING"
        logger.info(f"- [{status}] {item['name']} ({item['skills']}): {item['detail']}")


if __name__ == "__main__":
    main()
