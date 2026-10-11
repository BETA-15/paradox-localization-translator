"""翻訳先の言語（v0.12.0）の画面側の処理。App は起動せず、関数とメソッドだけを呼ぶ。"""
from __future__ import annotations

import importlib
import os
import tempfile
import types
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("PARADOX_TRANSLATOR_DATA_ROOT", tempfile.mkdtemp(prefix="plt-main-test-"))

main = importlib.import_module("main")


def test_target_language_choices_round_trip():
    for lang in main.core.TARGET_LANGUAGES:
        assert main._target_lang_from_choice(main._target_lang_choice(lang)) == lang
    assert main._target_lang_choice("french") == "フランス語（l_french）"
    assert main._target_lang_from_choice("unknown") == "japanese"


def test_saved_queue_items_without_target_are_japanese():
    assert main._item_target_lang({}) == "japanese"
    assert main._item_target_lang({"target_lang": "korean"}) == "korean"
    assert main._item_target_lang({"target_lang": "klingon"}) == "japanese"


def test_cache_for_other_languages_is_kept_apart_from_japanese(tmp_path):
    cache = tmp_path / "jobs" / "mod_a" / "translate_cache.json"
    assert main._cache_for_target(cache, "japanese") == cache
    french = main._cache_for_target(cache, "french")
    assert french == cache.parent / "target_french" / "translate_cache.json"
    # source_manifest.json はキャッシュと同じフォルダに置かれるので、フォルダが違えば日本語の記録と混ざらない
    assert french.parent != cache.parent and french.parent.is_dir()


def test_start_checks_block_diff_mode_and_warn_about_unreadable_languages():
    hoi4 = {"input": "/Steam/steamapps/workshop/content/394360/1/", "target_lang": "turkish"}
    vic3 = {"input": "/Steam/steamapps/workshop/content/529340/2/", "target_lang": "turkish"}
    stop, warnings = main._target_language_problems([hoi4, vic3], diff_requested=False, preset="CK3")
    assert stop == "" and len(warnings) == 1 and "Hearts of Iron IV" in warnings[0]
    stop, _ = main._target_language_problems([vic3], diff_requested=True)
    assert "差分だけ翻訳" in stop
    assert main._target_language_problems([{"input": "/x"}], diff_requested=True) == ("", [])


def test_append_queue_records_the_selected_target(tmp_path):
    mod = tmp_path / "mod"; mod.mkdir()
    saved = []
    state = SimpleNamespace(queue_items=[], target_lang_var=SimpleNamespace(get=lambda: "german"),
                            _normal_queue_locked=lambda: False, _default_output=lambda p: tmp_path / "out",
                            _new_cache_path=lambda p: tmp_path / "cache.json", _refresh_queue_tree=lambda: None,
                            _save_workspace_state=saved.append)
    main.App._append_queue(state, mod)
    assert state.queue_items[0]["target_lang"] == "german"


def test_source_overwrite_layout_uses_the_item_target_language(tmp_path):
    mod = tmp_path / "Mod"; (mod / "localization" / "english").mkdir(parents=True)
    out = tmp_path / "out"
    for lang in ("french", "japanese"):
        path = out / lang / f"ev_l_{lang}.yml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"l_{lang}:\n a:0 \"x\"\n", encoding="utf-8")
    state = SimpleNamespace(_infer_mod_target_for_item=lambda _item: (mod / "localization", mod))
    item = {"input": str(mod), "output": str(out), "target_lang": "french"}

    _loc, _root, mappings = main.App._source_overwrite_layout(state, item)

    assert [(src.name, str(rel)) for src, _dst, rel in mappings] == [("ev_l_french.yml", "french/ev_l_french.yml")]
    item["target_lang"] = "japanese"
    _loc, _root, mappings = main.App._source_overwrite_layout(state, item)
    assert [src.name for src, _dst, _rel in mappings] == ["ev_l_japanese.yml"]


def test_non_japanese_items_never_target_a_japanese_translation_mod():
    conflicts = [{"mod": "JP", "effective": True, "stale_translation_candidate": True}]
    state = SimpleNamespace(_source_overwrite_path_conflicts=lambda _item: conflicts)
    assert main.App._preferred_later_translation_conflict(state, {"target_lang": "french"})[0] is None
    assert main.App._preferred_later_translation_conflict(state, {})[0]["mod"] == "JP"
