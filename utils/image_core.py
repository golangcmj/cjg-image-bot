from __future__ import annotations


def _normalize_v1_base_url(base_url: str) -> str:
    value = (base_url or "").strip().rstrip("/")
    if not value:
        raise ValueError("base_url 不能为空")
    if value.endswith("/v1"):
        return value
    return f"{value}/v1"


def build_models_endpoint(base_url: str) -> str:
    return f"{_normalize_v1_base_url(base_url)}/models"


def build_generation_endpoint(base_url: str) -> str:
    return f"{_normalize_v1_base_url(base_url)}/images/generations"


def build_generation_payload(model_id: str, prompt: str) -> dict:
    return {
        "model": model_id,
        "prompt": prompt,
    }


def build_timeout_kwargs() -> dict:
    return {
        "total": None,
        "sock_read": None,
        "connect": 30,
    }


def extract_command_prompt(raw_text: str, command_name: str) -> str:
    text = raw_text or ""
    prefix_options = (f"/{command_name}", command_name)
    matched_prefix = None

    for prefix in prefix_options:
        if text.startswith(prefix):
            matched_prefix = prefix
            break

    if matched_prefix is None:
        return text

    remainder = text[len(matched_prefix) :]
    if remainder.startswith("\r\n"):
        remainder = remainder[2:]
    elif remainder.startswith("\n") or remainder.startswith("\r") or remainder.startswith(" "):
        remainder = remainder[1:]
    return remainder


def parse_model_choices(payload: dict | None) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    for item in (payload or {}).get("data", []):
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("id") or "").strip()
        model_name = str(item.get("name") or model_id).strip()
        if not model_id:
            continue
        models.append({"id": model_id, "name": model_name})
    return models


def build_model_option_strings(models: list[dict[str, str]]) -> list[str]:
    options: list[str] = []
    for item in models:
        model_id = item.get("id") or ""
        if not model_id:
            continue
        options.append(model_id)
    return options


def normalize_selected_model_value(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    if " | " in raw:
        return raw.split(" | ", 1)[0].strip()
    return raw


def build_model_hint(models: list[dict[str, str]]) -> str:
    if not models:
        return "当前没有可用模型"

    lines = ["可选模型："]
    for item in models:
        model_id = item.get("id") or ""
        model_name = item.get("name") or model_id
        if not model_id:
            continue
        lines.append(f"{model_id} | {model_name}")
    return "\n".join(lines)


def update_selected_model_schema(schema: dict, models: list[dict[str, str]]) -> dict:
    updated = dict(schema)
    field = dict(updated.get("selected_model_id") or {})
    field["type"] = "string"
    field["options"] = build_model_option_strings(models)
    field["hint"] = build_model_hint(models)
    updated["selected_model_id"] = field
    return updated


def format_model_listing(models: list[dict[str, str]]) -> str:
    if not models:
        return "当前没有可用模型"

    lines = ["可用模型列表："]
    for item in models:
        model_id = item.get("id") or ""
        model_name = item.get("name") or model_id
        lines.append(f"{model_id} | {model_name}")
    return "\n".join(lines)


def resolve_selected_model_id(selection: str, models: list[dict[str, str]]) -> str | None:
    value = normalize_selected_model_value(selection)
    if not value:
        return None

    for item in models:
        if item.get("id") == value:
            return item["id"]

    for item in models:
        if item.get("name") == value:
            return item["id"]

    return None


def extract_image_result(payload: dict | None) -> tuple[str | None, str | None]:
    for item in (payload or {}).get("data", []):
        if not isinstance(item, dict):
            continue
        b64_json = item.get("b64_json")
        if isinstance(b64_json, str) and b64_json:
            return "b64_json", b64_json
        image_url = item.get("url")
        if isinstance(image_url, str) and image_url:
            return "url", image_url
    return None, None
