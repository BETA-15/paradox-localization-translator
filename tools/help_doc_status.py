"""使い方の説明書の訳し直しが要る節と言語を出す道具（第3段 5-2 章）。

  python tools/help_doc_status.py            … 言語ごとに、訳し直しが要る節を出す
  python tools/help_doc_status.py --stamp X  … 言語 X の SOURCE_HASHES を今の原本に合わせて書き直す（訳し直した後に使う）
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import i18n  # noqa: E402


from i18n.help import help_module, section_hash, source_hashes  # noqa: E402,F401  アプリと同じ計算を使う


def language_status(lang: str) -> dict:
    """{"translated": bool, "order_ok": bool, "stale": [節 ID], "missing": [節 ID]}"""
    src = source_hashes()
    mod = help_module(lang)
    sections = list(getattr(mod, "HELP_SECTIONS", []) or [])
    if not sections:
        return {"translated": False, "order_ok": True, "stale": [], "missing": list(src)}
    ids = [sid for sid, _ in sections]
    hashes = dict(getattr(mod, "SOURCE_HASHES", {}) or {})
    stale = [sid for sid in src if sid in ids and hashes.get(sid) != src[sid]]
    return {"translated": True, "order_ok": ids == list(src), "stale": stale,
            "missing": [sid for sid in src if sid not in ids]}


def stamp(lang: str) -> None:
    """訳し直した言語の SOURCE_HASHES を、今の原本の値に書き直す。"""
    path = ROOT / "app" / "i18n" / lang / "help_doc.py"
    text = path.read_text(encoding="utf-8")
    new = "SOURCE_HASHES = " + repr(source_hashes())
    text = re.sub(r"^SOURCE_HASHES = .*$", new, text, flags=re.M)
    path.write_text(text, encoding="utf-8")


def main(argv):
    if argv[:1] == ["--stamp"] and len(argv) == 2:
        stamp(argv[1]); print(f"{argv[1]}: SOURCE_HASHES を更新しました"); return 0
    for lang in i18n.UI_LANGUAGES:
        if lang == "japanese":
            continue
        st = language_status(lang)
        if not st["translated"]:
            print(f"{lang}: まだ訳していません"); continue
        notes = []
        if not st["order_ok"]:
            notes.append("節の並びが原本と違う")
        if st["missing"]:
            notes.append("足りない節: " + ", ".join(st["missing"]))
        if st["stale"]:
            notes.append("訳し直しが要る節: " + ", ".join(st["stale"]))
        print(f"{lang}: " + ("; ".join(notes) if notes else "最新"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
