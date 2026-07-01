"""
SCMP SPD 产品规格 / 产品配置 / 特性配置清单

HAR: scmp根据项目信息查询配置清单以及特性清单.har

Flow:
  project search (build-platform) -> projectBid
  getProjectInfoDetail -> project detail
  queryProductSpecificationList -> spec list bid (sid_...)
  queryProductConfigList -> product config items
  queryFeatureConfigList -> feature config items (filterable)
"""

from __future__ import annotations

import argparse
from typing import Any

from tones_cli.http_client import TonesHttpClient
from tones_cli.modules.base import ApiModule
from tones_cli.modules.partition_profiles import get_partition

SPD_SERVICE = "tones-spd"
BUILD_SERVICE = "tones-build-platform"


class ScmpSpdSpecModule(ApiModule):
    name = "scmp-spd-spec"
    description = "SCMP SPD 产品规格、产品配置与特性配置清单"

    def __init__(self, client: TonesHttpClient | None = None):
        super().__init__(client)
        self._spd = TonesHttpClient(SPD_SERVICE)
        self._build = TonesHttpClient(BUILD_SERVICE)

    def register_commands(self, scmp_subparsers) -> None:
        spd = scmp_subparsers.add_parser("spd", help="SPD product spec / config / feature lists")
        spd_sub = spd.add_subparsers(dest="spd_command", required=True)

        self._register_resolve(spd_sub)
        self._register_project_detail(spd_sub)
        self._register_spec_list(spd_sub)
        self._register_config_list(spd_sub)
        self._register_feature_list(spd_sub)

    def _register_resolve(self, parent) -> None:
        cmd = parent.add_parser(
            "resolve",
            help="Resolve projectBid + spec list bid from project name keyword",
        )
        cmd.add_argument("--name", required=True, help="Project name keyword, e.g. KM9")
        cmd.add_argument(
            "--partition",
            default="tr_product",
            choices=["tr_product", "tr_region", "tr_carrier"],
            help="Partition for project search (default tr_product)",
        )
        cmd.add_argument("--tos-version", default=None, help="Filter spec by tOS version, e.g. 16.3.0")
        cmd.set_defaults(handler=self._handle_resolve, output_kind="spd-resolve")

    def _register_project_detail(self, parent) -> None:
        cmd = parent.add_parser("project", help="SPD project detail")
        proj_sub = cmd.add_subparsers(dest="spd_project_command", required=True)
        detail = proj_sub.add_parser("detail", help="getProjectInfoDetail")
        detail.add_argument("--bid", required=True, help="Project bid, e.g. 1498968929236815872")
        detail.set_defaults(handler=self._handle_project_detail, output_kind="spd-project")

    def _register_spec_list(self, parent) -> None:
        cmd = parent.add_parser("spec", help="Product specification list")
        spec_sub = cmd.add_subparsers(dest="spd_spec_command", required=True)
        lst = spec_sub.add_parser("list", help="queryProductSpecificationList")
        lst.add_argument("--project-bid", default=None, help="Project bid")
        lst.add_argument("--name", default=None, help="Resolve project bid by name keyword")
        lst.add_argument(
            "--partition",
            default="tr_product",
            choices=["tr_product", "tr_region", "tr_carrier"],
        )
        lst.add_argument("--tos-version", action="append", default=None, help="tOS version filter (repeatable)")
        lst.set_defaults(handler=self._handle_spec_list, output_kind="spd-spec")

    def _register_config_list(self, parent) -> None:
        cmd = parent.add_parser("config", help="Product configuration list")
        cfg_sub = cmd.add_subparsers(dest="spd_config_command", required=True)
        lst = cfg_sub.add_parser("list", help="queryProductConfigList")
        lst.add_argument("--spec-bid", required=True, help="Product specification list bid (sid_...)")
        lst.set_defaults(handler=self._handle_config_list, output_kind="spd-config")

    def _register_feature_list(self, parent) -> None:
        cmd = parent.add_parser("feature", help="Feature configuration list")
        feat_sub = cmd.add_subparsers(dest="spd_feature_command", required=True)
        lst = feat_sub.add_parser("list", help="queryFeatureConfigList")
        lst.add_argument("--spec-bid", required=True, help="Product specification list bid (sid_...)")
        lst.add_argument("--page", type=int, default=1)
        lst.add_argument("--size", type=int, default=200)
        lst.add_argument(
            "--my-related",
            choices=["true", "false"],
            default="false",
            help="myRelated filter: false=full feature list (default, matches web UI); true=only features related to current user",
        )
        lst.add_argument("--feature-code", default=None, help="lv4Code feature code, e.g. SF-202507-002778")
        lst.add_argument("--feature-name", default=None, help="lv4Name feature name (substring)")
        lst.add_argument("--feature-owner", default=None, help="featureOwner, e.g. 张三(18651234)")
        lst.add_argument("--feature-se", default=None, help="featureSe employee no")
        lst.add_argument("--config-owner", default=None, help="configOwner")
        lst.add_argument(
            "--config-status",
            choices=["true", "false"],
            default=None,
            help="configStatus: true=已完成 false=未完成",
        )
        lst.add_argument(
            "--build-config-status",
            choices=["true", "false"],
            default=None,
            help="buildConfigStatus filter",
        )
        lst.add_argument("--self-check-status", default=None, help="e.g. Pass")
        lst.set_defaults(handler=self._handle_feature_list, output_kind="spd-feature")

    def _resolve_project_bid(self, args: argparse.Namespace) -> str:
        if getattr(args, "project_bid", None):
            return args.project_bid
        name = getattr(args, "name", None)
        if not name:
            raise ValueError("Provide --project-bid or --name")
        partition = get_partition(getattr(args, "partition", "tr_product"))
        if partition.project_api == "name_like":
            result = self._build.post(
                "/projectInfo/queryProjectInfoByNameLike",
                json_body={"name": name},
            )
            items = result.get("data") or []
            if not items:
                raise ValueError(f"No project found for name: {name}")
            if len(items) == 1:
                return items[0]["bid"]
            needle = name.lower()
            exact = [
                i
                for i in items
                if (i.get("projectName") or "").lower() == needle
                or (i.get("name") or "").lower() == needle
            ]
            if len(exact) == 1:
                return exact[0]["bid"]
            if len(exact) > 1:
                items = exact
            names = [f"{i.get('projectName')} ({i.get('name')})" for i in items]
            raise ValueError(
                f"Multiple projects match '{name}': {names}. "
                "Use --project-bid or a more specific --name."
            )
        result = self._build.post("/projectInfo/queryProjectInfoTree", json_body={"name": name})
        tree = result.get("data") or []
        matches = []
        needle = name.lower()

        def walk(nodes: list[dict[str, Any]]) -> None:
            for node in nodes:
                n = (node.get("name") or "").lower()
                p = (node.get("projectName") or "").lower()
                if needle in n or needle in p:
                    if node.get("type") != 1:
                        matches.append(node)
                for child in node.get("children") or []:
                    walk([child])

        walk(tree)
        if not matches:
            raise ValueError(f"No project found for name: {name}")
        if len(matches) > 1:
            names = [m.get("name") for m in matches]
            raise ValueError(f"Multiple projects match '{name}': {names}. Use --project-bid.")
        return matches[0]["bid"]

    def _handle_resolve(self, args: argparse.Namespace) -> dict[str, Any]:
        project_bid = self._resolve_project_bid(args)
        detail = self._spd.post("/spd-projectInfo/getProjectInfoDetail", json_body={"bid": project_bid})
        spec_args = argparse.Namespace(
            project_bid=project_bid,
            name=None,
            partition=args.partition,
            tos_version=[args.tos_version] if args.tos_version else None,
        )
        specs = self._handle_spec_list(spec_args)
        spec_items = specs.get("data") or []
        if not spec_items:
            raise ValueError(f"No product specification list for project {project_bid}")
        spec = spec_items[0]
        return {
            "code": "0000",
            "msg": "success",
            "data": {
                "projectBid": project_bid,
                "projectName": (detail.get("data") or {}).get("name"),
                "specBid": spec.get("bid"),
                "tosVersion": spec.get("tosVersion"),
                "marketList": spec.get("marketList"),
            },
            "_meta": {
                "hint": "Use specBid with `scmp spd config list` and `scmp spd feature list`",
            },
        }

    def _handle_project_detail(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._spd.post("/spd-projectInfo/getProjectInfoDetail", json_body={"bid": args.bid})

    def _handle_spec_list(self, args: argparse.Namespace) -> dict[str, Any]:
        project_bid = self._resolve_project_bid(args)
        body: dict[str, Any] = {"projectBid": project_bid}
        if args.tos_version:
            body["tosVersionList"] = args.tos_version
        return self._spd.post("/productSpecificationList/queryProductSpecificationList", json_body=body)

    def _handle_config_list(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._spd.post(
            "/productSpecificationList/queryProductConfigList",
            json_body={"bid": args.spec_bid},
        )

    def _feature_body(self, args: argparse.Namespace) -> dict[str, Any]:
        body: dict[str, Any] = {
            "bid": args.spec_bid,
            "current": args.page,
            "size": args.size,
        }
        optional_fields = {
            "feature_code": ("lv4Code", ""),
            "feature_name": ("lv4Name", ""),
            "feature_owner": ("featureOwner", None),
            "feature_se": ("featureSe", None),
            "config_owner": ("configOwner", None),
            "self_check_status": ("selfCheckStatus", None),
        }
        for arg_name, (json_key, empty_default) in optional_fields.items():
            val = getattr(args, arg_name, None)
            if val is not None:
                body[json_key] = val
            elif empty_default is not None and json_key in ("lv4Code", "lv4Name"):
                body[json_key] = empty_default

        body["myRelated"] = args.my_related == "true"
        if args.config_status is not None:
            body["configStatus"] = args.config_status == "true"
        if args.build_config_status is not None:
            body["buildConfigStatus"] = args.build_config_status == "true"
        return body

    def _handle_feature_list(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._spd.post(
            "/productSpecificationList/queryFeatureConfigList",
            json_body=self._feature_body(args),
        )
