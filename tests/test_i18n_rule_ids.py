"""rule_id の日本語の説明（診断の ZIP の rule_ids_ja.txt）と、QA のログの ui_language（第3段 2-3 章の5番）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import i18n  # noqa: E402
import i18n.rule_ids as rule_ids  # noqa: E402


def test_every_rule_id_in_the_code_has_a_japanese_description():
    found = set()
    for name in ("translator_core.py", "main.py"):
        text = (ROOT / "app" / name).read_text(encoding="utf-8")
        found |= set(re.findall(r'"(QA-[A-Z0-9-]+-\d{3})"', text))
    assert found, "rule_id が1つも見つからない（探し方が古い）"
    assert not found - set(rule_ids.RULE_IDS_JA), f"説明の無い rule_id: {sorted(found - set(rule_ids.RULE_IDS_JA))}"


def test_rule_ids_ja_text_lists_every_rule_once():
    text = rule_ids.rule_ids_ja_text()
    for rule_id, desc in rule_ids.RULE_IDS_JA.items():
        assert text.count(f"{rule_id}\t{desc}\n") == 1


def test_qa_log_records_the_ui_language():
    import main
    previous = i18n.get_ui_language()
    try:
        i18n.set_ui_language("french")
        assert main._build_qa_log_payload([], [])["ui_language"] == "french"
        assert main._build_qa_log_payload([], [], ui_language="korean")["ui_language"] == "korean"
        payload = main._build_qa_log_payload([], [])
        assert payload["schema"] == 2  # 欄を足しただけなので数字は変えない
    finally:
        i18n.set_ui_language(previous)
