import json

import pytest

from app import translator_core as core


@pytest.mark.parametrize('terms,text,prompt,qa,meta', [
    (['Duke'], 'the Dukes of X', ['Duke'], ['Duke'], {}),
    (['Duke'], "the Duke's army", ['Duke'], ['Duke'], {}),
    (['Duke'], 'the Duke’s army', ['Duke'], ['Duke'], {}),
    (['Duke'], 'Dukedom', [], [], {}),
    (['Duke'], 'the duke', ['Duke'], [], {}),
    (['A.O.G.'], 'A.O.G. troops', ['A.O.G.'], ['A.O.G.'], {'A.O.G.': {'case_sensitive': True}}),
    (['A.O.G.'], 'a.o.g. troops', [], [], {'A.O.G.': {'case_sensitive': True}}),
    (['AOG'], 'aog', ['AOG'], [], {'AOG': {'case_sensitive': False}}),
    (['-aligned'], 'pro-aligned', ['-aligned'], ['-aligned'], {}),
    (['Grand Duke', 'Duke'], 'Grand Duke of X', ['Grand Duke'], ['Grand Duke'], {}),
    (['Grand Duke', 'Duke'], 'Grand Duke and the Duke', ['Grand Duke', 'Duke'], ['Grand Duke', 'Duke'], {}),
    (['节度使'], '设立节度使府', ['节度使'], ['节度使'], {}),
    (['Box'], 'Boxes', ['Box'], ['Box'], {}),
    (['Grand Duke', 'Duke'], 'Grand Dukes of X', ['Grand Duke'], ['Grand Duke'], {}),
    (['AI'], 'AI系统', ['AI'], ['AI'], {}),
])
def test_fixed_examples(terms, text, prompt, qa, meta):
    glossary = {term: f'訳{i}' for i, term in enumerate(terms)}
    assert core.match_glossary_terms(glossary, text, fold_case=True, term_meta=meta) == prompt
    assert core.match_glossary_terms(glossary, text, fold_case=False, term_meta=meta) == qa
    assert core.glossary_for_prompt(glossary, [text], term_meta=meta) == [(term, glossary[term]) for term in prompt]
    issues = core.qa_entries({'k': '仮訳'}, {'k': text}, glossary=glossary, term_meta=meta)
    assert [i['source_term'] for i in issues if i['rule_id'] == 'QA-TERM-001'] == qa


@pytest.mark.parametrize('count', [0, 5, 80, 85])
def test_prompt_selects_longest_then_restores_glossary_order(count):
    glossary = {f'Term{i:03d}' + ('x' * (i % 7)): str(i) for i in range(count)}
    text = ' / '.join(glossary)
    hits = core.match_glossary_terms(glossary, text, fold_case=True)
    chosen = set(sorted(hits, key=len, reverse=True)[:80])
    selected = core.glossary_for_prompt(glossary, [text])
    assert selected == [(term, glossary[term]) for term in glossary if term in chosen]
    if count <= 80:
        assert {term for term, _ in selected} == set(hits)


@pytest.mark.parametrize('term,text,expected', [
    ('AI', 'xAI AI2', []), ('F16', 'F160 AF16', []), ('F16', 'F16系统', ['F16']),
    ('A.O.G.', 'XA.O.G.', []), ('a+b', 'a+b', ['a+b']),
    ('s', 'ſ', []), ('', 'anything', []),
])
def test_boundaries_escaping_and_substring_prefilter(term, text, expected):
    assert core.match_glossary_terms({term: '訳'}, text, fold_case=True) == expected


def test_matching_reflects_mutated_glossary_and_metadata():
    glossary = {'Duke': '公爵'}
    meta = {'Duke': {'case_sensitive': 'true'}}
    assert core.match_glossary_terms(glossary, 'duke', fold_case=True, term_meta=meta) == ['Duke']
    meta['Duke']['case_sensitive'] = True
    assert core.match_glossary_terms(glossary, 'duke', fold_case=True, term_meta=meta) == []
    glossary['Box'] = '箱'
    assert core.match_glossary_terms(glossary, 'Boxes', fold_case=False) == ['Box']


@pytest.mark.parametrize('content', [None, '{broken', '[]', 'null', '{"Duke":{"case_sensitive":true}}'])
def test_load_term_metadata(tmp_path, content):
    path = tmp_path / 'glossary.json'
    if content is not None:
        core.glossary_variants_path(path).write_text(content, encoding='utf-8')
    expected = {'Duke': {'case_sensitive': True}} if content and 'Duke' in content else {}
    assert core.load_glossary_term_meta(path) == expected


def test_qa_and_bulk_unify_attempt_same_terms(tmp_path):
    glossary = {'Duke': '公爵', 'Grand Duke': '大公', 'Box': '箱', 'AOG': '組織', '节度使': '節度使'}
    rows = ['Grand Dukes of X', 'Grand Duke and the Duke', 'Dukedom', 'Boxes', 'aog', '设立节度使府']
    source = tmp_path / 'sample_l_english.yml'
    target = tmp_path / 'sample_l_japanese.yml'
    path = tmp_path / 'glossary.json'
    path.write_text(json.dumps(glossary), encoding='utf-8')
    # Each variant identifies a term that bulk unification actually attempted.
    meta = {term: {'variants': [f'旧訳{i}終']} for i, term in enumerate(glossary)}
    core.glossary_variants_path(path).write_text(json.dumps(meta), encoding='utf-8')
    value = ' '.join(info['variants'][0] for info in meta.values())
    sources = {f'k{i}': text for i, text in enumerate(rows)}
    targets = {key: value for key in sources}
    source.write_text('l_english:\n' + ''.join(f' {key}:0 "{text}"\n' for key, text in sources.items()), encoding='utf-8')
    target.write_text('l_japanese:\n' + ''.join(f' {key}:0 "{text}"\n' for key, text in targets.items()), encoding='utf-8')
    issues = core.qa_entries(targets, sources, glossary=glossary, term_meta=meta)
    qa_terms = {(i['key'], i['source_term']) for i in issues if i['rule_id'] == 'QA-TERM-001'}
    core.bulk_unify_qa_terms(target, source, path)
    _, updated, _ = core.parse_localization_file(target)
    attempted = {(key, term) for key, text in updated.items() for term, info in meta.items()
                 if info['variants'][0] not in text}
    assert attempted == qa_terms
    assert attempted == {('k0', 'Grand Duke'), ('k1', 'Grand Duke'), ('k1', 'Duke'), ('k3', 'Box'), ('k5', '节度使')}


def test_runtime_reload_updates_glossary_and_case_metadata_together(tmp_path, monkeypatch):
    source = tmp_path / 'sample_l_english.yml'
    target = tmp_path / 'sample_l_japanese.yml'
    path = tmp_path / 'glossary.json'
    source.write_text('l_english:\n a:0 "the aog council"\n b:0 "the aog army"\n', encoding='utf-8')
    path.write_text(json.dumps({'AOG': '組織'}), encoding='utf-8')
    meta_path = core.glossary_variants_path(path)
    meta_path.write_text('{}', encoding='utf-8')
    controller = core.TranslationController()
    controller.update_runtime_settings(glossary_path=str(path))
    prompts = []

    def llm(provider, url, model, user, system, **kwargs):
        prompts.append(system)
        # The next batch must observe both files changing at the boundary.
        path.write_text(json.dumps({'AOG': '別組織'}), encoding='utf-8')
        meta_path.write_text(json.dumps({'AOG': {'case_sensitive': True}}), encoding='utf-8')
        return '0' + core.BATCH_LINE_SEP + '組織の訳文'

    monkeypatch.setattr(core, 'call_llm_raw', llm)
    result = core.process_file(source, target, 'unused', 'fake', 'japanese', {}, 1, False,
                               batch_size=1, controller=controller)
    assert result['failed'] == 0
    assert len(prompts) == 2
    assert prompts[0] == core.build_system_prompt('english', {'AOG': '組織'}, 'General', False, False)
    assert prompts[1] == core.build_system_prompt('english', {}, 'General', False, False)


@pytest.mark.parametrize('chinese_basis', [False, True])
@pytest.mark.parametrize('case_sensitive', [False, True])
def test_translation_entry_points_load_case_metadata(tmp_path, monkeypatch, chinese_basis, case_sensitive):
    language = 'simp_chinese' if chinese_basis else 'english'
    source = tmp_path / f'sample_l_{language}.yml'
    source.write_text(f'l_{language}:\n a:0 "the aog council"\n', encoding='utf-8')
    path = tmp_path / 'glossary.json'
    path.write_text(json.dumps({'AOG': '組織'}), encoding='utf-8')
    core.glossary_variants_path(path).write_text(
        json.dumps({'AOG': {'case_sensitive': case_sensitive}}), encoding='utf-8')
    prompts = []

    def llm(provider, url, model, user, system, **kwargs):
        prompts.append(system)
        return '0' + core.BATCH_LINE_SEP + '組織の訳文'

    monkeypatch.setattr(core, 'call_llm_raw', llm)
    run = core.run_chinese_basis_translation if chinese_basis else core.run_translation
    run(source, tmp_path / 'out', glossary_path=path, auto_qa=True)
    selected = {} if case_sensitive else {'AOG': '組織'}
    assert prompts == [core.build_system_prompt(language, selected, 'General', False, chinese_basis)]


@pytest.mark.parametrize('target_lang', ['japanese', 'korean'])
def test_auto_repair_pairs_pass_matching_case_metadata(tmp_path, monkeypatch, target_lang):
    source = tmp_path / 'sample_l_english.yml'
    target = tmp_path / f'sample_l_{target_lang}.yml'
    source.write_text('l_english:\n a:0 "the aog council"\n', encoding='utf-8')
    translated = "評議会" if target_lang == "japanese" else "평의회"
    target.write_text(f'l_{target_lang}:\n a:0 "{translated}"\n', encoding='utf-8')
    base_path = tmp_path / 'glossary.json'
    path = base_path if target_lang == 'japanese' else core.glossary_path_for_language(base_path, target_lang)
    path.write_text(json.dumps({'AOG': '組織'}), encoding='utf-8')
    metadata = {'AOG': {'case_sensitive': True}}
    core.glossary_variants_path(path).write_text(json.dumps(metadata), encoding='utf-8')
    repair = core.qa_file_with_auto_repair
    received = []

    def inspect_metadata(*args, **kwargs):
        received.append(kwargs.get('term_meta'))
        return repair(*args, **kwargs)

    def unexpected_translation(*args, **kwargs):
        pytest.fail('translate_batch called without repairable errors')

    monkeypatch.setattr(core, 'qa_file_with_auto_repair', inspect_metadata)
    monkeypatch.setattr(core, 'translate_batch', unexpected_translation)
    result = core.auto_repair_qa_pairs(
        [{'source_file': str(source), 'target_file': str(target), 'target_language': target_lang}],
        glossary_path=base_path, backup_root=tmp_path / 'backups')
    assert received == [metadata]
    assert len(result['files']) == 1
    assert result['files'][0]['initial_errors'] == 0
    assert not [issue for issue in result['files'][0]['issues'] if issue['rule_id'] == 'QA-TERM-001']
