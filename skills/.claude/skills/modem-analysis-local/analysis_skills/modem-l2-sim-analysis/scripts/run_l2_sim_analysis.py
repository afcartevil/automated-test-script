#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
L2 SIM 卡业务分析脚本 — 独立实现

基于 references/ 中的分析规则，实现 5 步 SIM 卡深度分析：
1. ATR 响应检测（硬件问题）
2. AT+ESIMS 序列解析
3. updateSimState 状态流转
4. 特殊场景检测（PIN/eSIM/Modem crash/救卡）
5. 综合分类与输出
"""

import argparse
import json
import os
import re
import sys
from copy import deepcopy
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHARED_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, "..", "..", "_shared"))
if SHARED_DIR not in sys.path:
    sys.path.insert(0, SHARED_DIR)

from modem_analysis_runtime import (
    configure_stdio, load_manifest, save_manifest, setup_skill_logger,
    discover_log_groups, select_primary_group,
    parse_occurrence_times, seconds_of_day, parse_line_timestamp, trim_text,
)

# ---------------------------------------------------------------------------
# 正则
# ---------------------------------------------------------------------------
RE_ESIMS = re.compile(
    r"(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[\.\d]*)"
    r".*handleSimStateChanged.*\+ESIMS\s*:\s*(?P<inserted>[01])\s*,\s*(?P<cause>\d+)",
    re.IGNORECASE,
)
RE_UPDATE_SIM_STATE = re.compile(
    r"(?P<stamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[\.\d]*)"
    r".*updateSimState.*?(?:slot\s*(?P<slot>[01]))?\s*[:,]?\s*"
    r"(?P<state>ABSENT|UNKNOWN|READY|LOADED|PIN_REQUIRED|PUK_REQUIRED|CARD_IO_ERROR|CARD_RESTRICTED|NOT_READY)",
    re.IGNORECASE,
)
RE_ATR_ERROR = re.compile(r"AnswerToReset.*(?:must at least|invalid|fail)", re.IGNORECASE)
RE_ATR_OK = re.compile(r"(?:AnswerToReset.*received successfully|\[SIM\]ATR:\s*3[Bb])", re.IGNORECASE)
RE_NO_ATR = re.compile(r"\[SIM_DRV:(?P<slot>[01])\].*\[ERR\].*No ATR", re.IGNORECASE)
RE_ESIM_IGNORE = re.compile(r"eSIM\s+ignore\s+hot\s*plug", re.IGNORECASE)
RE_SIM_ERROR_IND = re.compile(r"MSG_ID_SIM_ERROR_IND", re.IGNORECASE)
RE_MODEM_CRASH = re.compile(r"\b(?:Assert|Fatal\s*error|ModemEE|PhoneCrash)\b", re.IGNORECASE)
RE_SIM_SLOT = re.compile(r"\[SIM_DRV:(?P<slot>[01])\]", re.IGNORECASE)

ESIMS_CAUSE_MAP = {
    0: "SIM_CARD_REMOVED", 1: "SIM_ACCESS_ERROR",
    11: "SIM_PLUG_OUT", 12: "SIM_PLUG_IN",
    13: "SIM_RECOVERY_START", 14: "SIM_RECOVERY_END",
    29: "SIM_DETECTED",
}

def _ts(line):
    m = re.match(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)", line or "")
    if not m:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(m.group(1), fmt)
        except ValueError:
            pass
    return None


# ---------------------------------------------------------------------------
# 日志加载
# ---------------------------------------------------------------------------
def _read_lines(path):
    if not path or not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.readlines()


def load_all_lines(group):
    """加载 trace 文件 + radio_log + main_log（支持文件或目录）"""
    lines = {}
    for name, path in (group.get("files") or {}).items():
        lines[name] = _read_lines(path)
    # support files (radio_log / main_log — 可能是文件或目录)
    group_path = group.get("path", "")
    for sub in ("radio_log", "main_log"):
        p = os.path.join(group_path, sub)
        if os.path.isfile(p):
            lines[sub] = _read_lines(p)
        elif os.path.isdir(p):
            combined = []
            for fn in sorted(os.listdir(p)):
                fp = os.path.join(p, fn)
                if os.path.isfile(fp):
                    combined.extend(_read_lines(fp))
            if combined:
                lines[sub] = combined
    return lines


# ---------------------------------------------------------------------------
# 步骤 1: ATR 响应检测
# ---------------------------------------------------------------------------
def detect_atr(lines_map):
    atr = {"slot_0": "unknown", "slot_1": "unknown"}
    evidence = []

    search_in = []
    for key in ("main_log", "radio_log", "system", "ps"):
        search_in.extend([(key, l) for l in lines_map.get(key, [])])

    for src, line in search_in:
        if RE_ATR_ERROR.search(line):
            slot_m = RE_SIM_SLOT.search(line)
            slot = int(slot_m.group("slot")) if slot_m else 0
            atr[f"slot_{slot}"] = "failed"
            evidence.append({"type": "atr_error", "content": trim_text(line),
                             "log_file": src, "timestamp": (_ts(line) or "").isoformat() if _ts(line) else "",
                             "relevance": "high"})
        elif RE_ATR_OK.search(line):
            slot_m = RE_SIM_SLOT.search(line)
            slot = int(slot_m.group("slot")) if slot_m else 0
            atr[f"slot_{slot}"] = "success"

    for src, line in search_in:
        m = RE_NO_ATR.search(line)
        if m:
            slot = int(m.group("slot"))
            atr[f"slot_{slot}"] = "failed"
            evidence.append({"type": "atr_error", "content": trim_text(line),
                             "log_file": src, "timestamp": (_ts(line) or "").isoformat() if _ts(line) else "",
                             "relevance": "high"})
    return atr, evidence


# ---------------------------------------------------------------------------
# 步骤 2: AT+ESIMS 序列解析
# ---------------------------------------------------------------------------
def parse_esims_sequence(lines_map):
    seq = []
    for key in ("radio_log", "main_log", "ps", "system"):
        for line in lines_map.get(key, []):
            m = RE_ESIMS.search(line)
            if not m:
                continue
            ts = _ts(line)
            inserted = int(m.group("inserted"))
            cause = int(m.group("cause"))
            slot_m = RE_SIM_SLOT.search(line)
            slot = int(slot_m.group("slot")) if slot_m else None
            seq.append({
                "timestamp": ts.isoformat() if ts else "",
                "slot": slot,
                "inserted_status": inserted,
                "cause": cause,
                "interpretation": ESIMS_CAUSE_MAP.get(cause, f"UNKNOWN({cause})"),
                "_dt": ts,
            })
    seq.sort(key=lambda x: x.get("_dt") or datetime.min)
    for item in seq:
        item.pop("_dt", None)
    return seq


def analyze_esims_patterns(seq):
    """识别关键模式：不识卡、救卡、热插拔异常"""
    patterns = []
    for i, cur in enumerate(seq):
        cause = cur["cause"]
        # 规则 1: +ESIMS:1,29 后紧跟 +ESIMS:0,1 → 不识卡
        if cause == 29 and cur["inserted_status"] == 1 and i + 1 < len(seq):
            nxt = seq[i + 1]
            if nxt["cause"] == 1 and nxt["inserted_status"] == 0:
                patterns.append("DETECT_AFTER_ERROR")
        # 规则 3: 救卡 +ESIMS:0,13
        if cause == 13 and cur["inserted_status"] == 0:
            # 查找后续 +ESIMS:1,14
            found_end = any(s["cause"] == 14 and s["inserted_status"] == 1
                           for s in seq[i + 1: i + 10])
            patterns.append("RECOVERY_SUCCESS" if found_end else "RECOVERY_FAILED")
    return patterns


# ---------------------------------------------------------------------------
# 步骤 3: updateSimState 状态流转
# ---------------------------------------------------------------------------
def parse_state_flow(lines_map):
    flow = {"slot_0": [], "slot_1": []}
    for key in ("main_log", "radio_log", "ps", "system"):
        for line in lines_map.get(key, []):
            m = RE_UPDATE_SIM_STATE.search(line)
            if not m:
                continue
            ts = _ts(line)
            state = m.group("state").upper()
            slot_str = m.group("slot")
            slot = int(slot_str) if slot_str else 0
            slot_key = f"slot_{slot}"
            flow[slot_key].append({
                "timestamp": ts.isoformat() if ts else "",
                "state": state,
                "_dt": ts,
            })
    for slot_key in flow:
        flow[slot_key].sort(key=lambda x: x.get("_dt") or datetime.min)
        for item in flow[slot_key]:
            item.pop("_dt", None)
    return flow


def detect_state_anomalies(flow):
    """检测异常状态"""
    anomalies = []
    for slot_key, states in flow.items():
        for s in states:
            st = s["state"]
            if st in ("CARD_IO_ERROR", "UNKNOWN", "PUK_REQUIRED"):
                anomalies.append({"slot": slot_key, "state": st, "timestamp": s["timestamp"]})
        # 检测掉卡: LOADED/READY → ABSENT 且无 PLUG_OUT
        for i in range(1, len(states)):
            prev, cur = states[i - 1], states[i]
            if prev["state"] in ("LOADED", "READY") and cur["state"] == "ABSENT":
                anomalies.append({"slot": slot_key, "state": "DROP_CARD",
                                  "timestamp": cur["timestamp"]})
    return anomalies


# ---------------------------------------------------------------------------
# 步骤 4: 特殊场景检测
# ---------------------------------------------------------------------------
def detect_special_scenarios(lines_map, state_flow):
    special = {
        "pin_lock": {"detected": False, "slot": None},
        "esim_conflict": {"detected": False, "slot": None},
        "modem_crash": {"detected": False, "crash_type": None},
        "recovery_process": {"triggered": False, "success": False, "duration": None},
    }

    # PIN 锁
    for slot_key, states in state_flow.items():
        for s in states:
            if s["state"] == "PIN_REQUIRED":
                special["pin_lock"]["detected"] = True
                special["pin_lock"]["slot"] = int(slot_key[-1])
                break

    # eSIM 占用
    all_lines = []
    for key in ("radio_log", "main_log", "ps", "system"):
        all_lines.extend(lines_map.get(key, []))
    for line in all_lines:
        if RE_ESIM_IGNORE.search(line):
            special["esim_conflict"]["detected"] = True
            special["esim_conflict"]["slot"] = 1
            break

    # Modem crash
    for line in all_lines:
        m = RE_MODEM_CRASH.search(line)
        if m:
            special["modem_crash"]["detected"] = True
            special["modem_crash"]["crash_type"] = m.group(0)
            break

    return special


def detect_recovery(esims_seq, special):
    """从 ESIMS 序列中检测救卡流程"""
    for i, item in enumerate(esims_seq):
        if item["cause"] == 13 and item["inserted_status"] == 0:
            special["recovery_process"]["triggered"] = True
            start_ts = item["timestamp"]
            for j in range(i + 1, min(i + 10, len(esims_seq))):
                if esims_seq[j]["cause"] == 14 and esims_seq[j]["inserted_status"] == 1:
                    special["recovery_process"]["success"] = True
                    end_ts = esims_seq[j]["timestamp"]
                    try:
                        dt_s = datetime.fromisoformat(start_ts)
                        dt_e = datetime.fromisoformat(end_ts)
                        special["recovery_process"]["duration"] = f"{(dt_e - dt_s).total_seconds():.1f}s"
                    except Exception:
                        pass
                    break
            break


# ---------------------------------------------------------------------------
# 步骤 5: 综合分类
# ---------------------------------------------------------------------------
def classify_problem(atr, esims_patterns, state_anomalies, special, esims_seq, state_flow):
    """按优先级判断问题分类"""
    affected_slot = None

    # 优先级 1: 硬件问题
    for slot_idx in (0, 1):
        if atr.get(f"slot_{slot_idx}") == "failed":
            affected_slot = slot_idx
            if "DETECT_AFTER_ERROR" in esims_patterns:
                return "SIM_ACCESS_ERROR", affected_slot, "SIM 卡识别后立即访问错误，硬件接触不良"
            return "HARDWARE_NO_ATR", affected_slot, "硬件接触无 ATR 响应，SIM 卡无法被识别"

    # 优先级 2: ESIMS 模式
    if "DETECT_AFTER_ERROR" in esims_patterns:
        return "SIM_ACCESS_ERROR", affected_slot, "+ESIMS:1,29 后紧跟 +ESIMS:0,1，SIM 卡访问错误"

    # 优先级 3: 救卡
    if special["recovery_process"]["triggered"]:
        if special["recovery_process"]["success"]:
            return "RECOVERY_SUCCESS", affected_slot, "接触不良触发救卡机制，救卡成功"
        return "RECOVERY_FAILED", affected_slot, "救卡流程启动但未成功"

    # 优先级 4: 特殊场景
    if special["modem_crash"]["detected"]:
        return "MODEM_CRASH", affected_slot, f"Modem 异常: {special['modem_crash']['crash_type']}"
    if special["esim_conflict"]["detected"]:
        return "ESIM_CONFLICT", 1, "eSIM 占用物理卡槽，热插拔被忽略"
    if special["pin_lock"]["detected"]:
        return "PIN_LOCK", special["pin_lock"]["slot"], "SIM 卡 PIN 锁已开启，等待用户输入"

    # 优先级 5: 状态异常
    for a in state_anomalies:
        if a["state"] == "CARD_IO_ERROR":
            slot = int(a["slot"][-1]) if isinstance(a["slot"], str) else a["slot"]
            return "SIM_ACCESS_ERROR", slot, "SIM 卡状态进入 CARD_IO_ERROR"
        if a["state"] == "DROP_CARD":
            slot = int(a["slot"][-1]) if isinstance(a["slot"], str) else a["slot"]
            return "HOT_PLUG_ISSUE", slot, "SIM 卡从 LOADED/READY 状态突然变为 ABSENT（掉卡）"

    # 检查是否有正常识卡
    for slot_key, states in state_flow.items():
        for s in states:
            if s["state"] in ("READY", "LOADED"):
                return "NORMAL", None, "SIM 卡正常识别"

    # 没有足够证据
    if not esims_seq and all(not v for v in state_flow.values()):
        return "INSUFFICIENT_EVIDENCE", None, "未找到 SIM 相关日志，无法分析"

    return "UNKNOWN", affected_slot, "未能明确分类"


# ---------------------------------------------------------------------------
# 构建时间线
# ---------------------------------------------------------------------------
def build_timeline(esims_seq, state_flow):
    events = []
    event_type_map = {
        0: "sim_removed", 1: "sim_error", 11: "plug_out", 12: "plug_in",
        13: "recovery_start", 14: "recovery_end", 29: "sim_detected",
    }
    for item in esims_seq:
        events.append({
            "timestamp": item["timestamp"],
            "slot": item.get("slot"),
            "event_type": event_type_map.get(item["cause"], "esims_event"),
            "event_code": f"+ESIMS:{item['inserted_status']},{item['cause']}",
            "description": item["interpretation"],
            "log_source": "radio_log",
        })
    for slot_key, states in state_flow.items():
        slot = int(slot_key[-1])
        for s in states:
            events.append({
                "timestamp": s["timestamp"],
                "slot": slot,
                "event_type": "state_change",
                "event_code": s["state"],
                "description": f"updateSimState: slot {slot} {s['state']}",
                "log_source": "main_log",
            })
    events.sort(key=lambda x: x.get("timestamp", ""))
    return events[:30]


# ---------------------------------------------------------------------------
# 构建建议
# ---------------------------------------------------------------------------
def build_recommendations(classification):
    recs = {
        "HARDWARE_NO_ATR": ["清洁 SIM 卡触点，重新插入测试", "如问题持续，更换卡槽测试", "检查 SIM 卡是否变形或损坏"],
        "SIM_ACCESS_ERROR": ["清洁 SIM 卡触点", "交叉测试：将 SIM 卡插入其他设备", "将其他 SIM 卡插入本设备"],
        "HOT_PLUG_ISSUE": ["检查卡托是否松动", "避免频繁插拔 SIM 卡"],
        "PIN_LOCK": ["输入正确的 PIN 码解锁", "如忘记 PIN 码，联系运营商获取 PUK 码"],
        "RECOVERY_SUCCESS": ["虽已恢复，但建议检查 SIM 卡和卡槽状态", "如频繁触发救卡，需排查接触不良"],
        "RECOVERY_FAILED": ["清洁 SIM 卡触点", "更换 SIM 卡测试", "检查卡槽硬件"],
        "ESIM_CONFLICT": ["检查 eSIM 配置", "如需使用物理卡，禁用 eSIM"],
        "MODEM_CRASH": ["收集完整 Modem dump 日志", "提交 Modem 异常问题单"],
        "NORMAL": ["SIM 卡识别正常，无需处理"],
    }
    return recs.get(classification, ["需要更多日志进一步分析"])


# ---------------------------------------------------------------------------
# 主分析入口
# ---------------------------------------------------------------------------
def analyze_sim(manifest, log_root=None):
    """执行完整的 L2 SIM 分析"""
    final_log_root = os.path.abspath(log_root or manifest.get("final_log_root") or "")
    if not final_log_root or not os.path.isdir(final_log_root):
        return {
            "analysis_type": "sim", "problem_classification": "INSUFFICIENT_EVIDENCE",
            "affected_slot": None, "root_cause": "缺少 final_log_root 或目录不存在",
            "timeline": [], "evidence": [], "candidate_causes": [],
            "state_flow": {"slot_0": [], "slot_1": []}, "at_esims_sequence": [],
            "hardware_detection": {"atr_response": {"slot_0": "unknown", "slot_1": "unknown"},
                                   "hot_plug_analysis": {"count": 0, "time_span": "", "abnormal_patterns": []}},
            "special_scenarios": {"pin_lock": {"detected": False, "slot": None},
                                  "esim_conflict": {"detected": False, "slot": None},
                                  "modem_crash": {"detected": False, "crash_type": None},
                                  "recovery_process": {"triggered": False, "success": False, "duration": None}},
            "gaps": ["final_log_root 不存在"], "recommendations": [],
        }

    groups = discover_log_groups(final_log_root)
    primary = select_primary_group(groups)
    lines_map = load_all_lines(primary)

    # 步骤 1: ATR 检测
    atr, atr_evidence = detect_atr(lines_map)

    # 步骤 2: ESIMS 序列
    esims_seq = parse_esims_sequence(lines_map)
    esims_patterns = analyze_esims_patterns(esims_seq)

    # 步骤 3: 状态流转
    state_flow = parse_state_flow(lines_map)
    state_anomalies = detect_state_anomalies(state_flow)

    # 步骤 4: 特殊场景
    special = detect_special_scenarios(lines_map, state_flow)
    detect_recovery(esims_seq, special)

    # 步骤 5: 综合分类
    classification, affected_slot, root_cause = classify_problem(
        atr, esims_patterns, state_anomalies, special, esims_seq, state_flow)

    # 构建时间线
    timeline = build_timeline(esims_seq, state_flow)

    # 构建证据（保留更多上下文，让 AI 有足够的原材料）
    evidence = list(atr_evidence)
    
    # 添加所有 ESIMS 事件（标注重要性，而不是过滤）
    for item in esims_seq:
        # 关键事件：检测、错误、救卡
        is_critical = item["cause"] in [1, 13, 14, 29]
        evidence.append({
            "type": "at_esims", 
            "content": f"+ESIMS:{item['inserted_status']},{item['cause']} ({item['interpretation']})",
            "log_file": "radio_log", 
            "timestamp": item["timestamp"], 
            "relevance": "high" if is_critical else "medium",
            "slot": item.get("slot"),
        })
    
    # 添加所有状态异常（不限制数量）
    for a in state_anomalies:
        evidence.append({
            "type": "state_anomaly", 
            "content": f"{a['slot']} → {a['state']}",
            "log_file": "main_log", 
            "timestamp": a.get("timestamp", ""), 
            "relevance": "high",
            "slot": a.get("slot"),
        })

    # 构建候选根因（添加更多候选项，让 AI 有选择空间）
    candidate_causes = []
    
    # 主要根因（脚本的判断）
    confidence = "high" if classification not in ["UNKNOWN", "INSUFFICIENT_EVIDENCE"] else "low"
    candidate_causes.append({
        "cause": root_cause, 
        "confidence": confidence,
        "supporting_evidence": [e["content"] for e in evidence if e.get("relevance") == "high"][:5],
        "source": "script_analysis"
    })
    
    # 添加备选根因（基于检测到的模式）
    if "DETECT_AFTER_ERROR" in esims_patterns:
        candidate_causes.append({
            "cause": "SIM 卡接触不良或芯片损坏",
            "confidence": "medium",
            "supporting_evidence": ["+ESIMS:1,29 后立即出现 +ESIMS:0,1"],
            "source": "pattern_detection"
        })
    
    if special["recovery_process"]["triggered"]:
        candidate_causes.append({
            "cause": "间歇性接触不良（已触发救卡机制）",
            "confidence": "medium" if special["recovery_process"]["success"] else "high",
            "supporting_evidence": [f"救卡流程{'成功' if special['recovery_process']['success'] else '失败'}"],
            "source": "recovery_analysis"
        })
    
    if hot_plug["count"] >= 3:
        candidate_causes.append({
            "cause": "频繁热插拔导致的接触问题",
            "confidence": "medium",
            "supporting_evidence": [f"检测到 {hot_plug['count']} 次插拔操作"],
            "source": "hot_plug_analysis"
        })

    # 热插拔统计
    plug_count = sum(1 for e in esims_seq if e["cause"] in (11, 12))
    hot_plug = {
        "count": plug_count // 2,
        "time_span": "",
        "abnormal_patterns": [],
    }
    if plug_count >= 6:
        hot_plug["abnormal_patterns"].append(f"短时间内 {plug_count // 2} 次插拔")

    # gaps（添加更详细的缺失信息，引导 AI 补充搜索）
    gaps = []
    if not esims_seq and all(not v for v in state_flow.values()):
        gaps.append({
            "type": "missing_logs",
            "description": "未在日志中找到 AT+ESIMS 或 updateSimState 记录",
            "impact": "无法判断 SIM 卡状态变化",
            "suggestion": "使用 $log-search-read 搜索关键字：'SIM'、'ESIMS'、'updateSimState'"
        })
    if atr["slot_0"] == "unknown" and atr["slot_1"] == "unknown":
        gaps.append({
            "type": "missing_hardware_info",
            "description": "未找到 ATR 响应日志，无法判断硬件状态",
            "impact": "无法区分硬件问题和软件问题",
            "suggestion": "使用 $log-search-read 搜索关键字：'ATR'、'AnswerToReset'、'SIM_DRV'"
        })
    if not timeline:
        gaps.append({
            "type": "missing_timeline",
            "description": "无法构建完整的事件时间线",
            "impact": "无法分析问题发生的时序关系",
            "suggestion": "检查日志文件是否包含时间戳"
        })
    
    # 检查是否缺少某个卡槽的信息
    if atr["slot_0"] != "unknown" and atr["slot_1"] == "unknown":
        gaps.append({
            "type": "incomplete_slot_info",
            "description": "只有 Slot 0 的信息，缺少 Slot 1 的数据",
            "impact": "如果用户使用双卡，无法判断 Slot 1 的状态",
            "suggestion": "如果用户反馈涉及 Slot 1，需要补充搜索 Slot 1 相关日志"
        })
    elif atr["slot_1"] != "unknown" and atr["slot_0"] == "unknown":
        gaps.append({
            "type": "incomplete_slot_info",
            "description": "只有 Slot 1 的信息，缺少 Slot 0 的数据",
            "impact": "如果用户使用双卡，无法判断 Slot 0 的状态",
            "suggestion": "如果用户反馈涉及 Slot 0，需要补充搜索 Slot 0 相关日志"
        })

    return {
        "analysis_type": "sim",
        "problem_classification": classification,
        "affected_slot": affected_slot,
        "root_cause": root_cause,
        "confidence": confidence,  # 新增：顶层置信度
        "timeline": timeline,
        "evidence": evidence,
        "candidate_causes": candidate_causes,
        "state_flow": {k: v for k, v in state_flow.items()},
        "at_esims_sequence": esims_seq,  # 保留完整序列，不截断
        "hardware_detection": {
            "atr_response": atr,
            "hot_plug_analysis": hot_plug,
        },
        "special_scenarios": special,
        "gaps": gaps,
        "recommendations": build_recommendations(classification),
        # 新增：分析元数据
        "analysis_metadata": {
            "script_version": "2.0",
            "analysis_timestamp": datetime.now().isoformat(),
            "log_files_analyzed": list(lines_map.keys()),
            "total_esims_events": len(esims_seq),
            "total_state_changes": sum(len(v) for v in state_flow.values()),
            "patterns_detected": esims_patterns,
        },
        # 新增：原始数据摘要（供 AI 参考）
        "raw_data_summary": {
            "esims_causes_distribution": {
                str(cause): sum(1 for e in esims_seq if e["cause"] == cause)
                for cause in set(e["cause"] for e in esims_seq)
            } if esims_seq else {},
            "state_distribution": {
                slot: {
                    state: sum(1 for s in states if s["state"] == state)
                    for state in set(s["state"] for s in states)
                } for slot, states in state_flow.items() if states
            },
        },
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args():
    parser = argparse.ArgumentParser(description="执行 L2 SIM 域分析")
    parser.add_argument("--manifest", required=True, help="manifest 文件路径")
    parser.add_argument("--log-root", help="覆盖 manifest.final_log_root")
    parser.add_argument("--output", help="结果 JSON 输出路径（可选）")
    parser.add_argument("--skip-gate", action="store_true", help="跳过 L0 validity gate 检查")
    return parser.parse_args()


def main():
    configure_stdio()
    args = parse_args()

    try:
        manifest = load_manifest(args.manifest)
    except Exception as exc:
        print(f"SKILL_FAILED: L2-SIM 无法加载 manifest ({args.manifest}): {exc}")
        sys.exit(1)

    issue_key = manifest.get("issue_key", "") or "unknown"
    logger = setup_skill_logger(args.manifest, issue_key)
    logger.info("=== L2 SIM analysis 开始 ===")

    # L0 validity gate 检查（除非 --skip-gate）
    if not args.skip_gate:
        l0 = manifest.get("analysis", {}).get("l0_baseline", {})
        gate = l0.get("validity_gate", {})
        if gate.get("status") == "invalid" and not l0.get("should_continue", True):
            result = {
                "analysis_type": "sim", "problem_classification": "SKIPPED",
                "affected_slot": None, "root_cause": "L0 validity gate 判定为无效，跳过 L2 SIM 分析",
                "timeline": [], "evidence": [], "candidate_causes": [],
                "state_flow": {"slot_0": [], "slot_1": []}, "at_esims_sequence": [],
                "hardware_detection": {"atr_response": {"slot_0": "unknown", "slot_1": "unknown"},
                                       "hot_plug_analysis": {"count": 0, "time_span": "", "abnormal_patterns": []}},
                "special_scenarios": {"pin_lock": {"detected": False, "slot": None},
                                      "esim_conflict": {"detected": False, "slot": None},
                                      "modem_crash": {"detected": False, "crash_type": None},
                                      "recovery_process": {"triggered": False, "success": False, "duration": None}},
                "gaps": ["L0 已判定为无效问题"], "recommendations": [],
            }
            manifest.setdefault("analysis", {}).setdefault("l2_domains", {})["sim"] = result
            save_manifest(args.manifest, manifest)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

    # 执行分析
    result = analyze_sim(manifest, log_root=args.log_root)
    logger.info(f"L2-SIM 完成: classification={result.get('problem_classification')}, "
                f"slot={result.get('affected_slot')}")

    # 写回 manifest
    manifest.setdefault("analysis", {}).setdefault("l2_domains", {})["sim"] = result
    save_manifest(args.manifest, manifest)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
