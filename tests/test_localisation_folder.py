"""HOI4・Stellaris・EU4 の Mod は localization ではなく localisation フォルダを使う。

どちらの綴りでも Mod として認識し、訳文を正しい側へ書き戻すことを確かめる。
"""
from pathlib import Path

from app import translator_core as core


def _make_mod(root: Path, folder: str = "localisation", name: str = "Test Mod") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    (root / "descriptor.mod").write_text(f'name="{name}"\n', encoding="utf-8")
    eng = root / folder / "english"
    eng.mkdir(parents=True)
    (eng / "test_l_english.yml").write_text(
        '﻿l_english:\n test_key:0 "Hello"\n', encoding="utf-8")
    return root


def test_is_localization_dir_name_accepts_both_spellings():
    assert core.is_localization_dir_name("localization")
    assert core.is_localization_dir_name("localisation")
    assert core.is_localization_dir_name("Localisation")
    assert not core.is_localization_dir_name("english")


def test_mod_localization_root_finds_localisation(tmp_path):
    mod = _make_mod(tmp_path / "hoi4_mod")
    assert core.mod_localization_root(mod) == mod / "localisation"
    assert core.mod_localization_root(mod / "localisation") == mod / "localisation"


def test_find_mod_roots_finds_localisation_mods(tmp_path):
    workshop = tmp_path / "394360"
    a = _make_mod(workshop / "111", "localisation")
    b = _make_mod(workshop / "222", "localization")
    assert core.find_mod_roots(workshop) == [a, b]
    assert core.find_mod_roots(a) == [a]
    assert core.find_mod_roots(a / "localisation") == [a]


def test_find_mod_roots_fallback_two_levels_localisation(tmp_path):
    root = tmp_path / "mods"
    mod = _make_mod(root / "category" / "mod1", "localisation")
    assert core.find_mod_roots(root) == [mod]


def test_count_mod_roots_fast_counts_localisation_without_descriptor(tmp_path):
    parent = tmp_path / "workshop"
    mod = parent / "333" / "localisation"
    mod.mkdir(parents=True)
    assert core._count_mod_roots_fast(parent) == 1


def test_collect_mod_language_entries_reads_localisation(tmp_path):
    mod = _make_mod(tmp_path / "hoi4_mod")
    data = core._collect_mod_language_entries(mod)
    assert data["localization"] == str(mod / "localisation")
    assert data["english"] == {"test_key": "Hello"}


def test_localization_dir_path_prefers_existing_folder(tmp_path):
    mod = _make_mod(tmp_path / "any_mod", "localisation")
    assert core.localization_dir_path(mod) == mod / "localisation"
    other = _make_mod(tmp_path / "ck3_mod", "localization")
    assert core.localization_dir_path(other) == other / "localization"


def test_localization_dir_path_default_follows_game(tmp_path):
    hoi4 = tmp_path / "Paradox Interactive" / "Hearts of Iron IV" / "mod" / "new_mod"
    hoi4.mkdir(parents=True)
    assert core.localization_dir_path(hoi4).name == "localisation"
    workshop = tmp_path / "steamapps" / "workshop" / "content" / "394360" / "999"
    workshop.mkdir(parents=True)
    assert core.localization_dir_path(workshop).name == "localisation"
    ck3 = tmp_path / "Paradox Interactive" / "Crusader Kings III" / "mod" / "new_mod"
    ck3.mkdir(parents=True)
    assert core.localization_dir_path(ck3).name == "localization"


def test_mod_profile_skips_localisation_folder(tmp_path):
    mod = _make_mod(tmp_path / "hoi4_mod")
    (mod / "common").mkdir()
    (mod / "common" / "x.txt").write_text("a", encoding="utf-8")
    rows = core.build_translation_mod_index([mod])
    assert rows == []  # 日本語が無いので候補にならない（落ちないこと）
    ja = mod / "localisation" / "japanese"
    ja.mkdir()
    (ja / "test_l_japanese.yml").write_text(
        '﻿l_japanese:\n test_key:0 "こんにちは"\n', encoding="utf-8")
    rows = core.build_translation_mod_index([mod])
    assert len(rows) == 1
    assert rows[0]["localization"] == str(mod / "localisation")
    assert "localisation" not in [n.lower() for n in rows[0]["localization_folder_names"]]


def test_hoi4_workshop_mods_are_discovered_and_listed(tmp_path):
    steam = tmp_path / "steam"
    workshop = steam / "steamapps" / "workshop" / "content" / "394360"
    a = _make_mod(workshop / "2000001", "localisation", "Road to 56")
    # HOI4 の Workshop Mod には descriptor.mod が無いものもある
    b = workshop / "2000002"
    (b / "localisation" / "english").mkdir(parents=True)
    (b / "localisation" / "english" / "b_l_english.yml").write_text(
        '﻿l_english:\n b_key:0 "World"\n', encoding="utf-8")
    rows = core.discover_paradox_mod_locations(home=tmp_path / "home", platform="darwin",
                                               extra_steam_roots=[steam])
    hoi4 = [r for r in rows if r["game"] == "Hearts of Iron IV"]
    assert len(hoi4) == 1 and hoi4[0]["mod_count"] == 2
    assert core.find_mod_roots(workshop) == [a, b]
    assert core._collect_mod_language_entries(b)["english"] == {"b_key": "World"}
