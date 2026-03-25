from astrbot.api import logger
from astrbot.api.all import Image
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Reply

from .utils.image_store import save_image_bytes
from .utils.image_core import extract_command_prompt
from .utils.image_http import (
    fetch_image_bytes_from_result,
    fetch_models,
    request_generation,
)


@register(
    "蠢酒馆生图",
    "golangcmj",
    "蠢酒馆生图",
    "3.0.0",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.openai_api_base = str(config.get("openai_api_base", "") or "").strip()
        self.openai_api_key = str(config.get("openai_api_key", "") or "").strip()
        self.selected_model_id = str(config.get("selected_model_id", "") or "").strip()

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
                logger.warning("构造 Reply 组件失败，将退化为直接发图")
                return None

    async def _selected_model_is_available(self) -> bool:
        if not self.openai_api_base or not self.openai_api_key or not self.selected_model_id:
            return False

        try:
            models = await fetch_models(self.openai_api_base, self.openai_api_key)
        except Exception as exc:
            logger.warning("拉取模型列表失败，将继续使用已配置模型: %s", exc)
            return True

        return any(model.get("id") == self.selected_model_id for model in models)

    @filter.command("生图")
    async def generate_image(self, event: AstrMessageEvent, prompt: str = ""):
        if not self.openai_api_base or not self.openai_api_key:
            yield event.plain_result("当前未配置生图服务")
            return

        if not self.selected_model_id:
            yield event.plain_result("当前未配置模型")
            return

        raw_text = self._get_message_text(event)
        final_prompt = extract_command_prompt(raw_text, "生图")
        if not final_prompt:
            final_prompt = prompt or ""

        if not final_prompt:
            yield event.plain_result("请输入提示词")
            return

        if not await self._selected_model_is_available():
            yield event.plain_result("当前模型不可用，请在后台重新设置")
            return

        yield event.plain_result("图片生成中")

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
            logger.error("生图失败: %s", exc)
            yield event.plain_result("图片生成失败")
