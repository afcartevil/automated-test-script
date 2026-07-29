"""
Reliable probe for "is this endpoint our company's service?"
- Only probes the provided host:port entries (no network-wide scanning).
- Probes: TCP connect, HTTP(S) GET (optional path), HTTPS certificate SAN check,
  optional response token/header check.
- Produces a score and evidence list; caller decides threshold for 'ours'.
"""
import platform
import re
import subprocess
import time
from typing import List, Dict, Any, Optional, Tuple, Union
import socket
import ssl
import http.client
import json
import hashlib

# Tunables / weights
WEIGHTS = {
    "tcp_connect": 1,  # can connect
    "http_ok": 2,  # got HTTP 200
    "http_token": 6,  # response contains expected token (very strong)
    "http_header": 5,  # header contains expected header/value
    "tls_san_match": 4,  # cert SAN contains our domain
    "tls_cert_fingerprint": 5,  # cert fingerprint matches expected
}

DEFAULT_THRESHOLD = 6  # score >= => conclude "ours"


def _tcp_connect(host: str, port: int, timeout: float = 0.8) -> Tuple[bool, Optional[str]]:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True, None
    except Exception as e:
        return False, str(e)


def _tls_peek_cert(host: str, port: int, timeout: float = 1.0) -> Tuple[Optional[dict], Optional[bytes], Optional[str]]:
    """
    Return (peer_cert_dict, cert_der_bytes, error)
    peer_cert_dict = ssock.getpeercert(binary_form=False) (subject, SANs, etc)
    cert_der_bytes = ssock.getpeercert(binary_form=True)
    """
    context = ssl.create_default_context()
    # we intentionally do not verify hostname here; we'll inspect cert manually
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                # This may raise if handshake fails
                cert = ssock.getpeercert(binary_form=False)
                cert_der = ssock.getpeercert(binary_form=True)
                return cert, cert_der, None
    except Exception as e:
        return None, None, str(e)


def _cert_der_fingerprint(cert_der: bytes, algo: str = "sha256") -> str:
    if cert_der is None:
        return ""
    h = hashlib.new(algo, cert_der).hexdigest()
    return h


def _http_get(host: str, port: int, path: str = "/", use_https: bool = False, timeout: float = 1.0) -> Tuple[
    Optional[int], Dict[str, str], Optional[str], Optional[str]]:
    """
    returns (status, headers_dict, body_snippet, error)
    body_snippet is first ~1024 bytes of body decoded as utf-8 (errors ignored)
    """
    try:
        conn_cls = http.client.HTTPSConnection if use_https else http.client.HTTPConnection
        conn = conn_cls(host, port, timeout=timeout)
        conn.request("GET", path, headers={"User-Agent": "probe-client/1.0"})
        resp = conn.getresponse()
        status = resp.status
        headers = {k.lower(): v for k, v in resp.getheaders()}
        raw = resp.read(4096)
        conn.close()
        try:
            body = raw.decode("utf-8", errors="ignore")
        except Exception:
            body = None
        snippet = body[:1024] if body else None
        return status, headers, snippet, None
    except Exception as e:
        return None, {}, None, str(e)


def probe_endpoints_for_ours(
        endpoints: List[Dict[str, Any]],
        *,
        expected_domains: Optional[List[str]] = None,
        expected_cert_fingerprints: Optional[List[str]] = None,
        expected_http_token: Optional[str] = None,
        expected_http_header: Optional[Tuple[str, str]] = None,
        timeout: float = 1.0,
        threshold: int = DEFAULT_THRESHOLD,
) -> Dict[str, Any]:
    """
    endpoints: list of dicts: {"host": "...", "port": 443, "protocol": "https"|"http"|"tcp", "path": "/health" (optional)}
      protocol guides whether to do HTTPS/HTTP probes; if protocol=="tcp" do only TCP/TLS peek if port==443 attempt TLS.
    expected_domains: list of domain substrings (e.g. ["corp.example.com"]) to match against cert SAN or DNS.
    expected_cert_fingerprints: list of lower-hex fingerprints (sha256 hex) to compare against cert DER.
    expected_http_token: a token string expected to appear in HTTP body (strong evidence).
    expected_http_header: tuple (header_name_lower, expected_value_substring)
    """
    expected_domains = expected_domains or []
    expected_cert_fingerprints = [fp.lower() for fp in (expected_cert_fingerprints or [])]

    report = {"endpoints": [], "total_score": 0, "conclusion": "unknown", "threshold": threshold}

    total_score = 0
    evidence = []

    for ep in endpoints:
        host = ep["host"]
        port = int(ep.get("port", 443))
        protocol = ep.get("protocol", None)  # "https" | "http" | "tcp" | None
        path = ep.get("path", "/")
        ep_name = f"{host}:{port}"
        ep_report = {"endpoint": ep_name, "checks": [], "score": 0}
        ep_score = 0

        # 1) TCP connect
        ok, err = _tcp_connect(host, port, timeout=timeout)
        ep_report["checks"].append({"tcp_connect": ok, "error": err})
        if ok:
            ep_score += WEIGHTS["tcp_connect"]

        # 2) TLS cert peek if TLS-ish port or protocol indicates https
        want_tls = (protocol == "https") or (port in (443, 8443))
        cert = None
        cert_der = None
        if want_tls:
            cert, cert_der, cert_err = _tls_peek_cert(host, port, timeout=timeout)
            ep_report["checks"].append({"tls_peek_error": cert_err})
            if cert:
                # parse SANs if present
                sans = []
                try:
                    san = cert.get("subjectAltName", ())
                    for t, v in san:
                        if t.lower() == "dns":
                            sans.append(v)
                except Exception:
                    pass
                subj = cert.get("subject", ())
                ep_report["checks"].append({"tls_subject": subj, "tls_san": sans})
                # check expected_domains in SANs or subject CN
                found_san_match = False
                for d in expected_domains:
                    for s in sans:
                        if d in s:
                            found_san_match = True
                            break
                    if found_san_match:
                        break
                # also check commonName
                if not found_san_match:
                    try:
                        for at in subj:
                            for k, v in at:
                                if k.lower() in ("commonname", "common_name", "cn"):
                                    for d in expected_domains:
                                        if d in v:
                                            found_san_match = True
                                            break
                                    if found_san_match:
                                        break
                            if found_san_match:
                                break
                    except Exception:
                        pass
                if found_san_match:
                    ep_report["checks"].append({"tls_san_match": True})
                    ep_score += WEIGHTS["tls_san_match"]

                # fingerprint check (sha256 of cert DER)
                if cert_der:
                    fp = _cert_der_fingerprint(cert_der, algo="sha256")
                    ep_report["checks"].append({"tls_cert_fingerprint_sha256": fp})
                    if fp.lower() in expected_cert_fingerprints:
                        ep_report["checks"].append({"tls_cert_fingerprint_match": True})
                        ep_score += WEIGHTS["tls_cert_fingerprint"]

        # 3) HTTP(S) probe if requested
        if protocol in ("http", "https") or (protocol is None and port in (80, 443, 8080, 8443)):
            use_https = (protocol == "https") or (port in (443, 8443))
            status, headers, body_snip, http_err = _http_get(host, port, path=path, use_https=use_https,
                                                             timeout=timeout)
            ep_report["checks"].append({"http_status": status, "http_error": http_err})
            if status and 200 <= status < 300:
                ep_score += WEIGHTS["http_ok"]
            # check token in body
            if body_snip and expected_http_token:
                if expected_http_token in body_snip:
                    ep_report["checks"].append({"http_token_present": True})
                    ep_score += WEIGHTS["http_token"]
            # check header
            if headers and expected_http_header:
                hn, hv_sub = expected_http_header
                hv = headers.get(hn.lower())
                if hv and hv_sub in hv:
                    ep_report["checks"].append({"http_header_match": {hn: hv}})
                    ep_score += WEIGHTS["http_header"]

        ep_report["score"] = ep_score
        report["endpoints"].append(ep_report)
        total_score += ep_score
        # add evidence summary
        evidence.append((ep_name, ep_score, ep_report["checks"]))

    report["total_score"] = total_score
    report["evidence"] = evidence

    # decision: if any endpoint provides enough score alone OR total_score >= threshold
    any_strong = any(ep["score"] >= threshold for ep in report["endpoints"])
    if any_strong or total_score >= threshold:
        report["conclusion"] = "ours"
    else:
        report["conclusion"] = "not_ours" if total_score == 0 else "unknown"

    return report


def ping_host(host: str, count: int = 1, timeout_sec: float = 1.0) -> Dict[str, Any]:
    """
    Ping host once (or multiple times). Cross-platform helper.

    返回 dict:
      {
        "host": host,
        "success": True/False,
        "avg_ms": float or None,
        "raw": <raw output str>,
        "returncode": int
      }

    说明:
      - count: ping 次数（通常 1 就够做启发式判断）
      - timeout_sec: subprocess 超时（秒），整个 ping 命令必须在这个时间内返回
    """
    system = platform.system().lower()
    if system.startswith("win"):
        cmd = ["ping", "-n", str(count), host]
    else:
        # Unix/macOS: use -c count (count), rely on subprocess timeout for overall timing
        cmd = ["ping", "-c", str(count), host]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec
        )
        out = proc.stdout + (proc.stderr or "")
        rc = proc.returncode
        success = (rc == 0)

        # try parse avg RTT robustly
        avg_ms: Optional[float] = None

        # Linux-like: look for "rtt min/avg/max/mdev = X/Y/Z/W ms"
        m = re.search(r"rtt [\w/]+ = [\d\.]+/([\d\.]+)/", out)
        if m:
            try:
                avg_ms = float(m.group(1))
            except Exception:
                avg_ms = None

        # macOS sometimes: "round-trip min/avg/max/stddev = X/X/X/X ms"
        if avg_ms is None:
            m2 = re.search(r"round-trip [\w/ =]+/([\d\.]+)/", out)
            if m2:
                try:
                    avg_ms = float(m2.group(1))
                except Exception:
                    avg_ms = None

        # Windows: look for "Average = 12ms"
        if avg_ms is None:
            m3 = re.search(r"Average = ([\d]+)ms", out)
            if m3:
                try:
                    avg_ms = float(m3.group(1))
                except Exception:
                    avg_ms = None

        # Another Windows variant (localized) -- try more general "平均 = " for some locales?
        # We avoid locale-specific parsers here; raw output is returned for debugging.

        return {"host": host, "success": success, "avg_ms": avg_ms, "raw": out, "returncode": rc}
    except subprocess.TimeoutExpired as e:
        # command timed out (treat as failure)
        out = (e.stdout or "") + (e.stderr or "")
        return {"host": host, "success": False, "avg_ms": None, "raw": out, "returncode": -1}
    except FileNotFoundError:
        # ping command not found on system
        return {"host": host, "success": False, "avg_ms": None, "raw": "ping command not found", "returncode": -2}
    except Exception as e:
        return {"host": host, "success": False, "avg_ms": None, "raw": f"error: {e}", "returncode": -3}


def ping_until_available(
    host: str,
    *,
    max_retries: int = 5,
    count: int = 1,
    timeout_sec: float = 1.0,
    interval: float = 0.5,
    backoff: float = 1.0,
    return_details: bool = False
) -> Union[bool, Dict[str, Any]]:
    """
    多次 ping 主机，直到某次成功或达到最大重试次数。

    参数:
      host: 要 ping 的主机（域名或 IP）
      max_retries: 最多尝试次数（>=1）
      count: 单次 ping 调用的 ICMP 包数（传入 ping_host 的 count）
      timeout_sec: 每次 ping 调用的超时时间（秒）
      interval: 两次尝试之间的初始等待时间（秒）
      backoff: 指数回退因子；每次重试后 interval *= backoff（backoff>=1.0）
      return_details: 若 True 返回 dict 含详细尝试记录，否则仅返回 bool

    返回:
      如果 return_details=False -> 返回 bool（True 表示某次 ping 成功）
      如果 return_details=True  -> 返回 dict:
        {
          "available": bool,
          "attempts": [ <ping_host 返回的 dict> ],
          "attempt_count": int
        }
    """
    if max_retries < 1:
        raise ValueError("max_retries must be >= 1")

    attempts: List[Dict[str, Any]] = []
    cur_interval = float(interval)

    for attempt in range(1, max_retries + 1):
        try:
            # call ping_host (assumed available)
            res = ping_host(host, count=count, timeout_sec=timeout_sec)
        except Exception as e:
            # 如果 ping_host 本身抛异常，也保存异常信息并继续（或返回）
            res = {"host": host, "success": False, "avg_ms": None, "raw": f"ping_host exception: {e}", "returncode": -9}

        attempts.append(res)

        if bool(res.get("success")):
            if return_details:
                return {"available": True, "attempts": attempts, "attempt_count": attempt}
            return True

        # 未成功且仍需重试
        if attempt < max_retries:
            # sleep 可被 KeyboardInterrupt 中断
            try:
                time.sleep(cur_interval)
            except KeyboardInterrupt:
                # 中断时直接返回失败并把当前尝试历史返回
                if return_details:
                    return {"available": False, "attempts": attempts, "attempt_count": attempt, "interrupted": True}
                return False
            # 指数回退
            cur_interval *= max(1.0, float(backoff))

    # 全部尝试完仍未成功
    if return_details:
        return {"available": False, "attempts": attempts, "attempt_count": max_retries}
    return False


_is_transsion_network = None


def is_transsion_network(forced_recheck: bool = True):
    global _is_transsion_network
    if _is_transsion_network is None or forced_recheck:
        _transsion_internal_host = 'gitlab.transsion.com'
        _is_transsion_network = ping_until_available(_transsion_internal_host, interval=0.25, return_details=True)
    return _is_transsion_network


# ----------------------------------------------------------------


def _demo():
    endpoints = [
        {"host": "gitlab.transsion.com", "port": 80, "protocol": "http", "path": ""},
    ]

    res = probe_endpoints_for_ours(
        endpoints,
        expected_domains=["corp.example"],
        expected_cert_fingerprints=["<sha256-hex-of-cert>"],  # optional
        expected_http_token="CORP_HEALTH_TOKEN_v1",
        expected_http_header=("x-company", "our-company"),
        timeout=1.0,
        threshold=6,
    )
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    _demo()
