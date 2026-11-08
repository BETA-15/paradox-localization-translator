"""PARADOX_TRANSLATOR_DATA_ROOT で置き場所を決めた開発版が、配布版の保存場所の記録を書き換えないこと（v0.13.1）。"""
import os
from types import SimpleNamespace

import pytest

import i18n
import main

LOCATOR = (".config", "paradox-localization-translator", "location.json")


def _record_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(main.subprocess, "run", lambda *a, **k: calls.append(a))
    return calls


@pytest.mark.skipif(os.name == "nt", reason="Windows はレジストリに書く")
def test_preference_is_not_saved_when_env_decides_the_root(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("PARADOX_TRANSLATOR_DATA_ROOT", str(tmp_path / "dev-data"))
    calls = _record_calls(monkeypatch)
    main._save_data_root_preference(tmp_path / "elsewhere")
    assert calls == []
    assert not tmp_path.joinpath(*LOCATOR).exists()


@pytest.mark.skipif(os.name == "nt", reason="Windows はレジストリに書く")
def test_preference_is_saved_without_env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("PARADOX_TRANSLATOR_DATA_ROOT", raising=False)
    calls = _record_calls(monkeypatch)
    main._save_data_root_preference(tmp_path / "elsewhere")
    assert calls or tmp_path.joinpath(*LOCATOR).exists()


def test_change_button_explains_env_instead_of_moving(monkeypatch, tmp_path):
    monkeypatch.setenv("PARADOX_TRANSLATOR_DATA_ROOT", str(tmp_path / "dev-data"))
    shown = []
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *a, **k: shown.append(a))
    monkeypatch.setattr(main.filedialog, "askdirectory",
                        lambda *a, **k: pytest.fail("フォルダを選ばせてはいけない"))
    fake = SimpleNamespace(_active_file_operation_names=lambda: [], data_root_move_thread=None)
    main.App.change_data_root(fake)
    assert shown and shown[0][1] == i18n.t('u5.storage_env_override', env="PARADOX_TRANSLATOR_DATA_ROOT")


def test_env_override_note_exists_in_every_language():
    for lang in i18n.UI_LANGUAGES:
        text = i18n.strings(lang).get('u5.storage_env_override', '')
        assert "{env}" in text, lang
