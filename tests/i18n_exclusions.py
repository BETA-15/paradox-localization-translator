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
    # LLM接続エラーとログの判定語（表示文ではなく、外部応答の分類に使用）
    "読み込み済み", "失敗",
    # ファイル名の安全化パターンと不足分の保存フォルダ名（変更すると保存先が変わる）
    r"[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+", "不足翻訳キュー",
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


# 4. 段階1の単位ごとの追加（並行して作業するので、自分の単位の塊だけに足す。ほかの単位の塊には触らない）
#    OWNERS は (ファイル, 関数) の組、VALUES は文字列、COMPARISONS は ALLOWED_COMPARISONS と同じ形。足すときは理由をコメントに書く。

# ---- U1_translate_queue
U1_OWNERS = set()
# ---- U1_translate_queue（値）
U1_VALUES = set()
# ---- U1_translate_queue（比較）
U1_COMPARISONS = set()

# ---- U2_chinese
U2_OWNERS = set()
# ---- U2_chinese（値）
U2_VALUES = set()
# ---- U2_chinese（比較）
U2_COMPARISONS = set()

# ---- U3_review_diff_search
U3_OWNERS = set()
# ---- U3_review_diff_search（値）
U3_VALUES = set()
# ---- U3_review_diff_search（比較）
U3_COMPARISONS = set()

# ---- U4_glossary
U4_OWNERS = set()
# ---- U4_glossary（値）
U4_VALUES = set()
# ---- U4_glossary（比較）
U4_COMPARISONS = set()

# ---- U5_models_settings
U5_OWNERS = set()
# ---- U5_models_settings（値）
U5_VALUES = set()
# ---- U5_models_settings（比較）
U5_COMPARISONS = set()

# ---- U6_status_mods
U6_OWNERS = {
    # 表示文は移行済み。残るのは固定ファイル名と build_relation_report の列キーだけ。
    # 「要確認」を全体の VALUES に入れると U9 の未移行数まで変わるため、この関数だけを除外。
    ("app/main.py", "export_relation_report"),
}
# ---- U6_status_mods（値）
U6_VALUES = set()
# ---- U6_status_mods（比較）
U6_COMPARISONS = set()

# ---- U7_diag_backup
U7_OWNERS = set()
# ---- U7_diag_backup（値）
U7_VALUES = set()
# ---- U7_diag_backup（比較）
U7_COMPARISONS = set()

# ---- U8_help
U8_OWNERS = set()
# ---- U8_help（値）
U8_VALUES = set()
# ---- U8_help（比較）
U8_COMPARISONS = set()

# ---- U9_core
U9_OWNERS = set()
# ---- U9_core（値）
U9_VALUES = set()
# ---- U9_core（比較）
U9_COMPARISONS = set()

_UNITS = ((U1_OWNERS, U1_VALUES, U1_COMPARISONS), (U2_OWNERS, U2_VALUES, U2_COMPARISONS), (U3_OWNERS, U3_VALUES, U3_COMPARISONS), (U4_OWNERS, U4_VALUES, U4_COMPARISONS), (U5_OWNERS, U5_VALUES, U5_COMPARISONS), (U6_OWNERS, U6_VALUES, U6_COMPARISONS), (U7_OWNERS, U7_VALUES, U7_COMPARISONS), (U8_OWNERS, U8_VALUES, U8_COMPARISONS), (U9_OWNERS, U9_VALUES, U9_COMPARISONS))
for _owners, _values, _comparisons in _UNITS:
    for _file, _owner in _owners:
        EXCLUDED_OWNERS.setdefault(_file, set()).add(_owner)
    EXCLUDED_VALUES |= _values
    ALLOWED_COMPARISONS |= _comparisons
