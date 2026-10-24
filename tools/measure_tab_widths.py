"""Measure the 13 notebook labels using TkDefaultFont, without creating App.

Run with python -B tools/measure_tab_widths.py; --json returns structured results.
Each total includes 20 pixels of padding per tab. A working Tk display is required.
"""
from __future__ import annotations

import argparse
import importlib
import json
import sys
import tkinter as tk
from pathlib import Path
from tkinter import font


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'app'))

import i18n


TAB_KEYS = (
    'p0.tab_label.translate', 'p0.tab_label.chinese', 'p0.tab_label.review',
    'p0.tab_label.diff', 'p0.tab_label.search', 'p0.tab_label.glossary',
    'p0.tab_label.models', 'p0.tab_label.monitor', 'p0.tab_label.status',
    'p0.tab_label.diagnostic', 'p0.tab_label.backup', 'p0.tab_label.settings',
    'p0.tab_label.help',
)
ORIGINAL_KEYS = (
    'p0.translation_queue', 'p0.tab.chinese', 'p0.qa_comparison_editor',
    'p0.difference_scan', 'p0.translation_search', 'p0.glossary',
    'p0.model_connection', 'p0.untranslated_monitor', 'p0.translation_status',
    'p0.tab.diagnostic', 'p0.restore_backup', 'p0.tab.settings', 'p0.help',
)
TAB_PADDING = 20
MAX_WIDTH = 1140  # ウィンドウの最小の幅 1180 で、タブの並びに使える幅


def measure_tab_widths():
    root = tk.Tk()
    try:
        root.withdraw()
        default_font = font.nametofont('TkDefaultFont', root=root)
        results = {}
        for language in i18n.UI_LANGUAGES:
            strings = importlib.import_module(f'i18n.{language}.p0_common').STRINGS
            original_labels = [strings[key] for key in ORIGINAL_KEYS]
            labels = [strings[key] for key in TAB_KEYS]
            results[language] = {
                'before': sum(default_font.measure(label) + TAB_PADDING for label in original_labels),
                'after': sum(default_font.measure(label) + TAB_PADDING for label in labels),
                'labels': labels,
            }
        return results
    finally:
        root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--json', action='store_true', help='Print structured measurements.')
    args = parser.parse_args()
    try:
        results = measure_tab_widths()
    except tk.TclError as error:
        parser.exit(2, f'Tk display unavailable: {error}\n')
    if args.json:
        print(json.dumps(results, ensure_ascii=False))
    else:
        print(f'TkDefaultFont; {TAB_PADDING}px padding per tab; limit {MAX_WIDTH}px')
        for language, result in results.items():
            status = 'OK' if result['after'] <= MAX_WIDTH else 'OVER'
            print(f"{language}: {result['before']} -> {result['after']}px [{status}]")
            print('  ' + ' / '.join(result['labels']))
    return int(any(result['after'] > MAX_WIDTH for result in results.values()))


if __name__ == '__main__':
    raise SystemExit(main())
