from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import translator_core as core


@pytest.fixture
def classified():
    items = json.loads((Path(__file__).parent / "fixtures/paratranz_sample.json").read_text(encoding="utf-8"))
    return core.classify_paratranz_glossary(items)


@pytest.mark.parametrize("data,expected", [([], True), ([{"term": "A", "translation": "甲"}], True),
    ({"A": "甲"}, False), ([{"term": "A"}], False), ([{"term": "A", "translation": "甲"}, 1], False)])
def test_detection(data, expected):
    assert core.is_paratranz_glossary(data) is expected


def test_classification(classified):
    assert classified["counts"] == {
        "items": 20, "terms": 14, "from_variants": 3, "rules": 2,
        "affixes": 3, "symbols": 2, "short_terms": 2,
        "spaces_fixed": 4, "duplicates": 4, "note_rules": 4,
    }
    assert classified["terms"]["Grand Fleet"] == "大艦隊"
    assert classified["terms"]["Protectorates"] == "保護国"
    assert classified["terms"]["Empire"] == "帝国"
    assert len(classified["rules"]) == 7
    assert classified["meta"]["Protectorates"]["variant_of"] == "Protectorate"
    assert classified["meta"]["Protectorate"] == {
        "source_kind": "import:paratranz", "paratranz_id": 101, "note": "", "pos": "noun",
        "case_sensitive": False, "variant_of": None, "project": 1,
    }


def test_rule_never_enters_prompt(tmp_path, classified):
    path = tmp_path / "glossary.json"
    core.save_paratranz_import(path, classified, "replace")
    glossary = core.load_glossary(path)
    assert "※架空の表記ルール" not in glossary.values()
    selected = dict(core.glossary_for_prompt(glossary, ["& Protectorate QX ?! -esque"]))
    assert "※架空の表記ルール" not in core.build_system_prompt("english", selected)
    assert "※架空の表記ルール" not in core.build_system_prompt("english", glossary)


def test_merge_and_separate_metadata(tmp_path, classified):
    path = tmp_path / "glossary.json"
    core.save_glossary(path, {"Protectorate": "既存訳", "Old": "旧"})
    core.save_json(core.glossary_variants_path(path), {"Protectorate": {"custom": "keep", "note": "既存note"}, "Old": {"note": "旧note"}})
    result = core.save_paratranz_import(path, classified, "merge")
    assert core.load_glossary(path)["Protectorate"] == "既存訳"
    assert result["conflicts"] == [{"term": "Protectorate", "existing": "既存訳", "incoming": "保護国"}]
    assert result["counts"] == {"added": 13, "updated": 0, "conflicts": 1}
    meta = core.load_json(core.glossary_variants_path(path), {})
    assert meta["Protectorate"] == {"custom": "keep", "note": "既存note"}
    assert meta["Old"]["note"] == "旧note"
    assert meta["Empire"]["note"] == "省略しないように"
    rules = core.load_json(core.glossary_notation_rules_path(path), {})
    assert rules == {"rules": classified["rules"], "note_rules": classified["note_rules"]}
    assert set(meta) <= set(core.load_glossary(path))
    assert "&" not in meta and "rules" not in meta
    core.save_paratranz_import(path, classified, "merge")
    assert core.load_json(core.glossary_notation_rules_path(path), {}) == rules


def test_replace(tmp_path, classified):
    path = tmp_path / "glossary.json"
    core.save_glossary(path, {"Protectorate": "既存訳", "Old": "旧"})
    core.save_json(core.glossary_variants_path(path), {"Protectorate": {"custom": "keep"}, "Old": {"note": "旧"}})
    result = core.save_paratranz_import(path, classified, "replace")
    assert core.load_glossary(path) == classified["terms"]
    assert result["counts"] == {"added": 13, "updated": 1, "conflicts": 0}
    meta = core.load_json(core.glossary_variants_path(path), {})
    assert "Old" not in meta
    assert meta["Protectorate"]["custom"] == "keep"


def test_save_ui_retains_metadata_and_french_target(tmp_path, classified, monkeypatch):
    monkeypatch.setenv("PARADOX_TRANSLATOR_DATA_ROOT", str(tmp_path / "data"))
    main = importlib.import_module("main")

    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

    class Tree:
        def get_children(self):
            return tuple(classified["terms"])

        def item(self, term, option):
            return (term, classified["terms"][term])

    state = SimpleNamespace(glossary_path_var=Variable(str(tmp_path / "glossary.json")),
        glossary_lang_var=Variable(main._target_lang_choice("french")), progress_text=Variable(),
        auto_glossary_tree=Tree())
    path = main._selected_glossary_path(state)
    assert path.name == "glossary_french.json"
    core.save_paratranz_import(path, classified, "replace")
    before = core.load_json(core.glossary_variants_path(path), {})
    state.save_glossary_ui = main.App.save_glossary_ui.__get__(state)
    state.save_glossary_ui()
    assert core.load_json(core.glossary_variants_path(path), {}) == before
    assert core.load_glossary(path) == classified["terms"]
    assert not (tmp_path / "glossary.json").exists()


@pytest.mark.parametrize("mode", ["merge", "replace"])
def test_unsupported_destination_not_overwritten(tmp_path, classified, mode):
    path = tmp_path / "glossary.json"
    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        core.save_paratranz_import(path, classified, mode)
    assert path.read_text(encoding="utf-8") == "[]"
    assert not core.glossary_variants_path(path).exists()


def test_invalid_mode(tmp_path, classified):
    with pytest.raises(ValueError):
        core.save_paratranz_import(tmp_path / "glossary.json", classified, "invalid")


def test_variants_also_classified():
    result = core.classify_paratranz_glossary([{"term": "Empire", "translation": "帝国", "variants": ["-esque", "?!", "QX", "Empire"]}])
    assert result["terms"] == {"Empire": "帝国", "QX": "帝国"}
    assert len(result["rules"]) == 2
    assert result["counts"]["duplicates"] == 1
    assert result["counts"]["short_terms"] == 1


@pytest.mark.parametrize("item", [{"term": None, "translation": "甲"}, {"term": "A", "translation": 1}, {"term": " ", "translation": "甲"}])
def test_invalid_term_values(item):
    with pytest.raises(ValueError):
        core.classify_paratranz_glossary([item])


def test_note_selection_without_app(tmp_path, monkeypatch):
    monkeypatch.setenv("PARADOX_TRANSLATOR_DATA_ROOT", str(tmp_path / "data"))
    main = importlib.import_module("main")
    displayed = []
    state = SimpleNamespace(glossary_note_var=SimpleNamespace(set=displayed.append),
        _glossary_variant_metadata=lambda: {"Empire": {"note": "省略しないように"}})
    tree = SimpleNamespace(selection=lambda: ["selected"], item=lambda *args: ("Empire", "帝国"))
    main.App.show_selected_glossary_note(state, tree)
    assert "省略しないように" in displayed[-1]
    tree.selection = lambda: []
    main.App.show_selected_glossary_note(state, tree)
    assert "選択" in displayed[-1]


def test_merge_preserves_other_notation_and_same_translation_fields(tmp_path):
    path = tmp_path / "glossary.json"
    core.save_glossary(path, {"Empire": "帝国"})
    core.save_json(core.glossary_variants_path(path), {"Empire": {"custom": "keep"}})
    old_rule = {"term": "Old", "translation": "※旧ルール", "note": "", "reason": "旧"}
    core.save_json(core.glossary_notation_rules_path(path), {"rules": [old_rule], "note_rules": []})
    data = core.classify_paratranz_glossary([{"term": "Empire", "translation": "帝国", "note": "note"}])
    core.save_paratranz_import(path, data, "merge")
    meta = core.load_json(core.glossary_variants_path(path), {})["Empire"]
    assert meta["note"] == "note" and meta["custom"] == "keep"
    assert core.load_json(core.glossary_notation_rules_path(path), {})["rules"] == [old_rule]
    core.save_paratranz_import(path, data, "replace")
    assert core.load_json(core.glossary_notation_rules_path(path), {})["rules"] == []


@pytest.mark.parametrize("source", ["カナ", "한글", "𠀀", "A!", "1?", "王!"])
def test_cjk_letters_and_digits_are_not_symbols(source):
    result = core.classify_paratranz_glossary([{"term": source, "translation": "用語"}])
    assert result["terms"] == {source: "用語"}


@pytest.mark.parametrize("source", ["・", "。", "＆", "―", "!"])
def test_punctuation_is_not_a_cjk_letter(source):
    result = core.classify_paratranz_glossary([{"term": source, "translation": "記号"}])
    assert result["terms"] == {}
    assert result["counts"]["symbols"] == 1


@pytest.mark.parametrize("cancel", [False, True])
def test_confirmation_language_and_cancel_without_app(tmp_path, classified, monkeypatch, cancel):
    monkeypatch.setenv("PARADOX_TRANSLATOR_DATA_ROOT", str(tmp_path / "data"))
    main = importlib.import_module("main")
    widgets = []
    previews = []

    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

        def set(self, value):
            self.value = value

        def trace_add(self, *args):
            pass

    class Widget:
        def __init__(self, *args, **kwargs):
            self.options = kwargs
            widgets.append(self)

        def pack(self, **kwargs):
            pass

        def title(self, *args):
            pass

        def geometry(self, *args):
            pass

        def transient(self, *args):
            pass

        def grab_set(self):
            pass

        def destroy(self):
            pass

    monkeypatch.setattr(main.tk, "StringVar", Variable)
    monkeypatch.setattr(main.tk, "Toplevel", Widget)
    for name in ("Frame", "Label", "Combobox", "Radiobutton", "Button"):
        monkeypatch.setattr(main.ttk, name, Widget)
    monkeypatch.setattr(main, "WrappingLabel", Widget)
    state = SimpleNamespace(glossary_path_var=Variable(str(tmp_path / "glossary.json")),
        glossary_lang_var=Variable(main._target_lang_choice("japanese")), progress_text=Variable(),
        _show_glossary_import_text=lambda parent, text: previews.append(text),
        load_glossary_ui=lambda **kwargs: None)
    main.App.confirm_paratranz_import(state, classified)
    assert "短い語は、ほかの単語の一部に誤って当たるおそれ" in previews[0]
    assert "※架空の表記ルール" in previews[0]
    assert not (tmp_path / "glossary.json").exists()
    language = next(widget.options["textvariable"] for widget in widgets if widget.options.get("state") == "readonly")
    assert language.get() == main._target_lang_choice("japanese")
    language.set(main._target_lang_choice("french"))
    button = next(widget for widget in widgets if widget.options.get("text") == ("やめる" if cancel else "取り込む"))
    button.options["command"]()
    path = tmp_path / "glossary_french.json"
    if cancel:
        assert not path.exists()
    else:
        assert core.load_glossary(path) == classified["terms"]
        assert state.glossary_lang_var.get() == main._target_lang_choice("french")
        assert core.glossary_notation_rules_path(path).exists()
    assert not (tmp_path / "glossary.json").exists()


def test_variants_null_is_treated_as_no_variants():
    """ParaTranz は variants の無い語を null で書き出す（実物で確認）。"""
    items = [{"id": 1, "term": "Fleet", "translation": "艦隊", "variants": None},
             {"id": 2, "term": "Army", "translation": "陸軍", "variants": ["Armies", None, " "]}]
    result = core.classify_paratranz_glossary(items)
    assert result["terms"] == {"Fleet": "艦隊", "Army": "陸軍", "Armies": "陸軍"}


def test_paratranz_boundary_sample():
    """ParaTranz の書き出しと同じ形の架空のデータ。実物の境目の性質（ルール・接辞・記号・前後の空白・重なり・短い語・variants が null）をそろえてある。"""
    import json as _json
    data = _json.loads((Path(__file__).parent / "fixtures" / "paratranz_boundary_sample.json").read_text(encoding="utf-8"))
    result = core.classify_paratranz_glossary(data)
    counts = result["counts"]
    assert counts["rules"] == 1 and counts["affixes"] == 4 and counts["symbols"] == 3
    assert counts["short_terms"] >= 1 and counts["duplicates"] >= 1 and counts["spaces_fixed"] >= 3
    assert "&" not in result["terms"] and not any(v.startswith("※") for v in result["terms"].values())
    assert all(k == k.strip() for k in result["terms"])
