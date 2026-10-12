"""U3 display snapshots without constructing App or a Tk window."""
import ast
import re
from pathlib import Path

import pytest
import i18n
from app.i18n.japanese.u3_review import STRINGS as JAPANESE
from app.i18n.english.u3_review import STRINGS as ENGLISH


ORIGINAL_CASES = [
    ('u3.error', {}, 'エラー'),
    ('u3.choose_pair', {}, '使用する原文と日本語訳の組み合わせを選択してください。'),
    ('u3.source_language', {}, '原文言語'),
    ('u3.source_yaml', {}, '原文YAML'),
    ('u3.japanese_yaml', {}, '日本語YAML'),
    ('u3.english', {}, '英語'),
    ('u3.simplified_chinese', {}, '簡体字中国語'),
    ('u3.all_english', {'english_count': 'sample'}, '英語をすべて (sample)'),
    ('u3.all_chinese', {'chinese_count': 'sample'}, '簡体字中国語をすべて (sample)'),
    ('u3.selected_files', {}, '選択したファイル'),
    ('u3.cancel', {}, 'キャンセル'),
    ('u3.normal_translation', {}, '通常翻訳'),
    ('u3.select_status_mod', {}, '翻訳状況一覧からModを1件選択してください。'),
    ('u3.select_one_status_mod', {}, 'QA / 差分調査へ送る場合は、翻訳状況一覧からModを1件だけ選択してください。'),
    ('u3.translation_status', {}, '翻訳状況'),
    ('u3.pair_not_found', {'label': 'sample'}, 'sampleから、原文（英語/簡体字中国語）と対応する日本語YAMLの組み合わせを見つけられませんでした。\n翻訳完了後、または日本語化Modが存在する状態で実行してください。'),
    ('u3.choose_pair_from', {'label': 'sample'}, 'sampleからQA / 差分用ファイルを選択'),
    ('u3.source_translation', {}, '原文 / 訳文'),
    ('u3.source', {}, '原文'),
    ('u3.choose', {}, '選択'),
    ('u3.translation', {}, '訳文'),
    ('u3.choose', {}, '選択'),
    ('u3.load_comparison', {}, '比較を読み込む'),
    ('u3.drop_pair', {'target_name': '日本語'}, '英語または簡体字中国語の原文YAMLと日本語YAMLをここへドラッグ＆ドロップできます'),
    ('u3.dnd_unavailable', {}, 'ドラッグ＆ドロップはこのビルドでは利用できません'),
    ('u3.rerun_qa', {}, 'QA再実行'),
    ('u3.backup_auto_repair', {}, 'バックアップして全エラーを自動修復'),
    ('u3.export_qa_log', {}, 'QAログを書き出す'),
    ('u3.issues_only', {}, '問題・注意だけ表示'),
    ('u3.all_keys', {}, '全キー表示'),
    ('u3.unify_terms', {}, '用語不一致を一括統一'),
    ('u3.create_glossary', {}, '用語集を自動作成'),
    ('u3.apply_settings', {}, '現在の翻訳設定を適用'),
    ('u3.proofread_hint', {}, 'AI校正は現在の翻訳モデル設定を使用 / 一覧は重要度→問題種別→キーで整理'),
    ('u3.severity_category', {}, '重要度 / 分類'),
    ('u3.type', {}, '種別'),
    ('u3.file', {}, 'ファイル'),
    ('u3.key', {}, 'キー'),
    ('u3.english_chinese_source', {}, '原文（英語 / 簡体字中国語）'),
    ('u3.editable_translation', {}, '訳文（編集可）'),
    ('u3.save_translation_file', {'target_name': '日本語'}, 'この訳を日本語ファイルへ保存'),
    ('u3.save_glossary', {}, 'この訳を用語集へ保存'),
    ('u3.ai_proofread', {}, 'AIで誤字脱字校正'),
    ('u3.restore_source', {}, '原文に戻す'),
    ('u3.diff_files', {'target_name': '日本語'}, '原文（英語 / 簡体字中国語） / 日本語ファイル'),
    ('u3.diff_source', {}, '原文（英語 / 中国語）'),
    ('u3.choose', {}, '選択'),
    ('u3.target_language', {'target_name': '日本語'}, '日本語'),
    ('u3.choose', {}, '選択'),
    ('u3.inspect_diff', {}, '差分を調査'),
    ('u3.drop_pair', {'target_name': '日本語'}, '英語または簡体字中国語の原文YAMLと日本語YAMLをここへドラッグ＆ドロップできます'),
    ('u3.dnd_unavailable', {}, 'ドラッグ＆ドロップはこのビルドでは利用できません'),
    ('u3.translate_selected', {}, '選択項目を翻訳'),
    ('u3.translate_missing', {}, '欠落・未翻訳をまとめて翻訳'),
    ('u3.save_selected', {}, '選択訳を保存'),
    ('u3.create_glossary', {}, '用語集を自動作成'),
    ('u3.apply_settings', {}, '現在の翻訳設定を適用'),
    ('u3.diff_hint', {}, '差分翻訳は現在の翻訳モデル設定を使用 / 一覧は状態→キーで整理'),
    ('u3.status', {}, '状態'),
    ('u3.file', {}, 'ファイル'),
    ('u3.key', {}, 'キー'),
    ('u3.multi_select_hint', {}, 'Ctrlキーを押しながらクリックすると複数選択できます。'),
    ('u3.english_chinese_source', {}, '原文（英語 / 簡体字中国語）'),
    ('u3.editable_target', {'target_name': '日本語'}, '日本語（直接編集可）'),
    ('u3.search_japanese', {}, 'ゲーム内の日本語翻訳を検索'),
    ('u3.game', {}, '対象ゲーム'),
    ('u3.rediscover_locations', {}, 'ゲーム / Mod場所を再検出'),
    ('u3.search_term', {}, '検索語'),
    ('u3.search', {}, '検索'),
    ('u3.clear_results', {}, '結果を消去'),
    ('u3.search_hint', {}, '検索語は必須です。ローカライズキー・日本語本文・原文を検索し、原文にあるのに日本語側にないキーは「未訳」として表示します。'),
    ('u3.search_mods', {}, '対象Mod（翻訳状況 / 未翻訳監視から取得）'),
    ('u3.refresh_mods', {}, '対象Modを更新'),
    ('u3.select_all', {}, 'すべて選択'),
    ('u3.deselect_all', {}, '選択解除'),
    ('u3.search_scope', {}, 'Modを選択した場合はそのModだけを検索します。未選択なら、取得済みの対象ゲームModすべてを検索します。'),
    ('u3.file', {}, 'ファイル'),
    ('u3.key', {}, 'キー'),
    ('u3.japanese_translation', {}, '日本語訳'),
    ('u3.select_result', {}, '検索結果を選択してください'),
    ('u3.save_japanese', {}, 'この日本語訳を保存'),
    ('u3.research_running', {}, 'すでに調査中です。'),
    ('u3.research_progress', {'count': 3}, 'バックグラウンド調査中: 0/3'),
    ('u3.research_start', {'count': 3}, '● 未翻訳Mod探索開始 — 0/3'),
    ('u3.research_detail', {}, 'Mod一覧と別日本語化Modを確認しています'),
    ('u3.research_stop', {}, '調査停止要求済み…'),
    ('u3.external_gaps', {'mod': 'sample', 'external_translation_mod': 'sample', 'count': 3, 'value': 'sample'}, 'sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（3件）。 sample。'),
    ('u3.external_complete', {'mod': 'sample', 'external_translation_mod': 'sample'}, 'sampleには日本語化Mod『sample』があり、完全な日本語化を確認できました。'),
    ('u3.no_japanese', {'mod': 'sample'}, 'sampleというModは日本語翻訳がありません。日本語化Modも確認できませんでした。'),
    ('u3.mod_gaps', {'mod': 'sample', 'count': 3, 'value': 'sample'}, 'sampleのModに翻訳の欠損箇所があります（3件）。 sample。'),
    ('u3.japanese_found', {'mod': 'sample'}, 'sampleのModは日本語翻訳が確認できました。'),
    ('u3.research_llm_error', {}, 'Mod翻訳状況 LLM精査'),
    ('u3.research_llm_skip', {'mod': 'sample', 'e': 'sample'}, 'sample のLLM精査をスキップ: sample'),
    ('u3.research_cache', {'mod': 'sample'}, 'sample: 前回調査結果をキャッシュから再利用'),
    ('u3.diff_status_error', {}, '差分翻訳 翻訳状況欠損取得'),
    ('u3.snapshot_present', {}, 'あり'),
    ('u3.snapshot_absent', {}, 'なし（現在の欠損から判定）'),
    ('u3.diff_confirmation', {'snapshot_note': 'sample', 'added': 'sample', 'changed': 'sample', 'removed': 'sample', 'missing_total': 'sample', 'added_files': 'sample', 'removed_files': 'sample'}, '差分翻訳対象を確認しました。\n\nスナップショット: sample\n新規キー: sample\n変更キー: sample\n削除キー: sample\n翻訳状況の欠損（このキューで補完可能）: sample\n新規ファイル: sample\n削除ファイル: sample\n\n原文差分と翻訳状況の欠損だけを補完します。'),
    ('u3.snapshot_not_found', {}, '同じ入力元に対応する過去の差分スナップショット付きキャッシュが見つかりません。\n一度v0.5.6以降で通常翻訳すると、次回更新から自動判定できます。'),
    ('u3.no_source_changes', {}, '前回翻訳時から原文の差分はありません。'),
    ('u3.japanese_yaml', {}, '日本語YAML'),
    ('u3.source_yaml_languages', {}, '英語または簡体字中国語の原文YAML'),
    ('u3.drop_other_side', {'side': 'sample'}, '片方を受け取りました。sampleもドロップしてください。'),
    ('u3.review_drop_files', {}, 'QAにはYAMLファイル、またはYAMLを含むフォルダをドロップしてください。'),
    ('u3.diff_drop_both', {}, '片方を受け取りました。英語または簡体字中国語の原文と日本語の両方をドロップしてください。'),
    ('u3.diff_drop_files', {}, '差分調査にはYAMLファイル、またはYAMLを含むフォルダをドロップしてください。'),
    ('u3.qa_repair_running', {}, 'QA・自動修正はすでに実行中です。'),
    ('u3.qa_llm_busy', {}, '別の翻訳用LLM処理が動作中です。完了または停止後にQA・自動修正を開始してください。'),
    ('u3.qa_pair_missing', {'target_name': '日本語'}, '原文と日本語出力の組み合わせを見つけられませんでした。'),
    ('u3.normal_queue', {}, '通常翻訳キュー'),
    ('u3.chinese_queue', {}, '中国語基準翻訳キュー'),
    ('u3.qa_review', {}, 'QA／比較編集'),
    ('u3.qa_repair_label', {'label': 'sample'}, 'sampleのQA・自動修正'),
    ('u3.qa_repair_confirm', {'label': 'sample', 'count': 3}, 'sampleの3ファイルをQAし、注意・警告を除く修復可能な全エラーを自動修正します。\n\n変更前ファイルはバックアップし、修正後にエラーが減らなければ自動復元します。\n続行しますか？'),
    ('u3.qa_repair_working', {'count': 3}, 'バックアップ・自動QA・修正中… 3ファイル'),
    ('u3.qa_repair_start', {'count': 3}, 'QA・自動修正開始: 3ファイル'),
    ('u3.qa_repair_start', {'count': 3}, 'QA・自動修正開始: 3ファイル'),
    ('u3.qa_repair_summary', {'initial_errors': 'sample', 'final_errors': 'sample', 'resolved_errors': 'sample', 'repaired_keys': 'sample', 'warnings': 'sample', 'notices': 'sample', 'failed_files': 'sample', 'spaces_removed': 'sample'}, '修正前エラー sample / 修正後 sample / 解消 sample / 修正キー sample / 警告 sample / 注意 sample / 失敗ファイル sample / 半角スペース除去 sample個'),
    ('u3.qa_repair_complete_log', {'text': 'sample'}, 'QA・自動修正完了: sample'),
    ('u3.qa_repair_complete_log', {'text': 'sample'}, 'QA・自動修正完了: sample'),
    ('u3.repair_log', {'report_path': 'sample'}, '修正ログ: sample'),
    ('u3.qa_repair_complete_log', {'text': 'sample'}, 'QA・自動修正完了: sample'),
    ('u3.repair_log', {'report_path': 'sample'}, '修正ログ: sample'),
    ('u3.llm_idle', {}, 'LLM 待機中'),
    ('u3.qa_repair_complete', {}, 'QA・自動修正が完了しました'),
    ('u3.qa_repair_complete_message', {'text': 'sample', 'backup_dir': 'sample', 'report_path': 'sample'}, 'QA・自動修正が完了しました。\n\nsample\nバックアップ: sample\nログ: sample'),
    ('u3.qa_repair_stopped', {'text': 'sample', 'report_path': 'sample'}, 'QA・自動修正を停止しました。\n\nsample\nログ: sample'),
    ('u3.file_start', {}, 'ファイル開始'),
    ('u3.initial_qa', {}, '初回QA中'),
    ('u3.backup', {}, 'バックアップ中'),
    ('u3.repair_pass', {}, '修復対象を整理中'),
    ('u3.mechanical_repair', {}, '機械修復中'),
    ('u3.llm_retranslate', {}, 'LLM再翻訳準備中'),
    ('u3.recheck', {}, '再QA中'),
    ('u3.final_qa', {}, '最終QA中'),
    ('u3.rollback', {}, '復元中'),
    ('u3.file_done', {}, 'ファイル完了'),
    ('u3.processing', {}, '処理中'),
    ('u3.qa_auto_repair', {}, 'QA自動修正'),
    ('u3.qa_repair_stage', {'stage_label': 'sample'}, '● QA自動修正中 — sample'),
    ('u3.repairable_detail', {'repairable_errors': 'sample', 'detail': 'sample'}, 'sample / 修復対象 sample件'),
    ('u3.repair_keys_detail', {'repair_keys': 'sample', 'detail': 'sample'}, 'sample / 対象 sample件'),
    ('u3.checking_progress', {}, '処理状況を確認中'),
    ('u3.qa_repair_progress', {'progress': 'sample', 'filename': 'sample', 'stage_label': 'sample'}, 'QA・自動修正 sample — sample — sample'),
    ('u3.qa_file_summary', {'progress': 'sample', 'filename': 'sample', 'initial_errors': 'sample', 'final_errors': 'sample', 'repaired': 'sample'}, 'sample sample: error sample→sample / 修正 sample'),
    ('u3.qa_repair_file_log', {'summary': 'sample'}, 'QA修正: sample'),
    ('u3.qa_repair_file_log', {'summary': 'sample'}, 'QA修正: sample'),
    ('u3.llm_idle', {}, 'LLM 待機中'),
    ('u3.qa_repair_failed', {}, 'QA・自動修正でエラーが発生しました'),
    ('u3.qa_repair_error_context', {}, 'QA・自動修正エラー'),
    ('u3.qa_repair', {}, 'QA・自動修正'),
    ('u3.qa_repair_error', {'error_type': 'sample', 'message': 'sample'}, 'QA・自動修正に失敗しました。\nsample: sample'),
    ('u3.select_qa_items', {}, 'QA・自動修正する通常翻訳項目を選択してください。'),
    ('u3.diff_completion_error', {}, '差分翻訳 言語別完了判定'),
    ('u3.diff_preparing', {}, '差分翻訳の準備はすでにバックグラウンドで実行中です。'),
    ('u3.select_diff_items', {}, '差分翻訳する項目を選択してください。'),
    ('u3.diff_prepare_progress', {'count': 3}, '差分をバックグラウンド解析中… 0/3'),
    ('u3.diff_prepare_progress', {'count': 3}, '差分をバックグラウンド解析中… 0/3'),
    ('u3.diff_unavailable', {'value': 'sample'}, '差分スナップショットがなく、翻訳状況にも判定材料となる欠損がないため、差分を判定できない項目があります。\n\nsample'),
    ('u3.language_completed_list', {'value': 'sample', 'prefix': 'sample'}, 'sample\n\n言語別に完了している項目:\nsample'),
    ('u3.some_completed', {'value': 'sample'}, '一部項目は現在の言語で翻訳が完了しています。\n\nsample'),
    ('u3.no_diff_gaps', {}, '原文差分も翻訳状況の欠損もありません。'),
    ('u3.select_diff_files', {'target_name': '日本語'}, '英語または簡体字中国語の原文ファイルと日本語ファイルの両方を選択してください。'),
    ('u3.diff_background', {}, '差分をバックグラウンド解析中…'),
    ('u3.diff_background_hint', {}, '差分をバックグラウンド解析中… GUIは操作できます'),
    ('u3.diff_background', {}, '差分をバックグラウンド解析中…'),
    ('u3.diff_batch_background', {'count': 3}, '差分を一括解析中… 3ファイル / GUIは操作できます'),
    ('u3.missing', {}, '欠落'),
    ('u3.untranslated', {}, '未翻訳'),
    ('u3.target_only', {'target_name': '日本語'}, '日本語のみ'),
    ('u3.matched', {}, '対応あり'),
    ('u3.diff_summary_rendering', {'missing': 'sample', 'untranslated': 'sample', 'extra': 'sample', 'ok': 'sample', 'target_name': '日本語'}, '欠落 sample / 未翻訳 sample / 日本語のみ sample / 対応あり sample — 表示作成中…'),
    ('u3.diff_summary', {'missing': 'sample', 'untranslated': 'sample', 'extra': 'sample', 'ok': 'sample', 'target_name': '日本語'}, '欠落 sample / 未翻訳 sample / 日本語のみ sample / 対応あり sample'),
    ('u3.diff_batch_failed', {'count': 3}, '差分一括解析失敗: 3ファイル'),
    ('u3.diff_no_files', {'value': 'sample'}, '差分を読み込めるファイルがありませんでした。\n\nsample'),
    ('u3.missing', {}, '欠落'),
    ('u3.untranslated', {}, '未翻訳'),
    ('u3.target_only', {'target_name': '日本語'}, '日本語のみ'),
    ('u3.matched', {}, '対応あり'),
    ('u3.diff_batch_summary_failed', {'count': 3, 'missing': 'sample', 'untranslated': 'sample', 'extra': 'sample', 'ok': 'sample', 'target_name': '日本語', 'failed': 2}, '差分一括: 3ファイル / 欠落 sample / 未翻訳 sample / 日本語のみ sample / 対応あり sample / 読込失敗 2'),
    ('u3.diff_batch_summary', {'count': 3, 'missing': 'sample', 'untranslated': 'sample', 'extra': 'sample', 'ok': 'sample', 'target_name': '日本語'}, '差分一括: 3ファイル / 欠落 sample / 未翻訳 sample / 日本語のみ sample / 対応あり sample'),
    ('u3.diff_batch_skipped', {'failed': 'sample', 'value': 'sample'}, 'sampleファイルをスキップし、残りの差分調査を完了しました。\n\nsample'),
    ('u3.save_diff_error', {}, '差分訳保存'),
    ('u3.diff_backup_label', {}, '差分翻訳の書き込み直前のlocalization全体'),
    ('u3.diff_translation_running', {}, '差分翻訳はすでに実行中です。'),
    ('u3.select_missing_keys', {}, '翻訳対象の欠落/未翻訳キーを選択してください。'),
    ('u3.diff_translating', {'count': 3}, '差分翻訳中… 3件'),
    ('u3.translation_failed', {'value': 'sample', 'exc': 'sample'}, '翻訳に失敗しました: sample: sample'),
    ('u3.search_game_scope', {}, '翻訳検索はゲーム単位の検索に変更されました。対象ゲームを選んで検索してください。'),
    ('u3.search_yaml_scope', {}, '翻訳検索はゲーム単位の検索に変更されました。個別YAMLはQA / 比較編集または差分調査から選択できます。'),
    ('u3.search_idle', {}, '検索待機中'),
    ('u3.select_result', {}, '検索結果を選択してください'),
    ('u3.search_mods_background', {}, '対象Modをバックグラウンド取得中…'),
    ('u3.select_search_game', {}, '検索するゲームを選択してください。'),
    ('u3.require_search_term', {}, '全件列挙を防ぐため、検索語を入力してください。'),
    ('u3.search_background', {'game': 'sample'}, 'sample: バックグラウンド検索中…'),
    ('u3.search_missing_path', {'mod_name': 'sample', 'localization_key': 'sample', 'src': 'sample', 'dst': 'sample'}, 'sample / sample / 未訳  原文: sample  → 日本語: sample'),
    ('u3.search_target_missing', {}, '日本語ファイルの保存先を特定できませんでした。'),
    ('u3.search_update_failed', {}, '対象キーをファイル内で更新できませんでした'),
    ('u3.saved_key', {'localization_key': 'sample'}, '保存しました: sample'),
    ('u3.search_save_error', {}, '翻訳検索から直接訂正'),
    ('u3.select_translation_file', {}, '訳文ファイルを選択してください。'),
    ('u3.qa_log_exported', {'path': 'sample'}, 'QAログを書き出しました。\n\nsample'),
    ('u3.qa_log_error_context', {}, 'QAログ書き出し'),
    ('u3.qa_log_export_failed', {'exc': 'sample'}, 'QAログの書き出しに失敗しました。\nsample'),
    ('u3.no_repairable_errors', {}, '現在のQA結果に自動修復できるエラーはありません。'),
    ('u3.qa_background', {}, 'QAをバックグラウンド解析中…'),
    ('u3.qa_batch_background', {'count': 3}, 'QAを一括解析中… 3ファイル / GUIは操作できます'),
    ('u3.cancel_qa', {}, 'QAを中止'),
    ('u3.skip_continue', {}, 'スキップして継続'),
    ('u3.qa_background', {}, 'QAをバックグラウンド解析中…'),
    ('u3.qa_background_hint', {}, 'QAをバックグラウンド解析中… GUIは操作できます'),
    ('u3.select_translation_file', {}, '訳文ファイルを選択してください。'),
    ('u3.cancel_qa', {}, 'QAを中止'),
    ('u3.qa_summary', {'errs': 'sample', 'warns': 'sample', 'notices': 'sample', 'count': 3}, 'QA: エラー sample / 警告 sample / 注意 sample / キー 3'),
    ('u3.qa_batch_failed', {'count': 3}, 'QA一括解析失敗: 3ファイル'),
    ('u3.qa_no_files', {'value': 'sample'}, 'QAで読み込めるファイルがありませんでした。\n\nsample'),
    ('u3.warning', {}, '警告'),
    ('u3.notice', {}, '注意'),
    ('u3.no_issues', {}, '問題なし'),
    ('u3.qa_batch_summary_failed', {'count': 3, 'error': 'sample', 'warning': 'sample', 'notice': 'sample', 'total_keys': 'sample', 'failed': 2}, 'QA一括: 3ファイル / エラー sample / 警告 sample / 注意 sample / キー sample / 読込失敗 2'),
    ('u3.qa_batch_summary', {'count': 3, 'error': 'sample', 'warning': 'sample', 'notice': 'sample', 'total_keys': 'sample'}, 'QA一括: 3ファイル / エラー sample / 警告 sample / 注意 sample / キー sample'),
    ('u3.qa_batch_skipped', {'failed': 'sample', 'value': 'sample'}, 'sampleファイルをスキップし、残りのQAを完了しました。\n\nsample'),
    ('u3.other', {}, 'その他'),
    ('u3.review_rendering', {'value': 'sample', 'count': 3}, 'sample / 表示 3件を分割描画中…'),
    ('u3.warning', {}, '警告'),
    ('u3.notice', {}, '注意'),
    ('u3.no_issues', {}, '問題なし'),
    ('u3.no_issues', {}, '問題なし'),
    ('u3.qa_summary', {'errs': 'sample', 'warns': 'sample', 'notices': 'sample', 'count': 3}, 'QA: エラー sample / 警告 sample / 注意 sample / キー 3'),
    ('u3.ai_proofreading', {}, 'AI校正中…（上部のLLM動作表示から停止できます）'),
    ('u3.ai_typo_check', {}, 'AI誤字脱字校正'),
    ('u3.load_before_unify', {'target_name': '日本語'}, '先にQA / 比較編集で原文と日本語訳を読み込んでください。'),
    ('u3.no_term_issues', {}, '現在のQA結果に用語不一致はありません。'),
    ('u3.unify_confirm', {'count': 3}, '用語集の自動用語候補を使って、用語不一致 3件を一括統一しますか？\n\n既知の表記揺れだけを安全に置換します。判定できない箇所は変更しません。'),
    ('u3.unify_complete', {'changed': 'sample', 'skipped': 'sample'}, '用語統一が完了しました。\n変更: sample件\n自動置換できなかった候補: sample件'),
    ('u3.unify_error_context', {}, 'QA用語一括統一'),
]


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.get_ui_language()
    yield
    i18n.set_ui_language(previous)


@pytest.mark.parametrize("key,fields,original", ORIGINAL_CASES)
def test_japanese_display_unchanged(key, fields, original):
    i18n.set_ui_language("japanese")
    assert i18n.t(key, **fields) == original


def test_all_u3_keys_have_english_translations():
    i18n.set_ui_language("english")
    assert JAPANESE
    assert set(JAPANESE) == set(ENGLISH)
    assert {case[0] for case in ORIGINAL_CASES} == set(JAPANESE)
    for key in JAPANESE:
        assert key.startswith("u3.")
        assert i18n.t(key) == ENGLISH[key]
        assert not re.search(r"[぀-ヿ一-鿿]", ENGLISH[key])


def test_target_names_support_all_languages():
    for ui_language in ("japanese", "english"):
        i18n.set_ui_language(ui_language)
        for target_language in i18n.UI_LANGUAGES:
            target_name = i18n.t("lang." + target_language)
            for key, template in JAPANESE.items():
                if "{target_name}" in template:
                    assert target_name in i18n.t(key, target_name=target_name)


def test_u3_main_calls_are_qualified():
    source = (Path(__file__).resolve().parents[1] / "app" / "main.py").read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            if isinstance(node.args[0].value, str) and node.args[0].value.startswith("u3."):
                assert isinstance(node.func, ast.Attribute)
                assert isinstance(node.func.value, ast.Name)
                assert node.func.value.id == "i18n"
                assert node.func.attr == "t"
                assert all(keyword.arg != "key" for keyword in node.keywords)
