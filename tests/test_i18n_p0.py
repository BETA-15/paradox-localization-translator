"""P0 display regressions, with original Japanese literals independent of the dictionaries."""
from __future__ import annotations

import ast
import queue
import re
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import pytest
import i18n
import main
from i18n.english import p0_common as english_p0
from i18n.japanese import p0_common as japanese_p0

FIXED_ORIGINALS = [
    ('p0.no_search_results', '検索結果なし'),
    ('p0.no_scan_results', '調査結果なし'),
    ('p0.no_translation_status_scan_results', '翻訳状況の調査結果がありません'),
    ('p0.unknown_file', '不明ファイル'),
    ('p0.the_qa_comparison_editor_also', 'QA／比較編集タブも、ここで選んだ翻訳先の基準で確認します。日本語以外の翻訳先では、Mod調査・日本語化Modの判定と紐付け・差分だけ翻訳・中国語基準翻訳は使えません（日本語のみ）。日本語以外の品質チェックは日本語より簡易です（ラテン文字の言語どうしは「原文と同じ」だけを確認します）。'),
    ('p0.this_feature_is_available_only', 'この機能は日本語の用語集だけで使えます'),
    ('p0.missing_only_translation_is_available', '「差分だけ翻訳」は翻訳先が日本語の項目だけで使えます。日本語以外の項目は「一からすべて翻訳」を使ってください。'),
    ('p0.the_llm_response_was_empty', 'LLMの応答が空でした'),
    ('p0.internal_markers_n_remain', '内部の記号（@@N@@）が残りました'),
    ('p0.game_variables_or_tags_do', 'ゲーム変数・タグが原文と一致しません'),
    ('p0.the_response_was_chinese_not', '日本語ではなく中国語の応答でした'),
    ('p0.the_response_is_unchanged_or', '原文のまま、または翻訳として使えない応答でした'),
    ('p0.this_model_is_not_supported', 'このモデルは使用できません'),
    ('p0.thinking_models_are_not_supported', '推論（Thinking）モデルは使用できません'),
    ('p0.models_that_output_reasoning_are', '考える過程を出すモデルは翻訳に向きません'),
    ('p0.embedding_only_models_cannot_translate', '埋め込み専用モデルは翻訳に使用できません'),
    ('p0.cannot_connect_to_the_llm', 'LLMに接続できません'),
    ('p0.llm_connection_failed', 'LLMと接続できません'),
    ('p0.skip_and_continue', 'スキップして継続'),
    ('p0.could_not_extract_a_crash', 'クラッシュ概要を抽出できませんでした。'),
    ('p0.model_statistics', 'モデル統計'),
    ('p0.model_profiles', 'モデルプロファイル'),
    ('p0.llm_idle', 'LLM 待機中'),
    ('p0.llm_activity_appears_here_when', 'LLM処理が始まるとここに常時表示されます'),
    ('p0.discovery_llm_idle', '探索用LLM 待機中'),
    ('p0.discovery_and_review_of_untranslated', '未翻訳Modの探索・精査状況をここに表示します'),
    ('p0.drag_and_drop_checking_initialization', 'ドラッグ＆ドロップ: 初期化確認中'),
    ('p0.waiting_for_a_response', '応答待機中'),
    ('p0.app_settings', 'アプリ設定'),
    ('p0.auto_glossary_idle', '自動用語作成: 待機中'),
    ('p0.checking_llm_connection', 'LLM接続確認中…'),
    ('p0.idle', '待機中'),
    ('p0.qa_not_run', 'QA未実行'),
    ('p0.add_yaml_files_or_a', 'YAML / localizationフォルダを追加してください'),
    ('p0.select_simplified_chinese_yaml_files', '簡体字中国語YAMLを選択してください'),
    ('p0.differences_not_scanned', '差分未調査'),
    ('p0.search_idle', '検索待機中'),
    ('p0.target_mods_not_loaded', '対象Mod: 未取得'),
    ('p0.monitor_targets_select_a_game', '監視対象: 翻訳状況タブでゲーム / Mod場所を選択してください'),
    ('p0.monitor_llm_unchecked', '監視用LLM: 未確認'),
    ('p0.monitor_stopped', '監視停止中'),
    ('p0.untranslated_candidates', '未翻訳候補: --'),
    ('p0.scan_results', '調査結果: --'),
    ('p0.games_shown_all', '表示ゲーム: すべて'),
    ('p0.diagnostics_idle', '診断待機中'),
    ('p0.target_mods_from_translation_status', '対象Mod: 翻訳状況から取得'),
    ('p0.backups_not_loaded', 'バックアップ未読込'),
    ('p0.select_a_backup_from_the', '一覧からバックアップを選択してください。'),
    ('p0.game_mod_locations_not_detected', 'ゲーム/Mod場所: 未検出'),
    ('p0.mod_classification_cache', 'Mod分類キャッシュ'),
    ('p0.initial_mod_classification_cache_migration', 'Mod初回分類キャッシュ移行'),
    ('p0.mod_linking_settings', 'Mod関連付け設定'),
    ('p0.standard_translation', '通常翻訳'),
    ('p0.preparing_missing_only_translation', '差分翻訳準備'),
    ('p0.single_overwrite', '単体上書き'),
    ('p0.bulk_overwrite', '一括上書き'),
    ('p0.restore_backup', 'バックアップ復元'),
    ('p0.full_diagnostics_and_repair', '総合診断・修復'),
    ('p0.qa_and_auto_fix', 'QA・自動修正'),
    ('p0.llm_connection_check', 'LLM接続確認'),
    ('p0.import_glossary', '用語取り込み'),
    ('p0.stop_translation_llm', '翻訳LLM停止'),
    ('p0.stop_discovery_llm', '探索LLM停止'),
    ('p0.latest_translation_llm_response_read', '翻訳用LLM 最新応答（読み取り専用）'),
    ('p0.open_full_response', '全文を開く'),
    ('p0.clear', 'クリア'),
    ('p0.latest_discovery_llm_response_read', '探索用LLM 最新応答（読み取り専用）'),
    ('p0.translation_queue', '翻訳 / キュー'),
    ('p0.qa_comparison_editor', 'QA / 比較編集'),
    ('p0.difference_scan', '差分調査'),
    ('p0.translation_search', '翻訳検索'),
    ('p0.glossary', '用語集'),
    ('p0.model_connection', 'モデル / 接続'),
    ('p0.untranslated_monitor', '未翻訳監視'),
    ('p0.translation_status', '翻訳状況'),
    ('p0.help', '使い方'),
    ('p0.ctrl_multi_select', 'Ctrl複数選択'),
    ('p0.close_the_app', 'アプリを閉じますか？'),
    ('p0.the_close_button_was_pressed', '×ボタンが押されました'),
    ('p0.minimize_the_window_or_quit', '最小化しますか？ それともアプリを終了しますか？\n\n・最小化: ウィンドウだけを最小化します。翻訳・探索・LLM処理は続行します。\n・終了: 翻訳中ならセッションとキャッシュを保存し、安全停止を要求してから終了します。'),
    ('p0.translation', '翻訳'),
    ('p0.mod_discovery_monitoring', 'Mod探索/監視'),
    ('p0.minimize', '最小化'),
    ('p0.quit', '終了'),
    ('p0.cancel', 'キャンセル'),
    ('p0.shutdown_stop_request', '終了時停止要求'),
    ('p0.continuous_monitoring', '常時監視'),
    ('p0.mod_scan', 'Mod調査'),
    ('p0.model_speed_test', 'モデル速度テスト'),
    ('p0.qa_analysis', 'QA解析'),
    ('p0.difference_analysis', '差分解析'),
    ('p0.ai_proofreading', 'AI校正'),
    ('p0.auto_glossary', '自動用語作成'),
    ('p0.preparing_to_exit_waiting_for', '終了準備中 — 保存と処理停止を待っています'),
    ('p0.force_quit', '強制終了'),
    ('p0.the_user_chose_to_force', 'worker完了前にユーザーが強制終了を選択しました'),
    ('p0.detecting_checking_other_drives_and', '自動検出中…（別ドライブ・外付けSSDも確認）'),
    ('p0.mod_location_scan', 'Mod場所調査'),
    ('p0.load_base_game_source', 'ゲーム本体原文取得'),
    ('p0.saving_and_stopping_waiting_for', '保存して中断中… 現在のリクエスト完了を待っています'),
    ('p0.glossary_import_is_already_running', '用語取り込みはすでにバックグラウンドで実行中です。'),
    ('p0.ollama_is_not_running_cannot', 'Ollamaが起動していません（接続できません）'),
    ('p0.cannot_connect_to_lm_studio', 'LM Studio Local Serverに接続できません'),
    ('p0.cannot_connect_to_the_openai', 'OpenAI互換APIに接続できません。URL/APIキーを確認してください'),
    ('p0.ollama_is_not_running', 'Ollamaが起動していません'),
    ('p0.backup_loading_error', 'バックアップ読込エラー'),
    ('p0.background_loading_of_the_backup', 'バックアップ復元一覧バックグラウンド読込'),
    ('p0.could_not_restore_previous_translation', '前回翻訳状況の復元に失敗'),
    ('p0.background_restore_of_the_translation', '翻訳状況キャッシュバックグラウンド復元'),
    ('p0.background_restore_of_the_full', '総合診断キャッシュバックグラウンド復元'),
    ('p0.detection_log_generation_error', '判定ログ生成エラー'),
    ('p0.generate_translation_mod_detection_log', '日本語化Mod判定ログ生成'),
    ('p0.detection_log_exported', '判定ログ書き出し完了'),
    ('p0.detection_log_export_error', '判定ログ書き出しエラー'),
    ('p0.export_translation_mod_detection_log', '日本語化Mod判定ログ書き出し'),
    ('p0.difference_analysis_error', '差分解析エラー'),
    ('p0.background_difference_scan', '差分調査バックグラウンド解析'),
    ('p0.qa_analysis_error', 'QA解析エラー'),
    ('p0.background_qa_analysis', 'QAバックグラウンド解析'),
    ('p0.qa_auto_fix', 'QA自動修正'),
    ('p0.backup_restore_error', 'バックアップ復元エラー'),
    ('p0.storage_location_change_error', '保存場所変更エラー'),
    ('p0.background_storage_location_copy', '保存場所バックグラウンドコピー'),
    ('p0.pause', '一時停止'),
    ('p0.stopped_cache_saved', '中断しました（キャッシュ保存済み）'),
    ('p0.chinese_based_translation_stopped', '中国語基準翻訳を中断しました'),
    ('p0.chinese_based_translation_completed', '中国語基準翻訳が完了しました'),
    ('p0.an_error_occurred_in_chinese', '中国語基準翻訳でエラーが発生しました'),
    ('p0.speed_test_complete', '速度テスト完了'),
    ('p0.speed_test_completed', '速度テストが完了しました'),
    ('p0.speed_test_stopped', '速度テストを停止しました'),
    ('p0.auto_detection_failed_select_a', '自動検出できませんでした — 手動選択を使用してください'),
    ('p0.auto_detection_error', '自動検出エラー'),
    ('p0.monitor_stopped_2', '○ 監視停止中'),
    ('p0.continuous_monitoring_started', '常時監視を開始'),
    ('p0.untranslated_monitor_stopped', '未翻訳監視を終了しました'),
    ('p0.monitoring_error', '監視エラー'),
    ('p0.mod_translation_status_scan_completed', 'Mod翻訳状況の調査が完了しました'),
    ('p0.resolve_backup_restore_destinations_again', 'バックアップ復元先の再解決'),
    ('p0.mod_translation_status_scan', 'Mod翻訳状況調査'),
    ('p0.scan_error', '調査エラー'),
    ('p0.an_error_occurred_during_the', 'Mod調査でエラーが発生しました'),
    ('p0.choose_which_conflicting_version_to', '競合の優先先を指定してください'),
    ('p0.diagnostics_completed_select_an_item', '診断が完了しました。一覧から項目を選択すると詳細を確認できます。'),
    ('p0.refresh_full_diagnostics_cache_after', '総合診断 修復後キャッシュ更新'),
    ('p0.diagnostics_error', '診断エラー'),
    ('p0.could_not_load_target_mods', '対象Mod取得エラー'),
    ('p0.load_target_mods_for_translation', '翻訳検索 対象Mod取得'),
    ('p0.untranslated', '【未訳】'),
    ('p0.search_error', '検索エラー'),
    ('p0.translation_stopped_cache_saved', '翻訳を中断しました。キャッシュを保存しました。'),
    ('p0.translation_stopped', '翻訳を中断しました'),
    ('p0.translation_completed', '翻訳が完了しました'),
    ('p0.selected_translations_completed', '選択した翻訳が完了しました'),
    ('p0.unresolved_items_remain_in_the', '\n\n未解決項目はキューに保持されています。各翻訳結果フォルダの translation_error_report.json で詳細を確認できます。'),
    ('p0.fatal_translation_error', '翻訳処理 fatal'),
    ('p0.an_error_occurred_during_translation', '翻訳処理でエラーが発生しました'),
    ('p0.missing_only_translation_stopped', '差分翻訳を停止しました'),
    ('p0.an_error_occurred_in_missing', '差分翻訳でエラーが発生しました'),
    ('p0.auto_glossary_completed', '自動用語作成が完了しました'),
    ('p0.auto_glossary_stopped', '自動用語作成を終了しました'),
    ('p0.find_matching_source_text_in', '対応原文をゲーム本体から探せます'),
    ('p0.no_matching_english_simplified_chinese', '選択した日本語localizationの近くに、対応する英語 / 簡体字中国語原文が見つかりませんでした。\n\n対象ゲーム本体のlocalizationを同じキーで自動照合できます。ゲーム本体に存在しないMod独自キーはスキップされます。'),
    ('p0.import_glossary_from_japanese_localization', '日本語localizationからの用語取り込み'),
    ('p0.glossary_import_complete', '用語取り込み完了'),
    ('p0.no_importable_japanese_localization_was', '取り込み可能な日本語localizationを確認できませんでした。'),
    ('p0.no_glossary_candidates_were_available', '取り込み可能な用語候補はありませんでした。'),
    ('p0.glossary_import_error', '用語取り込みエラー'),
    ('p0.ai_spelling_and_typo_check', 'AI誤字脱字校正'),
    ('p0.ai_proofreading_results_are_shown', 'AI校正結果を表示しました。内容を確認して保存してください。'),
    ('p0.ai_proofreading_completed', 'AI校正が完了しました'),
    ('p0.ai_proofreading_stopped', 'AI校正を停止しました。'),
    ('p0.ai_proofreading_stopped_2', 'AI校正を停止しました'),
    ('p0.an_error_occurred_during_ai', 'AI校正でエラーが発生しました'),
]

DYNAMIC_ORIGINALS = [
    ('p0.no_mods_match', {'query': 'Example'}, "f'検索条件「{query}」に一致するModはありません'"),
    ('p0.provider', {'display': 'Example'}, "f'プロバイダ: {display}'"),
    ('p0.endpoint', {'endpoint': 'Example'}, "f'接続先: {endpoint}'"),
    ('p0.model', {'model': 'Example'}, "f'モデル: {model}'"),
    ('p0.no_model_is_selected_for', {'display': 'Example'}, "f'{display}に接続するモデルが選択されていません。モデルを読み込んで選択してください。'"),
    ('p0.api_authentication_failed_check_the', {'display': 'Example'}, "f'{display}のAPI認証に失敗しました。APIキー、利用権限、接続先を確認してください。'"),
    ('p0.cannot_verify_the_model_or', {'display': 'Example'}, "f'{display}のモデルまたはAPI URLを確認できません。モデル名と接続先を確認してください。'"),
    ('p0.cannot_communicate_with_check_the', {'display': 'Example'}, "f'{display}と通信できません。API URL、モデル、認証情報、サーバー状態を確認してください。'"),
    ('p0.details', {'detail': 'Example'}, "f'詳細: {detail}'"),
    ('p0.backup_failed', {'path': 'Example', 'move_exc': 'Example'}, "f'{path}; 退避失敗: {move_exc}'"),
    ('p0.json_corrupted', {'label': 'Example'}, "f'{label} JSON破損'"),
    ('p0.previous_start_pid_no_clean', {'started_at': 'Example', 'pid': 7}, "f'Previous start: {started_at} / pid={pid}. 正常終了マーカーが残らなかったため、強制終了またはネイティブクラッシュの可能性があります。'"),
    ('p0.close_button_behavior_saved_action', {'value': 'Example'}, "f'×ボタンの動作設定を保存しました。\\n\\n動作: {value}'"),
    ('p0.currently_running', {'value': 'Example'}, "'現在動作中: ' + value"),
    ('p0.preparing_to_exit', {'APP_NAME': 'Example', 'APP_VERSION': 'Example'}, "f'{APP_NAME} {APP_VERSION} — 終了準備中'"),
    ('p0.preparing_to_exit_2', {'names': 'Example'}, "'終了準備中: ' + names"),
    ('p0.waiting_for_saves_or_workers', {'names': 'Example'}, "f'保存または処理の停止を待っています。\\n\\n動作中: {names}\\n\\n［はい］: 強制終了する（処理中の最新バッチは失われる可能性があります）\\n［いいえ］: 安全な停止を待ち続ける'"),
    ('p0.an_unexpected_error_occurred_recorded', {'exc_value': 'Example'}, "f'予期しないエラーが発生しました。\\n\\n{exc_value}\\n\\nエラーログに記録しました。'"),
    ('p0.chinese_based_translation_is_complete', {'count': 7}, "f'中国語基準の翻訳は完了しています。残り{count}件は英語原文にのみ存在します。'"),
    ('p0.standard_translation_is_complete_the', {'count': 7}, "f'通常翻訳は完了しています。残り{count}件は簡体字中国語原文にのみ存在します。'"),
    ('p0.session_saved', {'RESUME_STATE_PATH': 'Example'}, "f'セッション保存: {RESUME_STATE_PATH}'"),
    ('p0.select_the_base_game_localization', {'game': 'Example'}, "f'{game} のゲーム本体 localization / localisation フォルダを選択'"),
    ('p0.connected_models', {'value': 'Example', 'count': 7}, "f'{value} 接続済み / {count}モデル'"),
    ('p0.cannot_connect_to_the_api', {'p': 'Example'}, "f'{p} APIに接続できません。APIキー・モデル・利用権限を確認してください'"),
    ('p0.monitor_llm_connected_models', {'value': 'Example', 'count': 7}, "f'監視用LLM: {value} 接続済み / {count}モデル'"),
    ('p0.cannot_connect_to', {'p': 'Example'}, "f'{p}に接続できません'"),
    ('p0.monitor_llm', {'msg': 'Example'}, "'監視用LLM: ' + msg"),
    ('p0.translation_mod_detection_log_exported', {'payload': 'Example'}, "f'日本語化Mod判定ログを書き出しました。\\n\\n{payload}'"),
    ('p0.could_not_export_the_detection', {'payload': 'Example'}, "f'判定ログの書き出しに失敗しました。\\n{payload}'"),
    ('p0.bulk_overwrite_2', {'pos': 7, 'total': 7, 'name': 'Example'}, "f'一括上書き中… {pos}/{total} — {name}'"),
    ('p0.restored_target_pre_restore_backup', {'target': 'Example', 'safety_root': 'Example'}, "f'復元しました。\\n\\n対象: {target}\\n復元前退避: {safety_root}\\n\\n翻訳状況は次回の再調査で再判定されます。'"),
    ('p0.could_not_restore_the_backup', {'payload': 'Example'}, "f'バックアップ復元に失敗しました。\\n{payload}'"),
    ('p0.analyzing_differences', {'pos': 7, 'total': 7, 'name': 'Example'}, "f'差分解析中… {pos}/{total} — {name}'"),
    ('p0.could_not_analyze_differences', {'value': 'Example'}, "'差分解析に失敗しました。\\n' + value"),
    ('p0.could_not_change_the_storage', {'payload': 'Example'}, "f'保存場所の変更に失敗しました。\\n{payload}'"),
    ('p0.queue_file_lines', {'value': 'Example', 'count': 7, 'file_no': 7, 'file_total': 7, 'done': 7, 'total': 7}, "f'キュー {value}/{count} / ファイル {file_no}/{file_total} / {done}/{total}行'"),
    ('p0.translating_lines', {'name': 'Example', 'done': 7, 'total': 7}, "f'翻訳中: {name} — {done}/{total}行'"),
    ('p0.completed', {'name': 'Example'}, "f'完了: {name}'"),
    ('p0.auto_repair_utf_8_bom', {'name': 'Example', 'detected_encoding': 'Example'}, "f'[自動修復] {name}: {detected_encoding} → UTF-8 BOM出力'"),
    ('p0.file_error', {'name': 'Example', 'stage': 'Example', 'error_type': 'Example', 'action': 'Example'}, "f'[ファイルエラー] {name} / {stage}: {error_type} — {action}'"),
    ('p0.queue', {'i': 7, 'total': 7, 'name': 'Example'}, "f'キュー {i}/{total} — {name}'"),
    ('p0.started', {'name': 'Example', 'i': 7, 'total': 7}, "f'開始: {name} ({i}/{total})'"),
    ('p0.completed_items_qa_errors_warnings', {'processed_files': 7, 'queue_total': 7, 'qa_e': 7, 'qa_w': 7, 'qa_n': 7, 'qa_r': 7}, "f'完了 — {processed_files}/{queue_total}項目 / QA error {qa_e}・warning {qa_w}・notice {qa_n}・修正 {qa_r}'"),
    ('p0.auto_qa_and_fixes_for', {'qa_e': 7, 'qa_w': 7, 'qa_n': 7, 'qa_r': 7}, "f'翻訳語 自動QA・修正: error {qa_e} / warning {qa_w} / notice {qa_n} / 修正 {qa_r}'"),
    ('p0.qa_repair_log', {'report': 'Example'}, "f'QA修正ログ: {report}'"),
    ('p0.pre_qa_repair_backup', {'backup': 'Example'}, "f'QA修復前バックアップ: {backup}'"),
    ('p0.output', {'output': 'Example'}, "f'出力先: {output}'"),
    ('p0.chinese_based_translation_completed_auto', {'qa_e': 7, 'qa_w': 7, 'qa_n': 7, 'qa_r': 7}, "f'中国語基準翻訳が完了しました。\\n翻訳語 自動QA・修正: error {qa_e} / warning {qa_w} / notice {qa_n} / 修正 {qa_r}'"),
    ('p0.error', {'value': 'Example'}, "'エラー: ' + value"),
    ('p0.chinese_based_translation_error', {'value': 'Example'}, "'中国語基準翻訳エラー: ' + value"),
    ('p0.speed_test', {'i': 7, 'total': 7, 'model': 'Example'}, "f'速度テスト中 {i}/{total} — {model}'"),
    ('p0.model_speed_test_2', {'i': 7, 'total': 7}, "f'モデル速度テスト {i}/{total}'"),
    ('p0.speed_test_completed_preparing_the', {'i': 7, 'total': 7}, "f'速度テスト中 {i}/{total} 完了 — 次のモデルを準備'"),
    ('p0.failed', {'model': 'Example', 'i': 7, 'total': 7}, "f'{model} 失敗 ({i}/{total})'"),
    ('p0.speed_test_failed', {'model': 'Example', 'err': 'Example'}, "f'[速度テスト失敗] {model}: {err}'"),
    ('p0.locations_detected', {'count': 7}, "f'{count}か所検出'"),
    ('p0.mod_location_auto_detection', {'value': 'Example'}, "'[Mod場所自動検出] ' + value"),
    ('p0.untranslated_monitor_2', {'value': 'Example'}, "'[未翻訳監視] ' + value"),
    ('p0.untranslated_candidates_2', {'count': 7, 'value': 'Example'}, "f'未翻訳候補: {count}' + value"),
    ('p0.continuous_monitoring_last_checked', {'value': 'Example'}, "f'● 常時監視中 — 最終確認 {value}'"),
    ('p0.untranslated_monitor_error', {'payload': 'Example'}, "'未翻訳監視エラー: ' + payload"),
    ('p0.scan_results_entries', {'count': 7}, "f'調査結果: {count}件'"),
    ('p0.scan_results_entries_2', {'count': 7, 'value': 'Example'}, "f'調査結果: {count}件' + value"),
    ('p0.scanning_in_background', {'i': 7, 'total': 7, 'name': 'Example'}, "f'バックグラウンド調査中: {i}/{total} — {name}'"),
    ('p0.discovering_untranslated_mods', {'i': 7, 'total': 7}, "f'● 未翻訳Mod探索中 — {i}/{total}'"),
    ('p0.currently_scanning', {'name': 'Example'}, "f'現在調査中: {name}'"),
    ('p0.scan_stopped_entries_checked', {'count': 7}, "f'調査を停止しました — {count}件確認'"),
    ('p0.scan_complete_entries', {'count': 7, 'value': 'Example'}, "f'調査完了: {count}件' + value"),
    ('p0.mod_translation_status_scan_error', {'payload': 'Example'}, "'Mod翻訳状況の調査エラー: ' + payload"),
    ('p0.diagnostic_progress', {'phase': 'Example', 'done': 7, 'total': 7, 'mod': 'Example'}, "f'{phase}中: {done}/{total} — {mod}'"),
    ('p0.before_repair_choose_which_version', {'value': 'Example'}, "'修復前に本体 / 日本語化Modの重複キーについて優先先の指定が必要です。\\n\\n' + value + '\\n\\n総合診断の『本体/日本語化Mod重複』行を選択し、\\n『本体を残す』または『日本語化Modを残す』を設定してください。\\n設定後、左側の『設定した内容で修復を実行』を押してください。複数行や一括指定も使用できます。'"),
    ('p0.repair_complete_summary', {'count': 7, 'issues': 7}, "'修復・再診断完了' + f': {count} Mod / 要確認 {issues}件'"),
    ('p0.diagnostics_complete_summary', {'count': 7, 'issues': 7}, "'診断完了' + f': {count} Mod / 要確認 {issues}件'"),
    ('p0.post_repair_diagnostics_are_shown', {'value': 'Example'}, "value + '\\n\\n修復後の診断結果を一覧へ表示しています。'"),
    ('p0.full_diagnostics_error', {'value': 'Example'}, "'総合診断エラー: ' + value"),
    ('p0.target_mods', {'count': 7}, "f'対象Mod: {count}件'"),
    ('p0.searching_in_background', {'game': 'Example', 'done': 7, 'total': 7, 'mod': 'Example'}, "f'{game}: バックグラウンド検索中 {done}/{total} — {mod}'"),
    ('p0.searched_mods_matches_untranslated', {'game': 'Example', 'scanned_mods': 7, 'count': 7, 'missing': 7}, "f'{game}: {scanned_mods} Modを検索 / {count}件一致（未訳 {missing}件）'"),
    ('p0.translation_search_error', {'value': 'Example'}, "'翻訳検索エラー: ' + value"),
    ('p0.translation_complete_items_recovered_by', {'processed_items': 7, 'selected_total': 7, 'recovered': 7, 'unresolved': 7}, "f'翻訳完了: {processed_items}/{selected_total}項目 / 再試行で復旧 {recovered} / 未解決 {unresolved}'"),
    ('p0.translation_complete_unresolved_items', {'unresolved': 7}, "f'翻訳完了・未解決 {unresolved}項目'"),
    ('p0.translation_complete_unresolved_items_2', {'unresolved': 7}, "f'翻訳完了（未解決 {unresolved}項目）'"),
    ('p0.selected_translations_completed_completed_items', {'processed_items': 7, 'selected_total': 7, 'recovered': 7, 'unresolved': 7}, "f'選択した翻訳が完了しました。\\n完了: {processed_items}/{selected_total}項目\\n再試行で復旧: {recovered}項目\\n未解決: {unresolved}項目'"),
    ('p0.unattended_run_report', {'queue_report': 'Example'}, "f'\\n\\n夜間処理レポート:\\n{queue_report}'"),
    ('p0.translating_missing_entries', {'i': 7, 'total': 7, 'entry_key': 'Example'}, "f'差分翻訳中 {i}/{total} — {entry_key}'"),
    ('p0.missing_only_translation_completed_entries', {'written': 7}, "f'差分翻訳 {written}件が完了しました'"),
    ('p0.untranslated_entry', {'file': 'Example', 'entry_key': 'Example', 'reason': 'Example'}, "f'・{file} / {entry_key}: {reason}'"),
    ('p0.more_entries', {'value': 'Example'}, "f'\\nほか {value}件'"),
    ('p0.these_keys_could_not_be', {'lines': 'Example', 'more': 'Example'}, "f'次のキーは翻訳できなかったため、書き込まずに未翻訳のまま残しました。\\n\\n{lines}{more}\\n\\nモデルや設定を変えて、もう一度試してください。'"),
    ('p0.missing_only_translation_error', {'value': 'Example'}, "'差分翻訳エラー: ' + value"),
    ('p0.added_candidates_variants', {'added': 7, 'total': 7, 'conflicts': 7, 'kind_summary': 'Example'}, "f'追加 {added} / 候補 {total} / 表記揺れ {conflicts} / {kind_summary}'"),
    ('p0.auto_glossary_completed_candidates_new', {'total': 7, 'added': 7, 'conflicts': 7, 'kind_summary': 'Example'}, "f'自動用語作成が完了しました。\\n候補: {total}件\\n新規追加: {added}件\\n複数訳を統一: {conflicts}件\\n{kind_summary}'"),
    ('p0.auto_glossary_2', {'value': 'Example'}, "'自動用語作成: ' + value"),
    ('p0.auto_glossary_error', {'value': 'Example'}, "'自動用語作成エラー: ' + value"),
    ('p0.completed_2', {'label': 'Example'}, "f'{label}が完了しました。'"),
    ('p0.added_candidates', {'label': 'Example', 'added': 7, 'total': 7}, "f'{label}: {added}件追加 / 候補 {total}件'"),
    ('p0.candidates', {'total': 7}, "f'候補: {total}件'"),
    ('p0.new_entries', {'added': 7}, "f'新規追加: {added}件'"),
    ('p0.japanese_keys', {'japanese_keys': 7}, "f'日本語キー: {japanese_keys}件'"),
    ('p0.english_matches', {'english': 7}, "f'英語対応: {english}件'"),
    ('p0.chinese_matches', {'chinese': 7}, "f'中国語対応: {chinese}件'"),
    ('p0.unmatched', {'unmatched': 7}, "f'対応なし: {unmatched}件'"),
    ('p0.skipped_entries_with_no_matching', {'unmatched': 7}, "f'ゲーム本体に対応原文がないため {unmatched}件をスキップしました。'"),
    ('p0.glossary_import_error_2', {'value': 'Example'}, "'用語取り込みエラー: ' + value"),
    ('p0.ai_proofreading_error', {'payload': 'Example'}, "'AI校正エラー: ' + payload"),
    ('p0.local_server_guidance', {'service': 'LM Studio'}, 'f"{service}が起動していない、またはLocal Serverが開始されていない可能性があります。\\n\\n{service}を起動し、モデルを読み込んでサーバーを開始してから、再接続を確認してください。"'),
    ('p0.llm_server_guidance', {'service': 'Ollama'}, 'f"{service}が起動していない、またはLLMサーバーが開始されていない可能性があります。\\n\\n{service}を起動し、モデルを読み込んでサーバーを開始してから、再接続を確認してください。"'),
    ('p0.diff_complete', {'written': 7, 'spaces_removed': 3}, 'f"差分翻訳完了: 書き込み {written}件" + f" / 半角スペース除去 {spaces_removed}個"'),
    ('p0.diff_complete_untranslated', {'written': 7, 'spaces_removed': 3, 'count': 2}, 'f"差分翻訳完了: 書き込み {written}件" + f" / 半角スペース除去 {spaces_removed}個" + f" / 未翻訳のまま {count}件（原文のまま・使えない訳は書き込みませんでした）"'),
]


P0_OWNERS = [
    "_mod_status_empty_row",
    "_qa_failure_display",
    "<module>",
    "_japanese_glossary_only",
    "_target_language_problems",
    "_diff_translation_problem",
    "_llm_connection_alert_content",
    "_build_qa_log_payload",
    "load_persistent_json",
    "_collect_native_crash_reports",
    "_mark_runtime_started",
    "App.__init__",
    "App._poll_events",
    "App._build_ui",
    "App._active_file_operation_names",
    "App._active_shutdown_threads",
    "App._enable_ctrl_multiselect.on_ctrl_click",
    "App.save_close_behavior_settings",
    "App._show_close_choice_dialog",
    "App._request_worker_shutdown",
    "App._begin_graceful_exit",
    "App._poll_shutdown_completion",
    "App._finalize_app_exit",
    "App.discover_mod_locations",
    "App._collect_mod_roots_from_location_rows",
    "App._tk_callback_exception",
    "App._base_game_source_data_for_mod",
    "App._language_complete_notice_text",
    "App.save_and_stop",
    "App.save_session",
    "App._find_base_game_localization_root",
    "App._import_japanese_targets_with_fallback",
    "App._finish_controls"
]


@pytest.fixture(autouse=True)
def japanese_ui():
    previous = i18n.get_ui_language()
    missing, unknown = i18n.MISSING.copy(), i18n.UNKNOWN.copy()
    i18n.set_ui_language("japanese")
    yield
    i18n.set_ui_language(previous)
    i18n.MISSING.clear()
    i18n.MISSING.update(missing)
    i18n.UNKNOWN.clear()
    i18n.UNKNOWN.update(unknown)


@pytest.mark.parametrize("key,original", FIXED_ORIGINALS)
def test_fixed_japanese_matches_original(key, original):
    assert i18n.t(key) == original


@pytest.mark.parametrize("key,fields,original", DYNAMIC_ORIGINALS)
def test_dynamic_japanese_matches_original_expression(key, fields, original):
    assert i18n.t(key, **fields) == eval(original, {"__builtins__": {}}, fields)


def test_all_added_keys_have_independent_original_cases():
    cases = {key for key, _original in FIXED_ORIGINALS}
    cases.update(key for key, _fields, _original in DYNAMIC_ORIGINALS)
    source = Path(main.__file__).read_text(encoding="utf-8")
    referenced = {
        argument.value for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and node.args
        and ((isinstance(node.func, ast.Name) and node.func.id == "t")
             or (isinstance(node.func, ast.Attribute) and node.func.attr == "t"
                 and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"))
        for argument in ast.walk(node.args[0])
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        and argument.value.startswith("p0.")
    }
    assert cases <= referenced
    assert len(cases) == len(FIXED_ORIGINALS) + len(DYNAMIC_ORIGINALS)


def test_every_p0_key_is_english_without_fallback():
    i18n.set_ui_language("english")
    for key, original in japanese_p0.STRINGS.items():
        if not key.startswith("p0."):
            continue
        assert key in english_p0.STRINGS
        fields = {
            name: "Example" for _literal, name, _format, _conversion in Formatter().parse(original)
            if name is not None
        }
        missing_before = i18n.MISSING.copy()
        assert i18n.t(key, **fields) == english_p0.STRINGS[key].format_map(fields)
        assert i18n.MISSING == missing_before
        assert not re.search(r"[぀-ヿ一-鿿]", english_p0.STRINGS[key])


def test_new_placeholder_names_match_in_both_dictionaries():
    for key, _fields, _original in DYNAMIC_ORIGINALS:
        def names(text):
            return {name for _literal, name, _format, _conversion in Formatter().parse(text)
                    if name is not None}
        assert names(japanese_p0.STRINGS[key]) == names(english_p0.STRINGS[key])


def test_p0_has_no_pending_display_literals():
    from i18n_exclusions import EXCLUDED_VALUES
    from i18n_pending import PENDING
    from i18n_scan import japanese_strings

    path = Path(main.__file__)
    assert {entry: count for entry, (unit, count) in PENDING.items() if unit == "P0_shared"} == {
        "app/main.py::_llm_connection_alert_content": 1,
    }
    assert [(row["owner"], row["text"]) for row in japanese_strings(path)
            if row["owner"] in P0_OWNERS and row["text"] not in EXCLUDED_VALUES] == [
        ("_llm_connection_alert_content", "モデル"),
    ]


def test_target_language_note_is_lazy():
    japanese = main.target_lang_note()
    i18n.set_ui_language("english")
    assert japanese != main.target_lang_note()
    assert not re.search(r"[぀-ヿ一-鿿]", main.target_lang_note())


@pytest.mark.parametrize("provider,service,server_note", [
    ("lmstudio", "LM Studio", "Local Serverが開始されていない"),
    ("ollama", "Ollama", "LLMサーバーが開始されていない"),
])
def test_connection_guidance_keeps_japanese_and_category(provider, service, server_note):
    result = main._llm_connection_alert_content(provider, "http://localhost:1", error="connection refused")
    expected = (f"{service}が起動していない、または{server_note}可能性があります。\n\n"
                f"{service}を起動し、モデルを読み込んでサーバーを開始してから、再接続を確認してください。")
    assert result["message"].startswith(expected)
    assert result["category"] == "local_unavailable"
    i18n.set_ui_language("english")
    english = main._llm_connection_alert_content(provider, "http://localhost:1", error="connection refused")
    assert english["category"] == result["category"]
    assert not re.search(r"[぀-ヿ一-鿿]", english["message"])


@pytest.mark.parametrize("error", ["モデル not found", "読み込み済みモデルがありません"])
def test_connection_error_detection_does_not_depend_on_ui_language(error):
    for language in ("japanese", "english"):
        i18n.set_ui_language(language)
        assert main._llm_connection_alert_content("ollama", "http://localhost:1", "example", error)["category"] == "configuration"


def test_poll_events_uses_selected_language_without_tk():
    class Variable:
        def __init__(self):
            self.value = ""

        def set(self, value):
            self.value = value

    state = SimpleNamespace(
        events=queue.Queue(), benchmark_status_var=Variable(), after=lambda *_args: None,
        _refresh_operation_states=lambda: None, _poll_events=lambda: None,
    )
    for language, expected in (("japanese", "速度テスト中 2/3 — Example"),
                               ("english", "Speed test 2/3 — Example")):
        i18n.set_ui_language(language)
        state.events.put(("benchmark_model_start", (2, 3, "Example")))
        main.App._poll_events(state)
        assert state.benchmark_status_var.value == expected
        assert state.events.empty()


def test_dictionary_keys_are_unique():
    for module in (japanese_p0, english_p0):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        dictionary = next(node.value for node in tree.body
                          if isinstance(node, ast.Assign) and any(
                              isinstance(target, ast.Name) and target.id == "STRINGS"
                              for target in node.targets))
        keys = [node.value for node in dictionary.keys]
        assert len(keys) == len(set(keys))

