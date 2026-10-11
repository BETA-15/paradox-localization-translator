"""保存して比べている状態の値と、画面に出す表示を分ける（第3段 2-3 章の2番）。

- キューの状態や翻訳状況の判定は、今までどおりの日本語の文字列で保存し、比べる（古い版で保存したジョブも、そのまま読める）。
  この日本語の文字列は「内部の値」で、訳さない。作るときは status_value() を使う。
- 画面に出すときだけ display_status() で画面の言語の表示にする。保存された値をひな形に当てはめて、差し込む値を取り出す。
- 知らない値（将来の版の値など）は、そのまま表示する。
"""
from __future__ import annotations

import re

import i18n

# 内部の値のひな形（日本語。v0.12.0 までに保存された値と一字一句同じ。変えないこと）
STATUS_VALUES = {
    # 翻訳キュー・中国語基準翻訳キュー
    "waiting": "待機",
    "translating": "翻訳中",
    "interrupted": "中断",
    "interrupted_resumable": "中断（再開可）",
    "retrying_errors": "エラー項目を再試行中",
    "error_retry_later": "エラー（後で再試行）",
    "unresolved_error": "未解決エラー",
    "done": "完了",
    "done_warnings": "完了（警告 {count}件）",
    "done_partial_gap": "完了（一部差分欠落あり）",
    "done_diff_updated": "完了（差分更新）",
    "done_no_diff": "完了（差分なし）",
    "done_unresolved": "完了（未解決: {details}）",
    "warn_retry": "警告あり（{details}・再試行予定）",
    "done_lang_chinese": "完了（中国語側完了・英語欠損{count}）",
    "done_lang_normal": "完了（通常側完了・中国語欠損{count}）",
    "overwritten": "上書き済み",
    "no_diff": "差分なし",
    "diff_added_changed_missing": "差分 +{added} / 変更{changed} / 欠損{missing}",
    "diff_added_changed": "差分 +{added} / 変更{changed}",
    "gap_fill": "欠損補完 {missing}",
    # 翻訳状況（translator_core.analyze_mod_translation_status の result["status"]）
    "mod_unknown": "不明",
    "mod_no_target": "対象なし",
    "mod_translated": "翻訳あり",
    "mod_external_complete": "別Modで完全翻訳",
    "mod_external_gaps": "別Mod翻訳・欠損",
    "mod_not_translated": "翻訳なし",
    "mod_gaps": "欠損あり",
    "mod_review_legacy": "要確認（旧式日本語化）",
    "mod_review_unresolved": "要確認（関連元未特定）",
}
# 「警告あり（…）」「完了（未解決: …）」の … の部分
DETAIL_VALUES = {"skipped": "{count}ファイルスキップ", "failed": "翻訳失敗{count}件"}
DETAIL_JOINER = "・"


def _details_value(skipped: int = 0, failed: int = 0) -> str:
    parts = []
    if skipped:
        parts.append(DETAIL_VALUES["skipped"].format(count=skipped))
    if failed:
        parts.append(DETAIL_VALUES["failed"].format(count=failed))
    return DETAIL_JOINER.join(parts)


def status_value(key: str, **fields) -> str:
    """保存する内部の値（日本語）。details は skipped・failed から作る。"""
    if key in ("done_unresolved", "warn_retry"):
        fields = dict(fields)
        fields["details"] = _details_value(int(fields.pop("skipped", 0) or 0), int(fields.pop("failed", 0) or 0))
    return STATUS_VALUES[key].format(**fields)


def _pattern(template: str) -> re.Pattern:
    out, last = "", 0
    for m in re.finditer(r"\{(\w+)\}", template):
        out += re.escape(template[last:m.start()])
        out += rf"(?P<{m.group(1)}>.+?)"
        last = m.end()
    return re.compile("^" + out + re.escape(template[last:]) + "$")


_PATTERNS = [(key, _pattern(template)) for key, template in STATUS_VALUES.items()]
_DETAIL_PATTERNS = [(name, _pattern(template)) for name, template in DETAIL_VALUES.items()]


def parse_status(value: str):
    """内部の値から (key, fields) を取り出す。知らない値なら (None, {})。"""
    text = str(value or "")
    for key, pattern in _PATTERNS:
        m = pattern.match(text)
        if m:
            fields = m.groupdict()
            if "details" in fields:
                for part in fields.pop("details").split(DETAIL_JOINER):
                    for name, detail in _DETAIL_PATTERNS:
                        dm = detail.match(part)
                        if dm:
                            fields[name] = dm.group("count")
            return key, fields
    return None, {}


def display_status(value) -> str:
    """画面の言語の表示。value は内部の値（日本語）か、"status" を持つ dict。"""
    if isinstance(value, dict):
        value = value.get("status", "")
    key, fields = parse_status(value)
    if key is None:
        return str(value or "")
    if key in ("done_unresolved", "warn_retry"):
        parts = []
        if fields.get("skipped"):
            parts.append(i18n.t("status.detail.skipped", count=fields["skipped"]))
        if fields.get("failed"):
            parts.append(i18n.t("status.detail.failed", count=fields["failed"]))
        fields = {"details": i18n.t("status.detail.joiner").join(parts)}
    return i18n.t("status." + key, **fields)


# 閉じるときの動き：保存は confirm / minimize / quit。表示は画面の言語。
CLOSE_ACTIONS = ("confirm", "minimize", "quit")
CLOSE_ACTION_LEGACY = {"毎回確認": "confirm", "最小化": "minimize", "終了": "quit"}


def close_action_label(action: str) -> str:
    return i18n.t("close_action." + (action if action in CLOSE_ACTIONS else "confirm"))


def close_action_from_label(label: str) -> str:
    """選択欄の表示（どの言語でも）または古い版の日本語の値から、保存する値を返す。"""
    label = str(label or "")
    if label in CLOSE_ACTIONS:
        return label
    if label in CLOSE_ACTION_LEGACY:
        return CLOSE_ACTION_LEGACY[label]
    for action in CLOSE_ACTIONS:
        if label == close_action_label(action):
            return action
    return "confirm"


# 性能のおすすめ設定：保存は stable / standard / fast。古い版は日本語の表示を保存していた。
PERFORMANCE_PRESETS = {"stable": (20, 1), "standard": (40, 1), "fast": (60, 2)}
PERFORMANCE_PRESET_LEGACY = {"安定重視（20 / 1）": "stable", "標準（40 / 1）": "standard", "高速（60 / 2）": "fast"}


def performance_preset_label(preset: str) -> str:
    batch, workers = PERFORMANCE_PRESETS.get(preset, PERFORMANCE_PRESETS["standard"])
    return i18n.t("performance_preset." + (preset if preset in PERFORMANCE_PRESETS else "standard"),
                  batch=batch, workers=workers)


def performance_preset_from_label(label: str) -> str:
    label = str(label or "")
    if label in PERFORMANCE_PRESETS:
        return label
    if label in PERFORMANCE_PRESET_LEGACY:
        return PERFORMANCE_PRESET_LEGACY[label]
    for preset in PERFORMANCE_PRESETS:
        if label == performance_preset_label(preset):
            return preset
    return "standard"


# 保存して後で表示し直す文（第3段 2-3 章の決まり2）：文そのものではなく「key と差し込む値」を保存する。
# 結果の dict に "message_parts": [{"id": i18n の key, "fields": {...}}, ...] を入れ、表示するときに組み立てる。
# "message"（作ったときの画面の言語の文）も今までどおり入れておく（古い版・ログ用）。
MESSAGE_PART_JOINER = " "


def message_part(key: str, **fields) -> dict:
    return {"id": key, "fields": dict(fields)}


def build_message(parts) -> str:
    """message_parts を、今の画面の言語の文にする。"""
    texts = []
    for part in parts or []:
        if isinstance(part, dict) and part.get("id"):
            fields = part.get("fields") if isinstance(part.get("fields"), dict) else {}
            texts.append(i18n.t(str(part["id"]), **fields))
    return MESSAGE_PART_JOINER.join(text for text in texts if text).strip()


def display_message(result) -> str:
    """保存した結果の文を表示する。message_parts があれば今の画面の言語で組み立て、無ければ（古い版の結果）message をそのまま。"""
    if not isinstance(result, dict):
        return str(result or "")
    parts = result.get("message_parts")
    if parts:
        text = build_message(parts)
        if text:
            return text
    return str(result.get("message") or "")


DIAGNOSTIC_KINDS = {
    'localization欠落': 'u7.kind.missing_localization',
    'YAML読込エラー': 'u7.kind.yaml_error',
    '日本語化Mod（複数対応可）': 'u7.kind.translation_mod',
    '日本語化Mod候補（未確定）': 'u7.kind.translation_candidate',
    '英語原文なし': 'u7.kind.missing_english',
    '簡体字中国語なし': 'u7.kind.missing_chinese',
    '日本語なし': 'u7.kind.missing_target',
    '同一Mod内の完全重複': 'u7.kind.identical_duplicates',
    '同一Mod内の訳競合': 'u7.kind.translation_conflicts',
    '不要日本語キー': 'u7.kind.unnecessary_keys',
    '不要日本語ファイル': 'u7.kind.unnecessary_files',
    '修復基準なし': 'u7.kind.no_repair_basis',
    '本体/日本語化Mod重複': 'u7.kind.source_translation_duplicates',
    '日本語ファイル異常増加': 'u7.kind.excess_target_files',
    '異常なし': 'u7.kind.healthy',
    '本体/日本語化Mod統合': 'u7.kind.source_translation_integration',
}


def diagnostic_kind_label(kind: str, target_lang: str = "japanese") -> str:
    key = DIAGNOSTIC_KINDS.get(kind)
    return i18n.t(key, target_name=i18n.t("lang." + target_lang)) if key else kind
