"""QA の rule_id の日本語の説明（第3段 2-3 章の5番）。

利用者のログは画面の言語で書かれる。著者が報告を読むときの手がかりとして、診断の ZIP に rule_ids_ja.txt を同梱する。
新しい rule_id を足したら、ここにも足す（tests/test_i18n_rule_ids.py が見張る）。
"""

RULE_IDS_JA = {
    "QA-KO-HANJA-001": "韓国語の訳文の括弧外に漢字が残っている（korean_hanja_outside・警告）",
    "QA-KO-HANJA-002": "韓国語の訳文の括弧内に漢字の添え書きがある（korean_hanja_annotation・注意・曖昧さ回避と初出のみか確認）",
    "QA-SPACE-001": "文字の間に余分な半角スペースがある（cjk_space・注意）",
    "QA-UNTRANSLATED-EN-001": "原文を指定せずに見つけた英語（または中国語）の未翻訳候補（untranslated・エラー）",
    "QA-UNTRANSLATED-EN-002": "原文が未翻訳のまま残っている（untranslated・エラー・再翻訳で直せる）",
    "QA-UNTRANSLATED-ZH-001": "簡体字中国語の原文が未翻訳のまま残っている（untranslated・エラー・再翻訳で直せる）",
    "QA-TYPO-001": "誤字・括弧の数の不一致などの表記の疑い（typo・警告）",
    "QA-PLACEHOLDER-001": "内部プレースホルダ @@N@@ が残っている（placeholder・エラー）",
    "QA-PROPER-NOUN-001": "原文と同じ表記だが固有名詞の可能性がある（proper_noun_untranslated・注意）",
    "QA-SAME-AS-SOURCE-001": "ラテン文字の言語で原文と同じ表記（same_as_source・注意）",
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
