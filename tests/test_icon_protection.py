"""HOI4 の £ のアイコンを1つの変数として守る（v0.12.0）。"""
from __future__ import annotations

import translator_core as core


def test_closed_open_framed_and_consecutive_icons_are_single_tokens():
    assert core.extract_protected_tokens("£gold£ gain") == ["£gold£"]
    assert core.extract_protected_tokens("£command_power §H100§!") == ["£command_power", "§H", "§!"]
    assert core.extract_protected_tokens("£command_power. Spend it") == ["£command_power"]
    assert core.extract_protected_tokens("£resources_strip|5 Steel") == ["£resources_strip|5"]
    assert core.extract_protected_tokens("£resources_strip|1£ Oil") == ["£resources_strip|1£"]
    assert core.extract_protected_tokens("£KR_flag_AUS  £KR_flag_HUN_habsburg  The Ausgleich of 1937") == \
        ["£KR_flag_AUS", "£KR_flag_HUN_habsburg"]
    assert core.extract_protected_tokens("£trigger_no£Not researched") == ["£trigger_no£"]


def test_protect_and_restore_round_trip_keeps_icon_names_away_from_the_llm():
    text = "£KR_flag_AUS  £KR_flag_HUN_habsburg  The Ausgleich of 1937"
    protected, tokens = core.protect_text(text)
    assert protected == "@@0@@  @@1@@  The Ausgleich of 1937"
    assert core.restore_text(protected, tokens) == text


def test_pound_sign_as_currency_is_kept_verbatim():
    # 実際の Mod とゲームの英語には通貨の £ は無かったが、念のため：数字は変数として守られ、そのまま残る
    protected, tokens = core.protect_text("It costs £500 a year")
    assert tokens == ["£500"] and core.restore_text(protected, tokens) == "It costs £500 a year"
    assert core.extract_protected_tokens("Price: £ 5") == []


def test_qa_reports_a_translated_icon_name_as_a_syntax_error():
    issues = core.qa_entries({"cp": "£poder_de_mando §H100§!"}, {"cp": "£command_power §H100§!"}, "english",
                             target_lang="spanish")
    assert any(i["type"] == "syntax" and i["severity"] == "error" for i in issues)
    issues = core.qa_entries({"cp": "£command_power §H100§!を使う"}, {"cp": "£command_power §H100§!"}, "english")
    assert not any(i["type"] == "syntax" for i in issues)
