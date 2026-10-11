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
