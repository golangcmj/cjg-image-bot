from dataclasses import dataclass
import re


DATA_URI_PATTERN = re.compile(
    r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=_-]+",
    re.IGNORECASE,
)
TAG_PATTERN = re.compile(r"\[\[\s*([^\]=]+)\s*=\s*([^\]]+)\s*\]\]")
DEFAULT_STRENGTH_KEYWORD = "\u5f3a\u5ea6"
STANDARD_STRENGTH_KEYWORD = "strength"


@dataclass
class NormalizedEditPrompt:
    text: str
    image_data_uri: str
    strength: float
    normalized_prompt: str


def _strength_key_aliases(strength_keyword: str) -> set[str]:
    aliases = {STANDARD_STRENGTH_KEYWORD.casefold(), DEFAULT_STRENGTH_KEYWORD.casefold()}
    keyword = strength_keyword.strip()
    if keyword:
        aliases.add(keyword.casefold())
    return aliases


def _is_strength_key(key: str, strength_keyword: str) -> bool:
    normalized = key.strip()
    if not normalized:
        return False
    return normalized.casefold() in _strength_key_aliases(strength_keyword)


def _extract_first_valid_strength(raw_text: str, strength_keyword: str) -> float | None:
    for match in TAG_PATTERN.finditer(raw_text):
        key = match.group(1).strip()
        value_text = match.group(2).strip()
        if not _is_strength_key(key, strength_keyword):
            continue
        try:
            value = float(value_text)
        except ValueError:
            continue
        if 0 <= value <= 1:
            return value
    return None


def _strip_strength_tags(raw_text: str, strength_keyword: str) -> str:
    def replacer(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if _is_strength_key(key, strength_keyword):
            return ""
        return match.group(0)

    return TAG_PATTERN.sub(replacer, raw_text)


def sanitize_generate_prompt(raw_text: str, strength_keyword: str = DEFAULT_STRENGTH_KEYWORD) -> str:
    without_images = DATA_URI_PATTERN.sub("", raw_text)
    without_strength = _strip_strength_tags(without_images, strength_keyword)
    return without_strength


def normalize_edit_prompt_controls(
    *,
    raw_text: str,
    strength_keyword: str,
    default_strength: float,
) -> NormalizedEditPrompt:
    if not 0 <= default_strength <= 1:
        raise ValueError("default_strength must be between 0 and 1")

    image_match = DATA_URI_PATTERN.search(raw_text)
    image_data_uri = image_match.group(0) if image_match else ""

    strength = _extract_first_valid_strength(raw_text, strength_keyword)
    if strength is None:
        strength = default_strength

    without_images = DATA_URI_PATTERN.sub("", raw_text)
    without_strength_tags = _strip_strength_tags(without_images, strength_keyword)
    text = without_strength_tags

    strength_tag = f"[[strength={strength:g}]]"
    parts = [part for part in [text, image_data_uri, strength_tag] if part]
    normalized_prompt = "\n".join(parts)

    return NormalizedEditPrompt(
        text=text,
        image_data_uri=image_data_uri,
        strength=strength,
        normalized_prompt=normalized_prompt,
    )
