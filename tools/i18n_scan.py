"""日本語を含む文字列リテラルを、関数（メソッド）ごとに数える道具（第3段の走査テストと共用）。

使い方: python tools/i18n_scan.py [app/main.py ...]
f 文字列は1つと数える。docstring は数えない（画面に出ないため）。
"""
from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from pathlib import Path

JAPANESE_RE = re.compile(r"[぀-ヿ一-鿿]")


def _docstring_nodes(tree: ast.AST) -> set:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def japanese_strings(path: Path) -> list[dict]:
    """[{"owner": "App._build_glossary_tab" or "<module>" or "func", "line": n, "text": "..."}]"""
    source = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(source)
    docs = _docstring_nodes(tree)
    rows = []

    def visit(node, owner, inside_fstring=False):
        if isinstance(node, ast.JoinedStr):
            parts = "".join(v.value for v in node.values if isinstance(v, ast.Constant) and isinstance(v.value, str))
            if JAPANESE_RE.search(parts):
                rows.append({"owner": owner, "line": node.lineno, "text": ast.get_source_segment(source, node) or parts})
            for v in node.values:
                if isinstance(v, ast.FormattedValue):
                    visit(v.value, owner, True)
            return
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and not inside_fstring:
            if id(node) not in docs and JAPANESE_RE.search(node.value):
                rows.append({"owner": owner, "line": node.lineno, "text": node.value})
            return
        for child in ast.iter_child_nodes(node):
            child_owner = owner
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                child_owner = (owner + "." if owner not in ("<module>",) else "") + child.name
            elif isinstance(child, ast.ClassDef):
                child_owner = child.name
            visit(child, child_owner, inside_fstring)

    visit(tree, "<module>")
    return rows


def main(argv):
    paths = [Path(p) for p in (argv or ["app/main.py", "app/translator_core.py"])]
    for path in paths:
        rows = japanese_strings(path)
        owners = Counter(r["owner"] for r in rows)
        top = Counter(r["owner"].split(".")[0] if r["owner"].startswith("App.") else r["owner"] for r in rows)
        print(f"{path}: {len(rows)} strings in {len(owners)} owners")
        in_app = sum(n for o, n in owners.items() if o.startswith("App."))
        print(f"  App methods: {in_app} / outside App: {len(rows) - in_app}")


if __name__ == "__main__":
    main(sys.argv[1:])
