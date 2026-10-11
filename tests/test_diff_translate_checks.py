"""v0.11.81：差分調査の「欠落・未翻訳をまとめて翻訳」で、使えない訳を書き戻さない・書く前にバックアップする・
翻訳状況のキャッシュを捨てる、のテスト。LLM は呼ばず translate_single_text を差し替える。"""
from __future__ import annotations

import importlib
import os
import queue
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("PARADOX_TRANSLATOR_DATA_ROOT", tempfile.mkdtemp(prefix="plt-main-test-"))

main = importlib.import_module("main")


class _Var:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _state(tmp_path, source, target):
    _, src_entries, _ = main.core.parse_localization_file(source)
    _, dst_entries, _ = main.core.parse_localization_file(target)
    rows = main.core.compare_localization_entries(src_entries, dst_entries, "english")
    invalidated = []
    state = SimpleNamespace(
        _closing=False, diff_controller=None, diff_rows=rows, diff_batch_contexts=[],
        diff_src_var=_Var(str(source)), diff_dst_var=_Var(str(target)), diff_source_lang="english",
        diff_source_entries=src_entries, diff_target_entries=dst_entries,
        diff_message_var=_Var(), glossary_path_var=_Var(""), url_var=_Var("http://localhost:1"),
        model_var=_Var("m"), preset_var=_Var("HOI4"), provider_var=_Var("Ollama"), api_key_var=_Var(""),
        events=queue.Queue(), llm_operation="", mod_research_results=[],
        _invalidate_mod_status_cache_paths=invalidated.extend,
    )
    for name in ("_backup_before_diff_write", "_invalidate_status_after_diff_write", "_create_full_localization_snapshot",
                 "_backup_game_name_for_root", "_safe_backup_mod_token", "_next_overwrite_backup_generation",
                 "_backup_manifest_records"):
        setattr(state, name, types.MethodType(getattr(main.App, name), state))
    return state, invalidated


def _run(state):
    main.App.translate_diff_items(state, all_missing=True, _llm_ready=True)
    state.diff_translate_thread.join(timeout=10)
    events = []
    while not state.events.empty():
        events.append(state.events.get())
    return next(p for k, p in events if k == "diff_translate_done")


def test_bulk_diff_translation_never_writes_source_text_back(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    mod = tmp_path / "JP Mod"
    source = tmp_path / "src" / "ev_l_english.yml"
    target = mod / "localization" / "japanese" / "ev_l_japanese.yml"
    _write(source, 'l_english:\n kept:0 "Kept"\n ok:0 "Declare war on them"\n stuck:0 "Raise the army now"\n'
                   ' retry:0 "Gain $GOLD$ gold"\n')
    _write(target, 'l_japanese:\n kept:0 "保持"\n stuck:0 "Raise the army now"\n')
    _write(mod / "descriptor.mod", 'name="JP Mod"\n')
    calls = {}

    def fake(_url, _model, text, *_args, **_kwargs):
        calls[text] = calls.get(text, 0) + 1
        if text == "Declare war on them":
            return "彼らに宣戦布告する"
        if text == "Raise the army now":
            return text  # LLM が原文のまま返す
        if text == "Gain $GOLD$ gold":
            return "金を得る" if calls[text] == 1 else "$GOLD$の金を得る"  # 1回目は変数が抜ける → 訳し直し
        return ""

    monkeypatch.setattr(main.core, "translate_single_text", fake)
    state, invalidated = _state(tmp_path, source, target)

    result = _run(state)

    entries = main.core.parse_localization_file(target)[1]
    assert entries["ok"] == "彼らに宣戦布告する"
    assert entries["retry"] == "$GOLD$の金を得る"
    assert entries["stuck"] == "Raise the army now"  # 書き換えていない（原文の新規書き込みもしない）
    assert result["written"] == 2
    assert [row["key"] for row in result["untranslated"]] == ["stuck"]
    assert calls["Raise the army now"] == main.DIFF_TRANSLATE_ATTEMPTS and calls["Gain $GOLD$ gold"] == 2
    # 書く前に、日本語化Modの localization 全体をバックアップしている
    backup = Path(result["backups"][0])
    assert main.core.parse_localization_file(backup / "localization" / "japanese" / "ev_l_japanese.yml")[1] == \
        {"kept": "保持", "stuck": "Raise the army now"}
    # 翻訳状況のキャッシュを捨てている（書き込んだ日本語化Mod）
    assert str(mod) in invalidated


def test_bulk_diff_translation_writes_nothing_when_every_answer_is_unusable(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    source = tmp_path / "src" / "ev_l_english.yml"
    target = tmp_path / "loose" / "ev_l_japanese.yml"
    _write(source, 'l_english:\n a:0 "Raise the army now"\n')
    _write(target, 'l_japanese:\n')
    before = target.read_bytes()
    monkeypatch.setattr(main.core, "translate_single_text", lambda _u, _m, text, *_a, **_k: text)
    state, invalidated = _state(tmp_path, source, target)

    result = _run(state)

    assert target.read_bytes() == before
    assert result["written"] == 0 and len(result["untranslated"]) == 1
    assert not (tmp_path / "backup").exists() and invalidated == []


def test_loose_files_are_backed_up_file_by_file(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    target = tmp_path / "loose" / "ev_l_japanese.yml"
    _write(target, 'l_japanese:\n a:0 "旧"\n')
    state, _ = _state(tmp_path, target, target)
    backups = state._backup_before_diff_write([str(target)])
    manifest = main.core.load_json(Path(backups[0]) / "manifest.json", {})
    assert manifest["files"][0]["original"] == str(target)
    assert Path(manifest["files"][0]["backup"]).read_text(encoding="utf-8") == 'l_japanese:\n a:0 "旧"\n'


def test_diff_translation_problem_checks():
    assert main._diff_translation_problem("Hello $NAME$", "こんにちは $NAME$", "english") == ""
    assert main._diff_translation_problem("Hello $NAME$", "Hello $NAME$", "english")
    assert main._diff_translation_problem("Hello $NAME$", "こんにちは", "english")
    assert main._diff_translation_problem("Hello", "こんにちは @@0@@", "english")
    assert main._diff_translation_problem("Hello", "  ", "english")
    assert "中国語" in main._diff_translation_problem("The railway was built", "在铁路建设中发现了少量矿藏，促使公司雇佣工程师。", "english")
