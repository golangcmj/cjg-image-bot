from pathlib import Path
import json
import sys
import asyncio
import importlib.util
import types


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.image_core import (  # type: ignore
    build_model_option_strings,
    build_generation_endpoint,
    build_generation_payload,
    build_models_endpoint,
    build_timeout_kwargs,
    extract_command_prompt,
    extract_image_result,
    format_model_listing,
    normalize_selected_model_value,
    parse_model_choices,
    resolve_selected_model_id,
    update_selected_model_schema,
)
from utils.image_http import (  # type: ignore
    fetch_image_bytes_from_result_sync,
    fetch_models_sync,
    request_generation_sync,
)
from utils.schema_store import persist_selected_model_options  # type: ignore
from utils.image_store import save_image_bytes  # type: ignore


class DummyResponse:
    def __init__(self, body: bytes):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_extract_command_prompt_preserves_newlines():
    raw = "/生图\n二次元美女\n\n白色长发\n蓝色眼睛"

    prompt = extract_command_prompt(raw, "生图")

    assert prompt == "二次元美女\n\n白色长发\n蓝色眼睛"


def test_extract_command_prompt_only_removes_one_separator_space():
    raw = "/生图  第一行  \n第二行  "

    prompt = extract_command_prompt(raw, "生图")

    assert prompt == " 第一行  \n第二行  "


def test_extract_command_prompt_empty_when_only_command():
    assert extract_command_prompt("/生图", "生图") == ""
    assert extract_command_prompt("/生图\n", "生图") == ""


def test_build_generation_payload_only_contains_model_and_prompt():
    payload = build_generation_payload("preset-314", "原始 prompt")

    assert payload == {
        "model": "preset-314",
        "prompt": "原始 prompt",
    }


def test_build_models_endpoint_accepts_base_url_with_or_without_v1():
    assert build_models_endpoint("https://image.cmjlevi.top") == "https://image.cmjlevi.top/v1/models"
    assert build_models_endpoint("https://image.cmjlevi.top/v1") == "https://image.cmjlevi.top/v1/models"


def test_build_generation_endpoint_accepts_base_url_with_or_without_v1():
    assert (
        build_generation_endpoint("https://image.cmjlevi.top")
        == "https://image.cmjlevi.top/v1/images/generations"
    )
    assert (
        build_generation_endpoint("https://image.cmjlevi.top/v1")
        == "https://image.cmjlevi.top/v1/images/generations"
    )


def test_parse_model_choices_uses_name_for_display():
    payload = {
        "object": "list",
        "data": [
            {"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"},
            {"id": "preset-128", "name": "写实人像"},
        ],
    }

    assert parse_model_choices(payload) == [
        {"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"},
        {"id": "preset-128", "name": "写实人像"},
    ]


def test_format_model_listing_renders_id_and_name():
    content = format_model_listing(
        [
            {"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"},
            {"id": "preset-128", "name": "写实人像"},
        ]
    )

    assert content == (
        "可用模型列表：\n"
        "preset-314 | 动漫预设1 | 鑫酒馆\n"
        "preset-128 | 写实人像"
    )


def test_format_model_listing_handles_empty_models():
    assert format_model_listing([]) == "当前没有可用模型"


def test_resolve_selected_model_id_accepts_exact_id():
    assert resolve_selected_model_id("preset-314", [{"id": "preset-314", "name": "动漫预设1"}]) == "preset-314"


def test_resolve_selected_model_id_accepts_name():
    assert resolve_selected_model_id("动漫预设1", [{"id": "preset-314", "name": "动漫预设1"}]) == "preset-314"


def test_resolve_selected_model_id_returns_none_for_unknown_value():
    assert resolve_selected_model_id("preset-999", [{"id": "preset-314", "name": "动漫预设1"}]) is None


def test_build_model_option_strings_include_id_and_name():
    assert build_model_option_strings(
        [{"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"}]
    ) == ["preset-314"]


def test_normalize_selected_model_value_extracts_id_from_option():
    assert normalize_selected_model_value("preset-314 | 动漫预设1 | 鑫酒馆") == "preset-314"
    assert normalize_selected_model_value("preset-314") == "preset-314"


def test_update_selected_model_schema_injects_dropdown_options():
    schema = {
        "selected_model_id": {
            "description": "固定模型 ID",
            "type": "string",
            "default": "",
        }
    }

    updated = update_selected_model_schema(
        schema,
        [{"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"}],
    )

    assert updated["selected_model_id"]["options"] == ["preset-314"]
    assert updated["selected_model_id"]["hint"] == "可选模型：\npreset-314 | 动漫预设1 | 鑫酒馆"


def test_persist_selected_model_options_writes_schema_file(tmp_path):
    schema_path = tmp_path / "_conf_schema.json"
    schema_path.write_text(
        json.dumps(
            {
                "selected_model_id": {
                    "description": "固定模型 ID",
                    "type": "string",
                    "default": "",
                }
            },
            ensure_ascii=False,
            indent=4,
        ),
        encoding="utf-8",
    )

    persist_selected_model_options(
        schema_path,
        [{"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"}],
    )

    updated = json.loads(schema_path.read_text(encoding="utf-8"))
    assert updated["selected_model_id"]["options"] == ["preset-314"]


def test_extract_image_result_prefers_b64_json():
    payload = {
        "created": 123,
        "data": [
            {"b64_json": "ZmFrZS1iYXNlNjQ="},
            {"url": "https://example.com/ignored.png"},
        ],
    }

    assert extract_image_result(payload) == ("b64_json", "ZmFrZS1iYXNlNjQ=")


def test_extract_image_result_falls_back_to_url():
    payload = {
        "created": 123,
        "data": [
            {"url": "https://example.com/output.png"},
        ],
    }

    assert extract_image_result(payload) == ("url", "https://example.com/output.png")


def test_build_timeout_kwargs_has_no_total_or_read_deadline():
    timeout_kwargs = build_timeout_kwargs()

    assert timeout_kwargs["total"] is None
    assert timeout_kwargs["sock_read"] is None
    assert timeout_kwargs["connect"] == 30


def test_fetch_models_sync_requests_models_endpoint_with_bearer_auth():
    def fake_urlopen(request, timeout=None):
        assert request.full_url == "https://image.cmjlevi.top/v1/models"
        assert request.get_method() == "GET"
        assert request.headers["Authorization"] == "Bearer sk-test"
        return DummyResponse(
            json.dumps(
                {
                    "data": [
                        {"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"},
                    ]
                }
            ).encode("utf-8")
        )

    models = fetch_models_sync(
        "https://image.cmjlevi.top",
        "sk-test",
        urlopen_func=fake_urlopen,
    )

    assert models == [{"id": "preset-314", "name": "动漫预设1 | 鑫酒馆"}]


def test_request_generation_sync_posts_only_model_and_prompt():
    raw_prompt = "二次元美女\n\n白色长发  "

    def fake_urlopen(request, timeout=None):
        assert request.full_url == "https://image.cmjlevi.top/v1/images/generations"
        assert request.get_method() == "POST"
        assert request.headers["Authorization"] == "Bearer sk-test"
        payload = json.loads(request.data.decode("utf-8"))
        assert payload == {
            "model": "preset-314",
            "prompt": raw_prompt,
        }
        return DummyResponse(
            json.dumps(
                {
                    "data": [
                        {"b64_json": "ZmFrZS1pbWFnZS1ieXRlcw=="},
                    ]
                }
            ).encode("utf-8")
        )

    result = request_generation_sync(
        "https://image.cmjlevi.top",
        "sk-test",
        "preset-314",
        raw_prompt,
        urlopen_func=fake_urlopen,
    )

    assert result == ("b64_json", "ZmFrZS1pbWFnZS1ieXRlcw==")


def test_fetch_image_bytes_from_result_sync_decodes_b64_json():
    image_bytes = fetch_image_bytes_from_result_sync("b64_json", "ZmFrZS1pbWFnZS1ieXRlcw==")

    assert image_bytes == b"fake-image-bytes"


def test_fetch_image_bytes_from_result_sync_downloads_url_bytes():
    def fake_urlopen(request, timeout=None):
        assert request.full_url == "https://example.com/generated.png"
        assert request.get_method() == "GET"
        return DummyResponse(b"png-bytes")

    image_bytes = fetch_image_bytes_from_result_sync(
        "url",
        "https://example.com/generated.png",
        urlopen_func=fake_urlopen,
    )

    assert image_bytes == b"png-bytes"


def test_save_image_bytes_writes_png_file(tmp_path):
    image_path = save_image_bytes(b"fake-png-bytes", image_dir=tmp_path)

    saved = Path(image_path)
    assert saved.exists()
    assert saved.parent == tmp_path
    assert saved.suffix == ".png"
    assert saved.read_bytes() == b"fake-png-bytes"


def _load_main_module():
    fake_astrbot = types.ModuleType("astrbot")
    fake_api = types.ModuleType("astrbot.api")
    fake_api_all = types.ModuleType("astrbot.api.all")
    fake_api_event = types.ModuleType("astrbot.api.event")
    fake_api_star = types.ModuleType("astrbot.api.star")
    fake_core = types.ModuleType("astrbot.core")
    fake_core_message = types.ModuleType("astrbot.core.message")
    fake_core_components = types.ModuleType("astrbot.core.message.components")

    class _DummyLogger:
        @staticmethod
        def warning(*args, **kwargs):
            return None

        @staticmethod
        def error(*args, **kwargs):
            return None

    class _DummyImage:
        @staticmethod
        def fromFileSystem(path):
            return f"image:{path}"

    class _DummyReply:
        def __init__(self, id=None):
            self.id = id

    class _DummyStar:
        def __init__(self, context):
            self.context = context

    class _DummyContext:
        pass

    class _DummyAstrMessageEvent:
        pass

    def _dummy_register(*args, **kwargs):
        def decorator(cls):
            return cls

        return decorator

    class _DummyFilter:
        @staticmethod
        def command(_name):
            def decorator(func):
                return func

            return decorator

    fake_api.logger = _DummyLogger()
    fake_api_all.Image = _DummyImage
    fake_api_event.filter = _DummyFilter()
    fake_api_event.AstrMessageEvent = _DummyAstrMessageEvent
    fake_api_star.Context = _DummyContext
    fake_api_star.Star = _DummyStar
    fake_api_star.register = _dummy_register
    fake_core_components.Reply = _DummyReply

    sys.modules["astrbot"] = fake_astrbot
    sys.modules["astrbot.api"] = fake_api
    sys.modules["astrbot.api.all"] = fake_api_all
    sys.modules["astrbot.api.event"] = fake_api_event
    sys.modules["astrbot.api.star"] = fake_api_star
    sys.modules["astrbot.core"] = fake_core
    sys.modules["astrbot.core.message"] = fake_core_message
    sys.modules["astrbot.core.message.components"] = fake_core_components

    spec = importlib.util.spec_from_file_location(
        "cjg_image_bot_testpkg",
        str(ROOT / "main.py"),
        submodule_search_locations=[str(ROOT)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec is not None and spec.loader is not None
    sys.modules["cjg_image_bot_testpkg"] = module
    spec.loader.exec_module(module)
    return module


class _DummyEvent:
    def __init__(self, message_str: str, *, current_images=None, reply_images=None, mention_avatars=None):
        self.message_str = message_str
        self.message_obj = None
        self.current_images = current_images or []
        self.reply_images = reply_images or []
        self.mention_avatars = mention_avatars or []

    def plain_result(self, text):
        return ("plain", text)

    def chain_result(self, chain):
        return ("chain", chain)


def test_generate_image_sanitizes_control_fragments_before_submission(monkeypatch):
    module = _load_main_module()
    plugin = module.MyPlugin(
        context=object(),
        config={
            "openai_api_base": "https://image.example",
            "openai_api_key": "sk-test",
            "selected_model_id": "preset-314",
        },
    )

    async def _available():
        return True

    captured_prompt = {"value": None}

    async def _fake_request_generation(base, key, model, prompt):
        captured_prompt["value"] = prompt
        return "b64_json", "ZmFrZS1pbWFnZS1ieXRlcw=="

    async def _fake_fetch_image_bytes(_kind, _value):
        return b"fake-image-bytes"

    monkeypatch.setattr(plugin, "_selected_model_is_available", _available)
    monkeypatch.setattr(module, "request_generation", _fake_request_generation)
    monkeypatch.setattr(module, "fetch_image_bytes_from_result", _fake_fetch_image_bytes)
    monkeypatch.setattr(module, "save_image_bytes", lambda *_args, **_kwargs: "fake.png")

    raw = "/生图 data:image/png;base64,QUJD [[强度=0.3]] 漫画女孩"
    event = _DummyEvent(raw)

    asyncio.run(_collect_results(plugin.generate_image(event)))

    prompt_value = captured_prompt["value"]
    assert prompt_value is not None
    assert "data:image/" not in prompt_value
    assert "[[强度=" not in prompt_value
    assert "[[strength=" not in prompt_value
    assert "漫画女孩" in prompt_value


def test_edit_image_requires_non_empty_text_after_control_stripping():
    module = _load_main_module()
    plugin = module.MyPlugin(
        context=object(),
        config={
            "openai_api_base": "https://image.example",
            "openai_api_key": "sk-test",
            "selected_model_id": "preset-314",
        },
    )
    event = _DummyEvent("/改图 [[强度=0.3]] data:image/png;base64,QUJD")

    outputs = asyncio.run(_collect_results(plugin.edit_image(event)))

    assert ("plain", "请输入改图描述") in outputs


def test_edit_image_returns_no_image_message_when_not_found():
    module = _load_main_module()
    plugin = module.MyPlugin(
        context=object(),
        config={
            "openai_api_base": "https://image.example",
            "openai_api_key": "sk-test",
            "selected_model_id": "preset-314",
        },
    )
    event = _DummyEvent("/改图 请加一点暖色调")

    outputs = asyncio.run(_collect_results(plugin.edit_image(event)))

    assert ("plain", "未检测到图片") in outputs


def test_edit_image_builds_prompt_with_resolved_image_and_strength(monkeypatch):
    module = _load_main_module()
    plugin = module.MyPlugin(
        context=object(),
        config={
            "openai_api_base": "https://image.example",
            "openai_api_key": "sk-test",
            "selected_model_id": "preset-314",
            "default_i2i_strength": 0.35,
            "strength_keyword": "强度",
        },
    )

    async def _available():
        return True

    captured_prompt = {"value": None}

    async def _fake_request_generation(base, key, model, prompt):
        captured_prompt["value"] = prompt
        return "b64_json", "ZmFrZS1pbWFnZS1ieXRlcw=="

    async def _fake_fetch_image_bytes(_kind, _value):
        return b"fake-image-bytes"

    monkeypatch.setattr(plugin, "_selected_model_is_available", _available)
    monkeypatch.setattr(module, "request_generation", _fake_request_generation)
    monkeypatch.setattr(module, "fetch_image_bytes_from_result", _fake_fetch_image_bytes)
    monkeypatch.setattr(module, "save_image_bytes", lambda *_args, **_kwargs: "fake.png")

    event = _DummyEvent(
        "/改图 请改成赛博朋克 [[强度=0.3]]",
        current_images=["data:image/png;base64,QUJD"],
    )

    outputs = asyncio.run(_collect_results(plugin.edit_image(event)))

    prompt_value = captured_prompt["value"]
    assert prompt_value is not None
    assert "请改成赛博朋克" in prompt_value
    assert "data:image/png;base64,QUJD" in prompt_value
    assert "[[strength=0.3]]" in prompt_value
    assert any(item[0] == "chain" for item in outputs)


async def _collect_results(async_generator):
    result = []
    async for item in async_generator:
        result.append(item)
    return result
