"""
SCMP 项目与分区策略 API — 按分区类型路由

tr_product : queryProjectInfoByNameLike + getPartitionStrategyByPage + getPartitionStrategyDetail
tr_region  : queryProjectInfoTree + getPartitionStrategyByPage + getPartitionStrategyDetail
tr_carrier : 同 tr_region（推导，无独立 HAR）
"""

from __future__ import annotations

import argparse
from typing import Any

from tones_cli.modules.base import ApiModule
from tones_cli.modules.partition_profiles import get_partition, partition_arg


def _flatten_project_tree(
    nodes: list[dict[str, Any]],
    *,
    keyword: str = "",
    include_markets: bool = False,
) -> list[dict[str, Any]]:
    """Flatten queryProjectInfoTree nodes for agent-friendly JSON."""
    needle = keyword.lower()
    flat: list[dict[str, Any]] = []

    def walk(node: dict[str, Any], parent_name: str | None = None) -> None:
        name = node.get("name") or ""
        project_name = node.get("projectName") or name
        node_type = node.get("type")
        entry = {
            "bid": node.get("bid"),
            "name": name,
            "projectName": project_name,
            "type": node_type,
            "parentName": parent_name,
            "isMarket": node_type == 1,
        }
        matched = not needle or needle in name.lower() or needle in project_name.lower()
        if matched and (include_markets or node_type != 1):
            flat.append(entry)
        for child in node.get("children") or []:
            walk(child, parent_name=name if node_type == 0 else parent_name)

    for root in nodes:
        walk(root)
    return flat


class ScmpProjectStrategyModule(ApiModule):
    name = "scmp-project-strategy"
    description = "SCMP 项目模糊查询与分区策略配置（按 tr_product / tr_region / tr_carrier）"

    def register_commands(self, scmp_subparsers) -> None:
        project = scmp_subparsers.add_parser("project", help="Project search (partition-aware)")
        project_sub = project.add_subparsers(dest="project_command", required=True)
        self._register_project_search(project_sub)

        partition = scmp_subparsers.add_parser("partition", help="Partition group helpers")
        partition_sub = partition.add_subparsers(dest="partition_command", required=True)
        self._register_partition_groups(partition_sub)
        self._register_partition_list(partition_sub)

        strategy = scmp_subparsers.add_parser("strategy", help="Partition strategy operations")
        strategy_sub = strategy.add_subparsers(dest="strategy_command", required=True)
        self._register_strategy_list(strategy_sub)
        self._register_strategy_detail(strategy_sub)

    def _register_project_search(self, parent) -> None:
        cmd = parent.add_parser(
            "search",
            help="Fuzzy search projects (API depends on --partition)",
        )
        partition_arg(cmd)
        cmd.add_argument("--name", required=True, help="Project name keyword, e.g. KM9 or X6886")
        cmd.add_argument(
            "--include-markets",
            action="store_true",
            help="For tr_region/tr_carrier tree: include market children (type=1) in output",
        )
        cmd.set_defaults(handler=self._handle_project_search, output_kind="project")

    def _register_partition_groups(self, parent) -> None:
        cmd = parent.add_parser(
            "groups",
            help="List partition groups from API (queryPartitionGroupInfoList)",
        )
        cmd.set_defaults(handler=self._handle_partition_groups, output_kind="partition")

    def _register_partition_list(self, parent) -> None:
        cmd = parent.add_parser(
            "list",
            help="List built-in partition profiles (tr_product / tr_region / tr_carrier)",
        )
        cmd.set_defaults(handler=self._handle_partition_list, output_kind="partition-list")

    def _register_strategy_list(self, parent) -> None:
        cmd = parent.add_parser(
            "list",
            help="List strategies for a project (getPartitionStrategyByPage)",
        )
        partition_arg(cmd)
        cmd.add_argument(
            "--project-name",
            required=True,
            help='Project name from search (tr_product: data[].name; tree: parent name field)',
        )
        cmd.add_argument("--page", type=int, default=1)
        cmd.add_argument("--size", type=int, default=10)
        cmd.add_argument("--strategy-type", type=int, default=0)
        cmd.add_argument("--status", type=int, default=0)
        cmd.add_argument(
            "--market",
            default=None,
            help="Optional market filter (tr_region HAR sends null when unused)",
        )
        cmd.add_argument(
            "--strategy-code",
            default=None,
            help="Client-side filter: strategy code substring match",
        )
        cmd.set_defaults(handler=self._handle_strategy_list, output_kind="strategy")

    def _register_strategy_detail(self, parent) -> None:
        cmd = parent.add_parser(
            "detail",
            help="Strategy full config (getPartitionStrategyDetail)",
        )
        partition_arg(cmd)
        group = cmd.add_mutually_exclusive_group(required=True)
        group.add_argument("--bid", help="Strategy bid, e.g. sid_2061361261089660928")
        group.add_argument(
            "--strategy-code",
            help="Resolve bid via strategy list (requires --project-name)",
        )
        cmd.add_argument(
            "--project-name",
            default=None,
            help="Required when using --strategy-code instead of --bid",
        )
        cmd.add_argument(
            "--market",
            default=None,
            help="Optional market when resolving --strategy-code on tr_region/tr_carrier",
        )
        cmd.add_argument(
            "--attr-code",
            default=None,
            help="Filter attributeInfo to matching attrCode (exact or substring)",
        )
        cmd.add_argument(
            "--attrs-only",
            action="store_true",
            help="Return only attributeInfo section from detail",
        )
        cmd.set_defaults(handler=self._handle_strategy_detail, output_kind="strategy-detail")

    def _handle_project_search(self, args: argparse.Namespace) -> dict[str, Any]:
        profile = get_partition(args.partition)
        if profile.project_api == "name_like":
            return self.client.post(
                "/projectInfo/queryProjectInfoByNameLike",
                json_body={"name": args.name},
            )

        result = self.client.post(
            "/projectInfo/queryProjectInfoTree",
            json_body={"name": args.name},
        )
        tree = result.get("data") or []
        if not isinstance(tree, list):
            return result
        flat = _flatten_project_tree(
            tree,
            keyword=args.name,
            include_markets=args.include_markets,
        )
        return {
            "code": result.get("code", "0000"),
            "msg": result.get("msg", "success"),
            "data": flat,
            "_meta": {
                "partition": profile.code,
                "api": "queryProjectInfoTree",
                "hint": "Use parent `name` as --project-name for strategy list; markets are type=1 children.",
            },
        }

    def _handle_partition_groups(self, _args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post("/partitionInfo/queryPartitionGroupInfoList", empty_body=True)

    def _handle_partition_list(self, _args: argparse.Namespace) -> dict[str, Any]:
        from tones_cli.modules.partition_profiles import PARTITION_PROFILES

        return {
            "code": "0000",
            "msg": "success",
            "data": [
                {
                    "partition": p.code,
                    "partitionGroupBid": p.bid,
                    "label": p.label,
                    "projectSearchApi": p.project_api,
                    "har": p.har_note,
                }
                for p in PARTITION_PROFILES.values()
            ],
        }

    def _strategy_list_body(self, args: argparse.Namespace) -> dict[str, Any]:
        profile = get_partition(args.partition)
        body: dict[str, Any] = {
            "current": args.page,
            "size": args.size,
            "partitionGroupBid": profile.bid,
            "strategyType": args.strategy_type,
            "status": args.status,
            "projectName": args.project_name,
        }
        if args.market is not None:
            body["market"] = args.market
        elif profile.code in ("tr_region", "tr_carrier"):
            body["market"] = None
        return body

    def _handle_strategy_list(self, args: argparse.Namespace) -> dict[str, Any]:
        result = self.client.post(
            "/partitionStrategy/getPartitionStrategyByPage",
            json_body=self._strategy_list_body(args),
        )
        if args.strategy_code and isinstance(result.get("data"), dict):
            records = result["data"].get("records") or []
            needle = args.strategy_code.lower()
            result["data"]["records"] = [
                r for r in records if needle in (r.get("strategyCode") or "").lower()
            ]
            result["data"]["total"] = len(result["data"]["records"])
        profile = get_partition(args.partition)
        result["_meta"] = {"partition": profile.code, "partitionGroupBid": profile.bid}
        return result

    def _resolve_strategy_bid(self, args: argparse.Namespace) -> str:
        if args.bid:
            return args.bid
        if not args.project_name:
            raise ValueError("--project-name is required when resolving --strategy-code")
        list_args = argparse.Namespace(
            partition=args.partition,
            project_name=args.project_name,
            page=1,
            size=50,
            strategy_type=0,
            status=0,
            market=getattr(args, "market", None),
            strategy_code=args.strategy_code,
        )
        listed = self._handle_strategy_list(list_args)
        records = (listed.get("data") or {}).get("records") or []
        if not records:
            raise ValueError(
                f"No strategy found for partition={args.partition} "
                f"code={args.strategy_code} project={args.project_name}"
            )
        if len(records) > 1:
            codes = [r.get("strategyCode") for r in records]
            raise ValueError(
                f"Multiple strategies match '{args.strategy_code}': {codes}. "
                "Use --bid with a specific sid_..."
            )
        return records[0]["bid"]

    def _handle_strategy_detail(self, args: argparse.Namespace) -> dict[str, Any]:
        profile = get_partition(args.partition)
        bid = self._resolve_strategy_bid(args)
        result = self.client.get(f"/partitionStrategy/getPartitionStrategyDetail/{bid}")
        data = result.get("data")
        if not isinstance(data, dict):
            return result

        if args.attr_code:
            attrs = data.get("attributeInfo") or []
            needle = args.attr_code.lower()
            data["attributeInfo"] = [
                a for a in attrs if needle in (a.get("attrCode") or "").lower()
            ]

        if args.attrs_only:
            result["data"] = {
                "bid": data.get("bid"),
                "strategyCode": data.get("strategyCode"),
                "partitionCode": data.get("partitionCode"),
                "projectName": data.get("projectName"),
                "attributeInfo": data.get("attributeInfo") or [],
            }
        result["_meta"] = {"partition": profile.code, "partitionGroupBid": profile.bid}
        return result
