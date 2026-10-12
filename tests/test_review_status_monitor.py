from __future__ import annotations

import json
import queue
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
import translator_core as core
from test_relation_main_languages import isolate, mod_fixture, state
from test_overwrite_languages import state as overwrite_state


@pytest.mark.parametrize('bulk', [False, True])
@pytest.mark.parametrize('target', ['japanese', 'korean'])
def test_chinese_status_queue_only_inherits_matching_language(tmp_path, bulk, target, monkeypatch):
    root = mod_fixture(tmp_path)
    result = dict(path=str(root), localization=str(root / 'localization'), mod='Source',
                  target_lang='korean', simp_chinese_files=1,
                  external_translation_mod='Korean', external_translation_path='/synthetic/korean',
                  external_translation_localization='/synthetic/korean/localization',
                  external_translation_gaps=[{'key': 'missing'}], candidates=[{'key': 'local'}], gap_count=1)
    item = {'target_lang': target}
    if target != 'korean':
        item.update(external_translation_path='/stale', external_gap_keys=['stale'],
                    status_gap_candidates=[{'key': 'stale'}], status_gap_count=1)
    app = SimpleNamespace(
        _selected_mod_status_results=lambda: [result],
        _status_results_except_selected=lambda: ([], [result]),
        _append_chinese_queue=lambda *args: (item, ''),
        _refresh_chinese_queue_tree=lambda: None,
        chinese_status_var=SimpleNamespace(set=lambda value: None),
        _append_chinese_log=lambda value: None)
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args: None)
    method = main.App.queue_all_except_selected_mods_chinese if bulk else main.App.queue_selected_mods_to_chinese_basis
    method(app)
    if target == 'korean':
        assert item['external_translation_path'] == '/synthetic/korean'
        assert item['external_gap_keys'] == ['missing']
    else:
        assert not item.get('external_translation_path')
        assert not item.get('external_gap_keys')
        assert 'status_gap_candidates' not in item


@pytest.mark.parametrize('kind', ['source_mod_overwrite', 'legacy_ja', 'legacy_en'])
@pytest.mark.parametrize('present', [False, True])
def test_first_seen_reads_earliest_backup_files(tmp_path, monkeypatch, kind, present):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    for stamp, has_target in [('2026-01-01', present), ('2026-02-01', not present)]:
        backup = main.BACKUP_ROOT / 'game' / 'mod' / 'overwrite' / stamp
        loc = backup / 'localization'
        loc.mkdir(parents=True)
        (loc / 'source_l_english.yml').write_text('l_english:\n KEY:0 "Source"\n')
        if has_target:
            (loc / 'target_l_korean.yml').write_text('l_korean:\n KEY:0 "번역"\n')
        manifest = dict(target_root=str(root), snapshot_type='full_localization',
                        created_at=stamp, written_target_lang='korean')
        if kind.startswith('legacy'):
            manifest['backup_kind'] = main.i18n.t_lang('japanese' if kind == 'legacy_ja' else 'english', 'u6.source_mod_overwrite')
        else:
            manifest.update(backup_kind='Source display', backup_kind_id=kind)
        (backup / 'backup_manifest.json').write_text(json.dumps(manifest))
    assert state('korean')._first_seen_japanese_candidate(root) is present


def test_snapshot_records_language_independent_kind(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'BACKUP_ROOT', tmp_path / 'backups')
    root = mod_fixture(tmp_path)
    _, manifest = overwrite_state()._create_full_localization_snapshot(
        root, 'Translated display', backup_kind_id='source_mod_overwrite', target_lang='korean')
    assert manifest['backup_kind_id'] == 'source_mod_overwrite'


@pytest.mark.parametrize('language', [lang for lang in core.TARGET_LANGUAGES if lang != 'japanese'])
def test_monitor_classifier_uses_target_language(monkeypatch, language):
    sent = []
    monkeypatch.setattr(core, 'call_llm_raw', lambda *args, **kwargs: sent.append(args[4]) or '0|||YES')
    assert core.classify_monitor_candidates('fake', 'fake', 'fake', [{'target': 'Open'}], target_lang=language) == {0: True}
    assert core.target_language_name(language) in sent[0]
    assert '日本語' not in sent[0]


def test_monitor_refinement_forwards_language(monkeypatch):
    received = []
    monkeypatch.setattr(core, 'classify_monitor_candidates', lambda *args, **kwargs: received.append(kwargs.get('target_lang')) or {0: True})
    main.App._refine_candidates_with_monitor_llm(SimpleNamespace(events=queue.Queue()),
        [{'target': 'Open', 'needs_llm': True}], {'use_llm': True, 'model': 'fake', 'target_lang': 'korean'})
    assert received == ['korean']


def test_language_switch_stops_monitor_and_invalidates_generation():
    language = ['japanese']
    scheduled = []
    app = SimpleNamespace(
        target_lang_var=SimpleNamespace(get=lambda: language[0], set=lambda value: language.__setitem__(0, value)),
        target_lang_choice_var=SimpleNamespace(set=lambda value: None),
        _refresh_glossary_import_language_labels=lambda: None,
        monitor_thread=SimpleNamespace(is_alive=lambda: True),
        monitor_stop_event=threading.Event(), monitor_force_event=threading.Event(),
        monitor_llm_controller=None, _monitor_generation=1,
        monitor_candidates=[{'key': 'old'}], monitor_snapshot={'old': 1},
        clear_monitor_results=lambda: None,
        after=lambda delay, callback: scheduled.append(callback),
        _restart_monitor_after_language_change=lambda generation: None)
    main.App._set_target_lang(app, 'korean', save=False)
    assert app.monitor_stop_event.is_set()
    assert app._monitor_generation > 1
    assert app.monitor_candidates == []
    assert app.monitor_snapshot == {}
    assert scheduled


def test_stale_monitor_worker_cannot_publish_results(monkeypatch):
    events = queue.Queue()
    app = SimpleNamespace(events=events, _monitor_generation=1,
        _current_monitor_roots=lambda: [Path('/synthetic')],
        _monitor_worker_settings={'target_lang': 'japanese', 'generation': 1},
        monitor_stop_event=threading.Event(), monitor_force_event=threading.Event(),
        monitor_snapshot={}, monitor_candidates=[])
    monkeypatch.setattr(core, 'localization_file_stats', lambda root: {})
    monkeypatch.setattr(core, 'scan_translation_gaps', lambda *args, **kwargs: [{'key': 'old'}])
    def refine(candidates, settings):
        app._monitor_generation = 2
        return candidates
    app._refine_candidates_with_monitor_llm = refine
    main.App._monitor_worker(app, one_shot=True)
    assert app.monitor_candidates == []
    assert not any(kind == 'monitor_results' for kind, payload in list(events.queue))


def test_monitor_events_discard_old_generations_without_touching_ui():
    events = queue.Queue()
    for kind, payload in [('monitor_results', [{'key': 'old'}]), ('monitor_stopped', None),
                          ('monitor_error', 'old error'), ('monitor_progress', {'kind': 'llm_response'})]:
        main._put_monitor_event(SimpleNamespace(events=events), kind, payload, {'generation': 1})
    updates = []
    main._put_monitor_event(SimpleNamespace(events=events), 'monitor_status', 'new', {'generation': 2})
    thread = object()
    app = SimpleNamespace(events=events, _monitor_generation=2, monitor_thread=thread,
        monitor_status_var=SimpleNamespace(set=updates.append),
        _refresh_operation_states=lambda: None, after=lambda *args: None,
        _poll_events=lambda: None)
    main.App._poll_events(app)
    assert updates == ['new']
    assert app.monitor_thread is thread


def test_monitor_restart_waits_for_old_worker_and_can_be_cancelled():
    alive = [True]
    scheduled = []
    starts = []
    app = SimpleNamespace(_monitor_restart_generation=2,
        monitor_thread=SimpleNamespace(is_alive=lambda: alive[0]),
        after=lambda delay, callback: scheduled.append(callback),
        monitor_toggle_btn=SimpleNamespace(config=lambda **kwargs: None),
        start_monitor=lambda: starts.append('started'))
    app._restart_monitor_after_language_change = main.App._restart_monitor_after_language_change.__get__(app)
    app._restart_monitor_after_language_change(2)
    assert not starts
    alive[0] = False
    scheduled.pop()()
    assert starts == ['started']
    app._monitor_restart_generation = None
    app._restart_monitor_after_language_change(2)
    assert starts == ['started']


def test_missing_earliest_backup_is_not_replaced_by_later_evidence(tmp_path, monkeypatch):
    isolate(monkeypatch, tmp_path)
    root = mod_fixture(tmp_path)
    for stamp in ['2026-01-01', '2026-02-01']:
        backup = main.BACKUP_ROOT / 'game' / 'mod' / 'overwrite' / stamp
        backup.mkdir(parents=True)
        (backup / 'backup_manifest.json').write_text(json.dumps(dict(
            target_root=str(root), backup_kind_id='source_mod_overwrite',
            snapshot_type='full_localization', created_at=stamp)))
        if stamp == '2026-02-01':
            (backup / 'localization').mkdir()
    assert state('korean')._original_target_presence_before_overwrite(root, 'korean') is None


def test_normal_status_queue_retains_its_researched_language(tmp_path):
    root = mod_fixture(tmp_path)
    result = dict(path=str(root), localization=str(root / 'localization'), target_lang='korean',
                  external_translation_path='/synthetic/korean',
                  external_translation_gaps=[{'key': 'missing'}], candidates=[{'key': 'local'}], gap_count=1)
    app = SimpleNamespace(normal_output_var=SimpleNamespace(get=lambda: str(tmp_path / 'output')),
        _isolated_output_path=lambda *args, **kwargs: tmp_path / 'output', queue_items=[])
    app._append_queue = lambda *args, **kwargs: app.queue_items.append({'target_lang': kwargs['target_lang']})
    item = main.App._queue_mod_status_result(app, result)
    assert item['target_lang'] == 'korean'
    assert item['external_gap_keys'] == ['missing']
    assert item['status_gap_candidates'] == [{'key': 'local'}]


@pytest.mark.parametrize('target', ['japanese', 'korean'])
@pytest.mark.parametrize('missing_only', [False, True])
def test_status_derived_queue_transfer_does_not_cross_language_links(tmp_path, monkeypatch, target, missing_only):
    root = mod_fixture(tmp_path)
    source = dict(mod_root=str(root), mod_name='Source', target_lang='korean',
                  external_translation_path='/synthetic/korean', external_gap_keys=['missing'])
    destination = dict(target_lang=target)
    app = SimpleNamespace(_normal_queue_locked=lambda: False, _chinese_queue_locked=lambda: False,
        _selected_queue_items_for_kind=lambda kind: [source],
        _infer_mod_target_for_item=lambda item: (root / 'localization', root),
        _append_chinese_queue=lambda *args: (destination, ''),
        chinese_target_lang_var=SimpleNamespace(get=lambda: target),
        _write_missing_source_subset=lambda *args: root / 'localization',
        _refresh_queue_tree=lambda: None, _refresh_chinese_queue_tree=lambda: None,
        save_session=lambda **kwargs: None)
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args: None)
    scanned = []
    monkeypatch.setattr(core, 'scan_translation_gaps', lambda *args, **kwargs:
        scanned.append(kwargs['target_lang']) or [{'key': 'missing', 'source_origin': 'chinese_only'}])
    main.App.transfer_selected_queue_to_opposite(app, 'normal', missing_only=missing_only)
    assert bool(destination.get('external_translation_path')) == (target == 'korean')
    if missing_only:
        assert scanned == [target]
