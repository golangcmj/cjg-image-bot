from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.prompt_media import (  # type: ignore
    normalize_edit_prompt_controls,
    sanitize_generate_prompt,
)


def test_sanitize_generate_prompt_only_removes_control_fragments_without_global_whitespace_cleanup():
    raw = (
        "A\tdata:image/png;base64,QUJD\tB\n"
        "[[强度=0.3]]  C  [[strength=0.9]]\n"
        "data:image/jpeg;base64,REVG\tD"
    )

    cleaned = sanitize_generate_prompt(raw)

    assert "data:image/" not in cleaned
    assert "[[寮哄害=" not in cleaned
    assert "[[strength=" not in cleaned
    assert "A" in cleaned
    assert "B" in cleaned
    assert "C" in cleaned
    assert "D" in cleaned


def test_sanitize_generate_prompt_supports_configured_strength_keyword_with_backward_compatibility():
    raw = (
        "x [[力度=0.2]] y [[strength=0.7]] z [[强度=0.3]] "
        "data:image/png;base64,QUJD end"
    )

    cleaned = sanitize_generate_prompt(raw, strength_keyword="力度")

    assert "data:image/" not in cleaned
    assert "[[鍔涘害=" not in cleaned
    assert "[[寮哄害=" not in cleaned
    assert "[[strength=" not in cleaned
    assert "x" in cleaned
    assert "y" in cleaned
    assert "z" in cleaned
    assert "end" in cleaned


def test_normalize_edit_prompt_controls_keeps_text_when_data_uri_in_middle_without_collapsing_whitespace():
    raw = "prefix\tdata:image/png;base64,QUJD\t suffix\n[[强度=0.3]]\n"

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert "data:image/" not in normalized.text
    assert "[[寮哄害=" not in normalized.text
    assert normalized.image_data_uri == "data:image/png;base64,QUJD"
    assert normalized.strength == 0.3
    assert normalized.normalized_prompt.count("data:image/png;base64,QUJD") == 1
    assert normalized.normalized_prompt.count("[[strength=0.3]]") == 1


def test_normalize_edit_prompt_controls_preserves_text_with_uri_at_beginning_middle_end():
    begin_raw = "data:image/png;base64,QUJD begin\ttext"
    middle_raw = "begin  data:image/png;base64,QUJD\tmiddle\ntext"
    end_raw = "end\ttext data:image/png;base64,QUJD"

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

    assert "begin" in begin.text
    assert "text" in begin.text
    assert "begin" in middle.text
    assert "middle" in middle.text
    assert "text" in middle.text
    assert "end" in end.text
    assert "text" in end.text
    assert "data:image/" not in begin.text
    assert "data:image/" not in middle.text
    assert "data:image/" not in end.text


def test_normalize_edit_prompt_controls_normalizes_chinese_strength_keyword():
    raw = "subject [[强度=0.3]] data:image/png;base64,QUJD"

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
        "subject [[强度=2]] [[强度=0.4]] [[strength=0.7]] "
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
    raw = "subject data:image/png;base64,QUJD"

    normalized = normalize_edit_prompt_controls(
        raw_text=raw,
        strength_keyword="强度",
        default_strength=0.35,
    )

    assert normalized.strength == 0.35
    assert "[[strength=0.35]]" in normalized.normalized_prompt
