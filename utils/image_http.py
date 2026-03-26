from __future__ import annotations

import asyncio
import base64
import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .image_core import (
    build_generation_endpoint,
    build_generation_payload,
    build_models_endpoint,
    extract_image_result,
    parse_model_choices,
)


class UpstreamRequestError(Exception):
    pass


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _decode_response_text(raw: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_payload_error_message(payload: object) -> str | None:
    if not isinstance(payload, dict):
        return None

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
        text = error.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()

    for key in ("detail", "message"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def _read_json_response(response) -> dict:
    raw = response.read()
    if not raw:
        return {}
    try:
        return json.loads(_decode_response_text(raw))
    except json.JSONDecodeError as exc:
        content_type = ""
        headers = getattr(response, "headers", None)
        if headers is not None:
            content_type = headers.get("Content-Type", "")
        body = _decode_response_text(raw)
        raise UpstreamRequestError(
            "上游返回的不是 JSON 响应\n"
            f"Content-Type: {content_type or 'unknown'}\n"
            f"响应内容:\n{body}"
        ) from exc


def _open_request(request, urlopen_func=urlopen):
    try:
        return urlopen_func(request)
    except HTTPError as exc:
        raw = exc.read()
        body = _decode_response_text(raw) if raw else ""
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        detail = (
            "上游请求失败\n"
            f"状态码: {exc.code}\n"
            f"Content-Type: {content_type or 'unknown'}"
        )
        if body:
            detail += f"\n响应内容:\n{body}"
        raise UpstreamRequestError(detail) from exc
    except URLError as exc:
        raise UpstreamRequestError(f"上游连接失败\n原因: {exc.reason}") from exc


def _raise_if_payload_contains_error(payload: dict) -> None:
    message = _extract_payload_error_message(payload)
    if message:
        raise UpstreamRequestError(f"上游返回错误:\n{message}")


def fetch_models_sync(base_url: str, api_key: str, urlopen_func=urlopen) -> list[dict[str, str]]:
    request = Request(
        build_models_endpoint(base_url),
        headers=_build_headers(api_key),
        method="GET",
    )
    with _open_request(request, urlopen_func=urlopen_func) as response:
        payload = _read_json_response(response)
    _raise_if_payload_contains_error(payload)
    return parse_model_choices(payload)


def request_generation_sync(
    base_url: str,
    api_key: str,
    model_id: str,
    prompt: str,
    urlopen_func=urlopen,
) -> tuple[str | None, str | None]:
    request = Request(
        build_generation_endpoint(base_url),
        data=json.dumps(build_generation_payload(model_id, prompt)).encode("utf-8"),
        headers=_build_headers(api_key),
        method="POST",
    )
    with _open_request(request, urlopen_func=urlopen_func) as response:
        payload = _read_json_response(response)
    _raise_if_payload_contains_error(payload)
    result = extract_image_result(payload)
    if result == (None, None):
        raise UpstreamRequestError(
            "上游返回成功但没有图片结果\n"
            f"响应内容:\n{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
    return result


def fetch_image_bytes_from_result_sync(
    result_kind: str | None,
    result_value: str | None,
    urlopen_func=urlopen,
) -> bytes:
    if result_kind == "b64_json" and result_value:
        return base64.b64decode(result_value)

    if result_kind == "url" and result_value:
        request = Request(result_value, method="GET")
        with _open_request(request, urlopen_func=urlopen_func) as response:
            return response.read()

    raise UpstreamRequestError("未找到可用的图片结果")


async def fetch_models(base_url: str, api_key: str) -> list[dict[str, str]]:
    return await asyncio.to_thread(fetch_models_sync, base_url, api_key)


async def request_generation(
    base_url: str,
    api_key: str,
    model_id: str,
    prompt: str,
) -> tuple[str | None, str | None]:
    return await asyncio.to_thread(request_generation_sync, base_url, api_key, model_id, prompt)


async def fetch_image_bytes_from_result(result_kind: str | None, result_value: str | None) -> bytes:
    return await asyncio.to_thread(fetch_image_bytes_from_result_sync, result_kind, result_value)
