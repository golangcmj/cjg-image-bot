from astrbot.api import logger
from astrbot.api.all import Image
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from astrbot.core.message.components import Reply

from .utils.image_core import extract_command_prompt, normalize_selected_model_value
from .utils.group_model_state import GroupModelStateStore, default_group_model_state_path
from .utils.image_http import (
    fetch_image_bytes_from_result,
    fetch_models,
    request_generation,
)
from .utils.image_store import save_image_bytes
from .utils.message_image import resolve_edit_image
from .utils.model_registry import (
    format_model_brief,
    format_model_listing,
    parse_model_directory_text,
    resolve_default_model,
    resolve_model_by_name_or_id,
)
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
        self.default_model = ""
        self.model_directory_text = ""
        self.model_directory: list[dict[str, str]] = []
        self._group_model_state = GroupModelStateStore(default_group_model_state_path())
        self._reload_runtime_config(config)

    def _get_current_plugin_config(self) -> dict:
        latest = self.config or {}
        return latest if isinstance(latest, dict) else {}

    def _reload_runtime_config(self, config: dict | None = None) -> None:
        source = config if isinstance(config, dict) else self._get_current_plugin_config()
        self.openai_api_base = str(source.get("openai_api_base", "") or "").strip()
        self.openai_api_key = str(source.get("openai_api_key", "") or "").strip()
        self.selected_model_id = normalize_selected_model_value(str(source.get("selected_model_id", "") or ""))
        self.default_model = str(source.get("default_model", "") or "").strip()
        self.model_directory_text = str(source.get("model_directory", "") or "")
        self.model_directory = parse_model_directory_text(self.model_directory_text)

    def _get_strength_keyword(self) -> str:
        source = self._get_current_plugin_config()
        keyword = str(source.get("strength_keyword", "") or "").strip()
        return keyword or "强度"

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
                logger.warning("Reply 组件构造失败，改为直接发图")
                return None

    def _resolve_effective_model(self, event: AstrMessageEvent) -> dict[str, str] | None:
        group_model_id = self._group_model_state.get_for_event(event)
        if group_model_id:
            group_model = resolve_model_by_name_or_id(self.model_directory, group_model_id)
            if group_model is not None:
                return group_model

        return resolve_default_model(
            self.model_directory,
            self.default_model,
            legacy_selected_model_id=self.selected_model_id,
        )

    async def _selected_model_is_available(self, model_id: str) -> bool:
        if not self.openai_api_base or not self.openai_api_key or not model_id:
            return False

        try:
            models = await fetch_models(self.openai_api_base, self.openai_api_key)
        except Exception as exc:
            logger.warning("拉取模型列表失败，继续使用已配置模型: %s", exc)
            return True

        return any(model.get("id") == model_id for model in models)

    async def _request_and_reply_image(
        self,
        event: AstrMessageEvent,
        final_prompt: str,
        *,
        action_name: str,
        model: dict[str, str],
    ):
        model_id = model.get("id", "")
        if not model_id:
            yield event.plain_result("当前未配置模型")
            return

        if not await self._selected_model_is_available(model_id):
            yield event.plain_result("当前模型不可用，请在后台重新设置")
            return

        yield event.plain_result("图片生成中")

        try:
            result_kind, result_value = await request_generation(
                self.openai_api_base,
                self.openai_api_key,
                model_id,
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
            logger.error("%s失败: %s", action_name, exc)
            yield event.plain_result(f"图片生成失败\n{exc}")

    @filter.command("当前模型")
    async def current_model(self, event: AstrMessageEvent):
        self._reload_runtime_config()
        model = self._resolve_effective_model(event)
        if model is None:
            yield event.plain_result("当前未配置模型")
            return
        yield event.plain_result(f"当前模型：{format_model_brief(model)}")

    @filter.command("模型列表")
    async def model_list(self, event: AstrMessageEvent):
        self._reload_runtime_config()

        if self.model_directory:
            yield event.plain_result(format_model_listing(self.model_directory))
            return

        yield event.plain_result("模型目录为空，请先配置 model_directory")

    @filter.command("切换模型")
    async def switch_model(self, event: AstrMessageEvent, prompt: str = ""):
        self._reload_runtime_config()
        raw_text = self._get_message_text(event)
        requested = extract_command_prompt(raw_text, "切换模型")
        if not requested:
            requested = prompt or ""
        requested = requested.strip()
        if not requested:
            yield event.plain_result("请输入模型名称或模型ID")
            return

        target = resolve_model_by_name_or_id(self.model_directory, requested)
        if target is None:
            yield event.plain_result("未找到目标模型，请先使用 /模型列表 查看可选项")
            return

        if not self._group_model_state.set_for_event(event, target["id"]):
            yield event.plain_result("模型切换失败，请检查插件状态目录权限")
            return
        yield event.plain_result(f"已切换模型：{format_model_brief(target)}")

    @filter.command("生图")
    async def generate_image(self, event: AstrMessageEvent, prompt: str = ""):
        self._reload_runtime_config()
        strength_keyword = self._get_strength_keyword()

        if not self.openai_api_base or not self.openai_api_key:
            yield event.plain_result("当前未配置生图服务")
            return

        model = self._resolve_effective_model(event)
        if model is None:
            yield event.plain_result("当前未配置模型")
            return

        raw_text = self._get_message_text(event)
        final_prompt = extract_command_prompt(raw_text, "生图")
        if not final_prompt:
            final_prompt = prompt or ""
        final_prompt = sanitize_generate_prompt(final_prompt, strength_keyword=strength_keyword)
        if not final_prompt:
            yield event.plain_result("请输入提示词")
            return

        async for item in self._request_and_reply_image(
            event,
            final_prompt,
            action_name="生图",
            model=model,
        ):
            yield item

    @filter.command("改图")
    async def edit_image(self, event: AstrMessageEvent, prompt: str = ""):
        self._reload_runtime_config()
        strength_keyword = self._get_strength_keyword()
        default_strength = self._get_default_i2i_strength()

        if not self.openai_api_base or not self.openai_api_key:
            yield event.plain_result("当前未配置生图服务")
            return

        model = self._resolve_effective_model(event)
        if model is None:
            yield event.plain_result("当前未配置模型")
            return

        raw_text = self._get_message_text(event)
        edit_text = extract_command_prompt(raw_text, "改图")
        if not edit_text:
            edit_text = prompt or ""

        stripped_text = sanitize_generate_prompt(edit_text, strength_keyword=strength_keyword)
        if not stripped_text.strip():
            yield event.plain_result("请输入改图描述")
            return

        resolved_image = await resolve_edit_image(event)
        if resolved_image is None:
            yield event.plain_result("未检测到图片")
            return

        normalized = normalize_edit_prompt_controls(
            raw_text=f"{edit_text}\n{resolved_image.image_data_uri}",
            strength_keyword=strength_keyword,
            default_strength=default_strength,
        )
        strength_tag = f"[[strength={normalized.strength:g}]]"
        final_prompt = "\n".join([stripped_text, resolved_image.image_data_uri, strength_tag])

        async for item in self._request_and_reply_image(
            event,
            final_prompt,
            action_name="改图",
            model=model,
        ):
            yield item
