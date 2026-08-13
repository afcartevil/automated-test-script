"""TONES CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys

from tones_cli import __version__
from tones_cli.modules.scmp_common import dispatch_scmp
from tones_cli.uac_login import auth_status, ensure_auth


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

    _register_auth_commands(sub)
    _register_scmp_commands(sub)

    return parser


def _register_auth_commands(sub) -> None:
    auth = sub.add_parser("auth", help="UAC auto-login (built-in credentials)")
    auth_sub = auth.add_subparsers(dest="auth_command", required=True)

    login = auth_sub.add_parser("login", help="Login via UAC and cache token")
    login.add_argument(
        "--force",
        action="store_true",
        help="Force refresh even if a cached token exists",
    )
    login.set_defaults(auth_handler=_auth_login)

    auth_sub.add_parser("status", help="Show whether a token cache exists").set_defaults(
        auth_handler=_auth_status
    )


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


def _auth_login(args: argparse.Namespace) -> int:
    auth = ensure_auth(force_refresh=bool(args.force))
    result = {
        "code": "0000",
        "msg": "success",
        "data": {
            "logged_in": True,
            "p_auth_present": bool(auth.get("p_auth") or auth.get("authorization")),
            "p_rtoken_present": bool(auth.get("p_rtoken")),
            "forced": bool(args.force),
        },
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print("UAC login OK (token cached)")
    return 0


def _auth_status(args: argparse.Namespace) -> int:
    result = auth_status()
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        data = result["data"]
        state = "cached" if data["cached"] else "missing"
        print(f"auth status: {state} ({data['token_file']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "auth":
        return args.auth_handler(args)

    if args.command == "scmp":
        # 业务命令入口前确保有 token（无缓存则自动登录）
        ensure_auth()
        return dispatch_scmp(args)

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
