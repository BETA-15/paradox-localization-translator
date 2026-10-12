import ast
import copy
import importlib.util
import inspect
import subprocess
import sys
from pathlib import Path

import pytest

import i18n
import ui_status
from app import translator_core as core


@pytest.fixture(autouse=True)
def japanese_ui():
    previous = i18n.get_ui_language()
    i18n.set_ui_language("japanese")
    yield
    i18n.set_ui_language(previous)


def make_mod(tmp_path, name, languages):
    root = tmp_path / name
    root.mkdir(parents=True)
    (root / "descriptor.mod").write_text(f'name="{name}"\n', encoding="utf-8")
    for language, entries in languages.items():
        folder = root / "localisation" / language
        folder.mkdir(parents=True)
        text = f"l_{language}:\n" + "".join(
            f' {key}:0 "{value}"\n' for key, value in entries.items())
        (folder / f"sample_l_{language}.yml").write_text(text, encoding="utf-8-sig")
    return root


def clean_result(value):
    if isinstance(value, dict):
        return {key: clean_result(item) for key, item in value.items()
                if key not in {"target_lang", "message_parts"}}
    if isinstance(value, list):
        return [clean_result(item) for item in value]
    return value


@pytest.fixture
def baseline(tmp_path):
    workspace = Path(__file__).resolve().parents[1]
    contents = subprocess.run(
        ["git", "show", "HEAD:app/translator_core.py"], cwd=workspace,
        check=True, capture_output=True, text=True, timeout=20).stdout
    path = tmp_path / "head_translator_core.py"
    path.write_text(contents, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("l4a_head_translator_core", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


@pytest.mark.parametrize("language", [language for language in core.TARGET_LANGUAGES if language != "english"])
def test_target_only_translation_links_correct_source(tmp_path, language):
    source = make_mod(tmp_path, "Synthetic Atlas", {"english": {"atlas_desc": "Build a prosperous new country"}})
    other = make_mod(tmp_path, "Synthetic Delta", {"english": {"delta_desc": "Choose another distant frontier"}})
    values = {
        "japanese": "新しい豊かな国を作る", "korean": "새로운 번영의 나라를 건설합니다",
        "russian": "Создайте новую процветающую страну", "simp_chinese": "建设一个繁荣的新国家",
        "french": "Construisez un nouveau pays prospère", "german": "Bauen Sie ein neues wohlhabendes Land",
        "spanish": "Construye un nuevo país próspero", "polish": "Zbuduj nowy dostatni kraj",
        "braz_por": "Construa um novo país próspero", "turkish": "Yeni ve müreffeh bir ülke kurun",
    }
    translation = make_mod(tmp_path, "Synthetic Atlas Translation", {language: {"atlas_desc": values[language]}})
    index = core.build_translation_mod_index([translation], target_lang=language)
    index = core.assign_translation_candidate_owners([source, other], index, target_lang=language)
    result = core.analyze_mod_translation_status(source, translation_index=index, target_lang=language)
    assert result["external_translation_path"] == str(translation)
    assert result["external_translation_complete"]
    assert result["target_lang"] == language
    assert not core.find_external_japanese_translation(other, index, target_lang=language)
    assert ui_status.build_message(result["message_parts"]) == result["message"]
    assert all(part["fields"]["target_name"] == language
               for part in result["message_parts"])
    report = core.build_relation_report([result], target_lang=language)
    markdown = core.relation_report_markdown(report, target_lang=language)
    assert i18n.t("lang." + language) + "化Mod" in markdown
    if language != "japanese":
        assert "日本語化Mod" not in markdown
        assert "日本語化Mod" not in core.relation_report_csv(report)


def test_french_source_copy_is_not_complete(tmp_path):
    entries = {"atlas_desc": "Build a prosperous new country", "atlas_label": "new government"}
    source = make_mod(tmp_path, "Synthetic Atlas", {"english": entries})
    translation = make_mod(tmp_path, "Synthetic Atlas French", {"french": entries})
    index = core.build_translation_mod_index([translation], target_lang="french")
    result = core.analyze_mod_translation_status(source, translation_index=index, target_lang="french")
    assert result["external_translation_path"] == str(translation)
    assert not result["external_translation_complete"]
    assert result["external_translation_gap_count"] == 2
    assert {gap["kind"] for gap in result["external_translation_gaps"]} == {"source_copy"}


def test_english_skips_external_matching(tmp_path, monkeypatch):
    source = make_mod(tmp_path, "Synthetic Atlas", {
        "french": {"atlas_desc": "Construisez un nouveau pays prospère"},
        "english": {"atlas_desc": "Build a prosperous new country"}})
    def forbidden(*args, **kwargs):
        pytest.fail("English targets must not perform external matching")
    monkeypatch.setattr(core, "find_external_japanese_translation", forbidden)
    monkeypatch.setattr(core, "rank_external_japanese_translations", forbidden)
    result = core.analyze_mod_translation_status(source, translation_index=[{}], target_lang="english")
    assert result["external_check_skipped"] == "english_target"
    assert result["source_keys"] == 1
    assert result["japanese_keys"] == 1
    assert result["status"] == "翻訳あり"
    assert "英語" in result["message"]
    assert not core.build_translation_mod_index([source], target_lang="english")


def test_unsupported_game_language_is_excluded(tmp_path, monkeypatch):
    source = make_mod(tmp_path, "Synthetic Atlas", {"english": {"atlas_desc": "Build a prosperous new country"}})
    translation = make_mod(tmp_path, "Synthetic Atlas Turkish", {"turkish": {"atlas_desc": "Yeni bir ülke kurun"}})
    monkeypatch.setattr(core, "game_for_translation", lambda path=None, preset="": "Hearts of Iron IV")
    result = core.analyze_mod_translation_status(source, translation_index=[{"path": str(translation)}], target_lang="turkish")
    assert result["unsupported_game_language"] is True
    assert core.game_language_warning("turkish", source) in result["message"]
    assert not result["external_translation_path"]
    assert not core.build_translation_mod_index([translation], target_lang="turkish")
    assert not core.rank_external_japanese_translations(source, [{"path": str(translation)}], target_lang="turkish")
    assert core.analyze_external_translation_coverage(source, translation, target_lang="turkish")["unsupported_game_language"]
    report = core.build_relation_report([dict(result, external_translation_mod="Synthetic Atlas Turkish")], target_lang="turkish")
    assert not report["by_translation"]


@pytest.mark.parametrize("language,source_language", [("english", "simp_chinese"), ("simp_chinese", "english"), ("french", "german")])
def test_source_excludes_target_and_falls_back(tmp_path, language, source_language):
    source = make_mod(tmp_path, "Synthetic Atlas", {
        language: {"target_only": "Only in target"},
        source_language: {"source_only": "A missing source description"}})
    gaps = core.scan_translation_gaps(source, target_lang=language)
    assert [gap["key"] for gap in gaps] == ["source_only"]
    assert gaps[0]["source_lang"] == source_language
    assert gaps[0]["source_file"]
    assert gaps[0]["source"] == "A missing source description"
    assert gaps[0]["target"] == ""


@pytest.mark.parametrize("ui_language", ["japanese", "english"])
def test_japanese_matches_head(tmp_path, baseline, ui_language, monkeypatch):
    i18n.set_ui_language(ui_language)
    english = {f"atlas_{number}": f"Build a prosperous new country number {number}" for number in range(12)}
    japanese = {key: f"新しい豊かな国を作る{number}" for number, key in enumerate(english)}
    source = make_mod(tmp_path, "Synthetic Atlas", {"english": english})
    translation = make_mod(tmp_path, "+JP Synthetic Atlas", {"japanese": japanese})
    missing = make_mod(tmp_path, "Synthetic Atlas Gaps", {"japanese": dict(list(japanese.items())[:-2])})
    partial = make_mod(tmp_path, "Synthetic Atlas Partial", {"japanese": dict(list(japanese.items())[:4])})
    internal = make_mod(tmp_path, "Synthetic Internal", {"english": english, "japanese": japanese})
    legacy = make_mod(tmp_path, "+JP Synthetic Legacy", {"english": japanese})
    roots = [source, translation, missing, partial, internal, legacy]
    for candidates in ([translation], [missing], [partial], []):
        before_index = baseline.build_translation_mod_index(candidates)
        after_index = core.build_translation_mod_index(candidates)
        assert clean_result(after_index) == clean_result(before_index)
        before_results = [baseline.analyze_mod_translation_status(root, translation_index=before_index) for root in roots]
        after_results = [core.analyze_mod_translation_status(root, translation_index=after_index) for root in roots]
        assert clean_result(after_results) == clean_result(before_results)
        before_report = baseline.build_relation_report(before_results)
        after_report = core.build_relation_report(after_results)
        assert clean_result(after_report) == clean_result(before_report)
        assert core.relation_report_markdown(after_report) == baseline.relation_report_markdown(before_report)
        for root in roots:
            assert core.scan_translation_gaps(root) == baseline.scan_translation_gaps(root)
        for candidate in candidates:
            assert clean_result(core.analyze_external_translation_coverage(source, candidate)) == clean_result(
                baseline.analyze_external_translation_coverage(source, candidate))
        for before_row, after_row in zip(before_index, after_index):
            assert core.classify_translation_candidate_role(after_row) == baseline.classify_translation_candidate_role(before_row)
            languages = {"english": english, "simp_chinese": {}}
            assert core.translation_relation_evidence(languages, after_row) == baseline.translation_relation_evidence(languages, before_row)
            assert core._translation_mod_weight("Synthetic Atlas", set(english), after_row, source_language_entries=languages) == baseline._translation_mod_weight(
                "Synthetic Atlas", set(english), before_row, source_language_entries=languages)
            assert core._translation_mod_weight_legacy("Synthetic Atlas", set(english), after_row) == baseline._translation_mod_weight_legacy(
                "Synthetic Atlas", set(english), before_row)
        assert clean_result(core.rank_external_japanese_translations(source, after_index)) == clean_result(
            baseline.rank_external_japanese_translations(source, before_index))
        assert clean_result(core.find_external_japanese_translation(source, after_index)) == clean_result(
            baseline.find_external_japanese_translation(source, before_index))
        shared_weights = baseline.relation_key_weights([set(english), set(english)])
        assert core.relation_key_weights([set(english), set(english)]) == shared_weights
        with monkeypatch.context() as patch:
            patch.setattr(core, "relation_key_weights", lambda key_sets: shared_weights)
            patch.setattr(baseline, "relation_key_weights", lambda key_sets: shared_weights)
            before_owners = baseline.assign_translation_candidate_owners([source, internal], copy.deepcopy(before_index))
            after_owners = core.assign_translation_candidate_owners([source, internal], copy.deepcopy(after_index))
        assert clean_result(after_owners) == clean_result(before_owners)


def test_japanese_dual_source_and_qa_match_head(tmp_path, baseline):
    source = make_mod(tmp_path, "Synthetic Dual", {
        "english": {"shared_desc": "Build a prosperous new country", "english_desc": "Develop a distant frontier"},
        "simp_chinese": {"shared_desc": "建设一个繁荣的新国家", "chinese_desc": "开发新的边疆地区"}})
    translation = make_mod(tmp_path, "Synthetic Dual JP", {
        "japanese": {"shared_desc": "Build a prosperous new country", "english_desc": "遠い辺境を開発する"}})
    for preferred in ("english", "simp_chinese"):
        assert core.scan_translation_gaps(source, preferred_source=preferred) == baseline.scan_translation_gaps(source, preferred_source=preferred)
        before = baseline.analyze_external_translation_coverage(source, translation)
        after = core.analyze_external_translation_coverage(source, translation)
        assert clean_result(after) == clean_result(before)
        assert after["gap_count"] == 2
    assert core.qa_entries({"shared_desc": "Build a prosperous new country"},
                           {"shared_desc": "Build a prosperous new country"}) == baseline.qa_entries(
                               {"shared_desc": "Build a prosperous new country"},
                               {"shared_desc": "Build a prosperous new country"})


def test_target_templates_preserve_old_japanese_and_match_english_fields():
    workspace = Path(__file__).resolve().parents[1]
    for ui_language, needle, target_name in (("japanese", "日本語", "日本語"), ("english", "Japanese", "Japanese")):
        # .target の key に日本語の名前を差し込むと、日本語だけの key（L4a の前からある key）と同じになる。
        # （以前は HEAD と比べていたが、コミットした後は自分自身と比べることになるので、今の辞書の中で比べる）
        strings = i18n.strings(ui_language)
        old_strings = strings
        target_keys = [key for key in strings if key.startswith("u9.") and key.endswith(".target")]
        assert target_keys
        for key in target_keys:
            assert strings[key].replace("{target_name}", target_name) == old_strings[key.removesuffix(".target")]
            assert needle not in strings[key]


def test_source_preference_and_default_fallback(tmp_path):
    source = make_mod(tmp_path, "Synthetic Basis", {
        "english": {"shared_desc": "An English source description"},
        "simp_chinese": {"shared_desc": "中文原文说明"},
        "french": {"target_only": "Texte cible"}})
    default = core.scan_translation_gaps(source, target_lang="french")
    chinese = core.scan_translation_gaps(source, preferred_source="simp_chinese", target_lang="french")
    same_as_target = core.scan_translation_gaps(source, preferred_source="french", target_lang="french")
    assert default[0]["source_lang"] == "english"
    assert chinese[0]["source_lang"] == "simp_chinese"
    assert same_as_target == default


def test_legacy_japanese_index_is_not_used_for_another_target(tmp_path):
    source = make_mod(tmp_path, "Synthetic Atlas", {"english": {"atlas_desc": "Build a prosperous new country"}})
    translation = make_mod(tmp_path, "Synthetic Atlas JP", {"japanese": {"atlas_desc": "新しい国を作る"}})
    index = core.build_translation_mod_index([translation])
    for row in index:
        row.pop("target_lang")
    assert not core.rank_external_japanese_translations(source, index, target_lang="korean")


@pytest.mark.parametrize("name", [
    "analyze_mod_translation_status", "scan_translation_gaps", "analyze_external_translation_coverage",
    "_external_gap_candidates", "build_translation_mod_index", "classify_translation_candidate_role",
    "_translation_mod_weight", "_translation_mod_weight_legacy", "rank_external_japanese_translations",
    "find_external_japanese_translation", "translation_relation_evidence", "build_relation_report",
    "relation_report_markdown", "assign_translation_candidate_owners", "gap_reason_text",
])
def test_target_language_is_keyword_only(name):
    parameter = inspect.signature(getattr(core, name)).parameters["target_lang"]
    assert parameter.kind == inspect.Parameter.KEYWORD_ONLY
    assert parameter.default == "japanese"
