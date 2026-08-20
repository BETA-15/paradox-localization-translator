# Paradox Localization Translator v0.5.2

Paradox Interactive系ゲームのローカライズYAMLを、ローカルLLMまたはクラウドLLM APIで日本語化・修復・QAするGUIアプリです。

## 対応LLMプロバイダ

### ローカル
- **Ollama** — `http://localhost:11434`
- **LM Studio** — `http://localhost:1234/v1`

### クラウド
- **OpenAI** — `https://api.openai.com/v1`
- **Anthropic** — `https://api.anthropic.com/v1`
- **Google Gemini** — `https://generativelanguage.googleapis.com/v1beta`
- **OpenAI Compatible** — OpenAI互換 `/models` + `/chat/completions` APIを持つ任意サービス

GUIの「プロバイダ」から切り替えられます。

## APIキー

クラウドAPIではGUIの「APIキー」欄へ入力してください。入力欄はマスク表示されます。

**APIキーはアプリのセッション、モデルプロファイル、速度統計には保存しません。**
アプリを終了するとGUIに入力したキーは失われます。

環境変数も利用できます。

- OpenAI: `OPENAI_API_KEY`
- Anthropic: `ANTHROPIC_API_KEY`
- Gemini: `GEMINI_API_KEY` または `GOOGLE_API_KEY`
- OpenAI Compatible: `PLT_API_KEY`（未設定時は `OPENAI_API_KEY` も参照）

## v0.5.1 の追加機能

- **OpenAI API対応** — Responses APIを使用
- **Anthropic API対応** — Messages APIを使用
- **Gemini API対応** — `generateContent` APIを使用
- **OpenAI互換クラウドAPI対応** — URL + APIキーを任意指定
- **クラウドモデル一覧取得** — 各APIのモデル一覧からGUIへ読み込み
- **クラウドモデルも速度比較可能** — 平均秒、tokens/s（APIがトークン数を返す場合）、失敗率を記録
- **APIキー非保存** — 秘密情報をセッション/プロファイルJSONへ書き込まない
- **環境変数APIキー対応**

## 継続機能

- 残り時間予測
- モデル速度比較 / モデルプロファイル
- Ollama未起動検出
- LM Studio対応
- 一時停止 / 再開
- セーブして中断 / 次回再開
- 複数Mod・複数YAMLの翻訳キュー
- 未翻訳チェック / Paradox構文QA
- 誤字脱字チェック + AI校正
- 原文 / 訳文比較エディタ
- 用語集
- 英語 + 簡体字中国語の併用翻訳
- 既存日本語YAMLの未翻訳箇所修復
- キャッシュによる差分翻訳

## クラウドAPIの使い方

1. 「プロバイダ」で OpenAI / Anthropic / Gemini / OpenAI Compatible のいずれかを選択します。
2. 通常は自動入力されたURLをそのまま使用します。
3. 「APIキー」へキーを入力します（環境変数を設定済みなら空欄でも可）。
4. 「接続確認 / モデル再読込」を押します。
5. モデルを選択します。
6. 翻訳キューを追加して「翻訳開始」を押します。

OpenAI CompatibleではAPIサービスのベースURLを手動指定してください。通常は `/v1` を含むURLを指定します。

## モデル統計

実際の翻訳と速度テストの結果を `.paradox_localization_translator/model_stats.json` に保存します。
APIキーは保存されません。

- Ollama: `eval_count / eval_duration`
- OpenAI互換 / LM Studio: `usage.completion_tokens`
- OpenAI: `usage.output_tokens`
- Anthropic: `usage.output_tokens`
- Gemini: `usageMetadata.candidatesTokenCount`

トークン数が返らない場合でも、平均処理時間と失敗率は記録します。

## スタンドアロンビルド

GitHub Actions の **Build standalone apps** を実行すると、macOS / Windows / Linux のスタンドアロン成果物を生成します。
Pythonを利用者側へインストールする必要はありません。

## v0.5.1 出力先と内蔵説明書

- 翻訳結果・セッション・用語集・モデル統計などの自動生成ファイルは、原則としてアプリ/実行ファイルの隣に `ParadoxLocalizationTranslator_Data` を作って保存します。
- アプリの隣へ書き込めない場合（例: macOSの `/Applications`）は、`Documents/Paradox Localization Translator` を自動利用します。
- 翻訳結果はその中の `翻訳結果`、設定類は `設定` に分けて保存します。
- 「選択項目の出力先変更」は、キュー内の対象行を選んでから使う個別変更ボタンです。未選択時には案内を表示します。
- GUI内に「使い方」タブを追加し、基本操作・出力先・中断再開・QA・各LLM接続方法をアプリ単体で確認できます。

## v0.5.2
- アプリ上部に常設のLLM状態バーを追加。翻訳・AI校正・速度テスト中は「LLM 動作中」、モデル、プロバイダ、経過時間を表示します。
- 現在のLLM処理を停止する共通ボタンを追加しました。
- モデル速度テストに「速度テスト停止」を追加し、全モデルテスト中でも安全に中断できます。
- AI誤字脱字校正もLLM動作表示・停止対象になりました。
- 停止は通信中リクエストの応答後、安全な処理境界で行います。
