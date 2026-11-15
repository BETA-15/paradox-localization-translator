"""A2 GUI acceptance, opt-in only. These tests create Tk roots."""
import importlib
import os
import queue
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'app'))
pytestmark=pytest.mark.skipif(os.environ.get('PLT_GUI_TESTS')!='1',reason='Requires PLT_GUI_TESTS=1; creates Tk roots')


@pytest.fixture
def ui(tmp_path,monkeypatch):
    monkeypatch.setenv('PARADOX_TRANSLATOR_DATA_ROOT',str(tmp_path/'data'))
    m=importlib.import_module('main')
    root=m.tk.Tk();root.withdraw()
    try:
        yield m,root
    finally:
        root.destroy()


@pytest.mark.parametrize('kind',['normal','chinese'])
def test_queue_routes_combined_frozen_rules(ui,tmp_path,monkeypatch,kind):
    m,root=ui
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
        events=queue.Queue(),progress={},chinese_progress={},chinese_progress_var=m.tk.StringVar(root),
        chinese_log=m.tk.Text(root),extra_rules_var=m.tk.StringVar(root,value='Global'),
        chinese_output_var=m.tk.StringVar(root,value=str(tmp_path/'out')),
        start_btn=m.ttk.Button(root),pause_btn=m.ttk.Button(root),stop_btn=m.ttk.Button(root),
        chinese_start_btn=m.ttk.Button(root),chinese_pause_btn=m.ttk.Button(root),chinese_stop_btn=m.ttk.Button(root),
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
    else:
        monkeypatch.setattr(m.core,'run_chinese_basis_translation',run)
        m.App._start_chinese_selected(state,[0],_llm_ready=True)
        state.extra_rules_var.set('Changed')
        state.chinese_worker.target()
    assert seen==['Global\nItem']


def test_item_dialog_save_cancel_and_lock(ui,monkeypatch):
    m,root=ui;item={'extra_rules':'Old'};locked=[False];saved=[]
    root._normal_queue_locked=lambda:locked[0]
    root._selected_queue_item=lambda:item
    root._save_item_extra_rules=lambda item,text,kind:(item.update(extra_rules=text) or saved.append(text) or True)
    m.App.edit_item_extra_rules(root)
    win=next(w for w in root.winfo_children() if isinstance(w,m.tk.Toplevel))
    field=next(w for w in win.winfo_children() if isinstance(w,m.tk.Text))
    buttons=[w for frame in win.winfo_children() for w in frame.winfo_children() if isinstance(w,m.ttk.Button)]
    field.delete('1.0','end');field.insert('1.0','New')
    next(b for b in buttons if b.cget('text')==m.i18n.t('u4.save')).invoke()
    assert saved==['New'] and item['extra_rules']=='New'
    m.App.edit_item_extra_rules(root)
    win=next(w for w in root.winfo_children() if isinstance(w,m.tk.Toplevel))
    buttons=[w for frame in win.winfo_children() for w in frame.winfo_children() if isinstance(w,m.ttk.Button)]
    next(b for b in buttons if b.cget('text')==m.i18n.t('p0.cancel')).invoke()
    assert saved==['New']
    locked[0]=True
    m.App.edit_item_extra_rules(root)
    assert not any(isinstance(w,m.tk.Toplevel) for w in root.winfo_children())
