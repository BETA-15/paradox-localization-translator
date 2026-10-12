"""11 言語の画面で、文字が切れる・枠の外にはみ出す部品が無いこと（v0.13.0 で著者がドイツ語で見つけた）。

画面（Tk）を作るので、PLT_GUI_TESTS=1 のときだけ動かす（画面を持てない所で Tk を起動すると Python が強制終了する）。
ウィンドウは 1180x800（小さい画面のときの初期の大きさで、最小の幅）。道具は tools/measure_ui_overflow.py。
"""
import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(os.environ.get("PLT_GUI_TESTS") != "1", reason="画面が要る（PLT_GUI_TESTS=1 のときだけ）")
def test_no_clipped_or_overflowing_widgets_in_any_language(tmp_path):
    out = tmp_path / "overflow.json"
    subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "measure_ui_overflow.py"), "--size", "1180x800",
                    "--json", str(out), "--tag", f"plt-gui-test-{uuid.uuid4()}"],
                   check=True, timeout=1500, cwd=ROOT, capture_output=True)
    results = json.loads(out.read_text(encoding="utf-8"))
    problems = {lang: [f"[{i['tab']}] {i['class']} {i['need']}/{i['have']} {i['text'][:40]}" for i in r["issues"]]
                for lang, r in results.items() if r["count"]}
    assert not problems, problems
