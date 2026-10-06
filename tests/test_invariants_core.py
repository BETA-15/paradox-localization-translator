"""README・CHANGELOG の約束ごと（不変条件）のうち、翻訳コア側の回帰テスト。

各テストの docstring の番号は docs/invariants.md の対応表の番号と一致する。
LLM は呼ばない（translate_batch は monkeypatch で差し替える）。
"""
from __future__ import annotations

import json
from pathlib import Path


import translator_core as core


def _write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------- 構文保護

def test_all_documented_syntax_forms_are_protected_and_restored():
    """INV-02: README の「Paradoxゲーム構文を保護」に挙げた全種類を保護して戻す。"""
    source = r'[ROOT.Char.GetName] $VALUE$ £gold_icon£ @flag_uk! §Ytext§! #tooltip;x#! a\nb'
    protected, tokens = core.protect_text(source)

    for raw in ("[ROOT.Char.GetName]", "$VALUE$", "£gold_icon£", "@flag_uk!",
                "§Y", "§!", "#tooltip;x", "#!", r"\n"):
        assert raw in tokens
        assert raw not in protected
    assert core.restore_text(protected, tokens) == source


def test_restore_rescues_placeholder_with_broken_suffix():
    """INV-03: LLM がプレースホルダの記号を崩しても、番号から元の構文へ戻す。"""
    _, tokens = core.protect_text("Hello $NAME$")
    assert core.restore_text("こんにちは @@0@", tokens) == "こんにちは $NAME$"
    assert core.restore_text("こんにちは @@0", tokens) == "こんにちは $NAME$"


def test_restore_rescue_keeps_following_text():
    """INV-03: 崩れたプレースホルダの直後の訳文を消さない（v0.11.78 で修正）。"""
    _, tokens = core.protect_text("Hello $NAME$")
    assert core.restore_text("こんにちは @@0 さん", tokens) == "こんにちは $NAME$ さん"
    assert core.restore_text("こんにちは @@0さん", tokens) == "こんにちは $NAME$さん"
    assert core.restore_text("こんにちは @@0@ さん", tokens) == "こんにちは $NAME$ さん"
    assert core.restore_text("こんにちは @@0@さん", tokens) == "こんにちは $NAME$さん"


def test_unknown_placeholder_index_is_left_visible_for_qa():
    """INV-03: 存在しない番号は勝手に埋めず、QA が @@ 残りとして拾えるようにする。"""
    _, tokens = core.protect_text("Hello $NAME$")
    restored = core.restore_text("こんにちは @@5@@", tokens)
    assert "@@5@@" in restored
    assert any(issue["type"] == "placeholder"
               for issue in core.qa_entries({"k": restored}, {"k": "Hello $NAME$"}, "english"))


def test_written_values_escape_quotes_without_double_escaping(tmp_path):
    """INV-04: 訳文の " はエスケープして書き、既存の \\" は二重にしない。"""
    assert core.escape_localization_value('彼は"王"だ') == '彼は\\"王\\"だ'
    assert core.escape_localization_value('既に\\"済み\\"') == '既に\\"済み\\"'

    target = tmp_path / "a_l_japanese.yml"
    _write(target, 'l_japanese:\n key_a:0 "旧"\n')
    core.upsert_localization_values(target, {"key_a": '彼は"王"だ', "key_b": "新規"})
    _, entries, _ = core.parse_localization_file(target)
    assert entries == {"key_a": '彼は\\"王\\"だ', "key_b": "新規"}


# ---------------------------------------------------------------- 未翻訳・キャッシュ

def test_english_left_in_japanese_output_is_untranslated():
    """INV-05: 日本語訳に英語原文が残っていれば未翻訳と判定する。"""
    assert core.looks_untranslated("Declare war", "Declare war", "english") is True
    assert core.looks_untranslated("Declare war", "宣戦布告", "english") is False
    # 記号・変数だけの値は翻訳不要なので未翻訳扱いしない
    assert core.looks_untranslated("$VALUE$", "$VALUE$", "english") is False


def test_cached_english_source_is_rejected_as_bad_cache():
    """INV-06: 「翻訳成功」として英語原文がキャッシュされていても不良キャッシュとして使わない。"""
    assert core.cache_entry_is_valid("Declare war on them", "Declare war on them", "english") is False
    assert core.cache_entry_is_valid("Declare war on them", "彼らに宣戦布告する", "english") is True


def test_cache_key_changes_with_settings_that_change_output():
    """INV-07: モデル・プロバイダ・用語集・翻訳モードが違えば別のキャッシュになる。"""
    base = dict(provider="Ollama", model="m1", preset="General", source_lang="english",
                original="Hello", glossary={"Duke": "公爵"})
    key = core.translation_cache_key(**base)
    assert key == core.translation_cache_key(**base)
    for change in ({"model": "m2"}, {"provider": "LM Studio"}, {"glossary": {"Duke": "大公"}},
                   {"translation_mode": "fast"}, {"original": "Hello!"}, {"preset": "CK3"}):
        assert core.translation_cache_key(**{**base, **change}) != key


# ---------------------------------------------------------------- 差分翻訳・出力先

def test_source_manifest_diff_reports_added_changed_removed_and_new_files(tmp_path):
    """INV-08: Mod 更新後の新規・変更・削除キーと新規ファイルを判定する。"""
    root = tmp_path / "localization"
    _write(root / "english" / "a_l_english.yml",
           'l_english:\n same:0 "Same"\n changed:0 "Old"\n removed:0 "Gone"\n')
    old = core.build_source_manifest(root)
    _write(root / "english" / "a_l_english.yml",
           'l_english:\n same:0 "Same"\n changed:0 "New"\n added:0 "Added"\n')
    _write(root / "english" / "b_l_english.yml", 'l_english:\n fresh:0 "Fresh"\n')

    diff = core.compare_source_manifests(old, core.build_source_manifest(root))

    assert diff["counts"] == {"added": 2, "changed": 1, "removed": 1, "unchanged": 1,
                              "added_files": 1, "removed_files": 0}
    modified = next(d for d in diff["details"] if d["kind"] == "modified")
    assert (modified["added"], modified["changed"], modified["removed"]) == (["added"], ["changed"], ["removed"])


def test_missing_translation_keys_use_all_japanese_files(tmp_path):
    """INV-09: 日本語出力に無いキーだけを欠落とし、別の日本語ファイルにあるキーは欠落にしない。"""
    source = tmp_path / "src"
    output = tmp_path / "out"
    _write(source / "english" / "a_l_english.yml",
           'l_english:\n present:0 "Present"\n elsewhere:0 "Elsewhere"\n absent:0 "Absent"\n token_only:0 "$X$"\n')
    _write(output / "japanese" / "a_l_japanese.yml", 'l_japanese:\n present:0 "ある"\n')
    _write(output / "japanese" / "extra_l_japanese.yml", 'l_japanese:\n elsewhere:0 "別ファイル"\n')

    result = core.collect_missing_translation_keys(source, output, "english")

    assert result["count"] == 1
    assert result["details"][0]["keys"] == ["absent"]


def test_generated_japanese_files_never_share_source_language_folder():
    """INV-10: 生成した日本語 YAML は english / simp_chinese と同じフォルダに置かない。"""
    assert core.remap_rel_dir(Path("english/events"), "japanese") == Path("japanese/events")
    assert core.remap_rel_dir(Path("simp_chinese"), "japanese") == Path("japanese")
    assert core.remap_rel_dir(Path("."), "japanese") == Path("japanese")
    assert core.rename_for_target(Path("ev_l_english.yml"), "japanese", "english") == "ev_l_japanese.yml"
    assert core.rename_for_target(Path("plain.yml"), "japanese", "english") == "plain_l_japanese.yml"


def test_broken_json_falls_back_and_save_leaves_no_temp_file(tmp_path):
    """INV-11: 壊れた JSON は既定値で読み、保存は一時ファイルを残さず置き換える。"""
    path = tmp_path / "state.json"
    path.write_text("{broken", encoding="utf-8")
    assert core.load_json(path, {"default": True}) == {"default": True}

    core.save_json(path, {"ok": "日本語"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"ok": "日本語"}
    assert [p.name for p in tmp_path.iterdir()] == ["state.json"]


# ---------------------------------------------------------------- QA 自動修復

def test_mechanical_token_repair_only_restores_unambiguous_edge_tokens():
    """INV-14: 機械修復は位置が一意に決まる端のトークンだけ。中の欠落・入れ替わりは触らない。"""
    assert core.repair_syntax_tokens("$NAME$ wins", "勝利") == ("$NAME$勝利", True)
    assert core.repair_syntax_tokens("Gain £gold£", "獲得") == ("獲得£gold£", True)
    # 中央のトークンは挿入位置が決まらない
    assert core.repair_syntax_tokens("Give $A$ to them", "渡す") == ("渡す", False)
    # 順序の入れ替わりは直さない
    assert core.repair_syntax_tokens("$A$ and $B$", "$B$と$A$") == ("$B$と$A$", False)
    # 同じトークンが両端にあり、どちらが欠けたか決まらない
    assert core.repair_syntax_tokens("$A$ x $A$", "$A$ x") == ("$A$ x", False)


def test_auto_repair_never_changes_warnings_or_notices(tmp_path, monkeypatch):
    """INV-13: 警告・注意は自動変更せず、修復可能なエラーだけを直す。"""
    source = tmp_path / "src" / "english" / "a_l_english.yml"
    target = tmp_path / "out" / "japanese" / "a_l_japanese.yml"
    _write(source, 'l_english:\n typo:0 "Done."\n broken:0 "Broken sentence here"\n')
    _write(target, 'l_japanese:\n typo:0 "完了。。"\n broken:0 "Broken sentence here"\n only_ja:0 "独自キー"\n')
    sent = []

    def translated(_url, _model, jobs, _lang, **_kwargs):
        sent.extend(job["key"] for job in jobs)
        return ["壊れた文"] * len(jobs)

    monkeypatch.setattr(core, "translate_batch", translated)
    result = core.qa_file_with_auto_repair(
        target, source, source_lang="english",
        backup_dir=core.create_qa_repair_backup_dir(tmp_path / "bk", "t"))

    assert sent == ["broken"]
    _, entries, _ = core.parse_localization_file(target)
    assert entries["typo"] == "完了。。"
    assert entries["only_ja"] == "独自キー"
    assert entries["broken"] == "壊れた文"
    assert result["final_errors"] == 0
    assert {i["type"] for i in result["issues"]} == {"typo", "extra_key"}


def test_auto_repair_rejects_llm_output_that_breaks_tokens(tmp_path, monkeypatch):
    """INV-15: 再翻訳結果が検証（変数一致・未翻訳でない）に通らなければ書き込まない。"""
    source = tmp_path / "a_l_english.yml"
    target = tmp_path / "a_l_japanese.yml"
    _write(source, 'l_english:\n key_a:0 "Give $GOLD$ to the ruler"\n')
    _write(target, 'l_japanese:\n key_a:0 "Give $GOLD$ to the ruler"\n')
    monkeypatch.setattr(core, "translate_batch", lambda *_a, **_k: ["支配者に金を渡す"])

    result = core.qa_file_with_auto_repair(target, source, source_lang="english",
                                           backup_dir=core.create_qa_repair_backup_dir(tmp_path / "bk", "t"))

    assert core.parse_localization_file(target)[1]["key_a"] == "Give $GOLD$ to the ruler"
    assert result["repaired"] == 0
    assert any(e["result"] == "rejected_by_validation" for e in result["events"])


def test_auto_repair_rolls_back_when_errors_do_not_decrease(tmp_path, monkeypatch):
    """INV-16: 修復後にエラーが減らなければ、修復前のファイルへ差し戻す。"""
    source = tmp_path / "a_l_english.yml"
    target = tmp_path / "a_l_japanese.yml"
    _write(source, 'l_english:\n key_a:0 "English sentence here"\n')
    original = 'l_japanese:\n key_a:0 "English sentence here"\n'
    _write(target, original)
    state = {"updated": False}
    real_qa_file = core.qa_file

    def translated(*_a, **_k):
        state["updated"] = True
        return ["日本語の文"]

    def qa_with_new_error(*args, **kwargs):
        issues = real_qa_file(*args, **kwargs)
        if state["updated"]:
            # 修復で別の（修復できない）エラーが生じた状況を作る
            issues.append({"key": "other", "severity": "error", "type": "untranslated", "repairable": False})
        return issues

    monkeypatch.setattr(core, "translate_batch", translated)
    monkeypatch.setattr(core, "qa_file", qa_with_new_error)
    result = core.qa_file_with_auto_repair(target, source, source_lang="english",
                                           backup_dir=core.create_qa_repair_backup_dir(tmp_path / "bk", "t"))

    assert result["rolled_back"] is True
    assert target.read_text(encoding="utf-8") == original
    assert any(e["action"] == "rollback" for e in result["events"])


def test_manual_auto_repair_removes_created_output_when_it_did_not_help(tmp_path, monkeypatch):
    """INV-16: 新しく作った日本語出力でエラーが減らなければ、その出力を消す。"""
    source = tmp_path / "src" / "english" / "a_l_english.yml"
    target = tmp_path / "out" / "japanese" / "a_l_japanese.yml"
    _write(source, 'l_english:\n key_a:0 "English sentence here"\n')
    monkeypatch.setattr(core, "translate_batch", lambda *_a, **_k: ["English sentence here"])

    result = core.auto_repair_qa_pairs(
        [{"source_file": str(source), "target_file": str(target), "source_language": "english"}],
        backup_root=tmp_path / "bk")

    assert not target.exists()
    assert result["files"][0]["rolled_back"] is True


def test_glossary_term_missing_from_translation_is_a_warning_not_an_error():
    """INV-51: 用語集の訳語が訳文に無ければ警告にする（自動修復の対象にはしない）。"""
    issues = core.qa_entries({"k": "大公が来た"}, {"k": "The Duke arrives"}, "english",
                             glossary={"Duke": "公爵"})
    term = [i for i in issues if i["type"] == "term_mismatch"]
    assert len(term) == 1
    assert term[0]["severity"] == "warning" and term[0]["repairable"] is False
    assert not [i for i in core.qa_entries({"k": "公爵が来た"}, {"k": "The Duke arrives"}, "english",
                                           glossary={"Duke": "公爵"}) if i["type"] == "term_mismatch"]
