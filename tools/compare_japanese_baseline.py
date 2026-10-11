"""日本語の動きが変わっていないかを、実データで確かめる道具（「日本語のみ」の機能の11言語化 L0、3章の門）。

  python tools/compare_japanese_baseline.py collect --out DIR [--games hoi4,vic3,ck3,stellaris] [--qa-dir DIR] [--full]
      この版のコードで、この Mac の Mod（Steam Workshop とローカル Mod）を読み、結果を DIR に JSON で書く。
      - relation_<game>.json：build_relation_report（ゲーム全体の紐付けの報告）
      - status_<game>.json：analyze_mod_translation_status（Mod ごとの翻訳状況の調査）
      - gaps_<game>.json：scan_translation_gaps（Mod ごとの差分の調べ）
      - qa.json：決めた日本語の文章の束（+JP: Kaiserreich と 資料/ の COS のファイル）の qa_entries
  python tools/compare_japanese_baseline.py compare BASE NEW [--strict]
      2つの DIR を比べる。値が変わった・消えた所が1つでもあれば 1 で終わる。
      新しく足された欄（message_parts など）は一覧に出すだけ（--strict なら差に数える）。

実データは読むだけ（書かない）。結果は利用者の Mod の中身を含むので、リポジトリに入れない
（置き場所は ~/Documents/開発運営/プロジェクト/パラドックス翻訳/資料/基準_<コミット>/）。
古い版（4cfe990 など）で基準を取るときは、その版の worktree にこのファイルを写して流す。古い版にある関数だけを使う。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import translator_core as core  # noqa: E402

GAMES = {
    "ck3": "Crusader Kings III",
    "hoi4": "Hearts of Iron IV",
    "stellaris": "Stellaris",
    "vic3": "Victoria 3",
}
VOLATILE_KEYS = {"checked_at", "generated_at", "scanned_at", "created_at", "updated_at", "elapsed", "elapsed_seconds",
                 "duration", "mtime"}
QA_SOURCE_MOD = "1521695605"      # Kaiserreich（英語の原文）
QA_TARGET_MOD = "1849164647"      # +JP: Kaiserreich
WORKSHOP_HOI4 = Path.home() / "Library/Application Support/Steam/steamapps/workshop/content/394360"
DEFAULT_QA_DIR = Path.home() / "Documents/開発運営/プロジェクト/パラドックス翻訳/資料"


def normalize(value):
    """比べられる形にする（集合は並べ替え、Path は文字列、時刻などの変わる欄は捨てる）。"""
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in sorted(value.items(), key=lambda kv: str(kv[0]))
                if str(k) not in VOLATILE_KEYS}
    if isinstance(value, (list, tuple)):
        return [normalize(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted((normalize(v) for v in value), key=lambda v: json.dumps(v, ensure_ascii=False, sort_keys=True))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def digest(value) -> dict:
    """大きな値（未翻訳候補の一覧など）は、件数とハッシュだけにする（基準のファイルを小さくする）。"""
    text = json.dumps(normalize(value), ensure_ascii=False, sort_keys=True)
    return {"count": len(value) if hasattr(value, "__len__") else None,
            "sha": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]}


def compact(row, full: bool = False):
    """1つの Mod の結果を、欄ごとに「小さな値はそのまま、大きな値は件数とハッシュ」にする。"""
    if full or not isinstance(row, dict):
        return normalize(row) if full or not isinstance(row, list) else digest(row)
    out = {}
    for k, v in row.items():
        if str(k) in VOLATILE_KEYS:
            continue
        if isinstance(v, (str, int, float, bool)) or v is None or isinstance(v, Path):
            out[str(k)] = normalize(v)
        elif isinstance(v, (list, tuple, set, dict)) and len(v) <= 3 and len(json.dumps(normalize(v), ensure_ascii=False)) <= 300:
            out[str(k)] = normalize(v)
        else:
            out[str(k)] = digest(v)
    return out


def _has_japanese(mod_root: Path) -> bool:
    """main.App._current_mod_has_japanese と同じ（今ある日本語の YAML で初めの分類をする）。"""
    loc = core.mod_localization_root(Path(mod_root))
    if not loc:
        return False
    for fp in core.gather_yml_files(loc):
        try:
            if core.parse_localization_file(fp)[0] == "japanese":
                return True
        except Exception:
            continue
    return False


def game_roots(game_name: str) -> list:
    roots = []
    for row in core.discover_paradox_mod_locations():
        if row.get("game") != game_name:
            continue
        for root in core.find_mod_roots(Path(row["path"])):
            if root not in roots:
                roots.append(root)
    return sorted(roots, key=str)


def source_fingerprint(mod_root: Path) -> str:
    """Mod のローカライズのファイルの数・大きさ・更新時刻（Steam Workshop の更新で中身が変わったかを見分ける）。"""
    loc = core.mod_localization_root(Path(mod_root))
    h = hashlib.sha256()
    for fp in sorted(core.gather_yml_files(loc)) if loc else []:
        try:
            st = fp.stat()
        except OSError:
            continue
        h.update(f"{fp.relative_to(mod_root)}|{st.st_size}|{int(st.st_mtime)}\n".encode("utf-8", "ignore"))
    return h.hexdigest()[:16]


def collect_game(game: str, out: Path, full: bool = False) -> dict:
    roots = game_roots(GAMES[game])
    (out / f"sources_{game}.txt").write_text("".join(f"{r}\t{source_fingerprint(r)}\n" for r in roots), encoding="utf-8")
    started = time.time()
    eligible = [r for r in roots if _has_japanese(r)]
    index = core.build_translation_mod_index(eligible)
    index = core.assign_translation_candidate_owners(roots, index)
    statuses, gaps = {}, {}
    for root in roots:
        key = str(root)
        try:
            statuses[key] = core.analyze_mod_translation_status(root, translation_index=index)
        except Exception as exc:  # 例外も結果として残す（変わったら差に出る）
            statuses[key] = {"exception": f"{type(exc).__name__}: {exc}"}
        try:
            gaps[key] = core.scan_translation_gaps(root)
        except Exception as exc:
            gaps[key] = {"exception": f"{type(exc).__name__}: {exc}"}
    results = [dict(r, path=k) if "path" not in r else r for k, r in statuses.items() if "exception" not in r]
    report = core.build_relation_report(results)
    statuses = {k: compact(v, full) for k, v in statuses.items()}
    gaps = {k: (normalize(v) if full else digest(v)) if isinstance(v, list) else v for k, v in gaps.items()}
    for name, data in (("relation", report), ("status", statuses), ("gaps", gaps)):
        (out / f"{name}_{game}.json").write_text(json.dumps(normalize(data), ensure_ascii=False, indent=1),
                                                 encoding="utf-8")
    return {"game": game, "mods": len(roots), "japanese_candidates": len(eligible),
            "seconds": round(time.time() - started, 1)}


def _entries_by_file(mod_root: Path, lang: str) -> dict:
    loc = core.mod_localization_root(mod_root)
    files = {}
    for fp in core.gather_yml_files(loc) if loc else []:
        try:
            found_lang, entries = core.parse_localization_file(fp)[:2]
        except Exception:
            continue
        if found_lang == lang:
            files[str(fp.relative_to(mod_root))] = entries
    return files


def _qa_rows(issues, full: bool) -> list:
    """QA の結果。訳文そのもの（value）はハッシュにする。message・type・rule_id などはそのまま比べる。"""
    if full:
        return issues
    rows = []
    for issue in issues:
        row = dict(issue)
        if "value" in row:
            row["value"] = hashlib.sha256(str(row["value"]).encode("utf-8")).hexdigest()[:12]
        rows.append(row)
    return rows


def collect_qa(out: Path, qa_dir: Path, full: bool = False) -> dict:
    english = {}
    for entries in _entries_by_file(WORKSHOP_HOI4 / QA_SOURCE_MOD, "english").values():
        english.update(entries)
    results = {}
    for rel, entries in sorted(_entries_by_file(WORKSHOP_HOI4 / QA_TARGET_MOD, "japanese").items()):
        source = {k: english[k] for k in entries if k in english}
        results[f"{QA_TARGET_MOD}/{rel}"] = _qa_rows(core.qa_entries(entries, source or None, source_lang="english"), full)
    for fp in sorted(qa_dir.glob("*.yml")):
        lang, entries = core.parse_localization_file(fp)[:2]
        if lang == "japanese":
            results[f"資料/{fp.name}"] = _qa_rows(core.qa_entries(entries, None, source_lang="english"), full)
    (out / "qa.json").write_text(json.dumps(normalize(results), ensure_ascii=False, indent=1), encoding="utf-8")
    return {"qa_files": len(results), "issues": sum(len(v) for v in results.values())}


def collect(args) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    summary = {"games": []}
    for game in [g.strip() for g in args.games.split(",") if g.strip()]:
        info = collect_game(game, out, args.full)
        summary["games"].append(info)
        print(json.dumps(info, ensure_ascii=False), flush=True)
    summary["qa"] = collect_qa(out, Path(args.qa_dir), args.full)
    print(json.dumps(summary["qa"], ensure_ascii=False), flush=True)
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


def diff(base, new, path="", out=None):
    """(種類, 場所) の一覧。種類は changed・removed・added。"""
    out = [] if out is None else out
    if isinstance(base, dict) and isinstance(new, dict):
        for k in base:
            if k not in new:
                out.append(("removed", f"{path}/{k}"))
            else:
                diff(base[k], new[k], f"{path}/{k}", out)
        for k in new:
            if k not in base:
                out.append(("added", f"{path}/{k}"))
    elif isinstance(base, list) and isinstance(new, list):
        if len(base) != len(new):
            out.append(("changed", f"{path}（件数 {len(base)} → {len(new)}）"))
        for i, (b, n) in enumerate(zip(base, new)):
            diff(b, n, f"{path}[{i}]", out)
    elif base != new:
        out.append(("changed", f"{path}: {json.dumps(base, ensure_ascii=False)[:120]} → "
                               f"{json.dumps(new, ensure_ascii=False)[:120]}"))
    return out


def _changed_sources(base_dir: Path, new_dir: Path) -> list:
    changed = []
    for base_file in sorted(base_dir.glob("sources_*.txt")):
        new_file = new_dir / base_file.name
        if not new_file.exists():
            continue
        old = dict(line.split("\t", 1) for line in base_file.read_text(encoding="utf-8").splitlines() if "\t" in line)
        new = dict(line.split("\t", 1) for line in new_file.read_text(encoding="utf-8").splitlines() if "\t" in line)
        changed += [k for k in sorted(set(old) | set(new)) if old.get(k) != new.get(k)]
    return changed


def compare(args) -> int:
    base_dir, new_dir = Path(args.base), Path(args.new)
    failures = 0
    changed_sources = _changed_sources(base_dir, new_dir)
    if changed_sources:
        print(f"注意：基準を取った後に中身が変わった Mod が {len(changed_sources)} 個あります（Steam Workshop の更新など）。"
              "その Mod の差はコードの差とは限りません。同じ時に基準と新しい版を取り直して比べてください。")
        for path in changed_sources[:20]:
            print(f"  変わった Mod: {path}")
    for base_file in sorted(base_dir.glob("*.json")):
        if base_file.name == "summary.json":
            continue
        new_file = new_dir / base_file.name
        if not new_file.exists():
            print(f"{base_file.name}: 新しい側に無い"); failures += 1; continue
        rows = diff(json.loads(base_file.read_text(encoding="utf-8")), json.loads(new_file.read_text(encoding="utf-8")))
        added = sorted({p.split("[")[0] if "[" in p else p for kind, p in rows if kind == "added"})
        bad = [(kind, p) for kind, p in rows if kind != "added" or args.strict]
        failures += len(bad)
        print(f"{base_file.name}: 差 {len(bad)} 件" + (f"（足された欄 {len(added)} 種）" if added else ""))
        for kind, p in bad[:30]:
            print(f"  {kind}: {p}")
        for p in added[:10]:
            print(f"  足された欄: {p}")
    print(f"日本語の差：{failures} 件")
    return 1 if failures else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--out", required=True)
    c.add_argument("--games", default="hoi4,vic3,ck3,stellaris")
    c.add_argument("--qa-dir", default=str(DEFAULT_QA_DIR))
    c.add_argument("--full", action="store_true", help="件数とハッシュにせず全部書く（差の中身を調べるとき。とても大きい）")
    m = sub.add_parser("compare")
    m.add_argument("base")
    m.add_argument("new")
    m.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    return collect(args) if args.command == "collect" else compare(args)


if __name__ == "__main__":
    sys.exit(main())
