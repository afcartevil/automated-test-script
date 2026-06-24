import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path
import shutil

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def collect_requirements(skills_root, skill_names=None):
    requirements = []
    requirement_files = []
    selected = set(skill_names or [])

    for req_file in sorted(skills_root.glob("*/requirements.txt")):
        skill_name = req_file.parent.name
        if selected and skill_name not in selected:
            continue
        requirement_files.append(req_file)
        for line in req_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line not in requirements:
                requirements.append(line)
    return requirements, requirement_files


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
            return child
    return None


def main():
    parser = argparse.ArgumentParser(description="Install Python dependencies for one or more modem skills.")
    parser.add_argument(
        "--skills-root",
        default=str(Path(__file__).resolve().parent.parent),
        help="Root directory that contains the skill folders.",
    )
    parser.add_argument(
        "--skill",
        action="append",
        dest="skills",
        help="Install only the named skill. Repeat for multiple skills.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only print the resolved requirements instead of installing them.",
    )
    args = parser.parse_args()

    skills_root = Path(args.skills_root).resolve()
    requirements, requirement_files = collect_requirements(skills_root, args.skills)
    if not requirement_files:
        logger.error("No matching requirements.txt files were found.")
        sys.exit(1)

    logger.info("Requirement files:")
    for req_file in requirement_files:
        logger.info(f"- {req_file}")

    if not requirements:
        logger.info("No Python packages are required for the selected skills.")
        return

    logger.info("Packages:")
    for item in requirements:
        logger.info(f"- {item}")

    if args.dry_run:
        return

    cmd = [sys.executable, "-m", "pip", "install", *requirements]
    subprocess.run(cmd, check=True)

    if "playwright" in requirements:
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except subprocess.CalledProcessError:
            existing_browser = find_playwright_chromium() or find_browser()
            if existing_browser:
                logger.warning(
                    f"Playwright Chromium download failed, but an existing browser/runtime was found: {existing_browser}"
                )
                logger.warning("Continuing with the existing browser fallback.")
                return
            raise


if __name__ == "__main__":
    main()
