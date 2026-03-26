from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from utils.group_model_state import GroupModelStateStore, build_scope_key  # type: ignore


class _Event:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.message_obj = kwargs.get("message_obj")


def test_build_scope_key_prefers_group_then_session_then_user():
    assert build_scope_key(_Event(group_id="1001", session_id="sess-A", user_id="u-1")) == "group:1001"
    assert build_scope_key(_Event(session_id="sess-A", user_id="u-1")) == "session:sess-A"
    assert build_scope_key(_Event(user_id="u-1")) == "user:u-1"


def test_build_scope_key_has_stable_global_fallback():
    assert build_scope_key(_Event()) == "global:default"


def test_group_model_state_store_isolates_groups_and_persists(tmp_path):
    state_path = tmp_path / "group_model_state.json"
    store = GroupModelStateStore(state_path)

    store.set_model_id("group:g-1", "preset-314")
    store.set_model_id("group:g-2", "preset-128")

    assert store.get_model_id("group:g-1") == "preset-314"
    assert store.get_model_id("group:g-2") == "preset-128"

    reopened = GroupModelStateStore(state_path)
    assert reopened.get_model_id("group:g-1") == "preset-314"
    assert reopened.get_model_id("group:g-2") == "preset-128"


def test_group_model_state_store_get_set_for_event(tmp_path):
    state_path = tmp_path / "group_model_state.json"
    store = GroupModelStateStore(state_path)

    event_a = _Event(group_id="1001")
    event_b = _Event(group_id="1002")
    assert store.set_for_event(event_a, "preset-314") is True
    assert store.set_for_event(event_b, "preset-128") is True

    assert store.get_for_event(event_a) == "preset-314"
    assert store.get_for_event(event_b) == "preset-128"


def test_group_model_state_store_returns_false_and_reverts_when_persist_fails(tmp_path):
    occupied_parent = tmp_path / "occupied"
    occupied_parent.write_text("not-a-directory", encoding="utf-8")
    store = GroupModelStateStore(occupied_parent / "group_model_state.json")

    assert store.set_model_id("group:1001", "preset-314") is False
    assert store.get_model_id("group:1001") == ""
