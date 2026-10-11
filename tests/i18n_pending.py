"""第3段：まだ辞書に移していない日本語の文字列の数（関数ごと）。走査テストは、これより増えないことを確かめる。

各単位は、自分の関数の文字列を t() に移したら、その行を消す（0 にする）。全部消えたら第3段の段階1は終わり。
訳してはいけないものは tests/i18n_exclusions.py に入れる（理由を書く）。
"""

PENDING = {
    # ---- P0_shared（この単位の行だけを直す。ほかの単位の塊には触らない）
    # 外部LLMエラーの判定語。「モデル」は他単位の画面ラベルにも使うため、全体除外しない。
    'app/main.py::_llm_connection_alert_content': ('P0_shared', 1),

    # ---- U1_translate_queue（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U2_chinese（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U3_review_diff_search（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U4_glossary（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U5_models_settings（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U6_status_mods（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U7_diag_backup（この単位の行だけを直す。ほかの単位の塊には触らない）

    # ---- U9_core（この単位の行だけを直す。ほかの単位の塊には触らない）
    'app/translator_core.py::<module>': ('U9_core', 24),
    'app/translator_core.py::_external_gap_candidates': ('U9_core', 3),
    'app/translator_core.py::_normalize_mod_name_for_match': ('U9_core', 2),
    'app/translator_core.py::_translation_mod_weight': ('U9_core', 22),
    'app/translator_core.py::_translation_mod_weight_legacy': ('U9_core', 25),
    'app/translator_core.py::analyze_mod_translation_status': ('U9_core', 10),
    'app/translator_core.py::apply_translation_warning_status': ('U9_core', 1),
    'app/translator_core.py::auto_repair_qa_pairs': ('U9_core', 3),
    'app/translator_core.py::build_relation_report': ('U9_core', 41),
    'app/translator_core.py::call_llm_raw': ('U9_core', 3),
    'app/translator_core.py::classify_paratranz_glossary': ('U9_core', 1),
    'app/translator_core.py::classify_paratranz_glossary.add_source': ('U9_core', 9),
    'app/translator_core.py::compare_localization_entries': ('U9_core', 4),
    'app/translator_core.py::discover_paradox_mod_locations': ('U9_core', 1),
    'app/translator_core.py::embedding_only_model_warning': ('U9_core', 1),
    'app/translator_core.py::game_language_warning': ('U9_core', 3),
    'app/translator_core.py::gap_reason_text': ('U9_core', 5),
    'app/translator_core.py::glossary_file_problem': ('U9_core', 6),
    'app/translator_core.py::looks_like_proper_noun_candidate': ('U9_core', 2),
    'app/translator_core.py::mod_location_kind': ('U9_core', 1),
    'app/translator_core.py::normalize_cjk_spacing': ('U9_core', 1),
    'app/translator_core.py::normalize_provider': ('U9_core', 1),
    'app/translator_core.py::process_file': ('U9_core', 9),
    'app/translator_core.py::qa_chinese_basis_translation': ('U9_core', 1),
    'app/translator_core.py::qa_entries': ('U9_core', 23),
    'app/translator_core.py::qa_file_with_auto_repair': ('U9_core', 1),
    'app/translator_core.py::qa_translation_output': ('U9_core', 1),
    'app/translator_core.py::rank_external_japanese_translations': ('U9_core', 2),
    'app/translator_core.py::reasoning_model_warning_text': ('U9_core', 1),
    'app/translator_core.py::relation_report_csv': ('U9_core', 4),
    'app/translator_core.py::relation_report_markdown': ('U9_core', 29),
    'app/translator_core.py::run_chinese_basis_translation': ('U9_core', 3),
    'app/translator_core.py::run_translation': ('U9_core', 15),
    'app/translator_core.py::run_translation.collect_file_error': ('U9_core', 1),
    'app/translator_core.py::save_paratranz_import': ('U9_core', 4),
    'app/translator_core.py::scan_translation_gaps': ('U9_core', 7),
    'app/translator_core.py::source_language_gap_reason_text': ('U9_core', 3),
    'app/translator_core.py::thinking_only_model_warning': ('U9_core', 1),
    'app/translator_core.py::translation_localization_format_profile': ('U9_core', 2),
    'app/translator_core.py::translation_localization_warnings': ('U9_core', 2),
    'app/translator_core.py::translation_relation_evidence': ('U9_core', 2),
}
