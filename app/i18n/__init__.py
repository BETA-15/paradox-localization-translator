"""画面の文字列の辞書（第3段：画面の表示を11言語に）。

- 言語の名前は翻訳先の言語と同じ（english, japanese, ... translator_core.TARGET_LANGUAGES のキー）。
- 文字列は app/i18n/<言語>/<単位>.py の STRINGS に置く（JSON は PyInstaller が同梱しないので使わない）。
- t(key, **fields) は「選んだ言語 → 英語 → 日本語」の順に探す。どこにも無ければ key をそのまま返す。
- 差し込みは名前付きの欄（{count} など）。足りない欄はそのまま残す（例外を出さない）。
"""
from __future__ import annotations

import locale
import os
import subprocess
import sys
from collections import Counter
from string import Formatter
from typing import Optional

from . import (braz_por, english, french, german, japanese, korean, polish, russian, simp_chinese, spanish,
               turkish)

UI_LANGUAGES = ("english", "french", "german", "spanish", "japanese", "korean", "polish", "braz_por", "russian",
                "simp_chinese", "turkish")
DEFAULT_UI_LANGUAGE = "english"      # OS の言語が11言語に無いとき
LEGACY_UI_LANGUAGE = "japanese"      # 設定ファイルがある（以前から使っている）人の既定

# 言語の選択欄に出す名前（それぞれの言葉で書く）
NATIVE_NAMES = {
    "english": "English", "french": "Français", "german": "Deutsch", "spanish": "Español", "japanese": "日本語",
    "korean": "한국어", "polish": "Polski", "braz_por": "Português (Brasil)", "russian": "Русский",
    "simp_chinese": "简体中文", "turkish": "Türkçe",
}

_PACKAGES = {
    "english": english, "french": french, "german": german, "spanish": spanish, "japanese": japanese,
    "korean": korean, "polish": polish, "braz_por": braz_por, "russian": russian, "simp_chinese": simp_chinese,
    "turkish": turkish,
}

_current = LEGACY_UI_LANGUAGE
MISSING = Counter()      # 選んだ言語に無かった key（英語・日本語に戻った、またはどこにも無かった）
UNKNOWN = Counter()      # どの言語にも無かった key


class _KeepMissing(dict):
    def __missing__(self, key):
        return _MissingField(key)


class _MissingField:
    def __init__(self, key):
        self.key = key

    def __format__(self, spec):
        return "{" + self.key + (":" + spec if spec else "") + "}"

    def __getattr__(self, name):
        return _MissingField(self.key + "." + name)

    def __getitem__(self, key):
        return _MissingField(self.key + "[" + str(key) + "]")


class _MissingFormatter(Formatter):
    def convert_field(self, value, conversion):
        if isinstance(value, _MissingField) and conversion:
            return _MissingField(value.key + "!" + conversion)
        return super().convert_field(value, conversion)


_FORMATTER = _MissingFormatter()


def strings(lang: str) -> dict:
    package = _PACKAGES.get(lang)
    return package.STRINGS if package is not None else {}


def set_ui_language(lang: str) -> str:
    """画面の言語を決める。知らない言語なら英語にする。決まった言語を返す。"""
    global _current
    _current = lang if lang in _PACKAGES else DEFAULT_UI_LANGUAGE
    return _current


def get_ui_language() -> str:
    return _current


def lookup(key: str, lang: Optional[str] = None) -> Optional[str]:
    """ひな形（差し込む前の文字列）。選んだ言語 → 英語 → 日本語。無ければ None。"""
    lang = lang or _current
    for candidate in (lang, "english", "japanese"):
        text = strings(candidate).get(key)
        if text is not None:
            if candidate != lang:
                MISSING[key] += 1
            return text
    MISSING[key] += 1
    UNKNOWN[key] += 1
    return None


def t(key: str, **fields) -> str:
    """画面の言語の文字列。fields は名前付きの欄に差し込む。"""
    template = lookup(key)
    if template is None:
        return key
    if not fields:
        return template
    return _FORMATTER.vformat(template, (), _KeepMissing(fields))


def t_lang(lang: str, key: str, **fields) -> str:
    """言語を指定して引く（ログの rule_id の日本語の説明など、画面の言語と別に要るとき）。"""
    template = lookup(key, lang)
    if template is None:
        return key
    return _FORMATTER.vformat(template, (), _KeepMissing(fields)) if fields else template


# ---------------------------------------------------------------- OS の言語

_LOCALE_PREFIXES = (
    # 先に長いものを見る（pt-BR と pt、zh-Hans と zh-Hant）
    ("zh-hans", "simp_chinese"), ("zh_cn", "simp_chinese"), ("zh-cn", "simp_chinese"), ("zh_sg", "simp_chinese"),
    ("zh-sg", "simp_chinese"), ("zh-hant", None), ("zh_tw", None), ("zh-tw", None), ("zh_hk", None), ("zh-hk", None),
    ("pt-br", "braz_por"), ("pt_br", "braz_por"),
    ("en", "english"), ("fr", "french"), ("de", "german"), ("es", "spanish"), ("ja", "japanese"),
    ("ko", "korean"), ("pl", "polish"), ("ru", "russian"), ("tr", "turkish"), ("zh", "simp_chinese"),
)


def language_from_locale(value: str) -> Optional[str]:
    """OS の言語の値（"ja"、"ja_JP.UTF-8"、"zh-Hans-CN"、"pt-BR" など）を画面の言語にする。11言語に無ければ None。

    ポルトガル語はブラジル以外（pt-PT）も、11言語ではブラジルのものしか無いので braz_por にする。
    """
    text = str(value or "").strip().lower()
    if not text or text in ("c", "posix"):
        return None
    for prefix, lang in _LOCALE_PREFIXES:
        if text == prefix or text.startswith(prefix + "-") or text.startswith(prefix + "_") \
                or text.startswith(prefix + ".") or text.startswith(prefix + "@") or \
                (len(prefix) > 2 and text.startswith(prefix)):
            return lang
    if text.startswith("pt"):
        return "braz_por"
    return None


def _os_locale_values(platform: str, env: dict) -> list:
    values = []
    if platform == "darwin":
        try:
            out = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True,
                                 timeout=3).stdout
            values += [part.strip().strip('"(),') for part in out.replace("\n", " ").split(",") if part.strip()]
        except Exception:
            pass
    elif platform.startswith("win"):
        try:
            import ctypes  # noqa: F401
            lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
            name = locale.windows_locale.get(lang_id)
            if name:
                values.append(name)
        except Exception:
            pass
    for key in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        if env.get(key):
            values += str(env[key]).split(":")
    try:
        values.append(locale.getlocale()[0] or "")
    except Exception:
        pass
    return [v for v in values if v]


def detect_os_language(platform: Optional[str] = None, env: Optional[dict] = None,
                       values: Optional[list] = None) -> str:
    """OS の言語に合わせた画面の言語。11言語に無ければ英語。values を渡すとそれを使う（テスト用）。"""
    candidates = values if values is not None else _os_locale_values(platform or sys.platform, env or dict(os.environ))
    for value in candidates:
        lang = language_from_locale(value)
        if lang:
            return lang
        if value and str(value).strip().lower() not in ("c", "posix"):
            return DEFAULT_UI_LANGUAGE  # 最初に挙がった言語が11言語に無い（例：繁体字）なら英語
    return DEFAULT_UI_LANGUAGE


def initial_ui_language(saved: Optional[str], has_existing_settings: bool, detect=detect_os_language) -> str:
    """起動したときの画面の言語。

    - 設定に保存した言語があればそれ。
    - 設定ファイルがすでにある（以前から使っている）人で保存した値が無ければ日本語（今までの画面のまま）。
    - 初めて起動した人は OS の言語（11言語に無ければ英語）。
    """
    if saved in _PACKAGES:
        return saved
    if has_existing_settings:
        return LEGACY_UI_LANGUAGE
    return detect()
