"""U5 display snapshots, without importing App or creating Tk windows."""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from string import Formatter
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import i18n
from i18n.english.u5_models import STRINGS as ENGLISH
from i18n.japanese.u5_models import STRINGS as JAPANESE

CASES = [
    (2685, 37, 2685, 78, 'u5.storage_frame', '自動生成ファイルの保存場所', {}, '"自動生成ファイルの保存場所"', "i18n.t('u5.storage_frame')"),
    (2688, 28, 2688, 48, 'u5.storage_folder', '保存フォルダ', {}, '"保存フォルダ"', "i18n.t('u5.storage_folder')"),
    (2690, 55, 2690, 78, 'u5.change_storage', '保存場所を変更', {}, '"保存場所を変更"', "i18n.t('u5.change_storage')"),
    (2693, 29, 2693, 52, 'u5.open_folder', 'フォルダを開く', {}, '"フォルダを開く"', "i18n.t('u5.open_folder')"),
    (2694, 29, 2694, 55, 'u5.open_error_logs', 'エラーログを開く', {}, '"エラーログを開く"', "i18n.t('u5.open_error_logs')"),
    (2695, 29, 2695, 52, 'u5.collect_logs', '診断ログを収集', {}, '"診断ログを収集"', "i18n.t('u5.collect_logs')"),
    (2696, 28, 2696, 265, 'u5.storage_note', '翻訳結果・キャッシュ・バックアップ・設定・セッション・モデル統計など、アプリが自動生成するデータはすべてこの『Paradox Localization Translator』フォルダ内にまとめます。', {}, '"翻訳結果・キャッシュ・バックアップ・設定・セッション・モデル統計など、アプリが自動生成するデータはすべてこの『Paradox Localization Translator』フォルダ内にまとめます。"', "i18n.t('u5.storage_note')"),
    (2698, 43, 2698, 101, 'u5.close_behavior', 'ウィンドウの×ボタンを押したときの動作', {}, '"ウィンドウの×ボタンを押したときの動作"', "i18n.t('u5.close_behavior')"),
    (2700, 34, 2700, 48, 'u5.default_action', '既定動作', {}, '"既定動作"', "i18n.t('u5.default_action')"),
    (2704, 34, 2704, 84, 'u5.close_recommendation', '通常は『毎回確認』を推奨します。', {}, '"通常は『毎回確認』を推奨します。"', "i18n.t('u5.close_recommendation')"),
    (2705, 35, 2705, 58, 'u5.save_setting', 'この設定を保存', {}, '"この設定を保存"', "i18n.t('u5.save_setting')"),
    (2707, 12, 2709, 148, 'u5.close_help', '毎回確認: ×ボタンを押すたびに『最小化 / 終了 / キャンセル』を選びます。\n最小化: 確認せずウィンドウだけを最小化し、翻訳・探索・LLM処理は続行します。\n終了: 確認せず、翻訳中ならセッションとキャッシュを保存して停止要求を出してから終了します。', {}, '"毎回確認: ×ボタンを押すたびに『最小化 / 終了 / キャンセル』を選びます。\\n"\n            "最小化: 確認せずウィンドウだけを最小化し、翻訳・探索・LLM処理は続行します。\\n"\n            "終了: 確認せず、翻訳中ならセッションとキャッシュを保存して停止要求を出してから終了します。"', "i18n.t('u5.close_help')"),
    (2712, 43, 2712, 63, 'u5.folder_structure', 'フォルダ構成', {}, '"フォルダ構成"', "i18n.t('u5.folder_structure')"),
    (2753, 41, 2753, 121, 'u5.storage_busy', '保存場所の変更はすでにバックグラウンドで実行中です。', {}, "'保存場所の変更はすでにバックグラウンドで実行中です。'", "i18n.t('u5.storage_busy')"),
    (2755, 45, 2755, 112, 'u5.choose_storage', 'Paradox Localization Translator フォルダの保存先を選択', {}, "'Paradox Localization Translator フォルダの保存先を選択'", "i18n.t('u5.choose_storage')"),
    (2759, 84, 2759, 122, 'u5.same_storage', '現在と同じ保存場所です。', {}, "'現在と同じ保存場所です。'", "i18n.t('u5.same_storage')"),
    (2761, 73, 2761, 133, 'u5.storage_unwritable', '選択した場所へ書き込めません。\n{new_root}', {'new_root': 'new_root'}, "f'選択した場所へ書き込めません。\\n{new_root}'", "i18n.t('u5.storage_unwritable', new_root=new_root)"),
    (2766, 31, 2766, 87, 'u5.storage_copying', '保存場所をバックグラウンドで変更中…', {}, "'保存場所をバックグラウンドで変更中…'", "i18n.t('u5.storage_copying')"),
    (2766, 100, 2766, 135, 'u5.storage_switching', '保存場所を切り替え中…', {}, "'保存場所を切り替え中…'", "i18n.t('u5.storage_switching')"),
    (2796, 64, 2796, 81, 'u5.model_stats', 'モデル統計', {}, '"モデル統計"', "i18n.t('u5.model_stats')"),
    (2796, 142, 2796, 171, 'u5.model_profiles', 'モデルプロファイル', {}, '"モデルプロファイル"', "i18n.t('u5.model_profiles')"),
    (2799, 91, 2799, 117, 'u5.classification_cache', 'Mod分類キャッシュ', {}, '"Mod分類キャッシュ"', "i18n.t('u5.classification_cache')"),
    (2801, 88, 2801, 111, 'u5.relation_settings', 'Mod関連付け設定', {}, '"Mod関連付け設定"', "i18n.t('u5.relation_settings')"),
    (2804, 35, 2804, 70, 'u5.storage_changed', '保存場所を変更しました', {}, "'保存場所を変更しました'", "i18n.t('u5.storage_changed')"),
    (2808, 25, 2808, 51, 'u5.storage_apply_error', '保存場所切替適用', {}, "'保存場所切替適用'", "i18n.t('u5.storage_apply_error')"),
    (2808, 88, 2808, 143, 'u5.storage_failed', '保存場所の変更に失敗しました。\n{exc}', {'exc': 'exc'}, "f'保存場所の変更に失敗しました。\\n{exc}'", "i18n.t('u5.storage_failed', exc=exc)"),
    (2996, 22, 2996, 108, 'u5.stable_note', '長文が多いMod、初回利用、メモリに余裕がない環境向けです。', {}, '"長文が多いMod、初回利用、メモリに余裕がない環境向けです。"', "i18n.t('u5.stable_note')"),
    (2997, 24, 2997, 119, 'u5.standard_note', '通常はこちらを推奨します。速度と安定性のバランスを優先します。', {}, '"通常はこちらを推奨します。速度と安定性のバランスを優先します。"', "i18n.t('u5.standard_note')"),
    (2998, 20, 2998, 156, 'u5.fast_note', '同時2リクエストを処理できる環境向けです。Ollama/LM Studio側の並列処理と十分なメモリが必要です。', {}, '"同時2リクエストを処理できる環境向けです。Ollama/LM Studio側の並列処理と十分なメモリが必要です。"', "i18n.t('u5.fast_note')"),
    (3001, 12, 3001, 32, 'u5.recommended_settings', 'おすすめ設定', {}, '"おすすめ設定"', "i18n.t('u5.recommended_settings')"),
    (3002, 12, 3010, 143, 'u5.preset_applied', '{name} を適用しました。\n\nバッチ: {batch}\n並列: {workers}\n\n{note}\n\n安定性の目安\n・バッチ 1–60: 通常範囲\n・バッチ 80超: 長文では応答欠落・タイムアウトに注意\n・バッチ 120超: 非推奨\n・並列 1: 最も安定\n・並列 2: サーバー側が同時処理できる場合のみ推奨\n・並列 3以上: ローカルLLMではVRAM/RAM圧迫、待ち行列、タイムアウトが増えやすい\n\nクラウドAPIでは並列数を上げられる場合がありますが、API側のレート制限を優先してください。', {'name': 'name', 'batch': 'batch', 'workers': 'workers', 'note': 'note'}, 'f"{name} を適用しました。\\n\\nバッチ: {batch}\\n並列: {workers}\\n\\n{note}\\n\\n"\n            "安定性の目安\\n"\n            "・バッチ 1–60: 通常範囲\\n"\n            "・バッチ 80超: 長文では応答欠落・タイムアウトに注意\\n"\n            "・バッチ 120超: 非推奨\\n"\n            "・並列 1: 最も安定\\n"\n            "・並列 2: サーバー側が同時処理できる場合のみ推奨\\n"\n            "・並列 3以上: ローカルLLMではVRAM/RAM圧迫、待ち行列、タイムアウトが増えやすい\\n\\n"\n            "クラウドAPIでは並列数を上げられる場合がありますが、API側のレート制限を優先してください。"', "i18n.t('u5.preset_applied', name=name, batch=batch, workers=workers, note=note)"),
    (5651, 25, 5651, 42, 'u5.save_llm_settings', 'LLM設定保存', {}, '"LLM設定保存"', "i18n.t('u5.save_llm_settings')"),
    (5689, 29, 5689, 55, 'u5.apply_translation_settings', '翻訳設定全体適用', {}, '"翻訳設定全体適用"', "i18n.t('u5.apply_translation_settings')"),
    (5690, 61, 5690, 108, 'u5.settings_failed', '設定の適用に失敗しました。\n{e}', {'e': 'e'}, 'f"設定の適用に失敗しました。\\n{e}"', "i18n.t('u5.settings_failed', e=e)"),
    (7578, 38, 7578, 49, 'u5.llm_connection', 'LLM接続', {}, '"LLM接続"', "i18n.t('u5.llm_connection')"),
    (7580, 28, 7580, 45, 'u5.provider', 'プロバイダ', {}, '"プロバイダ"', "i18n.t('u5.provider')"),
    (7585, 29, 7585, 64, 'u5.refresh_connection', '接続確認 / モデル再読込', {}, '"接続確認 / モデル再読込"', "i18n.t('u5.refresh_connection')"),
    (7587, 28, 7587, 39, 'u5.model', 'モデル', {}, '"モデル"', "i18n.t('u5.model')"),
    (7590, 28, 7590, 39, 'u5.api_key', 'APIキー', {}, '"APIキー"', "i18n.t('u5.api_key')"),
    (7592, 28, 7592, 157, 'u5.api_key_note', 'APIキーは保存しません。ローカル: Ollama / LM Studio\u3000クラウド: OpenAI / Anthropic / Gemini / OpenAI互換API', {}, '"APIキーは保存しません。ローカル: Ollama / LM Studio\u3000クラウド: OpenAI / Anthropic / Gemini / OpenAI互換API"', "i18n.t('u5.api_key_note')"),
    (7594, 40, 7594, 60, 'u5.common_settings', '翻訳共通設定', {}, '"翻訳共通設定"', "i18n.t('u5.common_settings')"),
    (7596, 30, 7596, 56, 'u5.game_preset', 'ゲームプリセット', {}, '"ゲームプリセット"', "i18n.t('u5.game_preset')"),
    (7598, 36, 7598, 74, 'u5.repair_existing', '既存{target_name}の未翻訳を修復', {'target_name': "i18n.t('lang.' + _current_target_lang(self))"}, '"既存日本語の未翻訳を修復"', "i18n.t('u5.repair_existing', target_name=i18n.t('lang.' + _current_target_lang(self)))"),
    (7599, 36, 7599, 103, 'u5.auto_qa', '通常翻訳後にバックアップ・自動QA・エラー修正', {}, '"通常翻訳後にバックアップ・自動QA・エラー修正"', "i18n.t('u5.auto_qa')"),
    (7600, 36, 7600, 112, 'u5.chinese_auto_qa', '中国語基準翻訳後にバックアップ・自動QA・エラー修正', {}, '"中国語基準翻訳後にバックアップ・自動QA・エラー修正"', "i18n.t('u5.chinese_auto_qa')"),
    (7601, 36, 7601, 110, 'u5.normalize_spacing', '日本語・中国語の文字の間の半角スペースを取り除く', {}, '"日本語・中国語の文字の間の半角スペースを取り除く"', "i18n.t('u5.normalize_spacing')"),
    (7602, 30, 7602, 41, 'u5.batch', 'バッチ', {}, '"バッチ"', "i18n.t('u5.batch')"),
    (7604, 30, 7604, 38, 'u5.workers', '並列', {}, '"並列"', "i18n.t('u5.workers')"),
    (7606, 30, 7606, 44, 'u5.recommended', 'おすすめ', {}, '"おすすめ"', "i18n.t('u5.recommended')"),
    (7609, 31, 7609, 60, 'u5.apply_preset', 'おすすめ設定を適用', {}, '"おすすめ設定を適用"', "i18n.t('u5.apply_preset')"),
    (7610, 30, 7610, 41, 'u5.glossary', '用語集', {}, '"用語集"', "i18n.t('u5.glossary')"),
    (7612, 31, 7612, 51, 'u5.choose_glossary', '用語集を選択', {}, '"用語集を選択"', "i18n.t('u5.choose_glossary')"),
    (7613, 30, 7613, 70, 'u5.batch_recommendation', '推奨: バッチ20–60 / 並列1–2', {}, '"推奨: バッチ20–60 / 並列1–2"', "i18n.t('u5.batch_recommendation')"),
    (7614, 66, 7614, 101, 'u5.apply_current_settings', '現在の翻訳へ設定を適用', {}, '"現在の翻訳へ設定を適用"', "i18n.t('u5.apply_current_settings')"),
    (7617, 41, 7617, 76, 'u5.profile_selection', 'モデルプロファイル選択', {}, '"モデルプロファイル選択"', "i18n.t('u5.profile_selection')"),
    (7622, 29, 7622, 37, 'u5.apply', '適用', {}, '"適用"', "i18n.t('u5.apply')"),
    (7623, 29, 7623, 37, 'u5.delete', '削除', {}, '"削除"', "i18n.t('u5.delete')"),
    (7624, 29, 7624, 52, 'u5.save_current_settings', '現在設定を保存', {}, '"現在設定を保存"', "i18n.t('u5.save_current_settings')"),
    (7626, 36, 7626, 77, 'u5.saved_profiles', '保存済みモデルプロファイル', {}, '"保存済みモデルプロファイル"', "i18n.t('u5.saved_profiles')"),
    (7628, 27, 7628, 68, 'u5.save_profile', '現在設定をプロファイル保存', {}, '"現在設定をプロファイル保存"', "i18n.t('u5.save_profile')"),
    (7629, 27, 7629, 44, 'u5.apply_selected', '選択を適用', {}, '"選択を適用"', "i18n.t('u5.apply_selected')"),
    (7630, 27, 7630, 44, 'u5.delete_selected', '選択を削除', {}, '"選択を削除"', "i18n.t('u5.delete_selected')"),
    (7634, 32, 7634, 40, 'u5.name', '名前', {}, '"名前"', "i18n.t('u5.name')"),
    (7634, 55, 7634, 63, 'u5.purpose', '用途', {}, '"用途"', "i18n.t('u5.purpose')"),
    (7634, 81, 7634, 89, 'u5.method', '方式', {}, '"方式"', "i18n.t('u5.method')"),
    (7634, 104, 7634, 115, 'u5.model', 'モデル', {}, '"モデル"', "i18n.t('u5.model')"),
    (7634, 130, 7634, 141, 'u5.batch', 'バッチ', {}, '"バッチ"', "i18n.t('u5.batch')"),
    (7634, 157, 7634, 165, 'u5.workers', '並列', {}, '"並列"', "i18n.t('u5.workers')"),
    (7643, 40, 7643, 105, 'u5.speed_comparison', 'モデル速度比較（実翻訳時の統計も自動記録）', {}, '"モデル速度比較（実翻訳時の統計も自動記録）"', "i18n.t('u5.speed_comparison')"),
    (7645, 28, 7645, 60, 'u5.benchmark_current', '現在のLLMを速度テスト', {}, '"現在のLLMを速度テスト"', "i18n.t('u5.benchmark_current')"),
    (7646, 28, 7646, 69, 'u5.benchmark_selected', '選択したモデルを比較テスト', {}, '"選択したモデルを比較テスト"', "i18n.t('u5.benchmark_selected')"),
    (7647, 52, 7647, 75, 'u5.stop_benchmark', '速度テスト停止', {}, '"速度テスト停止"', "i18n.t('u5.stop_benchmark')"),
    (7648, 28, 7648, 45, 'u5.clear_stats', '統計を消去', {}, '"統計を消去"', "i18n.t('u5.clear_stats')"),
    (7651, 45, 7651, 99, 'u5.choose_models', '比較するモデルを選択（最大5モデル）', {}, '"比較するモデルを選択（最大5モデル）"', "i18n.t('u5.choose_models')"),
    (7652, 34, 7652, 155, 'u5.multiselect_note', 'Ctrlキーを押しながらクリックすると複数選択できます。最大5モデルまで選択できます。', {}, '"Ctrlキーを押しながらクリックすると複数選択できます。最大5モデルまで選択できます。"', "i18n.t('u5.multiselect_note')"),
    (7658, 36, 7658, 53, 'u5.provider', 'プロバイダ', {}, '"プロバイダ"', "i18n.t('u5.provider')"),
    (7658, 68, 7658, 79, 'u5.model', 'モデル', {}, '"モデル"', "i18n.t('u5.model')"),
    (7658, 97, 7658, 105, 'u5.requests', '回数', {}, '"回数"', "i18n.t('u5.requests')"),
    (7658, 117, 7658, 128, 'u5.average_seconds', '平均秒', {}, '"平均秒"', "i18n.t('u5.average_seconds')"),
    (7658, 164, 7658, 175, 'u5.failure_rate', '失敗率', {}, '"失敗率"', "i18n.t('u5.failure_rate')"),
    (7713, 51, 7713, 92, 'u5.select_model', 'モデルを選択してください。', {}, '"モデルを選択してください。"', "i18n.t('u5.select_model')"),
    (7723, 38, 7723, 98, 'u5.benchmark_limit_status', '比較テストは最大5モデルまで選択できます', {}, '"比較テストは最大5モデルまで選択できます"', "i18n.t('u5.benchmark_limit_status')"),
    (7730, 41, 7730, 102, 'u5.select_comparison_models', '比較するモデルを1〜5個選択してください。', {}, '"比較するモデルを1〜5個選択してください。"', "i18n.t('u5.select_comparison_models')"),
    (7733, 41, 7733, 107, 'u5.benchmark_limit', '比較テストで選択できるのは最大5モデルです。', {}, '"比較テストで選択できるのは最大5モデルです。"', "i18n.t('u5.benchmark_limit')"),
    (7740, 38, 7740, 92, 'u5.benchmark_starting', '速度テスト中 0/{count} — 開始準備', {'count': 'len(models)'}, 'f"速度テスト中 0/{len(models)} — 開始準備"', "i18n.t('u5.benchmark_starting', count=len(models))"),
    (7741, 29, 7741, 55, 'u5.model_benchmark', 'モデル速度テスト', {}, '"モデル速度テスト"', "i18n.t('u5.model_benchmark')"),
    (7773, 42, 7773, 127, 'u5.benchmark_stop_requested', '速度テスト停止要求済み — 現在のLLM応答完了を待っています', {}, '"速度テスト停止要求済み — 現在のLLM応答完了を待っています"', "i18n.t('u5.benchmark_stop_requested')"),
    (7775, 36, 7775, 113, 'u5.api_stop_requested', '停止要求済み — 現在のAPI/LLM応答が返り次第停止します', {}, '"停止要求済み — 現在のAPI/LLM応答が返り次第停止します"', "i18n.t('u5.api_stop_requested')"),
    (7778, 40, 7778, 96, 'u5.confirm_clear_stats', 'モデル速度統計をすべて消去しますか？', {}, '"モデル速度統計をすべて消去しますか？"', "i18n.t('u5.confirm_clear_stats')"),
    (7791, 36, 7791, 65, 'u5.model_profiles', 'モデルプロファイル', {}, '"モデルプロファイル"', "i18n.t('u5.model_profiles')"),
    (7791, 66, 7791, 121, 'u5.profile_name', 'プロファイル名（例: Qwen 30B 品質重視）', {}, '"プロファイル名（例: Qwen 30B 品質重視）"', "i18n.t('u5.profile_name')"),
    (7793, 37, 7793, 66, 'u5.model_profiles', 'モデルプロファイル', {}, '"モデルプロファイル"', "i18n.t('u5.model_profiles')"),
    (7793, 67, 7793, 113, 'u5.profile_purpose', '用途メモ（例: 品質重視 / 高速）', {}, '"用途メモ（例: 品質重視 / 高速）"', "i18n.t('u5.profile_purpose')"),
    (7814, 42, 7814, 113, 'u5.select_profile_delete', '削除するモデルプロファイルを選択してください。', {}, '"削除するモデルプロファイルを選択してください。"', "i18n.t('u5.select_profile_delete')"),
    (7826, 41, 7826, 112, 'u5.select_profile_delete', '削除するモデルプロファイルを選択してください。', {}, '"削除するモデルプロファイルを選択してください。"', "i18n.t('u5.select_profile_delete')"),
    (7828, 44, 7828, 110, 'u5.confirm_delete_profile', 'モデルプロファイル『{name}』を削除しますか？', {'name': 'name'}, 'f"モデルプロファイル『{name}』を削除しますか？"', "i18n.t('u5.confirm_delete_profile', name=name)"),
    (7929, 61, 7929, 84, 'u5.cache_registry', 'キャッシュ台帳', {}, '"キャッシュ台帳"', "i18n.t('u5.cache_registry')"),
    (8388, 18, 8388, 76, 'u5.cache_title', 'キャッシュを見る — {filename}', {'filename': "Path(item['input']).name"}, 'f"キャッシュを見る — {Path(item[\'input\']).name}"', "i18n.t('u5.cache_title', filename=Path(item['input']).name)"),
    (8391, 28, 8391, 60, 'u5.cache_path', 'キャッシュ: {cache_path}', {'cache_path': 'cache_path'}, 'f"キャッシュ: {cache_path}"', "i18n.t('u5.cache_path', cache_path=cache_path)"),
    (8392, 28, 8392, 46, 'u5.entry_count', '{count}件', {'count': 'len(cache)'}, 'f"{len(cache)}件"', "i18n.t('u5.entry_count', count=len(cache))"),
    (8394, 29, 8394, 52, 'u5.open_storage', '保存場所を開く', {}, '"保存場所を開く"', "i18n.t('u5.open_storage')"),
    (8395, 29, 8395, 47, 'u5.reload_json', 'JSONを再読込', {}, '"JSONを再読込"', "i18n.t('u5.reload_json')"),
    (8413, 47, 8413, 85, 'u5.choose_cache', '追加するキャッシュを選択', {}, '"追加するキャッシュを選択"', "i18n.t('u5.choose_cache')"),
    (8419, 33, 8419, 90, 'u5.cache_not_dictionary', 'キャッシュJSONが辞書形式ではありません', {}, '"キャッシュJSONが辞書形式ではありません"', "i18n.t('u5.cache_not_dictionary')"),
    (8421, 54, 8421, 200, 'u5.confirm_import_cache', '{count}件のキャッシュを追加します。\n同じキーがある場合、追加するキャッシュで上書きしますか？', {'count': 'len(imported)'}, 'f"{len(imported)}件のキャッシュを追加します。\\n同じキーがある場合、追加するキャッシュで上書きしますか？"', "i18n.t('u5.confirm_import_cache', count=len(imported))"),
    (8429, 42, 8429, 130, 'u5.cache_imported', 'キャッシュを追加しました。\n現在: {count}件\n保存先: {dst_path}', {'count': 'len(dst)', 'dst_path': 'dst_path'}, 'f"キャッシュを追加しました。\\n現在: {len(dst)}件\\n保存先: {dst_path}"', "i18n.t('u5.cache_imported', count=len(dst), dst_path=dst_path)"),
    (8431, 43, 8431, 99, 'u5.cache_import_failed', 'キャッシュの追加に失敗しました。\n{e}', {'e': 'e'}, 'f"キャッシュの追加に失敗しました。\\n{e}"', "i18n.t('u5.cache_import_failed', e=e)"),
    (9033, 25, 9033, 63, 'u5.save_shared_state', '共通Mod状態キャッシュ保存', {}, '"共通Mod状態キャッシュ保存"', "i18n.t('u5.save_shared_state')"),
    (9626, 32, 9626, 53, 'u5.llm_disconnected', '● LLM接続なし', {}, '"● LLM接続なし"', "i18n.t('u5.llm_disconnected')"),
    (9627, 32, 9627, 145, 'u5.connection_check_note', '{provider} / {endpoint} — 起動状態・モデル・接続設定を確認してください', {'provider': "info['provider']", 'endpoint': "info['endpoint']"}, 'f"{info[\'provider\']} / {info[\'endpoint\']} — 起動状態・モデル・接続設定を確認してください"', "i18n.t('u5.connection_check_note', provider=info['provider'], endpoint=info['endpoint'])"),
    (9640, 87, 9640, 98, 'u5.llm_task', 'LLM処理', {}, '"LLM処理"', "i18n.t('u5.llm_task')"),
    (9659, 28, 9659, 67, 'u5.cannot_start', '{context}を開始できません。', {'context': 'context'}, 'f"{context}を開始できません。"', "i18n.t('u5.cannot_start', context=context)"),
    (9675, 32, 9675, 52, 'u5.retry_connection', '再接続を確認', {}, '"再接続を確認"', "i18n.t('u5.retry_connection')"),
    (9676, 32, 9676, 49, 'u5.open_settings', '設定を開く', {}, '"設定を開く"', "i18n.t('u5.open_settings')"),
    (9677, 32, 9677, 49, 'u5.cancel_task', '処理を中止', {}, '"処理を中止"', "i18n.t('u5.cancel_task')"),
    (9687, 32, 9687, 64, 'u5.checking_connection', '{provider} 接続確認中…', {'provider': 'provider'}, 'f"{provider} 接続確認中…"', "i18n.t('u5.checking_connection', provider=provider)"),
    (9688, 32, 9688, 57, 'u5.llm_checking', '● LLM 接続確認中', {}, '"● LLM 接続確認中"', "i18n.t('u5.llm_checking')"),
    (9693, 39, 9693, 101, 'u5.no_translation_model', '翻訳に使用するモデルが選択されていません', {}, '"翻訳に使用するモデルが選択されていません"', "i18n.t('u5.no_translation_model')"),
    (9696, 39, 9696, 125, 'u5.no_loaded_models', '接続には成功しましたが、読み込み済みのモデルがありません', {}, '"接続には成功しましたが、読み込み済みのモデルがありません"', "i18n.t('u5.no_loaded_models')"),
    (9708, 41, 9708, 82, 'u5.connection_check_busy', '現在LLMの接続を確認中です。', {}, '"現在LLMの接続を確認中です。"', "i18n.t('u5.connection_check_busy')"),
    (9724, 32, 9724, 94, 'u5.connected_models', '{provider} 接続済み / {count}モデル', {'provider': "request['provider']", 'count': 'len(models)'}, 'f"{request[\'provider\']} 接続済み / {len(models)}モデル"', "i18n.t('u5.connected_models', provider=request['provider'], count=len(models))"),
    (9725, 27, 9725, 42, 'u5.llm_idle', 'LLM 待機中', {}, '"LLM 待機中"', "i18n.t('u5.llm_idle')"),
    (9725, 43, 9725, 78, 'u5.connection_checked', '接続確認が完了しました', {}, '"接続確認が完了しました"', "i18n.t('u5.connection_checked')"),
    (9733, 42, 9733, 80, 'u5.connection_failed', 'LLM接続確認に失敗しました', {}, '"LLM接続確認に失敗しました"', "i18n.t('u5.connection_failed')"),
    (9734, 21, 9734, 47, 'u5.preflight_error', 'LLM開始前接続確認', {}, '"LLM開始前接続確認"', "i18n.t('u5.preflight_error')"),
    (9742, 36, 9742, 75, 'u5.missing_api_key', '{label}: APIキーが未設定です', {'label': 'label'}, 'f"{label}: APIキーが未設定です"', "i18n.t('u5.missing_api_key', label=label)"),
    (9744, 36, 9744, 65, 'u5.checking_connection', '{provider} 接続確認中…', {'provider': 'label'}, 'f"{label} 接続確認中…"', "i18n.t('u5.checking_connection', provider=label)"),
    (9755, 35, 9755, 121, 'u5.no_loaded_models', '接続には成功しましたが、読み込み済みのモデルがありません', {}, '"接続には成功しましたが、読み込み済みのモデルがありません"', "i18n.t('u5.no_loaded_models')"),
    (11312, 15, 11312, 76, 'u5.response_meta', '{received} / {provider} / {model} / {count:,}文字', {'received': 'received', 'provider': 'provider', 'model': 'model', 'count': 'len(content)'}, 'f"{received} / {provider} / {model} / {len(content):,}文字"', "i18n.t('u5.response_meta', received=received, provider=provider, model=model, count=len(content))"),
    (11334, 45, 11334, 62, 'u5.waiting_response', '応答待機中', {}, '"応答待機中"', "i18n.t('u5.waiting_response')"),
    (11335, 47, 11335, 64, 'u5.waiting_response', '応答待機中', {}, '"応答待機中"', "i18n.t('u5.waiting_response')"),
    (11339, 49, 11339, 66, 'u5.waiting_response', '応答待機中', {}, '"応答待機中"', "i18n.t('u5.waiting_response')"),
    (11340, 51, 11340, 68, 'u5.waiting_response', '応答待機中', {}, '"応答待機中"', "i18n.t('u5.waiting_response')"),
    (11348, 42, 11348, 80, 'u5.no_response', 'まだLLM応答はありません。', {}, '"まだLLM応答はありません。"', "i18n.t('u5.no_response')"),
    (11376, 37, 11376, 48, 'u5.llm_task', 'LLM処理', {}, '"LLM処理"', "i18n.t('u5.llm_task')"),
    (11377, 36, 11377, 65, 'u5.llm_running', '● LLM 動作中 — {op}', {'op': 'op'}, 'f"● LLM 動作中 — {op}"', "i18n.t('u5.llm_running', op=op)"),
    (11378, 36, 11378, 91, 'u5.llm_waiting', '{provider} / {model} — 応答を待っています', {'provider': 'provider', 'model': 'model'}, 'f"{provider} / {model} — 応答を待っています"', "i18n.t('u5.llm_waiting', provider=provider, model=model)"),
    (11382, 36, 11382, 99, 'u5.llm_retrying', '● LLM 再試行中 — {operation}', {'operation': "self.llm_operation or i18n.t('u5.llm_task')"}, 'f"● LLM 再試行中 — {self.llm_operation or \'LLM処理\'}"', "i18n.t('u5.llm_retrying', operation=self.llm_operation or i18n.t('u5.llm_task'))"),
    (11383, 36, 11383, 127, 'u5.llm_retry_detail', '{provider} / {model} — 再試行 {attempt}/{retries}', {'provider': 'provider', 'model': 'model', 'attempt': "payload.get('attempt', 0)", 'retries': "payload.get('retries', 0)"}, 'f"{provider} / {model} — 再試行 {payload.get(\'attempt\',0)}/{payload.get(\'retries\',0)}"', "i18n.t('u5.llm_retry_detail', provider=provider, model=model, attempt=payload.get('attempt', 0), retries=payload.get('retries', 0))"),
    (11388, 35, 11388, 50, 'u5.llm_idle', 'LLM 待機中', {}, '"LLM 待機中"', "i18n.t('u5.llm_idle')"),
    (11388, 52, 11388, 93, 'u5.llm_finished', '直前のLLM処理が終了しました', {}, '"直前のLLM処理が終了しました"', "i18n.t('u5.llm_finished')"),
    (11393, 78, 11393, 89, 'u5.llm_task', 'LLM処理', {}, '"LLM処理"', "i18n.t('u5.llm_task')"),
    (11402, 32, 11402, 60, 'u5.elapsed', '{base} / 経過 {seconds}秒', {'base': 'base', 'seconds': 'secs'}, 'f"{base} / 経過 {secs}秒"', "i18n.t('u5.elapsed', base=base, seconds=secs)"),
    (11405, 34, 11405, 49, 'u5.llm_idle', 'LLM 待機中', {}, '"LLM 待機中"', "i18n.t('u5.llm_idle')"),
    (11405, 57, 11405, 98, 'u5.llm_not_running', 'LLM処理は実行されていません', {}, '"LLM処理は実行されていません"', "i18n.t('u5.llm_not_running')"),
    (11421, 36, 11421, 71, 'u5.qa_stop_requested', 'QA自動修正 停止要求済み', {}, '"QA自動修正 停止要求済み"', "i18n.t('u5.qa_stop_requested')"),
    (11422, 36, 11422, 105, 'u5.safe_stop_note', '現在のAPI/LLM応答完了後、安全な位置で停止します', {}, '"現在のAPI/LLM応答完了後、安全な位置で停止します"', "i18n.t('u5.safe_stop_note')"),
    (11429, 38, 11429, 133, 'u5.diff_stop_requested', '差分翻訳の停止を要求しました。現在のLLM応答完了後に停止します。', {}, '"差分翻訳の停止を要求しました。現在のLLM応答完了後に停止します。"', "i18n.t('u5.diff_stop_requested')"),
    (11430, 36, 11430, 110, 'u5.waiting_stop', '停止要求済み — 現在のAPI/LLM応答完了を待っています', {}, '"停止要求済み — 現在のAPI/LLM応答完了を待っています"', "i18n.t('u5.waiting_stop')"),
    (11434, 32, 11434, 123, 'u5.proofread_stop_requested', 'AI校正の停止を要求しました。現在のLLM応答完了後に停止します。', {}, '"AI校正の停止を要求しました。現在のLLM応答完了後に停止します。"', "i18n.t('u5.proofread_stop_requested')"),
    (11435, 36, 11435, 110, 'u5.waiting_stop', '停止要求済み — 現在のAPI/LLM応答完了を待っています', {}, '"停止要求済み — 現在のAPI/LLM応答完了を待っています"', "i18n.t('u5.waiting_stop')"),
    (2762, 47, 2762, 376, 'u5.confirm_storage_change', '自動生成ファイルの保存場所を変更します。\n\n現在: {old_root}\n変更後: {new_root}\n\n［はい］: 現在のデータを新しい場所へコピーしてから切り替える\n［いいえ］: データは移動せず、今後の生成先だけ変更する\n［キャンセル］: 変更しない', {'old_root': 'old_root', 'new_root': 'new_root'}, "'自動生成ファイルの保存場所を変更します。\\n\\n'+f'現在: {old_root}\\n変更後: {new_root}\\n\\n'+'［はい］: 現在のデータを新しい場所へコピーしてから切り替える\\n［いいえ］: データは移動せず、今後の生成先だけ変更する\\n［キャンセル］: 変更しない'", "i18n.t('u5.confirm_storage_change', old_root=old_root, new_root=new_root)"),
    (2806, 45, 2806, 243, 'u5.storage_changed_copy', '保存場所を変更しました。\n\n{root}\n\n既存データもコピーしました。', {'root': 'str(DATA_ROOT)'}, "'保存場所を変更しました。\\n\\n'+str(DATA_ROOT)+'\\n\\n'+('既存データもコピーしました。' if copied else '今後作成するデータから新しい場所を使用します。')", "i18n.t('u5.storage_changed_copy', root=str(DATA_ROOT))"),
    (2806, 45, 2806, 243, 'u5.storage_changed_new', '保存場所を変更しました。\n\n{root}\n\n今後作成するデータから新しい場所を使用します。', {'root': 'str(DATA_ROOT)'}, "'保存場所を変更しました。\\n\\n'+str(DATA_ROOT)+'\\n\\n'+('既存データもコピーしました。' if copied else '今後作成するデータから新しい場所を使用します。')", "i18n.t('u5.storage_changed_new', root=str(DATA_ROOT))"),
    (5694, 16, 5695, 166, 'u5.settings_applied', '現在の翻訳設定を適用しました。\n\nQAのAI校正と差分翻訳は、この画面で現在選択されているプロバイダ・URL・モデル・用語集を使用します。', {}, '"現在の翻訳設定を適用しました。\\n\\nQAのAI校正と差分翻訳は、この画面で現在選択されているプロバイダ・URL・モデル・用語集を使用します。"\n                + ("\\n実行中の通常翻訳は次のバッチから切り替わります。" if self.controller and self.worker and self.worker.is_alive() else "")', "i18n.t('u5.settings_applied')"),
    (5694, 16, 5695, 166, 'u5.settings_applied_running', '現在の翻訳設定を適用しました。\n\nQAのAI校正と差分翻訳は、この画面で現在選択されているプロバイダ・URL・モデル・用語集を使用します。\n実行中の通常翻訳は次のバッチから切り替わります。', {}, '"現在の翻訳設定を適用しました。\\n\\nQAのAI校正と差分翻訳は、この画面で現在選択されているプロバイダ・URL・モデル・用語集を使用します。"\n                + ("\\n実行中の通常翻訳は次のバッチから切り替わります。" if self.controller and self.worker and self.worker.is_alive() else "")', "i18n.t('u5.settings_applied_running')"),
    (7817, 45, 7817, 127, 'u5.confirm_delete_profiles', '次のモデルプロファイルを削除しますか？\n\n{names}', {'names': '"\\n".join(names)'}, '"次のモデルプロファイルを削除しますか？\\n\\n" + "\\n".join(names)', 'i18n.t(\'u5.confirm_delete_profiles\', names="\\n".join(names))'),
    (11326, 55, 11326, 101, 'u5.response_truncated', '…（前半省略）…\n{content}', {'content': 'content[-8000:]'}, '"…（前半省略）…\\n" + content[-8000:]', "i18n.t('u5.response_truncated', content=content[-8000:])"),
    (11351, 18, 11351, 80, 'u5.discovery_response_title', '探索用LLM 応答全文', {}, '("探索用" if monitor else "翻訳用") + "LLM 応答全文"', "i18n.t('u5.discovery_response_title')"),
    (11351, 18, 11351, 80, 'u5.translation_response_title', '翻訳用LLM 応答全文', {}, '("探索用" if monitor else "翻訳用") + "LLM 応答全文"', "i18n.t('u5.translation_response_title')"),
    (2717, 12, 2745, 128, 'u5.folder_tree', 'Paradox Localization Translator/\n├── 翻訳結果/\n├── キャッシュ/\n│   ├── mod_translation_status_cache.json\n│   ├── mod_classification_cache.json\n│   ├── mod_relation_overrides.json\n│   ├── translation_status_state.json\n│   ├── diagnostic_state.json\n│   └── shared_mod_state_cache.json\n├── バックアップ/\n├── ログ/\n│   ├── QA/\n│   ├── エラー/\n│   ├── 日本語化Mod判定/\n│   ├── 診断/\n│   ├── 夜間処理/\n│   └── システム・履歴/\n├── 作業データ/  ← バージョン非依存の一時・作業状態用\n└── 設定/\n    ├── session.json\n    ├── resume_state.json\n    ├── storage_migration.json\n    ├── glossary.json\n    ├── model_stats.json\n    ├── model_profiles.json\n    ├── steam_library_roots.json\n    └── app_preferences.json  ← 前回LLM設定・×ボタン動作\n\n既定位置: 書類/Documents/Paradox Localization Translator\n［保存場所を変更］から、別ドライブ・外付けSSD・任意のフォルダへ移動できます。', {}, '"Paradox Localization Translator/\\n"\n            "├── 翻訳結果/\\n"\n            "├── キャッシュ/\\n"\n            "│   ├── mod_translation_status_cache.json\\n"\n            "│   ├── mod_classification_cache.json\\n"\n            "│   ├── mod_relation_overrides.json\\n"\n            "│   ├── translation_status_state.json\\n"\n            "│   ├── diagnostic_state.json\\n"\n            "│   └── shared_mod_state_cache.json\\n"\n            "├── バックアップ/\\n"\n            "├── ログ/\\n"\n            "│   ├── QA/\\n"\n            "│   ├── エラー/\\n"\n            "│   ├── 日本語化Mod判定/\\n"\n            "│   ├── 診断/\\n"\n            "│   ├── 夜間処理/\\n"\n            "│   └── システム・履歴/\\n"\n            "├── 作業データ/  ← バージョン非依存の一時・作業状態用\\n"\n            "└── 設定/\\n"\n            "    ├── session.json\\n"\n            "    ├── resume_state.json\\n"\n            "    ├── storage_migration.json\\n"\n            "    ├── glossary.json\\n"\n            "    ├── model_stats.json\\n"\n            "    ├── model_profiles.json\\n"\n            "    ├── steam_library_roots.json\\n"\n            "    └── app_preferences.json  ← 前回LLM設定・×ボタン動作\\n\\n"\n            "既定位置: 書類/Documents/Paradox Localization Translator\\n"\n            "［保存場所を変更］から、別ドライブ・外付けSSD・任意のフォルダへ移動できます。"', "i18n.t('u5.folder_tree')"),
]

EXPECTED_ENGLISH = {
    'u5.storage_frame': 'Generated data location',
    'u5.storage_folder': 'Storage folder',
    'u5.change_storage': 'Change location',
    'u5.open_folder': 'Open folder',
    'u5.open_error_logs': 'Open error logs',
    'u5.collect_logs': 'Collect diagnostic logs',
    'u5.storage_note': 'All app-generated data, including translations, caches, backups, settings, sessions, and model statistics, is stored in this “Paradox Localization Translator” folder.',
    'u5.close_behavior': 'Window close-button behavior',
    'u5.default_action': 'Default action',
    'u5.close_recommendation': '“Ask every time” is recommended.',
    'u5.save_setting': 'Save this setting',
    'u5.close_help': 'Ask every time: Choose “Minimize / Quit / Cancel” whenever you click ×.\nMinimize: Minimize the window without asking; translation, discovery, and LLM tasks continue.\nQuit: Quit without asking; if translating, save the session and cache and request a stop first.',
    'u5.folder_structure': 'Folder structure',
    'u5.storage_busy': 'The storage location is already being changed in the background.',
    'u5.choose_storage': 'Choose a location for the Paradox Localization Translator folder',
    'u5.same_storage': 'This is the current storage location.',
    'u5.storage_unwritable': 'Cannot write to the selected location.\n{new_root}',
    'u5.storage_copying': 'Changing storage location in the background…',
    'u5.storage_switching': 'Switching storage location…',
    'u5.model_stats': 'Model statistics',
    'u5.model_profiles': 'Model profiles',
    'u5.classification_cache': 'Mod classification cache',
    'u5.relation_settings': 'Mod relation settings',
    'u5.storage_changed': 'Storage location changed',
    'u5.storage_apply_error': 'Apply storage location change',
    'u5.storage_failed': 'Failed to change storage location.\n{exc}',
    'u5.stable_note': 'For mods with long text, first-time users, or systems with limited memory.',
    'u5.standard_note': 'Recommended for most users. Balances speed and stability.',
    'u5.fast_note': 'For systems that can handle two simultaneous requests. Requires parallel processing in Ollama/LM Studio and sufficient memory.',
    'u5.recommended_settings': 'Recommended settings',
    'u5.preset_applied': 'Applied {name}.\n\nBatch: {batch}\nParallel requests: {workers}\n\n{note}\n\nStability guidelines\n• Batch 1–60: Normal range\n• Batch over 80: Long text may cause missing responses or timeouts\n• Batch over 120: Not recommended\n• Parallel requests 1: Most stable\n• Parallel requests 2: Recommended only if the server supports concurrent processing\n• Parallel requests 3 or more: Local LLMs are more prone to VRAM/RAM pressure, queuing, and timeouts\n\nCloud APIs may allow more parallel requests, but respect the API rate limits.',
    'u5.save_llm_settings': 'Save LLM settings',
    'u5.apply_translation_settings': 'Apply translation settings everywhere',
    'u5.settings_failed': 'Failed to apply settings.\n{e}',
    'u5.llm_connection': 'LLM connection',
    'u5.provider': 'Provider',
    'u5.refresh_connection': 'Check connection / Reload models',
    'u5.model': 'Model',
    'u5.api_key': 'API key',
    'u5.api_key_note': 'API keys are not saved. Local: Ollama / LM Studio\u3000Cloud: OpenAI / Anthropic / Gemini / OpenAI-compatible API',
    'u5.common_settings': 'Shared translation settings',
    'u5.game_preset': 'Game preset',
    'u5.repair_existing': 'Repair untranslated text in existing {target_name}',
    'u5.auto_qa': 'Back up, run automatic QA, and fix errors after normal translation',
    'u5.chinese_auto_qa': 'Back up, run automatic QA, and fix errors after Chinese-based translation',
    'u5.normalize_spacing': 'Remove spaces between Japanese/Chinese characters',
    'u5.batch': 'Batch',
    'u5.workers': 'Parallel requests',
    'u5.recommended': 'Recommended',
    'u5.apply_preset': 'Apply recommended settings',
    'u5.glossary': 'Glossary',
    'u5.choose_glossary': 'Choose Glossary',
    'u5.batch_recommendation': 'Recommended: Batch 20–60 / Parallel requests 1–2',
    'u5.apply_current_settings': 'Apply settings to current translation',
    'u5.profile_selection': 'Select model profile',
    'u5.apply': 'Apply',
    'u5.delete': 'Delete',
    'u5.save_current_settings': 'Save current settings',
    'u5.saved_profiles': 'Saved model profiles',
    'u5.save_profile': 'Save current settings as a profile',
    'u5.apply_selected': 'Apply selected',
    'u5.delete_selected': 'Delete selected',
    'u5.name': 'Name',
    'u5.purpose': 'Purpose',
    'u5.method': 'Provider type',
    'u5.speed_comparison': 'Model speed comparison (translation statistics are recorded automatically)',
    'u5.benchmark_current': 'Test current LLM speed',
    'u5.benchmark_selected': 'Compare selected models',
    'u5.stop_benchmark': 'Stop speed test',
    'u5.clear_stats': 'Clear statistics',
    'u5.choose_models': 'Select models to compare (up to 5)',
    'u5.multiselect_note': 'Hold Ctrl and click to select multiple models. You can select up to 5 models.',
    'u5.requests': 'Requests',
    'u5.average_seconds': 'Average seconds',
    'u5.failure_rate': 'Failure rate',
    'u5.select_model': 'Select a model.',
    'u5.benchmark_limit_status': 'You can select up to 5 models for comparison',
    'u5.select_comparison_models': 'Select 1–5 models to compare.',
    'u5.benchmark_limit': 'You can select at most 5 models for comparison.',
    'u5.benchmark_starting': 'Speed test 0/{count} — Preparing',
    'u5.model_benchmark': 'Model speed test',
    'u5.benchmark_stop_requested': 'Speed test stop requested — Waiting for the current LLM response',
    'u5.api_stop_requested': 'Stop requested — Will stop when the current API/LLM response arrives',
    'u5.confirm_clear_stats': 'Clear all model speed statistics?',
    'u5.profile_name': 'Profile name (e.g. Qwen 30B Quality)',
    'u5.profile_purpose': 'Purpose note (e.g. Quality / Speed)',
    'u5.select_profile_delete': 'Select a model profile to delete.',
    'u5.confirm_delete_profile': 'Delete model profile “{name}”?',
    'u5.cache_registry': 'Cache registry',
    'u5.cache_title': 'View cache — {filename}',
    'u5.cache_path': 'Cache: {cache_path}',
    'u5.entry_count': '{count} entries',
    'u5.open_storage': 'Open storage location',
    'u5.reload_json': 'Reload JSON',
    'u5.choose_cache': 'Select a cache to import',
    'u5.cache_not_dictionary': 'Cache JSON is not a dictionary',
    'u5.confirm_import_cache': 'Import {count} cache entries.\nOverwrite matching keys with entries from the imported cache?',
    'u5.cache_imported': 'Cache imported.\nCurrent entries: {count}\nSaved to: {dst_path}',
    'u5.cache_import_failed': 'Failed to import cache.\n{e}',
    'u5.save_shared_state': 'Save shared mod state cache',
    'u5.llm_disconnected': '● LLM disconnected',
    'u5.connection_check_note': '{provider} / {endpoint} — Check server status, model, and connection settings',
    'u5.llm_task': 'LLM task',
    'u5.cannot_start': 'Cannot start {context}.',
    'u5.retry_connection': 'Check connection again',
    'u5.open_settings': 'Open settings',
    'u5.cancel_task': 'Cancel task',
    'u5.checking_connection': '{provider} checking connection…',
    'u5.llm_checking': '● LLM checking connection',
    'u5.no_translation_model': 'No model selected for translation',
    'u5.no_loaded_models': 'Connected, but no models are loaded',
    'u5.connection_check_busy': 'The LLM connection is currently being checked.',
    'u5.connected_models': '{provider} connected / {count} models',
    'u5.llm_idle': 'LLM idle',
    'u5.connection_checked': 'Connection check complete',
    'u5.connection_failed': 'LLM connection check failed',
    'u5.preflight_error': 'LLM preflight connection check',
    'u5.missing_api_key': '{label}: API key not set',
    'u5.response_meta': '{received} / {provider} / {model} / {count:,} characters',
    'u5.waiting_response': 'Waiting for response',
    'u5.no_response': 'No LLM response yet.',
    'u5.llm_running': '● LLM running — {op}',
    'u5.llm_waiting': '{provider} / {model} — Waiting for response',
    'u5.llm_retrying': '● LLM retrying — {operation}',
    'u5.llm_retry_detail': '{provider} / {model} — Retry {attempt}/{retries}',
    'u5.llm_finished': 'The previous LLM task has finished',
    'u5.elapsed': '{base} / Elapsed {seconds}s',
    'u5.llm_not_running': 'No LLM task is running',
    'u5.qa_stop_requested': 'QA auto-correction stop requested',
    'u5.safe_stop_note': 'Will stop at a safe point after the current API/LLM response completes',
    'u5.diff_stop_requested': 'Gap filling stop requested. Will stop after the current LLM response completes.',
    'u5.waiting_stop': 'Stop requested — Waiting for the current API/LLM response',
    'u5.proofread_stop_requested': 'AI proofreading stop requested. Will stop after the current LLM response completes.',
    'u5.confirm_storage_change': 'Change the storage location for generated files.\n\nCurrent: {old_root}\nNew: {new_root}\n\n[Yes]: Copy existing data to the new location, then switch\n[No]: Leave existing data in place and change only where new data is saved\n[Cancel]: Do not change',
    'u5.storage_changed_copy': 'Storage location changed.\n\n{root}\n\nExisting data has also been copied.',
    'u5.storage_changed_new': 'Storage location changed.\n\n{root}\n\nNew data will be saved to this location.',
    'u5.settings_applied': 'Current translation settings applied.\n\nQA AI proofreading and gap filling use the provider, URL, model, and Glossary currently selected on this screen.',
    'u5.settings_applied_running': 'Current translation settings applied.\n\nQA AI proofreading and gap filling use the provider, URL, model, and Glossary currently selected on this screen.\nRunning normal translation will switch at the next batch.',
    'u5.confirm_delete_profiles': 'Delete the following model profiles?\n\n{names}',
    'u5.response_truncated': '…(beginning omitted)…\n{content}',
    'u5.discovery_response_title': 'Discovery LLM full response',
    'u5.translation_response_title': 'Translation LLM full response',
    'u5.folder_tree': 'Paradox Localization Translator/\n├── 翻訳結果/\n├── キャッシュ/\n│   ├── mod_translation_status_cache.json\n│   ├── mod_classification_cache.json\n│   ├── mod_relation_overrides.json\n│   ├── translation_status_state.json\n│   ├── diagnostic_state.json\n│   └── shared_mod_state_cache.json\n├── バックアップ/\n├── ログ/\n│   ├── QA/\n│   ├── エラー/\n│   ├── 日本語化Mod判定/\n│   ├── 診断/\n│   ├── 夜間処理/\n│   └── システム・履歴/\n├── 作業データ/  ← version-independent temporary files and working state\n└── 設定/\n    ├── session.json\n    ├── resume_state.json\n    ├── storage_migration.json\n    ├── glossary.json\n    ├── model_stats.json\n    ├── model_profiles.json\n    ├── steam_library_roots.json\n    └── app_preferences.json  ← last LLM settings and close-button behavior\n\nDefault location: Documents/Paradox Localization Translator\nUse [Change location] to move to another drive, external SSD, or any folder.',
}


@pytest.fixture(autouse=True)
def restore_language():
    language = i18n.get_ui_language()
    yield
    i18n.set_ui_language(language)


def environment(active=False, copied=False, monitor=False):
    worker = SimpleNamespace(is_alive=lambda: active)
    return dict(
        i18n=i18n, Path=Path, _current_target_lang=lambda app: app.target_lang,
        self=SimpleNamespace(target_lang="japanese", llm_operation="", controller=active, worker=worker),
        old_root=Path("/old/data"), new_root=Path("/new/data"), DATA_ROOT=Path("/new/data"),
        copied=copied, monitor=monitor, name="Profile A", names=["Profile A", "Profile B"],
        batch=40, workers=2, note="説明", models=["Model A", "Model B"],
        item={"input": "/mods/example"}, cache_path=Path("/cache/cache.json"), cache={"a": "b"},
        imported={"a": "b"}, dst={"a": "b", "c": "d"}, dst_path=Path("/cache/dst.json"),
        info={"provider": "Ollama", "endpoint": "localhost"}, context="LLM処理",
        provider="Ollama", request={"provider": "Ollama"}, label="Ollama", model="Model A",
        received="12:34:56", content="応答" * 5000, op="LLM処理", base="詳細", secs=12,
        payload={"attempt": 1, "retries": 3}, e=ValueError("error"), exc=ValueError("error"),
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case[4])
def test_japanese_original_display(case):
    i18n.set_ui_language("japanese")
    key, template, field_expressions, original = case[4:8]
    values = environment(active=key == "u5.settings_applied_running",
                         copied=key == "u5.storage_changed_copy",
                         monitor=key == "u5.discovery_response_title")
    fields = {name: eval(expression, values) for name, expression in field_expressions.items()}
    expected = eval("(" + original + ")", values)
    assert JAPANESE[key] == template
    assert i18n.t(key, **fields) == expected


def test_english_keys_and_fields():
    i18n.set_ui_language("english")
    assert set(JAPANESE) == set(ENGLISH) == set(EXPECTED_ENGLISH)
    for key, expected in EXPECTED_ENGLISH.items():
        assert ENGLISH[key] == expected
        fields = {name for _, name, _, _ in Formatter().parse(JAPANESE[key]) if name}
        assert fields == {name for _, name, _, _ in Formatter().parse(expected) if name}
        values = {name: 12345 if name == "count" else "sample" for name in fields}
        assert i18n.t(key, **values) == expected.format_map(values)


@pytest.mark.parametrize("language", i18n.UI_LANGUAGES)
def test_repair_label_uses_target_language_name(language):
    i18n.set_ui_language("english")
    target_name = i18n.t("lang." + language)
    assert i18n.t("u5.repair_existing", target_name=target_name) == (
        "Repair untranslated text in existing " + target_name
    )


def test_all_u5_keys_are_used_in_main():
    tree = ast.parse((ROOT / "app/main.py").read_text())
    keys = {node.args[0].value for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"
            and node.func.attr == "t" and node.args and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str) and node.args[0].value.startswith("u5.")}
    assert keys == set(JAPANESE)


def test_snapshot_calls_match_main_fields():
    tree = ast.parse((ROOT / "app/main.py").read_text())
    calls = {ast.dump(node) for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n"
             and node.func.attr == "t"}
    for case in CASES:
        assert ast.dump(ast.parse(case[8], mode="eval").body) in calls, case[4]


def isolated_method(name):
    tree = ast.parse((ROOT / "app/main.py").read_text())
    app = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "App")
    method = next(node for node in app.body if isinstance(node, ast.FunctionDef) and node.name == name)
    namespace = {"i18n": i18n}
    module = ast.Module(body=[method], type_ignores=[])
    exec(compile(module, "<U5 isolated method>", "exec"), namespace)
    return namespace[name]


class DisplayVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


@pytest.mark.parametrize("language", ["japanese", "english"])
def test_elapsed_display_does_not_accumulate(language, monkeypatch):
    import time

    i18n.set_ui_language(language)
    monkeypatch.setattr(time, "time", lambda: 100)
    method = isolated_method("_update_llm_elapsed")
    detail = DisplayVariable("Ollama / Model A — details")
    app = SimpleNamespace(llm_busy_count=1, llm_busy_since=88,
                          llm_detail_var=detail, after=lambda *args: None,
                          _update_llm_elapsed=lambda: method(app))
    method(app)
    first = detail.get()
    method(app)
    assert detail.get() == first
    assert detail.get() == i18n.t("u5.elapsed", base="Ollama / Model A — details", seconds=12)


def test_idle_defaults_follow_language_at_call_time():
    i18n.set_ui_language("japanese")
    method = isolated_method("_set_llm_idle")
    widget = SimpleNamespace(config=lambda **kwargs: None)
    app = SimpleNamespace(llm_active_ids={"request"}, llm_status_var=DisplayVariable(),
                          llm_detail_var=DisplayVariable(), llm_banner=widget,
                          llm_status_label=widget, llm_detail_label=widget, llm_stop_btn=widget)
    i18n.set_ui_language("english")
    method(app)
    assert app.llm_status_var.get() == "LLM idle"
    assert app.llm_detail_var.get() == "No LLM task is running"
    i18n.set_ui_language("japanese")
    method(app)
    assert app.llm_status_var.get() == "LLM 待機中"
    assert app.llm_detail_var.get() == "LLM処理は実行されていません"
    method(app, status="", detail="")
    assert app.llm_status_var.get() == app.llm_detail_var.get() == ""
