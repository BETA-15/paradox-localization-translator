# v0.11.16

## 自動生成・一時データの保存先をさらに統一

- 実行ファイル / `.app` の隣に残っている旧 `ParadoxLocalizationTranslator_Data` を起動時に検出し、認識可能なデータを現在の `Paradox Localization Translator` データルートへ非破壊で移行するようにした。
- 旧 `~/.paradox_localization_translator` のモデル統計・キャッシュ・ログ等も可能な範囲で引き継ぐ。
- 対象は翻訳結果、キャッシュ、バックアップ、ログ、設定、再開状態など。旧側は自動削除しない。
- 移行記録を `設定/storage_migration.json` と `ログ/storage_migration.log` に保存する。
- バージョン非依存の一時・作業状態用に `作業データ/` を用意した。
- 再開状態へ `data_root` を保存し、以前のデータルート下にあるキャッシュ・出力・用語集等のパスを現在の保存先へ読み替えられるようにした。
- 設定タブからデータルートを変更した際、現在のキューが旧ルートのキャッシュ等を参照し続けないようにパスも追従させる。
- OSがデータルートそのものの場所を覚えるための locator（Registry / macOS defaults / Linux ~/.config）は例外として従来どおりOS側へ保存する。
- APIキーは永続保存しない。
