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
    # 中国語の参考訳は翻訳先が中国語のときは付けない。中国語基準翻訳は日本語専用
    assert "ZH_REF" not in core.build_system_prompt("english", dual_source=True, target_lang="simp_chinese")
    assert "ZH_REF" in core.build_system_prompt("english", dual_source=True, target_lang="french")
    assert "中国語基準" not in core.build_system_prompt("simp_chinese", chinese_basis=True, target_lang="korean")


def test_non_japanese_proofreading_prompt(monkeypatch):
    sent = []
    monkeypatch.setattr(core, "call_llm_raw", lambda _p, _u, _m, user, system, **_k: sent.append((system, user)) or "Bonjour @@0@@")
    assert core.proofread_text("u", "m", "Bonjur $NAME$", "Hello $NAME$", target_lang="french") == "Bonjour $NAME$"
    system, user = sent[0]
    assert "French localization" in system and "日本語" not in system
    assert user == "Source for reference: Hello [VAR]\nFrench: Bonjur @@0@@"
