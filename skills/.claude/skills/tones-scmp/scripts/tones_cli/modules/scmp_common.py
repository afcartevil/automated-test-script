"""Shared SCMP CLI dispatch and output helpers."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from tones_cli.http_client import TonesApiError

APPLY_STATUS_LABELS = {
    0: "待审批",
    1: "未通过",
    2: "已通过",
    3: "取消",
    4: "全部",
}


def dispatch_scmp(args: argparse.Namespace) -> int:
    handler = getattr(args, "handler", None)
    if not handler:
        return 1
    try:
        result = handler(args)
    except TonesApiError as exc:
        emit_error(str(exc), exc.body, json_mode=args.json)
        return 1
    except ValueError as exc:
        emit_error(str(exc), None, json_mode=args.json)
        return 1

    emit_success(result, json_mode=args.json, output_kind=getattr(args, "output_kind", "auto"))
    return 0


def emit_success(result: dict[str, Any], *, json_mode: bool, output_kind: str = "auto") -> None:
    if json_mode:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    data = result.get("data", result)

    if output_kind == "project" and isinstance(data, list):
        if data and data[0].get("isMarket") is not None:
            _print_project_tree(data)
        else:
            _print_project_list(data)
    elif output_kind == "partition-list" and isinstance(data, list):
        _print_partition_profiles(data)
    elif output_kind == "partition" and isinstance(data, list):
        _print_partition_groups(data)
    elif output_kind == "strategy" and isinstance(data, dict) and "records" in data:
        _print_strategy_list(data)
    elif output_kind == "strategy-detail" and isinstance(data, dict):
        _print_strategy_detail(data)
    elif output_kind == "spd-resolve" and isinstance(data, dict):
        _print_spd_resolve(data)
    elif output_kind == "spd-spec" and isinstance(data, list):
        _print_spd_spec_list(data)
    elif output_kind == "spd-config" and isinstance(data, list):
        _print_spd_config_list(data)
    elif output_kind == "spd-feature" and isinstance(data, dict) and "records" in data:
        _print_spd_feature_list(data)
    elif output_kind == "spd-google" and isinstance(data, list):
        _print_spd_google_list(data)
    elif output_kind in ("spd-market-support", "spd-one-step") and isinstance(data, dict):
        _print_spd_market_support(data, result.get("_meta") or {})
    elif output_kind == "spd-candidates" and isinstance(data, list):
        _print_spd_candidates(data)
    elif output_kind == "spd-project-list" and isinstance(data, list):
        _print_spd_project_list(data)
    elif output_kind == "spd-project" and isinstance(data, dict):
        _print_spd_project(data)
    elif output_kind == "info" or (
        output_kind == "auto"
        and isinstance(data, dict)
        and "records" in data
        and data["records"]
        and "attrDefaultValue" in data["records"][0]
    ):
        _print_info_records(data)
    elif output_kind == "info-detail" and isinstance(data, dict):
        _print_info_detail(data)
    elif isinstance(data, dict) and "records" in data:
        _print_apply_records(data)
    elif isinstance(data, list) and data and isinstance(data[0], dict) and "status" in data[0]:
        for item in data:
            print(f"- {item.get('status')}: {item.get('statusTotal')}")
    elif isinstance(data, list):
        for item in data:
            print(f"- {item}")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


def _print_apply_records(data: dict[str, Any]) -> None:
    total = data.get("total", "?")
    records = data["records"]
    print(f"Total: {total}, showing {len(records)} record(s)\n")
    for rec in records:
        status = rec.get("status")
        status_label = APPLY_STATUS_LABELS.get(status, str(status))
        print(f"- [{status_label}] {rec.get('attrCode')} ({rec.get('applyCode')})")
        print(f"  负责人: {rec.get('responsiblePerson')}")
        definition = rec.get("attrDefinition") or ""
        print(f"  定义: {definition[:80]}")
        print()


def _print_partition_profiles(profiles: list[dict[str, Any]]) -> None:
    for p in profiles:
        print(
            f"- {p.get('partition')} ({p.get('label')}) "
            f"bid={p.get('partitionGroupBid')} api={p.get('projectSearchApi')}"
        )


def _print_project_tree(nodes: list[dict[str, Any]]) -> None:
    print(f"Found {len(nodes)} node(s)\n")
    for n in nodes:
        kind = "market" if n.get("isMarket") else "project"
        print(f"- [{kind}] {n.get('name')} (projectName={n.get('projectName')})")
        if n.get("parentName"):
            print(f"  parent: {n.get('parentName')}")
        print(f"  bid: {n.get('bid')}")
        print()


def _print_project_list(projects: list[dict[str, Any]]) -> None:
    print(f"Found {len(projects)} project(s)\n")
    for p in projects:
        print(f"- {p.get('projectName')} | {p.get('name')}")
        print(f"  bid: {p.get('bid')} | chip: {p.get('chip')} ({p.get('chipPlatform')})")
        print()


def _print_partition_groups(groups: list[dict[str, Any]]) -> None:
    for g in groups:
        print(
            f"- {g.get('partitionName')} ({g.get('partitionCode')}) "
            f"bid={g.get('bid')}"
        )


def _print_strategy_list(data: dict[str, Any]) -> None:
    records = data.get("records") or []
    print(f"Total: {data.get('total', len(records))}, showing {len(records)} strategy(ies)\n")
    for rec in records:
        print(f"- {rec.get('strategyCode')}")
        print(f"  bid: {rec.get('bid')} | version: {rec.get('version')} | project: {rec.get('projectName')}")
        print()


def _print_strategy_detail(data: dict[str, Any]) -> None:
    print(f"Strategy: {data.get('strategyCode')} ({data.get('bid')})")
    print(f"Project: {data.get('projectName')} | partition: {data.get('partitionCode')}")
    attrs = data.get("attributeInfo") or []
    if attrs:
        print(f"\nAttributes ({len(attrs)}):\n")
        for a in attrs[:20]:
            print(f"- {a.get('attrCode')} = {a.get('attrValue')} ({a.get('attrValueType')})")
        if len(attrs) > 20:
            print(f"... and {len(attrs) - 20} more (use --json for full list)")
    else:
        print("\n(no attributeInfo or filtered empty)")
    print()


def _print_spd_resolve(data: dict[str, Any]) -> None:
    print(f"Project: {data.get('projectName')} (bid={data.get('projectBid')})")
    print(f"Spec list bid: {data.get('specBid')} | tOS: {data.get('tosVersion')} | markets: {data.get('marketList')}")
    print()


def _print_spd_project(data: dict[str, Any]) -> None:
    print(f"Project: {data.get('name')} (bid={data.get('bid')})")
    print(f"  chip: {data.get('chip')} | osVersion: {data.get('osVersion')}")
    print()


def _print_spd_project_list(items: list[dict[str, Any]]) -> None:
    print(f"SPD projects: {len(items)}\n")
    for item in items[:50]:
        print(f"- {item.get('name')} (bid={item.get('bid')})")
    if len(items) > 50:
        print(f"... and {len(items) - 50} more (use --json)")
    print()


def _print_spd_candidates(items: list[dict[str, Any]]) -> None:
    print(f"Candidates: {len(items)}\n")
    for item in items:
        print(f"- rank={item.get('rank')} {item.get('name')} (bid={item.get('bid')})")
    print()


def _print_spd_google_list(items: list[dict[str, Any]]) -> None:
    print(f"Google program items: {len(items)}\n")
    for item in items[:30]:
        print(f"- [{item.get('googleConfigCode')}] {item.get('strategy')} status={item.get('configStatus')}")
    if len(items) > 30:
        print(f"... and {len(items) - 30} more (use --json)")
    print()


def _print_spd_market_support(data: dict[str, Any], meta: dict[str, Any]) -> None:
    print(f"Market-support features: {len(data)}")
    if meta:
        used = meta.get("spd_project") or meta.get("specBid")
        if used:
            print(f"  source: {used}")
        if meta.get("warning"):
            print(f"  warning: {meta['warning']}")
    sample = list(data.items())[:10]
    for code, markets in sample:
        preview = ", ".join(f"{k}={v}" for k, v in list(markets.items())[:6])
        print(f"- {code}: {preview}")
    if len(data) > 10:
        print(f"... and {len(data) - 10} more (use --json)")
    print()


def _print_spd_spec_list(items: list[dict[str, Any]]) -> None:
    print(f"Found {len(items)} product specification list(s)\n")
    for item in items:
        print(f"- bid: {item.get('bid')} | tOS: {item.get('tosVersion')} | markets: {item.get('marketList')}")
        print(f"  projectBid: {item.get('projectBid')} | updated: {item.get('modifyTime')}")
        print()


def _print_spd_config_list(items: list[dict[str, Any]]) -> None:
    print(f"Product config items: {len(items)}\n")
    for item in items[:30]:
        code = item.get("code") or item.get("productConfigCode") or item.get("attrCode")
        name = item.get("name") or ""
        status = "已完成" if item.get("configStatus") else "未完成"
        print(f"- [{code}] {name} ({status})")
    if len(items) > 30:
        print(f"... and {len(items) - 30} more (use --json)")
    print()


def _print_spd_feature_list(data: dict[str, Any]) -> None:
    records = data.get("records") or []
    print(f"Total: {data.get('total', len(records))}, showing {len(records)} feature(s)\n")
    for rec in records:
        done = "已完成" if rec.get("configStatus") else "未完成"
        build = "构建完成" if rec.get("buildConfigStatus") else "构建未完成"
        print(f"- [{rec.get('lv4Code')}] {rec.get('lv4Name')}")
        print(f"  特性负责人: {rec.get('featureOwner')} | 配置负责人: {rec.get('configOwner')}")
        print(f"  配置状态: {done} | {build}")
        print()


def _print_info_records(data: dict[str, Any]) -> None:
    total = data.get("total", "?")
    records = data["records"]
    print(f"Total: {total}, showing {len(records)} record(s)\n")
    for rec in records:
        print(f"- {rec.get('attrCode')}")
        print(f"  类型: {rec.get('attrType')} | 层级: {rec.get('architectureLevel')} | 模式: {rec.get('attrMode')}")
        print(f"  负责人: {rec.get('responsiblePerson')}")
        print(f"  部门: {rec.get('secondDepartment')} / {rec.get('thirdDepartment')} / {rec.get('fourthDepartment')}")
        print(f"  默认值: {rec.get('attrDefaultValue')} — {rec.get('attrDefaultValueDefinition', '')[:60]}")
        print(f"  版本: {rec.get('version')} | 适用范围: {rec.get('applyTypeDesc')}")
        print()


def _print_info_detail(data: dict[str, Any]) -> None:
    print(f"Attribute: {data.get('attrCode')} (bid={data.get('bid')})")
    print(f"  定义: {data.get('attrDefinition')}")
    print(f"  负责人: {data.get('responsiblePerson')}")
    print(f"  默认值: {data.get('attrDefaultValue')} — {data.get('attrDefaultValueDefinition', '')[:80]}")
    print(f"  关联特性: {'是' if data.get('isConfigRefFlag') else '否'}")

    features = data.get("attributeFeatures") or []
    if features:
        print(f"\nLinked features ({len(features)}):\n")
        for feat in features:
            code = feat.get("fourthFeatureCode") or feat.get("thirdFeatureCode") or feat.get("secondFeatureCode")
            name = feat.get("fourthFeature") or feat.get("thirdFeature") or feat.get("secondFeature")
            path = " / ".join(
                part
                for part in [
                    feat.get("firstFeature"),
                    feat.get("secondFeature"),
                    feat.get("thirdFeature"),
                    feat.get("fourthFeature"),
                ]
                if part
            )
            print(f"- [{code}] {name}")
            print(f"  路径: {path}")
            print(f"  支持值: {feat.get('supportAttrValue')} — {feat.get('supportAttrValueExplain', '')[:60]}")
            print(f"  不支持值: {feat.get('notSupportAttrValue')} — {feat.get('notSupportAttrValueExplain', '')[:60]}")
            owner = feat.get("fourthFeatureOwner") or feat.get("thirdFeaturePerson")
            if owner:
                print(f"  特性负责人: {owner}")
            print()
    else:
        print("\n(no attributeFeatures)")

    values = data.get("attributeValues") or []
    if values:
        print(f"Attribute values ({len(values)}):")
        for val in values:
            default = " [default]" if val.get("defaultFlag") else ""
            print(f"- {val.get('attrValue')}{default}: {val.get('attrValueDefinition', '')[:60]}")
        print()


def emit_error(message: str, body: Any, *, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps({"error": message, "body": body}, ensure_ascii=False, indent=2))
    else:
        print(f"Error: {message}", file=sys.stderr)
        if body:
            print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
