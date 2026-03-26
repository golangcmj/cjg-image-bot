from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.prompt_media import (  # type: ignore
    normalize_edit_prompt_controls,
    sanitize_generate_prompt,
)


def test_sanitize_generate_prompt_strips_data_uri_and_strength_tags():
    raw = (
        "开头 data:image/png;base64,QUJD [[强度=0.3]] 中间 "
        "[[strength=0.9]] data:image/jpeg;base64,REVG 结尾"
    )

    cleaned = sanitize_generate_prompt(raw)

    assert cleaned == "开头 中间 结尾"


def test_normalize_edit_prompt_controls_keeps_text_when_data_uri_in_middle():
    raw = "前缀 data:image/png;base64,QUJD 后缀 [[强度=0.3]]"

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert normalized.text == "前缀 后缀"
    assert normalized.image_data_uri == "data:image/png;base64,QUJD"
    assert normalized.strength == 0.3
    assert normalized.normalized_prompt.count("data:image/png;base64,QUJD") == 1
    assert normalized.normalized_prompt.count("[[strength=0.3]]") == 1


def test_normalize_edit_prompt_controls_preserves_text_with_uri_at_beginning_middle_end():
    begin_raw = "data:image/png;base64,QUJD 开头文本"
    middle_raw = "开头文本 data:image/png;base64,QUJD 中间文本"
    end_raw = "结尾文本 data:image/png;base64,QUJD"

    begin = normalize_edit_prompt_controls(
        raw_text=begin_raw,
        strength_keyword="强度",
        default_strength=0.35,
    )
    middle = normalize_edit_prompt_controls(
        raw_text=middle_raw,
        strength_keyword="强度",
        default_strength=0.35,
    )
    end = normalize_edit_prompt_controls(
        raw_text=end_raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert begin.text == "开头文本"
    assert middle.text == "开头文本 中间文本"
    assert end.text == "结尾文本"


def test_normalize_edit_prompt_controls_normalizes_chinese_strength_keyword():
    raw = "主体内容 [[强度=0.3]] data:image/png;base64,QUJD"

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert normalized.strength == 0.3
    assert "[[strength=0.3]]" in normalized.normalized_prompt
    assert "[[强度=0.3]]" not in normalized.normalized_prompt


def test_normalize_edit_prompt_controls_keeps_first_valid_strength_and_discards_rest():
    raw = (
        "主体 [[强度=2]] [[强度=0.4]] [[strength=0.7]] "
        "data:image/png;base64,QUJD"
    )

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert normalized.strength == 0.4
    assert normalized.normalized_prompt.count("[[strength=0.4]]") == 1
    assert "[[strength=0.7]]" not in normalized.normalized_prompt
    assert "[[强度=2]]" not in normalized.normalized_prompt


def test_normalize_edit_prompt_controls_injects_default_strength_when_missing():
    raw = "主体内容 data:image/png;base64,QUJD"

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert normalized.strength == 0.35
    assert "[[strength=0.35]]" in normalized.normalized_prompt
