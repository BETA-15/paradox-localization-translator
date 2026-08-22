from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

_data_root = Path(tempfile.mkdtemp(prefix="plt-main-test-"))
os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = str(_data_root)

main = importlib.import_module("main")


def test_relation_algorithm_change_invalidates_old_status_cache_generation():
    assert main.MOD_STATUS_CACHE_VERSION == 14
    assert main.core.TRANSLATION_RELATION_ALGORITHM_VERSION == 2
    assert main._translation_status_snapshot_is_current({"schema": 1}) is False
    assert main._translation_status_snapshot_is_current({
        "schema": 2,
        "mod_status_cache_version": 12,
        "relation_algorithm_version": 1,
    }) is False
    assert main._translation_status_snapshot_is_current({
        "schema": 2,
        "mod_status_cache_version": 14,
        "relation_algorithm_version": 2,
    }) is True


class FakeThread:
    def __init__(self, alive):
        self.alive = alive

    def is_alive(self):
        return self.alive


class FakeController:
    def __init__(self, stopping=False):
        self.stop_event = SimpleNamespace(is_set=lambda: stopping)


class FakeWidget:
    def __init__(self):
        self.state_value = None

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state_value = kwargs["state"]


def _state(**overrides):
    values = {
        "_closing": False,
        "worker": None,
        "chinese_worker": None,
        "differential_prepare_thread": None,
        "_differential_prepare_mode": None,
        "bulk_overwrite_thread": None,
        "_bulk_overwrite_queue_kind": None,
        "single_overwrite_thread": None,
        "data_root_move_thread": None,
        "backup_restore_operation_thread": None,
        "diagnostic_thread": None,
        "_thread_is_active": main.App._thread_is_active,
        "_operation_pending": main.App._operation_pending,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_normal_queue_locks_while_translation_is_running():
    state = _state(worker=FakeThread(True))
    assert main.App._normal_queue_locked(state)


def test_normal_queue_stays_locked_until_completion_event_is_applied():
    state = _state(worker=FakeThread(False))
    assert main.App._normal_queue_locked(state)


def test_chinese_queue_locks_during_shared_restore():
    state = _state(backup_restore_operation_thread=FakeThread(True))
    assert main.App._chinese_queue_locked(state)


def test_busy_ui_greys_out_conflicting_normal_controls():
    state = _state(worker=FakeThread(True))
    state._normal_queue_locked = lambda: main.App._normal_queue_locked(state)
    state._chinese_queue_locked = lambda: main.App._chinese_queue_locked(state)
    state._active_file_operation_names = lambda: ["通常翻訳"]
    state._set_control_group_state = main.App._set_control_group_state
    state._normal_queue_controls = [FakeWidget()]
    state._chinese_queue_controls = [FakeWidget()]
    state._cross_queue_controls = [FakeWidget()]
    state._data_root_controls = [FakeWidget()]
    state.start_btn = FakeWidget(); state.pause_btn = FakeWidget(); state.stop_btn = FakeWidget()
    state.chinese_start_btn = FakeWidget(); state.chinese_pause_btn = FakeWidget(); state.chinese_stop_btn = FakeWidget()
    state.controller = FakeController(False); state.chinese_controller = None

    main.App._refresh_operation_states(state)

    assert state._normal_queue_controls[0].state_value == "disabled"
    assert state._cross_queue_controls[0].state_value == "disabled"
    assert state._data_root_controls[0].state_value == "disabled"
    assert state.start_btn.state_value == "disabled"
    assert state.pause_btn.state_value == "normal"
    assert state.stop_btn.state_value == "normal"
    assert state._chinese_queue_controls[0].state_value == "normal"


def test_forced_exit_does_not_write_clean_marker(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_mark_runtime_clean_exit", lambda: calls.append("clean"))
    monkeypatch.setattr(main, "record_error", lambda *args, **kwargs: None)
    state = SimpleNamespace(_fatal_log_handle=None, destroy=lambda: calls.append("destroy"), _save_exit_state=lambda: calls.append("save"))

    main.App._finalize_app_exit(state, force=True)

    assert calls == ["destroy"]


def test_clean_exit_saves_then_writes_clean_marker(monkeypatch):
    calls = []
    monkeypatch.setattr(main, "_mark_runtime_clean_exit", lambda: calls.append("clean"))
    state = SimpleNamespace(_fatal_log_handle=None, destroy=lambda: calls.append("destroy"), _save_exit_state=lambda: calls.append("save"))

    main.App._finalize_app_exit(state, force=False)

    assert calls == ["save", "clean", "destroy"]


def test_malformed_persistent_json_is_quarantined(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "LOG_ROOT", tmp_path / "logs")
    broken = tmp_path / "workspace_state.json"
    broken.write_text("{broken", encoding="utf-8")

    assert main.load_persistent_json(broken, {"safe": True}, "テスト") == {"safe": True}
    assert not broken.exists()
    assert list(tmp_path.glob("workspace_state.json.corrupt_*"))
