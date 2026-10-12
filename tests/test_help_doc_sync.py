"""使い方の説明書の訳が原本（日本語）とずれていないか（第3段 5-2 章）。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import help_doc_status as hs  # noqa: E402
import i18n  # noqa: E402

# 全文の訳が出そろっていなければならない言語（段階1の U8 で english、段階2で残りを足す）
REQUIRED_LANGUAGES: tuple = ("english", "simp_chinese")


def test_japanese_original_reproduces_the_v0_12_manual_layout():
    sections = i18n.japanese.help_doc.HELP_SECTIONS
    ids = [sid for sid, _ in sections]
    assert len(ids) == len(set(ids)) and ids[0] == "intro"
    assert all(body for _sid, body in sections)


def test_translated_languages_follow_the_original():
    for lang in i18n.UI_LANGUAGES:
        if lang == "japanese":
            continue
        st = hs.language_status(lang)
        if not st["translated"]:
            assert lang not in REQUIRED_LANGUAGES, f"{lang} の説明書がまだ訳されていません"
            continue
        assert st["order_ok"] and not st["missing"], (lang, st)
        assert not st["stale"], f"{lang} の訳し直しが要る節: {st['stale']}（python tools/help_doc_status.py）"


def test_stale_sections_are_detected(monkeypatch):
    english = i18n.english.help_doc
    src = hs.source_hashes()
    sections = [(sid, f"[en] {sid}") for sid in src]
    monkeypatch.setattr(english, "HELP_SECTIONS", sections)
    monkeypatch.setattr(english, "SOURCE_HASHES", dict(src))
    assert hs.language_status("english") == {"translated": True, "order_ok": True, "stale": [], "missing": []}
    changed = dict(src); changed["s10_glossary"] = "000000000000"
    monkeypatch.setattr(english, "SOURCE_HASHES", changed)
    assert hs.language_status("english")["stale"] == ["s10_glossary"]
    monkeypatch.setattr(english, "HELP_SECTIONS", sections[:-1])
    assert hs.language_status("english")["missing"] == [list(src)[-1]]


def test_help_text_in_japanese_is_the_original():
    import i18n.help as help_
    assert help_.help_text("japanese") == "".join(body for _sid, body in i18n.japanese.help_doc.HELP_SECTIONS)
    assert help_.help_title("japanese") == i18n.japanese.help_doc.HELP_TITLE


def test_help_text_falls_back_and_marks_stale_sections(monkeypatch):
    import i18n.help as help_
    src = hs.source_hashes()
    ids = list(src)
    japanese = dict(i18n.japanese.help_doc.HELP_SECTIONS)
    # 英語の訳が無い間は、どの言語でも日本語の原本
    monkeypatch.setattr(i18n.english.help_doc, "HELP_SECTIONS", [])
    monkeypatch.setattr(i18n.french.help_doc, "HELP_SECTIONS", [])
    assert help_.help_text("french") == "".join(japanese.values())
    # 英語は全部、フランス語は1節だけ訳がある。フランス語の節は原本が変わった後（ハッシュが古い）
    monkeypatch.setattr(i18n.english.help_doc, "HELP_SECTIONS", [(sid, f"[en {sid}]") for sid in ids])
    monkeypatch.setattr(i18n.english.help_doc, "SOURCE_HASHES", dict(src))
    monkeypatch.setattr(i18n.french.help_doc, "HELP_SECTIONS", [("s10_glossary", "[fr glossaire]")])
    monkeypatch.setattr(i18n.french.help_doc, "SOURCE_HASHES", {"s10_glossary": "000000000000"})
    monkeypatch.setattr(i18n.french.help_doc, "STALE_NOTICE", "[fr pas à jour]", raising=False)
    text = help_.help_text("french")
    assert "[fr pas à jour]\n[fr glossaire]" in text
    assert "[en s10_glossary]" not in text and "[en intro]" in text
    # 題も英語・日本語の順に戻る
    monkeypatch.setattr(i18n.english.help_doc, "HELP_TITLE", "[en title]", raising=False)
    monkeypatch.setattr(i18n.french.help_doc, "HELP_TITLE", "", raising=False)
    assert help_.help_title("french") == "[en title]"
    monkeypatch.setattr(i18n.english.help_doc, "HELP_TITLE", "")
    assert help_.help_title("french") == i18n.japanese.help_doc.HELP_TITLE
