import json
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from app import translator_core as core


@pytest.fixture(autouse=True)
def restore_ui_language():
    import i18n
    previous = i18n.get_ui_language()
    yield
    i18n.set_ui_language(previous)


def test_korean_chinese_basis_prompt_snapshot():
    snapshot = json.loads((Path(__file__).parent / "fixtures" / "korean_chinese_basis_prompt.json").read_text(encoding="utf-8"))
    assert core.build_system_prompt("simp_chinese", {"科举": "과거"}, chinese_basis=True,
                                    target_lang="korean") == snapshot


def test_korean_basis_cache_keys_are_distinct():
    arguments = ("Ollama", "m", "General", "simp_chinese", "科举")
    keys = [core.translation_cache_key(*arguments, target_lang=language, translation_mode=mode)
            for language, mode in (("korean", "standard"), ("korean", "chinese_basis"),
                                   ("japanese", "chinese_basis"))]
    assert len(set(keys)) == 3


@pytest.mark.parametrize("value,severities", [
    ("과거", []), ("과거 科擧", ["warning"]), ("과거(科擧)", ["notice"]),
    ("과거（科擧）", ["notice"]), ("科擧 과거(科擧)", ["warning", "notice"]),
    ("과거(科擧", ["warning"]), ("[ROOT.科擧] $科擧$ 과거", []),
])
def test_korean_basis_hanja_qa(value, severities):
    issues = core.qa_entries({"law": value}, source_lang="simp_chinese", target_lang="korean")
    hanja = [issue for issue in issues if issue["type"].startswith("korean_hanja")]
    assert sorted(issue["severity"] for issue in hanja) == sorted(severities)
    assert all(not issue["repairable"] for issue in hanja)


def test_supported_chinese_basis_targets():
    assert core.CHINESE_BASIS_TARGETS == ("japanese", "korean")


def test_unsupported_basis_run_fails_before_writing(tmp_path):
    output = tmp_path / "output"
    with pytest.raises(ValueError):
        core.run_chinese_basis_translation(tmp_path, output, target_lang="french")
    assert not output.exists()


def test_korean_basis_file_qa(tmp_path):
    source = tmp_path / "source" / "simp_chinese" / "law_l_simp_chinese.yml"
    target = tmp_path / "output" / "korean" / "law_l_korean.yml"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text('l_simp_chinese:\n law:0 "科举"\n', encoding="utf-8")
    target.write_text('l_korean:\n law:0 "과거(科擧)"\n', encoding="utf-8")
    result = core.qa_chinese_basis_translation(source.parent.parent, target.parent.parent,
                                              target_lang="korean")
    assert result["checked_files"] == 1
    assert result["missing_outputs"] == 0
    assert result["notices"] == 1


def test_korean_basis_run_preserves_glossary_and_qa_target(tmp_path, monkeypatch):
    source = tmp_path / "source" / "simp_chinese" / "law_l_simp_chinese.yml"
    source.parent.mkdir(parents=True)
    source.write_text('l_simp_chinese:\n law:0 "科举"\n', encoding="utf-8")
    glossary = tmp_path / "glossary.json"
    glossary.write_text('{"科举": "과거"}', encoding="utf-8")
    calls = []

    def translate(url, model, jobs, language, *args, **kwargs):
        calls.append((language, args, kwargs))
        return ["과거(科擧)" for job in jobs]

    monkeypatch.setattr(core, "translate_batch", translate)
    output = tmp_path / "output"
    result = core.run_chinese_basis_translation(source.parent.parent, output, target_lang="korean",
                                                glossary_path=glossary, workers=1)
    assert core.parse_localization_file(output / "korean" / "law_l_korean.yml")[0] == "korean"
    assert result["qa_notices"] == 1
    assert result["qa_errors"] == 0
    assert calls
    cache = core.load_cache(output / "chinese_basis_translate_cache.json")
    key = core.translation_cache_key("Ollama", core.DEFAULT_MODEL, "General", "simp_chinese", "科举",
                                     {"科举": "과거"}, translation_mode="chinese_basis", target_lang="korean")
    assert cache[key] == "과거(科擧)"


def main_method(name, **namespace):
    tree = ast.parse((Path(__file__).parents[1] / "app" / "main.py").read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == name)
    scope = {"core": core, "Path": Path, **namespace}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "<Chinese-basis UI>", "exec"), scope)
    return scope[name]


@pytest.mark.parametrize("language", core.TARGET_LANGUAGES)
def test_chinese_target_selector_accepts_only_supported_languages(language):
    import i18n
    i18n.set_ui_language("english")
    values = {"target": "japanese", "display": i18n.t("lang." + language)}
    messages = []
    variable = lambda key: SimpleNamespace(get=lambda: values[key], set=lambda value: values.update({key: value}))
    widget = SimpleNamespace(config=lambda **kwargs: None)
    app = SimpleNamespace(chinese_target_lang_var=variable("target"), chinese_target_display_var=variable("display"),
                          chinese_intro_frame=widget, chinese_intro_label=widget, chinese_korean_hint=widget,
                          chinese_vocabulary_label=widget)
    select = main_method("_select_chinese_target_language", i18n=i18n, APP_NAME="PLT",
                         messagebox=SimpleNamespace(showinfo=lambda *args: messages.append(args)))
    select(app)
    if language in core.CHINESE_BASIS_TARGETS:
        assert values["target"] == language
        assert not messages
    else:
        assert values["target"] == "japanese"
        assert values["display"] == i18n.t("lang.japanese")
        assert messages[0][1] == i18n.t("u2.supported_targets_reason")


def test_ui_qa_pairs_keep_korean_target(tmp_path):
    source = tmp_path / "source" / "simp_chinese" / "law_l_simp_chinese.yml"
    target = tmp_path / "output" / "korean" / "law_l_korean.yml"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text('l_simp_chinese:\n law:0 "科举"\n', encoding="utf-8")
    target.write_text('l_korean:\n law:0 "과거"\n', encoding="utf-8")
    collect = main_method("_collect_qa_diff_pairs")
    pairs = collect(SimpleNamespace(), source.parent.parent, target.parent.parent,
                    ("simp_chinese",), target_lang="korean")
    assert pairs == [{"source": source, "target": target, "lang": "simp_chinese", "target_language": "korean"}]


def test_japanese_chinese_basis_regression():
    snapshot = json.loads((Path(__file__).parent / "fixtures" / "japanese_chinese_basis_regression.json").read_text(encoding="utf-8"))
    assert core.translation_cache_key("Ollama", "m", "General", "simp_chinese", "科举",
                                      translation_mode="chinese_basis") == snapshot["cache_key"]
    assert core.qa_entries(snapshot["target"], snapshot["source"], "simp_chinese") == snapshot["qa"]
