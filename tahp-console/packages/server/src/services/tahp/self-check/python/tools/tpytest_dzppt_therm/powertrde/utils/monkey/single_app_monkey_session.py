#!/usr/bin/env python3
# single_app_monkey_final.py
"""
Single-app Monkey with light AI monitor — final improved version.

主要特性：
 - 启动 monkey 前探测远端 help，仅加入设备支持的 --pct-* 参数（尽量把系统键等置 0）
 - 轻量且可靠的 foreground 检测（优先 dumpsys activity grep mFocusedActivity/mFocusedWindow）
 - 有序的恢复策略：collapse -> monkey wake -> am start（若需要）
 - AI: 若在同一 activity 停留超过 stuck_seconds 则发送 BACK（1..N 次），若返回桌面则唤回
 - 停止时使用 ps|grep|awk 风格 kill（用户喜好方式），并提供多个 fallback
 - 修复 start(..., background=False) 死锁（不在持锁时阻塞）
 - 默认不捕获远端输出（继承宿主终端），可传 output_file 重定向日志
"""
from typing import Optional
import subprocess
import threading
import time
import shlex
import random
import re
import atexit
import signal

from powertrde.env import ADB_EXE

ADB_BIN = ADB_EXE


class SingleAppMonkeySession:
    def __init__(self,
                 pkg: str,
                 adb_serial: Optional[str] = None,
                 events: int = 100_000_000,
                 throttle_ms: int = 200,
                 stuck_seconds: float = 20.0,
                 back_repeat: int = 1,
                 monitor_interval: float = 2.0,
                 verbosity: int = 1,
                 seed: Optional[int] = None,
                 output_file: Optional[str] = None,
                 main_activity_hint: Optional[str] = None  # optional exact main activity if available
                 ):
        self.pkg = pkg
        self.adb_serial = adb_serial
        self.events = int(events)
        self.throttle_ms = int(throttle_ms)
        self.stuck_seconds = float(stuck_seconds)
        self.back_repeat = int(back_repeat)
        self.monitor_interval = float(monitor_interval)
        self.verbosity = int(verbosity)
        self.seed = seed if seed is not None else random.SystemRandom().randint(1, 2 ** 31 - 1)
        self.output_file = output_file
        self.main_activity_hint = main_activity_hint

        # runtime
        self._proc: Optional[subprocess.Popen] = None
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._running = False
        self._start_time: Optional[float] = None
        self._duration: Optional[float] = None
        self._duration_timer: Optional[threading.Timer] = None

        # ai tracking
        self._last_activity: Optional[str] = None
        self._last_activity_ts: float = 0.0

        atexit.register(self._atexit_cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    # ---------------- adb helpers ----------------
    def _adb_prefix(self):
        cmd = [ADB_BIN]
        if self.adb_serial:
            cmd += ["-s", self.adb_serial]
        return cmd

    def _adb_run(self, argv, timeout: Optional[float] = None, capture_output: bool = False):
        full = self._adb_prefix() + argv
        if capture_output:
            try:
                p = subprocess.run(full, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
                out = p.stdout.decode("utf-8", errors="ignore") if p.stdout else ""
                return p.returncode, out
            except subprocess.TimeoutExpired:
                return -1, ""
        else:
            return subprocess.run(full, timeout=timeout)

    # ---------------- monkey help detection & command build ----------------
    def _get_remote_monkey_help(self) -> str:
        """
        Try to read remote monkey help (`monkey --help` or `monkey -h`).
        Return help string (might be empty).
        """
        for opt in (["shell", "monkey", "--help"], ["shell", "monkey", "-h"]):
            rc, out = self._adb_run(opt, timeout=3, capture_output=True)
            if rc == 0 and out:
                return out
        # fallback: try 'shell monkey' (some devices print usage)
        rc, out = self._adb_run(["shell", "monkey"], timeout=2, capture_output=True)
        return out or ""

    def _build_monkey_cmd(self) -> str:
        """
        Build a safe monkey command string based on remote help (if available).
        Try to set pct flags that would cause system keys/motion to 0 if supported.
        """
        help_text = self._get_remote_monkey_help()
        if self.verbosity:
            snippet = "\n".join(help_text.splitlines()[:8])
            print(f"[{self.pkg}] remote monkey help (snippet):\n{snippet}")

        def support(flag: str) -> bool:
            return flag in help_text

        # base command parts
        parts = ["monkey", "-p", shlex.quote(self.pkg)]
        # seed
        if "-s" in help_text or "SEED" in help_text or " -s " in help_text:
            parts += ["-s", str(int(self.seed))]
        else:
            # some devices still accept -s; include as best-effort
            parts += ["-s", str(int(self.seed))]

        # protective pct flags we want to set to 0 if supported
        protective_pct = ["--pct-syskeys", "--pct-motion", "--pct-trackball",
                          "--pct-nav", "--pct-majornav", "--pct-appswitch"]
        for f in protective_pct:
            if support(f):
                parts += [f, "0"]
            else:
                # if help missing, still include commonly supported ones as best-effort for modern devices
                if f in ("--pct-syskeys", "--pct-motion"):
                    parts += [f, "0"]

        # other safe flags
        safe_flags = ["--ignore-crashes", "--ignore-timeouts", "--ignore-security-exceptions",
                      "--monitor-native-crashes", "--kill-process-after-error"]
        for sf in safe_flags:
            if support(sf) or sf.replace("--", "") in help_text:
                parts.append(sf)
            else:
                # include ignore flags even if help not found - they're widely supported
                if sf.startswith("--ignore"):
                    parts.append(sf)

        # throttle if supported or assume supported
        parts += ["--throttle", str(int(self.throttle_ms))]

        # verbosity
        parts += ["-v"]

        # count
        parts += [str(int(self.events))]

        return " ".join(map(str, parts))

    # ---------------- collapse only ----------------
    def _collapse_statusbar(self):
        # Only collapse; do not call expansion (service call statusbar 1)
        try:
            self._adb_run(["shell", "cmd", "statusbar", "collapse"])
        except Exception:
            pass
        try:
            self._adb_run(["shell", "service", "call", "statusbar", "2"])
        except Exception:
            pass

    # ---------------- foreground detection (lightweight) ----------------
    def _get_foreground_component(self) -> Optional[str]:
        """
        Try several short commands in priority order to get the foreground component.
        Return the first token containing '/'.
        """
        cmds = [
            "dumpsys activity activities | grep -E 'mFocusedActivity|mFocusedWindow' -m 1",
            "dumpsys window windows | grep -m 1 mCurrentFocus",
            "dumpsys activity top | grep -m 1 ACTIVITY"
        ]
        for shell_cmd in cmds:
            full = self._adb_prefix() + ["shell", shell_cmd]
            try:
                p = subprocess.run(full, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=2.0)
                out = p.stdout.decode("utf-8", errors="ignore").strip()
            except subprocess.TimeoutExpired:
                out = ""
            if not out:
                continue
            toks = out.replace("{", " ").replace("}", " ").split()
            for t in toks:
                if "/" in t and any(ch.isalpha() for ch in t):
                    t = t.strip(",;")
                    if t.endswith(")"):
                        t = t[:-1]
                    return t
        return None

    # ---------------- kill remote monkey (user preferred approach) ----------------
    def _kill_monkey_process_via_ps(self) -> bool:
        # device command returns PIDs (one per line) for monkey processes
        remote_cmd = "ps | grep -v grep | grep -F com.android.commands.monkey | awk '{print $2}'"
        full = self._adb_prefix() + ["shell", remote_cmd]
        try:
            out = subprocess.check_output(full, stderr=subprocess.DEVNULL, text=True, timeout=4)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return False
        killed_any = False
        for line in out.splitlines():
            pid = line.strip()
            if not pid:
                continue
            if not pid.isdigit():
                m = re.search(r"(\d+)", pid)
                if m:
                    pid = m.group(1)
                else:
                    continue
            try:
                subprocess.run(self._adb_prefix() + ["shell", "kill", "-9", pid],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
                killed_any = True
            except Exception:
                pass
        return killed_any

    def _kill_monkey_fallback(self) -> bool:
        rc, out = self._adb_run(["shell", "pidof", "monkey"], timeout=2, capture_output=True)
        if rc == 0 and out.strip():
            for p in out.strip().split():
                if p.isdigit():
                    subprocess.run(self._adb_prefix() + ["shell", "kill", "-9", p],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        # pkill
        try:
            subprocess.run(self._adb_prefix() + ["shell", "pkill", "-f", "com.android.commands.monkey"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        except Exception:
            pass
        # ps fallback
        rc, out = self._adb_run(["shell", "ps"], timeout=2, capture_output=True)
        if rc == 0 and out:
            for line in out.splitlines():
                if "monkey" in line and "com.android.commands.monkey" in line:
                    cols = line.split()
                    pid = None
                    if len(cols) >= 2 and cols[1].isdigit():
                        pid = cols[1]
                    else:
                        for c in cols:
                            if c.isdigit():
                                pid = c
                                break
                    if pid:
                        subprocess.run(self._adb_prefix() + ["shell", "kill", "-9", pid],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        return False

    def _kill_remote_monkey(self) -> bool:
        ok = self._kill_monkey_process_via_ps()
        if ok:
            if self.verbosity:
                print(f"[{self.pkg}] killed monkey via ps-grep-awk")
            return True
        ok2 = self._kill_monkey_fallback()
        if ok2:
            if self.verbosity:
                print(f"[{self.pkg}] killed monkey via fallback")
            return True
        if self.verbosity:
            print(f"[{self.pkg}] no monkey process found")
        return False

    # ---------------- ai/back handling ----------------
    def _ai_check_and_back(self, current_component: Optional[str]):
        now = time.time()
        if current_component and current_component.startswith(self.pkg):
            if self._last_activity != current_component:
                self._last_activity = current_component
                self._last_activity_ts = now
                if self.verbosity:
                    print(f"[{self.pkg}] activity changed -> {current_component}")
                return
            elapsed = now - self._last_activity_ts
            if elapsed >= self.stuck_seconds:
                if self.verbosity:
                    print(f"[{self.pkg}] stuck on {current_component} for {elapsed:.1f}s -> sending {self.back_repeat} BACK")
                for _ in range(self.back_repeat):
                    if self._stop_event.is_set():
                        return
                    # Only BACK allowed from AI (no Home/Power)
                    try:
                        self._adb_run(["shell", "input", "keyevent", "4"])
                    except Exception:
                        pass
                    time.sleep(0.35)
                    fg = self._get_foreground_component()
                    if fg and fg.startswith(self.pkg):
                        self._last_activity = fg
                        self._last_activity_ts = time.time()
                        if self.verbosity:
                            print(f"[{self.pkg}] after BACK still in app: {fg}")
                        return
                # after BACKs, if not in-app -> wake
                fg2 = self._get_foreground_component()
                if not (fg2 and fg2.startswith(self.pkg)):
                    if self.verbosity:
                        print(f"[{self.pkg}] app left foreground after BACK (fg={fg2}) -> wake")
                    self._recover_wake()
                # reset timer to avoid immediate repeat
                self._last_activity = None
                self._last_activity_ts = time.time()
        else:
            self._last_activity = None
            self._last_activity_ts = 0.0

    # ---------------- recovery/wake ----------------
    def _recover_wake(self):
        """
        Recovery sequence (escalating):
         1) collapse statusbar
         2) monkey -p pkg 1 (light wake)
         3) am start -W -a MAIN -c LAUNCHER -n pkg/<main> (if main_activity_hint provided)
        After each step, re-check foreground.
        """
        # 1) collapse
        self._collapse_statusbar()
        time.sleep(0.15)
        fg = self._get_foreground_component()
        if fg and fg.startswith(self.pkg):
            if self.verbosity:
                print(f"[{self.pkg}] recovered after collapse: {fg}")
            return

        # 2) monkey wake
        try:
            subprocess.run(self._adb_prefix() + ["shell", "monkey", "-p", self.pkg, "-c", "android.intent.category.LAUNCHER", "1"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
        except Exception:
            pass
        time.sleep(0.5)
        fg = self._get_foreground_component()
        if fg and fg.startswith(self.pkg):
            if self.verbosity:
                print(f"[{self.pkg}] recovered after monkey wake: {fg}")
            return

        # 3) am start fallback if provided hint
        if self.main_activity_hint:
            try:
                subprocess.run(self._adb_prefix() + ["shell", "am", "start", "-W", "-n", f"{self.pkg}/{self.main_activity_hint}"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
            except Exception:
                pass
            time.sleep(0.7)
            fg = self._get_foreground_component()
            if fg and fg.startswith(self.pkg):
                if self.verbosity:
                    print(f"[{self.pkg}] recovered after am start: {fg}")
                return

        # last-effort: generic AM launch
        try:
            subprocess.run(self._adb_prefix() + ["shell", "am", "start", "-W", "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", "-n", f"{self.pkg}/.MainActivity"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=6)
        except Exception:
            pass
        time.sleep(0.7)

    # ---------------- monitor loop ----------------
    def _monitor_loop(self):
        """
        Periodically:
         - check foreground
         - if foreground==pkg -> update last activity timestamp
         - else -> try recovery (recover_wake)
         - also do AI stuck/back handling
        """
        while not self._stop_event.is_set():
            try:
                fg = self._get_foreground_component()
                if self.verbosity:
                    print(f"[{self.pkg}] monitor fg={fg}")
                if fg and fg.startswith(self.pkg):
                    # in-app, handle stuck AI
                    self._ai_check_and_back(fg)
                else:
                    # not foreground -> recovery attempts (several quick attempts)
                    if self.verbosity:
                        print(f"[{self.pkg}] not foreground ({fg}) -> recovery sequence")
                    for attempt in range(3):
                        if self._stop_event.is_set():
                            break
                        self._recover_wake()
                        fg2 = self._get_foreground_component()
                        if fg2 and fg2.startswith(self.pkg):
                            break
                        time.sleep(0.4)
                # duration handled by timer in start()
            except Exception as e:
                if self.verbosity:
                    print(f"[{self.pkg}] monitor exception: {e}")
            # sleep small intervals but interruptible
            for _ in range(int(self.monitor_interval * 10)):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)

    # ---------------- public API ----------------
    def start(self, duration_seconds: Optional[float] = None, background: bool = True):
        """
        Start monkey session.
         - duration_seconds: stop automatically after seconds (None = no auto stop)
         - background: if False then block until adb monkey process ends (or stop called)
        """
        with self._lock:
            if self._running:
                raise RuntimeError("already running")
            self._running = True
            self._stop_event.clear()
            self._duration = duration_seconds
            self._start_time = time.time()

            # start monitor thread
            self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
            self._monitor_thread.start()

            # schedule duration timer
            if self._duration is not None:
                self._duration_timer = threading.Timer(self._duration, self.stop)
                self._duration_timer.daemon = True
                self._duration_timer.start()

            # collapse before start
            self._collapse_statusbar()

            # build monkey command safely
            monkey_cmd = self._build_monkey_cmd()
            # wrapper: use shell -c to allow the string command
            full_cmd = self._adb_prefix() + ["shell", monkey_cmd]

            # decide stdout destination
            stdout_target = None
            stderr_target = None
            if self.output_file:
                self._out_fh = open(self.output_file, "ab")
                stdout_target = self._out_fh
                stderr_target = self._out_fh

            if self.verbosity:
                print(f"[{self.pkg}] starting monkey (seed={self.seed}): {monkey_cmd.split()[:8]} ...")

            try:
                # start adb local process; do not hold self._lock while waiting below
                self._proc = subprocess.Popen(full_cmd, stdout=stdout_target, stderr=stderr_target)
            except Exception:
                self._running = False
                raise

        # lock released

        if not background:
            try:
                if self.verbosity:
                    print(f"[{self.pkg}] blocking wait for local adb child (pid={self._proc.pid})")
                self._proc.wait()
            finally:
                self.stop()
            return

    def stop(self, timeout: float = 10.0):
        with self._lock:
            if not self._running:
                return
            if self.verbosity:
                print(f"[{self.pkg}] stop() called")
            # set stop flag
            self._stop_event.set()
            # cancel timer
            try:
                if self._duration_timer:
                    self._duration_timer.cancel()
            except Exception:
                pass
            # kill remote monkey
            try:
                self._kill_remote_monkey()
            except Exception as e:
                if self.verbosity:
                    print(f"[{self.pkg}] _kill_remote_monkey error: {e}")
            # terminate local adb proc
            if self._proc:
                try:
                    self._proc.terminate()
                    try:
                        self._proc.wait(timeout=2.0)
                    except Exception:
                        self._proc.kill()
                except Exception:
                    pass
                finally:
                    self._proc = None
            # join monitor
            if self._monitor_thread and self._monitor_thread.is_alive():
                self._monitor_thread.join(timeout=timeout)
            # close out file
            try:
                if hasattr(self, "_out_fh") and self._out_fh:
                    self._out_fh.flush()
                    self._out_fh.close()
            except Exception:
                pass
            self._running = False

    def is_running(self):
        return self._running

    def wait(self, timeout: Optional[float] = None):
        start = time.time()
        while True:
            if not self._running:
                return True
            if timeout is not None and (time.time() - start) > timeout:
                return False
            time.sleep(0.2)

    # ---------------- signals / cleanup ----------------
    def _signal_handler(self, signum, frame):
        if self.verbosity:
            print(f"[{self.pkg}] got signal {signum}, stopping")
        threading.Thread(target=self.stop, daemon=True).start()

    def _atexit_cleanup(self):
        try:
            if self._running:
                self.stop()
        except Exception:
            pass


# ----------------------
# optional CLI for quick debug
# ----------------------
def _cli():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--pkg", required=True)
    parser.add_argument("--adb-serial", default=None)
    parser.add_argument("--events", type=int, default=20000)
    parser.add_argument("--throttle", type=int, default=200)
    parser.add_argument("--monitor-interval", type=float, default=2.5)
    parser.add_argument("--duration", type=float, default=None)
    args = parser.parse_args()

    s = SingleAppMonkeySession(pkg=args.pkg, adb_serial=args.adb_serial, events=args.events,
                               throttle_ms=args.throttle, monitor_interval=args.monitor_interval)
    print("Starting monkey session...")
    s.start(duration_seconds=args.duration, background=True)
    try:
        if args.duration:
            s.wait(timeout=args.duration + 10)
        else:
            while s.is_running():
                time.sleep(1)
    except KeyboardInterrupt:
        print("Interrupted -> stopping")
    finally:
        s.stop()
        s.wait()


def _mock():
    from powertrde.utils.trde import adb
    _d = adb.first_device()
    s = SingleAppMonkeySession(pkg='com.whatsapp', adb_serial=_d, throttle_ms=200)
    s.start(duration_seconds=60, background=False)


def _stop_monkey():
    from tpy_aw.u2d_test_helper import U2DTestHelper
    from powertrde.utils.trde import adb
    _d = adb.first_device()
    u2h = U2DTestHelper(_d)
    u2h.kill_monkey_process()


def _normal_monkey():
    from tpy_aw.u2d_test_helper import U2DTestHelper
    from powertrde.utils.trde import adb
    _d = adb.first_device()
    u2h = U2DTestHelper(_d)
    u2h.run_monkey_test('com.whatsapp', 40)


if __name__ == "__main__":
    # _cli_main()
    # _mock()
    _stop_monkey()
    # _normal_monkey()
