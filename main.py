from astrbot.api import logger
from astrbot.api.all import Image
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Reply

from .utils.image_core import extract_command_prompt, normalize_selected_model_value
from .utils.image_http import (
    fetch_image_bytes_from_result,
    fetch_models,
    request_generation,
)
from .utils.image_store import save_image_bytes
from .utils.message_image import resolve_edit_image
from .utils.prompt_media import normalize_edit_prompt_controls, sanitize_generate_prompt


@register(
    "蠢酒馆生图",
    "golangcmj",
    "蠢酒馆生图",
    "3.0.0",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config
        self.openai_api_base = ""
        self.openai_api_key = ""
        self.selected_model_id = ""
        self._reload_runtime_config(config)

    def _get_current_plugin_config(self) -> dict:
        latest = self.config or {}
        return latest if isinstance(latest, dict) else {}

    def _reload_runtime_config(self, config: dict | None = None) -> None:
        source = config if isinstance(config, dict) else self._get_current_plugin_config()
        self.openai_api_base = str(source.get("openai_api_base", "") or "").strip()
        self.openai_api_key = str(source.get("openai_api_key", "") or "").strip()
        self.selected_model_id = normalize_selected_model_value(str(source.get("selected_model_id", "") or ""))

    def _get_strength_keyword(self) -> str:
        source = self._get_current_plugin_config()
        keyword = str(source.get("strength_keyword", "") or "").strip()
        return keyword or "\u5f3a\u5ea6"

    def _get_default_i2i_strength(self) -> float:
        source = self._get_current_plugin_config()
        raw_value = source.get("default_i2i_strength", 0.35)
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            return 0.35
        if 0 <= value <= 1:
            return value
        return 0.35

    def _get_message_text(self, event: AstrMessageEvent) -> str:
        message_obj = getattr(event, "message_obj", None)
        message_chain = getattr(message_obj, "message", None)
        if message_chain:
            text_parts: list[str] = []
            for component in message_chain:
                text = getattr(component, "text", None)
                if isinstance(text, str):
                    text_parts.append(text)
            if text_parts:
                return "".join(text_parts)
        return getattr(event, "message_str", "") or ""

    def _build_reply_component(self, event: AstrMessageEvent):
        message_obj = getattr(event, "message_obj", None)
        message_id = getattr(message_obj, "message_id", None) or getattr(message_obj, "id", None)
        if message_id is None:
            return None

        try:
            return Reply(id=message_id)
        except TypeError:
            try:
                return Reply(message_id)
            except Exception:
                logger.warning("Reply \u7ec4\u4ef6\u6784\u9020\u5931\u8d25\uff0c\u6539\u4e3a\u76f4\u63a5\u53d1\u56fe")
                return None

    async def _selected_model_is_available(self) -> bool:
        if not self.openai_api_base or not self.openai_api_key or not self.selected_model_id:
            return False

        try:
            models = await fetch_models(self.openai_api_base, self.openai_api_key)
        except Exception as exc:
            logger.warning("\u62c9\u53d6\u6a21\u578b\u5217\u8868\u5931\u8d25\uff0c\u7ee7\u7eed\u4f7f\u7528\u5df2\u914d\u7f6e\u6a21\u578b: %s", exc)
            return True

        return any(model.get("id") == self.selected_model_id for model in models)

    @filter.command("\u751f\u56fe")
    async def generate_image(self, event: AstrMessageEvent, prompt: str = ""):
        self._reload_runtime_config()
        strength_keyword = self._get_strength_keyword()

        if not self.openai_api_base or not self.openai_api_key:
            yield event.plain_result("\u5f53\u524d\u672a\u914d\u7f6e\u751f\u56fe\u670d\u52a1")
            return

        if not self.selected_model_id:
            yield event.plain_result("\u5f53\u524d\u672a\u914d\u7f6e\u6a21\u578b")
            return

        raw_text = self._get_message_text(event)
        final_prompt = extract_command_prompt(raw_text, "\u751f\u56fe")
        if not final_prompt:
            final_prompt = prompt or ""
        final_prompt = sanitize_generate_prompt(final_prompt, strength_keyword=strength_keyword)

        if not final_prompt:
            yield event.plain_result("\u8bf7\u8f93\u5165\u63d0\u793a\u8bcd")
            return

        if not await self._selected_model_is_available():
            yield event.plain_result("\u5f53\u524d\u6a21\u578b\u4e0d\u53ef\u7528\uff0c\u8bf7\u5728\u540e\u53f0\u91cd\u65b0\u8bbe\u7f6e")
            return

        yield event.plain_result("\u56fe\u7247\u751f\u6210\u4e2d")

        try:
            result_kind, result_value = await request_generation(
                self.openai_api_base,
                self.openai_api_key,
                self.selected_model_id,
                final_prompt,
            )
            image_bytes = await fetch_image_bytes_from_result(result_kind, result_value)
            image_path = save_image_bytes(image_bytes)
            image_component = Image.fromFileSystem(image_path)

            chain = []
            reply_component = self._build_reply_component(event)
            if reply_component is not None:
                chain.append(reply_component)
            chain.append(image_component)
            yield event.chain_result(chain)
        except Exception as exc:
            logger.error("\u751f\u56fe\u5931\u8d25: %s", exc)
            yield event.plain_result(f"\u56fe\u7247\u751f\u6210\u5931\u8d25\n{exc}")

    @filter.command("\u6539\u56fe")
    async def edit_image(self, event: AstrMessageEvent, prompt: str = ""):
        self._reload_runtime_config()
        strength_keyword = self._get_strength_keyword()
        default_strength = self._get_default_i2i_strength()

        if not self.openai_api_base or not self.openai_api_key:
            yield event.plain_result("\u5f53\u524d\u672a\u914d\u7f6e\u751f\u56fe\u670d\u52a1")
            return

        if not self.selected_model_id:
            yield event.plain_result("\u5f53\u524d\u672a\u914d\u7f6e\u6a21\u578b")
            return

        raw_text = self._get_message_text(event)
        edit_text = extract_command_prompt(raw_text, "\u6539\u56fe")
        if not edit_text:
            edit_text = prompt or ""

        stripped_text = sanitize_generate_prompt(edit_text, strength_keyword=strength_keyword)
        if not stripped_text.strip():
            yield event.plain_result("\u8bf7\u8f93\u5165\u6539\u56fe\u63cf\u8ff0")
            return

        resolved_image = resolve_edit_image(event, strength_keyword=strength_keyword)
        if resolved_image is None:
            yield event.plain_result("\u672a\u68c0\u6d4b\u5230\u56fe\u7247")
            return

        normalized = normalize_edit_prompt_controls(
            raw_text=f"{edit_text}\n{resolved_image.image_data_uri}",
            strength_keyword=strength_keyword,
            default_strength=default_strength,
        )
        strength_tag = f"[[strength={normalized.strength:g}]]"
        final_prompt = "\n".join([stripped_text, resolved_image.image_data_uri, strength_tag])

        if not await self._selected_model_is_available():
            yield event.plain_result("\u5f53\u524d\u6a21\u578b\u4e0d\u53ef\u7528\uff0c\u8bf7\u5728\u540e\u53f0\u91cd\u65b0\u8bbe\u7f6e")
            return

        yield event.plain_result("\u56fe\u7247\u751f\u6210\u4e2d")

        try:
            result_kind, result_value = await request_generation(
                self.openai_api_base,
                self.openai_api_key,
                self.selected_model_id,
                final_prompt,
            )
            image_bytes = await fetch_image_bytes_from_result(result_kind, result_value)
            image_path = save_image_bytes(image_bytes)
            image_component = Image.fromFileSystem(image_path)

            chain = []
            reply_component = self._build_reply_component(event)
            if reply_component is not None:
                chain.append(reply_component)
            chain.append(image_component)
            yield event.chain_result(chain)
        except Exception as exc:
            logger.error("\u6539\u56fe\u5931\u8d25: %s", exc)
            yield event.plain_result(f"\u56fe\u7247\u751f\u6210\u5931\u8d25\n{exc}")
