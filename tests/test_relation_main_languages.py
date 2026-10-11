from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import tempfile
import subprocess
import sys
import queue
import threading
from pathlib import Path
from datetime import datetime
from types import SimpleNamespace

import pytest

os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = tempfile.mkdtemp(prefix="plt-relation-main-test-")

import main


def state(lang="japanese", app_class=None):
    app_class = app_class or main.App
    app = SimpleNamespace(
        target_lang_var=SimpleNamespace(get=lambda: lang),
        mod_classification_lock=threading.Lock(),
        mod_status_cache_lock=threading.Lock(),
        mod_relation_override_lock=threading.Lock(),
        mod_classification_cache={"schema": 2, "mods": {}},
        mod_status_cache={"version": 16, "items": {}},
        mod_relation_overrides={"schema": 1, "mods": {}},
        _restore_status_snapshot_cache=None,
        _restore_status_rows_cache=None,
        _save_shared_mod_state_cache=lambda *args: None,
        _save_translation_status_state=lambda *args: None,
    )
    for name in (
        "_mod_classification_key", "_current_mod_has_japanese",
        "_first_seen_japanese_candidate", "_mod_source_signature",
        "_cached_status_for_mod", "_cache_mod_status_result",
        "_mod_relation_override", "_set_mod_relation_override",
        "_save_mod_relation_overrides", "_load_translation_status_snapshot",
        "_original_target_presence_before_overwrite",
    ):
        if hasattr(app_class, name):
            setattr(app, name, getattr(app_class, name).__get__(app))
    return app


@pytest.fixture
def head_main(tmp_path, monkeypatch):
    workspace = Path(__file__).resolve().parents[1]
    contents = subprocess.run(["git", "show", "HEAD:app/main.py"], cwd=workspace,
                              capture_output=True, text=True, check=True, timeout=20).stdout
    source = tmp_path / "head_main.py"
    source.write_text(contents)
    spec = importlib.util.spec_from_file_location("l4b_head_main", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        for name in ("MOD_CLASSIFICATION_CACHE_PATH", "MOD_STATUS_CACHE_PATH",
                     "MOD_RELATION_OVERRIDES_PATH", "TRANSLATION_STATUS_STATE_PATH"):
            monkeypatch.setattr(module, name, getattr(main, name))
        yield module
    finally:
        sys.modules.pop(spec.name, None)


def mod_fixture(tmp_path):
    root = tmp_path / "source"
    loc = root / "localization"
    loc.mkdir(parents=True)
    (loc / "sample_l_english.yml").write_text('l_english:\n KEY:0 "Source"\n')
    (loc / "sample_l_korean.yml").write_text('l_korean:\n KEY:0 "번역"\n')
    return root


def isolate(monkeypatch, tmp_path):
    for name in ("MOD_CLASSIFICATION_CACHE_PATH", "MOD_STATUS_CACHE_PATH",
                 "MOD_RELATION_OVERRIDES_PATH", "TRANSLATION_STATUS_STATE_PATH"):
        monkeypatch.setattr(main, name, tmp_path / (name + ".json"))
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backups")


@pytest.fixture(autouse=True)
def japanese_ui():
    previous = main.i18n.get_ui_language()
    main.i18n.set_ui_language("japanese")
    yield
    main.i18n.set_ui_language(previous)


def test_head_format_four_files_remain_japanese(monkeypatch, tmp_path, head_main):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    app = state()
    key = str(root.resolve())
    signature_hash = hashlib.sha256()
    loc = root / "localization"
    files = sorted(loc.rglob("*.yml"))
    for file in files:
        stat = file.stat()
        signature_hash.update(str(file.relative_to(loc)).encode("utf-8", "ignore"))
        signature_hash.update(str(stat.st_size).encode())
        signature_hash.update(str(stat.st_mtime_ns).encode())
    signature_hash.update(str(len(files)).encode())
    signature = signature_hash.hexdigest()
    result = {"path": key, "mod": "source", "japanese_files": 0, "gap_count": 1}
    fixtures = {
        "MOD_CLASSIFICATION_CACHE_PATH": {"schema": 2, "mods": {key: {
            "mod": "source", "path": key, "had_japanese_at_first_seen": False,
            "initial_role": "source_mod", "first_seen_at": "2026-01-01"}}},
        "MOD_STATUS_CACHE_PATH": {"version": 16, "items": {key: {
            "signature": signature, "checked_at": "2026-01-01", "result": result}}},
        "MOD_RELATION_OVERRIDES_PATH": {"schema": 1, "mods": {key: {
            "role": "source", "source_paths": [], "mod": "source"}}},
        "TRANSLATION_STATUS_STATE_PATH": {"schema": 2,
            "mod_status_cache_version": 16, "relation_algorithm_version": 5,
            "results": [result], "selected_paths": [key]},
    }
    for name, payload in fixtures.items():
        getattr(main, name).write_text(json.dumps(payload))
        monkeypatch.setattr(head_main, name, getattr(main, name))
    app.mod_classification_cache = main.core.load_json(main.MOD_CLASSIFICATION_CACHE_PATH, {})
    app.mod_status_cache = main.core.load_json(main.MOD_STATUS_CACHE_PATH, {})
    app.mod_relation_overrides = main.core.load_json(main.MOD_RELATION_OVERRIDES_PATH, {})
    legacy = state(app_class=head_main.App)
    legacy.mod_classification_cache = main.core.load_json(main.MOD_CLASSIFICATION_CACHE_PATH, {})
    legacy.mod_status_cache = main.core.load_json(main.MOD_STATUS_CACHE_PATH, {})
    legacy.mod_relation_overrides = main.core.load_json(main.MOD_RELATION_OVERRIDES_PATH, {})
    assert app._first_seen_japanese_candidate(root) == legacy._first_seen_japanese_candidate(root)
    assert app._mod_relation_override(root) == legacy._mod_relation_override(root)
    assert app._mod_source_signature(root) == legacy._mod_source_signature(root)
    for tested_signature in (signature, "changed"):
        assert app._cached_status_for_mod(root, tested_signature) == legacy._cached_status_for_mod(root, tested_signature)
    assert app._load_translation_status_snapshot() == legacy._load_translation_status_snapshot()
    assert app._first_seen_japanese_candidate(root) is False
    assert app._mod_relation_override(root) == fixtures["MOD_RELATION_OVERRIDES_PATH"]["mods"][key]
    assert app._mod_source_signature(root) == signature
    assert app._cached_status_for_mod(root, signature) == dict(result, cached=True)
    assert app._cached_status_for_mod(root, "changed") is None
    assert app._load_translation_status_snapshot()["results"] == [result]
    app.target_lang_var = SimpleNamespace(get=lambda: "korean")
    assert app._cached_status_for_mod(root, signature) is None
    assert app._mod_relation_override(root) == {}
    assert app._load_translation_status_snapshot() == {}
    assert app._first_seen_japanese_candidate(root) is True
    assert app.mod_classification_cache["mods"][key]["had_japanese_at_first_seen"] is False
    assert app.mod_classification_cache["mods"][key]["had_target_at_first_seen"] == {"korean": True}


def test_language_cache_override_and_snapshot_roundtrip(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    app = state("korean")
    signature = app._mod_source_signature(root)
    app._cache_mod_status_result(root, signature, {"path": str(root), "target_lang": "korean"})
    app._set_mod_relation_override(root, "source")
    assert app._cached_status_for_mod(root, signature)["target_lang"] == "korean"
    assert app._mod_relation_override(root)["role"] == "source"
    assert app.mod_status_cache["items"] == {}
    assert app.mod_relation_overrides["mods"] == {}
    app.mod_research_results = [{"path": str(root), "target_lang": "korean"}]
    app._json_safe_state = main.App._json_safe_state
    app._workspace_scalar = lambda *args: ""
    main.App._save_translation_status_state(app)
    assert not main.TRANSLATION_STATUS_STATE_PATH.exists()
    assert app._load_translation_status_snapshot(force_disk=True)["target_lang"] == "korean"
    app.target_lang_var = SimpleNamespace(get=lambda: "japanese")
    assert app._mod_relation_override(root) == {}
    assert app._cached_status_for_mod(root, signature) is None
    assert app._load_translation_status_snapshot() == {}


def test_old_source_overwrite_snapshot_prevents_generated_candidate(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    backup = main.BACKUP_ROOT / "game" / "source__hash" / "overwrite" / "generation"
    backup.mkdir(parents=True)
    (backup / "backup_manifest.json").write_text(json.dumps({
        "schema_version": 2, "target_root": str(root),
        "backup_kind": main.i18n.t_lang("japanese", "u6.source_mod_overwrite"),
        "snapshot_type": "full_localization", "created_at": "2026-01-01",
    }))
    (backup / "localization").mkdir()
    app = state("korean")
    assert app._first_seen_japanese_candidate(root) is False
    app._set_mod_relation_override(root, "translation")
    assert app._mod_relation_override(root)["role"] == "translation"


@pytest.mark.parametrize("language", list(main.core.TARGET_LANGUAGES))
def test_worker_forwards_captured_language_without_tk_or_external_services(monkeypatch, tmp_path, language):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    app = state(language)
    app.events = queue.Queue()
    app.mod_research_stop_event = threading.Event()
    app._mod_research_worker_settings = {"target_lang": language, "check_translation_mods": True}
    app._annotate_translation_index_with_base_game_keys = lambda rows: rows
    app._build_stable_translation_mod_index = main.App._build_stable_translation_mod_index.__get__(app)
    app._refine_candidates_with_monitor_llm = lambda candidates, settings: candidates
    app._backup_game_name_for_root = lambda root: "synthetic"
    captured = []
    for name in ("build_translation_mod_index", "assign_translation_candidate_owners", "analyze_mod_translation_status"):
        original = getattr(main.core, name)
        def capture(*args, _original=original, _name=name, **kwargs):
            captured.append((_name, kwargs["target_lang"]))
            return _original(*args, **kwargs)
        monkeypatch.setattr(main.core, name, capture)
    app.target_lang_var = SimpleNamespace(get=lambda: pytest.fail("Worker read a Tk-backed variable"))
    main.App._mod_research_worker(app, [root])
    events = list(app.events.queue)
    errors = [payload for kind, payload in events if kind == "mod_research_error"]
    assert errors == []
    result = next(payload for kind, payload in events if kind == "mod_status_append")
    assert result.get("target_lang", "japanese") == language
    assert ("analyze_mod_translation_status", language) in captured
    if language == "english":
        assert captured == [("analyze_mod_translation_status", "english")]
        assert result["external_check_skipped"] == "english_target"
        assert main.i18n.t('u6.english_external_check_skipped') in main.ui_status.display_message(result)
    else:
        assert ("build_translation_mod_index", language) in captured
        assert ("assign_translation_candidate_owners", language) in captured
    cache = main.core.load_json(main.MOD_STATUS_CACHE_PATH, {})
    assert str(root.resolve()) in main._relation_language_items(cache, "items", language)


def test_snapshot_language_marker_blocks_mismatched_results(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    main.TRANSLATION_STATUS_STATE_PATH.write_text(json.dumps({"target_lang": "korean", "results": [{"path": "legacy"}]}))
    assert state()._load_translation_status_snapshot() == {}


def test_classification_preserves_other_languages_when_japanese_first_seen_later(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    app = state("korean")
    assert app._first_seen_japanese_candidate(root) is True
    app.target_lang_var = SimpleNamespace(get=lambda: "japanese")
    assert app._first_seen_japanese_candidate(root) is False
    assert app.mod_classification_cache["mods"][str(root.resolve())]["had_target_at_first_seen"] == {"korean": True}


def test_explicit_written_language_and_other_mod_backups(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    backup = main.BACKUP_ROOT / "game" / "source__hash" / "overwrite" / "generation"
    backup.mkdir(parents=True)
    manifest = {"target_root": str(root), "backup_kind": main.i18n.t('u6.source_mod_overwrite'),
                "snapshot_type": "full_localization", "written_target_lang": "korean"}
    (backup / "backup_manifest.json").write_text(json.dumps(manifest))
    assert state("korean")._first_seen_japanese_candidate(root) is False
    manifest["target_root"] = str(tmp_path / "other")
    (backup / "backup_manifest.json").write_text(json.dumps(manifest))
    assert state("korean")._first_seen_japanese_candidate(root) is True


@pytest.mark.parametrize("had_japanese", [False, True])
def test_head_historical_bootstrap_and_sticky_classification(monkeypatch, tmp_path, head_main, had_japanese):
    isolate(monkeypatch, tmp_path)
    fixed_clock = SimpleNamespace(now=lambda: datetime(2026, 10, 11, 12, 0, 0))
    monkeypatch.setattr(main, "datetime", fixed_clock)
    monkeypatch.setattr(head_main, "datetime", fixed_clock)
    for name in ("MOD_CLASSIFICATION_CACHE_PATH", "MOD_STATUS_CACHE_PATH",
                 "MOD_RELATION_OVERRIDES_PATH", "TRANSLATION_STATUS_STATE_PATH"):
        monkeypatch.setattr(head_main, name, getattr(main, name))
    root = mod_fixture(tmp_path)
    (root / "localization" / "generated_l_japanese.yml").write_text('l_japanese:\n KEY:0 "訳文"\n')
    key = str(root.resolve())
    cache = {"version": 16, "items": {key: {"signature": "old", "result": {
        "path": key, "japanese_files": int(had_japanese), "gap_count": 3}}}}
    main.MOD_STATUS_CACHE_PATH.write_text(json.dumps(cache))
    current = state()
    legacy = state(app_class=head_main.App)
    for app in (current, legacy):
        app.mod_status_cache = main.core.load_json(main.MOD_STATUS_CACHE_PATH, {})
        assert app._first_seen_japanese_candidate(root) is had_japanese
        assert app._first_seen_japanese_candidate(root) is had_japanese
    assert current.mod_classification_cache["mods"][key] == legacy.mod_classification_cache["mods"][key]


def test_language_switch_saves_previous_results_before_clearing():
    app = state()
    current_language = ["japanese"]
    app.target_lang_var = SimpleNamespace(get=lambda: current_language[0], set=lambda lang: current_language.__setitem__(0, lang))
    app.target_lang_choice_var = SimpleNamespace(set=lambda value: None)
    app.mod_research_results = [{"path": "synthetic", "mod": "synthetic"}]
    saved = []
    app._save_translation_status_state = lambda reason: saved.append((current_language[0], list(app.mod_research_results)))
    app._refresh_glossary_import_language_labels = lambda: None
    app.mod_status_tree = object()
    app.mod_research_stop_event = threading.Event()
    app._populate_mod_status_tree = lambda: None
    app._refresh_relation_target_labels = lambda previous, target: None
    app._restore_cached_mod_status = lambda: None
    main.App._set_target_lang(app, "korean", save=False)
    assert saved == [("japanese", [{"path": "synthetic", "mod": "synthetic"}])]
    assert current_language == ["korean"]
    assert app.mod_research_results == []


def test_english_tab_explains_skipped_external_matching_without_results():
    assert main.i18n.t('u6.english_external_check_skipped') in main._relation_scope_text("english")


def test_overwrite_invalidates_affected_mod_in_every_language(monkeypatch, tmp_path):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    app = state()
    key = str(root.resolve())
    other = str((tmp_path / "other").resolve())
    app.mod_status_cache["items"] = {key: {"signature": "ja"}, other: {"signature": "other"}}
    app.mod_status_cache["languages"] = {"korean": {"items": {key: {"signature": "ko"}, other: {"signature": "other"}}}}
    main.App._invalidate_status_cache_for_item(app, {"mod_root": str(root), "target_lang": "korean"})
    assert app.mod_status_cache["items"] == {other: {"signature": "other"}}
    assert app.mod_status_cache["languages"]["korean"]["items"] == {other: {"signature": "other"}}
