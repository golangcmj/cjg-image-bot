from __future__ import annotations

from dataclasses import dataclass
import asyncio
import base64
import ipaddress
import logging
import mimetypes
from pathlib import Path
import socket
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


MAX_IMAGE_BYTES = 10 * 1024 * 1024
_REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
_MAX_REDIRECTS = 3
_LOGGER = logging.getLogger(__name__)


@dataclass
class ResolvedMessageImage:
    source: str
    image_data_uri: str

    @property
    def image_uri(self) -> str:
        return self.image_data_uri


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _normalize_image_candidate(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    candidate = value.strip()
    if not candidate:
        return ""
    return candidate


def _normalize_component_type(value: Any) -> str:
    if value is None:
        return ""
    for attr in ("value", "name"):
        attr_value = getattr(value, attr, None)
        if isinstance(attr_value, str) and attr_value.strip():
            return attr_value.strip().split(".")[-1].lower()
    return str(value).strip().split(".")[-1].lower()


def _component_type_name(component: Any) -> str:
    if isinstance(component, dict):
        return _normalize_component_type(component.get("type"))
    return _normalize_component_type(getattr(component, "type", None))


def _iter_component_candidates(component: Any, *, allow_plain_string: bool):
    if isinstance(component, str):
        if not allow_plain_string:
            return
        yield component
        return

    if isinstance(component, dict):
        for key in ("data_uri", "image_data_uri", "image", "url", "src", "file", "path"):
            if key in component:
                yield component.get(key)
        payload = component.get("data")
        if isinstance(payload, dict):
            for key in ("data_uri", "image_data_uri", "image", "url", "src", "file", "path"):
                if key in payload:
                    yield payload.get(key)
        return

    for attr in ("data_uri", "image_data_uri", "image", "url", "src", "file", "path"):
        yield getattr(component, attr, None)
    payload = getattr(component, "data", None)
    if isinstance(payload, dict):
        for key in ("data_uri", "image_data_uri", "image", "url", "src", "file", "path"):
            yield payload.get(key)


def _extract_image_strings_from_components(components: Any, *, allow_plain_strings: bool) -> list[str]:
    if not components:
        return []

    results: list[str] = []
    for component in components:
        for candidate in _iter_component_candidates(component, allow_plain_string=allow_plain_strings):
            normalized = _normalize_image_candidate(candidate)
            if normalized:
                results.append(normalized)
    return results


def _extract_current_images(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(
        getattr(event, "current_images", None),
        allow_plain_strings=True,
    )
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    message_components = getattr(message_obj, "message", None)
    return _extract_image_strings_from_components(message_components, allow_plain_strings=False)


def _extract_reply_images(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(
        getattr(event, "reply_images", None),
        allow_plain_strings=True,
    )
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    for reply_attr in ("reply", "quote", "referenced_message", "reply_message"):
        reply_obj = getattr(message_obj, reply_attr, None)
        reply_components = getattr(reply_obj, "message", None) or getattr(reply_obj, "chain", None)
        extracted = _extract_image_strings_from_components(reply_components, allow_plain_strings=False)
        if extracted:
            return extracted

    message_components = getattr(message_obj, "message", None) or []
    for component in message_components:
        component_type = _component_type_name(component)
        if component_type != "reply":
            if not isinstance(component, dict) or _normalize_component_type(component.get("type")) != "reply":
                continue
        reply_components = getattr(component, "chain", None)
        if reply_components is None and isinstance(component, dict):
            reply_components = component.get("chain")
            if reply_components is None:
                payload = component.get("data")
                if isinstance(payload, dict):
                    reply_components = payload.get("chain")
        extracted = _extract_image_strings_from_components(reply_components, allow_plain_strings=False)
        if extracted:
            return extracted
    return []


def _extract_at_targets_from_message(message_obj: Any) -> list[str]:
    message_components = getattr(message_obj, "message", None) or []
    targets: list[str] = []
    for component in message_components:
        component_type = _component_type_name(component)
        if isinstance(component, dict):
            component_type = _normalize_component_type(component.get("type", component_type))
            payload = component.get("data")
            if component_type == "at":
                target = component.get("qq") or component.get("target")
                if target is None and isinstance(payload, dict):
                    target = payload.get("qq") or payload.get("target")
                normalized = str(target or "").strip()
                if normalized and normalized != "all":
                    targets.append(normalized)
            continue

        if component_type != "at":
            continue
        target = getattr(component, "qq", None) or getattr(component, "target", None)
        payload = getattr(component, "data", None)
        if target is None and isinstance(payload, dict):
            target = payload.get("qq") or payload.get("target")
        normalized = str(target or "").strip()
        if normalized and normalized != "all":
            targets.append(normalized)
    return targets


def _build_qq_avatar_url(user_id: str) -> str:
    normalized = str(user_id or "").strip()
    if not normalized or not normalized.isdigit():
        return ""
    return f"https://q4.qlogo.cn/headimg_dl?dst_uin={normalized}&spec=640"


def _extract_mention_avatars(event: Any) -> list[str]:
    direct = _extract_image_strings_from_components(
        getattr(event, "mention_avatars", None),
        allow_plain_strings=True,
    )
    if direct:
        return direct

    message_obj = getattr(event, "message_obj", None)
    mentions = getattr(message_obj, "mentions", None)
    if not mentions:
        mentions = _extract_at_targets_from_message(message_obj)
        return [avatar for avatar in (_build_qq_avatar_url(mention) for mention in mentions) if avatar]

    avatars: list[str] = []
    for mention in mentions:
        if isinstance(mention, dict):
            for key in ("avatar", "avatar_url", "user_avatar", "face"):
                normalized = _normalize_image_candidate(mention.get(key))
                if normalized:
                    avatars.append(normalized)
                    break
            else:
                target = mention.get("qq") or mention.get("target")
                fallback = _build_qq_avatar_url(str(target or ""))
                if fallback:
                    avatars.append(fallback)
            continue

        for attr in ("avatar", "avatar_url", "user_avatar", "face"):
            normalized = _normalize_image_candidate(getattr(mention, attr, None))
            if normalized:
                avatars.append(normalized)
                break
        else:
            target = getattr(mention, "qq", None) or getattr(mention, "target", None)
            payload = getattr(mention, "data", None)
            if target is None and isinstance(payload, dict):
                target = payload.get("qq") or payload.get("target")
            fallback = _build_qq_avatar_url(str(target or ""))
            if fallback:
                avatars.append(fallback)
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


def _read_with_size_limit(reader, max_bytes: int) -> bytes:
    content = reader(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("image too large")
    return content


def _is_public_ip(ip_text: str) -> bool:
    ip = ipaddress.ip_address(ip_text)
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _is_safe_public_http_target(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
    except Exception:
        return False

    addresses = {info[4][0] for info in infos if info and len(info) >= 5 and info[4]}
    if not addresses:
        return False
    return all(_is_public_ip(addr) for addr in addresses)


def _decode_data_uri_limited(candidate: str, *, max_bytes: int) -> tuple[bytes, str] | None:
    try:
        header, payload = candidate.split(",", 1)
    except ValueError:
        return None

    lower_header = header.lower()
    if not lower_header.startswith("data:image/") or ";base64" not in lower_header:
        return None

    normalized_payload = payload.strip()
    estimated_size = (len(normalized_payload) * 3) // 4
    if estimated_size > max_bytes:
        return None

    try:
        image_bytes = base64.b64decode(normalized_payload, validate=True)
    except Exception:
        return None
    if len(image_bytes) > max_bytes:
        return None

    mime_type = header[5:].split(";", 1)[0].strip().lower()
    if not mime_type.startswith("image/"):
        return None
    return image_bytes, mime_type


def _open_http_no_redirect(url: str, *, timeout: int):
    opener = build_opener(_NoRedirectHandler())
    request = Request(url, method="GET")
    return opener.open(request, timeout=timeout)


def _read_bytes_from_http_limited(candidate: str, *, max_bytes: int) -> tuple[bytes, str] | None:
    if not _is_safe_public_http_target(candidate):
        return None

    current = candidate
    for _ in range(_MAX_REDIRECTS + 1):
        if not _is_safe_public_http_target(current):
            return None
        try:
            with _open_http_no_redirect(current, timeout=30) as response:
                final_url = str(getattr(response, "geturl", lambda: current)() or current)
                if final_url != current and not _is_safe_public_http_target(final_url):
                    return None

                image_bytes = _read_with_size_limit(response.read, max_bytes)
                info = getattr(response, "info", None)
                header_content_type = ""
                if callable(info):
                    headers = info()
                    header_content_type = str(getattr(headers, "get_content_type", lambda: "")())
                mime_type = _guess_mime_type(final_url, header_content_type=header_content_type)
                return image_bytes, mime_type
        except HTTPError as exc:
            if exc.code not in _REDIRECT_STATUS_CODES:
                return None
            location = str(exc.headers.get("Location", "")).strip()
            if not location:
                return None
            next_url = urljoin(current, location)
            if not _is_safe_public_http_target(next_url):
                return None
            current = next_url
            continue
        except Exception:
            return None
    return None


def _read_bytes_from_path_limited(candidate: str, *, max_bytes: int) -> tuple[bytes, str] | None:
    parsed = urlparse(candidate)
    if parsed.scheme in ("http", "https", "file"):
        return None
    if candidate.startswith("\\\\") or candidate.startswith("//"):
        return None
    if parsed.netloc:
        return None

    path = Path(candidate)
    if not path.is_file():
        return None
    if path.stat().st_size > max_bytes:
        return None

    image_bytes = path.read_bytes()
    if len(image_bytes) > max_bytes:
        return None
    mime_type = _guess_mime_type(str(path))
    return image_bytes, mime_type


def _candidate_kind(candidate: str) -> str:
    if _is_data_image_uri(candidate):
        return "data-uri"
    parsed = urlparse(candidate)
    if parsed.scheme:
        return f"url:{parsed.scheme}"
    return "path"


def _as_standard_data_uri_sync(candidate: str, *, max_bytes: int) -> str:
    if _is_data_image_uri(candidate):
        data_uri_result = _decode_data_uri_limited(candidate, max_bytes=max_bytes)
        if data_uri_result is None:
            return ""
        image_bytes, mime_type = data_uri_result
        return _to_data_uri(image_bytes, mime_type)

    http_result = _read_bytes_from_http_limited(candidate, max_bytes=max_bytes)
    if http_result is not None:
        image_bytes, mime_type = http_result
        return _to_data_uri(image_bytes, mime_type)

    path_result = _read_bytes_from_path_limited(candidate, max_bytes=max_bytes)
    if path_result is not None:
        image_bytes, mime_type = path_result
        return _to_data_uri(image_bytes, mime_type)

    return ""


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


def _first_normalized_or_empty(values: list[str]) -> str:
    for candidate in values:
        normalized = _normalize_image_candidate(candidate)
        if normalized:
            return normalized
    return ""


def _iter_priority_candidates(event: Any):
    for source_name, values in (
        ("current", _extract_current_images(event)),
        ("reply", _extract_reply_images(event)),
        ("avatar", _extract_mention_avatars(event)),
    ):
        first_candidate = _first_normalized_or_empty(values)
        if first_candidate:
            yield source_name, first_candidate


async def resolve_edit_image(event: Any) -> ResolvedMessageImage | None:
    for source_name, candidate in _iter_priority_candidates(event):
        try:
            data_uri = await asyncio.to_thread(
                _as_standard_data_uri_sync,
                candidate,
                max_bytes=MAX_IMAGE_BYTES,
            )
        except Exception as exc:
            _LOGGER.debug(
                "image conversion failed: source=%s kind=%s err_type=%s",
                source_name,
                _candidate_kind(candidate),
                type(exc).__name__,
            )
            continue
        if data_uri:
            return ResolvedMessageImage(source=source_name, image_data_uri=data_uri)
        _LOGGER.debug("image conversion rejected: source=%s kind=%s", source_name, _candidate_kind(candidate))
    return None
