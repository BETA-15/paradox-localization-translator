from pathlib import Path
import json

import pytest

import translator_core as core


CHINESE = [
    "在铁路建设中发现了少量矿藏，促使公司雇佣欧洲工程师。",
    "コルテス将繼續執政。這將帶來嚴重影響！",
    "种植园的连接", "我們不怕的。", "國家將繼續行動。",
    "出生：1900年3月10日，出生于圣何塞",
]
# 見分けられない短いラベル（中国語にしかない字が1字だけ）。公式の日本語訳の地名・人名を誤判定しないための割り切り。
KNOWN_MISSES = ["保守的胜利", "國家行動", "1940 年選舉已結束", "出售政府土地"]
JAPANESE = [
    "銀行改革", "農村信用", "公共事業", "国民医療制度導入", "社会主義の勝利",
    "外国貨物車を購入", "大統領選挙", "海軍施設", "鉄道拡張", "教育改革",
    "新式砲弾", "漁業産業の刺激", "宣戦布告の準備が整った。",
    "王国は新たな時代を迎えた",
    "政府は国家安全保障会議を設置し、国内経済の立て直しと軍備の近代化を同時に進める方針を発表した。",
    "社会主義一国", "最低賃金導入", "社会的不平等", "作戦終了",
    "剝", "頰", "塡", "國の制度について説明します。",
    "公共改革是正", "公共改革到着", "公共改革終了", "公共改革最低",
]


@pytest.mark.parametrize("text", CHINESE)
def test_detects_chinese_in_japanese(text):
    assert core.looks_like_chinese_in_japanese(text) is True


@pytest.mark.parametrize("text", JAPANESE)
def test_preserves_japanese(text):
    assert core.looks_like_chinese_in_japanese(text) is False


@pytest.mark.parametrize("text, expected", [
    ("", False), ("公共改革可", False), ("公共改革可以", True),
    ("國家制度改革あ", False), ("國家制度改革案あ", False), ("國會制度改革案あ", False), ("國會讓制度改革あ", True),
    ("國會について説明します。", True),
    ("[ROOT.國會] $國會$ £國會£ #tag;國會#! \\n @@0@@ 銀行改革", False),
    ("§Y銀行改革§! [ROOT.GetName] $VAR$ £icon£ #tag \\n @@0@@", False),
    ("§Y國家行動§!", False), ("§Y國會將行動§!", True),
])
def test_thresholds_and_protected_syntax(text, expected):
    assert core.looks_like_chinese_in_japanese(text) is expected


@pytest.mark.parametrize("source_lang", ["english", "simp_chinese"])
@pytest.mark.parametrize("text", CHINESE)
def test_shared_validation_rejects_chinese(source_lang, text):
    assert core.unusable_japanese_translation("A government reform", text, source_lang)
    assert not core.cache_entry_is_valid("A government reform", text, source_lang)
    assert core.foreign_in_japanese_output(text)
    assert not core.cache_entry_is_valid("A government reform", text, source_lang)


@pytest.mark.parametrize("text", ["銀行改革", "農村信用", "公共事業", "国民医療制度導入"])
def test_unchanged_short_chinese_source_labels_remain_valid(text):
    assert not core.looks_untranslated(text, text, "simp_chinese")
    assert core.cache_entry_is_valid(text, text, "simp_chinese")
    assert not core.qa_entries({"label": text}, {"label": text}, "simp_chinese")


def _write_localization(path, language, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'l_{language}:\n event_description:0 "{value}"\n', encoding="utf-8")


@pytest.mark.parametrize("source_lang, original", [
    ("english", "The government announced a reform."),
    ("simp_chinese", "國家將繼續行動。"),
])
@pytest.mark.parametrize("bad_attempts", [0, 1])
def test_translation_discards_chinese_cache_and_retries(tmp_path, monkeypatch, source_lang, original, bad_attempts):
    source = tmp_path / "input" / source_lang / f"events_l_{source_lang}.yml"
    output = tmp_path / "output"
    cache_path = tmp_path / "cache.json"
    _write_localization(source, source_lang, original)
    cache_key = core.translation_cache_key("Ollama", core.DEFAULT_MODEL, "General", source_lang, original)
    core.save_cache(cache_path, {cache_key: CHINESE[0]})
    calls = []

    def translate(_url, _model, jobs, language, *args, **kwargs):
        calls.append(language)
        value = CHINESE[0] if len(calls) <= bad_attempts else "政府は改革を発表した。"
        return [value for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translate)
    core.run_translation(source.parent.parent, output, cache_path=cache_path,
                         auto_qa=False, verbose=False, workers=1)

    generated = output / "japanese" / "events_l_japanese.yml"
    assert core.parse_localization_file(generated)[1] == {"event_description": "政府は改革を発表した。"}
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    assert cache[cache_key] == "政府は改革を発表した。"
    assert CHINESE[0] not in cache.values()
    assert calls == [source_lang] * (bad_attempts + 1)


@pytest.mark.parametrize("source_lang, original", [
    ("english", "The government announced a reform."), ("simp_chinese", "國家將繼續行動。"),
])
def test_translation_never_caches_chinese_after_retry_exhaustion(tmp_path, monkeypatch, source_lang, original):
    source = tmp_path / "input" / source_lang / f"events_l_{source_lang}.yml"
    output = tmp_path / "output"
    cache_path = tmp_path / "cache.json"
    _write_localization(source, source_lang, original)
    calls = []

    def translate(_url, _model, jobs, _language, *args, **kwargs):
        calls.append(len(jobs))
        return [CHINESE[0] for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translate)
    core.run_translation(source.parent.parent, output, cache_path=cache_path,
                         auto_qa=False, verbose=False, workers=1)
    assert core.parse_localization_file(output / "japanese" / "events_l_japanese.yml")[1] == {
        "event_description": original,
    }
    assert json.loads(cache_path.read_text(encoding="utf-8")) == {}
    assert calls == [1, 1]


def test_qa_marks_chinese_translation_as_repairable_error():
    issues = core.qa_entries({"event_description": CHINESE[0]},
                             {"event_description": "The government announced a reform."}, "english")
    issue = next(item for item in issues if item["type"] == "untranslated")
    assert issue["severity"] == "error"
    assert issue["repairable"] is True


def test_qa_without_source_rejects_chinese():
    issues = core.qa_entries({"event_description": CHINESE[0]})
    assert any(item["type"] == "untranslated" and item["severity"] == "error" for item in issues)


def test_japanese_input_is_retranslated_when_chinese(tmp_path, monkeypatch):
    source = tmp_path / "input" / "japanese" / "events_l_japanese.yml"
    output = tmp_path / "output"
    _write_localization(source, "japanese", CHINESE[0])

    def translate(_url, _model, jobs, _language, *args, **kwargs):
        return ["政府は改革を発表した。" for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translate)
    core.run_translation(source.parent.parent, output, cache_path=tmp_path / "cache.json",
                         auto_qa=False, verbose=False)
    assert core.parse_localization_file(output / "japanese" / source.name)[1] == {
        "event_description": "政府は改革を発表した。",
    }


@pytest.mark.parametrize("source_lang, original", [
    ("english", "The government announced a reform."), ("simp_chinese", "國家將繼續行動。"),
])
def test_auto_repair_rejects_chinese_response_and_retries(tmp_path, monkeypatch, source_lang, original):
    source = tmp_path / "source" / f"events_l_{source_lang}.yml"
    target = tmp_path / "output" / "events_l_japanese.yml"
    _write_localization(source, source_lang, original)
    _write_localization(target, "japanese", CHINESE[0])
    calls = []

    def translate(_url, _model, jobs, _language, *args, **kwargs):
        calls.append(core.parse_localization_file(target)[1]["event_description"])
        return ["國家將繼續行動。" if len(calls) == 1 else "政府は改革を発表した。" for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translate)
    result = core.qa_file_with_auto_repair(target, source, source_lang=source_lang,
                                           backup_dir=tmp_path / "backup", max_passes=2)
    assert result["initial_errors"] == 1
    assert result["final_errors"] == 0
    assert result["repaired"] == 1
    assert any(event["result"] == "rejected_by_validation" for event in result["events"])
    assert calls == [CHINESE[0], CHINESE[0]]
    assert core.parse_localization_file(target)[1] == {"event_description": "政府は改革を発表した。"}


@pytest.mark.parametrize("folder", ["names", "dynasties"])
def test_unchanged_chinese_proper_names_remain_notices(folder):
    value = "这是刘氏家族的名称"
    issues = core.qa_entries({"name": value}, {"name": value}, "simp_chinese",
                             source_path=Path("localization/simp_chinese") / folder / "names.yml")
    assert any(item["type"] == "proper_noun_untranslated" and item["severity"] == "notice"
               and item["repairable"] is False for item in issues)
    assert not any(item["severity"] == "error" for item in issues)


@pytest.mark.parametrize("text", ["弗朗西斯科·瓦加斯·瓦加斯", "再次強調，巴拿馬必須遵守法洛白統治",
                                  "因长期低迷及随后黑星期一事件，投资者已借资我们。"])
def test_detects_chinese_by_punctuation_and_name_dots(text):
    assert core.looks_like_chinese_in_japanese(text)


@pytest.mark.parametrize("text", ["大日本帝国万歳！", "全軍突撃！", "宣戦布告。", "社会的不平等", "ジョン・スミス将軍",
                                  "作戦終了", "人民前衛党（人民前衛党）", "ZKG 銀行崩壊：再発出口量", "国民医療制度導入",
                                  # ゲームの公式の日本語訳にある語（誤判定しないこと）
                                  "国家給付運動", "予想売却価格", "第一段階完了。", "産出目標達成。", "小磯國昭", "鄯善", "贛州",
                                  "昌林·林格", "翁文灝", "國川丸"])
def test_japanese_with_kanji_punctuation_is_kept(text):
    assert not core.looks_like_chinese_in_japanese(text)


@pytest.mark.parametrize("text", KNOWN_MISSES)
def test_known_short_label_misses_are_documented(text):
    assert not core.looks_like_chinese_in_japanese(text)
