"""保存・内部の値（日本語）を、表示のときに画面の言語へ訳すこと（v0.13.1、韓国語の画面で「ローカルMod」が出た件）。"""
import pytest

import i18n
import ui_status

INTERNAL_BACKUP_KINDS = ("総合診断修復", "不足分上書き", "差分翻訳", "復元前退避", "差分上書き", "元Mod上書き", "バックアップ")


@pytest.fixture
def ui_language():
    previous = i18n.get_ui_language()
    yield i18n.set_ui_language
    i18n.set_ui_language(previous)


def test_location_kind_is_translated(ui_language):
    ui_language("korean")
    assert ui_status.location_kind_label("ローカルMod") == i18n.t("u6.location_kind.local_mod")
    assert ui_status.location_kind_label("ローカルMod") != "ローカルMod"
    assert ui_status.location_kind_label("Steam Workshop") == "Steam Workshop"
    ui_language("japanese")
    assert ui_status.location_kind_label("ローカルMod") == "ローカルMod"


@pytest.mark.parametrize("kind", INTERNAL_BACKUP_KINDS)
def test_internal_backup_kinds_are_translated(ui_language, kind):
    ui_language("japanese")
    assert ui_status.backup_kind_label(kind) == kind  # 日本語の表示は変わらない
    for lang in i18n.UI_LANGUAGES:
        if lang == "japanese":
            continue
        ui_language(lang)
        assert ui_status.backup_kind_label(kind) != kind, lang


def test_backup_kind_saved_in_another_ui_language_is_redrawn(ui_language):
    saved = i18n.t_lang("japanese", "u6.translation_mod_difference_overwrite", target_name=i18n.t_lang("japanese", "lang.korean"))
    ui_language("english")
    assert ui_status.backup_kind_label(saved) == i18n.t("u6.translation_mod_difference_overwrite", target_name=i18n.t("lang.korean"))
    assert ui_status.backup_kind_label("my own label") == "my own label"


def test_unknown_game_is_translated(ui_language):
    ui_language("korean")
    assert ui_status.game_label("ゲーム未特定") == i18n.t("u7.unknown_game")
    assert ui_status.game_label("Victoria 3") == "Victoria 3"
