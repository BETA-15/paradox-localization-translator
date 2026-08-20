# v0.8.5 Release Check

リリース前総合チェック結果: PASS

確認済み:
- Python構文チェック (`app/main.py`, `app/translator_core.py`)
- GUI起動スモークテスト（全10タブ生成、初期ウィンドウ生成）
- Paradox YAML解析・引用符エスケープ・値更新・欠落キー追記
- QA: 未翻訳 / 欠落キー検出
- 差分比較: missing / untranslated 判定
- プレースホルダ保護・復元
- 用語集 / 英中併用を含むキャッシュキー分離
- Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI互換 API形式をローカルモックで確認
- Ollamaモックによる翻訳 → 日本語YAML出力 → キャッシュ再利用
- macOS / Linux ビルドスクリプトのShell構文チェック
- GitHub Actions定義と必要ファイル存在確認
- README / 内蔵使い方の旧設定説明を修正

実機での最終確認が必要:
- GitHub Actionsで macOS / Windows / Linux の3ジョブが成功すること
- 生成されたmacOS .app / Windows .exeを各OSで1回起動すること
- スタンドアロン版でTkDnDドラッグ＆ドロップを実機確認すること

