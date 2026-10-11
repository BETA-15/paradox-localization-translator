from __future__ import annotations

import importlib
import json
import queue
from types import SimpleNamespace

import pytest

import translator_core as core


class FakeVar:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTree:
    def __init__(self):
        self.rows = {}
        self.next_id = 0

    def get_children(self):
        return tuple(self.rows)

    def delete(self, row_id):
        del self.rows[row_id]

    def insert(self, parent, position, *, values):
        self.next_id += 1
        self.rows[str(self.next_id)] = values

    def item(self, row_id, option):
        assert option == "values"
        return self.rows[row_id]


@pytest.mark.parametrize("source,source_lang,key,expected", [
    ("Great!", "english", "", "phrase"),
    ("Very well.", "english", "", "phrase"),
    ("So be it.", "english", "", "phrase"),
    ("What?", "english", "", "phrase"),
    ("Wait…", "english", "", "phrase"),
    ("[GetYear] Elections", "english", "", "phrase"),
    ("$COUNTRY$ Army", "english", "", "phrase"),
    ("£army£ Infantry", "english", "", "phrase"),
    ("§GInfantry§!", "english", "", "phrase"),
    ("#bold Infantry#!", "english", "", "phrase"),
    (r"Infantry\nEconomy", "english", "", "phrase"),
    ("Increase Conscription", "english", "", "phrase"),
    ("increase Conscription", "english", "", "phrase"),
    ("Gain 50 Political Power", "english", "", "phrase"),
    ("Join the Faction", "english", "", "phrase"),
    ("Support for the Monarchy", "english", "", "phrase"),
    ("Cost per Division", "english", "", "phrase"),
    ("The Holy Roman Empire", "english", "", "proper"),  # 大文字の語が並ぶ名前は4語以上でも固有名詞
    ("Model 2", "english", "", "phrase"),
    ("Economy not Politics", "english", "", "phrase"),
    ("Holy Roman Empire", "english", "", "proper"),
    ("Duke of York", "english", "", "proper"),
    ("Mitteleuropa League", "english", "", "proper"),
    ("Kingdom of Hungary", "english", "", "proper"),
    ("Grand Fleet", "english", "", "proper"),
    ("The Netherlands", "english", "", "proper"),
    ("the Netherlands", "english", "", "proper"),
    ("Alexandra", "english", "character_name_alexandra", "proper"),
    ("Great!", "english", "character_name", "phrase"),
    ("Infantry", "english", "", "term"),
    ("Economy", "english", "", "term"),
    ("Alexandra", "english", "", "term"),
    # The explicit title-case rule classifies UI noun phrases as proper too.
    ("Political Power", "english", "", "proper"),
    ("Conscription Law", "english", "", "proper"),
    ("civilian factory", "english", "", "term"),
    ("war goal", "english", "", "term"),
    ("增加征兵", "simp_chinese", "", "phrase"),
    ("获得政治点数", "simp_chinese", "", "phrase"),
    ("减少征兵", "simp_chinese", "", "phrase"),
    ("需要工厂", "simp_chinese", "", "phrase"),
    ("好的。", "simp_chinese", "", "phrase"),
    ("好的！", "simp_chinese", "", "phrase"),
    ("什么？", "simp_chinese", "", "phrase"),
    ("军队", "simp_chinese", "", "term"),
    ("经济", "simp_chinese", "", "term"),
    ("亚历山德拉", "simp_chinese", "character_name", "proper"),
])
def test_classify_examples(source, source_lang, key, expected):
    assert core._classify_glossary_term_kind(source, source_lang, key) == expected


@pytest.mark.parametrize("verb", "Increase Decrease Gain Lose Add Remove Enable Disable Unlock Lock Can Cannot Is Are Has Have Will Do Does Get Give Take Make Build Raise Lower Reduce Improve Start Stop Join Leave Declare Accept Refuse Reject Allow Ban Demand Request Send Recruit Grant Revoke Choose Select Open Close Show Hide".split())
def test_english_verb_prefixes(verb):
    assert core._classify_glossary_term_kind(f"{verb.lower()} Infantry", "english") == "phrase"


@pytest.mark.parametrize("word", "to for per by with from into than if when while not".split())
def test_english_function_words(word):
    assert core._classify_glossary_term_kind(f"Support {word} Infantry", "english") == "phrase"


@pytest.mark.parametrize("prefix", "增加 减少 获得 失去 提高 降低 解锁 允许 禁止 可以 需要".split())
def test_chinese_verb_prefixes(prefix):
    assert core._classify_glossary_term_kind(prefix + "军队", "simp_chinese") == "phrase"


def test_target_only_used_by_specific_term_heuristic():
    assert core._classify_glossary_term_kind("Infantry", "english", target="増加してください！") == "term"
    assert core._classify_glossary_term_kind("York Duke", "english", target="ヨーク公爵") == "proper"


def test_build_preserves_candidates_and_existing_values(tmp_path):
    source = tmp_path / "sample_l_english.yml"
    target = tmp_path / "sample_l_japanese.yml"
    source.write_text('l_english:\n a:0 "Great!"\n b:0 "Great!"\n c:0 "Infantry"\n d:0 "Infantry"\n e:0 "Grand Fleet"\n f:0 "Grand Fleet"\n g:0 "Economy"\n', encoding="utf-8")
    target.write_text('l_japanese:\n a:0 "素晴らしい！"\n b:0 "よし！"\n c:0 "歩兵"\n d:0 "歩兵"\n e:0 "大艦隊"\n f:0 "大艦隊"\n g:0 "経済"\n', encoding="utf-8")
    candidates = core.build_auto_glossary_candidates([{"source": source, "target": target}])
    assert [candidate["term_kind"] for candidate in candidates] == ["phrase", "proper", "term"]
    assert [{key: value for key, value in candidate.items() if key != "term_kind"} for candidate in candidates] == [
        {"source": "Great!", "source_lang": "english", "preferred": "よし！", "occurrences": 2, "variants": [{"text": "よし！", "count": 1}, {"text": "素晴らしい！", "count": 1}], "conflict": True, "keys": ["a", "b"], "source_kind": "auto"},
        {"source": "Grand Fleet", "source_lang": "english", "preferred": "大艦隊", "occurrences": 2, "variants": [{"text": "大艦隊", "count": 2}], "conflict": False, "keys": ["e", "f"], "source_kind": "auto"},
        {"source": "Infantry", "source_lang": "english", "preferred": "歩兵", "occurrences": 2, "variants": [{"text": "歩兵", "count": 2}], "conflict": False, "keys": ["c", "d"], "source_kind": "auto"},
    ]


def candidates_for_save():
    return [{"source": source, "preferred": target, "term_kind": kind, "conflict": True,
             "source_lang": "english", "occurrences": 2,
             "variants": [{"text": target, "count": 1}, {"text": target + "別訳", "count": 1}]}
            for source, target, kind in [("Great!", "よし！", "phrase"), ("Infantry", "歩兵", "term"), ("Grand Fleet", "大艦隊", "proper")]]


@pytest.mark.parametrize("source_lang,source_text", [("english", "Alexandra"), ("simp_chinese", "亚历山德拉")])
def test_build_uses_first_key_and_preferred_target(tmp_path, monkeypatch, source_lang, source_text):
    source = tmp_path / f"names_l_{source_lang}.yml"
    target = tmp_path / "names_l_japanese.yml"
    source.write_text(f'l_{source_lang}:\n character_name_first:0 "{source_text}"\n second:0 "{source_text}"\n third:0 "{source_text}"\n', encoding="utf-8")
    target.write_text('l_japanese:\n character_name_first:0 "女史"\n second:0 "アレクサンドラ"\n third:0 "アレクサンドラ"\n', encoding="utf-8")
    calls = []
    classify = core._classify_glossary_term_kind

    def record_classification(source, source_lang, key="", target="", target_lang="japanese"):
        calls.append((source, source_lang, key, target))
        return classify(source, source_lang, key, target, target_lang)

    monkeypatch.setattr(core, "_classify_glossary_term_kind", record_classification)
    candidates = core.build_auto_glossary_candidates([{"source": source, "target": target}])
    assert calls == [(source_text, source_lang, "character_name_first", "アレクサンドラ")]
    assert candidates[0]["term_kind"] == "proper"
    assert candidates[0]["conflict"] is True
    assert candidates[0]["occurrences"] == 3


@pytest.mark.parametrize("include_phrases", [False, True])
def test_save_keeps_metadata_and_respects_phrase_option(tmp_path, include_phrases):
    path = tmp_path / "glossary.json"
    options = {"include_phrases": True} if include_phrases else {}
    result = core.save_auto_glossary_candidates(path, candidates_for_save(), **options)
    assert ("Great!" in core.load_glossary(path)) is include_phrases
    assert result["added"] == (3 if include_phrases else 2)
    assert result["total"] == 3
    metadata = core.load_json(core.glossary_variants_path(path), {})
    assert {source: info["term_kind"] for source, info in metadata.items()} == {"Great!": "phrase", "Infantry": "term", "Grand Fleet": "proper"}
    assert metadata["Great!"]["preferred"] == "よし！"


def test_save_preserves_manual_terms_and_legacy_candidates(tmp_path):
    path = tmp_path / "glossary.json"
    core.save_glossary(path, {"Great!": "手動訳"})
    candidates = candidates_for_save() + [{"source": "Legacy", "preferred": "旧用語"}]
    core.save_auto_glossary_candidates(path, candidates)
    assert core.load_glossary(path)["Great!"] == "手動訳"
    assert core.load_glossary(path)["Legacy"] == "旧用語"
    assert "Great!" not in core.load_json(core.glossary_variants_path(path), {})


def test_resolver_excludes_phrases_before_limit(monkeypatch):
    sent = []

    def fake_llm(provider, url, model, user, system, **kwargs):
        sent.append(json.loads(user))
        return '[{"source":"Infantry","preferred":"統一歩兵"}]'

    monkeypatch.setattr(core, "call_llm_raw", fake_llm)
    candidates = [dict(candidates_for_save()[0], source=f"Reply {index}!") for index in range(81)] + candidates_for_save()[1:]
    result = core.resolve_auto_glossary_conflicts("local", "unused", "fake", candidates)
    assert [item["source"] for item in sent[0]["items"]] == ["Infantry", "Grand Fleet"]
    assert result is candidates
    assert candidates[-2]["preferred"] == "統一歩兵"
    assert candidates[0]["preferred"] == "よし！"


def test_phrase_only_conflicts_do_not_call_llm(monkeypatch):
    monkeypatch.setattr(core, "call_llm_raw", lambda *args, **kwargs: pytest.fail("phrase sent to LLM"))
    candidates = candidates_for_save()[:1]
    assert core.resolve_auto_glossary_conflicts("local", "unused", "fake", candidates) is candidates


@pytest.mark.parametrize("include_phrases", [False, True])
def test_ui_generation_captures_checkbox_before_worker(tmp_path, monkeypatch, include_phrases):
    main = importlib.import_module("main")
    monkeypatch.setattr(main.messagebox, "showinfo", lambda *args: None)
    monkeypatch.setattr(core, "build_auto_glossary_candidates", lambda pairs, target_lang="japanese": candidates_for_save())
    pending = []

    class FakeThread:
        def __init__(self, *, target, **kwargs):
            self.target = target

        def start(self):
            pending.append(self.target)

    monkeypatch.setattr(main.threading, "Thread", FakeThread)
    state = SimpleNamespace(_closing=False, glossary_import_busy=False, auto_glossary_controller=None,
                            _auto_glossary_pairs_from_origin=lambda origin: [{}], events=queue.Queue(),
                            auto_glossary_status_var=FakeVar(""), auto_glossary_include_phrases_var=FakeVar(include_phrases),
                            glossary_path_var=FakeVar(str(tmp_path / "glossary.json")),
                            provider_var=FakeVar("local"), url_var=FakeVar("unused"), model_var=FakeVar(""),
                            preset_var=FakeVar("General"), api_key_var=FakeVar(""))
    main.App.start_auto_glossary_generation.__get__(state)("normal")
    state.auto_glossary_include_phrases_var.set(not include_phrases)
    pending[0]()
    event, result = state.events.get_nowait()
    assert event == "auto_glossary_done", result
    assert ("Great!" in core.load_glossary(tmp_path / "glossary.json")) is include_phrases


def make_ui(main, path):
    state = SimpleNamespace(glossary_path_var=FakeVar(str(path)), progress_text=FakeVar(""),
                            glossary_tree=FakeTree(), auto_glossary_tree=FakeTree(),
                            auto_glossary_kind_filter_vars={kind: FakeVar(True) for kind in ("proper", "term", "phrase")})
    for name in ("_glossary_variant_metadata", "_glossary_kind_label", "load_glossary_ui", "save_glossary_ui", "_refresh_auto_glossary_tree", "_run_glossary_action"):
        setattr(state, name, getattr(main.App, name).__get__(state))
    return state


def test_display_filters_and_metadata_only_phrases_do_not_change_load_or_save(tmp_path, monkeypatch):
    main = importlib.import_module("main")
    monkeypatch.setattr(main.messagebox, "showerror", lambda *args: pytest.fail(str(args)))
    path = tmp_path / "glossary.json"
    core.save_auto_glossary_candidates(path, candidates_for_save() + [{"source": "Legacy", "preferred": "旧用語"}])
    core.save_glossary(path, dict(core.load_glossary(path), Manual="手動"))
    state = make_ui(main, path)
    state.load_glossary_ui(silent=True)
    assert "Great!" not in {row[0] for row in state.auto_glossary_tree.rows.values()}
    state._refresh_auto_glossary_tree()
    rows = {row[0]: row for row in state.auto_glossary_tree.rows.values()}
    assert rows["Great!"][3] == "定型句"
    assert rows["Legacy"][3] == ""
    assert rows["Grand Fleet"][3] == "固有名詞"
    assert rows["Infantry"][3] == "単語"
    state.auto_glossary_kind_filter_vars["term"].set(False)
    state._refresh_auto_glossary_tree()
    assert "Infantry" not in {row[0] for row in state.auto_glossary_tree.rows.values()}
    before = core.load_glossary(path)
    state._run_glossary_action(state.save_glossary_ui)
    assert core.load_glossary(path) == before
    state.load_glossary_ui(silent=True)
    assert "Great!" not in {row[0] for row in state.auto_glossary_tree.rows.values()}


@pytest.mark.parametrize("term_kind,source", [("proper", "Grand Fleet"), ("term", "Infantry"), ("phrase", "Great!")])
def test_each_display_filter_is_read_only(tmp_path, term_kind, source):
    main = importlib.import_module("main")
    path = tmp_path / "glossary.json"
    core.save_auto_glossary_candidates(path, candidates_for_save())
    before = (path.read_bytes(), core.glossary_variants_path(path).read_bytes())
    state = make_ui(main, path)
    state._refresh_auto_glossary_tree()
    assert source in {row[0] for row in state.auto_glossary_tree.rows.values()}
    state.auto_glossary_kind_filter_vars[term_kind].set(False)
    state._refresh_auto_glossary_tree()
    assert source not in {row[0] for row in state.auto_glossary_tree.rows.values()}
    assert (path.read_bytes(), core.glossary_variants_path(path).read_bytes()) == before


@pytest.mark.parametrize("include_phrases", [False, True])
def test_kind_summary_matches_save_option(tmp_path, include_phrases):
    main = importlib.import_module("main")
    result = core.save_auto_glossary_candidates(tmp_path / "glossary.json", candidates_for_save(), include_phrases=include_phrases)
    summary = main.App._auto_glossary_kind_summary(result)
    assert "固有名詞 1／単語 1／定型句 1" in summary
    assert ("用語集には入れていません" in summary) is not include_phrases


@pytest.mark.parametrize("text", ["The League of Eight Provinces", "Union for the Defence of the Motherland and Freedom",
                                  "Cape to Cairo Railway", "2nd Sino-Japanese War", "the House of Commons",
                                  "Bourse Générale du Travail"])
def test_long_names_are_proper(text):
    assert core._classify_glossary_term_kind(text, "english") == "proper"


@pytest.mark.parametrize("text", ["Ltd.", "Jr.", "S.A.", "H.R.M.", "Accept", "Unlock", "request"])
def test_abbreviations_and_single_verbs_are_not_phrases(text):
    assert core._classify_glossary_term_kind(text, "english") != "phrase"


@pytest.mark.parametrize("text", ["Good.", "Fine.", "OK.", "Damn.", "Very well."])
def test_short_replies_with_a_period_are_phrases(text):
    assert core._classify_glossary_term_kind(text, "english") == "phrase"


@pytest.mark.parametrize("text", ["Close Air Support", "Lower Yangtze", "Open Door Policy"])
def test_adjective_verbs_at_the_start_of_names(text):
    assert core._classify_glossary_term_kind(text, "english") == "proper"
