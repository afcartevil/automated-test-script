"""
SCMP 属性信息查询 API — derived from scmp属性查询字段.har / 根据属性查询关联特性信息.har

Endpoints:
  POST /attributeInfo/queryAttributeInfoByPage
  POST /attributeInfo/getAttributeVersionDetail
"""

from __future__ import annotations

import argparse
from typing import Any

from tones_cli.modules.base import ApiModule


class ScmpAttributeInfoModule(ApiModule):
    name = "scmp-info"
    description = "SCMP 属性信息查询 (tones-build-platform/attributeInfo)"

    def register_commands(self, scmp_subparsers) -> None:
        info = scmp_subparsers.add_parser("info", help="Attribute info query")
        info_sub = info.add_subparsers(dest="info_command", required=True)
        self._register_query(info_sub)
        self._register_detail(info_sub)

    def _register_query(self, parent) -> None:
        cmd = parent.add_parser(
            "query",
            help="Paginated attribute info search (queryAttributeInfoByPage)",
        )
        cmd.add_argument("--page", type=int, default=1, help="Page number (current)")
        cmd.add_argument("--size", type=int, default=50, help="Page size")
        cmd.add_argument("--attr-code", default=None, help="Attribute code filter")
        cmd.add_argument(
            "--attr-type",
            choices=["1", "2"],
            default=None,
            help="Attribute type: 1=系统属性 2=应用属性",
        )
        cmd.add_argument(
            "--architecture-level",
            choices=["system", "vendor"],
            default=None,
            help="Architecture level",
        )
        cmd.add_argument("--package-name", default=None, help="Package name filter")
        cmd.add_argument("--attr-mode", type=int, default=None, help="Attribute mode")
        cmd.add_argument("--second-department", default=None, help="Second department")
        cmd.add_argument("--third-department", default=None, help="Third department")
        cmd.add_argument("--fourth-department", default=None, help="Fourth department")
        cmd.set_defaults(handler=self._handle_query, output_kind="info")

    def _register_detail(self, parent) -> None:
        cmd = parent.add_parser(
            "detail",
            help="Attribute version detail with linked features (getAttributeVersionDetail)",
        )
        cmd.add_argument("--bid", default=None, help="Attribute bid, e.g. sid_1394974796370022400")
        cmd.add_argument(
            "--version",
            default=None,
            help="Attribute version, e.g. 20251226.0001 (required with --bid)",
        )
        cmd.add_argument(
            "--attr-code",
            default=None,
            help="Resolve bid+version via info query when --bid omitted",
        )
        cmd.add_argument(
            "--features-only",
            action="store_true",
            help="Return only attributeFeatures section",
        )
        cmd.set_defaults(handler=self._handle_detail, output_kind="info-detail")

    def _query_body(self, args: argparse.Namespace) -> dict[str, Any]:
        body: dict[str, Any] = {
            "current": args.page,
            "size": args.size,
        }
        field_map = {
            "attr_code": "attrCode",
            "attr_type": "attrType",
            "architecture_level": "architectureLevel",
            "package_name": "packageName",
            "attr_mode": "attrMode",
            "second_department": "secondDepartment",
            "third_department": "thirdDepartment",
            "fourth_department": "fourthDepartment",
        }
        for arg_name, json_key in field_map.items():
            value = getattr(args, arg_name, None)
            if value is not None:
                body[json_key] = value
        return body

    def _handle_query(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post(
            "/attributeInfo/queryAttributeInfoByPage",
            json_body=self._query_body(args),
        )

    def _resolve_bid_version(self, args: argparse.Namespace) -> tuple[str, str]:
        if args.bid and args.version:
            return args.bid, args.version

        if args.bid and not args.version:
            raise ValueError("--version is required when --bid is provided")

        if not args.attr_code:
            raise ValueError("Provide --bid and --version, or --attr-code")

        result = self.client.post(
            "/attributeInfo/queryAttributeInfoByPage",
            json_body={"current": 1, "size": 1, "attrCode": args.attr_code},
        )
        records = (result.get("data") or {}).get("records") or []
        if not records:
            raise ValueError(f"No attribute found for attrCode: {args.attr_code}")

        rec = records[0]
        bid = rec.get("bid")
        version = args.version or rec.get("version")
        if not bid or not version:
            raise ValueError(
                f"Could not resolve bid/version for {args.attr_code}: bid={bid}, version={version}"
            )
        return bid, version

    def _handle_detail(self, args: argparse.Namespace) -> dict[str, Any]:
        bid, version = self._resolve_bid_version(args)
        result = self.client.post(
            "/attributeInfo/getAttributeVersionDetail",
            json_body={"bid": bid, "version": version},
        )
        if not args.features_only:
            return result

        data = result.get("data") or {}
        return {
            "code": result.get("code", "0000"),
            "msg": result.get("msg", "success"),
            "data": {
                "bid": data.get("bid"),
                "attrCode": data.get("attrCode"),
                "version": version,
                "isConfigRefFlag": data.get("isConfigRefFlag"),
                "attributeFeatures": data.get("attributeFeatures") or [],
            },
        }
