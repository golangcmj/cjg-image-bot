from __future__ import annotations

from dataclasses import dataclass
import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen


@dataclass
class ResolvedMessageImage:
    source: str
    image_data_uri: str

    @property
    def image_uri(self) -> str:
        return self.image_data_uri


def _normalize_image_candidate(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    return candidate


def _iter_component_candidates(component: Any):
    if isinstance(component, str):
        yield component
        return

    if isinstance(component, dict):
        for key in (
            "data_uri",
            "image_data_uri",
            "image",
            "url",
            "src",
            "file",
            "path",
        ):
            if key in component:
                yield component.get(key)
        return

    for attr in (
        "data_uri",
        "image_data_uri",
        "image",
        "url",
        "src",
        "file",
        "path",
    ):
        yield getattr(component, attr, None)


def _extract_image_strings_from_components(components: Any) -> list[str]:
    if not components:
        return []

    results: list[str] = []
    for component in components:
        for candidate in _iter_component_candidates(component):
            normalized = _normalize_image_candidate(candidate)
            if normalized:
                results.append(normalized)
    return results


def _extract_current_images(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(getattr(event, "current_images", None))
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    message_components = getattr(message_obj, "message", None)
    return _extract_image_strings_from_components(message_components)


def _extract_reply_images(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(getattr(event, "reply_images", None))
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    for reply_attr in ("reply", "quote", "referenced_message", "reply_message"):
        reply_obj = getattr(message_obj, reply_attr, None)
        reply_components = getattr(reply_obj, "message", None)
        extracted = _extract_image_strings_from_components(reply_components)
        if extracted:
            return extracted
    return []


def _extract_mention_avatars(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(getattr(event, "mention_avatars", None))
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    mentions = getattr(message_obj, "mentions", None)
    if not mentions:
        return []

    avatars: list[str] = []
    for mention in mentions:
        if isinstance(mention, dict):
            for key in ("avatar", "avatar_url", "user_avatar", "face"):
                normalized = _normalize_image_candidate(mention.get(key))
                if normalized:
                    avatars.append(normalized)
                    break
            continue

        for attr in ("avatar", "avatar_url", "user_avatar", "face"):
            normalized = _normalize_image_candidate(getattr(mention, attr, None))
            if normalized:
                avatars.append(normalized)
                break
    return avatars


def _is_data_image_uri(candidate: str) -> bool:
    return candidate.lower().startswith("data:image/")


def _guess_mime_type(source: str, *, header_content_type: str = "") -> str:
    content_type = (header_content_type or "").split(";", 1)[0].strip().lower()
    if content_type.startswith("image/"):
        return content_type

    guessed, _ = mimetypes.guess_type(source)
    if guessed and guessed.lower().startswith("image/"):
        return guessed.lower()

    return "image/png"


def _to_data_uri(image_bytes: bytes, mime_type: str) -> str:
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _read_bytes_from_url(candidate: str) -> tuple[bytes, str]:
    with urlopen(candidate, timeout=30) as response:  # nosec B310
        image_bytes = response.read()
        info = getattr(response, "info", None)
        header_content_type = ""
        if callable(info):
            headers = info()
            header_content_type = str(getattr(headers, "get_content_type", lambda: "")())
        mime_type = _guess_mime_type(candidate, header_content_type=header_content_type)
        return image_bytes, mime_type


def _read_bytes_from_path(candidate: str) -> tuple[bytes, str] | None:
    path = Path(candidate)
    if not path.is_file():
        return None
    image_bytes = path.read_bytes()
    mime_type = _guess_mime_type(str(path))
    return image_bytes, mime_type


def _as_standard_data_uri(candidate: str) -> str:
    if _is_data_image_uri(candidate):
        return candidate

    parsed = urlparse(candidate)
    if parsed.scheme in ("http", "https", "file"):
        try:
            image_bytes, mime_type = _read_bytes_from_url(candidate)
        except Exception:
            return ""
        if not image_bytes:
            return ""
        return _to_data_uri(image_bytes, mime_type)

    path_result = _read_bytes_from_path(candidate)
    if path_result is None:
        return ""
    image_bytes, mime_type = path_result
    if not image_bytes:
        return ""
    return _to_data_uri(image_bytes, mime_type)


def choose_first_image_source(
    *,
    current_images: list[str] | None,
    reply_images: list[str] | None,
    mention_avatars: list[str] | None,
) -> ResolvedMessageImage | None:
    for source_name, candidates in (
        ("current", current_images or []),
        ("reply", reply_images or []),
        ("avatar", mention_avatars or []),
    ):
        for candidate in candidates:
            normalized = _normalize_image_candidate(candidate)
            if normalized:
                return ResolvedMessageImage(source=source_name, image_data_uri=normalized)
    return None


def resolve_edit_image(event: Any, *, strength_keyword: str) -> ResolvedMessageImage | None:
    _ = strength_keyword
    source = choose_first_image_source(
        current_images=_extract_current_images(event),
        reply_images=_extract_reply_images(event),
        mention_avatars=_extract_mention_avatars(event),
    )
    if source is None:
        return None

    data_uri = _as_standard_data_uri(source.image_data_uri)
    if not data_uri:
        return None

    return ResolvedMessageImage(source=source.source, image_data_uri=data_uri)
