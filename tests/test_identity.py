from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_metadata_author_is_golangcmj():
    metadata = (ROOT / "metadata.yaml").read_text(encoding="utf-8")

    assert "author: golangcmj" in metadata
    assert "cmjlevi" not in metadata


def test_main_register_author_is_golangcmj():
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")

    assert '"golangcmj",' in main_py
    assert '"cmjlevi",' not in main_py
