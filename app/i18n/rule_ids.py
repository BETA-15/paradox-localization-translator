"""QA の rule_id の日本語の説明（第3段 2-3 章の5番）。

利用者のログは画面の言語で書かれる。著者が報告を読むときの手がかりとして、診断の ZIP に rule_ids_ja.txt を同梱する。
新しい rule_id を足したら、ここにも足す（tests/test_i18n_rule_ids.py が見張る）。
"""

RULE_IDS_JA = {
    "QA-SPACE-001": "文字の間に余分な半角スペースがある（cjk_space・注意）",
    "QA-UNTRANSLATED-EN-001": "原文を指定せずに見つけた英語（または中国語）の未翻訳候補（untranslated・エラー）",
    "QA-UNTRANSLATED-EN-002": "原文が未翻訳のまま残っている（untranslated・エラー・再翻訳で直せる）",
    "QA-UNTRANSLATED-ZH-001": "簡体字中国語の原文が未翻訳のまま残っている（untranslated・エラー・再翻訳で直せる）",
    "QA-TYPO-001": "誤字・括弧の数の不一致などの表記の疑い（typo・警告）",
    "QA-PLACEHOLDER-001": "内部プレースホルダ @@N@@ が残っている（placeholder・エラー）",
    "QA-PROPER-NOUN-001": "原文と同じ表記だが固有名詞の可能性がある（proper_noun_untranslated・注意）",
    "QA-SAME-AS-SOURCE-001": "日本語以外で原文と同じ表記。既存の未翻訳エラー・固有名詞候補・略語・数字や記号のみ・3文字以下は除く（same_as_source・警告）",
    "QA-SCRIPT-HAN-001": "中国語・日本語以外の訳文に漢字が混入（script_han・警告。韓国語の直前がハングルの括弧内添え書きは注意）",
    "QA-SCRIPT-KANA-001": "日本語以外の訳文にかなが混入（script_kana・警告）",
    "QA-SCRIPT-HANGUL-001": "韓国語以外の訳文にハングルが混入（script_hangul・警告。日本語への追加は保留）",
    "QA-SCRIPT-CYRILLIC-001": "ロシア語以外の訳文にキリル文字が混入（script_cyrillic・ラテン文字言語は警告、中国語・韓国語は注意。日本語への追加は保留）",
    "QA-ENGLISH-LEFT-001": "訳文に英語の残りが疑われる（english_left・注意。英語・日本語は対象外）",
    "QA-TOKEN-001": "ゲーム変数・タグが原文と一致しない（syntax・エラー・修復できる）",
    "QA-TERM-001": "用語集の指定が訳文に反映されていない（term_mismatch・警告）",
    "QA-MISSING-KEY-001": "訳文側にキーが無い（missing_key・エラー・追加できる）",
    "QA-EXTRA-KEY-001": "原文側に無いキーがある（extra_key・警告）",
}


def rule_ids_ja_text() -> str:
    """診断の ZIP に入れる rule_ids_ja.txt の中身。"""
    lines = ["# rule_id とその意味（日本語）。ログの文は利用者の画面の言語で書かれています。", ""]
    lines += [f"{rule_id}\t{text}" for rule_id, text in sorted(RULE_IDS_JA.items())]
    return "\n".join(lines) + "\n"
