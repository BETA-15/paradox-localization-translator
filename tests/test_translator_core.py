from __future__ import annotations

from pathlib import Path
import json

import translator_core as core


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_detect_mod_name_supports_victoria3_metadata(tmp_path):
    root = tmp_path / "2941539986"
    metadata = root / ".metadata" / "metadata.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"name": "Laws +", "id": "2941539986"}), encoding="utf-8")

    assert core.detect_mod_name(root) == "Laws +"


def test_detect_mod_name_keeps_legacy_descriptor_priority(tmp_path):
    root = tmp_path / "LegacyMod"
    _write(root / "descriptor.mod", 'name="Descriptor Name"\n')
    metadata = root / ".metadata" / "metadata.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(json.dumps({"name": "Metadata Name"}), encoding="utf-8")

    assert core.detect_mod_name(root) == "Descriptor Name"


def test_detect_mod_name_falls_back_when_metadata_is_invalid(tmp_path):
    root = tmp_path / "Workshop123"
    metadata = root / ".metadata" / "metadata.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text("{not valid json", encoding="utf-8")

    assert core.detect_mod_name(root) == "Workshop123"


def test_detect_mod_name_recovers_name_from_victoria3_metadata_with_unescaped_windows_path(tmp_path):
    root = tmp_path / "3276835261"
    metadata = root / ".metadata" / "metadata.json"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        '{\n  "name": "Joinable Powerblocks",\n'
        '  "path": "C:\\Users\\Admin\\Documents\\Victoria 3\\mod"\n}\n',
        encoding="utf-8",
    )

    assert core.detect_mod_name(root) == "Joinable Powerblocks"


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


def test_qa_downgrades_unchanged_chinese_proper_name_to_warning():
    issues = core.qa_entries(
        {"dynn_Liu": "这是刘氏家族的名称"}, {"dynn_Liu": "这是刘氏家族的名称"}, "simp_chinese",
        source_path=Path("localization/simp_chinese/dynasties/test_l_simp_chinese.yml"),
    )

    assert any(issue["type"] == "proper_noun_untranslated" and issue["severity"] == "warning"
               for issue in issues)
    assert not any(issue["type"] == "untranslated" and issue["severity"] == "error"
                   for issue in issues)


def test_qa_keeps_unchanged_chinese_sentence_as_repairable_error():
    issues = core.qa_entries(
        {"event_description": "这是尚未翻译的完整句子。"},
        {"event_description": "这是尚未翻译的完整句子。"},
        "simp_chinese", source_path=Path("localization/simp_chinese/events/test.yml"),
    )

    issue = next(item for item in issues if item["type"] == "untranslated")
    assert issue["severity"] == "error"
    assert issue["repairable"] is True


def test_auto_qa_repair_backs_up_retranslates_and_adds_missing_key(tmp_path, monkeypatch):
    source = tmp_path / "source" / "simp_chinese" / "events_l_simp_chinese.yml"
    target = tmp_path / "output" / "japanese" / "events_l_japanese.yml"
    _write(source, 'l_simp_chinese:\n event_text:0 "这是尚未翻译的内容 $NAME$"\n missing_text:0 "缺少内容"\n')
    _write(target, 'l_japanese:\n event_text:0 "这是尚未翻译的内容 $NAME$"\n')

    def translated(_url, _model, jobs, _source_lang, **_kwargs):
        values = {"event_text": "こんにちは @@0@@", "missing_text": "不足内容"}
        return [values[job["key"]] for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translated)
    backup_dir = core.create_qa_repair_backup_dir(tmp_path / "backups", "test")
    result = core.qa_file_with_auto_repair(
        target, source, source_lang="simp_chinese", backup_dir=backup_dir,
        backup_relative_root=tmp_path / "output", max_passes=2,
    )

    assert result["initial_errors"] == 2
    assert result["final_errors"] == 0
    assert result["repaired"] == 2
    assert Path(result["backup"]).exists()
    _, entries, _ = core.parse_localization_file(target)
    assert entries == {"event_text": "こんにちは $NAME$", "missing_text": "不足内容"}
    manifest = json.loads((backup_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"][0]["original"] == str(target)


def test_manual_auto_repair_continues_after_file_failure(tmp_path, monkeypatch):
    source = tmp_path / "source" / "english" / "events_l_english.yml"
    target = tmp_path / "output" / "japanese" / "events_l_japanese.yml"
    _write(source, 'l_english:\n event_text:0 "English sentence"\n')
    _write(target, 'l_japanese:\n event_text:0 "English sentence"\n')

    monkeypatch.setattr(core, "translate_batch", lambda *_args, **_kwargs: ["日本語文"])
    result = core.auto_repair_qa_pairs([
        {"source_file":str(source),"target_file":str(target),"source_language":"english"},
        {"source_file":str(tmp_path / "missing.yml"),"target_file":str(tmp_path / "missing_ja.yml"),"source_language":"english"},
    ],backup_root=tmp_path / "backups")

    assert result["summary"]["files"] == 2
    assert result["summary"]["completed_files"] == 1
    assert result["summary"]["failed_files"] == 1
    assert result["summary"]["final_errors"] == 0
    assert result["failures"][0]["action"] == "スキップして次のファイルを継続"
    assert Path(result["backup_dir"]).exists()


def test_manual_auto_repair_creates_missing_japanese_output(tmp_path, monkeypatch):
    source_root = tmp_path / "source"
    source = source_root / "localization" / "english" / "ui_l_english.yml"
    output = tmp_path / "output"
    _write(source, 'l_english:\n ui_key:0 "English interface text"\n')
    pairs = core.collect_translation_qa_pairs(source_root, output, ("english",))
    assert len(pairs) == 1
    target = Path(pairs[0]["target_file"])
    assert not target.exists()

    monkeypatch.setattr(core, "translate_batch", lambda *_args, **_kwargs: ["日本語インターフェース文"])
    result = core.auto_repair_qa_pairs(pairs, backup_root=tmp_path / "backups")

    assert result["summary"]["initial_errors"] == 1
    assert result["summary"]["final_errors"] == 0
    assert target.exists()
    _, entries, _ = core.parse_localization_file(target)
    assert entries == {"ui_key":"日本語インターフェース文"}
