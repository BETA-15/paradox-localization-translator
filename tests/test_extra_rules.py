"""A2: prompt/cache identity and job-frozen additional instructions; no Tk roots."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import translator_core as core

LANGUAGES = [('japanese', False), ('english', False), ('korean', False),
             ('simp_chinese', False), ('german', False), ('korean', True)]

@pytest.mark.parametrize('target,basis', LANGUAGES)
def test_prompt_and_cache_identity_and_suffix(target, basis):
    args = dict(target_lang=target, chinese_basis=basis)
    plain = core.build_system_prompt('english', **args)
    assert core.build_system_prompt('english', extra_rules='', **args) == plain
    assert core.build_system_prompt('english', extra_rules='  \n ', **args) == plain
    prefix = ('利用者の追加指示（厳守事項 1〜2 に反する場合は厳守事項を優先）:' if target == 'japanese'
              else 'Additional user instructions (if they conflict with rules 1-2, rules 1-2 take precedence):')
    assert core.build_system_prompt('english', extra_rules='X', **args) == plain + prefix + '\nX\n'
    assert plain.index('1.') < len(plain)
    keyargs = ('Ollama', 'model', 'General', 'english', 'source')
    key = core.translation_cache_key(*keyargs, target_lang=target)
    assert key == core.translation_cache_key(*keyargs, target_lang=target, extra_rules=' \n ')
    assert key != core.translation_cache_key(*keyargs, target_lang=target, extra_rules='X')


def test_combine_and_limits():
    for a,b,result in [('A','','A'), ('','B','B'), ('A','B','A\nB'), (' ','\n',''), ('A\r\n',' B ','A\nB')]:
        assert core.combine_extra_rules(a,b) == result
    assert core.validate_extra_rules('あ'*2000) == (True, 'あ'*2000)
    assert core.validate_extra_rules('あ'*2001)[0] is False
    assert core.validate_extra_rules(' A\r\nB\rC ') == (True, 'A\nB\nC')
    args = ('Ollama','m','General','english','source')
    assert core.translation_cache_key(*args, extra_rules=core.combine_extra_rules('A','B')) == core.translation_cache_key(*args, extra_rules=core.combine_extra_rules('A\r\n',' B '))
    assert core.translation_cache_key(*args, target_lang='english',extra_rules='X') != core.translation_cache_key(*args,target_lang='german',extra_rules='X')

@pytest.mark.parametrize('cached_rules,expected_calls,expected', [('',1,'新訳'), ('X',0,'保存訳')])
def test_process_file_cache_lookups(tmp_path, monkeypatch, cached_rules, expected_calls, expected):
    src = tmp_path/'s_l_english.yml'; out = tmp_path/'out.yml'
    src.write_text('l_english:\n key:0 "Hello world"\n', encoding='utf-8')
    cache = {core.translation_cache_key('Ollama','m','General','english','Hello world', extra_rules=cached_rules): '保存訳'}
    calls = []
    def translate(*args, **kw):
        calls.append(kw['extra_rules']); return ['新訳']
    monkeypatch.setattr(core,'translate_batch',translate)
    core.process_file(src,out,'url','m','japanese',cache,1,False,extra_rules='X')
    assert calls == ['X']*expected_calls
    assert expected in out.read_text(encoding='utf-8-sig')

@pytest.fixture
def main_module(monkeypatch, tmp_path):
    monkeypatch.setenv('PARADOX_TRANSLATOR_DATA_ROOT', str(tmp_path/'data'))
    import main
    return main


def fake_var(value):
    from types import SimpleNamespace
    box = [value]
    return SimpleNamespace(get=lambda: box[0], set=lambda v: box.__setitem__(0,v))

@pytest.mark.parametrize('active', [True,False])
@pytest.mark.parametrize('worker_thread', [True,False])
def test_settings_snapshot_frozen(main_module, monkeypatch, active, worker_thread):
    from types import SimpleNamespace
    import threading
    m=main_module
    state=SimpleNamespace(controller=object(),worker=SimpleNamespace(is_alive=lambda:active),
                          translation_start_settings={'extra_rules':'X'},extra_rules_var=fake_var('Y'))
    for name in ['provider','url','model','preset','batch','workers','repair','dual','autoqa','glossary_path']:
        setattr(state,name+'_var',fake_var(''))
    if worker_thread:
        monkeypatch.setattr(m.threading,'current_thread',lambda:object())
    assert m.App._settings_dict(state)['extra_rules'] == ('X' if active or worker_thread else 'Y')


def test_editor_rejects_long_text_without_changing_saved_value(main_module, monkeypatch):
    from types import SimpleNamespace
    m=main_module; notices=[]
    monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**kw:notices.append(a))
    state=SimpleNamespace(extra_rules_var=fake_var('old'), _save_llm_preferences=lambda:None)
    assert not m.App._save_global_extra_rules(state,'あ'*2001)
    assert state.extra_rules_var.get() == 'old'
    assert notices
    assert m.App._save_global_extra_rules(state,' A\r\nB ')
    assert state.extra_rules_var.get() == 'A\nB'


def test_job_rules_survive_runtime_changes_and_single_retry(tmp_path, monkeypatch):
    src=tmp_path/'events_l_english.yml';out=tmp_path/'out.yml'
    src.write_text('l_english:\n a:0 "First line"\n b:0 "Second line"\n c:0 "Third line"\n')
    glossary=tmp_path/'terms.json';core.save_json(glossary, {'line':'行'})
    controller=core.TranslationController()
    controller.update_runtime_settings(batch_size=1,workers=1)
    calls=[];keys=[]; original_key=core.translation_cache_key
    def key(*args,**kw):
        assert kw['extra_rules']=='X'
        result=original_key(*args,**kw);keys.append((result,args,kw));return result
    def translate(_url,_model,jobs,*args,**kw):
        calls.append(kw['extra_rules'])
        controller.update_runtime_settings(preset='CK3',glossary_path=str(glossary),extra_rules='Y')
        return [jobs[0]['protected']] if len(calls)==1 else ['翻訳済み']
    monkeypatch.setattr(core,'translate_batch',translate)
    monkeypatch.setattr(core,'translation_cache_key',key)
    cache={}
    result=core.process_file(src,out,'url','m','japanese',cache,1,False,controller=controller,extra_rules='X')
    assert result['failed']==0
    assert calls==['X']*4  # three batches plus the first line's single retry
    assert len(keys)==7  # three initial lookups, three batch writes, one retry
    assert len(cache)==3
    assert set(cache) <= {k for k,_,_ in keys}
    assert any(kw.get('glossary')=={'line':'行'} for _,_,kw in keys)
    assert any(args[2]=='CK3' for _,args,_ in keys)
    assert 'First line' not in out.read_text(encoding='utf-8-sig')


def test_qa_retranslation_and_single_text_receive_rules(tmp_path,monkeypatch):
    src=tmp_path/'s_l_english.yml'; dst=tmp_path/'t_l_japanese.yml'
    src.write_text('l_english:\n key:0 "Hello world"\n');dst.write_text('l_japanese:\n key:0 "Hello world"\n')
    seen=[]
    def translate(_url,_model,jobs,*a,**kw):
        seen.append(kw['extra_rules']);return ['翻訳済み']*len(jobs)
    monkeypatch.setattr(core,'translate_batch',translate)
    result=core.auto_repair_qa_pairs([{'source_file':str(src),'target_file':str(dst)}],backup_root=tmp_path/'backup',extra_rules='X')
    assert core.parse_localization_file(dst)[1]['key']=='翻訳済み'
    assert seen==['X']
    assert core.translate_single_text('url','m','Hello world',extra_rules='X')=='翻訳済み'
    assert seen==['X','X']


@pytest.mark.parametrize('basis', [False,True])
def test_core_job_routes_rules_to_translation_and_qa(tmp_path,monkeypatch,basis):
    language='simp_chinese' if basis else 'english'
    src=tmp_path/f'events_l_{language}.yml'
    src.write_text(f'l_{language}:\n key:0 "'+('你好世界' if basis else 'Hello world')+'"\n')
    seen=[]
    def translate(_url,_model,jobs,*a,**kw):
        seen.append(kw['extra_rules']);return ['翻訳済み']*len(jobs)
    monkeypatch.setattr(core,'translate_batch',translate)
    qa=[];real_qa=core.qa_file_with_auto_repair
    def repair(*a,**kw):
        qa.append(kw['extra_rules']);return real_qa(*a,**kw)
    monkeypatch.setattr(core,'qa_file_with_auto_repair',repair)
    run=core.run_chinese_basis_translation if basis else core.run_translation
    result=run(src,tmp_path/'out',cache_path=tmp_path/'cache.json',extra_rules='X',auto_qa=True)
    assert seen==['X'] and qa==['X']
    assert result.get('failed',0)==0


def test_priority_instruction_is_after_protected_rules():
    for target in ['japanese','english']:
        prompt=core.build_system_prompt('english',target_lang=target,extra_rules='プレースホルダを消して')
        prefix=core.EXTRA_RULES_PREFIX_JA if target=='japanese' else core.EXTRA_RULES_PREFIX_OTHER
        assert prompt.index('@@0@@') < prompt.index(prefix) < prompt.index('プレースホルダを消して')


@pytest.mark.parametrize('kind', ['normal','chinese'])
def test_item_save_validation_lock_and_round_trip(main_module,tmp_path,monkeypatch,kind):
    from types import SimpleNamespace
    m=main_module;item={};saved=[];locked=[False];path=tmp_path/'workspace.json'
    state=SimpleNamespace(_normal_queue_locked=lambda:locked[0],_chinese_queue_locked=lambda:locked[0],
        _refresh_queue_tree=lambda:None,_refresh_chinese_queue_tree=lambda:None,
        _save_workspace_state=lambda reason:m.core.save_json(path,{'queue':[item,{}]}))
    monkeypatch.setattr(m.messagebox,'showinfo',lambda *a,**kw:None)
    assert m.App._save_item_extra_rules(state,item,' A\r\nB ',kind)
    rows=m.core.load_json(path,{})['queue']
    assert rows[0]['extra_rules']=='A\nB'
    assert m.core.combine_extra_rules('',rows[1].get('extra_rules',''))==''
    assert not m.App._save_item_extra_rules(state,item,'a'*2001,kind)
    assert item['extra_rules']=='A\nB'
    locked[0]=True
    assert not m.App._save_item_extra_rules(state,item,'changed',kind)
    assert item['extra_rules']=='A\nB'


def test_apply_does_not_replace_job_rules(main_module,monkeypatch):
    from types import SimpleNamespace
    m=main_module;controller=m.core.TranslationController()
    state=SimpleNamespace(controller=controller,worker=SimpleNamespace(is_alive=lambda:True),
        translation_start_settings={'extra_rules':'X'},extra_rules_var=fake_var('Y'),
        _save_llm_preferences=lambda:None,save_session=lambda **kw:None)
    for name,value in {'provider':'Ollama','url':'url','model':'m','api_key':'','preset':'General',
                       'batch':1,'workers':1,'glossary_path':'','dual':False}.items():
        setattr(state,name+'_var',fake_var(value))
    assert m.App.apply_translation_settings_everywhere(state,silent=True)
    assert state.translation_start_settings['extra_rules']=='X'
    assert 'extra_rules' not in controller.get_runtime_settings()


def test_preferences_save_global_rules(main_module,monkeypatch,tmp_path):
    from types import SimpleNamespace
    m=main_module;path=tmp_path/'prefs.json';monkeypatch.setattr(m,'APP_PREFS_PATH',path)
    state=SimpleNamespace(app_preferences={},extra_rules_var=fake_var('A\nB'))
    for name,value in {'provider':'Ollama','url':'','model':'m','batch':1,'workers':1,'chinese_autoqa':True,
                       'monitor_provider':'Ollama','monitor_url':'','monitor_model':'','close_action':'毎回確認'}.items():
        setattr(state,name+'_var',fake_var(value))
    m.App._save_llm_preferences(state)
    assert m.core.load_json(path,{})['translation_llm']['extra_rules']=='A\nB'


def test_session_restore_global_and_item_rules(main_module):
    from types import SimpleNamespace
    m=main_module
    state=SimpleNamespace(_ensure_item_cache=lambda i:None,_write_session_file=lambda **kw:None,
        _refresh_queue_tree=lambda:None,_save_workspace_state=lambda *a:None,progress_text=fake_var(''))
    for name in ['provider','url','model','preset','extra_rules','normalize_spacing','batch','workers','repair','dual','autoqa','glossary_path']:
        setattr(state,name+'_var',fake_var(''))
    item={'extra_rules':'B'}
    m.App.restore_session(state,{'settings':{'extra_rules':'A'},'queue':[item,{}]})
    assert state.extra_rules_var.get()=='A'
    assert state.queue_items==[item,{}]
    # User edits after stopping: the next session snapshot uses the edit.
    state.extra_rules_var.set('Y')
    assert m.App._settings_dict(state)['extra_rules']=='Y'


def test_diff_and_manual_qa_use_global_only(main_module,monkeypatch,tmp_path):
    from types import SimpleNamespace
    import queue
    m=main_module;src=tmp_path/'s_l_english.yml';dst=tmp_path/'t_l_japanese.yml'
    src.write_text('l_english:\n key:0 "Hello world"\n');dst.write_text('l_japanese:\n')
    seen=[]
    def translate(*a,**kw):
        seen.append(kw['extra_rules']);return '翻訳済み'
    monkeypatch.setattr(m.core,'translate_single_text',translate)
    state=SimpleNamespace(_closing=False,diff_controller=None,diff_batch_contexts=[],
        diff_rows=[{'key':'key','status':'missing','source':'Hello world'}],
        diff_source_lang='english',diff_source_entries={'key':'Hello world'},diff_target_entries={},
        diff_src_var=fake_var(str(src)),diff_dst_var=fake_var(str(dst)),diff_message_var=fake_var(''),
        target_lang_var=fake_var('japanese'),events=queue.Queue(),extra_rules_var=fake_var('Global'),
        _backup_before_diff_write=lambda paths:[],_invalidate_status_after_diff_write=lambda paths:None)
    for name,value in {'glossary_path':'','url':'url','model':'m','preset':'General','provider':'Ollama','api_key':''}.items():
        setattr(state,name+'_var',fake_var(value))
    m.App.translate_diff_items(state,all_missing=True,_llm_ready=True)
    state.diff_translate_thread.join(5)
    assert not state.diff_translate_thread.is_alive()
    assert seen==['Global']
    assert '翻訳済み' in dst.read_text(encoding='utf-8-sig')
    # QA tab captures the UI value before its worker starts.
    qa=[]
    def repair(*a,**kw):
        qa.append(kw['extra_rules']);return {}
    monkeypatch.setattr(m.core,'auto_repair_qa_pairs',repair)
    monkeypatch.setattr(m.messagebox,'askyesno',lambda *a,**kw:True)
    state.worker=None;state.chinese_worker=None;state.proofread_thread=None;state.auto_glossary_thread=None
    state.llm_busy_count=0
    state._operation_pending=lambda thread:False
    state.qa_repair_thread=None;state._qa_repair_busy=lambda:False
    state._active_file_operation_names=lambda:[]
    state.qa_summary_var=fake_var('');state._refresh_operation_states=lambda:None
    m.App._start_manual_qa_repair(state,[{'source_file':str(src),'target_file':str(dst)}],origin='review',_llm_ready=True)
    state.qa_repair_thread.join(5)
    assert not state.qa_repair_thread.is_alive()
    assert qa==['Global']


# ce58b8b（A2 の前の main）の値の SHA-256。git の履歴が無い浅い clone（CI）でも比べられるように、
# 履歴を読まずに固定の値で持つ。日本語の文・指示文・キャッシュのキーを意図して変えたときだけ更新する。
BASELINE_JAPANESE_STRINGS_SHA256 = 'e681565a788625dc5da11fd15661d75d81e61183c8eae3f26d9d2969e2b24cec'  # 2101 key
BASELINE_PROMPTS_AND_KEYS_SHA256 = '13312485ca8b500c38b2ff08532235357599f7eb9f0b6a9ff69e3c739359f6d2'


def test_japanese_dictionary_only_adds_six_specified_values():
    import ast
    import hashlib
    import json
    root=Path(__file__).resolve().parents[1]
    expected={
        'u5.extra_rules_global':'追加の翻訳指示（全体）',
        'u5.extra_rules_example':'例：です・ます調にしない／軍の階級は旧日本軍の呼び方にする',
        'u5.extra_rules_cache_note':'指示を変えると、その項目のキャッシュは使われません（訳し直しになります）。',
        'u5.extra_rules_too_long':'追加の翻訳指示は {limit} 字までです（今 {count} 字）。保存していません。',
        'u1.extra_rules_item_button':'追加指示…', 'u1.extra_rules_item_title':'この項目の追加指示',
    }
    def strings(source):
        for n in ast.parse(source).body:
            if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='STRINGS' for t in n.targets):
                return ast.literal_eval(n.value)
        return {}
    new={}
    for p in sorted((root/'app/i18n/japanese').glob('*.py')):
        new.update(strings(p.read_text()))
    assert {k:new.get(k) for k in expected}==expected
    old={k:v for k,v in new.items() if k not in expected}
    digest=hashlib.sha256(json.dumps(old,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    assert digest==BASELINE_JAPANESE_STRINGS_SHA256


def test_empty_prompts_and_keys_are_byte_identical_to_baseline():
    import hashlib
    h=hashlib.sha256()
    for lang,basis in LANGUAGES:
        for glossary in [None,{'Duke':'公爵'}]:
            h.update(core.build_system_prompt('english',extra_rules='',glossary=glossary,target_lang=lang,chinese_basis=basis).encode()+b'\0')
        h.update(core.translation_cache_key('Ollama','m','General','english','Hello world',target_lang=lang,extra_rules='').encode()+b'\0')
    assert h.hexdigest()==BASELINE_PROMPTS_AND_KEYS_SHA256


@pytest.mark.parametrize('kind',['normal','chinese'])
def test_queue_routes_without_tk(main_module,tmp_path,monkeypatch,kind):
    from types import SimpleNamespace
    import queue
    m=main_module
    widget=lambda:SimpleNamespace(config=lambda **kw:None,delete=lambda *a:None)
    # Defer worker execution until after changing the UI, deterministically.
    class DeferredThread:
        def __init__(self,target,**kw): self.target=target
        def start(self): pass
        def is_alive(self): return True
    monkeypatch.setattr(m.threading,'Thread',DeferredThread)
    monkeypatch.setattr(m,'UNATTENDED_LOG_ROOT',tmp_path/'reports')
    item={'input':str(tmp_path/'input'),'output':str(tmp_path/'out'),
          'cache':str(tmp_path/'cache.json'),'extra_rules':'Item','target_lang':'japanese'}
    state=SimpleNamespace(_closing=False,worker=None,chinese_worker=None,queue_items=[item],chinese_queue_items=[item],
        events=queue.Queue(),progress={},chinese_progress={},chinese_progress_var=fake_var(''),
        chinese_log=widget(),extra_rules_var=fake_var('Global'),
        chinese_output_var=fake_var(str(tmp_path/'out')),
        start_btn=widget(),pause_btn=widget(),stop_btn=widget(),
        chinese_start_btn=widget(),chinese_pause_btn=widget(),chinese_stop_btn=widget(),
        _ensure_isolated_item_output=lambda *a,**kw:None,_refresh_queue_tree=lambda:None,
        _refresh_chinese_queue_tree=lambda:None,_refresh_operation_states=lambda:None,
        _clear_log=lambda:None,_append_log=lambda *a:None,_checkpoint=lambda *a:None,
        save_session=lambda **kw:None,_write_session_file=lambda **kw:None,
        _ensure_item_cache=lambda item:Path(item['cache']),_register_cache_job=lambda *a,**kw:None,
        _item_has_remaining_translation_gap=lambda item:False)
    for name,value in {'provider':'Ollama','url':'url','model':'m','api_key':'','preset':'General',
                       'batch':1,'workers':1,'glossary_path':'','repair':True,'autoqa':False,'chinese_autoqa':False}.items():
        setattr(state,name+'_var',SimpleNamespace(get=lambda v=value:v))
    seen=[]
    def run(*a,**kw):seen.append(kw['extra_rules']);return {}
    if kind=='normal':
        monkeypatch.setattr(m.core,'run_translation',run)
        state._queue_worker=lambda:m.App._queue_worker(state)
        m.App._start_normal_selected(state,[0],_llm_ready=True)
        state.extra_rules_var.set('Changed')
        state.worker.target()
        reports=list((tmp_path/'reports').glob('*.json'))
        assert len(reports)==1
        report=m.core.load_json(reports[0],{})
        assert report['items'][0]['extra_rules_present'] is True
        assert report['items'][0]['extra_rules_hash']==m.core.text_hash('Global\nItem')
        assert 'Global' not in reports[0].read_text() and 'Item' not in reports[0].read_text()
    else:
        monkeypatch.setattr(m.core,'run_chinese_basis_translation',run)
        m.App._start_chinese_selected(state,[0],_llm_ready=True)
        state.extra_rules_var.set('Changed')
        state.chinese_worker.target()
    assert seen==['Global\nItem']



def test_workspace_round_trip_preserves_global_and_both_item_fields(main_module,monkeypatch,tmp_path):
    from types import SimpleNamespace
    m=main_module
    state=SimpleNamespace(queue_items=[{'extra_rules':'Normal'},{}],chinese_queue_items=[{'extra_rules':'Chinese'},{}],
        current_queue_index=0,chinese_queue_index=0,monitor_target_paths=[],search_selected_mod_paths=[],
        notebook=SimpleNamespace(select=lambda *a:None,index=lambda *a:0),
        _workspace_scalar=m.App._workspace_scalar,_workspace_selected_paths=lambda:[],
        _refresh_queue_tree=lambda:None,_refresh_chinese_queue_tree=lambda:None,
        _select_chinese_target_language=lambda:None,_set_target_lang=lambda *a,**kw:None,
        after_idle=lambda *a:None,refresh_translation_search_mods=lambda:None)
    variables=('normal_input normal_output chinese_target_lang chinese_target_display chinese_input chinese_output '
               'review_src review_dst diff_src diff_dst glossary_path provider url model preset target_lang batch workers '
               'performance_preset repair extra_rules normalize_spacing dual autoqa chinese_autoqa profile '
               'monitor_interval monitor_use_llm monitor_check_translation_mods monitor_provider monitor_url monitor_model '
               'monitor_path discovery_multi_select mod_status_search search_game search_query')
    for name in variables.split():setattr(state,name+'_var',fake_var(''))
    for name,value in {'extra_rules':'Global','batch':40,'workers':1,'monitor_interval':15}.items():
        getattr(state,name+'_var').set(value)
    data=m.App._collect_workspace_state(state)
    assert data['models']['extra_rules']=='Global'
    path=tmp_path/'workspace.json';m.core.save_json(path,data)
    monkeypatch.setattr(m,'WORKSPACE_STATE_PATH',path)
    def error(*a):raise AssertionError(a)
    monkeypatch.setattr(m,'record_error',error)
    state.extra_rules_var.set('Changed');state.queue_items=[];state.chinese_queue_items=[]
    m.App._restore_workspace_state(state)
    assert state.extra_rules_var.get()=='Global'
    assert state.queue_items==[{'extra_rules':'Normal'},{}]
    assert state.chinese_queue_items==[{'extra_rules':'Chinese'},{}]
