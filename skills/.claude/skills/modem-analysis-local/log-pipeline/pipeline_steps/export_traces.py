import argparse
import hashlib
import importlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
from contextlib import ExitStack
from copy import deepcopy
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    pass

_SHARED_DIR = Path(__file__).resolve().parent.parent / "_shared"
if str(_SHARED_DIR) not in sys.path:
    sys.path.insert(0, str(_SHARED_DIR))

from log_group_paths import resolve_group_rel_path  # noqa: E402
from trace_extensions import iter_qcom_trace_groups  # noqa: E402

TRACE_KEYS = ("ota", "ps", "system", "sip", "icd", "l1", "l2", "ps_raw")
MUX_EXTENSIONS = (".mux", ".muxz", ".muxraw")
EXPORT_ROOTS = {"elt_export_txt", "nlt_export_txt"}
DEFAULT_MANIFEST = {
    "issue_key": "",
    "workspace_root": "",
    "extraction": {
        "normalized_log_roots": [],
    },
    "downloads": {
        "download_root": "",
        "download_dirs": [],
    },
    "trace_exports": {
        "groups": [],
        "results": [],
    },
}


def configure_stdio():
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def merge_defaults(target, defaults):
    for key, value in defaults.items():
        if key not in target:
            target[key] = deepcopy(value)
        elif isinstance(value, dict) and isinstance(target.get(key), dict):
            merge_defaults(target[key], value)
    return target


def load_manifest(path):
    if not path or not os.path.exists(path):
        return deepcopy(DEFAULT_MANIFEST)
    with open(path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"manifest format is invalid: {path}")
    return merge_defaults(data, deepcopy(DEFAULT_MANIFEST))


def save_manifest(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    data = merge_defaults(data, deepcopy(DEFAULT_MANIFEST))
    data["_meta"] = {"updated_at": datetime.now().isoformat(timespec="seconds")}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def write_json(path, payload):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def sanitize_dir_component(name):
    name = "" if name is None else str(name)
    name = name.strip()
    if not name:
        return "unknown"
    for ch in '<>:"/\\|?*':
        name = name.replace(ch, "_")
    return name.strip("._") or "unknown"


def unique_paths(paths):
    seen = set()
    ordered = []
    for path in paths:
        if not path:
            continue
        abs_path = os.path.abspath(path)
        norm = os.path.normcase(abs_path)
        if norm in seen:
            continue
        seen.add(norm)
        ordered.append(abs_path)
    return ordered


def normalize_input_root(path):
    abs_path = os.path.abspath(path)
    if os.path.isfile(abs_path):
        return os.path.dirname(abs_path)
    return abs_path


def normalize_role_token(token):
    token = (token or "").strip().upper()
    if token.startswith("DUT"):
        return "DUT"
    if token.startswith("REF"):
        return "REF"
    return ""


def tree_has_explicit_role_dirs(base_dir):
    if not base_dir or not os.path.isdir(base_dir):
        return False
    for root, dirs, _files in os.walk(base_dir):
        if any(part.lower() in EXPORT_ROOTS for part in os.path.normpath(root).split(os.sep)):
            dirs[:] = []
            continue
        for name in dirs:
            if normalize_role_token(name):
                return True
    return False


def resolve_group_key(path, base_dir):
    """相对 normalized_root 的完整目录路径（POSIX），用于打包保留层级。"""
    return resolve_group_rel_path(path, base_dir)


def has_mux_files(path, recursive):
    if not os.path.isdir(path):
        return False
    if recursive:
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d.lower() not in EXPORT_ROOTS]
            for name in files:
                if name.lower().endswith(MUX_EXTENSIONS):
                    return True
        return False
    try:
        return any(
            entry.is_file() and entry.name.lower().endswith(MUX_EXTENSIONS)
            for entry in os.scandir(path)
        )
    except OSError:
        return False


def is_mdlog_source_name(name):
    lower = (name or "").lower()
    if lower == "modem":
        return True
    if lower == "mdlog1_config":
        return False
    return lower == "mdlog1" or lower.startswith("mdlog1_")


def discover_source_dirs(input_path):
    abs_input = os.path.abspath(input_path)
    if os.path.isfile(abs_input):
        if abs_input.lower().endswith(MUX_EXTENSIONS):
            return [os.path.dirname(abs_input)]
        return []

    if not os.path.isdir(abs_input):
        return []

    base_name = os.path.basename(abs_input).lower()
    if base_name in EXPORT_ROOTS:
        return []
    if is_mdlog_source_name(base_name):
        return [abs_input]

    discovered = []
    for root, dirs, _files in os.walk(abs_input):
        if any(part.lower() in EXPORT_ROOTS for part in os.path.normpath(root).split(os.sep)):
            dirs[:] = []
            continue
        dirs[:] = [d for d in dirs if d.lower() not in EXPORT_ROOTS]
        parent_name = os.path.basename(root).lower()
        for name in dirs:
            if not is_mdlog_source_name(name):
                continue
            if "mdlog1" in parent_name or parent_name in EXPORT_ROOTS:
                continue
            discovered.append(os.path.join(root, name))

    if discovered:
        return unique_paths(sorted(discovered))

    if has_mux_files(abs_input, recursive=True):
        return [abs_input]
    return []


def has_mace_env_dir(path, expected_markers):
    if not path or not os.path.isdir(path):
        return False
    if not os.path.isfile(os.path.join(path, "mace.py")):
        return False
    if expected_markers and any(os.path.exists(os.path.join(path, marker)) for marker in expected_markers):
        return True
    try:
        for name in os.listdir(path):
            lower = name.lower()
            if lower.startswith("libmace") and (
                lower.endswith(".pyd")
                or lower.endswith(".dll")
                or lower.endswith(".so")
                or lower.endswith(".dylib")
            ):
                return True
    except OSError:
        return False
    return False


def scan_for_tool_home(search_roots, expected_markers, max_depth=3, max_nodes=5000):
    queue = []
    seen = set()
    for root in search_roots:
        if root and os.path.isdir(root):
            queue.append((os.path.abspath(root), 0))

    visited = 0
    while queue and visited < max_nodes:
        current, depth = queue.pop(0)
        norm = os.path.normcase(current)
        if norm in seen:
            continue
        seen.add(norm)
        visited += 1

        try:
            if has_mace_env_dir(current, expected_markers):
                return current
            if depth >= max_depth:
                continue
            with os.scandir(current) as entries:
                for entry in entries:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    if has_mace_env_dir(entry.path, expected_markers):
                        return entry.path
                    queue.append((entry.path, depth + 1))
        except OSError:
            continue
    return None


def find_tool_home(runtime):
    runtime = runtime.lower()
    env_var = "ELT_HOME" if runtime == "elt" else "NLT_HOME"
    expected_markers = ["env_check.py", "ELT.exe"] if runtime == "elt" else ["env_check.py", "NLT.exe"]
    default_dirs = [fr"{drive}:\{runtime.upper()}" for drive in ("C", "D", "E")]

    env_home = os.environ.get(env_var)
    candidates = []
    if env_home:
        candidates.append(env_home)
    candidates.extend(default_dirs)

    for candidate in candidates:
        if has_mace_env_dir(candidate, expected_markers):
            return os.path.abspath(candidate)

    search_roots = []
    if env_home and os.path.isdir(env_home):
        search_roots.append(env_home)
    for drive in ("C", "D", "E"):
        root = f"{drive}:\\"
        if os.path.isdir(root):
            search_roots.append(root)
    
    # 对于 NLT，确保找到的目录包含 NLT.exe
    result = scan_for_tool_home(search_roots, expected_markers)
    if runtime == "nlt" and result:
        nlt_exe = os.path.join(result, "NLT.exe")
        if not os.path.isfile(nlt_exe):
            return None
    return result


def list_python_interpreters():
    try:
        result = subprocess.run(
            ["py", "-0p"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception:
        return []

    interpreters = []
    for raw_line in (result.stdout or "").splitlines():
        line = raw_line.strip()
        match = re.search(r"([A-Za-z]:\\.*python(?:w)?\.exe)", line, re.IGNORECASE)
        if not match:
            continue
        executable = match.group(1)
        version = line[: match.start()].replace("*", "").strip()
        interpreters.append({"version": version, "executable": executable})
    return interpreters


def parse_version_tag(text):
    match = re.search(r"(\d+)\.(\d+)", text or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def current_python_supported(runtime):
    if sys.maxsize <= 2**32:
        return False
    major = sys.version_info.major
    minor = sys.version_info.minor
    if major != 3:
        return False
    if runtime == "elt":
        return 7 <= minor <= 11
    return 7 <= minor <= 12


def embedded_python_for_runtime(runtime, tool_home=None):
    """ELT/NLT 自带 Python，已捆绑 mace，无需再装独立 Python 环境。"""
    runtime = runtime.lower()
    if tool_home is None:
        tool_home = find_tool_home(runtime)
    if not tool_home:
        return None
    if runtime == "elt":
        candidate = os.path.join(tool_home, "Utilities", "Python3", "EmbeddedPython.exe")
    else:
        candidate = os.path.join(tool_home, "Utilities", "Python3", "python.exe")
    if os.path.isfile(candidate):
        return os.path.abspath(candidate)
    return None


def choose_python(runtime):
    runtime = runtime.lower()
    override = os.environ.get("ELT_PYTHON" if runtime == "elt" else "NLT_PYTHON")
    if override and os.path.isfile(override):
        return os.path.abspath(override)

    tool_home = find_tool_home(runtime)
    embedded = embedded_python_for_runtime(runtime, tool_home)
    if embedded:
        return embedded

    if current_python_supported(runtime):
        return os.path.abspath(sys.executable)

    launcher_items = list_python_interpreters()
    preferences = [7, 11, 10, 9, 8] if runtime == "elt" else [12, 11, 10, 9, 8, 7]
    ranked = []
    for item in launcher_items:
        version = parse_version_tag(item.get("version"))
        if not version or version[0] != 3:
            continue
        minor = version[1]
        if runtime == "elt" and not (7 <= minor <= 11):
            continue
        if runtime == "nlt" and not (7 <= minor <= 12):
            continue
        try:
            rank = preferences.index(minor)
        except ValueError:
            continue
        ranked.append((rank, item["executable"]))
    if ranked:
        ranked.sort(key=lambda pair: pair[0])
        return os.path.abspath(ranked[0][1])

    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    if runtime == "elt":
        candidates.extend(
            [
                os.path.join(local_appdata, "Programs", "Python", "Python37", "python.exe"),
                os.path.join(local_appdata, "Programs", "Python", "Python311", "python.exe"),
                os.path.join(local_appdata, "Programs", "Python", "Python310", "python.exe"),
            ]
        )
        elt_home = find_tool_home("elt")
        if elt_home:
            emb = embedded_python_for_runtime("elt", elt_home)
            if emb:
                candidates.append(emb)
    else:
        candidates.extend(
            [
                os.path.join(local_appdata, "Programs", "Python", "Python312", "python.exe"),
                os.path.join(local_appdata, "Programs", "Python", "Python311", "python.exe"),
            ]
        )
        uv_root = os.path.join(appdata, "uv", "python")
        if os.path.isdir(uv_root):
            try:
                for name in sorted(os.listdir(uv_root), reverse=True):
                    lower = name.lower()
                    if "cpython-3.12" in lower:
                        candidates.append(os.path.join(uv_root, name, "python.exe"))
            except OSError:
                pass
        nlt_home = find_tool_home("nlt")
        if nlt_home:
            emb = embedded_python_for_runtime("nlt", nlt_home)
            if emb:
                candidates.append(emb)

    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return os.path.abspath(candidate)
    return None


def load_mace_module(tool_home):
    logger = logging.getLogger("elt-nlt-export")
    tool_home = os.path.abspath(tool_home)
    if tool_home not in sys.path:
        sys.path.insert(0, tool_home)

    dll_dirs = [tool_home, os.path.join(tool_home, "Utilities", "Python3")]
    dll_dirs = [path for path in dll_dirs if os.path.isdir(path)]
    if dll_dirs:
        prefix = os.pathsep.join(dll_dirs)
        os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")

    for modname in ("mace", "libmace3", "libmace27"):
        if modname in sys.modules:
            try:
                del sys.modules[modname]
            except Exception:
                pass

    try:
        if os.name == "nt" and sys.version_info >= (3, 8):
            with ExitStack() as stack:
                for path in dll_dirs:
                    try:
                        stack.enter_context(os.add_dll_directory(path))
                    except Exception:
                        continue
                return importlib.import_module("mace")
        return importlib.import_module("mace")
    except Exception as exc:
        logger.error(
            "failed to load mace from %s with python %s.%s: %s",
            tool_home,
            sys.version_info.major,
            sys.version_info.minor,
            exc,
        )
        raise


def open_log_file_with_fallback(mace_mod, source_input):
    try:
        return mace_mod.open_log_file(source_input)
    except Exception as original_error:
        error_text = str(original_error)
        if "Database not found" in error_text or "database" in error_text.lower():
            os.environ["MACE_IGNORE_DB_MISMATCH"] = "1"
            try:
                return mace_mod.open_log_file(source_input, ignore_db_mismatch=True)
            except TypeError:
                return mace_mod.open_log_file(source_input)
        os.environ["MACE_IGNORE_DB_MISMATCH"] = "1"
        try:
            return mace_mod.open_log_file(source_input, ignore_db_mismatch=True)
        except TypeError:
            return mace_mod.open_log_file(source_input)


def close_if_possible(obj):
    for attr in ("close", "release"):
        func = getattr(obj, attr, None)
        if callable(func):
            try:
                func()
            except Exception:
                pass


def maybe_short_path_for_windows(path, logger, label):
    def noop():
        return None

    if os.name != "nt":
        return path, noop

    abs_path = os.path.abspath(path)
    is_file = os.path.isfile(abs_path)
    base_dir = os.path.dirname(abs_path) if is_file else abs_path
    if not base_dir or not os.path.isdir(base_dir):
        return path, noop

    try:
        threshold = int(os.getenv("OSAI_LONG_PATH_THRESHOLD", "220"))
    except Exception:
        threshold = 220
    if threshold < 120:
        threshold = 120
    if len(base_dir) < threshold:
        return path, noop

    flag = (os.getenv("OSAI_ENABLE_PATH_JUNCTION") or "").strip().lower()
    if flag in {"0", "false", "no", "off"}:
        logger.warning("%s detected a long path but junction mapping is disabled: %s", label, base_dir)
        return path, noop

    root = (os.getenv("OSAI_JUNCTION_ROOT") or "").strip()
    if not root:
        drive = os.path.splitdrive(base_dir)[0]
        root = (drive + "\\_osai_junc") if drive else os.path.join(tempfile.gettempdir(), "_osai_junc")
    try:
        os.makedirs(root, exist_ok=True)
    except Exception:
        root = os.path.join(tempfile.gettempdir(), "_osai_junc")
        os.makedirs(root, exist_ok=True)

    seed = (base_dir + "|" + label + "|" + str(time.time())).encode("utf-8", errors="ignore")
    digest = hashlib.md5(seed).hexdigest()[:8]
    link_dir = os.path.join(root, f"j_{label.lower()}_{digest}_{uuid.uuid4().hex[:6]}")

    try:
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", link_dir, base_dir],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if result.returncode != 0 or not os.path.isdir(link_dir):
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            logger.warning("%s short-path junction creation failed: %s", label, output[:300])
            return path, noop
    except Exception as exc:
        logger.warning("%s short-path junction creation raised: %s", label, exc)
        return path, noop

    def cleanup():
        try:
            if os.path.isdir(link_dir):
                os.rmdir(link_dir)
        except Exception:
            try:
                subprocess.run(
                    ["cmd", "/c", "rmdir", "/s", "/q", link_dir],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            except Exception:
                pass

    new_path = os.path.join(link_dir, os.path.basename(abs_path)) if is_file else link_dir
    logger.info("%s is using a junction-mapped path: %s -> %s", label, new_path, abs_path)
    return new_path, cleanup


def iter_trace_groups(input_path):
    input_path = os.path.abspath(input_path)
    if os.path.isfile(input_path):
        return [(os.path.dirname(input_path), [input_path])]

    grouped = {}
    for root, dirs, files in os.walk(input_path):
        dirs[:] = [d for d in dirs if d.lower() not in EXPORT_ROOTS]
        paths = []
        for name in files:
            if name.lower().endswith(MUX_EXTENSIONS):
                paths.append(os.path.join(root, name))
        if paths:
            grouped[root] = sorted(paths)
    return sorted(grouped.items(), key=lambda item: item[0])


def open_source_for_group(group_dir, files):
    mux_like = [path for path in files if os.path.splitext(path)[1].lower() in (".mux", ".muxz")]
    muxraw_like = [path for path in files if os.path.splitext(path)[1].lower() == ".muxraw"]
    if len(mux_like) > 1 and not muxraw_like:
        return os.path.join(group_dir, "*.mux*")
    return files[0]


def find_database_file(group_dir):
    try:
        candidates = [
            os.path.join(group_dir, name)
            for name in sorted(os.listdir(group_dir))
            if name.lower().endswith(".edb")
        ]
    except OSError:
        return None
    return candidates[0] if candidates else None


def converter_input_spec(group_dir, files):
    if len(files) == 1:
        return files[0]
    return os.path.join(group_dir, "*.mux*")


def runtime_env(runtime, tool_home):
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    if runtime == "elt":
        env["ELT_HOME"] = tool_home
    else:
        env["NLT_HOME"] = tool_home
    prefix_parts = [tool_home]
    python_dir = os.path.join(tool_home, "Utilities", "Python3")
    if os.path.isdir(python_dir):
        prefix_parts.append(python_dir)
    env["PATH"] = os.pathsep.join(prefix_parts) + os.pathsep + env.get("PATH", "")
    return env


def run_external_converter(runtime, group_dir, files, output_elg):
    logger = logging.getLogger("elt-nlt-export")
    runtime = runtime.lower()
    logger.info(f"Finding {runtime} tool home")
    tool_home = find_tool_home(runtime)
    if not tool_home:
        env_name = "ELT_HOME" if runtime == "elt" else "NLT_HOME"
        raise RuntimeError(f"{runtime.upper()} runtime not found. Set {env_name}.")
    logger.info(f"Found {runtime} tool home: {tool_home}")

    input_spec = converter_input_spec(group_dir, files)
    database = find_database_file(group_dir)
    utilities_dir = os.path.join(tool_home, "Utilities")
    os.makedirs(os.path.dirname(os.path.abspath(output_elg)), exist_ok=True)

    if runtime == "elt":
        converter = os.path.join(utilities_dir, "MDLogMan.exe")
        if not os.path.isfile(converter):
            raise RuntimeError(f"MDLogMan.exe not found under {utilities_dir}")
        elt_exe = os.path.join(tool_home, "ELT.exe")
        command = [converter, "-i", input_spec, "-o", output_elg, "--verbose", "--dbchk-off"]
        if database:
            command.extend(["-db", database])
        if os.path.isfile(elt_exe):
            command.append(f"--elt={elt_exe}")
    else:
        converter = os.path.join(utilities_dir, "LogFileConverter.py")
        runtime_python = choose_python("nlt")
        if not runtime_python:
            raise RuntimeError("No compatible Python runtime was found for NLT conversion.")
        if not os.path.isfile(converter):
            raise RuntimeError(f"LogFileConverter.py not found under {utilities_dir}")
        command = [runtime_python, converter, "-i", input_spec, "-o", output_elg, "-dbchk-off"]
        if database:
            command.extend(["-db", database])

    logger.info(f"Running converter command: {command}")
    logger.info(f"Working directory: {utilities_dir}")
    # 增加超时时间到30分钟
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=runtime_env(runtime, tool_home),
        cwd=utilities_dir,
        check=False,
        timeout=1800,  # 10 minutes timeout
    )
    logger.info(f"Converter exit code: {result.returncode}")
    logger.info(f"Converter stdout: {result.stdout[:500]}...")
    logger.info(f"Converter stderr: {result.stderr[:500]}...")
    if result.returncode != 0 or not os.path.isfile(output_elg):
        stdout_tail = (result.stdout or "").strip()[-2000:]
        stderr_tail = (result.stderr or "").strip()[-2000:]
        raise RuntimeError(
            f"{runtime.upper()} converter failed for {group_dir} (exit={result.returncode}). "
            f"stdout_tail={stdout_tail!r} stderr_tail={stderr_tail!r}"
        )
    logger.info(f"Converter succeeded, output: {output_elg}")
    return os.path.abspath(output_elg)


def format_message_line(timestamp, message):
    return f"{timestamp} {message}\n"


_ICD_ENUM_CACHE = {}


def parse_enum_description(desc):
    enums = {}
    if not desc or not isinstance(desc, str):
        return enums
    pattern = r'Enum\s*\{([^}]+)\}'
    match = re.search(pattern, desc)
    if match:
        enum_str = match.group(1)
        for item in enum_str.split(','):
            if ':' in item:
                val, name = item.split(':', 1)
                try:
                    enums[int(val.strip())] = name.strip()
                except ValueError:
                    pass
    return enums


def load_icd_enum_mappings(tool_home):
    global _ICD_ENUM_CACHE
    if _ICD_ENUM_CACHE:
        return _ICD_ENUM_CACHE
    
    icd_json_paths = [
        os.path.join(tool_home, "System", "Icd", "AllICD.json"),
        os.path.join(tool_home, "Icd", "AllICD.json"),
    ]
    
    for icd_json_path in icd_json_paths:
        if os.path.isfile(icd_json_path):
            try:
                with open(icd_json_path, 'r', encoding='utf-8') as f:
                    _ICD_ENUM_CACHE = json.load(f)
                return _ICD_ENUM_CACHE
            except Exception:
                pass
    return {}


def get_icd_enum_mapping(icd_data, icd_name):
    if not icd_data or icd_name not in icd_data:
        return {}
    
    result = {}
    tables = icd_data[icd_name].get('table', {})
    
    for table_name, table_info in tables.items():
        if 'Data' not in table_info:
            continue
        for row_id, row_data in table_info['Data'].items():
            if isinstance(row_data, list) and len(row_data) >= 6:
                field_name = row_data[0]
                description = row_data[5]
                enums = parse_enum_description(description)
                if enums:
                    result[field_name] = enums
    
    return result


def decode_icd_with_enum(icd_name, icd_json_str, icd_db):
    try:
        data = json.loads(icd_json_str)
    except Exception:
        return None
    
    enum_mapping = get_icd_enum_mapping(icd_db, icd_name)
    
    result = {}
    for key, value in data.items():
        result[key] = {
            'value': value,
            # 'hex': hex(value) if isinstance(value, int) else None
        }
        if key in enum_mapping and isinstance(value, int):
            if value in enum_mapping[key]:
                result[key]['enum'] = enum_mapping[key][value]
    
    return result


def format_sip_line(timestamp, sip_info, fallback_message):
    if isinstance(sip_info, (dict, list)):
        info_text = json.dumps(sip_info, ensure_ascii=False)
    else:
        info_text = str(sip_info) if sip_info is not None else str(fallback_message)
    return f"{timestamp} {info_text}\n"


def format_item_detail(item, trace_name, icd_db=None):
    parts = []
    parts.append(f"[{trace_name.upper()}] {getattr(item, 'timestamp', '')}".strip())
    
    common_attrs = [
        # ("type", "type"),
        # ("index", "index"),
        # ("module_id", "module_id"),
        ("message_id", "message_id"),
        ("message", "message"),
        # ("device_time", "device_time"),
        # ("frame_num_2g", "frame_num_2g"),
        # ("frame_num_3g", "frame_num_3g"),
        # ("frame_num_4g", "frame_num_4g"),
        # ("global_id", "global_id"),
        ("direction", "direction"),
        # ("ota_message_type", "ota_message_type"),
    ]
    
    for attr_name, display_name in common_attrs:
        try:
            val = getattr(item, attr_name, None)
            if val is not None:
                if hasattr(val, 'name'):
                    val = f"{val.name}({val.value})" if hasattr(val, 'value') else val.name
                if attr_name == "message" and str(val).strip() == "Internal Processing":
                    continue
                parts.append(f"{display_name}: {val}".strip())
        except Exception as e:
            parts.append(f"{display_name}: <error: {e}>".strip())
    
    icd_name = getattr(item, 'icd_name', None)
    detail_attrs = [
        ("icd_data", "icd_data"),
        # ("icd_version", "icd_version"),
        # ("icd_name", "icd_name"),
        ("ota_json", "ota_json"),
        ("ota", "ota"),
        ("peer_xml", "peer_xml"),
        # ("peer", "peer"),
        # ("primitive", "primitive"),
        # ("prim", "prim"),
        # ("sip_info", "sip_info"),
        # ("system_time", "system_time"),
        # ("src_ip", "src_ip"),
        # ("dst_ip", "dst_ip"),
        # ("rat", "rat"),
        # ("protocol", "protocol"),
        # ("sip_msg_type", "sip_msg_type"),
        # ("sip_method", "sip_method"),
        # ("response_code", "response_code"),
        # ("transaction_id", "transaction_id"),
        # ("cseq", "cseq"),
        # ("mipc", "mipc"),
    ]
    
    for attr_name, display_name in detail_attrs:
        try:
            val = getattr(item, attr_name, None)
            if val is not None:
                if attr_name == "icd_data":
                    try:
                        if icd_db and icd_name:
                            decoded = decode_icd_with_enum(icd_name, val, icd_db)
                            if decoded:
                                formatted = json.dumps(decoded, ensure_ascii=False)
                                parts.append(f"{display_name}: {formatted}".strip())
                            else:
                                parsed = json.loads(val)
                                formatted = json.dumps(parsed, ensure_ascii=False)
                                parts.append(f"{display_name}: {formatted}".strip())
                        else:
                            parsed = json.loads(val)
                            formatted = json.dumps(parsed, ensure_ascii=False)
                            parts.append(f"{display_name}: {formatted}".strip())
                    except Exception:
                        parts.append(f"{display_name}: {val}".strip())
                elif attr_name == "ota_json":
                    try:
                        parsed = json.loads(val)
                        formatted = json.dumps(parsed, ensure_ascii=False)
                        parts.append(f"{display_name}: {formatted}".strip())
                    except Exception:
                        parts.append(f"{display_name}: {val}".strip())
                elif attr_name in ("peer", "primitive", "prim"):
                    try:
                        if hasattr(val, 'to_dict'):
                            val_dict = val.to_dict()
                            formatted = json.dumps(val_dict, ensure_ascii=False).strip()
                            parts.append(f"{display_name}: {formatted}".strip())
                        elif isinstance(val, dict):
                            formatted = json.dumps(val, ensure_ascii=False)
                            parts.append(f"{display_name}: {formatted}".strip())
                        else:
                            parts.append(f"{display_name}: {val}".strip())
                    except Exception as e:
                        parts.append(f"{display_name}: {val} (parse error: {e})".strip())
                elif attr_name in ("ota", "peer_xml", "sip_info"):
                    if isinstance(val, str):
                        single_line = ' '.join(val.split())
                        parts.append(f"{display_name}: {single_line}".strip())
                    else:
                        parts.append(f"{display_name}: {val}".strip())
                else:
                    parts.append(f"{display_name}: {val}".strip())
        except Exception as e:
            pass
    
    buffer_attrs = [
        ("prim_local_buffer", "prim_local_buffer"),
        ("prim_peer_buffer", "prim_peer_buffer"),
        ("ota_buffer", "ota_buffer"),
    ]
    
    for attr_name, display_name in buffer_attrs:
        try:
            val = getattr(item, attr_name, None)
            if val is not None and len(val) > 0:
                parts.append(f"{display_name}: <{len(val)} bytes>".strip())
        except Exception:
            pass
    
    return ' '.join(parts) + '\n'


def read_trace_lines_from_elg(mace_mod, elg_path, trace_name, icd_db=None):
    logfile = None
    itemset = None
    lines = []
    try:
        logfile = mace_mod.open_log_file(elg_path)
        itemset = mace_mod.create_itemset(logfile)
        if trace_name == "ota":
            itemset.subscribe_ota()
        elif trace_name == "ps":
            try:
                itemset.subscribe_ps(-1)
            except TypeError:
                itemset.subscribe_ps(protocol_id=-1)
        elif trace_name == "system":
            itemset.subscribe_sys()
        elif trace_name == "sip":
            try:
                itemset.subscribe_sip()
            except Exception:
                return []
        elif trace_name == "icd":
            itemset.subscribe_icd()
        elif trace_name == "l1":
            try:
                itemset.subscribe_l1()
            except TypeError:
                try:
                    itemset.subscribe_l1(-1)
                except Exception:
                    return []
            except Exception:
                return []
        elif trace_name == "l2":
            try:
                itemset.subscribe_l2()
            except TypeError:
                try:
                    itemset.subscribe_l2(-1)
                except Exception:
                    return []
            except Exception:
                return []
        elif trace_name == "ps_raw":
            itemset.subscribe_raw_string()
        else:
            raise ValueError(f"unsupported trace type: {trace_name}")

        for item in itemset:
            lines.append(format_item_detail(item, trace_name, icd_db))
        return lines
    finally:
        close_if_possible(itemset)
        close_if_possible(logfile)


def export_elg_to_txt(runtime, elg_path, output_dir):
    tool_home = find_tool_home(runtime)
    if not tool_home:
        env_name = "ELT_HOME" if runtime == "elt" else "NLT_HOME"
        raise RuntimeError(f"{runtime.upper()} runtime not found. Set {env_name}.")

    mace_mod = load_mace_module(tool_home)
    os.makedirs(output_dir, exist_ok=True)

    icd_db = load_icd_enum_mappings(tool_home)

    outputs = {key: os.path.join(output_dir, f"{key}.txt") for key in TRACE_KEYS}
    for key, path in outputs.items():
        lines = read_trace_lines_from_elg(mace_mod, elg_path, key, icd_db)
        with open(path, "w", encoding="utf-8", errors="replace") as f:
            if lines:
                f.writelines(lines)
            else:
                f.write("\n")
    return {key: os.path.realpath(path) for key, path in outputs.items()}


def run_worker(runtime, source_path, output_dir, group_source_dir):
    runtime = runtime.lower()
    source_path = os.path.abspath(source_path)
    output_dir = os.path.abspath(output_dir)
    group_source_dir = os.path.abspath(group_source_dir or os.path.dirname(source_path))
    outputs = export_elg_to_txt(runtime, source_path, output_dir)
    return {
        "success": True,
        "exporter": runtime.upper(),
        "output": [
            {
                "source_dir": group_source_dir,
                "exporter": runtime.upper(),
                "files": outputs,
            }
        ],
        "errors": [],
    }


def parse_json_payload(text):
    text = (text or "").strip()
    if not text:
        raise ValueError("empty worker output")
    try:
        return json.loads(text)
    except Exception:
        pass

    lines = text.splitlines()
    for index in range(len(lines)):
        candidate = "\n".join(lines[index:]).strip()
        if not candidate.startswith("{"):
            continue
        try:
            return json.loads(candidate)
        except Exception:
            continue
    raise ValueError(f"unable to parse worker output as JSON: {text[-500:]}")


def invoke_worker(runtime, source_path, output_dir, group_source_dir):
    logger = logging.getLogger("elt-nlt-export")
    interpreter = choose_python(runtime)
    if not interpreter:
        env_name = "ELT_PYTHON" if runtime == "elt" else "NLT_PYTHON"
        raise RuntimeError(f"no compatible Python interpreter was found for {runtime.upper()}. Set {env_name}.")

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    tool_home = find_tool_home(runtime)
    if tool_home:
        env["ELT_HOME" if runtime == "elt" else "NLT_HOME"] = tool_home

    command = [
        interpreter,
        os.path.abspath(__file__),
        "--runtime-worker",
        runtime,
        "--source",
        os.path.abspath(source_path),
        "--worker-output-dir",
        os.path.abspath(output_dir),
        "--worker-source-dir",
        os.path.abspath(group_source_dir),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    try:
        payload = parse_json_payload(result.stdout)
    except Exception as exc:
        stderr_tail = (result.stderr or "").strip()[-500:]
        stdout_tail = (result.stdout or "").strip()[-500:]
        raise RuntimeError(
            f"{runtime.upper()} worker output could not be parsed: {exc}. stdout_tail={stdout_tail!r} stderr_tail={stderr_tail!r}"
        )

    if result.stderr:
        logger.info("%s worker stderr: %s", runtime.upper(), result.stderr.strip()[-500:])
    if result.returncode != 0 and not payload.get("success"):
        logger.warning("%s worker exited with code %s", runtime.upper(), result.returncode)
    return payload


def export_with_preference(source_dir, prefer):
    logger = logging.getLogger("elt-nlt-export")
    errors = []
    
    trace_types = list(TRACE_KEYS)

    existing_export_dirs = [
        os.path.join(source_dir, "elt_export_txt"),
        os.path.join(source_dir, "elt_export_txt2"),
        os.path.join(source_dir, "nlt_export_txt")
    ]
    
    for export_dir in existing_export_dirs:
        if os.path.isdir(export_dir):
            required_files = [f"{key}.txt" for key in trace_types]
            existing_files = [f for f in required_files if os.path.isfile(os.path.join(export_dir, f))]
            
            if len(existing_files) >= min(3, len(trace_types)):
                logger.info(f"Found existing export directory: {export_dir}")
                logger.info(f"Existing files: {existing_files}")
                
                exported = [{
                    "source_dir": source_dir,
                    "exporter": "ELT" if "elt" in export_dir.lower() else "NLT",
                    "files": {key: os.path.join(export_dir, f"{key}.txt") for key in trace_types}
                }]
                logger.info("Using existing export files instead of reprocessing")
                return exported, errors
    
    ordered_runtimes = ["elt", "nlt"] if prefer == "auto" else [prefer, "nlt" if prefer == "elt" else "elt"]
    logger.info(f"Exporting with preference: {prefer}, ordered runtimes: {ordered_runtimes}")
    for runtime in ordered_runtimes:
        logger.info(f"Trying runtime: {runtime}")
        export_root = os.path.join(source_dir, f"{runtime}_export_txt")
        logger.info(f"Export root: {export_root}")
        exported = []
        runtime_errors = []
        groups = iter_trace_groups(source_dir)
        logger.info(f"Found {len(list(groups))} trace groups")
        groups = iter_trace_groups(source_dir)
        for group_dir, files in groups:
            logger.info(f"Processing group: {group_dir}, files: {files}")
            rel = os.path.relpath(group_dir, source_dir) if os.path.isdir(source_dir) else "."
            output_dir = export_root if rel == "." else os.path.join(export_root, rel)
            os.makedirs(output_dir, exist_ok=True)
            elg_name = f"{sanitize_dir_component(os.path.basename(group_dir))}.{runtime}.elg"
            elg_path = os.path.join(output_dir, elg_name)
            logger.info(f"Output ELG path: {elg_path}")
            try:
                logger.info(f"Running external converter for {runtime}")
                converted_elg = run_external_converter(runtime, group_dir, files, elg_path)
                logger.info(f"Converted ELG: {converted_elg}")
                logger.info(f"Invoking worker for {runtime}")
                payload = invoke_worker(runtime, converted_elg, output_dir, group_dir)
                logger.info(f"Worker payload: {json.dumps(payload, ensure_ascii=False, indent=2)}")
                worker_errors = payload.get("errors") or []
                for item in worker_errors:
                    item = dict(item)
                    item.setdefault("exporter", payload.get("exporter", runtime.upper()))
                    runtime_errors.append(item)
                output = payload.get("output") or []
                if payload.get("success") and isinstance(output, list):
                    logger.info(f"Successfully exported {len(output)} items")
                    exported.extend(output)
                elif payload.get("error"):
                    error_msg = payload["error"]
                    logger.error(f"Worker error: {error_msg}")
                    runtime_errors.append(
                        {
                            "source_dir": os.path.abspath(group_dir),
                            "exporter": payload.get("exporter", runtime.upper()),
                            "error": error_msg,
                        }
                    )
            except Exception as exc:
                error_msg = str(exc)
                logger.error(f"Exception during export: {error_msg}")
                logger.error(traceback.format_exc())
                runtime_errors.append({"source_dir": os.path.abspath(group_dir), "exporter": runtime.upper(), "error": error_msg})

        errors.extend(runtime_errors)
        if exported:
            logger.info(f"Successfully exported with {runtime}")
            return exported, errors
    logger.info("No runtimes succeeded")
    return [], errors


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export .mux/.muxz modem traces into ota.txt, ps.txt, system.txt, and sip.txt via ELT or NLT."
    )
    parser.add_argument("--manifest", help="manifest JSON file path")
    parser.add_argument(
        "--input-dir",
        action="append",
        dest="input_dirs",
        help="normalized root, mdlog1/modem directory, or a single .mux/.muxz/.muxraw file; may be repeated",
    )
    parser.add_argument("--prefer", choices=("auto", "elt", "nlt"), default="auto", help="runtime preference order")
    parser.add_argument("--output", help="optional standalone JSON output path")
    parser.add_argument("--runtime-worker", choices=("elt", "nlt"), help=argparse.SUPPRESS)
    parser.add_argument("--source", help=argparse.SUPPRESS)
    parser.add_argument("--worker-output-dir", help=argparse.SUPPRESS)
    parser.add_argument("--worker-source-dir", help=argparse.SUPPRESS)
    return parser.parse_args()


QCOM_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qcom")
QCOM_EXPORT_ROOT_NAME = "qcom_export"
DEFAULT_QUTS_PYTHON_PATH = r"C:\Program Files\Qualcomm\QUTS\Support\python"
_qcom_export_module = None


def qcom_export_skipped() -> bool:
    return os.environ.get("QCOM_SKIP_EXPORT", "").strip().lower() in ("1", "true", "yes")


def qcom_keep_raw_in_package() -> bool:
    return os.environ.get("QCOM_KEEP_RAW_IN_PACKAGE", "").strip().lower() in ("1", "true", "yes")


def find_quts_support_python():
    mod = load_qcom_export_module()
    return mod.resolve_quts_python_path()


def load_qcom_export_module():
    global _qcom_export_module
    if _qcom_export_module is not None:
        return _qcom_export_module
    if QCOM_DIR not in sys.path:
        sys.path.insert(0, QCOM_DIR)
    import export_modem_log as mod  # noqa: WPS433 — pipeline_steps/qcom

    _qcom_export_module = mod
    return mod


def build_qcom_export_options_from_env(mod):
    type_list = []
    id_list = []
    export_type = (os.environ.get("QCOM_EXPORT_TYPE") or "").strip()
    export_id = (os.environ.get("QCOM_EXPORT_ID") or "").strip()
    if export_type:
        type_list.append(export_type)
    if export_id:
        id_list.append(export_id)
    type_id_pairs = mod.parse_type_id_pairs(type_list or None, id_list or None)
    search_text = (os.environ.get("QCOM_EXPORT_SEARCH") or "").strip() or None
    use_regex = os.environ.get("QCOM_EXPORT_REGEX", "").strip().lower() in ("1", "true", "yes")
    if use_regex and not search_text:
        raise ValueError("QCOM_EXPORT_REGEX=1 时必须设置 QCOM_EXPORT_SEARCH")
    return type_id_pairs, search_text, use_regex


def list_cached_qcom_export_txts(export_root, source_files):
    """qcom_export/ 下已有、且与源 trace 文件名前缀匹配的 .txt（用于跳过重复 QUTS 导出）。"""
    if not os.path.isdir(export_root):
        return []
    stems = {os.path.splitext(os.path.basename(f))[0] for f in source_files}
    if not stems:
        return []

    cached = []
    for name in sorted(os.listdir(export_root)):
        if not name.lower().endswith(".txt"):
            continue
        path = os.path.join(export_root, name)
        if not os.path.isfile(path) or os.path.getsize(path) <= 64:
            continue
        if any(name.startswith(stem) for stem in stems):
            cached.append(os.path.abspath(path))

    if not cached:
        return []
    for stem in stems:
        if not any(os.path.basename(p).startswith(stem) for p in cached):
            return []
    return cached


def invoke_qcom_export_inprocess(group_dir, export_root):
    """进程内调用 export_modem_log.run_batch_export（不启子进程）。"""
    logger = logging.getLogger("elt-nlt-export")
    quts_path = find_quts_support_python()
    if not quts_path:
        raise RuntimeError(
            "QUTS Support/python 未找到，请安装 QUTS 或设置 QUTS_PYTHON_PATH"
        )

    mod = load_qcom_export_module()
    type_id_pairs, search_text, use_regex = build_qcom_export_options_from_env(mod)
    logger.info(
        "QCOM in-process export: group=%s output=%s types=%s search=%s",
        group_dir,
        export_root,
        type_id_pairs,
        search_text or "",
    )
    return mod.run_batch_export(
        os.path.abspath(group_dir),
        os.path.abspath(export_root),
        type_id_pairs=type_id_pairs,
        search_text=search_text,
        use_regex=use_regex,
        quts_python_path=quts_path,
    )


def export_qcom_group(group_dir, files, normalized_root):
    """
    对单个 QCOM 分组执行 QUTS 导出（或仅登记原始 trace）。
    返回 (group_dict, errors)。
    """
    logger = logging.getLogger("elt-nlt-export")
    errors: list[dict] = []
    group_dir = os.path.abspath(group_dir)
    export_root = os.path.join(group_dir, QCOM_EXPORT_ROOT_NAME)

    qmdl2_files = sorted(p for p in files if p.lower().endswith(".qmdl2"))
    qdss_files = sorted(p for p in files if p.lower().endswith(".qdss"))
    source_files = qmdl2_files + qdss_files
    file_map: dict = {}

    if not qcom_export_skipped():
        cached_txt = list_cached_qcom_export_txts(export_root, source_files)
        if cached_txt:
            logger.info("Using existing QCOM export (%d txt): %s", len(cached_txt), export_root)
            file_map["qcom_txt"] = cached_txt
        else:
            try:
                payload = invoke_qcom_export_inprocess(group_dir, export_root)
                txt_files = sorted(
                    os.path.abspath(p)
                    for p in (payload.get("txt_files") or [])
                    if p and os.path.isfile(p)
                )
                for err in payload.get("errors") or []:
                    errors.append({"source_dir": group_dir, "error": err, "trace_kind": "qcom"})
                if txt_files:
                    file_map["qcom_txt"] = txt_files
                elif not payload.get("success"):
                    errors.append(
                        {
                            "source_dir": group_dir,
                            "error": "QCOM QUTS 导出未产生 txt",
                            "trace_kind": "qcom",
                        }
                    )
            except Exception as exc:
                logger.exception("QCOM export failed for %s", group_dir)
                errors.append({"source_dir": group_dir, "error": str(exc), "trace_kind": "qcom"})

    if qcom_keep_raw_in_package() or not file_map.get("qcom_txt"):
        if qmdl2_files:
            file_map["qmdl2"] = qmdl2_files
        if qdss_files:
            file_map["qdss"] = qdss_files

    if not file_map:
        return None, errors

    group = {
        "normalized_root": normalized_root,
        "source_dir": group_dir,
        "group_key": resolve_group_key(group_dir, normalized_root),
        "exporter": "QCOM",
        "trace_kind": "qcom",
        "files": file_map,
    }
    logger.info(
        "QCOM group %s: qmdl2=%d qdss=%d exported_txt=%d",
        group_dir,
        len(qmdl2_files),
        len(qdss_files),
        len(file_map.get("qcom_txt") or []),
    )
    return group, errors


def export_qcom_traces_for_input(abs_input, normalized_root):
    """
    QCOM：进程内调用 pipeline_steps/qcom/export_modem_log.run_batch_export（QUTS）导出 txt，
    并写入 trace_exports.groups（与 ELT/NLT 并列，不改动 MTK 路径）。
    返回 (exported_count, groups, errors)。
    """
    logger = logging.getLogger("elt-nlt-export")
    groups = []
    errors = []
    exported_count = 0

    qcom_groups = iter_qcom_trace_groups(abs_input)
    if not qcom_groups:
        return 0, [], []

    logger.info("QCOM trace groups under %s: %d", abs_input, len(qcom_groups))
    for group_dir, files in qcom_groups:
        group, group_errors = export_qcom_group(group_dir, files, normalized_root)
        errors.extend(group_errors)
        if group:
            groups.append(group)
            exported_count += 1

    return exported_count, groups, errors


def export_all_traces(manifest_path):
    """
    导出所有 trace 文件（供 pipeline 调用）
    
    Args:
        manifest_path: manifest 文件路径
    
    Returns:
        dict: 导出结果
    """
    configure_stdio()
    logger = logging.getLogger("elt-nlt-export")
    logger.info("Starting export traces")
    
    manifest = load_manifest(manifest_path)
    input_roots = list(manifest.get("extraction", {}).get("normalized_log_roots") or [])
    if not input_roots:
        raise ValueError("No input provided. manifest.extraction.normalized_log_roots is empty.")
    
    normalized_roots = []
    groups = []
    results = []
    
    for raw_input in input_roots:
        abs_input = os.path.abspath(raw_input)
        logger.info(f"Processing input: {abs_input}")
        normalized_root = normalize_input_root(abs_input)
        normalized_roots.append(normalized_root)
        
        item = {
            "input_root": abs_input,
            "success": False,
            "exported_count": 0,
            "mdlog_dirs": [],
            "errors": [],
        }
        
        if not os.path.exists(abs_input):
            error_msg = f"path does not exist: {abs_input}"
            logger.error(error_msg)
            item["errors"].append({"source_dir": abs_input, "error": error_msg})
            results.append(item)
            continue
        
        source_dirs = discover_source_dirs(abs_input)
        logger.info(f"Discovered source dirs: {source_dirs}")
        item["mdlog_dirs"] = source_dirs

        exported_count = 0
        if source_dirs:
            for source_dir in source_dirs:
                logger.info(f"Processing source dir: {source_dir}")
                output, source_errors = export_with_preference(source_dir, prefer="elt")
                item["errors"].extend(source_errors)
                for error in source_errors:
                    logger.error(f"Export error: {error}")
                for exported in output:
                    groups.append(
                        {
                            "normalized_root": normalized_root,
                            "source_dir": exported.get("source_dir") or os.path.abspath(source_dir),
                            "group_key": resolve_group_key(exported.get("source_dir") or source_dir, normalized_root),
                            "exporter": exported.get("exporter") or "",
                            "files": exported.get("files") or {},
                        }
                    )
                exported_count += len(output)
                logger.info(f"Exported {len(output)} items from {source_dir}")
        else:
            error_msg = "no mdlog1/modem/.muxz source found"
            logger.info("%s (将继续尝试 QCOM .qmdl2/.qdss)", error_msg)
            item["errors"].append({"source_dir": abs_input, "error": error_msg, "trace_kind": "mtk"})

        qcom_count, qcom_groups, qcom_errors = export_qcom_traces_for_input(abs_input, normalized_root)
        groups.extend(qcom_groups)
        item["errors"].extend(qcom_errors)
        exported_count += qcom_count
        item["qcom_exported_count"] = qcom_count

        if not source_dirs and exported_count == 0:
            results.append(item)
            continue

        item["success"] = exported_count > 0
        item["exported_count"] = exported_count
        logger.info(f"Input {abs_input}: success={item['success']}, exported_count={exported_count}")
        results.append(item)
    
    normalized_roots = unique_paths(normalized_roots)
    
    return {
        "normalized_log_roots": normalized_roots,
        "groups": groups,
        "results": results,
    }


def main():
    configure_stdio()
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logger = logging.getLogger("elt-nlt-export")
    logger.info("Starting export traces script")
    logger.info(f"Input directories: {args.input_dirs}")

    if args.runtime_worker:
        try:
            payload = run_worker(args.runtime_worker, args.source, args.worker_output_dir, args.worker_source_dir)
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            return 0 if payload.get("success") else 1
        except Exception as exc:
            payload = {
                "success": False,
                "exporter": args.runtime_worker.upper(),
                "output": [],
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
            print(json.dumps(payload, ensure_ascii=False), flush=True)
            return 1

    manifest = load_manifest(args.manifest)
    input_roots = list(args.input_dirs or manifest.get("extraction", {}).get("normalized_log_roots") or [])
    if not input_roots:
        raise SystemExit("No input provided. Use --input-dir or manifest.extraction.normalized_log_roots.")

    normalized_roots = []
    groups = []
    results = []

    for raw_input in input_roots:
        abs_input = os.path.abspath(raw_input)
        logger.info(f"Processing input: {abs_input}")
        normalized_root = normalize_input_root(abs_input)
        normalized_roots.append(normalized_root)

        item = {
            "input_root": abs_input,
            "success": False,
            "exported_count": 0,
            "mdlog_dirs": [],
            "errors": [],
        }

        if not os.path.exists(abs_input):
            error_msg = f"path does not exist: {abs_input}"
            logger.error(error_msg)
            item["errors"].append({"source_dir": abs_input, "error": error_msg})
            results.append(item)
            continue

        source_dirs = discover_source_dirs(abs_input)
        logger.info(f"Discovered source dirs: {source_dirs}")
        item["mdlog_dirs"] = source_dirs

        exported_count = 0
        if source_dirs:
            for source_dir in source_dirs:
                logger.info(f"Processing source dir: {source_dir}")
                output, source_errors = export_with_preference(source_dir, args.prefer)
                item["errors"].extend(source_errors)
                for error in source_errors:
                    logger.error(f"Export error: {error}")
                for exported in output:
                    groups.append(
                        {
                            "normalized_root": normalized_root,
                            "source_dir": exported.get("source_dir") or os.path.abspath(source_dir),
                            "group_key": resolve_group_key(exported.get("source_dir") or source_dir, normalized_root),
                            "exporter": exported.get("exporter") or "",
                            "files": exported.get("files") or {},
                        }
                    )
                exported_count += len(output)
                logger.info(f"Exported {len(output)} items from {source_dir}")
        else:
            error_msg = "no mdlog1/modem/.muxz source found"
            logger.info("%s (将继续尝试 QCOM .qmdl2/.qdss)", error_msg)
            item["errors"].append({"source_dir": abs_input, "error": error_msg, "trace_kind": "mtk"})

        qcom_count, qcom_groups, qcom_errors = export_qcom_traces_for_input(abs_input, normalized_root)
        groups.extend(qcom_groups)
        item["errors"].extend(qcom_errors)
        exported_count += qcom_count
        item["qcom_exported_count"] = qcom_count

        if not source_dirs and exported_count == 0:
            results.append(item)
            continue

        item["success"] = exported_count > 0
        item["exported_count"] = exported_count
        logger.info(f"Input {abs_input}: success={item['success']}, exported_count={exported_count}")
        results.append(item)

    normalized_roots = unique_paths(normalized_roots)
    manifest["extraction"]["normalized_log_roots"] = normalized_roots
    manifest["trace_exports"]["groups"] = groups
    manifest["trace_exports"]["results"] = results

    payload = {
        "normalized_log_roots": normalized_roots,
        "groups": groups,
        "results": results,
    }
    logger.info(f"Final results: {json.dumps(payload, ensure_ascii=False, indent=2)}")
    if args.manifest:
        save_manifest(args.manifest, manifest)
    if args.output:
        write_json(args.output, payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    success = any(item.get("success") for item in results)
    logger.info(f"Script completed with success={success}")
    # 即使没有成功导出任何 trace，也返回 0（不阻断后续分析）
    # 因为某些日志（如 AEE 异常日志）可能本身就没有 modem trace
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
