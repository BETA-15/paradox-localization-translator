import json
from pathlib import Path
import re
from string import Formatter

import pytest

import i18n
from app import translator_core as core
import ui_status


SNAPSHOTS = json.loads(r'''
[
  ["u9.unsupported_game_language","sample は日本語（l_sample）を読めません。翻訳しても、ゲームの中には表示されません。sample が読める言語: sample",{"game":"sample","target_name":"日本語","target_lang":"sample","supported_game":"sample","supported_languages":"sample"}],
  ["u9.glossary_unsupported_format","対応していない形式です（sample）。このアプリの用語集は {\"原語\": \"訳語\"} 形式のJSONです。ParaTranz の用語集は『ParaTranz の用語集を取り込む』から取り込めます。",{"format_name":"sample"}],
  ["u9.thinking_only_warning","sample は思考を止められないThinking専用モデルのため、翻訳には使用できません。1回の翻訳で長く考え込み、時間切れや空の応答になります。qwen3:4b-instruct-2507 などのinstruct版（思考なし）のモデルを選んでください。",{"model":"sample","marker":"Thinking専用モデル"}],
  ["u9.embedding_only_warning","sample は文章を検索用の数値に変える埋め込み専用モデルのため、翻訳には使用できません。文章を書けないので、翻訳を始めても訳文が返りません。qwen3:8b や gemma3 などの、文章を生成するモデルを選んでください。",{"model":"sample","marker":"埋め込み専用モデル"}],
  ["u9.reasoning_warning","sample は考える過程に時間を使うモデルのため、翻訳に向きません。1回の翻訳で長く考え込み、時間切れや空の応答になります。instruct 版など、考える過程を出さないモデルに替えてください。",{"model":"sample","marker":"考える過程に時間を使うモデル"}],
  ["u9.report_title","紐付けレポート",{}],
  ["u9.glossary_list_format","リスト形式",{}],
  ["u9.glossary_non_dict_format","辞書ではない形式",{}],
  ["u9.llm_retries_failed","LLM呼び出しにsample回失敗しました: sample",{"retries":"sample","error":"sample"}],
  ["u9.source_no_gaps","原文間の欠落なし",{}],
  ["u9.gap_none","欠損なし",{}],
  ["u9.skip_continue","スキップして継続",{}],
  ["u9.keep_results_continue","翻訳結果を保持して継続",{}],
  ["u9.translation_settings","プロバイダ: sample / モデル: sample / 対象ファイル: sample / 読込スキップ: sample / プリセット: sample / 英中併用: sample",{"provider":"sample","model":"sample","file_count":"sample","skipped_file_count":"sample","preset":"sample","dual_source":"sample"}],
  ["u9.spaces_removed","半角スペース除去: sample個",{"count":"sample"}],
  ["u9.chinese_spaces_removed","半角スペース除去: sample個",{"count":"sample"}],
  ["u9.structure_japanese_only","日本語localization専用（大幅加点）",{}],
  ["u9.legacy_threshold_large","100キー以上 → 50キー一致",{}],
  ["u9.legacy_threshold_small","100キー未満 → 20%",{}],
  ["u9.legacy_source_coverage","元Modキー完全一致率 2.5% (sample/sample) / 判定基準 sample → 2.5点",{"percent":2.5,"matched":"sample","total":"sample","threshold":"sample","points":2.5}],
  ["u9.legacy_candidate_coverage","参考: 日本語化Mod側一致率 2.5% (sample/sample)",{"percent":2.5,"matched":"sample","total":"sample"}],
  ["u9.legacy_structure_score","構成評価 sample: 日本語YAML sample / 他言語YAML sample / localization比率 2.5% / 非localization sampleファイル → 2.5点",{"kind":"sample","japanese_file_count":"sample","other_language_file_count":"sample","localization_percent":2.5,"non_localization_file_count":"sample","points":2.5}],
  ["u9.legacy_gameplay_score","ゲーム内容 sampleファイル / sample分類 → 2.5点",{"file_count":"sample","category_count":"sample","points":2.5}],
  ["u9.relation_large_threshold","有効キー100以上 → sampleキーかつ双方向40%のどちらか",{"min_keys":"sample"}],
  ["u9.relation_small_threshold","有効キー100未満 → 元Mod側20%",{}],
  ["u9.structure_japanese_only_new","日本語localization専用（大幅加点）",{}],
  ["u9.relation_raw_keys","生共通キー sample件 / バニラ持ち込み除外 sample件",{"shared_keys":"sample","excluded_keys":"sample"}],
  ["u9.relation_shared_breakdown","共通キー内訳: 本体原文変更 sample件 / 非本体 sample件",{"changed_base_keys":"sample","non_base_keys":"sample"}],
  ["u9.relation_source_check","候補原文照合: 一致 sample件 / 不一致 sample件 / 候補原文なし sample件",{"matched":"sample","mismatched":"sample","missing_source_keys":"sample"}],
  ["u9.relation_effective_keys","最終有効共通キー sample件 / 元Mod側 2.5% / 候補側 2.5%",{"shared_keys":"sample","source_percent":2.5,"candidate_percent":2.5}],
  ["u9.relation_gate","関係ゲート: 件数 sample / 元Mod側 sample / 候補側 sample",{"count_result":"sample","source_result":"sample","candidate_result":"sample"}],
  ["u9.relation_structure","候補構成: 本体キー sample/sample (2.5%) / 非本体 2.5% / 原文同梱 2.5%",{"base_keys":"sample","total_keys":"sample","base_percent":2.5,"non_base_percent":2.5,"paired_source_percent":2.5}],
  ["u9.relation_role","候補役割: sample / sample",{"classification":"sample","localization_kind":"sample"}],
  ["u9.mod_localization_missing","sampleのlocalizationフォルダを確認できませんでした。",{"mod_name":"sample"}],
  ["u9.mod_no_sources","sampleには判定対象となる英語/中国語ローカライズが見つかりませんでした。",{"mod_name":"sample"}],
  ["u9.mod_review_candidate","日本語化Mod候補『sample』を検出しましたが、関連度 2.5/100 のため自動関連付けしていません。",{"mod_name":"sample","score":2.5}],
  ["u9.local_location","ローカル",{}],
  ["u9.report_weight_explanation","一致率の「重み付き」は、多くのModに共通して出てくるキー（国名など）ほど軽く数えた割合です（キーの重み = log((Mod数 + 1) ÷ そのキーを原文に持つMod数)）。",{}],
  ["u9.report_summary","元Mod sample件のうち、紐付けあり sample件、要確認 sample件。",{"mod_count":"sample","linked_count":"sample","review_count":"sample"}],
  ["u9.report_flag_explanation","「要確認」の印の意味：候補のみ＝自動では紐付けていない／一致が少ない＝元Modのキーのうち日本語化Modにもある割合（重み付き）が2%未満／名前が似ていない＝名前に共通の語が無い／複数に紐付き＝同じ日本語化Modが2つ以上の元Modに紐付いている（総合和訳なら正しいこともある）。",{"threshold_percent":2.5}],
  ["u9.report_source_heading","## 元Modごとの紐付け（要確認を先に表示）",{}],
  ["u9.report_source_columns","| 要確認 | ゲーム | 元Mod | 元Modの保管場所 | 状態 | 紐付け先 | 紐付け先の保管場所 | 種別 | 点数 | 重み付き一致率（元Mod側） | 重み付き一致率（日本語化Mod側） |",{}],
  ["u9.report_translation_heading","## 日本語化Modごとの紐付け先",{}],
  ["u9.report_translation_columns","| 日本語化Mod | 保管場所 | 元Modの数 | 元Mod |",{}],
  ["u9.glossary_json_line","用語集のJSONを読めません（sample行目: sample）",{"line":"sample","error":"sample"}],
  ["u9.glossary_json_error","用語集のJSONを読めません（sample）",{"error":"sample"}],
  ["u9.source_english_only","英語にのみ存在する翻訳対象キー sample件",{"count":"sample"}],
  ["u9.source_chinese_only","簡体字中国語にのみ存在する翻訳対象キー sample件",{"count":"sample"}],
  ["u9.gap_english_only","英語にのみ存在するキーのうち、日本語訳が必要な sample件が欠如",{"count":"sample"}],
  ["u9.gap_chinese_only","簡体字中国語にのみ存在するキーのうち、日本語訳が必要な sample件が欠如",{"count":"sample"}],
  ["u9.gap_shared","英語・簡体字中国語の共通キーで sample件が欠如または未翻訳",{"count":"sample"}],
  ["u9.gap_other","その他の翻訳不足 sample件",{"count":"sample"}],
  ["u9.repair_source_notice","  原文は既にsampleです。未翻訳の外国語部分だけを修復します",{"target_lang":"sample"}],
  ["u9.file_translation_summary","  原文言語: sample / 全キー: sample / 翻訳対象: sample",{"source_lang":"sample","total_keys":"sample","translation_count":"sample"}],
  ["u9.no_yaml_files","翻訳対象のYAMLファイルが見つかりませんでした。",{}],
  ["u9.file_error","  [警告] sampleエラーのためsample: sample / sample: sample",{"stage":"sample","action":"sample","path":"sample","error_type":"sample","error":"sample"}],
  ["u9.completed_with_warnings","警告付きで完了しました。スキップ sampleファイル / 翻訳失敗 sample件",{"skipped_file_count":"sample","failed_count":"sample"}],
  ["u9.completed","完了しました。",{}],
  ["u9.proper_noun_path","中国語原文と同一で、names/dynasties配下の短い表記です",{}],
  ["u9.proper_noun_key","中国語原文と同一で、キー名が人物名・家名系の形式です",{}],
  ["u9.not_paratranz_glossary","ParaTranz の用語集（term / translation を持つリスト）ではありません。",{}],
  ["u9.import_mode_required","取り込み方法は merge または replace を指定してください。",{}],
  ["u9.comparison_missing","日本語側にキーがありません",{"target_name":"日本語"}],
  ["u9.no_chinese_yaml","簡体字中国語（l_simp_chinese）のYAMLファイルが見つかりませんでした。",{}],
  ["u9.legacy_translation_warning","古い日本語化方式の可能性があります。日本語文が英語localization（l_english）として収録されています。",{}],
  ["u9.translation_source_unknown","日本語化Mod形式ですが対応元Modを自動特定できません。対応元Modの未導入、古いバージョン、またはキーの大幅な変更が考えられます。",{}],
  ["u9.structure_localization_only","localization専用（他言語を含む）",{}],
  ["u9.legacy_folder_match","localizationフォルダ名一致『sample』 → +2.5点",{"folder_name":"sample","points":2.5}],
  ["u9.legacy_no_folder_match","localizationフォルダ名一致なし → 0.0点",{}],
  ["u9.legacy_dependency_match","dependencies一致『sample』 → 20.0点",{"dependency":"sample"}],
  ["u9.legacy_no_dependency","dependencies一致なし → 0.0点",{}],
  ["u9.legacy_other_language_score","他言語localizationの元Mod関連度: sample / 基準充足度平均 2.5% → 2.5点",{"details":"sample","average_quality_percent":2.5,"points":2.5}],
  ["u9.legacy_no_other_language","他言語localizationなし → 減点なし",{}],
  ["u9.legacy_base_unavailable","ゲーム本体キーを取得できないため、本体和訳修正例外の減点なし",{}],
  ["u9.legacy_exception_gate","日本語localization専用の例外ゲート: 日本語化Mod側一致率 2.5% / 完全一致 sampleキー → 関係判定対象",{"percent":2.5,"matched":"sample"}],
  ["u9.structure_localization_only_new","localization専用（他言語を含む）",{}],
  ["u9.relation_auto_level","自動で紐付けできる水準",{}],
  ["u9.relation_candidate_level","候補の水準",{}],
  ["u9.relation_reject_level","紐付けない水準",{}],
  ["u9.relation_weighted","情報量で重み付けした一致率（多くのModに共通するキーほど軽く数える）: 元Mod側 2.5% / 日本語化Mod側 2.5% → sample",{"source_percent":2.5,"candidate_percent":2.5,"level":"sample"}],
  ["u9.relation_union_gate","総合和訳集合ゲート: 候補有効キー和集合率 2.5% → PASS",{"percent":2.5}],
  ["u9.relation_standalone_excluded","候補が原文と日本語を80%以上同梱する独立Mod型で、明示的な関係証拠がないため除外",{}],
  ["u9.relation_base_excluded","候補が本体キー80%以上・50キー以上の本体日本語化型で、明示的な関係証拠がないため除外",{}],
  ["u9.relation_gate_failed","有効なMod間関連キーのゲート未通過のため、構成点だけでは自動関連付けしない",{}],
  ["u9.mod_translated","sampleのModは日本語翻訳が確認できました。",{"mod_name":"sample"}],
  ["u9.automatic_link","自動で紐付け",{}],
  ["u9.candidate_link","候補（自動では紐付けず）",{}],
  ["u9.report_review_heading","## 要確認の根拠",{}],
  ["u9.deferred_provider_failure","接続・プロバイダ障害のため後段再試行へ延期: sample",{"reason":"sample"}],
  ["u9.single_retry_count","  sample件を単発再試行します…",{"count":"sample"}],
  ["u9.translation_failed","翻訳できませんでした",{}],
  ["u9.saved_stop","保存して中断しました。次回はキャッシュから再開できます。",{}],
  ["u9.untranslated_chinese_candidate","中国語の未翻訳候補",{}],
  ["u9.untranslated_english_candidate","英語の未翻訳候補",{}],
  ["u9.repair_no_improvement","修復前よりエラーが減らなかったため",{}],
  ["u9.paratranz_strings_required","原語と訳語は文字列で、原語は空白だけでない必要があります。",{}],
  ["u9.paratranz_rule_item","訳語が「※」で始まるルールの項目",{}],
  ["u9.invalid_terms_sidecar","用語の補助ファイルが辞書形式ではないため上書きしません。",{}],
  ["u9.invalid_rules_sidecar","表記ルールのファイルの形式が不正なため上書きしません。",{}],
  ["u9.comparison_extra","日本語側だけに存在するキーです",{"target_name":"日本語"}],
  ["u9.structure_helper_only","日本語化補助ファイルのみ",{}],
  ["u9.legacy_base_penalty","日本語化Mod側から見たゲーム本体キー一致率 2.5% (sample/sample) / 70%以上 → 本体和訳修正の可能性が高いため 2.5点",{"percent":2.5,"matched":"sample","total":"sample","points":2.5}],
  ["u9.legacy_base_no_penalty","日本語化Mod側から見たゲーム本体キー一致率 2.5% (sample/sample) / 70%未満 → 減点なし",{"percent":2.5,"matched":"sample","total":"sample"}],
  ["u9.legacy_few_matches","元Modとの完全一致が必要値 50キー未満のため関係判定対象外",{}],
  ["u9.legacy_low_coverage","元Modキーの完全一致率が必要値 2% 未満のため関係判定対象外",{"threshold_percent":2.5}],
  ["u9.structure_helper_only_new","日本語化補助ファイルのみ",{}],
  ["u9.mod_external_also","別Mod『sample』にも日本語化があります。",{"translation_mod_name":"sample"}],
  ["u9.mod_external_complete","sampleには日本語化Mod『sample』があり、完全な日本語化を確認できました。",{"mod_name":"sample","translation_mod_name":"sample"}],
  ["u9.report_candidate_only","候補のみ（自動では紐付けていない）",{}],
  ["u9.report_low_match","元Modのキーとの一致が少ない（重み付き sample）",{"percent":"sample"}],
  ["u9.report_names_unrelated","名前が似ていない",{}],
  ["u9.report_multiple_sources","同じ日本語化Modが複数の元Modに紐付いている",{}],
  ["u9.report_review_line","- 要確認：sample",{"review_reason":"sample"}],
  ["u9.no_record","（記録なし）",{}],
  ["u9.report_evidence_line","- 根拠：sample",{"evidence":"sample"}],
  ["u9.report_source_path","- 元Modの場所：sample",{"source_path":"sample"}],
  ["u9.report_target_path","- 紐付け先の場所：sample",{"target_path":"sample"}],
  ["u9.empty_llm_response","LLMから空の応答が返されました",{}],
  ["u9.batch_failed","  [警告] バッチ失敗: sample",{"error":"sample"}],
  ["u9.provider_retry_deferred","  [警告] プロバイダ障害が継続しているため、残り sample件をキュー後段の再試行へ延期します",{"count":"sample"}],
  ["u9.single_retry_unusable","単発再試行後も原文のまま、または翻訳として利用できませんでした",{}],
  ["u9.mixed_bom_repair","混在BOMを除去して読み込み、出力はUTF-8 BOMへ正規化",{}],
  ["u9.mixed_bom_detected","  [自動修復] 混在BOMを検出: sample / sample",{"path":"sample","encoding":"sample"}],
  ["u9.extra_spaces","文字の間に余分な半角スペースがsample個あります",{"count":"sample"}],
  ["u9.review_content_reason","内容を確認",{}],
  ["u9.internal_placeholder","内部プレースホルダ @@N@@ が残っています",{}],
  ["u9.missing_target_key","訳文側にキーがありません",{}],
  ["u9.extra_target_key","原文側に存在しないキーです",{}],
  ["u9.source_file_missing","原文ファイルが見つかりません: sample",{"source_path":"sample"}],
  ["u9.paratranz_affix_item","原語が「-」で始まるか終わる接辞の項目",{}],
  ["u9.paratranz_note_rule","note にルールがある（自動でプロンプトには入れません）",{}],
  ["u9.unsupported_overwrite"," 対応していない形式のファイルには上書きしません。",{}],
  ["u9.comparison_untranslated","原文のまま残っている可能性があります",{}],
  ["u9.comparison_ok","対応あり",{}],
  ["u9.chinese_qa_summary","  中国語翻訳語 自動QA・修正: error sample / warning sample / notice sample / 修正 sample件 / 試行 sample回",{"error_count":"sample","warning_count":"sample","notice_count":"sample","repaired_count":"sample","repair_attempts":"sample"}],
  ["u9.structure_localization_focused","localization中心",{}],
  ["u9.structure_localization_focused_new","localization中心",{}],
  ["u9.manual_relation_override","手動例外: この日本語化Modと元Modの対応関係をユーザーが指定",{}],
  ["u9.unusable_llm_translation","LLM応答が原文のまま、または翻訳として利用できませんでした",{}],
  ["u9.duplicate_output_skip","[sample/sample] 出力先重複のためスキップ: sample",{"index":"sample","total":"sample","file_name":"sample"}],
  ["u9.qa_repair_summary","  自動QA・修正: error sample / warning sample / notice sample / 修正 sample件 / 試行 sample回",{"error_count":"sample","warning_count":"sample","notice_count":"sample","repaired_count":"sample","repair_attempts":"sample"}],
  ["u9.review_content","内容を確認",{}],
  ["u9.specify_source_retranslate","原文を指定して再翻訳",{}],
  ["u9.retranslate_source","原文から再翻訳",{}],
  ["u9.untranslated_chinese_source","簡体字中国語の原文が未翻訳のままです",{}],
  ["u9.untranslated_source","原文が未翻訳のままです",{}],
  ["u9.token_mismatch","ゲーム変数/タグが原文と一致しません",{}],
  ["u9.translate_add_key","原文から翻訳して追加",{}],
  ["u9.review_extra_key","古いキーか独自キーか確認",{}],
  ["u9.new_output_no_improvement","新規出力のエラーが減らなかったため",{}],
  ["u9.skip_next_file","スキップして次のファイルを継続",{}],
  ["u9.paratranz_symbol_item","英字・数字・CJKの文字がない記号だけの項目",{}],
  ["u9.missing_output","対応する日本語の出力ファイルがありません",{"target_name":"日本語"}],
  ["u9.missing_japanese_output","対応する日本語出力ファイルがありません",{}],
  ["u9.structure_localization_dominant","localization優勢",{}],
  ["u9.structure_localization_dominant_new","localization優勢",{}],
  ["u9.manual_translation_override","手動例外: このModを日本語化Modとして固定（対応元は自動判定）",{}],
  ["u9.mod_no_translation","sampleというModは日本語翻訳がありません。日本語化Modも確認できませんでした。",{"mod_name":"sample"}],
  ["u9.proper_noun_notice","固有名詞の可能性があるため原文同一表記を注意として扱います",{}],
  ["u9.identical_source","原文と同じ表記です（固有名詞なら問題ありません）",{}],
  ["u9.repair_tokens_action","安全なトークン修復後、必要なら再翻訳",{}],
  ["u9.glossary_not_applied","用語集指定『sample → sample』が訳文に反映されていません",{"source_term":"sample","target_term":"sample"}],
  ["u9.review_glossary","用語集と訳文を確認",{}],
  ["u9.structure_mixed","localization混在",{}],
  ["u9.structure_gameplay","ゲーム内容中心",{}],
  ["u9.structure_mixed_new","localization混在",{}],
  ["u9.structure_gameplay_new","ゲーム内容中心",{}],
  ["u9.mod_translated_fallback","sampleのModは日本語翻訳が確認できました。",{"mod_name":"sample"}],
  ["u9.review_proper_noun","固有名詞として適切か確認",{}],
  ["u9.retranslate_unchanged","原文から再翻訳",{}],
  ["u9.review_identical_source","固有名詞か、訳し忘れかを確認",{}],
  ["u9.unsupported_provider","未対応のプロバイダです: sample",{"provider":"sample"}],
  ["u9.file_translation_summary_repair","  原文言語: sample（修復） / 全キー: sample / 翻訳対象: sample",{"source_lang":"sample","total_keys":"sample","translation_count":"sample"}],
  ["u9.mod_external_gaps_none","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 欠損なし。",{"name":"sample","gap_count":4,"mod":"sample"}],
  ["u9.mod_external_gaps_english_only","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1}],
  ["u9.mod_external_gaps_chinese_only","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"mod":"sample","chinese_only":1}],
  ["u9.mod_external_gaps_english_only_chinese_only","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"chinese_only":1}],
  ["u9.mod_external_gaps_shared","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"mod":"sample","shared":1}],
  ["u9.mod_external_gaps_english_only_shared","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"shared":1}],
  ["u9.mod_external_gaps_chinese_only_shared","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"mod":"sample","chinese_only":1,"shared":1}],
  ["u9.mod_external_gaps_english_only_chinese_only_shared","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"chinese_only":1,"shared":1}],
  ["u9.mod_external_gaps_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","other":1}],
  ["u9.mod_external_gaps_english_only_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"other":1}],
  ["u9.mod_external_gaps_chinese_only_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","chinese_only":1,"other":1}],
  ["u9.mod_external_gaps_english_only_chinese_only_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"chinese_only":1,"other":1}],
  ["u9.mod_external_gaps_shared_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","shared":1,"other":1}],
  ["u9.mod_external_gaps_english_only_shared_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"shared":1,"other":1}],
  ["u9.mod_external_gaps_chinese_only_shared_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","chinese_only":1,"shared":1,"other":1}],
  ["u9.mod_external_gaps_english_only_chinese_only_shared_other","sampleには日本語化Mod『sample』がありますが、翻訳に欠損があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"mod":"sample","english_only":1,"chinese_only":1,"shared":1,"other":1}],
  ["u9.mod_translation_gaps_none","sampleのModに翻訳の欠損箇所があります（4件）。 欠損なし。",{"name":"sample","gap_count":4}],
  ["u9.mod_translation_gaps_english_only","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"english_only":1}],
  ["u9.mod_translation_gaps_chinese_only","sampleのModに翻訳の欠損箇所があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"chinese_only":1}],
  ["u9.mod_translation_gaps_english_only_chinese_only","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如。",{"name":"sample","gap_count":4,"english_only":1,"chinese_only":1}],
  ["u9.mod_translation_gaps_shared","sampleのModに翻訳の欠損箇所があります（4件）。 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"shared":1}],
  ["u9.mod_translation_gaps_english_only_shared","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"english_only":1,"shared":1}],
  ["u9.mod_translation_gaps_chinese_only_shared","sampleのModに翻訳の欠損箇所があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"chinese_only":1,"shared":1}],
  ["u9.mod_translation_gaps_english_only_chinese_only_shared","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳。",{"name":"sample","gap_count":4,"english_only":1,"chinese_only":1,"shared":1}],
  ["u9.mod_translation_gaps_other","sampleのModに翻訳の欠損箇所があります（4件）。 その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"other":1}],
  ["u9.mod_translation_gaps_english_only_other","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"english_only":1,"other":1}],
  ["u9.mod_translation_gaps_chinese_only_other","sampleのModに翻訳の欠損箇所があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"chinese_only":1,"other":1}],
  ["u9.mod_translation_gaps_english_only_chinese_only_other","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"english_only":1,"chinese_only":1,"other":1}],
  ["u9.mod_translation_gaps_shared_other","sampleのModに翻訳の欠損箇所があります（4件）。 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"shared":1,"other":1}],
  ["u9.mod_translation_gaps_english_only_shared_other","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"english_only":1,"shared":1,"other":1}],
  ["u9.mod_translation_gaps_chinese_only_shared_other","sampleのModに翻訳の欠損箇所があります（4件）。 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"chinese_only":1,"shared":1,"other":1}],
  ["u9.mod_translation_gaps_english_only_chinese_only_shared_other","sampleのModに翻訳の欠損箇所があります（4件）。 英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如 / 英語・簡体字中国語の共通キーで 1件が欠如または未翻訳 / その他の翻訳不足 1件。",{"name":"sample","gap_count":4,"english_only":1,"chinese_only":1,"shared":1,"other":1}],
  ["u9.warning_text","警告: sample",{"warnings":"sample"}],
  ["u9.warnings_legacy","警告: 古い日本語化方式の可能性があります。日本語文が英語localization（l_english）として収録されています。",{}],
  ["u9.warnings_source","警告: 日本語化Mod形式ですが対応元Modを自動特定できません。対応元Modの未導入、古いバージョン、またはキーの大幅な変更が考えられます。",{}],
  ["u9.warnings_legacy_source","警告: 古い日本語化方式の可能性があります。日本語文が英語localization（l_english）として収録されています。 日本語化Mod形式ですが対応元Modを自動特定できません。対応元Modの未導入、古いバージョン、またはキーの大幅な変更が考えられます。",{}],
  ["u9.column_game","ゲーム",{}],
  ["u9.column_source_mod","元Mod",{}],
  ["u9.column_source_storage","元Modの保管場所",{}],
  ["u9.column_status","状態",{}],
  ["u9.column_linked_mod","紐付け先",{}],
  ["u9.column_linked_storage","紐付け先の保管場所",{}],
  ["u9.column_type","種別",{}],
  ["u9.column_score","点数",{}],
  ["u9.column_source_match","元Mod側の一致率",{}],
  ["u9.column_translation_match","日本語化Mod側の一致率",{}],
  ["u9.column_source_weighted","重み付き一致率（元Mod側）",{}],
  ["u9.column_translation_weighted","重み付き一致率（日本語化Mod側）",{}],
  ["u9.column_review","要確認",{}],
  ["u9.column_evidence","根拠",{}],
  ["u9.column_source_path","元Modの場所",{}],
  ["u9.column_linked_path","紐付け先の場所",{}],
  ["u9.exception_detail","sample",{"detail":"sample"}],
  ["u9.unsupported_game_language_with_preset","sample は日本語（l_sample）を読めません（Mod の場所からゲームが分からないため、ゲームプリセットから判断）。翻訳しても、ゲームの中には表示されません。sample が読める言語: sample",{"game":"sample","target_name":"日本語","target_lang":"sample","supported_game":"sample","supported_languages":"sample"}],
  ["u9.glossary_paratranz_format","対応していない形式です（sample）。このアプリの用語集は {\"原語\": \"訳語\"} 形式のJSONです。ParaTranz の用語集は『ParaTranz の用語集を取り込む』から取り込めます。ParaTranz の用語集のようです。",{"format_name":"sample"}],
  ["u9.comparison_missing.english","英語側にキーがありません",{}],
  ["u9.comparison_missing.french","フランス語側にキーがありません",{}],
  ["u9.comparison_missing.german","ドイツ語側にキーがありません",{}],
  ["u9.comparison_missing.spanish","スペイン語側にキーがありません",{}],
  ["u9.comparison_missing.japanese","日本語側にキーがありません",{}],
  ["u9.comparison_missing.korean","韓国語側にキーがありません",{}],
  ["u9.comparison_missing.polish","ポーランド語側にキーがありません",{}],
  ["u9.comparison_missing.braz_por","ポルトガル語（ブラジル）側にキーがありません",{}],
  ["u9.comparison_missing.russian","ロシア語側にキーがありません",{}],
  ["u9.comparison_missing.simp_chinese","簡体字中国語側にキーがありません",{}],
  ["u9.comparison_missing.turkish","トルコ語側にキーがありません",{}],
  ["u9.comparison_extra.english","英語側だけに存在するキーです",{}],
  ["u9.comparison_extra.french","フランス語側だけに存在するキーです",{}],
  ["u9.comparison_extra.german","ドイツ語側だけに存在するキーです",{}],
  ["u9.comparison_extra.spanish","スペイン語側だけに存在するキーです",{}],
  ["u9.comparison_extra.japanese","日本語側だけに存在するキーです",{}],
  ["u9.comparison_extra.korean","韓国語側だけに存在するキーです",{}],
  ["u9.comparison_extra.polish","ポーランド語側だけに存在するキーです",{}],
  ["u9.comparison_extra.braz_por","ポルトガル語（ブラジル）側だけに存在するキーです",{}],
  ["u9.comparison_extra.russian","ロシア語側だけに存在するキーです",{}],
  ["u9.comparison_extra.simp_chinese","簡体字中国語側だけに存在するキーです",{}],
  ["u9.comparison_extra.turkish","トルコ語側だけに存在するキーです",{}],
  ["u9.missing_output.english","対応する英語の出力ファイルがありません",{}],
  ["u9.missing_output.french","対応するフランス語の出力ファイルがありません",{}],
  ["u9.missing_output.german","対応するドイツ語の出力ファイルがありません",{}],
  ["u9.missing_output.spanish","対応するスペイン語の出力ファイルがありません",{}],
  ["u9.missing_output.japanese","対応する日本語の出力ファイルがありません",{}],
  ["u9.missing_output.korean","対応する韓国語の出力ファイルがありません",{}],
  ["u9.missing_output.polish","対応するポーランド語の出力ファイルがありません",{}],
  ["u9.missing_output.braz_por","対応するポルトガル語（ブラジル）の出力ファイルがありません",{}],
  ["u9.missing_output.russian","対応するロシア語の出力ファイルがありません",{}],
  ["u9.missing_output.simp_chinese","対応する簡体字中国語の出力ファイルがありません",{}],
  ["u9.missing_output.turkish","対応するトルコ語の出力ファイルがありません",{}]
]
''')


@pytest.fixture(autouse=True)
def restore_ui_language():
    previous = i18n.get_ui_language()
    i18n.set_ui_language("japanese")
    yield
    i18n.set_ui_language(previous)


@pytest.mark.parametrize("key,expected,fields", SNAPSHOTS, ids=[row[0] for row in SNAPSHOTS])
def test_japanese_original_strings(key, expected, fields):
    assert i18n.t(key, **fields) == expected


def test_all_u9_keys_are_in_english():
    i18n.set_ui_language("english")
    japanese = {key for key in i18n.strings("japanese") if key.startswith("u9.")}
    english = {key for key in i18n.strings("english") if key.startswith("u9.")}
    assert japanese == english == {row[0] for row in SNAPSHOTS}
    for key, _, fields in SNAPSHOTS:
        assert i18n.t(key, **fields) != key


def test_u9_placeholders_have_meaningful_names():
    root = Path(__file__).resolve().parents[1]
    for relative_path in (
        "app/i18n/japanese/u9_core.py",
        "app/i18n/english/u9_core.py",
        "app/translator_core.py",
    ):
        assert not re.search(r"field_[0-9]+", (root / relative_path).read_text(encoding="utf-8")), relative_path


def test_u9_placeholder_names_and_formats_match():
    formatter = Formatter()
    japanese = i18n.strings("japanese")
    english = i18n.strings("english")
    for key, _, fields in SNAPSHOTS:
        japanese_fields = {
            (name, format_spec, conversion)
            for _, name, format_spec, conversion in formatter.parse(japanese[key])
            if name is not None
        }
        english_fields = {
            (name, format_spec, conversion)
            for _, name, format_spec, conversion in formatter.parse(english[key])
            if name is not None
        }
        assert japanese_fields == english_fields, key
        assert {name for name, _, _ in japanese_fields} == set(fields), key


def test_comparison_messages_are_saved_and_rebuilt():
    results = core.compare_localization_entries({"missing": "Source", "same": "$VALUE$"}, {"extra": "余分", "same": "$VALUE$"})
    originals = {"missing": "日本語側にキーがありません", "extra": "日本語側だけに存在するキーです", "same": "対応あり"}
    for result in results:
        assert result["message"] == originals[result["key"]]
        assert result["message_parts"]
    i18n.set_ui_language("english")
    for result in results:
        assert ui_status.display_message(result) != result["message"]


def test_qa_messages_are_saved_and_rebuilt():
    results = core.qa_entries({"one": "@@1@@", "extra": "$VALUE$"}, {"one": "Source", "missing": "Missing"})
    assert results
    for result in results:
        assert ui_status.build_message(result["message_parts"]) == result["message"]
    i18n.set_ui_language("english")
    for result in results:
        assert ui_status.display_message(result) != result["message"]


def test_analyze_missing_localization_rebuilds(monkeypatch, tmp_path):
    monkeypatch.setattr(core, "mod_localization_root", lambda path: None)
    monkeypatch.setattr(core, "detect_mod_name", lambda path: "Test Mod")
    result = core.analyze_mod_translation_status(tmp_path)
    assert result["message"] == "Test Modのlocalizationフォルダを確認できませんでした。"
    assert result["message_parts"] == [ui_status.message_part("u9.mod_localization_missing", mod_name="Test Mod")]
    i18n.set_ui_language("english")
    assert ui_status.display_message(result) == "Could not find Test Mod’s localization folder."


def test_warning_parts_rebuild_without_duplicate(monkeypatch):
    result = {"message_parts": [ui_status.message_part("u9.mod_translated", mod_name="Test Mod")], "translation_warnings": [i18n.t("u9.legacy_translation_warning")], "translation_warning_ids": ["legacy"], "translation_format_profile": {"legacy_english_japanese_layout": True}}
    result["message"] = ui_status.build_message(result["message_parts"])
    core.apply_translation_warning_status(result)
    expected = "Test ModのModは日本語翻訳が確認できました。 警告: 古い日本語化方式の可能性があります。日本語文が英語localization（l_english）として収録されています。"
    assert result["message"] == expected
    core.apply_translation_warning_status(result)
    assert result["message"] == expected
    i18n.set_ui_language("english")
    core.apply_translation_warning_status(result)
    assert len(result["message_parts"]) == 2
    assert "Warning: Possibly an old Japanese translation format." in ui_status.display_message(result)


def test_report_english_default_title_and_headers():
    i18n.set_ui_language("english")
    assert core.relation_report_markdown({}).startswith("# Relation report\n")
    assert core.relation_report_csv({}) == "Game,Source mod,Linked mod,Review\n"


MOVED_STRING_COUNTS = {
  "<module>": 0,
  "_external_gap_candidates": 0,
  "_normalize_mod_name_for_match": 0,
  "_translation_mod_weight": 22,
  "_translation_mod_weight_legacy": 25,
  "analyze_mod_translation_status": 10,
  "apply_translation_warning_status": 1,
  "auto_repair_qa_pairs": 3,
  "build_relation_report": 6,
  "call_llm_raw": 3,
  "classify_paratranz_glossary": 1,
  "classify_paratranz_glossary.add_source": 5,
  "compare_localization_entries": 4,
  "discover_paradox_mod_locations": 0,
  "embedding_only_model_warning": 1,
  "game_language_warning": 2,
  "gap_reason_text": 5,
  "glossary_file_problem": 6,
  "looks_like_proper_noun_candidate": 2,
  "mod_location_kind": 1,
  "normalize_cjk_spacing": 0,
  "normalize_provider": 0,
  "process_file": 9,
  "qa_chinese_basis_translation": 1,
  "qa_entries": 23,
  "qa_file_with_auto_repair": 1,
  "qa_translation_output": 1,
  "rank_external_japanese_translations": 2,
  "reasoning_model_warning_text": 1,
  "relation_report_csv": 0,
  "relation_report_markdown": 13,
  "run_chinese_basis_translation": 3,
  "run_translation": 12,
  "run_translation.collect_file_error": 1,
  "save_paratranz_import": 4,
  "scan_translation_gaps": 0,
  "source_language_gap_reason_text": 3,
  "thinking_only_model_warning": 1,
  "translation_localization_format_profile": 0,
  "translation_localization_warnings": 2,
  "translation_relation_evidence": 2
}

JAPANESE_LANGUAGE_AUDIT = json.loads(r'''
[
  {
    "owner": "<module>",
    "line": 86,
    "text": "日本語",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "<module>",
    "line": 246,
    "text": "Paradox Interactiveゲーム全般。簡潔で自然なUI日本語を優先する。",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "gap_reason_text",
    "line": 1602,
    "text": "f\"英語にのみ存在するキーのうち、日本語訳が必要な {counts['english_only']}件が欠如\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "gap_reason_text",
    "line": 1604,
    "text": "f\"簡体字中国語にのみ存在するキーのうち、日本語訳が必要な {counts['chinese_only']}件が欠如\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "scan_translation_gaps",
    "line": 1660,
    "text": "日本語キーなし",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "qa_chinese_basis_translation",
    "line": 3795,
    "text": "対応する日本語出力ファイルがありません",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "translation_localization_format_profile",
    "line": 4097,
    "text": "japanese|translation|locali[sz]ation|日本語|(?:^|[^a-z0-9])\\+?jp(?:[^a-z0-9]|$)",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "translation_localization_warnings",
    "line": 4129,
    "text": "古い日本語化方式の可能性があります。日本語文が英語localization（l_english）として収録されています。",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "translation_localization_warnings",
    "line": 4136,
    "text": "日本語化Mod形式ですが対応元Modを自動特定できません。対応元Modの未導入、古いバージョン、またはキーの大幅な変更が考えられます。",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "apply_translation_warning_status",
    "line": 4148,
    "text": "要確認（旧式日本語化）",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_normalize_mod_name_for_match",
    "line": 4289,
    "text": "日本語化",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_normalize_mod_name_for_match",
    "line": 4289,
    "text": "日本語",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4432,
    "text": "日本語localization専用（大幅加点）",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4438,
    "text": "日本語化補助ファイルのみ",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4552,
    "text": "f\"参考: 日本語化Mod側一致率 {precision*100:.1f}% ({overlap_n}/{len(ja_keys)})\"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4553,
    "text": "f\"構成評価 {structure_label}: 日本語YAML {japanese_file_count} / 他言語YAML {non_japanese_loc_files} / localization比率 {loc_ratio*100:.1f}% / 非localization {non_loc}ファイル → {translation_only_points:.1f}点\"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4570,
    "text": "f\"日本語化Mod側から見たゲーム本体キー一致率 {base_game_match_ratio*100:.1f}% \"\n                f\"({base_game_match_n}/{len(ja_keys)}) / 70%以上 → 本体和訳修正の可能性が高いため \"\n                f\"{base_game_penalty:.1f}点\"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4576,
    "text": "f\"日本語化Mod側から見たゲーム本体キー一致率 {base_game_match_ratio*100:.1f}% \"\n                f\"({base_game_match_n}/{len(ja_keys)}) / 70%未満 → 減点なし\"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight_legacy",
    "line": 4583,
    "text": "f\"日本語localization専用の例外ゲート: 日本語化Mod側一致率 {precision*100:.1f}% / \"\n            f\"完全一致 {overlap_n}キー → 関係判定対象\"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight",
    "line": 4946,
    "text": "日本語localization専用（大幅加点）",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight",
    "line": 4952,
    "text": "日本語化補助ファイルのみ",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight",
    "line": 5060,
    "text": "f\"情報量で重み付けした一致率（多くのModに共通するキーほど軽く数える）: \"\n        f\"元Mod側 {float(evidence.get('weighted_source_rate',0.0))*100:.1f}% / \"\n        f\"日本語化Mod側 {float(evidence.get('weighted_candidate_rate',0.0))*100:.1f}% → \"",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight",
    "line": 5070,
    "text": "候補が原文と日本語を80%以上同梱する独立Mod型で、明示的な関係証拠がないため除外",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "_translation_mod_weight",
    "line": 5072,
    "text": "候補が本体キー80%以上・50キー以上の本体日本語化型で、明示的な関係証拠がないため除外",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "rank_external_japanese_translations",
    "line": 5269,
    "text": "手動例外: この日本語化Modと元Modの対応関係をユーザーが指定",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "rank_external_japanese_translations",
    "line": 5273,
    "text": "手動例外: このModを日本語化Modとして固定（対応元は自動判定）",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5465,
    "text": "f\"{name}のModは日本語翻訳が確認できました。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5467,
    "text": "f\" 別Mod『{external['mod']}』にも日本語化があります。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5475,
    "text": "f\"{name}には日本語化Mod『{external['mod']}』があり、完全な日本語化を確認できました。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5480,
    "text": "f\"{name}には日本語化Mod『{external['mod']}』がありますが、翻訳に欠損があります（{result['gap_count']}件）。 {gap_reason_text(result['candidates'])}。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5483,
    "text": "f\"{name}というModは日本語翻訳がありません。日本語化Modも確認できませんでした。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5489,
    "text": "f\"{name}のModは日本語翻訳が確認できました。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "analyze_mod_translation_status",
    "line": 5491,
    "text": "f\" 日本語化Mod候補『{review_candidate.get('mod','')}』を検出しましたが、\"\n                              f\"関連度 {float(review_candidate.get('score',0.0) or 0.0):.1f}/100 のため自動関連付けしていません。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "<module>",
    "line": 5886,
    "text": "日本語化",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "<module>",
    "line": 5886,
    "text": "日本語",
    "classification": "本当に日本語（言語名・日本語専用判定・日本語を検査する説明）"
  },
  {
    "owner": "build_relation_report",
    "line": 5951,
    "text": "日本語化Mod側の一致率",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "build_relation_report",
    "line": 5953,
    "text": "重み付き一致率（日本語化Mod側）",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "build_relation_report",
    "line": 5982,
    "text": "同じ日本語化Modが複数の元Modに紐付いている",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "build_relation_report",
    "line": 5988,
    "text": "日本語化Mod",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6023,
    "text": "\"「要確認」の印の意味：候補のみ＝自動では紐付けていない／一致が少ない＝元Modのキーのうち日本語化Modにもある割合\"\n           f\"（重み付き）が{RELATION_REPORT_LOW_COVERAGE*100:.0f}%未満／名前が似ていない＝名前に共通の語が無い／\"\n           \"複数に紐付き＝同じ日本語化Modが2つ以上の元Modに紐付いている（総合和訳なら正しいこともある）。\"",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6027,
    "text": "| 要確認 | ゲーム | 元Mod | 元Modの保管場所 | 状態 | 紐付け先 | 紐付け先の保管場所 | 種別 | 点数 | 重み付き一致率（元Mod側） | 重み付き一致率（日本語化Mod側） |",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6032,
    "text": "重み付き一致率（日本語化Mod側）",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6033,
    "text": "## 日本語化Modごとの紐付け先",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6034,
    "text": "| 日本語化Mod | 保管場所 | 元Modの数 | 元Mod |",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  },
  {
    "owner": "relation_report_markdown",
    "line": 6036,
    "text": "日本語化Mod",
    "classification": "翻訳先の言語（target_lang がないため汎用化を保留）"
  }
]
''')

U9_INTERNAL_LITERALS = json.loads(r'''
[
  [
    "<module>",
    "英語"
  ],
  [
    "<module>",
    "フランス語"
  ],
  [
    "<module>",
    "ドイツ語"
  ],
  [
    "<module>",
    "スペイン語"
  ],
  [
    "<module>",
    "日本語"
  ],
  [
    "<module>",
    "韓国語"
  ],
  [
    "<module>",
    "ポーランド語"
  ],
  [
    "<module>",
    "ポルトガル語（ブラジル）"
  ],
  [
    "<module>",
    "ロシア語"
  ],
  [
    "<module>",
    "簡体字中国語"
  ],
  [
    "<module>",
    "トルコ語"
  ],
  [
    "game_language_warning",
    "・"
  ],
  [
    "normalize_cjk_spacing",
    "・"
  ],
  [
    "<module>",
    "Paradox Interactiveゲーム全般。簡潔で自然なUI日本語を優先する。"
  ],
  [
    "<module>",
    "Crusader Kings III。中世の称号・封建制・宮廷・宗教・制度の歴史語彙を重視する。"
  ],
  [
    "<module>",
    "Victoria 3。19世紀の政治・経済・産業・外交用語を重視する。"
  ],
  [
    "<module>",
    "Hearts of Iron IV。20世紀前半の軍事・政治・外交・装備用語を重視する。"
  ],
  [
    "<module>",
    "Stellaris。SF、宇宙政治、技術、艦船、異星文明の用語を自然に訳す。"
  ],
  [
    "<module>",
    "Europa Universalis V。中世後期から近世・近代初期の政治・外交・宗教・交易・軍事・制度語彙を重視する。"
  ],
  [
    "normalize_provider",
    "openai互換"
  ],
  [
    "<module>",
    "Thinking専用モデル"
  ],
  [
    "<module>",
    "埋め込み専用モデル"
  ],
  [
    "<module>",
    "考える過程に時間を使うモデル"
  ],
  [
    "scan_translation_gaps",
    "英語固有キー欠損"
  ],
  [
    "scan_translation_gaps",
    "中国語固有キー欠損"
  ],
  [
    "scan_translation_gaps",
    "日本語キーなし"
  ],
  [
    "scan_translation_gaps",
    "確定"
  ],
  [
    "scan_translation_gaps",
    "英語/外国語残り"
  ],
  [
    "scan_translation_gaps",
    "要確認"
  ],
  [
    "scan_translation_gaps",
    "高"
  ],
  [
    "run_translation",
    "読み込み・文字コード判定"
  ],
  [
    "run_translation",
    "翻訳処理"
  ],
  [
    "run_translation",
    "翻訳後QA"
  ],
  [
    "classify_paratranz_glossary.add_source",
    "ルール"
  ],
  [
    "classify_paratranz_glossary.add_source",
    "入れないように"
  ],
  [
    "classify_paratranz_glossary.add_source",
    "しないように"
  ],
  [
    "classify_paratranz_glossary.add_source",
    "禁止"
  ],
  [
    "translation_localization_format_profile",
    "japanese|translation|locali[sz]ation|日本語|(?:^|[^a-z0-9])\\+?jp(?:[^a-z0-9]|$)"
  ],
  [
    "translation_localization_format_profile",
    "[\\u3041-\\u3096\\u30a1-\\u30faー]"
  ],
  [
    "_normalize_mod_name_for_match",
    "日本語化"
  ],
  [
    "_normalize_mod_name_for_match",
    "日本語"
  ],
  [
    "_external_gap_candidates",
    "確定"
  ],
  [
    "_external_gap_candidates",
    "確定"
  ],
  [
    "_external_gap_candidates",
    "要確認"
  ],
  [
    "discover_paradox_mod_locations",
    "ローカルMod"
  ],
  [
    "<module>",
    "日本語化"
  ],
  [
    "<module>",
    "日本語"
  ],
  [
    "<module>",
    "翻訳"
  ],
  [
    "<module>",
    "和訳"
  ],
  [
    "build_relation_report",
    "ゲーム"
  ],
  [
    "build_relation_report",
    "元Mod"
  ],
  [
    "build_relation_report",
    "元Modの保管場所"
  ],
  [
    "build_relation_report",
    "状態"
  ],
  [
    "build_relation_report",
    "紐付け先"
  ],
  [
    "build_relation_report",
    "紐付け先の保管場所"
  ],
  [
    "build_relation_report",
    "種別"
  ],
  [
    "build_relation_report",
    "点数"
  ],
  [
    "build_relation_report",
    "元Mod側の一致率"
  ],
  [
    "build_relation_report",
    "日本語化Mod側の一致率"
  ],
  [
    "build_relation_report",
    "重み付き一致率（元Mod側）"
  ],
  [
    "build_relation_report",
    "重み付き一致率（日本語化Mod側）"
  ],
  [
    "build_relation_report",
    "要確認"
  ],
  [
    "build_relation_report",
    "根拠"
  ],
  [
    "build_relation_report",
    "元Modの場所"
  ],
  [
    "build_relation_report",
    "紐付け先の場所"
  ],
  [
    "build_relation_report",
    "紐付け先の場所"
  ],
  [
    "build_relation_report",
    "紐付け先の場所"
  ],
  [
    "build_relation_report",
    "紐付け先"
  ],
  [
    "build_relation_report",
    "要確認"
  ],
  [
    "build_relation_report",
    "重み付き一致率（元Mod側）"
  ],
  [
    "build_relation_report",
    "元Mod"
  ],
  [
    "build_relation_report",
    "紐付け先"
  ],
  [
    "build_relation_report",
    "紐付け先の場所"
  ],
  [
    "build_relation_report",
    "要確認"
  ],
  [
    "build_relation_report",
    "紐付け先"
  ],
  [
    "build_relation_report",
    "日本語化Mod"
  ],
  [
    "build_relation_report",
    "保管場所"
  ],
  [
    "build_relation_report",
    "元Modの数"
  ],
  [
    "build_relation_report",
    "元Mod"
  ],
  [
    "build_relation_report",
    "場所"
  ],
  [
    "build_relation_report",
    "紐付け先"
  ],
  [
    "build_relation_report",
    "紐付け先の保管場所"
  ],
  [
    "build_relation_report",
    "要確認"
  ],
  [
    "build_relation_report",
    "ゲーム"
  ],
  [
    "build_relation_report",
    "元Mod"
  ],
  [
    "relation_report_csv",
    "ゲーム"
  ],
  [
    "relation_report_csv",
    "元Mod"
  ],
  [
    "relation_report_csv",
    "紐付け先"
  ],
  [
    "relation_report_csv",
    "要確認"
  ],
  [
    "relation_report_csv",
    "ゲーム"
  ],
  [
    "relation_report_csv",
    "元Mod"
  ],
  [
    "relation_report_csv",
    "元Modの保管場所"
  ],
  [
    "relation_report_csv",
    "状態"
  ],
  [
    "relation_report_csv",
    "紐付け先"
  ],
  [
    "relation_report_csv",
    "紐付け先の保管場所"
  ],
  [
    "relation_report_csv",
    "種別"
  ],
  [
    "relation_report_csv",
    "点数"
  ],
  [
    "relation_report_csv",
    "元Mod側の一致率"
  ],
  [
    "relation_report_csv",
    "日本語化Mod側の一致率"
  ],
  [
    "relation_report_csv",
    "重み付き一致率（元Mod側）"
  ],
  [
    "relation_report_csv",
    "重み付き一致率（日本語化Mod側）"
  ],
  [
    "relation_report_csv",
    "要確認"
  ],
  [
    "relation_report_csv",
    "根拠"
  ],
  [
    "relation_report_csv",
    "元Modの場所"
  ],
  [
    "relation_report_csv",
    "紐付け先の場所"
  ],
  [
    "relation_report_csv",
    "状態"
  ],
  [
    "relation_report_markdown",
    "要確認"
  ],
  [
    "relation_report_markdown",
    "紐付け先"
  ],
  [
    "relation_report_markdown",
    "状態"
  ],
  [
    "relation_report_markdown",
    "要確認"
  ],
  [
    "relation_report_markdown",
    "ゲーム"
  ],
  [
    "relation_report_markdown",
    "元Mod"
  ],
  [
    "relation_report_markdown",
    "元Modの保管場所"
  ],
  [
    "relation_report_markdown",
    "状態"
  ],
  [
    "relation_report_markdown",
    "紐付け先"
  ],
  [
    "relation_report_markdown",
    "紐付け先の保管場所"
  ],
  [
    "relation_report_markdown",
    "種別"
  ],
  [
    "relation_report_markdown",
    "点数"
  ],
  [
    "relation_report_markdown",
    "重み付き一致率（元Mod側）"
  ],
  [
    "relation_report_markdown",
    "重み付き一致率（日本語化Mod側）"
  ],
  [
    "relation_report_markdown",
    "日本語化Mod"
  ],
  [
    "relation_report_markdown",
    "保管場所"
  ],
  [
    "relation_report_markdown",
    "元Modの数"
  ],
  [
    "relation_report_markdown",
    "元Mod"
  ],
  [
    "relation_report_markdown",
    "要確認"
  ],
  [
    "relation_report_markdown",
    "根拠"
  ],
  [
    "relation_report_markdown",
    "元Modの場所"
  ],
  [
    "relation_report_markdown",
    "紐付け先の場所"
  ],
  [
    "scan_translation_gaps",
    "英語固有キー欠損"
  ],
  [
    "scan_translation_gaps",
    "中国語固有キー欠損"
  ],
  [
    "scan_translation_gaps",
    "日本語キーなし"
  ],
  [
    "discover_paradox_mod_locations",
    "ローカルMod"
  ],
  [
    "run_translation",
    "読み込み・文字コード判定"
  ],
  [
    "run_translation",
    "翻訳処理"
  ],
  [
    "run_translation",
    "翻訳後QA"
  ]
]
''')


def test_no_unlisted_u9_internal_japanese_literals():
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tools"))
    import i18n_scan
    import i18n_exclusions
    allowed = {tuple(row) for row in U9_INTERNAL_LITERALS}
    owners = set(MOVED_STRING_COUNTS)
    for row in i18n_scan.japanese_strings(root / "app" / "translator_core.py"):
        if row["owner"] in owners and row["text"] not in i18n_exclusions.EXCLUDED_VALUES:
            assert (row["owner"], row["text"]) in allowed, row


@pytest.mark.parametrize("target_lang", i18n.UI_LANGUAGES)
def test_all_target_names_preserve_japanese_and_follow_ui(target_lang):
    expected_name = core.TARGET_LANGUAGES[target_lang]["label"]
    result = core.compare_localization_entries({"key": "Source"}, {}, target_lang=target_lang)[0]
    assert result["message"] == f"{expected_name}側にキーがありません"
    i18n.set_ui_language("english")
    result = core.compare_localization_entries({"key": "Source"}, {}, target_lang=target_lang)[0]
    assert result["message"] == f"The key is missing on the {i18n.t('lang.' + target_lang)} side"


@pytest.mark.parametrize("target_lang", i18n.UI_LANGUAGES)
def test_saved_target_name_is_relocalized(target_lang):
    result = core.compare_localization_entries({"key": "Source"}, {}, target_lang=target_lang)[0]
    i18n.set_ui_language("english")
    assert ui_status.display_message(result) == f"The key is missing on the {i18n.t('lang.' + target_lang)} side"


def test_glossary_format_messages_match_original(tmp_path):
    path = tmp_path / "glossary.json"
    path.write_text('[ {"term": "source", "translation": "target"} ]', encoding="utf-8")
    assert core.glossary_file_problem(path) == ('対応していない形式です（リスト形式）。このアプリの用語集は {"原語": "訳語"} 形式のJSONです。ParaTranz の用語集は『ParaTranz の用語集を取り込む』から取り込めます。ParaTranz の用語集のようです。')


@pytest.mark.parametrize("direct", [True, False])
def test_game_warning_matches_original(monkeypatch, direct):
    game = "Europa Universalis IV"
    monkeypatch.setattr(core, "game_for_translation", lambda path, preset="": game if direct or preset else "")
    basis = "" if direct else "（Mod の場所からゲームが分からないため、ゲームプリセットから判断）"
    names = "・".join(core.target_language_label(lang) for lang in core.GAME_LANGUAGES[game])
    assert core.game_language_warning("japanese", preset="General") == (f"{game} は日本語（l_japanese）を読めません{basis}。翻訳しても、ゲームの中には表示されません。{game} が読める言語: {names}")


@pytest.mark.parametrize("external", [False, True])
@pytest.mark.parametrize("mask", range(1, 16))
def test_analyzed_gap_messages_preserve_original_and_rebuild(monkeypatch, tmp_path, external, mask):
    origins = ("english_only", "chinese_only", "shared", "other")
    candidates = [{"source_origin": origin} for index, origin in enumerate(origins) if mask & (1 << index)]
    source_file = tmp_path / "english.yml"
    target_file = tmp_path / "japanese.yml"
    monkeypatch.setattr(core, "mod_localization_root", lambda path: tmp_path)
    monkeypatch.setattr(core, "detect_mod_name", lambda path: "Test Mod")
    monkeypatch.setattr(core, "gather_yml_files", lambda path: [source_file, target_file])
    monkeypatch.setattr(core, "parse_localization_file", lambda path: (
        "english" if path == source_file else "japanese", {"key": "Source"}, []))
    monkeypatch.setattr(core, "scan_translation_gaps", lambda path, preferred_source="english": candidates)
    monkeypatch.setattr(core, "translation_localization_format_profile", lambda path, entries: {})
    monkeypatch.setattr(core, "find_external_japanese_translation", lambda path, index: (
        {"mod": "Add-on", "complete": False, "gaps": candidates, "gap_count": len(candidates)} if external else None))
    result = core.analyze_mod_translation_status(tmp_path)
    reasons = {
        "english_only": "英語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如",
        "chinese_only": "簡体字中国語にのみ存在するキーのうち、日本語訳が必要な 1件が欠如",
        "shared": "英語・簡体字中国語の共通キーで 1件が欠如または未翻訳",
        "other": "その他の翻訳不足 1件",
    }
    details = " / ".join(reasons[origin] for index, origin in enumerate(origins) if mask & (1 << index))
    expected = (f"Test Modには日本語化Mod『Add-on』がありますが、翻訳に欠損があります（{len(candidates)}件）。 {details}。"
                if external else f"Test ModのModに翻訳の欠損箇所があります（{len(candidates)}件）。 {details}。")
    assert result["message"] == expected
    assert ui_status.build_message(result["message_parts"]) == expected
    fields = result["message_parts"][0]["fields"]
    assert all(isinstance(value, int) or value in ("Test Mod", "Add-on") for value in fields.values())
    saved = json.loads(json.dumps(result))
    i18n.set_ui_language("english")
    assert ui_status.display_message(saved) != expected
    assert "日本語" not in ui_status.display_message(saved)


def test_report_status_is_displayed_without_changing_stored_value():
    report = {"rows": [{"ゲーム": "Game", "元Mod": "Source", "状態": "翻訳あり"}]}
    assert "翻訳あり" in core.relation_report_csv(report)
    i18n.set_ui_language("english")
    assert ui_status.display_status("翻訳あり") in core.relation_report_csv(report)
    assert report["rows"][0]["状態"] == "翻訳あり"
