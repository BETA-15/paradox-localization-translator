from types import SimpleNamespace
import ast
import hashlib
import subprocess
from pathlib import Path

import pytest
import main
import i18n
import ui_status
import translator_core as core
from test_relation_all_languages import make_mod


def diagnostic_state(language):
    return SimpleNamespace(target_lang_var=SimpleNamespace(get=lambda: language), diagnostic_conflict_choices={})


@pytest.mark.parametrize("language", core.TARGET_LANGUAGES)
def test_diagnostic_counts_selected_language(tmp_path, language):
    root = make_mod(tmp_path, "source", {"english": {"KEY": "Source value"}, language: {"KEY": "Target value", "EXTRA": "Extra value"}})
    result = main.App._analyze_localization_health(diagnostic_state(language), root, {}, {})
    assert result["stats"]["japanese_keys"] == 2
    assert "日本語なし" not in {issue["kind"] for issue in result["issues"]}
    if language not in {"english", "simp_chinese"}:
        assert result["remove_by_file"]


def test_occurrences_use_selected_language(tmp_path):
    root = make_mod(tmp_path, "source", {"japanese": {"JA": "日本語"}, "french": {"FR": "Français"}})
    result = main.App._diagnostic_japanese_occurrence_index(diagnostic_state("french"), [root])
    assert set(result) == {"FR"}


def test_kind_labels_keep_japanese_ids():
    previous = i18n.get_ui_language()
    try:
        i18n.set_ui_language("japanese")
        for kind in ui_status.DIAGNOSTIC_KINDS:
            assert ui_status.diagnostic_kind_label(kind, "japanese") == kind
        assert ui_status.diagnostic_kind_label("日本語なし", "french") == "フランス語なし"
        i18n.set_ui_language("english")
        assert ui_status.diagnostic_kind_label("日本語なし", "french") == "No French localization"
        assert ui_status.diagnostic_kind_label("unknown", "french") == "unknown"
    finally:
        i18n.set_ui_language(previous)


@pytest.mark.parametrize("language,copied,rejected", [("french", 20, True), ("french", 16, True), ("french", 15, False), ("japanese", 20, False)])
def test_source_copy_candidate_gate(tmp_path, language, copied, rejected):
    sources = {f"KEY_{index}": f"The population requires more resources {index}" for index in range(20)}
    targets = {key: value if index < copied else f"La population demande des ressources {index}" for index, (key, value) in enumerate(sources.items())}
    source = make_mod(tmp_path, "source", {"english": sources})
    candidate = make_mod(tmp_path, "source translation", {language: targets})
    ranked = core.rank_external_japanese_translations(source, core.build_translation_mod_index([candidate], target_lang=language), target_lang=language)
    assert ranked
    if rejected:
        assert ranked[0]["classification"] == "rejected"
        assert ranked[0]["candidate_rejected"] == "source_copy"
        assert core.find_external_japanese_translation(source, core.build_translation_mod_index([candidate], target_lang=language), target_lang=language) is None
    else:
        assert ranked[0]["classification"] == "auto"


@pytest.mark.parametrize("source_language", ["english", "simp_chinese"])
def test_copy_gate_requires_twenty_eligible_values(tmp_path, source_language):
    originals = {f"KEY_{index}": "The population needs more resources" for index in range(19)}
    originals.update({"label": "Paris", "short": "Yes", "acronym": "NASA", "number": "12345"})
    source = make_mod(tmp_path, "source", {source_language: originals})
    candidate = make_mod(tmp_path, "source translation", {"french": originals})
    ranked = core.rank_external_japanese_translations(source, core.build_translation_mod_index([candidate], target_lang="french"), target_lang="french")
    assert ranked[0]["candidate_source_comparable"] == 19
    assert "candidate_rejected" not in ranked[0]
    assert ranked[0]["classification"] == "auto"


def test_source_name_files_are_not_counted(tmp_path):
    originals = {f"KEY_{index}": "The population needs more resources" for index in range(20)}
    source = make_mod(tmp_path, "source", {"english": originals})
    folder = source / "localisation" / "english"
    (folder / "sample_l_english.yml").rename(folder / "character_names_l_english.yml")
    candidate = make_mod(tmp_path, "source translation", {"french": originals})
    ranked = core.rank_external_japanese_translations(source, core.build_translation_mod_index([candidate], target_lang="french"), target_lang="french")
    assert ranked[0]["candidate_source_comparable"] == 0
    assert "candidate_rejected" not in ranked[0]


def test_copy_gate_prefers_english_and_blocks_manual_link(tmp_path):
    originals = {f"KEY_{index}": "The population needs more resources" for index in range(20)}
    chinese = {key: "这是不同的原文" for key in originals}
    source = make_mod(tmp_path, "source", {"english": originals, "simp_chinese": chinese})
    candidate = make_mod(tmp_path, "source translation", {"french": originals})
    index = core.build_translation_mod_index([candidate], target_lang="french")
    index[0].update(manual_role="translation", manual_source_paths=[str(source.resolve())])
    ranked = core.rank_external_japanese_translations(source, index, target_lang="french")
    assert ranked[0]["classification"] == "rejected"
    assert ranked[0]["candidate_rejected"] == "source_copy"


def test_diagnostic_skips_english_external_mods():
    state = diagnostic_state("english")
    assert main.App._diagnostic_translation_relation_map(state, []) == {}
    assert main.App._build_diagnostic_integrations(state, [], {}, {"invalid": {}}, {}) == []


def test_english_diagnostic_uses_other_source_languages(tmp_path):
    root = make_mod(tmp_path, "source", {"french": {"KEY": "Source", "EXTRA": "Source extra"}, "english": {"KEY": "Target", "EXTRA": "Target extra"}})
    state = diagnostic_state("english")
    index, meta = main.App._diagnostic_source_key_index(state, [root])
    assert set(index) == {"KEY", "EXTRA"}
    result = main.App._analyze_localization_health(state, root, index, meta)
    assert result["stats"]["source_keys"] == 2
    assert not result["remove_by_file"]


def test_japanese_diagnostic_matches_head(tmp_path):
    contents = subprocess.run(["git", "show", "HEAD:app/main.py"], capture_output=True, text=True, check=True, timeout=20).stdout
    original_class = next(node for node in ast.parse(contents).body if isinstance(node, ast.ClassDef) and node.name == "App")
    original = next(node for node in original_class.body if isinstance(node, ast.FunctionDef) and node.name == "_analyze_localization_health")
    namespace = dict(vars(main))
    exec(compile(ast.fix_missing_locations(ast.Module(body=[original], type_ignores=[])), "head_diagnostic", "exec"), namespace)
    root = make_mod(tmp_path, "source", {"english": {"KEY": "Source"}, "japanese": {"KEY": "訳文", "EXTRA": "不要"}})
    state = diagnostic_state("japanese")
    previous = i18n.get_ui_language()
    try:
        i18n.set_ui_language("japanese")
        expected = namespace["_analyze_localization_health"](state, root, {}, {})
        current = main.App._analyze_localization_health(state, root, {}, {})
        assert current.pop("target_lang") == "japanese"
        assert current == expected
    finally:
        i18n.set_ui_language(previous)


@pytest.mark.parametrize("language", core.TARGET_LANGUAGES)
def test_target_dictionary_preserves_japanese_and_has_english(language):
    from i18n.japanese.u7_diagnostics import STRINGS as japanese
    from i18n.english.u7_diagnostics import STRINGS as english
    previous = i18n.get_ui_language()
    try:
        i18n.set_ui_language("japanese")
        for key in japanese:
            if not key.endswith(".target"):
                continue
            if language == "japanese":
                original = japanese[key.removesuffix(".target")]
                if key == "u7.back_up_the_entire_localization_folder.target":
                    original = original.replace('・英語 / 簡体字中国語は変更しません', '・翻訳先以外の言語は変更しません')
                assert japanese[key].replace("{target_name}", "日本語") == original
            assert "{target_name}" in english[key]
    finally:
        i18n.set_ui_language(previous)


def test_display_defaults_are_localized():
    previous = i18n.get_ui_language()
    try:
        i18n.set_ui_language("japanese")
        assert i18n.t("u7.unknown_game") == "ゲーム未特定"
        assert i18n.t("u7.diagnostic_phase") == "診断"
    finally:
        i18n.set_ui_language(previous)


def test_diagnostic_choice_ids_are_scoped_but_japanese_ids_unchanged():
    state = diagnostic_state("japanese")
    original = hashlib.sha1(b"source\0translation\0KEY").hexdigest()
    assert main.App._diagnostic_conflict_id(state, "source", "translation", "KEY") == original
    assert main.App._diagnostic_conflict_id(state, "source", "translation", "KEY", target_lang="french") != original
    assert main.App._diagnostic_conflict_id(state, "source", "translation", "KEY", target_lang="french") != main.App._diagnostic_conflict_id(state, "source", "translation", "KEY", target_lang="german")


def test_repair_writes_only_selected_language(tmp_path, monkeypatch):
    import queue

    source = make_mod(tmp_path, "source", {"english": {"KEY_1": "Source one", "KEY_2": "Source two"}, "french": {"KEY_1": "Traduction une"}, "japanese": {"KEY_1": "日本語"}})
    candidate = make_mod(tmp_path, "source translation", {"french": {"KEY_2": "Traduction deux", "EXTRA": "Inutile"}})
    source_files = {path: path.read_bytes() for path in (source / "localisation").rglob("*.yml") if "l_french" not in path.name}
    state = diagnostic_state("french")
    state.events = queue.Queue()
    state.diagnostic_thread = None
    state.diagnostic_generation = 0
    state._selected_diagnostic_roots = lambda: [source, candidate]
    state._all_known_mod_roots_for_diagnostic = lambda: [source, candidate]
    state._save_diagnostic_state = lambda *args: None
    state._set_diagnostic_repair_busy = lambda *args: None
    state._refresh_operation_states = lambda: None
    state.diagnostic_summary_var = SimpleNamespace(set=lambda *args: None)
    state._set_diagnostic_detail = lambda *args: None
    def translation_index(roots, **kwargs):
        rows = core.build_translation_mod_index([candidate], **kwargs)
        rows[0].update(manual_role="translation", manual_source_paths=[str(source.resolve())])
        return rows

    state._build_stable_translation_mod_index = translation_index
    state._mod_relation_override = lambda *args, **kwargs: {}
    state._backup_localization_for_repair = lambda root, stamp: tmp_path / "synthetic_backup"
    for method in ("_diagnostic_source_key_index", "_diagnostic_translation_relation_map", "_diagnostic_allowed_context", "_diagnostic_japanese_occurrence_index", "_analyze_localization_health", "_build_diagnostic_integrations", "_attach_diagnostic_integration_issues", "_diagnostic_relation_id", "_diagnostic_conflict_id", "_apply_localization_removal_plan"):
        setattr(state, method, getattr(main.App, method).__get__(state))
    monkeypatch.setattr(main.messagebox, "askyesno", lambda *args: True)
    class ImmediateThread:
        def __init__(self, target, **kwargs):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr(main.threading, "Thread", ImmediateThread)
    main.App._start_localization_diagnostic(state, repair=True)
    events = list(state.events.queue)
    assert not [payload for event, payload in events if event == "diagnostic_error"], events
    assert any(event == "diagnostic_done" for event, payload in events)
    output = candidate / "localisation" / "french" / "zzz_paradox_localization_translator_consolidated_l_french.yml"
    assert core.parse_localization_file(output)[0:2] == ("french", {"KEY_1": "Traduction une"})
    for path, original in source_files.items():
        assert path.read_bytes() == original
    assert "EXTRA" not in core._collect_mod_language_entries(candidate, target_lang="french")["japanese"]
