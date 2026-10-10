"""同じゲームの保管場所（ローカル・Steam Workshop）をまたいで日本語化Modを照合する。"""
from __future__ import annotations

import importlib
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("PARADOX_TRANSLATOR_DATA_ROOT", tempfile.mkdtemp(prefix="plt-cross-loc-"))
main = importlib.import_module("main")
core = main.core


def _mod(root: Path, lang: str, key: str = "k", text: str = "Hello") -> Path:
    d = root / "localisation" / lang
    d.mkdir(parents=True)
    (d / f"x_l_{lang}.yml").write_text(f'﻿l_{lang}:\n {key}:0 "{text}"\n', encoding="utf-8")
    (root / "descriptor.mod").write_text(f'name="{root.name}"\n', encoding="utf-8")
    return root


def _locations(tmp_path):
    ws = tmp_path / "steam" / "steamapps" / "workshop" / "content" / "394360"
    local = tmp_path / "Paradox Interactive" / "Hearts of Iron IV" / "mod"
    ck3 = tmp_path / "Paradox Interactive" / "Crusader Kings III" / "mod"
    src = _mod(ws / "111", "english")
    ja = _mod(local / "my_ja", "japanese", text="こんにちは")
    other = _mod(ck3 / "ck3_mod", "english")
    rows = [
        {"game": "Hearts of Iron IV", "kind": "Steam Workshop", "path": str(ws)},
        {"game": "Hearts of Iron IV", "kind": "ローカルMod", "path": str(local)},
        {"game": "Crusader Kings III", "kind": "ローカルMod", "path": str(ck3)},
    ]
    return rows, src, ja, other


def _state(rows):
    s = SimpleNamespace(detected_mod_locations=rows)
    s._collect_mod_roots_from_location_rows = lambda r: main.App._collect_mod_roots_from_location_rows(s, r)
    return s


def test_pool_spans_all_locations_of_the_selected_game(tmp_path):
    rows, src, ja, other = _locations(tmp_path)
    s = _state(rows)
    pool = main.App._game_wide_translation_pool(s, [rows[0]], [src])
    assert src in pool and ja in pool  # ワークショップだけ選んでも、ローカルの日本語化Modが照合相手に入る
    assert other not in pool  # 別のゲームは混ぜない
    assert pool[0] == src  # 選んだ場所のModが先


def test_pool_without_known_game_falls_back_to_selection(tmp_path):
    rows, src, ja, other = _locations(tmp_path)
    s = _state(rows)
    pool = main.App._game_wide_translation_pool(s, [{"path": rows[0]["path"], "game": "", "kind": ""}], [src])
    assert pool == [src]


def test_research_keeps_results_from_other_locations(tmp_path):
    a = {"mod": "A", "path": str(tmp_path / "ws" / "a")}
    b = {"mod": "B", "path": str(tmp_path / "local" / "b")}
    kept = main.App._results_without_roots([a, b], [Path(a["path"])])
    assert kept == [b]
