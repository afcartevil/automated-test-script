from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecMatch:
    spd_project: str
    project_bid: str
    spec_bid: str
    tos_version: str
    market_list: list[str]


def pick_unique_spec(
    candidates: list[dict],
    tos_version: str,
) -> SpecMatch:
    matches: list[SpecMatch] = []
    for candidate in candidates:
        name = str(candidate.get("name") or "")
        project_bid = str(candidate.get("bid") or "")
        for spec in candidate.get("specs") or []:
            if spec.get("tosVersion") != tos_version:
                continue
            spec_bid = spec.get("bid")
            if not spec_bid:
                continue
            matches.append(
                SpecMatch(
                    spd_project=name,
                    project_bid=project_bid,
                    spec_bid=str(spec_bid),
                    tos_version=str(spec.get("tosVersion") or tos_version),
                    market_list=list(spec.get("marketList") or []),
                )
            )

    usable = [item for item in matches if "SUNMAO" not in item.spd_project.upper()]
    pool = usable or matches
    if not pool:
        names = [str(item.get("name") or "") for item in candidates]
        raise ValueError(
            f"SCMP 未找到 tosVersion={tos_version} 的产品规格。候选项目: {names}"
        )
    if len(pool) > 1:
        detail = [
            f"{item.spd_project} ({item.spec_bid})"
            for item in pool
        ]
        raise ValueError(
            f"SCMP 找到多个 tosVersion={tos_version} 规格，拒绝猜测: {detail}"
        )
    return pool[0]
