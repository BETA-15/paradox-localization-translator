"""U2 Chinese-based translation display regressions; no tkinter application is started."""
import ast
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import pytest
import i18n
from i18n.japanese.u2_chinese import STRINGS as JAPANESE
from i18n.english.u2_chinese import STRINGS as ENGLISH


ORIGINALS = [
    ('u2.intro_title', {'target_name': '日本語'}, '中国語の漢字を基準に日本語化'),
    ('u2.intro_description', {'target_name': '日本語'}, '簡体字中国語のlocalizationを直接読み込み、中国語原文の漢字語彙・制度名・官職名・歴史用語を第一基準として日本語化します。\n英語ファイルは不要です。簡体字は日本語で一般的な字体へ整え、文章は自然な日本語にします。'),
    ('u2.input_output', {}, '入力 / 出力'),
    ('u2.chinese_input', {}, '中国語YAML / フォルダ'),
    ('u2.add_yaml', {}, '中国語YAMLファイルを追加'),
    ('u2.add_localization', {}, '中国語localizationフォルダを追加'),
    ('u2.add', {}, '追加'),
    ('u2.selection_hint', {}, '選択するとそのまま中国語基準翻訳キューへ追加します'),
    ('u2.output_root', {}, '出力先ルート'),
    ('u2.select', {}, '選択'),
    ('u2.open', {}, '開く'),
    ('u2.shared_settings', {}, 'モデル / 接続（共通設定）'),
    ('u2.shared_settings_hint', {}, '中国語基準翻訳でも、プロバイダ / URL / モデル / APIキー / バッチ / 並列 / プリセット / 用語集は［モデル / 接続］タブの共通設定を使用します。'),
    ('u2.open_settings', {}, 'モデル / 接続を開く'),
    ('u2.vocabulary_hint', {}, '中国語の漢字語彙を優先し、不要な英語風カタカナ化を避けます。'),
    ('u2.autoqa', {}, '翻訳後にバックアップ・中国語翻訳語自動QA・エラー修正'),
    ('u2.autoqa_hint', {}, 'チェック時は未翻訳、キー欠落、ゲーム変数/タグを自動QA・修正します。固有名詞候補などの注意は修正しません。'),
    ('u2.queue_title', {}, '中国語基準翻訳キュー'),
    ('u2.remove_selected', {}, '選択削除'),
    ('u2.clear_all', {}, '全消去'),
    ('u2.change_output', {}, '出力先変更'),
    ('u2.view_cache', {}, 'キャッシュを見る'),
    ('u2.add_cache', {}, 'キャッシュを追加'),
    ('u2.overwrite_selected', {}, '選択項目を一括上書き'),
    ('u2.qa_selected', {}, '選択項目のQA・自動修正を実行'),
    ('u2.auto_glossary', {}, '用語集を自動作成'),
    ('u2.send_to_qa', {}, 'QA / 比較編集へ'),
    ('u2.send_to_diff', {}, '差分調査へ'),
    ('u2.send_to_normal', {}, '通常翻訳キューへ渡す'),
    ('u2.queue_missing_english', {}, '英語不足分だけをキューへ追加'),
    ('u2.overwrite_hint', {}, '上書き: 複数選択に対応。最初に上書き方針を1回だけ選び、完了済み項目をまとめて処理します。成功した項目は「上書き済み」と表示します。'),
    ('u2.mod_item', {}, 'Mod / 項目'),
    ('u2.chinese_localization', {}, '中国語localization'),
    ('u2.output', {}, '出力'),
    ('u2.status', {}, '状態'),
    ('u2.start', {}, '翻訳開始'),
    ('u2.pause', {}, '一時停止'),
    ('u2.save_stop', {}, 'セーブして中断'),
    ('u2.open_output', {}, '出力を開く'),
    ('u2.log_title', {}, '中国語基準翻訳ログ'),
    ('u2.open_error_log', {}, 'エラーログを開く'),
    ('u2.collect_logs', {}, '診断ログを収集'),
    ('u2.path_missing', {}, '選択したパスが存在しません。'),
    ('u2.folder_no_yaml', {}, 'フォルダ内に l_simp_chinese のYAMLが見つかりませんでした。'),
    ('u2.queue_locked', {}, '中国語基準キューは処理中のため変更できません。'),
    ('u2.already_queued', {}, 'すでに中国語基準キューに追加されています。'),
    ('u2.select_queue_item', {}, '中国語基準翻訳キューから項目を1つ選択してください。'),
    ('u2.change_output_title', {}, '選択した中国語基準翻訳の出力先を変更'),
    ('u2.item', {}, '項目'),
    ('u2.output_unset', {}, 'この項目の出力先が設定されていません。'),
    ('u2.cache_missing', {}, 'この項目にはまだキャッシュがありません。翻訳を開始すると作成されます。'),
    ('u2.import_cache_title', {}, '中国語基準翻訳キャッシュを追加'),
    ('u2.import_cache_error_context', {}, '中国語基準キャッシュ追加'),
    ('u2.select_overwrite', {}, '中国語基準翻訳キューから上書きする項目を選択してください。'),
    ('u2.select_qa', {}, 'QA・自動修正する中国語基準翻訳項目を選択してください。'),
    ('u2.pick_yaml_title', {}, '簡体字中国語YAMLを追加'),
    ('u2.pick_folder_title', {}, '簡体字中国語localizationを含むフォルダを追加'),
    ('u2.pick_output_title', {}, '中国語基準翻訳の出力先'),
    ('u2.drop_no_yaml', {}, 'ドロップした項目に l_simp_chinese のYAMLが見つかりませんでした。'),
    ('u2.select_translation', {}, '翻訳する項目を選択してください。'),
    ('u2.translation_mode', {}, '中国語基準翻訳 — 翻訳方法'),
    ('u2.preparing', {}, 'キュー翻訳準備中…'),
    ('u2.queue_item_lost', {}, '中国語基準キュー項目が処理中に失われました'),
    ('u2.resumed', {}, '再開しました'),
    ('u2.resume', {}, '再開'),
    ('u2.pausing', {}, '一時停止中 — 現在のLLM応答完了後に停止します'),
    ('u2.stopping', {}, 'セーブして中断中 — 現在のLLM応答完了を待っています'),
    ('u2.select_status_mods', {}, '翻訳状況の一覧からModを選択してください。'),
    ('u2.selected_no_chinese', {}, '選択したModには簡体字中国語（l_simp_chinese）が見つかりませんでした。'),
    ('u2.yaml_read_error', {'error': 'read error'}, 'YAMLを読み込めません: read error'),
    ('u2.wrong_language', {'language': 'english'}, 'このファイルは l_simp_chinese ではありません（検出: english）。'),
    ('u2.yaml_confirmed', {'filename': 'example.yml'}, '簡体字中国語YAMLを確認しました: example.yml'),
    ('u2.yaml_count', {'count': 3}, '簡体字中国語YAMLを 3 ファイル検出しました。'),
    ('u2.output_changed', {'mod_name': 'Example Mod', 'path': '/output'}, '出力先変更: Example Mod → /output'),
    ('u2.cache_imported', {'mod_name': 'Example Mod', 'filename': 'cache.json'}, 'キャッシュ追加: Example Mod ← cache.json'),
    ('u2.cache_import_failed', {'error': 'read error'}, 'キャッシュを追加できませんでした。\nread error'),
    ('u2.spaces_removed', {'count': 3}, '半角スペース除去: 3個'),
    ('u2.status_mods_added', {'count': 3}, '翻訳状況から中国語localizationを持つ 3 Modをキューへ追加しました。'),
    ('u2.mods_excluded_summary', {'selected_count': 2, 'added_count': 3, 'no_chinese_count': 4, 'invalid_count': 5}, '選択した 2 Modを除外し、中国語localizationがある 3 Modを中国語基準キューへ追加しました。\n中国語なし: 4件\nlocalizationなし: 5件'),
    ('u2.skipped_mods', {'mods': 'Mod A、Mod B'}, '中国語なしのため除外: Mod A、Mod B'),
    ('u2.skipped_mods_more', {'mods': 'Mod A、Mod B', 'count': 2}, '中国語なしのため除外: Mod A、Mod B ほか2件'),
]


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.get_ui_language()
    yield
    i18n.set_ui_language(previous)


@pytest.mark.parametrize("key,fields,expected", ORIGINALS)
def test_original_japanese_display(key, fields, expected):
    i18n.set_ui_language("japanese")
    assert i18n.t(key, **fields) == expected


def test_all_keys_have_english_and_matching_fields():
    i18n.set_ui_language("english")
    additions = {"u2.target_language", "u2.supported_targets_reason", "u2.korean_basis_hint", "u2.korean_intro_description",
                 "u2.mixed_targets_auto_glossary"}
    assert set(JAPANESE) == set(ENGLISH) == {key for key, _, _ in ORIGINALS} | additions
    for key, fields, _ in ORIGINALS:
        assert i18n.t(key, **fields) == ENGLISH[key].format(**fields)
        japanese_fields = {name for _, name, _, _ in Formatter().parse(JAPANESE[key]) if name}
        english_fields = {name for _, name, _, _ in Formatter().parse(ENGLISH[key]) if name}
        assert japanese_fields == english_fields == set(fields)


def test_main_uses_all_u2_keys():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app/main.py").read_text(encoding="utf-8"))
    used = {node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"
            and node.func.attr == "t" and node.args and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str) and node.args[0].value.startswith("u2.")}
    assert used == set(JAPANESE)


@pytest.mark.parametrize("language", i18n.UI_LANGUAGES)
def test_target_names_use_language_dictionary(language):
    i18n.set_ui_language("english")
    target_name = i18n.t("lang." + language)
    assert target_name in i18n.t("u2.intro_title", target_name=target_name)
    assert target_name in i18n.t("u2.intro_description", target_name=target_name)


FORMATTED_EXPRESSIONS = [
    ("u2.yaml_read_error", "f\"YAMLを読み込めません: {exc}\""),
    ("u2.wrong_language", "f\"このファイルは l_simp_chinese ではありません（検出: {lang}）。\""),
    ("u2.yaml_confirmed", "f\"簡体字中国語YAMLを確認しました: {path.name}\""),
    ("u2.yaml_count", "f\"簡体字中国語YAMLを {count} ファイル検出しました。\""),
    ("u2.output_changed", "f\"出力先変更: {item.get(\u0027mod_name\u0027,\u0027項目\u0027)} → {raw}\""),
    ("u2.cache_imported", "f\"キャッシュ追加: {item.get(\u0027mod_name\u0027,\u0027項目\u0027)} ← {src.name}\""),
    ("u2.cache_import_failed", "f\"キャッシュを追加できませんでした。\\n{exc}\""),
    ("u2.spaces_removed", "f\"半角スペース除去: {result.get(\u0027spaces_removed\u0027,0)}個\""),
    ("u2.status_mods_added", "f\"翻訳状況から中国語localizationを持つ {added} Modをキューへ追加しました。\""),
    ("u2.mods_excluded_summary", "f\"選択した {len(selected)} Modを除外し、中国語localizationがある {added} Modを中国語基準キューへ追加しました。\\n中国語なし: {no_chinese}件\\nlocalizationなし: {invalid}件\""),
]


@pytest.mark.parametrize("key,original", FORMATTED_EXPRESSIONS)
@pytest.mark.parametrize("missing_values", [False, True])
def test_actual_template_arguments_match_original_fstrings(key, original, missing_values):
    i18n.set_ui_language("japanese")
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app/main.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"
             and node.func.attr == "t" and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value == key]
    assert calls
    values = dict(i18n=i18n, exc=ValueError("read error"), lang="english",
                  path=Path("example.yml"), src=Path("cache.json"), raw="/output",
                  count=3, added=3, selected=["A", "B"], no_chinese=4, invalid=5,
                  item={} if missing_values else {"mod_name": "Example Mod"},
                  result={} if missing_values else {"spaces_removed": 3})
    expected = eval(original, values)
    for call in calls:
        actual = eval(compile(ast.Expression(call), "<u2 display>", "eval"), values)
        assert actual == expected


@pytest.mark.parametrize("count", [1, 10, 11, 12])
def test_skipped_mods_full_message_matches_original(count):
    i18n.set_ui_language("japanese")
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app/main.py").read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "queue_selected_mods_to_chinese_basis")
    call = next(node for node in ast.walk(method) if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute) and node.func.attr == "_append_chinese_log")
    skipped = [f"Mod {index}" for index in range(count)]
    expected = "中国語なしのため除外: " + "、".join(skipped[:10]) + (f" ほか{len(skipped)-10}件" if len(skipped)>10 else "")
    assert eval(compile(ast.Expression(call.args[0]), "<u2 skipped mods>", "eval"),
                dict(i18n=i18n, skipped=skipped)) == expected


def test_intro_calls_use_the_actual_translation_target():
    i18n.set_ui_language("japanese")
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app/main.py").read_text(encoding="utf-8"))
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
             and node.func.value.id == "i18n" and node.func.attr == "t"
             and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value in ("u2.intro_title", "u2.intro_description")]
    assert len(calls) == 2
    for call in calls:
        original = next(expected for key, _, expected in ORIGINALS if key == call.args[0].value)
        assert eval(compile(ast.Expression(call), "<u2 intro>", "eval"),
                    dict(i18n=i18n, core=SimpleNamespace(DEFAULT_TARGET_LANG="japanese"))) == original
