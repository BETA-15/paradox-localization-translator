"""作り物の翻訳 Mod を作る道具（「日本語のみ」の機能の11言語化 L0・L4 の試験用）。

この Mac には、英語以外の「訳だけを入れた別の Mod」（+JP のような単独の翻訳 Mod）が無い。
元の Mod に同梱されている l_<言語> のファイルだけを抜き出して、別の Mod のフォルダを作り、紐付けを試せるようにする。

  python tools/make_fake_translation_mod.py SOURCE_MOD LANG OUT_DIR [--name NAME] [--english-copy]

- SOURCE_MOD：元の Mod のフォルダ（読むだけ。書き込まない）。
- LANG：抜き出す言語（korean, russian, german, simp_chinese など）。
- OUT_DIR：作る Mod のフォルダ（中身は消して作り直す）。**Steam Workshop・ゲームの mod フォルダの中には作らない**（作ろうとしたら止める）。
- --english-copy：訳ではなく、l_english の値をそのまま l_<LANG> として写した「英語の写し」を作る（翻訳 Mod とみなさないことの試験用）。
- --drop N：抜き出す l_<LANG> のファイルのうち、N 個おきに1個を入れない（欠損のある翻訳 Mod。紐付けの「欠損あり」の試験用）。
- --stripped-source DIR：元の Mod を DIR に写し、その中から l_<LANG> のファイルを取り除く。元の Mod が訳を同梱していると
  「Mod の中に訳あり」になって外の翻訳 Mod の照合が働かないため、この写しを元の Mod として試す。
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import translator_core as core  # noqa: E402

FORBIDDEN_PARTS = ("steamapps", "Paradox Interactive")


def _check_out_dir(out: Path) -> None:
    resolved = str(out.resolve())
    if any(part in resolved for part in FORBIDDEN_PARTS):
        raise SystemExit(f"作り物の Mod は作業用のフォルダに作る（Workshop・ゲームの mod フォルダは禁止）: {resolved}")


def _language_files(mod_root: Path, lang: str) -> list:
    loc = core.mod_localization_root(mod_root)
    out = []
    for fp in core.gather_yml_files(loc) if loc else []:
        try:
            if core.parse_localization_file(fp)[0] == lang:
                out.append(fp)
        except Exception:
            continue
    return loc, out


def strip_source(source: Path, lang: str, dest: Path) -> dict:
    """元の Mod を dest に写し、l_<lang> のファイルを取り除く（元の Mod は読むだけ）。"""
    _check_out_dir(dest)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("*.png", "*.dds", "*.tga", "*.ogg", "*.wav", "*.mp3"))
    _loc, files = _language_files(dest, lang)
    for fp in files:
        fp.unlink()
    return {"stripped_source": str(dest), "removed_files": len(files)}


def make(source: Path, lang: str, out: Path, name: str = "", english_copy: bool = False, drop: int = 0) -> dict:
    _check_out_dir(out)
    source_name = core.detect_mod_name(source) or source.name
    loc, files = _language_files(source, "english" if english_copy else lang)
    if not files:
        raise SystemExit(f"{source} に l_{'english' if english_copy else lang} のファイルがありません")
    if out.exists():
        shutil.rmtree(out)
    loc_name = loc.name  # localization か localisation（ゲームに合わせる）
    keys = 0
    dropped = 0
    for index, fp in enumerate(files):
        if drop and index % drop == drop - 1:
            dropped += 1
            continue
        rel = fp.relative_to(loc)
        text = core.read_localization_text(fp)
        if english_copy:
            # 中身は英語のまま、言語の見出しとファイル名だけを l_<lang> にする
            text = re.sub(r"^(﻿?)l_english:", rf"\1l_{lang}:", text, count=1, flags=re.M)
            rel = Path(*[lang if part == "english" else part.replace("l_english", f"l_{lang}") for part in rel.parts])
        dest = out / loc_name / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8-sig")
        keys += len(core.parse_localization_file(dest)[1])
    mod_name = name or f"{source_name} - {lang} translation (test)"
    descriptor = (f'version="1.0"\ntags={{\n\t"Translation"\n}}\nname="{mod_name}"\n'
                  f'dependencies={{\n\t"{source_name}"\n}}\n')
    (out / "descriptor.mod").write_text(descriptor, encoding="utf-8")
    return {"source": str(source), "source_name": source_name, "lang": lang, "out": str(out), "name": mod_name,
            "files": len(files) - dropped, "dropped_files": dropped, "keys": keys, "english_copy": english_copy}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source")
    parser.add_argument("lang")
    parser.add_argument("out")
    parser.add_argument("--name", default="")
    parser.add_argument("--english-copy", action="store_true")
    parser.add_argument("--drop", type=int, default=0)
    parser.add_argument("--stripped-source", default="")
    args = parser.parse_args(argv)
    print(make(Path(args.source), args.lang, Path(args.out), args.name, args.english_copy, args.drop))
    if args.stripped_source:
        print(strip_source(Path(args.source), args.lang, Path(args.stripped_source)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
