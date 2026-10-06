# 不変条件とテストの対応表

README.md と CHANGELOG.md に書かれた約束ごと（利用者に約束している動き）を一覧にし、それを確かめる pytest があるかを表にしたものです。main.py を分ける前の安全網として使います。

- 作成：2026-10-06（v0.11.77 時点、main `a6e431e`）
- 「テスト」欄はテスト関数名です。新しく足したテストの docstring には、この表の番号（INV-NN）を書いています。
- 「状態」欄：**あり**＝確かめるテストがある／**一部**＝一部だけ確かめている／**なし**＝テストがない。「追加前」は今回の追加より前の状態です。
- 約束ごとを変えたときは、この表とテストを一緒に直してください。

## 集計

| | 項目数 | あり | 一部 | なし |
|---|---|---|---|---|
| 追加前 | 57 | 28 | 2 | 27 |
| 追加後 | 57 | 50 | 1 | 6 |
| v0.11.78 | 57 | 51 | 0 | 6 |

「テストなし」（なし＋一部）は 29 件（51%）から 7 件（12%）になりました。v0.11.78 で INV-03 の不具合を直し、6 件（11%）です。

## 翻訳と構文の保護

| 番号 | 約束ごと（出典） | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-01 | 翻訳中はゲーム構文をプレースホルダに置き換えて保護し、あとで元に戻す（README「Paradoxゲーム構文を保護」） | `test_translator_core.py::test_placeholder_round_trip` | あり | あり |
| INV-02 | README に挙げた構文（`[...]`、`$...$`、`£...£`、`@...!`、`§Y…§!`、`#tooltip;…#!`、`\n`）をすべて保護する（同上） | `test_invariants_core.py::test_all_documented_syntax_forms_are_protected_and_restored` | なし | あり |
| INV-03 | LLM が記号を多少崩しても復元する救済処理がある（同上） | `test_restore_rescues_placeholder_with_broken_suffix`、`test_unknown_placeholder_index_is_left_visible_for_qa`、`test_restore_rescue_keeps_following_text` | なし | あり（v0.11.78 で修正。下の「見つかった不具合」） |
| INV-04 | 訳文中の `"` はエスケープして YAML を壊さない | `test_written_values_escape_quotes_without_double_escaping` | なし | あり |
| INV-05 | 日本語 YAML に残った英語を未翻訳として検出する（README「未翻訳箇所の自動修復」） | `test_english_left_in_japanese_output_is_untranslated` | 一部 | あり |
| INV-06 | 「翻訳成功」として誤ってキャッシュされた英語原文を不良キャッシュとして再翻訳する（同上） | `test_cached_english_source_is_rejected_as_bad_cache` | なし | あり |
| INV-07 | 出力を変える設定（プロバイダ・モデル・用語集・翻訳モードなど）が違えばキャッシュを分ける | `test_cache_key_changes_with_settings_that_change_output` | なし | あり |
| INV-08 | Mod 更新後、新規・変更・削除されたキーと新規ファイルを判定する（README「Mod更新時の差分翻訳」） | `test_source_manifest_diff_reports_added_changed_removed_and_new_files` | なし | あり |
| INV-09 | 日本語出力に無いキーだけを欠落とし、別の日本語ファイルにあるキーは欠落にしない | `test_missing_translation_keys_use_all_japanese_files` | なし | あり |
| INV-10 | 生成した日本語 YAML は english・simp_chinese のフォルダや localization 直下に置かない | `test_generated_japanese_files_never_share_source_language_folder` | なし | あり |
| INV-11 | 状態の JSON は一時ファイル経由で置き換え、壊れていれば既定値で読む | `test_broken_json_falls_back_and_save_leaves_no_temp_file` | なし | あり |

## QA と自動修復（v0.11.70〜0.11.73）

| 番号 | 約束ごと（出典） | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-12 | 修復前にバックアップと復元用マニフェストを作り、修復後に再 QA する（v0.11.70） | `test_translator_core.py::test_auto_qa_repair_backs_up_retranslates_and_adds_missing_key` | あり | あり |
| INV-13 | 注意・警告は自動で変えず、修復可能なエラーだけを直す（v0.11.71、v0.11.73） | `test_auto_repair_never_changes_warnings_or_notices`、`test_manual_auto_repair_counts_proper_name_as_notice_not_warning` | 一部 | あり |
| INV-14 | 機械修復は、挿入位置が一意に決まる端の変数・タグだけを直す | `test_mechanical_token_repair_only_restores_unambiguous_edge_tokens` | なし | あり |
| INV-15 | LLM の再翻訳結果は、変数・タグの一致と未翻訳でないことを確かめてから書き込む | `test_auto_repair_rejects_llm_output_that_breaks_tokens` | なし | あり |
| INV-16 | エラーが減らなかったら修復前へ差し戻す。新しく作った出力なら消す（v0.11.70） | `test_auto_repair_rolls_back_when_errors_do_not_decrease`、`test_manual_auto_repair_removes_created_output_when_it_did_not_help` | なし | あり |
| INV-17 | ファイル単位の失敗はスキップして残りを続ける（v0.11.71） | `test_manual_auto_repair_continues_after_file_failure` | あり | あり |
| INV-18 | 修復可能なエラーが無いときや処理中は自動修復ボタンをグレーアウトする（v0.11.71） | `test_qa_auto_repair_button_gate_requires_repairable_error` | あり | あり |
| INV-19 | QA 修正は専用コントローラーで止められ、通常翻訳の停止が優先される（v0.11.72） | `test_manual_auto_repair_honors_dedicated_stop_controller`、`test_translation_stop_keeps_priority_over_qa_repair_controller`、`test_translation_stop_routes_to_dedicated_qa_controller_when_qa_is_active` | あり | あり |
| INV-20 | QA 修正の段階（バックアップ・機械修復・再翻訳・再 QA など）を表示する（v0.11.72） | `test_manual_auto_repair_reports_file_and_stage_progress` | あり | あり |
| INV-21 | 中国語原文と同じ人物名・王朝名は未翻訳エラーではなく「注意」にする（v0.11.70、v0.11.73） | `test_qa_downgrades_unchanged_chinese_proper_name_to_notice`、`test_qa_keeps_unchanged_chinese_sentence_as_repairable_error`、`test_qa_severity_group_keeps_notice_separate_from_warning` | あり | あり |
| INV-22 | QA ログに原文・日本語本文を保存しない（v0.11.68） | `test_qa_log_payload_has_diagnostics_without_localization_text`、`test_qa_log_payload_counts_notice_separately`、`test_qa_log_payload_includes_auto_repair_diagnostics` | あり | あり |
| INV-23 | QA ログはボタン操作のときだけ書き出し、QA 前はボタンをグレーアウトする（v0.11.68） | `test_qa_log_is_written_only_by_export_action`、`test_qa_log_button_is_disabled_without_results_and_enabled_with_results` | あり | あり |
| INV-51 | 用語集の訳語が訳文に無ければ警告にする（自動修復はしない） | `test_glossary_term_missing_from_translation_is_a_warning_not_an_error` | なし | あり |

## バックアップと復元

| 番号 | 約束ごと（出典） | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-24 | Mod へ書き込む前に localization 全体をマニフェスト付きで保存する。localization が無い Mod でもその旨を記録する（v0.11.75、README「Steam Workshop Modへの直接上書き」） | `test_overwrite_snapshot_copies_whole_localization_with_manifest_and_generation`、`test_snapshot_of_mod_without_localization_records_that_it_did_not_exist` | なし | あり |
| INV-25 | 上書きバックアップは対象 Mod ごとに第N回と数える | `test_overwrite_snapshot_copies_whole_localization_with_manifest_and_generation` | なし | あり |
| INV-26 | 復元の前に今の localization 全体を「復元前退避」へ保存する。確認で「いいえ」なら何も変えない | `test_exact_restore_saves_current_state_first_then_replaces_localization`、`test_restore_is_cancelled_without_touching_files` | なし | あり |
| INV-27 | 完全バックアップの復元は localization をそっくり当時に戻す（後から足したファイルは消える） | `test_exact_restore_saves_current_state_first_then_replaces_localization` | なし | あり |
| INV-28 | 旧形式の部分バックアップは保存済みのファイルだけを戻し、後から作ったファイルは消さない | `test_legacy_partial_restore_only_puts_back_saved_files` | なし | あり |

## 日本語化 Mod と元 Mod への上書き

| 番号 | 約束ごと（出典） | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-29 | 後順位の日本語化 Mod を選んだら、隠している側のファイルへ完成済み翻訳を反映し、判定キャッシュを無効にする（v0.11.75） | `test_effective_stale_same_path_translation_is_preferred_for_overwrite`、`test_full_stale_translation_overwrite_replaces_masking_file_and_invalidates_cache` | あり | あり |
| INV-30 | 日本語化 Mod へは差分キーだけを書き、既存の日本語訳は維持する。差分が無ければ何も書かない（README「7. Modへ反映」） | `test_external_gap_overwrite_writes_only_gap_keys_and_backs_up_first`、`test_external_gap_overwrite_refuses_without_gap_keys` | なし | あり |
| INV-31 | 日本語化 Mod に無いキーは専用の追加ファイルへ足す | `test_external_gap_overwrite_writes_only_gap_keys_and_backs_up_first` | なし | あり |
| INV-32 | 元 Mod へ直接上書きするときは、置き換える既存ファイルを先にバックアップする | `test_source_mod_overwrite_backs_up_existing_files_before_replacing` | なし | あり |
| INV-33 | 書き込む前に、後順位 Mod の同じパスで隠されないかを確かめる（v0.11.75） | `test_later_stale_translation_with_same_virtual_path_is_detected`、`test_same_path_in_earlier_mod_does_not_mask_source` | あり | あり |

## 日本語化 Mod の判定（v0.11.60〜0.11.62）

| 番号 | 約束ごと | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-34 | 有効キー100件以上は有効共通200件以上かつ双方向40%、100件未満は元 Mod 側20%（README「自動調査の判定について」） | `test_large_partial_translation_passes_candidate_side_40_percent`、`test_large_relation_requires_200_effective_keys`、`test_small_source_keeps_20_percent_gate`、`test_translation_shape_20_and_80_percent_boundaries`、`test_multi_translation_*` | あり | あり |
| INV-35 | ゲーム本体の未変更キーと、原文が食い違うキーは関連の根拠にしない。Mod 名やフォルダ名だけで関連付けない | `test_ercf_ditn_vanilla_carryover_is_not_relationship_evidence`、`test_candidate_source_text_mismatch_removes_shared_keys`、`test_base_translation_is_not_linked_by_folder_name_alone`、`test_self_localized_mod_is_not_external_translation_without_explicit_evidence` ほか | あり | あり |
| INV-36 | `l_english` に日本語を書く旧式の日本語化を警告し、中国語を日本語と取り違えない | `test_legacy_japanese_in_l_english_is_reported_as_warning`、`test_chinese_text_is_not_mistaken_for_legacy_japanese`、`test_normal_english_mod_has_no_translation_warning`、`test_outdated_native_japanese_candidate_gets_unresolved_source_warning`、`test_warning_status_is_restored_after_later_status_refinement` | あり | あり |
| INV-47 | 判定方式を変えたら古い判定キャッシュを使わない。保存は軽量形式で世代を記録する（v0.11.61、v0.11.65） | `test_relation_algorithm_change_invalidates_old_status_cache_generation`、`test_compact_translation_status_result_keeps_gap_identity_without_source_text`、`test_translation_status_save_writes_current_generation_and_compact_rows`、`test_translation_status_save_schedule_coalesces_rapid_updates` | あり | あり |

## 読み込み・キュー・状態

| 番号 | 約束ごと | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-37 | Victoria 3 の `.metadata/metadata.json` から Mod 名を取り、壊れた JSON でも名前を回収する（v0.11.64） | `test_detect_mod_name_*`（4件） | あり | あり |
| INV-38 | 重なった BOM を直し、出力を UTF-8 BOM にそろえる（v0.11.63） | `test_decode_mixed_utf8_and_utf16le_bom`、`test_run_translation_recovers_mixed_bom_and_normalizes_output` | あり | あり |
| INV-39 | 読めないファイルはスキップして残りを続ける（v0.11.63、v0.11.67） | `test_run_translation_skips_unreadable_file_and_continues` | あり | あり |
| INV-40 | 接続障害で全キーを1件ずつ再試行せず、一巡後に失敗項目だけを再試行する（v0.11.63） | `test_provider_failure_defers_remaining_jobs_without_retrying_every_key`、`test_queue_continues_then_retries_only_failed_item` | あり | あり |
| INV-41 | 壊れたアプリの重要 JSON は `*.corrupt_日時` へ退避する（v0.11.59） | `test_malformed_persistent_json_is_quarantined` | あり | あり |
| INV-42 | キュー項目は安定 ID で扱い、並べ替えに左右されない（v0.11.59） | `test_queue_item_ids_survive_reordering` | あり | あり |
| INV-43 | GUI イベントは1回あたり最大200件・約12ms で区切る（v0.11.59） | `test_event_budget_stops_by_count`、`test_event_budget_stops_by_elapsed_time` | あり | あり |
| INV-44 | 処理中は競合するキュー操作をグレーアウトする（v0.11.59） | `test_normal_queue_locks_while_translation_is_running` ほか3件、`test_busy_ui_greys_out_conflicting_normal_controls` | あり | あり |
| INV-45 | 終了時は保存してから正常終了を記録し、強制終了では記録しない（v0.11.59） | `test_clean_exit_saves_then_writes_clean_marker`、`test_forced_exit_does_not_write_clean_marker` | あり | あり |
| INV-46 | ログを種類別フォルダへ移し、同名は上書きせず連番を付ける。診断 ZIP は過去の ZIP を入れない（v0.11.69） | `test_log_category_mapping_covers_each_global_log_type`、`test_existing_logs_are_moved_by_category_without_overwrite`、`test_diagnostics_collects_category_logs_but_not_previous_diagnostic_zips` | あり | あり |

## LLM への接続（v0.11.74〜0.11.77）

| 番号 | 約束ごと | テスト | 追加前 | 追加後 |
|---|---|---|---|---|
| INV-48 | ローカル・LAN の LLM へはプロキシを通さず、`http://` 省略や `/v1` 付き URL も扱う（v0.11.76） | `test_local_model_list_bypasses_system_proxy`、`test_local_llm_call_bypasses_system_proxy`、`test_local_url_without_scheme_or_with_openai_suffix_is_normalized`、`test_remote_hosts_keep_using_configured_proxy` | あり | あり |
| INV-49 | 思考過程を取り除いて訳だけを読み、切り替えられるモデルは思考をオフにする（v0.11.77） | `test_reasoning_is_stripped_from_thinking_model_output`、`test_ollama_disables_thinking_and_explains_thinking_only_models` | あり | あり |
| INV-50 | 接続確認に成功してから処理を始め、接続エラーの種類ごとに案内を分ける（v0.11.74） | `test_normal_translation_waits_for_preflight_before_creating_output`、`test_successful_preflight_runs_original_operation_on_gui_queue`、`test_lm_studio_connection_refused_uses_large_local_startup_warning` ほか3件 | あり | あり |

## まだテストがないもの

| 番号 | 約束ごと（出典） | メモ |
|---|---|---|
| INV-52 | Mod ごと・翻訳ジョブごとにキャッシュを分け、混ざらない（README「翻訳ごとの独立キャッシュ」） | キャッシュの置き場所を決めるのは main.py 側。分割のときに関数を切り出してから試すのがよい |
| INV-53 | 翻訳中の設定変更は、次の安全なバッチ境界から反映する（README「複数Mod翻訳キュー」） | `TranslationController` とワーカーの組み合わせが要る |
| INV-54 | 「セーブして中断」と次回起動時のセッション復元（同上） | `save_session`／`restore_session` は App の状態が多い |
| INV-55 | 差分翻訳では追加・変更された箇所だけを LLM へ送り、ほかはキャッシュを使う（README「Mod更新時の差分翻訳」） | `run_translation` に偽の `translate_batch` を渡せば試せる。次に足す候補 |
| INV-56 | 翻訳状況の検索語は再起動・復元・新規調査で引き継がない（v0.11.66） | |
| INV-57 | 翻訳・診断・復元・上書き中は保存場所の変更をグレーアウトする（v0.11.59） | |

## 見つかった不具合

- **INV-03：崩れたプレースホルダの救済で、直後の訳文が最大2文字消えていた（v0.11.78 で修正）。** 救済用の正規表現 `PLACEHOLDER_FALLBACK_RE` が `@@(\d+)\D{0,2}` で、崩れた閉じ記号だけでなく後ろの普通の文字まで飲み込んでいました（例：`こんにちは @@0 さん` → `こんにちは $NAME$ん`）。`@@(\d+)@?` に直し、消すのは閉じ記号の残りの `@` だけにしました。`test_restore_rescue_keeps_following_text` が `@@0`・`@@0@` と空白の有無の4つの形を確かめます。
