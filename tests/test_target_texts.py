import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import i18n

EXPECTED_JAPANESE = {'p0.before_repair_choose_which_version': '修復前に本体 / 日本語化Modの重複キーについて優先先の指定が必要です。\n'
                                          '\n'
                                          '{value}\n'
                                          '\n'
                                          '総合診断の『本体/日本語化Mod重複』行を選択し、\n'
                                          '『本体を残す』または『日本語化Modを残す』を設定してください。\n'
                                          '設定後、左側の『設定した内容で修復を実行』を押してください。複数行や一括指定も使用できます。',
 'p0.export_translation_mod_detection_log': '日本語化Mod判定ログ書き出し',
 'p0.generate_translation_mod_detection_log': '日本語化Mod判定ログ生成',
 'p0.reason.no_gap_info': '日本語化Modへ反映する差分情報がありません',
 'p0.translation_mod_detection_log_exported': '日本語化Mod判定ログを書き出しました。\n\n{payload}',
 'u3.choose_pair': '使用する原文と日本語訳の組み合わせを選択してください。',
 'u3.external_complete': '{mod}には日本語化Mod『{external_translation_mod}』があり、完全な日本語化を確認できました。',
 'u3.external_gaps': '{mod}には日本語化Mod『{external_translation_mod}』がありますが、翻訳に欠損があります（{count}件）。 '
                     '{value}。',
 'u3.japanese_yaml': '日本語YAML',
 'u3.no_japanese': '{mod}というModは日本語翻訳がありません。日本語化Modも確認できませんでした。',
 'u3.pair_not_found': '{label}から、原文（英語/簡体字中国語）と対応する日本語YAMLの組み合わせを見つけられませんでした。\n'
                      '翻訳完了後、または日本語化Modが存在する状態で実行してください。',
 'u3.research_detail': 'Mod一覧と別日本語化Modを確認しています'}


@pytest.mark.parametrize("key", EXPECTED_JAPANESE)
def test_target_text_preserves_exact_japanese(key):
    assert i18n.strings("japanese")[key].replace("{target_name}", "日本語") == EXPECTED_JAPANESE[key]


@pytest.mark.parametrize("language", i18n.UI_LANGUAGES)
@pytest.mark.parametrize("key", EXPECTED_JAPANESE)
def test_shared_text_has_target_language_in_every_dictionary(language, key):
    assert "{target_name}" in i18n.strings(language)[key]


def test_shared_text_calls_supply_target_language():
    tree = ast.parse((ROOT / "app" / "main.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and node.func.attr == "t"
             and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value in EXPECTED_JAPANESE]
    assert calls
    assert all(any(field.arg == "target_name" for field in node.keywords) for node in calls)


LEGACY_JAPANESE = {
    "u1.base_game_error": "本体和訳修正例外",
    "u6.base_game_translation_70_gate": "  本体和訳70%判定: {value}",
    "u6.multi_mod_translations_use_a_separate": "  ・総合和訳は2つ以上の元Modで各200件以上、候補有効キー和集合率70%以上を別ゲートとして使用",
    "u9.legacy_base_unavailable": "ゲーム本体キーを取得できないため、本体和訳修正例外の減点なし",
    "u9.relation_union_gate": "総合和訳集合ゲート: 候補有効キー和集合率 {percent:.1f}% → PASS",
}


@pytest.mark.parametrize("key, expected", LEGACY_JAPANESE.items())
def test_legacy_watranslation_wording_stays_exact(key, expected):
    assert i18n.strings("japanese")[key] == expected


@pytest.mark.parametrize("language", i18n.UI_LANGUAGES)
@pytest.mark.parametrize("key", LEGACY_JAPANESE)
def test_legacy_wording_has_separate_target_template(language, key):
    assert "{target_name}" in i18n.strings(language)[key + ".language"]


@pytest.mark.parametrize("key", LEGACY_JAPANESE)
def test_legacy_templates_are_only_used_in_japanese_branches(key):
    trees = [ast.parse((ROOT / "app" / name).read_text())
             for name in ("main.py", "translator_core.py")]

    def literal_key(node):
        if isinstance(node, ast.Call):
            if not node.args:
                return None
            node = node.args[0]
        return node.value if isinstance(node, ast.Constant) else None

    branches = [node for tree in trees for node in ast.walk(tree)
                if isinstance(node, ast.IfExp) and literal_key(node.body) == key]
    assert branches
    assert all(ast.unparse(node.test) == "target_lang == 'japanese'"
               and literal_key(node.orelse) == key + ".language" for node in branches)


def test_pair_dialog_uses_item_language_and_legacy_drop_stays_japanese():
    tree = ast.parse((ROOT / "app" / "main.py").read_text())
    methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    pair_source = ast.unparse(methods["_choose_qa_diff_pairs"])
    assert "pairs[0].get('target_language', core.DEFAULT_TARGET_LANG)" in pair_source
    drop_source = ast.unparse(methods["on_review_drop_paths"])
    assert "i18n.t('u3.japanese_yaml', target_name=i18n.t('lang.japanese'))" in drop_source
