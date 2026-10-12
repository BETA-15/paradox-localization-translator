"""U1 の日本語表示、英語辞書と呼び出しを GUI なしで検証する。"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))

import i18n
from i18n.english.u1_translate import STRINGS as ENGLISH
from i18n.japanese.u1_translate import STRINGS as JAPANESE

ORIGINAL_CASES = [['u1.normal_translation', {}, '通常翻訳'],
 ['u1.intro',
  {'target_name': '日本語'},
  '英語などのParadox localizationを日本語化します。YAMLまたはMod / localizationフォルダを追加すると、直接翻訳キューへ登録します。\n'
  'LLM・バッチ・並列・プリセット・用語集などは［モデル / 接続］タブの共通設定を使用します。'],
 ['u1.target_language', {}, '翻訳先の言語'],
 ['u1.target', {}, '翻訳先'],
 ['u1.target_note', {}, 'キューへ追加するときの翻訳先です。追加済みの項目の翻訳先は変わりません。'],
 ['u1.input_output', {}, '入力 / 出力'],
 ['u1.input_folder', {}, 'YAML / Mod / localizationフォルダ'],
 ['u1.add_yaml', {}, 'YAMLファイルを追加'],
 ['u1.add_folder', {}, 'Mod / localizationフォルダを追加'],
 ['u1.add', {}, '追加'],
 ['u1.add_note', {}, '選択するとそのまま翻訳キューへ追加します'],
 ['u1.output_root', {}, '出力先ルート'],
 ['u1.select', {}, '選択'],
 ['u1.open', {}, '開く'],
 ['u1.shared_models', {}, 'モデル / 接続（共通設定）'],
 ['u1.shared_models_note', {}, 'プロバイダ / URL / モデル / APIキー / バッチ / 並列 / プリセット / 用語集は［モデル / 接続］タブの共通設定を使用します。'],
 ['u1.open_models', {}, 'モデル / 接続を開く'],
 ['u1.auto_qa', {}, '翻訳後にバックアップ・自動QA・エラー修正'],
 ['u1.qa_note', {}, 'QAでは未翻訳原文、キー欠落、ゲーム変数/タグ、誤字脱字、用語集の固定訳を確認します。'],
 ['u1.normal_queue', {}, '通常翻訳キュー'],
 ['u1.remove_selected', {}, '選択削除'],
 ['u1.clear_queue', {}, '全消去'],
 ['u1.change_output', {}, '出力先変更'],
 ['u1.view_cache', {}, 'キャッシュを見る'],
 ['u1.add_cache', {}, 'キャッシュを追加'],
 ['u1.overwrite_selected', {}, '選択項目を一括上書き'],
 ['u1.qa_selected', {}, '選択項目のQA・自動修正を実行'],
 ['u1.create_glossary', {}, '用語集を自動作成'],
 ['u1.open_qa', {}, 'QA / 比較編集へ'],
 ['u1.open_diff', {}, '差分調査へ'],
 ['u1.transfer_chinese', {}, '中国語基準キューへ渡す'],
 ['u1.queue_chinese_missing', {}, '中国語不足分だけをキューへ追加'],
 ['u1.overwrite_note', {}, '上書き: 複数選択に対応。最初に上書き方針を1回だけ選び、完了済み項目をまとめて処理します。成功した項目は「上書き済み」と表示します。'],
 ['u1.item', {}, 'Mod / 項目'],
 ['u1.source_localization', {}, '原文localization'],
 ['u1.output', {}, '出力'],
 ['u1.status', {}, '状態'],
 ['u1.dnd_enabled', {}, 'ドラッグ＆ドロップ有効 — YAML / localizationフォルダ'],
 ['u1.dnd_error', {'error': '例 {value} / テスト'}, 'ドラッグ＆ドロップ初期化失敗: 例 {value} / テスト'],
 ['u1.dnd_init', {}, 'DnD初期化'],
 ['u1.dnd_disabled', {}, 'ドラッグ＆ドロップ無効 — 『追加』ボタンは利用できます'],
 ['u1.start_translation', {}, '翻訳開始'],
 ['u1.pause', {}, '一時停止'],
 ['u1.save_stop', {}, 'セーブして中断'],
 ['u1.open_output', {}, '出力を開く'],
 ['u1.normal_log', {}, '通常翻訳ログ'],
 ['u1.open_errors', {}, 'エラーログを開く'],
 ['u1.collect_diagnostics', {}, '診断ログを収集'],
 ['u1.base_game_error', {}, '本体和訳修正例外'],
 ['u1.select_status_mod', {}, '翻訳状況の一覧からModを1件以上選択してください。'],
 ['u1.queued_after_current', {'count': 3}, '3 Modをキュー末尾へ追加しました。現在の翻訳完了後に続けて処理します。'],
 ['u1.selected_mods_added', {'count': 3}, '選択した 3 Modを通常翻訳キューへ追加しました。'],
 ['u1.localization_skipped', {'count': 3}, '\nlocalizationを確認できずスキップ: 3件'],
 ['u1.no_localization', {}, '選択したModから調査可能なlocalizationフォルダを確認できませんでした。'],
 ['u1.no_remaining_mods', {}, '選択したModを除外すると、通常翻訳キューへ追加できるModは残っていません。'],
 ['u1.remaining_mods_added',
  {'excluded': 3, 'added': 3, 'complete': 3, 'invalid': 3},
  '選択した 3 Modを除外し、3 Modを通常翻訳キューへ追加しました。\n翻訳済みで対象外: 3件\nlocalizationなし: 3件'],
 ['u1.chinese_basis', {}, '中国語基準'],
 ['u1.normal', {}, '通常'],
 ['u1.select_source_queue', {'queue_name': '例 {value} / テスト'}, '例 {value} / テスト翻訳キューから項目を選択してください。'],
 ['u1.unnamed_item', {}, '項目'],
 ['u1.localization_unknown', {'mod': '例 {value} / テスト'}, '例 {value} / テスト: localizationを特定できません'],
 ['u1.no_source_gaps',
  {'mod': '例 {value} / テスト', 'source_lang': '例 {value} / テスト'},
  '例 {value} / テスト: 例 {value} / テスト固有の不足翻訳なし'],
 ['u1.missing_source_failed', {'mod': '例 {value} / テスト'}, '例 {value} / テスト: 不足原文を作成できません'],
 ['u1.queue_add_failed', {}, 'キュー追加できませんでした'],
 ['u1.normal_translation', {}, '通常翻訳'],
 ['u1.chinese_translation', {}, '中国語基準翻訳'],
 ['u1.no_queue_items_added', {'skipped': 3}, 'キューへ追加できる項目がありませんでした。\nスキップ: 3件'],
 ['u1.no_japanese_yaml', {}, '不足分の完成済み日本語YAMLが見つかりません'],
 ['u1.no_missing_results', {}, '不足分の翻訳結果が見つかりません'],
 ['u1.overwrite_missing', {}, '不足翻訳の上書き'],
 ['u1.confirm_missing_overwrite',
  {'count': 3, 'target': '例 {value} / テスト'},
  '不足していた翻訳 3件だけを既存日本語本文へ追加します。\n\n対象: 例 {value} / テスト\n\n既存の他キーは置き換えません。続行しますか？'],
 ['u1.before_missing_overwrite', {}, '不足分上書き直前の原文（既存localization全体）'],
 ['u1.validation_unknown', {}, '上書き後確認: 判定対象を特定できません'],
 ['u1.validation_complete', {}, '上書き後確認: 欠損なし'],
 ['u1.text_has_gaps', {'reason': '例 {value} / テスト'}, '⚠ 本文自体に欠落があります。\n例 {value} / テスト'],
 ['u1.validation_complete', {}, '上書き後確認: 欠損なし'],
 ['u1.translation_gaps', {}, '翻訳不足があります'],
 ['u1.text_has_gaps', {'reason': '例 {value} / テスト'}, '⚠ 本文自体に欠落があります。\n例 {value} / テスト'],
 ['u1.missing_overwrite_done',
  {'updated': 3, 'added': 3, 'files': 3, 'validation': '例 {value} / テスト'},
  '不足していた翻訳だけを反映しました。\n\n既存キー更新: 3件\n新規キー追加: 3件\nバックアップ: 3ファイル\n\n例 {value} / テスト'],
 ['u1.missing_overwrite_summary',
  {'updated': 3, 'added': 3, 'validation': '例 {value} / テスト'},
  '既存キー更新 3 / 新規キー追加 3 / 例 {value} / テスト'],
 ['u1.overwrite_error', {}, '不足翻訳上書き'],
 ['u1.missing_overwrite_failed', {'error': '例 {value} / テスト'}, '不足翻訳の上書きに失敗しました。\n例 {value} / テスト'],
 ['u1.choose_output_root', {}, '通常翻訳の出力先ルートを選択'],
 ['u1.choose_mod_folder', {}, '翻訳するMod/localizationフォルダを選択'],
 ['u1.folder_added', {'name': '例 {value} / テスト'}, 'キューへ追加しました: 例 {value} / テスト'],
 ['u1.choose_yaml', {}, '翻訳するYAMLを複数選択'],
 ['u1.yaml_added', {'count': 3}, 'YAMLを 3 件キューへ追加しました。'],
 ['u1.dnd_parse', {}, 'DnDフォルダ解析'],
 ['u1.dnd_added', {'count': 3}, 'ドラッグ＆ドロップで3件追加しました'],
 ['u1.unnamed_item', {}, '項目'],
 ['u1.select_queue_item', {}, '先にキュー一覧から対象の翻訳を選択してください。'],
 ['u1.output_help',
  {},
  '出力先を変更する項目を、キュー一覧から先に選択してください。\n'
  '\n'
  '通常は変更不要です。既定では『Paradox Localization Translator/翻訳結果』へ出力されます。全体の保存場所は［設定］タブから変更できます。'],
 ['u1.selected_output', {}, '選択項目の出力先'],
 ['u1.empty_queue', {}, '翻訳キューにフォルダまたはファイルを追加してください。'],
 ['u1.select_translation_items', {}, '翻訳する項目を選択してください。'],
 ['u1.normal_method', {}, '通常翻訳 — 翻訳方法'],
 ['u1.select_translation_items_period', {}, '翻訳する項目を選択してください.'],
 ['u1.unsupported_language', {}, 'ゲームが読めない言語'],
 ['u1.normal_translation', {}, '通常翻訳'],
 ['u1.translation', {}, '翻訳'],
 ['u1.diff_only', {}, '差分だけ翻訳'],
 ['u1.full_translation', {}, '一からすべて翻訳'],
 ['u1.translation_started', {'count': 3, 'mode': '例 {value} / テスト'}, '翻訳開始: 3項目 / 例 {value} / テスト'],
 ['u1.model_unspecified', {}, '(model未指定)'],
 ['u1.connection',
  {'provider': '例 {value} / テスト', 'model': '例 {value} / テスト', 'batch': 3, 'workers': 3},
  '接続: 例 {value} / テスト / 例 {value} / テスト / batch 3 / workers 3'],
 ['u1.pause', {}, '一時停止'],
 ['u1.queue_item_lost', {}, '通常翻訳キュー項目が処理中に失われました'],
 ['u1.glossary_file', {'name': '例 {value} / テスト'}, '用語集: 例 {value} / テスト'],
 ['u1.no_glossary', {}, 'この言語の用語集はありません'],
 ['u1.translation_target',
  {'target_name': '日本語', 'glossary': '例 {value} / テスト'},
  '翻訳先: 日本語（例 {value} / テスト）'],
 ['u1.processing_result',
  {'mod': '例 {value} / テスト', 'processed': 3, 'jobs': 3, 'failed': 3, 'skipped': 3, 'warnings': 3},
  '処理結果: 例 {value} / テスト / ファイル 3 / LLMジョブ 3 / 失敗 3 / スキップ 3 / 警告 3'],
 ['u1.spaces_removed', {'count': 3}, '半角スペース除去: 3個'],
 ['u1.auto_qa_result',
  {'errors': 3, 'warnings': 3, 'notices': 3, 'repaired': 3},
  '自動QA・修正: error 3 / warning 3 / notice 3 / 修正 3'],
 ['u1.qa_report', {'path': '例 {value} / テスト'}, 'QA修正ログ: 例 {value} / テスト'],
 ['u1.qa_backup', {'path': '例 {value} / テスト'}, 'QA修復前バックアップ: 例 {value} / テスト'],
 ['u1.encoding_repaired', {'mod': '例 {value} / テスト', 'count': 3}, '自動修復: 例 {value} / テスト / 文字コード 3ファイル'],
 ['u1.error_report', {'path': '例 {value} / テスト'}, 'エラー記録: 例 {value} / テスト'],
 ['u1.queue_item_error', {'mod': '例 {value} / テスト'}, '翻訳キュー項目: 例 {value} / テスト'],
 ['u1.defer_retry', {}, '後段の自動再試行へ延期'],
 ['u1.retry_warning',
  {'mod': '例 {value} / テスト', 'error_type': '例 {value} / テスト', 'error': '例 {value} / テスト'},
  '[警告] 例 {value} / テスト を後で再試行します: 例 {value} / テスト: 例 {value} / テスト'],
 ['u1.retry_started', {'count': 3}, '未解決 3項目の自動再試行を開始します。'],
 ['u1.queue_retry_error', {'mod': '例 {value} / テスト'}, '翻訳キュー再試行: 例 {value} / テスト'],
 ['u1.record_unresolved', {}, '未解決として記録'],
 ['u1.unresolved',
  {'mod': '例 {value} / テスト', 'error_type': '例 {value} / テスト', 'error': '例 {value} / テスト'},
  '[未解決] 例 {value} / テスト: 例 {value} / テスト: 例 {value} / テスト'],
 ['u1.unattended_report', {'path': '例 {value} / テスト'}, '夜間処理レポート: 例 {value} / テスト'],
 ['u1.report_save', {}, '夜間処理レポート保存'],
 ['u1.fatal_translation', {}, '翻訳処理 fatal'],
 ['u1.pause', {}, '一時停止'],
 ['u1.resumed', {}, '再開しました'],
 ['u1.resume', {}, '再開'],
 ['u1.paused', {}, '一時停止中（現在のLLM応答完了後に停止）'],
 ['u1.workspace_save', {}, 'ワークスペース状態保存'],
 ['u1.japanese_key_alignment', {'game': '例 {value} / テスト'}, '例 {value} / テスト 本体の原文と日本語キーを照合中…'],
 ['u1.common_names', {}, '共通名のみ'],
 ['u1.all_names', {}, 'すべて'],
 ['u1.base_glossary_started', {'game': '例 {value} / テスト'}, '例 {value} / テスト 本体と照合する用語取り込みを開始しました…'],
 ['u1.language_warning', {'warnings': '警告1\n\n警告2'}, '警告1\n\n警告2\n\nそれでも翻訳しますか？'],
 ['u1.dnd_rejected_items', {'items': 'one.txt\ntwo.png'}, 'YAMLファイルまたはフォルダ以外は追加しませんでした。\n\none.txt\ntwo.png'],
 ['u1.transfer_missing',
  {'target_queue': '通常翻訳', 'added': 3, 'skipped': 2},
  '不足している翻訳だけを通常翻訳キューへ追加しました。\n追加: 3件 / スキップ: 2件'],
 ['u1.transfer_selected',
  {'target_queue': '中国語基準翻訳', 'added': 3, 'skipped': 2},
  '選択項目を中国語基準翻訳キューへ追加しました。\n追加: 3件 / スキップ: 2件'],
 ['u1.queue_retry', {'mod': 'Example Mod', 'pos': 2, 'total': 3}, '再試行: Example Mod (2/3)'],
 ['u1.queue_start', {'mod': 'Example Mod', 'pos': 2, 'total': 3}, '開始: Example Mod (2/3)']]


ORIGINAL_CASES += [
    ['u1.no_target_yaml', {'target_name': '韓国語'}, '翻訳済み韓国語 YAMLがありません。'],
    ['u1.confirm_target_missing_overwrite', {'count': 3, 'target': 'Fixture', 'target_name': '韓国語'},
     '不足していた翻訳 3件だけを既存韓国語本文へ追加します。\n\n対象: Fixture\n\n既存の値は置き換えません。続行しますか？'],
]


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.get_ui_language()
    yield
    i18n.set_ui_language(previous)


ORIGINAL_CASES.append([
    "u1.base_game_error.language", {"target_name": "日本語"}, "本体日本語訳修正例外"
])


@pytest.mark.parametrize("key,fields,expected", ORIGINAL_CASES)
def test_original_japanese_display(key, fields, expected):
    i18n.set_ui_language("japanese")
    assert i18n.t(key, **fields) == expected


def test_every_key_has_an_original_japanese_case():
    assert JAPANESE
    assert set(JAPANESE) == {key for key, _fields, _expected in ORIGINAL_CASES}


@pytest.mark.parametrize("key,fields,expected", ORIGINAL_CASES)
def test_every_key_uses_the_english_dictionary(key, fields, expected):
    i18n.set_ui_language("english")
    assert key in ENGLISH
    assert i18n.lookup(key) == ENGLISH[key]
    assert i18n.t(key, **fields) == ENGLISH[key].format_map(fields)


def test_dictionary_fields_match_call_sites():
    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"
                and node.func.attr == "t" and node.args and isinstance(node.args[0], ast.Constant)):
            continue
        key = node.args[0].value
        if not isinstance(key, str) or not key.startswith("u1."):
            continue
        assert key in JAPANESE
        used.add(key)
        assert {field.arg for field in node.keywords} == set(re.findall(r"\{(\w+)\}", JAPANESE[key]))
    assert used == set(JAPANESE) - {"u1.japanese_key_alignment"}
    assert any(isinstance(node, ast.Constant) and node.value == "u4.target_key_alignment"
               for node in ast.walk(tree))


@pytest.mark.parametrize("ui_language", ["japanese", "english"])
@pytest.mark.parametrize("target_language", i18n.UI_LANGUAGES)
def test_intro_uses_the_selected_target_language(ui_language, target_language):
    tree = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))
    intro = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.Call) and node.args
                 and isinstance(node.args[0], ast.Constant) and node.args[0].value == "u1.intro")
    i18n.set_ui_language(ui_language)
    result = eval(compile(ast.Expression(intro), "<intro>", "eval"),
                  {"i18n": i18n, "self": SimpleNamespace(),
                   "_current_target_lang": lambda _self: target_language})
    target_name = i18n.t("lang." + target_language)
    assert target_name in result
    assert result == i18n.t("u1.intro", target_name=target_name)


def test_japanese_only_operations_keep_their_language():
    for ui_language in i18n.UI_LANGUAGES:
        i18n.set_ui_language(ui_language)
        assert "Japanese" in i18n.t("u1.no_japanese_yaml") or "日本語" in i18n.t("u1.no_japanese_yaml")
        assert "target_name" not in JAPANESE["u1.no_japanese_yaml"]
        assert "target_name" not in JAPANESE["u1.confirm_missing_overwrite"]
        assert "target_name" not in JAPANESE["u1.japanese_key_alignment"]


def test_internal_values_and_comparisons_are_unchanged():
    source = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = {node.name: node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    completed = ast.get_source_segment(source, methods["_queue_item_is_completed"])
    assert 'status.startswith("完了") or status == "上書き済み"' in completed
    reset = ast.get_source_segment(source, methods["_reset_item_for_full_translation"])
    assert '.startswith("差分")' in reset
    merge = ast.get_source_segment(source, methods["_merge_missing_only_output"])
    assert 'target_root, "不足分上書き", category="上書き"' in merge
    assert 'core.remap_rel_dir(Path(), target_lang)' in merge
    assert 'core.rename_for_target(Path("paradox_localization_translator_missing_l_japanese.yml"), target_lang, "japanese")' in merge
    transfer = ast.get_source_segment(source, methods["transfer_selected_queue_to_opposite"])
    assert transfer.count('"（不足分）"') == 2


def test_u1_has_only_documented_internal_japanese_literals():
    sys.path.insert(0, str(ROOT / "tools"))
    import i18n_scan

    owners = {
        "_annotate_translation_index_with_base_game_keys", "_build_translate_tab", "_extract_drop_paths",
        "_merge_missing_only_output", "_queue_item_is_completed", "_queue_worker", "_refresh_queue_tree",
        "_reset_item_for_full_translation", "_save_workspace_state", "_selected_queue_item",
        "_start_japanese_base_fallback", "_start_normal_selected", "add_files", "add_folder", "change_output",
        "on_drop_paths", "pick_normal_output", "queue_all_except_selected_mods", "queue_selected_mod_from_status",
        "start_queue", "toggle_pause", "transfer_selected_queue_to_opposite",
    }
    remaining = [(row["owner"], row["text"])
                 for row in i18n_scan.japanese_strings(ROOT / "app" / "main.py")
                 if row["owner"].startswith("App.") and row["owner"].split(".")[1] in owners]
    assert sorted(remaining) == sorted([
        ("App._annotate_translation_index_with_base_game_keys", "ゲーム未特定"),
        ("App.queue_all_except_selected_mods", "翻訳あり"),
        ("App.queue_all_except_selected_mods", "別Modで完全翻訳"),
        ("App.transfer_selected_queue_to_opposite", "（不足分）"),
        ("App.transfer_selected_queue_to_opposite", "（不足分）"),
        ("App._merge_missing_only_output", "不足分上書き"),
        ("App._merge_missing_only_output", "上書き"),
        ("App._queue_item_is_completed", "完了"),
        ("App._queue_item_is_completed", "上書き済み"),
        ("App._reset_item_for_full_translation", "差分"),
        ("App._queue_worker.run_item", "QA自動修復"),
    ])

