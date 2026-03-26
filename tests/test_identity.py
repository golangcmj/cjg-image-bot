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


def test_main_register_name_and_desc_are_readable():
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")

    assert '"蠢酒馆生图",' in main_py


def test_main_has_no_broad_importerror_fallback():
    main_py = (ROOT / "main.py").read_text(encoding="utf-8")

    assert "except ImportError" not in main_py
