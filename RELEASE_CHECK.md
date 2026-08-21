# v0.11.34 追加確認

- [x] `VERSION` / `APP_VERSION` を 0.11.34 に統一
- [x] 翻訳専用構成（localization + descriptor/thumbnail/README中心）を最大35点で強く加点
- [x] 20%キー一致ゲートを維持
- [x] 同じ日本語化Mod候補を複数元Modへ自動関連付けせず、最高スコア1件へ割り当てる競合判定を追加
- [x] localization-only + 100%一致候補が90点で自動関連付けされる合成テスト PASS
- [x] 同じ候補がSourceA/SourceB双方に一致してもSourceAだけに割り当てられる合成テスト PASS
- [x] gameplay 100ファイルを持つ候補は45点で候補止まりになる合成テスト PASS
- [x] 翻訳状況キャッシュ世代を更新し旧判定を自動再調査
- [x] `python -m py_compile app/main.py app/translator_core.py` PASS

---

# v0.11.33 追加確認

- [x] `VERSION` / `APP_VERSION` を 0.11.33 に統一
- [x] 翻訳状況キャッシュ世代を更新し、旧日本語化Mod関連付けを自動リセット
- [x] 20%未満の候補は比重判定対象外
- [x] 日本語キー一致率 最大50点 / localization主体度 最大25点 / dependencies 20点 / ゲーム内容の少なさ 最大15点 / 英語・中国語localization 最大-10点を実装
- [x] 60点以上=自動関連付け、40〜59点=候補表示のみ、39点以下=別Mod扱い
- [x] localizationのみ・100%キー一致の日本語化Modが高得点で自動関連付けされるテスト PASS
- [x] 20%一致 + dependencies一致の部分日本語化Modが60点以上になるテスト PASS
- [x] 100%キー一致でも大量の gameplay script を持つModは自動関連付けされず候補止まりになるテスト PASS
- [x] 翻訳状況に候補表示・スコア・判定理由を追加
- [x] 総合診断に比重スコアと判定理由を追加し、候補/高信頼関係のキーを誤修復から保護
- [x] Mod構成評価でネストした独立Modを境界外として扱う
- [x] 総合診断で高信頼/要確認の日本語化Mod関係キーを別Mod混入として誤削除しない合成テスト PASS
- [x] Xvfb上でGUI起動、12タブ生成、総合診断の関連度列生成 PASS
- [x] `python -m py_compile app/main.py app/translator_core.py` PASS

---

# v0.11.32 追加確認

- [x] `VERSION` / `APP_VERSION` を 0.11.32 に統一
- [x] 独立した「総合診断」タブを追加（全12タブ生成確認）
- [x] 翻訳状況から診断対象Modを単体 / 複数選択可能
- [x] 診断・既知Mod原文索引作成をバックグラウンド化
- [x] 別Mod由来キー / 原文にない日本語キー / 日本語キー重複 / 別Mod由来ファイル疑い / 日本語ファイル異常増加を検出
- [x] 自動修復は「別Mod1件だけに原文キーが存在する」一意判定のキーに限定
- [x] 出所不明・複数Mod共通キーは自動削除しない
- [x] 修復前に選択した全Modの localization フォルダを丸ごとバックアップし、全件成功後に修復開始
- [x] 修復では日本語側のみ変更し、英語 / 簡体字中国語のSHA256が不変であることを合成テストで確認
- [x] 別Mod由来キー除去後も出所不明日本語キーを保持することを合成テストで確認
- [x] 修復後の自動再診断を実装
- [x] 修復時に既存日本語YAMLの UTF-8 / UTF-8 BOM / UTF-16 LE / UTF-16 BE を保持する書き戻しテスト PASS
- [x] 総合診断タブ追加による旧workspaceの設定 / 使い方タブ位置ずれを移行処理で吸収
- [x] `python -m py_compile app/main.py app/translator_core.py` PASS
- [x] Xvfb上でGUI起動、12タブ生成、総合診断タブ生成 PASS

---

# v0.11.31 追加確認

- [x] `VERSION` / `APP_VERSION` を 0.11.31 に統一
- [x] 日本語化Mod候補判定を候補側日本語キー一致率20%以上へ変更
- [x] 最低一致キー数なし（1キー規模でも割合条件のみで判定）
- [x] 19%候補は除外、20%候補は採用するテストを実施
- [x] 1/1キー一致の小規模日本語化Modが採用されるテストを実施
- [x] 旧翻訳状況キャッシュ世代を更新し自動リセット
- [x] 旧workspace/session/resumeの外部日本語化Mod関連情報を復元時に破棄
- [x] 初回Mod役割キャッシュは保持・schema 2へ移行
- [x] `python -m py_compile app/main.py app/translator_core.py` PASS

---

# Release Check — v0.11.30

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


## v0.11.23 追加確認
- [ ] スナップショットなし + 日本語欠損ありで差分翻訳を開始できる
- [ ] スナップショット差分 + 日本語欠損を同時に差分対象へ含める
- [ ] 日本語の補助YAMLに既存キーがある場合は欠損扱いしない
- [ ] 動的参照だけのキーは欠損対象にしない
- [ ] 原文差分・欠損ともになければ `完了（差分なし）` になる
- [ ] 通常翻訳 / 中国語基準翻訳の両方で同じ動作をする

## v0.11.24 追加確認

- [ ] 翻訳状況で欠損と表示されるキーが差分翻訳対象になる
- [ ] 通常翻訳では英語原文を持つ欠損だけを差分対象にする
- [ ] 中国語基準翻訳では簡体字中国語原文を持つ欠損だけを差分対象にする
- [ ] スナップショットなしでも翻訳状況に補完可能な欠損があれば差分翻訳できる
- [ ] 欠損なし・原文差分なしでは `完了（差分なし）` になる


## v0.11.25 追加確認

- `python -m py_compile app/main.py app/translator_core.py`: PASS
- ワークスペース状態のJSON直列化: PASS
- 通常翻訳 / 中国語基準翻訳キューが同一ワークスペースへ独立保存されること: PASS
- 最新ワークスペースより古いsessionを除外し、より新しいresume_stateを採用するテスト: PASS
- 上書き時に対象Modの翻訳状況キャッシュを無効化する処理を追加


## v0.11.26 追加確認

- [x] 中国語基準で英語固有欠損だけが残る場合、差分判定不能にせず中国語側完了と判定
- [x] 通常翻訳で中国語固有欠損だけが残る場合、通常側完了と判定
- [x] スナップショットなし + 反対側言語固有欠損のみでも言語別完了を判定
- [x] 実データで中国語基準 0件 / 全欠損39件（英語固有39件）を確認
- [x] `python -m py_compile app/main.py app/translator_core.py`: PASS


## v0.11.27 追加確認

- [ ] 通常翻訳で未選択のまま「翻訳開始」を押すと選択を促す。
- [ ] 中国語基準翻訳で未選択のまま「翻訳開始」を押すと選択を促す。
- [ ] 複数選択して「差分だけ翻訳」を選ぶと、選択項目だけが処理される。
- [ ] 完了済み/上書き済み項目でも選択して差分確認できる。
- [ ] 「一からすべて翻訳」で選択項目のキャッシュが新規化される。
- [ ] 未選択項目の状態やキャッシュが変更されない。
- [ ] 通常翻訳・中国語基準翻訳とも独立した「差分翻訳」ボタンが存在しない。

## v0.11.28 追加確認

- [ ] 通常翻訳が正常完了した後に「翻訳開始」が再有効化される
- [ ] 差分だけ翻訳の完了後にも「翻訳開始」が再有効化される
- [ ] 一からすべて翻訳の完了後にも「翻訳開始」が再有効化される
- [ ] セーブして中断した後に「翻訳開始」が再有効化される
- [ ] 通常翻訳で例外が起きてもUIが操作可能状態へ戻る
- [ ] LLM状態表示が完了／中断／エラー後に待機中へ戻る


## v0.11.30 追加確認

- [x] `APP_VERSION` / `VERSION` が 0.11.30 で一致
- [x] 通常翻訳ログ用イベント `normal_log` と progress のUI反映経路を確認
- [x] 翻訳検索の対象Mod一覧取得がバックグラウンドスレッドで実行される
- [x] 翻訳検索本体がバックグラウンドスレッドで実行される
- [x] 検索世代番号により古い結果を無視する
- [x] 翻訳検索の対象Mod選択をワークスペース保存対象に追加
- [x] Python構文チェック


## v0.11.30 Mod隔離確認

- [x] `localization` という同名入力を持つ別Modが別出力フォルダになる
- [x] 生成ファイルが `japanese` ツリーに配置される
- [x] 元Mod上書きで英語・簡体字中国語YAMLが変更されない
- [x] 初回日本語なしModは後から日本語YAMLが増えても日本語化Mod候補へ昇格しない
- [x] 初回から存在する日本語化Modは従来どおり検出可能
- [x] 日本語化Mod上書き前に関係確認の警告を表示
