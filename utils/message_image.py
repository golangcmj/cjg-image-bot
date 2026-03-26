from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    return choose_first_image_source(
        current_images=_extract_current_images(event),
        reply_images=_extract_reply_images(event),
        mention_avatars=_extract_mention_avatars(event),
    )
