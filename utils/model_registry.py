from __future__ import annotations

import re

from .image_core import normalize_selected_model_value


MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")


def _clean_text(value: str | None) -> str:
    return str(value or "").strip()


def _build_model_entry(name: str, model_id: str) -> dict[str, str]:
    clean_name = _clean_text(name)
    clean_id = _clean_text(model_id)
    if not clean_name or not clean_id:
        return {}
    return {"name": clean_name, "id": clean_id}


def _looks_like_model_id(value: str | None) -> bool:
    return bool(MODEL_ID_PATTERN.fullmatch(_clean_text(value)))


def parse_model_directory_text(raw_text: str | None) -> list[dict[str, str]]:
    models: list[dict[str, str]] = []
    seen_ids: set[str] = set()

    for line in str(raw_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split("|")
        if len(parts) != 2:
            continue
        entry = _build_model_entry(parts[0], parts[1])
        if not entry:
            continue
        model_id = entry["id"]
        if model_id in seen_ids:
            continue
        seen_ids.add(model_id)
        models.append(entry)

    return models


def _extract_candidate_tokens(value: str | None) -> list[str]:
    raw = _clean_text(value)
    if not raw:
        return []

    tokens: list[str] = [raw]
    if "|" in raw:
        parts = [segment.strip() for segment in raw.split("|") if segment.strip()]
        tokens.extend(parts)
        if len(parts) >= 2:
            # 支持“模型名称|模型ID”的目录写法。
            tokens.append(parts[0])
            tokens.append(parts[1])
    normalized = normalize_selected_model_value(raw)
    if normalized:
        tokens.append(normalized)

    deduped: list[str] = []
    seen: set[str] = set()
    for item in tokens:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def resolve_model_by_name_or_id(models: list[dict[str, str]], selection: str | None) -> dict[str, str] | None:
    if not models:
        return None

    candidates = _extract_candidate_tokens(selection)
    if not candidates:
        return None

    for token in candidates:
        for item in models:
            if item.get("id") == token:
                return {"name": item.get("name") or token, "id": token}

    for token in candidates:
        for item in models:
            if item.get("name") == token:
                model_id = item.get("id") or ""
                if model_id:
                    return {"name": item.get("name") or model_id, "id": model_id}

    return None


def resolve_default_model(
    models: list[dict[str, str]],
    default_model: str | None,
    *,
    legacy_selected_model_id: str | None = "",
) -> dict[str, str] | None:
    selected = resolve_model_by_name_or_id(models, default_model)
    if selected is not None:
        return selected

    normalized_default = normalize_selected_model_value(_clean_text(default_model))
    if normalized_default and _looks_like_model_id(normalized_default):
        return {"name": normalized_default, "id": normalized_default}

    legacy_id = normalize_selected_model_value(_clean_text(legacy_selected_model_id))
    if not legacy_id:
        return None

    legacy_resolved = resolve_model_by_name_or_id(models, legacy_id)
    if legacy_resolved is not None:
        return legacy_resolved
    return {"name": legacy_id, "id": legacy_id}


def format_model_brief(model: dict[str, str] | None) -> str:
    if not model:
        return ""
    model_id = _clean_text(model.get("id"))
    model_name = _clean_text(model.get("name")) or model_id
    if not model_id:
        return ""
    return f"{model_name} | {model_id}"


def format_model_listing(models: list[dict[str, str]]) -> str:
    if not models:
        return "当前没有可用模型"

    lines = ["可用模型列表："]
    for item in models:
        brief = format_model_brief(item)
        if brief:
            lines.append(brief)
    return "\n".join(lines) if len(lines) > 1 else "当前没有可用模型"
