"""画面のはみ出しを見つける道具（v0.13.0、画面の11言語化）。**画面（Tk）を起動するので、GPT の作業の中では流さない。**

  python tools/measure_ui_overflow.py [--languages english,german] [--json OUT.json] [--shots DIR] [--size 1280x860]

画面の言語ごとに App を作り、すべてのタブを順に表示して、次のものを数える。
- clipped：文字を持つ部品（Label・Button・Checkbutton・Radiobutton・Menubutton）で、必要な幅（winfo_reqwidth）が
  置かれた幅（winfo_width）より大きいもの（文字が切れている）。
- outside：部品の右端が、囲んでいる枠（祖先のどれか）の右端より外に出ているもの（枠の外で見えない）。
--shots を付けると、言語・タブごとの画面写真を DIR/<言語>/<番号>_<タブ>.png に保存する（macOS の screencapture）。
データの置き場所は一時フォルダにし、利用者の設定・キャッシュに触らない。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEXT_CLASSES = {"TLabel", "Label", "TButton", "Button", "TCheckbutton", "Checkbutton", "TRadiobutton",
                "Radiobutton", "TMenubutton", "Menubutton", "TLabelframe.Label"}
TOLERANCE = 2


def _text(widget) -> str:
    try:
        return str(widget.cget("text"))
    except Exception:
        return ""


def _visible_right(widget) -> int:
    """祖先の枠のうち、いちばん左にある右端（その外は見えない）。"""
    right = widget.winfo_rootx() + widget.winfo_width()
    parent = widget.master
    while parent is not None:
        try:
            if parent.winfo_ismapped() and parent.winfo_width() > 1:
                right = min(right, parent.winfo_rootx() + parent.winfo_width())
        except Exception:
            break
        parent = getattr(parent, "master", None)
    return right


def scan(widget, issues: list, tab_name: str) -> None:
    for child in widget.winfo_children():
        try:
            if not child.winfo_ismapped():
                continue
            cls = child.winfo_class()
            text = _text(child)
            width = child.winfo_width()
            if cls in TEXT_CLASSES and text.strip():
                req = child.winfo_reqwidth()
                if req > width + TOLERANCE:
                    issues.append({"tab": tab_name, "kind": "clipped", "class": cls, "text": text[:80],
                                   "need": req, "have": width})
                parent = child.master
                if parent is not None and parent.winfo_width() > 1:
                    right = child.winfo_rootx() + width
                    visible = _visible_right(parent)
                    if right > visible + TOLERANCE:
                        issues.append({"tab": tab_name, "kind": "outside", "class": cls, "text": text[:80],
                                       "need": right - child.winfo_rootx(), "have": max(0, visible - child.winfo_rootx())})
        except Exception:
            continue
        scan(child, issues, tab_name)


def screenshot(app, path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    app.update()
    x, y, w, h = app.winfo_rootx(), app.winfo_rooty(), app.winfo_width(), app.winfo_height()
    try:
        r = subprocess.run(["screencapture", "-x", "-R", f"{x},{y},{w},{h}", str(path)], timeout=20,
                           capture_output=True)
        return r.returncode == 0 and path.exists()
    except Exception:
        return False


def measure(languages, size: str, shots: Path | None) -> dict:
    data_root = Path(tempfile.mkdtemp(prefix="plt-ui-overflow-"))
    os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = str(data_root)
    sys.path.insert(0, str(ROOT / "app"))
    import translator_core as core
    core.list_models = lambda *a, **k: []
    core._urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("network disabled"))
    import main
    import i18n
    # 起動時の LLM の接続確認で出る警告の窓は、画面の写真を隠すので出さない（道具の中だけ）
    main.App._show_llm_connection_alert = lambda self, *a, **k: None
    results = {}
    for lang in languages:
        main.APP_PREFS_PATH.write_text(json.dumps({"ui_language": lang}), encoding="utf-8")
        app = main.App()
        if size:
            app.geometry(size)
        app.update()
        issues: list = []
        top_children = [w for w in app.winfo_children() if w is not app.notebook]
        for w in top_children:
            scan(w, issues, "(common)")
        for index, tab_id in enumerate(app.notebook.tabs()):
            app.notebook.select(tab_id)
            app.update()
            name = app.notebook.tab(tab_id, "text")
            scan(app.nametowidget(tab_id), issues, name)
            if shots:
                safe = "".join(ch if ch.isalnum() else "_" for ch in name)[:40]
                screenshot(app, shots / lang / f"{index:02d}_{safe}.png")
        results[lang] = {"count": len(issues), "issues": issues}
        app.destroy()
        print(f"{lang}: {len(issues)}", flush=True)
    return results


def main_cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--languages", default="")
    parser.add_argument("--json", default="")
    parser.add_argument("--shots", default="")
    parser.add_argument("--size", default="")
    parser.add_argument("--tag", default="", help="印（プロセスを見分けるため。中では使わない）")
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT / "app"))
    import i18n
    langs = [x for x in args.languages.split(",") if x] or list(i18n.UI_LANGUAGES)
    results = measure(langs, args.size, Path(args.shots) if args.shots else None)
    if args.json:
        Path(args.json).write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
