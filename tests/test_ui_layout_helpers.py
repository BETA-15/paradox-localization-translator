import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
import i18n

from ui_layout import FlowRow, WrappingCheck, _autowrap, flow_rows, initial_pane_split, pane_split, wrap_width


@pytest.mark.parametrize("width,padding,expected", [
    (430, 18, 412), (166, 18, 148), (342, 16, 326),
    (1, 18, 1), (0, 0, 1), (20, 40, 1),
])
def test_wrap_width_tracks_available_space(width, padding, expected):
    assert wrap_width(width, padding) == expected


@pytest.mark.parametrize("width,widths,gap,expected", [
    (300, [], 6, []),
    (300, [100, 100, 88], 6, [[0, 1, 2]]),
    (299, [100, 100, 88], 6, [[0, 1], [2]]),
    (115, [115, 115, 115], 6, [[0], [1], [2]]),
    (100, [140, 40, 40], 6, [[0], [1, 2]]),
    (0, [20, 30], 6, [[0], [1]]),
    (80, [40, 40], 0, [[0, 1]]),
])
def test_flow_preserves_order_and_wraps_at_boundary(width, widths, gap, expected):
    assert flow_rows(width, widths, gap) == expected


def test_resize_reflows_without_losing_items():
    widths = [115, 210, 233, 160, 320]
    assert flow_rows(1180, widths, 6) == [[0, 1, 2, 3, 4]]
    assert flow_rows(324, widths, 6) == [[0], [1], [2], [3], [4]]
    assert flow_rows(700, widths, 6) == [[0, 1, 2], [3, 4]]


def test_every_non_oversize_row_fits():
    widths = [115, 210, 233, 160, 320]
    for available in range(1, 1200):
        rows = flow_rows(available, widths, 6)
        assert [index for row in rows for index in row] == list(range(len(widths)))
        for row in rows:
            total = sum(widths[index] for index in row) + 6 * (len(row) - 1)
            assert total <= available or len(row) == 1


class FakeWidget:
    def __init__(self, width=100, height=24, text="", children=()):
        self.width = width
        self.height = height
        self.options = {"text": text, "wraplength": 100}
        self.children = list(children)
        self.bindings = {}
        self.master = SimpleNamespace()
        self.exists = True

    def winfo_width(self):
        return self.width

    def winfo_reqwidth(self):
        return self.width

    def winfo_reqheight(self):
        return self.height

    def winfo_exists(self):
        return self.exists

    def winfo_children(self):
        return self.children

    def cget(self, key):
        return self.options[key]

    def configure(self, **options):
        self.options.update(options)

    def bind(self, event, callback, add=None):
        assert add == "+"
        self.bindings[event] = callback

    def place(self, **options):
        self.position = options


def test_autowrap_uses_allocated_label_width_including_sibling_space():
    parent = FakeWidget(width=430)
    label = FakeWidget(width=166)
    assert _autowrap(label, parent, padding=4) is label
    parent.bindings["<Configure>"]()
    assert label.cget("wraplength") == 162
    label.width = 26
    label.bindings["<Configure>"]()
    assert label.cget("wraplength") == 120  # 最小の幅（これより狭い折り返しは読めない）
    label.width = 600
    label.bindings["<Configure>"]()
    assert label.cget("wraplength") == 596
    label.exists = False
    parent.bindings["<Configure>"]()
    assert label.cget("wraplength") == 596


def test_autowrap_before_mapping_and_tiny_allocation():
    parent = FakeWidget(width=20)
    label = FakeWidget(width=1)
    _autowrap(label, parent, padding=30)
    label.bindings["<Map>"]()
    assert label.cget("wraplength") == 120  # 最小の幅


def test_flow_adapter_preserves_margins_heights_and_right_aligned_order():
    first = FakeWidget(width=100, height=24)
    second = FakeWidget(width=100, height=30)
    right_first = FakeWidget(width=40)
    right_second = FakeWidget(width=50)
    row = SimpleNamespace(
        _items=[(first, "left", 0, 0), (second, "left", 6, 0),
                (right_first, "right", 0, 0), (right_second, "right", 0, 6)],
        _layout_pending=True, winfo_width=lambda: 210, winfo_reqheight=lambda: 1,
        configure=lambda **options: setattr(first, "row_options", options),
    )
    FlowRow._layout(row)
    assert first.position == {"x": 0, "y": 3}
    assert second.position == {"x": 106, "y": 0}
    assert right_second.position == {"x": 114, "y": 34}
    assert right_first.position == {"x": 170, "y": 34}
    assert first.row_options == {"height": 58}
    assert row._layout_pending is None


def test_flow_adapter_stretches_separators_and_ignores_destroyed_children():
    button = FakeWidget(width=115, height=24)
    separator = FakeWidget(width=2, height=1)
    removed = FakeWidget(width=500)
    removed.exists = False
    row = SimpleNamespace(
        _items=[(button, "left", 0, 0), (separator, "left", 8, 8), (removed, "left", 0, 0)],
        _fills={separator: "y"}, _layout_pending=True,
        winfo_width=lambda: 200, winfo_reqheight=lambda: 24, configure=lambda **options: None,
    )
    FlowRow._layout(row)
    assert separator.position == {"x": 123, "y": 0, "height": 24}
    assert not hasattr(removed, "position")


def test_wrapping_check_label_invokes_original_checkbutton():
    invoked = []
    widget = SimpleNamespace(check=SimpleNamespace(invoke=lambda: invoked.append(True)))
    assert WrappingCheck._toggle(widget) == "break"
    assert invoked == [True]


def test_initial_pane_split_does_not_override_user_resizing():
    assert pane_split(1180, 2, 3) == 472
    paned = FakeWidget(width=1180)
    positions = []
    paned.sashpos = lambda index, position: positions.append((index, position))
    initial_pane_split(paned, 2, 3)
    paned.bindings["<Map>"](SimpleNamespace(widget=paned))
    paned.width = 800
    paned.bindings["<Map>"](SimpleNamespace(widget=paned))
    assert positions == [(0, 472)]


@pytest.mark.parametrize("ui_language", ["japanese", "english", "german", "russian"])
def test_target_dependent_labels_refresh_without_changing_settings(ui_language):
    source = Path(__file__).resolve().parents[1] / "app" / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                  and node.name == "_refresh_target_language_labels")
    scope = {"i18n": i18n, "tk": SimpleNamespace(TclError=RuntimeError), "FlowRow": FlowRow}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(source), "exec"), scope)
    previous_ui = i18n.get_ui_language()
    try:
        i18n.set_ui_language(ui_language)
        keys = ['u5.repair_existing', 'u1.intro', 'u3.diff_files', 'u3.drop_pair',
                'u3.save_translation_file', 'u3.target_language', 'u3.editable_target',
                'u6.also_search_other_mods_for_japanese', 'u6.overwrite_mod_with_completed_translation']
        labels = [FakeWidget(text=i18n.t(key, target_name=i18n.t('lang.japanese'))) for key in keys]
        variable = SimpleNamespace(value=True)
        check = FakeWidget(children=[labels[0]])
        check.variable = variable
        state = SimpleNamespace(tab_models=FakeWidget(children=[check]),
                                tab_translate=FakeWidget(children=labels[1:]))
        previous = 'japanese'
        for target in ('korean', 'french', 'japanese'):
            scope['_refresh_target_language_labels'](state, previous, target)
            for key, label in zip(keys, labels):
                assert label.cget('text') == i18n.t(key, target_name=i18n.t('lang.' + target))
            assert variable.value is True
            previous = target
    finally:
        i18n.set_ui_language(previous_ui)


def test_wraplength_does_not_creep_when_the_parent_shrinks_to_fit():
    """閉じるときの確認の窓で、折り返しを狭める → 窓が縮む → … が止まらず画面が固まった（v0.13.0 候補）。"""
    from ui_layout import next_wraplength
    current = 420
    width = current + 4  # 窓の幅＝ラベルの幅（折り返しの幅＋余白）
    for _ in range(100):
        new = next_wraplength(current, width, padding=4)
        if new is None:
            break
        current = new
        width = current + 4
    else:
        raise AssertionError("折り返しの幅が止まらない")
    assert current == 420
    assert next_wraplength(100, 600, padding=4) == 596  # 大きく広がるときは追従する
    assert next_wraplength(300, 20, padding=4) == 120  # 最小の幅より狭くしない


def test_autowrap_stops_two_state_oscillation():
    """ラベルの幅で親の幅が決まる所で、折り返しの幅が 420 と 446 を行き来して止まらなかった（閉じるときの確認の窓）。"""
    parent = FakeWidget(width=460)
    label = FakeWidget(width=424)
    _autowrap(label, parent, padding=4)
    label.configure(wraplength=420)
    widths = [450, 424, 450, 424, 450, 424]
    seen = []
    for width in widths:
        label.width = width
        label.bindings["<Configure>"]()
        seen.append(label.cget("wraplength"))
    assert seen[-1] == seen[-3] == seen[-5]  # 行ったり来たりしない
