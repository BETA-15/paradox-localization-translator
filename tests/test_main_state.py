from __future__ import annotations

import importlib
import os
import tempfile
import queue
from pathlib import Path
from types import SimpleNamespace

_data_root = Path(tempfile.mkdtemp(prefix="plt-main-test-"))
os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = str(_data_root)

main = importlib.import_module("main")


def test_relation_algorithm_change_invalidates_old_status_cache_generation():
    assert main.MOD_STATUS_CACHE_VERSION == 15
    assert main.core.TRANSLATION_RELATION_ALGORITHM_VERSION == 2
    assert main._translation_status_snapshot_is_current({"schema": 1}) is False
    assert main._translation_status_snapshot_is_current({
        "schema": 2,
        "mod_status_cache_version": 12,
        "relation_algorithm_version": 1,
    }) is False
    assert main._translation_status_snapshot_is_current({
        "schema": 2,
        "mod_status_cache_version": 15,
        "relation_algorithm_version": 2,
    }) is True


def test_compact_translation_status_result_keeps_gap_identity_without_source_text():
    result = {
        "mod": "Example",
        "status": "欠損あり",
        "candidates": [{"key": "example_key", "source_origin": "english_only", "source": "x" * 10000}],
        "external_translation_gaps": [{"key": "external_key", "source": "y" * 10000}],
    }

    compact = main._compact_translation_status_result(result)

    assert compact["mod"] == "Example"
    assert "candidates" not in compact
    assert "external_translation_gaps" not in compact
    assert main._status_gap_rows(compact) == [{"key": "example_key", "source_origin": "english_only"}]
    assert main._status_gap_rows(compact, external=True) == [{"key": "external_key"}]
    assert len(str(compact)) < 500


def test_translation_status_save_writes_current_generation_and_compact_rows(monkeypatch):
    saved = []
    monkeypatch.setattr(main.core, "save_json", lambda path, payload: saved.append((path, payload)))
    state = SimpleNamespace(
        _translation_status_save_after_id=None,
        _translation_status_pending_reason="",
        mod_research_results=[{
            "path": "/mods/example",
            "mod": "Example",
            "candidates": [{"key": "missing", "source": "large source text"}],
            "external_translation_gaps": [],
        }],
        _restore_status_snapshot_cache=None,
        _restore_status_rows_cache=None,
        _json_safe_state=main.App._json_safe_state,
        _workspace_scalar=main.App._workspace_scalar,
        _save_shared_mod_state_cache=lambda reason: None,
    )

    main.App._save_translation_status_state(state, "test")

    payload = saved[0][1]
    assert payload["schema"] == main.TRANSLATION_STATUS_SNAPSHOT_SCHEMA
    assert payload["mod_status_cache_version"] == main.MOD_STATUS_CACHE_VERSION
    assert payload["relation_algorithm_version"] == main.core.TRANSLATION_RELATION_ALGORITHM_VERSION
    assert main._translation_status_snapshot_is_current(payload)
    assert main._status_gap_rows(payload["results"][0]) == [{"key": "missing"}]
    assert payload["search"] == ""


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeStatusTree:
    def __init__(self):
        self.rows = {}
        self.selected = ()

    def get_children(self):
        return tuple(self.rows)

    def delete(self, iid):
        self.rows.pop(iid, None)

    def insert(self, parent, position, iid, values, tags=()):
        self.rows[iid] = {"values": values, "tags": tags}

    def selection(self):
        return self.selected

    def item(self, iid, option):
        return self.rows[iid][option]


class FakeDiscoveryTree:
    def __init__(self, selected=()):
        self.selected=tuple(selected)

    def selection(self):
        return self.selected


def test_mod_status_empty_row_distinguishes_search_from_no_scan_results():
    assert main._mod_status_empty_row("reali", 87)[:2] == (
        "検索結果なし", "検索条件「reali」に一致するModはありません"
    )
    assert main._mod_status_empty_row("", 0)[:2] == (
        "調査結果なし", "翻訳状況の調査結果がありません"
    )


def test_mod_status_tree_shows_non_operable_no_match_row():
    details = []
    actions = []
    state = SimpleNamespace(
        mod_status_tree=FakeStatusTree(),
        mod_status_search_var=FakeVar("reali"),
        mod_status_search_result_var=FakeVar(),
        mod_research_results=[{"mod": "More Bookmarks+", "status": "翻訳なし", "path": "/mods/bookmarks"}],
        _mod_status_matches_query=lambda result, query: main.App._mod_status_matches_query(state, result, query),
        _set_mod_status_selection_actions_enabled=lambda enabled: actions.append(enabled),
        _set_mod_status_detail_text=lambda text: details.append(text),
    )

    main.App._populate_mod_status_tree(state)

    assert tuple(state.mod_status_tree.rows) == (main.MOD_STATUS_EMPTY_IID,)
    row = state.mod_status_tree.rows[main.MOD_STATUS_EMPTY_IID]
    assert row["values"][0] == "検索結果なし"
    assert row["tags"] == ("empty",)
    assert state.mod_status_search_result_var.get() == "0件 / 全1件"
    assert actions[-1] is False
    assert "［解除］" in details[-1]

    state.mod_status_tree.selected = (main.MOD_STATUS_EMPTY_IID,)
    assert main.App._selected_mod_status_results(state) == []


def test_mod_status_game_filter_unions_selected_locations_of_same_game():
    state=SimpleNamespace(
        mod_research_results=[
            {"mod":"CK3 Workshop Mod","game":"Crusader Kings III"},
            {"mod":"CK3 Local Mod","game":"Crusader Kings III"},
            {"mod":"HOI4 Mod","game":"Hearts of Iron IV"},
        ],
        detected_mod_locations=[
            {"game":"Crusader Kings III","kind":"Steam Workshop"},
            {"game":"Crusader Kings III","kind":"ローカルMod"},
        ],
        discovered_mod_tree=FakeDiscoveryTree(("loc_0",)),
    )

    rows,games=main.App._game_filtered_mod_status_results(state)

    assert games == ["Crusader Kings III"]
    assert [row["mod"] for row in rows] == ["CK3 Workshop Mod","CK3 Local Mod"]


def test_mod_status_tree_explains_selected_game_without_results():
    details=[]
    state=SimpleNamespace(
        mod_status_tree=FakeStatusTree(), mod_status_search_var=FakeVar(""), mod_status_search_result_var=FakeVar(),
        mod_status_game_filter_var=FakeVar(),
        mod_research_results=[{"mod":"HOI4 Mod","game":"Hearts of Iron IV"}],
        detected_mod_locations=[{"game":"Crusader Kings III"}], discovered_mod_tree=FakeDiscoveryTree(("loc_0",)),
        _mod_status_matches_query=lambda result,query: True,
        _set_mod_status_selection_actions_enabled=lambda enabled: None,
        _set_mod_status_detail_text=lambda text: details.append(text),
    )

    main.App._populate_mod_status_tree(state)

    row=state.mod_status_tree.rows[main.MOD_STATUS_EMPTY_IID]
    assert row["values"][0] == "表示対象なし"
    assert "Crusader Kings III" in row["values"][1]
    assert "Crusader Kings III" in details[-1]


def test_qa_diff_language_bulk_selection_and_all_selection():
    pairs=[{"lang":"english","source":"a"},{"lang":"simp_chinese","source":"b"},{"lang":"english","source":"c"}]
    assert [p["source"] for p in main._qa_diff_pairs_for_language(pairs,"english")] == ["a","c"]
    assert [p["source"] for p in main._qa_diff_pairs_for_language(pairs,"simp_chinese")] == ["b"]
    assert main._qa_diff_pairs_for_language(pairs) == pairs


def test_diff_bulk_translation_deduplicates_same_target_key():
    contexts=[{"target_path":"/tmp/ja.yml"},{"target_path":"/tmp/ja.yml"},{"target_path":"/tmp/other.yml"}]
    tasks=[(0,"same"),(1,"same"),(2,"same"),(1,"unique")]
    assert main._dedupe_diff_translation_tasks(contexts,tasks) == [(0,"same"),(2,"same"),(1,"unique")]


def test_translation_status_save_schedule_coalesces_rapid_updates():
    callbacks = {}
    cancelled = []
    saved = []

    def after(delay, callback):
        token = f"after-{len(callbacks) + 1}"
        callbacks[token] = callback
        return token

    state = SimpleNamespace(
        _translation_status_save_after_id=None,
        _translation_status_pending_reason="",
        after=after,
        after_cancel=lambda token: cancelled.append(token),
        _save_translation_status_state=lambda reason: saved.append(reason),
    )

    main.App._schedule_translation_status_state_save(state, "first", 750)
    first_token = state._translation_status_save_after_id
    main.App._schedule_translation_status_state_save(state, "latest", 750)
    latest_token = state._translation_status_save_after_id
    callbacks[latest_token]()

    assert cancelled == [first_token]
    assert saved == ["latest"]
    assert state._translation_status_save_after_id is None


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


class RuntimeController:
    def __init__(self):
        self.settings = {"batch_size": 60, "workers": 2}

    def get_runtime_settings(self):
        return dict(self.settings)

    def update_runtime_settings(self, **settings):
        self.settings.update(settings)


def test_queue_continues_then_retries_only_failed_item(tmp_path, monkeypatch):
    calls = []
    outcomes = {"mod-a": [RuntimeError("broken file"), {"processed": 1, "jobs": 0, "failed": 0, "skipped": 0}],
                "mod-b": [{"processed": 1, "jobs": 0, "failed": 0, "skipped": 0}]}

    def fake_run(input_path, output_path, **kwargs):
        name = Path(input_path).name
        calls.append(name)
        result = outcomes[name].pop(0)
        if isinstance(result, Exception):
            raise result
        return {**result, "interrupted": False, "encoding_recoveries": [],
                "error_report": str(Path(output_path) / "translation_error_report.json")}

    monkeypatch.setattr(main.core, "run_translation", fake_run)
    monkeypatch.setattr(main, "record_error", lambda *args, **kwargs: None)
    items = [
        {"input": str(tmp_path / "mod-a"), "output": str(tmp_path / "out-a"), "mod_name": "A", "queue_item_id": "a"},
        {"input": str(tmp_path / "mod-b"), "output": str(tmp_path / "out-b"), "mod_name": "B", "queue_item_id": "b"},
    ]
    saved = []
    state = SimpleNamespace(
        queue_items=items, _active_normal_item_ids=["a", "b"], controller=RuntimeController(),
        events=queue.SimpleQueue(), current_queue_index=0,
        translation_start_settings={"batch": 60, "workers": 2},
        _checkpoint=lambda payload: saved.append(("checkpoint", payload)),
        _ensure_item_cache=lambda item: str(tmp_path / f"{item['queue_item_id']}.json"),
        _register_cache_job=lambda item: None,
        _item_has_remaining_translation_gap=lambda item: False,
        _write_session_file=lambda **kwargs: saved.append(("session", kwargs)),
    )

    main.App._queue_worker(state)

    events = []
    while not state.events.empty():
        events.append(state.events.get())
    done = next(payload for kind, payload in events if kind == "done")
    assert calls == ["mod-a", "mod-b", "mod-a"]
    assert [item["status"] for item in items] == ["完了", "完了"]
    assert done["recovered_items"] == 1
    assert done["unresolved_items"] == 0
    assert state.controller.settings == {"batch_size": 60, "workers": 2}
