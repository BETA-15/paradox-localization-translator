from __future__ import annotations

import ast
import json
import queue
import subprocess
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

import main


def write(path, language, values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('\ufeffl_' + language + ':\n' + ''.join(
        f' {key}:0 "{value}"\n' for key, value in values.items()), encoding='utf-8')


def state():
    result = SimpleNamespace(mod_research_results=[],
        _infer_mod_target_for_item=lambda item: (Path(item['mod_root']) / 'localization', Path(item['mod_root'])),
        _invalidate_mod_status_cache_paths=lambda paths: None)
    for name in ('_create_full_localization_snapshot', '_backup_game_name_for_root',
                 '_safe_backup_mod_token', '_next_overwrite_backup_generation',
                 '_backup_manifest_records', '_generated_japanese_files', '_source_overwrite_layout'):
        setattr(result, name, types.MethodType(getattr(main.App, name), result))
    return result


def existing_value(language):
    return {'korean': '기존 번역', 'russian': 'Существующий перевод',
            'simp_chinese': '现有翻译'}.get(language, 'Existing')


def setup(tmp_path, monkeypatch, language):
    monkeypatch.setattr(main, 'BACKUP_ROOT', tmp_path / 'backups')
    source = tmp_path / 'source'
    external = tmp_path / 'translation'
    output = tmp_path / 'output'
    write(source / 'localization/english/source_l_english.yml', 'english', {'kept': 'Original', 'added': 'New'})
    existing = external / f'localization/{language}/source_l_{language}.yml'
    write(existing, language, {'kept': existing_value(language)})
    write(output / f'{language}/source_l_{language}.yml', language, {'kept': 'Changed', 'added': 'Translated', 'ignored': 'Ignore'})
    item = dict(target_lang=language, mod_root=str(source), input=str(source / 'localization'),
                output=str(output), external_translation_path=str(external),
                external_translation_localization=str(external / 'localization'),
                external_gap_keys=['kept', 'added'], missing_keys=['kept', 'added'])
    return state(), item, existing


@pytest.mark.parametrize('language', ['korean', 'russian', 'german'])
@pytest.mark.parametrize('operation', ['gap', 'missing', 'full', 'source'])
def test_target_overwrites_preserve_existing_values(tmp_path, monkeypatch, language, operation):
    app, item, existing = setup(tmp_path, monkeypatch, language)
    if operation == 'source':
        existing = Path(item['mod_root']) / f'localization/{language}/source_l_{language}.yml'
        write(existing, language, {'kept': existing_value(language)})
    before = existing.read_bytes()
    if operation == 'gap':
        ok, reason = main.App._perform_external_gap_overwrite(app, item, False, False)
    elif operation == 'missing':
        ok, reason = main.App._merge_missing_only_output(app, item, existing.parents[1], existing.parents[2], False, False)
    elif operation == 'full':
        ok, reason = main.App._perform_full_translation_mod_overwrite(app, item,
            dict(path=item['external_translation_path'], localization=item['external_translation_localization']), False, False)
    else:
        ok, reason = main.App._perform_source_mod_overwrite(app, item, False, False)
    assert ok, reason
    assert main.core.parse_localization_file(existing)[1]['kept'] == existing_value(language)
    values = {}
    for path in main._generated_language_files(existing.parents[1], language):
        header, entries, _ = main.core.parse_localization_file(path)
        assert header == language
        assert f'_l_{language}.yml' in path.name
        values.update(entries)
    assert values['added'] == 'Translated'
    if operation in ('gap', 'missing'):
        assert existing.read_bytes() == before
        assert 'ignored' not in values
    manifest_path = next((tmp_path / 'backups').rglob('backup_manifest.json'))
    assert json.loads(manifest_path.read_text())['written_target_lang'] == language
    assert (manifest_path.parent / existing.relative_to(existing.parents[2])).read_bytes() == before


@pytest.mark.parametrize('operation', ['gap', 'full'])
def test_english_external_overwrite_is_refused(tmp_path, monkeypatch, operation):
    app, item, existing = setup(tmp_path, monkeypatch, 'english')
    before = existing.read_bytes()
    if operation == 'gap':
        ok, reason = main.App._perform_external_gap_overwrite(app, item, False, False)
    else:
        ok, reason = main.App._perform_full_translation_mod_overwrite(app, item,
            dict(path=item['external_translation_path'], localization=item['external_translation_localization']), False, False)
    assert not ok and reason
    assert existing.read_bytes() == before
    assert not (tmp_path / 'backups').exists()


@pytest.mark.parametrize('operation', ['gap', 'missing', 'full', 'source'])
def test_unsupported_game_language_is_refused(tmp_path, monkeypatch, operation):
    app, item, existing = setup(tmp_path, monkeypatch, 'korean')
    item['game'] = 'Europa Universalis IV'
    before = existing.read_bytes()
    if operation == 'gap':
        ok, reason = main.App._perform_external_gap_overwrite(app, item, False, False)
    elif operation == 'missing':
        ok, reason = main.App._merge_missing_only_output(app, item, existing.parents[1], existing.parents[2], False, False)
    elif operation == 'full':
        ok, reason = main.App._perform_full_translation_mod_overwrite(app, item,
            dict(path=item['external_translation_path'], localization=item['external_translation_localization']), False, False)
    else:
        ok, reason = main.App._perform_source_mod_overwrite(app, item, False, False)
    assert not ok and reason
    assert existing.read_bytes() == before
    assert not (tmp_path / 'backups').exists()


@pytest.mark.parametrize('language', ['korean', 'russian', 'german', 'english'])
def test_missing_subset_is_translated_without_llm_then_merged(tmp_path, monkeypatch, language):
    app, item, _existing = setup(tmp_path, monkeypatch, language)
    monkeypatch.setattr(main, 'WORK_STATE_ROOT', tmp_path / 'work')
    source_language = 'simp_chinese' if language == 'english' else 'english'
    item['mod_root'] = str(tmp_path / 'missing-source')
    item['output'] = str(tmp_path / 'missing-output')
    loc = Path(item['mod_root']) / 'localization'
    write(loc / f'{language}/existing_l_{language}.yml', language, {'kept': 'Existing'})
    write(loc / f'{source_language}/original_l_{source_language}.yml', source_language,
          {'kept': 'Old source', 'added': 'New source'})
    sparse = main.App._write_missing_source_subset(app, loc, source_language, ['added'], 'Fixture')
    calls = []
    translated = {'korean': '새로운 번역 문장', 'russian': 'Новый перевод текста',
                  'german': 'Ein neuer übersetzter Text', 'english': 'A newly translated sentence'}[language]

    def fake_translate(_url, _model, jobs, source_lang, *args, **kwargs):
        calls.extend((source_lang, kwargs.get('target_lang'), job['key']) for job in jobs)
        return [translated for job in jobs]

    monkeypatch.setattr(main.core, 'translate_batch', fake_translate)
    main.core.run_translation(sparse, Path(item['output']), target_lang=language, verbose=False,
                              dual_source=True, qa_backup_root=tmp_path / 'qa')
    item['missing_keys'] = ['added']
    assert calls and all(call == (source_language, language, 'added') for call in calls)
    before = (loc / f'{language}/existing_l_{language}.yml').read_bytes()
    ok, reason = main.App._merge_missing_only_output(app, item, loc, Path(item['mod_root']), False, False)
    assert ok, reason
    assert (loc / f'{language}/existing_l_{language}.yml').read_bytes() == before
    patch = loc / language / f'paradox_localization_translator_missing_l_{language}.yml'
    assert main.core.parse_localization_file(patch)[1] == {'added': translated}


def test_current_target_is_used_only_when_item_has_no_language(tmp_path, monkeypatch):
    app, item, existing = setup(tmp_path, monkeypatch, 'korean')
    app.target_lang_var = SimpleNamespace(get=lambda: 'german')
    assert main._overwrite_target_lang(app, item) == 'korean'
    app.target_lang_var = SimpleNamespace(get=lambda: 'korean')
    item.pop('target_lang')
    ok, reason = main.App._perform_external_gap_overwrite(app, item, False, False)
    assert ok, reason
    assert main.core.parse_localization_file(existing)[1] == {'kept': existing_value('korean')}


@pytest.mark.parametrize('language', ['korean', 'russian', 'german', 'english'])
def test_differential_start_accepts_target_languages(language):
    assert main._target_language_problems([dict(target_lang=language)], diff_requested=True)[0] == ''


@pytest.mark.parametrize('language', ['korean', 'russian', 'german', 'english'])
def test_differential_preparation_selects_only_absent_target_keys(tmp_path, monkeypatch, language):
    app, item, existing = setup(tmp_path, monkeypatch, language)
    source_language = 'simp_chinese' if language == 'english' else 'english'
    source = Path(item['mod_root'])
    if language == 'english':
        source = tmp_path / 'english-source'
        item['mod_root'] = str(source)
        item['input'] = str(source / 'localization')
        write(source / 'localization/english/kept_l_english.yml', 'english', {'kept': 'Existing'})
    write(source / f'localization/{source_language}/input_l_{source_language}.yml', source_language,
          {'kept': 'The council approved an old law', 'added': 'The council approved a new law'})
    app._ensure_item_cache = lambda item: str(tmp_path / 'cache.json')
    app._find_previous_cache = lambda *args, **kwargs: None
    app.repair_var = SimpleNamespace(get=lambda: False)
    app._translation_status_missing_for_item = types.MethodType(main.App._translation_status_missing_for_item, app)
    prepared = main.App._prepare_differential_cache(app, item)
    assert prepared is not None
    assert prepared['missing']['source_language'] == source_language
    assert prepared['missing']['selected_keys'] == ['added']


@pytest.mark.parametrize('language', ['korean', 'russian', 'german', 'english'])
def test_preferred_conflict_uses_linked_target_language(tmp_path, language):
    linked = tmp_path / 'linked'
    conflict = dict(path=str(linked), effective=True, stale_translation_candidate=False)
    app = SimpleNamespace(_source_overwrite_path_conflicts=lambda item: [conflict])
    preferred, conflicts = main.App._preferred_later_translation_conflict(app,
        dict(target_lang=language, external_translation_path=str(linked)))
    assert conflicts == [conflict]
    assert preferred == (None if language == 'english' else conflict)


class InlineThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        self.target()


def interactive_state(monkeypatch):
    app = state()
    app.single_overwrite_thread = None
    app.bulk_overwrite_thread = None
    app.events = queue.Queue()
    app.progress_text = SimpleNamespace(set=lambda text: None)
    app._refresh_operation_states = lambda: None
    app._invalidate_status_cache_for_item = lambda item: None
    app._preferred_later_translation_conflict = lambda item: (None, [])
    for name in ('_queue_item_is_completed', '_set_overwritten_status', '_perform_external_gap_overwrite',
                 '_perform_source_mod_overwrite', '_merge_missing_only_output'):
        setattr(app, name, types.MethodType(getattr(main.App, name), app))
    monkeypatch.setattr(main.threading, 'Thread', InlineThread)
    monkeypatch.setattr(main.messagebox, 'askyesno', lambda *args, **kwargs: True)
    monkeypatch.setattr(main.messagebox, 'showinfo', lambda *args, **kwargs: None)
    return app


def test_differential_worker_queues_a_sparse_missing_only_input(tmp_path, monkeypatch):
    _app, item, _existing = setup(tmp_path, monkeypatch, 'korean')
    app = interactive_state(monkeypatch)
    monkeypatch.setattr(main, 'WORK_STATE_ROOT', tmp_path / 'work')
    app.worker = None
    app.chinese_worker = None
    app.differential_prepare_thread = None
    app.repair_var = SimpleNamespace(get=lambda: False)
    app._ensure_item_cache = lambda item: str(tmp_path / 'cache.json')
    app._find_previous_cache = lambda *args, **kwargs: None
    for name in ('_prepare_differential_cache', '_translation_status_missing_for_item', '_write_missing_source_subset'):
        setattr(app, name, types.MethodType(getattr(main.App, name), app))
    source = Path(item['mod_root']) / 'localization/english/source_l_english.yml'
    write(source, 'english', {'kept': 'The council approved an old law', 'added': 'The council approved a new law'})
    main.App._start_differential_prepare(app, [(0, item)])
    assert item.get('missing_only') is True
    assert item['missing_keys'] == ['added']
    assert item['mod_localization'] == str(Path(item['mod_root']) / 'localization')
    values = {}
    for path in Path(item['input']).rglob('*.yml'):
        values.update(main.core.parse_localization_file(path)[1])
    assert values == {'added': 'The council approved a new law'}


@pytest.mark.parametrize('language', ['korean', 'russian', 'german', 'english'])
def test_single_overwrite_offers_only_supported_destinations(tmp_path, monkeypatch, language):
    _app, item, existing = setup(tmp_path, monkeypatch, language)
    app = interactive_state(monkeypatch)
    item['status'] = '完了'
    offers = []

    def choose(*args, **kwargs):
        offers.append(args)
        return True

    monkeypatch.setattr(main.messagebox, 'askyesnocancel', choose)
    before = existing.read_bytes()
    assert main.App._overwrite_single_item_interactive(app, item)
    event, (_item, ok, reason, _label) = app.events.get_nowait()
    assert event == 'single_overwrite_done' and ok, reason
    assert bool(offers) == (language != 'english')
    assert existing.read_bytes() == before
    if language == 'english':
        target = Path(item['mod_root']) / 'localization/english/source_l_english.yml'
        assert main.core.parse_localization_file(target)[1]['ignored'] == 'Ignore'
    else:
        patch = existing.parent / f'paradox_localization_translator_missing_l_{language}.yml'
        assert main.core.parse_localization_file(patch)[1] == {'added': 'Translated'}


@pytest.mark.parametrize('queue_kind', ['normal', 'chinese'])
def test_bulk_mixed_targets_never_write_to_english_external_mod(tmp_path, monkeypatch, queue_kind):
    app = interactive_state(monkeypatch)
    monkeypatch.setattr(main.messagebox, 'askyesnocancel', lambda *args, **kwargs: True)
    entries = []
    existing_files = []
    for index, language in enumerate(('korean', 'english', 'russian')):
        _state, item, existing = setup(tmp_path / language, monkeypatch, language)
        item['status'] = '完了'
        entries.append((index, item))
        existing_files.append((existing, existing.read_bytes()))
    monkeypatch.setattr(main, 'BACKUP_ROOT', tmp_path / 'backups')
    main.App._bulk_overwrite_queue_entries(app, entries, queue_kind=queue_kind)
    events = []
    while not app.events.empty():
        events.append(app.events.get_nowait())
    completed = next(payload for event, payload in events if event == 'bulk_overwrite_done')
    assert completed[:3] == (3, 0, 0)
    assert all(path.read_bytes() == before for path, before in existing_files)
    english_source = Path(entries[1][1]['mod_root']) / 'localization/english/source_l_english.yml'
    assert main.core.parse_localization_file(english_source)[1]['ignored'] == 'Ignore'


@pytest.mark.parametrize('bulk', [False, True])
def test_interactive_unsupported_language_never_writes(tmp_path, monkeypatch, bulk):
    _app, item, existing = setup(tmp_path, monkeypatch, 'korean')
    app = interactive_state(monkeypatch)
    item.update(status='完了', game='Europa Universalis IV')
    monkeypatch.setattr(main.messagebox, 'askyesnocancel', lambda *args, **kwargs: True)
    before = existing.read_bytes()
    if bulk:
        main.App._bulk_overwrite_queue_entries(app, [(0, item)])
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        completed = next(payload for event, payload in events if event == 'bulk_overwrite_done')
        assert completed[:3] == (0, 1, 0)
    else:
        assert not main.App._overwrite_single_item_interactive(app, item)
    assert existing.read_bytes() == before
    assert not (tmp_path / 'backups').exists()


@pytest.mark.parametrize('language', ['french', 'spanish', 'polish', 'braz_por', 'simp_chinese', 'turkish'])
def test_other_supported_target_gap_layout(tmp_path, monkeypatch, language):
    app, item, existing = setup(tmp_path, monkeypatch, language)
    item['game'] = 'Victoria 3'
    before = existing.read_bytes()
    ok, reason = main.App._perform_external_gap_overwrite(app, item, False, False)
    assert ok, reason
    assert existing.read_bytes() == before
    patch = existing.parent / f'paradox_localization_translator_missing_l_{language}.yml'
    header, entries, _ = main.core.parse_localization_file(patch)
    assert header == language and entries == {'added': 'Translated'}


@pytest.mark.parametrize('operation', ['gap', 'missing', 'full', 'source'])
def test_japanese_matches_dc13312(tmp_path, monkeypatch, operation):
    baseline = subprocess.run(['git', 'show', 'dc13312:app/main.py'], capture_output=True, text=True, timeout=15)
    if baseline.returncode:
        pytest.skip('dc13312:app/main.py unavailable')
    tree = ast.parse(baseline.stdout)
    old_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'App')
    methods = {node.name: node for node in old_class.body if isinstance(node, ast.FunctionDef)}
    method_name = {'gap': '_perform_external_gap_overwrite', 'missing': '_merge_missing_only_output',
                   'full': '_perform_full_translation_mod_overwrite', 'source': '_perform_source_mod_overwrite'}[operation]
    results = []
    for label in ('old', 'new'):
        root = tmp_path / label
        app, item, existing = setup(root, monkeypatch, 'japanese')
        if label == 'old':
            namespace = dict(vars(main))
            for name in ('_create_full_localization_snapshot', '_backup_game_name_for_root',
                         '_safe_backup_mod_token', '_next_overwrite_backup_generation',
                         '_backup_manifest_records', '_generated_japanese_files',
                         '_source_overwrite_layout', method_name):
                if name in methods:
                    exec(compile(ast.Module(body=[methods[name]], type_ignores=[]), '<dc13312>', 'exec'), namespace)
                    setattr(app, name, types.MethodType(namespace[name], app))
        else:
            setattr(app, method_name, types.MethodType(getattr(main.App, method_name), app))
        if operation == 'missing':
            ok, reason = getattr(app, method_name)(item, existing.parents[1], existing.parents[2], False, False)
        elif operation == 'full':
            ok, reason = getattr(app, method_name)(item,
                dict(path=item['external_translation_path'], localization=item['external_translation_localization']), False, False)
        else:
            ok, reason = getattr(app, method_name)(item, False, False)
        assert ok, reason
        files = {str(path.relative_to(root)): path.read_bytes() for folder in ('source', 'translation')
                 for path in (root / folder).rglob('*.yml')}
        manifest_path = next((root / 'backups').rglob('backup_manifest.json'))
        backup = {str(path.relative_to(manifest_path.parent)): path.read_bytes()
                  for path in manifest_path.parent.rglob('*.yml')}
        manifest = json.loads(manifest_path.read_text())
        for key in ('created_at', 'stamp', 'timestamp'):
            manifest.pop(key, None)
        manifest = str(manifest).replace(str(root), '<root>')
        results.append((files, backup, manifest))
    assert results[0] == results[1]
