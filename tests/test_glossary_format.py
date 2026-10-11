from __future__ import annotations

import importlib
import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import translator_core as core

os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = tempfile.mkdtemp(prefix="plt-glossary-test-")
main = importlib.import_module("main")


class FakeVar:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTree:
    def __init__(self, rows=()):
        self.rows = {str(index): row for index, row in enumerate(rows)}
        self.next_id = len(self.rows)

    def get_children(self):
        return tuple(self.rows)

    def delete(self, row_id):
        del self.rows[row_id]

    def insert(self, parent, position, *, values):
        row_id = str(self.next_id)
        self.next_id += 1
        self.rows[row_id] = values
        return row_id

    def item(self, row_id, option):
        assert option == "values"
        return self.rows[row_id]


@pytest.fixture
def ui(monkeypatch):
    errors = []
    records = []
    monkeypatch.setattr(main.messagebox, "showerror", lambda *args: errors.append(args))
    monkeypatch.setattr(main, "record_error", lambda *args, **kwargs: records.append((args, kwargs)))
    state = SimpleNamespace(
        glossary_path_var=FakeVar(),
        progress_text=FakeVar(),
        glossary_tree=FakeTree([("Existing", "既存")]),
        auto_glossary_tree=FakeTree([("Automatic", "自動", "名称")]),
        _glossary_variant_metadata=lambda: {},
    )
    state.load_glossary_ui = main.App.load_glossary_ui.__get__(state)
    state.save_glossary_ui = main.App.save_glossary_ui.__get__(state)
    return state, errors, records


@pytest.fixture
def paratranz_file(tmp_path):
    path = tmp_path / "paratranz.json"
    path.write_text(json.dumps([
        {"id": 1, "term": "Protectorate", "translation": "保護国", "variants": []},
        {"id": 2, "term": "Empire", "translation": "帝国", "variants": []},
    ], ensure_ascii=False), encoding="utf-8")
    return path


def test_missing_glossary_has_no_problem(tmp_path):
    assert core.glossary_file_problem(tmp_path / "missing.json") == ""


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "utf-32"])
def test_dict_glossary_has_no_problem(tmp_path, encoding):
    path = tmp_path / "glossary.json"
    path.write_text('{"Empire": "帝国"}', encoding=encoding)
    assert core.glossary_file_problem(path) == ""


def test_paratranz_format_is_explained(paratranz_file):
    problem = core.glossary_file_problem(paratranz_file)
    assert "対応していない形式" in problem
    assert "リスト形式" in problem
    assert "ParaTranz" in problem


@pytest.mark.parametrize("content", ["[]", "null", "42", '"term"'])
def test_other_non_dict_formats_are_rejected(tmp_path, content):
    path = tmp_path / "glossary.json"
    path.write_text(content, encoding="utf-8")
    assert "対応していない形式" in core.glossary_file_problem(path)


def test_broken_json_reports_line_number(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{\n"Empire":\n}', encoding="utf-8")
    assert "3行目" in core.glossary_file_problem(path)


def test_unreadable_glossary_reports_problem(tmp_path):
    assert core.glossary_file_problem(tmp_path)


def test_load_glossary_keeps_legacy_list_behavior(paratranz_file):
    assert core.load_glossary(paratranz_file) == {}


def test_bad_load_preserves_both_trees_and_blocks_save(ui, paratranz_file):
    state, errors, records = ui
    state.glossary_path_var.set(str(paratranz_file))
    original = paratranz_file.read_bytes()
    state.load_glossary_ui()
    assert len(errors) == 1
    assert list(state.glossary_tree.rows.values()) == [("Existing", "既存")]
    assert list(state.auto_glossary_tree.rows.values()) == [("Automatic", "自動", "名称")]
    assert state._glossary_unsafe_path == paratranz_file.resolve()
    state.save_glossary_ui()
    assert len(errors) == 2
    assert "別の名前で保存" in errors[-1][1]
    assert paratranz_file.read_bytes() == original


def test_silent_bad_load_records_problem_without_dialog(ui, paratranz_file):
    state, errors, records = ui
    state.glossary_path_var.set(str(paratranz_file))
    state.load_glossary_ui(silent=True)
    assert errors == []
    assert records
    assert "対応していない形式" in state.progress_text.get()
    assert state._glossary_unsafe_path == paratranz_file.resolve()
    assert list(state.glossary_tree.rows.values()) == [("Existing", "既存")]


@pytest.mark.parametrize("content", ['[{"term":"Empire","translation":"帝国"}]', "{broken"])
def test_save_checks_existing_file_without_prior_load(ui, tmp_path, content):
    state, errors, records = ui
    path = tmp_path / "unsafe.json"
    path.write_text(content, encoding="utf-8")
    state.glossary_path_var.set(str(path))
    original = path.read_bytes()
    state.save_glossary_ui()
    assert len(errors) == 1
    assert path.read_bytes() == original


def test_remembered_unsafe_path_stays_blocked_after_file_removal(ui, paratranz_file):
    state, errors, records = ui
    state.glossary_path_var.set(str(paratranz_file))
    state.load_glossary_ui()
    paratranz_file.unlink()
    state.glossary_path_var.set(str(paratranz_file.parent / "." / paratranz_file.name))
    state.save_glossary_ui()
    assert len(errors) == 2
    assert not paratranz_file.exists()


def test_valid_load_and_save_clears_guard_after_path_change(ui, tmp_path, paratranz_file):
    state, errors, records = ui
    state.glossary_path_var.set(str(paratranz_file))
    state.load_glossary_ui()
    path = tmp_path / "valid.json"
    path.write_text('{"Empire": "帝国"}', encoding="utf-8")
    state.glossary_path_var.set(str(path))
    state.load_glossary_ui()
    assert state._glossary_unsafe_path is None
    assert list(state.glossary_tree.rows.values()) == [("Empire", "帝国")]
    assert state.auto_glossary_tree.rows == {}
    state.glossary_tree.insert("", "end", values=("Protectorate", "保護国"))
    state.save_glossary_ui()
    assert len(errors) == 1
    assert core.load_glossary(path) == {"Empire": "帝国", "Protectorate": "保護国"}


def test_save_to_new_name_is_allowed_after_bad_load(ui, tmp_path, paratranz_file):
    state, errors, records = ui
    state.glossary_path_var.set(str(paratranz_file))
    original = paratranz_file.read_bytes()
    state.load_glossary_ui()
    path = tmp_path / "new.json"
    state.glossary_path_var.set(str(path))
    state.save_glossary_ui()
    assert len(errors) == 1
    assert core.load_glossary(path) == {"Existing": "既存", "Automatic": "自動"}
    assert paratranz_file.read_bytes() == original
