"""情報量（IDF）で重み付けした一致率による紐付け判定。

どの Mod にも出てくるキー（国名など）は関係の証拠として弱く、その Mod にしか無いキーは強い。
共通のキーだけで別の日本語化Modに紐付かないことを確かめる。
"""
from pathlib import Path

from app import translator_core as core

GENERIC = [f"generic_country_{i}" for i in range(400)]  # 多くの Mod が持つ共通のキー


def _write(root: Path, lang: str, entries: dict, name: str):
    d = root / "localisation" / lang
    d.mkdir(parents=True, exist_ok=True)
    body = "".join(f' {k}:0 "{v}"\n' for k, v in entries.items())
    (d / f"{root.name}_l_{lang}.yml").write_text(f"﻿l_{lang}:\n{body}", encoding="utf-8")
    (root / "descriptor.mod").write_text(f'name="{name}"\n', encoding="utf-8")


def _pool(tmp_path):
    ws = tmp_path / "workshop" / "content" / "394360"
    mods = {}
    # 元Mod 3つ：どれも共通キーを持つ。固有キーはそれぞれ300件。
    for tag in ("alpha", "beta", "gamma"):
        own = {f"{tag}_key_{i}": f"{tag} text {i}" for i in range(300)}
        own.update({k: f"Country {k}" for k in GENERIC})
        _write(ws / tag, "english", own, f"{tag.title()} Overhaul")
        mods[tag] = ws / tag
    # Alpha の日本語化：Alpha の固有キーをすべて訳している。
    _write(ws / "alpha_jp", "japanese", {f"alpha_key_{i}": f"アルファ {i}" for i in range(300)}, "+JP Alpha Overhaul")
    # 共通キーだけを大量に訳した日本語化（国名パック）：どの元Modとも共通キーで一致してしまう。
    _write(ws / "names_jp", "japanese", {k: f"国 {k}" for k in GENERIC}, "+JP Country Names")
    mods["alpha_jp"] = ws / "alpha_jp"; mods["names_jp"] = ws / "names_jp"
    return mods


def _index(mods):
    roots = list(mods.values())
    ja = [m for m in roots if core._collect_mod_language_entries(m)["japanese"]]
    return core.assign_translation_candidate_owners(roots, core.build_translation_mod_index(ja))


def test_generic_keys_do_not_link_unrelated_mod(tmp_path):
    mods = _pool(tmp_path)
    idx = _index(mods)
    beta = core.find_external_japanese_translation(mods["beta"], idx)
    assert beta is None  # Beta の日本語化は無い。国名パックへは紐付けない


def test_true_translation_is_linked(tmp_path):
    mods = _pool(tmp_path)
    idx = _index(mods)
    alpha = core.find_external_japanese_translation(mods["alpha"], idx)
    assert alpha is not None and alpha["mod"] == "+JP Alpha Overhaul"


def test_weighted_rates_are_reported(tmp_path):
    mods = _pool(tmp_path)
    idx = _index(mods)
    ranked = {r["mod"]: r for r in core.rank_external_japanese_translations(mods["beta"], idx)}
    names = ranked.get("+JP Country Names")
    assert names is not None
    # 共通キーは3つの元Modすべてと国名パックにあるので重みが小さく、重み付きの一致率は
    # 自動で紐付ける境目よりずっと低い（この小さなプールでは候補の水準にとどまる）
    assert names["weighted_coverage"] < core.RELATION_AUTO_PARTIAL_SOURCE_RATE
    assert names["classification"] != "auto"
    assert any("情報量で重み付け" in r for r in names["reasons"])


def test_without_pool_weights_falls_back_to_plain_rates():
    w = core.relation_key_weights([{"a", "b"}, {"a", "c"}])
    assert w["b"] > w["a"]  # 1つの Mod にしか無いキーほど重い
    assert core.weighted_rate({"a"}, {"a", "b"}, {}) == 0.5  # 重みが無ければ件数の割合


def test_best_covering_translation_wins_over_higher_structure_score(tmp_path):
    mods = _pool(tmp_path)
    ws = mods["alpha"].parent
    # 全部を訳した日本語化Modに英語のファイルが少し混ざっている → 構成の点数が下がる（実データの +JP: Kaiserreich と同じ形）
    _write(ws / "alpha_jp", "english", {f"alpha_note_{i}": f"note {i}" for i in range(5)}, "+JP Alpha Overhaul")
    # Alpha の一部（250キー）だけを訳した、日本語だけの Mod（構成の点数は高い）
    _write(ws / "alpha_part_jp", "japanese", {f"alpha_key_{i}": f"部分 {i}" for i in range(250)}, "+JP Alpha Part")
    mods["alpha_part_jp"] = ws / "alpha_part_jp"
    idx = _index(mods)
    ranked = {r["mod"]: r for r in core.rank_external_japanese_translations(mods["alpha"], idx)}
    assert ranked["+JP Alpha Part"]["classification"] == "auto"
    assert ranked["+JP Alpha Part"]["score"] > ranked["+JP Alpha Overhaul"]["score"]  # 点数だけなら一部の方が上
    alpha = core.find_external_japanese_translation(mods["alpha"], idx)
    assert alpha["mod"] == "+JP Alpha Overhaul"  # 元Modをいちばん多く訳している方を選ぶ


def test_shared_generic_keys_do_not_make_a_multi_translation_pack(tmp_path):
    mods = _pool(tmp_path)
    idx = {r["mod"]: r for r in _index(mods)}
    # 国名パックは3つの元Modと同じ共通キーで重なるだけ。元Modごとに別々の部分を訳した総合和訳ではない
    assert idx["+JP Country Names"]["multi_translation_source_paths"] == []
    ranked = {r["mod"]: r for r in core.rank_external_japanese_translations(mods["alpha"], list(idx.values()))}
    assert ranked["+JP Country Names"]["classification"] != "auto"
