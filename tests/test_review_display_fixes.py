from types import SimpleNamespace
import queue

import pytest
import i18n
import main
import translator_core as core
import ui_status


class Variable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class DeferredThread:
    def __init__(self, target, **kwargs):
        self.target = target

    def start(self):
        pass

    def is_alive(self):
        return False


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.get_ui_language()
    yield
    i18n.set_ui_language(previous)


def localization(tmp_path, lang):
    path = tmp_path / f"sample_l_{lang}.yml"
    path.write_text(f'l_{lang}:\n key:0 "Sample"\n', encoding="utf-8-sig")
    return path


def test_review_pair_qa_keeps_file_language_and_glossary(tmp_path, monkeypatch):
    source = localization(tmp_path, "english")
    target = localization(tmp_path, "french")
    app = SimpleNamespace(target_lang_var=Variable("japanese"), review_worker=None,
                          glossary_path_var=Variable(str(tmp_path / "glossary.json")),
                          qa_summary_var=Variable(), events=queue.Queue(),
                          _clear_pending_review_qa_log=lambda: None)
    seen = []
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(main, "_existing_language_glossary", lambda path, lang: seen.append(("glossary", lang)) or "")
    monkeypatch.setattr(core, "qa_file", lambda *args, **kwargs: seen.append(("qa", kwargs["target_lang"])) or [])
    main.App._start_review_pairs_background(app, [{"source": source, "target": target, "target_language": "french"}])
    app.target_lang_var.set("korean")
    app.review_worker.target()
    contexts, errors = app.events.get()[1]
    assert not errors
    assert contexts[0]["target_lang"] == "french"
    assert seen == [("glossary", "french"), ("qa", "french")]


def test_diff_pair_comparison_keeps_file_language(tmp_path, monkeypatch):
    source = localization(tmp_path, "english")
    targets = [localization(tmp_path, lang) for lang in ("french", "korean")]
    app = SimpleNamespace(target_lang_var=Variable("japanese"), diff_load_worker=None,
                          diff_src_var=Variable(), diff_dst_var=Variable(),
                          diff_summary_var=Variable(), events=queue.Queue())
    seen = []
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(core, "compare_localization_entries", lambda source, target, lang, target_lang: seen.append(target_lang) or [])
    main.App.load_diff_pairs(app, [{"source": source, "target": target} for target in targets])
    app.target_lang_var.set("german")
    app.diff_load_worker.target()
    contexts, errors = app.events.get()[1]
    assert not errors
    assert seen == ["french", "korean"]
    assert [context["target_lang"] for context in contexts] == seen


@pytest.mark.parametrize("kind", ["file", "mod"])
def test_glossary_import_uses_tab_language(tmp_path, monkeypatch, kind):
    target = localization(tmp_path, "french")
    app = SimpleNamespace(target_lang_var=Variable("japanese"), glossary_lang_var=Variable("french"),
                          glossary_import_busy=False)
    seen = []
    app._import_japanese_targets_with_fallback = lambda *args, **kwargs: seen.append(kwargs["target_lang"])
    monkeypatch.setattr(main.filedialog, "askopenfilename", lambda **kwargs: str(target))
    monkeypatch.setattr(main.filedialog, "askdirectory", lambda **kwargs: str(tmp_path))
    main.App.import_glossary_from_japanese_source(app, kind)
    assert seen == ["french"]


def test_saved_language_notice_relocalizes_without_mutation(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "game_for_translation", lambda root: "CK3")
    monkeypatch.setitem(core.GAME_LANGUAGES, "CK3", ("english", "japanese"))
    i18n.set_ui_language("japanese")
    result = core._translation_status_language_notice(
        {"message_parts": [], "unsupported_game_language": True}, tmp_path, target_lang="korean")
    fields = result["message_parts"][0]["fields"]
    assert fields["target_name"] == "korean"
    assert fields["supported_languages"] == ["english", "japanese"]
    i18n.set_ui_language("english")
    rendered = ui_status.display_message(result)
    assert "Korean" in rendered and "Japanese" in rendered
    assert "韓国語" not in rendered
    assert fields["target_name"] == "korean"
    legacy = [ui_status.message_part("u9.external_english_skipped", target_name="韓国語")]
    assert "韓国語" in ui_status.build_message(legacy)


def test_monitor_internal_labels_translate_only_for_display():
    i18n.set_ui_language("english")
    for label in ("日本語キーなし", "確定", "要確認"):
        assert ui_status.display_monitor_label(label) != label
    assert ui_status.display_monitor_label("future") == "future"
    assert ui_status.display_status("欠損あり") != "欠損あり"
    i18n.set_ui_language("japanese")
    for label in ("日本語キーなし", "確定", "要確認"):
        assert ui_status.display_monitor_label(label) == label


def test_status_entry_uses_the_researched_language(tmp_path):
    seen = []
    pair = {"source": tmp_path / "english.yml", "target": tmp_path / "korean.yml"}
    app = SimpleNamespace(
        target_lang_var=Variable("japanese"),
        _selected_mod_status_results=lambda: [{"localization": str(tmp_path), "target_lang": "korean"}],
        _collect_qa_diff_pairs=lambda *args, **kwargs: seen.append(kwargs["target_lang"]) or [pair],
        _choose_qa_diff_pairs=lambda pairs, title: pairs,
        notebook=SimpleNamespace(select=lambda tab: None), tab_review=None,
        load_review_pairs=lambda pairs: None)
    main.App._send_pair_to_qa_or_diff(app, "status", "review")
    assert seen == ["korean"]


def test_glossary_base_import_freezes_language_and_destination(tmp_path, monkeypatch):
    seen = []
    app = SimpleNamespace(
        target_lang_var=Variable("japanese"), glossary_lang_var=Variable("french"),
        glossary_path_var=Variable(str(tmp_path / "glossary.json")), glossary_import_busy=False,
        glossary_import_thread=None, auto_glossary_controller=None, events=queue.Queue(),
        _choose_game_for_glossary_import=lambda: "CK3", _choose_glossary_import_mode=lambda: "common",
        _find_base_game_localization_root=lambda game: tmp_path,
        _set_glossary_import_busy=lambda *args: None,
        _collect_qa_diff_pairs=lambda *args, **kwargs: seen.append("japanese") or [],
        _align_japanese_with_base_root=lambda *args, **kwargs: seen.append(kwargs["target_lang"]) or {"records": []})
    app._start_glossary_import_thread = main.App._start_glossary_import_thread.__get__(app)
    app._finish_import_candidates_in_worker = main.App._finish_import_candidates_in_worker.__get__(app)
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(core, "build_import_glossary_candidates_from_records", lambda *args, **kwargs: seen.append(kwargs["target_lang"]) or [{"source": "Sample", "target": "Exemple"}])
    monkeypatch.setattr(core, "save_auto_glossary_candidates", lambda path, *args, **kwargs: seen.append(path) or {"total": 1})
    main.App.import_glossary_from_base_game(app)
    expected_path = core.glossary_path_for_language(tmp_path / "glossary.json", "french")
    app.glossary_lang_var.set("korean")
    app.glossary_path_var.set(str(tmp_path / "other.json"))
    app.glossary_import_thread.target()
    assert seen == ["french", "french", expected_path]


def test_diff_llm_and_write_use_each_context_language(tmp_path, monkeypatch):
    contexts = []
    for lang in ("french", "korean"):
        target = localization(tmp_path, lang)
        contexts.append({"source_path": tmp_path / "english.yml", "target_path": target,
                         "lang": "english", "target_lang": lang, "source_entries": {"key": "Sample"},
                         "target_entries": {}, "rows": [{"key": "key", "source": "Sample", "status": "missing"}]})
    app = SimpleNamespace(_closing=False, diff_controller=None, diff_rows=[], diff_batch_contexts=contexts,
                          target_lang_var=Variable("japanese"), events=queue.Queue(), diff_message_var=Variable(),
                          glossary_path_var=Variable(""), _backup_before_diff_write=lambda paths: [],
                          _invalidate_status_after_diff_write=lambda paths: None)
    for name in ("url", "model", "preset", "provider", "api_key"):
        setattr(app, name + "_var", Variable())
    seen = []
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(main, "_diff_translation_problem", lambda *args: "")
    monkeypatch.setattr(core, "translate_single_text", lambda *args, **kwargs: seen.append(("llm", kwargs["target_lang"])) or "Translated")
    monkeypatch.setattr(core, "upsert_localization_values", lambda path, values, lang: seen.append(("write", lang)))
    main.App.translate_diff_items(app, all_missing=True, _llm_ready=True)
    app.target_lang_var.set("german")
    app.diff_translate_thread.target()
    assert seen == [("llm", "french"), ("llm", "korean"), ("write", "french"), ("write", "korean")]
    assert app.events.queue[-1][0] == "diff_translate_done"


@pytest.mark.parametrize("language", ["english", "japanese"])
def test_event_results_translate_internal_labels_without_changing_data(tmp_path, language):
    i18n.set_ui_language(language)
    rows = []
    tree = SimpleNamespace(get_children=lambda: [], delete=lambda iid: None,
                           insert=lambda *args, **kwargs: rows.append(kwargs["values"]))
    candidate = {"kind": "日本語キーなし", "confidence": "確定", "source": "Sample"}
    app = SimpleNamespace(events=queue.Queue(), monitor_tree=tree, monitor_summary_var=Variable(),
                          monitor_status_var=Variable(), target_lang_var=Variable("japanese"),
                          mod_research_results=[], mod_status_summary_var=Variable(),
                          _populate_mod_status_tree=lambda: None, _schedule_translation_status_state_save=lambda reason: None,
                          _refresh_operation_states=lambda: None, after=lambda *args: None, _poll_events=lambda: None)
    app.events.put(("monitor_results", [candidate]))
    app.events.put(("mod_status_append", {"status": "欠損あり", "target_lang": "japanese"}))
    main.App._poll_events(app)
    expected = ("Japanese key missing", "Confirmed") if language == "english" else ("日本語キーなし", "確定")
    assert rows[0][:2] == expected
    assert ui_status.display_status("欠損あり") in app.mod_status_summary_var.get()
    assert candidate == {"kind": "日本語キーなし", "confidence": "確定", "source": "Sample"}


def test_single_review_qa_reuses_pinned_language(tmp_path, monkeypatch):
    source = localization(tmp_path, "english")
    target = localization(tmp_path, "french")
    app = SimpleNamespace(target_lang_var=Variable("japanese"), review_worker=None,
                          review_src_var=Variable(str(source)), review_dst_var=Variable(str(target)),
                          review_target_lang="french", review_target_path=str(target),
                          review_target_entries={"key": "Exemple"}, review_source_entries={"key": "Sample"},
                          review_source_lang="english", glossary_path_var=Variable(""),
                          qa_summary_var=Variable(), events=queue.Queue(), _clear_pending_review_qa_log=lambda: None)
    seen = []
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(core, "qa_file", lambda *args, **kwargs: seen.append(kwargs["target_lang"]) or [])
    main.App._start_review_background(app)
    app.target_lang_var.set("korean")
    app.review_worker.target()
    assert seen == ["french"]
    assert app.events.get()[0] == "review_qa_loaded"


def test_proofreading_uses_opened_file_language(tmp_path, monkeypatch):
    target = localization(tmp_path, "french")
    app = SimpleNamespace(_closing=False, target_lang_var=Variable("japanese"),
                          review_dst_var=Variable(str(target)), _selected_review_key=lambda: "key",
                          dst_text=SimpleNamespace(get=lambda *args: "Exemple"),
                          review_source_entries={"key": "Sample"}, issue_text=Variable(),
                          glossary_path_var=Variable(""), events=queue.Queue())
    for name in ("url", "model", "preset", "provider", "api_key"):
        setattr(app, name + "_var", Variable())
    seen = []
    monkeypatch.setattr(main.threading, "Thread", DeferredThread)
    monkeypatch.setattr(core, "proofread_text", lambda *args, **kwargs: seen.append(kwargs["target_lang"]) or "Exemple")
    main.App.ai_proofread_selected(app)
    app.target_lang_var.set("korean")
    app.proofread_thread.target()
    assert seen == ["french"]
    assert app.events.get() == ("proofread", "Exemple")


def test_manual_diff_save_keeps_opened_file_language(tmp_path, monkeypatch):
    target = localization(tmp_path, "french")
    app = SimpleNamespace(target_lang_var=Variable("japanese"), diff_dst_var=Variable(str(target)),
                          diff_src_var=Variable(str(tmp_path / "english.yml")),
                          _selected_diff_keys=lambda: ["key"],
                          diff_dst_text=SimpleNamespace(get=lambda *args: "Exemple"),
                          _backup_before_diff_write=lambda paths: [], _invalidate_status_after_diff_write=lambda paths: None,
                          diff_batch_contexts=[], load_diff_inspector=lambda: None)
    seen = []
    monkeypatch.setattr(core, "upsert_localization_values", lambda path, values, lang: seen.append(lang))
    monkeypatch.setattr(main, "record_error", lambda *args, **kwargs: pytest.fail(str(args)))
    monkeypatch.setattr(main.messagebox, "showerror", lambda *args: pytest.fail(str(args)))
    main.App.save_diff_value(app)
    assert seen == ["french"]
