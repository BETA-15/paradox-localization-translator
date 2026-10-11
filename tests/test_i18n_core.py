"""第3段：画面の文字列の辞書の仕組み（app/i18n）。"""
from __future__ import annotations

import i18n


def setup_function(_fn):
    i18n.MISSING.clear(); i18n.UNKNOWN.clear(); i18n.set_ui_language("japanese")


def test_lookup_order_selected_then_english_then_japanese(monkeypatch):
    monkeypatch.setitem(i18n.strings("japanese"), "test.a", "日本語A")
    monkeypatch.setitem(i18n.strings("english"), "test.a", "English A")
    monkeypatch.setitem(i18n.strings("japanese"), "test.only_ja", "日本語だけ")
    i18n.set_ui_language("french")
    assert i18n.t("test.a") == "English A"
    assert i18n.t("test.only_ja") == "日本語だけ"
    assert i18n.t("test.nowhere") == "test.nowhere"
    assert i18n.MISSING["test.a"] == 1 and i18n.UNKNOWN["test.nowhere"] == 1
    i18n.set_ui_language("japanese")
    assert i18n.t("test.a") == "日本語A"


def test_named_fields_and_missing_fields(monkeypatch):
    monkeypatch.setitem(i18n.strings("japanese"), "test.count", "用語集 {count}件を読み込みました")
    assert i18n.t("test.count", count=3) == "用語集 3件を読み込みました"
    assert i18n.t("test.count") == "用語集 {count}件を読み込みました"
    assert i18n.t("test.count", other=1) == "用語集 {count}件を読み込みました"


def test_unknown_language_falls_back_to_english():
    assert i18n.set_ui_language("klingon") == "english"


def test_every_language_package_has_every_unit_and_help_doc():
    for lang in i18n.UI_LANGUAGES:
        assert isinstance(i18n.strings(lang), dict)
        assert lang in i18n.NATIVE_NAMES


def test_os_locale_values_map_to_ui_languages():
    cases = {"ja": "japanese", "ja_JP.UTF-8": "japanese", "ja-JP": "japanese", "en-US": "english",
             "zh-Hans-CN": "simp_chinese", "zh_CN.UTF-8": "simp_chinese", "zh-Hant-TW": None, "zh_TW": None,
             "pt-BR": "braz_por", "pt_PT": "braz_por", "de_DE": "german", "fr-CA": "french", "es-419": "spanish",
             "ko-KR": "korean", "pl_PL": "polish", "ru": "russian", "tr-TR": "turkish", "it-IT": None, "C": None}
    for value, expected in cases.items():
        assert i18n.language_from_locale(value) == expected, value


def test_detect_os_language_uses_the_first_preferred_language():
    assert i18n.detect_os_language(values=["ko-KR", "en-US"]) == "korean"
    assert i18n.detect_os_language(values=["zh-Hant-TW", "ja-JP"]) == "english"  # 繁体字は11言語に無い → 英語
    assert i18n.detect_os_language(values=["C", "ja_JP.UTF-8"]) == "japanese"
    assert i18n.detect_os_language(values=[]) == "english"
    assert i18n.detect_os_language(platform="linux", env={"LANG": "de_DE.UTF-8"}) == "german"


def test_initial_ui_language_keeps_existing_users_on_japanese():
    assert i18n.initial_ui_language("french", True) == "french"
    assert i18n.initial_ui_language(None, True, detect=lambda: "german") == "japanese"
    assert i18n.initial_ui_language(None, False, detect=lambda: "german") == "german"
    assert i18n.initial_ui_language("klingon", False, detect=lambda: "english") == "english"
