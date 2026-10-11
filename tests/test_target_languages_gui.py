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
                            _normal_queue_locked=lambda: False, _default_output=lambda p, *_a: tmp_path / "out",
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


def test_items_from_translation_status_stay_japanese(tmp_path):
    loc = tmp_path / "Mod" / "localization"; loc.mkdir(parents=True)
    state = SimpleNamespace(queue_items=[], target_lang_var=SimpleNamespace(get=lambda: "french"),
                            normal_output_var=SimpleNamespace(get=lambda: str(tmp_path / "out")),
                            _isolated_output_path=lambda *_a: tmp_path / "out" / "mod",
                            _normal_queue_locked=lambda: False, _new_cache_path=lambda p: tmp_path / "c.json",
                            _refresh_queue_tree=lambda: None, _save_workspace_state=lambda *_a: None)
    state._append_queue = types.MethodType(main.App._append_queue, state)
    item = main.App._queue_mod_status_result(state, {"localization": str(loc), "path": str(loc.parent), "mod": "Mod"})
    assert item["target_lang"] == "japanese"


def test_output_folder_name_follows_the_target_language(tmp_path):
    """v0.12.1：日本語以外の出力先が「…_japanese」になり、同じ Mod の日本語と出力先を共有していた。"""
    state = SimpleNamespace(_output_identity_source=lambda p: p)
    mod = tmp_path / "mods" / "Example"; mod.mkdir(parents=True)
    ja = main.App._isolated_output_path(state, mod, tmp_path / "out", "Example")
    fr = main.App._isolated_output_path(state, mod, tmp_path / "out", "Example", target_lang="french")
    assert ja.name.endswith("_japanese") and fr.name.endswith("_french")
    assert ja.name[:-len("_japanese")] == fr.name[:-len("_french")]  # 言語以外は同じ（Mod ごとに分ける部分）
    assert main.App._isolated_output_path(state, mod, tmp_path / "out", "Example", target_lang="klingon") == ja


def test_queue_items_get_a_per_language_output_and_old_items_are_corrected(tmp_path):
    mod = tmp_path / "Example"; mod.mkdir()
    state = SimpleNamespace(queue_items=[], target_lang_var=SimpleNamespace(get=lambda: "french"),
                            normal_output_var=SimpleNamespace(get=lambda: str(tmp_path / "out")),
                            _normal_queue_locked=lambda: False, _new_cache_path=lambda p: tmp_path / "c.json",
                            _refresh_queue_tree=lambda: None, _save_workspace_state=lambda *_a: None,
                            _output_identity_source=lambda p: p)
    state._isolated_output_path = types.MethodType(main.App._isolated_output_path, state)
    state._default_output = types.MethodType(main.App._default_output, state)
    main.App._append_queue(state, mod)
    main.App._append_queue(state, mod, target_lang="japanese")
    fr, ja = state.queue_items
    assert fr["output"].endswith("_french") and ja["output"].endswith("_japanese") and fr["output"] != ja["output"]
    # v0.12.0 で保存したフランス語の項目（出力先が _japanese）は、次に始めるときに _french へ向け直す。
    # キャッシュの場所は変えない（訳し直しにならない）。古い出力のファイルは動かさない。
    cache = tmp_path / "cache" / "job" / "translate_cache.json"
    old = {"input": str(mod), "mod_name": "Example", "target_lang": "french", "output_isolated_v2": True,
           "output": ja["output"], "cache": str(cache)}
    old_output = Path(ja["output"]); (old_output / "french").mkdir(parents=True)
    (old_output / "french" / "ev_l_french.yml").write_text('l_french:\n a:0 "Texte"\n', encoding="utf-8")
    main.App._ensure_isolated_item_output(state, old)
    assert old["output"] == fr["output"]
    assert old["cache"] == str(cache)
    assert main._cache_for_target(old["cache"], "french") == cache.parent / "target_french" / cache.name
    assert (old_output / "french" / "ev_l_french.yml").exists()
    # 新しく足したフランス語の項目は、フランス語の出力先のまま
    main.App._ensure_isolated_item_output(state, fr)
    assert fr["output"].endswith("_french")
    main.App._ensure_isolated_item_output(state, ja)
    assert ja["output"].endswith("_japanese")


def test_japanese_output_folder_name_is_the_same_as_v0_12_0(tmp_path):
    import hashlib, re
    state = SimpleNamespace(_output_identity_source=lambda p: p)
    mod = tmp_path / "mods" / "Example Mod"; mod.mkdir(parents=True)
    got = main.App._isolated_output_path(state, mod, tmp_path / "out", "Example Mod")
    # v0.12.0 の式：f"{safe}_{sha256(source)[:10]}_japanese"
    safe = re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+', '_', "Example Mod").strip('_')[:64]
    digest = hashlib.sha256(str(mod.resolve()).encode()).hexdigest()[:10]
    assert got == tmp_path / "out" / f"{safe}_{digest}_japanese"


def test_same_mod_in_japanese_and_french_keeps_outputs_and_reports_apart(tmp_path, monkeypatch):
    import json
    src = tmp_path / "mod" / "localization" / "english"; src.mkdir(parents=True)
    (src / "ev_l_english.yml").write_text('l_english:\n a:0 "The council approved the law"\n', encoding="utf-8")
    texts = {"japanese": "評議会は法を承認した", "french": "Le conseil a approuvé la loi"}
    monkeypatch.setattr(main.core, "translate_batch",
                        lambda _u, _m, jobs, _s, *a, **k: [texts[k.get("target_lang", "japanese")] for _ in jobs])
    state = SimpleNamespace(_output_identity_source=lambda p: p)
    outputs = {}
    for lang in ("japanese", "french"):
        out = main.App._isolated_output_path(state, tmp_path / "mod" / "localization", tmp_path / "out", "Mod",
                                             target_lang=lang)
        main.core.run_translation(tmp_path / "mod" / "localization", out, target_lang=lang, verbose=False,
                                  cache_path=tmp_path / f"cache_{lang}" / "translate_cache.json",
                                  qa_backup_root=tmp_path / "bk")
        outputs[lang] = out
    assert outputs["japanese"] != outputs["french"]
    for lang, out in outputs.items():
        assert [p.name for p in out.iterdir() if p.is_dir()] == [lang]
        assert len(json.loads((out / "translation_error_report.json").read_text(encoding="utf-8"))["attempts"]) == 1
        assert (out / "translation_qa_repair_report.json").exists()
    assert main.core.parse_localization_file(outputs["japanese"] / "japanese" / "ev_l_japanese.yml")[1]["a"] == texts["japanese"]


def test_redirected_output_reuses_the_cache_without_calling_the_llm(tmp_path, monkeypatch):
    """v0.12.0 の項目を _french へ向け直しても、キャッシュから出力でき、訳し直しにならない。"""
    src = tmp_path / "mod" / "localization" / "english"; src.mkdir(parents=True)
    (src / "ev_l_english.yml").write_text('l_english:\n a:0 "The council approved the law"\n', encoding="utf-8")
    calls = []
    monkeypatch.setattr(main.core, "translate_batch",
                        lambda _u, _m, jobs, _s, *a, **k: calls.append(1) or ["Le conseil a approuvé la loi" for _ in jobs])
    cache = main._cache_for_target(tmp_path / "cache" / "job" / "translate_cache.json", "french")
    old_out, new_out = tmp_path / "out" / "Mod_x_japanese", tmp_path / "out" / "Mod_x_french"
    main.core.run_translation(tmp_path / "mod" / "localization", old_out, target_lang="french", cache_path=cache,
                              verbose=False, auto_qa=False)
    calls.clear()
    main.core.run_translation(tmp_path / "mod" / "localization", new_out, target_lang="french", cache_path=cache,
                              verbose=False, auto_qa=False)
    assert calls == []
    assert main.core.parse_localization_file(new_out / "french" / "ev_l_french.yml")[1]["a"] == "Le conseil a approuvé la loi"
    assert (old_out / "french" / "ev_l_french.yml").exists()
