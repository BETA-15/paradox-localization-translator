#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
translate_paradox.py
Paradox系ゲーム（CK3, Victoria 3, HOI4 等）のローカライズYAMLを
ローカルLLM（Ollama）で一括翻訳するツール。
未翻訳応答の自動検出・不良キャッシュ無効化・単発再試行に対応。

入力フォルダに english / simp_chinese など複数言語のフォルダが混在していても、
ファイルごとに言語を自動判定してすべて日本語に翻訳します。
（ファイル名の "_l_english" "_l_simp_chinese" 等のサフィックス、
  もしくはYAML内の "l_english:" ヘッダーから判定）

想定入力: l_english.yml / l_simp_chinese.yml 形式のファイル群
  ﻿l_english:
   key_name: "text here [Variable.Something] $placeholder$"

使い方:
  # 1. 単一ファイルを日本語へ翻訳
  python translate_paradox.py input.yml -o output_dir

  # 2. フォルダごと再帰的に翻訳（english/ simp_chinese/ が混在していてもOK）
  python translate_paradox.py localization/ -o japanese_folder/

  # 3. モデルやOllamaのURLを指定
  python translate_paradox.py english/ -o japanese/ --model qwen3.6:latest --url http://localhost:11434

  # 4. 途中から再開（キャッシュ済みキーはスキップ）
  python translate_paradox.py english/ -o japanese/ --resume --cache-dir キャッシュ/
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------

DEFAULT_MODEL = "qwen3.6:latest"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_TARGET_LANG = "japanese"  # 出力するl_タグ名にも使う (l_japanese)
CACHE_FILE_NAME = "translate_cache.json"

# Paradoxが使う言語タグ一覧（フォルダ名判定・ヘッダー変換用）
KNOWN_SOURCE_LANGS = [
    "english", "simp_chinese", "german", "french", "spanish",
    "russian", "polish", "braz_por", "japanese", "korean",
]

# Paradox YAML の行パターン: インデント + key: "value" [# comment]
# キー名は基本的に英数字・アンダースコア・ドット・ハイフン・アポストロフィだが、
# Mod側の記述揺れで & や半角スペースが混じることがあるため許容範囲を広げている
LINE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-\'&][A-Za-z0-9_.\-\'& ]*)\s*:\s*'
    r'(?P<version>\d+\s+)?'
    r'"(?P<value>(?:[^"\\]|\\.)*)"'
    r'(?P<trailing>.*)$'
)

# 原文Mod側がダブルクォートのエスケープを誤って忘れているケース
# （例: "...obtain the knowledge of "History of the Subjugation of India" through...")
# を救済するための緩い行パターン。行末が確実に "(コメント以外なにもない) で終わる
# 場合に限り、行全体を1つの value とみなす。
LOOSE_LINE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-\'&][A-Za-z0-9_.\-\'& ]*)\s*:\s*'
    r'(?P<version>\d+\s+)?'
    r'"(?P<value>.*)"\s*(?P<trailing>#.*)?$'
)

HEADER_PATTERN = re.compile(r'^\s*l_(?P<lang>[a-z_]+)\s*:\s*$')

# 保護すべきトークン（翻訳させず、そのまま保持する）
# 例: [ROOT.Char.GetTitledFirstNameNoTooltip], $variable$, £icon£, #tooltippable ... #!,
#     @flag!, [SomeGameConcept|E], 改行 \n, カラーコード §Y ... §!
PROTECT_PATTERNS = [
    r'\[[^\[\]]*\]',            # [Something.Something|X]
    r'\$[^\$]+\$',              # $variable$
    r'£[^£]+£',                 # £icon£
    r'@[A-Za-z_]+!',            # @flag!
    r'§[A-Za-z!]',              # §Y ... §!  (色コード、単体トークンとして保護)
    r'#[A-Za-z_]+(?:;[^#]*)?',  # #tooltip; ... (先頭のみ保護、終端の#!は別途)
    r'#!',                      # 終端タグ
    r'\\n',                     # 改行（文字列としての\n）
    r'\\"',                     # エスケープされたダブルクォート
]
PROTECT_RE = re.compile('(' + '|'.join(PROTECT_PATTERNS) + ')')

PLACEHOLDER_PREFIX = "@@"
PLACEHOLDER_SUFFIX = "@@"
# 正規のプレースホルダ形式: @@0@@ @@1@@ ...
PLACEHOLDER_RE = re.compile(re.escape(PLACEHOLDER_PREFIX) + r'(\d+)' + re.escape(PLACEHOLDER_SUFFIX))
# モデルが記号を書き間違えた場合のフォールバック用（@@0@ @@0# @@0】 等、
# 前置記号は一致するが後置記号が微妙に崩れているケースを拾う）
PLACEHOLDER_FALLBACK_RE = re.compile(re.escape(PLACEHOLDER_PREFIX) + r'(\d+)\D{0,2}')

BATCH_LINE_SEP = "|||"


def load_cache(cache_path: Path) -> dict:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache_path: Path, cache: dict):
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")


def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def protect_text(value: str):
    """
    翻訳対象文字列内の保護トークンを @@0@@ @@1@@ ... のプレースホルダに置換し、
    (置換後文字列, トークンリスト) を返す。
    """
    tokens = []

    def repl(m):
        tokens.append(m.group(0))
        return f"{PLACEHOLDER_PREFIX}{len(tokens)-1}{PLACEHOLDER_SUFFIX}"

    protected = PROTECT_RE.sub(repl, value)
    return protected, tokens


def restore_text(translated: str, tokens: list) -> str:
    """プレースホルダ @@N@@ を元のトークンへ戻す（多少の記号崩れも許容）"""
    def repl(m):
        idx = int(m.group(1))
        if 0 <= idx < len(tokens):
            return tokens[idx]
        return m.group(0)

    # まず正規の形式で復元を試みる
    result = PLACEHOLDER_RE.sub(repl, translated)

    # 正規形式で復元しきれなかった @@N... が残っていれば、崩れた記号ごと救済する
    if PLACEHOLDER_PREFIX in result:
        result = PLACEHOLDER_FALLBACK_RE.sub(repl, result)

    return result


def looks_untranslatable(value: str) -> bool:
    """
    プレースホルダ除去後にほぼ空、または記号のみの場合は翻訳不要と判断。
    (例: "[Character.Custom('x')]" のような完全変数のみの行)
    """
    stripped = PROTECT_RE.sub('', value).strip()
    # 英数字・日本語文字・中国語漢字が一切残らない場合はスキップ
    if not re.search(r'[A-Za-z0-9\u3040-\u30ff\u4e00-\u9fff]', stripped):
        return True
    return False


def looks_foreign_in_target(value: str, target_lang: str) -> bool:
    """対象言語ファイル内に残った未翻訳らしい自然言語を検出する。

    現在は日本語ファイル内の英語残りを主対象とする。Paradoxの変数・タグを除外後、
    日本語文字が無く英語の自然言語らしい場合だけ修復翻訳へ回す。
    短い大文字略語（DLC, AI等）は誤検出を避ける。
    """
    if target_lang != "japanese":
        return False

    plain = PROTECT_RE.sub('', value).strip()
    if not plain:
        return False

    # ひらがな・カタカナ・漢字が1文字でもあれば、既に日本語化されているものとして扱う。
    if re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', plain):
        return False

    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", plain)
    letters = ''.join(words)
    if not words or len(letters) < 4:
        return False

    # DLC / AI / CK3 のような短いコード・略語はそのまま許容。
    if len(words) == 1 and words[0].isupper() and len(words[0]) <= 6:
        return False

    # 複数単語の英文、または小文字を含む4文字以上の単語は修復対象。
    if len(words) >= 2:
        return True
    return len(words[0]) >= 4 and any(c.islower() for c in words[0])


def looks_untranslated(original: str, translated: str, source_lang: str) -> bool:
    """LLMが原文をほぼそのまま返したケースを未翻訳として検出する。

    false positive を避けるため、主に以下を対象にする:
    - 英語/簡体字中国語の原文と訳文が完全一致
    - 英語原文で、十分な英字が残っているのに日本語文字がまったく無い

    ゲーム変数だけの行や、ごく短い略語・固有記号は除外する。
    """
    if original is None or translated is None:
        return False

    orig = original.strip()
    trans = translated.strip()
    if not orig or not trans:
        return False

    # 変数・タグ等を除いた自然言語部分を比較する
    orig_plain = PROTECT_RE.sub('', orig).strip()
    trans_plain = PROTECT_RE.sub('', trans).strip()
    if not orig_plain:
        return False

    # 短い略語・コード類は英語のままでも正常な場合がある
    # ただし単語として明らかな自然言語なら完全一致を未翻訳とみなす
    if orig == trans:
        if source_lang == 'english':
            letters = re.findall(r'[A-Za-z]', orig_plain)
            words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", orig_plain)
            if len(letters) >= 4 and any(len(w) >= 4 for w in words):
                return True
        elif source_lang == 'simp_chinese':
            if re.search(r'[\u4e00-\u9fff]', orig_plain):
                return True

    if source_lang == 'english':
        english_chars = len(re.findall(r'[A-Za-z]', trans_plain))
        japanese_chars = len(re.findall(r'[\u3040-\u30ff]', trans_plain))
        # 漢字だけでは中国語原文・日本語訳の区別がつかないため、英語検出では
        # ひらがな/カタカナの存在を重視する。長めの英文が丸ごと残る事故を拾う。
        if english_chars >= 12 and japanese_chars == 0:
            # 記号や識別子だけでなく、空白を含む自然文らしい場合を優先
            if re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{2,}', trans_plain):
                return True

    return False


def cache_entry_is_valid(original: str, cached: str, source_lang: str) -> bool:
    """既存キャッシュが未翻訳原文そのものなら無効として扱う。"""
    return not looks_untranslated(original, cached, source_lang)


def build_system_prompt(source_lang: str) -> str:
    lang_label = {
        "english": "英語",
        "simp_chinese": "簡体字中国語",
    }.get(source_lang, source_lang)

    return f"""あなたはParadox Interactive社のゲーム（Crusader Kings III, Victoria 3, Hearts of Iron IV等）の
ローカライズ翻訳者です。{lang_label}のゲームテキストを自然で読みやすい日本語に翻訳してください。

入力は複数行のテキストで、各行の先頭に "N|||" (Nは番号) が付いています。
出力も同じ形式で、同じ番号を使い、1行ずつ翻訳結果を返してください。行の順序・行数は変えないこと。

厳守事項:
1. @@0@@ @@1@@ のようなアットマーク+数字+アットマークのプレースホルダは絶対に翻訳・変更・削除・
   移動させず、元の位置関係を保ったまま文中にそのまま残すこと。@@ の数や数字を書き間違えないこと。
   プレースホルダの中身を推測して展開しない。
2. 各行の出力は "N|||翻訳後のテキスト" の形式のみ。説明・注釈・前置き・余計な空行は一切不要。
3. 中世〜近代の統治機構、称号、身分制度などの文脈に合った訳語を使う（例: liege→主君, vassal→家臣, councillor→顧問官 等、文脈に応じて）。
   簡体字中国語が原文の場合、中国語の官職・称号表現（丞相、太守 等）も文脈に応じた自然な日本語の歴史的訳語に変換すること。
4. 原文の改行位置やスペースの意味合いは保持する。
5. ゲーム内の固有名詞的な短いラベル（ボタン名、UI用語）は簡潔に。
6. 性別変数などで文が不完全に見えても、それはテンプレートの一部なので不自然でも直訳的に処理してよい。
7. 原文が中国語の場合、簡体字の漢字表記をそのまま流用せず、自然な日本語（新字体・仮名交じり）に書き改めること。
8. 入力にあった行番号Nは必ずすべて出力に含めること。1行も欠かさないこと。
9. 原文が長い1行の場合、文中に別のダブルクォート（"..."のような入れ子の引用）が含まれることがあるが、
   それも含めて行全体を最後まで省略せず翻訳すること。文中で翻訳を止めないこと。
"""


def call_ollama_raw(url: str, model: str, user_content: str, system_prompt: str,
                     timeout: int = 300, retries: int = 5) -> str:
    endpoint = url.rstrip('/') + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "options": {"temperature": 0.2},
    }
    data = json.dumps(payload).encode("utf-8")

    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                endpoint, data=data, headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = body.get("message", {}).get("content", "").strip()
                content = content.strip('`').strip()
                if not content:
                    # 空応答はOllama側がまだモデルをロード中／過負荷の可能性が高いので
                    # 例外扱いにしてリトライさせる
                    raise RuntimeError("Ollamaから空の応答が返されました")
                return content
        # URLError/TimeoutError/JSONDecodeError に加え、HTTPError（4xx/5xx応答）や
        # ConnectionResetError等のOSレベルの通信エラー、および上の空応答チェックによる
        # RuntimeErrorも含めて広く捕捉し、確実にリトライする
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, ConnectionError, OSError, RuntimeError) as e:
            last_err = e
            # 並列実行時にOllama側が同時1リクエストしか処理できない環境が多いため、
            # 単純な指数バックオフではなく、ある程度長めに待ってから再試行する
            wait = min(5 * (attempt + 1), 30)
            time.sleep(wait)
    raise RuntimeError(f"Ollama呼び出しに{retries}回失敗しました: {last_err}")


def translate_batch(url: str, model: str, values: list, system_prompt: str) -> list:
    """
    複数のvalue（プレースホルダ保護済み文字列）を1回のLLM呼び出しでまとめて翻訳する。
    戻り値は values と同じ順序・同じ長さのリスト。
    パースに失敗した行は原文のまま返す。
    """
    if not values:
        return []

    user_lines = [f"{i}{BATCH_LINE_SEP}{v}" for i, v in enumerate(values)]
    user_content = "\n".join(user_lines)

    raw_response = call_ollama_raw(url, model, user_content, system_prompt)

    result = [None] * len(values)
    for line in raw_response.splitlines():
        if BATCH_LINE_SEP not in line:
            continue
        idx_str, _, translated = line.partition(BATCH_LINE_SEP)
        idx_str = idx_str.strip()
        if not idx_str.isdigit():
            continue
        idx = int(idx_str)
        if 0 <= idx < len(values):
            result[idx] = translated

    # パースできなかった行は原文のまま埋める（安全側）
    for i in range(len(values)):
        if result[i] is None:
            result[i] = values[i]

    return result


def detect_source_lang(path: Path, first_lines: list) -> str:
    """
    ファイル名のサフィックス（_l_english, _l_simp_chinese 等）または
    YAML先頭のヘッダー（l_english: 等）から原文言語を判定する。
    判定できない場合は 'english' として扱う。
    """
    name = path.name.lower()
    for lang in KNOWN_SOURCE_LANGS:
        if f"_l_{lang}" in name or name == f"l_{lang}.yml":
            return lang

    for line in first_lines[:5]:
        m = HEADER_PATTERN.match(line)
        if m:
            return m.group("lang")

    return "english"


def chunk_list(items: list, chunk_size: int):
    for i in range(0, len(items), chunk_size):
        yield items[i:i + chunk_size]


def parse_line(line: str):
    """
    1行をパースして LINE_PATTERN の match オブジェクトを返す。
    通常パターンで失敗した場合、原文Mod側のダブルクォートエスケープ漏れ
    （例: "...knowledge of "History of X" through resolutions..."）を
    救済するための緩いパターンでも試す。
    """
    m = LINE_PATTERN.match(line)
    if m:
        # 通常パターンでマッチしても、閉じクォートの後ろに
        # さらに "..." のような文字列らしきものが続いている場合は
        # エスケープ漏れによる早期終端の疑いがあるため、緩いパターンで
        # 行全体を再取得できるか確認する（できれば長い方を採用）
        trailing = m.group("trailing") or ""
        if re.search(r'^[^#\n]*"[^"]*"', trailing):
            loose_m = LOOSE_LINE_PATTERN.match(line)
            if loose_m and len(loose_m.group("value")) > len(m.group("value")):
                return loose_m
        return m

    # 通常パターンで全くマッチしない場合も緩いパターンで救済を試みる
    loose_m = LOOSE_LINE_PATTERN.match(line)
    if loose_m:
        return loose_m

    return None


def process_file(
    in_path: Path,
    out_path: Path,
    url: str,
    model: str,
    target_lang: str,
    cache: dict,
    workers: int,
    verbose: bool,
    batch_size: int = 40,
):
    raw = in_path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines(keepends=False)

    source_lang = detect_source_lang(in_path, lines)

    # 日本語ファイルを入力した場合も即コピーせず、中に残っている英語だけを修復する。
    # これにより「一部だけ英語のまま残った翻訳済みファイル」をそのまま再投入できる。
    repair_target_file = (source_lang == target_lang)
    translation_source_lang = "english" if repair_target_file and target_lang == "japanese" else source_lang

    if repair_target_file and verbose:
        print(f"  原文は既に{target_lang}です。未翻訳の外国語部分だけを検出して修復します")

    system_prompt = build_system_prompt(translation_source_lang)

    parsed_lines = []  # (kind, data)
    jobs = []

    for line in lines:
        if HEADER_PATTERN.match(line):
            new_header = re.sub(r'l_[a-z_]+', f'l_{target_lang}', line)
            parsed_lines.append(("header", new_header))
            continue

        m = parse_line(line)
        if not m:
            parsed_lines.append(("raw", line))
            continue

        value = m.group("value")
        parsed_lines.append(("line", m))
        line_idx = len(parsed_lines) - 1

        if value == "" or looks_untranslatable(value):
            continue

        if repair_target_file and not looks_foreign_in_target(value, target_lang):
            continue

        h = translation_source_lang + ":" + text_hash(value)
        if h in cache:
            if cache_entry_is_valid(value, cache[h], translation_source_lang):
                continue
            # 原文のまま等の不良キャッシュは破棄して再翻訳する
            if verbose:
                print(f"  [未翻訳キャッシュ検出] {m.group('key')} を再翻訳します")
            cache.pop(h, None)

        protected, tokens = protect_text(value)
        jobs.append({"line_idx": line_idx, "value": value, "protected": protected,
                     "tokens": tokens, "hash": h})

    total_keys = sum(1 for k, _ in parsed_lines if k == "line")
    if verbose:
        print(f"  原文言語: {source_lang}" + ("（修復モード）" if repair_target_file else "") + f" / 全キー数: {total_keys} / "
              f"新規翻訳対象: {len(jobs)} (バッチサイズ: {batch_size})")

    results = {}
    failed_line_indices = set()

    batches = list(chunk_list(jobs, batch_size))

    def run_batch(batch):
        values = [j["protected"] for j in batch]
        try:
            translated_list = translate_batch(url, model, values, system_prompt)
        except Exception as e:
            return batch, None, str(e)
        return batch, translated_list, None

    done_batches = 0
    if workers <= 1 or len(batches) <= 1:
        for b in batches:
            batch, translated_list, err = run_batch(b)
            _apply_batch_result(batch, translated_list, results, cache, translation_source_lang, failed_line_indices)
            if translated_list is None:
                failed_line_indices.update(j["line_idx"] for j in batch)
            done_batches += 1
            if err and verbose:
                print(f"  [警告] バッチ翻訳失敗（該当分は原文のまま出力、後で自動リトライします）: {err}")
            if verbose:
                print(f"    バッチ {done_batches}/{len(batches)} 完了 "
                      f"({sum(len(x) for x in batches[:done_batches])}/{len(jobs)}行)")
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = [ex.submit(run_batch, b) for b in batches]
            for fut in concurrent.futures.as_completed(futures):
                batch, translated_list, err = fut.result()
                _apply_batch_result(batch, translated_list, results, cache, translation_source_lang, failed_line_indices)
                if translated_list is None:
                    failed_line_indices.update(j["line_idx"] for j in batch)
                done_batches += 1
                if err and verbose:
                    print(f"  [警告] バッチ翻訳失敗（該当分は原文のまま出力、後で自動リトライします）: {err}")
                if verbose:
                    print(f"    バッチ {done_batches}/{len(batches)} 完了")

    # 失敗したバッチがあれば、間隔を空けてから単発リトライ（バッチをまとめず1件ずつ）を試みる。
    # 並列実行時の輻輳や一時的なOllama側の過負荷が原因であることが多く、
    # 時間を置いて再試行するだけで解消するケースが多いための救済措置。
    if failed_line_indices:
        if verbose:
            print(f"  {len(failed_line_indices)}件の翻訳失敗または未翻訳応答を検出しました。間隔を空けて単発リトライします...")
        time.sleep(3)
        retry_jobs = [j for j in jobs if j["line_idx"] in failed_line_indices]
        retry_fail_count = 0
        for j in retry_jobs:
            try:
                translated_list = translate_batch(url, model, [j["protected"]], system_prompt)
                restored = restore_text(translated_list[0], j["tokens"])
                if looks_untranslated(j["value"], restored, translation_source_lang):
                    # 単発再試行でも原文のままなら未翻訳として残す
                    results[j["line_idx"]] = j["value"]
                    cache.pop(j["hash"], None)
                    retry_fail_count += 1
                else:
                    results[j["line_idx"]] = restored
                    cache[j["hash"]] = restored
                    failed_line_indices.discard(j["line_idx"])
            except Exception:
                retry_fail_count += 1
        if verbose and retry_fail_count:
            print(f"  再試行後も{retry_fail_count}件は失敗しました（原文のまま出力）。")

    if failed_line_indices and verbose:
        print(f"  [注意] {len(failed_line_indices)}件は再試行後も翻訳できない、または未翻訳応答のため原文のまま出力されています。"
              f"もう一度このツールを実行すると再翻訳が試みられます。")

    out_lines = []
    for idx, (kind, data) in enumerate(parsed_lines):
        if kind == "header":
            out_lines.append(data)
        elif kind == "raw":
            out_lines.append(data)
        elif kind == "line":
            m = data
            orig_value = m.group("value")
            if idx in results:
                translated_value = results[idx]
            elif orig_value != "" and not looks_untranslatable(orig_value):
                h = translation_source_lang + ":" + text_hash(orig_value)
                translated_value = cache.get(h, orig_value)
            else:
                translated_value = orig_value
            version = m.group("version") or ""
            trailing = m.group("trailing") or ""
            new_line = f'{m.group("indent")}{m.group("key")}: {version}"{translated_value}"{trailing}'
            out_lines.append(new_line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\ufeff" + "\n".join(out_lines) + "\n", encoding="utf-8")


def _apply_batch_result(batch, translated_list, results: dict, cache: dict,
                        source_lang: str, failed_line_indices: set):
    """バッチ翻訳結果を反映し、原文のまま返された行も失敗扱いにする。"""
    if translated_list is None:
        for j in batch:
            results[j["line_idx"]] = j["value"]
            failed_line_indices.add(j["line_idx"])
        return

    for j, translated_protected in zip(batch, translated_list):
        restored = restore_text(translated_protected, j["tokens"])
        if looks_untranslated(j["value"], restored, source_lang):
            # 原文のまま返された翻訳はキャッシュしない。後段の単発リトライへ回す。
            results[j["line_idx"]] = j["value"]
            failed_line_indices.add(j["line_idx"])
            cache.pop(j["hash"], None)
        else:
            results[j["line_idx"]] = restored
            cache[j["hash"]] = restored
            failed_line_indices.discard(j["line_idx"])


def rename_for_target(path: Path, target_lang: str, source_lang: str) -> str:
    """ *_l_english.yml -> *_l_japanese.yml  (simp_chinese等も同様) """
    name = path.name
    marker = f"_l_{source_lang}"
    if marker in name:
        return name.replace(marker, f"_l_{target_lang}")
    if name.endswith(".yml"):
        return name[:-4] + f"_l_{target_lang}.yml"
    return name


def remap_rel_dir(rel_dir: Path, target_lang: str) -> Path:
    """
    相対パス中の言語フォルダ名（english, simp_chinese 等）を target_lang に置換する。
    """
    new_parts = []
    for part in rel_dir.parts:
        if part.lower() in KNOWN_SOURCE_LANGS:
            new_parts.append(target_lang)
        else:
            new_parts.append(part)
    return Path(*new_parts) if new_parts else rel_dir


def gather_yml_files(input_path: Path, exclude_lang_dir: str = None):
    if input_path.is_file():
        return [input_path]
    files = []
    for p in sorted(input_path.rglob("*.yml")):
        if "__MACOSX" in p.parts or p.name.startswith("._"):
            continue
        if exclude_lang_dir and exclude_lang_dir.lower() in [part.lower() for part in p.parts]:
            continue
        files.append(p)
    return files


def run_translation(input_path, output_path, model=DEFAULT_MODEL, url=DEFAULT_OLLAMA_URL,
                    target_lang=DEFAULT_TARGET_LANG, workers=1, batch_size=40,
                    cache_path=None, cache_dir=None, resume=True, verbose=True,
                    include_target_files=True):
    """GUI/CLI共通の翻訳実行API。成功した処理ファイル数を返す。"""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    if cache_path:
        cache_file = Path(cache_path)
        cache_file.parent.mkdir(parents=True, exist_ok=True)
    elif cache_dir:
        cache_dir = Path(cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / CACHE_FILE_NAME
    else:
        cache_file = output_path / CACHE_FILE_NAME

    cache = load_cache(cache_file) if (resume or cache_file.exists()) else {}

    # GUI版では既存日本語ファイルの修復も行えるため、既定では target_lang フォルダも探索する。
    exclude = None if include_target_files else target_lang
    files = gather_yml_files(input_path, exclude_lang_dir=exclude)
    if not files:
        raise RuntimeError("翻訳対象のYAMLファイルが見つかりませんでした。")

    def sort_key(p: Path):
        parts_lower = [part.lower() for part in p.parts]
        name = p.name.lower()
        is_english = "english" in parts_lower or "_l_english" in name
        is_target = target_lang in parts_lower or f"_l_{target_lang}" in name
        # 英語を優先し、日本語修復は同一出力先に英語が無い場合に回す。
        return (0 if is_english else 2 if is_target else 1, str(p))

    files = sorted(files, key=sort_key)
    print(f"モデル: {model} / URL: {url}")
    print(f"対象ファイル数: {len(files)}")

    base_dir = input_path if input_path.is_dir() else input_path.parent
    planned_outputs = {}
    processed = 0

    for i, f in enumerate(files, 1):
        rel_dir = f.parent.relative_to(base_dir) if input_path.is_dir() else Path(".")
        out_rel_dir = remap_rel_dir(rel_dir, target_lang)
        try:
            head_lines = f.read_text(encoding="utf-8-sig").splitlines()[:5]
        except Exception:
            head_lines = []
        source_lang = detect_source_lang(f, head_lines)
        out_name = rename_for_target(f, target_lang, source_lang)
        out_file = output_path / out_rel_dir / out_name

        out_key = str(out_file.resolve())
        if out_key in planned_outputs:
            prev_src, prev_lang = planned_outputs[out_key]
            print(f"[{i}/{len(files)}] {f} は {out_file} と出力先が重複するためスキップします "
                  f"（既に {prev_src}（{prev_lang}）を使用済み）")
            continue
        planned_outputs[out_key] = (f, source_lang)

        shown = f.relative_to(base_dir) if input_path.is_dir() else f.name
        print(f"[{i}/{len(files)}] {shown} [{source_lang}] -> {out_file}")
        try:
            process_file(f, out_file, url, model, target_lang,
                         cache, workers, verbose, batch_size)
            processed += 1
        except Exception as e:
            print(f"  [エラー] {f} の処理中に失敗: {e}", file=sys.stderr)
        finally:
            save_cache(cache_file, cache)

    print("完了しました。")
    print(f"キャッシュ: {cache_file}")
    return processed


def main():
    ap = argparse.ArgumentParser(description="ParadoxゲームのローカライズをローカルLLMで一括翻訳")
    ap.add_argument("input", help="入力ファイルまたはフォルダ")
    ap.add_argument("-o", "--output", required=True, help="出力先フォルダ")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollamaモデル名 (既定: {DEFAULT_MODEL})")
    ap.add_argument("--url", default=DEFAULT_OLLAMA_URL, help=f"Ollama API URL (既定: {DEFAULT_OLLAMA_URL})")
    ap.add_argument("--target-lang", default=DEFAULT_TARGET_LANG)
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--batch-size", type=int, default=40)
    ap.add_argument("--cache", default=None)
    ap.add_argument("--cache-dir", default=None)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--exclude-target-files", action="store_true",
                    help="入力内の既存ターゲット言語ファイルを探索対象から除外")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    try:
        run_translation(args.input, args.output, model=args.model, url=args.url,
                        target_lang=args.target_lang, workers=args.workers,
                        batch_size=args.batch_size, cache_path=args.cache,
                        cache_dir=args.cache_dir, resume=args.resume,
                        verbose=args.verbose,
                        include_target_files=not args.exclude_target_files)
    except Exception as e:
        print(f"[致命的エラー] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
