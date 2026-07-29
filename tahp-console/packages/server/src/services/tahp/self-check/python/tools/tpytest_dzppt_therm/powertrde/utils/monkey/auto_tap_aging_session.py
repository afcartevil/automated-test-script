#!/usr/bin/env python3
"""
autotap_aging_with_kill_and_recover.py

在原有版本基础上加入：
 - 心跳机制 (heartbeat)（主机写入，设备端检查）
 - 当主机因 QuickEdit/暂停 导致设备脚本自杀，主机恢复后自动重启远端脚本（除非用户主动 stop）
 - 重启限流（window/count + backoff）防止无限重启
 - 保持原子 host-back / LAST_BACK 节流 / PAUSE / STOP 等行为
"""
import subprocess
import tempfile
import time
import os
import atexit
import signal
from collections import deque
from typing import Optional, Tuple
import random
import re
import threading

from powertrde.env import ADB_EXE

# === Configuration paths on device ===
REMOTE_SCRIPT = "/data/local/tmp/autotap_aging.sh"
REMOTE_LOG = "/data/local/tmp/autotap_aging.log"
REMOTE_STOP = "/data/local/tmp/autotap_aging.stop"
REMOTE_PID = "/data/local/tmp/autotap_aging.pid"
REMOTE_LAST_BACK = "/data/local/tmp/autotap_last_back"
REMOTE_PAUSE = "/data/local/tmp/autotap_pause"
REMOTE_HEARTBEAT = "/data/local/tmp/autotap_heartbeat"

# Heartbeat parameters
HEARTBEAT_INTERVAL = 2           # 主机每 2s 写一次心跳
HEARTBEAT_TIMEOUT = 8            # 设备端超过 8s 未见心跳就退出（防止孤儿）

# Restart rate-limit / backoff
RESTART_WINDOW_SECONDS = 60      # 统计窗口（秒）
RESTART_MAX_IN_WINDOW = 5        # 窗口内最大重启次数
RESTART_BACKOFF_BASE = 5         # 超窗后最小回退秒数（会乘以次数等简单退避策略）

TAG = "autotap"


# === Helper external cleanup function ===
def kill_autotap_on_device(adb_serial: Optional[str] = None, verbose: bool = True) -> None:
    def prefix(cmd):
        p = [ADB_EXE]
        if adb_serial:
            p += ["-s", adb_serial]
        return p + cmd

    if verbose:
        print("[kill_autotap] initiating cleanup on device")
    subprocess.run(prefix(["shell", "touch", REMOTE_STOP]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        p = subprocess.run(prefix(["shell", f"cat {REMOTE_PID}"]), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, text=True)
        if p.returncode == 0 and p.stdout:
            for ln in p.stdout.splitlines():
                m = re.search(r"(\d+)", ln)
                if m:
                    pid = m.group(1)
                    if verbose:
                        print(f"[kill_autotap] killing pid {pid}")
                    subprocess.run(prefix(["shell", "kill", "-9", pid]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
    except Exception:
        pass
    try:
        subprocess.run(prefix(["shell", f"pkill -f {os.path.basename(REMOTE_SCRIPT)}"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass
    try:
        subprocess.run(prefix(["shell", f"ps | grep -v grep | grep -F {os.path.basename(REMOTE_SCRIPT)} | awk '{{print $2}}' | xargs -r kill -9"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False, timeout=3)
    except Exception:
        pass
    for f in (REMOTE_PID, REMOTE_STOP, REMOTE_LOG, REMOTE_LAST_BACK, REMOTE_PAUSE):
        try:
            subprocess.run(prefix(["shell", "rm", "-f", f]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass
    try:
        subprocess.run(prefix(["shell", "ps | grep -v grep | grep -i autotap | awk '{print $2}' | xargs -r kill -9"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except Exception:
        pass
    if verbose:
        print("[kill_autotap] cleanup finished")


# === Session class ===
class AutoTapAgingSession:
    def __init__(self,
                 pkg: str,
                 adb_serial: Optional[str] = None,
                 sleep_min: float = 0.20,
                 sleep_max: float = 0.50,
                 back_pct: int = 5,
                 swipe_pct: int = 10,
                 monitor_interval: float = 1.0,
                 oscillation_window: int = 8,
                 oscillation_threshold: int = 6,
                 margin_ratio: float = 0.06,
                 verbosity: int = 1):
        self.pkg = pkg
        self.adb_serial = adb_serial
        self.sleep_min = float(sleep_min)
        self.sleep_max = float(sleep_max)
        self.back_pct = int(back_pct)
        self.swipe_pct = int(swipe_pct)
        self.monitor_interval = float(monitor_interval)
        self.osc_window = int(oscillation_window)
        self.osc_threshold = int(oscillation_threshold)
        self.margin_ratio = float(margin_ratio)
        self.verbosity = int(verbosity)

        self._running = False
        self._stop_requested = False
        self._monitor_thread = None
        self._hist = deque(maxlen=self.osc_window)

        # heartbeat
        self._heartbeat_thread = None
        self._heartbeat_running = threading.Event()

        # restart limits
        self._restart_timestamps = deque()  # store timestamps of recent restarts
        self._last_restart_time = 0

        # store last-used args for restarting remote script
        self._last_remote_args = None  # tuple(minx,maxx,miny,maxy,sleep_min,sleep_max,back_pct,swipe_pct)

        atexit.register(self._cleanup_on_exit)
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._signal_handler)
            except Exception:
                pass

    # --- adb helpers ---
    def _adb_prefix(self):
        p = [ADB_EXE]
        if self.adb_serial:
            p += ["-s", self.adb_serial]
        return p

    def _run(self, args, timeout: Optional[float] = None, capture_output: bool = True) -> Tuple[int, str]:
        full = self._adb_prefix() + args
        if capture_output:
            try:
                out = subprocess.check_output(full, stderr=subprocess.STDOUT, timeout=timeout, text=True)
                return 0, out
            except subprocess.CalledProcessError as e:
                return e.returncode, (e.output or "")
            except subprocess.TimeoutExpired:
                return -1, ""
        else:
            p = subprocess.run(full, timeout=timeout)
            return p.returncode, ""

    def _get_screen_size(self) -> Tuple[int, int]:
        rc, out = self._run(["shell", "wm", "size"], timeout=2.0)
        if rc == 0 and out:
            m = re.search(r"Physical size:\s*(\d+)x(\d+)|(\d+)x(\d+)", out)
            if m:
                if m.group(1) and m.group(2):
                    return int(m.group(1)), int(m.group(2))
                else:
                    return int(m.group(3)), int(m.group(4))
        rc, out = self._run(["shell", "dumpsys", "display"], timeout=2.0)
        if rc == 0 and out:
            m = re.search(r"phys=(\d+)x(\d+)", out)
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1080, 1920

    # --- produce device-side script (with heartbeat check) ---
    def _make_script(self) -> str:
        hb_timeout = HEARTBEAT_TIMEOUT
        script = rf'''#!/system/bin/sh
MINX=$1; MAXX=$2; MINY=$3; MAXY=$4
SLEEP_MIN=$5; SLEEP_MAX=$6
BACK_PCT=$7; SWIPE_PCT=$8
STOPFILE="{REMOTE_STOP}"
PAUSEFILE="{REMOTE_PAUSE}"
LASTBACKFILE="{REMOTE_LAST_BACK}"
HEARTBEATFILE="{REMOTE_HEARTBEAT}"
HEARTBEAT_TIMEOUT={hb_timeout}
LOGFILE="{REMOTE_LOG}"

trap "exit 0" TERM INT

rand_sleep() {{
  awk -v a="$SLEEP_MIN" -v b="$SLEEP_MAX" 'BEGIN{{srand(); printf "%.3f", a + rand()*(b-a)}}' | xargs sleep
}}

if [ ! -f "$LASTBACKFILE" ]; then
  echo 0 > "$LASTBACKFILE" 2>/dev/null || true
fi

while [ ! -f "$STOPFILE" ]; do
  # HEARTBEAT check
  hb=0
  if [ -f "$HEARTBEATFILE" ]; then
    hb=$(cat "$HEARTBEATFILE" 2>/dev/null || echo 0)
  fi
  now=$(date +%s 2>/dev/null || busybox date +%s 2>/dev/null || echo 0)
  delta=$((now - hb))
  if [ "$hb" = "0" ] || [ "$delta" -gt $HEARTBEAT_TIMEOUT ]; then
    echo "[autotap] heartbeat lost (hb=$hb now=$now delta=$delta) -> exiting" >> "$LOGFILE" 2>/dev/null || true
    exit 0
  fi

  if [ -f "$PAUSEFILE" ]; then
    sleep 0.5
    continue
  fi

  X=$((MINX + (RANDOM % (MAXX - MINX + 1))))
  Y=$((MINY + (RANDOM % (MAXY - MINY + 1))))
  input tap $X $Y
  R=$((RANDOM % 100))
  if [ $R -lt $SWIPE_PCT ]; then
    X2=$((MINX + (RANDOM % (MAXX - MINX + 1))))
    Y2=$((MINY + (RANDOM % (MAXY - MINY + 1))))
    input swipe $X $Y $X2 $Y2 300
  elif [ $R -lt $((SWIPE_PCT + BACK_PCT)) ]; then
    now=$(date +%s 2>/dev/null || busybox date +%s 2>/dev/null || echo 0)
    last=0
    if [ -f "$LASTBACKFILE" ]; then
      last=$(cat "$LASTBACKFILE" 2>/dev/null || echo 0)
    fi
    delta=$((now - last))
    if [ "$delta" -ge 5 ]; then
      input keyevent 4
      echo "$now" > "$LASTBACKFILE" 2>/dev/null || true
    fi
  fi
  rand_sleep
done
exit 0
'''
        return script

    def _push_script(self):
        script = self._make_script()
        fd, lp = tempfile.mkstemp(suffix=".sh")
        try:
            with os.fdopen(fd, "w", newline="\n") as f:
                f.write(script)
            rc, out = self._run(["push", lp, REMOTE_SCRIPT], timeout=10, capture_output=True)
            if rc != 0:
                raise RuntimeError("adb push failed: " + out)
            self._run(["shell", "chmod", "+x", REMOTE_SCRIPT], timeout=2.0)
        finally:
            try:
                os.remove(lp)
            except Exception:
                pass

    def _start_remote_script(self, minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct) -> Optional[int]:
        # ensure helper files cleared
        self._run(["shell", "rm", "-f", REMOTE_STOP], timeout=1.0)
        self._run(["shell", "rm", "-f", REMOTE_PAUSE], timeout=1.0)
        try:
            self._run(["shell", f"sh -c \"echo 0 > {REMOTE_LAST_BACK} || true\""], timeout=1.0)
        except Exception:
            pass
        # ensure heartbeat file has initial value
        try:
            now = int(time.time())
            self._run(["shell", f"sh -c \"echo {now} > {REMOTE_HEARTBEAT} || true\""], timeout=1.0)
        except Exception:
            pass

        args = " ".join(map(str, [minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct]))
        shell_cmd = f"sh -c '{REMOTE_SCRIPT} {args} >/data/local/tmp/autotap_aging.log 2>&1 & echo $! '"
        try:
            rc, out = self._run(["shell", shell_cmd], timeout=8.0)
            if rc == 0 and out:
                pid_line = out.strip().splitlines()[-1].strip()
                m = re.search(r"(\d+)", pid_line)
                if m:
                    pid = int(m.group(1))
                    self._run(["shell", f"echo {pid} > {REMOTE_PID}"], timeout=1.0)
                    # record last args for potential restart
                    self._last_remote_args = (minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct)
                    return pid
            return None
        except Exception:
            return None

    def _stop_remote_script(self):
        self._run(["shell", "touch", REMOTE_STOP], timeout=1.0)
        rc, out = self._run(["shell", "cat", REMOTE_PID], timeout=1.0)
        if rc == 0 and out.strip():
            for ln in out.splitlines():
                m = re.search(r"(\d+)", ln)
                if m:
                    pid = m.group(1)
                    self._run(["shell", "kill", "-9", pid], timeout=1.0)
        self._run(["shell", "pkill", "-f", os.path.basename(REMOTE_SCRIPT)], timeout=1.0)
        self._run(["shell", "rm", "-f", REMOTE_PID, REMOTE_STOP, REMOTE_LAST_BACK, REMOTE_PAUSE, REMOTE_HEARTBEAT], timeout=1.0)

    def _get_foreground_component(self) -> Optional[str]:
        candidates = [
            "dumpsys activity activities | grep -E 'mFocusedActivity|mFocusedWindow' -m 1",
            "dumpsys window windows | grep -m 1 mCurrentFocus",
            "dumpsys activity top | grep -m 1 ACTIVITY"
        ]
        for cmd in candidates:
            rc, out = self._run(["shell", cmd], timeout=2.0)
            if rc != 0 or not out:
                continue
            toks = out.replace("{", " ").replace("}", " ").split()
            for t in toks:
                if "/" in t and any(ch.isalpha() for ch in t):
                    t = t.strip(",;")
                    if t.endswith(")"):
                        t = t[:-1]
                    return t
        return None

    def _detect_oscillation(self) -> bool:
        if len(self._hist) < self.osc_threshold:
            return False
        uniq = list(dict.fromkeys(self._hist))
        if len(uniq) != 2:
            return False
        a, b = uniq[0], uniq[1]
        for i, v in enumerate(self._hist):
            exp = a if (i % 2 == 0) else b
            if v != exp:
                exp2 = b if (i % 2 == 0) else a
                if v != exp2:
                    return False
        return True

    # == NEW: 原子化 host-side BACK 尝试 ==
    def _try_host_back(self) -> bool:
        """
        在设备端原子判断并执行 BACK（满足 >=5s 保护）。
        返回 True 表示实际发送了 BACK（并写回 LAST_BACK），False 表示跳过（因节流）。
        这个实现避免主机读/写产生的 race 条件。
        """
        cmd = (
            "sh -c 'now=$(date +%s 2>/dev/null || busybox date +%s 2>/dev/null || echo 0); "
            f"last=$(cat {REMOTE_LAST_BACK} 2>/dev/null || echo 0); "
            "delta=$((now - last)); "
            "if [ \"$delta\" -ge 5 ]; then input keyevent 4; echo $now > " + REMOTE_LAST_BACK + " 2>/dev/null || true; echo SENT; else echo SKIP; fi'"
        )
        rc, out = self._run(["shell", cmd], timeout=3.0)
        if rc == 0 and out:
            if "SENT" in out:
                if self.verbosity >= 2:
                    print("[autotap] host_back: SENT")
                return True
            else:
                if self.verbosity >= 3:
                    print(f"[autotap] host_back: SKIP (out={out.strip()})")
                return False
        return False

    def _escape_and_restart(self, screen_w, screen_h):
        if self.verbosity:
            print("[autotap] oscillation detected -> escape")
        # stop remote script
        self._stop_remote_script()
        # try ONE host back with atomic check (do NOT do two fast backs)
        try:
            sent = self._try_host_back()
            if self.verbosity >= 1:
                print(f"[autotap] escape host_back sent={sent}")
        except Exception:
            pass
        # then safe tap + swipe escape maneuver
        safe_x = int(screen_w * 0.25)
        safe_y = int(screen_h * 0.25)
        self._run(["shell", "input", "tap", str(safe_x), str(safe_y)], timeout=1)
        time.sleep(0.2)
        x1 = int(screen_w * 0.7)
        y1 = int(screen_h * 0.5)
        x2 = int(screen_w * 0.3)
        y2 = int(screen_h * 0.5)
        self._run(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), "250"], timeout=2)
        time.sleep(0.3)
        min_margin = self.margin_ratio + random.random() * 0.04
        self._start_autotap_with_margins(min_margin=min_margin)

    # --- heartbeat threads ---
    def _heartbeat_loop(self, interval_seconds: float):
        if self.verbosity >= 2:
            print(f"[autotap] heartbeat thread started (interval={interval_seconds}s)")
        while self._heartbeat_running.is_set() and self._running and not self._stop_requested:
            try:
                now = int(time.time())
                # atomic write
                cmd = f"sh -c \"echo {now} > {REMOTE_HEARTBEAT} || true\""
                self._run(["shell", cmd], timeout=2.0, capture_output=False)
            except Exception:
                if self.verbosity >= 3:
                    print("[autotap] heartbeat write failed (ignored)")
            for _ in range(int(interval_seconds * 10)):
                if not (self._heartbeat_running.is_set() and self._running and not self._stop_requested):
                    break
                time.sleep(0.1)
        if self.verbosity >= 2:
            print("[autotap] heartbeat thread exiting")

    def _start_heartbeat(self, interval_seconds: float = HEARTBEAT_INTERVAL):
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            return
        self._heartbeat_running.set()
        try:
            now = int(time.time())
            self._run(["shell", f"sh -c \"echo {now} > {REMOTE_HEARTBEAT} || true\""], timeout=2.0)
        except Exception:
            pass
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, args=(interval_seconds,), daemon=True)
        self._heartbeat_thread.start()

    def _stop_heartbeat(self):
        self._heartbeat_running.clear()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)
        try:
            self._run(["shell", "rm", "-f", REMOTE_HEARTBEAT], timeout=1.0)
        except Exception:
            pass

    def _start_autotap_with_margins(self, min_margin: Optional[float] = None):
        sw, sh = self._get_screen_size()
        margin = self.margin_ratio if min_margin is None else float(min_margin)
        if margin < 0.01:
            margin = 0.01
        if margin > 0.4:
            margin = 0.4
        minx = int(sw * margin)
        maxx = int(sw * (1.0 - margin))
        miny = int(sh * margin)
        maxy = int(sh * (1.0 - margin))
        sleep_min = round(self.sleep_min * (0.8 + random.random() * 0.4), 3)
        sleep_max = round(self.sleep_max * (0.8 + random.random() * 0.6), 3)
        back_pct = max(0, min(50, self.back_pct))
        swipe_pct = max(0, min(50, self.swipe_pct))

        # start heartbeat BEFORE launching remote script
        self._start_heartbeat()

        pid = self._start_remote_script(minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct)
        if self.verbosity:
            print(f"[autotap] started pid={pid}, margin={margin*100:.1f}% bounds=({minx},{miny})-({maxx},{maxy}) sleep=({sleep_min},{sleep_max}) back%={back_pct} swipe%={swipe_pct}")

    # --- detect if remote script running on device ---
    def _is_remote_running(self) -> bool:
        # Look for script basename in ps output
        base = os.path.basename(REMOTE_SCRIPT)
        rc, out = self._run(["shell", f"ps | grep -v grep | grep -F {base}"], timeout=2.0)
        if rc == 0 and out and out.strip():
            return True
        # fallback: check PID file then ps -p
        rc2, pid_out = self._run(["shell", f"cat {REMOTE_PID}"], timeout=1.0)
        if rc2 == 0 and pid_out and pid_out.strip():
            for line in pid_out.splitlines():
                m = re.search(r"(\d+)", line)
                if m:
                    pid = m.group(1)
                    rc3, _ = self._run(["shell", f"ps -p {pid}"], timeout=1.0)
                    if rc3 == 0:
                        return True
        return False

    # --- restart limiter & backoff ---
    def _can_restart_now(self) -> Tuple[bool, float]:
        """
        Return (can_restart, wait_seconds_if_not)
        """
        now = time.time()
        # remove old timestamps outside window
        while self._restart_timestamps and (now - self._restart_timestamps[0]) > RESTART_WINDOW_SECONDS:
            self._restart_timestamps.popleft()
        if len(self._restart_timestamps) < RESTART_MAX_IN_WINDOW:
            return True, 0.0
        # compute backoff: exponential-ish by number of recent restarts
        backoff = RESTART_BACKOFF_BASE * (1 + len(self._restart_timestamps) - RESTART_MAX_IN_WINDOW)
        # also avoid too-frequent attempts (min spacing)
        if now - self._last_restart_time < backoff:
            return False, backoff - (now - self._last_restart_time)
        return True, 0.0

    def _record_restart(self):
        now = time.time()
        self._restart_timestamps.append(now)
        self._last_restart_time = now

    def _ensure_remote_running(self):
        """
        Called by monitor loop periodically.
        If remote script is missing (and user not requested stop), attempt to restart it
        subject to restart rate limits.
        """
        if self._stop_requested:
            return
        # if remote already running, nothing to do
        if self._is_remote_running():
            return
        # remote not running -> try to restart if we have last args
        if not self._last_remote_args:
            if self.verbosity >= 1:
                print("[autotap] remote script missing but no saved args to restart")
            return
        can, wait = self._can_restart_now()
        if not can:
            if self.verbosity >= 1:
                print(f"[autotap] remote script missing, rate-limited: wait {wait:.1f}s")
            return
        # attempt restart
        if self.verbosity >= 1:
            print("[autotap] remote script missing -> attempting restart")
        try:
            # ensure heartbeat is running (so remote script won't immediately exit)
            self._start_heartbeat()
            (minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct) = self._last_remote_args
            pid = self._start_remote_script(minx, maxx, miny, maxy, sleep_min, sleep_max, back_pct, swipe_pct)
            if pid:
                self._record_restart()
                if self.verbosity:
                    print(f"[autotap] remote script restarted pid={pid}")
            else:
                # restart failed; mark a restart attempt (to avoid tight loop)
                self._record_restart()
                if self.verbosity >= 1:
                    print("[autotap] remote script restart failed (no pid)")
        except Exception as e:
            self._record_restart()
            if self.verbosity >= 1:
                print(f"[autotap] remote restart exception: {e}")

    def start(self, duration_seconds: Optional[int] = None, background: bool = True):
        if self._running:
            raise RuntimeError("already running")
        # ensure app foreground
        fg = self._get_foreground_component()
        if self.verbosity:
            print(f"[autotap] pre-start foreground check: {fg}")
        if not fg or not fg.startswith(self.pkg):
            if self.verbosity:
                print(f"[autotap] target not foreground -> launching {self.pkg} via monkey and waiting 1s")
            try:
                self._run(["shell", "pkill", "-f", "com.android.commands.monkey"], timeout=1.0)
            except Exception:
                pass
            self._run(["shell", "monkey", "-p", self.pkg, "-c", "android.intent.category.LAUNCHER", "1"], timeout=4.0)
            time.sleep(1.0)

        if self.verbosity:
            print("[autotap] pushing script")
        self._push_script()
        sw, sh = self._get_screen_size()
        margin = self.margin_ratio
        self._running = True
        self._stop_requested = False
        self._start_autotap_with_margins(min_margin=margin)
        self._monitor_thread = threading.Thread(target=self._monitor_loop, args=(sw, sh,), daemon=True)
        self._monitor_thread.start()

        if duration_seconds:
            def _delayed_stop():
                if self.verbosity:
                    print("[autotap] duration reached -> stopping")
                self.stop()
            t = threading.Timer(duration_seconds, _delayed_stop)
            t.daemon = True
            t.start()

        if not background:
            try:
                while self._running:
                    time.sleep(0.5)
            finally:
                self.stop()

    def stop(self):
        if not self._running:
            return
        if self.verbosity:
            print("[autotap] stop requested")
        self._stop_requested = True
        # stop heartbeat first => device will detect and exit if needed
        self._stop_heartbeat()
        # then stop remote script
        self._stop_remote_script()
        self._running = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

    def _read_remote_last_back(self) -> int:
        rc, out = self._run(["shell", f"cat {REMOTE_LAST_BACK}"], timeout=1.0)
        if rc == 0 and out:
            try:
                return int(out.strip().splitlines()[-1].strip())
            except Exception:
                return 0
        return 0

    def _write_remote_last_back(self, ts: int):
        try:
            self._run(["shell", f"sh -c \"echo {ts} > {REMOTE_LAST_BACK} || true\""], timeout=1.0)
        except Exception:
            pass

    def _monitor_loop(self, screen_w, screen_h):
        """
        主控制循环：监测前台、检测震荡、pause/resume、并调用 _ensure_remote_running() 以便在主机暂停恢复后自动重启远端脚本。
        """
        while self._running and not self._stop_requested:
            fg = self._get_foreground_component()
            if self.verbosity >= 2:
                print(f"[autotap] fg={fg}")
            if fg:
                self._hist.append(fg)
            if self._detect_oscillation():
                if self.verbosity:
                    print("[autotap] oscillation detected -> escape")
                try:
                    self._escape_and_restart(screen_w, screen_h)
                    self._hist.clear()
                except Exception as e:
                    if self.verbosity:
                        print(f"[autotap] escape failed: {e}")

            # ensure remote script still alive; if not, try to restart (unless user requested stop)
            try:
                self._ensure_remote_running()
            except Exception as e:
                if self.verbosity >= 1:
                    print(f"[autotap] ensure_remote_running error: {e}")

            if fg and fg.startswith(self.pkg):
                self._run(["shell", "rm", "-f", REMOTE_PAUSE], timeout=1.0)
            else:
                if self.verbosity:
                    print("[autotap] app not foreground -> pausing remote taps and will wait 1s then recheck")
                self._run(["shell", "touch", REMOTE_PAUSE], timeout=1.0)
                time.sleep(1.0)
                fg2 = self._get_foreground_component()
                if fg2 and fg2.startswith(self.pkg):
                    if self.verbosity >= 1:
                        print("[autotap] app returned to foreground during 1s wait -> resuming remote taps")
                    self._run(["shell", "rm", "-f", REMOTE_PAUSE], timeout=1.0)
                else:
                    if self.verbosity >= 1:
                        print("[autotap] still not foreground after 1s -> collapse + monkey wake")
                    self._run(["shell", "cmd", "statusbar", "collapse"], timeout=1.0)
                    time.sleep(0.15)
                    self._run(["shell", "monkey", "-p", self.pkg, "-c", "android.intent.category.LAUNCHER", "1"], timeout=3.0)
                    time.sleep(0.7)
                    fg3 = self._get_foreground_component()
                    if fg3 and fg3.startswith(self.pkg):
                        if self.verbosity >= 1:
                            print("[autotap] wake succeeded -> resuming remote taps")
                        self._run(["shell", "rm", "-f", REMOTE_PAUSE], timeout=1.0)
                    else:
                        if self.verbosity >= 1:
                            print("[autotap] wake did not bring app foreground -> trying ONE BACK (if allowed)")
                        sent = self._try_host_back()
                        if sent:
                            time.sleep(0.7)
                            fg4 = self._get_foreground_component()
                            if fg4 and fg4.startswith(self.pkg):
                                if self.verbosity >= 1:
                                    print("[autotap] BACK helped -> resuming remote taps")
                                self._run(["shell", "rm", "-f", REMOTE_PAUSE], timeout=1.0)
                            else:
                                if self.verbosity >= 1:
                                    print("[autotap] BACK did not restore app -> remain paused until manual recovery")
                        else:
                            if self.verbosity >= 2:
                                print("[autotap] host BACK skipped due to throttle")
            for _ in range(int(self.monitor_interval * 10)):
                if self._stop_requested:
                    break
                time.sleep(0.1)

    def _cleanup_on_exit(self):
        try:
            # stop heartbeat and remote script
            self._stop_heartbeat()
        except Exception:
            pass
        try:
            if self._running:
                self.stop()
        except Exception:
            pass

    def _signal_handler(self, signum, frame):
        if self.verbosity:
            print("[autotap] signal received -> stopping")
        try:
            self.stop()
        except Exception:
            pass


# === Demo ===
if __name__ == "__main__":
    sess = AutoTapAgingSession(pkg="com.ss.android.ugc.trill", verbosity=1, margin_ratio=0.06)
    sess.start(duration_seconds=60, background=False)
    print("done")
