# Release Check — v0.8.9

## 主な変更

- 通常翻訳タブを左右2ブロックへ再設計
  - 左: LLM / 翻訳設定（縦スクロール対応）
  - 右: 翻訳キュー / 進捗 / ログ
- 翻訳LLM / 探索LLM状態表示を上部左右配置へ変更
- 中国語基準翻訳タブを左右2ブロックへ再設計
- 中国語基準翻訳に複数項目キューを追加
- 翻訳状況一覧へ「中国語」列を追加
- 簡体字中国語 localization が存在するModのみ「中国語基準キューへ追加」可能
- 旧翻訳状況キャッシュでも実ファイルを再確認して中国語有無を判定

## 確認済み

- `python -m py_compile app/main.py app/translator_core.py`: PASS
- 1920x1080仮想画面でGUI起動: PASS
- 全11タブ生成: PASS
- 中国語基準キューUI生成: PASS
- 翻訳状況→中国語基準キュー追加: PASS
- `l_simp_chinese` 検出件数/キー数: PASS
- 中国語なしModでは追加ボタンを無効化する処理: 実装済み

## 実機で確認推奨

- macOS / WindowsのフルHD表示で左右ペイン・スクロールバー操作
- GitHub Actions 3OSビルド
- スタンドアロン版でドラッグ＆ドロップ

- バッチサイズ・並列数の app_preferences.json 保存/次回起動復元を確認。


## v0.9.0 追加確認

- 中国語基準翻訳キューに出力先変更・キャッシュ閲覧/追加を追加
- 中国語基準翻訳の完成結果を、既存日本語化Modへ差分上書きまたは元Modへ直接上書き可能
- 翻訳状況から中国語基準キューへ追加した場合、元Mod・日本語化Mod情報を引き継ぐ
- 翻訳状況一覧で選択したModだけを強制再調査可能
- Mod場所一覧の操作を「監視対象に設定」と「選択場所の全Modを一括調査」に明確化
- Mod場所一覧に「すべて選択」「選択解除」を追加し、Ctrl+クリック複数選択も維持
- Python構文チェック: PASS


## v0.9.1 regression checks
- Python syntax: PASS
- GUI startup / 11 tabs: PASS
- Normal queue mock completion -> status 完了, done event, session deleted: PASS
- Session behavior: completed queue is not persisted on exit; unfinished queue is persisted for one restore prompt
- Declining restore deletes the stale session
- Chinese basis overwrite UI consolidated to one button


## v0.9.5 QA回帰確認

- Python構文チェック: PASS
- GUI起動 / 11タブ生成: PASS
- 英語原文QA: PASS
- 簡体字中国語原文QA: PASS
- 中国語の未翻訳原文検出: PASS
- Paradoxトークン不一致検出: PASS
- 中国語用語集固定訳チェック: PASS
- 簡体字中国語→日本語の差分判定: PASS
- 中国語基準翻訳後の自動QAレポート生成: PASS
- 中国語基準翻訳の手動QAヘルパー: PASS


## v0.9.7 additional checks
- Python syntax: PASS
- GUI startup under virtual display: PASS (11 tabs)
- English output pair detection for QA/diff: PASS
- Simplified Chinese output pair detection for QA/diff: PASS
- Translation status buttons reorganized into two rows.

- v0.10.2: 自動用語候補生成・複数訳集計・QA一括用語統一の回帰テスト: PASS


## v0.11.0 additional checks
- Python syntax: PASS
- GUI startup / 11 tabs: PASS
- Manual vs generated glossary split: PASS
- Auto glossary buttons on normal/chinese/QA/diff: PASS
- Single-occurrence glossary import candidate extraction: PASS
- Japanese YAML pairing for import: PASS
- Manual terms remain manual when auto/import candidates overlap: PASS


## v0.11.21 追加確認
- [ ] 不足分キュー追加直後にセッション保存エラーが出ない
- [ ] 通常翻訳の `差分翻訳` で前回翻訳済みキーを再翻訳しない
- [ ] 中国語基準翻訳の `差分翻訳` で前回翻訳済みキーを再翻訳しない
- [ ] 差分スナップショットがない場合は案内して開始しない
- [ ] 残存欠落がある完了項目は `完了（一部差分欠落あり）` と表示される
- [ ] 通常 / 中国語基準のキュー操作ボタンが2段で表示される


## v0.11.22 追加確認
- 通常翻訳キューで横スクロールが全列へ作用すること。
- 中国語基準翻訳キューで横スクロールが全列へ作用すること。
- 列幅拡張後も縦スクロールが利用できること。
