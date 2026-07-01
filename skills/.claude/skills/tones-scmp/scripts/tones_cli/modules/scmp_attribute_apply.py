"""
SCMP 属性申请清单 API — derived from scmp属性清单信息.har

Endpoints:
  POST /attributeApply/attributeApplyResponsiblePersonSelect  (empty body)
  POST /attributeApply/attributeApplyPersonSelect               (empty body)
  GET  /attributeInfo/getSecondDepartmentSelect
  GET  /attributeInfo/getThirdDepartmentSelect
  POST /attributeApply/getAttributeApplyCountByStatus
  POST /attributeApply/queryAttributeApplyByPage
"""

from __future__ import annotations

import argparse
from typing import Any

from tones_cli.modules.base import ApiModule


class ScmpAttributeApplyModule(ApiModule):
    name = "scmp"
    description = "SCMP 属性申请清单 (tones-build-platform/attributeApply)"

    def register_commands(self, scmp_subparsers) -> None:
        """Register apply/department subcommands under an existing `scmp` parser."""

        apply = scmp_subparsers.add_parser("apply", help="Attribute apply operations")
        apply_sub = apply.add_subparsers(dest="apply_command", required=True)

        self._register_list(apply_sub)
        self._register_count(apply_sub)
        self._register_responsible_persons(apply_sub)
        self._register_persons(apply_sub)

        dept = scmp_subparsers.add_parser("department", help="Department selectors")
        dept_sub = dept.add_subparsers(dest="dept_command", required=True)
        self._register_second_department(dept_sub)
        self._register_third_department(dept_sub)

    def _register_list(self, parent) -> None:
        cmd = parent.add_parser(
            "list",
            help="Paginated attribute apply list (queryAttributeApplyByPage)",
        )
        cmd.add_argument("--page", type=int, default=1, help="Page number (current)")
        cmd.add_argument("--size", type=int, default=10, help="Page size")
        cmd.add_argument(
            "--status",
            type=int,
            default=None,
            choices=[0, 1, 2, 3],
            help="Filter by status: 0=待审批 1=未通过 2=已通过 3=取消; omit for all",
        )
        cmd.add_argument(
            "--attr-code",
            default=None,
            help="Filter by attribute code (if supported by API)",
        )
        cmd.add_argument(
            "--apply-code",
            default=None,
            help="Filter by apply code",
        )
        cmd.set_defaults(handler=self._handle_list, output_kind="apply")

    def _register_count(self, parent) -> None:
        cmd = parent.add_parser(
            "count",
            help="Count by status (getAttributeApplyCountByStatus)",
        )
        cmd.add_argument("--page", type=int, default=1)
        cmd.add_argument("--size", type=int, default=10)
        cmd.add_argument("--status", type=int, default=None, choices=[0, 1, 2, 3, 4])
        cmd.set_defaults(handler=self._handle_count, output_kind="count")

    def _register_responsible_persons(self, parent) -> None:
        cmd = parent.add_parser(
            "responsible-persons",
            help="List responsible person options",
        )
        cmd.set_defaults(handler=self._handle_responsible_persons)

    def _register_persons(self, parent) -> None:
        cmd = parent.add_parser("persons", help="List apply person options")
        cmd.set_defaults(handler=self._handle_persons)

    def _register_second_department(self, parent) -> None:
        cmd = parent.add_parser("second", help="Second-level department list")
        cmd.set_defaults(handler=self._handle_second_department)

    def _register_third_department(self, parent) -> None:
        cmd = parent.add_parser("third", help="Third-level department list")
        cmd.set_defaults(handler=self._handle_third_department)

    # --- handlers ---

    def _page_body(self, args: argparse.Namespace) -> dict[str, Any]:
        body: dict[str, Any] = {
            "current": args.page,
            "size": args.size,
            "status": getattr(args, "status", None),
        }
        if getattr(args, "attr_code", None):
            body["attrCode"] = args.attr_code
        if getattr(args, "apply_code", None):
            body["applyCode"] = args.apply_code
        return body

    def _handle_list(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post(
            "/attributeApply/queryAttributeApplyByPage",
            json_body=self._page_body(args),
        )

    def _handle_count(self, args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post(
            "/attributeApply/getAttributeApplyCountByStatus",
            json_body=self._page_body(args),
        )

    def _handle_responsible_persons(self, _args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post(
            "/attributeApply/attributeApplyResponsiblePersonSelect",
            empty_body=True,
        )

    def _handle_persons(self, _args: argparse.Namespace) -> dict[str, Any]:
        return self.client.post(
            "/attributeApply/attributeApplyPersonSelect",
            empty_body=True,
        )

    def _handle_second_department(self, _args: argparse.Namespace) -> dict[str, Any]:
        return self.client.get("/attributeInfo/getSecondDepartmentSelect")

    def _handle_third_department(self, _args: argparse.Namespace) -> dict[str, Any]:
        return self.client.get("/attributeInfo/getThirdDepartmentSelect")

