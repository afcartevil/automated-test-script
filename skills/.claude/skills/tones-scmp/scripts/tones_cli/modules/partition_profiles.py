"""Known SCMP partition group profiles (from queryPartitionGroupInfoList HAR)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

PartitionCode = Literal["tr_product", "tr_region", "tr_carrier"]


@dataclass(frozen=True)
class PartitionProfile:
    code: PartitionCode
    bid: str
    label: str
    project_api: Literal["name_like", "tree"]
    har_note: str


PARTITION_PROFILES: dict[str, PartitionProfile] = {
    "tr_product": PartitionProfile(
        code="tr_product",
        bid="1234567892",
        label="项目定制软件（公共分区）",
        project_api="name_like",
        har_note="scmp根据项目名称模糊查询项目信息.har / scmp查询项目策略信息.har / scmp查询某个策略的具体配置信息.har",
    ),
    "tr_region": PartitionProfile(
        code="tr_region",
        bid="1234567894",
        label="区域定制软件",
        project_api="tree",
        har_note="scmp根据区域分区中项目信息名称模糊查询项目信息.har / scmp根据区域分区中策略信息查询策略详情.har",
    ),
    "tr_carrier": PartitionProfile(
        code="tr_carrier",
        bid="1234567893",
        label="运营商定制软件",
        project_api="tree",
        har_note="由 tr_region 同模式推导（无独立 HAR）",
    ),
}


def get_partition(code: str) -> PartitionProfile:
    key = code.strip().lower()
    if key not in PARTITION_PROFILES:
        choices = ", ".join(sorted(PARTITION_PROFILES))
        raise ValueError(
            f"Unknown partition '{code}'. Choose one of: {choices}. "
            "Run `scmp partition groups` to list partitionGroupBid values."
        )
    return PARTITION_PROFILES[key]


def partition_arg(parser) -> None:
    parser.add_argument(
        "--partition",
        required=True,
        choices=sorted(PARTITION_PROFILES),
        help="Partition code: tr_product (项目定制) | tr_region (区域) | tr_carrier (运营商)",
    )
