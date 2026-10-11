"""保存して比べている状態の値と表示を分ける（第3段 2-3 章）。古い版で保存した値も読めること。"""
from __future__ import annotations

import i18n
import ui_status as us

EXAMPLES = {
    "waiting": {}, "translating": {}, "interrupted_resumable": {}, "done": {}, "done_warnings": {"count": 3},
    "done_unresolved": {"skipped": 2, "failed": 5}, "warn_retry": {"failed": 4},
    "diff_added_changed_missing": {"added": 1, "changed": 2, "missing": 3}, "gap_fill": {"missing": 7},
    "done_lang_chinese": {"count": 9}, "overwritten": {}, "mod_gaps": {}, "mod_review_legacy": {},
}

# v0.12.0 までに保存された値（実際の文字列）
LEGACY = ["待機", "翻訳中", "中断（再開可）", "完了", "完了（警告 3件）", "警告あり（2ファイルスキップ・翻訳失敗5件・再試行予定）",
          "完了（未解決: 翻訳失敗4件）", "差分 +1 / 変更2 / 欠損3", "欠損補完 7", "完了（中国語側完了・英語欠損9）",
          "上書き済み", "翻訳あり", "別Mod翻訳・欠損", "要確認（関連元未特定）"]


def setup_function(_fn):
    i18n.set_ui_language("japanese")


def test_values_round_trip_and_japanese_display_is_unchanged():
    for key in us.STATUS_VALUES:
        fields = EXAMPLES.get(key, {k: 1 for k in __import__("re").findall(r"\{(\w+)\}", us.STATUS_VALUES[key])})
        value = us.status_value(key, **fields)
        parsed_key, _ = us.parse_status(value)
        assert parsed_key == key, (key, value)
        assert us.display_status(value) == value, key  # 日本語の画面の表示は保存の値と同じ


def test_legacy_saved_values_are_recognized_and_shown_in_english():
    i18n.set_ui_language("english")
    for value in LEGACY:
        key, _ = us.parse_status(value)
        assert key is not None, value
        shown = us.display_status({"status": value})
        assert shown and not __import__("re").search(r"[ぁ-んァ-ヶ一-龯]", shown), (value, shown)
    assert us.display_status("警告あり（2ファイルスキップ・翻訳失敗5件・再試行予定）") == \
        "Warnings (2 files skipped, 5 translations failed; will retry)"
    assert us.display_status("未来の版の状態") == "未来の版の状態"


def test_status_values_are_exactly_the_legacy_strings():
    assert us.status_value("warn_retry", skipped=2, failed=5) == "警告あり（2ファイルスキップ・翻訳失敗5件・再試行予定）"
    assert us.status_value("done_unresolved", failed=4) == "完了（未解決: 翻訳失敗4件）"
    assert us.status_value("diff_added_changed", added=1, changed=0) == "差分 +1 / 変更0"
    assert us.status_value("done_lang_normal", count=2) == "完了（通常側完了・中国語欠損2）"


def test_close_action_and_performance_preset_mapping_reads_old_and_new_values():
    for label, action in (("毎回確認", "confirm"), ("最小化", "minimize"), ("終了", "quit"), ("quit", "quit")):
        assert us.close_action_from_label(label) == action
    i18n.set_ui_language("english")
    assert us.close_action_label("minimize") == "Minimize" and us.close_action_from_label("Minimize") == "minimize"
    assert us.performance_preset_from_label("高速（60 / 2）") == "fast"
    assert us.performance_preset_label("stable") == "Stable (20 / 1)"
    assert us.performance_preset_from_label("Stable (20 / 1)") == "stable"
    i18n.set_ui_language("japanese")
    assert us.performance_preset_label("standard") == "標準（40 / 1）"
