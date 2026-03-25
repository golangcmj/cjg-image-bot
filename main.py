from pathlib import Path

from astrbot.api import logger
from astrbot.api.all import Image
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Reply

from .utils.image_store import save_image_bytes
from .utils.image_core import extract_command_prompt, normalize_selected_model_value
from .utils.image_http import (
    fetch_image_bytes_from_result,
    fetch_models,
    fetch_models_sync,
    request_generation,
)
from .utils.schema_store import clear_selected_model_options, persist_selected_model_options


@register(
    "蠢酒馆生图",
    "golangcmj",
    "蠢酒馆生图",
    "3.0.0",
)
class MyPlugin(Star):
    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.openai_api_base = ""
        self.openai_api_key = ""
        self.selected_model_id = ""
        self._model_source_signature = ""
        self._reload_runtime_config(config, force_sync=True)

    def _get_current_plugin_config(self) -> dict:
        try:
            latest = self.context.get_config() or {}
        except Exception:
            latest = {}
        return latest if isinstance(latest, dict) else {}

    def _reload_runtime_config(self, config: dict | None = None, force_sync: bool = False) -> None:
        source = config if isinstance(config, dict) else self._get_current_plugin_config()
        new_base = str(source.get("openai_api_base", "") or "").strip()
        new_key = str(source.get("openai_api_key", "") or "").strip()
        new_model = normalize_selected_model_value(str(source.get("selected_model_id", "") or ""))
        new_signature = f"{new_base}\n{new_key}"

        self.openai_api_base = new_base
        self.openai_api_key = new_key
        self.selected_model_id = new_model

        if force_sync or new_signature != self._model_source_signature:
            self._model_source_signature = new_signature
            self._sync_selected_model_options()

    def _sync_selected_model_options(self) -> None:
        schema_path = Path(__file__).with_name("_conf_schema.json")
        if not self.openai_api_base or not self.openai_api_key:
            clear_selected_model_options(schema_path, "请先填写服务地址和 API Key")
            return

        try:
            models = fetch_models_sync(self.openai_api_base, self.openai_api_key)
            if not models:
                clear_selected_model_options(schema_path, "当前没有可用模型")
                logger.info("模型列表为空，已清空模型下拉选项")
                return
            persist_selected_model_options(schema_path, models)
            logger.info("已动态更新模型下拉选项，共 %s 个模型", len(models))
        except Exception as exc:
            clear_selected_model_options(schema_path, "拉取模型列表失败，请检查服务地址和 API Key")
            logger.warning("动态拉取模型列表失败，已清空下拉配置: %s", exc)

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
        self._reload_runtime_config()

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
