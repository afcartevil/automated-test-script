#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用 HTTP 请求工具：
- 支持 GET / POST 等方法
- 可选 headers（dict，支持为空）
- 可选 body_json 请求体（dict，支持为空）
- 响应被包装为 HttpResponse(status, headers, body)，headers/body 均为 dict
- debug=True 时打印请求/响应细节，便于调试

依赖：pip install requests

使用示例：
    from http_client import request, get, post

    # GET
    resp = get("https://example.com/api/info", debug=True)
    print(resp.status, resp.headers, resp.body)

    # POST 带 headers + JSON body
    resp = post(
        "https://example.com/api/login",
        headers={"X-App-Id": "xxx"},
        body_json={"username": "u", "password": "p"},
        debug=True,
    )
    token = resp.body["data"]["token"]
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

import requests
from requests import Response


DEFAULT_TIMEOUT = 15  # 秒


class HttpRequestError(Exception):
    """HTTP 请求或响应解析失败时抛出。"""


@dataclass
class HttpResponse:
    """HTTP 响应对象。

    属性:
        status:  HTTP 状态码（int）
        headers: 响应头（dict[str, str]）
        body:    响应体 JSON 解析后的字典（dict[str, Any]）
    """

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: dict[str, Any] = field(default_factory=dict)


def _print_debug_request(
    method: str,
    url: str,
    headers: Optional[dict[str, Any]],
    body_json: Optional[dict[str, Any]],
    params: Optional[dict[str, Any]],
) -> None:
    """打印请求详情（debug 模式）。"""
    print("=" * 60)
    print(f"[HTTP] >>> {method.upper()} {url}")
    if params:
        print(f"[HTTP] params : {params}")
    if headers:
        print(f"[HTTP] headers: {headers}")
    if body_json is not None:
        try:
            body_str = json.dumps(body_json, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            body_str = str(body_json)
        print(f"[HTTP] body   : {body_str}")


def _print_debug_response(resp: Response) -> None:
    """打印响应详情（debug 模式）。"""
    print(f"[HTTP] <<< status : {resp.status_code}")
    print(f"[HTTP] <<< headers: {dict(resp.headers)}")
    text = resp.text
    if len(text) > 2000:
        text = text[:2000] + "...<truncated>"
    print(f"[HTTP] <<< body   : {text}")
    print("=" * 60)


def request(
    url: str,
    method: str = "GET",
    headers: Optional[dict[str, Any]] = None,
    body_json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    debug: bool = False,
    raise_for_status: bool = True,
) -> HttpResponse:
    """
    发送 HTTP 请求，返回 HttpResponse(status, headers, body)。

    参数:
        url: 完整请求地址。
        method: 请求方法，默认 GET，支持 GET/POST/PUT/DELETE 等。
        headers: 请求头键值对，可为空。
        body_json: JSON 请求体（dict），可为空；非空时自动以 JSON 序列化发送。
        params: URL 查询参数，可为空。
        timeout: 请求超时（秒）。
        debug: 为 True 时打印请求/响应详情。
        raise_for_status: 为 True 时遇到 4xx/5xx 抛 HttpRequestError。

    返回:
        HttpResponse:
            - status:  状态码 int
            - headers: 响应头 dict
            - body:    响应体 JSON 解析后的 dict

    异常:
        HttpRequestError: 请求失败、状态码异常或响应非合法 JSON。
    """
    method = method.upper()
    headers = headers or None
    params = params or None

    if debug:
        _print_debug_request(method, url, headers, body_json, params)

    try:
        resp = requests.request(
            method=method,
            url=url,
            headers=headers,
            json=body_json if body_json is not None else None,
            params=params,
            timeout=timeout,
        )
    except requests.RequestException as e:
        if debug:
            print(f"[HTTP] !!! request error: {e}")
        raise HttpRequestError(f"请求失败: {e}") from e

    if debug:
        _print_debug_response(resp)

    if raise_for_status and not resp.ok:
        raise HttpRequestError(
            f"HTTP 状态码异常: {resp.status_code}, body={resp.text!r}"
        )

    try:
        body = resp.json()
    except ValueError as e:
        raise HttpRequestError(
            f"响应不是合法 JSON: {e}, body={resp.text!r}"
        ) from e

    if not isinstance(body, dict):
        raise HttpRequestError(
            f"响应 JSON 根节点不是对象(dict)，实际类型: {type(body).__name__}, "
            f"body={resp.text!r}"
        )

    return HttpResponse(
        status=resp.status_code,
        headers=dict(resp.headers),
        body=body,
    )


def get(
    url: str,
    headers: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    debug: bool = False,
    raise_for_status: bool = True,
) -> HttpResponse:
    """便捷 GET 请求，返回 HttpResponse。"""
    return request(
        url=url,
        method="GET",
        headers=headers,
        params=params,
        timeout=timeout,
        debug=debug,
        raise_for_status=raise_for_status,
    )


def post(
    url: str,
    headers: Optional[dict[str, Any]] = None,
    body_json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
    timeout: float = DEFAULT_TIMEOUT,
    debug: bool = False,
    raise_for_status: bool = True,
) -> HttpResponse:
    """便捷 POST 请求（JSON body），返回 HttpResponse。"""
    return request(
        url=url,
        method="POST",
        headers=headers,
        body_json=body_json,
        params=params,
        timeout=timeout,
        debug=debug,
        raise_for_status=raise_for_status,
    )
