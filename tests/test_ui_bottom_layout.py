import ast
from pathlib import Path

import pytest


SOURCE = Path(__file__).resolve().parents[1] / "app" / "main.py"


def layout_method(name):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name == name)


def pack_call(method, widget):
    calls = [node for node in ast.walk(method)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "pack" and ast.unparse(node.func.value) == widget]
    assert len(calls) == 1
    return calls[0]


def options(call):
    return {keyword.arg: ast.literal_eval(keyword.value) for keyword in call.keywords}


@pytest.mark.parametrize("method_name", ["_build_translate_tab", "_build_chinese_tab"])
def test_translation_settings_use_existing_vertical_scroll_area(method_name):
    method = layout_method(method_name)
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
             and ast.unparse(node.func) == "self._make_vertical_scroll_area"]
    assert len(calls) == 1
    assert ast.unparse(calls[0].args[0]) == "left_pane"
    assert options(pack_call(method, "left_outer")) == {"fill": "both", "expand": True}


@pytest.mark.parametrize("method_name,progress", [
    ("_build_translate_tab", "self.progress"),
    ("_build_chinese_tab", "self.chinese_progress"),
])
def test_translation_reserves_bottom_controls_before_expanding_queue(method_name, progress):
    method = layout_method(method_name)
    widgets = ["logbox", progress, "progress_label", "actions", "qbox"]
    calls = [pack_call(method, widget) for widget in widgets]
    assert [call.lineno for call in calls] == sorted(call.lineno for call in calls)
    assert all(options(call)["side"] == "bottom" for call in calls[:-1])
    assert options(calls[-1])["expand"] is True


def test_diagnostics_reserves_actions_and_conflict_controls_before_lists():
    method = layout_method("_build_diagnostic_tab")
    for bottom, expanding in [("actions", "targets"), ("tbtn", "tw"),
                              ("detail", "resultbox"), ("conflict_controls", "rw")]:
        bottom_call = pack_call(method, bottom)
        expanding_call = pack_call(method, expanding)
        assert bottom_call.lineno < expanding_call.lineno
        assert options(bottom_call)["side"] == "bottom"
        assert options(expanding_call)["expand"] is True


@pytest.mark.parametrize("method_name", [
    "_build_translate_tab", "_build_chinese_tab", "_build_diagnostic_tab",
])
def test_expanding_widgets_have_small_requested_heights(method_name):
    method = layout_method(method_name)
    calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
             and ast.unparse(node.func) in {"ttk.Treeview", "tk.Text"}]
    assert calls
    for call in calls:
        height = next(keyword.value for keyword in call.keywords if keyword.arg == "height")
        assert 1 <= ast.literal_eval(height) <= 4
