"""README・CHANGELOG の約束ごと（不変条件）のうち、バックアップ・復元・Mod への上書きの回帰テスト。

各テストの docstring の番号は docs/invariants.md の対応表の番号と一致する。
App は起動せず、必要なメソッドだけを SimpleNamespace に結びつけて呼ぶ（test_main_state.py と同じ方式）。
"""
from __future__ import annotations

import importlib
import json
import os
import queue
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("PARADOX_TRANSLATOR_DATA_ROOT", tempfile.mkdtemp(prefix="plt-main-test-"))

main = importlib.import_module("main")

_SNAPSHOT_METHODS = (
    "_create_full_localization_snapshot", "_backup_game_name_for_root", "_safe_backup_mod_token",
    "_next_overwrite_backup_generation", "_backup_manifest_records", "_generated_japanese_files",
)


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _state(**attrs):
    state = SimpleNamespace(mod_research_results=[], **attrs)
    for name in _SNAPSHOT_METHODS:
        setattr(state, name, types.MethodType(getattr(main.App, name), state))
    return state


def _mod(root: Path, name: str, files: dict) -> Path:
    _write(root / "descriptor.mod", f'name="{name}"\n')
    for rel, text in files.items():
        _write(root / "localization" / rel, text)
    return root


def _entries(path: Path) -> dict:
    return main.core.parse_localization_file(path)[1]


# ---------------------------------------------------------------- 上書き前のバックアップ

def test_overwrite_snapshot_copies_whole_localization_with_manifest_and_generation(tmp_path, monkeypatch):
    """INV-24・INV-25: 上書き前に localization 全体を保存し、対象 Mod ごとに第N回を数える。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    mod = _mod(tmp_path / "steamapps" / "workshop" / "content" / "1158310" / "123", "My Mod", {
        "english/a_l_english.yml": 'l_english:\n a:0 "A"\n',
        "japanese/a_l_japanese.yml": 'l_japanese:\n a:0 "エー"\n',
    })
    state = _state()

    first, manifest = state._create_full_localization_snapshot(mod, "元Mod上書き", stamp="s1")
    second, manifest2 = state._create_full_localization_snapshot(mod, "元Mod上書き", stamp="s2")

    assert first.name == "第0001回_s1" and second.name == "第0002回_s2"
    assert (manifest["generation"], manifest2["generation"]) == (1, 2)
    assert manifest["game_name"] == "Crusader Kings III"
    assert manifest["target_mod_name"] == "My Mod"
    assert manifest["snapshot_type"] == "full_localization" and manifest["localization_existed"] is True
    assert _entries(first / "localization" / "japanese" / "a_l_japanese.yml") == {"a": "エー"}
    assert _entries(first / "localization" / "english" / "a_l_english.yml") == {"a": "A"}
    saved = json.loads((first / "backup_manifest.json").read_text(encoding="utf-8"))
    assert saved["target_root"] == str(mod)

    other = _mod(tmp_path / "Other", "Other Mod", {"english/b_l_english.yml": 'l_english:\n b:0 "B"\n'})
    assert state._create_full_localization_snapshot(other, "元Mod上書き", stamp="s3")[1]["generation"] == 1


def test_snapshot_of_mod_without_localization_records_that_it_did_not_exist(tmp_path, monkeypatch):
    """INV-24: localization が無い Mod でも空のスナップショットを作り、無かったことを記録する。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    mod = _mod(tmp_path / "Empty", "Empty Mod", {})

    root, manifest = _state()._create_full_localization_snapshot(mod, "元Mod上書き", stamp="s1")

    assert manifest["localization_existed"] is False
    assert (root / "localization").is_dir() and not any((root / "localization").iterdir())


# ---------------------------------------------------------------- バックアップの復元

def _restore_state(tmp_path, entry):
    events = queue.Queue()
    invalidated = []
    state = _state(
        backup_restore_operation_thread=None,
        backup_restore_tree=SimpleNamespace(selection=lambda: ("e1",)),
        backup_restore_entry_map={"e1": entry},
        backup_restore_btn=SimpleNamespace(config=lambda **_k: None),
        backup_restore_summary_var=SimpleNamespace(set=lambda _v: None),
        events=events,
        _invalidate_mod_status_cache_paths=invalidated.extend,
        _refresh_operation_states=lambda: None,
    )
    return state, events, invalidated


def _run_restore(state):
    main.App._restore_selected_backup(state)
    state.backup_restore_operation_thread.join(timeout=10)
    assert not state.backup_restore_operation_thread.is_alive()


def test_exact_restore_saves_current_state_first_then_replaces_localization(tmp_path, monkeypatch):
    """INV-26・INV-27: 復元前に今の localization を『復元前退避』へ保存し、完全バックアップでそっくり戻す。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *_a, **_k: True)
    mod = _mod(tmp_path / "Mod", "Mod", {"japanese/a_l_japanese.yml": 'l_japanese:\n a:0 "当時の訳"\n'})
    snapshot, _ = _state()._create_full_localization_snapshot(mod, "元Mod上書き", stamp="s1")
    _write(mod / "localization" / "japanese" / "a_l_japanese.yml", 'l_japanese:\n a:0 "今の訳"\n')
    _write(mod / "localization" / "japanese" / "later_l_japanese.yml", 'l_japanese:\n b:0 "後で追加"\n')
    entry = {"target_root": str(mod), "generation": 1, "mod": "Mod", "kind": "元Mod上書き",
             "state": "上書き直前", "exact": True, "snapshot": str(snapshot / "localization")}
    state, events, invalidated = _restore_state(tmp_path, entry)

    _run_restore(state)

    kind, (target, safety) = events.get_nowait()
    assert kind == "backup_restore_done" and target == str(mod)
    assert _entries(mod / "localization" / "japanese" / "a_l_japanese.yml") == {"a": "当時の訳"}
    assert not (mod / "localization" / "japanese" / "later_l_japanese.yml").exists()
    safety = Path(safety)
    assert safety.parent.name == "復元前退避"
    assert _entries(safety / "localization" / "japanese" / "a_l_japanese.yml") == {"a": "今の訳"}
    assert (safety / "localization" / "japanese" / "later_l_japanese.yml").exists()
    assert invalidated == [str(mod)]


def test_legacy_partial_restore_only_puts_back_saved_files(tmp_path, monkeypatch):
    """INV-28: 旧形式の部分バックアップは保存済みファイルだけを戻し、後から作ったファイルは消さない。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *_a, **_k: True)
    mod = _mod(tmp_path / "Mod", "Mod", {
        "japanese/a_l_japanese.yml": 'l_japanese:\n a:0 "今の訳"\n',
        "japanese/new_l_japanese.yml": 'l_japanese:\n n:0 "新規"\n',
    })
    legacy = tmp_path / "legacy_backup"
    _write(legacy / "japanese" / "a_l_japanese.yml", 'l_japanese:\n a:0 "当時の訳"\n')
    _write(legacy / "backup_manifest.json", "{}")
    entry = {"target_root": str(mod), "generation": None, "mod": "Mod", "kind": "旧形式",
             "state": "不明", "exact": False, "snapshot": str(legacy)}
    state, events, _ = _restore_state(tmp_path, entry)

    _run_restore(state)

    assert events.get_nowait()[0] == "backup_restore_done"
    assert _entries(mod / "localization" / "japanese" / "a_l_japanese.yml") == {"a": "当時の訳"}
    assert _entries(mod / "localization" / "japanese" / "new_l_japanese.yml") == {"n": "新規"}
    assert not (mod / "localization" / "backup_manifest.json").exists()
    assert not (mod / "backup_manifest.json").exists()


def test_restore_is_cancelled_without_touching_files(tmp_path, monkeypatch):
    """INV-26: 確認で「いいえ」なら何も変えない。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *_a, **_k: False)
    mod = _mod(tmp_path / "Mod", "Mod", {"japanese/a_l_japanese.yml": 'l_japanese:\n a:0 "今の訳"\n'})
    entry = {"target_root": str(mod), "generation": 1, "mod": "Mod", "kind": "k", "state": "s",
             "exact": True, "snapshot": str(tmp_path / "nowhere")}
    state, events, _ = _restore_state(tmp_path, entry)

    main.App._restore_selected_backup(state)

    assert state.backup_restore_operation_thread is None
    assert events.empty()
    assert _entries(mod / "localization" / "japanese" / "a_l_japanese.yml") == {"a": "今の訳"}
    assert not (tmp_path / "backup").exists()


# ---------------------------------------------------------------- 日本語化 Mod・元 Mod への上書き

def test_external_gap_overwrite_writes_only_gap_keys_and_backs_up_first(tmp_path, monkeypatch):
    """INV-30・INV-31: 日本語化 Mod へは差分キーだけを書き、既存訳は維持し、無いキーは専用ファイルへ足す。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    ext = _mod(tmp_path / "JP", "JP Translation", {
        "japanese/ext_l_japanese.yml": 'l_japanese:\n kept:0 "既存訳"\n gap:0 "Gap text"\n',
    })
    output = tmp_path / "Output"
    _write(output / "japanese" / "src_l_japanese.yml",
           'l_japanese:\n kept:0 "別の訳"\n gap:0 "差分訳"\n added:0 "追加訳"\n')
    state = _state(_infer_mod_target_for_item=lambda _item: (None, None))
    item = {"external_translation_path": str(ext), "external_translation_localization": str(ext / "localization"),
            "external_gap_keys": ["gap", "added"], "output": str(output), "mod_name": "Source"}

    ok, reason = main.App._perform_external_gap_overwrite(state, item, confirm=False, notify=False)

    assert ok is True and "既存キー更新 1" in reason and "新規キー追加 1" in reason
    assert _entries(ext / "localization" / "japanese" / "ext_l_japanese.yml") == {"kept": "既存訳", "gap": "差分訳"}
    patch = ext / "localization" / "japanese" / "paradox_localization_translator_missing_l_japanese.yml"
    assert _entries(patch) == {"added": "追加訳"}
    snapshot = next((tmp_path / "backup").rglob("backup_manifest.json")).parent
    assert _entries(snapshot / "localization" / "japanese" / "ext_l_japanese.yml") == {"kept": "既存訳", "gap": "Gap text"}


def test_external_gap_overwrite_refuses_without_gap_keys(tmp_path, monkeypatch):
    """INV-30: 差分情報が無ければ日本語化 Mod に何も書かない。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    ext = _mod(tmp_path / "JP", "JP", {"japanese/ext_l_japanese.yml": 'l_japanese:\n kept:0 "既存訳"\n'})
    item = {"external_translation_path": str(ext), "external_translation_localization": str(ext / "localization"),
            "external_gap_keys": [], "output": str(tmp_path / "Output")}

    ok, _reason = main.App._perform_external_gap_overwrite(_state(), item, confirm=False, notify=False)

    assert ok is False
    assert not (tmp_path / "backup").exists()


def test_source_mod_overwrite_backs_up_existing_files_before_replacing(tmp_path, monkeypatch):
    """INV-32: 元 Mod へ直接上書きするときは、置き換える既存ファイルを先にバックアップする。"""
    monkeypatch.setattr(main, "BACKUP_ROOT", tmp_path / "backup")
    mod = _mod(tmp_path / "Mod", "Mod", {
        "english/a_l_english.yml": 'l_english:\n a:0 "Alpha"\n',
        "japanese/a_l_japanese.yml": 'l_japanese:\n a:0 "古い訳"\n',
    })
    generated = tmp_path / "Output" / "japanese" / "a_l_japanese.yml"
    _write(generated, 'l_japanese:\n a:0 "新しい訳"\n')
    rel = Path("localization/japanese/a_l_japanese.yml")
    dst = mod / rel
    state = _state(_source_overwrite_layout=lambda _item: (mod / "localization", mod, [(generated, dst, rel)]))

    ok, reason = main.App._perform_source_mod_overwrite(state, {"mod_name": "Mod"}, confirm=False, notify=False)

    assert ok is True and "書き込み 1" in reason and "バックアップ 1" in reason
    assert _entries(dst) == {"a": "新しい訳"}
    snapshot = next((tmp_path / "backup").rglob("backup_manifest.json")).parent
    assert _entries(snapshot / rel) == {"a": "古い訳"}
