"""翻訳先の11言語対応（v0.12.0）のテスト。LLM は呼ばない。"""
from __future__ import annotations

from pathlib import Path

import translator_core as core

OFFICIAL = ["english", "french", "german", "spanish", "japanese", "korean",
            "polish", "braz_por", "russian", "simp_chinese", "turkish"]


def test_language_table_lists_the_eleven_official_languages():
    assert sorted(core.TARGET_LANGUAGES) == sorted(OFFICIAL)
    assert set(OFFICIAL) <= set(core.KNOWN_SOURCE_LANGS)
    scripts = {lang: core.target_language_script(lang) for lang in OFFICIAL}
    assert scripts["japanese"] == "japanese" and scripts["korean"] == "hangul"
    assert scripts["russian"] == "cyrillic" and scripts["simp_chinese"] == "han"
    assert {scripts[x] for x in ("english", "french", "german", "spanish", "polish", "braz_por", "turkish")} == {"latin"}
    for lang in OFFICIAL:
        assert core.target_language_label(lang) and core.target_language_name(lang)
    for game, langs in core.GAME_LANGUAGES.items():
        assert set(langs) <= set(OFFICIAL), game


def test_turkish_files_are_recognized_as_a_language_folder():
    assert core.detect_source_lang(Path("events_l_turkish.yml"), []) == "turkish"
    assert core.remap_rel_dir(Path("turkish/events"), "japanese") == Path("japanese/events")
    assert core.rename_for_target(Path("ev_l_english.yml"), "turkish", "english") == "ev_l_turkish.yml"


def test_game_language_warning_for_languages_the_game_cannot_read():
    hoi4_mod = "/Steam/steamapps/workshop/content/394360/123/"
    eu4_mod = "/Users/x/Documents/Paradox Interactive/Europa Universalis IV/mod/my_mod"
    assert "l_turkish" in core.game_language_warning("turkish", hoi4_mod)
    assert core.game_language_warning("japanese", hoi4_mod) == ""
    assert "l_japanese" in core.game_language_warning("japanese", eu4_mod)
    assert core.game_language_warning("german", eu4_mod) == ""
    assert core.game_language_warning("korean", "/Steam/steamapps/workshop/content/859580/1/") != ""
    # CK3 のゲーム本文は braz_por・turkish を持たない
    assert core.game_language_warning("braz_por", None, "CK3") != ""
    # 場所が分からなければプリセットで判定し、それも分からなければ警告しない
    assert core.game_language_warning("turkish", "/somewhere/else", "Victoria 3") == ""
    assert core.game_language_warning("turkish", "/somewhere/else", "General") == ""
    # 場所の情報はプリセットより優先する
    assert core.game_language_warning("turkish", hoi4_mod, "Victoria 3") != ""


def test_cache_keys_are_separated_by_target_language_except_japanese_unchanged():
    args = ("Ollama", "qwen3:8b", "CK3", "english", "Hello")
    japanese = core.translation_cache_key(*args)
    assert core.translation_cache_key(*args, target_lang="japanese") == japanese
    keys = {lang: core.translation_cache_key(*args, target_lang=lang) for lang in OFFICIAL}
    assert len(set(keys.values())) == len(OFFICIAL)
    assert keys["japanese"] == japanese


def test_non_japanese_prompts_use_the_english_template_for_the_target():
    for lang in OFFICIAL:
        if lang == "japanese":
            continue
        source = "simp_chinese" if lang == "english" else "english"
        prompt = core.build_system_prompt(source, {"Duke": "Herzog"}, "HOI4", target_lang=lang)
        name = core.target_language_name(lang)
        assert f"into natural, readable {name}" in prompt
        assert f"Translate the {core.target_language_name(source)} game text" in prompt
        assert "Hearts of Iron IV" in prompt and "- Duke => Herzog" in prompt
        assert "@@0@@" in prompt and "日本語" not in prompt
    assert "Simplified Chinese characters" in core.build_system_prompt("english", target_lang="simp_chinese")
    # 中国語の参考訳は翻訳先が中国語のときは付けない。
    assert "ZH_REF" not in core.build_system_prompt("english", dual_source=True, target_lang="simp_chinese")
    assert "ZH_REF" in core.build_system_prompt("english", dual_source=True, target_lang="french")
    assert "Chinese-basis translation" in core.build_system_prompt("simp_chinese", chinese_basis=True, target_lang="korean")
    for language in set(core.TARGET_LANGUAGES) - set(core.CHINESE_BASIS_TARGETS):
        assert "Chinese-basis translation" not in core.build_system_prompt("simp_chinese", chinese_basis=True, target_lang=language)


def test_non_japanese_proofreading_prompt(monkeypatch):
    sent = []
    monkeypatch.setattr(core, "call_llm_raw", lambda _p, _u, _m, user, system, **_k: sent.append((system, user)) or "Bonjour @@0@@")
    assert core.proofread_text("u", "m", "Bonjur $NAME$", "Hello $NAME$", target_lang="french") == "Bonjour $NAME$"
    system, user = sent[0]
    assert "French localization" in system and "日本語" not in system
    assert user == "Source for reference: Hello [VAR]\nFrench: Bonjur @@0@@"


def test_japanese_untranslated_checks_are_unchanged_by_default():
    # 既定（日本語）と明示した日本語は同じ結果
    cases = [("Declare war", "Declare war", "english"), ("Declare war", "宣戦布告", "english"),
             ("The council approved", "The council approved the law", "english"),
             ("这是尚未翻译的完整句子。", "这是尚未翻译的完整句子。", "simp_chinese")]
    for orig, trans, src in cases:
        assert core.looks_untranslated(orig, trans, src) == core.looks_untranslated(orig, trans, src, "japanese")
    assert core.looks_foreign_in_target("Open the gate", "japanese") is True


def test_latin_targets_accept_normal_translations_and_flag_only_long_identical_text():
    # 普通の訳は未翻訳にしない（日本語の「英字12文字以上・かな無し」の判定を使わない）
    for lang, text in (("french", "Le conseil a approuvé la nouvelle loi"), ("german", "Der Rat hat das Gesetz beschlossen"),
                       ("spanish", "El consejo aprobó la nueva ley"), ("polish", "Rada zatwierdziła nową ustawę"),
                       ("braz_por", "O conselho aprovou a nova lei"), ("turkish", "Konsey yeni yasayı onayladı")):
        assert core.looks_untranslated("The council approved the new law", text, "english", lang) is False, lang
        assert core.cache_entry_is_valid("The council approved the new law", text, "english", lang)
    # 原文と同じでも短いもの（固有名詞が多い）は未翻訳にしない。文の長さなら未翻訳
    assert core.looks_untranslated("Napoleon", "Napoleon", "english", "french") is False
    assert core.looks_untranslated("Karl Marx", "Karl Marx", "english", "german") is False
    assert core.looks_untranslated("The council approved the law", "The council approved the law", "english", "french") is True
    # 中国語の原文が残っていれば未翻訳
    assert core.looks_untranslated("议会通过了新法律", "议会通过了新法律", "simp_chinese", "english") is True
    assert core.looks_untranslated("议会通过了新法律", "The council passed the law", "simp_chinese", "english") is False
    assert core.looks_foreign_in_target("Open the gate", "french") is False


def test_non_latin_targets_are_checked_by_script():
    src = "The council approved the new law"
    assert core.looks_untranslated(src, "의회가 새 법을 승인했다", "english", "korean") is False
    assert core.looks_untranslated(src, "Совет одобрил новый закон", "english", "russian") is False
    assert core.looks_untranslated(src, "议会批准了新法律", "english", "simp_chinese") is False
    for lang in ("korean", "russian", "simp_chinese"):
        assert core.looks_untranslated(src, src, "english", lang) is True, lang
        assert core.looks_foreign_in_target(src, lang) is True, lang
    # 中国語のまま残った韓国語・ロシア語の訳
    assert core.looks_untranslated("议会通过了法律", "议会通过了法律", "simp_chinese", "korean") is True
    # 変数だけ・略語だけは未翻訳にしない（原文と同じでも）
    assert core.looks_untranslated("$NAME$", "$NAME$", "english", "russian") is False
    for lang in ("korean", "russian", "simp_chinese"):
        for abbr in ("AI", "DLC", "OK", "GDP"):
            assert core.looks_untranslated(abbr, abbr, "english", lang) is False, (lang, abbr)
        assert core.looks_untranslated("Declare war", "Declare war", "english", lang) is True, lang
    assert core.looks_foreign_in_target("NATO", "korean") is False


# ---------------------------------------------------------------- 翻訳の流れ全体（偽の LLM）

import json as _json

import pytest

FAKE_TEXT = {"french": "Texte traduit", "german": "Übersetzter Text", "korean": "번역된 문장",
             "spanish": "Texto traducido", "polish": "Przetłumaczony tekst", "braz_por": "Texto traduzido",
             "russian": "Переведённый текст", "english": "Translated text", "simp_chinese": "已翻译的文本",
             "japanese": "翻訳された文", "turkish": "Çevrilmiş metin"}


def _fake_translate(calls):
    def fake(_url, _model, jobs, source_lang, *args, **kwargs):
        target = kwargs.get("target_lang", "japanese")
        calls.append((source_lang, target, [j["key"] for j in jobs]))
        return [" ".join([FAKE_TEXT[target]] + [f"@@{k}@@" for k in range(len(j["tokens"]))]) for j in jobs]
    return fake


def _mod(root, files):
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


EN = 'l_english:\n greet:0 "Hello there $NAME$"\n title:0 "The council approved the new law"\n'
ZH = 'l_simp_chinese:\n greet:0 "你好 $NAME$"\n title:0 "议会通过了新法律"\n'


@pytest.mark.parametrize("target,files,expected_source", [
    ("french", {"english/ev_l_english.yml": EN}, "english"),
    ("korean", {"english/ev_l_english.yml": EN}, "english"),
    ("russian", {"english/ev_l_english.yml": EN}, "english"),
    ("turkish", {"english/ev_l_english.yml": EN}, "english"),
    ("german", {"english/ev_l_english.yml": EN}, "english"),
    ("spanish", {"english/ev_l_english.yml": EN}, "english"),
    ("polish", {"english/ev_l_english.yml": EN}, "english"),
    ("braz_por", {"english/ev_l_english.yml": EN}, "english"),
    # 翻訳先が english：english は原文から外し、simp_chinese を原文にする
    ("english", {"english/ev_l_english.yml": EN, "simp_chinese/ev_l_simp_chinese.yml": ZH}, "simp_chinese"),
    # 翻訳先が simp_chinese：simp_chinese は原文から外し、english を原文にする
    ("simp_chinese", {"english/ev_l_english.yml": EN, "simp_chinese/ev_l_simp_chinese.yml": ZH}, "english"),
])
def test_run_translation_end_to_end_for_each_target(tmp_path, monkeypatch, target, files, expected_source):
    calls = []
    monkeypatch.setattr(core, "translate_batch", _fake_translate(calls))
    src = _mod(tmp_path / "mod" / "localization", files)
    out = tmp_path / "out"

    result = core.run_translation(src, out, target_lang=target, verbose=False, dual_source=True,
                                  qa_backup_root=tmp_path / "bk")

    generated = out / target / f"ev_l_{target}.yml"
    assert generated.exists(), list(out.rglob("*.yml"))
    text = generated.read_text(encoding="utf-8-sig")
    assert text.startswith(f"l_{target}:")
    lang, entries, _ = core.parse_localization_file(generated)
    assert lang == target
    # 日本語・簡体字中国語は、文字と変数の間の半角スペースを取り除く（要望A1）
    space = "" if core.TARGET_LANGUAGES[target].get("remove_cjk_spaces") else " "
    assert entries["greet"] == f"{FAKE_TEXT[target]}{space}$NAME$"
    assert entries["title"] == FAKE_TEXT[target]
    assert {c[0] for c in calls} == {expected_source} and {c[1] for c in calls} == {target}
    assert result["qa_errors"] == 0 and result["failed"] == 0
    report = _json.loads((out / "translation_qa_repair_report.json").read_text(encoding="utf-8"))
    assert not any(e.get("action", "").startswith("rollback") for e in report.get("repair_events", []))
    # キャッシュは翻訳先ごとのキーで保存され、2回目は LLM を呼ばずにそのまま使える
    calls.clear()
    core.run_translation(src, out, target_lang=target, verbose=False, dual_source=True)
    assert calls == []
    assert core.parse_localization_file(generated)[1] == entries


def test_japanese_and_french_runs_do_not_share_cache_entries(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(core, "translate_batch", _fake_translate(calls))
    src = _mod(tmp_path / "mod" / "localization", {"english/ev_l_english.yml": EN})
    cache = tmp_path / "cache.json"
    core.run_translation(src, tmp_path / "ja", cache_path=cache, verbose=False, auto_qa=False)
    core.run_translation(src, tmp_path / "fr", cache_path=cache, target_lang="french", verbose=False, auto_qa=False)

    assert [c[1] for c in calls] == ["japanese", "french"]
    assert core.parse_localization_file(tmp_path / "fr" / "french" / "ev_l_french.yml")[1]["title"] == "Texte traduit"
    assert core.parse_localization_file(tmp_path / "ja" / "japanese" / "ev_l_japanese.yml")[1]["title"] == "翻訳された文"


def test_qa_pairs_and_output_qa_use_the_same_source_choice(tmp_path):
    src = _mod(tmp_path / "mod" / "localization",
               {"english/ev_l_english.yml": EN, "simp_chinese/ev_l_simp_chinese.yml": ZH,
                "french/ev_l_french.yml": 'l_french:\n greet:0 "Bonjour $NAME$"\n'})
    pairs = core.collect_translation_qa_pairs(src, tmp_path / "out", None, target_lang="english")
    assert [p["source_language"] for p in pairs] == ["simp_chinese"]
    pairs = core.collect_translation_qa_pairs(src, tmp_path / "out", None, target_lang="german")
    assert [p["source_language"] for p in pairs] == ["english"]
    # 日本語の既定（english と simp_chinese だけを見る）は今までどおり
    pairs = core.collect_translation_qa_pairs(src, tmp_path / "out", ("english", "simp_chinese"))
    assert [p["source_language"] for p in pairs] == ["english"]


def test_qa_on_french_output_reports_no_japanese_specific_errors():
    issues = core.qa_entries({"a": "Le conseil a approuvé la loi.", "b": "Napoleon"},
                             {"a": "The council approved the law.", "b": "Napoleon"}, "english",
                             target_lang="french")
    assert not [i for i in issues if i["severity"] in {"error", "warning"}]
    same = [i for i in issues if i["type"] == "same_as_source"]
    assert len(same) == 1 and same[0]["severity"] == "notice" and same[0]["repairable"] is False


def test_without_english_simplified_chinese_is_preferred_over_other_languages(tmp_path, monkeypatch):
    """英語が無く仏語と中国語があるとき、簡体字中国語を原文にする（日本語でも同じ。v0.11.80 までは仏語）。"""
    calls = []
    monkeypatch.setattr(core, "translate_batch", _fake_translate(calls))
    src = _mod(tmp_path / "mod" / "localization",
               {"french/ev_l_french.yml": 'l_french:\n greet:0 "Bonjour $NAME$"\n title:0 "Le conseil a approuvé la loi"\n',
                "simp_chinese/ev_l_simp_chinese.yml": ZH})
    for target in ("korean", "japanese"):
        calls.clear()
        core.run_translation(src, tmp_path / target, target_lang=target, verbose=False, auto_qa=False)
        assert {c[0] for c in calls} == {"simp_chinese"}, target


def test_dual_source_cache_hits_on_second_run_when_chinese_is_the_source(tmp_path, monkeypatch):
    """英中併用で英語が無く中国語が原文のとき、2回目はキャッシュが当たる（v0.12.0 で修正した古い不具合）。"""
    calls = []
    monkeypatch.setattr(core, "translate_batch", _fake_translate(calls))
    src = _mod(tmp_path / "mod" / "localization",
               {"french/ev_l_french.yml": 'l_french:\n greet:0 "Bonjour $NAME$"\n title:0 "Le conseil a approuvé la loi"\n',
                "simp_chinese/ev_l_simp_chinese.yml": ZH})
    for target in ("korean", "japanese"):
        out = tmp_path / target
        core.run_translation(src, out, target_lang=target, verbose=False, auto_qa=False, dual_source=True)
        calls.clear()
        core.run_translation(src, out, target_lang=target, verbose=False, auto_qa=False, dual_source=True)
        assert calls == [], target


def test_dual_source_with_english_source_keeps_the_same_cache_key(tmp_path, monkeypatch):
    """英語の原文の英中併用は、キャッシュのキー（参考訳込み）が今までどおりで、2回目も当たる。"""
    calls = []
    monkeypatch.setattr(core, "translate_batch", _fake_translate(calls))
    src = _mod(tmp_path / "mod" / "localization", {"english/ev_l_english.yml": EN, "simp_chinese/ev_l_simp_chinese.yml": ZH})
    out = tmp_path / "ja"
    core.run_translation(src, out, verbose=False, auto_qa=False, dual_source=True)
    cache = core.load_cache(out / core.CACHE_FILE_NAME)
    expected = core.translation_cache_key("Ollama", core.DEFAULT_MODEL, "General", "english", "Hello there $NAME$",
                                          dual_source=True, zh_ref="你好 $NAME$")
    assert expected in cache
    calls.clear()
    core.run_translation(src, out, verbose=False, auto_qa=False, dual_source=True)
    assert calls == []


def test_chinese_check_from_v0_11_81_applies_only_to_japanese_targets():
    zh = "议会通过了新法律，并决定扩大铁路建设。"
    assert core.unusable_translation("The council passed the law.", zh, "english", "japanese") is True
    assert core.unusable_translation("The council passed the law.", zh, "english", "simp_chinese") is False
    assert core.cache_entry_is_valid("The council passed the law.", zh, "english", "simp_chinese")
    assert core.foreign_in_output(zh, "simp_chinese") is False
    # 韓国語は文字の種類の判定で中国語を弾く（v0.12.0）
    assert core.unusable_translation("The council passed the law.", zh, "english", "korean") is True
    assert not [i for i in core.qa_entries({"a": zh}, {"a": "The council passed the law."}, "english",
                                           target_lang="simp_chinese") if i["severity"] == "error"]
