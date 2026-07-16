"""Interactive SSH via cqris bastion: password + OTP → target IP → target login."""
from __future__ import annotations

import re
import shlex
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import paramiko
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("缺少 paramiko，请执行: pip install paramiko") from exc


@dataclass
class BastionSSHConfig:
    bastion_host: str = "cqris.transsion.com"
    bastion_port: int = 22
    target_ip: str = "10.205.0.158"
    connect_timeout: int = 45
    command_timeout: int = 3600
    upload_http_port: int = 18765
    upload_http_bind: str = "0.0.0.0"
    prompt_patterns: Dict[str, str] = field(default_factory=lambda: {
        "otp": r"(?i)(2nd\s*password|verification\s*code|verify\s*code|otp|动态码|验证码|one[- ]time)\s*:?\s*$",
        "bastion_repassword": r"(?i)(\(.*@.*\)\s*)?password\s*:?\s*$|(?i)password authentication",
        "password": r"(?:'s\s+)?password\s*[：:]?\s*$|密码\s*[：:]?\s*$",
        "asset": r"(请选择目标资产|选择目标资产|请选择资产)\s*[：:]?\s*$",
        "ip": r"(input\s*ip|请输入\s*ip|目标\s*ip|enter\s*ip|host\s*ip|ip\s*address)\s*[：:]?\s*$",
        "login": r"(login|用户名|username|user\s*name|登录名)\s*[：:]?\s*$",
        "shell": r"[\$#>%]\s*$",
    })


@dataclass
class BastionSSHCredentials:
    bastion_user: str
    bastion_password: str
    otp: str
    target_ip: str = ""
    target_user: str = ""
    target_password: str = ""


@dataclass
class RemoteCommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


def load_bastion_config() -> BastionSSHConfig:
    cfg = BastionSSHConfig()
    try:
        root = __import__("pathlib").Path(__file__).resolve().parent.parent
        sys.path.insert(0, str(root / "tools"))
        from cli_config import load_settings

        settings, _ = load_settings()
        ssh = settings.get("ssh") or {}
        if isinstance(ssh, dict):
            cfg.bastion_host = str(ssh.get("bastion_host") or cfg.bastion_host)
            cfg.bastion_port = int(ssh.get("bastion_port") or cfg.bastion_port)
            cfg.target_ip = str(ssh.get("target_ip") or cfg.target_ip)
            cfg.connect_timeout = int(ssh.get("connect_timeout") or cfg.connect_timeout)
            cfg.command_timeout = int(ssh.get("command_timeout") or cfg.command_timeout)
            cfg.upload_http_port = int(ssh.get("upload_http_port") or cfg.upload_http_port)
            cfg.upload_http_bind = str(ssh.get("upload_http_bind") or cfg.upload_http_bind)
            prompts = ssh.get("prompt_patterns")
            if isinstance(prompts, dict):
                cfg.prompt_patterns.update({str(k): str(v) for k, v in prompts.items()})
    except Exception:
        pass
    return cfg


class BastionSSHSession:
    """Single interactive shell session through cqris to target host."""

    def __init__(self, config: Optional[BastionSSHConfig] = None):
        self.config = config or load_bastion_config()
        self._client: Optional[paramiko.SSHClient] = None
        self._shell: Optional[paramiko.Channel] = None
        self._buffer = ""
        self._awaiting_otp = False
        self._target_ip = ""
        self._target_user = ""
        self._target_password = ""
        self._progress_log: Optional[Callable[[str], None]] = None
        self._remote_temp_dir = ""
        self._remote_temp_dir_ready = False
        self._run_lock = threading.RLock()

    def set_remote_temp_dir(self, path: str) -> None:
        from web_app.remote_workdir_config import resolve_remote_temp_dir

        resolved = resolve_remote_temp_dir(path)
        if resolved != self._remote_temp_dir:
            self._remote_temp_dir = resolved
            self._remote_temp_dir_ready = False

    def set_progress_log(self, fn: Optional[Callable[[str], None]]) -> None:
        self._progress_log = fn

    def _log(self, msg: str) -> None:
        if self._progress_log and msg:
            self._progress_log(msg)

    def connect_cqris_phase1(self, bastion_user: str, bastion_password: str) -> None:
        """Phase 1: ssh -p 22 user@cqris (password at SSH auth), stop at OTP prompt."""
        cfg = self.config
        if not bastion_user or not bastion_password:
            raise RuntimeError("需要 cqris 用户名和密码")

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=cfg.bastion_host,
                port=cfg.bastion_port,
                username=bastion_user,
                password=bastion_password,
                look_for_keys=False,
                allow_agent=False,
                timeout=cfg.connect_timeout,
                banner_timeout=cfg.connect_timeout,
                auth_timeout=cfg.connect_timeout,
            )
        except (socket.error, paramiko.SSHException) as exc:
            raise RuntimeError(
                f"连接 cqris 失败（等同 ssh -p {cfg.bastion_port} "
                f"{bastion_user}@{cfg.bastion_host}）: {exc}"
            ) from exc

        shell = client.invoke_shell(width=220, height=48)
        shell.settimeout(1.0)
        self._client = client
        self._shell = shell
        self._buffer = ""
        time.sleep(0.8)
        self._append_buffer(self._recv_available(1.2))
        self._awaiting_otp = self._wait_for_otp_prompt()

    def complete_to_target(
        self,
        otp: str,
        target_ip: str,
        target_user: str,
        target_password: str,
    ) -> None:
        """Phase 2: user-entered OTP → target IP → target login."""
        cfg = self.config
        if not self._shell:
            raise RuntimeError("cqris 会话未建立，请先连接 cqris")
        otp = (otp or "").strip()
        if len(otp) < 4:
            raise RuntimeError("需要 6 位动态验证码 (OTP)")
        if not target_ip or not target_user or not target_password:
            raise RuntimeError("需要目标 IP、用户名和密码")

        self._log(f"OTP 阶段: 提交验证码并选择目标资产 {target_ip}")
        if self._asset_prompt_ready():
            self._log("已处于资产选择提示，直接输入 IP")
            self._send_line(target_ip)
            time.sleep(0.5)
            self._append_buffer(self._recv_available(1.0))
        elif self._awaiting_otp or self._buffer_suggests_otp() or self._match_prompt(cfg.prompt_patterns["otp"]):
            self._log("发送 OTP…")
            self._send_line(otp)
            time.sleep(0.8)
            self._wait_and_send_asset_or_ip(target_ip)
        else:
            self._log("等待资产列表并输入 IP…")
            self._wait_and_send_asset_or_ip(target_ip)

        self._log(f"目标机登录: 用户 {target_user}")
        self._expect_target_login(target_user)
        self._log("输入目标机 password…")
        self._expect_target_password(target_password)
        self._log("等待目标 shell 就绪…")
        self._wait_shell_ready()
        self._awaiting_otp = False
        self._target_ip = target_ip.strip()
        self._target_user = target_user.strip()
        self._target_password = target_password
        self._log(f"已登录目标机 {target_ip} ({target_user})")

    def connect(self, creds: BastionSSHCredentials) -> None:
        """One-shot connect (legacy): cqris + OTP + target in a single call."""
        cfg = self.config
        target_ip = (creds.target_ip or cfg.target_ip).strip()
        self.connect_cqris_phase1(creds.bastion_user, creds.bastion_password)
        self.complete_to_target(
            creds.otp, target_ip, creds.target_user, creds.target_password,
        )

    def _buffer_suggests_otp(self) -> bool:
        tail = self._buffer[-400:]
        return bool(re.search(
            r"(?i)(2nd\s*password|verification\s*code|verify\s*code|otp|动态码|验证码)\s*:?",
            tail,
        ))

    def _wait_for_otp_prompt(self) -> bool:
        cfg = self.config
        deadline = time.time() + cfg.connect_timeout
        saw_otp = False
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.4))
            if self._buffer_suggests_otp() or self._match_prompt(cfg.prompt_patterns["otp"]):
                saw_otp = True
                break
            if self._match_prompt(cfg.prompt_patterns["ip"]) or self._buffer_suggests_asset_selection():
                return False
            if self._match_prompt(cfg.prompt_patterns["shell"]):
                return False
            if self._match_prompt(cfg.prompt_patterns.get("bastion_repassword", "")):
                tail = self._buffer[-400:]
                raise RuntimeError(
                    "cqris 仍要求输入首次密码，请检查账号密码是否正确。最近输出:\n" + tail
                )
            time.sleep(0.1)
        if not saw_otp:
            tail = self._buffer[-800:]
            raise RuntimeError(
                "已连接 cqris，但未检测到 OTP 提示（期望 2nd Password: 或验证码提示）。\n" + tail
            )
        return True

    def close(self) -> None:
        try:
            if self._shell:
                self._shell.close()
        finally:
            self._shell = None
            if self._client:
                self._client.close()
            self._client = None

    def _recv_available(self, wait: float = 0.2) -> str:
        assert self._shell is not None
        chunks: List[str] = []
        deadline = time.time() + wait
        while time.time() < deadline:
            if self._shell.recv_ready():
                data = self._shell.recv(65535)
                if not data:
                    break
                chunks.append(data.decode("utf-8", errors="replace"))
            else:
                time.sleep(0.05)
        if self._shell.recv_ready():
            data = self._shell.recv(65535)
            if data:
                chunks.append(data.decode("utf-8", errors="replace"))
        return "".join(chunks)

    def _append_buffer(self, text: str) -> None:
        self._buffer += text
        if len(self._buffer) > 200_000:
            self._buffer = self._buffer[-100_000:]

    def _last_line(self) -> str:
        lines = [ln for ln in self._buffer.splitlines() if ln.strip()]
        return lines[-1] if lines else self._buffer

    def _strip_ansi(self, text: str) -> str:
        return re.sub(
            r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)",
            "",
            text,
        )

    def _asset_prompt_ready(self) -> bool:
        """True when the last visible line is 「请选择目标资产：」 (ready for IP input)."""
        clean = self._strip_ansi(self._buffer[-2500:])
        lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
        if not lines:
            return False
        return bool(re.match(r"请选择目标资产\s*[：:]?\s*$", lines[-1], re.IGNORECASE))

    def _buffer_suggests_asset_selection(self) -> bool:
        """Asset menu is visible (banner/list); may not yet be ready for input."""
        clean = self._strip_ansi(self._buffer[-2500:])
        return bool(re.search(
            r"(目标资产列表|请选择目标资产|选择目标资产)",
            clean,
            re.IGNORECASE,
        ))

    def _wait_and_send_asset_or_ip(self, target_ip: str) -> None:
        """Wait for 「请选择目标资产：」 then send IP + Enter (same as manual flow)."""
        cfg = self.config
        pattern = self._asset_or_ip_pattern(cfg)
        deadline = time.time() + cfg.connect_timeout
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.5))
            if self._asset_prompt_ready() or self._match_prompt(pattern):
                self._send_line(target_ip)
                time.sleep(0.6)
                self._append_buffer(self._recv_available(1.5))
                return
            time.sleep(0.15)
        tail = self._strip_ansi(self._buffer[-1200:])
        raise RuntimeError(
            f"等待「请选择目标资产：」提示超时（OTP 后应出现齐治资产列表）。"
            f"请确认 OTP 有效。最近输出:\n{tail}"
        )

    @staticmethod
    def _normalize_pattern(pattern: str) -> str:
        """Strip inline flags; callers use re.IGNORECASE instead."""
        if not pattern:
            return pattern
        return re.sub(r"\(\?[imsx]+\)", "", pattern)

    @staticmethod
    def _asset_or_ip_pattern(cfg: BastionSSHConfig) -> str:
        parts = [
            cfg.prompt_patterns.get("asset", ""),
            cfg.prompt_patterns.get("ip", ""),
        ]
        stripped = [BastionSSHSession._normalize_pattern(p) for p in parts if p]
        inner = "|".join(f"(?:{p})" for p in stripped)
        return inner or BastionSSHSession._normalize_pattern(cfg.prompt_patterns["ip"])

    def _match_prompt(self, pattern: str) -> bool:
        norm = self._normalize_pattern(pattern)
        line = self._strip_ansi(self._last_line()).strip()
        if re.search(norm, line, re.MULTILINE | re.IGNORECASE):
            return True
        tail = self._strip_ansi(self._buffer[-800:])
        return bool(re.search(norm, tail, re.MULTILINE | re.IGNORECASE))

    def _login_prompt_ready(self) -> bool:
        clean = self._strip_ansi(self._buffer[-1500:])
        lines = [ln.strip() for ln in clean.splitlines() if ln.strip()]
        if not lines:
            return False
        return bool(re.match(r"login\s*[：:]?\s*$", lines[-1], re.IGNORECASE))

    def _login_already_sent(self) -> bool:
        clean = self._strip_ansi(self._buffer[-1500:])
        return bool(re.search(r"(?im)^login:\s*\S+", clean))

    def _password_prompt_ready(self) -> bool:
        clean = self._strip_ansi(self._buffer[-1500:])
        if re.search(r"(?im)2nd\s*password", clean[-300:]):
            return False
        return bool(re.search(
            r"(?im)(?:[\w.@-]+'s\s+)?password\s*[：:]?\s*$|密码\s*[：:]?\s*$",
            clean,
        ))

    def _expect_target_login(self, username: str) -> None:
        if self._login_already_sent() or self._password_prompt_ready():
            return
        cfg = self.config
        deadline = time.time() + cfg.connect_timeout
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.4))
            if self._login_prompt_ready():
                self._send_line(username)
                time.sleep(0.5)
                self._append_buffer(self._recv_available(1.0))
                return
            if self._password_prompt_ready():
                return
            time.sleep(0.1)
        tail = self._strip_ansi(self._buffer[-800:])
        raise RuntimeError(f"等待 login 提示超时，最近输出:\n{tail}")

    def _expect_target_password(self, password: str) -> None:
        cfg = self.config
        deadline = time.time() + cfg.connect_timeout
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.4))
            if self._password_prompt_ready():
                self._send_line(password)
                time.sleep(0.6)
                self._append_buffer(self._recv_available(1.5))
                return
            time.sleep(0.1)
        tail = self._strip_ansi(self._buffer[-800:])
        raise RuntimeError(f"等待目标 password 提示超时，最近输出:\n{tail}")

    def _expect_and_send(
        self,
        pattern: str,
        value: str,
        label: str,
        timeout: Optional[int] = None,
    ) -> None:
        timeout = timeout or self.config.connect_timeout
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.3))
            if self._match_prompt(pattern):
                self._send_line(value)
                time.sleep(0.4)
                self._append_buffer(self._recv_available(0.5))
                return
            time.sleep(0.1)
        tail = self._buffer[-800:]
        raise RuntimeError(f"等待 {label} 提示超时，最近输出:\n{tail}")

    def _clear_shell_buffer(self) -> None:
        assert self._shell is not None
        deadline = time.time() + 2.0
        while time.time() < deadline:
            if self._shell.recv_ready():
                self._shell.recv(65535)
            else:
                time.sleep(0.05)
        self._buffer = ""

    def _recover_shell(self) -> None:
        """Clear stuck heredoc/base64 state on the interactive PTY."""
        if not self._shell:
            return
        try:
            for _ in range(3):
                self._shell.send("\x03")
                time.sleep(0.15)
            self._clear_shell_buffer()
            self.run("stty sane 2>/dev/null; true", check=False, timeout=20)
            self._clear_shell_buffer()
        except Exception:
            pass

    def _prepare_shell_for_upload(self) -> None:
        self._recover_shell()
        self.run(
            "stty -echo 2>/dev/null; printf '\\033[?2004l' 2>/dev/null; true",
            check=False,
            timeout=20,
        )
        self._clear_shell_buffer()

    def _maybe_gzip_local(self, local_path: str) -> Tuple[str, bool, List[str]]:
        """Return (path_to_upload, is_gzip, temp_files_to_delete)."""
        import gzip
        import os
        import tempfile
        from pathlib import Path

        local = Path(local_path)
        cleanups: List[str] = []
        try:
            fd, gz_path = tempfile.mkstemp(suffix=".patch.gz")
            os.close(fd)
            with local.open("rb") as fin, gzip.open(gz_path, "wb", compresslevel=6) as fout:
                while True:
                    block = fin.read(1024 * 1024)
                    if not block:
                        break
                    fout.write(block)
            raw_size = local.stat().st_size
            gz_size = Path(gz_path).stat().st_size
            if gz_size >= raw_size * 0.92:
                Path(gz_path).unlink(missing_ok=True)
                return str(local), False, cleanups
            cleanups.append(gz_path)
            self._log(
                f"上传前 gzip: {raw_size / 1024 / 1024:.1f} MB → "
                f"{gz_size / 1024 / 1024:.1f} MB"
            )
            return gz_path, True, cleanups
        except Exception as exc:
            self._log(f"gzip 跳过 ({exc})，上传原文件")
            return str(local), False, cleanups

    def _verify_remote_file_size(self, remote_path: str, expected: int) -> int:
        qremote = shlex.quote(remote_path)
        # stat 只读元数据，避免 wc -c 在大文件/NFS 上全量读盘导致 60s 超时
        mb = max(1, expected // (1024 * 1024))
        timeout = min(600, max(60, 60 + mb * 15))
        r = self.run(
            f"stat -c%s {qremote} 2>/dev/null || wc -c < {qremote} 2>/dev/null | tr -d ' \\n'",
            check=False,
            timeout=timeout,
        )
        try:
            size = int((r.stdout or "0").strip() or "0")
        except ValueError:
            size = 0
        if size < expected * 0.95:
            raise RuntimeError(
                f"远程文件大小异常: {size} 字节，期望约 {expected} 字节"
            )
        return size

    def _send_line(self, text: str) -> None:
        assert self._shell is not None
        self._shell.send(text + "\n")

    def _wait_shell_ready(self, timeout: Optional[int] = None) -> None:
        timeout = timeout or self.config.connect_timeout
        pattern = self.config.prompt_patterns["shell"]
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._append_buffer(self._recv_available(0.3))
            if self._match_prompt(pattern):
                return
            time.sleep(0.1)
        tail = self._buffer[-800:]
        raise RuntimeError(f"等待目标 shell 就绪超时，最近输出:\n{tail}")

    def _extract_run_stdout(
        self,
        raw: str,
        marker: str,
        out_begin: str,
        out_end: str,
        command: str,
    ) -> str:
        text = self._strip_ansi(raw)
        # Use rfind: the wrapped command line also contains out_begin/out_end strings
        # (shell echo); the last pair wraps the real captured output from cat.
        b = text.rfind(out_begin)
        e = text.rfind(out_end)
        if b >= 0 and e > b:
            return text[b + len(out_begin): e].strip()
        return self._sanitize_run_stdout(raw, marker, command)

    def _sanitize_run_stdout(self, raw: str, marker: str, command: str) -> str:
        """Drop echoed command, bracketed-paste codes, and shell prompt noise."""
        text = self._strip_ansi(raw)
        idx = text.find(marker)
        if idx >= 0:
            text = text[:idx]
        cmd = (command or "").strip()
        lines: List[str] = []
        for ln in text.splitlines():
            s = ln.strip()
            if not s:
                continue
            if cmd and cmd in s and ("&&" in s or s.startswith("cd ") or s.startswith("git ")):
                continue
            if re.search(r"\bgit status\b", s) and ("&&" in s or ";" in s):
                continue
            if s.startswith("cd ") and "&&" in s:
                continue
            if re.match(r"^\[\?[0-9]", s):
                continue
            if re.search(r"[\$#]\s*$", s) and ("@" in s or ":~" in s or ":/" in s):
                continue
            lines.append(ln.rstrip())
        return "\n".join(lines).strip()

    def _ensure_remote_temp_dir(self) -> None:
        if self._remote_temp_dir_ready or not self._shell:
            return
        self._remote_temp_dir_ready = True
        from web_app.remote_workdir_config import DEFAULT_REMOTE_TEMP_DIR

        d = shlex.quote(self._remote_temp_dir or DEFAULT_REMOTE_TEMP_DIR)
        self.run(f"mkdir -p {d}", check=False, capture_output=False, timeout=60)

    def _remote_temp_join(self, *parts: str) -> str:
        from web_app.remote_workdir_config import DEFAULT_REMOTE_TEMP_DIR

        base = self._remote_temp_dir or DEFAULT_REMOTE_TEMP_DIR
        tail = "/".join(p.strip("/").replace("\\", "/") for p in parts if p)
        if not tail:
            return base
        return f"{base}/{tail}"

    def run(
        self,
        command: str,
        *,
        timeout: Optional[int] = None,
        check: bool = True,
        capture_output: bool = True,
    ) -> RemoteCommandResult:
        if not self._shell:
            raise RuntimeError("SSH 会话未连接")
        with self._run_lock:
            return self._run_unlocked(
                command,
                timeout=timeout,
                check=check,
                capture_output=capture_output,
            )

    def _run_unlocked(
        self,
        command: str,
        *,
        timeout: Optional[int] = None,
        check: bool = True,
        capture_output: bool = True,
    ) -> RemoteCommandResult:
        if not self._shell:
            raise RuntimeError("SSH 会话未连接")
        self._ensure_remote_temp_dir()
        timeout = timeout or self.config.command_timeout
        marker = f"__GKI_EXIT_{int(time.time() * 1000)}__"
        if capture_output:
            out_file = self._remote_temp_join(f"gki_cmd_{marker}.out")
            out_begin = f"__GKI_OUT_B_{marker}__"
            out_end = f"__GKI_OUT_E_{marker}__"
            qout = shlex.quote(out_file)
            wrapped = (
                f"{{ {command}; }} > {qout} 2>&1; "
                f"ec=$?; echo {out_begin}; cat {qout}; echo {out_end}; "
                f"rm -f {qout}; echo {marker}$ec"
            )
        else:
            # 长耗时、低输出命令（如 git reset）：不 cat 回传，避免 PTY 吞吐成为瓶颈
            wrapped = f"{{ {command}; }}; ec=$?; echo {marker}$ec"
        cmd_preview = command if len(command) <= 100 else command[:97] + "..."
        self._log(f"▶ 远程执行: {cmd_preview}")
        self._buffer = ""
        self._send_line(wrapped)
        deadline = time.time() + timeout
        t0 = time.time()
        last_hb = t0
        output_parts: List[str] = []
        exit_code = -1
        while time.time() < deadline:
            chunk = self._recv_available(0.5)
            if chunk:
                output_parts.append(chunk)
            joined = "".join(output_parts)
            match = re.search(rf"{re.escape(marker)}(\d+)", joined)
            if match:
                exit_code = int(match.group(1))
                if capture_output:
                    stdout = self._extract_run_stdout(
                        joined, marker, out_begin, out_end, wrapped,
                    )
                else:
                    stdout = self._sanitize_run_stdout(joined, marker, wrapped)
                elapsed = time.time() - t0
                mark = "✓" if exit_code == 0 else "✗"
                self._log(f"{mark} 远程完成 (exit={exit_code}, {elapsed:.1f}s): {cmd_preview}")
                result = RemoteCommandResult(exit_code, stdout, "")
                if check and not result.ok:
                    raise RuntimeError(
                        f"远程命令失败 (exit {exit_code}): {command}\n{stdout[-2000:]}"
                    )
                return result
            now = time.time()
            if now - last_hb >= 30:
                self._log(f"… 仍在执行 ({now - t0:.0f}s): {cmd_preview}")
                last_hb = now
            time.sleep(0.05)
        elapsed = time.time() - t0
        tail = "".join(output_parts)[-2000:]
        self._log(f"✗ 远程超时 ({elapsed:.0f}s / 限 {timeout}s): {cmd_preview}")
        raise RuntimeError(f"远程命令超时 ({timeout}s): {command}\n{tail}")

    def upload_text_file(self, local_text: str, remote_path: str) -> None:
        """Upload text via shell chunked base64."""
        import tempfile
        from pathlib import Path

        with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as tmp:
            tmp.write(local_text.encode("utf-8", errors="replace"))
            tmp_path = tmp.name
        try:
            self._upload_via_shell_chunked(tmp_path, remote_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _upload_via_shell_chunked(self, local_path: str, remote_path: str) -> None:
        """Append base64 chunks via run() then decode (reliable on cqris PTY)."""
        import base64
        import uuid
        from pathlib import Path

        upload_path, is_gz, cleanups = self._maybe_gzip_local(local_path)
        local = Path(upload_path)
        raw_expected = Path(local_path).stat().st_size
        total_raw = local.stat().st_size
        # b64 追加写在 /tmp，避免 NFS 编译目录上 500+ 次 append 极慢或挂死
        bid = uuid.uuid4().hex[:12]
        b64_path = self._remote_temp_join(f"gki_upload_{bid}.b64")
        remote_staging = self._remote_temp_join(
            f"gki_upload_{bid}.patch" + (".gz" if is_gz else ""),
        )
        qb64 = shlex.quote(b64_path)
        qstaging = shlex.quote(remote_staging)
        qremote = shlex.quote(remote_path)
        qerr = shlex.quote(b64_path + ".err")
        chunk_chars = 8_192

        self._prepare_shell_for_upload()
        self._log(
            f"分块上传: {local.name} ({total_raw / 1024 / 1024:.1f} MB"
            f"{', gzip' if is_gz else ''})，暂存 {b64_path}"
        )
        self.run(f"rm -f {qb64} {qstaging} {qerr}", check=False)

        encoded = base64.b64encode(local.read_bytes()).decode("ascii")
        total_b64 = len(encoded)
        n_chunks = (total_b64 + chunk_chars - 1) // chunk_chars if total_b64 else 0
        self._log(f"分块上传: {total_b64 / 1024 / 1024:.1f} MB base64，{n_chunks} 块")

        sent = 0
        last_pct = -1
        t0 = time.time()
        # 单块超 3 分钟视为挂死，触发重试或上层换上传方式
        chunk_timeout = min(180, self.config.command_timeout)
        for i in range(0, total_b64, chunk_chars):
            chunk = encoded[i : i + chunk_chars]
            safe = chunk.replace("'", "'\"'\"'")
            cmd = f"printf '%s' '{safe}' >> {qb64}"
            for attempt in range(3):
                try:
                    self.run(cmd, timeout=chunk_timeout, check=True)
                    break
                except RuntimeError as exc:
                    if attempt >= 2 or "超时" not in str(exc):
                        raise
                    self._log(
                        f"分块上传重试 ({attempt + 2}/3): "
                        f"块 {i // chunk_chars + 1}/{n_chunks} 超时，等待 5s…"
                    )
                    time.sleep(5)
            sent = min(i + chunk_chars, total_b64)
            pct = int(sent * 100 / total_b64) if total_b64 else 100
            if pct >= last_pct + 5 or sent >= total_b64:
                last_pct = pct
                elapsed = time.time() - t0
                self._log(
                    f"分块上传进度: {pct}% ({sent}/{total_b64}) "
                    f"· {elapsed:.0f}s"
                )

        self._log(f"分块上传: base64 解码 → {remote_staging}")
        dec_cmd = f"base64 -d {qb64} > {qstaging} 2>{qerr}"
        self.run(dec_cmd, timeout=max(300, total_raw // 400_000))
        err_r = self.run(f"test -s {qerr} && cat {qerr} || true", check=False, timeout=30)
        if (err_r.stdout or "").strip():
            raise RuntimeError(f"base64 解码失败: {err_r.stdout.strip()[:500]}")
        self.run(f"rm -f {qb64} {qerr}", check=False)

        if is_gz:
            self._log(f"分块上传: gunzip → {remote_path}")
            self.run(
                f"gunzip -c {qstaging} > {qremote} && rm -f {qstaging}",
                timeout=max(300, raw_expected // 400_000),
            )
        else:
            self.run(f"mv {qstaging} {qremote}", check=False)

        remote_size = self._verify_remote_file_size(remote_path, raw_expected)
        self._log(f"远程 patch 就绪: {remote_size / 1024 / 1024:.1f} MB")
        for p in cleanups:
            Path(p).unlink(missing_ok=True)

    def _remote_http_download(self, url: str, remote_dest: str, file_bytes: int) -> None:
        qdest = shlex.quote(remote_dest)
        qurl = shlex.quote(url)
        max_time = max(600, file_bytes // 150_000)
        last_err = ""
        for cmd in (
            f"curl -fsSL --connect-timeout 20 --max-time {max_time} -o {qdest} {qurl}",
            f"wget -q -O {qdest} {qurl}",
        ):
            r = self.run(cmd, check=False, timeout=max_time + 60)
            if r.ok:
                return
            last_err = (r.stdout or "").strip()[:300]
        raise RuntimeError(f"远程下载失败 ({url}): {last_err or 'curl/wget 均失败'}")

    def _finalize_staged_upload(
        self,
        remote_staging: str,
        remote_path: str,
        is_gz: bool,
        raw_expected: int,
    ) -> int:
        qremote = shlex.quote(remote_path)
        qstaging = shlex.quote(remote_staging)
        if is_gz:
            self._log(f"gunzip → {remote_path}")
            self.run(
                f"gunzip -c {qstaging} > {qremote} && rm -f {qstaging}",
                timeout=max(300, raw_expected // 400_000),
            )
        elif remote_staging != remote_path:
            self.run(f"mv {qstaging} {qremote}", check=False)
        return self._verify_remote_file_size(remote_path, raw_expected)

    def _upload_to_bastion_exec_pipe(self, local_path: str, bastion_path: str) -> None:
        if not self._client:
            raise RuntimeError("cqris SSH client 未就绪")
        from pathlib import Path

        total = Path(local_path).stat().st_size
        qb = shlex.quote(bastion_path)
        self._log(f"cqris exec 管道 → {bastion_path} ({total / 1024 / 1024:.1f} MB)")
        stdin, stdout, stderr = self._client.exec_command(
            f"cat > {qb}",
            timeout=self.config.command_timeout,
        )
        sent = 0
        last_pct = -1
        with open(local_path, "rb") as fh:
            while True:
                block = fh.read(256 * 1024)
                if not block:
                    break
                stdin.write(block)
                sent += len(block)
                pct = int(sent * 100 / total) if total else 100
                if pct >= last_pct + 10 or sent >= total:
                    last_pct = pct
                    self._log(f"cqris exec 进度: {pct}%")
        stdin.channel.shutdown_write()
        code = stdout.channel.recv_exit_status()
        err = stderr.read().decode("utf-8", errors="replace")
        if code != 0:
            raise RuntimeError(f"cqris exec 上传失败 (exit={code}): {err[:300]}")

    def _upload_via_bastion_exec_ssh(self, local_path: str, remote_path: str) -> None:
        """Upload to cqris via exec pipe, then pipe to 158 over SSH (no PTY)."""
        import uuid
        from pathlib import Path

        upload_path, is_gz, cleanups = self._maybe_gzip_local(local_path)
        raw_expected = Path(local_path).stat().st_size
        bid = uuid.uuid4().hex[:12]
        bastion_tmp = f"/tmp/gki_{bid}.patch.gz" if is_gz else f"/tmp/gki_{bid}.patch"
        remote_staging = remote_path + (".gz" if is_gz else "")
        try:
            self._upload_to_bastion_exec_pipe(upload_path, bastion_tmp)
            qtmp = shlex.quote(bastion_tmp)
            qdest = shlex.quote(remote_staging)
            quser = shlex.quote(self._target_user)
            qhost = shlex.quote(self._target_ip)
            qpass = shlex.quote(self._target_password)
            self._log(f"cqris exec: SSH 管道写入 158:{remote_staging}")
            pipe_cmd = (
                f"sshpass -p {qpass} ssh -o StrictHostKeyChecking=no "
                f"-o UserKnownHostsFile=/dev/null {quser}@{qhost} "
                f"'cat > {qdest}' < {qtmp} && rm -f {qtmp}"
            )
            _, stdout, stderr = self._client.exec_command(
                pipe_cmd, timeout=self.config.command_timeout,
            )
            code = stdout.channel.recv_exit_status()
            err = stderr.read().decode("utf-8", errors="replace")
            if code != 0:
                self._client.exec_command(f"rm -f {qtmp}", timeout=30)
                raise RuntimeError(
                    f"cqris→158 SSH 管道失败 (exit={code}): {err[:300]}"
                )
            size = self._finalize_staged_upload(
                remote_staging, remote_path, is_gz, raw_expected,
            )
            self._log(f"远程 patch 就绪: {size / 1024 / 1024:.1f} MB")
        finally:
            for p in cleanups:
                Path(p).unlink(missing_ok=True)

    def _upload_via_bastion_http(self, local_path: str, remote_path: str) -> None:
        """Upload to cqris, serve via python http.server, curl from 158."""
        import random
        import uuid
        from pathlib import Path

        upload_path, is_gz, cleanups = self._maybe_gzip_local(local_path)
        raw_expected = Path(local_path).stat().st_size
        port = random.randint(18080, 18999)
        bid = uuid.uuid4().hex[:12]
        fname = f"gki_{bid}.patch.gz" if is_gz else f"gki_{bid}.patch"
        bastion_tmp = f"/tmp/{fname}"
        remote_staging = remote_path + (".gz" if is_gz else "")
        pid = ""
        try:
            self._upload_to_bastion_exec_pipe(upload_path, bastion_tmp)
            host = self.config.bastion_host
            self._log(f"cqris 临时 HTTP :{port} 提供 {fname}")
            _, stdout, _ = self._client.exec_command(
                f"nohup python3 -m http.server {port} --bind 0.0.0.0 --directory /tmp "
                f">/tmp/gki_http_{port}.log 2>&1 & echo $!",
                timeout=30,
            )
            pid = (stdout.read().decode("utf-8", errors="replace") or "").strip()
            if pid:
                pid = pid.splitlines()[-1].strip()
            time.sleep(1.5)
            url = f"http://{host}:{port}/{fname}"
            self._log(f"158 curl ← {url}")
            self._remote_http_download(url, remote_staging, Path(upload_path).stat().st_size)
            size = self._finalize_staged_upload(
                remote_staging, remote_path, is_gz, raw_expected,
            )
            self._log(f"远程 patch 就绪: {size / 1024 / 1024:.1f} MB")
        finally:
            if pid:
                self._client.exec_command(
                    f"kill {shlex.quote(pid)} 2>/dev/null; "
                    f"pkill -f 'http.server {port}' 2>/dev/null; "
                    f"rm -f {shlex.quote(bastion_tmp)}",
                    timeout=20,
                )
            for p in cleanups:
                Path(p).unlink(missing_ok=True)

    def _upload_via_local_http(self, local_path: str, remote_path: str) -> None:
        """Windows/Linux: temporary HTTP server; 158 curls the patch."""
        from pathlib import Path

        from web_app.patch_upload_server import serve_patch_temporarily

        upload_path, is_gz, cleanups = self._maybe_gzip_local(local_path)
        raw_expected = Path(local_path).stat().st_size
        remote_staging = remote_path + (".gz" if is_gz else "")
        cfg = self.config
        try:
            with serve_patch_temporarily(
                Path(upload_path),
                port=cfg.upload_http_port,
                bind=cfg.upload_http_bind,
            ) as info:
                urls = info.get("urls") or []
                ips = info.get("host_ips") or []
                port = info.get("port")
                try_urls = [
                    u for u in urls
                    if "127.0.0.1" not in u and "localhost" not in u
                ]
                if not try_urls:
                    try_urls = list(urls)
                self._log(
                    f"本机临时 HTTP :{port}（158 需能访问以下 IP 之一: "
                    f"{', '.join(ips) or '见 URL'}）"
                )
                for u in urls:
                    self._log(f"  下载 URL: {u}")
                self._log(
                    "若失败：检查 Windows 防火墙是否放行该端口，"
                    "或确认 158 与办公网互通"
                )
                last_exc: Optional[Exception] = None
                for url in try_urls:
                    try:
                        self._log(f"158 尝试 curl ← {url}")
                        self._remote_http_download(
                            url, remote_staging, Path(upload_path).stat().st_size,
                        )
                        last_exc = None
                        break
                    except Exception as exc:
                        last_exc = exc
                        self._log(f"  失败: {exc}")
                if last_exc:
                    raise last_exc
            size = self._finalize_staged_upload(
                remote_staging, remote_path, is_gz, raw_expected,
            )
            self._log(f"远程 patch 就绪: {size / 1024 / 1024:.1f} MB")
        finally:
            for p in cleanups:
                Path(p).unlink(missing_ok=True)

    def _upload_via_bastion_sftp(self, local_path: str, remote_path: str) -> None:
        """Upload to cqris /tmp then scp to target via cqris exec (when direct-tcpip is blocked)."""
        import uuid
        from pathlib import Path

        if not self._client or not self._target_ip:
            raise RuntimeError("cqris 会话未就绪")
        upload_path, is_gz, cleanups = self._maybe_gzip_local(local_path)
        raw_expected = Path(local_path).stat().st_size
        bid = uuid.uuid4().hex[:12]
        bastion_tmp = f"/tmp/gki_{bid}.patch.gz" if is_gz else f"/tmp/gki_{bid}.patch"
        remote_staging = remote_path + (".gz" if is_gz else "")
        local = Path(upload_path)
        total = local.stat().st_size
        self._log(f"经 cqris 中转: 上传到 {bastion_tmp} ({total / 1024 / 1024:.1f} MB)…")
        sftp = self._client.open_sftp()
        last_pct = -1
        try:
            def _cb(done: int, total_bytes: int) -> None:
                nonlocal last_pct
                pct = int(done * 100 / total_bytes) if total_bytes else 0
                if pct >= last_pct + 5 or done >= total_bytes:
                    last_pct = pct
                    self._log(f"cqris SFTP 进度: {pct}% ({done}/{total_bytes} 字节)")

            sftp.put(upload_path, bastion_tmp, callback=_cb)
        finally:
            sftp.close()

        qtmp = shlex.quote(bastion_tmp)
        qremote = shlex.quote(remote_staging)
        quser = shlex.quote(self._target_user)
        qhost = shlex.quote(self._target_ip)
        qpass = shlex.quote(self._target_password)
        self._log(f"经 cqris 中转: scp → {self._target_ip}:{remote_staging}")
        scp_cmd = (
            f"sshpass -p {qpass} scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "
            f"{qtmp} {quser}@{qhost}:{qremote} "
            f"&& rm -f {qtmp}"
        )
        stdin, stdout, stderr = self._client.exec_command(scp_cmd, timeout=self.config.command_timeout)
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        if exit_code != 0:
            self._client.exec_command(f"rm -f {qtmp}", timeout=30)
            raise RuntimeError(
                f"cqris scp 到目标机失败 (exit={exit_code}): {(err or out).strip()[:300]}"
            )
        try:
            size = self._finalize_staged_upload(
                remote_staging, remote_path, is_gz, raw_expected,
            )
            self._log(f"远程 patch 就绪: {size / 1024 / 1024:.1f} MB")
        finally:
            for p in cleanups:
                Path(p).unlink(missing_ok=True)

    def _open_target_sftp(self) -> Tuple[paramiko.SSHClient, Any]:
        if not self._client or not self._target_ip:
            raise RuntimeError("目标机 SSH 信息未就绪")
        transport = self._client.get_transport()
        if not transport or not transport.is_active():
            raise RuntimeError("cqris 传输通道未激活")
        self._log(f"经 cqris 打开到 {self._target_ip}:22 的 SFTP 通道…")
        sock = transport.open_channel(
            "direct-tcpip",
            (self._target_ip, 22),
            ("127.0.0.1", 0),
            timeout=self.config.connect_timeout,
        )
        tclient = paramiko.SSHClient()
        tclient.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        tclient.connect(
            hostname=self._target_ip,
            username=self._target_user,
            password=self._target_password,
            sock=sock,
            look_for_keys=False,
            allow_agent=False,
            timeout=self.config.connect_timeout,
            banner_timeout=self.config.connect_timeout,
            auth_timeout=self.config.connect_timeout,
        )
        return tclient, tclient.open_sftp()

    def _upload_local_file_sftp(self, local_path: str, remote_path: str) -> None:
        from pathlib import Path

        local = Path(local_path)
        total = local.stat().st_size
        self._log(f"SFTP 上传: {local.name} ({total / 1024 / 1024:.1f} MB) -> {remote_path}")
        tclient, sftp = self._open_target_sftp()
        last_pct = -1
        try:
            def _cb(done: int, total_bytes: int) -> None:
                nonlocal last_pct
                pct = int(done * 100 / total_bytes) if total_bytes else 0
                if pct >= last_pct + 5 or done >= total_bytes:
                    last_pct = pct
                    self._log(f"SFTP 上传进度: {pct}% ({done}/{total_bytes} 字节)")

            sftp.put(local_path, remote_path, callback=_cb)
        finally:
            sftp.close()
            tclient.close()

    def upload_local_file(self, local_path: str, remote_path: str) -> None:
        from pathlib import Path

        local = Path(local_path)
        if not local.is_file():
            raise FileNotFoundError(f"本地文件不存在: {local_path}")
        size_mb = local.stat().st_size / (1024 * 1024)
        self._log(
            f"准备上传 patch ({size_mb:.1f} MB) -> {remote_path}"
        )
        strategies: List[Tuple[str, Any]] = []
        if self._client and self._target_ip:
            strategies.extend([
                ("cqris exec + SSH 管道", self._upload_via_bastion_exec_ssh),
                ("cqris SFTP + scp", self._upload_via_bastion_sftp),
                ("cqris 临时 HTTP", self._upload_via_bastion_http),
            ])
        strategies.append(("SSH shell 分块（兜底）", self._upload_via_shell_chunked))

        errors: List[str] = []
        for name, upload_fn in strategies:
            self._log(f"尝试上传方式: {name}")
            try:
                upload_fn(local_path, remote_path)
                self._log(f"上传完成 ({name}): {remote_path}")
                return
            except Exception as exc:
                msg = str(exc).strip() or type(exc).__name__
                self._log(f"{name} 失败: {msg[:400]}")
                errors.append(f"{name}: {msg[:200]}")
                self._recover_shell()
        raise RuntimeError(
            "patch 上传失败，已尝试: "
            + "; ".join(errors[:4])
        )

    def diagnose_repo(self, repo_dir: str) -> Tuple[bool, str]:
        """Check remote path exists and is a git work tree; return (ok, detail)."""
        q = shlex.quote(repo_dir.rstrip("/"))
        lines: List[str] = []
        r_exist = self.run(f"test -d {q} && echo EXISTS || echo MISSING", check=False)
        exist = r_exist.stdout.strip()
        lines.append(f"路径检测 ({repo_dir}): {exist or '(无输出)'}")
        if exist != "EXISTS":
            r_pwd = self.run("pwd", check=False)
            if r_pwd.stdout.strip():
                lines.append(f"远程当前目录: {r_pwd.stdout.strip()}")
            r_ls = self.run(f"ls -ld {q} 2>&1 || true", check=False)
            if r_ls.stdout.strip():
                lines.append(f"ls: {r_ls.stdout.strip()}")
            return False, "\n".join(lines)

        r_git = self.run(
            f"git -C {q} rev-parse --is-inside-work-tree 2>&1",
            check=False,
        )
        inside = r_git.stdout.strip()
        if inside.lower() == "true":
            return True, ""
        lines.append(f"git rev-parse --is-inside-work-tree: {inside or '(无输出)'}")
        r_gitdir = self.run(f"git -C {q} rev-parse --git-dir 2>&1", check=False)
        if r_gitdir.stdout.strip():
            lines.append(f"git rev-parse --git-dir: {r_gitdir.stdout.strip()}")
        r_dotgit = self.run(
            f"test -e {q}/.git -o -f {q}/.git && echo DOTGIT_OK || echo DOTGIT_NO",
            check=False,
        )
        lines.append(f".git 存在: {r_dotgit.stdout.strip() or '(无输出)'}")
        return False, "\n".join(lines)

    def test_repo(self, repo_dir: str) -> bool:
        ok, _ = self.diagnose_repo(repo_dir)
        return ok
