# Paradox Localization Translator v0.2.0 — Standalone Build

Paradox Interactive系ゲームのローカライズYAMLを、OllamaのローカルLLMで日本語化・修復するGUIアプリです。

## 配布版で利用者が用意するもの

- Ollama
- Ollamaに入れた翻訳用LLMモデル（既定 `qwen3.6:latest`）

**Python / pip / Tkinter / PyInstaller は利用者側では不要です。**
配布用 `.app` / `.exe` / Linux実行ファイルにはPythonランタイム、標準ライブラリ、Tk/Tcl、翻訳コアが内蔵されます。

## 生成される配布物

- macOS: `Paradox Localization Translator.app`（ZIP配布）
- Windows: `ParadoxLocalizationTranslator.exe`
- Linux: `ParadoxLocalizationTranslator`

## ローカルでビルド

### macOS

```bash
bash build/build_macos_standalone.sh
```

生成先: `dist/Paradox Localization Translator.app`

### Windows

```bat
build\build_windows_standalone.bat
```

生成先: `dist\ParadoxLocalizationTranslator.exe`

### Linux

```bash
bash build/build_linux_standalone.sh
```

## GitHub Actionsで3OSを自動ビルド

`.github/workflows/build-standalone.yml` を同梱しています。
GitHubのActions画面から `Build standalone apps` → `Run workflow` で実行すると、macOS / Windows / Linux の3種類がArtifactsとして生成されます。

`v0.2.0` のようなタグをpushした場合は、3種類をGitHub Releaseへ自動添付する設定です。

## macOSの注意

同梱ビルドはDeveloper ID証明書を使わないadhoc署名です。インターネット配布時はGatekeeperの警告が出る場合があります。本格公開する場合はApple Developer IDによるcodesignとnotarizationを追加してください。

## Ollama

アプリは既定で `http://localhost:11434` に接続します。起動後にインストール済みモデル一覧を自動取得します。

## 翻訳機能

- English / Simplified Chinese等のParadox localization YAMLを日本語化
- `[ROOT.Char...]`, `$VALUE$`, `£icon£`, `§Y`, `#!`, `\\n` 等を保護
- バッチ翻訳
- キャッシュ / 差分翻訳
- 通信失敗時の再試行
- 日本語ファイル中に残った英語を検出して修復
- 「原文をそのまま返したLLM応答」の未翻訳判定と再翻訳
