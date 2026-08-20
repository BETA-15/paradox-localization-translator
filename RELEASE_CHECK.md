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
