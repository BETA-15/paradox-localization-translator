"""第3段の走査テスト：画面の文字列を辞書（app/i18n）に移す作業が後戻りしないことを確かめる。

1. 関数ごとの日本語の文字列の数が tests/i18n_pending.py の数を超えない（新しく日本語の文字列を足していない）。
   一覧に無い関数に日本語の文字列があれば失敗する（辞書に移すか、訳さない理由があれば i18n_exclusions に足す）。
2. 日本語の文字列と比べている所（==・in・startswith など）が、i18n_exclusions.ALLOWED_COMPARISONS の中だけ。
   文で判断すると、画面の言語を変えたときに動きが変わる（2-5 章の決まり1）。
3. 日本語と英語の辞書で、同じ key の差し込みの欄の名前が同じ。日本語にある key は英語にもある。
"""
from __future__ import annotations

import re
import ast
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import i18n  # noqa: E402
import i18n_exclusions as ex  # noqa: E402
import i18n_pending as pending  # noqa: E402
import i18n_scan as scan  # noqa: E402

FILES = ("app/main.py", "app/translator_core.py")


def _direct_display_literals(source):
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        method = node.func.attr
        if method in {"set", "showinfo", "showerror", "showwarning", "askyesno"}:
            arguments = list(node.args) + [keyword.value for keyword in node.keywords]
        elif method in {"insert", "heading"}:
            arguments = [keyword.value for keyword in node.keywords if keyword.arg == "text"]
        else:
            continue
        for argument in arguments:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str) and re.search(r"[぀-ヿ一-鿿]", argument.value):
                found.append((argument.lineno, argument.value))
    return found


def test_display_calls_do_not_bypass_dictionary_exclusions():
    assert not _direct_display_literals((ROOT / "app/main.py").read_text(encoding="utf-8"))


def test_display_literal_scan_covers_all_requested_sinks():
    for call in ("var.set('エラー')", "messagebox.showinfo('エラー', '失敗')",
                 "messagebox.showerror(message='エラー')", "messagebox.showwarning('エラー')",
                 "messagebox.askyesno('エラー')", "tree.insert('', 'end', text='エラー')",
                 "tree.heading('error', text='エラー')"):
        assert _direct_display_literals(call), call
    assert not _direct_display_literals("var.set(i18n.t('u3.error'))")


def _current_counts() -> Counter:
    counts = Counter()
    for rel in FILES:
        excluded = ex.EXCLUDED_OWNERS.get(rel, set())
        for row in scan.japanese_strings(ROOT / rel):
            owner = row["owner"]
            method = owner.split(".")[1] if owner.startswith("App.") else owner.split(".")[0]
            if method in excluded or row["text"] in ex.EXCLUDED_VALUES:
                continue
            counts[f"{rel}::{owner}"] += 1
    return counts


def test_no_new_japanese_strings_outside_the_dictionary():
    over = []
    for key, count in _current_counts().items():
        allowed = pending.PENDING.get(key, (None, 0))[1]
        if count > allowed:
            over.append(f"{key}: {count} > {allowed}")
    assert not over, "辞書に移していない日本語の文字列が増えた:\n" + "\n".join(sorted(over))


def test_pending_list_has_no_stale_entries():
    """移し終わった関数は一覧から消す（数が減ったら一覧も減らす）。"""
    current = _current_counts()
    stale = [f"{key}: 一覧 {allowed} / 今 {current.get(key, 0)}"
             for key, (_unit, allowed) in pending.PENDING.items() if current.get(key, 0) < allowed]
    assert not stale, "tests/i18n_pending.py の数を今の数に減らしてください:\n" + "\n".join(sorted(stale))


def test_japanese_text_is_compared_only_in_allowed_places():
    bad = []
    for rel in FILES:
        for row in scan.japanese_comparisons(ROOT / rel):
            code = row["code"] or ""
            if not any(rel == f and row["owner"] == owner and part in code for f, owner, part in ex.ALLOWED_COMPARISONS):
                bad.append(f"{rel}:{row['line']} {row['owner']}: {code[:100]}")
    assert not bad, "文で判断している所（ID で判断すること）:\n" + "\n".join(bad)


def _fields(text):
    return sorted(set(re.findall(r"\{(\w+)\}", text)))


def test_japanese_and_english_dictionaries_match():
    ja, en = i18n.strings("japanese"), i18n.strings("english")
    missing = sorted(set(ja) - set(en))
    assert not missing, f"英語に無い key: {missing}"
    mismatched = [k for k in ja if k in en and _fields(ja[k]) != _fields(en[k])]
    assert not mismatched, f"差し込みの欄の名前が違う key: {mismatched}"


def test_other_languages_use_the_same_fields():
    ja = i18n.strings("japanese")
    for lang in i18n.UI_LANGUAGES:
        for key, text in i18n.strings(lang).items():
            if key in ja:
                assert _fields(text) == _fields(ja[key]), (lang, key)


def test_main_calls_the_dictionary_as_i18n_t():
    """main.py の画面を作る関数は「t = self.tab_…」のように t を変数に使う。素の t(...) は隠れてしまうので、
    辞書は必ず i18n.t(...) で引く（段階0で実際に起きた：バックアップ復元タブで TypeError）。"""
    import ast
    for name in ("main.py", "translator_core.py"):
        tree = ast.parse((ROOT / "app" / name).read_text(encoding="utf-8"))
        bare = [node.lineno for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "t"]
        assert not bare, f"{name}: 素の t(...) を i18n.t(...) に直す: 行 {bare[:20]}"


def test_widget_labels_are_never_japanese_literals():
    """画面の部品の text=・label=・title=・message= に日本語をじかに書かない。
    訳さない値の一覧（フォルダの名前など）と同じ語でも、画面に出すなら辞書から引く（段階1でタブの名前が漏れた）。"""
    import ast
    import re
    jp = re.compile(r"[぀-ヿ一-鿿]")
    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    found = [(node.value.lineno, node.value.value[:30]) for node in ast.walk(tree)
             if isinstance(node, ast.keyword) and node.arg in ("text", "label", "title", "message")
             and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)
             and jp.search(node.value.value)]
    assert not found, f"辞書に移す: {found[:20]}"


# 段階2で辞書がそろった言語（開発部門がマージのときに足す）。ここにある言語は、日本語と同じ key がすべてある。
COMPLETE_LANGUAGES = ("japanese", "english", "braz_por", "russian", "korean")


def test_complete_languages_have_every_key():
    ja = set(i18n.strings("japanese"))
    for lang in COMPLETE_LANGUAGES:
        missing = sorted(ja - set(i18n.strings(lang)))
        extra = sorted(set(i18n.strings(lang)) - ja)
        assert not missing, f"{lang} に無い key（{len(missing)} 個）: {missing[:20]}"
        assert not extra, f"{lang} にだけある key: {extra[:20]}"
