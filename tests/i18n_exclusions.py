"""第3段：訳してはいけない日本語の文字列（走査テスト tests/test_i18n_scan.py が数えない）。

増やすときは、理由をコメントに書くこと。
"""

# 1. 中身をまるごと訳さない関数（LLM への指示文・判定の手がかり）。v0.12 のスナップショットテストで固定しているもの。
EXCLUDED_OWNERS = {
    "app/translator_core.py": {
        "build_system_prompt",              # LLM への指示文（日本語は一字一句固定）
        "proofread_text",                   # 校正の指示文
        "resolve_auto_glossary_conflicts",  # 用語統一の指示文
        "classify_monitor_candidates",      # 軽量QAの指示文
        "benchmark_model",                  # ベンチマークの指示文
        "_is_probable_specific_glossary_term",  # 判定の手がかり（日本語の称号の一覧）
        "typo_checks",                      # 判定の手がかり（日本語の誤字の正規表現）。message は U9 で別に扱う
        "_looks_like_untranslated_chinese_sentence",  # 判定の手がかり（中国語の字）
        "looks_like_chinese_in_japanese",   # 判定の手がかり（中国語の字と機能語）
        "_is_katakana_word_char",           # 判定の手がかり（カタカナ）
        "_classify_glossary_term_kind",     # 判定の手がかり（中国語の動詞）
        "_is_auto_glossary_source_candidate",  # 判定の手がかり（句点）
        "_relation_name_tokens",            # 判定の手がかり（名前の語）
    },
    "app/main.py": set(),
}

# 2. ディスク上の名前・保存して比べている値・内部の ID（訳すと、利用者のフォルダや保存したジョブが読めなくなる）
EXCLUDED_VALUES = {
    # フォルダ・ファイルの名前（v0.11.69 の移行処理と利用者のフォルダがこの名前を前提にしている）
    "設定", "翻訳結果", "キャッシュ", "バックアップ", "ログ", "作業データ", "QA", "エラー", "日本語化Mod判定", "診断",
    "夜間処理", "システム・履歴", "QA自動修復", "差分翻訳", "上書き", "復元前退避", "総合診断", "中国語基準翻訳",
    "保存場所コピー", "_差分上書き", "_不足分上書き", "ゲーム未特定",
    # 保存して比べている値（翻訳状況の判定の結果。translator_core が作り、ui_status.display_status で表示する）
    "不明", "対象なし", "翻訳あり", "別Modで完全翻訳", "別Mod翻訳・欠損", "翻訳なし", "欠損あり",
    "要確認（旧式日本語化）", "要確認（関連元未特定）",
    # 内部の ID
    "本体/日本語化Mod統合",
}

# 3. 日本語の文字列と比べてよい所（保存した値・フォルダの名前・判定の手がかりとの比較）。(ファイル, 関数, 比べている式の一部)
ALLOWED_COMPARISONS = {
    ("app/main.py", "_create_full_localization_snapshot", "category =="),
    ("app/main.py", "_next_overwrite_backup_generation", "category') !="),
    ("app/main.py", "_next_overwrite_backup_generation", "d.name in"),
    ("app/main.py", "_base_game_source_data_for_mod", "ゲーム未特定"),
    ("app/main.py", "_apply_translation_status_restore_resolution", "ゲーム未特定"),
    ("app/main.py", "_queue_item_is_completed", "完了"),
    ("app/main.py", "_queue_item_is_completed", "上書き済み"),
    ("app/main.py", "_reset_item_for_full_translation", "差分"),
    ("app/main.py", "restore_session", "翻訳中"),
    ("app/main.py", "change_data_root", "保存場所コピー"),
    ("app/main.py", "_collect_backup_restore_entries_background", "上書き'"),
    ("app/main.py", "_refresh_diagnostic_action_state", "本体/日本語化Mod統合"),
    ("app/main.py", "queue_all_except_selected_mods", "翻訳あり"),
    ("app/main.py", "_apply_data_root_change", "設定"),
    ("app/translator_core.py", "_is_katakana_word_char", "ーヽヾ"),
    ("app/translator_core.py", "_classify_glossary_term_kind", "增加"),
}
