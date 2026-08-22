from __future__ import annotations

from pathlib import Path

import translator_core as core


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_placeholder_round_trip():
    original = "Text $NAME$ [GetValue] £gold£ #P green#! \\n next"
    protected, tokens = core.protect_text(original)
    assert core.restore_text(protected, tokens) == original


def test_multilingual_gap_scan_ignores_dynamic_only_values(tmp_path):
    root = tmp_path / "TestMod" / "localization"
    _write(root / "english" / "test_l_english.yml", "l_english:\n key_a:0 \"Hello $NAME$\"\n key_b:0 \"Only English\"\n key_dyn:0 \"$VALUE$\"\n")
    _write(root / "simp_chinese" / "test_l_simp_chinese.yml", "l_simp_chinese:\n key_a:0 \"你好 $NAME$\"\n key_c:0 \"仅中文\"\n key_dyn:0 \"$VALUE$\"\n")
    _write(root / "japanese" / "test_l_japanese.yml", "l_japanese:\n key_a:0 \"こんにちは $NAME$\"\n key_c:0 \"仅中文\"\n")

    gaps = core.scan_translation_gaps(root)
    assert [(item["key"], item["source_origin"]) for item in gaps] == [("key_b", "english_only")]

    status = core.analyze_mod_translation_status(root.parent)
    assert status["status"] == "欠損あり"
    assert status["gap_count"] == 1


def test_qa_detects_protected_token_mismatch():
    issues = core.qa_entries(
        {"key_a": "こんにちは $WRONG$"},
        {"key_a": "Hello $NAME$"},
        "english",
    )
    assert any(issue["type"] == "syntax" and issue["severity"] == "error" for issue in issues)
