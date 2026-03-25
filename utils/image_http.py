from __future__ import annotations

import asyncio
import base64
import json
from urllib.request import Request, urlopen

from .image_core import (
    build_generation_endpoint,
    build_generation_payload,
    build_models_endpoint,
    extract_image_result,
    parse_model_choices,
)


def _build_headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _read_json_response(response) -> dict:
    raw = response.read()
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def _open_request(request, urlopen_func=urlopen):
    return urlopen_func(request)


def fetch_models_sync(base_url: str, api_key: str, urlopen_func=urlopen) -> list[dict[str, str]]:
    request = Request(
        build_models_endpoint(base_url),
        headers=_build_headers(api_key),
        method="GET",
    )
    with _open_request(request, urlopen_func=urlopen_func) as response:
        payload = _read_json_response(response)
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
    return extract_image_result(payload)


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

    raise ValueError("未找到可用的图片结果")


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
