"""紐付けレポート：元Modと日本語化Modの紐付けを一覧にし、ズレていそうなものに印を付ける。"""
import csv
import io

from app import translator_core as core

WS = "/x/steamapps/workshop/content/394360"
LOCAL = "/x/Documents/Paradox Interactive/Hearts of Iron IV/mod"


def _results():
    return [
        {"mod": "Road to 56", "path": f"{WS}/111", "game": "Hearts of Iron IV", "status": "別Modで完全翻訳",
         "external_translation_mod": "Road to 56 日本語化", "external_translation_path": f"{LOCAL}/r56_ja",
         "external_translation_score": 92.0, "external_translation_confidence": "auto",
         "external_translation_precision": 0.95, "external_translation_coverage": 0.9,
         "external_translation_reasons": ["共通キー 1200"]},
        {"mod": "Kaiserreich", "path": f"{WS}/222", "game": "Hearts of Iron IV", "status": "別Mod翻訳・欠損",
         "external_translation_mod": "Music Pack JP", "external_translation_path": f"{LOCAL}/music_ja",
         "external_translation_score": 41.0, "external_translation_confidence": "auto",
         "external_translation_precision": 0.3, "external_translation_coverage": 0.05,
         "external_translation_reasons": ["共通キー 12"]},
        {"mod": "Millennium Dawn", "path": f"{WS}/333", "game": "Hearts of Iron IV", "status": "翻訳なし",
         "translation_candidate_mod": "Road to 56 日本語化", "translation_candidate_path": f"{LOCAL}/r56_ja",
         "translation_candidate_score": 30.0, "translation_candidate_precision": 0.2,
         "translation_candidate_coverage": 0.1, "translation_candidate_reasons": ["共通キー 40"]},
        {"mod": "My Mod", "path": f"{LOCAL}/mine", "game": "Hearts of Iron IV", "status": "翻訳あり"},
    ]


def test_rows_cover_every_mod_with_location_and_link():
    rep = core.build_relation_report(_results())
    rows = {r["元Mod"]: r for r in rep["rows"]}
    assert len(rows) == 4
    assert rows["Road to 56"]["元Modの保管場所"] == "Steam Workshop"
    assert rows["Road to 56"]["紐付け先"] == "Road to 56 日本語化"
    assert rows["Road to 56"]["紐付け先の保管場所"] == "ローカル"
    assert rows["Road to 56"]["種別"] == "自動で紐付け"
    assert rows["Millennium Dawn"]["種別"] == "候補（自動では紐付けず）"
    assert rows["My Mod"]["紐付け先"] == ""


def test_suspicious_links_are_flagged_with_reasons():
    rows = {r["元Mod"]: r for r in core.build_relation_report(_results())["rows"]}
    assert rows["Road to 56"]["要確認"] == ""
    assert "元Modのキーとの一致が少ない" in rows["Kaiserreich"]["要確認"]
    assert "名前が似ていない" in rows["Kaiserreich"]["要確認"]
    assert "候補のみ" in rows["Millennium Dawn"]["要確認"]


def test_translation_mod_used_by_several_sources_is_listed():
    rep = core.build_relation_report(_results())
    by = {r["日本語化Mod"]: r for r in rep["by_translation"]}
    assert by["Road to 56 日本語化"]["元Modの数"] == 2
    rows = {r["元Mod"]: r for r in rep["rows"]}
    assert "同じ日本語化Modが複数の元Modに紐付いている" in rows["Millennium Dawn"]["要確認"]


def test_csv_and_markdown_render():
    rep = core.build_relation_report(_results())
    text = core.relation_report_csv(rep)
    parsed = list(csv.DictReader(io.StringIO(text)))
    assert len(parsed) == 4 and "要確認" in parsed[0]
    md = core.relation_report_markdown(rep, title="テスト")
    assert md.startswith("# テスト")
    assert "Kaiserreich" in md and "要確認" in md
