#!/usr/bin/env python3
from __future__ import annotations

import json
import mimetypes
import os
import sys
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from qiwei_qunfa_mcp import __version__

API_BASE = os.getenv("QIWEI_API_BASE", "https://xapi.ytk.life").rstrip("/")
API_TOKEN = os.getenv("QIWEI_API_TOKEN", "")
API_PREFIX = "/api/v1/wecom-broadcast"


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TASK_PAYLOAD_SCHEMA = {
    "name": {"type": "string", "description": "任务名称"},
    "text_content": {"type": "string", "description": "群发文本内容"},
    "status": {
        "type": "string",
        "description": "任务状态，常用 draft 或 pending；pending 会按后端规则触发发送或定时发送",
    },
    "send_type": {
        "type": "string",
        "description": "发送类型，immediate 或 scheduled",
        "default": "immediate",
    },
    "scheduled_at": {
        "type": "string",
        "description": "定时发送时间，ISO 格式；非定时可省略",
    },
    "repeat_type": {"type": "string", "default": "none"},
    "repeat_until": {"type": "string", "description": "重复截止时间，ISO 格式"},
    "image_first": {"type": "boolean", "default": True},
    "group_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "收件人组 ID 列表",
    },
    "user_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "企微用户 ID 列表",
    },
    "chat_ids": {
        "type": "array",
        "items": {"type": "integer"},
        "description": "企微群聊 ID 列表",
    },
    "image_urls": {
        "type": "array",
        "items": {"type": "string"},
        "description": "已上传图片 URL 列表",
    },
}


TOOLS = [
    {
        "name": "search_wecom_users",
        "description": "搜索企微用户。需要 recipient_group.view 权限。",
        "inputSchema": schema({"keyword": {"type": "string", "default": ""}}),
    },
    {
        "name": "refresh_wecom_users",
        "description": "从企微数据源刷新用户。需要 recipient_group.edit 权限。",
        "inputSchema": schema({}),
    },
    {
        "name": "search_wecom_chats",
        "description": "搜索企微群聊。需要 recipient_group.view 权限。",
        "inputSchema": schema({"keyword": {"type": "string", "default": ""}}),
    },
    {
        "name": "refresh_wecom_chats",
        "description": "从企微数据源刷新群聊。需要 recipient_group.edit 权限。",
        "inputSchema": schema({}),
    },
    {
        "name": "list_recipient_groups",
        "description": "列出收件人组。需要 recipient_group.view 权限。",
        "inputSchema": schema({}),
    },
    {
        "name": "create_recipient_group",
        "description": "创建收件人组。需要 recipient_group.create 权限。",
        "inputSchema": schema(
            {
                "name": {"type": "string"},
                "description": {"type": "string", "default": ""},
                "user_ids": {"type": "array", "items": {"type": "integer"}},
                "chat_ids": {"type": "array", "items": {"type": "integer"}},
            },
            ["name"],
        ),
    },
    {
        "name": "update_recipient_group",
        "description": "更新收件人组名称和说明。需要 recipient_group.edit 权限。",
        "inputSchema": schema(
            {
                "group_id": {"type": "integer"},
                "name": {"type": "string"},
                "description": {"type": "string", "default": ""},
            },
            ["group_id", "name"],
        ),
    },
    {
        "name": "delete_recipient_group",
        "description": "删除收件人组。需要 recipient_group.delete 权限。",
        "inputSchema": schema({"group_id": {"type": "integer"}}, ["group_id"]),
    },
    {
        "name": "list_broadcast_tasks",
        "description": "查询群发任务列表。需要 wecom_broadcast.view 权限。",
        "inputSchema": schema(
            {
                "name": {"type": "string", "default": ""},
                "status": {"type": "string", "default": ""},
                "send_type": {"type": "string", "default": ""},
            }
        ),
    },
    {
        "name": "get_broadcast_task",
        "description": "查询群发任务详情。需要 wecom_broadcast.view 权限。",
        "inputSchema": schema({"task_id": {"type": "integer"}}, ["task_id"]),
    },
    {
        "name": "create_broadcast_task",
        "description": "创建群发任务。需要 wecom_broadcast.create 权限。",
        "inputSchema": schema(TASK_PAYLOAD_SCHEMA, ["name", "text_content", "status"]),
    },
    {
        "name": "update_broadcast_task",
        "description": "更新群发任务。需要 wecom_broadcast.edit 权限。",
        "inputSchema": schema(
            {"task_id": {"type": "integer"}, **TASK_PAYLOAD_SCHEMA},
            ["task_id", "name", "text_content", "status"],
        ),
    },
    {
        "name": "cancel_broadcast_task",
        "description": "取消群发任务。需要 wecom_broadcast.execute 权限。",
        "inputSchema": schema({"task_id": {"type": "integer"}}, ["task_id"]),
    },
    {
        "name": "delete_broadcast_task",
        "description": "删除群发任务。需要 wecom_broadcast.delete 权限。",
        "inputSchema": schema({"task_id": {"type": "integer"}}, ["task_id"]),
    },
    {
        "name": "upload_broadcast_image",
        "description": "上传群发图片。需要 wecom_broadcast.create 权限。",
        "inputSchema": schema(
            {"file_path": {"type": "string", "description": "本地图片绝对路径"}},
            ["file_path"],
        ),
    },
]


def api_headers(extra: dict[str, str] | None = None) -> dict[str, str]:
    headers = {"Accept": "application/json"}
    if API_TOKEN:
        headers["Authorization"] = f"Bearer {API_TOKEN}"
    if extra:
        headers.update(extra)
    return headers


def api_request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    url = f"{API_BASE}{API_PREFIX}{path}"
    if params:
        clean_params = {
            key: value
            for key, value in params.items()
            if value is not None and value != ""
        }
        if clean_params:
            url = f"{url}?{urlencode(clean_params)}"
    data = None
    headers = api_headers()
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=60) as response:
            body = response.read()
            if not body:
                return {"ok": True}
            return json.loads(body.decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(read_http_error(exc)) from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接后端 API: {exc.reason}") from exc


def upload_file(path: str) -> Any:
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise RuntimeError(f"图片文件不存在: {file_path}")
    boundary = f"----qiwei-mcp-{uuid.uuid4().hex}"
    content_type = mimetypes.guess_type(str(file_path))[0] or "application/octet-stream"
    file_bytes = file_path.read_bytes()
    parts = [
        f"--{boundary}\r\n".encode("utf-8"),
        (
            'Content-Disposition: form-data; name="file"; '
            f'filename="{file_path.name}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        f"\r\n--{boundary}--\r\n".encode("utf-8"),
    ]
    data = b"".join(parts)
    headers = api_headers(
        {
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(data)),
        }
    )
    request = Request(
        f"{API_BASE}{API_PREFIX}/images",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=120) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(read_http_error(exc)) from exc
    except URLError as exc:
        raise RuntimeError(f"无法连接后端 API: {exc.reason}") from exc


def read_http_error(exc: HTTPError) -> str:
    body = exc.read().decode("utf-8", errors="replace")
    try:
        detail = json.loads(body).get("detail", body)
    except json.JSONDecodeError:
        detail = body
    return f"后端 API 返回 {exc.code}: {detail}"


def task_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": arguments["name"],
        "text_content": arguments["text_content"],
        "status": arguments["status"],
        "send_type": arguments.get("send_type", "immediate"),
        "scheduled_at": arguments.get("scheduled_at"),
        "repeat_type": arguments.get("repeat_type", "none"),
        "repeat_until": arguments.get("repeat_until"),
        "image_first": arguments.get("image_first", True),
        "group_ids": arguments.get("group_ids", []),
        "user_ids": arguments.get("user_ids", []),
        "chat_ids": arguments.get("chat_ids", []),
        "image_urls": arguments.get("image_urls", []),
    }


def call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if name == "search_wecom_users":
        return api_request("GET", "/users", params={"keyword": arguments.get("keyword", "")})
    if name == "refresh_wecom_users":
        return api_request("POST", "/users/refresh")
    if name == "search_wecom_chats":
        return api_request("GET", "/chats", params={"keyword": arguments.get("keyword", "")})
    if name == "refresh_wecom_chats":
        return api_request("POST", "/chats/refresh")
    if name == "list_recipient_groups":
        return api_request("GET", "/recipient-groups")
    if name == "create_recipient_group":
        return api_request(
            "POST",
            "/recipient-groups",
            payload={
                "name": arguments["name"],
                "description": arguments.get("description", ""),
                "user_ids": arguments.get("user_ids", []),
                "chat_ids": arguments.get("chat_ids", []),
            },
        )
    if name == "update_recipient_group":
        return api_request(
            "PUT",
            f"/recipient-groups/{arguments['group_id']}",
            payload={
                "name": arguments["name"],
                "description": arguments.get("description", ""),
            },
        )
    if name == "delete_recipient_group":
        return api_request("DELETE", f"/recipient-groups/{arguments['group_id']}")
    if name == "list_broadcast_tasks":
        return api_request(
            "GET",
            "/tasks",
            params={
                "name": arguments.get("name", ""),
                "status": arguments.get("status", ""),
                "send_type": arguments.get("send_type", ""),
            },
        )
    if name == "get_broadcast_task":
        return api_request("GET", f"/tasks/{arguments['task_id']}")
    if name == "create_broadcast_task":
        return api_request("POST", "/tasks", payload=task_payload(arguments))
    if name == "update_broadcast_task":
        return api_request(
            "PUT",
            f"/tasks/{arguments['task_id']}",
            payload=task_payload(arguments),
        )
    if name == "cancel_broadcast_task":
        return api_request("POST", f"/tasks/{arguments['task_id']}/cancel")
    if name == "delete_broadcast_task":
        return api_request("DELETE", f"/tasks/{arguments['task_id']}")
    if name == "upload_broadcast_image":
        return upload_file(arguments["file_path"])
    raise RuntimeError(f"未知工具: {name}")


def json_rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def json_rpc_error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def encode_tool_result(result: Any) -> dict[str, Any]:
    text = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    return {"content": [{"type": "text", "text": text}]}


def handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    request_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}
    if request_id is None:
        return None
    try:
        if method == "initialize":
            return json_rpc_result(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "qiwei-qunfa-mcp", "version": __version__},
                },
            )
        if method == "tools/list":
            return json_rpc_result(request_id, {"tools": TOOLS})
        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            return json_rpc_result(request_id, encode_tool_result(call_tool(name, arguments)))
        return json_rpc_error(request_id, -32601, f"不支持的方法: {method}")
    except Exception as exc:
        return json_rpc_error(request_id, -32000, str(exc))


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
            response = handle_message(message)
        except Exception as exc:
            response = json_rpc_error(None, -32700, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
