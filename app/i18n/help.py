"""使い方タブの説明書を、画面の言語で組み立てる（第3段 5-2 章）。

- 原本は app/i18n/japanese/help_doc.py。ほかの言語は節ごとに訳を持ち、訳した時の原本のハッシュを SOURCE_HASHES に書く。
- 原本が変わったのに訳し直していない節は、古い訳の上に STALE_NOTICE を出す。
- 訳の無い節は英語、英語にも無ければ日本語の原本を出す。
"""
from __future__ import annotations

import hashlib
import importlib


def section_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def help_module(lang: str):
    return importlib.import_module(f"i18n.{lang}.help_doc")


def source_sections() -> list:
    return list(help_module("japanese").HELP_SECTIONS)


def source_hashes() -> dict:
    return {sid: section_hash(body) for sid, body in source_sections()}


def _attr(lang: str, name: str):
    for candidate in (lang, "english", "japanese"):
        try:
            value = getattr(help_module(candidate), name, None)
        except ImportError:
            value = None
        if value:
            return value
    return ""


def help_title(lang: str) -> str:
    return _attr(lang, "HELP_TITLE")


def help_text(lang: str) -> str:
    """画面の言語の説明書の全文。日本語なら原本をそのままつなぐ（v0.12.0 の説明書と一字一句同じ）。"""
    src = source_sections()
    if lang == "japanese":
        return "".join(body for _sid, body in src)
    hashes = source_hashes()
    out = []
    for sid, original in src:
        body = None
        for candidate in (lang, "english"):
            try:
                mod = help_module(candidate)
            except ImportError:
                continue
            translated = dict(getattr(mod, "HELP_SECTIONS", []) or [])
            if sid in translated:
                body = translated[sid]
                if dict(getattr(mod, "SOURCE_HASHES", {}) or {}).get(sid) != hashes[sid]:
                    notice = getattr(mod, "STALE_NOTICE", "") or _attr(lang, "STALE_NOTICE")
                    body = notice + "\n" + body
                break
        out.append(original if body is None else body)
    return "".join(out)
