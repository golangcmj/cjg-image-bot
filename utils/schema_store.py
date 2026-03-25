from __future__ import annotations

import json
from pathlib import Path

from .image_core import update_selected_model_schema


def persist_selected_model_options(schema_path: str | Path, models: list[dict[str, str]]) -> dict:
    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding="utf-8"))
    updated = update_selected_model_schema(schema, models)
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=4), encoding="utf-8")
    return updated


def clear_selected_model_options(schema_path: str | Path, hint: str) -> dict:
    path = Path(schema_path)
    schema = json.loads(path.read_text(encoding="utf-8"))
    updated = dict(schema)
    field = dict(updated.get("selected_model_id") or {})
    field["type"] = "string"
    field["options"] = []
    field["hint"] = hint
    updated["selected_model_id"] = field
    path.write_text(json.dumps(updated, ensure_ascii=False, indent=4), encoding="utf-8")
    return updated
