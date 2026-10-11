"""U4 Glossary display snapshots; no App import or Tk window creation."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
import i18n
from i18n.english.u4_glossary import STRINGS as ENGLISH
from i18n.japanese.u4_glossary import STRINGS as JAPANESE

CASES = [('App._build_glossary_tab', '"言語"', 'u4.language', {}, {}, '言語'),
 ('App._build_glossary_tab',
  'f"この言語のファイル: {_selected_glossary_path(self)}"',
  'u4.language_file',
  {'path': '_selected_glossary_path(self)'},
  {'path': '/tmp/用語集.json'},
  'この言語のファイル: /tmp/用語集.json'),
 ('App._build_glossary_tab', '"用語集設定"', 'u4.settings', {}, {}, '用語集設定'),
 ('App._build_glossary_tab', '"用語集ファイル"', 'u4.file', {}, {}, '用語集ファイル'),
 ('App._build_glossary_tab', '"読込"', 'u4.load', {}, {}, '読込'),
 ('App._build_glossary_tab', '"保存"', 'u4.save', {}, {}, '保存'),
 ('App._build_glossary_tab', '"ParaTranz の用語集（JSON）を取り込む"', 'u4.paratranz_import', {}, {}, 'ParaTranz の用語集（JSON）を取り込む'),
 ('App._build_glossary_tab', '"表記ルールを見る"', 'u4.view_rules', {}, {}, '表記ルールを見る'),
 ('App._build_glossary_tab', '"自分で作った用語"', 'u4.manual_terms', {}, {}, '自分で作った用語'),
 ('App._build_glossary_tab', '"自動生成 / 取り込み用語"', 'u4.generated_terms', {}, {}, '自動生成 / 取り込み用語'),
 ('App._build_glossary_tab', '"用語追加"', 'u4.add_term', {}, {}, '用語追加'),
 ('App._build_glossary_tab', '"選択編集"', 'u4.edit_selected', {}, {}, '選択編集'),
 ('App._build_glossary_tab', '"選択削除"', 'u4.delete_selected', {}, {}, '選択削除'),
 ('App._build_glossary_tab',
  '"手動で固定した原語 → 日本語訳です。手動用語は自動生成で上書きされません。"',
  'u4.manual_help',
  {'target_name': 'i18n.t("lang." + _glossary_language(self))'},
  {'target_name': '日本語'},
  '手動で固定した原語 → 日本語訳です。手動用語は自動生成で上書きされません。'),
 ('App._build_glossary_tab', '"原語"', 'u4.source', {}, {}, '原語'),
 ('App._build_glossary_tab',
  '"日本語"',
  'u4.target_heading',
  {'target_name': 'i18n.t("lang." + _glossary_language(self))'},
  {'target_name': '日本語'},
  '日本語'),
 ('App._build_glossary_tab', '"ゲーム本体から取り込む"', 'u4.import_base', {}, {}, 'ゲーム本体から取り込む'),
 ('App._build_glossary_tab', '"日本語YAMLファイルから取り込む"', 'u4.import_japanese_yaml', {}, {}, '日本語YAMLファイルから取り込む'),
 ('App._build_glossary_tab',
  '"日本語化Mod / localizationフォルダから取り込む"',
  'u4.import_japanese_mod',
  {},
  {},
  '日本語化Mod / localizationフォルダから取り込む'),
 ('App._build_glossary_tab', '"日本語化ファイル / Modから取り込む"', 'u4.import_japanese_files', {}, {}, '日本語化ファイル / Modから取り込む'),
 ('App._build_glossary_tab',
  '"※ ゲーム本体の日本語訳は［ゲーム本体から取り込む］を使うと、英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。"',
  'u4.base_help',
  {},
  {},
  '※ ゲーム本体の日本語訳は［ゲーム本体から取り込む］を使うと、英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。'),
 ('App._build_glossary_tab',
  '"通常翻訳・中国語基準翻訳・QA・差分調査で作成した用語と、ゲーム本体や既存日本語化から取り込んだ用語を表示します。自動生成は各作業タブから実行します。"',
  'u4.generated_help',
  {},
  {},
  '通常翻訳・中国語基準翻訳・QA・差分調査で作成した用語と、ゲーム本体や既存日本語化から取り込んだ用語を表示します。自動生成は各作業タブから実行します。'),
 ('App._build_glossary_tab',
  '"ドラッグ＆ドロップ対応 — 日本語YAML / 日本語化Mod / localizationフォルダ"',
  'u4.drop_help',
  {},
  {},
  'ドラッグ＆ドロップ対応 — 日本語YAML / 日本語化Mod / localizationフォルダ'),
 ('App._build_glossary_tab', '"ドラッグ＆ドロップはこのビルドでは利用できません"', 'u4.drop_unavailable', {}, {}, 'ドラッグ＆ドロップはこのビルドでは利用できません'),
 ('App._build_glossary_tab', '"定型句も用語集に入れる"', 'u4.include_phrases', {}, {}, '定型句も用語集に入れる'),
 ('App._build_glossary_tab', '"固有名詞"', 'u4.proper', {}, {}, '固有名詞'),
 ('App._build_glossary_tab', '"単語"', 'u4.term', {}, {}, '単語'),
 ('App._build_glossary_tab', '"定型句"', 'u4.phrase', {}, {}, '定型句'),
 ('App._build_glossary_tab', '"原語"', 'u4.source', {}, {}, '原語'),
 ('App._build_glossary_tab',
  '"日本語"',
  'u4.target_heading',
  {'target_name': 'i18n.t("lang." + _glossary_language(self))'},
  {'target_name': '日本語'},
  '日本語'),
 ('App._build_glossary_tab', '"由来"', 'u4.origin', {}, {}, '由来'),
 ('App._build_glossary_tab', '"種類"', 'u4.kind', {}, {}, '種類'),
 ('App._build_glossary_tab', '"note: 用語を選択すると表示します"', 'u4.note_hint', {}, {}, 'note: 用語を選択すると表示します'),
 ('App._build_glossary_tab',
  'f"ドラッグ＆ドロップ初期化失敗: {exc}"',
  'u4.dnd_failed',
  {'error': 'exc'},
  {'error': 'テストエラー'},
  'ドラッグ＆ドロップ初期化失敗: テストエラー'),
 ('App._build_glossary_tab', '"用語集DnD初期化"', 'u4.dnd_context', {}, {}, '用語集DnD初期化'),
 ('App.save_review_glossary_term',
  '"用語集へ保存する項目をQA / 比較編集の一覧から選択してください。"',
  'u4.review_selection',
  {},
  {},
  '用語集へ保存する項目をQA / 比較編集の一覧から選択してください。'),
 ('App.save_review_glossary_term', '"選択した項目に原文がありません。"', 'u4.missing_source', {}, {}, '選択した項目に原文がありません。'),
 ('App.save_review_glossary_term',
  'f"{core.target_language_label(target_lang)}訳を入力してから用語集へ保存してください。"',
  'u4.enter_translation',
  {'target_name': 'i18n.t("lang." + target_lang)'},
  {'target_name': '日本語'},
  '日本語訳を入力してから用語集へ保存してください。'),
 ('App.save_review_glossary_term',
  'f"この原文はすでに用語集に登録されています。\\n\\n原文: {src}\\n現在: {old}\\n新規: {dst}\\n\\n手動用語として上書きしますか？"',
  'u4.overwrite_manual',
  {'source': 'src', 'old': 'old', 'target': 'dst'},
  {'source': 'Duke', 'old': '旧訳', 'target': '公爵'},
  'この原文はすでに用語集に登録されています。\n\n原文: Duke\n現在: 旧訳\n新規: 公爵\n\n手動用語として上書きしますか？'),
 ('App.save_review_glossary_term',
  'f"手動用語を保存: {src} → {dst}"',
  'u4.manual_saved_status',
  {'source': 'src', 'target': 'dst'},
  {'source': 'Duke', 'target': '公爵'},
  '手動用語を保存: Duke → 公爵'),
 ('App.save_review_glossary_term',
  'f"手動用語として用語集へ保存しました。\\n\\n{src} → {dst}"',
  'u4.manual_saved',
  {'source': 'src', 'target': 'dst'},
  {'source': 'Duke', 'target': '公爵'},
  '手動用語として用語集へ保存しました。\n\nDuke → 公爵'),
 ('App.start_auto_glossary_generation',
  '"用語取り込み中です。完了してから自動用語作成を実行してください。"',
  'u4.import_busy_generate',
  {},
  {},
  '用語取り込み中です。完了してから自動用語作成を実行してください。'),
 ('App.start_auto_glossary_generation', '"自動用語作成はすでに実行中です。"', 'u4.generation_busy', {}, {}, '自動用語作成はすでに実行中です。'),
 ('App.start_auto_glossary_generation',
  '"QA / 比較編集で原文と日本語訳を読み込んでください。"',
  'u4.review_load',
  {'target_name': 'i18n.t("lang." + _current_target_lang(self))'},
  {'target_name': '日本語'},
  'QA / 比較編集で原文と日本語訳を読み込んでください。'),
 ('App.start_auto_glossary_generation',
  '"差分調査で原文と日本語訳を読み込んでください。"',
  'u4.diff_load',
  {'target_name': 'i18n.t("lang." + _current_target_lang(self))'},
  {'target_name': '日本語'},
  '差分調査で原文と日本語訳を読み込んでください。'),
 ('App.start_auto_glossary_generation',
  '"対象キューから翻訳済み項目を選択してください。"',
  'u4.queue_selection',
  {},
  {},
  '対象キューから翻訳済み項目を選択してください。'),
 ('App.start_auto_glossary_generation',
  'f"自動用語作成中: {len(pairs)}ファイル組"',
  'u4.generating',
  {'count': 'len(pairs)'},
  {'count': 3},
  '自動用語作成中: 3ファイル組'),
 ('App.start_auto_glossary_generation', '"自動用語作成"', 'u4.generation', {}, {}, '自動用語作成'),
 ('App._refresh_auto_glossary_tree', '"固有名詞"', 'u4.proper', {}, {}, '固有名詞'),
 ('App._refresh_auto_glossary_tree', '"単語"', 'u4.term', {}, {}, '単語'),
 ('App._refresh_auto_glossary_tree', '"定型句"', 'u4.phrase', {}, {}, '定型句'),
 ('App._glossary_kind_label', '"日本語YAML"', 'u4.japanese_yaml', {}, {}, '日本語YAML'),
 ('App._glossary_kind_label', '"日本語化Mod"', 'u4.japanese_mod', {}, {}, '日本語化Mod'),
 ('App._glossary_kind_label', '"自動生成"', 'u4.generated', {}, {}, '自動生成'),
 ('App._choose_game_for_glossary_import', '"ゲーム本体から用語を取り込む"', 'u4.choose_game_title', {}, {}, 'ゲーム本体から用語を取り込む'),
 ('App._choose_game_for_glossary_import', '"用語を取り込むゲームを選択してください。"', 'u4.choose_game', {}, {}, '用語を取り込むゲームを選択してください。'),
 ('App._choose_game_for_glossary_import', '"キャンセル"', 'u4.cancel', {}, {}, 'キャンセル'),
 ('App._choose_game_for_glossary_import', '"選択"', 'u4.select', {}, {}, '選択'),
 ('App._choose_glossary_import_mode', '"用語取り込みモード"', 'u4.import_mode', {}, {}, '用語取り込みモード'),
 ('App._choose_glossary_import_mode', '"取り込む用語の範囲を選択してください。"', 'u4.choose_scope', {}, {}, '取り込む用語の範囲を選択してください。'),
 ('App._choose_glossary_import_mode', '"共通名のみ取り込み"', 'u4.common_only', {}, {}, '共通名のみ取り込み'),
 ('App._choose_glossary_import_mode',
  '"制度名・官職名・UI語など再利用しやすい短い用語を取り込み、人物名・地名・王朝名・「〇〇公爵」「〇〇軍管区長官」のような固有名詞付き候補を除外します。"',
  'u4.common_help',
  {},
  {},
  '制度名・官職名・UI語など再利用しやすい短い用語を取り込み、人物名・地名・王朝名・「〇〇公爵」「〇〇軍管区長官」のような固有名詞付き候補を除外します。'),
 ('App._choose_glossary_import_mode', '"すべて取り込み"', 'u4.import_all', {}, {}, 'すべて取り込み'),
 ('App._choose_glossary_import_mode',
  '"英語または簡体字中国語と対応付けできた項目を、長い文や固有名詞を含め原則すべて候補にします。"',
  'u4.all_help',
  {},
  {},
  '英語または簡体字中国語と対応付けできた項目を、長い文や固有名詞を含め原則すべて候補にします。'),
 ('App._choose_glossary_import_mode',
  '"※ ゲーム本体の日本語訳なら、［ゲーム本体から取り込む］で英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。\\n日本語化Mod単独の場合も、対応原文が近くになければゲーム本体との照合を案内します。"',
  'u4.import_help',
  {},
  {},
  '※ ゲーム本体の日本語訳なら、［ゲーム本体から取り込む］で英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。\n日本語化Mod単独の場合も、対応原文が近くになければゲーム本体との照合を案内します。'),
 ('App._choose_glossary_import_mode', '"キャンセル"', 'u4.cancel', {}, {}, 'キャンセル'),
 ('App._choose_glossary_import_mode', '"取り込み"', 'u4.import', {}, {}, '取り込み'),
 ('App._start_glossary_import_thread',
  '"用語取り込みをバックグラウンドで開始しました…"',
  'u4.import_started',
  {},
  {},
  '用語取り込みをバックグラウンドで開始しました…'),
 ('App._start_glossary_import_thread',
  '"自動用語作成中です。完了してから用語取り込みを実行してください。"',
  'u4.generation_busy_import',
  {},
  {},
  '自動用語作成中です。完了してから用語取り込みを実行してください。'),
 ('App._start_glossary_import_thread',
  '"用語取り込みはすでにバックグラウンドで実行中です。"',
  'u4.import_busy',
  {},
  {},
  '用語取り込みはすでにバックグラウンドで実行中です。'),
 ('App._start_glossary_import_thread.run', '"用語集バックグラウンド取り込み"', 'u4.background_context', {}, {}, '用語集バックグラウンド取り込み'),
 ('App._start_japanese_glossary_import.worker',
  '"用語取り込み中: 日本語localizationを確認しています…"',
  'u4.checking_japanese',
  {},
  {},
  '用語取り込み中: 日本語localizationを確認しています…'),
 ('App._start_japanese_glossary_import.worker',
  'f"用語取り込み中: {idx}/{total} — {target.name}"',
  'u4.import_progress',
  {'index': 'idx', 'total': 'total', 'name': 'target.name'},
  {'index': 2, 'total': 7, 'name': 'terms_l_japanese.yml'},
  '用語取り込み中: 2/7 — terms_l_japanese.yml'),
 ('App._start_japanese_glossary_import.worker',
  'f"用語候補を作成中: {len(all_pairs)}ファイル組"',
  'u4.creating_candidates',
  {'count': 'len(all_pairs)'},
  {'count': 3},
  '用語候補を作成中: 3ファイル組'),
 ('App._save_imported_glossary_candidates',
  '"取り込み可能な用語候補が見つかりませんでした。"',
  'u4.no_candidates',
  {},
  {},
  '取り込み可能な用語候補が見つかりませんでした。'),
 ('App._save_imported_glossary_candidates',
  'f"{label}: {result.get(\'added\',0)}件追加 / 候補 {result.get(\'total\',0)}件"',
  'u4.import_result',
  {'label': 'label', 'added': "result.get('added',0)", 'total': "result.get('total',0)"},
  {'label': 'テスト取り込み', 'added': 2, 'total': 7},
  'テスト取り込み: 2件追加 / 候補 7件'),
 ('App._save_imported_glossary_candidates',
  'f"{label}が完了しました。"',
  'u4.import_complete',
  {'label': 'label'},
  {'label': 'テスト取り込み'},
  'テスト取り込みが完了しました。'),
 ('App._save_imported_glossary_candidates',
  'f"候補: {result.get(\'total\',0)}件"',
  'u4.candidates',
  {'count': "result.get('total',0)"},
  {'count': 3},
  '候補: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"新規追加: {result.get(\'added\',0)}件"',
  'u4.added',
  {'count': "result.get('added',0)"},
  {'count': 3},
  '新規追加: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"日本語キー: {stats.get(\'japanese_keys\',0)}件"',
  'u4.japanese_keys',
  {'count': "stats.get('japanese_keys',0)"},
  {'count': 3},
  '日本語キー: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"英語対応: {stats.get(\'english\',0)}件"',
  'u4.english_matches',
  {'count': "stats.get('english',0)"},
  {'count': 3},
  '英語対応: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"中国語対応: {stats.get(\'chinese\',0)}件"',
  'u4.chinese_matches',
  {'count': "stats.get('chinese',0)"},
  {'count': 3},
  '中国語対応: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"対応なし: {stats.get(\'unmatched\',0)}件"',
  'u4.unmatched',
  {'count': "stats.get('unmatched',0)"},
  {'count': 3},
  '対応なし: 3件'),
 ('App._save_imported_glossary_candidates',
  'f"ゲーム本体に対応原文がないため {stats.get(\'unmatched\',0)}件をスキップしました。"',
  'u4.skipped_unmatched',
  {'count': "stats.get('unmatched',0)"},
  {'count': 3},
  'ゲーム本体に対応原文がないため 3件をスキップしました。'),
 ('App._save_imported_glossary_pairs',
  '"原文（英語/簡体字中国語）と日本語を対応付けられるlocalizationが見つかりませんでした。\\n\\n日本語だけでは原語→日本語の用語集を作れません。英語または簡体字中国語の対応原文が必要です。"',
  'u4.no_pairs',
  {},
  {},
  '原文（英語/簡体字中国語）と日本語を対応付けられるlocalizationが見つかりませんでした。\n\n日本語だけでは原語→日本語の用語集を作れません。英語または簡体字中国語の対応原文が必要です。'),
 ('App._save_imported_glossary_pairs', '"用語集取り込み"', 'u4.import_context', {}, {}, '用語集取り込み'),
 ('App.import_glossary_from_base_game',
  '"用語取り込みはすでにバックグラウンドで実行中です。"',
  'u4.import_busy',
  {},
  {},
  '用語取り込みはすでにバックグラウンドで実行中です。'),
 ('App.import_glossary_from_base_game',
  'f"{game} 本体からの用語取り込み"',
  'u4.base_import',
  {'game': 'game'},
  {'game': 'CK3'},
  'CK3 本体からの用語取り込み'),
 ('App.import_glossary_from_base_game.worker',
  'f"{game} 本体localizationを走査中…"',
  'u4.base_scan',
  {'game': 'game'},
  {'game': 'CK3'},
  'CK3 本体localizationを走査中…'),
 ('App.import_glossary_from_base_game.worker',
  'f"用語候補を作成中: {len(pairs)}ファイル組"',
  'u4.creating_candidates',
  {'count': 'len(pairs)'},
  {'count': 3},
  '用語候補を作成中: 3ファイル組'),
 ('App.import_glossary_from_base_game',
  'f"{game} 本体からの用語取り込みを開始しました…"',
  'u4.base_started',
  {'game': 'game'},
  {'game': 'CK3'},
  'CK3 本体からの用語取り込みを開始しました…'),
 ('App.import_glossary_from_japanese_source',
  '"用語取り込みはすでにバックグラウンドで実行中です。"',
  'u4.import_busy',
  {},
  {},
  '用語取り込みはすでにバックグラウンドで実行中です。'),
 ('App.import_glossary_from_japanese_source',
  '"日本語localization YAMLを選択"',
  'u4.choose_japanese_yaml',
  {},
  {},
  '日本語localization YAMLを選択'),
 ('App.import_glossary_from_japanese_source',
  '"日本語化Modまたは localization フォルダを選択"',
  'u4.choose_japanese_mod',
  {},
  {},
  '日本語化Modまたは localization フォルダを選択'),
 ('App.import_glossary_from_japanese_source',
  '"日本語YAMLからの用語取り込み"',
  'u4.japanese_yaml_import',
  {},
  {},
  '日本語YAMLからの用語取り込み'),
 ('App.import_glossary_from_japanese_source',
  '"日本語化Modからの用語取り込み"',
  'u4.japanese_mod_import',
  {},
  {},
  '日本語化Modからの用語取り込み'),
 ('App.on_glossary_import_drop_paths',
  '"用語取り込みはすでにバックグラウンドで実行中です。"',
  'u4.import_busy',
  {},
  {},
  '用語取り込みはすでにバックグラウンドで実行中です。'),
 ('App.on_glossary_import_drop_paths',
  'f"ドラッグ＆ドロップからの用語取り込み（{len(targets)}項目）"',
  'u4.drop_import',
  {'count': 'len(targets)'},
  {'count': 3},
  'ドラッグ＆ドロップからの用語取り込み（3項目）'),
 ('App.on_glossary_import_drop_paths',
  '"取り込み可能な日本語YAML / 日本語化Mod / localizationフォルダを確認できませんでした。"',
  'u4.drop_no_targets',
  {},
  {},
  '取り込み可能な日本語YAML / 日本語化Mod / localizationフォルダを確認できませんでした。'),
 ('App.on_glossary_import_drop_paths',
  'f"DnD: 対象 {len(targets)}件 / 対象外 {len(ignored)}件"',
  'u4.drop_result',
  {'targets': 'len(targets)', 'ignored': 'len(ignored)'},
  {'targets': 3, 'ignored': 1},
  'DnD: 対象 3件 / 対象外 1件'),
 ('App.show_selected_glossary_note', '"note: 用語を選択すると表示します"', 'u4.note_hint', {}, {}, 'note: 用語を選択すると表示します'),
 ('App._show_glossary_import_text', '"選択部分をコピー"', 'u4.copy_selection', {}, {}, '選択部分をコピー'),
 ('App.import_paratranz_glossary',
  '"ParaTranz の用語集（JSON）を取り込む"',
  'u4.paratranz_import',
  {},
  {},
  'ParaTranz の用語集（JSON）を取り込む'),
 ('App.import_paratranz_glossary',
  '"ParaTranz の用語集（term / translation を持つリスト）ではありません。"',
  'u4.invalid_paratranz',
  {},
  {},
  'ParaTranz の用語集（term / translation を持つリスト）ではありません。'),
 ('App.import_paratranz_glossary', '"ParaTranz 取り込みエラー"', 'u4.paratranz_error', {}, {}, 'ParaTranz 取り込みエラー'),
 ('App.confirm_paratranz_import', '"ParaTranz 用語集の取り込み確認"', 'u4.paratranz_confirm', {}, {}, 'ParaTranz 用語集の取り込み確認'),
 ('App.confirm_paratranz_import', '"元の項目"', 'u4.original_items', {}, {}, '元の項目'),
 ('App.confirm_paratranz_import', '"取り込む用語（variants込み）"', 'u4.imported_terms', {}, {}, '取り込む用語（variants込み）'),
 ('App.confirm_paratranz_import', '"variantsから追加"', 'u4.from_variants', {}, {}, 'variantsから追加'),
 ('App.confirm_paratranz_import', '"※で始まるルール"', 'u4.rules_count', {}, {}, '※で始まるルール'),
 ('App.confirm_paratranz_import', '"接辞"', 'u4.affixes', {}, {}, '接辞'),
 ('App.confirm_paratranz_import', '"記号のみ"', 'u4.symbols', {}, {}, '記号のみ'),
 ('App.confirm_paratranz_import', '"短い英字の語"', 'u4.short_terms', {}, {}, '短い英字の語'),
 ('App.confirm_paratranz_import', '"空白を直した数"', 'u4.spaces_fixed', {}, {}, '空白を直した数'),
 ('App.confirm_paratranz_import', '"重なり（先の語を使用）"', 'u4.duplicates', {}, {}, '重なり（先の語を使用）'),
 ('App.confirm_paratranz_import', '"noteにルールがある語"', 'u4.note_rules_count', {}, {}, 'noteにルールがある語'),
 ('App.confirm_paratranz_import',
  '"短い語は、ほかの単語の一部に誤って当たるおそれがあります"',
  'u4.short_warning',
  {},
  {},
  '短い語は、ほかの単語の一部に誤って当たるおそれがあります'),
 ('App.confirm_paratranz_import', '"表記ルールに回る項目（用語集には入れません）"', 'u4.rules_section', {}, {}, '表記ルールに回る項目（用語集には入れません）'),
 ('App.confirm_paratranz_import',
  '"note にルールがある語（用語は取り込み、noteはプロンプトに入れません）"',
  'u4.note_rules_section',
  {},
  {},
  'note にルールがある語（用語は取り込み、noteはプロンプトに入れません）'),
 ('App.confirm_paratranz_import', '"なし"', 'u4.none', {}, {}, 'なし'),
 ('App.confirm_paratranz_import', '"取り込み先の言語"', 'u4.destination_language', {}, {}, '取り込み先の言語'),
 ('App.confirm_paratranz_import', '"今の用語集に足す"', 'u4.merge', {}, {}, '今の用語集に足す'),
 ('App.confirm_paratranz_import', '"置き換える"', 'u4.replace', {}, {}, '置き換える'),
 ('App.confirm_paratranz_import.update_destination',
  'f"保存先: {path}"',
  'u4.destination',
  {'path': 'path'},
  {'path': '/tmp/用語集.json'},
  '保存先: /tmp/用語集.json'),
 ('App.confirm_paratranz_import',
  '"置き換える場合は既存の用語と表記ルールを置き換えます。表記ルールはA2へ手でコピーできます。"',
  'u4.replace_help',
  {},
  {},
  '置き換える場合は既存の用語と表記ルールを置き換えます。表記ルールはA2へ手でコピーできます。'),
 ('App.confirm_paratranz_import.import_selected',
  '"ParaTranz 取り込みエラー"',
  'u4.paratranz_error',
  {},
  {},
  'ParaTranz 取り込みエラー'),
 ('App.confirm_paratranz_import.import_selected',
  'f"ParaTranz: 追加 {result[\'counts\'][\'added\']} / 更新 {result[\'counts\'][\'updated\']} / 訳が違う語 '
  '{result[\'counts\'][\'conflicts\']}"',
  'u4.paratranz_result',
  {'added': "result['counts']['added']",
   'updated': "result['counts']['updated']",
   'conflicts': "result['counts']['conflicts']"},
  {'added': 2, 'updated': 4, 'conflicts': 1},
  'ParaTranz: 追加 2 / 更新 4 / 訳が違う語 1'),
 ('App.confirm_paratranz_import.import_selected',
  '"訳が違う語（今の訳を残しました）"',
  'u4.conflicts_title',
  {},
  {},
  '訳が違う語（今の訳を残しました）'),
 ('App.confirm_paratranz_import.import_selected',
  'f"{entry[\'term\']}\\n今の訳: {entry[\'existing\']}\\n取り込み側の訳: {entry[\'incoming\']}"',
  'u4.conflict_entry',
  {'term': "entry['term']", 'existing': "entry['existing']", 'incoming': "entry['incoming']"},
  {'term': 'Duke', 'existing': '旧訳', 'incoming': '公爵'},
  'Duke\n今の訳: 旧訳\n取り込み側の訳: 公爵'),
 ('App.confirm_paratranz_import.import_selected', '"閉じる"', 'u4.close', {}, {}, '閉じる'),
 ('App.confirm_paratranz_import', '"取り込む"', 'u4.import_selected', {}, {}, '取り込む'),
 ('App.confirm_paratranz_import', '"やめる"', 'u4.abort', {}, {}, 'やめる'),
 ('App.show_glossary_notation_rules', '"表記ルールのファイルの形式が不正です。"', 'u4.invalid_rules', {}, {}, '表記ルールのファイルの形式が不正です。'),
 ('App.show_glossary_notation_rules', '"表記ルール"', 'u4.rules', {}, {}, '表記ルール'),
 ('App.show_glossary_notation_rules', '"表記ルール（読み取り専用）"', 'u4.rules_read_only', {}, {}, '表記ルール（読み取り専用）'),
 ('App.show_glossary_notation_rules',
  'f"{path}\\n自動でプロンプトには入りません。必要な内容を選択し、コピーしてA2へ手で写してください。"',
  'u4.rules_help',
  {'path': 'path'},
  {'path': '/tmp/用語集.json'},
  '/tmp/用語集.json\n自動でプロンプトには入りません。必要な内容を選択し、コピーしてA2へ手で写してください。'),
 ('App.show_glossary_notation_rules', '"表記ルール"', 'u4.rules', {}, {}, '表記ルール'),
 ('App.show_glossary_notation_rules', '"note にルールがある語"', 'u4.note_rules', {}, {}, 'note にルールがある語'),
 ('App.show_glossary_notation_rules',
  'f"原語: {entry.get(\'term\',\'\')}\\n訳: {entry.get(\'translation\',\'\')}\\nnote: {entry.get(\'note\',\'\')}\\n理由: '
  '{entry.get(\'reason\',\'\')}"',
  'u4.rule_entry',
  {'term': "entry.get('term','')",
   'translation': "entry.get('translation','')",
   'note': "entry.get('note','')",
   'reason': "entry.get('reason','')"},
  {'term': 'Duke', 'translation': '公爵', 'note': '表記の注意', 'reason': '固定表記'},
  '原語: Duke\n訳: 公爵\nnote: 表記の注意\n理由: 固定表記'),
 ('App.show_glossary_notation_rules', '"なし"', 'u4.none', {}, {}, 'なし'),
 ('App.show_glossary_notation_rules', '"閉じる"', 'u4.close', {}, {}, '閉じる'),
 ('App.load_glossary_ui',
  'f"この言語のファイル: {p}"',
  'u4.language_file',
  {'path': 'p'},
  {'path': '/tmp/用語集.json'},
  'この言語のファイル: /tmp/用語集.json'),
 ('App.load_glossary_ui', '"用語集読込"', 'u4.load_context', {}, {}, '用語集読込'),
 ('App.load_glossary_ui', '"用語集読込エラー"', 'u4.load_error', {}, {}, '用語集読込エラー'),
 ('App.load_glossary_ui', '"note: 用語を選択すると表示します"', 'u4.note_hint', {}, {}, 'note: 用語を選択すると表示します'),
 ('App.load_glossary_ui',
  'f"用語集 {len(gl)}件を読み込みました"',
  'u4.loaded',
  {'count': 'len(gl)'},
  {'count': 3},
  '用語集 3件を読み込みました'),
 ('App.save_glossary_ui', '"用語集保存エラー"', 'u4.save_error', {}, {}, '用語集保存エラー'),
 ('App.save_glossary_ui',
  '"対応していない形式のファイルなので上書きしません。別の名前で保存してください。"',
  'u4.unsupported_save',
  {},
  {},
  '対応していない形式のファイルなので上書きしません。別の名前で保存してください。'),
 ('App.save_glossary_ui',
  'f"用語集保存: {p}"',
  'u4.saved',
  {'path': 'p'},
  {'path': '/tmp/用語集.json'},
  '用語集保存: /tmp/用語集.json'),
 ('App.add_glossary_term', '"用語追加"', 'u4.add_term', {}, {}, '用語追加'),
 ('App.add_glossary_term', '"原語（英語/中国語）"', 'u4.source_languages', {}, {}, '原語（英語/中国語）'),
 ('App.add_glossary_term', '"用語追加"', 'u4.add_term', {}, {}, '用語追加'),
 ('App.add_glossary_term',
  'f"「{src}」の固定{core.target_language_label(_glossary_language(self))}訳"',
  'u4.fixed_translation',
  {'source': 'src', 'target_name': 'i18n.t("lang." + _glossary_language(self))'},
  {'source': 'Duke', 'target_name': '日本語'},
  '「Duke」の固定日本語訳'),
 ('App.edit_glossary_term', '"用語編集"', 'u4.edit_term', {}, {}, '用語編集'),
 ('App.edit_glossary_term', '"原語"', 'u4.source', {}, {}, '原語'),
 ('App.edit_glossary_term', '"用語編集"', 'u4.edit_term', {}, {}, '用語編集'),
 ('App._glossary_kind_label',
  '"ゲーム本体: "+kind.split(":",1)[1]',
  'u4.base_origin',
  {'game': 'kind.split(":",1)[1]'},
  {'game': 'CK3'},
  'ゲーム本体: CK3'),
 ('App._auto_glossary_kind_summary',
  None,
  'u4.kind_summary',
  {'proper': "counts.get('proper',0)", 'term_count': "counts.get('term',0)", 'phrase': "counts.get('phrase',0)"},
  {'proper': 2, 'term_count': 3, 'phrase': 4},
  '固有名詞 2／単語 3／定型句 4'),
 ('App._auto_glossary_kind_summary',
  None,
  'u4.kind_summary_no_phrases',
  {'proper': "counts.get('proper',0)", 'term_count': "counts.get('term',0)", 'phrase': "counts.get('phrase',0)"},
  {'proper': 2, 'term_count': 3, 'phrase': 4},
  '固有名詞 2／単語 3／定型句 4（用語集には入れていません）'),
 ('App._save_imported_glossary_candidates',
  None,
  'u4.no_candidates_stats',
  {'japanese': "stats.get('japanese_keys',0)",
   'english': "stats.get('english',0)",
   'chinese': "stats.get('chinese',0)",
   'unmatched': "stats.get('unmatched',0)"},
  {'japanese': 7, 'english': 3, 'chinese': 2, 'unmatched': 2},
  '取り込み可能な用語候補が見つかりませんでした。\n\n日本語キー: 7件\n英語対応: 3件\n中国語対応: 2件\n対応なし: 2件'),
 ('App.show_selected_glossary_note',
  'f"{source} — note: {note or \'なし\'}"',
  'u4.selected_note',
  {'source': 'source', 'note': "note or i18n.t('u4.none')"},
  {'source': 'Duke', 'note': '表記の注意'},
  'Duke — note: 表記の注意')]

TEMPLATES = {'u4.language': ('言語', 'Language'),
 'u4.language_file': ('この言語のファイル: {path}', 'File for this language: {path}'),
 'u4.settings': ('用語集設定', 'Glossary settings'),
 'u4.file': ('用語集ファイル', 'Glossary file'),
 'u4.load': ('読込', 'Load'),
 'u4.save': ('保存', 'Save'),
 'u4.paratranz_import': ('ParaTranz の用語集（JSON）を取り込む', 'Import ParaTranz Glossary (JSON)'),
 'u4.view_rules': ('表記ルールを見る', 'View notation rules'),
 'u4.manual_terms': ('自分で作った用語', 'Manual terms'),
 'u4.generated_terms': ('自動生成 / 取り込み用語', 'Generated / imported terms'),
 'u4.add_term': ('用語追加', 'Add term'),
 'u4.edit_selected': ('選択編集', 'Edit selected'),
 'u4.delete_selected': ('選択削除', 'Delete selected'),
 'u4.manual_help': ('手動で固定した原語 → {target_name}訳です。手動用語は自動生成で上書きされません。',
                    'Fixed source → {target_name} translations. Automatic generation does not overwrite manual terms.'),
 'u4.source': ('原語', 'Source term'),
 'u4.target_heading': ('{target_name}', '{target_name}'),
 'u4.import_base': ('ゲーム本体から取り込む', 'Import from base game'),
 'u4.import_japanese_yaml': ('日本語YAMLファイルから取り込む', 'Import from Japanese YAML file'),
 'u4.import_japanese_mod': ('日本語化Mod / localizationフォルダから取り込む',
                            'Import from Japanese translation mod / localization folder'),
 'u4.import_japanese_files': ('日本語化ファイル / Modから取り込む', 'Import from Japanese translation files / mod'),
 'u4.base_help': ('※ ゲーム本体の日本語訳は［ゲーム本体から取り込む］を使うと、英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。',
                  '※ Use [Import from base game] to match Japanese base-game translations with English / Simplified '
                  'Chinese source text and create a Glossary.'),
 'u4.generated_help': ('通常翻訳・中国語基準翻訳・QA・差分調査で作成した用語と、ゲーム本体や既存日本語化から取り込んだ用語を表示します。自動生成は各作業タブから実行します。',
                       'Shows terms from normal translation, Chinese-based translation, QA, and diff research, plus '
                       'imports from the base game or existing Japanese translations. Run automatic generation from '
                       'each task tab.'),
 'u4.drop_help': ('ドラッグ＆ドロップ対応 — 日本語YAML / 日本語化Mod / localizationフォルダ',
                  'Drag and drop supported — Japanese YAML / Japanese translation mod / localization folder'),
 'u4.drop_unavailable': ('ドラッグ＆ドロップはこのビルドでは利用できません', 'Drag and drop is unavailable in this build'),
 'u4.include_phrases': ('定型句も用語集に入れる', 'Include phrases in the Glossary'),
 'u4.proper': ('固有名詞', 'Proper nouns'),
 'u4.term': ('単語', 'Terms'),
 'u4.phrase': ('定型句', 'Phrases'),
 'u4.origin': ('由来', 'Origin'),
 'u4.kind': ('種類', 'Type'),
 'u4.note_hint': ('note: 用語を選択すると表示します', 'note: Select a term to view its note'),
 'u4.dnd_failed': ('ドラッグ＆ドロップ初期化失敗: {error}', 'Drag-and-drop initialization failed: {error}'),
 'u4.dnd_context': ('用語集DnD初期化', 'Glossary drag-and-drop initialization'),
 'u4.review_selection': ('用語集へ保存する項目をQA / 比較編集の一覧から選択してください。',
                         'Select an item from QA / comparison editing to save to the Glossary.'),
 'u4.missing_source': ('選択した項目に原文がありません。', 'The selected item has no source text.'),
 'u4.enter_translation': ('{target_name}訳を入力してから用語集へ保存してください。',
                          'Enter the {target_name} translation before saving to the Glossary.'),
 'u4.overwrite_manual': ('この原文はすでに用語集に登録されています。\n\n原文: {source}\n現在: {old}\n新規: {target}\n\n手動用語として上書きしますか？',
                         'This source text is already in the Glossary.\n'
                         '\n'
                         'Source: {source}\n'
                         'Current: {old}\n'
                         'New: {target}\n'
                         '\n'
                         'Overwrite it as a manual term?'),
 'u4.manual_saved_status': ('手動用語を保存: {source} → {target}', 'Manual term saved: {source} → {target}'),
 'u4.manual_saved': ('手動用語として用語集へ保存しました。\n\n{source} → {target}',
                     'Saved to the Glossary as a manual term.\n\n{source} → {target}'),
 'u4.import_busy_generate': ('用語取り込み中です。完了してから自動用語作成を実行してください。',
                             'Term import is running. Wait for it to finish before generating terms.'),
 'u4.generation_busy': ('自動用語作成はすでに実行中です。', 'Automatic term generation is already running.'),
 'u4.review_load': ('QA / 比較編集で原文と{target_name}訳を読み込んでください。',
                    'Load source text and {target_name} translations in QA / comparison editing.'),
 'u4.diff_load': ('差分調査で原文と{target_name}訳を読み込んでください。',
                  'Load source text and {target_name} translations in diff research.'),
 'u4.queue_selection': ('対象キューから翻訳済み項目を選択してください。', 'Select translated items from the target queue.'),
 'u4.generating': ('自動用語作成中: {count}ファイル組', 'Generating terms: {count} file pairs'),
 'u4.generation': ('自動用語作成', 'Automatic term generation'),
 'u4.japanese_yaml': ('日本語YAML', 'Japanese YAML'),
 'u4.japanese_mod': ('日本語化Mod', 'Japanese translation mod'),
 'u4.generated': ('自動生成', 'Automatically generated'),
 'u4.choose_game_title': ('ゲーム本体から用語を取り込む', 'Import terms from base game'),
 'u4.choose_game': ('用語を取り込むゲームを選択してください。', 'Select the game to import terms from.'),
 'u4.cancel': ('キャンセル', 'Cancel'),
 'u4.select': ('選択', 'Select'),
 'u4.import_mode': ('用語取り込みモード', 'Term import mode'),
 'u4.choose_scope': ('取り込む用語の範囲を選択してください。', 'Select which terms to import.'),
 'u4.common_only': ('共通名のみ取り込み', 'Import common names only'),
 'u4.common_help': ('制度名・官職名・UI語など再利用しやすい短い用語を取り込み、人物名・地名・王朝名・「〇〇公爵」「〇〇軍管区長官」のような固有名詞付き候補を除外します。',
                    'Import short, reusable terms such as institutions, offices, and UI terms. Exclude personal, '
                    'place, and dynasty names, and candidates containing proper nouns such as “Duke of …” or '
                    '“Commander of … Military District”.'),
 'u4.import_all': ('すべて取り込み', 'Import all'),
 'u4.all_help': ('英語または簡体字中国語と対応付けできた項目を、長い文や固有名詞を含め原則すべて候補にします。',
                 'Include all items matched to English or Simplified Chinese, including long sentences and proper '
                 'nouns.'),
 'u4.import_help': ('※ ゲーム本体の日本語訳なら、［ゲーム本体から取り込む］で英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。\n'
                    '日本語化Mod単独の場合も、対応原文が近くになければゲーム本体との照合を案内します。',
                    '※ For Japanese base-game translations, use [Import from base game] to match English / Simplified '
                    'Chinese source text and create a Glossary.\n'
                    'For a standalone Japanese translation mod, you will be prompted to match against the base game if '
                    'no source text is nearby.'),
 'u4.import': ('取り込み', 'Import'),
 'u4.import_started': ('用語取り込みをバックグラウンドで開始しました…', 'Term import started in the background…'),
 'u4.generation_busy_import': ('自動用語作成中です。完了してから用語取り込みを実行してください。',
                               'Automatic term generation is running. Wait for it to finish before importing terms.'),
 'u4.import_busy': ('用語取り込みはすでにバックグラウンドで実行中です。', 'Term import is already running in the background.'),
 'u4.background_context': ('用語集バックグラウンド取り込み', 'Background Glossary import'),
 'u4.checking_japanese': ('用語取り込み中: 日本語localizationを確認しています…', 'Importing terms: Checking Japanese localization…'),
 'u4.import_progress': ('用語取り込み中: {index}/{total} — {name}', 'Importing terms: {index}/{total} — {name}'),
 'u4.creating_candidates': ('用語候補を作成中: {count}ファイル組', 'Creating term candidates: {count} file pairs'),
 'u4.no_candidates': ('取り込み可能な用語候補が見つかりませんでした。', 'No importable term candidates found.'),
 'u4.import_result': ('{label}: {added}件追加 / 候補 {total}件', '{label}: {added} added / {total} candidates'),
 'u4.import_complete': ('{label}が完了しました。', '{label} completed.'),
 'u4.candidates': ('候補: {count}件', 'Candidates: {count}'),
 'u4.added': ('新規追加: {count}件', 'New terms added: {count}'),
 'u4.japanese_keys': ('日本語キー: {count}件', 'Japanese keys: {count}'),
 'u4.english_matches': ('英語対応: {count}件', 'English matches: {count}'),
 'u4.chinese_matches': ('中国語対応: {count}件', 'Chinese matches: {count}'),
 'u4.unmatched': ('対応なし: {count}件', 'Unmatched: {count}'),
 'u4.skipped_unmatched': ('ゲーム本体に対応原文がないため {count}件をスキップしました。',
                          'Skipped {count} items with no matching source text in the base game.'),
 'u4.no_pairs': ('原文（英語/簡体字中国語）と日本語を対応付けられるlocalizationが見つかりませんでした。\n\n日本語だけでは原語→日本語の用語集を作れません。英語または簡体字中国語の対応原文が必要です。',
                 'No localization matching English / Simplified Chinese source text to Japanese was found.\n'
                 '\n'
                 'Japanese alone cannot create a source → Japanese Glossary. Matching English or Simplified Chinese '
                 'source text is required.'),
 'u4.import_context': ('用語集取り込み', 'Glossary import'),
 'u4.base_import': ('{game} 本体からの用語取り込み', 'Term import from {game} base game'),
 'u4.base_scan': ('{game} 本体localizationを走査中…', 'Scanning {game} base-game localization…'),
 'u4.base_started': ('{game} 本体からの用語取り込みを開始しました…', 'Term import from {game} base game started…'),
 'u4.choose_japanese_yaml': ('日本語localization YAMLを選択', 'Select Japanese localization YAML'),
 'u4.choose_japanese_mod': ('日本語化Modまたは localization フォルダを選択',
                            'Select a Japanese translation mod or localization folder'),
 'u4.japanese_yaml_import': ('日本語YAMLからの用語取り込み', 'Term import from Japanese YAML'),
 'u4.japanese_mod_import': ('日本語化Modからの用語取り込み', 'Term import from Japanese translation mod'),
 'u4.drop_import': ('ドラッグ＆ドロップからの用語取り込み（{count}項目）', 'Term import from drag and drop ({count} items)'),
 'u4.drop_no_targets': ('取り込み可能な日本語YAML / 日本語化Mod / localizationフォルダを確認できませんでした。',
                        'No importable Japanese YAML / Japanese translation mod / localization folder found.'),
 'u4.drop_result': ('DnD: 対象 {targets}件 / 対象外 {ignored}件', 'DnD: {targets} targets / {ignored} ignored'),
 'u4.copy_selection': ('選択部分をコピー', 'Copy selection'),
 'u4.invalid_paratranz': ('ParaTranz の用語集（term / translation を持つリスト）ではありません。',
                          'This is not a ParaTranz Glossary (a list containing term / translation).'),
 'u4.paratranz_error': ('ParaTranz 取り込みエラー', 'ParaTranz import error'),
 'u4.paratranz_confirm': ('ParaTranz 用語集の取り込み確認', 'Confirm ParaTranz Glossary import'),
 'u4.original_items': ('元の項目', 'Original items'),
 'u4.imported_terms': ('取り込む用語（variants込み）', 'Terms to import (including variants)'),
 'u4.from_variants': ('variantsから追加', 'Added from variants'),
 'u4.rules_count': ('※で始まるルール', 'Rules starting with ※'),
 'u4.affixes': ('接辞', 'Affixes'),
 'u4.symbols': ('記号のみ', 'Symbols only'),
 'u4.short_terms': ('短い英字の語', 'Short Latin-letter terms'),
 'u4.spaces_fixed': ('空白を直した数', 'Spaces corrected'),
 'u4.duplicates': ('重なり（先の語を使用）', 'Duplicates (first term kept)'),
 'u4.note_rules_count': ('noteにルールがある語', 'Terms with rules in note'),
 'u4.short_warning': ('短い語は、ほかの単語の一部に誤って当たるおそれがあります', 'Short terms may incorrectly match parts of other words'),
 'u4.rules_section': ('表記ルールに回る項目（用語集には入れません）', 'Items saved as notation rules (not added to the Glossary)'),
 'u4.note_rules_section': ('note にルールがある語（用語は取り込み、noteはプロンプトに入れません）',
                           'Terms with rules in note (terms are imported; notes are not added to prompts)'),
 'u4.none': ('なし', 'None'),
 'u4.destination_language': ('取り込み先の言語', 'Import language'),
 'u4.merge': ('今の用語集に足す', 'Add to current Glossary'),
 'u4.replace': ('置き換える', 'Replace'),
 'u4.destination': ('保存先: {path}', 'Save to: {path}'),
 'u4.replace_help': ('置き換える場合は既存の用語と表記ルールを置き換えます。表記ルールはA2へ手でコピーできます。',
                     'Replacing overwrites existing terms and notation rules. You can manually copy notation rules to '
                     'A2.'),
 'u4.paratranz_result': ('ParaTranz: 追加 {added} / 更新 {updated} / 訳が違う語 {conflicts}',
                         'ParaTranz: {added} added / {updated} updated / {conflicts} conflicting translations'),
 'u4.conflicts_title': ('訳が違う語（今の訳を残しました）', 'Conflicting translations (current translations kept)'),
 'u4.conflict_entry': ('{term}\n今の訳: {existing}\n取り込み側の訳: {incoming}',
                       '{term}\nCurrent translation: {existing}\nImported translation: {incoming}'),
 'u4.close': ('閉じる', 'Close'),
 'u4.import_selected': ('取り込む', 'Import'),
 'u4.abort': ('やめる', 'Cancel'),
 'u4.invalid_rules': ('表記ルールのファイルの形式が不正です。', 'The notation rules file has an invalid format.'),
 'u4.rules': ('表記ルール', 'Notation rules'),
 'u4.rules_read_only': ('表記ルール（読み取り専用）', 'Notation rules (read-only)'),
 'u4.rules_help': ('{path}\n自動でプロンプトには入りません。必要な内容を選択し、コピーしてA2へ手で写してください。',
                   '{path}\n'
                   'Not automatically added to prompts. Select and copy what you need, then paste it into A2 '
                   'manually.'),
 'u4.note_rules': ('note にルールがある語', 'Terms with rules in note'),
 'u4.rule_entry': ('原語: {term}\n訳: {translation}\nnote: {note}\n理由: {reason}',
                   'Source term: {term}\nTranslation: {translation}\nnote: {note}\nReason: {reason}'),
 'u4.load_context': ('用語集読込', 'Glossary load'),
 'u4.load_error': ('用語集読込エラー', 'Glossary load error'),
 'u4.loaded': ('用語集 {count}件を読み込みました', 'Loaded {count} Glossary terms'),
 'u4.save_error': ('用語集保存エラー', 'Glossary save error'),
 'u4.unsupported_save': ('対応していない形式のファイルなので上書きしません。別の名前で保存してください。',
                         'This file format is unsupported and will not be overwritten. Save under a different name.'),
 'u4.saved': ('用語集保存: {path}', 'Glossary saved: {path}'),
 'u4.source_languages': ('原語（英語/中国語）', 'Source term (English/Chinese)'),
 'u4.fixed_translation': ('「{source}」の固定{target_name}訳', 'Fixed {target_name} translation of “{source}”'),
 'u4.edit_term': ('用語編集', 'Edit term'),
 'u4.base_origin': ('ゲーム本体: {game}', 'Base game: {game}'),
 'u4.kind_summary': ('固有名詞 {proper}／単語 {term_count}／定型句 {phrase}',
                     'Proper nouns {proper} / Terms {term_count} / Phrases {phrase}'),
 'u4.kind_summary_no_phrases': ('固有名詞 {proper}／単語 {term_count}／定型句 {phrase}（用語集には入れていません）',
                                'Proper nouns {proper} / Terms {term_count} / Phrases {phrase} (not included in the '
                                'Glossary)'),
 'u4.no_candidates_stats': ('取り込み可能な用語候補が見つかりませんでした。\n'
                            '\n'
                            '日本語キー: {japanese}件\n'
                            '英語対応: {english}件\n'
                            '中国語対応: {chinese}件\n'
                            '対応なし: {unmatched}件',
                            'No importable term candidates found.\n'
                            '\n'
                            'Japanese keys: {japanese}\n'
                            'English matches: {english}\n'
                            'Chinese matches: {chinese}\n'
                            'Unmatched: {unmatched}'),
 'u4.selected_note': ('{source} — note: {note}', '{source} — note: {note}')}


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.get_ui_language()
    i18n.set_ui_language("japanese")
    try:
        yield
    finally:
        i18n.set_ui_language(previous)


@pytest.mark.parametrize("owner,original,key,bindings,fields,expected", CASES,
                         ids=[f"{owner}-{index}-{key}" for index, (owner, _, key, _, _, _) in enumerate(CASES)])
def test_japanese_display_matches_original(owner, original, key, bindings, fields, expected):
    assert i18n.t(key, **fields) == expected, (owner, original)


@pytest.mark.parametrize("key", TEMPLATES)
def test_english_keys_are_complete_and_render(key):
    i18n.set_ui_language("english")
    assert key in ENGLISH
    japanese, english = TEMPLATES[key]
    assert JAPANESE[key] == japanese
    assert ENGLISH[key] == english
    fields = next(fields for _, _, case_key, _, fields, _ in CASES if case_key == key)
    assert i18n.t(key, **fields) == english.format(**fields)


def test_snapshots_cover_every_u4_dictionary_key():
    assert set(TEMPLATES) == set(JAPANESE) == set(ENGLISH)


def load_method(name):
    tree = ast.parse((ROOT / "app/main.py").read_text(encoding="utf-8"))
    application = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "App")
    method = next(node for node in application.body if isinstance(node, ast.FunctionDef) and node.name == name)
    method.decorator_list = []
    namespace = {"i18n": i18n}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[])), "<U4 method>", "exec"), namespace)
    return namespace[name]


@pytest.mark.parametrize("include_phrases", [True, False])
def test_summary_preserves_optional_phrase_note(include_phrases):
    summary = load_method("_auto_glossary_kind_summary")
    result = {"term_kind_counts": {"proper": 2, "term": 3, "phrase": 4}, "include_phrases": include_phrases}
    suffix = "" if include_phrases else "（用語集には入れていません）"
    assert summary(result) == f"固有名詞 2／単語 3／定型句 4{suffix}"
    i18n.set_ui_language("english")
    assert summary(result) == "Proper nouns 2 / Terms 3 / Phrases 4" + ("" if include_phrases else " (not included in the Glossary)")


@pytest.mark.parametrize("kind,expected", [("base:CK3", "ゲーム本体: CK3"), ("import:file", "日本語YAML"),
                                          ("import:mod", "日本語化Mod"), ("auto", "自動生成"),
                                          ("import:paratranz", "ParaTranz")])
def test_origin_label_preserves_japanese(kind, expected):
    assert load_method("_glossary_kind_label")(None, {"source_kind": kind}) == expected


def test_production_calls_preserve_interpolation_expressions():
    source = (ROOT / "app/main.py").read_text(encoding="utf-8")
    calls = {}

    def visit(node, owner=""):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = f"{owner}.{node.name}" if owner else node.name
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and \
                isinstance(node.func.value, ast.Name) and node.func.value.id == "i18n" and node.func.attr == "t":
            if node.args and isinstance(node.args[0], ast.Constant):
                key = node.args[0].value
                if isinstance(key, str) and key.startswith("u4."):
                    calls.setdefault((owner, key), []).append(node)
        for child in ast.iter_child_nodes(node):
            visit(child, owner)

    visit(ast.parse(source))
    for owner, original, key, bindings, fields, expected in CASES:
        if key in {"u4.kind_summary", "u4.kind_summary_no_phrases"}:
            continue
        expected_bindings = {name: ast.dump(ast.parse(expression, mode="eval").body)
                             for name, expression in bindings.items()}
        assert any({keyword.arg: ast.dump(keyword.value) for keyword in call.keywords} == expected_bindings
                   for call in calls.get((owner, key), [])), (owner, key, original)


@pytest.mark.parametrize("code", i18n.UI_LANGUAGES)
def test_target_language_names_follow_ui_language(code):
    for ui_language in ("japanese", "english"):
        i18n.set_ui_language(ui_language)
        target_name = i18n.t("lang." + code)
        assert target_name != "lang." + code
        assert i18n.t("u4.target_heading", target_name=target_name) == target_name
        assert target_name in i18n.t("u4.manual_help", target_name=target_name)


def test_import_default_is_resolved_at_call_time():
    tree = ast.parse((ROOT / "app/main.py").read_text(encoding="utf-8"))
    method = next(node for node in ast.walk(tree)
                  if isinstance(node, ast.FunctionDef) and node.name == "_start_glossary_import_thread")
    assert isinstance(method.args.defaults[0], ast.Constant)
    assert method.args.defaults[0].value is None
    busy_call = next(node for node in ast.walk(method)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                     and node.func.attr == "_set_glossary_import_busy")
    expression = ast.Expression(busy_call.args[1])
    for ui_language in ("japanese", "english"):
        i18n.set_ui_language(ui_language)
        for status in (None, "", "custom status"):
            assert eval(compile(expression, "<U4 default>", "eval"), {"i18n": i18n, "status": status}) == \
                (i18n.t("u4.import_started") if status is None else status)


@pytest.mark.parametrize("stats", [None, {}, {"japanese_keys": 7, "english": 3, "chinese": 2, "unmatched": 2}])
def test_empty_import_preserves_complete_message(stats):
    method = load_method("_save_imported_glossary_candidates")
    messages = []
    method.__globals__["_japanese_glossary_only"] = lambda app: True
    method.__globals__["APP_NAME"] = "Test"
    method.__globals__["messagebox"] = SimpleNamespace(showinfo=lambda title, text: messages.append(text))
    method(None, [], "Test", stats)
    expected = "取り込み可能な用語候補が見つかりませんでした。"
    if stats:
        expected += (f"\n\n日本語キー: {stats.get('japanese_keys', 0)}件"
                     f"\n英語対応: {stats.get('english', 0)}件"
                     f"\n中国語対応: {stats.get('chinese', 0)}件"
                     f"\n対応なし: {stats.get('unmatched', 0)}件")
    assert messages == [expected]
    i18n.set_ui_language("english")
    method(None, [], "Test", stats)
    assert messages[-1].startswith("No importable term candidates found.")
    assert "日本語" not in messages[-1]


@pytest.mark.parametrize("note", ["", "表記の注意"])
def test_selected_note_preserves_empty_note_fallback(note):
    method = load_method("show_selected_glossary_note")
    messages = []
    application = SimpleNamespace(glossary_note_var=SimpleNamespace(set=messages.append),
                                  _glossary_variant_metadata=lambda: {"Duke": {"note": note}})
    tree = SimpleNamespace(selection=lambda: ["row"], item=lambda row, option: ["Duke", "公爵"])
    method(application, tree)
    assert messages[-1] == f"Duke — note: {note or 'なし'}"
    i18n.set_ui_language("english")
    method(application, tree)
    assert messages[-1] == f"Duke — note: {note or 'None'}"
