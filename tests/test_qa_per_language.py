import pytest

from app import translator_core as core
import i18n


def new_issues(value, language, source=None):
    sources = {"sample": source} if source is not None else None
    return [issue for issue in core.qa_entries({"sample": value}, sources, target_lang=language)
            if issue["rule_id"].startswith("QA-SCRIPT-")
            or issue["rule_id"] in {"QA-ENGLISH-LEFT-001", "QA-SAME-AS-SOURCE-001"}]


@pytest.mark.parametrize("language,value,rule,severity", [
    ("korean", "국가 經 정책", "QA-SCRIPT-HAN-001", "warning"),
    ("korean", "과거(科擧) 제도", "QA-SCRIPT-HAN-001", "notice"),
    ("korean", "과거（科擧） 제도", "QA-SCRIPT-HAN-001", "notice"),
    ("korean", "국가 かな 정책", "QA-SCRIPT-KANA-001", "warning"),
    ("simp_chinese", "国家かな政策", "QA-SCRIPT-KANA-001", "warning"),
    ("simp_chinese", "国家한政策", "QA-SCRIPT-HANGUL-001", "warning"),
    ("simp_chinese", "国家Ж政策", "QA-SCRIPT-CYRILLIC-001", "notice"),
    ("korean", "국가 Ж 정책", "QA-SCRIPT-CYRILLIC-001", "notice"),
    ("french", "Le conseil Ж", "QA-SCRIPT-CYRILLIC-001", "warning"),
    ("russian", "Государство 經", "QA-SCRIPT-HAN-001", "warning"),
    ("russian", "Государство かな", "QA-SCRIPT-KANA-001", "warning"),
    ("russian", "Государство 한", "QA-SCRIPT-HANGUL-001", "warning"),
])
def test_script_qa(language, value, rule, severity):
    issues = new_issues(value, language)
    assert [(issue["rule_id"], issue["severity"]) for issue in issues] == [(rule, severity)]
    assert issues[0]["message_parts"]
    assert issues[0]["repairable"] is False


@pytest.mark.parametrize("language", ["english", "french", "german", "spanish", "polish", "braz_por", "turkish"])
@pytest.mark.parametrize("text,kind", [("經", "han"), ("か", "kana"), ("한", "hangul"), ("Ж", "cyrillic")])
def test_all_latin_languages(language, text, kind):
    assert [(issue[0], issue[1]) for issue in core.script_mixture_issues("Texte " + text, language)] == [(kind, "warning")]


@pytest.mark.parametrize("token", ["[GetName 經か한Ж]", "$經か한Ж$", "£icon_name£", "£icon_name|1", "@icon_name!", "@acceptance_status_1!", "#bold;tooltip:經か한Ж "])
def test_protected_tokens_do_not_count(token):
    assert core.script_mixture_issues(token + " Texte", "french") == []


def test_visible_style_contents_still_count():
    assert core.script_mixture_issues("§Y經§! #bold か#!", "french")
    assert new_issues("[GetName] 국가 經 정책", "korean")[0]["severity"] == "warning"


def test_korean_annotation_does_not_hide_outside_han():
    issues = new_issues("과거(科擧) 經 제도", "korean")
    assert any(issue["severity"] == "warning" for issue in issues)
    assert new_issues("(科擧) 제도", "korean")[0]["severity"] == "warning"


@pytest.mark.parametrize("character,kind", [("𠀀", "han"), ("ｶ", "kana"), ("ᄒ", "hangul"), ("Ꙁ", "cyrillic")])
def test_script_extensions(character, kind):
    assert core.script_mixture_issues(character, "french")[0][:2] == (kind, "warning")


@pytest.mark.parametrize("language", ["english", "french", "german", "spanish", "polish", "braz_por", "turkish", "russian", "korean", "simp_chinese"])
def test_new_same_source_only_when_legacy_does_not_reject(language):
    source = "national policy" if language != "english" else "politique nationale"
    source_language = "english" if language != "english" else "french"
    issues = core.qa_entries({"sample": source}, {"sample": source}, source_language, target_lang=language)
    legacy = core.unusable_translation(source, source, source_language, language)
    unchanged = [issue for issue in issues if issue["type"] in {"untranslated", "same_as_source"}]
    assert len(unchanged) == 1
    assert unchanged[0]["severity"] == ("error" if legacy else "warning")
    assert unchanged[0]["repairable"] is legacy


@pytest.mark.parametrize("language,value", [("simp_chinese", "国家政策"), ("korean", "국가정책"), ("russian", "политика")])
def test_new_warning_reaches_non_latin_languages(language, value):
    assert not core.unusable_translation(value, value, "english", language)
    assert [(issue["rule_id"], issue["severity"]) for issue in new_issues(value, language, value)] == [
        ("QA-SAME-AS-SOURCE-001", "warning")]


@pytest.mark.parametrize("value", ["Napoleon", "Karl Marx", "de Saint-André", "Herwarth von Bittenfeld", "d’Estaing", "NASA", "NATO EU", "12345", "!? 123", "abc", "[GetName]", "@acceptance_status_1!", "B-52", "F16"])
def test_same_source_exclusions(value):
    assert not [issue for issue in new_issues(value, "french", value)
                if issue["rule_id"] == "QA-SAME-AS-SOURCE-001"]


def test_existing_repairable_error_is_not_downgraded_or_duplicated():
    source = "The council approved the new law."
    issues = core.qa_entries({"sample": source}, {"sample": source}, target_lang="french")
    assert [(issue["rule_id"], issue["severity"], issue["repairable"]) for issue in issues
            if issue["type"] in {"untranslated", "same_as_source"}] == [("QA-UNTRANSLATED-EN-002", "error", True)]


def test_lowercase_name_file_is_exempt_only_from_new_same_source_rule():
    value = "von example"
    issues = core.qa_entries({"sample": value}, {"sample": value}, target_lang="french",
                             source_path=core.Path("/synthetic/localization/names_l_english.yml"))
    assert not issues


def test_numbers_do_not_exempt_an_ordinary_phrase():
    assert any(issue["rule_id"] == "QA-SAME-AS-SOURCE-001" and issue["severity"] == "warning"
               for issue in new_issues("raise 10 taxes", "french", "raise 10 taxes"))


def test_source_free_latin_copy_is_only_a_notice_and_mixture_does_not_retry():
    assert not core.foreign_in_output("the council of the state", "french")
    assert not core.foreign_in_output("국가 經 정책", "korean")
    assert not core.foreign_in_output("国家かな政策", "simp_chinese")
    assert not core.foreign_in_output("Государство 經", "russian")


@pytest.mark.parametrize("language,value", [
    ("french", "the council of the state"),
    ("simp_chinese", "国家 national policy"),
    ("korean", "국가 national policy"),
    ("russian", "Государство national policy"),
    ("simp_chinese", "国家national"),
    ("korean", "국가national"),
    ("russian", "Государствоnational"),
])
def test_english_residue_notice(language, value):
    assert any(issue["rule_id"] == "QA-ENGLISH-LEFT-001" and issue["severity"] == "notice"
               for issue in new_issues(value, language))


@pytest.mark.parametrize("language,prefix", [("simp_chinese", "国家"), ("korean", "국가"), ("russian", "Государство")])
def test_english_excludes_acronyms_models_and_tokens(language, prefix):
    assert not new_issues(prefix + " NATO EU B-52 F16 [the council of the state] $national_policy$", language)


def test_english_target_is_not_english_residue_or_same_language_copy():
    value = "the council of the state"
    assert not new_issues(value, "english", value)


@pytest.mark.parametrize("value", ["国民政策 한 Ж", "國家將繼續行動。", "national policy", "[GetName] 国家"])
def test_no_new_rules_for_japanese(value):
    assert core.script_mixture_issues(value, "japanese") == []
    assert not new_issues(value, "japanese", value)


def test_ui_messages_have_localized_parts():
    previous = i18n.get_ui_language()
    try:
        for language in ("japanese", "english"):
            i18n.set_ui_language(language)
            issue = new_issues("국가 經 정책", "korean")[0]
            assert not issue["message"].startswith("u9.")
            assert issue["message_parts"][0]["id"].startswith("u9.")
    finally:
        i18n.set_ui_language(previous)
