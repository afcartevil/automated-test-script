"""
SCMP SPD 产品规格 / 产品配置 / 特性配置清单

HAR: scmp根据项目信息查询配置清单以及特性清单.har

Flow (build-platform):
  project search -> projectBid

Flow (tones-spd, sdd_test 对齐能力):
  getProjectInfoList -> 全量 SPD 项目
  get_project_candidates -> 按项目名模糊匹配候选
  queryProductSpecificationList -> spec bid
  queryFeatureConfigList + queryGoogleProgramList -> 合并特性
  feature_with_market / one-step -> {featureCode: {market: "0"|"1"}}
"""

from __future__ import annotations

import argparse
import re
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
        self._spd_client: TonesHttpClient | None = None
        self._build_client: TonesHttpClient | None = None

    @property
    def _spd(self) -> TonesHttpClient:
        if self._spd_client is None:
            self._spd_client = TonesHttpClient(SPD_SERVICE)
        return self._spd_client

    @property
    def _build(self) -> TonesHttpClient:
        if self._build_client is None:
            self._build_client = TonesHttpClient(BUILD_SERVICE)
        return self._build_client

    def register_commands(self, scmp_subparsers) -> None:
        spd = scmp_subparsers.add_parser("spd", help="SPD product spec / config / feature lists")
        spd_sub = spd.add_subparsers(dest="spd_command", required=True)

        self._register_resolve(spd_sub)
        self._register_project(spd_sub)
        self._register_candidates(spd_sub)
        self._register_spec_list(spd_sub)
        self._register_config_list(spd_sub)
        self._register_feature_list(spd_sub)
        self._register_google_list(spd_sub)
        self._register_market_support(spd_sub)
        self._register_one_step(spd_sub)

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

    def _register_project(self, parent) -> None:
        cmd = parent.add_parser("project", help="SPD project list / detail")
        proj_sub = cmd.add_subparsers(dest="spd_project_command", required=True)

        lst = proj_sub.add_parser("list", help="getProjectInfoList (full SPD project map)")
        lst.set_defaults(handler=self._handle_project_list, output_kind="spd-project-list")

        detail = proj_sub.add_parser("detail", help="getProjectInfoDetail")
        detail.add_argument("--bid", required=True, help="Project bid, e.g. 1498968929236815872")
        detail.set_defaults(handler=self._handle_project_detail, output_kind="spd-project")

    def _register_candidates(self, parent) -> None:
        cmd = parent.add_parser(
            "candidates",
            help="Match ordered SPD project candidates by product/project name (sdd_test logic)",
        )
        cmd.add_argument("--name", required=True, help="Product/project name, e.g. X6886")
        cmd.set_defaults(handler=self._handle_candidates, output_kind="spd-candidates")

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
            help="myRelated filter: false=full feature list (default); true=only related to current user",
        )
        lst.add_argument("--feature-code", default=None, help="lv4Code feature code, e.g. SF-202507-002778")
        lst.add_argument("--feature-name", default=None, help="lv4Name feature name (substring)")
        lst.add_argument("--feature-owner", default=None, help="featureOwner")
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

    def _register_google_list(self, parent) -> None:
        cmd = parent.add_parser("google", help="Google program feature list")
        google_sub = cmd.add_subparsers(dest="spd_google_command", required=True)
        lst = google_sub.add_parser("list", help="queryGoogleProgramList")
        lst.add_argument("--spec-bid", required=True, help="Product specification list bid (sid_...)")
        lst.set_defaults(handler=self._handle_google_list, output_kind="spd-google")

    def _register_market_support(self, parent) -> None:
        cmd = parent.add_parser(
            "market-support",
            help="Parse feature(+google) market support map: feature -> {market: 0|1}",
        )
        cmd.add_argument("--spec-bid", required=True, help="Product specification list bid")
        cmd.add_argument(
            "--include-google",
            choices=["true", "false"],
            default="true",
            help="Merge google program list (default true)",
        )
        cmd.add_argument("--page", type=int, default=1)
        cmd.add_argument("--size", type=int, default=99999)
        cmd.set_defaults(handler=self._handle_market_support, output_kind="spd-market-support")

    def _register_one_step(self, parent) -> None:
        cmd = parent.add_parser(
            "one-step",
            help="sdd_test one_step_feature_list: product_name + tos -> market support map",
        )
        cmd.add_argument("--name", required=True, help="Product/project name, e.g. X6886")
        cmd.add_argument("--tos-version", required=True, help="tOS version, e.g. 16.1.0")
        cmd.set_defaults(handler=self._handle_one_step, output_kind="spd-one-step")

    # ---- project resolution (build-platform) ----

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

    # ---- SPD project candidates (sdd_test logic) ----

    def _fetch_project_info_map(self) -> dict[str, dict[str, Any]]:
        res = self._spd.post("/spd-projectInfo/getProjectInfoList", json_body={})
        msg = str(res.get("msg") or "")
        if "success" not in msg.lower() and res.get("code") not in (None, "0000", 0):
            raise ValueError(f"getProjectInfoList failed: {res}")
        items = res.get("data") or []
        return {item["name"]: item for item in items if item.get("name")}

    @staticmethod
    def _match_project_candidates(
        project_name: str, project_info_list: dict[str, dict[str, Any]]
    ) -> list[tuple[str, dict[str, Any]]]:
        normalized_project_name = (project_name or "").strip().upper()
        project_tokens = [
            token for token in re.split(r"[-_\s()]+", normalized_project_name) if token
        ]
        project_base_name = project_tokens[0] if project_tokens else ""
        candidates: list[tuple[int, int, str, str, dict[str, Any]]] = []

        for name, project_info in project_info_list.items():
            normalized_spd_name = (name or "").strip().upper()
            normalized_without_suffix = re.sub(r"\([^)]*\)", "", name or "").strip("-_ ").upper()
            spd_tokens = [
                token for token in re.split(r"[-_\s()]+", normalized_spd_name) if token
            ]
            spd_base_name = spd_tokens[0] if spd_tokens else ""
            is_candidate = (
                normalized_spd_name == normalized_project_name
                or normalized_without_suffix == normalized_project_name
                or (
                    project_base_name
                    and spd_base_name == project_base_name
                    and set(project_tokens).issubset(set(spd_tokens))
                )
            )
            if not is_candidate:
                continue

            if "SUNMAO" in normalized_spd_name:
                priority = 9
            elif normalized_spd_name == normalized_project_name:
                priority = 0
            elif normalized_without_suffix == normalized_project_name:
                priority = 1
            elif "ANDROID" in normalized_spd_name:
                priority = 3
            else:
                priority = 2
            candidates.append(
                (priority, len(normalized_spd_name), normalized_spd_name, name, project_info)
            )

        candidates.sort()
        return [(name, project_info) for _, _, _, name, project_info in candidates]

    @staticmethod
    def _feature_with_market(feature_config_list: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
        res: dict[str, dict[str, str]] = {}
        for key, value_dict in feature_config_list.items():
            market_info_list = value_dict.get("marketInfoList")
            if not market_info_list:
                continue
            market_support: dict[str, str] = {}
            for item in market_info_list:
                market = item.get("market")
                value = item.get("value")
                if market is None or value is None:
                    continue
                market_support[str(market)] = (
                    "0" if ("不参加" in str(value) or "不支持" in str(value)) else "1"
                )
            res[key] = market_support
        return res

    def _load_merged_features(self, spec_bid: str, *, page: int = 1, size: int = 99999) -> dict[str, dict[str, Any]]:
        feature_resp = self._spd.post(
            "/productSpecificationList/queryFeatureConfigList",
            json_body={
                "bid": spec_bid,
                "current": page,
                "size": size,
                "myRelated": False,
            },
        )
        feature_records = ((feature_resp.get("data") or {}).get("records")) or []
        common: dict[str, dict[str, Any]] = {}
        for item in feature_records:
            code = item.get("lv4Code")
            if not code:
                continue
            common[code] = {
                k: item[k]
                for k in ("lv4Code", "lv4Name", "description", "versionNumber", "marketInfoList")
                if k in item
            }

        google_resp = self._spd.post(
            "/productSpecificationList/queryGoogleProgramList",
            json_body={"bid": spec_bid},
        )
        google_items = google_resp.get("data") or []
        google: dict[str, dict[str, Any]] = {}
        for item in google_items:
            code = item.get("googleConfigCode")
            if not code:
                continue
            google[code] = {
                k: item[k]
                for k in (
                    "googleConfigCode",
                    "strategy",
                    "detail",
                    "configStatus",
                    "marketInfoList",
                )
                if k in item
            }
        return {**common, **google}

    def _pick_spec_bid(self, project_bid: str, tos_version: str | None) -> str | None:
        body: dict[str, Any] = {"projectBid": project_bid}
        if tos_version:
            body["tosVersionList"] = [tos_version]
        specs = self._spd.post(
            "/productSpecificationList/queryProductSpecificationList",
            json_body=body,
        )
        items = specs.get("data") or []
        if not items:
            return None
        if tos_version:
            for item in items:
                if item.get("tosVersion") == tos_version:
                    return item.get("bid")
            # fallback: exact match without list filter (API may ignore tosVersionList)
            raw = self._spd.post(
                "/productSpecificationList/queryProductSpecificationList",
                json_body={"projectBid": project_bid},
            )
            for item in raw.get("data") or []:
                if item.get("tosVersion") == tos_version:
                    return item.get("bid")
            return None
        return items[0].get("bid")

    # ---- handlers ----

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

    def _handle_project_list(self, _args: argparse.Namespace) -> dict[str, Any]:
        mapping = self._fetch_project_info_map()
        return {
            "code": "0000",
            "msg": "success",
            "data": [
                {"name": name, "bid": info.get("bid"), **{k: v for k, v in info.items() if k not in ("name", "bid")}}
                for name, info in mapping.items()
            ],
            "_meta": {"count": len(mapping)},
        }

    def _handle_project_detail(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._spd.post("/spd-projectInfo/getProjectInfoDetail", json_body={"bid": args.bid})

    def _handle_candidates(self, args: argparse.Namespace) -> dict[str, Any]:
        mapping = self._fetch_project_info_map()
        candidates = self._match_project_candidates(args.name, mapping)
        return {
            "code": "0000",
            "msg": "success",
            "data": [
                {
                    "name": name,
                    "bid": info.get("bid"),
                    "rank": idx + 1,
                }
                for idx, (name, info) in enumerate(candidates)
            ],
            "_meta": {
                "input": args.name,
                "count": len(candidates),
                "hint": "Prefer rank=1; SunMao ranked last. Use bid with spec/feature APIs.",
            },
        }

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

    def _handle_google_list(self, args: argparse.Namespace) -> dict[str, Any]:
        return self._spd.post(
            "/productSpecificationList/queryGoogleProgramList",
            json_body={"bid": args.spec_bid},
        )

    def _handle_market_support(self, args: argparse.Namespace) -> dict[str, Any]:
        if args.include_google == "true":
            merged = self._load_merged_features(args.spec_bid, page=args.page, size=args.size)
        else:
            feature_resp = self._spd.post(
                "/productSpecificationList/queryFeatureConfigList",
                json_body={
                    "bid": args.spec_bid,
                    "current": args.page,
                    "size": args.size,
                    "myRelated": False,
                },
            )
            records = ((feature_resp.get("data") or {}).get("records")) or []
            merged = {
                item["lv4Code"]: item
                for item in records
                if item.get("lv4Code")
            }
        support = self._feature_with_market(merged)
        return {
            "code": "0000",
            "msg": "success",
            "data": support,
            "_meta": {
                "specBid": args.spec_bid,
                "featureCount": len(support),
                "includeGoogle": args.include_google == "true",
            },
        }

    def _handle_one_step(self, args: argparse.Namespace) -> dict[str, Any]:
        mapping = self._fetch_project_info_map()
        candidates = self._match_project_candidates(args.name, mapping)
        if not candidates:
            return {
                "code": "0000",
                "msg": "success",
                "data": {},
                "_meta": {
                    "input": args.name,
                    "tosVersion": args.tos_version,
                    "warning": "No SPD project candidates matched",
                },
            }

        attempts = []
        for spd_project_name, project_info in candidates:
            product_id = project_info.get("bid")
            product_config_id = self._pick_spec_bid(product_id, args.tos_version)
            attempts.append(
                {
                    "spd_project": spd_project_name,
                    "projectBid": product_id,
                    "productConfigBid": product_config_id,
                }
            )
            if not product_config_id:
                continue
            merged = self._load_merged_features(product_config_id)
            support = self._feature_with_market(merged)
            if support:
                return {
                    "code": "0000",
                    "msg": "success",
                    "data": support,
                    "_meta": {
                        "input": args.name,
                        "tosVersion": args.tos_version,
                        "spd_project": spd_project_name,
                        "projectBid": product_id,
                        "productConfigBid": product_config_id,
                        "featureCount": len(support),
                        "attempts": attempts,
                    },
                }

        return {
            "code": "0000",
            "msg": "success",
            "data": {},
            "_meta": {
                "input": args.name,
                "tosVersion": args.tos_version,
                "warning": "All candidates tried; no market-support config obtained",
                "attempts": attempts,
            },
        }
