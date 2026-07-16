#!/usr/bin/env python3
"""Capture Android Perfetto trace via adb."""

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
CONFIG_DIR = SCRIPT_DIR.parent / "configs"
DEFAULT_CONFIG = CONFIG_DIR / "default_config.txt"


def load_config(config_path=None):
    """Load perfetto config template from file."""
    if config_path is None:
        config_path = DEFAULT_CONFIG

    if not os.path.exists(config_path):
        print(f"Config file not found: {config_path}", file=sys.stderr)
        sys.exit(1)

    with open(config_path, 'r') as f:
        return f.read()


def add_atrace_categories(config, categories):
    """Add additional atrace categories to the config."""
    if not categories:
        return config

    lines = [f'      atrace_categories: "{cat}"' for cat in categories]
    insert = '\n'.join(lines)
    new_config = config.replace(
        '      atrace_apps: "*"',
        insert + '\n      atrace_apps: "*"'
    )
    if new_config == config:
        print("Warning: atrace_apps not found in config, categories not injected", file=sys.stderr)
    return new_config



def run_adb(args, check=True):
    cmd = ["adb"] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"adb error: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    return result


def calculate_buffer_size(duration_secs):
    """Calculate appropriate buffer size based on capture duration.
    
    Rule of thumb:
    - ~5-10 MB per second for comprehensive tracing
    - Minimum 64 MB, maximum 512 MB
    """
    # Estimate ~8MB per second for comprehensive tracing
    estimated_mb = duration_secs * 8
    
    # Clamp between 64MB and 512MB
    buffer_mb = max(64, min(512, estimated_mb))
    
    # Convert to KB (perfetto uses KB)
    buffer_kb = buffer_mb * 1024
    
    return buffer_kb


def check_environment(output_file):
    """Check if the environment is ready for trace capture."""
    # Check if adb is available
    try:
        result = subprocess.run(["adb", "version"], capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print("Error: adb is not installed or not in PATH", file=sys.stderr)
            sys.exit(1)
    except FileNotFoundError:
        print("Error: adb command not found. Please install Android SDK Platform Tools.", file=sys.stderr)
        sys.exit(1)
    except subprocess.TimeoutExpired:
        print("Error: adb command timed out", file=sys.stderr)
        sys.exit(1)
    
    # Check if device is connected
    result = run_adb(["devices"], check=False)
    devices = [line for line in result.stdout.splitlines() if '\tdevice' in line]
    if not devices:
        print("Error: No Android device connected. Please connect a device via USB or use 'adb connect'.", file=sys.stderr)
        sys.exit(1)
    
    print(f"✓ Device connected: {devices[0].split()[0]}")
    
    # Check for stale perfetto/simpleperf processes
    try:
        stale_check = subprocess.run(
            ["adb", "shell", "ps -A | grep -E '(perfetto|simpleperf|traced)' | grep -v grep"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if stale_check.stdout.strip():
            print("⚠ Stale tracing processes detected. If capture fails, run:")
            print("  adb shell pkill -9 simpleperf")
            print("  adb shell pkill -9 perfetto")
            print("  adb shell pkill -9 traced")
            print("  adb shell pkill -9 traced_probes")
            print("  sleep 2")
    except Exception:
        pass  # Process check is optional, don't fail if it doesn't work
    
    # Check SELinux status and warn if enforcing
    try:
        selinux_result = subprocess.run(
            ["adb", "shell", "getenforce"],
            capture_output=True,
            text=True,
            timeout=5
        )
        selinux_status = selinux_result.stdout.strip()
        if selinux_status == "Enforcing":
            print("ℹ SELinux is Enforcing. The streaming capture path does NOT need "
                  "root/setenforce and works on user builds.")
            print("  If the (fallback) on-device file path is needed on a rootable "
                  "build, you may run: adb root && adb shell setenforce 0")
    except Exception:
        pass  # SELinux check is optional, don't fail if it doesn't work
    
    # Check if output directory exists and is writable
    output_dir = os.path.dirname(os.path.abspath(output_file))
    if not os.path.exists(output_dir):
        print(f"Error: Output directory does not exist: {output_dir}", file=sys.stderr)
        sys.exit(1)
    if not os.access(output_dir, os.W_OK):
        print(f"Error: Output directory is not writable: {output_dir}", file=sys.stderr)
        sys.exit(1)
    
    return True


def get_package_dir():
    """Skill package directory (same dir as scripts/, SKILL.md)."""
    return Path(__file__).resolve().parent.parent


def resolve_output_path(output_arg=None):
    """Always return a unique path under the package dir so every capture is kept.

    - No -o: package_dir/trace_<timestamp>.perfetto-trace
    - -o dir:  <dir>/trace_<timestamp>.perfetto-trace
    - -o file: use it if missing; if exists, insert timestamp before suffix
    """
    package_dir = get_package_dir()
    timestamp = time.strftime("%Y%m%d_%H%M%S")

    if output_arg is None:
        return str(package_dir / f"trace_{timestamp}.perfetto-trace")

    path = Path(output_arg).expanduser()
    if not path.is_absolute():
        path = package_dir / path

    if path.is_dir():
        return str(path / f"trace_{timestamp}.perfetto-trace")

    if not path.suffix:
        path.mkdir(parents=True, exist_ok=True)
        return str(path / f"trace_{timestamp}.perfetto-trace")

    if path.exists():
        path = path.with_name(f"{path.stem}_{timestamp}{path.suffix}")

    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


def get_build_type():
    """Return (build_type, is_rootable) for the connected device."""
    result = run_adb(["shell", "getprop", "ro.build.type"], check=False)
    build_type = result.stdout.strip()
    dbg = run_adb(["shell", "getprop", "ro.debuggable"], check=False).stdout.strip()
    is_rootable = build_type in ("userdebug", "eng") or dbg == "1"
    return build_type, is_rootable


def has_root():
    """Return True if adbd is currently running as root (uid 0)."""
    r = run_adb(["shell", "id", "-u"], check=False)
    return r.stdout.strip() == "0"


def ensure_root(is_rootable):
    """Try to elevate adbd to root. Returns True if root is active afterwards.

    - Already root: return True.
    - Rootable build (userdebug/eng/debuggable): run `adb root`, wait, recheck.
    - Production (user) build: cannot root, return False.
    """
    if has_root():
        return True
    if not is_rootable:
        return False
    print("Trying to acquire root (adb root)...")
    run_adb(["root"], check=False)
    time.sleep(2)
    # `adb root` restarts adbd; wait for the device to come back.
    run_adb(["wait-for-device"], check=False)
    time.sleep(1)
    return has_root()


def _stream_capture(device_config, output_path, duration_secs):
    """No-root capture: stream trace from device stdout via `adb exec-out`.

    Works on production (user) builds on Android 10+ because traced/traced_probes
    are enabled by default and the trace never has to be written to a
    root-only path on the device. Binary stdout is captured in Python (bytes),
    avoiding PowerShell/CRLF corruption.
    """
    with open(output_path, "wb") as f:
        proc = subprocess.run(
            ["adb", "exec-out", "perfetto", "-c", device_config, "--txt", "-o", "-"],
            stdout=f,
            stderr=subprocess.PIPE,
            timeout=duration_secs + 60,
        )
    stderr = proc.stderr.decode(errors="replace").strip()
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return proc.returncode, size, stderr


def _file_pull_capture(device_config, output_path, duration_secs):
    """Fallback: write to on-device file then pull (needs writable trace dir / root)."""
    run_adb(["shell", "mkdir -p /data/misc/perfetto-traces"], check=False)
    run_adb(["shell", "rm -f /data/misc/perfetto-traces/trace"], check=False)
    device_out = "/data/misc/perfetto-traces/trace"
    proc = subprocess.run(
        ["adb", "shell", "perfetto", "-c", device_config, "--txt", "-o", device_out],
        capture_output=True,
        text=True,
        timeout=duration_secs + 60,
    )
    if proc.returncode != 0:
        return proc.returncode, 0, proc.stderr.strip()
    run_adb(["pull", device_out, str(output_path)], check=False)
    size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
    return 0, size, proc.stderr.strip()


def capture_trace(duration_secs, output_file, config_path=None, categories=None):
    # Check environment before starting
    print("Checking environment...")
    check_environment(output_file)

    build_type, is_rootable = get_build_type()
    rooted = ensure_root(is_rootable)
    print(f"Device build type: {build_type or 'unknown'} | "
          f"root: {'YES' if rooted else 'NO'}")

    config_template = load_config(config_path)

    # Calculate buffer size based on duration
    buffer_size_kb = calculate_buffer_size(duration_secs)
    print(f"Buffer size: {buffer_size_kb // 1024} MB (for {duration_secs}s capture)")

    config = config_template.replace("{duration_ms}", str(duration_secs * 1000))
    config = config.replace("{buffer_size_kb}", str(buffer_size_kb))

    if categories:
        print(f"Adding custom atrace categories: {', '.join(categories)}")
        config = add_atrace_categories(config, categories)

    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='_perfetto_config.txt', delete=False) as f:
        f.write(config)
        local_config = f.name

    try:
        print("Pushing config to device (/data/local/tmp is writable on all builds)...")
        run_adb(["push", local_config, "/data/local/tmp/perfetto_config.txt"])
    finally:
        try:
            os.unlink(local_config)
        except OSError:
            pass
    device_config = "/data/local/tmp/perfetto_config.txt"

    output_path = Path(output_file).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prev_selinux = None
    try:
        if rooted:
            # Root available -> original method: on-device file + pull.
            # Drop SELinux to permissive if needed so perfetto can write the file,
            # remembering the previous state to restore it afterwards.
            prev_selinux = run_adb(["shell", "getenforce"], check=False).stdout.strip()
            if prev_selinux == "Enforcing":
                print("SELinux is Enforcing; setting permissive for capture...")
                run_adb(["shell", "setenforce", "0"], check=False)

            print(f"Starting perfetto capture for {duration_secs}s "
                  f"(root: on-device file + pull)...")
            print(f"Capturing... (wait ~{duration_secs}s)")
            rc, size, stderr = _file_pull_capture(device_config, output_path, duration_secs)

            if rc != 0 or size == 0:
                print("File+pull capture failed or empty, trying streaming fallback...")
                if stderr:
                    print(f"  (file+pull stderr: {stderr})")
                rc, size, stderr = _stream_capture(device_config, output_path, duration_secs)
        else:
            # No root -> new method: no-root streaming capture (user builds).
            print(f"Starting perfetto capture for {duration_secs}s "
                  f"(no root: streaming via exec-out)...")
            print(f"Capturing... (wait ~{duration_secs}s)")
            rc, size, stderr = _stream_capture(device_config, output_path, duration_secs)

            if rc != 0 or size == 0:
                print("Streaming capture failed or empty, trying on-device file + pull fallback...")
                if stderr:
                    print(f"  (streaming stderr: {stderr})")
                rc, size, stderr = _file_pull_capture(device_config, output_path, duration_secs)
    finally:
        # Restore SELinux state we changed (root path only).
        if rooted and prev_selinux == "Enforcing":
            run_adb(["shell", "setenforce", "1"], check=False)

    if rc != 0 or size == 0:
        print("Trace capture failed.", file=sys.stderr)
        if stderr:
            print(f"perfetto: {stderr}", file=sys.stderr)
        if not rooted:
            print(
                "Note: on production (user) builds, ensure Android 10+ and that "
                "system tracing is allowed (persist.traced.enable=1). Root/setenforce "
                "are NOT required for the streaming path.",
                file=sys.stderr,
            )
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        sys.exit(1)

    print(f"\n✓ Trace saved successfully!")
    print(f"  Location: {output_path}")
    print(f"  Size: {size / 1024 / 1024:.2f} MB")
    print(f"  Kept on disk for later analysis (not overwritten on next capture)")


def main():
    parser = argparse.ArgumentParser(description="Capture Android Perfetto trace")
    parser.add_argument("-d", "--duration", type=int, default=20, help="Duration in seconds")
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file or directory (default: skill package dir; always unique timestamped name)",
    )
    parser.add_argument("-c", "--config", default=None, help="Path to perfetto config template")
    parser.add_argument(
        "--categories",
        nargs='+',
        default=None,
        help="Additional atrace categories to capture (e.g., --categories dalvikviktime my_custom_tag)"
    )
    args = parser.parse_args()

    args.output = resolve_output_path(args.output)
    print(f"Capture will be saved to: {args.output}\n")

    capture_trace(args.duration, args.output, args.config, args.categories)


if __name__ == "__main__":
    main()
