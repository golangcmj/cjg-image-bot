from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger(__name__)


def default_group_model_state_path(app_name: str = "cjg-image-bot") -> Path:
    explicit_base = os.getenv("ASTRBOT_DATA_DIR") or os.getenv("ASTRBOT_STATE_DIR")
    if explicit_base:
        base_dir = Path(explicit_base)
    elif os.name == "nt":
        base_dir = Path(os.getenv("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    else:
        base_dir = Path(os.getenv("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))
    return base_dir / app_name / "group_model_state.json"


def _read_attr(obj: Any, attr_names: tuple[str, ...]) -> str:
    for name in attr_names:
        value = getattr(obj, name, None)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def build_scope_key(event: Any) -> str:
    message_obj = getattr(event, "message_obj", None)

    group_value = _read_attr(
        event,
        ("group_id", "groupId", "group_code", "groupCode", "channel_id", "channelId", "guild_id", "guildId"),
    ) or _read_attr(
        message_obj,
        ("group_id", "groupId", "group_code", "groupCode", "channel_id", "channelId", "guild_id", "guildId"),
    )
    if group_value:
        return f"group:{group_value}"

    session_value = _read_attr(
        event,
        ("session_id", "sessionId", "conversation_id", "conversationId", "chat_id", "chatId", "peer_id", "peerId"),
    ) or _read_attr(
        message_obj,
        ("session_id", "sessionId", "conversation_id", "conversationId", "chat_id", "chatId", "peer_id", "peerId"),
    )
    if session_value:
        return f"session:{session_value}"

    user_value = _read_attr(
        event,
        ("user_id", "userId", "sender_id", "senderId", "from_id", "fromId", "uid"),
    ) or _read_attr(
        message_obj,
        ("user_id", "userId", "sender_id", "senderId", "from_id", "fromId", "uid"),
    )
    if user_value:
        return f"user:{user_value}"

    message_id = _read_attr(event, ("message_id", "id")) or _read_attr(message_obj, ("message_id", "id"))
    if message_id:
        return f"message:{message_id}"

    return "global:default"


class GroupModelStateStore:
    def __init__(self, state_path: str | Path | None):
        self._state_path = Path(state_path) if state_path else None
        self._state_cache: dict[str, str] | None = None

    def _load_state(self) -> dict[str, str]:
        if self._state_cache is not None:
            return self._state_cache

        self._state_cache = {}
        if self._state_path is None or not self._state_path.exists():
            return self._state_cache

        try:
            payload = json.loads(self._state_path.read_text(encoding="utf-8"))
        except Exception as exc:
            LOGGER.warning("读取群模型状态失败，忽略旧数据: %s", exc)
            return self._state_cache

        if isinstance(payload, dict):
            scopes = payload.get("scopes")
            if isinstance(scopes, dict):
                source = scopes
            else:
                source = payload
            for key, value in source.items():
                if not isinstance(key, str):
                    continue
                text = str(value or "").strip()
                if text:
                    self._state_cache[key] = text
        return self._state_cache

    def _save_state(self) -> bool:
        if self._state_path is None or self._state_cache is None:
            return True
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"scopes": self._state_cache}
            self._state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            return True
        except Exception as exc:
            LOGGER.warning("写入群模型状态失败: %s", exc)

            return False

    def get_model_id(self, scope_key: str) -> str:
        state = self._load_state()
        return str(state.get(str(scope_key).strip(), "") or "").strip()

    def set_model_id(self, scope_key: str, model_id: str) -> bool:
        key = str(scope_key or "").strip()
        value = str(model_id or "").strip()
        if not key or not value:
            return False
        state = self._load_state()
        previous_value = state.get(key)
        state[key] = value
        if self._save_state():
            return True
        if previous_value is None:
            state.pop(key, None)
        else:
            state[key] = previous_value
        return False

    def get_for_event(self, event: Any) -> str:
        return self.get_model_id(build_scope_key(event))

    def set_for_event(self, event: Any, model_id: str) -> bool:
        return self.set_model_id(build_scope_key(event), model_id)
