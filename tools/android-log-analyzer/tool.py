"""Android Log Analyzer - 解析logcat/ril/atcmd日志"""
from typing import Optional
import re

class AndroidLogAnalyzer:
    ERROR_PATTERNS = [
        (r".*Exception.*", "Java Exception"),
        (r".*FATAL EXCEPTION.*", "Fatal Exception"),
        (r".*Error.*", "Error"),
        (r".*FAIL.*", "Failure"),
        (r".*panic.*", "Kernel Panic"),
        (r".*BUG:.*", "Kernel Bug"),
    ]
    TELEPHONY_PATTERNS = [
        (r".*RILJ.*", "RILJ Event"),
        (r".*RILC.*", "RILC Event"),
        (r".*RILD.*", "RILD Event"),
        (r".*TelephonyFramework.*", "Telephony Framework"),
        (r".*PhoneInterfaceManager.*", "Phone Interface"),
        (r".*ATCMD.*", "AT Command"),
        (r".*MODEM.*", "Modem Event"),
        (r".*IMS.*", "IMS Event"),
        (r".*VoLTE.*", "VoLTE Event"),
        (r".*ServiceState.*", "Service State Change"),
    ]

    def __init__(self):
        self.events = []
        self.errors = []

    def parse(self, log_content: str, log_type: str = "logcat", filters: Optional[list] = None) -> dict:
        self.events, self.errors = [], []
        for line_num, line in enumerate(log_content.strip().split("\n"), 1):
            for pattern, label in self.ERROR_PATTERNS:
                if re.match(pattern, line):
                    self.errors.append({"line": line_num, "content": line.strip(), "type": label})
            if log_type in ("logcat", "ril"):
                for pattern, label in self.TELEPHONY_PATTERNS:
                    if re.match(pattern, line):
                        self.events.append({"line": line_num, "content": line.strip(), "type": label})
        if filters:
            fl = [f.lower() for f in filters]
            self.events = [e for e in self.events if any(f in e["content"].lower() for f in fl)]
            self.errors = [e for e in self.errors if any(f in e["content"].lower() for f in fl)]
        return {"events": self.events, "errors": self.errors,
                "statistics": {"total_lines": len(log_content.split("\n")), "event_count": len(self.events), "error_count": len(self.errors), "log_type": log_type}}

def handle_analyze(params: dict) -> dict:
    return AndroidLogAnalyzer().parse(params.get("log_content", ""), params.get("log_type", "logcat"), params.get("filters"))
