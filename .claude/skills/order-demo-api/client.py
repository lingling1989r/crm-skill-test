#!/usr/bin/env python3
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_BASE_URL = "http://111.229.202.81:3021/api/v1"
DEFAULT_LOGIN_PATH = "/auth/login"
TOKEN_CANDIDATE_PATHS = [
    ("accessToken",),
    ("access_token",),
    ("token",),
    ("jwt",),
    ("data", "accessToken"),
    ("data", "access_token"),
    ("data", "token"),
    ("result", "accessToken"),
    ("result", "access_token"),
    ("result", "token"),
]
CONFIG_FILE_NAME = "config.json"


class ApiError(Exception):
    def __init__(self, message, status=None, payload=None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def load_local_config():
    path = Path(__file__).with_name(CONFIG_FILE_NAME)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ApiError(f"Invalid JSON in {CONFIG_FILE_NAME}: {exc}") from exc

    if not isinstance(payload, dict):
        raise ApiError(f"{CONFIG_FILE_NAME} must contain a JSON object")
    return payload


class CRMClient:
    def __init__(self):
        self.config = load_local_config()
        self.base_url = str(os.environ.get("CRM_API_BASE_URL") or self.config.get("base_url") or DEFAULT_BASE_URL).rstrip("/")
        self.login_path = os.environ.get("CRM_API_LOGIN_PATH") or self.config.get("login_path") or DEFAULT_LOGIN_PATH
        self.timeout = float(os.environ.get("CRM_API_TIMEOUT") or self.config.get("timeout") or "20")
        self.token = os.environ.get("CRM_API_TOKEN") or self.config.get("token")

    def _url(self, path, params=None):
        full_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{full_path}"
        if params:
            query = urllib.parse.urlencode(params, doseq=True)
            if query:
                url = f"{url}?{query}"
        return url

    def _headers(self, include_auth=True):
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if include_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _login_payload(self):
        raw_payload = os.environ.get("CRM_API_LOGIN_PAYLOAD")
        if raw_payload:
            try:
                payload = json.loads(raw_payload)
            except json.JSONDecodeError as exc:
                raise ApiError(f"CRM_API_LOGIN_PAYLOAD is not valid JSON: {exc}") from exc
            if not isinstance(payload, dict):
                raise ApiError("CRM_API_LOGIN_PAYLOAD must decode to a JSON object")
            return payload

        config_payload = self.config.get("login_payload")
        if config_payload is not None:
            if not isinstance(config_payload, dict):
                raise ApiError(f"{CONFIG_FILE_NAME} field 'login_payload' must be a JSON object")
            return config_payload

        username = os.environ.get("CRM_API_USERNAME") or self.config.get("username")
        password = os.environ.get("CRM_API_PASSWORD") or self.config.get("password")
        if username and password:
            return {"username": username, "password": password}

        raise ApiError(
            f"Missing credentials. Set CRM_API_TOKEN, or add token/username/password/login_payload in {CONFIG_FILE_NAME}, or set CRM_API_LOGIN_PAYLOAD / CRM_API_USERNAME / CRM_API_PASSWORD."
        )

    def can_login(self):
        if os.environ.get("CRM_API_LOGIN_PAYLOAD"):
            return True
        if self.config.get("login_payload") is not None:
            return True
        username = os.environ.get("CRM_API_USERNAME") or self.config.get("username")
        password = os.environ.get("CRM_API_PASSWORD") or self.config.get("password")
        return bool(username and password)

    def _extract_token(self, payload):
        if isinstance(payload, str) and payload:
            return payload
        if not isinstance(payload, dict):
            return None

        for path in TOKEN_CANDIDATE_PATHS:
            current = payload
            for key in path:
                if not isinstance(current, dict) or key not in current:
                    current = None
                    break
                current = current[key]
            if isinstance(current, str) and current:
                return current
        return None

    def login(self, force=False):
        if self.token and not force:
            return {"token_source": "config" if self.config.get("token") and not os.environ.get("CRM_API_TOKEN") else "env"}

        payload = self._login_payload()
        response = self.request("POST", self.login_path, body=payload, include_auth=False, retry_auth=False)
        token = self._extract_token(response)
        if not token:
            raise ApiError("Login succeeded but no token was found in response", status=201, payload=response)
        self.token = token
        return {"token_source": "login"}

    def request(self, method, path, params=None, body=None, include_auth=True, retry_auth=True):
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            self._url(path, params=params),
            data=data,
            headers=self._headers(include_auth=include_auth),
            method=method.upper(),
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = None
            if raw:
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    payload = raw
            if exc.code == 401 and include_auth and retry_auth and self.can_login():
                self.login(force=True)
                return self.request(method, path, params=params, body=body, include_auth=include_auth, retry_auth=False)
            raise ApiError(f"HTTP {exc.code} for {method.upper()} {path}", status=exc.code, payload=payload) from exc
        except urllib.error.URLError as exc:
            raise ApiError(f"Request failed: {exc.reason}") from exc


def load_api_map():
    path = Path(__file__).with_name("api_map.json")
    return json.loads(path.read_text())


def parse_json_input(value, field_name):
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ApiError(f"Invalid JSON for {field_name}: {exc}") from exc


def parse_path_params(values):
    params = {}
    for item in values or []:
        if "=" not in item:
            raise ApiError(f"Invalid --path-param '{item}', expected key=value")
        key, value = item.split("=", 1)
        params[key] = value
    return params


def resolve_action(api_map, name, path_params):
    action = api_map.get(name)
    if not action:
        raise ApiError(f"Unknown action: {name}")

    path = action["path"]
    for key, value in path_params.items():
        path = path.replace("{" + key + "}", str(value))

    if "{" in path or "}" in path:
        raise ApiError(f"Missing path params for action {name}: {path}")
    return action, path


def resolve_chinese_action(resource, operation, entity_id):
    resource = (resource or "").strip()
    operation = (operation or "查看").strip() or "查看"

    if resource in ("概览", "总览", "dashboard"):
        return "dashboard.overview", {}

    if resource in ("知识库", "知识") and operation in ("搜索", "检索"):
        return "knowledge.search", {}

    resource_map = {
        "客户": {
            "list": "customers.list",
            "get": "customers.get",
            "create": "customers.create",
            "update": "customers.update",
            "delete": "customers.delete",
            "id_key": "customerId",
        },
        "订单": {
            "list": "orders.list",
            "get": "orders.get",
            "create": "orders.create",
            "update": "orders.update",
            "delete": "orders.delete",
            "id_key": "orderId",
        },
        "产品": {
            "list": "products.list",
            "get": "products.get",
            "create": "products.create",
            "update": "products.update",
            "delete": "products.delete",
            "id_key": "productId",
        },
        "文章": {
            "list": "knowledge.articles.list",
            "get": "knowledge.articles.get",
            "create": "knowledge.articles.create",
            "update": "knowledge.articles.update",
            "delete": "knowledge.articles.delete",
            "id_key": "articleId",
        },
        "知识文章": {
            "list": "knowledge.articles.list",
            "get": "knowledge.articles.get",
            "create": "knowledge.articles.create",
            "update": "knowledge.articles.update",
            "delete": "knowledge.articles.delete",
            "id_key": "articleId",
        },
    }

    config = resource_map.get(resource)
    if not config:
        raise ApiError(f"Unsupported Chinese resource: {resource}")

    if operation in ("列表", "全部", "查询列表", "查列表"):
        return config["list"], {}
    if operation in ("新增", "创建", "新建"):
        return config["create"], {}
    if operation in ("更新", "修改", "编辑"):
        if not entity_id:
            raise ApiError(f"{resource}{operation} requires --id")
        return config["update"], {config["id_key"]: entity_id}
    if operation in ("删除", "移除"):
        if not entity_id:
            raise ApiError(f"{resource}{operation} requires --id")
        return config["delete"], {config["id_key"]: entity_id}

    if entity_id:
        return config["get"], {config["id_key"]: entity_id}
    return config["list"], {}


DISPLAY_FIELD_CANDIDATES = [
    "id",
    "customerId",
    "orderId",
    "productId",
    "articleId",
    "orderNo",
    "name",
    "title",
    "status",
    "phone",
    "mobile",
    "email",
    "sku",
    "price",
    "createdAt",
    "updatedAt",
]
LIST_CONTAINER_KEYS = ("items", "list", "rows", "records", "results")
TOTAL_FIELD_CANDIDATES = ("total", "count", "totalCount")


def infer_resource_label(action_name=None, command_info=None):
    resource = (command_info or {}).get("resource")
    if resource:
        if resource in ("总览", "dashboard"):
            return "概览"
        if resource in ("知识",):
            return "知识库"
        return resource

    if action_name == "auth.me":
        return "当前用户"
    if action_name == "dashboard.overview":
        return "概览"
    if action_name == "knowledge.search":
        return "知识库"
    if (action_name or "").startswith("customers."):
        return "客户"
    if (action_name or "").startswith("orders."):
        return "订单"
    if (action_name or "").startswith("products."):
        return "产品"
    if (action_name or "").startswith("knowledge.articles."):
        return "文章"
    return "数据"


def infer_operation_label(action_name=None, command_info=None):
    operation = (command_info or {}).get("operation")
    if operation:
        return operation

    if action_name == "dashboard.overview":
        return "概览"
    if action_name == "knowledge.search":
        return "搜索"
    if (action_name or "").endswith(".list"):
        return "列表"
    if (action_name or "").endswith(".get") or action_name == "auth.me":
        return "查看"
    if (action_name or "").endswith(".create"):
        return "新增"
    if (action_name or "").endswith(".update"):
        return "更新"
    if (action_name or "").endswith(".delete"):
        return "删除"
    return "请求"


def extract_total(payload):
    if not isinstance(payload, dict):
        return None

    for key in TOTAL_FIELD_CANDIDATES:
        value = payload.get(key)
        if isinstance(value, int):
            return value

    nested = payload.get("data")
    if isinstance(nested, dict):
        for key in TOTAL_FIELD_CANDIDATES:
            value = nested.get(key)
            if isinstance(value, int):
                return value

    pagination = payload.get("pagination")
    if isinstance(pagination, dict):
        for key in TOTAL_FIELD_CANDIDATES:
            value = pagination.get(key)
            if isinstance(value, int):
                return value

    return None


def extract_list_items(payload):
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return None

    for key in LIST_CONTAINER_KEYS:
        value = payload.get(key)
        if isinstance(value, list):
            return value

    nested = payload.get("data")
    if isinstance(nested, list):
        return nested
    if isinstance(nested, dict):
        for key in LIST_CONTAINER_KEYS:
            value = nested.get(key)
            if isinstance(value, list):
                return value

    return None


def extract_detail_item(payload):
    if isinstance(payload, dict):
        for key in ("item", "data", "result"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
    return payload


def pick_display_fields(item):
    if not isinstance(item, dict):
        return item

    result = {}
    for key in DISPLAY_FIELD_CANDIDATES:
        value = item.get(key)
        if value not in (None, "", [], {}):
            result[key] = value

    if result:
        return result

    for key, value in item.items():
        if value in (None, "", [], {}):
            continue
        result[key] = value
        if len(result) >= 5:
            break
    return result


def summarize_success(data, action_name=None, mode=None, command_info=None):
    resource = infer_resource_label(action_name=action_name, command_info=command_info)
    operation = infer_operation_label(action_name=action_name, command_info=command_info)
    items = extract_list_items(data)

    if items is not None:
        if not items:
            return {
                "summary": f"{resource}{operation}成功，但没有匹配数据",
                "display": {
                    "type": "empty",
                    "resource": resource,
                    "operation": operation,
                    "message": "请求成功，但没有匹配数据",
                },
            }

        display_items = [pick_display_fields(item) for item in items[:5]]
        total = extract_total(data)
        summary = f"已获取{resource}{operation}结果，返回 {len(items)} 条"
        if isinstance(total, int) and total >= 0:
            summary = f"已获取{resource}{operation}结果，当前返回 {len(items)} 条，共 {total} 条"

        display = {
            "type": "list",
            "resource": resource,
            "operation": operation,
            "items": display_items,
        }
        if isinstance(total, int):
            display["total"] = total
            if total > len(items):
                display["hint"] = "如需更多结果，请继续分页查询"
        elif len(items) > len(display_items):
            display["hint"] = "当前仅展示前 5 条"

        return {"summary": summary, "display": display}

    detail = extract_detail_item(data)
    if detail in (None, {}, []):
        if mode == "write":
            message = f"已完成{resource}{operation}"
        else:
            message = f"{resource}{operation}成功，但没有返回内容"
        return {
            "summary": message,
            "display": {
                "type": "message",
                "resource": resource,
                "operation": operation,
                "message": message,
            },
        }

    if isinstance(detail, dict):
        if resource == "概览":
            summary = "已获取概览信息"
        elif mode == "write":
            summary = f"已完成{resource}{operation}"
        else:
            summary = f"已获取{resource}{operation}结果"
        return {
            "summary": summary,
            "display": {
                "type": "detail",
                "resource": resource,
                "operation": operation,
                "item": pick_display_fields(detail),
            },
        }

    return {
        "summary": f"已获取{resource}{operation}结果",
        "display": {
            "type": "value",
            "resource": resource,
            "operation": operation,
            "value": detail,
        },
    }


def summarize_error(error, status=None, details=None, path=None):
    detail_message = None
    if isinstance(details, dict):
        detail_message = details.get("message") or details.get("error")
    elif isinstance(details, str):
        detail_message = details

    if status == 401:
        summary = "请求失败：接口需要 Bearer Token 或有效登录配置"
        hint = f"请设置 CRM_API_TOKEN，或在 {CONFIG_FILE_NAME} 中填写 token / username / password / login_payload；若显式配置了登录信息，客户端会自动重试登录"
    elif status == 404:
        summary = "请求失败：接口或资源不存在"
        hint = "请检查资源 ID 或请求路径是否正确"
    elif status in (400, 422):
        summary = "请求失败：参数或请求体不符合接口要求"
        hint = "请重新检查 --query 或 --body 的 JSON 结构"
    else:
        summary = f"请求失败：{error}"
        hint = None

    display = {
        "type": "error",
        "status": status,
        "path": path,
        "message": detail_message or str(error),
    }
    if hint:
        display["hint"] = hint
    return {"summary": summary, "display": display}


def emit(payload, exit_code=0):
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def build_parser():
    parser = argparse.ArgumentParser(description="Order Demo Workspace API client")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list-actions", help="List available named actions")
    subparsers.add_parser("login", help="Obtain a token using configured credentials")
    subparsers.add_parser("me", help="Fetch the current authenticated user")
    subparsers.add_parser("overview", help="Fetch dashboard overview")

    request_parser = subparsers.add_parser("request", help="Send an arbitrary API request")
    request_parser.add_argument("method")
    request_parser.add_argument("path")
    request_parser.add_argument("--query", default=None, help="JSON object with query parameters")
    request_parser.add_argument("--body", default=None, help="JSON object with request body")
    request_parser.add_argument("--no-auth", action="store_true", help="Send request without Authorization header")

    action_parser = subparsers.add_parser("action", help="Execute a named action from api_map.json")
    action_parser.add_argument("name")
    action_parser.add_argument("--query", default=None, help="JSON object with query parameters")
    action_parser.add_argument("--body", default=None, help="JSON object with request body")
    action_parser.add_argument("--path-param", action="append", default=[], help="Path parameter in key=value form")

    chinese_parser = subparsers.add_parser("中文", help="Use Chinese resource and operation names")
    chinese_parser.add_argument("resource", help="概览、客户、订单、产品、知识库、文章")
    chinese_parser.add_argument("operation", nargs="?", default="查看", help="查看、列表、新增、更新、删除、搜索")
    chinese_parser.add_argument("--id", dest="entity_id", default=None, help="Resource ID for detail/update/delete")
    chinese_parser.add_argument("--query", default=None, help="JSON object with query parameters")
    chinese_parser.add_argument("--body", default=None, help="JSON object with request body")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    client = CRMClient()
    api_map = load_api_map()

    try:
        if args.command == "list-actions":
            emit({"actions": api_map})

        if args.command == "login":
            result = client.login(force=not bool(os.environ.get("CRM_API_TOKEN")))
            emit({"ok": True, **result})

        if args.command == "me":
            data = client.request("GET", "/auth/me")
            summary_payload = summarize_success(data, action_name="auth.me", mode="read")
            emit({"ok": True, **summary_payload, "data": data})

        if args.command == "overview":
            data = client.request("GET", "/dashboard/overview")
            summary_payload = summarize_success(data, action_name="dashboard.overview", mode="read")
            emit({"ok": True, **summary_payload, "data": data})

        if args.command == "request":
            query = parse_json_input(args.query, "--query")
            body = parse_json_input(args.body, "--body")
            data = client.request(
                args.method,
                args.path,
                params=query,
                body=body,
                include_auth=not args.no_auth,
            )
            emit(
                {
                    "ok": True,
                    "method": args.method.upper(),
                    "path": args.path,
                    "data": data,
                }
            )

        if args.command == "action":
            query = parse_json_input(args.query, "--query")
            body = parse_json_input(args.body, "--body")
            path_params = parse_path_params(args.path_param)
            action, path = resolve_action(api_map, args.name, path_params)
            data = client.request(action["method"], path, params=query, body=body)
            summary_payload = summarize_success(data, action_name=args.name, mode=action["mode"])
            emit(
                {
                    "ok": True,
                    "action": args.name,
                    "mode": action["mode"],
                    "method": action["method"],
                    "path": path,
                    **summary_payload,
                    "data": data,
                }
            )

        if args.command == "中文":
            query = parse_json_input(args.query, "--query")
            body = parse_json_input(args.body, "--body")
            action_name, path_params = resolve_chinese_action(args.resource, args.operation, args.entity_id)
            action, path = resolve_action(api_map, action_name, path_params)
            data = client.request(action["method"], path, params=query, body=body)
            command_info = {
                "resource": args.resource,
                "operation": args.operation,
                "id": args.entity_id,
            }
            summary_payload = summarize_success(
                data,
                action_name=action_name,
                mode=action["mode"],
                command_info=command_info,
            )
            emit(
                {
                    "ok": True,
                    "command": command_info,
                    "action": action_name,
                    "mode": action["mode"],
                    "method": action["method"],
                    "path": path,
                    **summary_payload,
                    "data": data,
                }
            )

        parser.print_help()
        return 1
    except ApiError as exc:
        error_payload = summarize_error(
            error=str(exc),
            status=exc.status,
            details=exc.payload,
        )
        emit(
            {
                "ok": False,
                "error": str(exc),
                "status": exc.status,
                "details": exc.payload,
                **error_payload,
            },
            exit_code=1,
        )


if __name__ == "__main__":
    main()
