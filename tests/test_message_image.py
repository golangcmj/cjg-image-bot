from pathlib import Path
import base64
import sys
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.message_image import (  # type: ignore
    choose_first_image_source,
    resolve_edit_image,
)


def _event_with_sources(*, current_images=None, reply_images=None, mention_avatars=None):
    return SimpleNamespace(
        current_images=current_images or [],
        reply_images=reply_images or [],
        mention_avatars=mention_avatars or [],
    )


def test_choose_first_image_source_priority_current_reply_avatar():
    source = choose_first_image_source(
        current_images=["data:image/png;base64,CURRENT", "data:image/png;base64,CURRENT2"],
        reply_images=["data:image/png;base64,REPLY"],
        mention_avatars=["https://avatar.example/a.png"],
    )

    assert source is not None
    assert source.source == "current"
    assert source.image_uri == "data:image/png;base64,CURRENT"


def test_choose_first_image_source_falls_back_to_reply_then_avatar():
    reply_source = choose_first_image_source(
        current_images=[],
        reply_images=["data:image/png;base64,REPLY1", "data:image/png;base64,REPLY2"],
        mention_avatars=["https://avatar.example/a.png"],
    )
    avatar_source = choose_first_image_source(
        current_images=[],
        reply_images=[],
        mention_avatars=["https://avatar.example/a.png", "https://avatar.example/b.png"],
    )

    assert reply_source is not None
    assert reply_source.source == "reply"
    assert reply_source.image_uri == "data:image/png;base64,REPLY1"
    assert avatar_source is not None
    assert avatar_source.source == "avatar"
    assert avatar_source.image_uri == "https://avatar.example/a.png"


def test_resolve_edit_image_returns_first_available_image():
    event = _event_with_sources(
        current_images=["data:image/png;base64,CURRENT"],
        reply_images=["data:image/png;base64,REPLY"],
        mention_avatars=["https://avatar.example/a.png"],
    )

    resolved = resolve_edit_image(event, strength_keyword="强度")

    assert resolved is not None
    assert resolved.source == "current"
    assert resolved.image_data_uri == "data:image/png;base64,CURRENT"


def test_resolve_edit_image_returns_none_when_no_usable_images():
    event = _event_with_sources()

    resolved = resolve_edit_image(event, strength_keyword="强度")

    assert resolved is None


def test_resolve_edit_image_converts_local_path_to_data_uri(tmp_path):
    image_path = tmp_path / "sample.png"
    image_bytes = b"\x89PNG\r\n\x1a\nfake-png-bytes"
    image_path.write_bytes(image_bytes)

    event = _event_with_sources(current_images=[str(image_path)])

    resolved = resolve_edit_image(event, strength_keyword="强度")

    assert resolved is not None
    assert resolved.source == "current"
    assert resolved.image_data_uri.startswith("data:image/png;base64,")
    encoded = resolved.image_data_uri.split(",", 1)[1]
    assert base64.b64decode(encoded) == image_bytes


def test_resolve_edit_image_converts_file_url_to_data_uri(tmp_path):
    image_path = tmp_path / "avatar.jpg"
    image_bytes = b"\xff\xd8\xfffake-jpeg-bytes"
    image_path.write_bytes(image_bytes)

    event = _event_with_sources(mention_avatars=[image_path.as_uri()])

    resolved = resolve_edit_image(event, strength_keyword="强度")

    assert resolved is not None
    assert resolved.source == "avatar"
    assert resolved.image_data_uri.startswith("data:image/jpeg;base64,")
    encoded = resolved.image_data_uri.split(",", 1)[1]
    assert base64.b64decode(encoded) == image_bytes
