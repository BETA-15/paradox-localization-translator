from pathlib import Path
from types import SimpleNamespace

import pytest

import main
from test_overwrite_languages import setup, write


def differential_state(item):
    app = SimpleNamespace(
        repair_var=SimpleNamespace(get=lambda: False),
        _ensure_item_cache=lambda row: row['cache'],
        _infer_mod_target_for_item=lambda row: (Path(row['input']), Path(row['mod_root'])),
        _source_id=lambda path: str(path.resolve()),
    )
    for name in ('_find_previous_cache', '_translation_status_missing_for_item'):
        setattr(app, name, getattr(main.App, name).__get__(app))
    return app


@pytest.mark.parametrize('language,mode', [('french', 'normal'), ('english', 'normal'), ('korean', 'chinese')])
@pytest.mark.parametrize('legacy', [False, True])
def test_changed_source_uses_only_same_language_manifest(tmp_path, monkeypatch, language, mode, legacy):
    source_language = 'simp_chinese' if language == 'english' or mode == 'chinese' else 'english'
    root = tmp_path / 'source'
    source = root / f'localization/{source_language}/source_l_{source_language}.yml'
    write(source, source_language, {'changed': 'The old source text'})
    caches = tmp_path / 'caches'
    monkeypatch.setattr(main, 'CACHE_ROOT', caches)
    rows = []
    for target in (language, 'german'):
        cache = caches / target / main.core.CACHE_FILE_NAME
        main.core.save_json(cache, {'old': 'translation'})
        manifest = (main.core.build_source_manifest_for_language(source.parent.parent, 'simp_chinese')
                    if mode == 'chinese' else main.core.build_source_manifest(source.parent.parent, target))
        output = tmp_path / f'output_{target}'
        write(output / f'source_l_{target}.yml', target, {'changed': 'Translated text'})
        if not legacy:
            manifest['target_lang'] = target
        main.core.save_source_manifest(cache, manifest)
        row = {'cache': str(cache), 'mode': mode, 'output': str(output)}
        if not legacy:
            row['target_lang'] = target
        rows.append(row)
    write(source, source_language, {'changed': 'The new source text'})
    current = caches / 'current' / main.core.CACHE_FILE_NAME
    current.parent.mkdir()
    item = dict(input=str(source.parent.parent), mod_root=str(root), target_lang=language,
                cache=str(current), output=str(tmp_path / 'new_output'))
    app = differential_state(item)
    app._load_cache_registry = lambda: {str(source.parent.parent.resolve()): rows}
    app._translation_status_missing_for_item = lambda *args: {'count': 0, 'details': []}
    result = main.App._prepare_differential_cache(app, item, mode=mode)
    assert result and result['snapshot_available']
    assert result['counts']['changed'] == 1
    assert item['previous_cache'] == str(caches / language / main.core.CACHE_FILE_NAME)


def test_existing_source_copy_is_a_differential_target(tmp_path, monkeypatch):
    _app, item, existing = setup(tmp_path, monkeypatch, 'french')
    write(Path(item['mod_root']) / 'localization/english/source_l_english.yml', 'english',
          {'kept': 'The council approved the law', 'added': 'The council approved a new law'})
    write(existing, 'french', {'kept': 'The council approved the law'})
    result = main.App._translation_status_missing_for_item(differential_state(item), item, 'english')
    assert 'kept' in result['selected_keys']


@pytest.mark.parametrize('operation', ['gap', 'missing', 'full', 'source'])
@pytest.mark.parametrize('different_filename', [False, True])
def test_overwrite_updates_source_copy_after_backup(tmp_path, monkeypatch, operation, different_filename):
    app, item, existing = setup(tmp_path, monkeypatch, 'french')
    if operation == 'source':
        existing = Path(item['mod_root']) / 'localization/french/source_l_french.yml'
    if different_filename:
        if existing.exists():
            existing.unlink()
        existing = existing.with_name('other_l_french.yml')
    write(existing, 'french', {'kept': 'The council approved the law', 'valid': 'Traduction conservée'})
    write(Path(item['mod_root']) / 'localization/english/source_l_english.yml', 'english',
          {'kept': 'The council approved the law', 'added': 'New', 'valid': 'Valid source'})
    output = Path(item['output']) / 'french/source_l_french.yml'
    write(output, 'french', {'kept': 'Traduction corrigée', 'added': 'Nouvelle traduction', 'valid': 'Do not replace'})
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
    entries = main.core.parse_localization_file(existing)[1]
    assert entries['kept'] == 'Traduction corrigée'
    assert entries['valid'] == 'Traduction conservée'
    manifest = next((tmp_path / 'backups').rglob('backup_manifest.json'))
    assert (manifest.parent / existing.relative_to(existing.parents[2])).read_bytes() == before


@pytest.mark.parametrize('mode', ['normal', 'chinese'])
def test_manifest_recovery_rejects_other_and_unknown_languages(tmp_path, monkeypatch, mode):
    source = tmp_path / 'source'
    source.mkdir()
    caches = tmp_path / 'caches'
    monkeypatch.setattr(main, 'CACHE_ROOT', caches)
    for language in ('french', 'german', None):
        cache = caches / str(language) / main.core.CACHE_FILE_NAME
        main.core.save_json(cache, {})
        manifest = {'input': str(source.resolve()), 'files': {}}
        if language:
            manifest['target_lang'] = language
        if mode == 'chinese':
            manifest['language_filter'] = 'simp_chinese'
        main.core.save_source_manifest(cache, manifest)
    app = differential_state({})
    app._load_cache_registry = lambda: {}
    found = app._find_previous_cache(source, mode=mode, target_lang='french')
    assert found == caches / 'french' / main.core.CACHE_FILE_NAME
    assert app._find_previous_cache(source, mode=mode, target_lang='korean') is None


def test_legacy_shared_output_cannot_identify_cache_language(tmp_path, monkeypatch):
    source = tmp_path / 'source'
    source.mkdir()
    caches = tmp_path / 'caches'
    monkeypatch.setattr(main, 'CACHE_ROOT', caches)
    cache = caches / 'old' / main.core.CACHE_FILE_NAME
    main.core.save_json(cache, {})
    main.core.save_source_manifest(cache, {'input': str(source.resolve()), 'files': {}})
    output = tmp_path / 'shared_japanese'
    for language in ('french', 'german'):
        write(output / f'old_l_{language}.yml', language, {'key': 'Translation'})
    app = differential_state({})
    app._load_cache_registry = lambda: {str(source.resolve()): [{'cache': str(cache), 'output': str(output)}]}
    assert app._find_previous_cache(source, target_lang='french') is None


@pytest.mark.parametrize('language', ['japanese', 'french', 'korean'])
def test_cache_registry_records_target_only_for_non_japanese(tmp_path, language):
    cache = tmp_path / 'cache' / main.core.CACHE_FILE_NAME
    main.core.save_json(cache, {})
    main.core.save_source_manifest(cache, {'files': {}})
    source = tmp_path / 'source'
    item = {'input': str(source), 'cache': str(cache), 'target_lang': language}
    app = differential_state(item)
    registry = {}
    app._load_cache_registry = lambda: registry
    app._save_cache_registry = lambda result: None
    main.App._register_cache_job(app, item)
    row = registry[str(source.resolve())][0]
    if language == 'japanese':
        assert set(row) == {'cache', 'input', 'output', 'mode', 'updated_at'}
    else:
        assert row['target_lang'] == language


@pytest.mark.parametrize('language,mode', [('french', 'normal'), ('korean', 'chinese'), ('japanese', 'normal')])
def test_translation_records_manifest_language_without_changing_japanese(tmp_path, monkeypatch, language, mode):
    source_language = 'simp_chinese' if mode == 'chinese' else 'english'
    source = tmp_path / f'source_l_{source_language}.yml'
    write(source, source_language, {'key': 'The council approved the law'})
    cache = tmp_path / 'cache' / main.core.CACHE_FILE_NAME
    translations = {'french': 'Le conseil a approuvé la loi', 'korean': '의회가 법안을 승인했습니다', 'japanese': '議会は法律を承認しました'}
    monkeypatch.setattr(main.core, 'translate_batch',
                        lambda _url, _model, jobs, *args, **kwargs: [translations[language] for job in jobs])
    translate = main.core.run_chinese_basis_translation if mode == 'chinese' else main.core.run_translation
    translate(source, tmp_path / 'output', target_lang=language, cache_path=cache, auto_qa=False)
    manifest = main.core.load_source_manifest(cache)
    if language == 'japanese':
        assert 'target_lang' not in manifest
    else:
        assert manifest['target_lang'] == language


def test_source_overwrite_keeps_original_snapshot_across_output_files(tmp_path, monkeypatch):
    app, item, _existing = setup(tmp_path, monkeypatch, 'french')
    target = Path(item['mod_root']) / 'localization/french/z_l_french.yml'
    write(Path(item['mod_root']) / 'localization/english/source_l_english.yml', 'english',
          {'kept': 'The council approved the law'})
    write(target, 'french', {'kept': 'The council approved the law'})
    output = Path(item['output']) / 'french'
    write(output / 'source_l_french.yml', 'french', {'kept': 'Le conseil a approuvé la loi'})
    write(output / 'z_l_french.yml', 'french', {'other': 'Une autre traduction'})
    before = target.read_bytes()
    ok, reason = main.App._perform_source_mod_overwrite(app, item, False, False)
    assert ok, reason
    manifest = next((tmp_path / 'backups').rglob('backup_manifest.json'))
    assert (manifest.parent / target.relative_to(Path(item['mod_root']))).read_bytes() == before
    assert main.core.parse_localization_file(target)[1]['kept'] == 'Le conseil a approuvé la loi'
