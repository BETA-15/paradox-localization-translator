from __future__ import annotations

from pathlib import Path
import json

import translator_core as core


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_placeholder_round_trip():
    original = "Text $NAME$ [GetValue] £gold£ #P green#! \\n next"
    protected, tokens = core.protect_text(original)
    assert core.restore_text(protected, tokens) == original


def test_decode_mixed_utf8_and_utf16le_bom():
    source = 'l_english:\r\n key_a:0 "Hello"\r\n'
    data = b"\xef\xbb\xbf" + source.encode("utf-16")

    text, encoding = core.decode_text_bytes(data)

    assert text == source
    assert encoding == "utf-8-bom+utf-16-le"


def test_run_translation_recovers_mixed_bom_and_normalizes_output(tmp_path):
    source = tmp_path / "input" / "english" / "mixed_l_english.yml"
    source.parent.mkdir(parents=True)
    text = 'l_english:\r\n dynamic_only:0 "$VALUE$"\r\n'
    source.write_bytes(b"\xef\xbb\xbf" + text.encode("utf-16"))
    output = tmp_path / "output"

    result = core.run_translation(source.parent.parent, output, auto_qa=False, verbose=False)

    generated = output / "japanese" / "mixed_l_japanese.yml"
    assert result["processed"] == 1
    assert result["skipped"] == 0
    assert len(result["encoding_recoveries"]) == 1
    assert generated.read_bytes().startswith(b"\xef\xbb\xbf")
    assert "l_japanese:" in generated.read_text(encoding="utf-8-sig")


def test_run_translation_skips_unreadable_file_and_continues(tmp_path):
    root = tmp_path / "input" / "english"
    _write(root / "good_l_english.yml", 'l_english:\n dynamic_only:0 "$VALUE$"\n')
    bad = root / "bad_l_english.yml"
    bad.write_bytes(b"\xff\x00\xff")
    output = tmp_path / "output"

    result = core.run_translation(root.parent, output, auto_qa=False, verbose=False)

    assert result["processed"] == 1
    assert result["skipped"] == 1
    assert result["file_errors"][0]["file"] == str(bad)
    assert (output / "japanese" / "good_l_japanese.yml").exists()
    report = json.loads((output / "translation_error_report.json").read_text(encoding="utf-8"))
    assert report["summary"]["skipped_files"] == 1
    assert report["file_errors"][0]["action"] == "スキップして継続"

    _write(bad, 'l_english:\n repaired_dynamic:0 "$VALUE$"\n')
    retried = core.run_translation(root.parent, output, auto_qa=False, verbose=False)
    report = json.loads((output / "translation_error_report.json").read_text(encoding="utf-8"))
    assert retried["skipped"] == 0
    assert report["history_summary"]["attempts"] == 2
    assert report["history_summary"]["recovered_on_latest_retry"] is True
    assert report["attempts"][0]["file_errors"][0]["file"] == str(bad)


def test_provider_failure_defers_remaining_jobs_without_retrying_every_key(tmp_path, monkeypatch):
    source = tmp_path / "source_l_english.yml"
    _write(source, "l_english:\n" + "".join(
        f' key_{i}:0 "English sentence number {i}"\n' for i in range(5)
    ))
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(1)
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(core, "translate_batch", unavailable)
    result = core.process_file(
        source, tmp_path / "out.yml", "http://invalid", "model", "japanese",
        {}, 1, False, batch_size=2,
    )

    assert len(calls) == 1
    assert result["jobs"] == 5
    assert result["failed"] == 5
    assert all("provider unavailable" in item["reason"] for item in result["failed_jobs"])


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
