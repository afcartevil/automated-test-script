"""TONES CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys

from tones_cli import __version__
from tones_cli.config import (
    config_path,
    ensure_config_exists,
    load_config,
    mask_secret,
    set_config_value,
)
from tones_cli.modules.scmp_common import dispatch_scmp


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tones-cli",
        description="CLI for TONES platform APIs (extensible HAR-based modules)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON (for Agent / skill integration)",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    sub = parser.add_subparsers(dest="command", required=True)

    _register_config_commands(sub)
    _register_scmp_commands(sub)

    return parser


def _register_config_commands(sub) -> None:
    config = sub.add_parser("config", help="Manage shared auth configuration")
    config_sub = config.add_subparsers(dest="config_command", required=True)

    config_sub.add_parser("path", help="Print config file path").set_defaults(
        config_handler=_config_path
    )
    config_sub.add_parser("show", help="Show effective config (secrets masked)").set_defaults(
        config_handler=_config_show
    )
    config_sub.add_parser("init", help="Create config file from template").set_defaults(
        config_handler=_config_init
    )

    set_cmd = config_sub.add_parser("set", help="Set a config value by dotted key")
    set_cmd.add_argument("key", help="Dotted key, e.g. auth_profiles.hk-intra-paas.p_auth")
    set_cmd.add_argument("value", help="Value to set")
    set_cmd.set_defaults(config_handler=_config_set)


def _register_scmp_commands(sub) -> None:
    from tones_cli.modules.scmp_attribute_apply import ScmpAttributeApplyModule
    from tones_cli.modules.scmp_attribute_info import ScmpAttributeInfoModule
    from tones_cli.modules.scmp_project_strategy import ScmpProjectStrategyModule
    from tones_cli.modules.scmp_spd_spec import ScmpSpdSpecModule

    scmp_parser = sub.add_parser(
        "scmp",
        help="SCMP APIs (属性/项目/策略/SPD清单)",
    )
    scmp_sub = scmp_parser.add_subparsers(dest="scmp_command", required=True)
    ScmpAttributeApplyModule().register_commands(scmp_sub)
    ScmpAttributeInfoModule().register_commands(scmp_sub)
    ScmpProjectStrategyModule().register_commands(scmp_sub)
    ScmpSpdSpecModule().register_commands(scmp_sub)


def _config_path(_args: argparse.Namespace) -> int:
    print(config_path())
    return 0


def _config_init(_args: argparse.Namespace) -> int:
    path = ensure_config_exists()
    print(f"Config ready at: {path}")
    return 0


def _config_show(args: argparse.Namespace) -> int:
    cfg = load_config()
    masked = _mask_config(cfg)
    print(json.dumps(masked, ensure_ascii=False, indent=2))
    return 0


def _config_set(args: argparse.Namespace) -> int:
    set_config_value(args.key, args.value)
    print(f"Set {args.key} in {config_path()}")
    return 0


def _mask_config(cfg: dict) -> dict:
    result = json.loads(json.dumps(cfg))
    profiles = result.get("auth_profiles") or {}
    secret_keys = {"authorization", "p_auth", "p_rtoken"}
    for profile in profiles.values():
        if not isinstance(profile, dict):
            continue
        for key in secret_keys:
            if key in profile and profile[key]:
                profile[key] = mask_secret(str(profile[key]))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "config":
        return args.config_handler(args)

    if args.command == "scmp":
        return dispatch_scmp(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
