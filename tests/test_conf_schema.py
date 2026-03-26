from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_conf_schema_uses_astrbot_supported_float_type_for_default_i2i_strength():
    schema = (ROOT / "_conf_schema.json").read_text(encoding="utf-8")

    assert '"default_i2i_strength"' in schema
    assert '"type": "float"' in schema
    assert '"type": "number"' not in schema
