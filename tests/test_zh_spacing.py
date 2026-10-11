import pytest

from app import translator_core as core


@pytest.mark.parametrize("text", [
    "克 III", "径 Mk", "三号 G型", "三菱 九七重爆",
    "丘吉尔黑太子 自行防空炮", "温斯顿·丘吉尔", "温斯顿 丘吉尔",
    "ブリストル ブレニム", "债务 危机", "[ROOT.GetName] 的 军队",
    "$NAME$ 将军", "金 £gold£", "§Y 债务 §!", "£trigger_no 军队",
    "你好, 世界.", "你好\t，\t世界", "你好　，　世界", " 你好 ",
    "#italic 《战争论》#!", "#bold “你好”#!",
    "部署： ", "， ", "最后一站。 ", " —补员：", "机会。” ",
    "‘伟大’ 和", "“伟大” 和", "「伟大」 和", "『伟大』 和",
    "你好。\n （军队）", "你好。 \n军队", "你好。\r\n （军队）",
    r"你好。\n （军队）", r"你好。 \n军队",
    "紧张上限： §G", "§!、 §Y", "[ENG.GetName] 、",
    "： #bold", "#! ，", "： £gold£", "£gold£ ，", "： $NAME$",
    "$NAME$ ，", "： [ROOT.GetName]", "§Y ，", "， §!",
    "ABC ， DEF", "123 ， 456", "かな ， カナ",
    "V号坦克 “黑豹”", "飞机 （例如", "他的 《四书章句集注》",
    "行径 — 他们", "行径 —— 他们", "行径 … 他们", "行径 …… 他们",
])
def test_chinese_preserves_non_punctuation_spaces(text):
    assert core.normalize_cjk_spacing(text, "simp_chinese") == (text, 0)


@pytest.mark.parametrize("punctuation", list("，。、；：？！「」『』（）《》〈〉【】…—〔〕［］｛｝“”‘’"))
def test_chinese_punctuation_spaces(punctuation):
    original = f"甲  {punctuation}   乙"
    assert core.normalize_cjk_spacing(original, "simp_chinese") == (original, 0)


@pytest.mark.parametrize("punctuation", list("，。、；：？！）》」』〉】"))
def test_chinese_single_space_before_sentence_punctuation_and_closing_brackets(punctuation):
    original = f"甲 {punctuation} 乙"
    expected = f"甲{punctuation} 乙"
    assert core.normalize_cjk_spacing(original, "simp_chinese") == (expected, 1)
    assert core.normalize_cjk_spacing(expected, "simp_chinese") == (expected, 0)


@pytest.mark.parametrize("punctuation", list("（《「『〈【"))
def test_chinese_single_space_after_opening_brackets(punctuation):
    original = f"甲 {punctuation} 乙"
    expected = f"甲 {punctuation}乙"
    assert core.normalize_cjk_spacing(original, "simp_chinese") == (expected, 1)
    assert core.normalize_cjk_spacing(expected, "simp_chinese") == (expected, 0)


@pytest.mark.parametrize("punctuation", list("“”‘’—…〔〕［］｛｝"))
def test_chinese_preserves_single_spaces_around_other_symbols(punctuation):
    original = f"甲 {punctuation} 乙"
    assert core.normalize_cjk_spacing(original, "simp_chinese") == (original, 0)


@pytest.mark.parametrize("original,expected,removed", [
    ("你好 ，世界 。", "你好，世界。", 2),
    (" ， 你好 。 ", " ， 你好。 ", 1),
    ("甲 ， ！ 乙", "甲， ！ 乙", 1),
    ("[ROOT.GetName] ， 军队", "[ROOT.GetName] ， 军队", 0),
    ("§Y ， 军队 §!", "§Y ， 军队 §!", 0),
    ("£trigger_no ， 军队", "£trigger_no ， 军队", 0),
    ("㐀 ， 𠀀", "㐀， 𠀀", 1),
])
def test_chinese_punctuation_at_boundaries(original, expected, removed):
    assert core.normalize_cjk_spacing(original, "simp_chinese") == (expected, removed)


@pytest.mark.parametrize("token", [
    "[GetName('你好 ， 世界')]", "$你好 ， 世界$", "£gold£",
    "#bold;size=20 你好 ， 世界#!",
])
def test_chinese_does_not_change_protected_token_contents(token):
    assert core.normalize_cjk_spacing(token + " 的 军队", "simp_chinese") == (
        token + " 的 军队", 0)


def test_language_rule_metadata_preserves_existing_flags():
    assert core.TARGET_LANGUAGES["japanese"]["cjk_space_rule"] == "japanese"
    assert core.TARGET_LANGUAGES["simp_chinese"]["cjk_space_rule"] == "zh_punctuation"
    assert {language for language, info in core.TARGET_LANGUAGES.items()
            if info["remove_cjk_spaces"]} == {"japanese", "simp_chinese"}


def test_chinese_qa_notice_only_for_han_punctuation_spacing():
    assert not any(issue["rule_id"] == "QA-SPACE-001" for issue in
                   core.qa_entries({"description": "债务 危机"}, target_lang="simp_chinese"))
    assert any(issue["rule_id"] == "QA-SPACE-001" for issue in
               core.qa_entries({"description": "债务 ， 危机"}, target_lang="simp_chinese"))
