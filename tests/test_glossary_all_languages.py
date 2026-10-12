import ast
import queue
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

import main
import translator_core as core


class Variable:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def write_yaml(root, language, entries):
    folder = root / language
    folder.mkdir(exist_ok=True)
    path = folder / f"terms_l_{language}.yml"
    path.write_text(f"l_{language}:\n" + "".join(
        f' {key}:0 "{value}"\n' for key, value in entries.items()), encoding="utf-8-sig")
    return path


def app_state(language):
    state = SimpleNamespace(target_lang_var=Variable(main._target_lang_choice(language)))
    for name in ("_collect_qa_diff_pairs", "_collect_japanese_entries_from_target",
                 "_collect_base_source_maps", "_align_japanese_with_base_root",
                 "_align_japanese_with_base_game", "_collect_glossary_import_pairs_from_path"):
        setattr(state, name, getattr(main.App, name).__get__(state))
    return state


@pytest.mark.parametrize("language,translation", [
    ("korean", "보병"), ("russian", "Пехота"), ("french", "Infanterie")])
def test_import_and_auto_candidates(tmp_path, language, translation):
    source = write_yaml(tmp_path, "english", {"ONE": "Infantry", "TWO": "Infantry", "REPLY": "Great!", "REPLY2": "Great!"})
    target = write_yaml(tmp_path, language, {"ONE": translation, "TWO": translation, "REPLY": translation + "!", "REPLY2": translation + "!"})
    state = app_state(language)
    assert state._collect_japanese_entries_from_target(tmp_path, target_lang=language)[1] == 1
    pairs = state._collect_glossary_import_pairs_from_path(target, target_lang=language)
    assert pairs and pairs[0]["source"] == source
    imported = core.build_import_glossary_candidates(pairs, target_lang=language)
    generated = core.build_auto_glossary_candidates(pairs, target_lang=language)
    assert next(row for row in imported if row["source"] == "Infantry")["preferred"] == translation
    assert {row["source"]: row["term_kind"] for row in generated} == {"Infantry": "term", "Great!": "phrase"}
    aligned = state._align_japanese_with_base_root([target], tmp_path, target_lang=language)
    assert len(aligned["records"]) == 4
    state._find_base_game_localization_root = lambda game: tmp_path
    assert state._align_japanese_with_base_game([target], "fake", target_lang=language) == aligned


@pytest.mark.parametrize("language", list(core.TARGET_LANGUAGES))
def test_japanese_titles_are_target_specific(language):
    assert core._is_probable_specific_glossary_term("LABEL", "infantry", "ヨーク公爵", "english", target_lang=language) is (language == "japanese")
    assert core._is_probable_specific_glossary_term("house_name", "infantry", "anything", "english", target_lang=language)
    assert core._classify_glossary_term_kind("Great!", "english", target_lang=language) == "phrase"


def test_english_target_excludes_english_and_prefers_chinese(tmp_path):
    target = write_yaml(tmp_path, "english", {"ONE": "Infantry", "TWO": "Infantry", "FALLBACK": "Cavalry", "FALLBACK2": "Cavalry"})
    chinese = write_yaml(tmp_path, "simp_chinese", {"ONE": "步兵", "TWO": "步兵"})
    french = write_yaml(tmp_path, "french", {"ONE": "Infanterie", "TWO": "Infanterie", "FALLBACK": "Cavalerie", "FALLBACK2": "Cavalerie"})
    state = app_state("english")
    aligned = state._align_japanese_with_base_root([target], tmp_path, target_lang="english")
    assert [row["source_lang"] for row in aligned["records"]] == ["simp_chinese", "simp_chinese", "french", "french"]
    pairs = state._collect_glossary_import_pairs_from_path(target, target_lang="english")
    for build in (core.build_auto_glossary_candidates, core.build_import_glossary_candidates):
        candidates = build(pairs + [{"source": target, "target": target}], target_lang="english")
        assert {row["source"] for row in candidates} == {"步兵", "Cavalerie"}
        assert all(row["source_lang"] != "english" for row in candidates)
    assert chinese.exists() and french.exists()


def baseline_functions(path, names, namespace, class_name=None):
    content = subprocess.check_output(["git", "show", f"HEAD:{path}"], text=True)
    tree = ast.parse(content)
    nodes = tree.body if class_name is None else next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == class_name).body
    selected = [node for node in nodes if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=selected, type_ignores=[]), "<HEAD baseline>", "exec"), namespace)
    return namespace


def test_japanese_results_match_head(tmp_path):
    source = write_yaml(tmp_path, "english", {"ONE": "Infantry", "TWO": "Infantry", "TITLE": "york", "TITLE2": "york", "REPLY": "Great!", "REPLY2": "Great!"})
    target = write_yaml(tmp_path, "japanese", {"ONE": "歩兵", "TWO": "歩兵", "TITLE": "ヨーク公爵", "TITLE2": "ヨーク公爵", "REPLY": "素晴らしい！", "REPLY2": "素晴らしい！"})
    write_yaml(tmp_path, "simp_chinese", {"ONE": "步兵", "TWO": "步兵"})
    namespace = baseline_functions("app/translator_core.py", {
        "build_auto_glossary_candidates", "build_import_glossary_candidates",
        "build_import_glossary_candidates_from_records", "_classify_glossary_term_kind",
        "_is_probable_specific_glossary_term"}, dict(vars(core)))
    pairs = [{"source": source, "target": target}]
    for name in ("build_auto_glossary_candidates", "build_import_glossary_candidates"):
        assert getattr(core, name)(pairs) == namespace[name](pairs)
        assert getattr(core, name)(pairs, target_lang="japanese") == namespace[name](pairs)
    old = baseline_functions("app/main.py", {"_collect_qa_diff_pairs", "_collect_japanese_entries_from_target", "_collect_base_source_maps", "_align_japanese_with_base_root", "_collect_glossary_import_pairs_from_path"}, dict(vars(main)), "App")
    state = app_state("japanese")
    legacy = SimpleNamespace()
    for name in ("_collect_qa_diff_pairs", "_collect_japanese_entries_from_target", "_collect_base_source_maps", "_align_japanese_with_base_root", "_collect_glossary_import_pairs_from_path"):
        setattr(legacy, name, old[name].__get__(legacy))
    assert state._collect_glossary_import_pairs_from_path(target) == legacy._collect_glossary_import_pairs_from_path(target)
    assert state._align_japanese_with_base_root([target], tmp_path) == legacy._align_japanese_with_base_root([target], tmp_path)


def worker_state(tmp_path, language):
    state = app_state(language)
    state.glossary_path_var = Variable(str(tmp_path / "glossary.json"))
    state.glossary_lang_var = Variable(main._target_lang_choice(language))
    state.review_dst_var = Variable(str(tmp_path / language / f"terms_l_{language}.yml"))
    state.glossary_import_busy = False
    state.glossary_import_thread = None
    state.auto_glossary_controller = None
    state.auto_glossary_status_var = Variable("")
    state.events = queue.Queue()
    state._closing = False
    state._set_glossary_import_busy = lambda *args: None
    for name in ("_start_glossary_import_thread", "_finish_import_candidates_in_worker",
                 "_start_japanese_glossary_import", "_import_japanese_targets_with_fallback"):
        setattr(state, name, getattr(main.App, name).__get__(state))
    return state


def defer_threads(monkeypatch):
    pending = []

    class Thread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            pending.append(self.target)

        def is_alive(self):
            return False

    monkeypatch.setattr(main.threading, "Thread", Thread)
    return pending


@pytest.mark.parametrize("language,translation", [
    ("japanese", "歩兵"), ("korean", "보병"), ("russian", "Пехота"), ("french", "Infanterie"), ("english", "Infantry")])
@pytest.mark.parametrize("origin", ["base", "file", "folder", "auto"])
def test_ui_worker_uses_and_saves_captured_target(tmp_path, monkeypatch, language, translation, origin):
    source_language = "simp_chinese" if language == "english" else "english"
    source_text = "步兵" if source_language == "simp_chinese" else "Infantry"
    source = write_yaml(tmp_path, source_language, {"ONE": source_text, "TWO": source_text})
    target = write_yaml(tmp_path, language, {"ONE": translation, "TWO": translation})
    state = worker_state(tmp_path, language)
    state._choose_game_for_glossary_import = lambda: "fake"
    state._choose_glossary_import_mode = lambda: "all"
    state._find_base_game_localization_root = lambda game: tmp_path
    pending = defer_threads(monkeypatch)
    if origin == "base":
        main.App.import_glossary_from_base_game(state)
    elif origin in {"file", "folder"}:
        monkeypatch.setattr(main.filedialog, "askopenfilename", lambda **kwargs: str(target))
        monkeypatch.setattr(main.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
        main.App.import_glossary_from_japanese_source(state, origin)
    else:
        state._auto_glossary_pairs_from_origin = lambda origin: [{"source": source, "target": target}]
        state.provider_var = Variable("local")
        state.url_var = Variable("unused")
        state.model_var = Variable("unused")
        state.preset_var = Variable("General")
        state.api_key_var = Variable("")
        monkeypatch.setattr(core, "resolve_auto_glossary_conflicts", lambda provider, url, model, candidates, *args: candidates)
        main.App.start_auto_glossary_generation(state, "review")
    assert len(pending) == 1
    state.target_lang_var.set(main._target_lang_choice("german"))
    state.glossary_lang_var.set(main._target_lang_choice("german"))
    pending[0]()
    events = []
    while not state.events.empty():
        events.append(state.events.get_nowait())
    assert not any(kind.endswith("error") for kind, _ in events), events
    assert any(kind in {"glossary_import_done", "auto_glossary_done"} for kind, _ in events), events
    destination = core.glossary_path_for_language(tmp_path / "glossary.json", language)
    assert core.load_glossary(destination) == {source_text: translation}
    if language != "japanese":
        assert not (tmp_path / "glossary.json").exists()


def test_title_suffix_affects_import_and_auto_only_for_japanese(tmp_path):
    source = write_yaml(tmp_path, "english", {"ONE": "infantry", "TWO": "infantry"})
    for language in ("japanese", "korean"):
        translation = "ヨーク公爵" if language == "japanese" else "요크公爵"
        target = write_yaml(tmp_path, language, {"ONE": translation, "TWO": translation})
        pairs = [{"source": source, "target": target}]
        assert bool(core.build_import_glossary_candidates(pairs, target_lang=language)) is (language != "japanese")
        assert core.build_auto_glossary_candidates(pairs, target_lang=language)[0]["term_kind"] == (
            "proper" if language == "japanese" else "term")


@pytest.mark.parametrize("language,translation", [
    ("french", "Industrie de construction"), ("german", "Wirtschaftliche Entwicklung")])
def test_latin_multiword_translations_are_not_japanese_residue(tmp_path, language, translation):
    source = write_yaml(tmp_path, "english", {"ONE": "construction", "TWO": "construction"})
    target = write_yaml(tmp_path, language, {"ONE": translation, "TWO": translation})
    pairs = [{"source": source, "target": target}]
    assert core.build_auto_glossary_candidates(pairs, target_lang=language)[0]["preferred"] == translation
    assert core.build_import_glossary_candidates(pairs, target_lang=language)[0]["preferred"] == translation


def test_language_selection_refreshes_import_labels(monkeypatch):
    labels = {}
    menu_labels = {}
    state = app_state("japanese")
    state.glossary_lang_var = Variable(main._target_lang_choice("korean"))
    state.target_lang_choice_var = Variable("")
    state.glossary_import_menu = SimpleNamespace(
        entryconfigure=lambda index, **kwargs: menu_labels.update({index: kwargs["label"]}))
    for name in ("glossary_jp_import_btn", "glossary_base_help_label",
                 "glossary_generated_help_label", "auto_glossary_drop_hint"):
        setattr(state, name, SimpleNamespace(config=lambda name=name, **kwargs: labels.update({name: kwargs["text"]})))
    state._refresh_glossary_import_language_labels = main.App._refresh_glossary_import_language_labels.__get__(state)
    monkeypatch.setattr(main, "DND_AVAILABLE", True)
    main.App._set_target_lang(state, "korean", save=False)
    target_name = main.i18n.t("lang.korean")
    assert all(target_name in text for text in [*labels.values(), *menu_labels.values()])
    assert state.target_lang_var.get() == "korean"


@pytest.mark.parametrize("language,translation", [
    ("japanese", "歩兵"), ("korean", "보병"), ("russian", "Пехота"), ("french", "Infanterie")])
def test_japanese_llm_instructions_are_not_used_for_other_languages(tmp_path, monkeypatch, language, translation):
    source = write_yaml(tmp_path, "english", {"ONE": "infantry", "TWO": "infantry", "THREE": "infantry"})
    target = write_yaml(tmp_path, language, {"ONE": translation, "TWO": translation, "THREE": translation + "別"})
    state = worker_state(tmp_path, language)
    state._auto_glossary_pairs_from_origin = lambda origin: [{"source": source, "target": target}]
    state.provider_var = Variable("local")
    state.url_var = Variable("unused")
    state.model_var = Variable("unused")
    state.preset_var = Variable("General")
    state.api_key_var = Variable("")
    calls = []

    def resolve(provider, url, model, candidates, *args):
        calls.append(candidates)
        return candidates

    monkeypatch.setattr(core, "resolve_auto_glossary_conflicts", resolve)
    pending = defer_threads(monkeypatch)
    main.App.start_auto_glossary_generation(state, "review")
    pending[0]()
    assert bool(calls) is (language == "japanese")
    destination = core.glossary_path_for_language(tmp_path / "glossary.json", language)
    assert core.load_glossary(destination) == {"infantry": translation}


@pytest.mark.parametrize("source_kind,key", [("import:file", "u4.target_yaml"), ("import:mod", "u4.target_mod")])
def test_origin_labels_follow_the_displayed_glossary_language(source_kind, key):
    state = app_state("french")
    state.glossary_lang_var = Variable(main._target_lang_choice("japanese"))
    label = main.App._glossary_kind_label(state, {"source_kind": source_kind})
    assert label == main.i18n.t(key, target_name=main.i18n.t("lang.japanese"))
