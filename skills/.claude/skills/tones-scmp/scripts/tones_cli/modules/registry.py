"""Registry of HAR-derived API modules — extend here when adding new HAR captures."""

from __future__ import annotations

from tones_cli.modules.base import ApiModule
from tones_cli.modules.scmp_attribute_apply import ScmpAttributeApplyModule
from tones_cli.modules.scmp_attribute_info import ScmpAttributeInfoModule
from tones_cli.modules.scmp_project_strategy import ScmpProjectStrategyModule
from tones_cli.modules.scmp_spd_spec import ScmpSpdSpecModule

# Order matters for help text display.
REGISTERED_MODULES: list[type[ApiModule]] = [
    ScmpAttributeApplyModule,
    ScmpAttributeInfoModule,
    ScmpProjectStrategyModule,
    ScmpSpdSpecModule,
]


def all_modules() -> list[ApiModule]:
    return [cls() for cls in REGISTERED_MODULES]
