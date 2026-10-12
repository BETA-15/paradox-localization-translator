from __future__ import annotations

import ast
import importlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

import i18n


ROOT = Path(__file__).resolve().parents[1]
TAB_NAMES = (
    'translate', 'chinese', 'review', 'diff', 'search', 'glossary', 'models',
    'monitor', 'status', 'diagnostic', 'backup', 'settings', 'help',
)
ORIGINAL_KEYS = (
    'p0.translation_queue', 'p0.tab.chinese', 'p0.qa_comparison_editor',
    'p0.difference_scan', 'p0.translation_search', 'p0.glossary',
    'p0.model_connection', 'p0.untranslated_monitor', 'p0.translation_status',
    'p0.tab.diagnostic', 'p0.restore_backup', 'p0.tab.settings', 'p0.help',
)
TAB_KEYS = tuple(f'p0.tab_label.{name}' for name in TAB_NAMES)


@pytest.mark.parametrize('language', i18n.UI_LANGUAGES)
def test_tab_keys_exist_in_common_dictionary(language):
    strings = importlib.import_module(f'i18n.{language}.p0_common').STRINGS
    for key in TAB_KEYS:
        assert key in strings, (language, key)
        assert isinstance(strings[key], str) and strings[key].strip()


@pytest.mark.parametrize('language', ('japanese', 'korean', 'simp_chinese'))
def test_unchanged_tab_labels(language):
    strings = importlib.import_module(f'i18n.{language}.p0_common').STRINGS
    for key, original_key in zip(TAB_KEYS, ORIGINAL_KEYS):
        assert strings[key] == strings[original_key], (language, key)


def test_notebook_uses_dedicated_i18n_keys():
    tree = ast.parse((ROOT / 'app' / 'main.py').read_text(encoding='utf-8'))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name)
             and node.func.value.id == 'nb' and node.func.attr == 'add']
    assert len(calls) == len(TAB_KEYS) == 13
    for call, key in zip(sorted(calls, key=lambda node: node.lineno), TAB_KEYS):
        text = next(keyword.value for keyword in call.keywords if keyword.arg == 'text')
        assert isinstance(text, ast.Call)
        assert ast.unparse(text.func) == 'i18n.t'
        assert len(text.args) == 1 and isinstance(text.args[0], ast.Constant)
        assert text.args[0].value == key


def test_measurement_tool_counts_every_label_and_padding(monkeypatch):
    tk = pytest.importorskip('tkinter')
    from tkinter import font

    calls = []

    class FakeRoot:
        def withdraw(self):
            calls.append('withdraw')

        def destroy(self):
            calls.append('destroy')

    class FakeFont:
        def measure(self, label):
            return len(label) * 7

    root = FakeRoot()

    def default_font(name, **kwargs):
        assert name == 'TkDefaultFont'
        assert kwargs == {'root': root}
        return FakeFont()

    monkeypatch.setattr(tk, 'Tk', lambda: root)
    monkeypatch.setattr(font, 'nametofont', default_font)
    tool = runpy.run_path(str(ROOT / 'tools' / 'measure_tab_widths.py'))
    assert tool['TAB_KEYS'] == TAB_KEYS
    assert tool['ORIGINAL_KEYS'] == ORIGINAL_KEYS
    results = tool['measure_tab_widths']()
    assert set(results) == set(i18n.UI_LANGUAGES)
    assert calls == ['withdraw', 'destroy']
    for language, result in results.items():
        strings = importlib.import_module(f'i18n.{language}.p0_common').STRINGS
        assert result['labels'] == [strings[key] for key in TAB_KEYS]
        assert result['before'] == sum(len(strings[key]) * 7 + 20 for key in ORIGINAL_KEYS)
        assert result['after'] == sum(len(strings[key]) * 7 + 20 for key in TAB_KEYS)


@pytest.fixture(scope='module')
def measured_widths():
    # 画面（Tk）を作るので、PLT_GUI_TESTS=1 のときだけ測る。画面を持てない所（GPT の作業・CI の一部）で
    # Tk を起動すると Python が強制終了するため、起動して確かめる形にはしない。
    if os.environ.get('PLT_GUI_TESTS') != '1':
        pytest.skip('タブの幅は PLT_GUI_TESTS=1 のときだけ測る（画面が要る）')
    result = subprocess.run(
        [sys.executable, '-B', str(ROOT / 'tools' / 'measure_tab_widths.py'), '--json'],
        capture_output=True, text=True, timeout=30, check=True, cwd=ROOT,
    )
    return json.loads(result.stdout)


@pytest.mark.parametrize('language', i18n.UI_LANGUAGES)
def test_tab_widths_fit(language, measured_widths):
    result = measured_widths[language]
    assert len(result['labels']) == 13
    assert result['after'] <= 1400, (language, result)
