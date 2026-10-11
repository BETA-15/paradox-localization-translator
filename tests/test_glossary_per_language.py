from pathlib import Path
from types import MethodType, SimpleNamespace
import json
import queue

import pytest

import main


class Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Tree:
    def __init__(self):
        self.rows = {}
        self.headings = {}

    def get_children(self):
        return list(self.rows)

    def delete(self, item):
        del self.rows[item]

    def insert(self, parent, position, values):
        self.rows[str(len(self.rows))] = values

    def item(self, item, option):
        return self.rows[item]

    def heading(self, column, text):
        self.headings[column] = text


def glossary_state(base, language):
    state = SimpleNamespace(
        glossary_path_var=Variable(str(base)),
        glossary_lang_var=Variable(main._target_lang_choice(language)),
        glossary_tree=Tree(), auto_glossary_tree=Tree(),
        progress_text=Variable(), glossary_actual_path_var=Variable(),
    )
    for name in ("load_glossary_ui", "save_glossary_ui", "_glossary_variant_metadata"):
        setattr(state, name, MethodType(getattr(main.App, name), state))
    return state


@pytest.mark.parametrize("filename,language,expected", [
    ("glossary.json", "japanese", "glossary.json"),
    ("glossary.json", "french", "glossary_french.json"),
    ("my_terms.json", "korean", "my_terms_korean.json"),
])
def test_language_path(tmp_path, filename, language, expected):
    assert main.core.glossary_path_for_language(tmp_path / filename, language) == tmp_path / expected


@pytest.mark.parametrize("language,exists", [("french", True), ("french", False), ("japanese", False)])
def test_queue_uses_item_language(tmp_path, monkeypatch, language, exists):
    base = tmp_path / "glossary.json"
    translated = tmp_path / "glossary_french.json"
    if exists:
        translated.write_text('{"King": "Roi"}', encoding="utf-8")
    calls = []

    def fake_run(input_path, output_path, **kwargs):
        calls.append(kwargs["glossary_path"])
        return {"processed": 1, "jobs": 0, "failed": 0, "skipped": 0,
                "interrupted": False, "encoding_recoveries": []}

    monkeypatch.setattr(main.core, "run_translation", fake_run)
    state = SimpleNamespace(
        queue_items=[{"input": str(tmp_path / "input"), "output": str(tmp_path / "output"),
                      "queue_item_id": "example", "target_lang": language}],
        _active_normal_item_ids=["example"], controller=main.core.TranslationController(),
        events=queue.SimpleQueue(), current_queue_index=0,
        translation_start_settings={"glossary": str(base)},
        _checkpoint=lambda payload: None, _ensure_item_cache=lambda item: str(tmp_path / "cache.json"),
        _register_cache_job=lambda item: None, _item_has_remaining_translation_gap=lambda item: False,
        _write_session_file=lambda **kwargs: None,
    )
    main.App._queue_worker(state)
    expected = str(base) if language == "japanese" else translated if exists else None
    assert len(calls) == 1
    if expected is None:
        assert calls[0] is None
    else:
        assert Path(calls[0]) == Path(expected)
    if language == "japanese":
        assert calls[0] == str(base)
    logs = []
    while not state.events.empty():
        kind, payload = state.events.get()
        if kind == "normal_log":
            logs.append(payload)
    if language == "french":
        assert any((translated.name if exists else "この言語の用語集はありません") in text for text in logs)


@pytest.mark.parametrize("language", ["french", "japanese"])
def test_tab_reads_and_saves_selected_language(tmp_path, language):
    base = tmp_path / "glossary.json"
    base.write_text('{"King": "王"}', encoding="utf-8")
    french = tmp_path / "glossary_french.json"
    french.write_text('{"King": "Roi"}', encoding="utf-8")
    state = glossary_state(base, language)
    state.load_glossary_ui(silent=True)
    assert list(state.glossary_tree.rows.values()) == [("King", "Roi" if language == "french" else "王")]
    state.glossary_tree.rows["0"] = ("King", "Monarque" if language == "french" else "国王")
    state.save_glossary_ui()
    assert json.loads((french if language == "french" else base).read_text()) == {
        "King": "Monarque" if language == "french" else "国王"}
    assert json.loads((base if language == "french" else french).read_text()) == {
        "King": "王" if language == "french" else "Roi"}
    assert state.glossary_path_var.get() == str(base)
    assert state.glossary_tree.headings["dst"] == main.core.target_language_label(language)
    assert state.glossary_actual_path_var.get() == f"この言語のファイル: {french if language == 'french' else base}"


def test_switching_languages_reloads_and_clears_missing_glossary(tmp_path):
    base = tmp_path / "glossary.json"
    base.write_text('{"King": "王"}', encoding="utf-8")
    state = glossary_state(base, "japanese")
    state.load_glossary_ui(silent=True)
    assert list(state.glossary_tree.rows.values()) == [("King", "王")]
    state.glossary_lang_var.set(main._target_lang_choice("french"))
    state.load_glossary_ui(silent=True)
    assert state.glossary_tree.rows == {}
    assert state.auto_glossary_tree.rows == {}
    assert state.glossary_tree.headings["dst"] == "フランス語"
    state.glossary_lang_var.set(main._target_lang_choice("japanese"))
    state.load_glossary_ui(silent=True)
    assert list(state.glossary_tree.rows.values()) == [("King", "王")]


def test_review_save_uses_translation_language_not_tab_language(tmp_path, monkeypatch):
    base = tmp_path / "glossary.json"
    base.write_text('{"King": "王"}', encoding="utf-8")
    state = glossary_state(base, "japanese")
    state.target_lang_var = Variable(main._target_lang_choice("french"))
    state._selected_review_key = lambda: "KING"
    state.review_source_entries = {"KING": "King"}
    state.dst_text = SimpleNamespace(get=lambda *args: "Roi")
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *args: None)
    main.App.save_review_glossary_term(state)
    assert json.loads((tmp_path / "glossary_french.json").read_text()) == {"King": "Roi"}
    assert json.loads(base.read_text()) == {"King": "王"}
    assert state.glossary_path_var.get() == str(base)


@pytest.mark.parametrize("language", list(main.core.TARGET_LANGUAGES))
def test_translation_glossary_lookup_uses_explicit_language(tmp_path, language):
    base = tmp_path / "glossary.json"
    path = main.core.glossary_path_for_language(base, language)
    assert main._existing_language_glossary(str(base), language) is None
    path.write_text("{}", encoding="utf-8")
    assert main._existing_language_glossary(str(base), language) == path
    assert main._existing_language_glossary("", language) is None


@pytest.mark.parametrize("method,args", [
    ("start_auto_glossary_generation", ("review",)),
    ("_save_imported_glossary_candidates", ([{"source": "King", "target": "王"}], "example")),
    ("import_glossary_from_base_game", ()),
    ("import_glossary_from_japanese_source", ("file",)),
    ("bulk_unify_review_terms", ()),
    ("on_glossary_import_drop_paths", (None,)),
])
def test_japanese_generation_is_blocked_for_other_languages(tmp_path, monkeypatch, method, args):
    state = glossary_state(tmp_path / "glossary.json", "french")
    notices = []
    monkeypatch.setattr(main.messagebox, "showinfo", lambda title, text: notices.append(text))
    getattr(main.App, method)(state, *args)
    assert notices == ["この機能は日本語の用語集だけで使えます"]
    assert list(tmp_path.iterdir()) == []


def test_translation_passes_french_glossary_to_batch(tmp_path, monkeypatch):
    source = tmp_path / "example_l_english.yml"
    source.write_text('l_english:\n KING:0 "King"\n', encoding="utf-8-sig")
    glossary = tmp_path / "glossary_french.json"
    glossary.write_text('{"King": "Roi"}', encoding="utf-8")
    captured = []

    def fake_batch(*args, **kwargs):
        captured.append(kwargs.get("glossary", args[4] if len(args) > 4 else None))
        return ["Roi"]

    monkeypatch.setattr(main.core, "translate_batch", fake_batch)
    main.core.run_translation(source, tmp_path / "output", target_lang="french",
                              glossary_path=glossary, auto_qa=False)
    assert captured == [{"King": "Roi"}]
