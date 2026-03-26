from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.model_registry import (  # type: ignore
    format_model_brief,
    parse_model_directory_text,
    resolve_default_model,
    resolve_model_by_name_or_id,
)


def test_parse_model_directory_text_supports_single_or_multiline():
    single = parse_model_directory_text("动漫模型|preset-314")
    assert single == [{"name": "动漫模型", "id": "preset-314"}]

    multiple = parse_model_directory_text("动漫模型|preset-314\n写实模型|preset-128")
    assert multiple == [
        {"name": "动漫模型", "id": "preset-314"},
        {"name": "写实模型", "id": "preset-128"},
    ]


def test_parse_model_directory_text_ignores_invalid_lines_and_keeps_valid_entries():
    raw = "\n".join(
        [
            "动漫模型|preset-314",
            "invalid",
            " | preset-x",
            "模型A|",
            "too|many|parts",
            "写实模型|preset-128",
        ]
    )

    assert parse_model_directory_text(raw) == [
        {"name": "动漫模型", "id": "preset-314"},
        {"name": "写实模型", "id": "preset-128"},
    ]


def test_resolve_default_model_accepts_id_or_name_and_falls_back_to_legacy_id():
    models = parse_model_directory_text("动漫模型|preset-314\n写实模型|preset-128")

    assert resolve_default_model(models, "preset-128", legacy_selected_model_id="legacy-001") == {
        "name": "写实模型",
        "id": "preset-128",
    }
    assert resolve_default_model(models, "动漫模型", legacy_selected_model_id="legacy-001") == {
        "name": "动漫模型",
        "id": "preset-314",
    }
    assert resolve_default_model(models, "不存在", legacy_selected_model_id="legacy-001") == {
        "name": "legacy-001",
        "id": "legacy-001",
    }


    assert resolve_default_model([], "preset-314", legacy_selected_model_id="") == {
        "name": "preset-314",
        "id": "preset-314",
    }


def test_resolve_model_by_name_or_id_and_format_model_brief():
    models = parse_model_directory_text("动漫模型|preset-314\n写实模型|preset-128")
    assert resolve_model_by_name_or_id(models, "写实模型") == {"name": "写实模型", "id": "preset-128"}
    assert resolve_model_by_name_or_id(models, "preset-314") == {"name": "动漫模型", "id": "preset-314"}
    assert resolve_model_by_name_or_id(models, "unknown") is None
    assert format_model_brief({"name": "动漫模型", "id": "preset-314"}) == "动漫模型 | preset-314"
