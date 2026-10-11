import json
import importlib
import queue
from types import SimpleNamespace

import pytest

from app import translator_core as core


@pytest.mark.parametrize("original,expected,removed", [
    ("債務 危機", "債務危機", 1),
    ("が 4 ヶ月", "が4ヶ月", 2),
    ("ABC 社", "ABC社", 1),
    ("大統領 [GetName]", "大統領[GetName]", 1),
    ("$NAME$ 将軍", "$NAME$将軍", 1),
    ("金 £gold£", "金£gold£", 1),
    ("§Y 債務§!", "§Y債務§!", 1),
    ("債務 §!", "債務§!", 1),
    ("#bold 債務#!", "#bold 債務#!", 0),
    ("#bold   債務 危機#!", "#bold   債務危機#!", 1),
    ("#bold;size=20 債務 危機#!", "#bold;size=20 債務 危機#!", 0),
    ("Great War / 4 000 / New York", "Great War / 4 000 / New York", 0),
    (r" 債務 \n 危機 ", r" 債務 \n 危機 ", 0),
    (" 債務 \n 危機 ", " 債務 \n 危機 ", 0),
    ("債務   危機", "債務危機", 3),
    ("債務　危機", "債務　危機", 0),
    ("債務 、 危機 ！ （ 全角 ）", "債務、危機！（全角）", 6),
    ("日本 한국 日本", "日本 한국 日本", 0),
    ("[GetName('債務 危機')] 将軍", "[GetName('債務 危機')]将軍", 1),
    ("債務\t危機", "債務\t危機", 0),
    (" 債務 ", " 債務 ", 0),
    ("債務 §Y危機", "債務 §Y危機", 0),
    ("§! 債務", "§! 債務", 0),
    ("[GetName] $NAME$ £gold£", "[GetName] $NAME$ £gold£", 0),
    ("$債務 危機$ 将軍", "$債務 危機$将軍", 1),
    ("㐀 𠀀", "㐀𠀀", 1),
])
def test_spacing_rules(original, expected, removed):
    assert core.normalize_cjk_spacing(original, "japanese") == (expected, removed)
    assert core.normalize_cjk_spacing(expected, "japanese") == (expected, 0)


@pytest.mark.parametrize("language", ["korean", "english", "french", "russian"])
def test_other_languages_unchanged(language):
    assert core.normalize_cjk_spacing("債務 危機", language) == ("債務 危機", 0)


def test_chinese_and_language_flags():
    assert core.normalize_cjk_spacing("债务 危机", "simp_chinese") == ("债务危机", 1)
    assert {language for language, info in core.TARGET_LANGUAGES.items()
            if info["remove_cjk_spaces"]} == {"japanese", "simp_chinese"}


def write_localization(path, language, entries):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"l_{language}:\n" + "".join(
        f' {key}:0 "{value}"\n' for key, value in entries.items()), encoding="utf-8")


def test_translation_and_cache(tmp_path, monkeypatch):
    source = tmp_path / "input" / "english" / "events_l_english.yml"
    write_localization(source, "english", {"description": "Debt crisis"})
    cache = tmp_path / "cache.json"
    calls = []

    def translate(_url, _model, jobs, *args, **kwargs):
        calls.append(len(jobs))
        return ["債務   危機が 4 ヶ月"] * len(jobs)

    monkeypatch.setattr(core, "translate_batch", translate)
    for index, enabled in enumerate([True, True, False]):
        output = tmp_path / f"output{index}"
        result = core.run_translation(source.parent.parent, output, cache_path=cache,
                                      auto_qa=False, verbose=False, normalize_spacing=enabled)
        values = core.parse_localization_file(output / "japanese" / "events_l_japanese.yml")[1]
        assert values["description"] == ("債務危機が4ヶ月" if enabled else "債務   危機が 4 ヶ月")
        assert result["spaces_removed"] == (5 if enabled else 0)
        assert list(json.loads(cache.read_text()).values()) == ["債務   危機が 4 ヶ月"]
    assert calls == [1]


def test_repair_preserves_existing_lines(tmp_path, monkeypatch):
    source = tmp_path / "events_l_japanese.yml"
    write_localization(source, "japanese", {"existing": "債務 危機", "foreign": "Debt crisis"})
    monkeypatch.setattr(core, "translate_batch", lambda _url, _model, jobs, *args, **kwargs:
                        ["債務 危機"] * len(jobs))
    output = tmp_path / "output"
    result = core.run_translation(source, output, auto_qa=False, verbose=False)
    assert core.parse_localization_file(output / "japanese" / source.name)[1] == {
        "existing": "債務 危機", "foreign": "債務危機"}
    assert result["spaces_removed"] == 1


def test_notice_is_not_auto_repaired(tmp_path, monkeypatch):
    source = tmp_path / "events_l_english.yml"
    target = tmp_path / "events_l_japanese.yml"
    write_localization(source, "english", {"description": "Debt crisis"})
    write_localization(target, "japanese", {"description": "債務 危機"})
    monkeypatch.setattr(core, "translate_batch", lambda *args, **kwargs: pytest.fail("notice sent to LLM"))
    result = core.qa_file_with_auto_repair(target, source)
    notices = [issue for issue in result["issues"] if issue["rule_id"] == "QA-SPACE-001"]
    assert len(notices) == 1
    assert notices[0]["severity"] == "notice"
    assert notices[0]["type"] == "cjk_space"
    assert notices[0]["repairable"] is False
    assert result["repaired"] == 0
    assert core.parse_localization_file(target)[1]["description"] == "債務 危機"
    assert not any(issue["rule_id"] == "QA-SPACE-001" for issue in
                   core.qa_entries({"description": "#bold 債務#!"}))


@pytest.mark.parametrize("enabled", [True, False])
def test_qa_retranslated_value_spacing(tmp_path, monkeypatch, enabled):
    source = tmp_path / "events_l_english.yml"
    target = tmp_path / "events_l_japanese.yml"
    write_localization(source, "english", {"description": "Debt crisis"})
    write_localization(target, "japanese", {"description": "Debt crisis"})
    monkeypatch.setattr(core, "translate_batch", lambda _url, _model, jobs, *args, **kwargs:
                        ["債務 危機"] * len(jobs))
    result = core.qa_file_with_auto_repair(target, source, normalize_spacing=enabled)
    assert result["repaired"] == 1
    assert result["spaces_removed"] == int(enabled)
    assert core.parse_localization_file(target)[1]["description"] == ("債務危機" if enabled else "債務 危機")


@pytest.mark.parametrize("enabled", [True, False])
def test_chinese_basis_respects_setting(tmp_path, monkeypatch, enabled):
    source = tmp_path / "events_l_simp_chinese.yml"
    write_localization(source, "simp_chinese", {"description": "债务危机"})
    monkeypatch.setattr(core, "translate_batch", lambda _url, _model, jobs, *args, **kwargs:
                        ["債務 危機"] * len(jobs))
    output = tmp_path / "output"
    result = core.run_chinese_basis_translation(source, output, auto_qa=False,
                                               normalize_spacing=enabled)
    target = output / "japanese" / "events_l_japanese.yml"
    assert core.parse_localization_file(target)[1]["description"] == ("債務危機" if enabled else "債務 危機")
    assert result["spaces_removed"] == int(enabled)


@pytest.mark.parametrize("language", ["japanese", "simp_chinese", "korean", "french"])
def test_qa_notice_language_gating(language):
    issues = core.qa_entries({"description": "債務 危機"}, target_lang=language)
    assert any(issue["rule_id"] == "QA-SPACE-001" for issue in issues) == (
        language in {"japanese", "simp_chinese"})


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.mark.parametrize("enabled", [True, False])
@pytest.mark.parametrize("language,text", [("japanese", "債務 危機"), ("simp_chinese", "债务 危机")])
def test_diff_translation_spacing(tmp_path, monkeypatch, enabled, language, text):
    main = importlib.import_module("main")
    source = tmp_path / "events_l_english.yml"
    target = tmp_path / f"events_l_{language}.yml"
    write_localization(source, "english", {"description": "Debt crisis"})
    write_localization(target, language, {"existing": text})
    monkeypatch.setattr(main.core, "translate_single_text", lambda *args, **kwargs: text)
    state = SimpleNamespace(
        _closing=False, diff_controller=None, diff_batch_contexts=[],
        diff_rows=[{"key": "description", "status": "missing", "source": "Debt crisis"}],
        diff_src_var=Value(str(source)), diff_dst_var=Value(str(target)), diff_source_lang="english",
        diff_source_entries={"description": "Debt crisis"}, diff_target_entries={"existing": text},
        diff_message_var=Value(), glossary_path_var=Value(), url_var=Value(), model_var=Value(),
        preset_var=Value("General"), provider_var=Value("Ollama"), api_key_var=Value(),
        target_lang_var=Value(language), normalize_spacing_var=Value(enabled), events=queue.Queue(),
        _backup_before_diff_write=lambda paths: [], _invalidate_status_after_diff_write=lambda paths: None,
    )
    main.App.translate_diff_items(state, all_missing=True, _llm_ready=True)
    state.diff_translate_thread.join(timeout=10)
    assert not state.diff_translate_thread.is_alive()
    events = []
    while not state.events.empty():
        events.append(state.events.get())
    result = next(payload for kind, payload in events if kind == "diff_translate_done")
    assert result["spaces_removed"] == int(enabled)
    assert main.core.parse_localization_file(target)[1] == {
        "existing": text, "description": text.replace(" ", "") if enabled else text}


@pytest.mark.parametrize("enabled", [True, False])
def test_manual_qa_setting_and_count(tmp_path, monkeypatch, enabled):
    source = tmp_path / "events_l_english.yml"
    target = tmp_path / "events_l_japanese.yml"
    write_localization(source, "english", {"description": "Debt crisis"})
    write_localization(target, "japanese", {"description": "Debt crisis"})
    monkeypatch.setattr(core, "translate_batch", lambda _url, _model, jobs, *args, **kwargs:
                        ["債務 危機"] * len(jobs))
    result = core.auto_repair_qa_pairs([{"source_file": str(source), "target_file": str(target)}],
                                      backup_root=tmp_path / "backup", normalize_spacing=enabled)
    assert result["spaces_removed"] == result["summary"]["spaces_removed"] == int(enabled)
    assert core.parse_localization_file(target)[1]["description"] == ("債務危機" if enabled else "債務 危機")


@pytest.mark.parametrize("enabled", [True, False])
def test_preferences_save_spacing_option(tmp_path, monkeypatch, enabled):
    main = importlib.import_module("main")
    preferences = tmp_path / "preferences.json"
    monkeypatch.setattr(main, "APP_PREFS_PATH", preferences)
    state = SimpleNamespace(
        app_preferences={}, provider_var=Value("Ollama"), url_var=Value(), model_var=Value(),
        batch_var=Value(40), workers_var=Value(1), chinese_autoqa_var=Value(True),
        normalize_spacing_var=Value(enabled), monitor_provider_var=Value("Ollama"),
        monitor_url_var=Value(), monitor_model_var=Value(), close_action_var=Value("毎回確認"),
    )
    main.App._save_llm_preferences(state)
    assert json.loads(preferences.read_text())["translation_llm"]["normalize_spacing"] is enabled


def test_hoi4_icons_without_closing_pound_keep_their_terminating_space():
    """「£名前」の後ろの半角スペースはアイコン名の終わり。取ると表示が壊れる（実際の訳で見つかった）。"""
    for text in ("£trigger_no 特別計画が研究されている", "£KR_game_rule_flag_LKT  汪主席", "£pol_idea 影響"):
        assert core.normalize_cjk_spacing(text, "japanese") == (text, 0)
    assert core.normalize_cjk_spacing("£gold£ 金貨", "japanese") == ("£gold£金貨", 1)


def test_space_between_katakana_words_becomes_a_middle_dot():
    """著者の判断：カタカナの語どうしの空白は取らずに「・」にする。英数字・漢字・ひらがなの隣は今までどおり詰める。"""
    assert core.normalize_cjk_spacing("ブリストル ブレニム", "japanese") == ("ブリストル・ブレニム", 1)
    assert core.normalize_cjk_spacing("フェアリー  バトル", "japanese") == ("フェアリー・バトル", 2)
    assert core.normalize_cjk_spacing("フェアリー ・バトル", "japanese") == ("フェアリー・バトル", 1)
    assert core.normalize_cjk_spacing("三菱 A5M", "japanese") == ("三菱A5M", 1)
    assert core.normalize_cjk_spacing("フォッカー G.III", "japanese") == ("フォッカーG.III", 1)
    assert core.normalize_cjk_spacing("ホンジュラス 国家方針", "japanese") == ("ホンジュラス国家方針", 1)
    assert core.normalize_cjk_spacing("債務 危機", "japanese") == ("債務危機", 1)
    # 簡体字中国語にはカタカナが無いので影響しない。韓国語は何もしない
    assert core.normalize_cjk_spacing("ブリストル ブレニム", "korean") == ("ブリストル ブレニム", 0)
