#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import queue
import hashlib
import platform
import traceback
import faulthandler
import zipfile
import subprocess
import sys
import threading
import time
import urllib.request
from urllib.parse import urlparse, unquote
import uuid
import shutil
import re
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import translator_core as core
import i18n
import i18n.help as i18n_help
import i18n.rule_ids as i18n_rule_ids
import ui_status
from ui_status import status_value, display_status
import app_state

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    BaseTk = TkinterDnD.Tk
except Exception:
    DND_FILES = None
    DND_AVAILABLE = False
    BaseTk = tk.Tk

APP_NAME = "Paradox Localization Translator"
APP_VERSION = "0.12.1"
MOD_STATUS_CACHE_VERSION = 16
TRANSLATION_STATUS_SNAPSHOT_SCHEMA = 2
MOD_STATUS_EMPTY_IID = "__mod_status_empty__"


def _mod_status_empty_row(query: str, total: int) -> tuple:
    query = (query or "").strip()
    if query:
        return (i18n.t('p0.no_search_results'), i18n.t('p0.no_mods_match', query=query), "", "", "", "")
    return (i18n.t('p0.no_scan_results'), i18n.t('p0.no_translation_status_scan_results'), "", "", "", "")


def _translation_status_snapshot_is_current(snapshot) -> bool:
    return bool(
        isinstance(snapshot, dict)
        and snapshot.get("mod_status_cache_version") == MOD_STATUS_CACHE_VERSION
        and snapshot.get("relation_algorithm_version") == core.TRANSLATION_RELATION_ALGORITHM_VERSION
    )


def _qa_diff_pairs_for_language(pairs, lang=None):
    return [pair for pair in (pairs or []) if lang is None or pair.get("lang") == lang]


def _dedupe_diff_translation_tasks(contexts, tasks):
    out=[]; seen=set()
    for ci,key in tasks or []:
        if not (0 <= ci < len(contexts or [])):
            continue
        token=(str(contexts[ci].get("target_path") or ""),str(key))
        if token in seen:
            continue
        seen.add(token); out.append((ci,key))
    return out


def _qa_failure_display(failure):
    if not isinstance(failure, dict):
        return str(failure)
    name=Path(str(failure.get("source_file") or failure.get("target_file") or i18n.t('p0.unknown_file'))).name
    stage=str(failure.get("stage") or "qa")
    error_type=str(failure.get("error_type") or "Error")
    message=str(failure.get("message") or "")
    return f"{name} [{stage}]: {error_type}: {message}".rstrip(": ")


def _qa_contexts_have_repairable_errors(contexts):
    return any(
        issue.get("severity") == "error" and bool(issue.get("repairable"))
        for context in (contexts or [])
        for issue in (context.get("issues") or [])
    )


def _qa_severity_group(issues):
    severities={str(issue.get("severity") or "") for issue in (issues or [])}
    if "error" in severities: return "error"
    if "warning" in severities: return "warning"
    if "notice" in severities: return "notice"
    return "ok"


def target_lang_note():
    return i18n.t('p0.the_qa_comparison_editor_also')


def _target_lang_choice(lang):
    """翻訳先の選択欄に出す文字（例: フランス語（l_french））。"""
    return f"{core.target_language_label(lang)}（l_{lang}）"


def _target_lang_from_choice(text):
    for lang in core.TARGET_LANGUAGES:
        if text == _target_lang_choice(lang) or text == lang:
            return lang
    return core.DEFAULT_TARGET_LANG


def _item_target_lang(item):
    """キュー項目の翻訳先。v0.11 までに保存された項目には無いので日本語とみなす。"""
    lang=str((item or {}).get("target_lang") or core.DEFAULT_TARGET_LANG)
    return lang if lang in core.TARGET_LANGUAGES else core.DEFAULT_TARGET_LANG


def _current_target_lang(app):
    var=getattr(app,"target_lang_var",None)
    return _target_lang_from_choice(var.get()) if var is not None else core.DEFAULT_TARGET_LANG


def _overwrite_target_lang(app, item):
    return _item_target_lang(item) if item.get("target_lang") else _current_target_lang(app)


def _overwrite_language_problem(app, item, *, external=False, destination=None):
    target_lang = _overwrite_target_lang(app, item)
    if external and target_lang == "english":
        return i18n.t('u6.english_external_overwrite_unavailable')
    preset_var = getattr(app, "preset_var", None)
    preset = item.get("preset") or (preset_var.get() if preset_var is not None else "")
    for path in (item.get("mod_root"), item.get("input"), destination):
        game = item.get("game") or core.game_for_translation(path, preset)
        supported = core.GAME_LANGUAGES.get(game)
        if supported and target_lang not in supported:
            return i18n.t('u6.unsupported_overwrite_language', game=game,
                          target_name=i18n.t("lang." + target_lang))
    return ""


def _record_written_target(backup_root, metadata, target_lang):
    if target_lang != core.DEFAULT_TARGET_LANG:
        metadata["written_target_lang"] = target_lang
        core.save_json(backup_root / "backup_manifest.json", metadata)


def _copy_target_output(src, dst, target_lang, existing_keys):
    if target_lang == core.DEFAULT_TARGET_LANG:
        shutil.copy2(src, dst)
        return True
    language, entries, _ = core.parse_localization_file(src)
    if language != target_lang:
        return False
    missing = {key: value for key, value in entries.items() if key not in existing_keys}
    if not missing:
        return False
    text = core.read_localization_text(dst) if dst.exists() else f"l_{target_lang}:\n"
    if not text.endswith("\n"):
        text += "\n"
    for key, value in missing.items():
        text += f' {key}: "{core.escape_localization_value(value)}"\n'
    dst.write_text("\ufeff" + text.lstrip("\ufeff"), encoding="utf-8")
    existing_keys.update(missing)
    return True


def _existing_target_keys(root, target_lang):
    keys = set()
    for path in _generated_language_files(root, target_lang):
        language, entries, _ = core.parse_localization_file(path)
        if language == target_lang:
            keys.update(entries)
    return keys


def _relation_language_items(payload, field, target_lang, *, create=False):
    container = payload
    if target_lang != core.DEFAULT_TARGET_LANG:
        if create:
            container = payload.setdefault("languages", {}).setdefault(target_lang, {})
        else:
            container = (payload.get("languages") or {}).get(target_lang, {})
    return container.setdefault(field, {}) if create else (container.get(field) or {})


def _translation_status_path(target_lang):
    path = TRANSLATION_STATUS_STATE_PATH
    return path if target_lang == core.DEFAULT_TARGET_LANG else path.with_name(f"{path.stem}_{target_lang}{path.suffix}")


def _status_matches_language(result, target_lang):
    return isinstance(result, dict) and result.get("target_lang", core.DEFAULT_TARGET_LANG) == target_lang


def _relation_scope_text(target_lang):
    key = 'u6.mod_research_translation_mod_assessment_and' if target_lang == "japanese" else 'u6.target_relation_scope'
    text = i18n.t(key, target_name=i18n.t("lang." + target_lang))
    if target_lang == "english":
        text += " " + i18n.t('u6.english_external_check_skipped')
    return text


def _normalize_spacing_enabled(app):
    var = getattr(app, "normalize_spacing_var", None)
    return bool(var.get()) if var is not None else True


def _glossary_language(app):
    var=getattr(app,"glossary_lang_var",None)
    return _target_lang_from_choice(var.get()) if var is not None else core.DEFAULT_TARGET_LANG


def _selected_glossary_path(app):
    return core.glossary_path_for_language(app.glossary_path_var.get() or DEFAULT_GLOSSARY,
                                           _glossary_language(app))


def _existing_language_glossary(base_path, target_lang):
    if not base_path:
        return None
    path=core.glossary_path_for_language(base_path,target_lang)
    return path if path.is_file() else None


def _japanese_glossary_only(app):
    if _glossary_language(app) == core.DEFAULT_TARGET_LANG:
        return True
    messagebox.showinfo(APP_NAME,i18n.t('p0.this_feature_is_available_only'))
    return False


def _cache_for_target(cache_path, lang):
    """翻訳先ごとのキャッシュファイル。日本語は今までの場所のまま。

    source_manifest.json はキャッシュと同じフォルダに置かれるので、ほかの言語はフォルダごと分け、
    日本語の差分判定（前回の原文の記録）を別の言語の翻訳で上書きしない。
    """
    cache=Path(cache_path)
    if lang == core.DEFAULT_TARGET_LANG:
        return cache
    path=cache.parent / f"target_{lang}" / cache.name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _target_language_problems(items, diff_requested=False, preset=""):
    """翻訳開始前の確認：(止める理由, ゲームが読めない言語の警告の一覧) を返す。"""
    warnings=[]
    for it in items:
        warning=core.game_language_warning(_item_target_lang(it), it.get("input",""), preset)
        if warning and warning not in warnings:
            warnings.append(warning)
    return "", warnings


def _generated_language_files(output_root, target_lang):
    files=[]
    output_root=Path(output_root)
    if not output_root.exists():
        return files
    for p in sorted(output_root.rglob("*.yml")):
        try:
            head=core.read_localization_text(p).splitlines()[:5]
            lang=core.detect_source_lang(p,head)
        except Exception:
            lang=""
        if lang == target_lang or f"_l_{target_lang}" in p.name.lower():
            files.append(p)
    return files


DIFF_TRANSLATE_ATTEMPTS = 2  # 差分翻訳で、使えない訳が返ったときに訳し直す回数（最初の1回を含む）


def _diff_translation_problem(source_text, translated, source_lang, target_lang=core.DEFAULT_TARGET_LANG):
    """差分翻訳の訳文が書き込めるかを確かめる。書けないなら理由、書けるなら空文字。

    通常翻訳（process_file）と同じく、原文のまま・未翻訳に見えるもの・ゲーム変数やタグが原文と食い違うもの・
    内部の @@N@@ が残ったものは書き込まない。
    """
    text=str(translated or "")
    if not text.strip():
        return i18n.t('p0.the_llm_response_was_empty')
    if "@@" in text:
        return i18n.t('p0.internal_markers_n_remain')
    if core.extract_protected_tokens(text) != core.extract_protected_tokens(source_text):
        return i18n.t('p0.game_variables_or_tags_do')
    if target_lang == core.DEFAULT_TARGET_LANG and core.looks_like_chinese_in_japanese(text):
        return i18n.t('p0.the_response_was_chinese_not')
    if text.strip() == str(source_text or "").strip() or core.unusable_translation(source_text, text, source_lang, target_lang):
        return i18n.t('p0.the_response_is_unchanged_or')
    return ""


def _mod_root_of_localization_file(path):
    """localization（localisation）フォルダの中のファイルなら、その親（Mod のフォルダ）を返す。"""
    for parent in Path(path).parents:
        if core.is_localization_dir_name(parent.name):
            return parent.parent
    return None


def _llm_connection_alert_content(provider, url, model="", error=""):
    """Return user-facing connection guidance without touching Tk widgets."""
    display=core.provider_display_name(provider)
    normalized=core.normalize_provider(provider)
    endpoint=(url or core.default_url_for_provider(provider)).strip()
    detail=str(error or "").strip()
    low=detail.lower()
    transport_tokens=("connection refused","couldn't connect","failed to connect","timed out","timeout",
                      "network is unreachable","name or service not known","nodename nor servname",
                      "remote end closed","connection reset","urlopen error")
    transport_failure=any(token in low for token in transport_tokens)
    if core.THINKING_ONLY_MARKER in detail:
        lines=[detail,"",i18n.t('p0.provider', display=display),i18n.t('p0.endpoint', endpoint=endpoint)]
        if model: lines.append(i18n.t('p0.model', model=model))
        return {"title":i18n.t('p0.this_model_is_not_supported'),"heading":i18n.t('p0.thinking_models_are_not_supported'),
                "message":"\n".join(lines),"category":"thinking_model","provider":display,"endpoint":endpoint}
    if core.REASONING_MODEL_MARKER in detail:
        lines=[detail,"",i18n.t('p0.provider', display=display),i18n.t('p0.endpoint', endpoint=endpoint)]
        if model: lines.append(i18n.t('p0.model', model=model))
        return {"title":i18n.t('p0.this_model_is_not_supported'),"heading":i18n.t('p0.models_that_output_reasoning_are'),
                "message":"\n".join(lines),"category":"reasoning_model","provider":display,"endpoint":endpoint}
    if core.EMBEDDING_ONLY_MARKER in detail:
        lines=[detail,"",i18n.t('p0.provider', display=display),i18n.t('p0.endpoint', endpoint=endpoint)]
        if model: lines.append(i18n.t('p0.model', model=model))
        return {"title":i18n.t('p0.this_model_is_not_supported'),"heading":i18n.t('p0.embedding_only_models_cannot_translate'),
                "message":"\n".join(lines),"category":"embedding_model","provider":display,"endpoint":endpoint}
    if normalized in {"ollama","lmstudio"} and transport_failure:
        service="LM Studio" if normalized=="lmstudio" else "Ollama"
        guidance=i18n.t("p0.local_server_guidance" if normalized=="lmstudio" else "p0.llm_server_guidance",
                   service=service)
        category="local_unavailable"
    elif normalized in {"ollama","lmstudio"} and not model:
        guidance=i18n.t('p0.no_model_is_selected_for', display=display)
        category="model_missing"
    elif any(token in low for token in ("401","403","unauthorized","forbidden","api key","authentication")):
        guidance=i18n.t('p0.api_authentication_failed_check_the', display=display)
        category="authentication"
    elif any(token in low for token in ("404","model","not found","モデル","読み込み済み")):
        guidance=i18n.t('p0.cannot_verify_the_model_or', display=display)
        category="configuration"
    else:
        guidance=i18n.t('p0.cannot_communicate_with_check_the', display=display)
        category="unavailable"
    lines=[guidance,"",i18n.t('p0.provider', display=display),i18n.t('p0.endpoint', endpoint=endpoint)]
    if model: lines.append(i18n.t('p0.model', model=model))
    if detail: lines.extend(["",i18n.t('p0.details', detail=detail)])
    return {"title":i18n.t('p0.cannot_connect_to_the_llm'),"heading":i18n.t('p0.llm_connection_failed'),
            "message":"\n".join(lines),"category":category,"provider":display,"endpoint":endpoint}


def _is_llm_connection_alert_error(error):
    low=str(error or "").lower()
    return any(token in low for token in (
        "connection refused","couldn't connect","failed to connect","timed out","timeout",
        "network is unreachable","name or service not known","nodename nor servname",
        "remote end closed","connection reset","urlopen error","http error 401",
        "http error 403","http error 404","unauthorized","forbidden","model not found",
    ))


def _build_qa_log_payload(contexts, failures, generated_at=None, app_version=None, repair_result=None, ui_language=None):
    """Create a text-free but actionable snapshot of the latest inspected QA run.

    ui_language: 文（reason・message など）を書いた画面の言語。古いログに無いときは日本語とみなす。"""
    files=[]; issue_total=0; error_total=0; warning_total=0; notice_total=0; languages=[]
    for context in contexts or []:
        lang=str(context.get("lang") or "")
        if lang and lang not in languages: languages.append(lang)
        issues=[]
        for issue in context.get("issues") or []:
            severity=str(issue.get("severity") or "")
            row={
                "key":str(issue.get("key") or ""), "type":str(issue.get("type") or ""),
                "severity":severity, "rule_id":str(issue.get("rule_id") or ""),
                "repairable":bool(issue.get("repairable",False)),
                "recommended_action":str(issue.get("recommended_action") or ""),
                "reason":str(issue.get("reason") or ""),
                "source_line":issue.get("source_line"), "target_line":issue.get("target_line"),
            }
            if "expected_tokens" in issue: row["expected_tokens"]=list(issue.get("expected_tokens") or [])
            if "actual_tokens" in issue: row["actual_tokens"]=list(issue.get("actual_tokens") or [])
            issues.append(row); issue_total += 1
            if severity=="error": error_total += 1
            elif severity=="warning": warning_total += 1
            elif severity=="notice": notice_total += 1
        files.append({
            "source_file":str(context.get("source_path") or ""),
            "target_file":str(context.get("target_path") or ""),
            "source_language":lang,
            "source_keys":len(context.get("source_entries") or {}),
            "target_keys":len(context.get("target_entries") or {}),
            "errors":sum(i["severity"]=="error" for i in issues),
            "warnings":sum(i["severity"]=="warning" for i in issues),
            "notices":sum(i["severity"]=="notice" for i in issues),
            "repairable_errors":sum(i["severity"]=="error" and i["repairable"] for i in issues),
            "issue_types":{kind:sum(i["type"]==kind for i in issues) for kind in sorted({i["type"] for i in issues})},
            "issues":issues,
        })
    safe_failures=[]
    for failure in failures or []:
        if isinstance(failure,dict):
            row={k:str(failure.get(k) or "") for k in ("source_file","target_file","source_language","stage","error_type","message","action")}
            safe_failures.append(row)
            if row["source_language"] and row["source_language"] not in languages: languages.append(row["source_language"])
        else:
            safe_failures.append({"source_file":"","target_file":"","source_language":"","stage":"qa","error_type":"Error","message":str(failure),"action":i18n.t('p0.skip_and_continue')})
    mode="single" if len(files)+len(safe_failures)<=1 else ("english_bulk" if languages==["english"] else ("simp_chinese_bulk" if languages==["simp_chinese"] else "batch"))
    payload={
        "schema":2,
        "generated_at":generated_at or datetime.now().isoformat(timespec="seconds"),
        "app_version":str(app_version or APP_VERSION),
        "ui_language":str(ui_language or i18n.get_ui_language()),
        "mode":mode,
        "source_languages":languages,
        "summary":{"files":len(files)+len(safe_failures),"completed_files":len(files),"failed_files":len(safe_failures),
                   "issues":issue_total,"errors":error_total,"warnings":warning_total,"notices":notice_total,
                   "repairable_errors":sum(f.get("repairable_errors",0) for f in files)},
        "files":files,
        "failures":safe_failures,
    }
    if isinstance(repair_result,dict):
        payload["auto_repair"]={
            "backup_dir":str(repair_result.get("backup_dir") or ""),
            "summary":dict(repair_result.get("summary") or {}),
            "files":[{
                "source_file":str(row.get("source_file") or ""),
                "target_file":str(row.get("target_file") or ""),
                "source_language":str(row.get("source_language") or ""),
                "initial_errors":int(row.get("initial_errors",0) or 0),
                "final_errors":int(row.get("final_errors",0) or 0),
                "repaired":int(row.get("repaired",0) or 0),
                "repair_attempts":int(row.get("repair_attempts",0) or 0),
                "backup":str(row.get("backup") or ""),
                "rolled_back":bool(row.get("rolled_back",False)),
                "events":[dict(event) for event in (row.get("events") or [])],
            } for row in (repair_result.get("files") or [])],
            "failures":[dict(row) for row in (repair_result.get("failures") or [])],
        }
    return payload


def _compact_status_gap_groups(rows):
    """Group gap keys by origin without repeating a dict for every key."""
    compact = {}
    for row in rows or []:
        if not isinstance(row, dict) or not row.get("key"):
            continue
        origin = str(row.get("source_origin") or "")
        compact.setdefault(origin, []).append(str(row.get("key")))
    return compact


def _status_gap_rows(result, external=False):
    """Return full live gaps or rebuild lightweight persisted gaps on demand."""
    if not isinstance(result, dict):
        return []
    field = "external_translation_gaps" if external else "candidates"
    rows = result.get(field)
    if isinstance(rows, list) and rows:
        return rows
    if external and result.get("external_gaps_match_candidates"):
        groups = result.get("candidate_gap_keys_by_origin") or {}
    else:
        groups = result.get(
            "external_gap_keys_by_origin" if external else "candidate_gap_keys_by_origin"
        ) or {}
    rebuilt = []
    for origin, keys in groups.items():
        for key in keys or []:
            item = {"key": str(key)}
            if origin:
                item["source_origin"] = str(origin)
            rebuilt.append(item)
    return rebuilt


def _compact_translation_status_result(result):
    """Remove source text payloads while preserving visible status and gap keys."""
    if not isinstance(result, dict):
        return {}
    compact = dict(result)
    candidate_groups = _compact_status_gap_groups(_status_gap_rows(result))
    external_groups = _compact_status_gap_groups(_status_gap_rows(result, external=True))
    compact.pop("candidates", None)
    compact.pop("external_translation_gaps", None)
    compact["candidate_gap_keys_by_origin"] = candidate_groups
    if external_groups and external_groups == candidate_groups:
        compact["external_gaps_match_candidates"] = True
        compact.pop("external_gap_keys_by_origin", None)
    else:
        compact["external_gaps_match_candidates"] = False
        compact["external_gap_keys_by_origin"] = external_groups
    return compact


def _app_container_dir() -> Path:
    """Return the directory beside the packaged app/executable when possible."""
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        if sys.platform == "darwin":
            for parent in [exe, *exe.parents]:
                if parent.name.endswith(".app"):
                    return parent.parent
        return exe.parent
    return Path(__file__).resolve().parent.parent


def _is_writable_dir(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False


PREF_DOMAIN = "com.beta15.ParadoxLocalizationTranslator"
DATA_FOLDER_NAME = "Paradox Localization Translator"


def _default_data_root() -> Path:
    return Path.home() / "Documents" / DATA_FOLDER_NAME


def _load_saved_data_root() -> Path | None:
    """Read the chosen data-root location without placing normal app data outside DATA_ROOT."""
    try:
        if os.name == "nt":
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\BETA-15\ParadoxLocalizationTranslator") as key:
                value, _ = winreg.QueryValueEx(key, "DataRoot")
                if value:
                    return Path(value).expanduser()
        elif sys.platform == "darwin":
            cp = subprocess.run(["defaults", "read", PREF_DOMAIN, "DataRoot"], capture_output=True, text=True, timeout=2)
            value = cp.stdout.strip() if cp.returncode == 0 else ""
            if value:
                return Path(value).expanduser()
        else:
            locator = Path.home() / ".config" / "paradox-localization-translator" / "location.json"
            if locator.exists():
                data = json.loads(locator.read_text(encoding="utf-8"))
                if data.get("data_root"):
                    return Path(data["data_root"]).expanduser()
    except Exception:
        pass
    return None


def _save_data_root_preference(path: Path):
    path = path.expanduser().resolve()
    try:
        if os.name == "nt":
            import winreg
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\BETA-15\ParadoxLocalizationTranslator")
            with key:
                winreg.SetValueEx(key, "DataRoot", 0, winreg.REG_SZ, str(path))
        elif sys.platform == "darwin":
            subprocess.run(["defaults", "write", PREF_DOMAIN, "DataRoot", str(path)], check=False, capture_output=True)
        else:
            locator = Path.home() / ".config" / "paradox-localization-translator" / "location.json"
            locator.parent.mkdir(parents=True, exist_ok=True)
            locator.write_text(json.dumps({"data_root": str(path)}, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _automatic_data_root() -> Path:
    override=os.environ.get("PARADOX_TRANSLATOR_DATA_ROOT","").strip()
    if override:
        root=Path(override).expanduser()
        root.mkdir(parents=True,exist_ok=True)
        return root
    saved = _load_saved_data_root()
    if saved is not None and _is_writable_dir(saved):
        return saved
    root = _default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _log_category_dirs(root: Path) -> dict:
    root=Path(root)
    return {
        "qa":root / "QA",
        "error":root / "エラー",
        "judgement":root / "日本語化Mod判定",
        "diagnostic":root / "診断",
        "unattended":root / "夜間処理",
        "system":root / "システム・履歴",
    }


def _log_category_for_name(name: str):
    name=str(name or "")
    if name.startswith("qa_report_") and name.endswith(".json"): return "qa"
    if (name.startswith("errors_") or name.startswith("fatal_")) and name.endswith(".log"): return "error"
    if name.startswith("translation_mod_judgement_") and name.endswith(".txt"): return "judgement"
    if name.startswith("ParadoxLocalizationTranslator_diagnostics_") and name.endswith(".zip"): return "diagnostic"
    if name.startswith("unattended_translation_") and name.endswith(".json"): return "unattended"
    if name in {"resume_history.jsonl","storage_migration.log"}: return "system"
    return None


def _non_overwriting_log_destination(directory: Path, name: str) -> Path:
    target=Path(directory)/name
    if not target.exists(): return target
    source=Path(name); counter=1
    while True:
        candidate=Path(directory)/f"{source.stem}_migrated_{counter}{source.suffix}"
        if not candidate.exists(): return candidate
        counter += 1


def _organize_existing_logs(root: Path) -> dict:
    """Move known legacy root-level logs into category folders without overwriting."""
    root=Path(root); dirs=_log_category_dirs(root); result={"moved":[],"errors":[]}
    try:
        root.mkdir(parents=True,exist_ok=True)
        for directory in dirs.values(): directory.mkdir(parents=True,exist_ok=True)
        for source in list(root.iterdir()):
            if not source.is_file(): continue
            category=_log_category_for_name(source.name)
            if not category: continue
            target=_non_overwriting_log_destination(dirs[category],source.name)
            try:
                shutil.move(str(source),str(target)); result["moved"].append({"source":str(source),"target":str(target)})
            except Exception as exc:
                result["errors"].append({"source":str(source),"error":f"{type(exc).__name__}: {exc}"})
        old_native=root/"native_crash_reports"; new_native=dirs["error"]/"native_crash_reports"
        if old_native.is_dir() and old_native != new_native:
            new_native.mkdir(parents=True,exist_ok=True)
            for source in list(old_native.iterdir()):
                if not source.is_file(): continue
                target=_non_overwriting_log_destination(new_native,source.name)
                try:
                    shutil.move(str(source),str(target)); result["moved"].append({"source":str(source),"target":str(target)})
                except Exception as exc:
                    result["errors"].append({"source":str(source),"error":f"{type(exc).__name__}: {exc}"})
            try: old_native.rmdir()
            except OSError: pass
    except Exception as exc:
        result["errors"].append({"source":str(root),"error":f"{type(exc).__name__}: {exc}"})
    return result


def _diagnostic_log_files(root: Path) -> list[Path]:
    dirs=_log_category_dirs(Path(root)); files=[]
    for category in ("qa","error","judgement","unattended","system"):
        directory=dirs[category]
        if directory.exists(): files.extend(path for path in directory.rglob("*") if path.is_file())
    return sorted(files,key=lambda path:str(path))


def _configure_data_root(root: Path):
    """Update all generated-file locations after the user changes the storage root."""
    global DATA_ROOT, APP_HOME, OUTPUT_ROOT, SESSION_PATH, DEFAULT_GLOSSARY
    global STATS_PATH, PROFILES_PATH, CACHE_ROOT, CACHE_REGISTRY_PATH, BACKUP_ROOT
    global SAVED_STEAM_ROOTS_PATH, LOG_ROOT, QA_LOG_ROOT, ERROR_LOG_ROOT, JUDGEMENT_LOG_ROOT, DIAGNOSTIC_LOG_ROOT, UNATTENDED_LOG_ROOT, SYSTEM_LOG_ROOT
    global MOD_STATUS_CACHE_PATH, MOD_CLASSIFICATION_CACHE_PATH, MOD_RELATION_OVERRIDES_PATH, APP_PREFS_PATH
    global TRANSLATION_STATUS_STATE_PATH, DIAGNOSTIC_STATE_PATH, SHARED_MOD_STATE_CACHE_PATH
    global RESUME_STATE_PATH, RESUME_HISTORY_PATH, WORK_STATE_ROOT, MIGRATION_STATE_PATH, WORKSPACE_STATE_PATH
    DATA_ROOT = root.expanduser().resolve()
    APP_HOME = DATA_ROOT / "設定"
    OUTPUT_ROOT = DATA_ROOT / "翻訳結果"
    SESSION_PATH = APP_HOME / "session.json"
    DEFAULT_GLOSSARY = APP_HOME / "glossary.json"
    STATS_PATH = APP_HOME / "model_stats.json"
    PROFILES_PATH = APP_HOME / "model_profiles.json"
    CACHE_ROOT = DATA_ROOT / "キャッシュ"
    CACHE_REGISTRY_PATH = CACHE_ROOT / "cache_registry.json"
    BACKUP_ROOT = DATA_ROOT / "バックアップ"
    LOG_ROOT = DATA_ROOT / "ログ"
    log_dirs=_log_category_dirs(LOG_ROOT)
    QA_LOG_ROOT=log_dirs["qa"]; ERROR_LOG_ROOT=log_dirs["error"]; JUDGEMENT_LOG_ROOT=log_dirs["judgement"]
    DIAGNOSTIC_LOG_ROOT=log_dirs["diagnostic"]; UNATTENDED_LOG_ROOT=log_dirs["unattended"]; SYSTEM_LOG_ROOT=log_dirs["system"]
    SAVED_STEAM_ROOTS_PATH = APP_HOME / "steam_library_roots.json"
    MOD_STATUS_CACHE_PATH = CACHE_ROOT / "mod_translation_status_cache.json"
    # Stable first-seen Mod role cache.  A source/child Mod that originally had no
    # Japanese localization must not become an external Japanese-translation Mod
    # merely because this application later generated Japanese YAML inside it.
    MOD_CLASSIFICATION_CACHE_PATH = CACHE_ROOT / "mod_classification_cache.json"
    MOD_RELATION_OVERRIDES_PATH = CACHE_ROOT / "mod_relation_overrides.json"
    TRANSLATION_STATUS_STATE_PATH = CACHE_ROOT / "translation_status_state.json"
    DIAGNOSTIC_STATE_PATH = CACHE_ROOT / "diagnostic_state.json"
    SHARED_MOD_STATE_CACHE_PATH = CACHE_ROOT / "shared_mod_state_cache.json"
    APP_PREFS_PATH = APP_HOME / "app_preferences.json"
    # Stable, version-independent resume files. APP_VERSION is metadata only.
    RESUME_STATE_PATH = APP_HOME / "resume_state.json"
    RESUME_HISTORY_PATH = SYSTEM_LOG_ROOT / "resume_history.jsonl"
    # Version-independent runtime/work state belongs under the user data root,
    # never beside the executable/app bundle.
    WORK_STATE_ROOT = DATA_ROOT / "作業データ"
    MIGRATION_STATE_PATH = APP_HOME / "storage_migration.json"
    WORKSPACE_STATE_PATH = APP_HOME / "workspace_state.json"
    for d in (DATA_ROOT, APP_HOME, OUTPUT_ROOT, CACHE_ROOT, BACKUP_ROOT, LOG_ROOT, QA_LOG_ROOT, ERROR_LOG_ROOT,
              JUDGEMENT_LOG_ROOT, DIAGNOSTIC_LOG_ROOT, UNATTENDED_LOG_ROOT, SYSTEM_LOG_ROOT, WORK_STATE_ROOT):
        d.mkdir(parents=True, exist_ok=True)


DATA_ROOT = _automatic_data_root()
_configure_data_root(DATA_ROOT)


def _legacy_data_roots() -> list[Path]:
    """Known locations used by older builds for generated/runtime data."""
    app_dir = _app_container_dir()
    candidates = [
        app_dir / "ParadoxLocalizationTranslator_Data",
        app_dir / ".paradox_localization_translator",
        Path.home() / ".paradox_localization_translator",
    ]
    # Source runs from a repository directory. Very old development builds could
    # leave generated state directly beside main.py/project root. Treat the
    # project root itself as a source only for explicitly recognised loose files.
    unique = []
    seen = set()
    for path in candidates:
        try:
            key = str(path.expanduser().resolve())
        except Exception:
            key = str(path.expanduser())
        if key == str(DATA_ROOT):
            continue
        if key not in seen:
            seen.add(key); unique.append(path)
    return unique


def _copy_newer_file(src: Path, dst: Path) -> bool:
    """Copy a legacy file when missing or newer. Never delete the source."""
    try:
        if not src.is_file():
            return False
        if dst.exists():
            try:
                if dst.stat().st_mtime >= src.stat().st_mtime:
                    return False
            except Exception:
                return False
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except Exception:
        return False


def _merge_legacy_tree(src_root: Path, dst_root: Path) -> int:
    copied = 0
    if not src_root.is_dir():
        return copied
    for src in src_root.rglob("*"):
        if not src.is_file():
            continue
        try:
            rel = src.relative_to(src_root)
        except Exception:
            continue
        if _copy_newer_file(src, dst_root / rel):
            copied += 1
    return copied


def _migrate_legacy_generated_data() -> dict:
    """Copy recognised generated data away from executable-dependent locations.

    Migration is deliberately non-destructive. Old app-adjacent data is left in
    place, so a failed/new build can still be rolled back safely.
    """
    result = {"copied": 0, "sources": [], "timestamp": datetime.now().isoformat(timespec="seconds")}
    recognised_dirs = {
        "翻訳結果": OUTPUT_ROOT,
        "キャッシュ": CACHE_ROOT,
        "バックアップ": BACKUP_ROOT,
        "ログ": LOG_ROOT,
        "設定": APP_HOME,
        "作業データ": WORK_STATE_ROOT,
    }
    recognised_loose = {
        "session.json": SESSION_PATH,
        "resume_state.json": RESUME_STATE_PATH,
        "glossary.json": DEFAULT_GLOSSARY,
        "model_stats.json": STATS_PATH,
        "model_profiles.json": PROFILES_PATH,
        "steam_library_roots.json": SAVED_STEAM_ROOTS_PATH,
        "mod_translation_status_cache.json": MOD_STATUS_CACHE_PATH,
        "mod_classification_cache.json": MOD_CLASSIFICATION_CACHE_PATH,
        "mod_relation_overrides.json": MOD_RELATION_OVERRIDES_PATH,
        "translation_status_state.json": TRANSLATION_STATUS_STATE_PATH,
        "diagnostic_state.json": DIAGNOSTIC_STATE_PATH,
        "shared_mod_state_cache.json": SHARED_MOD_STATE_CACHE_PATH,
        "app_preferences.json": APP_PREFS_PATH,
        "workspace_state.json": WORKSPACE_STATE_PATH,
        "cache_registry.json": CACHE_REGISTRY_PATH,
    }
    for legacy in _legacy_data_roots():
        if not legacy.exists():
            continue
        copied_here = 0
        for name, dst in recognised_dirs.items():
            copied_here += _merge_legacy_tree(legacy / name, dst)
        # Some older builds stored config/cache files directly in their data dir.
        for name, dst in recognised_loose.items():
            if _copy_newer_file(legacy / name, dst):
                copied_here += 1
        if copied_here:
            result["sources"].append(str(legacy))
            result["copied"] += copied_here

    # Pre-v0.5 model statistics were stored under ~/.paradox_localization_translator.
    # The loop above handles known loose files there; preserve any cache/history
    # subdirectories too if they exist under familiar English names.
    old_home = Path.home() / ".paradox_localization_translator"
    for dirname, dst in (("cache", CACHE_ROOT), ("logs", LOG_ROOT), ("backup", BACKUP_ROOT)):
        n = _merge_legacy_tree(old_home / dirname, dst)
        if n:
            result["copied"] += n
            if str(old_home) not in result["sources"]:
                result["sources"].append(str(old_home))
    # v0.11.44 moved persistent Translation Status / Total Diagnosis cache files
    # from 設定 to キャッシュ. Copy the previous current-layout files once,
    # non-destructively, so upgrading never loses the user's state.
    for name, dst in (
        ("mod_translation_status_cache.json", MOD_STATUS_CACHE_PATH),
        ("mod_classification_cache.json", MOD_CLASSIFICATION_CACHE_PATH),
        ("mod_relation_overrides.json", MOD_RELATION_OVERRIDES_PATH),
    ):
        old = APP_HOME / name
        if old != dst and _copy_newer_file(old, dst):
            result["copied"] += 1
            if str(APP_HOME) not in result["sources"]:
                result["sources"].append(str(APP_HOME))

    try:
        previous = core.load_json(MIGRATION_STATE_PATH, {})
        result["previous_run"] = previous.get("timestamp") if isinstance(previous, dict) else None
        core.save_json(MIGRATION_STATE_PATH, result)
        if result["copied"]:
            SYSTEM_LOG_ROOT.mkdir(parents=True, exist_ok=True)
            with (SYSTEM_LOG_ROOT / "storage_migration.log").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(result, ensure_ascii=False) + "\n")
    except Exception:
        pass
    return result


def _remap_legacy_data_path(value):
    """Map saved absolute paths from an old executable-local data root to DATA_ROOT."""
    if not value or not isinstance(value, str):
        return value
    try:
        candidate = Path(value).expanduser()
    except Exception:
        return value
    roots = _legacy_data_roots()
    # Include the historic output/.cache layout as a special case elsewhere.
    for legacy in roots:
        try:
            rel = candidate.resolve().relative_to(legacy.resolve())
        except Exception:
            continue
        mapped = DATA_ROOT / rel
        # Old root subdirectory names match the current root for the main trees.
        # If migration copied it, prefer the portable location even when the old
        # executable is still present.
        return str(mapped)
    return value


def _remap_saved_data_path(value, saved_root=None):
    """Remap a path saved under another app-data root to the current DATA_ROOT."""
    if not value or not isinstance(value, str):
        return value
    if saved_root:
        try:
            candidate = Path(value).expanduser().resolve()
            old_root = Path(saved_root).expanduser().resolve()
            rel = candidate.relative_to(old_root)
            return str(DATA_ROOT / rel)
        except Exception:
            pass
    return _remap_legacy_data_path(value)


LEGACY_MIGRATION_RESULT = _migrate_legacy_generated_data()
LOG_CATEGORY_MIGRATION_RESULT = _organize_existing_logs(LOG_ROOT)


def _error_log_path() -> Path:
    ERROR_LOG_ROOT.mkdir(parents=True, exist_ok=True)
    return ERROR_LOG_ROOT / f"errors_{datetime.now().strftime('%Y%m%d')}.log"


def record_error(context: str, exc: BaseException | None = None, detail: str = ""):
    """Append an application error entry. API keys are never included."""
    try:
        lines = [
            "=" * 78,
            datetime.now().isoformat(timespec="seconds"),
            f"context: {context}",
            f"app: {APP_NAME} {APP_VERSION}",
            f"platform: {platform.platform()}",
            f"python: {sys.version.splitlines()[0]}",
        ]
        if detail:
            lines.append(f"detail: {detail}")
        if exc is not None:
            lines.append(f"exception: {type(exc).__name__}: {exc}")
            lines.append("traceback:")
            lines.extend(traceback.format_exception(type(exc), exc, exc.__traceback__))
        with _error_log_path().open("a", encoding="utf-8") as fh:
            fh.write("\n".join(str(x).rstrip("\n") for x in lines) + "\n")
    except Exception:
        pass


def load_persistent_json(path: Path, default, label: str):
    """Load application-owned JSON and quarantine malformed data with a visible log."""
    path=Path(path)
    if not path.exists():
        return default
    try:
        text,_encoding=core.decode_text_bytes(path.read_bytes())
        return json.loads(text)
    except Exception as exc:
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        quarantined=path.with_name(path.name+f".corrupt_{stamp}")
        try:
            path.replace(quarantined)
            detail=f"{path} -> {quarantined}"
        except Exception as move_exc:
            detail=i18n.t('p0.backup_failed', path=path, move_exc=move_exc)
        record_error(i18n.t('p0.json_corrupted', label=label),exc,detail)
        return default



def _native_crash_state_path() -> Path:
    return APP_HOME / "native_crash_import_state.json"


def _runtime_marker_path() -> Path:
    return APP_HOME / "runtime_state.json"


def _collect_native_crash_reports():
    """Import new macOS DiagnosticReports for this app into the normal error log."""
    if sys.platform != "darwin":
        return
    try:
        state = core.load_json(_native_crash_state_path(), {"seen": []})
        seen = set(state.get("seen") or []) if isinstance(state, dict) else set()
        report_dirs = [
            Path.home() / "Library" / "Logs" / "DiagnosticReports",
            Path.home() / "Library" / "Logs" / "DiagnosticReports" / "Retired",
        ]
        candidates = []
        for report_dir in report_dirs:
            if not report_dir.exists():
                continue
            for path in report_dir.glob("*"):
                if not path.is_file():
                    continue
                name = path.name.lower()
                if "paradox localization translator" not in name and "paradoxlocalizationtranslator" not in name:
                    continue
                if path.suffix.lower() not in {".ips", ".crash", ".diag"}:
                    continue
                try:
                    key = f"{path.resolve()}::{path.stat().st_mtime_ns}::{path.stat().st_size}"
                except Exception:
                    key = str(path)
                if key not in seen:
                    candidates.append((path, key))
        if not candidates:
            return
        archive_dir = ERROR_LOG_ROOT / "native_crash_reports"
        archive_dir.mkdir(parents=True, exist_ok=True)
        for path, key in sorted(candidates, key=lambda x: x[0].stat().st_mtime):
            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                summary = []
                for line in raw.splitlines():
                    stripped = line.strip()
                    if any(token in stripped for token in (
                        "Date/Time:", "Exception Type:", "Exception Codes:", "Termination Reason:",
                        "Triggered by Thread:", "Thread 0 Crashed", "GameControllerUI", "Tkapp_ThreadSend",
                    )):
                        summary.append(stripped)
                    if len(summary) >= 30:
                        break
                copied = archive_dir / path.name
                if copied.exists():
                    copied = archive_dir / f"{path.stem}_{int(time.time())}{path.suffix}"
                shutil.copy2(path, copied)
                record_error(
                    "macOS native crash imported",
                    detail=(
                        f"DiagnosticReport: {path}\nCopied: {copied}\n"
                        + ("\n".join(summary) if summary else i18n.t('p0.could_not_extract_a_crash'))
                    ),
                )
                seen.add(key)
            except Exception as exc:
                record_error("macOS native crash import failed", exc, detail=str(path))
        core.save_json(_native_crash_state_path(), {"seen": sorted(seen), "updated_at": datetime.now().isoformat(timespec="seconds")})
    except Exception as exc:
        record_error("macOS native crash scan", exc)


def _pid_is_running(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            # Avoid optional platform APIs here; stale markers are still harmless on Windows.
            return False
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except Exception:
        return False


def _mark_runtime_started():
    """Record a process marker so an unclean native termination is visible next launch."""
    try:
        previous = core.load_json(_runtime_marker_path(), {})
        previous_pid = previous.get("pid") if isinstance(previous, dict) else None
        if isinstance(previous, dict) and previous.get("active") and not _pid_is_running(previous_pid):
            record_error(
                "previous run ended unexpectedly",
                detail=(
                    i18n.t('p0.previous_start_pid_no_clean', started_at=previous.get('started_at','unknown'), pid=previous.get('pid','?'))
                ),
            )
        core.save_json(_runtime_marker_path(), {
            "active": True,
            "pid": os.getpid(),
            "app_version": APP_VERSION,
            "started_at": datetime.now().isoformat(timespec="seconds"),
        })
    except Exception as exc:
        record_error("runtime marker start", exc)


def _mark_runtime_clean_exit():
    try:
        core.save_json(_runtime_marker_path(), {
            "active": False,
            "pid": os.getpid(),
            "app_version": APP_VERSION,
            "clean_exit_at": datetime.now().isoformat(timespec="seconds"),
        })
    except Exception as exc:
        record_error("runtime marker clean exit", exc)


def _automatic_output_root() -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    return OUTPUT_ROOT


class App(BaseTk):
    def __init__(self):
        super().__init__()
        APP_HOME.mkdir(parents=True, exist_ok=True)
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
        _collect_native_crash_reports()
        _mark_runtime_started()
        self._fatal_log_handle = None
        try:
            fatal_path = ERROR_LOG_ROOT / f"fatal_{datetime.now().strftime('%Y%m%d')}.log"
            self._fatal_log_handle = fatal_path.open("a", encoding="utf-8")
            faulthandler.enable(file=self._fatal_log_handle, all_threads=True)
        except Exception as exc:
            record_error("faulthandler enable", exc)
        self.title(f"{APP_NAME} {APP_VERSION}")
        # v0.7.3: 機能増加後も起動直後から下部操作まで見えるよう、
        # 画面のほぼ全域を初期サイズとして使う。以前の 940px 高さ上限は撤廃。
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        initial_w = min(1480, max(1180, int(screen_w * 0.94)))
        # フルHDでも下部が欠けにくいよう、初期高さは少し控えめにする。
        # 追加の高さが必要な場合は各ペインの仕切りバーとウィンドウ拡大で対応する。
        initial_h = min(980, max(760, int(screen_h * 0.88)))
        initial_w = min(initial_w, max(960, screen_w - 36))
        initial_h = min(initial_h, max(700, screen_h - 96))
        self.geometry(f"{initial_w}x{initial_h}")
        self.minsize(1040, 700)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.events = queue.Queue()
        self.worker = None
        self.controller: core.TranslationController | None = None
        self.queue_items = []
        self.current_queue_index = -1
        self.review_source_entries = {}
        self.review_target_entries = {}
        self.review_issues = []
        self.review_issue_by_key = {}
        self.review_batch_contexts = []
        self.review_batch_errors = []
        self.review_last_qa_contexts = []
        self.review_last_qa_errors = []
        self.review_last_qa_repair_result = None
        self.review_tree_record_map = {}
        self.review_worker = None
        self.qa_repair_thread = None
        self.qa_repair_controller = None
        self._qa_repair_origin = None
        self.diff_load_worker = None
        self.differential_prepare_thread = None
        self.bulk_overwrite_thread = None
        self.single_overwrite_thread = None
        self.backup_restore_operation_thread = None
        self.data_root_move_thread = None
        self._differential_prepare_mode = None
        self._bulk_overwrite_queue_kind = None
        self._closing = False
        self._shutdown_wait_started = 0.0
        self._shutdown_prompted_at = 0.0
        self._normal_queue_controls = []
        self._chinese_queue_controls = []
        self._cross_queue_controls = []
        self._data_root_controls = []
        # 前回使用したLLM設定は通常セッションとは別に常時保存する。
        # APIキーだけは保存しない。
        # 以前から使っている人（設定ファイルがある人）は日本語の画面のまま。初めての人は OS の言語に合わせる。
        has_existing_settings = any((APP_HOME / name).exists() for name in
                                    ("app_preferences.json", "session.json", "workspace_state.json", "model_profiles.json"))
        self.app_preferences = load_persistent_json(APP_PREFS_PATH, {}, i18n.t('p0.app_settings'))
        if not isinstance(self.app_preferences, dict):
            self.app_preferences = {}
        self.ui_language = i18n.set_ui_language(
            i18n.initial_ui_language(self.app_preferences.get("ui_language"), has_existing_settings))
        self.ui_language_var = tk.StringVar(value=i18n.NATIVE_NAMES[self.ui_language])

        self.model_stats = load_persistent_json(STATS_PATH, {}, i18n.t('p0.model_statistics'))
        self.model_profiles = load_persistent_json(PROFILES_PATH, {}, i18n.t('p0.model_profiles'))
        self.benchmark_controller: core.TranslationController | None = None
        self.proofread_controller: core.TranslationController | None = None
        self.proofread_thread = None
        self.llm_busy_count = 0
        self.llm_active_ids = set()
        self.llm_busy_since = None
        self.llm_operation = ""
        self.llm_status_var = tk.StringVar(value=i18n.t('p0.llm_idle'))
        self.llm_detail_var = tk.StringVar(value=i18n.t('p0.llm_activity_appears_here_when'))
        self.monitor_llm_status_var = tk.StringVar(value=i18n.t('p0.discovery_llm_idle'))
        self.monitor_llm_detail_var = tk.StringVar(value=i18n.t('p0.discovery_and_review_of_untranslated'))
        self.monitor_llm_busy_since = None
        self.monitor_llm_active_ids = set()
        self.monitor_current_mod = ""
        self.dnd_status_var = tk.StringVar(value=i18n.t('p0.drag_and_drop_checking_initialization'))
        self.translation_llm_last_response = ""
        self.monitor_llm_last_response = ""
        self.translation_llm_response_meta = i18n.t('p0.waiting_for_a_response')
        self.monitor_llm_response_meta = i18n.t('p0.waiting_for_a_response')

        last_translation = self.app_preferences.get("translation_llm", {})
        last_monitor = self.app_preferences.get("monitor_llm", {})
        close_prefs = self.app_preferences.get("window_close", {}) if isinstance(self.app_preferences.get("window_close", {}), dict) else {}
        # ×ボタン時の既定動作。confirm / minimize / quit の3種類。
        # 保存は confirm / minimize / quit（古い版の日本語の値も読む）。選択欄には画面の言語の表示を出す。
        self.close_action_var = tk.StringVar(value=ui_status.close_action_label(ui_status.close_action_from_label(close_prefs.get("action", "confirm"))))

        self.provider_var = tk.StringVar(value=last_translation.get("provider", "Ollama"))
        self.api_key_var = tk.StringVar(value="")
        self._api_key_provider = self.provider_var.get(); self._api_keys_by_provider = {}
        self.url_var = tk.StringVar(value=last_translation.get("url") or core.default_url_for_provider(last_translation.get("provider", "Ollama")))
        self.model_var = tk.StringVar(value=last_translation.get("model") or core.DEFAULT_MODEL)
        self.preset_var = tk.StringVar(value="CK3")
        saved_target=str((self.app_preferences or {}).get("target_lang") or core.DEFAULT_TARGET_LANG) if isinstance(getattr(self,"app_preferences",None),dict) else core.DEFAULT_TARGET_LANG
        self.target_lang_var = tk.StringVar(value=saved_target if saved_target in core.TARGET_LANGUAGES else core.DEFAULT_TARGET_LANG)
        self.target_lang_choice_var = tk.StringVar(value=_target_lang_choice(self.target_lang_var.get()))
        self.batch_var = tk.IntVar(value=max(1, int(last_translation.get("batch", 40) or 40)))
        self.workers_var = tk.IntVar(value=max(1, int(last_translation.get("workers", 1) or 1)))
        self.performance_preset_var = tk.StringVar(value=ui_status.performance_preset_label("standard"))
        self.repair_var = tk.BooleanVar(value=True)
        self.normalize_spacing_var = tk.BooleanVar(value=bool(last_translation.get("normalize_spacing", True)))
        self.dual_var = tk.BooleanVar(value=False)
        self.autoqa_var = tk.BooleanVar(value=True)
        self.chinese_autoqa_var = tk.BooleanVar(value=bool(last_translation.get("chinese_autoqa", True)))
        self.glossary_path_var = tk.StringVar(value=str(DEFAULT_GLOSSARY))
        self.glossary_lang_var = tk.StringVar(value=_target_lang_choice(core.DEFAULT_TARGET_LANG))
        self.glossary_actual_path_var = tk.StringVar()
        self.auto_glossary_status_var = tk.StringVar(value=i18n.t('p0.auto_glossary_idle'))
        self.auto_glossary_controller = None
        self.auto_glossary_thread = None
        self.glossary_import_thread = None
        self.glossary_import_busy = False
        self.connection_var = tk.StringVar(value=i18n.t('p0.checking_llm_connection'))
        self.llm_preflight_thread = None
        self._llm_preflight_request = None
        self._llm_connection_alert_window = None
        self._llm_connection_alert_key = ""
        self.profile_var = tk.StringVar(value="")
        self.data_root_var = tk.StringVar(value=str(DATA_ROOT))
        self.progress_text = tk.StringVar(value=i18n.t('p0.idle'))
        self.review_src_var = tk.StringVar()
        self.review_dst_var = tk.StringVar()
        self.review_src_display_var = tk.StringVar()
        self.review_dst_display_var = tk.StringVar()
        self.qa_summary_var = tk.StringVar(value=i18n.t('p0.qa_not_run'))
        self.review_source_lang = "english"

        # Normal translation input/output display
        self.normal_input_var = tk.StringVar(value="")
        self.normal_output_var = tk.StringVar(value=str(OUTPUT_ROOT))
        self.normal_status_var = tk.StringVar(value=i18n.t('p0.add_yaml_files_or_a'))

        # Simplified Chinese basis translation
        self.chinese_input_var = tk.StringVar(value="")
        self.chinese_output_var = tk.StringVar(value=str(OUTPUT_ROOT / "中国語基準翻訳"))
        self.chinese_status_var = tk.StringVar(value=i18n.t('p0.select_simplified_chinese_yaml_files'))
        self.chinese_progress_var = tk.StringVar(value=i18n.t('p0.idle'))
        self.chinese_controller: core.TranslationController | None = None
        self.chinese_worker = None
        self.chinese_queue_items = []
        self.chinese_queue_index = -1

        # Difference inspector / translation search
        self.diff_src_var = tk.StringVar(value="")
        self.diff_dst_var = tk.StringVar(value="")
        self.diff_src_display_var = tk.StringVar(value="")
        self.diff_dst_display_var = tk.StringVar(value="")
        self.diff_summary_var = tk.StringVar(value=i18n.t('p0.differences_not_scanned'))
        self.diff_source_entries = {}
        self.diff_target_entries = {}
        self.diff_rows = []
        self.diff_row_by_key = {}
        self.diff_batch_contexts = []
        self.diff_tree_record_map = {}
        self.diff_controller: core.TranslationController | None = None
        self.diff_translate_thread = None
        self.diff_source_lang = "english"
        self.search_path_var = tk.StringVar(value="")  # legacy/internal compatibility; search is now game-scoped
        self.search_game_var = tk.StringVar(value="Crusader Kings III")
        self.search_query_var = tk.StringVar(value="")
        self.search_summary_var = tk.StringVar(value=i18n.t('p0.search_idle'))
        self.search_result_map = {}
        self.search_mod_map = {}
        self.search_selected_mod_paths = []
        self.search_thread = None
        self.search_generation = 0
        self.search_mod_refresh_generation = 0
        self.search_mod_status_var = tk.StringVar(value=i18n.t('p0.target_mods_not_loaded'))

        # Live untranslated-localization monitor
        self.monitor_path_var = tk.StringVar(value="")  # legacy / first monitor target
        self.monitor_target_paths = []
        self.monitor_target_summary_var = tk.StringVar(value=i18n.t('p0.monitor_targets_select_a_game'))
        self.monitor_interval_var = tk.IntVar(value=15)
        self.monitor_use_llm_var = tk.BooleanVar(value=True)
        self.monitor_check_translation_mods_var = tk.BooleanVar(value=True)
        self.monitor_provider_var = tk.StringVar(value=last_monitor.get("provider", "Ollama"))
        self.monitor_url_var = tk.StringVar(value=last_monitor.get("url") or core.default_url_for_provider(last_monitor.get("provider", "Ollama")))
        self.monitor_api_key_var = tk.StringVar(value="")
        self._monitor_api_key_provider = self.monitor_provider_var.get(); self._monitor_api_keys_by_provider = {}
        self.monitor_model_var = tk.StringVar(value=last_monitor.get("model", ""))
        self.monitor_connection_var = tk.StringVar(value=i18n.t('p0.monitor_llm_unchecked'))
        self.monitor_status_var = tk.StringVar(value=i18n.t('p0.monitor_stopped'))
        self.monitor_summary_var = tk.StringVar(value=i18n.t('p0.untranslated_candidates'))
        self.mod_status_summary_var = tk.StringVar(value=i18n.t('p0.scan_results'))
        self.mod_status_search_var = tk.StringVar(value="")
        self.mod_status_search_result_var = tk.StringVar(value="")
        self.mod_status_game_filter_var = tk.StringVar(value=i18n.t('p0.games_shown_all'))

        # Comprehensive localization diagnostics / repair
        self.diagnostic_summary_var = tk.StringVar(value=i18n.t('p0.diagnostics_idle'))
        self.diagnostic_target_var = tk.StringVar(value=i18n.t('p0.target_mods_from_translation_status'))
        self.diagnostic_results = []
        self.diagnostic_result_map = {}
        self.diagnostic_thread = None
        self.diagnostic_generation = 0
        self.diagnostic_conflict_choices = {}
        self.diagnostic_relation_choices = {}
        self.diagnostic_last_analyses = []

        # Backup restore / rollback
        self.backup_restore_entries = []
        self.backup_restore_entry_map = {}
        self.backup_restore_summary_var = tk.StringVar(value=i18n.t('p0.backups_not_loaded'))
        self.backup_restore_detail_var = tk.StringVar(value=i18n.t('p0.select_a_backup_from_the'))
        self.backup_restore_game_var = tk.StringVar(value=i18n.t("p0.filter.all_games"))
        self.backup_restore_mod_var = tk.StringVar(value=i18n.t("p0.filter.all_mods"))
        self.backup_restore_search_var = tk.StringVar(value="")
        # v0.11.56: restore-target resolution may need a large persisted Translation Status
        # snapshot. Keep one in-memory copy per refresh instead of reparsing the same JSON
        # once for every backup entry.
        self._restore_status_snapshot_cache = None
        self._restore_status_rows_cache = None
        self.backup_restore_refresh_thread = None
        self.backup_restore_refresh_generation = 0
        self.backup_restore_refresh_pending = False
        self.status_restore_thread = None
        self._translation_status_save_after_id = None
        self._translation_status_pending_reason = ""
        self.diagnostic_restore_thread = None
        self.judgement_log_thread = None
        self._judgement_log_window = None
        self._status_search_after_id = None

        self.mod_research_results = []
        self.mod_research_thread = None
        self.mod_research_stop_event = threading.Event()
        self.monitor_thread = None
        self.monitor_stop_event = threading.Event()
        self.monitor_force_event = threading.Event()
        self.monitor_llm_controller: core.TranslationController | None = None
        self.monitor_candidates = []
        self.monitor_snapshot = {}
        self.detected_mod_locations = []
        self.mod_discovery_status_var = tk.StringVar(value=i18n.t('p0.game_mod_locations_not_detected'))
        self.discovery_multi_select_var = tk.BooleanVar(value=False)
        self.mod_status_cache_lock = threading.Lock()
        # v0.11.58: do not decode the potentially large status cache while Tk is
        # still constructing the first window. _restore_cached_mod_status() loads it
        # on a worker after the GUI has become responsive.
        self.mod_status_cache = {"version": MOD_STATUS_CACHE_VERSION, "items": {}}
        # v0.11.31 migrates the first-seen role cache without discarding it.
        # The role cache is safety data (for example, a source Mod that originally
        # had no Japanese YAML must stay a source Mod after we generate Japanese).
        # False *relationships* live in the Translation Status/workspace caches and
        # are reset separately below.
        _classification = load_persistent_json(MOD_CLASSIFICATION_CACHE_PATH, {}, i18n.t('p0.mod_classification_cache'))
        if not isinstance(_classification, dict):
            _classification = {}
        self.mod_classification_cache = {
            "schema": 2,
            "migrated_for_version": APP_VERSION,
            "mods": dict(_classification.get("mods") or {}),
        }
        if _classification.get("updated_at"):
            self.mod_classification_cache["previous_updated_at"] = _classification.get("updated_at")
        try:
            core.save_json(MOD_CLASSIFICATION_CACHE_PATH, self.mod_classification_cache)
        except Exception as exc:
            record_error(i18n.t('p0.initial_mod_classification_cache_migration'), exc)
        self.mod_classification_lock = threading.Lock()
        _relation_overrides = load_persistent_json(MOD_RELATION_OVERRIDES_PATH, {"schema": 1, "mods": {}}, i18n.t('p0.mod_linking_settings'))
        if not isinstance(_relation_overrides, dict):
            _relation_overrides = {"schema": 1, "mods": {}}
        self.mod_relation_overrides = {
            "schema": 1,
            "mods": dict(_relation_overrides.get("mods") or {}),
            "languages": dict(_relation_overrides.get("languages") or {}),
            "updated_at": _relation_overrides.get("updated_at", ""),
        }
        self.mod_relation_override_lock = threading.Lock()
        self._restore_shared_mod_state_cache()
        # Cross-version workspace persistence. This is broader than the active
        # translation session and stores the last visible/working state of every
        # major tab. API keys are intentionally excluded.
        self.workspace_revision = 0
        self._workspace_restore_data = {}
        self._workspace_selected_location_paths = []
        self._workspace_save_in_progress = False
        self.report_callback_exception = self._tk_callback_exception
        sys.excepthook = self._sys_excepthook
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._thread_excepthook

        self._build_ui()
        for actual, display in ((self.review_src_var,self.review_src_display_var),(self.review_dst_var,self.review_dst_display_var),(self.diff_src_var,self.diff_src_display_var),(self.diff_dst_var,self.diff_dst_display_var)):
            actual.trace_add("write", lambda *_args, a=actual, d=display: d.set(self._localization_display_path(a.get())))
            display.set(self._localization_display_path(actual.get()))
        self._restore_workspace_state()
        self.after(100, self._poll_events)
        self.after(300, self.refresh_models)
        self.after(450, self.refresh_monitor_models)
        self.after(550, self._offer_restore_session)
        self.after(650, self._restore_cached_mod_status)
        self.after(760, self._restore_diagnostic_state)
        self.after(900, self._refresh_backup_restore_entries)
        self.after(750, self.discover_mod_locations)
        self.after(15000, self._workspace_autosave_tick)

    # ---------------- UI / operation state ----------------
    @staticmethod
    def _thread_is_active(thread):
        return bool(thread and thread.is_alive())

    @staticmethod
    def _operation_pending(thread):
        """Remain busy until the main thread consumes the worker completion event."""
        return thread is not None

    def _normal_queue_locked(self):
        differential = self._operation_pending(self.differential_prepare_thread) and self._differential_prepare_mode == "normal"
        overwrite = self._operation_pending(self.bulk_overwrite_thread) and self._bulk_overwrite_queue_kind in {None, "normal"}
        shared_write = any(self._operation_pending(x) for x in (
            self.data_root_move_thread,self.backup_restore_operation_thread,self.diagnostic_thread,getattr(self,"qa_repair_thread",None),
            getattr(self,"llm_preflight_thread",None),
        ))
        return bool(self._closing or shared_write or self._operation_pending(self.worker) or differential or overwrite or self._operation_pending(self.single_overwrite_thread))

    def _chinese_queue_locked(self):
        differential = self._operation_pending(self.differential_prepare_thread) and self._differential_prepare_mode == "chinese"
        overwrite = self._operation_pending(self.bulk_overwrite_thread) and self._bulk_overwrite_queue_kind in {None, "chinese"}
        shared_write = any(self._operation_pending(x) for x in (
            self.data_root_move_thread,self.backup_restore_operation_thread,self.diagnostic_thread,getattr(self,"qa_repair_thread",None),
            getattr(self,"llm_preflight_thread",None),
        ))
        return bool(self._closing or shared_write or self._operation_pending(self.chinese_worker) or differential or overwrite or self._operation_pending(self.single_overwrite_thread))

    def _active_file_operation_names(self):
        checks = (
            (i18n.t('p0.standard_translation'), self.worker),
            ("中国語基準翻訳", self.chinese_worker),
            (i18n.t('p0.preparing_missing_only_translation'), self.differential_prepare_thread),
            (i18n.t('p0.single_overwrite'), self.single_overwrite_thread),
            (i18n.t('p0.bulk_overwrite'), self.bulk_overwrite_thread),
            (i18n.t('p0.restore_backup'), self.backup_restore_operation_thread),
            ("保存場所コピー", self.data_root_move_thread),
            (i18n.t('p0.full_diagnostics_and_repair'), self.diagnostic_thread),
            (i18n.t('p0.qa_and_auto_fix'), getattr(self,"qa_repair_thread",None)),
            (i18n.t('p0.llm_connection_check'), getattr(self,"llm_preflight_thread",None)),
            (i18n.t('p0.import_glossary'), self.glossary_import_thread),
        )
        return [name for name, thread in checks if self._operation_pending(thread)]

    @staticmethod
    def _set_control_group_state(controls, disabled):
        state = "disabled" if disabled else "normal"
        for widget in controls:
            try:
                widget.configure(state=state)
            except (tk.TclError, AttributeError):
                try:
                    widget.state(["disabled"] if disabled else ["!disabled"])
                except (tk.TclError, AttributeError):
                    pass

    def _refresh_operation_states(self):
        """Keep unavailable operations visibly greyed out while workers own their data.

        0.1秒ごとに呼ばれるので、状態が変わっていなければ画面の設定し直しを省く
        （待機中の CPU 使用を抑える）。ほかの場所で直接変えた状態も戻るよう、1秒に1回は必ず設定し直す。
        """
        normal_locked = self._normal_queue_locked()
        chinese_locked = self._chinese_queue_locked()
        normal_can_control = self._thread_is_active(self.worker) and not (self.controller and self.controller.stop_event.is_set())
        chinese_can_control = self._thread_is_active(self.chinese_worker) and not (self.chinese_controller and self.chinese_controller.stop_event.is_set())
        data_root_locked = bool(self._closing or self._active_file_operation_names())
        signature = (normal_locked, chinese_locked, normal_can_control, chinese_can_control, data_root_locked,
                     len(self._normal_queue_controls), len(self._chinese_queue_controls),
                     len(self._cross_queue_controls), len(self._data_root_controls),
                     id(getattr(self, "review_batch_contexts", None)), id(getattr(self, "review_last_qa_contexts", None)))
        now = time.monotonic()
        if (signature == getattr(self, "_operation_state_signature", None)
                and now - getattr(self, "_operation_state_refreshed_at", 0.0) < 1.0):
            return
        self._operation_state_signature = signature
        self._operation_state_refreshed_at = now
        self._set_control_group_state(self._normal_queue_controls, normal_locked)
        self._set_control_group_state(self._chinese_queue_controls, chinese_locked)
        if not chinese_locked and hasattr(self, "chinese_target_combo"):
            self.chinese_target_combo.configure(state="readonly")
        self._set_control_group_state(self._cross_queue_controls, normal_locked or chinese_locked)

        if hasattr(self, "start_btn"):
            self.start_btn.configure(state="disabled" if normal_locked else "normal")
        if hasattr(self, "pause_btn"):
            self.pause_btn.configure(state="normal" if normal_can_control else "disabled")
        if hasattr(self, "stop_btn"):
            self.stop_btn.configure(state="normal" if normal_can_control else "disabled")
        if hasattr(self, "chinese_start_btn"):
            self.chinese_start_btn.configure(state="disabled" if chinese_locked else "normal")
        if hasattr(self, "chinese_pause_btn"):
            self.chinese_pause_btn.configure(state="normal" if chinese_can_control else "disabled")
        if hasattr(self, "chinese_stop_btn"):
            self.chinese_stop_btn.configure(state="normal" if chinese_can_control else "disabled")

        self._set_control_group_state(self._data_root_controls, data_root_locked)
        if hasattr(self,"review_auto_repair_btn"):
            self._set_review_auto_repair_enabled(
                not data_root_locked and _qa_contexts_have_repairable_errors(
                    self.review_batch_contexts or self.review_last_qa_contexts))

    def _disable_all_interactive_controls(self):
        """Grey out the complete UI after final shutdown has started."""
        interactive=(ttk.Button,ttk.Menubutton,ttk.Checkbutton,ttk.Combobox,ttk.Entry,ttk.Treeview,tk.Button,tk.Entry,tk.Listbox)
        stack=list(self.winfo_children())
        while stack:
            widget=stack.pop()
            try: stack.extend(widget.winfo_children())
            except (tk.TclError,AttributeError): pass
            if isinstance(widget,interactive):
                try: widget.configure(state="disabled")
                except (tk.TclError,AttributeError):
                    try: widget.state(["disabled"])
                    except (tk.TclError,AttributeError): pass

    def _build_ui(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass

        top = ttk.Frame(self, padding=(12, 10, 12, 4)); top.pack(fill="x")
        ttk.Label(top, text=APP_NAME, font=("", 20, "bold")).pack(side="left")
        ttk.Label(top, text=f"v{APP_VERSION}").pack(side="left", padx=(8, 0), pady=(8, 0))
        ttk.Label(top, textvariable=self.connection_var).pack(side="right")

        # v0.8.8: 上部ステータスも縦積みをやめ、左右2ブロックにして高さを節約。
        llm_row = ttk.Frame(self, padding=(10,2,10,2)); llm_row.pack(fill="x")
        self.llm_banner = tk.Frame(llm_row, bg="#e5e7eb", padx=9, pady=5)
        self.llm_banner.pack(side="left", fill="x", expand=True, padx=(0,4))
        self.llm_status_label = tk.Label(self.llm_banner, textvariable=self.llm_status_var, bg="#e5e7eb", fg="#222222", font=("", 11, "bold"))
        self.llm_status_label.pack(side="left")
        self.llm_detail_label = tk.Label(self.llm_banner, textvariable=self.llm_detail_var, bg="#e5e7eb", fg="#444444")
        self.llm_detail_label.pack(side="left", padx=(8,0))
        self.llm_stop_btn = ttk.Button(self.llm_banner, text=i18n.t('p0.stop_translation_llm'), command=self.stop_current_llm, state="disabled")
        self.llm_stop_btn.pack(side="right")

        self.monitor_llm_banner = tk.Frame(llm_row, bg="#dbeafe", padx=9, pady=5)
        self.monitor_llm_banner.pack(side="left", fill="x", expand=True, padx=(4,0))
        self.monitor_llm_status_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_status_var, bg="#dbeafe", fg="#1e3a8a", font=("", 10, "bold"))
        self.monitor_llm_status_label.pack(side="left")
        self.monitor_llm_detail_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_detail_var, bg="#dbeafe", fg="#1e3a8a")
        self.monitor_llm_detail_label.pack(side="left", padx=(8,0))
        self.monitor_llm_stop_btn = ttk.Button(self.monitor_llm_banner, text=i18n.t('p0.stop_discovery_llm'), command=self.stop_monitor_llm, state="disabled")
        self.monitor_llm_stop_btn.pack(side="right")

        # 実際にLLMから返ってきた最新応答を、そのまま確認するための読み取り専用欄。
        # 翻訳用と探索用を分離し、処理が本当に進んでいるか目視できるようにする。
        response_row = ttk.Frame(self, padding=(10, 0, 10, 2))
        response_row.pack(fill="x")
        tr_frame = ttk.LabelFrame(response_row, text=i18n.t('p0.latest_translation_llm_response_read'), padding=5)
        tr_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tr_head = ttk.Frame(tr_frame); tr_head.pack(fill="x")
        self.translation_response_meta_var = tk.StringVar(value=i18n.t('p0.waiting_for_a_response'))
        ttk.Label(tr_head, textvariable=self.translation_response_meta_var, foreground="#555").pack(side="left")
        ttk.Button(tr_head, text=i18n.t('p0.open_full_response'), command=lambda:self._open_llm_response_window(False)).pack(side="right")
        ttk.Button(tr_head, text=i18n.t('p0.clear'), command=lambda:self._clear_llm_response(False)).pack(side="right", padx=(0,5))
        self.translation_response_text = tk.Text(tr_frame, height=2, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.translation_response_text.pack(fill="x", pady=(4,0))

        mon_frame = ttk.LabelFrame(response_row, text=i18n.t('p0.latest_discovery_llm_response_read'), padding=5)
        mon_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        mon_head = ttk.Frame(mon_frame); mon_head.pack(fill="x")
        self.monitor_response_meta_var = tk.StringVar(value=i18n.t('p0.waiting_for_a_response'))
        ttk.Label(mon_head, textvariable=self.monitor_response_meta_var, foreground="#555").pack(side="left")
        ttk.Button(mon_head, text=i18n.t('p0.open_full_response'), command=lambda:self._open_llm_response_window(True)).pack(side="right")
        ttk.Button(mon_head, text=i18n.t('p0.clear'), command=lambda:self._clear_llm_response(True)).pack(side="right", padx=(0,5))
        self.monitor_response_text = tk.Text(mon_frame, height=2, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.monitor_response_text.pack(fill="x", pady=(4,0))

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=5)
        self.notebook = nb
        self.tab_translate = ttk.Frame(nb, padding=10)
        self.tab_chinese = ttk.Frame(nb, padding=10)
        self.tab_review = ttk.Frame(nb, padding=10)
        self.tab_diff = ttk.Frame(nb, padding=10)
        self.tab_search = ttk.Frame(nb, padding=10)
        self.tab_glossary = ttk.Frame(nb, padding=10)
        self.tab_models = ttk.Frame(nb, padding=10)
        self.tab_monitor = ttk.Frame(nb, padding=10)
        self.tab_status = ttk.Frame(nb, padding=10)
        self.tab_diagnostic = ttk.Frame(nb, padding=10)
        self.tab_backup_restore = ttk.Frame(nb, padding=10)
        self.tab_settings = ttk.Frame(nb, padding=10)
        self.tab_help = ttk.Frame(nb, padding=10)
        nb.add(self.tab_translate, text=i18n.t('p0.translation_queue'))
        nb.add(self.tab_chinese, text=i18n.t('p0.tab.chinese'))
        nb.add(self.tab_review, text=i18n.t('p0.qa_comparison_editor'))
        nb.add(self.tab_diff, text=i18n.t('p0.difference_scan'))
        nb.add(self.tab_search, text=i18n.t('p0.translation_search'))
        nb.add(self.tab_glossary, text=i18n.t('p0.glossary'))
        nb.add(self.tab_models, text=i18n.t('p0.model_connection'))
        nb.add(self.tab_monitor, text=i18n.t('p0.untranslated_monitor'))
        nb.add(self.tab_status, text=i18n.t('p0.translation_status'))
        nb.add(self.tab_diagnostic, text=i18n.t('p0.tab.diagnostic'))
        nb.add(self.tab_backup_restore, text=i18n.t('p0.restore_backup'))
        nb.add(self.tab_settings, text=i18n.t('p0.tab.settings'))
        nb.add(self.tab_help, text=i18n.t('p0.help'))
        self._build_translate_tab()
        self._build_chinese_tab()
        self._build_review_tab()
        self._build_diff_tab()
        self._build_search_tab()
        self._build_glossary_tab()
        self._build_models_tab()
        self._build_monitor_tab()
        self._build_status_tab()
        self._build_diagnostic_tab()
        self._build_backup_restore_tab()
        self._build_settings_tab()
        self._build_help_tab()

    def _tree_sort_value(self, value):
        """Treeview並び替え用。数字は数値、それ以外は文字列として比較する。"""
        text = "" if value is None else str(value).strip()
        m = re.match(r"^[\s]*([+-]?(?:\d+(?:,\d{3})*|\d*)(?:\.\d+)?)", text)
        if m and m.group(1) not in ("", "+", "-", "."):
            try:
                return (0, float(m.group(1).replace(",", "")), text.casefold())
            except ValueError:
                pass
        return (1, text.casefold())

    def _enable_tree_sort(self, tree, columns=None, recursive=False):
        """列見出しクリックで昇順/降順ソートを有効化する。"""
        if not hasattr(self, "_tree_sort_states"):
            self._tree_sort_states = {}
        if not hasattr(self, "_tree_heading_labels"):
            self._tree_heading_labels = {}
        if columns is None:
            columns = list(tree.cget("columns"))
        columns = list(columns)
        if tree.cget("show") in ("tree", "tree headings") and "#0" not in columns:
            columns = ["#0"] + columns
        for col in columns:
            try:
                label = tree.heading(col, "text")
            except tk.TclError:
                continue
            self._tree_heading_labels[(str(tree), col)] = label
            tree.heading(col, command=lambda c=col, tr=tree, rec=recursive: self._sort_treeview(tr, c, rec))

    def _sort_treeview(self, tree, column, recursive=False):
        key = (str(tree), column)
        # 最初のクリックは昇順、2回目は降順。
        descending = self._tree_sort_states.get(key, False)
        self._tree_sort_states[key] = not descending

        def cell(iid):
            return tree.item(iid, "text") if column == "#0" else tree.set(iid, column)

        def sort_children(parent=""):
            items = list(tree.get_children(parent))
            items.sort(key=lambda iid: self._tree_sort_value(cell(iid)), reverse=descending)
            for index, iid in enumerate(items):
                tree.move(iid, parent, index)
                if recursive:
                    sort_children(iid)

        sort_children("")
        for (tree_id, col), label in list(self._tree_heading_labels.items()):
            if tree_id != str(tree):
                continue
            marker = " ▼" if (col == column and descending) else (" ▲" if col == column else "")
            try:
                tree.heading(col, text=label + marker)
            except tk.TclError:
                pass

    def _enable_ctrl_multiselect(self, widget, max_items=None):
        """複数選択操作を全OSで Ctrl+クリック に統一する。

        Tkの標準extended選択はOSごとに修飾キーの慣習が異なるため、
        Ctrl+クリックを明示的にトグル操作として登録する。通常クリックは
        従来どおり単一選択として動作する。
        """
        def on_ctrl_click(event):
            try:
                if isinstance(widget, ttk.Treeview):
                    iid = widget.identify_row(event.y)
                    if not iid:
                        return "break"
                    selected = list(widget.selection())
                    if iid in selected:
                        widget.selection_remove(iid)
                    else:
                        if max_items is not None and len(selected) >= max_items:
                            self.bell()
                            return "break"
                        widget.selection_add(iid)
                    widget.focus(iid)
                    widget.see(iid)
                    widget.event_generate("<<TreeviewSelect>>")
                    return "break"
                if isinstance(widget, tk.Listbox):
                    idx = widget.nearest(event.y)
                    if idx < 0 or idx >= widget.size():
                        return "break"
                    selected = set(widget.curselection())
                    if idx in selected:
                        widget.selection_clear(idx)
                    else:
                        if max_items is not None and len(selected) >= max_items:
                            self.bell()
                            return "break"
                        widget.selection_set(idx)
                    widget.activate(idx)
                    widget.event_generate("<<ListboxSelect>>")
                    return "break"
            except Exception as exc:
                record_error(i18n.t('p0.ctrl_multi_select'), exc)
            return None

        widget.bind("<Control-Button-1>", on_ctrl_click, add="+")

    def _build_translate_tab(self):
        t = self.tab_translate

        # 通常翻訳も中国語基準翻訳と同じ左右2ブロック構成に統一する。
        main=ttk.Panedwindow(t,orient="horizontal"); main.pack(fill="both",expand=True)
        left=ttk.Frame(main,padding=(0,0,6,0)); right=ttk.Frame(main,padding=(6,0,0,0))
        main.add(left,weight=2); main.add(right,weight=3)

        intro=ttk.LabelFrame(left,text=i18n.t('u1.normal_translation'),padding=9); intro.pack(fill="x")
        ttk.Label(intro,text=(i18n.t('u1.intro', target_name=i18n.t("lang." + _current_target_lang(self)))),
                  wraplength=430,foreground="#333",justify="left").pack(fill="x")

        langbox=ttk.LabelFrame(left,text=i18n.t('u1.target_language'),padding=9); langbox.pack(fill="x",pady=(5,0)); langbox.columnconfigure(1,weight=1)
        ttk.Label(langbox,text=i18n.t('u1.target')).grid(row=0,column=0,sticky="w")
        self.target_lang_combo=ttk.Combobox(langbox,textvariable=self.target_lang_choice_var,state="readonly",width=26,
                                            values=[_target_lang_choice(x) for x in core.TARGET_LANGUAGES])
        self.target_lang_combo.grid(row=0,column=1,sticky="w",padx=(6,0))
        self.target_lang_combo.bind("<<ComboboxSelected>>",lambda _e:self._set_target_lang(_target_lang_from_choice(self.target_lang_choice_var.get())))
        ttk.Label(langbox,text=i18n.t('u1.target_note'),foreground="#555",wraplength=430,justify="left").grid(row=1,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Label(langbox,text=target_lang_note(),foreground="#8a5a00",wraplength=430,justify="left").grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,0))

        src=ttk.LabelFrame(left,text=i18n.t('u1.input_output'),padding=9); src.pack(fill="x",pady=(5,0)); src.columnconfigure(0,weight=1)
        ttk.Label(src,text=i18n.t('u1.input_folder')).grid(row=0,column=0,sticky="w")
        self.normal_input_entry=ttk.Entry(src,textvariable=self.normal_input_var,state="readonly")
        self.normal_input_entry.grid(row=1,column=0,sticky="ew",pady=(3,0))
        pickbar=ttk.Frame(src); pickbar.grid(row=2,column=0,sticky="ew",pady=(5,0))
        normal_add_menu=tk.Menu(pickbar,tearoff=False)
        normal_add_menu.add_command(label=i18n.t('u1.add_yaml'),command=self.add_files)
        normal_add_menu.add_command(label=i18n.t('u1.add_folder'),command=self.add_folder)
        self.add_menu_button=ttk.Menubutton(pickbar,text=i18n.t('u1.add'),menu=normal_add_menu)
        self.add_menu_button.pack(side="left")
        ttk.Label(pickbar,text=i18n.t('u1.add_note'),foreground="#666").pack(side="left",padx=(8,0))
        ttk.Label(src,textvariable=self.normal_status_var,foreground="#555",wraplength=430,justify="left").grid(row=3,column=0,sticky="w",pady=(4,0))
        ttk.Separator(src,orient="horizontal").grid(row=4,column=0,sticky="ew",pady=5)
        ttk.Label(src,text=i18n.t('u1.output_root')).grid(row=5,column=0,sticky="w")
        self.normal_output_entry=ttk.Entry(src,textvariable=self.normal_output_var)
        self.normal_output_entry.grid(row=6,column=0,sticky="ew",pady=(3,0))
        outbar=ttk.Frame(src); outbar.grid(row=7,column=0,sticky="ew",pady=(5,0))
        self.normal_pick_output_btn=ttk.Button(outbar,text=i18n.t('u1.select'),command=self.pick_normal_output)
        self.normal_pick_output_btn.pack(side="left")
        ttk.Button(outbar,text=i18n.t('u1.open'),command=lambda:self._open_path(Path(self.normal_output_var.get()))).pack(side="left",padx=(5,0))

        settings=ttk.LabelFrame(left,text=i18n.t('u1.shared_models'),padding=9); settings.pack(fill="x",pady=(5,0))
        ttk.Label(settings,text=i18n.t('u1.shared_models_note'),wraplength=430,justify="left").pack(anchor="w")
        ttk.Button(settings,text=i18n.t('u1.open_models'),command=lambda:self.notebook.select(self.tab_models)).pack(anchor="w",pady=(6,0))
        ttk.Checkbutton(settings,text=i18n.t('u1.auto_qa'),variable=self.autoqa_var,command=self._save_llm_preferences).pack(anchor="w",pady=(7,0))
        ttk.Label(settings,text=i18n.t('u1.qa_note'),foreground="#555",wraplength=430,justify="left").pack(anchor="w",pady=(5,0))

        qbox=ttk.LabelFrame(right,text=i18n.t('u1.normal_queue'),padding=8); qbox.pack(fill="both",expand=True)
        qbar=ttk.Frame(qbox); qbar.pack(fill="x",pady=(0,5))
        self.normal_remove_btn=ttk.Button(qbar,text=i18n.t('u1.remove_selected'),command=self.remove_queue); self.normal_remove_btn.pack(side="left")
        self.normal_clear_btn=ttk.Button(qbar,text=i18n.t('u1.clear_queue'),command=self.clear_queue); self.normal_clear_btn.pack(side="left",padx=(5,0))
        self.normal_change_output_btn=ttk.Button(qbar,text=i18n.t('u1.change_output'),command=self.change_output); self.normal_change_output_btn.pack(side="left",padx=(10,0))
        ttk.Button(qbar,text=i18n.t('u1.view_cache'),command=self.view_selected_cache).pack(side="left",padx=(5,0))
        self.normal_import_cache_btn=ttk.Button(qbar,text=i18n.t('u1.add_cache'),command=self.import_cache_to_selected); self.normal_import_cache_btn.pack(side="left",padx=(5,0))

        qbar2=ttk.Frame(qbox); qbar2.pack(fill="x",pady=(0,5))
        self.normal_overwrite_btn=ttk.Button(qbar2,text=i18n.t('u1.overwrite_selected'),command=self.overwrite_selected_translation_to_mod); self.normal_overwrite_btn.pack(side="left")
        self.normal_qa_btn=ttk.Button(qbar2,text=i18n.t('u1.qa_selected'),command=self.run_selected_translation_qa); self.normal_qa_btn.pack(side="left",padx=(6,0))
        self.normal_glossary_btn=ttk.Button(qbar2,text=i18n.t('u1.create_glossary'),command=lambda:self.start_auto_glossary_generation("normal")); self.normal_glossary_btn.pack(side="left",padx=(6,0))
        self.normal_send_qa_btn=ttk.Button(qbar2,text=i18n.t('u1.open_qa'),command=lambda:self._send_pair_to_qa_or_diff("normal","review")); self.normal_send_qa_btn.pack(side="left",padx=(6,0))
        self.normal_send_diff_btn=ttk.Button(qbar2,text=i18n.t('u1.open_diff'),command=lambda:self._send_pair_to_qa_or_diff("normal","diff")); self.normal_send_diff_btn.pack(side="left",padx=(6,0))
        self.normal_transfer_btn=ttk.Button(qbar,text=i18n.t('u1.transfer_chinese'),command=lambda:self.transfer_selected_queue_to_opposite("normal",False)); self.normal_transfer_btn.pack(side="left",padx=(10,0))
        self.normal_transfer_missing_btn=ttk.Button(qbar2,text=i18n.t('u1.queue_chinese_missing'),command=lambda:self.transfer_selected_queue_to_opposite("normal",True)); self.normal_transfer_missing_btn.pack(side="left",padx=(6,0))
        ttk.Label(qbox,text=i18n.t('u1.overwrite_note'),foreground="#8a5a00",wraplength=900,justify="left").pack(fill="x",anchor="w",pady=(0,5))

        self.drop_hint=ttk.Label(qbox,textvariable=self.dnd_status_var,foreground="#666")
        self.drop_hint.pack(fill="x",pady=(0,5))
        cols=("mod","input","output","status")
        queue_table=ttk.Frame(qbox)
        queue_table.pack(fill="both",expand=True)
        self.queue_tree=ttk.Treeview(queue_table,columns=cols,show="headings",height=10,selectmode="extended")
        for c,txt,w in (("mod",i18n.t('u1.item'),240),("input",i18n.t('u1.source_localization'),430),("output",i18n.t('u1.output'),390),("status",i18n.t('u1.status'),230)):
            self.queue_tree.heading(c,text=txt)
            self.queue_tree.column(c,width=w,minwidth=120,stretch=False,anchor="center" if c=="status" else "w")
        self._enable_ctrl_multiselect(self.queue_tree)
        self._enable_tree_sort(self.queue_tree)
        sy=ttk.Scrollbar(queue_table,orient="vertical",command=self.queue_tree.yview)
        sx=ttk.Scrollbar(queue_table,orient="horizontal",command=self.queue_tree.xview)
        self.queue_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        sx.pack(side="bottom",fill="x")
        sy.pack(side="right",fill="y")
        self.queue_tree.pack(side="left",fill="both",expand=True)
        self._normal_queue_controls=[
            self.add_menu_button,self.normal_output_entry,self.normal_pick_output_btn,
            self.normal_remove_btn,self.normal_clear_btn,self.normal_change_output_btn,self.normal_import_cache_btn,
            self.normal_overwrite_btn,self.normal_qa_btn,self.normal_glossary_btn,self.normal_send_qa_btn,
            self.normal_send_diff_btn,self.normal_transfer_btn,self.normal_transfer_missing_btn,self.queue_tree,
        ]
        self._cross_queue_controls.extend([self.normal_transfer_btn,self.normal_transfer_missing_btn])

        if DND_AVAILABLE:
            try:
                self._register_dnd_widgets([t,src,self.normal_input_entry,qbox,self.queue_tree],self.on_drop_paths)
                self.dnd_status_var.set(i18n.t('u1.dnd_enabled'))
            except Exception as e:
                self.dnd_status_var.set(i18n.t('u1.dnd_error', error=e))
                self._record_error(i18n.t('u1.dnd_init'),e)
        else:
            self.dnd_status_var.set(i18n.t('u1.dnd_disabled'))

        actions=ttk.Frame(right); actions.pack(fill="x",pady=(7,0))
        self.start_btn=ttk.Button(actions,text=i18n.t('u1.start_translation'),command=self.start_queue); self.start_btn.pack(side="left")
        self.pause_btn=ttk.Button(actions,text=i18n.t('u1.pause'),command=self.toggle_pause,state="disabled"); self.pause_btn.pack(side="left",padx=(6,0))
        self.stop_btn=ttk.Button(actions,text=i18n.t('u1.save_stop'),command=self.save_and_stop,state="disabled"); self.stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(actions,text=i18n.t('u1.open_output'),command=self.open_selected_output).pack(side="left",padx=(6,0))
        ttk.Label(actions,textvariable=self.progress_text).pack(side="right")
        self.progress=ttk.Progressbar(right,mode="determinate",maximum=100); self.progress.pack(fill="x",pady=(6,7))

        logbox=ttk.LabelFrame(right,text=i18n.t('u1.normal_log'),padding=6); logbox.pack(fill="both",expand=True)
        lbar=ttk.Frame(logbox); lbar.pack(fill="x",pady=(0,4))
        ttk.Button(lbar,text=i18n.t('u1.open_errors'),command=lambda:self._open_path(LOG_ROOT)).pack(side="left")
        ttk.Button(lbar,text=i18n.t('u1.collect_diagnostics'),command=self.collect_error_logs).pack(side="left",padx=(5,0))
        self.log=tk.Text(logbox,height=6,wrap="word",state="disabled")
        lsy=ttk.Scrollbar(logbox,command=self.log.yview); self.log.configure(yscrollcommand=lsy.set)
        self.log.pack(side="left",fill="both",expand=True); lsy.pack(side="right",fill="y")

    def _build_chinese_tab(self):
        t = self.tab_chinese
        self.chinese_target_lang_var = tk.StringVar(value=core.DEFAULT_TARGET_LANG)
        self.chinese_target_display_var = tk.StringVar(value=i18n.t("lang." + core.DEFAULT_TARGET_LANG))

        # 中国語基準翻訳は基準デザインとして維持し、入力追加だけ単純化する。
        main=ttk.Panedwindow(t,orient="horizontal"); main.pack(fill="both",expand=True)
        left=ttk.Frame(main,padding=(0,0,6,0)); right=ttk.Frame(main,padding=(6,0,0,0))
        main.add(left,weight=2); main.add(right,weight=3)

        intro=ttk.LabelFrame(left,text=i18n.t("u2.intro_title", target_name=i18n.t("lang." + core.DEFAULT_TARGET_LANG)),padding=9); intro.pack(fill="x")
        self.chinese_intro_frame = intro
        self.chinese_intro_label = ttk.Label(intro,text=(i18n.t("u2.intro_description", target_name=i18n.t("lang." + core.DEFAULT_TARGET_LANG))),
                  wraplength=430,foreground="#333",justify="left")
        self.chinese_intro_label.pack(fill="x")
        ttk.Label(intro, text=i18n.t("u2.target_language")).pack(anchor="w")
        self.chinese_target_combo = ttk.Combobox(intro, state="readonly", textvariable=self.chinese_target_display_var,
                                                values=[i18n.t("lang." + language) for language in core.TARGET_LANGUAGES])
        self.chinese_target_combo.pack(fill="x")
        self.chinese_target_combo.bind("<<ComboboxSelected>>", self._select_chinese_target_language)
        ttk.Label(intro, text=i18n.t("u2.supported_targets_reason"), wraplength=430).pack(fill="x")
        self.chinese_korean_hint = ttk.Label(intro, text="", wraplength=430, justify="left")
        self.chinese_korean_hint.pack(fill="x")

        src=ttk.LabelFrame(left,text=i18n.t("u2.input_output"),padding=9); src.pack(fill="x",pady=(5,0)); src.columnconfigure(0,weight=1)
        ttk.Label(src,text=i18n.t("u2.chinese_input")).grid(row=0,column=0,sticky="w")
        self.chinese_input_entry=ttk.Entry(src,textvariable=self.chinese_input_var,state="readonly"); self.chinese_input_entry.grid(row=1,column=0,sticky="ew",pady=(3,0))
        pickbar=ttk.Frame(src); pickbar.grid(row=2,column=0,sticky="ew",pady=(5,0))
        chinese_add_menu=tk.Menu(pickbar,tearoff=False)
        chinese_add_menu.add_command(label=i18n.t("u2.add_yaml"),command=self.pick_chinese_file)
        chinese_add_menu.add_command(label=i18n.t("u2.add_localization"),command=self.pick_chinese_folder)
        self.chinese_add_menu_button=ttk.Menubutton(pickbar,text=i18n.t("u2.add"),menu=chinese_add_menu)
        self.chinese_add_menu_button.pack(side="left")
        ttk.Label(pickbar,text=i18n.t("u2.selection_hint"),foreground="#666").pack(side="left",padx=(8,0))
        ttk.Label(src,textvariable=self.chinese_status_var,foreground="#555",wraplength=430,justify="left").grid(row=3,column=0,sticky="w",pady=(4,0))
        ttk.Separator(src,orient="horizontal").grid(row=4,column=0,sticky="ew",pady=5)
        ttk.Label(src,text=i18n.t("u2.output_root")).grid(row=5,column=0,sticky="w")
        self.chinese_output_entry=ttk.Entry(src,textvariable=self.chinese_output_var)
        self.chinese_output_entry.grid(row=6,column=0,sticky="ew",pady=(3,0))
        outbar=ttk.Frame(src); outbar.grid(row=7,column=0,sticky="ew",pady=(5,0))
        self.chinese_pick_output_btn=ttk.Button(outbar,text=i18n.t("u2.select"),command=self.pick_chinese_output)
        self.chinese_pick_output_btn.pack(side="left")
        ttk.Button(outbar,text=i18n.t("u2.open"),command=lambda:self._open_path(Path(self.chinese_output_var.get()))).pack(side="left",padx=(5,0))

        settings=ttk.LabelFrame(left,text=i18n.t("u2.shared_settings"),padding=9); settings.pack(fill="x",pady=(5,0))
        ttk.Label(settings,text=i18n.t("u2.shared_settings_hint"),wraplength=430,justify="left").pack(anchor="w")
        ttk.Button(settings,text=i18n.t("u2.open_settings"),command=lambda:self.notebook.select(self.tab_models)).pack(anchor="w",pady=(6,0))
        self.chinese_vocabulary_label = ttk.Label(settings,text=i18n.t("u2.vocabulary_hint"),foreground="#7a4b00",wraplength=430)
        self.chinese_vocabulary_label.pack(anchor="w",pady=(6,0))
        ttk.Checkbutton(settings,text=i18n.t("u2.autoqa"),variable=self.chinese_autoqa_var,command=self._save_llm_preferences).pack(anchor="w",pady=(7,0))
        ttk.Label(settings,text=i18n.t("u2.autoqa_hint"),foreground="#555",wraplength=430,justify="left").pack(anchor="w",pady=(5,0))

        qbox=ttk.LabelFrame(right,text=i18n.t("u2.queue_title"),padding=8); qbox.pack(fill="both",expand=True)
        qbar=ttk.Frame(qbox); qbar.pack(fill="x",pady=(0,5))
        self.chinese_remove_btn=ttk.Button(qbar,text=i18n.t("u2.remove_selected"),command=self.remove_chinese_queue_selected); self.chinese_remove_btn.pack(side="left")
        self.chinese_clear_btn=ttk.Button(qbar,text=i18n.t("u2.clear_all"),command=self.clear_chinese_queue); self.chinese_clear_btn.pack(side="left",padx=(5,0))
        self.chinese_change_output_btn=ttk.Button(qbar,text=i18n.t("u2.change_output"),command=self.change_chinese_output_for_selected); self.chinese_change_output_btn.pack(side="left",padx=(10,0))
        ttk.Button(qbar,text=i18n.t("u2.view_cache"),command=self.view_selected_chinese_cache).pack(side="left",padx=(5,0))
        self.chinese_import_cache_btn=ttk.Button(qbar,text=i18n.t("u2.add_cache"),command=self.import_cache_to_selected_chinese); self.chinese_import_cache_btn.pack(side="left",padx=(5,0))

        qbar2=ttk.Frame(qbox); qbar2.pack(fill="x",pady=(0,5))
        self.chinese_overwrite_btn=ttk.Button(qbar2,text=i18n.t("u2.overwrite_selected"),command=self.overwrite_selected_chinese_translation); self.chinese_overwrite_btn.pack(side="left")
        self.chinese_qa_btn=ttk.Button(qbar2,text=i18n.t("u2.qa_selected"),command=self.run_selected_chinese_qa); self.chinese_qa_btn.pack(side="left",padx=(6,0))
        self.chinese_glossary_btn=ttk.Button(qbar2,text=i18n.t("u2.auto_glossary"),command=lambda:self.start_auto_glossary_generation("chinese")); self.chinese_glossary_btn.pack(side="left",padx=(6,0))
        self.chinese_send_qa_btn=ttk.Button(qbar2,text=i18n.t("u2.send_to_qa"),command=lambda:self._send_pair_to_qa_or_diff("chinese","review")); self.chinese_send_qa_btn.pack(side="left",padx=(6,0))
        self.chinese_send_diff_btn=ttk.Button(qbar2,text=i18n.t("u2.send_to_diff"),command=lambda:self._send_pair_to_qa_or_diff("chinese","diff")); self.chinese_send_diff_btn.pack(side="left",padx=(6,0))
        self.chinese_transfer_btn=ttk.Button(qbar,text=i18n.t("u2.send_to_normal"),command=lambda:self.transfer_selected_queue_to_opposite("chinese",False)); self.chinese_transfer_btn.pack(side="left",padx=(10,0))
        self.chinese_transfer_missing_btn=ttk.Button(qbar2,text=i18n.t("u2.queue_missing_english"),command=lambda:self.transfer_selected_queue_to_opposite("chinese",True)); self.chinese_transfer_missing_btn.pack(side="left",padx=(6,0))
        ttk.Label(qbox,text=i18n.t("u2.overwrite_hint"),foreground="#8a5a00",wraplength=900,justify="left").pack(fill="x",anchor="w",pady=(0,5))
        cols=("mod","input","output","status","target")
        chinese_queue_table=ttk.Frame(qbox)
        chinese_queue_table.pack(fill="both",expand=True)
        self.chinese_queue_tree=ttk.Treeview(chinese_queue_table,columns=cols,show="headings",height=10,selectmode="extended")
        for c,txt,w in (("mod",i18n.t("u2.mod_item"),240),("input",i18n.t("u2.chinese_localization"),430),("output",i18n.t("u2.output"),390),("status",i18n.t("u2.status"),230)):
            self.chinese_queue_tree.heading(c,text=txt)
            self.chinese_queue_tree.column(c,width=w,minwidth=120,stretch=False,anchor="center" if c=="status" else "w")
        self.chinese_queue_tree.heading("target", text=i18n.t("u2.target_language"))
        self.chinese_queue_tree.column("target", width=120, minwidth=100, stretch=False)
        self._enable_ctrl_multiselect(self.chinese_queue_tree)
        self._enable_tree_sort(self.chinese_queue_tree)
        sy=ttk.Scrollbar(chinese_queue_table,orient="vertical",command=self.chinese_queue_tree.yview)
        sx=ttk.Scrollbar(chinese_queue_table,orient="horizontal",command=self.chinese_queue_tree.xview)
        self.chinese_queue_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        sx.pack(side="bottom",fill="x")
        sy.pack(side="right",fill="y")
        self.chinese_queue_tree.pack(side="left",fill="both",expand=True)
        self._chinese_queue_controls=[
            self.chinese_target_combo,
            self.chinese_add_menu_button,self.chinese_output_entry,self.chinese_pick_output_btn,
            self.chinese_remove_btn,self.chinese_clear_btn,self.chinese_change_output_btn,self.chinese_import_cache_btn,
            self.chinese_overwrite_btn,self.chinese_qa_btn,self.chinese_glossary_btn,self.chinese_send_qa_btn,
            self.chinese_send_diff_btn,self.chinese_transfer_btn,self.chinese_transfer_missing_btn,self.chinese_queue_tree,
        ]
        self._cross_queue_controls.extend([self.chinese_transfer_btn,self.chinese_transfer_missing_btn])

        actions=ttk.Frame(right); actions.pack(fill="x",pady=(7,0))
        self.chinese_start_btn=ttk.Button(actions,text=i18n.t("u2.start"),command=self.start_chinese_basis_translation); self.chinese_start_btn.pack(side="left")
        self.chinese_pause_btn=ttk.Button(actions,text=i18n.t("u2.pause"),command=self.toggle_chinese_pause,state="disabled"); self.chinese_pause_btn.pack(side="left",padx=(6,0))
        self.chinese_stop_btn=ttk.Button(actions,text=i18n.t("u2.save_stop"),command=self.save_and_stop_chinese_translation,state="disabled"); self.chinese_stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(actions,text=i18n.t("u2.open_output"),command=self.open_selected_chinese_output).pack(side="left",padx=(6,0))
        ttk.Label(actions,textvariable=self.chinese_progress_var).pack(side="right")
        self.chinese_progress=ttk.Progressbar(right,mode="determinate",maximum=100); self.chinese_progress.pack(fill="x",pady=(6,7))

        logbox=ttk.LabelFrame(right,text=i18n.t("u2.log_title"),padding=6); logbox.pack(fill="both",expand=True)
        lbar=ttk.Frame(logbox); lbar.pack(fill="x",pady=(0,4))
        ttk.Button(lbar,text=i18n.t("u2.open_error_log"),command=lambda:self._open_path(LOG_ROOT)).pack(side="left")
        ttk.Button(lbar,text=i18n.t("u2.collect_logs"),command=self.collect_error_logs).pack(side="left",padx=(5,0))
        self.chinese_log=tk.Text(logbox,height=6,wrap="word",state="disabled")
        y=ttk.Scrollbar(logbox,command=self.chinese_log.yview); self.chinese_log.configure(yscrollcommand=y.set)
        self.chinese_log.pack(side="left",fill="both",expand=True); y.pack(side="right",fill="y")
        self._register_dnd_widgets([t,intro,src,self.chinese_input_entry,qbox,self.chinese_queue_tree],self.on_chinese_drop_paths)

    def _select_chinese_target_language(self, event=None):
        selected = next((language for language in core.TARGET_LANGUAGES
                         if i18n.t("lang." + language) == self.chinese_target_display_var.get()), "")
        if selected not in core.CHINESE_BASIS_TARGETS:
            messagebox.showinfo(APP_NAME, i18n.t("u2.supported_targets_reason"))
            self.chinese_target_display_var.set(i18n.t("lang." + self.chinese_target_lang_var.get()))
            return
        self.chinese_target_lang_var.set(selected)
        target_name = i18n.t("lang." + selected)
        self.chinese_intro_frame.config(text=i18n.t("u2." + "intro_title", target_name=target_name))
        description = (i18n.t("u2.korean_intro_description", target_name=target_name) if selected == "korean"
                       else i18n.t("u2." + "intro_description", target_name=target_name))
        self.chinese_intro_label.config(text=description)
        self.chinese_korean_hint.config(text=i18n.t("u2.korean_basis_hint") if selected == "korean" else "")
        self.chinese_vocabulary_label.config(text=i18n.t("u2.korean_basis_hint") if selected == "korean"
                                            else i18n.t("u2." + "vocabulary_hint"))

    def _append_chinese_log(self, text):
        if not hasattr(self, "chinese_log"):
            return
        self.chinese_log.config(state="normal")
        self.chinese_log.insert("end",str(text)+"\n")
        self.chinese_log.see("end")
        self.chinese_log.config(state="disabled")

    def _validate_chinese_input(self, path: Path):
        if not path.exists():
            return False,i18n.t("u2.path_missing")
        if path.is_file():
            try: lang,_,_=core.parse_localization_file(path)
            except Exception as exc: return False,i18n.t("u2.yaml_read_error", error=exc)
            if lang!="simp_chinese": return False,i18n.t("u2.wrong_language", language=lang)
            return True,i18n.t("u2.yaml_confirmed", filename=path.name)
        count=0
        for f in core.gather_yml_files(path):
            try:
                lang,_,_=core.parse_localization_file(f)
                if lang=="simp_chinese": count+=1
            except Exception: pass
        if not count: return False,i18n.t("u2.folder_no_yaml")
        return True,i18n.t("u2.yaml_count", count=count)

    def _refresh_chinese_queue_tree(self):
        if not hasattr(self,"chinese_queue_tree"): return
        app_state.ensure_queue_item_ids(self.chinese_queue_items)
        for x in self.chinese_queue_tree.get_children(): self.chinese_queue_tree.delete(x)
        for i,item in enumerate(self.chinese_queue_items):
            self.chinese_queue_tree.insert("","end",iid=f"zh_{i}",values=(
                item.get("mod_name",Path(item.get("input","")).name),
                self._queue_display_path(item.get("input","")),
                self._queue_display_path(item.get("output","")),
                display_status(item.get("status") or status_value("waiting")),
                i18n.t("lang." + _item_target_lang(item))
            ))

    def _append_chinese_queue(self, path, mod_name=""):
        if self._chinese_queue_locked():
            return None,i18n.t("u2.queue_locked")
        path=Path(path); ok,msg=self._validate_chinese_input(path)
        if not ok: return None,msg
        key=str(path.resolve())
        target_var = getattr(self, "chinese_target_lang_var", None)
        target_lang = target_var.get() if target_var is not None else core.DEFAULT_TARGET_LANG
        if target_lang not in core.CHINESE_BASIS_TARGETS:
            return None, i18n.t("u2.supported_targets_reason")
        for item in self.chinese_queue_items:
            try:
                if str(Path(item.get("input","")).resolve())==key and _item_target_lang(item) == target_lang: return item,i18n.t("u2.already_queued")
            except Exception: pass
        output_root = Path(self.chinese_output_var.get().strip() or str(OUTPUT_ROOT/"中国語基準翻訳"))
        isolated_output = self._isolated_output_path(path, output_root, mod_name or "", target_lang=target_lang)
        item={"input":str(path),"mod_name":mod_name or path.name,"status":status_value("waiting"),"output":str(isolated_output),"output_isolated_v2":True,"target_lang":target_lang}
        app_state.ensure_queue_item_id(item)
        if path.is_dir() and core.is_localization_dir_name(path.name):
            item["mod_localization"]=str(path); item["mod_root"]=str(path.parent)
        elif path.is_dir() and core.mod_localization_root(path) is not None:
            item["mod_root"]=str(path); item["mod_localization"]=str(core.mod_localization_root(path))
        self.chinese_queue_items.append(item); self._refresh_chinese_queue_tree(); self._save_workspace_state("chinese_queue_changed")
        return item,msg

    def remove_chinese_queue_selected(self):
        if self._chinese_queue_locked(): return
        if not hasattr(self,"chinese_queue_tree"): return
        idx=[]
        for iid in self.chinese_queue_tree.selection():
            try: idx.append(int(iid.split("_",1)[1]))
            except Exception: pass
        for i in sorted(set(idx),reverse=True):
            if 0<=i<len(self.chinese_queue_items): self.chinese_queue_items.pop(i)
        self._refresh_chinese_queue_tree(); self._save_workspace_state("chinese_queue_changed")

    def clear_chinese_queue(self):
        if self._chinese_queue_locked(): return
        self.chinese_queue_items.clear(); self._refresh_chinese_queue_tree(); self._save_workspace_state("chinese_queue_cleared")

    def _selected_chinese_queue_item(self):
        if not hasattr(self,"chinese_queue_tree"):
            return None
        sel=self.chinese_queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME,i18n.t("u2.select_queue_item"))
            return None
        try:
            idx=int(sel[0].split("_",1)[1])
        except Exception:
            return None
        return self.chinese_queue_items[idx] if 0 <= idx < len(self.chinese_queue_items) else None

    def change_chinese_output_for_selected(self):
        if self._chinese_queue_locked(): return
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=filedialog.askdirectory(title=i18n.t("u2.change_output_title"))
        if not raw: return
        item["output"]=str(Path(raw))
        self._append_chinese_log(i18n.t("u2.output_changed", mod_name=item.get('mod_name',i18n.t('u2.item')), path=raw))

    def open_selected_chinese_output(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=item.get("output","")
        if not raw:
            messagebox.showinfo(APP_NAME,i18n.t("u2.output_unset"))
            return
        self._open_path(Path(raw))

    def view_selected_chinese_cache(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=item.get("cache","")
        if not raw:
            messagebox.showinfo(APP_NAME,i18n.t("u2.cache_missing"))
            return
        cache=Path(raw)
        self._open_path(cache.parent if cache.parent.exists() else cache)

    def import_cache_to_selected_chinese(self):
        if self._chinese_queue_locked(): return
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=filedialog.askopenfilename(title=i18n.t("u2.import_cache_title"),filetypes=[("JSON","*.json"),("All files","*")])
        if not raw: return
        src=Path(raw)
        try:
            core.load_json(src,{})
            cache=Path(item.get("cache", "")) if item.get("cache") else self._new_cache_path(Path(item["input"]))
            cache.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,cache)
            item["cache"]=str(cache)
            self._append_chinese_log(i18n.t("u2.cache_imported", mod_name=item.get('mod_name',i18n.t('u2.item')), filename=src.name))
        except Exception as exc:
            record_error(i18n.t("u2.import_cache_error_context"),exc,str(src))
            messagebox.showerror(APP_NAME,i18n.t("u2.cache_import_failed", error=exc))

    def overwrite_selected_chinese_translation(self):
        """Overwrite all selected completed Chinese-basis jobs in one batch."""
        entries=self._selected_chinese_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,i18n.t("u2.select_overwrite"))
            return
        self._bulk_overwrite_queue_entries(entries, queue_kind="chinese")

    def run_selected_chinese_qa(self):
        entries=self._selected_chinese_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,i18n.t("u2.select_qa")); return
        pairs=[]
        for _idx,item in entries:
            inp=Path(item.get("input", "")); out=Path(item.get("output", ""))
            if inp.exists(): pairs.extend(core.collect_translation_qa_pairs(inp,out,("simp_chinese",), target_lang=_item_target_lang(item)))
        self._start_manual_qa_repair(pairs,"chinese")

    def pick_chinese_file(self):
        raw=filedialog.askopenfilename(title=i18n.t("u2.pick_yaml_title"),filetypes=[("Paradox YAML","*.yml *.yaml"),("All files","*")])
        if not raw:return
        path=Path(raw)
        self.chinese_input_var.set(str(path))
        item,msg=self._append_chinese_queue(path)
        self.chinese_status_var.set(msg)
        if not item: messagebox.showwarning(APP_NAME,msg)

    def pick_chinese_folder(self):
        raw=filedialog.askdirectory(title=i18n.t("u2.pick_folder_title"))
        if not raw:return
        path=Path(raw)
        self.chinese_input_var.set(str(path))
        item,msg=self._append_chinese_queue(path)
        self.chinese_status_var.set(msg)
        if not item: messagebox.showwarning(APP_NAME,msg)

    def pick_chinese_output(self):
        raw=filedialog.askdirectory(title=i18n.t("u2.pick_output_title"))
        if raw:self.chinese_output_var.set(raw)

    def on_chinese_drop_paths(self,event):
        if self._chinese_queue_locked():
            return "break"
        paths=self._raw_drop_paths(event)
        added=0
        for path in paths:
            if path.is_file() and path.suffix.lower() not in {".yml",".yaml"}: continue
            item,msg=self._append_chinese_queue(path)
            if item: added+=1
        if paths:
            self.chinese_input_var.set(str(paths[0])); ok,msg=self._validate_chinese_input(paths[0]); self.chinese_status_var.set(msg)
        if not added and paths: messagebox.showinfo(APP_NAME,i18n.t("u2.drop_no_yaml"))
        return event.action if hasattr(event,"action") else None

    def _ask_translation_mode(self, title=None):
        """Return 'diff', 'full', or None using an explicit three-button dialog."""
        result = {"value": None}
        win = tk.Toplevel(self)
        win.title(title if title is not None else i18n.t("u6.choose_translation_mode"))
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        body = ttk.Frame(win, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=i18n.t('u6.how_would_you_like_to_translate'), font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(body, text=i18n.t('u6.only_the_selected_queue_items_will'), foreground="#555").pack(anchor="w", pady=(4, 12))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        def choose(value):
            result["value"] = value
            win.destroy()
        ttk.Button(buttons, text=i18n.t('u6.translate_differences_only'), command=lambda: choose("diff")).pack(side="left")
        ttk.Button(buttons, text=i18n.t('u6.translate_everything_from_scratch'), command=lambda: choose("full")).pack(side="left", padx=(8,0))
        ttk.Button(buttons, text=i18n.t('u6.cancel'), command=lambda: choose(None)).pack(side="left", padx=(8,0))
        win.protocol("WM_DELETE_WINDOW", lambda: choose(None))
        win.update_idletasks()
        try:
            x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - win.winfo_height()) // 2)
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.wait_window()
        return result["value"]

    def _prepare_selected_for_full_translation(self, entries):
        """Reset only selected queue entries and force a fresh cache for true full retranslation."""
        for _idx, item in entries:
            self._reset_item_for_full_translation(item)
            item["cache"] = str(self._new_cache_path(Path(item["input"])))
            item["status"] = status_value("waiting")

    def start_chinese_differential_translation(self, entries=None):
        entries=entries if entries is not None else self._selected_chinese_queue_entries()
        self._start_differential_prepare(entries, mode='chinese')

    def start_chinese_basis_translation(self):
        if self._closing: return
        if self.chinese_worker is not None:
            return
        if not self.chinese_queue_items:
            raw=self.chinese_input_var.get().strip()
            if raw:
                self._append_chinese_queue(Path(raw))
                self._refresh_chinese_queue_tree()
        entries = self._selected_chinese_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME, i18n.t("u2.select_translation"))
            return
        mode = self._ask_translation_mode(i18n.t("u2.translation_mode"))
        if mode is None:
            return
        if mode == "diff":
            self.start_chinese_differential_translation(entries)
            return
        self._prepare_selected_for_full_translation(entries)
        self._refresh_chinese_queue_tree()
        self._start_chinese_selected([idx for idx, _item in entries], diff_requested=False)

    def _start_chinese_selected(self, selected_indices, diff_requested=False, _llm_ready=False):
        if self._closing: return
        if self.chinese_worker is not None: return
        selected_indices = sorted(set(int(x) for x in selected_indices if 0 <= int(x) < len(self.chinese_queue_items)))
        if not selected_indices:
            messagebox.showinfo(APP_NAME,i18n.t("u2.select_translation")); return
        if any(_item_target_lang(self.chinese_queue_items[index]) not in core.CHINESE_BASIS_TARGETS
               for index in selected_indices):
            messagebox.showinfo(APP_NAME, i18n.t("u2.supported_targets_reason")); return
        if not _llm_ready:
            indices=tuple(selected_indices)
            self._begin_llm_preflight("中国語基準翻訳",
                lambda:self._start_chinese_selected(indices,diff_requested=diff_requested,_llm_ready=True))
            return
        for idx in selected_indices:
            self._ensure_isolated_item_output(self.chinese_queue_items[idx], mode="chinese")
            app_state.ensure_queue_item_id(self.chinese_queue_items[idx])
        self._refresh_chinese_queue_tree()
        out_root=Path(self.chinese_output_var.get().strip() or str(OUTPUT_ROOT/"中国語基準翻訳")); out_root.mkdir(parents=True,exist_ok=True)
        self.chinese_log.config(state="normal"); self.chinese_log.delete("1.0","end"); self.chinese_log.config(state="disabled")
        self.chinese_progress["value"]=0; self.chinese_progress_var.set(i18n.t("u2.preparing")); self.llm_operation="中国語基準翻訳"
        self.chinese_controller=core.TranslationController(progress_callback=lambda x:self.events.put(("chinese_progress",x)))
        self.chinese_start_btn.config(state="disabled"); self.chinese_pause_btn.config(state="normal", text=i18n.t("u2.pause")); self.chinese_stop_btn.config(state="normal")
        settings={"provider":self.provider_var.get(),"url":self.url_var.get().strip(),"model":self.model_var.get().strip(),"api_key":self.api_key_var.get().strip(),"preset":self.preset_var.get(),"batch":max(1,self.batch_var.get()),"workers":max(1,self.workers_var.get()),"glossary":self.glossary_path_var.get().strip() or None,"autoqa":self.chinese_autoqa_var.get(),"normalize_spacing":_normalize_spacing_enabled(self)}
        snapshot=[(app_state.ensure_queue_item_id(self.chinese_queue_items[i]), dict(self.chinese_queue_items[i])) for i in selected_indices]
        def worker():
            try:
                total=len(snapshot); completed=0; qa_errors=0; qa_warnings=0; qa_notices=0; qa_repaired=0
                qa_reports=[]; qa_backups=[]
                for pos,(item_id,item) in enumerate(snapshot):
                    if self.chinese_controller.stop_event.is_set(): break
                    live_item=app_state.queue_item_by_id(self.chinese_queue_items,item_id)
                    if live_item is None:
                        raise RuntimeError(i18n.t("u2.queue_item_lost"))
                    live_item["status"]=status_value("translating")
                    self.events.put(("chinese_queue_status",(item_id,status_value("translating"))))
                    self.events.put(("chinese_queue_current",(pos+1,total,item.get("mod_name",""))))
                    inp=Path(item["input"]); safe=re.sub(r'[^0-9A-Za-z_\-\u3040-\u30ff\u4e00-\u9fff]+','_',item.get("mod_name") or inp.name).strip("_") or f"item_{pos+1}"
                    out=Path(item.get("output") or (out_root/safe)); out.mkdir(parents=True,exist_ok=True)
                    cache=Path(item.get("cache", "")) if item.get("cache") else self._new_cache_path(inp)
                    item["output"]=str(out); item["cache"]=str(cache)
                    live_item["output"]=str(out); live_item["cache"]=str(cache)
                    result=core.run_chinese_basis_translation(inp,out,target_lang=_item_target_lang(item),model=settings["model"],url=settings["url"],workers=settings["workers"],batch_size=settings["batch"],cache_path=cache,controller=self.chinese_controller,glossary_path=settings["glossary"] if _item_target_lang(item) == core.DEFAULT_TARGET_LANG else _existing_language_glossary(settings["glossary"], _item_target_lang(item)),preset=settings["preset"],auto_qa=settings["autoqa"],provider=settings["provider"],api_key=settings["api_key"],qa_backup_root=BACKUP_ROOT/"QA自動修復",normalize_spacing=settings["normalize_spacing"])
                    self.events.put(("chinese_log", i18n.t("u2.spaces_removed", count=result.get('spaces_removed',0))))
                    qa_errors += int(result.get("qa_errors",0) or 0)
                    qa_warnings += int(result.get("qa_warnings",0) or 0)
                    qa_notices += int(result.get("qa_notices",0) or 0)
                    qa_repaired += int(result.get("qa_repaired",0) or 0)
                    if result.get("qa_report"): qa_reports.append(result["qa_report"])
                    if result.get("qa_backup"): qa_backups.append(result["qa_backup"])
                    self._register_cache_job(live_item, mode="chinese")
                    if result.get("interrupted"):
                        live_item["status"]=status_value("interrupted")
                        self.events.put(("chinese_queue_status",(item_id,status_value("interrupted")))); break
                    completed += 1
                    if live_item.get("diff_mode"):
                        lang_done = self._differential_language_completion(live_item, "simp_chinese")
                        if lang_done.get("language_complete"):
                            final_status = self._language_complete_status_text("simp_chinese", int(lang_done.get("opposite_only_count", 0) or 0))
                        elif self._item_has_remaining_translation_gap(live_item):
                            final_status = status_value("done_partial_gap")
                        else:
                            final_status = status_value("done_diff_updated")
                    elif self._item_has_remaining_translation_gap(live_item):
                        final_status = status_value("done_partial_gap")
                    else:
                        final_status = status_value("done")
                    live_item["status"]=final_status
                    self.events.put(("chinese_queue_status",(item_id,final_status)))
                self.events.put(("chinese_done",{"interrupted":self.chinese_controller.stop_event.is_set(),"processed_files":completed,"jobs":0,"output":str(out_root),"queue_total":total,"qa_errors":qa_errors,"qa_warnings":qa_warnings,"qa_notices":qa_notices,"qa_repaired":qa_repaired,"qa_reports":qa_reports,"qa_backups":qa_backups}))
            except Exception as exc: self.events.put(("chinese_error",str(exc)))
        self.chinese_worker=threading.Thread(target=worker,daemon=True); self.chinese_worker.start()
        self._refresh_operation_states()

    def toggle_chinese_pause(self):
        if not self.chinese_controller:
            return
        if self.chinese_controller.pause_event.is_set():
            self.chinese_controller.resume()
            self.chinese_pause_btn.config(text=i18n.t("u2.pause"))
            self.chinese_progress_var.set(i18n.t("u2.resumed"))
        else:
            self.chinese_controller.pause()
            self.chinese_pause_btn.config(text=i18n.t("u2.resume"))
            self.chinese_progress_var.set(i18n.t("u2.pausing"))

    def save_and_stop_chinese_translation(self):
        self._save_workspace_state("chinese_save_stop")
        if self.chinese_controller:
            self.chinese_controller.request_stop(save=True)
            self.chinese_progress_var.set(i18n.t("u2.stopping"))
            self.chinese_stop_btn.config(state="disabled")
            self.chinese_pause_btn.config(state="disabled", text=i18n.t("u2.pause"))

    def stop_chinese_basis_translation(self):
        # 旧内部呼び出しとの互換用。中国語基準翻訳は常にキャッシュを保存して安全に中断する。
        self.save_and_stop_chinese_translation()

    def _localization_display_path(self, value):
        """Return only the localization language folder and the path below it for UI display."""
        if not value:
            return ""
        try:
            p = Path(value)
            parts = list(p.parts)
            language_names = {"english", "japanese", "simp_chinese", "korean", "french", "german", "spanish", "russian"}
            for i, part in enumerate(parts):
                if part.lower() in language_names:
                    return str(Path(*parts[i:]))
            # Some mods keep files directly below localization; showing only the filename is clearer than a full system path.
            return p.name
        except Exception:
            return str(value)

    def _queue_display_path(self, value):
        """Short path representation for translation queue tables; full paths remain stored internally."""
        if not value:
            return ""
        try:
            p = Path(value)
            parts = list(p.parts)
            language_names = {"english", "japanese", "simp_chinese", "korean", "french", "german", "spanish", "russian"}
            for i, part in enumerate(parts):
                if part.lower() in language_names:
                    return str(Path(*parts[i:]))

            # Generated outputs are most useful relative to the app's data/output roots.
            for root in (OUTPUT_ROOT, DATA_ROOT):
                try:
                    rel = p.relative_to(root)
                    if str(rel) not in ("", "."):
                        return str(rel)
                except Exception:
                    pass

            # For a localization directory retain its parent Mod name so multiple entries are distinguishable.
            if core.is_localization_dir_name(p.name) and p.parent.name:
                return str(Path(p.parent.name) / p.name)
            if p.is_dir():
                return p.name or str(p)
            return p.name
        except Exception:
            return str(value)

    def _collect_qa_diff_pairs(self, source_root, target_root, source_langs=("english", "simp_chinese"),
                               target_lang=core.DEFAULT_TARGET_LANG):
        """Return source/Japanese YAML pairs for QA/diff import buttons."""
        source_root = Path(source_root)
        target_root = Path(target_root)
        if not source_root.exists() or not target_root.exists():
            return []

        source_files = [source_root] if source_root.is_file() else core.gather_yml_files(source_root)
        target_files = [target_root] if target_root.is_file() else core.gather_yml_files(target_root)
        targets = []
        for f in target_files:
            try:
                lang, entries, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang == target_lang:
                targets.append((f, entries))
        if not targets:
            return []

        source_base = source_root if source_root.is_dir() else source_root.parent
        pairs = []
        seen = set()
        for sf in source_files:
            try:
                lang, entries, _ = core.parse_localization_file(sf)
            except Exception:
                continue
            if lang not in source_langs or lang == target_lang:
                continue

            chosen = None
            # First prefer the deterministic path produced by the translator.
            if target_root.is_dir():
                try:
                    rel = sf.parent.relative_to(source_base) if source_root.is_dir() else Path(".")
                    expected = target_root / core.remap_rel_dir(rel, target_lang) / core.rename_for_target(sf, target_lang, lang)
                    if expected.exists():
                        chosen = expected
                except Exception:
                    chosen = None

            # Then prefer the same logical localization filename/relative layout.
            if chosen is None:
                try:
                    src_id = core._logical_localization_id(sf, source_root, lang)
                    for tf, _ in targets:
                        try:
                            if core._logical_localization_id(tf, target_root, target_lang) == src_id:
                                chosen = tf
                                break
                        except Exception:
                            continue
                except Exception:
                    pass

            # Separate translation Mods sometimes have a different directory layout.
            # In that case pair by localization-key overlap.
            if chosen is None and entries:
                source_keys = set(entries)
                best = None
                best_overlap = 0
                for tf, tentries in targets:
                    overlap = len(source_keys & set(tentries))
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best = tf
                if best_overlap:
                    chosen = best

            if chosen is None:
                continue
            key = (str(sf), str(chosen))
            if key in seen:
                continue
            seen.add(key)
            pair = {"source": sf, "target": chosen, "lang": lang}
            if target_lang != core.DEFAULT_TARGET_LANG:
                pair["target_language"] = target_lang
            pairs.append(pair)
        return pairs

    def _choose_qa_diff_pairs(self, pairs, title):
        if not pairs:
            return []
        if len(pairs) == 1:
            return [pairs[0]]

        result = {"value": []}
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("980x520")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text=i18n.t('u3.choose_pair'), padding=(10,10,10,4)).pack(anchor="w")
        frame = ttk.Frame(win, padding=(10,0,10,8)); frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("lang","src","dst"), show="headings", selectmode="browse")
        for c, label, width in (("lang",i18n.t('u3.source_language'),120),("src",i18n.t('u3.source_yaml'),390),("dst",i18n.t('u3.japanese_yaml'),390)):
            tree.heading(c, text=label); tree.column(c, width=width, anchor="w")
        sy = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.pack(side="top", fill="both", expand=True)
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        labels = {"english":i18n.t('u3.english'), "simp_chinese":i18n.t('u3.simplified_chinese')}
        for i, pair in enumerate(pairs):
            tree.insert("", "end", iid=str(i), values=(labels.get(pair["lang"], pair["lang"]), self._localization_display_path(pair["source"]), self._localization_display_path(pair["target"])))
        tree.selection_set("0"); tree.focus("0")

        buttons = ttk.Frame(win, padding=(10,0,10,10)); buttons.pack(fill="x")
        def accept_selected(_=None):
            sel = tree.selection()
            if not sel:
                return
            result["value"] = [pairs[int(sel[0])]]
            win.destroy()
        def accept_language(lang=None):
            selected=_qa_diff_pairs_for_language(pairs,lang)
            if not selected:
                return
            result["value"] = selected
            win.destroy()
        english_count=sum(pair.get("lang")=="english" for pair in pairs)
        chinese_count=sum(pair.get("lang")=="simp_chinese" for pair in pairs)
        ttk.Button(buttons, text=i18n.t('u3.all_english', english_count=english_count), command=lambda:accept_language("english"), state="normal" if english_count else "disabled").pack(side="left")
        ttk.Button(buttons, text=i18n.t('u3.all_chinese', chinese_count=chinese_count), command=lambda:accept_language("simp_chinese"), state="normal" if chinese_count else "disabled").pack(side="left", padx=(6,0))
        ttk.Button(buttons, text=i18n.t('u3.selected_files'), command=accept_selected).pack(side="right")
        ttk.Button(buttons, text=i18n.t('u3.cancel'), command=win.destroy).pack(side="right", padx=(0,6))
        tree.bind("<Double-1>", accept_selected)
        self.wait_window(win)
        return result["value"]

    def _send_pair_to_qa_or_diff(self, origin, destination):
        source_root = target_root = None
        if origin == "normal":
            item = self._selected_queue_item()
            if not item:
                return
            source_root = Path(item.get("input", ""))
            target_root = Path(item.get("output", ""))
            source_langs = ("english", "simp_chinese")
            label = i18n.t('u3.normal_translation')
        elif origin == "chinese":
            item = self._selected_chinese_queue_item()
            if not item:
                return
            source_root = Path(item.get("input", ""))
            target_root = Path(item.get("output", ""))
            source_langs = ("simp_chinese",)
            label = "中国語基準翻訳"
        elif origin == "status":
            results = self._selected_mod_status_results()
            if not results:
                messagebox.showinfo(APP_NAME, i18n.t('u3.select_status_mod'))
                return
            if len(results) != 1:
                messagebox.showinfo(APP_NAME, i18n.t('u3.select_one_status_mod'))
                return
            r = results[0]
            source_root = Path(r.get("localization") or core.localization_dir_path(Path(r.get("path", ""))))
            external = r.get("external_translation_localization", "")
            target_root = Path(external) if external and Path(external).exists() else source_root
            source_langs = ("english", "simp_chinese")
            label = r.get("mod", i18n.t('u3.translation_status'))
        else:
            return

        target_lang = _item_target_lang(item) if origin in ("normal", "chinese") else core.DEFAULT_TARGET_LANG
        pairs = self._collect_qa_diff_pairs(source_root, target_root, source_langs, target_lang=target_lang)
        if not pairs:
            messagebox.showinfo(APP_NAME, i18n.t('u3.pair_not_found', label=label))
            return
        selected_pairs = self._choose_qa_diff_pairs(pairs, i18n.t('u3.choose_pair_from', label=label))
        if not selected_pairs:
            return
        if origin == "chinese" and target_lang == "korean":
            self._set_target_lang(target_lang, save=False)
        if destination == "review":
            self.notebook.select(self.tab_review)
            self.load_review_pairs(selected_pairs)
        else:
            self.notebook.select(self.tab_diff)
            self.load_diff_pairs(selected_pairs)

    def _build_review_tab(self):
        t=self.tab_review
        pf=ttk.LabelFrame(t,text=i18n.t('u3.source_translation'),padding=8); pf.pack(fill="x")
        pf.columnconfigure(1,weight=1)
        ttk.Label(pf,text=i18n.t('u3.source')).grid(row=0,column=0,sticky="w")
        self.review_src_entry=ttk.Entry(pf,textvariable=self.review_src_display_var,state="readonly")
        self.review_src_entry.grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Button(pf,text=i18n.t('u3.choose'),command=lambda:self.pick_review_file(self.review_src_var)).grid(row=0,column=2)
        ttk.Label(pf,text=i18n.t('u3.translation')).grid(row=1,column=0,sticky="w",pady=(5,0))
        self.review_dst_entry=ttk.Entry(pf,textvariable=self.review_dst_display_var,state="readonly")
        self.review_dst_entry.grid(row=1,column=1,sticky="ew",padx=6,pady=(5,0))
        ttk.Button(pf,text=i18n.t('u3.choose'),command=lambda:self.pick_review_file(self.review_dst_var)).grid(row=1,column=2,pady=(5,0))
        ttk.Button(pf,text=i18n.t('u3.load_comparison'),command=self.load_review).grid(row=0,column=3,rowspan=2,padx=(8,0))
        self.review_drop_hint=ttk.Label(pf,text=i18n.t('u3.drop_pair', target_name=i18n.t("lang." + _current_target_lang(self))) if DND_AVAILABLE else i18n.t('u3.dnd_unavailable'),foreground="#555")
        self.review_drop_hint.grid(row=2,column=0,columnspan=4,sticky="ew",pady=(7,0))
        qa=ttk.Frame(t); qa.pack(fill="x",pady=(8,5))
        ttk.Button(qa,text=i18n.t('u3.rerun_qa'),command=self.run_review_qa).pack(side="left")
        self.review_auto_repair_btn=ttk.Button(qa,text=i18n.t('u3.backup_auto_repair'),command=self.run_review_auto_repair,state="disabled")
        self.review_auto_repair_btn.pack(side="left",padx=(6,0))
        self.review_export_log_btn=ttk.Button(qa,text=i18n.t('u3.export_qa_log'),command=self.export_review_qa_log,state="disabled")
        self.review_export_log_btn.pack(side="left",padx=(6,0))
        ttk.Button(qa,text=i18n.t('u3.issues_only'),command=lambda:self.populate_review(True)).pack(side="left",padx=(6,0))
        ttk.Button(qa,text=i18n.t('u3.all_keys'),command=lambda:self.populate_review(False)).pack(side="left",padx=(6,0))
        ttk.Button(qa,text=i18n.t('u3.unify_terms'),command=self.bulk_unify_review_terms).pack(side="left",padx=(8,0))
        ttk.Button(qa,text=i18n.t('u3.create_glossary'),command=lambda:self.start_auto_glossary_generation("review")).pack(side="left",padx=(8,0))
        ttk.Button(qa,text=i18n.t('u3.apply_settings'),command=self.apply_translation_settings_everywhere).pack(side="left",padx=(10,0))
        ttk.Label(qa,text=i18n.t('u3.proofread_hint'),foreground="#666").pack(side="left",padx=(12,0))
        ttk.Label(qa,textvariable=self.qa_summary_var).pack(side="right")

        paned=ttk.Panedwindow(t,orient="horizontal"); paned.pack(fill="both",expand=True)
        left=ttk.Frame(paned); right=ttk.Frame(paned); paned.add(left,weight=2); paned.add(right,weight=3)
        self.review_tree=ttk.Treeview(left,columns=("type","file","key"),show="tree headings")
        self.review_tree.heading("#0",text=i18n.t('u3.severity_category')); self.review_tree.column("#0",width=150)
        self.review_tree.heading("type",text=i18n.t('u3.type')); self.review_tree.column("type",width=130)
        self.review_tree.heading("file",text=i18n.t('u3.file')); self.review_tree.column("file",width=220)
        self.review_tree.heading("key",text=i18n.t('u3.key')); self.review_tree.column("key",width=300)
        self.review_tree.bind("<<TreeviewSelect>>",self.on_review_select)
        self._enable_tree_sort(self.review_tree, recursive=True)
        rys=ttk.Scrollbar(left,command=self.review_tree.yview); self.review_tree.configure(yscrollcommand=rys.set)
        self.review_tree.pack(side="left",fill="both",expand=True); rys.pack(side="right",fill="y")

        ttk.Label(right,text=i18n.t('u3.english_chinese_source')).pack(anchor="w")
        self.src_text=tk.Text(right,height=7,wrap="word"); self.src_text.pack(fill="x",pady=(2,8))
        ttk.Label(right,text=i18n.t('u3.editable_translation')).pack(anchor="w")
        self.dst_text=tk.Text(right,height=10,wrap="word"); self.dst_text.pack(fill="both",expand=True,pady=(2,6))
        self.issue_text=tk.StringVar(value="")
        ttk.Label(right,textvariable=self.issue_text,wraplength=550).pack(fill="x",pady=(0,6))
        eb=ttk.Frame(right); eb.pack(fill="x")
        ttk.Button(eb,text=i18n.t('u3.save_translation_file', target_name=i18n.t("lang." + _current_target_lang(self))),command=self.save_review_value).pack(side="left")
        ttk.Button(eb,text=i18n.t('u3.save_glossary'),command=self.save_review_glossary_term).pack(side="left",padx=(6,0))
        ttk.Button(eb,text=i18n.t('u3.ai_proofread'),command=self.ai_proofread_selected).pack(side="left",padx=(6,0))
        ttk.Button(eb,text=i18n.t('u3.restore_source'),command=self.restore_source_to_target).pack(side="left",padx=(6,0))
        self._register_dnd_widgets([pf,self.review_src_entry,self.review_dst_entry,self.review_drop_hint,self.review_tree,self.src_text,self.dst_text],self.on_review_drop_paths)

    def _build_diff_tab(self):
        t = self.tab_diff
        pf = ttk.LabelFrame(t, text=i18n.t('u3.diff_files', target_name=i18n.t("lang." + _current_target_lang(self))), padding=8); pf.pack(fill="x")
        pf.columnconfigure(1, weight=1)
        ttk.Label(pf, text=i18n.t('u3.diff_source')).grid(row=0, column=0, sticky="w")
        self.diff_src_entry=ttk.Entry(pf, textvariable=self.diff_src_display_var, state="readonly")
        self.diff_src_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(pf, text=i18n.t('u3.choose'), command=lambda:self.pick_review_file(self.diff_src_var)).grid(row=0, column=2)
        ttk.Label(pf, text=i18n.t('u3.target_language', target_name=i18n.t("lang." + _current_target_lang(self)))).grid(row=1, column=0, sticky="w", pady=(5,0))
        self.diff_dst_entry=ttk.Entry(pf, textvariable=self.diff_dst_display_var, state="readonly")
        self.diff_dst_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=(5,0))
        ttk.Button(pf, text=i18n.t('u3.choose'), command=lambda:self.pick_review_file(self.diff_dst_var)).grid(row=1, column=2, pady=(5,0))
        ttk.Button(pf, text=i18n.t('u3.inspect_diff'), command=self.load_diff_inspector).grid(row=0, column=3, rowspan=2, padx=(8,0))
        self.diff_drop_hint=ttk.Label(pf,text=i18n.t('u3.drop_pair', target_name=i18n.t("lang." + _current_target_lang(self))) if DND_AVAILABLE else i18n.t('u3.dnd_unavailable'),foreground="#555")
        self.diff_drop_hint.grid(row=2,column=0,columnspan=4,sticky="ew",pady=(7,0))

        bar = ttk.Frame(t); bar.pack(fill="x", pady=(8,5))
        ttk.Button(bar, text=i18n.t('u3.translate_selected'), command=lambda:self.translate_diff_items(False)).pack(side="left")
        ttk.Button(bar, text=i18n.t('u3.translate_missing'), command=lambda:self.translate_diff_items(True)).pack(side="left", padx=(6,0))
        ttk.Button(bar, text=i18n.t('u3.save_selected'), command=self.save_diff_value).pack(side="left", padx=(6,0))
        ttk.Button(bar,text=i18n.t('u3.create_glossary'),command=lambda:self.start_auto_glossary_generation("diff")).pack(side="left",padx=(8,0))
        ttk.Button(bar,text=i18n.t('u3.apply_settings'),command=self.apply_translation_settings_everywhere).pack(side="left",padx=(10,0))
        ttk.Label(bar,text=i18n.t('u3.diff_hint'),foreground="#666").pack(side="left",padx=(12,0))
        ttk.Label(bar, textvariable=self.diff_summary_var).pack(side="right")

        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=2); paned.add(right, weight=3)
        self.diff_tree = ttk.Treeview(left, columns=("file","key"), show="tree headings", selectmode="extended")
        self._enable_ctrl_multiselect(self.diff_tree)
        self.diff_tree.heading("#0", text=i18n.t('u3.status')); self.diff_tree.column("#0", width=150)
        self.diff_tree.heading("file", text=i18n.t('u3.file')); self.diff_tree.column("file", width=220)
        self.diff_tree.heading("key", text=i18n.t('u3.key')); self.diff_tree.column("key", width=360)
        self.diff_tree.tag_configure("missing", background="#fee2e2")
        self.diff_tree.tag_configure("untranslated", background="#fef3c7")
        self.diff_tree.tag_configure("extra", background="#e0e7ff")
        self.diff_tree.bind("<<TreeviewSelect>>", self.on_diff_select)
        self._enable_tree_sort(self.diff_tree, recursive=True)
        ys = ttk.Scrollbar(left, command=self.diff_tree.yview); self.diff_tree.configure(yscrollcommand=ys.set)
        hint = ttk.Label(left, text=i18n.t('u3.multi_select_hint'), foreground="#666")
        hint.pack(side="bottom", fill="x", pady=(3,0))
        self.diff_tree.pack(side="left", fill="both", expand=True); ys.pack(side="right", fill="y")

        compare = ttk.Panedwindow(right, orient="horizontal"); compare.pack(fill="both", expand=True)
        srcf = ttk.Frame(compare); dstf = ttk.Frame(compare); compare.add(srcf, weight=1); compare.add(dstf, weight=1)
        ttk.Label(srcf, text=i18n.t('u3.english_chinese_source')).pack(anchor="w")
        self.diff_src_text = tk.Text(srcf, wrap="word"); self.diff_src_text.pack(fill="both", expand=True, padx=(0,4), pady=(2,0))
        ttk.Label(dstf, text=i18n.t('u3.editable_target', target_name=i18n.t("lang." + _current_target_lang(self)))).pack(anchor="w")
        self.diff_dst_text = tk.Text(dstf, wrap="word"); self.diff_dst_text.pack(fill="both", expand=True, padx=(4,0), pady=(2,0))
        self.diff_message_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.diff_message_var, wraplength=650).pack(fill="x", pady=(4,0))
        self._register_dnd_widgets([pf,self.diff_src_entry,self.diff_dst_entry,self.diff_drop_hint,self.diff_tree,self.diff_src_text,self.diff_dst_text],self.on_diff_drop_paths)

    def _build_search_tab(self):
        t = self.tab_search
        top = ttk.LabelFrame(t, text=i18n.t('u3.search_japanese'), padding=8); top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text=i18n.t('u3.game')).grid(row=0, column=0, sticky="w")
        self.search_game_combo = ttk.Combobox(top, textvariable=self.search_game_var, values=list(core.PARADOX_STEAM_GAMES), state="readonly", width=28)
        self.search_game_combo.grid(row=0, column=1, sticky="w", padx=6)
        self.search_game_combo.bind("<<ComboboxSelected>>", lambda e:self.refresh_translation_search_mods())
        ttk.Button(top, text=i18n.t('u3.rediscover_locations'), command=self.discover_mod_locations).grid(row=0, column=2, columnspan=2, sticky="e")
        ttk.Label(top, text=i18n.t('u3.search_term')).grid(row=1, column=0, sticky="w", pady=(6,0))
        ent = ttk.Entry(top, textvariable=self.search_query_var); ent.grid(row=1, column=1, sticky="ew", padx=6, pady=(6,0)); ent.bind("<Return>", lambda e:self.run_translation_search())
        ttk.Button(top, text=i18n.t('u3.search'), command=self.run_translation_search).grid(row=1, column=2, sticky="ew", pady=(6,0))
        ttk.Button(top, text=i18n.t('u3.clear_results'), command=self.clear_translation_search_results).grid(row=1, column=3, sticky="ew", padx=(6,0), pady=(6,0))
        ttk.Label(top, text=i18n.t('u3.search_hint'), foreground="#666").grid(row=2, column=0, columnspan=4, sticky="w", pady=(6,0))

        target = ttk.LabelFrame(t, text=i18n.t('u3.search_mods'), padding=6); target.pack(fill="x", pady=(6,0))
        target.columnconfigure(0, weight=1)
        listframe=ttk.Frame(target); listframe.grid(row=0,column=0,rowspan=2,sticky="ew")
        listframe.columnconfigure(0,weight=1)
        self.search_mod_list = tk.Listbox(listframe, height=5, selectmode="extended", exportselection=False)
        smy=ttk.Scrollbar(listframe, orient="vertical", command=self.search_mod_list.yview); self.search_mod_list.configure(yscrollcommand=smy.set)
        self.search_mod_list.grid(row=0,column=0,sticky="ew"); smy.grid(row=0,column=1,sticky="ns")
        self.search_mod_list.bind("<<ListboxSelect>>", lambda e:self._remember_translation_search_mod_selection())
        buttons=ttk.Frame(target); buttons.grid(row=0,column=1,sticky="ns",padx=(8,0))
        ttk.Button(buttons,text=i18n.t('u3.refresh_mods'),command=self.refresh_translation_search_mods).pack(fill="x")
        ttk.Button(buttons,text=i18n.t('u3.select_all'),command=self._select_all_translation_search_mods).pack(fill="x",pady=(4,0))
        ttk.Button(buttons,text=i18n.t('u3.deselect_all'),command=self._clear_translation_search_mod_selection).pack(fill="x",pady=(4,0))
        ttk.Label(target,textvariable=self.search_mod_status_var,foreground="#555").grid(row=1,column=1,sticky="sw",padx=(8,0))
        ttk.Label(target,text=i18n.t('u3.search_scope'),foreground="#666").grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,0))

        ttk.Label(t, textvariable=self.search_summary_var).pack(anchor="w", pady=(7,4))
        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=3); paned.add(right, weight=2)
        search_table = ttk.Frame(left)
        search_table.pack(fill="both", expand=True)
        search_table.rowconfigure(0, weight=1)
        search_table.columnconfigure(0, weight=1)
        self.search_tree = ttk.Treeview(search_table, columns=("mod","file","key","value"), show="headings")
        for c, txt, w in (("mod","Mod",260),("file",i18n.t('u3.file'),260),("key",i18n.t('u3.key'),360),("value",i18n.t('u3.japanese_translation'),520)):
            self.search_tree.heading(c, text=txt)
            self.search_tree.column(c, width=w, minwidth=w, stretch=False, anchor="w")
        self.search_tree.bind("<<TreeviewSelect>>", self.on_search_select)
        self._enable_tree_sort(self.search_tree)
        ys = ttk.Scrollbar(search_table, orient="vertical", command=self.search_tree.yview)
        xs = ttk.Scrollbar(search_table, orient="horizontal", command=self.search_tree.xview)
        self.search_tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        self.search_tree.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        self.search_selected_var = tk.StringVar(value=i18n.t('u3.select_result'))
        ttk.Label(right, textvariable=self.search_selected_var, wraplength=420).pack(fill="x", anchor="w")
        self.search_edit_text = tk.Text(right, wrap="word"); self.search_edit_text.pack(fill="both", expand=True, pady=(6,6))
        ttk.Button(right, text=i18n.t('u3.save_japanese'), command=self.save_search_value).pack(anchor="w")
        self.after_idle(self.refresh_translation_search_mods)

    def _build_glossary_tab(self):
        t=self.tab_glossary
        language_bar=ttk.Frame(t); language_bar.pack(fill="x",pady=(0,6))
        ttk.Label(language_bar,text=i18n.t('u4.language')).pack(side="left")
        language_choice=ttk.Combobox(language_bar,textvariable=self.glossary_lang_var,
                                    values=[_target_lang_choice(lang) for lang in core.TARGET_LANGUAGES],state="readonly")
        language_choice.pack(side="left",padx=6)
        language_choice.bind("<<ComboboxSelected>>",lambda event:self.load_glossary_ui(silent=True))
        ttk.Label(t,textvariable=self.glossary_actual_path_var).pack(fill="x",pady=(0,6))
        self.glossary_path_var.trace_add("write",lambda *args:self.glossary_actual_path_var.set(
            i18n.t('u4.language_file', path=_selected_glossary_path(self))))
        top=ttk.LabelFrame(t,text=i18n.t('u4.settings'),padding=8); top.pack(fill="x",pady=(0,6))
        ttk.Label(top,text=i18n.t('u4.file')).pack(side="left")
        ttk.Entry(top,textvariable=self.glossary_path_var).pack(side="left",fill="x",expand=True,padx=6)
        ttk.Button(top,text=i18n.t('u4.load'),command=lambda:self._run_glossary_action(self.load_glossary_ui)).pack(side="left")
        ttk.Button(top,text=i18n.t('u4.save'),command=lambda:self._run_glossary_action(self.save_glossary_ui)).pack(side="left",padx=(6,0))
        ttk.Label(top,textvariable=self.auto_glossary_status_var,foreground="#555").pack(side="right",padx=(8,0))

        import_bar=ttk.Frame(t); import_bar.pack(fill="x",pady=(0,6))
        ttk.Button(import_bar,text=i18n.t('u4.paratranz_import'),
                   command=lambda:self._run_glossary_action(self.import_paratranz_glossary)).pack(side="left")
        ttk.Button(import_bar,text=i18n.t('u4.view_rules'),command=self.show_glossary_notation_rules).pack(side="left",padx=6)
        panes=ttk.Panedwindow(t,orient="horizontal"); panes.pack(fill="both",expand=True)
        manual=ttk.LabelFrame(panes,text=i18n.t('u4.manual_terms'),padding=8)
        generated=ttk.LabelFrame(panes,text=i18n.t('u4.generated_terms'),padding=8)
        panes.add(manual,weight=1); panes.add(generated,weight=1)

        mbar=ttk.Frame(manual); mbar.pack(fill="x",pady=(0,6))
        ttk.Button(mbar,text=i18n.t('u4.add_term'),command=lambda:self._run_glossary_action(self.add_glossary_term)).pack(side="left")
        ttk.Button(mbar,text=i18n.t('u4.edit_selected'),command=lambda:self._run_glossary_action(self.edit_glossary_term)).pack(side="left",padx=(6,0))
        ttk.Button(mbar,text=i18n.t('u4.delete_selected'),command=lambda:self._run_glossary_action(self.delete_glossary_term)).pack(side="left",padx=(6,0))
        ttk.Label(manual,text=i18n.t('u4.manual_help', target_name=i18n.t("lang." + _glossary_language(self))),foreground="#666",wraplength=520,justify="left").pack(fill="x",anchor="w",pady=(0,6))
        self.glossary_tree=ttk.Treeview(manual,columns=("src","dst"),show="headings")
        self.glossary_tree.heading("src",text=i18n.t('u4.source')); self.glossary_tree.heading("dst",text=i18n.t('u4.target_heading', target_name=i18n.t("lang." + _glossary_language(self))))
        self.glossary_tree.column("src",width=260,stretch=True); self.glossary_tree.column("dst",width=300,stretch=True)
        self._enable_tree_sort(self.glossary_tree)
        my=ttk.Scrollbar(manual,orient="vertical",command=self.glossary_tree.yview); mx=ttk.Scrollbar(manual,orient="horizontal",command=self.glossary_tree.xview)
        self.glossary_tree.configure(yscrollcommand=my.set,xscrollcommand=mx.set)
        self.glossary_tree.pack(fill="both",expand=True); mx.pack(fill="x")
        self.glossary_tree.bind("<Double-1>",lambda e:self.edit_glossary_term())

        gbar=ttk.Frame(generated); gbar.pack(fill="x",pady=(0,6))
        self.glossary_base_import_btn=ttk.Button(gbar,text=i18n.t('u4.import_base'),command=self.import_glossary_from_base_game)
        self.glossary_base_import_btn.pack(side="left")
        self.glossary_import_menu=tk.Menu(gbar,tearoff=False)
        self.glossary_import_menu.add_command(label=i18n.t('u4.target_import_yaml', target_name=i18n.t("lang." + _current_target_lang(self))),command=lambda:self.import_glossary_from_japanese_source("file"))
        self.glossary_import_menu.add_command(label=i18n.t('u4.target_import_mod', target_name=i18n.t("lang." + _current_target_lang(self))),command=lambda:self.import_glossary_from_japanese_source("folder"))
        self.glossary_jp_import_btn=ttk.Menubutton(gbar,text=i18n.t('u4.target_import_files', target_name=i18n.t("lang." + _current_target_lang(self))),menu=self.glossary_import_menu)
        self.glossary_jp_import_btn.pack(side="left",padx=(6,0))
        self.glossary_base_help_label=ttk.Label(generated,text=i18n.t('u4.target_base_help', target_name=i18n.t("lang." + _current_target_lang(self))),foreground="#8a5a00",wraplength=560,justify="left")
        self.glossary_base_help_label.pack(fill="x",anchor="w",pady=(0,4))
        self.glossary_generated_help_label=ttk.Label(generated,text=i18n.t('u4.target_generated_help', target_name=i18n.t("lang." + _current_target_lang(self))),foreground="#666",wraplength=560,justify="left")
        self.glossary_generated_help_label.pack(fill="x",anchor="w",pady=(0,4))
        self.auto_glossary_drop_hint=ttk.Label(generated,text=(i18n.t('u4.target_drop_help', target_name=i18n.t("lang." + _current_target_lang(self))) if DND_AVAILABLE else i18n.t('u4.drop_unavailable')),foreground="#555")
        self.auto_glossary_drop_hint.pack(fill="x",anchor="w",pady=(0,6))
        self.auto_glossary_include_phrases_var=tk.BooleanVar(value=False)
        ttk.Checkbutton(generated,text=i18n.t('u4.include_phrases'),variable=self.auto_glossary_include_phrases_var).pack(anchor="w",pady=(0,4))
        filters=ttk.Frame(generated); filters.pack(fill="x",pady=(0,6))
        self.auto_glossary_kind_filter_vars={}
        for term_kind,label in (("proper",i18n.t('u4.proper')),("term",i18n.t('u4.term')),("phrase",i18n.t('u4.phrase'))):
            variable=tk.BooleanVar(value=True)
            self.auto_glossary_kind_filter_vars[term_kind]=variable
            ttk.Checkbutton(filters,text=label,variable=variable,command=self._refresh_auto_glossary_tree).pack(side="left",padx=(0,8))
        self.auto_glossary_tree=ttk.Treeview(generated,columns=("src","dst","kind","term_kind"),show="headings")
        for c,label,w in (("src",i18n.t('u4.source'),250),("dst",i18n.t('u4.target_heading', target_name=i18n.t("lang." + _glossary_language(self))),280),("kind",i18n.t('u4.origin'),140),("term_kind",i18n.t('u4.kind'),90)):
            self.auto_glossary_tree.heading(c,text=label); self.auto_glossary_tree.column(c,width=w,stretch=True)
        self._enable_tree_sort(self.auto_glossary_tree)
        gy=ttk.Scrollbar(generated,orient="vertical",command=self.auto_glossary_tree.yview); gx=ttk.Scrollbar(generated,orient="horizontal",command=self.auto_glossary_tree.xview)
        self.auto_glossary_tree.configure(yscrollcommand=gy.set,xscrollcommand=gx.set)
        self.auto_glossary_tree.pack(fill="both",expand=True); gx.pack(fill="x")
        self.auto_glossary_tree.bind("<Map>",lambda event:self.after_idle(self._refresh_auto_glossary_tree))
        self.glossary_note_var=tk.StringVar(value=i18n.t('u4.note_hint'))
        ttk.Label(t,textvariable=self.glossary_note_var,wraplength=1000,justify="left").pack(fill="x",pady=6)
        for tree in (self.glossary_tree,self.auto_glossary_tree):
            tree.bind("<<TreeviewSelect>>",lambda event:self.show_selected_glossary_note(event.widget))
        if DND_AVAILABLE:
            try:
                self._register_dnd_widgets([generated,self.auto_glossary_drop_hint,self.auto_glossary_tree],self.on_glossary_import_drop_paths)
            except Exception as exc:
                self.auto_glossary_drop_hint.configure(text=i18n.t('u4.dnd_failed', error=exc))
                record_error(i18n.t('u4.dnd_context'),exc)
        self.load_glossary_ui(silent=True)
        self._refresh_auto_glossary_tree()

    def _choose_ui_language(self):
        """画面の言語を保存する。切り替わるのは次に起動したとき（Tk は画面を作るときに文字を入れるため）。"""
        chosen = next((lang for lang, name in i18n.NATIVE_NAMES.items() if name == self.ui_language_var.get()), None)
        if not chosen:
            return
        self.app_preferences["ui_language"] = chosen
        self._save_llm_preferences()
        if chosen != self.ui_language:
            messagebox.showinfo(APP_NAME, i18n.t_lang(chosen, "p0.settings.ui_language_restart"))

    def _build_settings_tab(self):
        t = self.tab_settings
        lang_box = ttk.LabelFrame(t, text=i18n.t("p0.settings.ui_language_frame"), padding=12)
        lang_box.pack(fill="x", pady=(0,12))
        ttk.Label(lang_box, text=i18n.t("p0.settings.ui_language_label")).grid(row=0, column=0, sticky="w")
        ui_combo = ttk.Combobox(lang_box, textvariable=self.ui_language_var, state="readonly", width=22,
                                values=[i18n.NATIVE_NAMES[x] for x in i18n.UI_LANGUAGES])
        ui_combo.grid(row=0, column=1, sticky="w", padx=(8,12))
        ui_combo.bind("<<ComboboxSelected>>", lambda _e: self._choose_ui_language())
        ttk.Label(lang_box, text=i18n.t("p0.settings.ui_language_note"), foreground="#555").grid(row=0, column=2, sticky="w")
        box = ttk.LabelFrame(t, text=i18n.t('u5.storage_frame'), padding=12)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text=i18n.t('u5.storage_folder')).grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.data_root_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8,8))
        self.data_root_change_btn=ttk.Button(box, text=i18n.t('u5.change_storage'), command=self.change_data_root)
        self.data_root_change_btn.grid(row=0, column=2)
        self._data_root_controls=[self.data_root_change_btn]
        ttk.Button(box, text=i18n.t('u5.open_folder'), command=lambda:self._open_path(DATA_ROOT)).grid(row=0, column=3, padx=(6,0))
        ttk.Button(box, text=i18n.t('u5.open_error_logs'), command=lambda:self._open_path(LOG_ROOT)).grid(row=2, column=2, pady=(10,0))
        ttk.Button(box, text=i18n.t('u5.collect_logs'), command=self.collect_error_logs).grid(row=2, column=3, padx=(6,0), pady=(10,0))
        ttk.Label(box, text=i18n.t('u5.storage_note'), wraplength=920, foreground="#555").grid(row=1, column=0, columnspan=4, sticky="w", pady=(10,0))

        close_box = ttk.LabelFrame(t, text=i18n.t('u5.close_behavior'), padding=12)
        close_box.pack(fill="x", pady=(12,0))
        ttk.Label(close_box, text=i18n.t('u5.default_action')).grid(row=0, column=0, sticky="w")
        close_combo = ttk.Combobox(close_box, textvariable=self.close_action_var, state="readonly", width=20,
                                   values=tuple(ui_status.close_action_label(a) for a in ui_status.CLOSE_ACTIONS))
        close_combo.grid(row=0, column=1, sticky="w", padx=(8,12))
        ttk.Label(close_box, text=i18n.t('u5.close_recommendation'), foreground="#555").grid(row=0,column=2,sticky="w")
        ttk.Button(close_box, text=i18n.t('u5.save_setting'), command=self.save_close_behavior_settings).grid(row=0,column=3,padx=(12,0))
        ttk.Label(close_box, text=(
            i18n.t('u5.close_help')
        ), foreground="#555", wraplength=1100, justify="left").grid(row=1,column=0,columnspan=4,sticky="w",pady=(5,0))

        structure = ttk.LabelFrame(t, text=i18n.t('u5.folder_structure'), padding=12)
        structure.pack(fill="both", expand=True, pady=(12,0))
        text = tk.Text(structure, height=16, wrap="none")
        text.pack(fill="both", expand=True)
        text.insert("1.0",
            i18n.t('u5.folder_tree'))
        text.config(state="disabled")

    def change_data_root(self):
        blockers=[name for name in self._active_file_operation_names() if name!="保存場所コピー"]
        if blockers:
            return
        if self.data_root_move_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u5.storage_busy')); return
        old_root=DATA_ROOT
        chosen=filedialog.askdirectory(title=i18n.t('u5.choose_storage'),initialdir=str(old_root.parent if old_root.exists() else Path.home()))
        if not chosen: return
        selected=Path(chosen).expanduser(); new_root=selected if selected.name==DATA_FOLDER_NAME else selected/DATA_FOLDER_NAME
        try:
            if new_root.resolve()==old_root.resolve(): messagebox.showinfo(APP_NAME,i18n.t('u5.same_storage')); return
        except Exception: pass
        if not _is_writable_dir(new_root): messagebox.showerror(APP_NAME,i18n.t('u5.storage_unwritable', new_root=new_root)); return
        ans=messagebox.askyesnocancel(APP_NAME,i18n.t('u5.confirm_storage_change', old_root=old_root, new_root=new_root))
        if ans is None: return
        current_glossary=self.glossary_path_var.get().strip()
        queue_snapshot=[dict(x) if isinstance(x,dict) else x for x in self.queue_items]
        self.progress_text.set(i18n.t('u5.storage_copying') if ans else i18n.t('u5.storage_switching'))
        def work():
            try:
                if ans and old_root.exists(): shutil.copytree(old_root,new_root,dirs_exist_ok=True)
                self.events.put(('data_root_copy_done',(str(old_root),str(new_root),bool(ans),current_glossary,queue_snapshot)))
            except Exception as exc:
                self.events.put(('data_root_copy_error',str(exc)))
        self.data_root_move_thread=threading.Thread(target=work,daemon=True,name='data-root-move'); self.data_root_move_thread.start()
        self._refresh_operation_states()

    def _apply_data_root_change(self, old_root_raw, new_root_raw, copied, current_glossary, queue_snapshot):
        global DATA_ROOT
        self.data_root_move_thread=None
        old_root=Path(old_root_raw); new_root=Path(new_root_raw)
        try:
            _save_data_root_preference(new_root); _configure_data_root(new_root); _organize_existing_logs(LOG_ROOT)
            for i,item in enumerate(self.queue_items):
                if not isinstance(item,dict): continue
                for key in ('cache','output','previous_cache'):
                    raw=item.get(key)
                    if not raw: continue
                    try:
                        rel=Path(raw).expanduser().resolve().relative_to(old_root.resolve()); item[key]=str(DATA_ROOT/rel)
                    except Exception: pass
            self.data_root_var.set(str(DATA_ROOT))
            try:
                rel=Path(current_glossary).expanduser().resolve().relative_to(old_root.resolve()) if current_glossary else None
                self.glossary_path_var.set(str(DATA_ROOT/rel) if rel is not None else str(DEFAULT_GLOSSARY))
            except Exception:
                if not current_glossary or current_glossary==str(old_root/'設定'/'glossary.json'): self.glossary_path_var.set(str(DEFAULT_GLOSSARY))
            self.model_stats=load_persistent_json(STATS_PATH,{},i18n.t('u5.model_stats')); self.model_profiles=load_persistent_json(PROFILES_PATH,{},i18n.t('u5.model_profiles'))
            # Large status cache is intentionally not decoded here; its worker does that.
            self.mod_status_cache={'version':MOD_STATUS_CACHE_VERSION,'items':{}}
            _cls=load_persistent_json(MOD_CLASSIFICATION_CACHE_PATH,{'schema':2,'mods':{}},i18n.t('u5.classification_cache')); _cls=_cls if isinstance(_cls,dict) else {'schema':2,'mods':{}}
            self.mod_classification_cache={'schema':2,'mods':dict(_cls.get('mods') or {}),'updated_at':_cls.get('updated_at','')}
            _ov=load_persistent_json(MOD_RELATION_OVERRIDES_PATH,{'schema':1,'mods':{}},i18n.t('u5.relation_settings')); _ov=_ov if isinstance(_ov,dict) else {'schema':1,'mods':{}}
            self.mod_relation_overrides={'schema':1,'mods':dict(_ov.get('mods') or {}),'languages':dict(_ov.get('languages') or {}),'updated_at':_ov.get('updated_at','')}
            self._restore_shared_mod_state_cache(); self.refresh_profiles_ui(); self._restore_cached_mod_status(); self._restore_diagnostic_state(); self._refresh_backup_restore_entries()
            self.progress_text.set(i18n.t('u5.storage_changed'))
            if not self._closing:
                messagebox.showinfo(APP_NAME,i18n.t('u5.storage_changed_copy', root=str(DATA_ROOT)) if copied else i18n.t('u5.storage_changed_new', root=str(DATA_ROOT)))
        except Exception as exc:
            record_error(i18n.t('u5.storage_apply_error'),exc); messagebox.showerror(APP_NAME,i18n.t('u5.storage_failed', exc=exc))

    def save_close_behavior_settings(self, silent=False):
        """Save the single × button behavior setting."""
        self._save_llm_preferences()
        if not silent:
            messagebox.showinfo(
                APP_NAME,
                i18n.t('p0.close_button_behavior_saved_action', value=self.close_action_var.get())
            )
        return True

    def _show_close_choice_dialog(self):
        """Return 'minimize', 'quit' or 'cancel'."""
        dlg = tk.Toplevel(self)
        dlg.title(i18n.t('p0.close_the_app'))
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        result = {"action": "cancel"}
        active_translation = bool(self.worker and self.worker.is_alive())
        active_monitor = bool(self.monitor_thread and self.monitor_thread.is_alive())

        frame = ttk.Frame(dlg, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=i18n.t('p0.the_close_button_was_pressed'), font=("", 14, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                i18n.t('p0.minimize_the_window_or_quit')
            ),
            justify="left", wraplength=560
        ).pack(anchor="w", pady=(10, 10))
        if active_translation or active_monitor:
            running = []
            if active_translation: running.append(i18n.t('p0.translation'))
            if active_monitor: running.append(i18n.t('p0.mod_discovery_monitoring'))
            ttk.Label(frame, text=i18n.t('p0.currently_running', value=" / ".join(running)), foreground="#a35a00").pack(anchor="w", pady=(0,8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        def choose(action):
            result["action"] = action
            dlg.destroy()
        ttk.Button(buttons, text=i18n.t('p0.minimize'), command=lambda: choose("minimize")).pack(side="left")
        ttk.Button(buttons, text=i18n.t('p0.quit'), command=lambda: choose("quit")).pack(side="left", padx=(8,0))
        ttk.Button(buttons, text=i18n.t('p0.cancel'), command=lambda: choose("cancel")).pack(side="right")
        dlg.protocol("WM_DELETE_WINDOW", lambda: choose("cancel"))
        dlg.update_idletasks()
        try:
            x = self.winfo_rootx() + max(0, (self.winfo_width() - dlg.winfo_width()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - dlg.winfo_height()) // 2)
            dlg.geometry(f"+{x}+{y}")
        except Exception:
            pass
        self.wait_window(dlg)
        return result["action"]

    def _save_exit_state(self):
        """Persist recoverable state before requesting worker shutdown."""
        self._save_llm_preferences()
        self._save_translation_status_state("app_exit")
        self._save_diagnostic_state("app_exit")
        self._save_shared_mod_state_cache("app_exit")
        self._save_workspace_state("app_exit")
        running=bool(self.worker and self.worker.is_alive())
        unfinished=any(not self._queue_item_is_completed(item) for item in self.queue_items)
        if running:
            self._write_session_file(active=True,restore_on_launch=True)
        elif self.queue_items and unfinished:
            self._write_session_file(active=False,restore_on_launch=True)
        else:
            self._delete_session()

    def _request_worker_shutdown(self):
        self.monitor_stop_event.set()
        self.mod_research_stop_event.set()
        controllers = (
            (self.controller, True),
            (self.chinese_controller, True),
            (getattr(self,"qa_repair_controller",None), False),
            (self.monitor_llm_controller, False),
            (self.benchmark_controller, False),
            (self.proofread_controller, False),
            (self.diff_controller, False),
            (self.auto_glossary_controller, False),
        )
        for controller, save in controllers:
            if controller:
                try:
                    controller.request_stop(save=save)
                except Exception as exc:
                    record_error(i18n.t('p0.shutdown_stop_request'),exc)

    def _active_shutdown_threads(self):
        checks = (
            (i18n.t('p0.standard_translation'), self.worker),
            ("中国語基準翻訳", self.chinese_worker),
            (i18n.t('p0.continuous_monitoring'), self.monitor_thread),
            (i18n.t('p0.mod_scan'), self.mod_research_thread),
            (i18n.t('p0.preparing_missing_only_translation'), self.differential_prepare_thread),
            (i18n.t('p0.single_overwrite'), self.single_overwrite_thread),
            (i18n.t('p0.bulk_overwrite'), self.bulk_overwrite_thread),
            (i18n.t('p0.restore_backup'), self.backup_restore_operation_thread),
            ("保存場所コピー", self.data_root_move_thread),
            (i18n.t('p0.full_diagnostics_and_repair'), self.diagnostic_thread),
            (i18n.t('p0.import_glossary'), self.glossary_import_thread),
            (i18n.t('p0.model_speed_test'), getattr(self,"benchmark_worker",None)),
            (i18n.t('p0.translation_search'), self.search_thread),
            (i18n.t('p0.qa_analysis'), self.review_worker),
            (i18n.t('p0.qa_and_auto_fix'), getattr(self,"qa_repair_thread",None)),
            (i18n.t('p0.llm_connection_check'), getattr(self,"llm_preflight_thread",None)),
            (i18n.t('p0.difference_analysis'), self.diff_load_worker),
            ("差分翻訳", self.diff_translate_thread),
            (i18n.t('p0.ai_proofreading'), self.proofread_thread),
            (i18n.t('p0.auto_glossary'), self.auto_glossary_thread),
        )
        return [(name,thread) for name,thread in checks if self._operation_pending(thread)]

    def _begin_graceful_exit(self):
        if self._closing:
            return
        self._closing=True
        self._shutdown_wait_started=time.monotonic()
        self._shutdown_prompted_at=0.0
        self._save_exit_state()
        self._request_worker_shutdown()
        self._refresh_operation_states()
        self._disable_all_interactive_controls()
        active=self._active_shutdown_threads()
        if not active:
            self._finalize_app_exit(force=False)
            return
        names=" / ".join(name for name,_thread in active)
        self.progress_text.set(i18n.t('p0.preparing_to_exit_waiting_for'))
        self.chinese_progress_var.set(i18n.t('p0.preparing_to_exit_waiting_for'))
        self.title(i18n.t('p0.preparing_to_exit', APP_NAME=APP_NAME, APP_VERSION=APP_VERSION))
        self.after(100,self._poll_shutdown_completion)

    def _poll_shutdown_completion(self):
        if not self._closing:
            return
        active=self._active_shutdown_threads()
        if not active:
            self._finalize_app_exit(force=False)
            return
        now=time.monotonic()
        names=" / ".join(name for name,_thread in active)
        self.progress_text.set(i18n.t('p0.preparing_to_exit_2', names=names))
        if now-self._shutdown_wait_started >= 10 and now-self._shutdown_prompted_at >= 10:
            self._shutdown_prompted_at=now
            force=messagebox.askyesno(
                APP_NAME,
                i18n.t('p0.waiting_for_saves_or_workers', names=names),
                icon="warning",
            )
            if force:
                self._finalize_app_exit(force=True)
                return
        self.after(100,self._poll_shutdown_completion)

    def _finalize_app_exit(self, force=False):
        """Destroy Tk only after workers stopped; forced exits remain marked unclean."""
        if not force:
            self._save_exit_state()
            _mark_runtime_clean_exit()
        else:
            record_error(i18n.t('p0.force_quit'),detail=i18n.t('p0.the_user_chose_to_force'))

        try:
            if self._fatal_log_handle:
                self._fatal_log_handle.flush()
        except Exception:
            pass
        self.destroy()

    def apply_performance_preset(self):
        """バッチサイズと並列数の安全側プリセットを適用する。

        Paradox localization は1行の長さが一定ではないため、数値は絶対的な
        上限ではなく実用上の目安。特にローカルLLMではサーバー側の並列設定と
        メモリ容量に左右される。
        """
        name = self.performance_preset_var.get()
        preset_id = ui_status.performance_preset_from_label(name)
        batch, workers = ui_status.PERFORMANCE_PRESETS[preset_id]
        self.batch_var.set(batch)
        self.workers_var.set(workers)
        note = {
            "stable": i18n.t('u5.stable_note'),
            "standard": i18n.t('u5.standard_note'),
            "fast": i18n.t('u5.fast_note'),
        }.get(preset_id, "")
        messagebox.showinfo(
            i18n.t('u5.recommended_settings'),
            i18n.t('u5.preset_applied', name=name, batch=batch, workers=workers, note=note)
        )

    def _build_help_tab(self):
        t = self.tab_help
        title = ttk.Label(t, text=i18n_help.help_title(self.ui_language), font=("", 18, "bold"))
        title.pack(anchor="w", pady=(0, 10))
        box = tk.Text(t, wrap="word", padx=12, pady=12)
        box.pack(fill="both", expand=True)
        guide = i18n_help.help_text(self.ui_language)
        box.insert("1.0", guide)
        box.config(state="disabled")

    def _make_vertical_scroll_area(self, parent):
        """親領域全体を縦スクロールできるCanvas+Frameとして返す。"""
        outer = ttk.Frame(parent)
        canvas = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background=self.cget("background"))
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        def update_scrollregion(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        def fit_inner_width(event):
            canvas.itemconfigure(window_id, width=event.width)
            update_scrollregion()

        inner.bind("<Configure>", update_scrollregion, add="+")
        canvas.bind("<Configure>", fit_inner_width, add="+")
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return outer, inner, canvas, scrollbar

    def _build_monitor_tab(self):
        t = self.tab_monitor

        # 未翻訳監視は監視そのものに専念する。Mod場所の検出・調査は「翻訳状況」へ集約。
        body = ttk.Panedwindow(t, orient="horizontal")
        body.pack(fill="both", expand=True)
        left_outer, left, self.monitor_left_canvas, self.monitor_left_scrollbar = self._make_vertical_scroll_area(body)
        right = ttk.Frame(body)
        body.add(left_outer, weight=1)
        body.add(right, weight=1)

        def _balance_monitor_panes(event=None):
            try:
                total = max(body.winfo_width(), 200)
                body.sashpos(0, max(320, total // 2))
            except Exception:
                pass
        body.bind("<Configure>", _balance_monitor_panes, add="+")
        self.after_idle(_balance_monitor_panes)

        target = ttk.LabelFrame(left, text=i18n.t('u6.monitor_targets'), padding=8)
        target.pack(fill="x", pady=(0,8))
        ttk.Label(target, textvariable=self.monitor_target_summary_var, wraplength=470, justify="left").pack(anchor="w")
        ttk.Label(target, text=i18n.t('u6.add_or_change_targets_and_research'), foreground="#666", wraplength=470, justify="left").pack(anchor="w", pady=(5,0))
        ttk.Button(target, text=i18n.t('u6.open_translation_status'), command=lambda:self.notebook.select(self.tab_status)).pack(anchor="w", pady=(7,0))

        cfg = ttk.LabelFrame(left, text=i18n.t('u6.untranslated_monitor_settings'), padding=8)
        cfg.pack(fill="x", pady=(0,8))
        cfg.columnconfigure(1, weight=1)
        ttk.Label(cfg, text=i18n.t('u6.interval_seconds')).grid(row=0, column=0, sticky="w")
        ttk.Spinbox(cfg, from_=3, to=600, textvariable=self.monitor_interval_var, width=7).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Separator(cfg, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=7)
        ttk.Label(cfg, text=i18n.t('u6.monitor_llm'), font=("", 10, "bold")).grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Label(cfg, text=i18n.t('u6.provider')).grid(row=3, column=0, sticky="w", pady=(5,0))
        self.monitor_provider_combo = ttk.Combobox(
            cfg, textvariable=self.monitor_provider_var,
            values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],
            state="readonly", width=15)
        self.monitor_provider_combo.grid(row=3, column=1, sticky="ew", padx=6, pady=(5,0))
        self.monitor_provider_combo.bind("<<ComboboxSelected>>", lambda e:self.on_monitor_provider_change())
        ttk.Button(cfg, text=i18n.t('u6.reload_models'), command=self.refresh_monitor_models).grid(row=3, column=2, pady=(5,0))
        ttk.Label(cfg, text="URL").grid(row=4, column=0, sticky="w", pady=(5,0))
        ttk.Entry(cfg, textvariable=self.monitor_url_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, text=i18n.t('u6.model')).grid(row=5, column=0, sticky="w", pady=(5,0))
        self.monitor_model_combo = ttk.Combobox(cfg, textvariable=self.monitor_model_var, state="normal")
        self.monitor_model_combo.grid(row=5, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, text=i18n.t('u6.api_key')).grid(row=6, column=0, sticky="w", pady=(5,0))
        ttk.Entry(cfg, textvariable=self.monitor_api_key_var, show="•").grid(row=6, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, textvariable=self.monitor_connection_var, foreground="#555", wraplength=460, justify="left").grid(row=7, column=0, columnspan=3, sticky="w", pady=(5,0))
        ttk.Checkbutton(cfg, text=i18n.t('u6.review_ambiguous_candidates_with_a_lightweight'), variable=self.monitor_use_llm_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(5,0))
        ttk.Checkbutton(cfg, text=i18n.t('u6.also_search_other_mods_for_japanese', target_name=i18n.t("lang." + 'japanese')), variable=self.monitor_check_translation_mods_var).grid(row=9, column=0, columnspan=3, sticky="w", pady=(3,0))
        ttk.Label(cfg, text=i18n.t('u6.use_a_small_model_3b_8b'), foreground="#8a4b00", wraplength=460, justify="left").grid(row=10, column=0, columnspan=3, sticky="w", pady=(5,0))

        controls = ttk.LabelFrame(left, text=i18n.t('u6.monitor_controls'), padding=8)
        controls.pack(fill="x")
        r1=ttk.Frame(controls); r1.pack(fill="x")
        self.monitor_toggle_btn = ttk.Button(r1, text=i18n.t('u6.start_continuous_monitoring'), command=self.toggle_monitor)
        self.monitor_toggle_btn.pack(side="left")
        ttk.Button(r1, text=i18n.t('u6.research_again'), command=self.research_monitor_targets).pack(side="left", padx=(6,0))
        self.mod_research_stop_btn = ttk.Button(r1, text=i18n.t('u6.stop_research'), command=self.stop_mod_research, state="disabled")
        self.mod_research_stop_btn.pack(side="left", padx=(6,0))
        ttk.Label(controls, textvariable=self.monitor_status_var, wraplength=460, justify="left").pack(anchor="w", pady=(6,0))

        result_top = ttk.Frame(right); result_top.pack(fill="x", pady=(0,6))
        ttk.Label(result_top, text=i18n.t('u6.untranslated_candidates'), font=("", 12, "bold")).pack(side="left")
        ttk.Label(result_top, textvariable=self.monitor_summary_var, font=("", 11, "bold")).pack(side="left", padx=(12,0))
        ttk.Button(result_top, text=i18n.t('u6.clear_candidates'), command=self.clear_monitor_results).pack(side="right")
        ttk.Button(result_top, text=i18n.t('u6.save_csv'), command=self.export_monitor_csv).pack(side="right", padx=(0,6))

        result_frame = ttk.Frame(right); result_frame.pack(fill="both", expand=True)
        cols=("kind","confidence","file","key","text")
        self.monitor_tree=ttk.Treeview(result_frame, columns=cols, show="headings", height=18)
        for c,txt,w in (("kind",i18n.t('u6.type'),130),("confidence",i18n.t('u6.assessment'),75),("file",i18n.t('u6.file'),280),("key",i18n.t('u6.key'),280),("text",i18n.t('u6.content'),450)):
            self.monitor_tree.heading(c,text=txt); self.monitor_tree.column(c,width=w,anchor="w")
        sy=ttk.Scrollbar(result_frame,orient="vertical",command=self.monitor_tree.yview)
        sx=ttk.Scrollbar(result_frame,orient="horizontal",command=self.monitor_tree.xview)
        self._enable_tree_sort(self.monitor_tree)
        self.monitor_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.monitor_tree.grid(row=0,column=0,sticky="nsew")
        sy.grid(row=0,column=1,sticky="ns")
        sx.grid(row=1,column=0,sticky="ew")
        result_frame.rowconfigure(0,weight=1); result_frame.columnconfigure(0,weight=1)

        note = ttk.LabelFrame(right, text=i18n.t('u6.how_it_works'), padding=6); note.pack(fill="x", pady=(6,0))
        ttk.Label(note, text=i18n.t('u6.while_idle_only_yaml_modification_times'), wraplength=650, justify="left").pack(anchor="w")

    def _build_status_tab(self):
        t = self.tab_status
        top = ttk.Frame(t); top.pack(fill="x", pady=(0,6))
        ttk.Label(top, text=i18n.t('u6.japanese_translation_status_by_mod', target_name=i18n.t("lang." + _current_target_lang(self))), font=("", 13, "bold")).pack(side="left")
        ttk.Label(top, text=_relation_scope_text(_current_target_lang(self)), foreground="#8a5a00").pack(side="left", padx=(8,0))
        ttk.Label(top, textvariable=self.mod_status_summary_var).pack(side="right")

        # フルHDでも縦方向が苦しくなりにくいよう、左に設定系、右に結果系を置く。
        body = ttk.Panedwindow(t, orient="horizontal")
        body.pack(fill="both", expand=True)
        left_outer, left, self.status_left_canvas, self.status_left_scrollbar = self._make_vertical_scroll_area(body)
        right_outer, right, self.status_right_canvas, self.status_right_scrollbar = self._make_vertical_scroll_area(body)
        body.add(left_outer, weight=2)
        body.add(right_outer, weight=5)

        discovery = ttk.LabelFrame(left, text=i18n.t('u6.game_mod_location'), padding=6); discovery.pack(fill="x", pady=(0,6))
        dbar1 = ttk.Frame(discovery); dbar1.pack(fill="x", pady=(0,5))
        ttk.Button(dbar1, text=i18n.t('u6.detect_game_mod_locations'), command=self.discover_mod_locations).pack(side="left")
        ttk.Button(dbar1, text=i18n.t('u6.research_mods_in_selected_locations'), command=self.research_selected_discovered_location).pack(side="left", padx=(6,0))
        ttk.Label(dbar1, textvariable=self.mod_discovery_status_var).pack(side="right")
        dbar2 = ttk.Frame(discovery); dbar2.pack(fill="x", pady=(0,5))
        ttk.Checkbutton(dbar2, text=i18n.t('u6.multi_select_mode'), variable=self.discovery_multi_select_var).pack(side="left")
        ttk.Button(dbar2, text=i18n.t('u6.select_all'), command=self.select_all_discovered_locations).pack(side="left", padx=(6,0))
        ttk.Button(dbar2, text=i18n.t('u6.deselect_all'), command=lambda:self.discovered_mod_tree.selection_remove(self.discovered_mod_tree.selection())).pack(side="left", padx=(6,0))
        cols=("game","kind","mods","path")
        treewrap = ttk.Frame(discovery); treewrap.pack(fill="both", expand=True)
        self.discovered_mod_tree=ttk.Treeview(treewrap, columns=cols, show="headings", height=6, selectmode="extended")
        self._enable_ctrl_multiselect(self.discovered_mod_tree)
        self.discovered_mod_tree.bind("<Button-1>", self._on_discovery_tree_click, add="+")
        self.discovered_mod_tree.bind("<<TreeviewSelect>>", lambda e:self._sync_monitor_targets_from_discovery_selection(), add="+")
        for c,txt,w in (("game",i18n.t('u6.game'),180),("kind",i18n.t('u6.type'),125),("mods",i18n.t('u6.mods'),70),("path",i18n.t('u6.detected_location'),650)):
            self.discovered_mod_tree.heading(c,text=txt)
            self.discovered_mod_tree.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        self._enable_tree_sort(self.discovered_mod_tree)
        dsy=ttk.Scrollbar(treewrap,orient="vertical",command=self.discovered_mod_tree.yview)
        dsx=ttk.Scrollbar(treewrap,orient="horizontal",command=self.discovered_mod_tree.xview)
        self.discovered_mod_tree.configure(yscrollcommand=dsy.set,xscrollcommand=dsx.set)
        self.discovered_mod_tree.grid(row=0,column=0,sticky="nsew")
        dsy.grid(row=0,column=1,sticky="ns")
        dsx.grid(row=1,column=0,sticky="ew")
        treewrap.rowconfigure(0,weight=1); treewrap.columnconfigure(0,weight=1)
        ttk.Label(discovery, text=i18n.t('u6.ctrl_click_to_select_multiple_locations'), foreground="#666", wraplength=330, justify="left").pack(anchor="w", pady=(4,0))

        search = ttk.LabelFrame(left, text=i18n.t('u6.search_assessed_mods'), padding=6); search.pack(fill="x", pady=(0,6))
        ttk.Label(search, text=i18n.t('u6.mod_name')).grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search, textvariable=self.mod_status_search_var, width=28)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6,6))
        search_entry.bind("<Return>", lambda e:self.search_mod_status())
        search_entry.bind("<KeyRelease>", self._schedule_mod_status_search)
        ttk.Button(search, text=i18n.t('u6.search'), command=self.search_mod_status).grid(row=0, column=2)
        ttk.Button(search, text=i18n.t('u6.clear'), command=self.clear_mod_status_search).grid(row=0, column=3, padx=(6,0))
        ttk.Label(search, textvariable=self.mod_status_search_result_var, foreground="#555", wraplength=300, justify="left").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6,0))
        search.columnconfigure(1, weight=1)

        relation = ttk.LabelFrame(left, text=i18n.t('u6.mod_classification_and_linking'), padding=6); relation.pack(fill="x", pady=(0,6))
        ttk.Label(relation, text=i18n.t('u6.set_translation_mod_source_mod_exceptions', target_name=i18n.t("lang." + _current_target_lang(self))), foreground="#555", wraplength=320, justify="left").pack(anchor="w")
        ttk.Button(relation, text=i18n.t('u6.open_mod_classification_and_linking'), command=lambda:self._open_mod_relation_dialog("status")).pack(anchor="w", pady=(6,0))

        # 翻訳状況タブから探索専用LLMをそのまま変更・適用できる。
        moncfg = ttk.LabelFrame(left, text=i18n.t('u6.research_llm_settings'), padding=6); moncfg.pack(fill="x", pady=(0,6))
        ttk.Label(moncfg, text=i18n.t('u6.provider')).grid(row=0,column=0,sticky="w")
        cmb=ttk.Combobox(moncfg,textvariable=self.monitor_provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=12)
        cmb.grid(row=0,column=1,padx=(5,8),sticky="ew"); cmb.bind("<<ComboboxSelected>>",lambda e:self.on_monitor_provider_change())
        ttk.Label(moncfg,text="URL").grid(row=1,column=0,sticky="w", pady=(6,0))
        ttk.Entry(moncfg,textvariable=self.monitor_url_var,width=26).grid(row=1,column=1,columnspan=2,sticky="ew",padx=(5,8), pady=(6,0))
        ttk.Label(moncfg,text=i18n.t('u6.model')).grid(row=2,column=0,sticky="w", pady=(6,0))
        self.status_monitor_model_combo=ttk.Combobox(moncfg,textvariable=self.monitor_model_var,state="normal",width=24)
        self.status_monitor_model_combo.grid(row=2,column=1,columnspan=2,sticky="ew",padx=(5,8), pady=(6,0))
        btnrow = ttk.Frame(moncfg); btnrow.grid(row=3,column=0,columnspan=3,sticky="ew", pady=(8,0))
        ttk.Button(btnrow,text=i18n.t('u6.reload_model_list'),command=self.refresh_monitor_models).pack(side="left")
        ttk.Button(btnrow,text=i18n.t('u6.apply_research_settings'),command=self.apply_monitor_settings).pack(side="left", padx=(6,0))
        moncfg.columnconfigure(1,weight=1); moncfg.columnconfigure(2,weight=1)
        ttk.Label(moncfg,text=i18n.t('u6.reloading_only_retrieves_the_model_list'),foreground="#a35a00",wraplength=320,justify="left").grid(row=4,column=0,columnspan=3,sticky="w",pady=(6,0))

        info = ttk.LabelFrame(left, text=i18n.t('u6.assessment_details'), padding=6); info.pack(fill="x", pady=(0,6))
        ttk.Label(info,text=i18n.t('u6.check_source_mods_and_separate_translation', target_name=i18n.t("lang." + _current_target_lang(self))),justify="left",wraplength=320).pack(anchor="w")

        guide = ttk.LabelFrame(left, text=i18n.t('u6.selection_and_actions'), padding=6); guide.pack(fill="both", expand=True)
        ttk.Label(guide, text=i18n.t('u6.tip_hold_ctrl_to_select_multiple'), foreground="#666", justify="left", wraplength=320).pack(anchor="w")

        ttk.Label(right, textvariable=self.mod_status_game_filter_var, foreground="#315b8a").pack(fill="x", pady=(0,4))
        content = ttk.Panedwindow(right, orient="vertical"); content.pack(fill="x", expand=False)
        tree_frame=ttk.Frame(content); detail_frame=ttk.Frame(content)
        content.add(tree_frame, weight=6); content.add(detail_frame, weight=2)
        cols=("status","mod","gaps","chinese","jpmod","jpmod_gaps")
        self.mod_status_tree=ttk.Treeview(tree_frame, columns=cols, show="headings", height=16, selectmode="extended")
        self._enable_ctrl_multiselect(self.mod_status_tree)
        # v0.11.2: 翻訳状況一覧は列幅を固定し、表示領域に合わせて潰さない。
        # 長いMod名・日本語化Mod名は下部の横スクロールバーで確認する。
        for c,txt,w in (("status",i18n.t('u6.status'),165),("mod","Mod",430),("gaps",i18n.t('u6.gaps'),80),("chinese",i18n.t('u6.chinese'),90),("jpmod",i18n.t('u6.translation_mod', target_name=i18n.t("lang." + _current_target_lang(self))),430),("jpmod_gaps",i18n.t('u6.translation_mod_gaps', target_name=i18n.t("lang." + _current_target_lang(self))),150)):
            self.mod_status_tree.heading(c,text=txt)
            self.mod_status_tree.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        sy=ttk.Scrollbar(tree_frame,orient="vertical",command=self.mod_status_tree.yview)
        sx=ttk.Scrollbar(tree_frame,orient="horizontal",command=self.mod_status_tree.xview)
        self.mod_status_tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        # pack順の影響で縦バーが下端へ押し出されることがあったため、gridで位置を固定する。
        tree_frame.columnconfigure(0,weight=1)
        tree_frame.rowconfigure(0,weight=1)
        self.mod_status_tree.grid(row=0,column=0,sticky="nsew")
        sy.grid(row=0,column=1,sticky="ns")
        sx.grid(row=1,column=0,sticky="ew")
        self.mod_status_tree.bind("<<TreeviewSelect>>", self._on_mod_status_selection_changed)
        self.mod_status_tree.tag_configure("empty", foreground="#777777")
        self._enable_tree_sort(self.mod_status_tree)

        detail = ttk.LabelFrame(detail_frame, text=i18n.t('u6.selected_mod_details'), padding=6); detail.pack(fill="both",expand=True,pady=(4,0))
        self.mod_status_detail = tk.Text(detail, height=7, wrap="word", relief="flat", background=self.cget("background"))
        self.mod_status_detail.pack(fill="both", expand=True)
        self.mod_status_detail.insert("1.0", i18n.t('u6.select_a_mod_to_see_research', target_name=i18n.t("lang." + _current_target_lang(self))))
        self.mod_status_detail.configure(state="disabled")

        bottom=ttk.Frame(right); bottom.pack(fill="x", pady=(4,0))
        bottom1=ttk.Frame(bottom); bottom1.pack(fill="x")
        bottom2=ttk.Frame(bottom); bottom2.pack(fill="x", pady=(4,0))
        self.status_selection_action_buttons=[]
        self.status_research_selected_btn=ttk.Button(bottom1,text=i18n.t('u6.research_selected_mods_only'),command=self.research_selected_status_mods,state="disabled")
        self.status_research_selected_btn.pack(side="left"); self.status_selection_action_buttons.append(self.status_research_selected_btn)
        self.status_normal_queue_btn=ttk.Button(bottom1,text=i18n.t('u6.add_to_translation_queue'),command=lambda:self.queue_selected_mod_from_status(start_now=False),state="disabled")
        self.status_normal_queue_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_normal_queue_btn)
        self.status_chinese_queue_btn = ttk.Button(bottom1,text=i18n.t('u6.add_to_chinese_based_queue'),command=self.queue_selected_mods_to_chinese_basis,state="disabled")
        self.status_chinese_queue_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_chinese_queue_btn)
        self.status_except_normal_btn=ttk.Button(bottom1,text=i18n.t('u6.add_to_translation_queue_excluding_selected'),command=self.queue_all_except_selected_mods,state="disabled")
        self.status_except_normal_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_except_normal_btn)
        self.status_except_chinese_btn=ttk.Button(bottom1,text=i18n.t('u6.add_to_chinese_based_queue_excluding'),command=self.queue_all_except_selected_mods_chinese,state="disabled")
        self.status_except_chinese_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_except_chinese_btn)

        self.status_qa_btn=ttk.Button(bottom2,text=i18n.t('u6.open_qa_comparison_editor'),command=lambda:self._send_pair_to_qa_or_diff("status","review"),state="disabled")
        self.status_qa_btn.pack(side="left"); self.status_selection_action_buttons.append(self.status_qa_btn)
        self.status_diff_btn=ttk.Button(bottom2,text=i18n.t('u6.open_difference_research'),command=lambda:self._send_pair_to_qa_or_diff("status","diff"),state="disabled")
        self.status_diff_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_diff_btn)
        self.status_overwrite_btn = ttk.Button(bottom2,text=i18n.t('u6.overwrite_mod_with_completed_translation', target_name=i18n.t("lang." + _current_target_lang(self))),command=self.overwrite_selected_status_mod,state="disabled")
        self.status_overwrite_btn.pack(side="left",padx=(6,0)); self.status_selection_action_buttons.append(self.status_overwrite_btn)
        ttk.Separator(bottom2,orient="vertical").pack(side="left",fill="y",padx=8)
        ttk.Button(bottom2,text=i18n.t('u6.show_assessment_log'),command=self.show_translation_judgement_log).pack(side="left")
        ttk.Button(bottom2,text=i18n.t('u6.export_assessment_log'),command=self.export_translation_judgement_log).pack(side="left",padx=(6,0))
        ttk.Button(bottom2,text=i18n.t('u6.export_link_report'),command=self.export_relation_report).pack(side="left",padx=(6,0))
        ttk.Separator(bottom2,orient="vertical").pack(side="left",fill="y",padx=8)
        ttk.Button(bottom2,text=i18n.t('u6.clear_results'),command=self.clear_mod_status_results).pack(side="left")
        ttk.Button(bottom2,text=i18n.t('u6.reload_cache'),command=self._restore_cached_mod_status).pack(side="left",padx=(6,0))
        ttk.Button(bottom2,text=i18n.t('u6.save_csv'),command=self.export_mod_status_csv).pack(side="left",padx=(6,0))

    def _translation_judgement_log_text(self, *, target_lang=None):
        """Build a human-readable audit snapshot of Japanese-Mod judgement state."""
        target_lang = target_lang or _current_target_lang(self)
        if target_lang != "japanese":
            return self._target_translation_judgement_log_text(target_lang)
        rows = [dict(r) for r in (self.mod_research_results or []) if r.get("path")]
        if not rows:
            return i18n.t('u6.no_translation_status_results_research_mods')

        roots=[]; seen=set()
        for r in rows:
            p=Path(r.get("path", ""))
            if not p.exists():
                continue
            try: key=str(p.resolve())
            except Exception: key=str(p)
            if key not in seen:
                seen.add(key); roots.append(p)

        # Audit candidates intentionally use *currently present* Japanese localization,
        # not only the stable first-seen candidate list.  This lets the log expose a
        # false negative caused by sticky initial classification instead of hiding it.
        japanese_roots=[]
        for root in roots:
            try:
                ov=self._mod_relation_override(root, target_lang=target_lang)
                if self._current_mod_has_japanese(root, target_lang=target_lang) or ov.get("role") in ("translation","source"):
                    japanese_roots.append(root)
            except Exception:
                continue
        audit_index=core.build_translation_mod_index(japanese_roots, target_lang=target_lang)
        self._annotate_translation_index_with_base_game_keys(audit_index)
        for row in audit_index:
            ov=self._mod_relation_override(Path(row.get("path","")), target_lang=target_lang)
            row["manual_role"]=ov.get("role","auto")
            row["manual_source_paths"]=list(ov.get("source_paths") or [])
        audit_index=core.assign_translation_candidate_owners(roots,audit_index, target_lang=target_lang)
        audit_by_path={}
        for row in audit_index:
            try: key=self._mod_classification_key(Path(row.get("path","")))
            except Exception: key=str(row.get("path",""))
            audit_by_path[key]=row

        generated=datetime.now().isoformat(timespec="seconds")
        out=[
            i18n.t('u6.v_translation_mod_assessment_log', app_name=APP_NAME, app_version=APP_VERSION, target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.generated', generated=generated),
            i18n.t('u6.mods_researched_currently_accessible_audit_candidates', target_name=i18n.t("lang." + target_lang), rows_count=len(rows), roots_count=len(roots), audit_index_count=len(audit_index)),
            "",
            i18n.t('u6.assessment_criteria'),
            i18n.t('u6.vanilla_carryover_keys_identical_to_the'),
            i18n.t('u6.100_effective_keys_at_least_200'),
            i18n.t('u6.fewer_than_100_effective_keys_at'),
            i18n.t('u6.candidate_keys_with_source_text_in'),
            i18n.t('u6.80_bundled_source_text_indicates_a', target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.50_candidate_keys_and_80_base', target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.multi_mod_translations_use_a_separate'),
            i18n.t('u6.structure_scores_names_and_dependencies_are'),
            i18n.t('u6.manual_translation_mod_source_mod_source', target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.legacy_japanese_translations_in_l_english', target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.identical_relative_localization_paths_in_effective'),
            i18n.t('u6.the_same_path_translation_related_names', target_name=i18n.t("lang." + target_lang)),
            i18n.t('u6.the_audit_also_compares_current_japanese', target_name=i18n.t("lang." + target_lang)),
            "",
        ]
        class_label={"auto":i18n.t('u6.translation_mod', target_name=i18n.t("lang." + target_lang)),"candidate":i18n.t('u6.candidate'),"rejected":i18n.t('u6.excluded')}
        for num,r in enumerate(rows,1):
            root=Path(r.get("path","")); name=r.get("mod") or root.name
            try: source_id=self._mod_classification_key(root)
            except Exception: source_id=str(root)
            out += ["="*78, i18n.t('u6.source_mod', num=num, name=name), i18n.t('u6.location', root=root), i18n.t('u6.current_translation_status', status=display_status(r))]
            if r.get("external_translation_mod"):
                out.append(i18n.t('u6.current_link_translation_mod', external_translation_mod=r.get('external_translation_mod'), target_name=i18n.t("lang." + target_lang)))
            elif r.get("translation_candidate_mod"):
                out.append(i18n.t('u6.current_link_candidate_not_linked_automatically', translation_candidate_mod=r.get('translation_candidate_mod')))
            else:
                out.append(i18n.t('u6.current_link_none'))
            try:
                source_loc=core.mod_localization_root(root)
                japanese_rels=[]
                if source_loc:
                    for fp in core.gather_yml_files(source_loc):
                        try:
                            lang,_entries,_lines=core.parse_localization_file(fp)
                            rel=fp.relative_to(source_loc)
                            if lang=="japanese":
                                expected=rel
                            elif lang in {"english","simp_chinese"}:
                                expected=(core.remap_rel_dir(rel.parent,"japanese") /
                                          core.rename_for_target(fp,"japanese",lang))
                            else:
                                continue
                            if expected not in japanese_rels: japanese_rels.append(expected)
                        except Exception:
                            continue
                path_conflicts=core.find_later_localization_path_conflicts(root,japanese_rels)
            except Exception as exc:
                path_conflicts=[]
                out.append(i18n.t('u6.same_name_file_conflict_check_failed', exc=exc))
            if path_conflicts:
                out.append(i18n.t('u6.same_name_localization_conflicts_with_later'))
                for conflict in path_conflicts:
                    out += [
                        (i18n.t('u6.load_order', mod=conflict.get('mod'), value=int(conflict.get('source_position', 0)) + 1, value_2=int(conflict.get('position', 0)) + 1, value_3=i18n.t('u6.effective') if conflict.get('effective') else i18n.t('u6.later'))),
                        (i18n.t('u6.same_paths_shared_keys_source_only', value=int(conflict.get('path_match_count', 0)), value_2=int(conflict.get('shared_keys', 0)), value_3=int(conflict.get('source_only_keys', 0)), value_4=int(conflict.get('candidate_only_keys', 0)))),
                        (i18n.t('u6.translation_related_names_tags_legacy_translation', value=i18n.t('u6.yes') if conflict.get('translation_hint') else i18n.t('u6.no'), value_2='PASS' if conflict.get('stale_translation_candidate') else 'FAIL', target_name=i18n.t("lang." + target_lang))),
                    ]
                    out.extend(i18n.t('u6.path', path=path) for path in conflict.get("relative_paths",[]))
            else:
                out.append(i18n.t('u6.same_name_localization_conflicts_with_later_2'))
            warnings=list(r.get("translation_warnings") or [])
            if warnings:
                out.append(i18n.t('u6.warnings'))
                out.extend([i18n.t('u6.detail', warning=warning) for warning in warnings])
                profile=dict(r.get("translation_format_profile") or {})
                out.append(
                    i18n.t('u6.warning_evidence_japanese_text_in_l', value=int(profile.get('english_japanese_text_keys', 0) or 0), value_2=int(profile.get('english_key_count', 0) or 0), value_3=format(float(profile.get('english_japanese_text_rate', 0) or 0) * 100, '.1f'), value_4=i18n.t('u6.yes') if profile.get('translation_hint') else i18n.t('u6.no'))
                )
            source_override=self._mod_relation_override(root, target_lang=target_lang)
            if source_override.get("role","auto") != "auto":
                out.append(i18n.t('u6.manual_classification_of_this_mod', role=source_override.get('role')))
            try:
                initial_candidate=self._first_seen_japanese_candidate(root, target_lang=target_lang)
                out.append(i18n.t('u6.initial_classification_of_this_mod', value=i18n.t('u6.japanese_candidate', target_name=i18n.t("lang." + target_lang)) if initial_candidate else i18n.t('u6.source_mod_2')))
            except Exception:
                pass
            try:
                src_data=core._collect_mod_language_entries(root)
                source_keys=set((src_data.get("source") or {}).keys())
            except Exception as exc:
                out += [i18n.t('u6.could_not_retrieve_source_keys', exc=exc), ""]
                continue
            out += [i18n.t('u6.source_keys_before_vanilla_exclusion', source_keys_count=len(source_keys)), i18n.t('u6.applied_gate_assessed_per_candidate_using')]
            if not source_keys:
                out += [i18n.t('u6.no_source_keys_this_mod_will'), ""]
                continue

            candidates=[]
            source_profile_cache={}
            for cand_key,cand in audit_by_path.items():
                if cand_key==source_id:
                    continue
                profile_key=str(cand.get("base_game_name") or id(cand.get("base_game_source_entries")))
                source_profile=source_profile_cache.get(profile_key)
                if source_profile is None:
                    source_profile=core.prepare_translation_source_profile(
                        {"english":dict(src_data.get("english") or {}),
                         "simp_chinese":dict(src_data.get("simp_chinese") or {})},
                        cand.get("base_game_source_entries") or {},
                        set(cand.get("base_game_keys") or set()),
                    )
                    source_profile_cache[profile_key]=source_profile
                auto=core._translation_mod_weight(
                    name,
                    source_keys,
                    cand,
                    source_language_entries={
                        "english": dict(src_data.get("english") or {}),
                        "simp_chinese": dict(src_data.get("simp_chinese") or {}),
                    },
                    source_path=source_id,
                    source_profile=source_profile,
                )
                role=cand.get("manual_role","auto")
                manual_sources=set(cand.get("manual_source_paths") or [])
                manual_relation=(role=="translation" and source_id in manual_sources)
                # Keep every candidate with actual shared keys, plus explicit manual
                # relations even if they intentionally have zero current overlap.
                if int(auto.get("raw_overlap_keys",auto.get("overlap_keys",0)) or 0)<=0 and not manual_relation:
                    continue
                try:
                    stable_candidate=self._first_seen_japanese_candidate(Path(cand.get("path","")), target_lang=target_lang)
                except Exception:
                    stable_candidate=False
                candidates.append((auto,cand,role,manual_sources,manual_relation,stable_candidate))
            candidates.sort(key=lambda item:(float(item[0].get("score",0) or 0),float(item[0].get("coverage",0) or 0)),reverse=True)
            if not candidates:
                out += [i18n.t('u6.translation_mod_candidates_with_matching_keys', target_name=i18n.t("lang." + target_lang)), ""]
                continue

            for ci,(auto,cand,role,manual_sources,manual_relation,stable_candidate) in enumerate(candidates,1):
                cand_path=Path(cand.get("path",""))
                auto_class=auto.get("classification","rejected")
                if role=="source":
                    final_text=i18n.t('u6.excluded_manually_marked_as_source_mod')
                elif role=="translation" and manual_sources and source_id not in manual_sources:
                    final_text=i18n.t('u6.excluded_not_a_manually_selected_source')
                elif manual_relation:
                    final_text=i18n.t('u6.translation_mod_manual_source_link_takes', target_name=i18n.t("lang." + target_lang))
                elif role=="translation":
                    final_text=i18n.t('u6.manually_fixed_as_translation_mod_source', value=class_label.get(auto_class, auto_class), target_name=i18n.t("lang." + target_lang))
                elif not stable_candidate:
                    final_text=i18n.t('u6.not_a_current_automatic_candidate_not', target_name=i18n.t("lang." + target_lang))
                else:
                    final_text=class_label.get(auto_class,auto_class)
                if auto.get("candidate_base_translation"):
                    candidate_role_text=i18n.t('u6.base_game_translation_mod', target_name=i18n.t("lang." + target_lang))
                elif auto.get("candidate_base_dominant"):
                    candidate_role_text=i18n.t('u6.large_mod_overwrite_candidate')
                elif auto.get("candidate_localization_shape")=="self_localized":
                    candidate_role_text=i18n.t('u6.standalone_mod_with_bundled_japanese', target_name=i18n.t("lang." + target_lang))
                elif auto.get("multi_translation_gate"):
                    candidate_role_text=i18n.t('u6.multi_mod_translation_mod', target_name=i18n.t("lang." + target_lang))
                else:
                    candidate_role_text=i18n.t('u6.standard_translation_mod_candidate', target_name=i18n.t("lang." + target_lang))
                pair_classification = (
                    i18n.t('u6.multi_mod_translation_candidate', target_name=i18n.t("lang." + target_lang)) if auto.get("multi_translation_gate") else
                    i18n.t('u6.specific_mod_translation_candidate', target_name=i18n.t("lang." + target_lang)) if auto_class in {"auto","candidate"} else
                    i18n.t('u6.unrelated')
                )
                raw_overlap=int(auto.get("raw_overlap_keys",auto.get("overlap_keys",0)) or 0)
                candidate_total=int(auto.get("candidate_total_keys",auto.get("japanese_keys",0)) or 0)
                base_count=int(auto.get("candidate_base_keys",auto.get("base_game_match_keys",0)) or 0)
                non_base_count=int(auto.get("candidate_non_base_keys",max(0,candidate_total-base_count)) or 0)
                paired_count=int(auto.get("candidate_paired_source_keys",0) or 0)
                out += [
                    "-"*72,
                    i18n.t('u6.candidate_2', ci=ci, value=cand.get('mod') or cand_path.name),
                    i18n.t('u6.location_2', cand_path=cand_path),
                    i18n.t('u6.total_candidate_keys', candidate_total=candidate_total),
                    (i18n.t('u6.base_game_key_matches', base_count=base_count, candidate_total=candidate_total, value=format(float(auto.get('candidate_base_rate', 0) or 0) * 100, '.1f'))),
                    (i18n.t('u6.non_base_game_keys', non_base_count=non_base_count, candidate_total=candidate_total, value=format(float(auto.get('candidate_non_base_rate', 0) or 0) * 100, '.1f'))),
                    i18n.t('u6.raw_shared_keys', raw_overlap=raw_overlap),
                    i18n.t('u6.shared_key_breakdown'),
                    i18n.t('u6.same_key_and_english_source_as', value=int(auto.get('vanilla_carryover_keys', 0) or 0)),
                    i18n.t('u6.base_game_key_with_source_text', value=int(auto.get('changed_base_overlap_keys', 0) or 0)),
                    i18n.t('u6.non_base_game_keys_2', value=int(auto.get('non_base_overlap_keys', 0) or 0)),
                    i18n.t('u6.excluded_as_vanilla_carryover', value=int(auto.get('vanilla_carryover_keys', 0) or 0)),
                    i18n.t('u6.final_effective_shared_keys', value=int(auto.get('effective_overlap_keys', 0) or 0)),
                    (i18n.t('u6.effective_matching_source_mod_candidate', value=format(float(auto.get('effective_source_rate', 0) or 0) * 100, '.1f'), value_2=format(float(auto.get('effective_candidate_rate', 0) or 0) * 100, '.1f'))),
                    i18n.t('u6.candidate_english_chinese_localization', value=i18n.t('u6.yes') if paired_count else i18n.t('u6.no'), paired_count=paired_count, candidate_total=candidate_total),
                    (i18n.t('u6.candidate_source_text_comparison_matches_mismatches', value=int(auto.get('source_text_match_keys', 0) or 0), value_2=int(auto.get('source_text_mismatch_keys', 0) or 0))),
                    i18n.t('u6.base_game_translation_70_gate', value='PASS' if float(auto.get('candidate_base_rate', 0) or 0) >= 0.7 else 'FAIL'),
                    i18n.t('u6.non_base_game_20_gate', value='PASS' if float(auto.get('candidate_non_base_rate', 0) or 0) <= 0.2 else 'FAIL'),
                    (i18n.t('u6.40_relationship_gate_source_candidate_effective', value='PASS' if auto.get('effective_source_rate_pass') else 'FAIL', value_2='PASS' if auto.get('effective_candidate_rate_pass') else 'FAIL', value_3=int(auto.get('required_match_count', 0) or 0), value_4='PASS' if auto.get('effective_count_pass') else 'FAIL')),
                    i18n.t('u6.candidate_type', candidate_role_text=candidate_role_text),
                    i18n.t('u6.final_pair_classification', pair_classification=pair_classification),
                    i18n.t('u6.structure_points', structure_label=auto.get('structure_label', ''), value=format(float(auto.get('translation_only_points', 0) or 0), '.1f')),
                    i18n.t('u6.other_language_penalty_points', value=format(float(auto.get('other_language_penalty', 0) or 0), '.1f')),
                    i18n.t('u6.automatic_score_100', value=format(float(auto.get('score', 0) or 0), '.1f')),
                    i18n.t('u6.pure_automatic_assessment', value=class_label.get(auto_class, auto_class)),
                    i18n.t('u6.initial_japanese_candidate', target_name=i18n.t("lang." + target_lang), value=i18n.t('u6.yes_2') if stable_candidate else i18n.t('u6.no_2')),
                ]
                if role != "auto":
                    out.append(i18n.t('u6.manual_classification', value=i18n.t('u6.translation_mod', target_name=i18n.t('lang.' + 'japanese')) if role == 'translation' else i18n.t('u6.source_mod_3') if role == 'source' else role))
                if manual_sources:
                    out.append(i18n.t('u6.manually_linked_sources_this_source_mod', manual_sources_count=len(manual_sources), value=i18n.t('u6.included') if source_id in manual_sources else i18n.t('u6.excluded_2')))
                out.append(i18n.t('u6.current_final_assessment', final_text=final_text))
                rels=list(auto.get("other_language_relations") or [])
                if rels:
                    for x in rels:
                        out.append(i18n.t('u6.other_language_files', language=x.get('language'), value=format(float(x.get('coverage', 0) or 0) * 100, '.1f'), overlap_keys=x.get('overlap_keys', 0), source_keys_count=len(source_keys), files=x.get('files', 0)))
                reasons=list(auto.get("reasons") or [])
                if reasons:
                    out.append(i18n.t('u6.automatic_assessment_reasons'))
                    out.extend([i18n.t('u6.detail_2', reason=reason) for reason in reasons])
            out.append("")
        return "\n".join(out).rstrip()+"\n"

    def _target_translation_judgement_log_text(self, target_lang):
        target_name = i18n.t("lang." + target_lang)
        results = [row for row in (self.mod_research_results or []) if _status_matches_language(row, target_lang)]
        out = [i18n.t('u6.v_translation_mod_assessment_log', app_name=APP_NAME, app_version=APP_VERSION, target_name=target_name)]
        if target_lang == "english":
            out.append(i18n.t('u6.english_external_check_skipped'))
            return "\n".join(out)
        roots = [Path(row["path"]) for row in results if row.get("path")]
        index = self._build_stable_translation_mod_index(roots, target_lang=target_lang)
        for row in results:
            out.append(i18n.t('u6.target_research_result', mod=row.get("mod", ""), target_name=target_name,
                              status=display_status(row), count=row.get("gap_count", 0)))
            root = Path(row["path"])
            out.append(i18n.t('u6.initial_japanese_candidate', target_name=target_name,
                              value=self._first_seen_japanese_candidate(root, target_lang=target_lang)))
            for candidate in core.rank_external_japanese_translations(root, index, target_lang=target_lang):
                out.append(i18n.t('u6.target_candidate_evidence', mod=candidate.get("mod", ""),
                                  score=candidate.get("score", 0), precision=candidate.get("precision", 0),
                                  classification=candidate.get("classification", ""), target_name=target_name))
        return "\n".join(out)

    def show_translation_judgement_log(self):
        if self.judgement_log_thread and self.judgement_log_thread.is_alive():
            messagebox.showinfo(APP_NAME,i18n.t('u6.generating_the_translation_mod_assessment_log', target_name=i18n.t("lang." + _current_target_lang(self))))
            return
        win=tk.Toplevel(self); win.title(i18n.t('u6.translation_mod_assessment_log', target_name=i18n.t("lang." + _current_target_lang(self)))); win.geometry('1100x760'); win.transient(self)
        outer=ttk.Frame(win,padding=8); outer.pack(fill='both',expand=True)
        status=tk.StringVar(value=i18n.t('u6.recalculating_the_assessment_log_in_the'))
        ttk.Label(outer,textvariable=status,foreground='#555').pack(fill='x',pady=(0,6))
        frame=ttk.Frame(outer); frame.pack(fill='both',expand=True)
        box=tk.Text(frame,wrap='none')
        sy=ttk.Scrollbar(frame,orient='vertical',command=box.yview); sx=ttk.Scrollbar(frame,orient='horizontal',command=box.xview)
        box.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        frame.rowconfigure(0,weight=1); frame.columnconfigure(0,weight=1)
        box.grid(row=0,column=0,sticky='nsew'); sy.grid(row=0,column=1,sticky='ns'); sx.grid(row=1,column=0,sticky='ew')
        box.insert('1.0',i18n.t('u6.generating_assessment_log'))
        bar=ttk.Frame(outer); bar.pack(fill='x',pady=(7,0))
        export_btn=ttk.Button(bar,text=i18n.t('u6.export_log'),state='disabled'); export_btn.pack(side='left')
        ttk.Button(bar,text=i18n.t('u6.close'),command=win.destroy).pack(side='right')
        token=id(win); self._judgement_log_window=(token,win,box,status,export_btn)
        target_lang = _current_target_lang(self)
        def work():
            try: self.events.put(('judgement_log_ready',(token,self._translation_judgement_log_text(target_lang=target_lang))))
            except Exception as exc: self.events.put(('judgement_log_error',(token,str(exc))))
        self.judgement_log_thread=threading.Thread(target=work,daemon=True,name='judgement-log-build'); self.judgement_log_thread.start()

    def _apply_judgement_log_ready(self, token, text):
        self.judgement_log_thread=None
        state=self._judgement_log_window
        if not state or state[0]!=token: return
        _,win,box,status,export_btn=state
        if not win.winfo_exists(): return
        box.delete('1.0','end'); box.insert('1.0',text); box.configure(state='disabled')
        status.set(i18n.t('u6.assessment_log_ready_generation_runs_on'))
        export_btn.config(state='normal',command=lambda t=text:self._write_translation_judgement_log_text(t))

    def _write_translation_judgement_log_text(self, text):
        try:
            JUDGEMENT_LOG_ROOT.mkdir(parents=True,exist_ok=True)
            target=JUDGEMENT_LOG_ROOT / f"translation_mod_judgement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            target.write_text(text,encoding='utf-8')
            messagebox.showinfo(APP_NAME,i18n.t('u6.exported_translation_mod_assessment_log', target=target, target_name=i18n.t("lang." + _current_target_lang(self))))
            return target
        except Exception as exc:
            record_error(i18n.t('u6.translation_mod_assessment_log_export', target_name=i18n.t("lang." + _current_target_lang(self))),exc); messagebox.showerror(APP_NAME,i18n.t('u6.could_not_export_assessment_log', exc=exc))
            return None

    def export_relation_report(self):
        """元Modと日本語化Modの紐付けを一覧表（CSV と Markdown）に書き出し、ズレていそうなものに印を付ける。"""
        results=[dict(r) for r in (self.mod_research_results or []) if r.get("path")]
        if not results:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_translation_status_results_research_mods_2'))
            return None
        for r in results:
            if not r.get("game"):
                r["game"]=self._backup_game_name_for_root(Path(r.get("path","")))
        try:
            report=core.build_relation_report(results, target_lang=_current_target_lang(self))
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S')
            JUDGEMENT_LOG_ROOT.mkdir(parents=True,exist_ok=True)
            csv_path=JUDGEMENT_LOG_ROOT / f"紐付けレポート_{stamp}.csv"
            md_path=JUDGEMENT_LOG_ROOT / f"紐付けレポート_{stamp}.md"
            # Excel で文字化けしないよう BOM 付き UTF-8 で書く。
            csv_path.write_text(core.relation_report_csv(report),encoding="utf-8-sig")
            md_path.write_text(core.relation_report_markdown(
                report,target_lang=_current_target_lang(self),title=i18n.t('u6.v_link_report', app_name=APP_NAME, app_version=APP_VERSION, value=datetime.now().strftime('%Y-%m-%d %H:%M'))),encoding="utf-8")
        except Exception as exc:
            record_error(i18n.t('u6.link_report'), exc)
            messagebox.showerror(APP_NAME,i18n.t('u6.could_not_export_link_report', exc=exc))
            return None
        flagged=sum(1 for r in report["rows"] if r.get("要確認"))
        self.mod_status_summary_var.set(i18n.t('u6.link_report_exported_entries_need_review', report__rows___count=len(report['rows']), flagged=flagged))
        self._open_path(JUDGEMENT_LOG_ROOT)
        return md_path

    def export_translation_judgement_log(self):
        if self.judgement_log_thread and self.judgement_log_thread.is_alive():
            messagebox.showinfo(APP_NAME,i18n.t('u6.generating_the_assessment_log_in_the'))
            return None
        def work():
            try:
                text=self._translation_judgement_log_text()
                JUDGEMENT_LOG_ROOT.mkdir(parents=True,exist_ok=True)
                target=JUDGEMENT_LOG_ROOT / f"translation_mod_judgement_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                target.write_text(text,encoding='utf-8')
                self.events.put(('judgement_log_exported',str(target)))
            except Exception as exc:
                self.events.put(('judgement_log_export_error',str(exc)))
        self.judgement_log_thread=threading.Thread(target=work,daemon=True,name='judgement-log-export'); self.judgement_log_thread.start()
        self.mod_status_summary_var.set(i18n.t('u6.generating_assessment_log_in_the_background'))
        return None

    # ---------------- Comprehensive localization diagnostics / repair ----------------
    def _build_diagnostic_tab(self):
        t = self.tab_diagnostic
        head = ttk.Frame(t); head.pack(fill="x")
        ttk.Label(head, text=i18n.t('u7.full_diagnostics_check_localization_contamination_missing'), font=("", 14, "bold")).pack(side="left")
        ttk.Label(head, textvariable=self.diagnostic_summary_var).pack(side="right")
        ttk.Label(t, text=(
            i18n.t('u7.using_english_simplified_chinese_source_keys' if _current_target_lang(self) == 'japanese' else 'u7.using_english_simplified_chinese_source_keys.target', target_name=i18n.t('lang.' + _current_target_lang(self)))
        ), foreground="#555", wraplength=1100, justify="left").pack(fill="x", pady=(6,8))

        pane = ttk.Panedwindow(t, orient="horizontal"); pane.pack(fill="both", expand=True)
        left = ttk.Frame(pane); right = ttk.Frame(pane)
        pane.add(left, weight=2); pane.add(right, weight=5)

        targets = ttk.LabelFrame(left, text=i18n.t('u7.diagnostic_targets_from_translation_status'), padding=6); targets.pack(fill="both", expand=True)
        ttk.Label(targets, textvariable=self.diagnostic_target_var, foreground="#555").pack(anchor="w")
        tw = ttk.Frame(targets); tw.pack(fill="both", expand=True, pady=(6,0))
        self.diagnostic_target_tree = ttk.Treeview(tw, columns=("mod","status","path"), show="headings", selectmode="extended", height=18)
        self._enable_ctrl_multiselect(self.diagnostic_target_tree)
        for c,txt,w in (("mod","Mod",260),("status",i18n.t('u7.current_status'),150),("path",i18n.t('u7.location'),500)):
            self.diagnostic_target_tree.heading(c,text=txt); self.diagnostic_target_tree.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        sy=ttk.Scrollbar(tw,orient="vertical",command=self.diagnostic_target_tree.yview); sx=ttk.Scrollbar(tw,orient="horizontal",command=self.diagnostic_target_tree.xview)
        self.diagnostic_target_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        tw.rowconfigure(0,weight=1); tw.columnconfigure(0,weight=1)
        self.diagnostic_target_tree.grid(row=0,column=0,sticky="nsew"); sy.grid(row=0,column=1,sticky="ns"); sx.grid(row=1,column=0,sticky="ew")
        tbtn=ttk.Frame(targets); tbtn.pack(fill="x",pady=(7,0))
        self.diagnostic_refresh_btn=ttk.Button(tbtn,text=i18n.t('u7.reload_from_translation_status'),command=self._refresh_diagnostic_targets); self.diagnostic_refresh_btn.pack(side="left")
        self.diagnostic_select_all_btn=ttk.Button(tbtn,text=i18n.t('u7.select_all'),command=self._select_all_diagnostic_targets); self.diagnostic_select_all_btn.pack(side="left",padx=(6,0))
        self.diagnostic_clear_selection_btn=ttk.Button(tbtn,text=i18n.t('u7.deselect_all'),command=self._clear_diagnostic_target_selection); self.diagnostic_clear_selection_btn.pack(side="left",padx=(6,0))
        self.diagnostic_relation_btn=ttk.Button(tbtn,text=i18n.t('u7.mod_classification_and_relations'),command=lambda:self._open_mod_relation_dialog("diagnostic")); self.diagnostic_relation_btn.pack(side="left",padx=(6,0))

        actions = ttk.LabelFrame(left, text=i18n.t('u7.actions'), padding=6); actions.pack(fill="x", pady=(8,0))
        self.diagnostic_scan_btn=ttk.Button(actions,text=i18n.t('u7.diagnose_selected_mods'),command=lambda:self._start_localization_diagnostic(False)); self.diagnostic_scan_btn.pack(fill="x")
        self.diagnostic_repair_btn=ttk.Button(actions,text=i18n.t('u7.repair_with_configured_choices'),command=lambda:self._start_localization_diagnostic(True)); self.diagnostic_repair_btn.pack(fill="x",pady=(6,0))
        ttk.Label(actions,text=i18n.t('u7.repair_backup_location_documents_paradox_localization'),foreground="#666",wraplength=340,justify="left").pack(anchor="w",pady=(7,0))

        resultbox=ttk.LabelFrame(right,text=i18n.t('u7.diagnostic_results'),padding=6); resultbox.pack(fill="both",expand=True)
        rw=ttk.Frame(resultbox); rw.pack(fill="both",expand=True)
        cols=("severity","mod","kind","score","location","plan","decision","file","count","detail")
        self.diagnostic_tree=ttk.Treeview(rw,columns=cols,show="headings",height=18,selectmode="extended")
        self._enable_ctrl_multiselect(self.diagnostic_tree)
        for c,txt,w in (("severity",i18n.t('u7.severity_2'),80),("mod","Mod",220),("kind",i18n.t('u7.diagnostic_item_2'),190),("score",i18n.t('u7.relevance'),80),("location",i18n.t('u7.current_location'),130),("plan",i18n.t('u7.repair_plan'),190),("decision",i18n.t('u7.translation_choice'),180),("file",i18n.t('u7.file'),250),("count",i18n.t('u7.count_2'),70),("detail",i18n.t('u7.details_2'),560)):
            self.diagnostic_tree.heading(c,text=txt); self.diagnostic_tree.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        sy2=ttk.Scrollbar(rw,orient="vertical",command=self.diagnostic_tree.yview); sx2=ttk.Scrollbar(rw,orient="horizontal",command=self.diagnostic_tree.xview)
        self.diagnostic_tree.configure(yscrollcommand=sy2.set,xscrollcommand=sx2.set)
        rw.rowconfigure(0,weight=1); rw.columnconfigure(0,weight=1)
        self.diagnostic_tree.grid(row=0,column=0,sticky="nsew"); sy2.grid(row=0,column=1,sticky="ns"); sx2.grid(row=1,column=0,sticky="ew")
        self.diagnostic_tree.bind("<<TreeviewSelect>>", self._on_diagnostic_result_selected)
        self._enable_tree_sort(self.diagnostic_tree)
        conflict_bar=ttk.Frame(resultbox); conflict_bar.pack(fill="x",pady=(7,0))
        ttk.Label(conflict_bar,text=i18n.t('u7.choose_translations_only_for_conflicts')).pack(side="left")
        self.diagnostic_keep_source_btn=ttk.Button(conflict_bar,text=i18n.t('u7.use_source_mod_translation_for_selected'),command=lambda:self._set_diagnostic_conflict_choice("source")); self.diagnostic_keep_source_btn.pack(side="left",padx=(8,0))
        self.diagnostic_keep_translation_btn=ttk.Button(conflict_bar,text=i18n.t('u7.use_japanese_translation_mod_translation_for' if _current_target_lang(self) == 'japanese' else 'u7.use_japanese_translation_mod_translation_for.target', target_name=i18n.t('lang.' + _current_target_lang(self))),command=lambda:self._set_diagnostic_conflict_choice("translation")); self.diagnostic_keep_translation_btn.pack(side="left",padx=(6,0))
        self.diagnostic_auto_choice_btn=ttk.Button(conflict_bar,text=i18n.t('u7.auto_organize_selected_conflicts'),command=lambda:self._set_diagnostic_conflict_choice("auto")); self.diagnostic_auto_choice_btn.pack(side="left",padx=(6,0))
        self.diagnostic_clear_choice_btn=ttk.Button(conflict_bar,text=i18n.t('u7.clear_selected_conflict_choices'),command=lambda:self._set_diagnostic_conflict_choice(None)); self.diagnostic_clear_choice_btn.pack(side="left",padx=(6,0))
        conflict_bar2=ttk.Frame(resultbox); conflict_bar2.pack(fill="x",pady=(5,0))
        self.diagnostic_integration_status_var = tk.StringVar(value=i18n.t('u7.integration_targets_not_diagnosed'))
        ttk.Label(conflict_bar2,textvariable=self.diagnostic_integration_status_var, foreground="#555").pack(side="left")
        ttk.Label(conflict_bar2,text=i18n.t('u7.all_conflicts')).pack(side="left")
        self.diagnostic_all_source_btn=ttk.Button(conflict_bar2,text=i18n.t('u7.use_source_translation_for_all_conflicts'),command=lambda:self._set_all_diagnostic_conflict_choices("source")); self.diagnostic_all_source_btn.pack(side="left",padx=(8,0))
        self.diagnostic_all_translation_btn=ttk.Button(conflict_bar2,text=i18n.t('u7.use_japanese_translation_mod_translation_for_2' if _current_target_lang(self) == 'japanese' else 'u7.use_japanese_translation_mod_translation_for_2.target', target_name=i18n.t('lang.' + _current_target_lang(self))),command=lambda:self._set_all_diagnostic_conflict_choices("translation")); self.diagnostic_all_translation_btn.pack(side="left",padx=(6,0))
        self.diagnostic_all_auto_btn=ttk.Button(conflict_bar2,text=i18n.t('u7.auto_organize_all_conflicts'),command=lambda:self._set_all_diagnostic_conflict_choices("auto")); self.diagnostic_all_auto_btn.pack(side="left",padx=(6,0))
        conflict_bar3=ttk.Frame(resultbox); conflict_bar3.pack(fill="x",pady=(4,0))
        self.diagnostic_conflict_help_var = tk.StringVar(value=i18n.t('u7.actions_needed_for_repair_will_appear'))
        ttk.Label(conflict_bar3,textvariable=self.diagnostic_conflict_help_var, foreground="#555",wraplength=1000,justify="left").pack(side="left",fill="x",expand=True)
        conflict_bar4=ttk.Frame(resultbox); conflict_bar4.pack(fill="x",pady=(3,0))
        self.diagnostic_exception_status_var = tk.StringVar(value=i18n.t('u7.auto_organize_manual_settings_in_mod'))
        ttk.Label(conflict_bar4,textvariable=self.diagnostic_exception_status_var, foreground="#555",wraplength=1000,justify="left").pack(side="left",fill="x",expand=True)
        detail=ttk.LabelFrame(right,text=i18n.t('u7.details_repair_log'),padding=6); detail.pack(fill="both",expand=True,pady=(8,0))
        self.diagnostic_detail=tk.Text(detail,height=9,wrap="word",state="disabled")
        dsy=ttk.Scrollbar(detail,orient="vertical",command=self.diagnostic_detail.yview); self.diagnostic_detail.configure(yscrollcommand=dsy.set)
        dsy.pack(side="right",fill="y"); self.diagnostic_detail.pack(side="left",fill="both",expand=True)
        self._refresh_diagnostic_targets()


    # ---------------- Backup restore / rollback ----------------
    def _safe_backup_mod_token(self, text):
        return re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯 _\-().\[\]]+', '_', str(text or '')).strip(' ._')[:90] or 'Mod'

    def _backup_game_name_for_root(self, target_root):
        """Infer the owning Paradox game without requiring a fresh Mod scan."""
        p=Path(target_root)
        raw=str(p).replace('\\','/').lower()
        # Steam Workshop paths are the strongest signal and work on every OS.
        for game, meta in core.PARADOX_STEAM_GAMES.items():
            appid=str(meta.get('appid') or '')
            if appid and f'/workshop/content/{appid}/' in raw:
                return game
        # Local launcher Mods normally live below Documents/Paradox Interactive/<game>/mod.
        for game, meta in core.PARADOX_STEAM_GAMES.items():
            for docs_name in meta.get('docs', []):
                needle='/' + str(docs_name).replace('\\','/').strip('/').lower() + '/mod/'
                if needle in raw:
                    return game
        # Reuse a game label already discovered by Translation Status when available.
        try:
            target_key=str(p.resolve())
        except Exception:
            target_key=str(p)
        for row in list(getattr(self,'mod_research_results',[]) or []):
            rr=row.get('mod_root') or row.get('path') or row.get('root')
            if not rr: continue
            try: rr_key=str(Path(rr).resolve())
            except Exception: rr_key=str(Path(rr))
            if rr_key == target_key and row.get('game'):
                return str(row.get('game'))
        return 'ゲーム未特定'

    def _translation_status_rows_for_restore(self, *, persisted_snapshot=None, use_persisted=True, force_rebuild=False):
        """Return Translation Status rows usable for rollback target resolution.

        v0.11.56 performance rule: the persisted translation-status JSON is parsed at most once
        for a backup-list refresh. Older code called this helper for every backup entry, causing
        hundreds of repeated JSON parses on startup.
        """
        if not force_rebuild and use_persisted and persisted_snapshot is None and self._restore_status_rows_cache is not None:
            return self._restore_status_rows_cache
        rows=[]
        seen=set()
        sources=[list(getattr(self, 'mod_research_results', []) or [])]
        if use_persisted:
            try:
                if persisted_snapshot is None:
                    persisted_snapshot=self._load_translation_status_snapshot()
                sources.append(list((persisted_snapshot or {}).get('results') or []))
            except Exception:
                pass
        for source in sources:
            for row in source:
                if not _status_matches_language(row, _current_target_lang(self)):
                    continue

                # The Translation Status row itself is always a restore candidate.
                # If the row points to a separate Japanese localization Mod, add that
                # Mod as an independent candidate too.  Older snapshots sometimes only
                # retain the relation on the source-Mod row, so relying on top-level
                # rows alone can leave a perfectly known Japanese Mod as "未特定".
                candidate_specs=[(
                    row.get('mod_root') or row.get('path') or row.get('root'),
                    row.get('mod') or row.get('name'),
                    row.get('game'),
                    i18n.t('u7.translation_status_mod'),
                )]
                ext_raw=row.get('external_translation_path') or row.get('external_translation_root')
                if not ext_raw and row.get('external_translation_localization'):
                    ext_raw=row.get('external_translation_localization')
                if ext_raw:
                    candidate_specs.append((
                        ext_raw,
                        row.get('external_translation_mod') or None,
                        row.get('game'),
                        i18n.t('u7.translation_mod_in_translation_status', target_name=i18n.t("lang." + (row.get("target_lang") or core.DEFAULT_TARGET_LANG))),
                    ))

                for raw, explicit_name, game, inventory_source in candidate_specs:
                    if not raw:
                        continue
                    p=Path(raw)
                    # external_translation_localization can point directly at localization.
                    if core.is_localization_dir_name(p.name):
                        p=p.parent
                    try: key=str(p.resolve())
                    except Exception: key=str(p)
                    if key in seen:
                        continue
                    seen.add(key)
                    rr=dict(row)
                    if explicit_name:
                        rr['mod']=str(explicit_name)
                    if game:
                        rr['game']=str(game)
                    rr['_restore_root']=p
                    rr['_restore_path_key']=key
                    rr['_restore_inventory_source']=inventory_source
                    rows.append(rr)
        if use_persisted:
            self._restore_status_rows_cache=rows
        return rows

    def _known_mod_roots_for_restore(self, restore_rows=None):
        roots=[]
        seen=set()
        for row in (restore_rows if restore_rows is not None else self._translation_status_rows_for_restore()):
            p=Path(row.get('_restore_root'))
            key=str(row.get('_restore_path_key') or p)
            if key in seen or not p.exists():
                continue
            seen.add(key); roots.append(p)
        for raw in list(getattr(self, 'monitor_target_paths', []) or []):
            p=Path(raw)
            if core.is_localization_dir_name(p.name): p=p.parent
            try: key=str(p.resolve())
            except Exception: key=str(p)
            if key in seen or not p.exists():
                continue
            seen.add(key); roots.append(p)
        return roots

    def _resolve_backup_target_from_translation_status(self, entry, restore_rows=None):
        """Resolve an old/unknown backup target using the Translation Status inventory.

        Priority: existing recorded path -> Workshop/content identifier -> exact normalized Mod
        name.  Ambiguous name matches are deliberately not auto-selected.
        """
        recorded=entry.get('target_root')
        if recorded:
            rp=Path(recorded)
            if rp.exists():
                return rp, self._backup_game_name_for_root(rp), i18n.t('u7.backup_record'), 1

        rows=restore_rows if restore_rows is not None else self._translation_status_rows_for_restore()
        candidates=[]
        for row in rows:
            root=Path(row.get('_restore_root'))
            if not root.exists():
                continue
            name=str(row.get('mod') or row.get('name') or '')
            if not name:
                try: name=core.detect_mod_name(root)
                except Exception: name=root.name
            candidates.append((root,name,row))

        # If an old manifest kept a Workshop/content id but the absolute path changed, use it.
        recorded_text=str(recorded or '').replace('\\','/')
        id_match=re.search(r'/workshop/content/(\d+)/(\d+)(?:/|$)', recorded_text)
        if id_match:
            appid, modid=id_match.groups()
            hits=[]
            for root,name,row in candidates:
                raw=str(root).replace('\\','/')
                if f'/workshop/content/{appid}/{modid}' in raw:
                    hits.append((root,name,row))
            if len(hits)==1:
                root,name,row=hits[0]
                game=str(row.get('game') or self._backup_game_name_for_root(root))
                return root, game, i18n.t('u7.identified_from_translation_status_workshop_id'), 1
            if len(hits)>1:
                return None, 'ゲーム未特定', i18n.t('u7.multiple_matching_workshop_ids_in_translation'), len(hits)

        raw_names=[]
        for value in (entry.get('mod'), (entry.get('manifest') or {}).get('target_mod_name') if isinstance(entry.get('manifest'),dict) else None):
            if value and str(value) not in raw_names:
                raw_names.append(str(value))
        # First try the displayed Mod name literally (case/space tolerant, but do not
        # strip words such as Japanese/JP).  Translation-status normalization is
        # intentionally broad for relation detection and can make a source Mod and its
        # Japanese companion collapse to the same name; restore target selection must be
        # stricter than that.
        exact_names=[]
        for value in raw_names:
            cleaned=re.sub(r'_[0-9a-fA-F]{8}$','',value)
            cleaned=re.sub(r'_(?:差分上書き|不足分上書き)$','',cleaned)
            cleaned=' '.join(cleaned.replace('_',' ').split()).casefold()
            if cleaned and cleaned not in exact_names:
                exact_names.append(cleaned)
        exact_hits=[]
        for root,name,row in candidates:
            cand=' '.join(str(name or '').replace('_',' ').split()).casefold()
            if cand and cand in exact_names:
                exact_hits.append((root,name,row))
        unique={}
        for root,name,row in exact_hits:
            try: key=str(root.resolve())
            except Exception: key=str(root)
            unique[key]=(root,name,row)
        exact_hits=list(unique.values())
        if len(exact_hits)==1:
            root,name,row=exact_hits[0]
            game=str(row.get('game') or self._backup_game_name_for_root(root))
            return root, game, i18n.t('u7.identified_from_translation_status_exact_mod'), 1
        if len(exact_hits)>1:
            return None, 'ゲーム未特定', i18n.t('u7.multiple_exact_mod_name_matches_in'), len(exact_hits)

        normalized=[]
        for value in raw_names:
            cleaned=re.sub(r'_[0-9a-fA-F]{8}$','',value)
            cleaned=re.sub(r'_(?:差分上書き|不足分上書き)$','',cleaned)
            cleaned=cleaned.replace('_',' ')
            norm=core._normalize_mod_name_for_match(cleaned)
            if norm and norm not in normalized:
                normalized.append(norm)

        hits=[]
        for root,name,row in candidates:
            norm=core._normalize_mod_name_for_match(name)
            if norm and norm in normalized:
                hits.append((root,name,row))
        # De-duplicate rows that came from current + persisted status state.
        unique={}
        for root,name,row in hits:
            try: key=str(root.resolve())
            except Exception: key=str(root)
            unique[key]=(root,name,row)
        hits=list(unique.values())
        if len(hits)==1:
            root,name,row=hits[0]
            game=str(row.get('game') or self._backup_game_name_for_root(root))
            return root, game, i18n.t('u7.identified_from_translation_status_normalized_mod'), 1
        if len(hits)>1:
            return None, 'ゲーム未特定', i18n.t('u7.multiple_normalized_mod_name_matches_in'), len(hits)
        return None, 'ゲーム未特定', i18n.t('u7.restore_target_not_identified_in_translation'), 0

    def _apply_translation_status_restore_resolution(self, entry, restore_rows=None):
        root,game,source,count=self._resolve_backup_target_from_translation_status(entry, restore_rows=restore_rows)
        if root is not None:
            entry['target_root']=root
            if not entry.get('game') or entry.get('game') == 'ゲーム未特定':
                entry['game']=game
        entry['target_source']=source
        entry['target_candidate_count']=count
        return entry

    def _backup_manifest_records(self):
        records=[]
        if not BACKUP_ROOT.exists():
            return records
        for mf in BACKUP_ROOT.rglob('backup_manifest.json'):
            try:
                data=json.loads(mf.read_text(encoding='utf-8'))
                if isinstance(data, dict):
                    data['_manifest_path']=str(mf)
                    data['_entry_root']=str(mf.parent)
                    records.append(data)
            except Exception:
                continue
        return records

    def _next_overwrite_backup_generation(self, target_root, mod_name):
        try: target_key=str(Path(target_root).resolve())
        except Exception: target_key=str(Path(target_root))
        highest=0
        for rec in self._backup_manifest_records():
            if rec.get('category') != '上書き':
                continue
            raw=rec.get('target_root') or ''
            try: raw_key=str(Path(raw).resolve()) if raw else ''
            except Exception: raw_key=raw
            if raw_key == target_key:
                try: highest=max(highest, int(rec.get('generation') or 0))
                except Exception: pass
        # Legacy pre-v0.11.51 backups had no manifest. Count likely matching top-level
        # overwrite folders so the first new generation does not misleadingly restart at 1.
        safe=self._safe_backup_mod_token(mod_name)
        legacy=0
        try:
            for d in BACKUP_ROOT.iterdir():
                if not d.is_dir() or d.name in {'総合診断','上書き','復元前退避'}:
                    continue
                if safe and safe in d.name:
                    legacy += 1
        except Exception:
            pass
        return max(highest, legacy) + 1

    def _create_full_localization_snapshot(self, target_root, backup_kind, *, category='上書き', source_mod_name='', state_label='', stamp=None, target_lang=None):
        target_root=Path(target_root)
        if core.is_localization_dir_name(target_root.name):
            loc=target_root
            target_root=target_root.parent
        else:
            loc=core.localization_dir_path(target_root)
        mod_name=core.detect_mod_name(target_root) if target_root.exists() else target_root.name
        game_name=self._backup_game_name_for_root(target_root)
        stamp=stamp or datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        generation=None
        mod_hash=hashlib.sha1(str(target_root).encode()).hexdigest()[:8]
        game_dir=BACKUP_ROOT / self._safe_backup_mod_token(game_name)
        mod_dir=game_dir / f"{self._safe_backup_mod_token(mod_name)}__{mod_hash}"
        if category == '上書き':
            generation=self._next_overwrite_backup_generation(target_root, mod_name)
            folder=f"第{generation:04d}回_{stamp}"
            root=mod_dir / '上書き' / folder
        elif category == '復元前退避':
            root=mod_dir / '復元前退避' / stamp
        else:
            root=mod_dir / self._safe_backup_mod_token(category) / stamp
        root.mkdir(parents=True, exist_ok=True)
        dst=root / 'localization'
        existed=loc.exists() and loc.is_dir()
        if existed:
            if dst.exists(): shutil.rmtree(dst)
            shutil.copytree(loc, dst)
        else:
            dst.mkdir(parents=True, exist_ok=True)
        manifest={
            'schema_version': 2,
            'app_version': APP_VERSION,
            'created_at': datetime.now().isoformat(timespec='seconds'),
            'timestamp': stamp,
            'game_name': game_name,
            'category': category,
            'backup_kind': backup_kind,
            'generation': generation,
            'target_mod_name': mod_name,
            'target_root': str(target_root),
            'target_localization': str(loc),
            'source_mod_name': source_mod_name or '',
            'snapshot_type': 'full_localization',
            'localization_existed': bool(existed),
            'state_label': state_label or (i18n.t('u7.source_immediately_before_overwrite_entire_existing') if category == '上書き' else i18n.t('u7.entire_localization_folder_immediately_before_the')),
        }
        if target_lang and target_lang != "japanese":
            manifest["target_lang"] = target_lang
        (root / 'backup_manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
        return root, manifest

    def _build_backup_restore_tab(self):
        t=self.tab_backup_restore
        head=ttk.Frame(t); head.pack(fill='x')
        ttk.Label(head,text=i18n.t('u7.backup_restoration_roll_back_by_game'),font=('',14,'bold')).pack(side='left')
        ttk.Label(head,textvariable=self.backup_restore_summary_var).pack(side='right')
        ttk.Label(t,text=(
            i18n.t('u7.select_a_game_and_mod_on')
        ),foreground='#555',wraplength=1150,justify='left').pack(fill='x',pady=(6,8))

        # 2ブロック構成: 左=対象選択、右=履歴/復元
        panes=ttk.Panedwindow(t,orient='horizontal')
        panes.pack(fill='both',expand=True)

        left=ttk.LabelFrame(panes,text=i18n.t('u7.select_a_game_mod'),padding=8)
        right=ttk.LabelFrame(panes,text=i18n.t('u7.select_backup_history_and_restore'),padding=8)
        panes.add(left,weight=1)
        panes.add(right,weight=3)

        ttk.Label(left,text=i18n.t('u7.game')).pack(anchor='w')
        self.backup_restore_game_combo=ttk.Combobox(left,textvariable=self.backup_restore_game_var,state='readonly')
        self.backup_restore_game_combo.pack(fill='x',pady=(3,8))
        self.backup_restore_game_combo.bind('<<ComboboxSelected>>',self._on_backup_restore_game_changed)

        ttk.Label(left,text=i18n.t('u7.search_2')).pack(anchor='w')
        searchrow=ttk.Frame(left); searchrow.pack(fill='x',pady=(3,8))
        self.backup_restore_search_entry=ttk.Entry(searchrow,textvariable=self.backup_restore_search_var)
        self.backup_restore_search_entry.pack(side='left',fill='x',expand=True)
        self.backup_restore_search_entry.bind('<KeyRelease>',self._on_backup_restore_search_changed)
        ttk.Button(searchrow,text=i18n.t('u7.clear'),command=self._clear_backup_restore_search).pack(side='left',padx=(6,0))

        ttk.Label(left,text=i18n.t('u7.mod_list')).pack(anchor='w')
        modbox=ttk.Frame(left); modbox.pack(fill='both',expand=True,pady=(3,8))
        self.backup_restore_mod_list=tk.Listbox(modbox,exportselection=False,activestyle='dotbox')
        mod_sy=ttk.Scrollbar(modbox,orient='vertical',command=self.backup_restore_mod_list.yview)
        mod_sx=ttk.Scrollbar(modbox,orient='horizontal',command=self.backup_restore_mod_list.xview)
        self.backup_restore_mod_list.configure(yscrollcommand=mod_sy.set,xscrollcommand=mod_sx.set)
        modbox.rowconfigure(0,weight=1); modbox.columnconfigure(0,weight=1)
        self.backup_restore_mod_list.grid(row=0,column=0,sticky='nsew')
        mod_sy.grid(row=0,column=1,sticky='ns')
        mod_sx.grid(row=1,column=0,sticky='ew')
        self.backup_restore_mod_list.bind('<<ListboxSelect>>',self._on_backup_restore_mod_list_selected)
        self.backup_restore_reload_btn=ttk.Button(left,text=i18n.t('u7.reload_backups'),command=self._refresh_backup_restore_entries)
        self.backup_restore_reload_btn.pack(fill='x')

        action=ttk.Frame(right); action.pack(fill='x')
        self.backup_restore_selected_mod_label=ttk.Label(action,text=i18n.t("p0.filter.selected_mod",mod=i18n.t("p0.filter.all_mods")),font=('',11,'bold'))
        self.backup_restore_selected_mod_label.pack(side='left',fill='x',expand=True)
        self.backup_restore_btn=ttk.Button(action,text=i18n.t('u7.restore_selected_backup'),command=self._restore_selected_backup,state='disabled')
        self.backup_restore_btn.pack(side='right',padx=(8,0))

        treebox=ttk.Frame(right); treebox.pack(fill='both',expand=True,pady=(8,0))
        cols=('generation','time','kind','state','target','format')
        self.backup_restore_tree=ttk.Treeview(treebox,columns=cols,show='headings',selectmode='browse',height=18)
        for c,txt,w in (
            ('generation',i18n.t('u7.generation_3'),90),('time',i18n.t('u7.created_at'),165),('kind',i18n.t('u7.backup_type'),155),
            ('state',i18n.t('u7.saved_state_source'),330),('target',i18n.t('u7.restore_target'),390),('format',i18n.t('u7.format'),110)):
            self.backup_restore_tree.heading(c,text=txt)
            self.backup_restore_tree.column(c,width=w,minwidth=80,stretch=False,anchor='w')
        sy=ttk.Scrollbar(treebox,orient='vertical',command=self.backup_restore_tree.yview)
        sx=ttk.Scrollbar(treebox,orient='horizontal',command=self.backup_restore_tree.xview)
        self.backup_restore_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        treebox.rowconfigure(0,weight=1); treebox.columnconfigure(0,weight=1)
        self.backup_restore_tree.grid(row=0,column=0,sticky='nsew')
        sy.grid(row=0,column=1,sticky='ns')
        sx.grid(row=1,column=0,sticky='ew')
        self.backup_restore_tree.bind('<<TreeviewSelect>>',self._on_backup_restore_selected)
        self.backup_restore_tree.bind('<Shift-MouseWheel>',self._on_backup_restore_tree_shift_wheel)
        self.backup_restore_tree.bind('<Shift-Button-4>',lambda _e:self.backup_restore_tree.xview_scroll(-3,'units'))
        self.backup_restore_tree.bind('<Shift-Button-5>',lambda _e:self.backup_restore_tree.xview_scroll(3,'units'))
        self._enable_tree_sort(self.backup_restore_tree)

        detail=ttk.LabelFrame(right,text=i18n.t('u7.selected_backup_details'),padding=6)
        detail.pack(fill='x',pady=(8,0))
        self.backup_restore_detail_label=ttk.Label(detail,textvariable=self.backup_restore_detail_var,foreground='#555',wraplength=760,justify='left')
        self.backup_restore_detail_label.pack(anchor='w',fill='x')
        right.bind('<Configure>',self._on_backup_restore_right_resize)
        self.backup_restore_summary_var.set(i18n.t('u7.waiting_to_load_backups_in_the'))

    def _on_backup_restore_right_resize(self, event=None):
        if hasattr(self,'backup_restore_detail_label') and event is not None:
            try:
                self.backup_restore_detail_label.configure(wraplength=max(360,event.width-40))
            except Exception:
                pass

    def _on_backup_restore_tree_shift_wheel(self, event):
        if not hasattr(self,'backup_restore_tree'):
            return 'break'
        delta=getattr(event,'delta',0)
        if delta:
            step=-1 if delta > 0 else 1
            # macOSの細かなトラックパッド入力でも横移動が見える量にする
            self.backup_restore_tree.xview_scroll(step*3,'units')
        return 'break'

    def _on_backup_restore_mod_list_selected(self, _event=None):
        if not hasattr(self,'backup_restore_mod_list'):
            return
        sel=self.backup_restore_mod_list.curselection()
        if not sel:
            return
        value=self.backup_restore_mod_list.get(sel[0])
        self.backup_restore_mod_var.set(value)
        self._render_backup_restore_entries()

    def _infer_legacy_backup_target(self, backup_name, known_roots=None):
        token=str(backup_name or '')
        token=re.sub(r'^\d{8}_\d{6}(?:_\d+)?_?', '', token)
        token=re.sub(r'_(?:不足分上書き|差分上書き)$','',token)
        token_norm=core._normalize_mod_name_for_match(token.replace('_',' '))
        candidates=[]
        for root in (known_roots if known_roots is not None else self._known_mod_roots_for_restore()):
            name=core.detect_mod_name(root)
            norm=core._normalize_mod_name_for_match(name)
            if token_norm and norm and (token_norm == norm or token_norm in norm or norm in token_norm):
                candidates.append((root,name))
        return candidates[0] if len(candidates)==1 else (None,'')

    def _refresh_backup_restore_entries(self):
        """Refresh backup inventory without blocking Tk's main thread."""
        if not hasattr(self,'backup_restore_tree'):
            return
        if self.backup_restore_refresh_thread and self.backup_restore_refresh_thread.is_alive():
            # Coalesce repeated startup/status-change requests. Never launch several heavy
            # backup scans in parallel when hundreds of backup generations exist.
            self.backup_restore_refresh_pending=True
            self.backup_restore_summary_var.set(i18n.t('u7.loading_backups_refresh_queued'))
            return
        self.backup_restore_refresh_generation += 1
        generation=self.backup_restore_refresh_generation
        self.backup_restore_summary_var.set(i18n.t('u7.loading_backups_in_the_background'))
        try:
            if hasattr(self,'backup_restore_reload_btn'):
                self.backup_restore_reload_btn.config(state='disabled')
        except Exception:
            pass
        def work():
            try:
                entries=self._collect_backup_restore_entries_background()
                self.events.put(('backup_restore_loaded',(generation,entries)))
            except Exception as exc:
                self.events.put(('backup_restore_load_error',(generation,str(exc))))
        self.backup_restore_refresh_thread=threading.Thread(target=work,daemon=True,name='backup-restore-refresh')
        self.backup_restore_refresh_thread.start()

    def _collect_backup_restore_entries_background(self):
        # No Tk calls are allowed in this function. It can scan hundreds/thousands of
        # backup records and resolve Translation Status targets entirely off the UI thread.
        self._restore_status_rows_cache = None
        restore_rows = self._translation_status_rows_for_restore(force_rebuild=True)
        known_restore_roots = self._known_mod_roots_for_restore(restore_rows=restore_rows)
        entries=[]; seen=set()
        for rec in self._backup_manifest_records():
            root=Path(rec.get('_entry_root',''))
            if not root.exists(): continue
            try: seen.add(str(root.resolve()))
            except Exception: seen.add(str(root))
            target=Path(rec.get('target_root') or '') if rec.get('target_root') else None
            game=rec.get('game_name') or (self._backup_game_name_for_root(target) if target else 'ゲーム未特定')
            entries.append({
                'entry_root':root,'snapshot':root/'localization','manifest':rec,
                'generation':rec.get('generation'),'created_at':rec.get('created_at') or rec.get('timestamp',''),
                'game':game,'mod':rec.get('target_mod_name') or (target.name if target else root.name),
                'kind':rec.get('backup_kind') or rec.get('category') or 'バックアップ',
                'state':rec.get('state_label') or i18n.t('u7.localization_backup'),
                'target_root':target,'format':i18n.t('u7.full_snapshot'),'exact':True,
            })
        diag=BACKUP_ROOT/'総合診断'
        if diag.exists():
            for loc in diag.glob('*/*/localization'):
                entry_root=loc.parent
                try: key=str(entry_root.resolve())
                except Exception: key=str(entry_root)
                if key in seen: continue
                mod_guess=re.sub(r'_[0-9a-fA-F]{8}$','',entry_root.name).replace('_',' ')
                target=None; target_name=''
                norm=core._normalize_mod_name_for_match(mod_guess)
                matches=[]
                for r in known_restore_roots:
                    n=core.detect_mod_name(r); rn=core._normalize_mod_name_for_match(n)
                    if norm and rn and (norm==rn or norm in rn or rn in norm): matches.append((r,n))
                if len(matches)==1: target,target_name=matches[0]
                stamp=entry_root.parent.name
                game=self._backup_game_name_for_root(target) if target else 'ゲーム未特定'
                entries.append({'entry_root':entry_root,'snapshot':loc,'manifest':None,'generation':None,'created_at':stamp,
                    'game':game,'mod':target_name or mod_guess,'kind':'総合診断修復','state':i18n.t('u7.entire_localization_folder_immediately_before_diagnostic'),
                    'target_root':target,'format':i18n.t('u7.legacy_full'),'exact':True})
                seen.add(key)
        try:
            top_dirs=list(BACKUP_ROOT.iterdir()) if BACKUP_ROOT.exists() else []
        except Exception:
            top_dirs=[]
        legacy_by_mod={}
        reserved={'総合診断','上書き','復元前退避'} | {self._safe_backup_mod_token(g) for g in core.PARADOX_STEAM_GAMES} | {'ゲーム未特定'}
        for d in sorted(top_dirs,key=lambda x:x.name):
            if not d.is_dir() or d.name in reserved: continue
            if not re.match(r'^\d{8}_\d{6}',d.name): continue
            target,target_name=self._infer_legacy_backup_target(d.name, known_roots=known_restore_roots)
            kind='差分上書き' if d.name.endswith('_差分上書き') else '不足分上書き' if d.name.endswith('_不足分上書き') else '元Mod上書き'
            key=target_name or re.sub(r'^\d{8}_\d{6}(?:_\d+)?_?','',d.name)
            legacy_by_mod.setdefault(key,[]).append(d)
            game=self._backup_game_name_for_root(target) if target else 'ゲーム未特定'
            entries.append({'entry_root':d,'snapshot':d,'manifest':None,'generation':None,'created_at':d.name[:22],
                'game':game,'mod':target_name or key,'kind':kind,'state':i18n.t('u7.existing_files_saved_before_overwrite_legacy'),
                'target_root':target,'format':i18n.t('u7.legacy_partial'),'exact':False})
        for mod, dirs in legacy_by_mod.items():
            order={str(d):i+1 for i,d in enumerate(sorted(dirs,key=lambda x:x.name))}
            for e in entries:
                if e['manifest'] is None and e['entry_root'] in dirs:
                    e['generation']=order.get(str(e['entry_root']))
        for entry in entries:
            self._apply_translation_status_restore_resolution(entry, restore_rows=restore_rows)
        entries.sort(key=lambda e:str(e.get('created_at') or e['entry_root'].name),reverse=True)
        return entries

    def _apply_backup_restore_loaded(self, generation, entries):
        if generation != self.backup_restore_refresh_generation:
            return
        self.backup_restore_refresh_thread=None
        self.backup_restore_entries=list(entries or [])
        games=sorted({str(e.get('game') or 'ゲーム未特定') for e in self.backup_restore_entries},key=str.casefold)
        game_values=[i18n.t("p0.filter.all_games")]+games
        self.backup_restore_game_combo['values']=game_values
        if self.backup_restore_game_var.get() not in game_values:
            self.backup_restore_game_var.set(game_values[0])
        self._refresh_backup_restore_mod_filter()
        self._render_backup_restore_entries()
        try:
            if hasattr(self,'backup_restore_reload_btn'):
                self.backup_restore_reload_btn.config(state='normal')
        except Exception:
            pass
        if self.backup_restore_refresh_pending:
            self.backup_restore_refresh_pending=False
            self.after_idle(self._refresh_backup_restore_entries)

    def _backup_restore_entry_matches_search(self, entry, query=None):
        query=(self.backup_restore_search_var.get() if query is None else query).strip().casefold()
        if not query:
            return True
        generation=entry.get('generation')
        generation_text=(i18n.t('u7.generation', value=int(generation)) if generation else '')
        haystack=' '.join(str(v or '') for v in (
            entry.get('game'), entry.get('mod'), entry.get('kind'), entry.get('state'),
            entry.get('created_at'), generation_text, entry.get('target_root'), entry.get('format'),
            entry.get('entry_root'),
        )).casefold()
        # Consecutive whitespace differences should not make a search miss.
        normalized_query=' '.join(query.split())
        normalized_haystack=' '.join(haystack.split())
        return normalized_query in normalized_haystack

    def _refresh_backup_restore_mod_filter(self):
        game=self.backup_restore_game_var.get() or i18n.t("p0.filter.all_games")
        query=self.backup_restore_search_var.get().strip() if hasattr(self,'backup_restore_search_var') else ''
        mods=sorted({str(e.get('mod') or 'Mod') for e in self.backup_restore_entries
                     if (game == i18n.t("p0.filter.all_games") or str(e.get('game')) == game)
                     and self._backup_restore_entry_matches_search(e,query)},key=str.casefold)
        values=[i18n.t("p0.filter.all_mods")]+mods
        if hasattr(self,'backup_restore_mod_list'):
            current=self.backup_restore_mod_var.get()
            self.backup_restore_mod_list.delete(0,'end')
            for value in values:
                self.backup_restore_mod_list.insert('end',value)
            if current not in values:
                current=values[0]
                self.backup_restore_mod_var.set(current)
            try:
                idx=values.index(current)
                self.backup_restore_mod_list.selection_clear(0,'end')
                self.backup_restore_mod_list.selection_set(idx)
                self.backup_restore_mod_list.see(idx)
            except Exception:
                pass

    def _on_backup_restore_search_changed(self, _event=None):
        self._refresh_backup_restore_mod_filter()
        self._render_backup_restore_entries()

    def _clear_backup_restore_search(self):
        self.backup_restore_search_var.set('')
        self._refresh_backup_restore_mod_filter()
        self._render_backup_restore_entries()
        if hasattr(self,'backup_restore_search_entry'):
            self.backup_restore_search_entry.focus_set()

    def _on_backup_restore_game_changed(self, _event=None):
        self.backup_restore_mod_var.set(i18n.t("p0.filter.all_mods"))
        self._refresh_backup_restore_mod_filter()
        self._render_backup_restore_entries()

    def _render_backup_restore_entries(self):
        if not hasattr(self,'backup_restore_tree'): return
        for iid in self.backup_restore_tree.get_children(): self.backup_restore_tree.delete(iid)
        self.backup_restore_entry_map={}
        game=self.backup_restore_game_var.get() or i18n.t("p0.filter.all_games")
        mod=self.backup_restore_mod_var.get() or i18n.t("p0.filter.all_mods")
        query=self.backup_restore_search_var.get().strip() if hasattr(self,'backup_restore_search_var') else ''
        visible=[]
        for e in self.backup_restore_entries:
            if game != i18n.t("p0.filter.all_games") and str(e.get('game')) != game: continue
            if mod != i18n.t("p0.filter.all_mods") and str(e.get('mod')) != mod: continue
            if not self._backup_restore_entry_matches_search(e,query): continue
            visible.append(e)
        for idx,e in enumerate(visible):
            iid=f'b{idx}'
            self.backup_restore_entry_map[iid]=e
            gen=(i18n.t('u7.generation_2', value=int(e['generation'])) if e.get('generation') else '—')
            created=str(e.get('created_at') or '')
            target=str(e.get('target_root') or i18n.t('u7.restore_target_not_identified'))
            self.backup_restore_tree.insert('', 'end', iid=iid, values=(gen,created,e['kind'],e['state'],target,e['format']))
        scope=[]
        if game != i18n.t("p0.filter.all_games"): scope.append(game)
        if mod != i18n.t("p0.filter.all_mods"): scope.append(mod)
        suffix=(' / ' + ' → '.join(scope)) if scope else ''
        search_suffix=(i18n.t('u7.search', query=query) if query else '')
        self.backup_restore_summary_var.set(i18n.t('u7.backups_of', count=len(visible), count_2=len(self.backup_restore_entries), suffix=suffix, search_suffix=search_suffix))
        if hasattr(self,'backup_restore_selected_mod_label'):
            self.backup_restore_selected_mod_label.config(text=i18n.t('u7.selected_mod', mod=mod))
        self.backup_restore_detail_var.set(i18n.t('u7.select_a_backup_from_the_list'))
        self.backup_restore_btn.config(state='disabled')

    def _on_backup_restore_selected(self, _event=None):
        sel=self.backup_restore_tree.selection() if hasattr(self,'backup_restore_tree') else ()
        e=self.backup_restore_entry_map.get(sel[0]) if sel else None
        if not e:
            self.backup_restore_btn.config(state='disabled'); return
        gen=i18n.t('u7.generation_2', value=int(e['generation'])) if e.get('generation') else i18n.t('u7.generation_not_recorded')
        target=e.get('target_root')
        exact=i18n.t('u7.the_entire_localization_folder_can_be') if e.get('exact') else i18n.t('u7.this_is_a_legacy_partial_backup')
        target_source=e.get('target_source') or (i18n.t('u7.backup_record') if target else i18n.t('u7.not_identified'))
        ambiguity=''
        if not target and int(e.get('target_candidate_count') or 0) > 1:
            ambiguity=i18n.t('u7.candidates_multiple_mods_share_this_name', value=int(e.get('target_candidate_count') or 0))
        self.backup_restore_detail_var.set(
            i18n.t('u7.game_mod_saved_state_backup_restore', game=e.get('game',i18n.t('u7.unknown_game')), mod=e['mod'], gen=gen, kind=e['kind'], state=e['state'], entry_root=e['entry_root'], value=target or i18n.t('u7.not_identified'), target_source=target_source, ambiguity=ambiguity, exact=exact)
        )
        self.backup_restore_btn.config(state='normal' if target and Path(target).exists() else 'disabled')

    def _restore_selected_backup(self):
        if self.backup_restore_operation_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u7.a_backup_restore_is_already_running')); return
        sel=self.backup_restore_tree.selection() if hasattr(self,'backup_restore_tree') else ()
        e=self.backup_restore_entry_map.get(sel[0]) if sel else None
        if not e: return
        target=Path(e.get('target_root') or '')
        if not target.exists():
            messagebox.showerror(APP_NAME,i18n.t('u7.cannot_identify_the_target_mod_no')); return
        gen=i18n.t('u7.generation_2', value=int(e['generation'])) if e.get('generation') else i18n.t('u7.generation_not_recorded')
        warning=(i18n.t('u7.restore_this_backup_game_target_mod', game=e.get('game',i18n.t('u7.unknown_game')), mod=e['mod'], gen=gen, kind=e['kind'], state=e['state'], target=target))
        if not e.get('exact'):
            warning=i18n.t('u7.this_legacy_partial_backup_restores_only', warning=warning)
        if not messagebox.askyesno(i18n.t('u7.confirm_backup_restoration'),i18n.t('u7.continue', warning=warning),icon='warning'): return
        self.backup_restore_btn.config(state='disabled')
        self.backup_restore_summary_var.set(i18n.t('u7.restoring_in_the_background', mod=e['mod']))
        def work():
            try:
                safety_root,_=self._create_full_localization_snapshot(target,'復元前退避',category='復元前退避',state_label=i18n.t('u7.entire_localization_folder_immediately_before_backup'))
                target_loc=core.localization_dir_path(target)
                if e.get('exact'):
                    snapshot=Path(e['snapshot'])
                    if target_loc.exists(): shutil.rmtree(target_loc)
                    if snapshot.exists(): shutil.copytree(snapshot,target_loc)
                    else: target_loc.mkdir(parents=True,exist_ok=True)
                else:
                    src=Path(e['snapshot'])
                    for fp in src.rglob('*'):
                        if not fp.is_file() or fp.name=='backup_manifest.json': continue
                        rel=fp.relative_to(src)
                        if rel.parts and rel.parts[0].lower() in {'japanese','english','simp_chinese','replace'}: dst=target_loc/rel
                        else: dst=target/rel
                        dst.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(fp,dst)
                self._invalidate_mod_status_cache_paths([str(target)])
                self.events.put(('backup_restore_done',(str(target),str(safety_root))))
            except Exception as exc:
                record_error(i18n.t('u7.backup_restoration'),exc,str(target)); self.events.put(('backup_restore_error',str(exc)))
        self.backup_restore_operation_thread=threading.Thread(target=work,daemon=True,name='backup-restore-operation'); self.backup_restore_operation_thread.start()
        self._refresh_operation_states()



    def _set_diagnostic_repair_busy(self, busy):
        """修復実行中は診断対象・競合設定を固定して途中操作を防ぐ。"""
        state="disabled" if busy else "normal"
        for name in (
            "diagnostic_scan_btn","diagnostic_repair_btn","diagnostic_refresh_btn",
            "diagnostic_select_all_btn","diagnostic_clear_selection_btn","diagnostic_relation_btn",
            "diagnostic_keep_source_btn","diagnostic_keep_translation_btn","diagnostic_auto_choice_btn","diagnostic_clear_choice_btn",
            "diagnostic_all_source_btn","diagnostic_all_translation_btn","diagnostic_all_auto_btn",
        ):
            widget=getattr(self,name,None)
            if widget is not None:
                try: widget.config(state=state)
                except Exception: pass
        for name in ("diagnostic_target_tree","diagnostic_tree"):
            widget=getattr(self,name,None)
            if widget is not None:
                try:
                    if busy: widget.state(("disabled",))
                    else: widget.state(("!disabled",))
                except Exception: pass

    def _set_diagnostic_detail(self, text):
        if not hasattr(self,"diagnostic_detail"): return
        self.diagnostic_detail.config(state="normal"); self.diagnostic_detail.delete("1.0","end"); self.diagnostic_detail.insert("1.0",str(text)); self.diagnostic_detail.config(state="disabled")

    def _refresh_diagnostic_targets(self):
        if not hasattr(self,"diagnostic_target_tree"): return
        selected_paths=set()
        for iid in self.diagnostic_target_tree.selection():
            vals=self.diagnostic_target_tree.item(iid,"values")
            if len(vals)>=3: selected_paths.add(str(vals[2]))
        for iid in self.diagnostic_target_tree.get_children(): self.diagnostic_target_tree.delete(iid)
        seen=set(); count=0
        for r in self.mod_research_results:
            path=str(r.get("path") or "")
            if not path or path in seen or not Path(path).exists(): continue
            seen.add(path); iid=f"diagmod_{count}"; count+=1
            self.diagnostic_target_tree.insert("","end",iid=iid,values=(r.get("mod") or Path(path).name,display_status(r.get("status") or ""),path))
            if path in selected_paths: self.diagnostic_target_tree.selection_add(iid)
        self.diagnostic_target_var.set(i18n.t('u7.target_mods', count=count) if count else i18n.t('u7.target_mods_scan_mods_in_the'))

    def _select_all_diagnostic_targets(self):
        if not hasattr(self, "diagnostic_target_tree"):
            return
        children = self.diagnostic_target_tree.get_children()
        if children:
            self.diagnostic_target_tree.selection_set(children)
        self._save_diagnostic_state("target_select_all")

    def _clear_diagnostic_target_selection(self):
        if not hasattr(self, "diagnostic_target_tree"):
            return
        selected = self.diagnostic_target_tree.selection()
        if selected:
            self.diagnostic_target_tree.selection_remove(selected)
        self._save_diagnostic_state("target_selection_cleared")

    def _selected_diagnostic_roots(self):
        roots=[]
        if not hasattr(self,"diagnostic_target_tree"): return roots
        for iid in self.diagnostic_target_tree.selection():
            vals=self.diagnostic_target_tree.item(iid,"values")
            if len(vals)>=3:
                p=Path(str(vals[2]))
                if p.exists(): roots.append(p)
        return roots

    def _all_known_mod_roots_for_diagnostic(self):
        roots=[]; seen=set()
        def add(p):
            try: key=str(Path(p).expanduser().resolve())
            except Exception: key=str(p)
            if key not in seen and Path(p).is_dir(): seen.add(key); roots.append(Path(p))
        for r in self.mod_research_results:
            if r.get("path"): add(r.get("path"))
        # Also include discovered Workshop/local Mod roots so foreign-key attribution
        # is not limited to the rows currently visible in Translation Status.
        for row in self.detected_mod_locations:
            raw=row.get("path")
            if not raw: continue
            try:
                for root in core.find_mod_roots(Path(raw)): add(root)
            except Exception:
                continue
        return roots

    def _diagnostic_source_key_index(self, roots, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        index={}; meta={}
        for root in roots:
            loc=core.mod_localization_root(root)
            if not loc or not loc.exists(): continue
            name=core.detect_mod_name(root)
            try: rid=str(root.resolve())
            except Exception: rid=str(root)
            meta[rid]={"name":name,"path":str(root),"keys":set()}
            keys=set()
            for f in core.gather_yml_files(loc):
                try:
                    lang,entries,_=core.parse_localization_file(f)
                except Exception:
                    continue
                if lang and lang != target_lang and (target_lang != "japanese" or lang in {"english","simp_chinese"}):
                    keys.update(entries)
            meta[rid]["keys"] = set(keys)
            for key in keys: index.setdefault(key,set()).add(rid)
        return index,meta

    def _diagnostic_translation_relation_map(self, roots, *, target_lang=None):
        """Map one Japanese candidate root to every weighted source relation.

        v0.11.36 deliberately keeps *all* relations.  Comprehensive Japanese
        packs can legitimately translate several independent Mods, so a
        candidate must not be collapsed to one strongest source.
        """
        target_lang = target_lang or _current_target_lang(self)
        if target_lang == "english": return {}
        translation_index=self._build_stable_translation_mod_index(roots, target_lang=target_lang)
        relations={}
        for source_root in roots:
            try:
                ranked=core.rank_external_japanese_translations(Path(source_root), translation_index, target_lang=target_lang)
            except Exception as exc:
                record_error(i18n.t('u7.full_diagnostics_japanese_translation_mod_weight' if target_lang == 'japanese' else 'u7.full_diagnostics_japanese_translation_mod_weight.target', target_name=i18n.t('lang.' + target_lang)), exc, str(source_root)); continue
            source_name=core.detect_mod_name(Path(source_root))
            try: source_id=str(Path(source_root).resolve())
            except Exception: source_id=str(source_root)
            for row in ranked:
                if row.get("classification") not in {"auto","candidate"}:
                    continue
                try: cand_id=str(Path(row.get("path","")).resolve())
                except Exception: cand_id=str(row.get("path", ""))
                rel={
                    "source_path":source_id,"source_mod":source_name,
                    "candidate_path":cand_id,"candidate_mod":row.get("mod", ""),
                    "score":float(row.get("score",0.0) or 0.0),
                    "classification":row.get("classification", ""),
                    "precision":float(row.get("precision",0.0) or 0.0),
                    "coverage":float(row.get("coverage",0.0) or 0.0),
                    "overlap_keys":int(row.get("overlap_keys",0) or 0),
                    "reasons":list(row.get("reasons") or []),
                }
                relations.setdefault(cand_id,[]).append(rel)
        for cand_id, rows in relations.items():
            rows.sort(key=lambda x:(float(x.get("score",0.0)),float(x.get("coverage",0.0))),reverse=True)
        return relations

    def _diagnostic_japanese_occurrence_index(self, roots, *, target_lang=None):
        """Return key -> Japanese occurrences across known Mod roots."""
        target_lang = target_lang or _current_target_lang(self)
        index={}
        for root in roots:
            loc=core.mod_localization_root(root)
            if not loc or not loc.exists(): continue
            try: rid=str(Path(root).resolve())
            except Exception: rid=str(root)
            for f in core.gather_yml_files(loc):
                try:
                    lang,entries,_=core.parse_localization_file(f)
                except Exception:
                    continue
                if lang!=target_lang: continue
                for key,value in entries.items():
                    index.setdefault(key,[]).append({"root":rid,"file":str(f),"value":value})
        return index

    def _diagnostic_allowed_context(self, roots, source_meta, relation_map):
        """Build per-root allowed key sets and relation metadata for safe repair."""
        ctx={}
        for root in roots:
            try: rid=str(Path(root).resolve())
            except Exception: rid=str(root)
            own=set((source_meta.get(rid) or {}).get("keys") or set())
            rels=list(relation_map.get(rid) or [])
            auto_rels=[r for r in rels if r.get("classification")=="auto"]
            candidate_rels=[r for r in rels if r.get("classification")=="candidate"]
            linked=set()
            for rel in auto_rels:
                linked.update((source_meta.get(str(rel.get("source_path") or "")) or {}).get("keys") or set())
            allowed=set(own)|linked
            ctx[rid]={
                "root":rid,"own_source_keys":own,"linked_source_keys":linked,"allowed_keys":allowed,
                "auto_relations":auto_rels,"candidate_relations":candidate_rels,
                "is_translation_mod":bool(auto_rels),
            }
        return ctx

    def _diagnostic_relation_id(self, source_id, translation_id, *, target_lang=None):
        raw=f"{source_id}\0{translation_id}".encode("utf-8","ignore")
        target_lang = target_lang or _current_target_lang(self)
        if target_lang != "japanese": raw += f"\0{target_lang}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _build_diagnostic_integrations(self, selected_roots, source_meta, allowed_context, occurrences, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        if target_lang == "english": return []
        selected_ids=set()
        for r in selected_roots:
            try: selected_ids.add(str(Path(r).resolve()))
            except Exception: selected_ids.add(str(r))
        pairs=[]; seen=set()
        for trans_id,ctx in (allowed_context or {}).items():
            for rel in ctx.get("auto_relations") or []:
                source_id=str(rel.get("source_path") or "")
                if not source_id or (source_id not in selected_ids and trans_id not in selected_ids):
                    continue
                rid=self._diagnostic_relation_id(source_id,trans_id, target_lang=target_lang)
                if rid in seen: continue
                seen.add(rid)
                keys=set((source_meta.get(source_id) or {}).get("keys") or set())
                source_vals={}; trans_vals={}
                for key in keys:
                    so=[o for o in occurrences.get(key,[]) if o.get("root")==source_id]
                    to=[o for o in occurrences.get(key,[]) if o.get("root")==trans_id]
                    if so: source_vals[key]=so
                    if to: trans_vals[key]=to
                source_only=set(source_vals)-set(trans_vals); trans_only=set(trans_vals)-set(source_vals); both=set(source_vals)&set(trans_vals)
                identical=set(); conflicts=set()
                for key in both:
                    sv={o.get("value") for o in source_vals[key]}; tv={o.get("value") for o in trans_vals[key]}
                    if len(sv)==1 and sv==tv: identical.add(key)
                    else: conflicts.add(key)
                trans_override=self._mod_relation_override(Path(trans_id), target_lang=target_lang)
                manual_sources=set(trans_override.get("source_paths") or [])
                manual_translation=(trans_override.get("role")=="translation")
                manual_relation=(manual_translation and source_id in manual_sources)
                if manual_translation:
                    target="translation"
                    if manual_relation:
                        target_reason=i18n.t('u7.override_the_japanese_translation_mod_source' if target_lang == 'japanese' else 'u7.override_the_japanese_translation_mod_source.target', target_name=i18n.t('lang.' + target_lang))
                    else:
                        target_reason=i18n.t('u7.override_this_mod_is_manually_classified' if target_lang == 'japanese' else 'u7.override_this_mod_is_manually_classified.target', target_name=i18n.t('lang.' + target_lang))
                else:
                    sc=len(source_vals); tc=len(trans_vals)
                    target="source" if sc>tc else "translation"
                    target_reason=i18n.t('u7.auto_organize_current_valid_translations_source' if target_lang == 'japanese' else 'u7.auto_organize_current_valid_translations_source.target', target_name=i18n.t('lang.' + target_lang), sc=sc, tc=tc)
                pairs.append({"id":rid,"source_root":source_id,"translation_root":trans_id,
                    "source_mod":core.detect_mod_name(Path(source_id)) if Path(source_id).exists() else Path(source_id).name,
                    "translation_mod":core.detect_mod_name(Path(trans_id)) if Path(trans_id).exists() else Path(trans_id).name,
                    "source_keys":keys,"source_vals":source_vals,"translation_vals":trans_vals,
                    "source_only":source_only,"translation_only":trans_only,"identical":identical,"conflict_keys":conflicts,
                    "target":target,"target_reason":target_reason,"manual_priority":manual_translation})
        return pairs

    def _attach_diagnostic_integration_issues(self, analyses, integrations, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        by_path={str(a.get("path") or ""):a for a in analyses}
        total=auto=conflicts=unresolved=0
        for pair in integrations:
            total += len(set(pair["source_vals"])|set(pair["translation_vals"]))
            auto += len(pair["source_only"])+len(pair["translation_only"])+len(pair["identical"])
            conflicts += len(pair["conflict_keys"])
            for key in pair["conflict_keys"]:
                cid=self._diagnostic_conflict_id(pair["source_root"],pair["translation_root"],key, target_lang=target_lang)
                if not self.diagnostic_conflict_choices.get(cid): unresolved += 1
            host=by_path.get(pair["source_root"]) or by_path.get(pair["translation_root"])
            if not host: continue
            host.setdefault("integrations",[]).append({"id":pair["id"],"source_root":pair["source_root"],"translation_root":pair["translation_root"],"target":pair["target"],"manual_priority":pair.get("manual_priority",False),"target_reason":pair.get("target_reason","")})
            host.setdefault("issues",[]).append({"severity":"INFO","kind":"本体/日本語化Mod統合","file":"","count":len(set(pair["source_vals"])|set(pair["translation_vals"])),
                "location":i18n.t('u7.source_japanese_translation_mod_2' if target_lang == 'japanese' else 'u7.source_japanese_translation_mod_2.target', target_name=i18n.t('lang.' + target_lang)),
                "plan":i18n.t('u7.automatically_integrate_into', value=i18n.t('u7.source_mod') if pair['target']=='source' else i18n.t('u7.japanese_translation_mod' if target_lang == 'japanese' else 'u7.japanese_translation_mod.target', target_name=i18n.t('lang.' + target_lang))),
                "decision":i18n.t('u7.source_japanese_translation_mod'),
                "manual_priority":bool(pair.get("manual_priority")),
                "detail":i18n.t('u7.repair_plan_integrate_into_source_only' if target_lang == 'japanese' else 'u7.repair_plan_integrate_into_source_only.target', target_name=i18n.t('lang.' + target_lang), source_mod=pair['source_mod'], translation_mod=pair['translation_mod'], value=i18n.t('u7.source_mod') if pair['target']=='source' else i18n.t('u7.japanese_translation_mod' if target_lang == 'japanese' else 'u7.japanese_translation_mod.target', target_name=i18n.t('lang.' + target_lang)), target_reason=pair['target_reason'], count=len(pair['source_only']), count_2=len(pair['translation_only']), count_3=len(pair['identical']), count_4=len(pair['conflict_keys']))})
            existing={x.get("conflict_id") for x in host.get("issues",[]) if x.get("conflict_id")}
            for key in sorted(pair["conflict_keys"]):
                cid=self._diagnostic_conflict_id(pair["source_root"],pair["translation_root"],key, target_lang=target_lang)
                if cid in existing: continue
                choice=self.diagnostic_conflict_choices.get(cid)
                auto_side=pair.get("target")
                if choice=="source": decision=i18n.t('u7.source_mod_translation')
                elif choice=="translation": decision=i18n.t('u7.japanese_translation_mod_translation' if target_lang == 'japanese' else 'u7.japanese_translation_mod_translation.target', target_name=i18n.t('lang.' + target_lang))
                elif choice=="auto": decision=i18n.t('u7.auto_organize_translation_from', value=i18n.t('u7.source_mod') if auto_side=='source' else i18n.t('u7.japanese_translation_mod' if target_lang == 'japanese' else 'u7.japanese_translation_mod.target', target_name=i18n.t('lang.' + target_lang)))
                else: decision=i18n.t('u7.not_selected')
                host.setdefault("conflicts",[]).append({"id":cid,"key":key,"source_root":pair["source_root"],"translation_root":pair["translation_root"],"source_mod":pair["source_mod"],"translation_mod":pair["translation_mod"],"choice":choice})
                host.setdefault("issues",[]).append({"severity":"WARN","kind":"本体/日本語化Mod重複","file":"","count":1,"conflict_id":cid,
                    "location":i18n.t('u7.both'), "plan":i18n.t('u7.resolve_translation_conflicts'), "decision":decision,
                    "manual_priority":bool(pair.get("manual_priority")),
                    "detail":i18n.t('u7.source_and_japanese_translation_mod_have' if target_lang == 'japanese' else 'u7.source_and_japanese_translation_mod_have.target', target_name=i18n.t('lang.' + target_lang), localization_key=key, source_mod=pair['source_mod'], translation_mod=pair['translation_mod'], value=i18n.t('u7.override_auto_organize_prioritizes_manual_settings') if pair.get('manual_priority') else '')})
        return {"total":total,"auto":auto,"conflicts":conflicts,"unresolved":unresolved}

    def _diagnostic_conflict_id(self, source_id, translation_id, key, *, target_lang=None):
        raw=f"{source_id}\0{translation_id}\0{key}".encode("utf-8","ignore")
        target_lang = target_lang or _current_target_lang(self)
        if target_lang != "japanese": raw += f"\0{target_lang}".encode("utf-8")
        return hashlib.sha1(raw).hexdigest()

    def _analyze_localization_health(self, mod_root, source_index, source_meta, translation_relations=None, allowed_context=None, japanese_occurrences=None, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        mod_root=Path(mod_root); loc=core.mod_localization_root(mod_root)
        name=core.detect_mod_name(mod_root)
        result={"mod":name,"path":str(mod_root),"localization":str(loc or ""),"issues":[],"remove_by_file":{},"stats":{},"conflicts":[],"target_lang":target_lang}
        if not loc or not loc.exists():
            result["issues"].append({"severity":"ERROR","kind":"localization欠落","file":"","count":1,"detail":i18n.t('u7.localization_folder_not_found_2')})
            return result
        try: self_id=str(mod_root.resolve())
        except Exception: self_id=str(mod_root)
        source_keys=set(); jp_files=[]; english_files=[]; chinese_files=[]; jp_key_files={}; jp_values={}
        for f in core.gather_yml_files(loc):
            try: lang,entries,_=core.parse_localization_file(f)
            except Exception as exc:
                result["issues"].append({"severity":"WARN","kind":"YAML読込エラー","file":str(f),"count":1,"detail":str(exc)})
                continue
            if lang=="english": english_files.append((f,entries))
            elif lang=="simp_chinese": chinese_files.append((f,entries))
            if lang and lang != target_lang and (target_lang != "japanese" or lang in {"english", "simp_chinese"}): source_keys.update(entries)
            if lang==target_lang:
                jp_files.append((f,entries))
                for k,v in entries.items():
                    jp_key_files.setdefault(k,[]).append(str(f)); jp_values.setdefault(k,[]).append((str(f),v))

        ctx=(allowed_context or {}).get(self_id) or {}
        own_source_keys=set(ctx.get("own_source_keys") or source_keys)
        linked_source_keys=set(ctx.get("linked_source_keys") or set())
        auto_rels=list(ctx.get("auto_relations") or [])
        candidate_rels=list(ctx.get("candidate_relations") or [])
        allowed_source_keys=set(ctx.get("allowed_keys") or source_keys)
        has_repair_basis=bool(own_source_keys or auto_rels)
        result["stats"]={
            "english_files":len(english_files),"chinese_files":len(chinese_files),"japanese_files":len(jp_files),
            "source_keys":len(source_keys),"japanese_keys":len(jp_key_files),"allowed_keys":len(allowed_source_keys),
            "translation_sources":len(auto_rels),
        }

        if auto_rels:
            names=[]
            for rel in auto_rels:
                reason_text="; ".join(str(x) for x in (rel.get("reasons") or []))
                item=i18n.t('u7.points_source_mod_coverage', source_mod=rel.get('source_mod',''), value=float(rel.get('score',0) or 0), value_2=float(rel.get('coverage',0) or 0)*100)
                if reason_text:
                    item = i18n.t('u7.reason', item=item, reason_text=reason_text)
                names.append(item)
            result["issues"].append({"severity":"INFO","kind":"日本語化Mod（複数対応可）","score":f"{max(float(r.get('score',0) or 0) for r in auto_rels):.1f}","file":"","count":len(auto_rels),"detail":i18n.t('u7.linked_sources', value="\n".join(names))})
        if candidate_rels:
            names=[]
            for rel in candidate_rels[:6]:
                reason_text="; ".join(str(x) for x in (rel.get("reasons") or []))
                item=i18n.t('u7.points_source_mod_coverage', source_mod=rel.get('source_mod',''), value=float(rel.get('score',0) or 0), value_2=float(rel.get('coverage',0) or 0)*100)
                if reason_text:
                    item = i18n.t('u7.reason', item=item, reason_text=reason_text)
                names.append(item)
            result["issues"].append({"severity":"WARN","kind":"日本語化Mod候補（未確定）","file":"","count":len(candidate_rels),"detail":i18n.t('u7.not_included_in_the_valid_key', value="\n".join(names))})

        if not english_files:
            result["issues"].append({"severity":"WARN","kind":"英語原文なし","file":"","count":0,"detail":i18n.t('u7.no_english_localization_found_this_may' if target_lang == 'japanese' else 'u7.no_english_localization_found_this_may.target', target_name=i18n.t('lang.' + target_lang))})
        if not chinese_files:
            result["issues"].append({"severity":"INFO","kind":"簡体字中国語なし","file":"","count":0,"detail":i18n.t('u7.no_simplified_chinese_localization_this_is')})
        if not jp_files:
            result["issues"].append({"severity":"INFO","kind":"日本語なし","file":"","count":0,"detail":i18n.t('u7.no_japanese_localization_yet' if target_lang == 'japanese' else 'u7.no_japanese_localization_yet.target', target_name=i18n.t('lang.' + target_lang))})

        duplicate={k:v for k,v in jp_key_files.items() if len(v)>1}
        identical_dup=0; conflicting_dup=0
        for key, files in duplicate.items():
            vals={v for _,v in jp_values.get(key,[])}
            if len(vals)<=1: identical_dup+=1
            else: conflicting_dup+=1
        if identical_dup:
            result["issues"].append({"severity":"WARN","kind":"同一Mod内の完全重複","file":"","count":identical_dup,"detail":i18n.t('u7.the_same_japanese_translation_key_appears' if target_lang == 'japanese' else 'u7.the_same_japanese_translation_key_appears.target', target_name=i18n.t('lang.' + target_lang))})
        if conflicting_dup:
            result["issues"].append({"severity":"WARN","kind":"同一Mod内の訳競合","file":"","count":conflicting_dup,"detail":i18n.t('u7.the_same_key_has_different_japanese' if target_lang == 'japanese' else 'u7.the_same_key_has_different_japanese.target', target_name=i18n.t('lang.' + target_lang))})

        total_extras=0
        # v0.11.36: once a reliable basis exists, every Japanese key outside
        # the own English/Chinese union or linked translation-source unions is
        # unnecessary.  We no longer require attribution to another Mod.
        if has_repair_basis:
            for f,entries in jp_files:
                unnecessary=[key for key in entries if key not in allowed_source_keys]
                if unnecessary:
                    total_extras += len(unnecessary)
                    result["remove_by_file"].setdefault(str(f),set()).update(unnecessary)
                    result["issues"].append({"severity":"ERROR","kind":"不要日本語キー","file":str(f),"count":len(unnecessary),"detail":i18n.t('u7.absent_from_the_source_mod_s' if target_lang == 'japanese' else 'u7.absent_from_the_source_mod_s.target', target_name=i18n.t('lang.' + target_lang))})
                    if len(unnecessary)==len(entries):
                        result["issues"].append({"severity":"ERROR","kind":"不要日本語ファイル","file":str(f),"count":len(entries),"detail":i18n.t('u7.all_localization_keys_in_this_yaml')})
        elif jp_files:
            result["issues"].append({"severity":"WARN","kind":"修復基準なし","file":"","count":len(jp_key_files),"detail":i18n.t('u7.no_english_chinese_source_or_high' if target_lang == 'japanese' else 'u7.no_english_chinese_source_or_high.target', target_name=i18n.t('lang.' + target_lang))})

        # Same-root identical duplicates: keep one deterministic file, remove the rest.
        for key,occ in jp_values.items():
            if len(occ)<=1: continue
            vals={v for _,v in occ}
            if len(vals)==1:
                for file_path,_ in sorted(occ,key=lambda x:x[0])[1:]:
                    result["remove_by_file"].setdefault(file_path,set()).add(key)

        # Cross-Mod duplicate conflicts only between a source Mod and a trusted
        # Japanese translation Mod linked to that source.  These require a
        # per-key user choice: keep source or keep translation.
        occurrences=japanese_occurrences or {}
        if own_source_keys:
            linked_translation_ids=[]
            for cand_id,cand_ctx in (allowed_context or {}).items():
                for rel in cand_ctx.get("auto_relations") or []:
                    if str(rel.get("source_path") or "")==self_id:
                        linked_translation_ids.append(cand_id); break
            self_jp_keys=set(jp_key_files)
            for cand_id in linked_translation_ids:
                cand_name=core.detect_mod_name(Path(cand_id)) if Path(cand_id).exists() else Path(cand_id).name
                for key in sorted(self_jp_keys & own_source_keys):
                    cand_occ=[o for o in occurrences.get(key,[]) if o.get("root")==cand_id]
                    if not cand_occ: continue
                    own_occ=[o for o in occurrences.get(key,[]) if o.get("root")==self_id]
                    if not own_occ: continue
                    own_values={o.get("value") for o in own_occ}
                    cand_values={o.get("value") for o in cand_occ}
                    if len(own_values)==1 and own_values==cand_values:
                        continue
                    cid=self._diagnostic_conflict_id(self_id,cand_id,key, target_lang=target_lang)
                    choice=self.diagnostic_conflict_choices.get(cid)
                    choice_text=i18n.t('u7.source_mod_translation') if choice=="source" else i18n.t('u7.japanese_translation_mod_translation' if target_lang == 'japanese' else 'u7.japanese_translation_mod_translation.target', target_name=i18n.t('lang.' + target_lang)) if choice=="translation" else i18n.t('u7.source_japanese_translation_mod') if choice=="auto" else i18n.t('u7.not_selected')
                    conflict={"id":cid,"key":key,"source_root":self_id,"translation_root":cand_id,"source_mod":name,"translation_mod":cand_name,"choice":choice}
                    result["conflicts"].append(conflict)
                    result["issues"].append({
                        "severity":"WARN","kind":"本体/日本語化Mod重複","file":"","count":1,"conflict_id":cid,
                        "location":i18n.t('u7.both'), "plan":i18n.t('u7.resolve_translation_conflicts'), "decision":choice_text,
                        "detail":i18n.t('u7.present_in_both_source_and_japanese' if target_lang == 'japanese' else 'u7.present_in_both_source_and_japanese.target', target_name=i18n.t('lang.' + target_lang), localization_key=key, name=name, cand_name=cand_name)
                    })

        if source_keys and len(jp_files) > max(4, (len(english_files)+len(chinese_files))*2):
            result["issues"].append({"severity":"WARN","kind":"日本語ファイル異常増加","file":"","count":len(jp_files),"detail":i18n.t('u7.there_are_japanese_yaml_files_versus' if target_lang == 'japanese' else 'u7.there_are_japanese_yaml_files_versus.target', target_name=i18n.t('lang.' + target_lang), count=len(jp_files), value=len(english_files)+len(chinese_files))})
        result["stats"].update({"extra_keys":total_extras,"conflicts":len(result["conflicts"])})
        if not result["issues"]:
            result["issues"].append({"severity":"OK","kind":"異常なし","file":"","count":0,"detail":i18n.t('u7.no_obvious_contamination_found_within_the')})
        return result

    def _backup_localization_for_repair(self, mod_root, stamp):
        mod_root=Path(mod_root); loc=core.mod_localization_root(mod_root)
        if not loc or not loc.exists(): raise FileNotFoundError(i18n.t('u7.localization_folder_not_found'))
        root,_=self._create_full_localization_snapshot(
            mod_root, "総合診断修復", category="総合診断", stamp=stamp,
            state_label=i18n.t('u7.entire_localization_folder_immediately_before_diagnostic')
        )
        dst=root / "localization"
        if not dst.exists(): raise OSError(i18n.t('u7.could_not_verify_backup_creation'))
        return dst

    def _apply_localization_removal_plan(self, removals_by_file):
        """Remove selected Japanese key definitions while preserving encoding."""
        removed=0; files_changed=0; files_deleted=0
        for raw,keys in (removals_by_file or {}).items():
            path=Path(raw)
            if not path.exists() or not keys: continue
            remove=set(keys)
            raw_bytes=path.read_bytes()
            if raw_bytes.startswith(b"\xff\xfe"):
                original_encoding="utf-16-le"
            elif raw_bytes.startswith(b"\xfe\xff"):
                original_encoding="utf-16-be"
            elif raw_bytes.startswith(b"\xef\xbb\xbf"):
                original_encoding="utf-8-sig"
            else:
                original_encoding="utf-8"
            text=core.read_localization_text(path)
            out=[]
            for line in text.splitlines(keepends=True):
                m=core.parse_line(line)
                if m and m.group("key").strip() in remove:
                    removed += 1; continue
                out.append(line)
            new_text=''.join(out)
            remaining=[]
            for line in new_text.splitlines():
                m=core.parse_line(line)
                if m: remaining.append(m.group("key").strip())
            if not remaining:
                path.unlink(); files_deleted += 1
            else:
                payload=new_text.lstrip('\ufeff')
                if original_encoding=="utf-16-le":
                    path.write_bytes(b"\xff\xfe"+payload.encode("utf-16-le"))
                elif original_encoding=="utf-16-be":
                    path.write_bytes(b"\xfe\xff"+payload.encode("utf-16-be"))
                elif original_encoding=="utf-8-sig":
                    path.write_bytes(b"\xef\xbb\xbf"+payload.encode("utf-8"))
                else:
                    path.write_bytes(payload.encode("utf-8"))
                files_changed += 1
        return {"removed_keys":removed,"changed_files":files_changed,"deleted_files":files_deleted}

    def _set_diagnostic_conflict_choice(self, choice):
        if not hasattr(self,"diagnostic_tree"): return
        changed=0
        for iid in self.diagnostic_tree.selection():
            row=self.diagnostic_result_map.get(iid) or {}
            cid=row.get("conflict_id")
            if not cid: continue
            if choice is None: self.diagnostic_conflict_choices.pop(cid,None)
            else: self.diagnostic_conflict_choices[cid]=choice
            changed += 1
        if not changed:
            has_conflict=any(issue.get("conflict_id") for a in self.diagnostic_last_analyses for issue in (a.get("issues") or []))
            if has_conflict:
                messagebox.showinfo(APP_NAME,i18n.t('u7.select_source_japanese_translation_mod_duplicates' if _current_target_lang(self) == 'japanese' else 'u7.select_source_japanese_translation_mod_duplicates.target', target_name=i18n.t('lang.' + _current_target_lang(self))))
            else:
                messagebox.showinfo(APP_NAME,i18n.t('u7.no_translation_conflicts_between_source_and' if _current_target_lang(self) == 'japanese' else 'u7.no_translation_conflicts_between_source_and.target', target_name=i18n.t('lang.' + _current_target_lang(self))))
            return
        # Re-render the last diagnostic result so each key keeps an independent choice.
        for analysis in self.diagnostic_last_analyses:
            for issue in analysis.get("issues") or []:
                cid=issue.get("conflict_id")
                if not cid: continue
                c=self.diagnostic_conflict_choices.get(cid)
                issue["decision"]=i18n.t('u7.source_mod_translation') if c=="source" else i18n.t('u7.japanese_translation_mod_translation' if _current_target_lang(self) == 'japanese' else 'u7.japanese_translation_mod_translation.target', target_name=i18n.t('lang.' + _current_target_lang(self))) if c=="translation" else i18n.t('u7.source_japanese_translation_mod') if c=="auto" else i18n.t('u7.not_selected')
        self._populate_diagnostic_results(self.diagnostic_last_analyses)
        self.diagnostic_summary_var.set(i18n.t('u7.updated_conflict_preferences', changed=changed))
        self._save_diagnostic_state("conflict_choice_changed")

    def _set_all_diagnostic_conflict_choices(self, choice):
        conflict_ids=[]
        for analysis in self.diagnostic_last_analyses:
            for issue in analysis.get("issues") or []:
                cid=issue.get("conflict_id")
                if cid and cid not in conflict_ids:
                    conflict_ids.append(cid)
        if not conflict_ids:
            messagebox.showinfo(APP_NAME,i18n.t('u7.no_translation_conflicts_need_bulk_choices'))
            return
        label=i18n.t('u7.source_mod_translation') if choice=="source" else i18n.t('u7.japanese_translation_mod_translation' if _current_target_lang(self) == 'japanese' else 'u7.japanese_translation_mod_translation.target', target_name=i18n.t('lang.' + _current_target_lang(self))) if choice=="translation" else i18n.t('u7.source_japanese_translation_mod')
        confirm_text=(
            i18n.t('u7.set_all_translation_conflicts_in_the', count=len(conflict_ids), label=label)
        )
        if not messagebox.askyesno(APP_NAME, confirm_text):
            return
        for cid in conflict_ids:
            self.diagnostic_conflict_choices[cid]=choice
        for analysis in self.diagnostic_last_analyses:
            for issue in analysis.get("issues") or []:
                cid=issue.get("conflict_id")
                if cid:
                    issue["decision"]=i18n.t('u7.source_mod_translation') if choice=="source" else i18n.t('u7.japanese_translation_mod_translation' if _current_target_lang(self) == 'japanese' else 'u7.japanese_translation_mod_translation.target', target_name=i18n.t('lang.' + _current_target_lang(self))) if choice=="translation" else i18n.t('u7.source_japanese_translation_mod')
        self._populate_diagnostic_results(self.diagnostic_last_analyses)
        self.diagnostic_summary_var.set(i18n.t('u7.set_all_conflict_preferences_to', count=len(conflict_ids), label=label))
        self._save_diagnostic_state("all_conflict_choices_changed")

    def _start_localization_diagnostic(self, repair=False):
        target_lang = _current_target_lang(self)
        if self.diagnostic_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u7.full_diagnostics_are_already_running_in'))
            return
        roots=self._selected_diagnostic_roots()
        self._save_diagnostic_state("diagnostic_start")
        if not roots:
            messagebox.showinfo(APP_NAME,i18n.t('u7.select_at_least_one_target_mod'))
            return
        if repair:
            if not messagebox.askyesno(APP_NAME,
                i18n.t('u7.back_up_the_entire_localization_folder' if target_lang == 'japanese' else 'u7.back_up_the_entire_localization_folder.target', target_name=i18n.t('lang.' + target_lang))):
                return
        self.diagnostic_generation += 1; generation=self.diagnostic_generation
        self.diagnostic_running_repair=bool(repair)
        if repair:
            self._set_diagnostic_repair_busy(True)
        else:
            self.diagnostic_scan_btn.config(state="disabled"); self.diagnostic_repair_btn.config(state="disabled")
        self.diagnostic_summary_var.set(i18n.t('u7.repairing_with_configured_choices', count=len(roots)) if repair else i18n.t('u7.diagnosing_in_the_background', count=len(roots)))
        self._set_diagnostic_detail(i18n.t('u7.indexing_source_keys_japanese_translation_mod' if target_lang == 'japanese' else 'u7.indexing_source_keys_japanese_translation_mod.target', target_name=i18n.t('lang.' + target_lang)))
        def work():
            try:
                all_roots=self._all_known_mod_roots_for_diagnostic()
                for r in roots:
                    if all(str(r)!=str(x) for x in all_roots): all_roots.append(r)
                source_index,source_meta=self._diagnostic_source_key_index(all_roots, target_lang=target_lang)
                relation_map=self._diagnostic_translation_relation_map(all_roots, target_lang=target_lang)
                allowed_context=self._diagnostic_allowed_context(all_roots,source_meta,relation_map)
                occurrences=self._diagnostic_japanese_occurrence_index(all_roots, target_lang=target_lang)
                before=[]; logs=[]; stamp=datetime.now().strftime("%Y-%m-%d_%H%M%S")
                for i,root in enumerate(roots,1):
                    self.events.put(("diagnostic_progress",{"generation":generation,"done":i,"total":len(roots),"mod":core.detect_mod_name(root),"phase":i18n.t('u7.diagnostic_phase')}))
                    try: relation_key=str(Path(root).resolve())
                    except Exception: relation_key=str(root)
                    before.append(self._analyze_localization_health(root,source_index,source_meta,relation_map.get(relation_key),allowed_context,occurrences, target_lang=target_lang))
                integrations=self._build_diagnostic_integrations(roots,source_meta,allowed_context,occurrences, target_lang=target_lang)
                integration_summary=self._attach_diagnostic_integration_issues(before,integrations, target_lang=target_lang)

                if repair:
                    selected_ids=set()
                    for root in roots:
                        try: selected_ids.add(str(Path(root).resolve()))
                        except Exception: selected_ids.add(str(root))
                    unresolved=[]
                    for pair in integrations:
                        for key in pair.get("conflict_keys") or set():
                            cid=self._diagnostic_conflict_id(pair["source_root"],pair["translation_root"],key, target_lang=target_lang)
                            if not self.diagnostic_conflict_choices.get(cid):
                                unresolved.append((pair,key))
                    if unresolved:
                        self.events.put(("diagnostic_choices_required",{"generation":generation,"before":before,"message":i18n.t('u7.translation_conflicts_with_no_retention_choice', count=len(unresolved))}))
                        return

                    # Any relation consolidation may modify both sides. Back up every touched localization first.
                    touched={str(Path(r).resolve()) for r in roots}
                    for pair in integrations:
                        touched.add(pair["source_root"]); touched.add(pair["translation_root"])
                    for i,raw in enumerate(sorted(touched),1):
                        root=Path(raw)
                        self.events.put(("diagnostic_progress",{"generation":generation,"done":i,"total":len(touched),"mod":core.detect_mod_name(root),"phase":"バックアップ"}))
                        backup=self._backup_localization_for_repair(root,stamp)
                        logs.append(i18n.t('u7.backed_up_the_entire_localization_folder', value=core.detect_mod_name(root), backup=backup))

                    # Base unnecessary-key + identical-duplicate plan.
                    plan={}
                    for analysis in before:
                        for file_path,keys in (analysis.get("remove_by_file") or {}).items():
                            plan.setdefault(file_path,set()).update(keys)

                    # Consolidate valid translations to one side for every trusted relation.
                    # Only missing/different winner definitions are written, avoiding a second duplicate on the winner side.
                    move_values_by_target={}
                    for pair in integrations:
                        target=pair.get("target")
                        target_root=pair["source_root"] if target=="source" else pair["translation_root"]
                        loser_root=pair["translation_root"] if target=="source" else pair["source_root"]
                        valid_keys=set(pair["source_vals"])|set(pair["translation_vals"])
                        values={}
                        for key in valid_keys:
                            cid=self._diagnostic_conflict_id(pair["source_root"],pair["translation_root"],key, target_lang=target_lang)
                            choice=self.diagnostic_conflict_choices.get(cid)
                            src_occ=pair["source_vals"].get(key) or []
                            tr_occ=pair["translation_vals"].get(key) or []
                            target_occ=src_occ if target=="source" else tr_occ
                            loser_occ=tr_occ if target=="source" else src_occ
                            if choice=="source" and src_occ: chosen=src_occ[0].get("value")
                            elif choice=="translation" and tr_occ: chosen=tr_occ[0].get("value")
                            elif choice=="auto" and target_occ: chosen=target_occ[0].get("value")
                            elif target_occ: chosen=target_occ[0].get("value")
                            elif loser_occ: chosen=loser_occ[0].get("value")
                            else: continue
                            # Always remove the losing-side definitions.
                            for occ in loser_occ:
                                plan.setdefault(occ.get("file"),set()).add(key)
                            target_values={o.get("value") for o in target_occ}
                            # Missing winner key, or the chosen translation differs from the winner: rewrite once in the consolidated file.
                            if not target_occ or target_values!={chosen}:
                                for occ in target_occ:
                                    plan.setdefault(occ.get("file"),set()).add(key)
                                values[key]=chosen
                        if values:
                            move_values_by_target.setdefault(target_root,{}).update(values)
                    # Delete old definitions first, then write the selected/missing values once on the winner side.
                    changed=self._apply_localization_removal_plan(plan)
                    moved=0
                    for target_root,values in move_values_by_target.items():
                        loc_root=core.localization_dir_path(Path(target_root))
                        out=Path(loc_root)/target_lang/f"zzz_paradox_localization_translator_consolidated_l_{target_lang}.yml"
                        moved += core.upsert_localization_values(out,values,target_lang)
                    if moved: logs.append(i18n.t('u7.source_japanese_translation_mod_integration_integrated' if target_lang == 'japanese' else 'u7.source_japanese_translation_mod_integration_integrated.target', target_name=i18n.t('lang.' + target_lang), moved=moved))
                    logs.append(i18n.t('u7.integration_repair_removed_japanese_keys_updated' if target_lang == 'japanese' else 'u7.integration_repair_removed_japanese_keys_updated.target', target_name=i18n.t('lang.' + target_lang), removed_keys=changed['removed_keys'], changed_files=changed['changed_files'], deleted_files=changed['deleted_files']))

                after=[]
                if repair:
                    # Rebuild occurrence/source state after modifications before re-check.
                    occurrences_after=self._diagnostic_japanese_occurrence_index(all_roots, target_lang=target_lang)
                    for i,root in enumerate(roots,1):
                        self.events.put(("diagnostic_progress",{"generation":generation,"done":i,"total":len(roots),"mod":core.detect_mod_name(root),"phase":i18n.t('u7.re_diagnose')}))
                        try: relation_key=str(Path(root).resolve())
                        except Exception: relation_key=str(root)
                        after.append(self._analyze_localization_health(root,source_index,source_meta,relation_map.get(relation_key),allowed_context,occurrences_after, target_lang=target_lang))
                self.events.put(("diagnostic_done",{"generation":generation,"repair":repair,"before":before,"after":after,"logs":logs,"integration_summary":integration_summary}))
            except Exception as exc:
                self.events.put(("diagnostic_error",{"generation":generation,"error":str(exc)}))
        self.diagnostic_thread=threading.Thread(target=work,daemon=True); self.diagnostic_thread.start()
        self._refresh_operation_states()

    def _refresh_diagnostic_action_state(self, analyses=None, integration_summary=None):
        analyses=list(self.diagnostic_last_analyses if analyses is None else (analyses or []))
        conflicts=[]; integrations=0; extras=0
        for a in analyses:
            extras += int((a.get("stats") or {}).get("extra_keys",0) or 0)
            for issue in a.get("issues") or []:
                if issue.get("conflict_id"): conflicts.append(issue.get("conflict_id"))
                if issue.get("kind")=="本体/日本語化Mod統合": integrations += int(issue.get("count",0) or 0)
        unique_conflicts=len(set(conflicts))
        unresolved=sum(1 for cid in set(conflicts) if not self.diagnostic_conflict_choices.get(cid))
        if integration_summary:
            integrations=int(integration_summary.get("total",integrations) or 0)
            unresolved=int(integration_summary.get("unresolved",unresolved) or 0)
        if hasattr(self,"diagnostic_integration_status_var"):
            self.diagnostic_integration_status_var.set(i18n.t('u7.integration_targets_keys_translation_conflicts_unspecified', integrations=integrations, unique_conflicts=unique_conflicts, unresolved=unresolved))
        repairable=bool(extras or integrations)
        if hasattr(self,"diagnostic_conflict_help_var"):
            if analyses and unique_conflicts == 0 and repairable:
                self.diagnostic_conflict_help_var.set(i18n.t('u7.no_translation_conflicts_no_settings_are'))
            elif unique_conflicts > 0:
                self.diagnostic_conflict_help_var.set(i18n.t('u7.there_are_translation_conflicts_choose_translations', unique_conflicts=unique_conflicts))
            elif analyses:
                self.diagnostic_conflict_help_var.set(i18n.t('u7.no_translation_conflicts_the_current_diagnostic' if _current_target_lang(self) == 'japanese' else 'u7.no_translation_conflicts_the_current_diagnostic.target', target_name=i18n.t('lang.' + _current_target_lang(self))))
            else:
                self.diagnostic_conflict_help_var.set(i18n.t('u7.actions_needed_for_repair_will_appear'))
        conflict_state="normal" if unique_conflicts else "disabled"
        for name in ("diagnostic_keep_source_btn","diagnostic_keep_translation_btn","diagnostic_auto_choice_btn","diagnostic_clear_choice_btn","diagnostic_all_source_btn","diagnostic_all_translation_btn","diagnostic_all_auto_btn"):
            w=getattr(self,name,None)
            if w is not None and not getattr(self,"diagnostic_running_repair",False):
                try: w.config(state=conflict_state)
                except Exception: pass
        w=getattr(self,"diagnostic_repair_btn",None)
        if w is not None and not getattr(self,"diagnostic_running_repair",False):
            try: w.config(state="normal" if repairable else "disabled")
            except Exception: pass

    def _populate_diagnostic_results(self, analyses):
        if not hasattr(self,"diagnostic_tree"): return
        self.diagnostic_last_analyses=list(analyses or [])
        for iid in self.diagnostic_tree.get_children(): self.diagnostic_tree.delete(iid)
        self.diagnostic_result_map={}; n=0
        for analysis in analyses:
            for issue in analysis.get("issues") or []:
                iid=f"diag_{n}"; n+=1
                row=dict(issue); row["mod"]=analysis.get("mod",""); row["path"]=analysis.get("path",""); row["stats"]=analysis.get("stats",{}); row["target_lang"]=analysis.get("target_lang") or "japanese"
                self.diagnostic_result_map[iid]=row
                file_name=Path(issue.get("file","")).name if issue.get("file") else ""
                decision=issue.get("decision","")
                self.diagnostic_tree.insert("","end",iid=iid,values=(issue.get("severity",""),analysis.get("mod",""),ui_status.diagnostic_kind_label(issue.get("kind",""), row["target_lang"]),issue.get("score",""),issue.get("location",""),issue.get("plan",""),decision,file_name,issue.get("count",0),issue.get("detail","")))
        self._refresh_diagnostic_action_state(analyses)
        return n

    def _on_diagnostic_result_selected(self, _event=None):
        sel=self.diagnostic_tree.selection() if hasattr(self,"diagnostic_tree") else []
        if not sel: return
        row=self.diagnostic_result_map.get(sel[0],{})
        target_lang = row.get("target_lang") or "japanese"
        stats=row.get("stats") or {}
        lines=[f"Mod: {row.get('mod','')}",i18n.t('u7.mod_location', path=row.get('path','')),i18n.t('u7.severity', severity=row.get('severity','')),i18n.t('u7.diagnostic_item', kind=ui_status.diagnostic_kind_label(row.get('kind',''), row.get('target_lang') or target_lang))]
        if row.get("score") not in (None, ""): lines.append(i18n.t('u7.relevance_score', score=row.get('score')))
        if row.get("location"): lines.append(i18n.t('u7.current_location_2', location=row.get('location')))
        if row.get("plan"): lines.append(i18n.t('u7.repair_plan_2', plan=row.get('plan')))
        if row.get("decision"): lines.append(i18n.t('u7.translation_choice_2', decision=row.get('decision')))
        if row.get("manual_priority"):
            lines.append(i18n.t('u7.override_manually_configured_in_mod_classification'))
        if row.get("file"): lines.append(i18n.t('u7.file_2', file=row.get('file')))
        lines += [i18n.t('u7.count', count=row.get('count',0)),i18n.t('u7.details', detail=row.get('detail','')),"",i18n.t('u7.english_yaml_chinese_yaml_japanese_yaml' if target_lang == 'japanese' else 'u7.english_yaml_chinese_yaml_japanese_yaml.target', target_name=i18n.t('lang.' + target_lang), english_files=stats.get('english_files',0), chinese_files=stats.get('chinese_files',0), japanese_files=stats.get('japanese_files',0)),i18n.t('u7.own_source_keys_keys_allowed_for' if target_lang == 'japanese' else 'u7.own_source_keys_keys_allowed_for.target', target_name=i18n.t('lang.' + target_lang), source_keys=stats.get('source_keys',0), allowed_keys=stats.get('allowed_keys',0), japanese_keys=stats.get('japanese_keys',0)),i18n.t('u7.linked_source_mods_unnecessary_keys_source' if target_lang == 'japanese' else 'u7.linked_source_mods_unnecessary_keys_source.target', target_name=i18n.t('lang.' + target_lang), translation_sources=stats.get('translation_sources',0), extra_keys=stats.get('extra_keys',0), conflicts=stats.get('conflicts',0))]
        self._set_diagnostic_detail("\n".join(lines))

    def _mod_status_matches_query(self, result, query):
        q = (query or "").strip().casefold()
        if not q:
            return True
        fields = [
            result.get("mod", ""),
            result.get("status", ""), display_status(result.get("status", "")),
            result.get("external_translation_mod", ""),
            result.get("translation_candidate_mod", ""),
            result.get("message", ""),
            " ".join(result.get("translation_warnings") or []),
            result.get("path", ""),
        ]
        return any(q in str(v).casefold() for v in fields)

    def _mod_status_result_game(self, result):
        game = str((result or {}).get("game") or (result or {}).get("game_name") or "").strip()
        if game:
            return game
        raw = (result or {}).get("path") or (result or {}).get("mod_root") or ""
        if not raw:
            return "ゲーム未特定"
        return self._backup_game_name_for_root(Path(raw))

    def _selected_mod_status_games(self):
        games=[]
        if not hasattr(self, "discovered_mod_tree"):
            return games
        for iid in self.discovered_mod_tree.selection():
            try:
                idx=int(str(iid).split("_",1)[1])
                game=str(self.detected_mod_locations[idx].get("game") or "").strip()
                if game and game not in games:
                    games.append(game)
            except Exception:
                continue
        return games

    def _game_filtered_mod_status_results(self, results=None):
        source=list(self.mod_research_results if results is None else results)
        games=App._selected_mod_status_games(self)
        if not games:
            return source, games
        wanted=set(games)
        return [r for r in source if App._mod_status_result_game(self,r) in wanted], games

    def _set_mod_status_selection_actions_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for widget in getattr(self, "status_selection_action_buttons", []):
            try: widget.config(state=state)
            except Exception: pass
        # Chinese-basis queueing has an additional source-availability condition
        # and is enabled separately after a valid selection is inspected.
        if hasattr(self, "status_chinese_queue_btn") and not enabled:
            self.status_chinese_queue_btn.config(state="disabled")

    def _populate_mod_status_tree(self, results=None):
        if not hasattr(self, "mod_status_tree"):
            return
        if hasattr(self, "diagnostic_target_tree"):
            try: self._refresh_diagnostic_targets()
            except Exception: pass
        query = self.mod_status_search_var.get().strip() if hasattr(self, "mod_status_search_var") else ""
        source, selected_games = App._game_filtered_mod_status_results(self,results)
        visible = [r for r in source if self._mod_status_matches_query(r, query)]
        for x in self.mod_status_tree.get_children():
            self.mod_status_tree.delete(x)
        # iidは元リストのindexを使う。検索で絞っても選択→元データ参照がずれない。
        index_by_id = {id(r): i for i, r in enumerate(self.mod_research_results)}
        for r in visible:
            i = index_by_id.get(id(r))
            if i is None:
                try:
                    i = self.mod_research_results.index(r)
                except ValueError:
                    continue
            self.mod_status_tree.insert("", "end", iid=f"mod_{i}", values=(
                display_status(r.get("status", "")), r.get("mod", ""), r.get("gap_count", 0),
                i18n.t('u6.yes') if r.get("simp_chinese_files", 0) else i18n.t('u6.no'),
                r.get("external_translation_mod", "") or ((i18n.t('u6.candidate_3', translation_candidate_mod=r.get('translation_candidate_mod', ''))) if r.get("translation_candidate_mod") else ""),
                r.get("external_translation_gap_count", 0) if r.get("external_translation_mod") else ((i18n.t('u6.points', value=format(float(r.get('translation_candidate_score', 0.0) or 0.0), '.1f'))) if r.get("translation_candidate_mod") else "")
            ))
        if not visible:
            empty_values=_mod_status_empty_row(query, len(source))
            if not query and selected_games and self.mod_research_results:
                empty_values=(i18n.t('u6.nothing_to_display'),i18n.t('u6.no_research_results_for_selected_games', value='、'.join(selected_games)),"","","","")
            self.mod_status_tree.insert("", "end", iid=MOD_STATUS_EMPTY_IID,
                                        values=empty_values, tags=("empty",))
        self._set_mod_status_selection_actions_enabled(False)
        total_all=len(self.mod_research_results)
        game_label="、".join(selected_games) if selected_games else i18n.t('u6.all')
        if hasattr(self,"mod_status_game_filter_var"):
            self.mod_status_game_filter_var.set(i18n.t('u6.displayed_games_entries_total', game_label=game_label, source_count=len(source), total_all=total_all))
        if query:
            scope_label=i18n.t('u6.displayed') if selected_games else i18n.t('u6.all_2')
            self.mod_status_search_result_var.set(i18n.t('u6.entries_entries', visible_count=len(visible), scope_label=scope_label, source_count=len(source)))
        else:
            self.mod_status_search_result_var.set("")
        if not visible:
            if query:
                self._set_mod_status_detail_text(i18n.t('u6.no_search_results_no_assessed_mods', query=query, source_count=len(source)))
            else:
                if selected_games and self.mod_research_results:
                    self._set_mod_status_detail_text(i18n.t('u6.no_research_results_for_selected_games_2', game_label=game_label))
                else:
                    self._set_mod_status_detail_text(i18n.t('u6.no_research_results_select_a_game'))

    def _schedule_mod_status_search(self, _event=None):
        if self._status_search_after_id is not None:
            try: self.after_cancel(self._status_search_after_id)
            except Exception: pass
        self._status_search_after_id=self.after(180, lambda:self._run_debounced_mod_status_search())

    def _run_debounced_mod_status_search(self):
        self._status_search_after_id=None
        self.search_mod_status(live=True)

    def search_mod_status(self, live=False):
        query = self.mod_status_search_var.get().strip()
        self._populate_mod_status_tree()
        if not query:
            return
        source,_games=App._game_filtered_mod_status_results(self)
        matches = [r for r in source if self._mod_status_matches_query(r, query)]
        if len(matches) == 1:
            r = matches[0]
            # 1件なら自動選択し、判定結果を下段に表示する。
            try:
                idx = self.mod_research_results.index(r)
                iid = f"mod_{idx}"
                if self.mod_status_tree.exists(iid):
                    self.mod_status_tree.selection_set(iid)
                    self.mod_status_tree.focus(iid)
                    self.mod_status_tree.see(iid)
                    self._on_mod_status_selection_changed()
            except Exception:
                pass
        elif not matches and not live:
            self.mod_status_search_result_var.set(i18n.t('u6.was_not_found', query=query))

    def clear_mod_status_search(self):
        self.mod_status_search_var.set("")
        self.mod_status_search_result_var.set("")
        self._populate_mod_status_tree()
        self._set_mod_status_detail_text(i18n.t('u6.select_a_mod_to_see_research', target_name=i18n.t("lang." + _current_target_lang(self))))

    def _set_mod_status_detail_text(self, text):
        if not hasattr(self, "mod_status_detail"):
            return
        self.mod_status_detail.configure(state="normal")
        self.mod_status_detail.delete("1.0", "end")
        self.mod_status_detail.insert("1.0", text)
        self.mod_status_detail.configure(state="disabled")

    def _on_mod_status_selection_changed(self, _event=None):
        selected = self._selected_mod_status_results() if hasattr(self, "mod_status_tree") else []
        target_lang = (selected[0].get("target_lang") or core.DEFAULT_TARGET_LANG) if selected else _current_target_lang(self)
        if not selected:
            query=self.mod_status_search_var.get().strip() if hasattr(self,"mod_status_search_var") else ""
            children=self.mod_status_tree.get_children() if hasattr(self,"mod_status_tree") else []
            if MOD_STATUS_EMPTY_IID in children and query:
                self._set_mod_status_detail_text(i18n.t('u6.no_search_results_no_assessed_mods_2', query=query, mod_research_results_count=len(self.mod_research_results)))
            elif MOD_STATUS_EMPTY_IID in children:
                games=App._selected_mod_status_games(self)
                if games and self.mod_research_results:
                    self._set_mod_status_detail_text(i18n.t('u6.no_research_results_for_selected_games_3', value='、'.join(games)))
                else:
                    self._set_mod_status_detail_text(i18n.t('u6.no_research_results_select_a_game'))
            else:
                self._set_mod_status_detail_text(i18n.t('u6.select_a_mod_to_see_research', target_name=i18n.t("lang." + target_lang)))
            self._set_mod_status_selection_actions_enabled(False)
            if hasattr(self, "status_overwrite_btn"):
                self.status_overwrite_btn.config(text=i18n.t('u6.overwrite_mod_with_completed_translation', target_name=i18n.t("lang." + target_lang)))
            if hasattr(self, "status_chinese_queue_btn"):
                self.status_chinese_queue_btn.config(state="disabled")
            return
        r = selected[0]
        self._set_mod_status_selection_actions_enabled(True)
        mod_name = r.get("mod", "Mod")
        jpmod = r.get("external_translation_mod", "")
        jp_path = r.get("external_translation_path", "")
        zh_count = r.get("simp_chinese_files", 0)
        lines = [f"Mod: {mod_name}", i18n.t('u6.status_gaps', status=display_status(r), gap_count=r.get('gap_count', 0)), i18n.t('u6.english_keys_simplified_chinese_keys_japanese', target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG)), english_keys=r.get('english_keys', 0), simp_chinese_keys=r.get('simp_chinese_keys', 0), japanese_keys=r.get('japanese_keys', 0)), i18n.t('u6.language_specific_keys_english_only_chinese', english_only_keys=r.get('english_only_keys', 0), chinese_only_keys=r.get('chinese_only_keys', 0)), i18n.t('u6.simplified_chinese', value=i18n.t('u6.yes_files', value=str(zh_count)) if zh_count else i18n.t('u6.no')), "", ui_status.display_message(r)]
        warnings=list(r.get("translation_warnings") or [])
        if warnings:
            profile=dict(r.get("translation_format_profile") or {})
            lines += ["", i18n.t('u6.warnings')] + [i18n.t('u6.detail_3', warning=warning) for warning in warnings]
            lines.append(
                i18n.t('u6.assessment_evidence_japanese_text_in_l', value=int(profile.get('english_japanese_text_keys', 0) or 0), value_2=int(profile.get('english_key_count', 0) or 0), value_3=format(float(profile.get('english_japanese_text_rate', 0) or 0) * 100, '.1f'))
            )
        if hasattr(self, "status_chinese_queue_btn"):
            # 複数選択時は、中国語localizationを持つModが1件でもあれば利用可。
            has_zh = any(x.get("simp_chinese_files", 0) for x in selected)
            self.status_chinese_queue_btn.config(state="normal" if has_zh else "disabled")
        if jpmod:
            score=float(r.get("external_translation_score",0.0) or 0.0)
            precision=float(r.get("external_translation_coverage",0.0) or 0.0)
            lines += ["", i18n.t('u6.translation_mod_2', jpmod=jpmod, target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG))), i18n.t('u6.relationship_score_100_source_mod_exact', score=format(score, '.1f'), value=format(precision * 100, '.1f')), i18n.t('u6.translation_mod_gaps_2', external_translation_gap_count=r.get('external_translation_gap_count', 0), target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG))), i18n.t('u6.overwrite_destination_translation_mod', jpmod=jpmod, target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG))), i18n.t('u6.translation_mod_location', jp_path=jp_path, target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG)))]
            reasons=list(r.get("external_translation_reasons") or [])
            if reasons:
                lines += [i18n.t('u6.assessment_reasons')] + [i18n.t('u6.detail_4', value=x) for x in reasons]
            if hasattr(self, "status_overwrite_btn"):
                label = i18n.t('u6.overwrite_differences_to_translation_mod', jpmod=jpmod, target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG)))
                if len(label) > 34:
                    label = i18n.t('u6.overwrite_differences_to_translation_mod_2', target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG)))
                self.status_overwrite_btn.config(text=label)
        else:
            cand=r.get("translation_candidate_mod", "")
            if cand:
                cscore=float(r.get("translation_candidate_score",0.0) or 0.0)
                cprec=float(r.get("translation_candidate_coverage",0.0) or 0.0)
                lines += ["", i18n.t('u6.translation_mod_candidate_not_linked_automatically', cand=cand, target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG))), i18n.t('u6.relationship_score_100_source_mod_exact_2', cscore=format(cscore, '.1f'), value=format(cprec * 100, '.1f')), i18n.t('u6.candidate_location', translation_candidate_path=r.get('translation_candidate_path', ''))]
                creasons=list(r.get("translation_candidate_reasons") or [])
                if creasons: lines += [i18n.t('u6.assessment_reasons')] + [i18n.t('u6.detail_4', value=x) for x in creasons]
            lines += ["", i18n.t('u6.overwrite_destination_japanese_localization_in_source', target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG)))]
            if hasattr(self, "status_overwrite_btn"):
                self.status_overwrite_btn.config(text=i18n.t('u6.overwrite_source_mod_with_completed_translation', target_name=i18n.t("lang." + (r.get("target_lang") or core.DEFAULT_TARGET_LANG))))
        lines += ["", i18n.t('u6.source_mod_location', path=r.get('path', ''))]
        self._set_mod_status_detail_text("\n".join(lines))

    def pick_monitor_path(self):
        p=filedialog.askdirectory(title=i18n.t('u6.select_a_mod_localization_folder_or'))
        if p: self.monitor_path_var.set(p)

    def discover_mod_locations(self):
        """Find Steam Workshop / Paradox user-mod folders without blocking the GUI.

        Previously discovered Steam library roots are reused, and the core also performs
        a shallow scan of other mounted drives/volumes so installations on another SSD
        or external drive can be found without a whole-disk recursive search.
        """
        if not hasattr(self, "discovered_mod_tree"):
            return
        self.mod_discovery_status_var.set(i18n.t('p0.detecting_checking_other_drives_and'))
        def work():
            try:
                saved=core.load_json(SAVED_STEAM_ROOTS_PATH, [])
                extra=[]
                for raw in saved if isinstance(saved,list) else []:
                    try:
                        p=Path(raw)
                        if p.exists(): extra.append(p)
                    except Exception:
                        pass
                rows=core.discover_paradox_mod_locations(extra_steam_roots=extra)
                self.events.put(("mod_locations_discovered",rows))
            except Exception as e:
                self.events.put(("mod_locations_error",str(e)))
        threading.Thread(target=work,daemon=True).start()

    def _on_discovery_tree_click(self, event):
        if not getattr(self,"discovery_multi_select_var",None) or not self.discovery_multi_select_var.get():
            return None
        iid=self.discovered_mod_tree.identify_row(event.y)
        if not iid:
            return "break"
        if iid in self.discovered_mod_tree.selection():
            self.discovered_mod_tree.selection_remove(iid)
        else:
            self.discovered_mod_tree.selection_add(iid)
        self.discovered_mod_tree.focus(iid)
        self.discovered_mod_tree.see(iid)
        self.after_idle(self._sync_monitor_targets_from_discovery_selection)
        return "break"

    def select_all_discovered_locations(self):
        if not hasattr(self,"discovered_mod_tree"):
            return
        items=self.discovered_mod_tree.get_children()
        if items:
            self.discovered_mod_tree.selection_set(items)
            self._sync_monitor_targets_from_discovery_selection()
            self.mod_discovery_status_var.set(i18n.t('u6.locations_selected_applied_to_monitor_targets', items_count=len(items)))

    def _sync_monitor_targets_from_discovery_selection(self):
        """翻訳状況の場所一覧で現在選択中の行を、そのまま未翻訳監視対象へ同期する。"""
        if not hasattr(self, "discovered_mod_tree"):
            return []
        rows=[]
        for iid in self.discovered_mod_tree.selection():
            try:
                idx=int(iid.split("_",1)[1])
                if 0 <= idx < len(self.detected_mod_locations):
                    rows.append(self.detected_mod_locations[idx])
            except Exception:
                continue
        self._set_monitor_targets(rows)
        self._populate_mod_status_tree()
        if rows:
            self.mod_discovery_status_var.set(i18n.t('u6.locations_selected_applied_to_monitor_targets_2', rows_count=len(rows)))
        return rows

    def _selected_discovered_locations(self):
        if not hasattr(self, "discovered_mod_tree"):
            return []
        sel = self.discovered_mod_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, i18n.t('u6.select_detected_game_mod_locations_hold'))
            return []
        rows = []
        for iid in sel:
            try:
                idx = int(iid.split("_", 1)[1])
                rows.append(self.detected_mod_locations[idx])
            except Exception:
                continue
        return rows

    def _selected_discovered_location(self):
        rows = self._selected_discovered_locations()
        return rows[0] if rows else None

    def _set_monitor_targets(self, rows):
        paths=[]
        labels=[]
        for row in rows or []:
            raw=str(row.get("path", "")).strip()
            if not raw:
                continue
            p=Path(raw)
            if not p.exists():
                continue
            resolved=str(p.resolve())
            if resolved not in paths:
                paths.append(resolved)
                labels.append(f"{row.get('game','')} / {row.get('kind','')}")
        self.monitor_target_paths=paths
        self.monitor_path_var.set(paths[0] if paths else "")
        if paths:
            label = "、".join(labels[:3])
            if len(labels)>3:
                label += i18n.t('u6.and_more_locations', value=len(labels) - 3)
            self.monitor_target_summary_var.set(i18n.t('u6.monitor_targets_locations', paths_count=len(paths), label=label))
        else:
            self.monitor_target_summary_var.set(i18n.t('u6.monitor_targets_select_game_mod_locations'))

    def use_selected_discovered_location(self):
        # 旧UI/内部呼び出しとの互換。選択場所を監視対象として登録する。
        rows = self._selected_discovered_locations()
        if not rows:
            return
        self._set_monitor_targets(rows)
        self.mod_discovery_status_var.set(i18n.t('u6.registered_monitor_target_locations', monitor_target_paths_count=len(self.monitor_target_paths)))

    def _collect_mod_roots_from_location_rows(self, rows):
        all_roots=[]
        missing=[]
        for row in rows or []:
            path=Path(row.get("path", ""))
            if not path.exists():
                missing.append(str(path)); continue
            try:
                roots=core.find_mod_roots(path)
            except Exception as exc:
                record_error(i18n.t('p0.mod_location_scan'), exc, str(path)); roots=[]
            for root in roots:
                rp=Path(root)
                if rp not in all_roots:
                    all_roots.append(rp)
        return all_roots, missing

    def _game_wide_translation_pool(self, rows, roots):
        """日本語化Modの照合相手を、選んだ場所と同じゲームの全保管場所（ローカル・Workshop など）に広げる。

        調べる対象は選んだ場所のまま。ゲームが分からない行は、選んだ場所だけで照合する。
        """
        pool=[]; seen=set()
        def add(root):
            rp=Path(root)
            try: key=str(rp.resolve())
            except Exception: key=str(rp)
            if key not in seen:
                seen.add(key); pool.append(rp)
        for root in roots or []:
            add(root)
        games={str(r.get("game") or "") for r in rows or [] if r.get("game")}
        if games:
            same_game=[r for r in list(getattr(self,"detected_mod_locations",[]) or []) if r.get("game") in games]
            extra,_=self._collect_mod_roots_from_location_rows(same_game)
            for root in extra:
                add(root)
        return pool

    @staticmethod
    def _results_without_roots(results, roots):
        """これから調べ直すModの古い結果だけを除き、ほかの保管場所の結果は残す。"""
        drop=set()
        for root in roots or []:
            try: drop.add(str(Path(root).resolve()))
            except Exception: drop.add(str(Path(root)))
        kept=[]
        for r in results or []:
            try: key=str(Path(r.get("path","")).resolve())
            except Exception: key=str(Path(r.get("path","")))
            if key not in drop:
                kept.append(r)
        return kept

    def research_selected_discovered_location(self):
        rows = self._selected_discovered_locations()
        if not rows:
            return
        all_roots, missing = self._collect_mod_roots_from_location_rows(rows)
        if not all_roots:
            counts = ", ".join(f"{r.get('game','')} {r.get('kind','')}: {r.get('mod_count',0)}" for r in rows)
            messagebox.showinfo(APP_NAME, i18n.t('u6.no_mods_with_localization_found_in', counts=counts))
            self.mod_discovery_status_var.set(i18n.t('u6.no_localization_found_to_research'))
            return
        pool=self._game_wide_translation_pool(rows, all_roots)
        self.mod_discovery_status_var.set(i18n.t('u6.researching_locations_mods_checking_translation_mods', rows_count=len(rows), all_roots_count=len(all_roots), pool_count=len(pool), target_name=i18n.t("lang." + 'japanese')))
        self._start_mod_research(all_roots, replace=True, translation_pool=pool)
        if missing:
            record_error(i18n.t('u6.bulk_mod_location_research'), detail=i18n.t('u6.missing_detected_locations', value=' | '.join(missing)))

    def research_monitor_targets(self):
        paths=[Path(p) for p in self.monitor_target_paths if Path(p).exists()]
        if not paths:
            messagebox.showinfo(APP_NAME, i18n.t('u6.no_monitor_targets_select_at_least'))
            return
        rows=[]
        for p in paths:
            matched=next((r for r in self.detected_mod_locations if str(Path(r.get("path", "")))==str(p)), None)
            rows.append(matched or {"path":str(p),"game":"","kind":""})
        roots,_=self._collect_mod_roots_from_location_rows(rows)
        if not roots:
            messagebox.showinfo(APP_NAME, i18n.t('u6.no_mods_with_localization_found_in_2'))
            return
        self._start_mod_research(roots, replace=True, translation_pool=self._game_wide_translation_pool(rows, roots))
        self.monitor_status_var.set(i18n.t('u6.researching_again_mods', roots_count=len(roots)))

    def on_monitor_provider_change(self):
        provider=self.monitor_provider_var.get()
        # 監視用LLMも、前のプロバイダのキーを別の相手へ送らない（起動中だけ覚える）。
        if not hasattr(self, "_monitor_api_keys_by_provider"): self._monitor_api_keys_by_provider={}
        old=getattr(self, "_monitor_api_key_provider", None)
        if old != provider:
            if old is not None: self._monitor_api_keys_by_provider[old]=self.monitor_api_key_var.get().strip()
            self.monitor_api_key_var.set(self._monitor_api_keys_by_provider.get(provider, ""))
            self._monitor_api_key_provider=provider
        self.monitor_url_var.set(core.default_url_for_provider(provider))
        self.monitor_model_var.set("")
        self.monitor_connection_var.set(i18n.t('u6.monitor_llm_not_checked'))
        self._save_llm_preferences()
        self.refresh_monitor_models()

    def refresh_monitor_models(self):
        provider=self.monitor_provider_var.get()
        url=self.monitor_url_var.get().strip() or core.default_url_for_provider(provider)
        api_key=self.monitor_api_key_var.get().strip()
        self.monitor_connection_var.set(i18n.t('u6.checking_connection', provider=provider))
        def work():
            try:
                models=core.list_models(provider,url,api_key=api_key)
                self.events.put(("monitor_models",models))
            except Exception as e:
                self.events.put(("monitor_model_error",str(e)))
        threading.Thread(target=work,daemon=True).start()

    def _monitor_llm_config(self):
        return (
            self.monitor_provider_var.get(),
            self.monitor_url_var.get().strip() or core.default_url_for_provider(self.monitor_provider_var.get()),
            self.monitor_model_var.get().strip(),
            self.monitor_api_key_var.get().strip(),
        )

    def _save_llm_preferences(self):
        """Persist last-used translation/monitor settings. API keys are intentionally excluded."""
        try:
            data = dict(self.app_preferences) if isinstance(self.app_preferences, dict) else {}
            data.update({
                "version": 2,
                "translation_llm": {
                    "provider": self.provider_var.get(),
                    "url": self.url_var.get().strip(),
                    "model": self.model_var.get().strip(),
                    # バッチ/並列も前回値を復元する。中国語基準翻訳も同じ翻訳設定を共有する。
                    "batch": max(1, self.batch_var.get()),
                    "workers": max(1, self.workers_var.get()),
                    "chinese_autoqa": bool(self.chinese_autoqa_var.get()),
                    "normalize_spacing": _normalize_spacing_enabled(self),
                },
                "monitor_llm": {
                    "provider": self.monitor_provider_var.get(),
                    "url": self.monitor_url_var.get().strip(),
                    "model": self.monitor_model_var.get().strip(),
                },
                "window_close": {
                    "action": ui_status.close_action_from_label(self.close_action_var.get()),
                },
                "target_lang": self.target_lang_var.get() if hasattr(self, "target_lang_var") else core.DEFAULT_TARGET_LANG,
                "ui_language": (self.app_preferences or {}).get("ui_language") or getattr(self, "ui_language", i18n.LEGACY_UI_LANGUAGE),
            })
            core.save_json(APP_PREFS_PATH, data)
            self.app_preferences = data
            if threading.current_thread() is threading.main_thread() and hasattr(self,"notebook"):
                self._save_workspace_state("settings_changed")
        except Exception as e:
            record_error(i18n.t('u5.save_llm_settings'), e)

    def apply_monitor_settings(self, silent=False):
        """Apply monitor/research LLM settings. Current in-flight request is not interrupted."""
        provider=self.monitor_provider_var.get()
        url=self.monitor_url_var.get().strip() or core.default_url_for_provider(provider)
        model=self.monitor_model_var.get().strip()
        self.monitor_url_var.set(url)
        if not model:
            if not silent:
                messagebox.showinfo(APP_NAME,i18n.t('u6.select_a_research_llm_model'))
            return False
        self._save_llm_preferences()
        self.monitor_connection_var.set(i18n.t('u6.monitor_llm_settings', provider=provider, model=model))
        self.monitor_llm_detail_var.set(i18n.t('u6.applies_from_the_next_research_llm', provider=provider, model=model))
        if not silent:
            messagebox.showinfo(APP_NAME,i18n.t('u6.research_llm_settings_applied_the_current'))
        return True

    def apply_translation_settings_everywhere(self, silent=False):
        """Persist UI translation settings and apply to active queue; QA/diff always read these UI values."""
        self._save_llm_preferences()
        if self.controller and self.worker and self.worker.is_alive():
            # Reuse the active-job runtime switching logic without a duplicate dialog.
            try:
                glossary_path=self.glossary_path_var.get().strip()
                self.controller.update_runtime_settings(
                    provider=self.provider_var.get(), url=self.url_var.get().strip(), model=self.model_var.get().strip(),
                    api_key=self.api_key_var.get().strip(), preset=self.preset_var.get(),
                    batch_size=max(1,self.batch_var.get()), workers=max(1,self.workers_var.get()),
                    glossary_path=glossary_path, dual_source=self.dual_var.get())
                self.translation_start_settings={**getattr(self,"translation_start_settings",{}),
                    "provider":self.provider_var.get(),"url":self.url_var.get().strip(),"model":self.model_var.get().strip(),
                    "api_key":self.api_key_var.get().strip(),"preset":self.preset_var.get(),
                    "batch":max(1,self.batch_var.get()),"workers":max(1,self.workers_var.get()),
                    "glossary":glossary_path or None,"dual":self.dual_var.get()}
                self.save_session(active=True)
            except Exception as e:
                record_error(i18n.t('u5.apply_translation_settings'), e)
                if not silent: messagebox.showerror(APP_NAME,i18n.t('u5.settings_failed', e=e))
                return False
        if not silent:
            messagebox.showinfo(APP_NAME,
                i18n.t('u5.settings_applied_running') if self.controller and self.worker and self.worker.is_alive() else i18n.t('u5.settings_applied'))
        return True

    def _snapshot_monitor_worker_settings(self):
        """Capture Tk-backed monitor settings on the main thread before workers start."""
        return {
            "target_lang": _current_target_lang(self),
            "interval": max(3, int(self.monitor_interval_var.get() or 15)),
            "use_llm": bool(self.monitor_use_llm_var.get()),
            "check_translation_mods": bool(self.monitor_check_translation_mods_var.get()),
            "provider": self.monitor_provider_var.get(),
            "url": self.monitor_url_var.get().strip(),
            "model": self.monitor_model_var.get().strip(),
            "api_key": self.monitor_api_key_var.get().strip(),
        }

    def _current_monitor_roots(self):
        roots=[]
        for raw in self.monitor_target_paths:
            p=Path(raw)
            if p.exists():
                roots.append(p)
        return roots

    def toggle_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.stop_monitor()
        else:
            self.start_monitor()

    def start_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        roots=self._current_monitor_roots()
        if not roots:
            # 監視対象キャッシュが空でも、翻訳状況で現在選択されている場所をその場で再取得する。
            self._sync_monitor_targets_from_discovery_selection()
            roots=self._current_monitor_roots()
        if not roots:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_monitor_targets_select_at_least'))
            return
        self.monitor_stop_event.clear(); self.monitor_force_event.set(); self.monitor_snapshot={}
        self._monitor_worker_settings = self._snapshot_monitor_worker_settings()
        self.monitor_toggle_btn.config(text=i18n.t('u6.stop_continuous_monitoring'))
        self.monitor_status_var.set(i18n.t('u6.monitoring_locations_initial_check', roots_count=len(roots)))
        self._set_monitor_scan_status(i18n.t('u6.monitoring_untranslated_mods'), i18n.t('u6.checking_changed_yaml_files_in_locations', roots_count=len(roots)))
        self.monitor_thread=threading.Thread(target=self._monitor_worker,daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self):
        if not (self.monitor_thread and self.monitor_thread.is_alive()):
            self.monitor_status_var.set(i18n.t('u6.monitoring_stopped'))
            self.monitor_toggle_btn.config(text=i18n.t('u6.start_continuous_monitoring'))
            return
        self.monitor_stop_event.set(); self.monitor_force_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.monitor_status_var.set(i18n.t('u6.stopping_monitor'))
        self.monitor_toggle_btn.config(text=i18n.t('u6.stopping'), state="disabled")

    def monitor_scan_now(self):
        # 旧内部呼び出しとの互換。現在は「再調査」に統合。
        self.research_monitor_targets()

    def _refine_candidates_with_monitor_llm(self, candidates, settings=None):
        ambiguous=[(i,c) for i,c in enumerate(candidates) if c.get("needs_llm")]
        settings = dict(settings or {})
        if not (bool(settings.get("use_llm", False)) and ambiguous):
            return candidates
        provider = settings.get("provider", "")
        url = settings.get("url", "")
        model = settings.get("model", "")
        api_key = settings.get("api_key", "")
        if not model:
            self.events.put(("monitor_log",i18n.t('u6.no_monitor_llm_selected_skipping_review')))
            return candidates
        self.monitor_llm_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("monitor_progress",p)))
        try:
            decisions=core.classify_monitor_candidates(
                provider,url,model,[c for _,c in ambiguous],self.monitor_llm_controller,
                api_key,batch_size=40)
            keep=set()
            for pos,(original_idx,c) in enumerate(ambiguous):
                if decisions.get(pos,True):
                    c["confidence"]=i18n.t('u6.llm_review'); keep.add(original_idx)
            return [c for i,c in enumerate(candidates) if not c.get("needs_llm") or i in keep]
        finally:
            self.monitor_llm_controller=None

    def _monitor_worker(self, one_shot=False):
        roots=self._current_monitor_roots()
        settings = dict(getattr(self, "_monitor_worker_settings", {}) or {})
        try:
            first=True
            while not self.monitor_stop_event.is_set():
                forced=self.monitor_force_event.is_set(); self.monitor_force_event.clear()
                combined_stats={}
                for root in roots:
                    stats=core.localization_file_stats(root)
                    prefix=str(root)
                    for rel,val in stats.items():
                        combined_stats[f"{prefix}::{rel}"]=val
                changed = first or forced or combined_stats != self.monitor_snapshot
                if changed:
                    self.events.put(("monitor_status",i18n.t('u6.monitoring_analyzing_locations', roots_count=len(roots))))
                    candidates=[]
                    for root in roots:
                        try:
                            candidates.extend(core.scan_translation_gaps(root, target_lang=settings.get("target_lang", core.DEFAULT_TARGET_LANG)))
                        except Exception as exc:
                            self.events.put(("monitor_log",i18n.t('u6.skipped_analysis', root=root, exc=exc)))
                    try:
                        candidates=self._refine_candidates_with_monitor_llm(candidates, settings)
                    except core.StopRequested:
                        if self.monitor_stop_event.is_set(): break
                    except Exception as e:
                        self.events.put(("monitor_log",i18n.t('u6.skipped_lightweight_llm_review', value=e)))
                    self.monitor_candidates=candidates; self.monitor_snapshot=combined_stats
                    self.events.put(("monitor_results",candidates))
                    first=False
                if one_shot:
                    break
                interval=max(3,int(settings.get("interval", 15) or 15))
                for _ in range(interval*5):
                    if self.monitor_stop_event.is_set() or self.monitor_force_event.is_set(): break
                    self.monitor_stop_event.wait(0.2)
            self.events.put(("monitor_stopped",None))
        except Exception as e:
            self.events.put(("monitor_error",str(e)))

    def _tk_callback_exception(self, exc_type, exc_value, exc_tb):
        try:
            exc_value.__traceback__ = exc_tb
        except Exception:
            pass
        record_error("Tkinter callback", exc_value)
        messagebox.showerror(APP_NAME, i18n.t('p0.an_unexpected_error_occurred_recorded', exc_value=exc_value))

    def _sys_excepthook(self, exc_type, exc_value, exc_tb):
        try:
            exc_value.__traceback__ = exc_tb
        except Exception:
            pass
        record_error("Unhandled exception", exc_value)

    def _thread_excepthook(self, args):
        try:
            args.exc_value.__traceback__ = args.exc_traceback
        except Exception:
            pass
        record_error(f"Thread exception: {getattr(args.thread, 'name', '')}", args.exc_value)

    def collect_error_logs(self):
        """Create a shareable diagnostics ZIP without API keys or localization content."""
        try:
            DIAGNOSTIC_LOG_ROOT.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = DIAGNOSTIC_LOG_ROOT / f"ParadoxLocalizationTranslator_diagnostics_{stamp}.zip"
            info = {
                "app": APP_NAME, "version": APP_VERSION,
                "ui_language": self.ui_language,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "platform": platform.platform(), "python": sys.version,
                "data_root": str(DATA_ROOT),
                "provider": self.provider_var.get(), "model": self.model_var.get(),
                "monitor_provider": self.monitor_provider_var.get(), "monitor_model": self.monitor_model_var.get(),
            }
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("diagnostics.json", json.dumps(info, ensure_ascii=False, indent=2))
                zf.writestr("rule_ids_ja.txt", i18n_rule_ids.rule_ids_ja_text())
                for lp in _diagnostic_log_files(LOG_ROOT):
                    try: rel=lp.relative_to(LOG_ROOT)
                    except Exception: rel=Path(lp.parent.name)/lp.name
                    zf.write(lp, str(Path("logs")/rel))
                if SESSION_PATH.exists():
                    try:
                        session = core.load_json(SESSION_PATH, {})
                        if isinstance(session, dict): session.pop("api_key", None)
                        zf.writestr("session_sanitized.json", json.dumps(session, ensure_ascii=False, indent=2))
                    except Exception:
                        pass
                if RESUME_STATE_PATH.exists():
                    try:
                        resume_state=core.load_json(RESUME_STATE_PATH,{})
                        zf.writestr("resume_state_sanitized.json",json.dumps(resume_state,ensure_ascii=False,indent=2))
                    except Exception:
                        pass
            messagebox.showinfo(APP_NAME, i18n.t('u7.diagnostic_logs_collected_api_keys_and', target=target))
        except Exception as e:
            record_error(i18n.t('u7.diagnostic_log_collection'), e)
            messagebox.showerror(APP_NAME, i18n.t('u7.failed_to_collect_diagnostic_logs', e=e))

    def _mod_source_signature(self, mod_root: Path, *, target_lang=None) -> str:
        """Cheap signature used to decide whether a cached status result is still current."""
        target_lang = target_lang or _current_target_lang(self)
        try:
            loc = core.mod_localization_root(Path(mod_root))
            if not loc:
                return "missing" if target_lang == "japanese" else f"{target_lang}:missing"
            h = hashlib.sha256()
            if target_lang != "japanese":
                h.update(f"target-lang:{target_lang}:".encode())
            count = 0
            for fp in sorted(Path(loc).rglob("*.yml")):
                try:
                    st = fp.stat()
                    rel = fp.relative_to(loc)
                    h.update(str(rel).encode("utf-8", "ignore"))
                    h.update(str(st.st_size).encode())
                    h.update(str(st.st_mtime_ns).encode())
                    count += 1
                except OSError:
                    continue
            h.update(str(count).encode())
            return h.hexdigest()
        except Exception as e:
            record_error("Mod status signature", e, str(mod_root))
            return "error" if target_lang == "japanese" else f"{target_lang}:error"

    def _cached_status_for_mod(self, mod_root: Path, signature: str, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        key = str(Path(mod_root).expanduser().resolve())
        with self.mod_status_cache_lock:
            if self.mod_status_cache.get("version") != MOD_STATUS_CACHE_VERSION:
                return None
            row = _relation_language_items(self.mod_status_cache, "items", target_lang).get(key)
        if row and row.get("signature") == signature and _status_matches_language(row.get("result"), target_lang):
            result = dict(row["result"])
            result["cached"] = True
            return result
        return None

    def _cache_mod_status_result(self, mod_root: Path, signature: str, result: dict, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        key = str(Path(mod_root).expanduser().resolve())
        summary = _compact_translation_status_result(result)
        summary["path"] = str(result.get("path") or mod_root)
        if target_lang != "japanese":
            summary["target_lang"] = target_lang
        row = {"signature": signature, "checked_at": datetime.now().isoformat(timespec="seconds"), "result": summary}
        with self.mod_status_cache_lock:
            _relation_language_items(self.mod_status_cache, "items", target_lang, create=True)[key] = row
            self.mod_status_cache["version"] = MOD_STATUS_CACHE_VERSION
            self.mod_status_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_STATUS_CACHE_PATH, self.mod_status_cache)
        try:
            if threading.current_thread() is threading.main_thread():
                self._save_translation_status_state("status_row_cached")
        except Exception:
            pass

    def _restore_cached_mod_status(self):
        """Restore potentially large Translation Status caches off the Tk thread."""
        if self.status_restore_thread and self.status_restore_thread.is_alive():
            return
        self.mod_status_summary_var.set(i18n.t('u7.restoring_previous_translation_status_in_the'))
        target_lang = _current_target_lang(self)
        def work():
            try:
                data = load_persistent_json(MOD_STATUS_CACHE_PATH, {"version": MOD_STATUS_CACHE_VERSION, "items": {}}, i18n.t('u7.translation_status_cache'))
                cache_is_current = isinstance(data, dict) and data.get("version") == MOD_STATUS_CACHE_VERSION
                if not cache_is_current:
                    data = {"version": MOD_STATUS_CACHE_VERSION, "items": {}}
                by_path={}
                cache_compacted = False
                for row in _relation_language_items(data, "items", target_lang).values():
                    result = row.get("result") if isinstance(row, dict) else None
                    if _status_matches_language(result, target_lang) and result.get("path"):
                        compact_result = _compact_translation_status_result(result)
                        if compact_result != result:
                            row["result"] = compact_result
                            cache_compacted = True
                        r=dict(compact_result); r["cached"]=True; by_path[str(r.get("path"))]=r
                snap=self._load_translation_status_snapshot(target_lang=target_lang)
                snapshot_is_current = _translation_status_snapshot_is_current(snap)
                if cache_is_current and snapshot_is_current:
                    for r in (snap.get("results") or []):
                        if not _status_matches_language(r, target_lang) or not r.get("path"): continue
                        path=str(r.get("path"))
                        if path not in by_path:
                            rr=_compact_translation_status_result(r); rr["cached"]=True; rr["stale_cached"]=True; by_path[path]=rr
                if cache_compacted:
                    data["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    core.save_json(MOD_STATUS_CACHE_PATH, data)
                rows=list(by_path.values()); rows.sort(key=lambda r:str(r.get("mod","")).lower())
                selected_paths = list(snap.get('selected_paths') or []) if snapshot_is_current else []
                data = dict(data, _restore_target_lang=target_lang)
                self.events.put(('status_cache_restored',(data,rows,selected_paths)))
            except Exception as exc:
                self.events.put(('status_cache_restore_error',str(exc)))
        self.status_restore_thread=threading.Thread(target=work,daemon=True,name='status-cache-restore')
        self.status_restore_thread.start()

    def _apply_restored_mod_status(self, data, rows, selected_paths):
        self.status_restore_thread=None
        data = dict(data) if isinstance(data, dict) else {}
        if data.pop("_restore_target_lang", "japanese") != _current_target_lang(self):
            self._restore_cached_mod_status()
            return
        self.mod_status_cache=data if isinstance(data,dict) else {"version":MOD_STATUS_CACHE_VERSION,"items":{}}
        self.mod_research_results=list(rows or [])
        self.mod_status_search_var.set("")
        self.mod_status_search_result_var.set("")
        self._populate_mod_status_tree()
        wanted={str(x) for x in (selected_paths or []) if x}
        if wanted:
            for iid in self.mod_status_tree.get_children():
                try:
                    idx=int(str(iid).replace('mod_',''))
                    if 0 <= idx < len(self.mod_research_results) and str(self.mod_research_results[idx].get('path','')) in wanted:
                        self.mod_status_tree.selection_add(iid)
                except Exception:
                    continue
        counts={}
        for r in self.mod_research_results: counts[r.get('status','')]=counts.get(r.get('status',''),0)+1
        summary=' / '.join(f'{display_status(k)}: {v}' for k,v in counts.items())
        self.mod_status_summary_var.set(i18n.t('u7.cache_restored_entries', count=len(self.mod_research_results), value=f'　{summary}' if summary else ''))
        # Rewrite legacy/markerless snapshots from the validated generation cache.
        self._save_translation_status_state("cache_restored")
        self._refresh_diagnostic_targets()
        self._refresh_backup_restore_entries()

    def research_selected_mod_background(self):
        # 旧UI互換。調査機能は翻訳状況タブの選択場所調査へ統合済み。
        self.research_monitor_targets()

    def research_all_mods_background(self):
        # 旧UI互換。調査機能は翻訳状況タブの選択場所調査へ統合済み。
        self.research_monitor_targets()

    def _mod_classification_key(self, mod_root: Path) -> str:
        try:
            return str(Path(mod_root).expanduser().resolve())
        except Exception:
            return str(Path(mod_root).expanduser())

    def _current_mod_has_japanese(self, mod_root: Path, *, target_lang=None) -> bool:
        target_lang = target_lang or _current_target_lang(self)
        loc = core.mod_localization_root(Path(mod_root))
        if not loc:
            return False
        for fp in core.gather_yml_files(loc):
            try:
                if core.parse_localization_file(fp)[0] == target_lang:
                    return True
            except Exception:
                continue
        return False

    def _original_target_presence_before_overwrite(self, mod_root, target_lang):
        """Use the earliest exact source-overwrite snapshot as pre-write evidence."""
        key = self._mod_classification_key(Path(mod_root))
        kinds = {i18n.t_lang(lang, 'u6.source_mod_overwrite') for lang in ("japanese", "english")}
        snapshots = []
        for manifest_path in BACKUP_ROOT.glob("*/*/*/*/backup_manifest.json"):
            manifest = core.load_json(manifest_path, {})
            if not isinstance(manifest, dict) or manifest.get("backup_kind") not in kinds:
                continue
            if not manifest.get("target_root") or self._mod_classification_key(Path(manifest["target_root"])) != key:
                continue
            if manifest.get("snapshot_type") != "full_localization":
                continue
            if manifest.get("written_target_lang") == target_lang:
                return False
            loc = manifest_path.parent / "localization"
            if loc.is_dir():
                snapshots.append((str(manifest.get("created_at") or manifest_path), loc))
        if not snapshots:
            return None
        loc = min(snapshots, key=lambda entry: entry[0])[1]
        for file in core.gather_yml_files(loc):
            if core.parse_localization_file(file)[0] == target_lang:
                return True
        return False

    def _first_seen_japanese_candidate(self, mod_root: Path, *, target_lang=None) -> bool:
        """Return whether this Mod was Japanese-capable when first classified.

        The value is sticky.  Japanese YAML generated later by this application
        must not promote an ordinary source/parent/child Mod into an external
        Japanese translation Mod candidate.  When available, the older Translation
        Status cache is used as bootstrap evidence so upgrading from an earlier
        version keeps the pre-generation classification.
        """
        root = Path(mod_root)
        target_lang = target_lang or _current_target_lang(self)
        key = self._mod_classification_key(root)
        with self.mod_classification_lock:
            mods = self.mod_classification_cache.setdefault("mods", {})
            row = mods.get(key)
            if target_lang != "japanese" and isinstance(row, dict):
                targets = row.get("had_target_at_first_seen") or {}
                if target_lang in targets:
                    return bool(targets[target_lang])
            if target_lang == "japanese" and isinstance(row, dict) and "had_japanese_at_first_seen" in row:
                # Refresh display-only metadata without changing the sticky
                # first-seen role.  This repairs Vic3 caches that previously
                # stored the numeric Workshop directory as the Mod name.
                detected_name = core.detect_mod_name(root)
                if detected_name and row.get("mod") != detected_name:
                    row["mod"] = detected_name
                    row["path"] = key
                    self.mod_classification_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    core.save_json(MOD_CLASSIFICATION_CACHE_PATH, self.mod_classification_cache)
                return bool(row.get("had_japanese_at_first_seen"))

        historical = None
        try:
            with self.mod_status_cache_lock:
                old = _relation_language_items(self.mod_status_cache, "items", target_lang).get(key)
            old_result = old.get("result") if isinstance(old, dict) else None
            files_field = "japanese_files"
            if _status_matches_language(old_result, target_lang) and files_field in old_result:
                historical = bool(int(old_result.get(files_field, 0) or 0))
        except Exception:
            historical = None
        if target_lang != "japanese":
            before_overwrite = self._original_target_presence_before_overwrite(root, target_lang)
            if before_overwrite is not None:
                historical = before_overwrite
        initial_has_japanese = self._current_mod_has_japanese(root, target_lang=target_lang) if historical is None else historical
        if target_lang != "japanese":
            with self.mod_classification_lock:
                row = self.mod_classification_cache.setdefault("mods", {}).setdefault(key, {
                    "path": key, "mod": core.detect_mod_name(root),
                })
                row.setdefault("had_target_at_first_seen", {})[target_lang] = bool(initial_has_japanese)
                self.mod_classification_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
                core.save_json(MOD_CLASSIFICATION_CACHE_PATH, self.mod_classification_cache)
            return bool(initial_has_japanese)
        row = {
            "path": key,
            "mod": core.detect_mod_name(root),
            "first_seen_at": datetime.now().isoformat(timespec="seconds"),
            "had_japanese_at_first_seen": bool(initial_has_japanese),
            "initial_role": "japanese_candidate" if initial_has_japanese else "source_mod",
        }
        with self.mod_classification_lock:
            previous = self.mod_classification_cache.setdefault("mods", {}).get(key, {})
            if "had_target_at_first_seen" in previous:
                row["had_target_at_first_seen"] = previous["had_target_at_first_seen"]
            self.mod_classification_cache.setdefault("mods", {})[key] = row
            self.mod_classification_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_CLASSIFICATION_CACHE_PATH, self.mod_classification_cache)
        return bool(initial_has_japanese)

    def _invalidate_mod_status_cache_paths(self, paths):
        changed=False
        with self.mod_status_cache_lock:
            for raw in paths or []:
                try: key=self._mod_classification_key(Path(raw))
                except Exception: key=str(raw)
                for target_lang in ["japanese", *self.mod_status_cache.get("languages", {})]:
                    items=_relation_language_items(self.mod_status_cache, "items", target_lang)
                    if key in items:
                        items.pop(key, None); changed=True
            if changed:
                self.mod_status_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
                core.save_json(MOD_STATUS_CACHE_PATH, self.mod_status_cache)

    def _mod_relation_override(self, mod_root: Path, *, target_lang=None) -> dict:
        target_lang = target_lang or _current_target_lang(self)
        key = self._mod_classification_key(Path(mod_root))
        with self.mod_relation_override_lock:
            row = _relation_language_items(self.mod_relation_overrides, "mods", target_lang).get(key, {})
            return dict(row) if isinstance(row, dict) else {}

    def _save_mod_relation_overrides(self):
        with self.mod_relation_override_lock:
            self.mod_relation_overrides["schema"] = 1
            self.mod_relation_overrides["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_RELATION_OVERRIDES_PATH, self.mod_relation_overrides)
        self._save_shared_mod_state_cache("relation_override_updated")
        try:
            self._save_translation_status_state("relation_override_updated")
        except Exception:
            pass

    def _set_mod_relation_override(self, mod_root: Path, role: str, source_paths=None, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        key = self._mod_classification_key(Path(mod_root))
        role = role if role in {"auto", "translation", "source"} else "auto"
        sources=[]
        for raw in (source_paths or []):
            try: src=self._mod_classification_key(Path(raw))
            except Exception: src=str(raw)
            if src != key and src not in sources:
                sources.append(src)
        with self.mod_relation_override_lock:
            mods=_relation_language_items(self.mod_relation_overrides, "mods", target_lang, create=True)
            if role == "auto" and not sources:
                mods.pop(key, None)
            else:
                mods[key]={
                    "role":role, "source_paths":sources,
                    "mod":core.detect_mod_name(Path(mod_root)),
                    "updated_at":datetime.now().isoformat(timespec="seconds"),
                }
        self._save_mod_relation_overrides()

    def _base_game_source_data_for_mod(self, mod_root):
        """Return cached vanilla source text by language for the owning game.

        This is deliberately non-interactive because Translation Status and Total
        Diagnosis may call it from background workers.  The cache is per game and
        retains English/Simplified-Chinese text so unchanged vanilla carryovers can
        be removed from Mod-to-Mod relationship evidence.
        """
        game = self._backup_game_name_for_root(mod_root)
        if not game or game == "ゲーム未特定":
            return {"english": {}, "simp_chinese": {}}, game
        cache = getattr(self, "_base_game_source_data_cache", None)
        if cache is None:
            cache = {}
            self._base_game_source_data_cache = cache
        if game in cache:
            return cache[game], game

        loc_root = None
        try:
            libs = core.discover_steam_libraries(Path.home(), sys.platform)
        except Exception:
            libs = []
        for lib in libs:
            base = Path(lib) / "steamapps" / "common" / game
            for rel in ("game/localization", "game/localisation", "localization", "localisation"):
                candidate = base / rel
                if candidate.is_dir():
                    loc_root = candidate
                    break
            if loc_root is not None:
                break

        source_data = {"english": {}, "simp_chinese": {}}
        if loc_root is not None:
            try:
                for fp in core.gather_yml_files(loc_root):
                    # Most Paradox layouts include the language in the directory or
                    # filename.  Skip clearly unrelated languages before parsing.
                    low = str(fp).replace("\\", "/").lower()
                    if not any(token in low for token in ("english", "simp_chinese", "l_english", "l_simp_chinese")):
                        continue
                    try:
                        lang, entries, _ = core.parse_localization_file(fp)
                    except Exception:
                        continue
                    if lang in {"english", "simp_chinese"}:
                        source_data[lang].update(entries or {})
            except Exception as exc:
                record_error(i18n.t('p0.load_base_game_source'), exc, f"{game}: {loc_root}")
        cache[game] = source_data
        return source_data, game

    def _base_game_source_keys_for_mod(self, mod_root):
        """Compatibility wrapper returning the cached vanilla key universe."""
        source_data, game = self._base_game_source_data_for_mod(mod_root)
        keys = set(source_data.get("english", {})) | set(source_data.get("simp_chinese", {}))
        return keys, game

    def _annotate_translation_index_with_base_game_keys(self, rows):
        """Attach the owning game's vanilla key set to every Japanese candidate."""
        for row in rows or []:
            try:
                source_data, game = self._base_game_source_data_for_mod(Path(row.get("path", "")))
                keys = set(source_data.get("english", {})) | set(source_data.get("simp_chinese", {}))
                row["base_game_keys"] = keys
                row["base_game_source_entries"] = source_data
                row["base_game_name"] = game
            except Exception as exc:
                row["base_game_keys"] = set()
                row["base_game_source_entries"] = {"english": {}, "simp_chinese": {}}
                row["base_game_name"] = "ゲーム未特定"
                record_error(i18n.t('u1.base_game_error'), exc, str(row.get("path", "")))
        return rows

    def _build_stable_translation_mod_index(self, pool_roots, *, target_lang=None):
        target_lang = target_lang or _current_target_lang(self)
        if target_lang == "english":
            return []
        eligible = []
        overrides = {}
        for root in pool_roots:
            root=Path(root)
            try:
                ov=self._mod_relation_override(root, target_lang=target_lang)
                role=ov.get("role","auto")
                if role == "source":
                    continue
                if role == "translation" or self._first_seen_japanese_candidate(root, target_lang=target_lang):
                    eligible.append(root)
                    overrides[self._mod_classification_key(root)] = ov
            except Exception as exc:
                record_error(i18n.t('u6.initial_mod_classification'), exc, str(root))
        rows=core.build_translation_mod_index(eligible, target_lang=target_lang)
        self._annotate_translation_index_with_base_game_keys(rows)
        for row in rows:
            try: key=self._mod_classification_key(Path(row.get("path","")))
            except Exception: key=str(row.get("path",""))
            ov=overrides.get(key) or {}
            row["manual_role"] = ov.get("role", "auto")
            row["manual_source_paths"] = list(ov.get("source_paths") or [])
        return core.assign_translation_candidate_owners(pool_roots, rows, target_lang=target_lang)

    def _known_mod_rows_for_relation_dialog(self):
        rows=[]; seen=set()
        def add(path, name=""):
            if not path: return
            p=Path(path)
            if not p.is_dir(): return
            key=self._mod_classification_key(p)
            if key in seen: return
            seen.add(key)
            rows.append({"path":key,"mod":name or core.detect_mod_name(p)})
        for r in self.mod_research_results:
            add(r.get("path"), r.get("mod",""))
        if hasattr(self,"diagnostic_target_tree"):
            for iid in self.diagnostic_target_tree.get_children():
                vals=self.diagnostic_target_tree.item(iid,"values")
                if len(vals)>=3: add(vals[2], vals[0])
        rows.sort(key=lambda x:(str(x.get("mod","")).lower(),str(x.get("path",""))))
        return rows

    def _preselected_relation_path(self, origin="status"):
        tree = self.mod_status_tree if origin=="status" and hasattr(self,"mod_status_tree") else self.diagnostic_target_tree if hasattr(self,"diagnostic_target_tree") else None
        if tree is not None:
            sel=tree.selection()
            if sel:
                vals=tree.item(sel[0],"values")
                if origin=="status":
                    name=str(vals[1]) if len(vals)>1 else ""
                    for r in self.mod_research_results:
                        if r.get("mod")==name and r.get("path"):
                            return self._mod_classification_key(Path(r["path"]))
                elif len(vals)>=3:
                    return self._mod_classification_key(Path(vals[2]))
        return ""

    def _open_mod_relation_dialog(self, origin="status"):
        rows=self._known_mod_rows_for_relation_dialog()
        if not rows:
            messagebox.showinfo(APP_NAME,i18n.t('u6.retrieve_the_mod_list_in_translation'))
            return
        win=tk.Toplevel(self); win.title(i18n.t('u6.mod_classification_and_linking')); win.geometry("1050x650"); win.transient(self)
        outer=ttk.Frame(win,padding=10); outer.pack(fill="both",expand=True)
        ttk.Label(outer,text=i18n.t('u6.manual_exceptions_override_automatic_assessment_translation', target_name=i18n.t("lang." + 'japanese')),foreground="#555").pack(fill="x",pady=(0,8))
        pane=ttk.Panedwindow(outer,orient="horizontal"); pane.pack(fill="both",expand=True)
        lf=ttk.LabelFrame(pane,text="Mod",padding=6); rf=ttk.Frame(pane); pane.add(lf,weight=3); pane.add(rf,weight=4)
        mt=ttk.Treeview(lf,columns=("mod","class","sources","path"),show="headings",selectmode="browse")
        for c,txt,w in (("mod","Mod",240),("class",i18n.t('u6.manual_classification_2'),110),("sources",i18n.t('u6.linked_sources'),70),("path",i18n.t('u6.location_3'),360)):
            mt.heading(c,text=txt); mt.column(c,width=w,minwidth=w,stretch=False,anchor="w")
        msy=ttk.Scrollbar(lf,orient="vertical",command=mt.yview); msx=ttk.Scrollbar(lf,orient="horizontal",command=mt.xview); mt.configure(yscrollcommand=msy.set,xscrollcommand=msx.set)
        lf.rowconfigure(0,weight=1); lf.columnconfigure(0,weight=1); mt.grid(row=0,column=0,sticky="nsew"); msy.grid(row=0,column=1,sticky="ns"); msx.grid(row=1,column=0,sticky="ew")
        mt_actions=ttk.Frame(lf); mt_actions.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(7,0))
        role_var=tk.StringVar(value="auto"); current_path=tk.StringVar(value="")
        rolebox=ttk.LabelFrame(rf,text=i18n.t('u6.classification'),padding=8); rolebox.pack(fill="x")
        for text,val in ((i18n.t('u6.automatic_assessment'),"auto"),(i18n.t('u6.this_is_a_translation_mod', target_name=i18n.t("lang." + 'japanese')),"translation"),(i18n.t('u6.this_is_a_source_mod'),"source")):
            ttk.Radiobutton(rolebox,text=text,value=val,variable=role_var).pack(anchor="w",pady=2)
        ttk.Label(rolebox,text=i18n.t('u6.marking_a_mod_as_a_translation', target_name=i18n.t("lang." + 'japanese')),foreground="#666",wraplength=520,justify="left").pack(anchor="w",pady=(6,0))
        srcbox=ttk.LabelFrame(rf,text=i18n.t('u6.linked_source_mods_multi_select'),padding=8); srcbox.pack(fill="both",expand=True,pady=(8,0))
        st=ttk.Treeview(srcbox,columns=("mod","path"),show="headings",selectmode="extended")
        st.heading("mod",text=i18n.t('u6.source_mod_4')); st.heading("path",text=i18n.t('u6.location_3')); st.column("mod",width=260,minwidth=260,stretch=False); st.column("path",width=480,minwidth=480,stretch=False)
        ssy=ttk.Scrollbar(srcbox,orient="vertical",command=st.yview); ssx=ttk.Scrollbar(srcbox,orient="horizontal",command=st.xview); st.configure(yscrollcommand=ssy.set,xscrollcommand=ssx.set)
        srcbox.rowconfigure(0,weight=1); srcbox.columnconfigure(0,weight=1); st.grid(row=0,column=0,sticky="nsew"); ssy.grid(row=0,column=1,sticky="ns"); ssx.grid(row=1,column=0,sticky="ew")
        src_actions=ttk.Frame(srcbox); src_actions.grid(row=2,column=0,columnspan=2,sticky="ew",pady=(7,0))

        # 対応元Modは通常クリック自体をON/OFFトグルにする。
        # macOS/Windows/Linuxで修飾キーに依存せず、選択済みの行を
        # もう一度押すだけで解除できるようにする。
        def toggle_source_click(event):
            if st.identify_region(event.x,event.y) not in ("cell","tree"):
                return None
            iid=st.identify_row(event.y)
            if not iid:
                return None
            selected=set(st.selection())
            if iid in selected:
                st.selection_remove(iid)
            else:
                st.selection_add(iid)
            st.focus(iid); st.see(iid)
            st.event_generate("<<TreeviewSelect>>")
            return "break"

        def clear_source_selection():
            sel=st.selection()
            if sel:
                st.selection_remove(sel)
                st.event_generate("<<TreeviewSelect>>")

        st.bind("<Button-1>",toggle_source_click,add="+")
        ttk.Button(src_actions,text=i18n.t('u6.deselect_linked_source_mods'),command=clear_source_selection).pack(side="left")
        iid_by_path={}; row_by_iid={}
        for row in rows:
            ov=self._mod_relation_override(Path(row["path"])); role=ov.get("role","auto"); label={"auto":i18n.t('u6.automatic'),"translation":i18n.t('u6.translation_mod', target_name=i18n.t("lang." + 'japanese')),"source":i18n.t('u6.source_mod_3')}.get(role,i18n.t('u6.automatic'))
            iid=mt.insert("","end",values=(row["mod"],label,len(ov.get("source_paths") or []),row["path"])); iid_by_path[row["path"]]=iid; row_by_iid[iid]=row
        def clear_mod_selection(*_):
            sel=mt.selection()
            if sel:
                mt.selection_remove(sel)
            current_path.set("")
            role_var.set("auto")
            for iid in st.get_children():
                st.delete(iid)

        click_state={"row":"","was_selected":False}
        def remember_mod_click(event):
            row=mt.identify_row(event.y) if mt.identify_region(event.x,event.y) in ("cell","tree") else ""
            click_state["row"]=row
            click_state["was_selected"]=bool(row and row in mt.selection())
        def toggle_mod_click(event):
            row=mt.identify_row(event.y) if mt.identify_region(event.x,event.y) in ("cell","tree") else ""
            if not row or row!=click_state.get("row"):
                return None
            if click_state.get("was_selected"):
                mt.selection_remove(row)
                current_path.set("")
                role_var.set("auto")
                for iid in st.get_children():
                    st.delete(iid)
            else:
                mt.selection_set(row)
                mt.focus(row)
                mt.see(row)
            mt.event_generate("<<TreeviewSelect>>")
            return "break"

        def load_selected(*_):
            sel=mt.selection()
            if not sel:
                current_path.set("")
                role_var.set("auto")
                for iid in st.get_children(): st.delete(iid)
                return
            row=row_by_iid.get(sel[0])
            if not row: return
            current_path.set(row["path"]); ov=self._mod_relation_override(Path(row["path"])); role_var.set(ov.get("role","auto"))
            for iid in st.get_children(): st.delete(iid)
            selected=set(ov.get("source_paths") or []); to_select=[]
            for src in rows:
                if src["path"]==row["path"]: continue
                iid=st.insert("","end",values=(src["mod"],src["path"]))
                if src["path"] in selected: to_select.append(iid)
            if to_select: st.selection_set(to_select); st.see(to_select[0])
        mt.bind("<ButtonPress-1>",remember_mod_click,add="+")
        mt.bind("<ButtonRelease-1>",toggle_mod_click,add="+")
        mt.bind("<<TreeviewSelect>>",load_selected)
        ttk.Button(mt_actions,text=i18n.t('u6.deselect_all'),command=clear_mod_selection).pack(side="left")
        btns=ttk.Frame(rf); btns.pack(fill="x",pady=(8,0))
        def save_current():
            raw=current_path.get()
            if not raw: return
            sources=[]
            if role_var.get()=="translation":
                for iid in st.selection():
                    vals=st.item(iid,"values")
                    if len(vals)>=2: sources.append(vals[1])
            self._set_mod_relation_override(Path(raw),role_var.get(),sources)
            iid=iid_by_path.get(raw)
            if iid:
                row=row_by_iid[iid]; label={"auto":i18n.t('u6.automatic'),"translation":i18n.t('u6.translation_mod', target_name=i18n.t("lang." + 'japanese')),"source":i18n.t('u6.source_mod_3')}.get(role_var.get(),i18n.t('u6.automatic'))
                mt.item(iid,values=(row["mod"],label,len(sources),row["path"]))
            self._invalidate_mod_status_cache_paths([r["path"] for r in rows])
            self._refresh_diagnostic_targets()
            messagebox.showinfo(APP_NAME,i18n.t('u6.mod_classification_link_exceptions_saved_they'),parent=win)
        ttk.Button(btns,text=i18n.t('u6.save_these_settings'),command=save_current).pack(side="left")
        ttk.Button(btns,text=i18n.t('u6.close'),command=win.destroy).pack(side="right")
        pre=self._preselected_relation_path(origin)
        iid=iid_by_path.get(pre) or (mt.get_children()[0] if mt.get_children() else "")
        if iid:
            mt.selection_set(iid); mt.see(iid); load_selected()

    def _start_mod_research(self, roots, replace=True, translation_pool=None):
        if self.mod_research_thread and self.mod_research_thread.is_alive():
            messagebox.showinfo(APP_NAME,i18n.t('u3.research_running'))
            return
        self.mod_research_stop_event.clear()
        self.mod_research_stop_btn.config(state="normal")
        self.mod_status_summary_var.set(i18n.t('u3.research_progress', count=len(roots)))
        self._set_monitor_scan_status(i18n.t('u3.research_start', count=len(roots)), i18n.t('u3.research_detail'))
        if replace:
            # 調べ直すModの古い結果だけを除く。別の保管場所（ローカル／Workshop）の結果は残して一緒に見られるようにする。
            self.mod_status_search_var.set("")
            self.mod_status_search_result_var.set("")
            self.events.put(("mod_status_results",App._results_without_roots(self.mod_research_results, roots)))
        self._mod_research_worker_settings = self._snapshot_monitor_worker_settings()
        self.mod_research_thread=threading.Thread(target=self._mod_research_worker,args=(roots,translation_pool),daemon=True)
        self.mod_research_thread.start()

    def stop_mod_research(self):
        self.mod_research_stop_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.mod_status_summary_var.set(i18n.t('u3.research_stop'))

    def _mod_research_worker(self, roots, translation_pool=None):
        try:
            total=len(roots)
            results=[]
            settings = dict(getattr(self, "_mod_research_worker_settings", {}) or {})
            target_lang = settings.get("target_lang", core.DEFAULT_TARGET_LANG)
            check_external = bool(settings.get("check_translation_mods", True))
            check_external = check_external and target_lang != "english"
            pool_roots = list(translation_pool or roots)
            translation_index = self._build_stable_translation_mod_index(pool_roots, target_lang=target_lang) if check_external else None
            pool_signature = ""
            if check_external:
                h = hashlib.sha256()
                h.update(f"relation-algorithm:{core.TRANSLATION_RELATION_ALGORITHM_VERSION}".encode())
                for root in sorted((Path(r) for r in pool_roots), key=lambda x: str(x)):
                    h.update(str(root).encode("utf-8", "ignore"))
                    h.update(self._mod_source_signature(root, target_lang=target_lang).encode())
                pool_signature = h.hexdigest()
            for i,mod_root in enumerate(roots,1):
                if self.mod_research_stop_event.is_set(): break
                mod_name = core.detect_mod_name(Path(mod_root))
                self.events.put(("mod_research_progress",(i,total,mod_name)))
                signature = self._mod_source_signature(Path(mod_root), target_lang=target_lang)
                if pool_signature:
                    signature = hashlib.sha256((signature + ":" + pool_signature).encode()).hexdigest()
                result = self._cached_status_for_mod(Path(mod_root), signature, target_lang=target_lang)
                if result is None:
                    result=core.analyze_mod_translation_status(mod_root, translation_index=translation_index, target_lang=target_lang)
                    candidates=result.get("candidates",[])
                    try:
                        refined=self._refine_candidates_with_monitor_llm(candidates, settings)
                        result["candidates"]=refined
                        result["gap_count"]=len(refined)
                        result["gap_origin_counts"]=core.gap_origin_counts(refined)
                        result["gap_reason"]=core.gap_reason_text(refined, target_lang=target_lang)
                        # For a separate Japanese translation mod, refined candidates are that mod's missing/foreign entries.
                        if result.get("external_translation_mod") and not result.get("external_translation_complete"):
                            result["external_translation_gaps"] = refined
                            result["external_translation_gap_count"] = len(refined)
                            result["gap_count"] = len(refined)
                            if refined:
                                result["status"]=status_value("mod_external_gaps")
                                result["message"]=i18n.t('u3.external_gaps', mod=result['mod'], external_translation_mod=result['external_translation_mod'], count=len(refined), value=core.gap_reason_text(refined, target_lang=target_lang))
                            else:
                                result["status"]=status_value("mod_external_complete")
                                result["external_translation_complete"] = True
                                result["message"]=i18n.t('u3.external_complete', mod=result['mod'], external_translation_mod=result['external_translation_mod'])
                        elif result.get("japanese_files",0)==0 or result.get("japanese_keys",0)==0:
                            if result.get("external_translation_complete"):
                                result["status"]=status_value("mod_external_complete")
                            elif result.get("external_translation_mod"):
                                result["status"]=status_value("mod_external_gaps")
                            else:
                                result["status"]=status_value("mod_not_translated")
                                result["message"]=i18n.t('u3.no_japanese', mod=result['mod'])
                        elif refined:
                            result["status"]=status_value("mod_gaps")
                            result["gap_count"] = len(refined)
                            result["message"]=i18n.t('u3.mod_gaps', mod=result['mod'], count=len(refined), value=core.gap_reason_text(refined, target_lang=target_lang))
                        elif not result.get("external_translation_mod"):
                            result["status"]=status_value("mod_translated")
                            result["gap_count"] = 0
                            result["message"]=i18n.t('u3.japanese_found', mod=result['mod'])
                    except core.StopRequested:
                        if self.mod_research_stop_event.is_set(): break
                    except Exception as e:
                        record_error(i18n.t('u3.research_llm_error'), e, str(mod_root))
                        self.events.put(("monitor_log",i18n.t('u3.research_llm_skip', mod=result.get('mod','Mod'), e=e)))
                    result["game"] = str(result.get("game") or self._backup_game_name_for_root(Path(mod_root)))
                    core.apply_translation_warning_status(result)
                else:
                    self.events.put(("monitor_log", i18n.t('u3.research_cache', mod=result.get('mod', Path(mod_root).name))))
                result["game"] = str(result.get("game") or self._backup_game_name_for_root(Path(mod_root)))
                if target_lang != "japanese":
                    notices = [part for part in result.get("message_parts", []) if part.get("id") == "u9.unsupported_game_language"]
                    result["message_parts"] = [ui_status.message_part(
                        'u6.target_research_result', mod=result.get("mod", ""),
                        target_name=i18n.t("lang." + target_lang),
                        status=display_status(result), count=result.get("gap_count", 0)), *notices]
                if result.get("external_check_skipped") == "english_target":
                    result.setdefault("message_parts", []).append(ui_status.message_part('u6.english_external_check_skipped'))
                if not result.get("cached"):
                    self._cache_mod_status_result(Path(mod_root), signature, result, target_lang=target_lang)
                results.append(result)
                self.events.put(("mod_status_append",result))
            self.events.put(("mod_research_done",results))
        except Exception as e:
            self.events.put(("mod_research_error",str(e)))

    def _selected_mod_status_result(self):
        if not hasattr(self, "mod_status_tree"):
            return None
        sel = self.mod_status_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, i18n.t('u6.select_one_mod_in_the_translation'))
            return None
        iid = sel[0]
        if iid.startswith("mod_"):
            try:
                idx = int(iid.split("_", 1)[1])
                if 0 <= idx < len(self.mod_research_results):
                    return self.mod_research_results[idx]
            except Exception:
                pass
        values = self.mod_status_tree.item(iid, "values")
        mod_name = values[1] if len(values) >= 2 else ""
        for r in self.mod_research_results:
            if r.get("mod") == mod_name:
                return r
        return None

    def research_selected_status_mods(self):
        """翻訳状況一覧で選択したModだけを強制再調査し、他の結果は保持する。"""
        selected=self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME,i18n.t('u6.select_mods_to_research_again_in'))
            return
        if self.mod_research_thread and self.mod_research_thread.is_alive():
            messagebox.showinfo(APP_NAME,i18n.t('u6.research_is_already_running'))
            return
        roots=[]; selected_paths=set()
        for result in selected:
            root=Path(result.get("path", ""))
            if root.exists() and core.mod_localization_root(root):
                roots.append(root)
                try:selected_paths.add(str(root.resolve()))
                except Exception:selected_paths.add(str(root))
        if not roots:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_accessible_mod_folders_found_in'))
            return
        kept=[]
        for r in self.mod_research_results:
            try:key=str(Path(r.get("path","")).resolve())
            except Exception:key=str(Path(r.get("path","")))
            if key not in selected_paths:
                kept.append(r)
        self.mod_research_results=kept
        with self.mod_status_cache_lock:
            items=_relation_language_items(self.mod_status_cache, "items", _current_target_lang(self), create=True)
            for key in selected_paths:
                items.pop(key,None)
            core.save_json(MOD_STATUS_CACHE_PATH,self.mod_status_cache)
        self._populate_mod_status_tree()
        pool=[]; seen=set()
        for r in kept+selected:
            root=Path(r.get("path", ""))
            try:key=str(root.resolve())
            except Exception:key=str(root)
            if root.exists() and key not in seen:
                seen.add(key); pool.append(root)
        games=[{"game":r.get("game") or self._backup_game_name_for_root(Path(r.get("path","")))} for r in selected]
        pool=self._game_wide_translation_pool(games, pool or roots)
        self._start_mod_research(roots, replace=False, translation_pool=pool)

    def queue_selected_mods_to_chinese_basis(self):
        """翻訳状況で選択したうち、簡体字中国語localizationを持つModだけ中国語基準キューへ追加する。"""
        selected=self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME,i18n.t("u2.select_status_mods"))
            return
        added=0; skipped=[]
        for result in selected:
            loc=Path(result.get("localization",""))
            # 旧キャッシュにはsimp_chinese_filesが無い場合があるため、実ファイルでも再確認する。
            has_zh=bool(result.get("simp_chinese_files",0))
            if not has_zh and loc.is_dir():
                try:
                    has_zh=any(core.parse_localization_file(f)[0]=="simp_chinese" for f in core.gather_yml_files(loc))
                except Exception:
                    has_zh=False
            if not has_zh:
                skipped.append(result.get("mod",loc.name))
                continue
            item,msg=self._append_chinese_queue(loc,result.get("mod",loc.name))
            if item:
                mod_root=Path(result.get("path", ""))
                item["mod_root"]=str(mod_root)
                item["mod_localization"]=str(loc)
                item["direct_from_status"]=True
                item["external_translation_mod"]=result.get("external_translation_mod","")
                item["external_translation_path"]=result.get("external_translation_path","")
                item["external_translation_localization"]=result.get("external_translation_localization","")
                item["external_gap_keys"]=[c.get("key") for c in _status_gap_rows(result, external=True) if c.get("key")]
                added+=1
        self._refresh_chinese_queue_tree()
        if added:
            try:self.notebook.select(self.tab_chinese)
            except Exception:pass
            self.chinese_status_var.set(i18n.t("u2.status_mods_added", count=added))
        if skipped:
            self._append_chinese_log((i18n.t("u2.skipped_mods_more", mods="、".join(skipped[:10]), count=len(skipped)-10) if len(skipped)>10 else i18n.t("u2.skipped_mods", mods="、".join(skipped[:10]))))
        if not added:
            messagebox.showinfo(APP_NAME,i18n.t("u2.selected_no_chinese"))

    def queue_selected_mod_from_status(self, start_now=False):
        """翻訳状況で選択したModをすべて通常翻訳キューへ追加する。"""
        selected = self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME, i18n.t('u1.select_status_mod'))
            return []
        added=[]; skipped=[]
        for result in selected:
            loc = Path(result.get("localization", ""))
            if not loc.is_dir():
                skipped.append(result.get("mod", Path(result.get("path", "")).name))
                continue
            item=self._queue_mod_status_result(result)
            if item is not None:
                added.append(item)
        self._refresh_queue_tree()
        self.save_session(active=False)
        if added:
            try:self.notebook.select(self.tab_translate)
            except Exception:pass
        if start_now and added:
            if self.worker and self.worker.is_alive():
                messagebox.showinfo(APP_NAME, i18n.t('u1.queued_after_current', count=len(added)))
            else:
                self.start_queue()
        elif added:
            msg=i18n.t('u1.selected_mods_added', count=len(added))
            if skipped: msg += i18n.t('u1.localization_skipped', count=len(skipped))
            messagebox.showinfo(APP_NAME,msg)
        elif skipped:
            messagebox.showinfo(APP_NAME,i18n.t('u1.no_localization'))
        return added

    def translate_selected_mod_from_status(self):
        """互換用。選択Modを通常翻訳キューへ追加して開始する。"""
        self.queue_selected_mod_from_status(start_now=True)

    def _selected_mod_status_results(self):
        """Return every selected result in the translation-status tree."""
        if not hasattr(self, "mod_status_tree"):
            return []
        selected = self.mod_status_tree.selection()
        results = []
        seen = set()
        for iid in selected:
            if iid == MOD_STATUS_EMPTY_IID:
                continue
            result = None
            if iid.startswith("mod_"):
                try:
                    idx = int(iid.split("_", 1)[1])
                    if 0 <= idx < len(self.mod_research_results):
                        result = self.mod_research_results[idx]
                except Exception:
                    pass
            if result is None:
                values = self.mod_status_tree.item(iid, "values")
                mod_name = values[1] if len(values) >= 2 else ""
                for candidate in self.mod_research_results:
                    if candidate.get("mod") == mod_name:
                        result = candidate
                        break
            if result is not None:
                key = result.get("path") or id(result)
                if key not in seen:
                    seen.add(key)
                    results.append(result)
        return results

    def _queue_mod_status_result(self, result):
        """Queue one researched mod without changing the current tab or showing per-mod dialogs."""
        loc = Path(result.get("localization", ""))
        mod_root = Path(result.get("path", ""))
        if not loc.is_dir():
            return None
        target_lang = result.get("target_lang", core.DEFAULT_TARGET_LANG)
        isolated_out = self._isolated_output_path(loc, Path(self.normal_output_var.get().strip() or str(OUTPUT_ROOT)), result.get("mod", mod_root.name), target_lang=target_lang)
        self._append_queue(loc, out=isolated_out, target_lang=target_lang)
        item = self.queue_items[-1]
        item["mod_root"] = str(mod_root)
        item["mod_localization"] = str(loc)
        item["mod_name"] = result.get("mod", mod_root.name)
        item["direct_from_status"] = True
        item["external_translation_mod"] = result.get("external_translation_mod", "")
        item["external_translation_path"] = result.get("external_translation_path", "")
        item["external_translation_localization"] = result.get("external_translation_localization", "")
        item["external_gap_keys"] = [c.get("key") for c in _status_gap_rows(result, external=True) if c.get("key")]
        # Preserve the exact gap set shown in the Translation Status tab for diagnostics/session restore.
        item["status_gap_candidates"] = _status_gap_rows(result)
        item["status_gap_count"] = int(result.get("gap_count", 0) or 0)
        return item

    def _status_results_except_selected(self):
        if not self.mod_research_results:
            messagebox.showinfo(APP_NAME, i18n.t('u6.research_mod_translation_status_first'))
            return None, None
        selected=self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME, i18n.t('u6.select_at_least_one_mod_to'))
            return None, None
        excluded={str(Path(r.get("path", ""))) for r in selected}
        remaining=[r for r in self.mod_research_results if str(Path(r.get("path", ""))) not in excluded]
        return selected, remaining

    def queue_all_except_selected_mods(self):
        """選択Modを除外し、残りを通常翻訳キューへ一括追加する。"""
        selected, remaining=self._status_results_except_selected()
        if selected is None: return
        targets=[]; skipped_complete=0; skipped_invalid=0
        for result in remaining:
            if result.get("status") in {"翻訳あり", "別Modで完全翻訳"} and not result.get("gap_count"):
                skipped_complete += 1
                continue
            if Path(result.get("localization", "")).is_dir(): targets.append(result)
            else: skipped_invalid += 1
        if not targets:
            messagebox.showinfo(APP_NAME,i18n.t('u1.no_remaining_mods'))
            return
        added=sum(1 for r in targets if self._queue_mod_status_result(r) is not None)
        self._refresh_queue_tree(); self.save_session(active=False)
        if added:
            try:self.notebook.select(self.tab_translate)
            except Exception:pass
        messagebox.showinfo(APP_NAME, i18n.t('u1.remaining_mods_added', excluded=len(selected), added=added, complete=skipped_complete, invalid=skipped_invalid))

    def queue_all_except_selected_mods_chinese(self):
        """選択Modを除外し、残りのうち中国語localizationがあるModを中国語基準キューへ一括追加する。"""
        selected, remaining=self._status_results_except_selected()
        if selected is None: return
        added=0; no_chinese=0; invalid=0
        for result in remaining:
            loc=Path(result.get("localization", ""))
            if not loc.is_dir():
                invalid += 1; continue
            has_zh=bool(result.get("simp_chinese_files",0))
            if not has_zh:
                try: has_zh=any(core.parse_localization_file(f)[0]=="simp_chinese" for f in core.gather_yml_files(loc))
                except Exception: has_zh=False
            if not has_zh:
                no_chinese += 1; continue
            item,_=self._append_chinese_queue(loc,result.get("mod",loc.name))
            if item:
                mod_root=Path(result.get("path", ""))
                item["mod_root"]=str(mod_root); item["mod_localization"]=str(loc); item["direct_from_status"]=True
                item["external_translation_mod"]=result.get("external_translation_mod","")
                item["external_translation_path"]=result.get("external_translation_path","")
                item["external_translation_localization"]=result.get("external_translation_localization","")
                item["external_gap_keys"]=[c.get("key") for c in _status_gap_rows(result, external=True) if c.get("key")]
                item["status_gap_candidates"] = _status_gap_rows(result)
                item["status_gap_count"] = int(result.get("gap_count", 0) or 0)
                added += 1
        self._refresh_chinese_queue_tree()
        if added:
            try:self.notebook.select(self.tab_chinese)
            except Exception:pass
        messagebox.showinfo(APP_NAME, i18n.t("u2.mods_excluded_summary", selected_count=len(selected), added_count=added, no_chinese_count=no_chinese, invalid_count=invalid))

    def translate_all_except_selected_mods(self):
        """旧呼び出し互換。現在は開始せず通常翻訳キューへ追加する。"""
        self.queue_all_except_selected_mods()

    def _infer_mod_target_for_item(self, item):
        loc = Path(item.get("mod_localization", "")) if item.get("mod_localization") else None
        root = Path(item.get("mod_root", "")) if item.get("mod_root") else None
        inp = Path(item.get("input", ""))
        if loc and loc.is_dir():
            if root and root.is_dir():
                return loc, root
            return loc, loc.parent
        if inp.is_dir() and core.is_localization_dir_name(inp.name):
            return inp, inp
        if inp.is_dir() and core.mod_localization_root(inp) is not None:
            return core.mod_localization_root(inp), inp
        return None, None

    def _selected_queue_items_for_kind(self, queue_kind):
        if queue_kind == "chinese":
            return [item for _, item in self._selected_chinese_queue_entries()]
        return [item for _, item in self._selected_normal_queue_entries()]

    def _write_missing_source_subset(self, loc_root: Path, source_lang: str, keys, mod_name: str):
        """Create a persistent sparse source tree containing only requested missing keys."""
        loc_root = Path(loc_root)
        wanted = {str(k) for k in keys if k}
        if not wanted:
            return None
        values = {}
        for fp in core.gather_yml_files(loc_root):
            try:
                lang, entries, _ = core.parse_localization_file(fp)
            except Exception:
                continue
            if lang != source_lang:
                continue
            for key in wanted:
                if key in entries:
                    values[key] = entries[key]
        if not values:
            return None
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe = re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+', '_', mod_name or "Mod").strip('_')[:60] or "Mod"
        work = WORK_STATE_ROOT / "不足翻訳キュー" / f"{stamp}_{safe}_{source_lang}"
        lang_dir = work / source_lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        out = lang_dir / f"paradox_localization_translator_missing_l_{source_lang}.yml"
        lines = [f"l_{source_lang}:"]
        for key in sorted(values):
            lines.append(f' {key}: "{core.escape_localization_value(values[key])}"')
        out.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")
        return work

    def transfer_selected_queue_to_opposite(self, queue_kind="normal", missing_only=False):
        """Transfer selected jobs to the opposite source-language queue, optionally only real missing keys."""
        if self._normal_queue_locked() or self._chinese_queue_locked():
            return
        items = self._selected_queue_items_for_kind(queue_kind)
        if not items:
            label = i18n.t('u1.chinese_basis') if queue_kind == "chinese" else i18n.t('u1.normal')
            messagebox.showinfo(APP_NAME, i18n.t('u1.select_source_queue', queue_name=label))
            return
        added = 0
        skipped = 0
        details = []
        for item in items:
            loc, mod_root = self._infer_mod_target_for_item(item)
            if not loc or not Path(loc).is_dir():
                skipped += 1; details.append(i18n.t('u1.localization_unknown', mod=item.get('mod_name',i18n.t('u1.unnamed_item'))))
                continue
            mod_name = item.get("mod_name") or (Path(mod_root).name if mod_root else Path(loc).name)
            source_lang = "english" if queue_kind == "chinese" else "simp_chinese"
            target_kind = "normal" if queue_kind == "chinese" else "chinese"
            input_path = Path(loc)
            missing_keys = []
            if missing_only:
                preferred = "simp_chinese" if queue_kind == "chinese" else "english"
                gaps = core.scan_translation_gaps(Path(loc), preferred_source=preferred, target_lang=_item_target_lang(item))
                origin = "english_only" if source_lang == "english" else "chinese_only"
                missing_keys = [g.get("key") for g in gaps if g.get("source_origin") == origin and g.get("key")]
                if not missing_keys:
                    skipped += 1; details.append(i18n.t('u1.no_source_gaps', mod=mod_name, source_lang=source_lang))
                    continue
                sparse = self._write_missing_source_subset(Path(loc), source_lang, missing_keys, mod_name)
                if not sparse:
                    skipped += 1; details.append(i18n.t('u1.missing_source_failed', mod=mod_name))
                    continue
                input_path = sparse
            if target_kind == "chinese":
                new_item, msg = self._append_chinese_queue(input_path, mod_name + ("（不足分）" if missing_only else ""))
            else:
                before = len(self.queue_items)
                # Preserve the Chinese-basis item's target language when transferring.
                self._append_queue(input_path, target_lang=_item_target_lang(item))
                new_item = self.queue_items[-1] if len(self.queue_items) > before else None
                msg = ""
            if not new_item:
                skipped += 1; details.append(f"{mod_name}: {msg or i18n.t('u1.queue_add_failed')}")
                continue
            new_item["mod_name"] = mod_name + ("（不足分）" if missing_only else "")
            new_item["mod_root"] = str(mod_root or Path(loc).parent)
            new_item["mod_localization"] = str(loc)
            for key in ("external_translation_mod","external_translation_path","external_translation_localization","external_gap_keys"):
                if item.get(key):
                    new_item[key] = item.get(key)
            if missing_only:
                new_item["missing_only"] = True
                new_item["missing_source_lang"] = source_lang
                new_item["missing_keys"] = list(missing_keys)
            added += 1
        self._refresh_queue_tree(); self._refresh_chinese_queue_tree()
        self.save_session(active=False)
        if added:
            target_label = i18n.t('u1.normal_translation') if queue_kind == "chinese" else i18n.t('u1.chinese_translation')
            mode = i18n.t("u1.transfer_missing", target_queue=target_label, added=added, skipped=skipped) if missing_only else i18n.t("u1.transfer_selected", target_queue=target_label, added=added, skipped=skipped)
            text = mode
        else:
            text = i18n.t('u1.no_queue_items_added', skipped=skipped)
        if details:
            text += "\n\n" + "\n".join(details[:8])
        messagebox.showinfo(APP_NAME, text)

    def _merge_missing_only_output(self, item, target_loc: Path, target_root: Path, confirm=True, notify=True):
        """Merge sparse output for the item's language, preserving the legacy Japanese path."""
        target_lang = _overwrite_target_lang(self, item)
        problem = _overwrite_language_problem(self, item, external=False)
        if problem:
            return False, problem
        external = bool((item.get("mod_root") and
                         Path(target_root).resolve() != Path(item["mod_root"]).resolve()) or
                        (item.get("external_translation_path") and
                         Path(target_root).resolve() == Path(item["external_translation_path"]).resolve()))
        problem = _overwrite_language_problem(self, item, external=external, destination=target_root)
        if problem:
            return False, problem
        out_root = Path(item.get("output", ""))
        generated = _generated_language_files(out_root, target_lang)
        if not generated:
            return False, i18n.t('u1.no_japanese_yaml') if target_lang == core.DEFAULT_TARGET_LANG else i18n.t('u1.no_target_yaml', target_name=i18n.t('lang.' + target_lang))
        translations = {}
        for fp in generated:
            try:
                lang, entries, _ = core.parse_localization_file(fp)
                if lang == target_lang:
                    translations.update(entries)
            except Exception:
                continue
        wanted = {k for k in item.get("missing_keys", []) if k}
        patch_values = {k: v for k, v in translations.items() if not wanted or k in wanted}
        if not patch_values:
            return False, i18n.t('u1.no_missing_results')
        target_loc = Path(target_loc); target_root = Path(target_root)
        patch_file = target_loc / core.remap_rel_dir(Path(), target_lang) / core.rename_for_target(Path("paradox_localization_translator_missing_l_japanese.yml"), target_lang, "japanese")
        if confirm:
            warning = (i18n.t('u1.confirm_missing_overwrite', count=len(patch_values), target=target_root)
                       if target_lang == core.DEFAULT_TARGET_LANG else
                       i18n.t('u1.confirm_target_missing_overwrite', count=len(patch_values), target=target_root,
                              target_name=i18n.t('lang.' + target_lang)))
            if not messagebox.askyesno(i18n.t('u1.overwrite_missing'), warning, icon="warning"):
                return False,i18n.t("p0.reason.cancelled")
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root, backup_meta = self._create_full_localization_snapshot(
            target_root, "不足分上書き", category="上書き", source_mod_name=item.get("mod_name", ""),
            state_label=i18n.t('u1.before_missing_overwrite'), stamp=stamp, target_lang=target_lang
        )
        _record_written_target(backup_root, backup_meta, target_lang)
        try:
            # Existing Japanese keys are updated in place. Truly absent keys are
            # collected in the dedicated patch file, so unrelated files are never replaced.
            existing_key_file = {}
            for fp in _generated_language_files(target_loc, target_lang):
                try:
                    _, entries, _ = core.parse_localization_file(fp)
                    for key in entries:
                        existing_key_file.setdefault(key, fp)
                except Exception:
                    continue
            backed = set(); updated = 0; added_values = {}
            for key, value in patch_values.items():
                target = existing_key_file.get(key)
                if target and target_lang != core.DEFAULT_TARGET_LANG:
                    continue
                if target:
                    if target not in backed and target.exists():
                        try:
                            rel = target.relative_to(target_root)
                        except ValueError:
                            rel = Path(target.name)
                        bdst = backup_root / rel
                        bdst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(target, bdst); backed.add(target)
                    if core.update_localization_value(target, key, value):
                        updated += 1
                else:
                    added_values[key] = value
            if added_values:
                patch_entries = {}
                if patch_file.exists():
                    try:
                        _, patch_entries, _ = core.parse_localization_file(patch_file)
                    except Exception:
                        patch_entries = {}
                    if patch_file not in backed:
                        try:
                            rel = patch_file.relative_to(target_root)
                        except ValueError:
                            rel = Path(patch_file.name)
                        bdst = backup_root / rel
                        bdst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(patch_file, bdst); backed.add(patch_file)
                patch_entries.update(added_values)
                patch_file.parent.mkdir(parents=True, exist_ok=True)
                lines = [f"l_{target_lang}:"]
                for key in sorted(patch_entries):
                    lines.append(f' {key}: "{core.escape_localization_value(patch_entries[key])}"')
                patch_file.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")
            source_mod_root = Path(item.get("mod_root", ""))
            validation_text = i18n.t('u1.validation_unknown')
            if source_mod_root.is_dir():
                if target_root.resolve() == source_mod_root.resolve():
                    post = core.analyze_mod_translation_status(source_mod_root, target_lang=target_lang)
                    validation_text = i18n.t('u1.validation_complete') if not post.get("gap_count") else i18n.t('u1.text_has_gaps', reason=post.get('gap_reason') or core.gap_reason_text(post.get('candidates', [])))
                else:
                    post = core.analyze_external_translation_coverage(source_mod_root, target_root, target_lang=target_lang)
                    validation_text = i18n.t('u1.validation_complete') if post.get("complete") else i18n.t('u1.text_has_gaps', reason=post.get('gap_reason',i18n.t('u1.translation_gaps')))
            if notify:
                messagebox.showinfo(APP_NAME, i18n.t('u1.missing_overwrite_done', updated=updated, added=len(added_values), files=len(backed), validation=validation_text))
            return True, i18n.t('u1.missing_overwrite_summary', updated=updated, added=len(added_values), validation=validation_text)
        except Exception as exc:
            record_error(i18n.t('u1.overwrite_error'), exc, str(target_root))
            if notify:
                messagebox.showerror(APP_NAME, i18n.t('u1.missing_overwrite_failed', error=exc))
            return False, str(exc)

    def _source_gap_notice_for_items(self, items):
        """Return a completion notice when English/Chinese source files disagree."""
        notices=[]
        for item in items or []:
            loc, _ = self._infer_mod_target_for_item(item)
            root = loc if loc and Path(loc).is_dir() else Path(item.get("input", ""))
            if root.is_file():
                root = root.parent
            # Direct Chinese/English folder selection may point below localization.
            # Walk upward so the sibling source language can still be compared.
            for candidate in [root, *root.parents]:
                if core.is_localization_dir_name(candidate.name):
                    root = candidate
                    break
            if not root.exists():
                continue
            try:
                result = core.analyze_source_language_gaps(root)
            except Exception:
                continue
            if result.get("has_gaps"):
                name=item.get("mod_name") or Path(item.get("input", "")).name or i18n.t('u6.item')
                notices.append(f"{name}: {core.source_language_gap_reason_text(result)}")
        if not notices:
            return ""
        text = i18n.t('u6.gaps_in_source_text_english_and', notices="\n".join(notices[:10]))
        if len(notices) > 10:
            text += i18n.t('u6.and_more', value=len(notices) - 10)
        return text

    def _generated_japanese_files(self, output_root: Path):
        return _generated_language_files(output_root, "japanese")

    def _source_overwrite_layout(self, item):
        """Return the direct-source overwrite layout without writing any files."""
        loc_root, mod_root = self._infer_mod_target_for_item(item)
        if not loc_root or not mod_root:
            return None, None, []
        loc_root=Path(loc_root); mod_root=Path(mod_root)
        out_root = Path(item.get("output", ""))
        input_path = Path(item.get("input", ""))
        target_base = loc_root if input_path.is_dir() and core.is_localization_dir_name(input_path.name) else mod_root
        mappings=[]
        target_lang=_overwrite_target_lang(self, item)
        for src in _generated_language_files(out_root, target_lang):
            try:
                rel=src.relative_to(out_root)
            except ValueError:
                continue
            safe_parent = core.remap_rel_dir(rel.parent, target_lang)
            safe_name = core.rename_for_target(src, target_lang, target_lang)
            safe_rel = safe_parent / safe_name
            mappings.append((src,target_base / safe_rel,safe_rel))
        return loc_root, mod_root, mappings

    def _source_overwrite_path_conflicts(self, item):
        """Find enabled later Mods that mask files produced by a source overwrite."""
        loc_root, mod_root, mappings = self._source_overwrite_layout(item)
        if not mod_root or not mappings:
            return []
        relative=[]
        for _src,_dst,safe_rel in mappings:
            rel=safe_rel
            # When target_base is the Mod root, normalize to a path below localization.
            if rel.parts and core.is_localization_dir_name(rel.parts[0]):
                rel=Path(*rel.parts[1:])
            relative.append(rel)
        return core.find_later_localization_path_conflicts(mod_root, relative)

    def _preferred_later_translation_conflict(self, item):
        conflicts=self._source_overwrite_path_conflicts(item)
        target_lang = _overwrite_target_lang(self, item)
        if target_lang == "english":
            return None, conflicts
        if target_lang != core.DEFAULT_TARGET_LANG:
            linked = item.get("external_translation_path")
            preferred = next((row for row in reversed(conflicts)
                              if linked and row.get("effective") and row.get("path")
                              and Path(row["path"]).resolve() == Path(linked).resolve()), None)
            return preferred, conflicts
        preferred=next((row for row in reversed(conflicts)
                        if row.get("effective") and row.get("stale_translation_candidate")),None)
        return preferred,conflicts

    def _perform_full_translation_mod_overwrite(self, item, conflict, confirm=True, notify=True):
        """Write target-language output to a linked later translation Mod."""
        target_lang = _overwrite_target_lang(self, item)
        problem = _overwrite_language_problem(self, item, external=True)
        if problem:
            return False, problem
        ext_root=Path(conflict.get("path", "")); ext_loc=Path(conflict.get("localization", ""))
        problem = _overwrite_language_problem(self, item, external=True, destination=ext_root)
        if problem:
            return False, problem
        out_root=Path(item.get("output", ""))
        generated=_generated_language_files(out_root, target_lang)
        if not ext_root.is_dir() or not ext_loc.is_dir():
            return False,i18n.t('u6.cannot_identify_the_later_translation_mod', target_name=i18n.t("lang." + target_lang))
        mappings=[]
        for src in generated:
            try: rel=src.relative_to(out_root)
            except ValueError: continue
            safe_parent=core.remap_rel_dir(rel.parent,target_lang)
            safe_name=core.rename_for_target(src,target_lang,target_lang)
            safe_rel=safe_parent / safe_name
            mappings.append((src,ext_loc / safe_rel,safe_rel))
        if not mappings:
            return False,i18n.t('u6.no_completed_japanese_yaml_files_to', target_name=i18n.t("lang." + target_lang))
        ext_name=conflict.get("mod") or ext_root.name
        src_name=item.get("mod_name") or Path(item.get("mod_root", "")).name
        shared=int(conflict.get("shared_keys",0) or 0)
        source_only=int(conflict.get("source_only_keys",0) or 0)
        paths="\n".join(i18n.t('u6.detail_5', path=path) for path in conflict.get("relative_paths",[])[:8])
        if confirm:
            warning=(
                i18n.t('u6.a_later_translation_mod_overrides_same', src_name=src_name, value=int(conflict.get('source_position', 0)) + 1, ext_name=ext_name, value_2=int(conflict.get('position', 0)) + 1, value_3=int(conflict.get('path_match_count', 0)), paths=paths, shared=shared, source_only=source_only, target_name=i18n.t("lang." + target_lang)))
            if target_lang != core.DEFAULT_TARGET_LANG:
                warning += "\n\n" + i18n.t('u6.preserve_target_values', target_name=i18n.t('lang.' + target_lang))
            if not messagebox.askyesno(i18n.t('u6.warning_overwrite_later_translation_mod', target_name=i18n.t("lang." + target_lang)),warning,icon="warning"):
                return False,i18n.t("p0.reason.cancelled")
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root,_meta=self._create_full_localization_snapshot(
            ext_root,i18n.t('u6.same_name_file_conflict_legacy_translation', target_name=i18n.t("lang." + target_lang)),category="上書き",source_mod_name=src_name,
            state_label=i18n.t('u6.before_updating_same_name_files_in', target_name=i18n.t("lang." + target_lang)),stamp=stamp, target_lang=target_lang)
        _record_written_target(backup_root, _meta, target_lang)
        existing_keys = _existing_target_keys(ext_loc, target_lang) if target_lang != core.DEFAULT_TARGET_LANG else set()
        copied=0; replaced=0
        try:
            for src,dst,_rel in mappings:
                if dst.exists(): replaced += 1
                dst.parent.mkdir(parents=True,exist_ok=True)
                copied += int(_copy_target_output(src, dst, target_lang, existing_keys))
            coverage=core.analyze_external_translation_coverage(Path(item.get("mod_root") or ext_root),ext_root, target_lang=target_lang)
            validation=(i18n.t('u6.post_overwrite_check_no_gaps') if coverage.get("complete") else
                        i18n.t('u6.gaps_remain_after_overwrite', gap_reason=coverage.get('gap_reason', i18n.t('u6.translations_are_missing'))))
            self._invalidate_mod_status_cache_paths([ext_root])
            reason=(i18n.t('u6.updated_later_translation_mod_replaced_shared', copied=copied, replaced=replaced, shared=shared, source_only=source_only, validation=validation, target_name=i18n.t("lang." + target_lang)))
            if target_lang != core.DEFAULT_TARGET_LANG:
                reason = i18n.t('u6.target_overwrite_preserved', copied=copied, backup_root=backup_root,
                                validation=validation, target_name=i18n.t('lang.' + target_lang))
            if notify:
                text = (i18n.t('u6.updated_later_translation_mod_target_files', ext_name=ext_name, copied=copied, replaced=replaced, backup_root=backup_root, validation=validation, target_name=i18n.t("lang." + target_lang))
                        if target_lang == core.DEFAULT_TARGET_LANG else reason)
                messagebox.showinfo(APP_NAME, text)
            return True,reason
        except Exception as exc:
            record_error(i18n.t('u6.same_name_file_conflict_translation_mod', target_name=i18n.t("lang." + target_lang)),exc,str(ext_root))
            if notify:
                messagebox.showerror(APP_NAME,i18n.t('u6.could_not_overwrite_later_translation_mod', exc=exc, backup_root=backup_root, target_name=i18n.t("lang." + target_lang)))
            return False,str(exc)

    def _queue_item_is_completed(self, item):
        status=str(item.get("status", ""))
        return status.startswith("完了") or status == "上書き済み"

    def _selected_normal_queue_entries(self):
        if not hasattr(self,"queue_tree"):
            return []
        out=[]
        for iid in self.queue_tree.selection():
            try:
                idx=int(iid)
            except Exception:
                continue
            if 0 <= idx < len(self.queue_items):
                out.append((idx,self.queue_items[idx]))
        return out

    def _selected_chinese_queue_entries(self):
        if not hasattr(self,"chinese_queue_tree"):
            return []
        out=[]
        for iid in self.chinese_queue_tree.selection():
            try:
                idx=int(str(iid).split("_",1)[1])
            except Exception:
                continue
            if 0 <= idx < len(self.chinese_queue_items):
                out.append((idx,self.chinese_queue_items[idx]))
        return out

    def _set_overwritten_status(self, item):
        item["status"]=status_value("overwritten")

    def _invalidate_status_cache_for_item(self, item):
        """Drop cached translation-status rows touched by an overwrite.

        This prevents a pre-overwrite result from being restored on the next
        launch before a fresh status scan has a chance to run.
        """
        roots=[]
        for raw in (item.get("mod_root"), item.get("external_translation_path")):
            if raw:
                try: roots.append(str(Path(raw).expanduser().resolve()))
                except Exception: roots.append(str(raw))
        if not roots:
            return
        with self.mod_status_cache_lock:
            for target_lang in ["japanese", *self.mod_status_cache.get("languages", {})]:
                items=_relation_language_items(self.mod_status_cache, "items", target_lang, create=True)
                for key in roots: items.pop(key,None)
            self.mod_status_cache["version"]=MOD_STATUS_CACHE_VERSION
            self.mod_status_cache["updated_at"]=datetime.now().isoformat(timespec="seconds")
            self.mod_status_cache["updated_at_ns"]=time.time_ns()
            core.save_json(MOD_STATUS_CACHE_PATH,self.mod_status_cache)

    def _perform_external_gap_overwrite(self, item, confirm=True, notify=True):
        """Write translated gap keys to the item's linked target-language Mod."""
        target_lang = _overwrite_target_lang(self, item)
        problem = _overwrite_language_problem(self, item, external=True)
        if problem:
            return False, problem
        ext_root = Path(item.get("external_translation_path", ""))
        problem = _overwrite_language_problem(self, item, external=True, destination=ext_root)
        if problem:
            return False, problem
        ext_loc = Path(item.get("external_translation_localization", ""))
        gap_keys = {k for k in item.get("external_gap_keys", []) if k}
        out_root = Path(item.get("output", ""))
        if not ext_root.is_dir() or not ext_loc.is_dir():
            return False,i18n.t('u6.cannot_identify_the_translation_mod_location', target_name=i18n.t("lang." + target_lang))
        if not gap_keys:
            return False,i18n.t("p0.reason.no_gap_info")
        generated = _generated_language_files(out_root, target_lang)
        translations = {}
        for fp in generated:
            try:
                lang, entries, _ = core.parse_localization_file(fp)
                if lang == target_lang:
                    translations.update(entries)
            except Exception:
                continue
        patch_values = {k: translations[k] for k in gap_keys if k in translations}
        if not patch_values:
            return False,i18n.t("p0.reason.no_gap_translation")

        ext_name = item.get("external_translation_mod") or ext_root.name
        src_name = item.get("mod_name") or Path(item.get("mod_root", "")).name
        if confirm:
            warning=(
                i18n.t('u6.write_only_missing_translations_to_another', src_name=src_name, ext_name=ext_name, ext_root=ext_root, patch_values_count=len(patch_values), target_name=i18n.t("lang." + target_lang)))
            if not messagebox.askyesno(i18n.t('u6.warning_overwrite_differences_to_translation_mod', target_name=i18n.t("lang." + target_lang)), warning, icon="warning"):
                return False,i18n.t("p0.reason.cancelled")
            if not messagebox.askyesno(i18n.t('u6.final_confirmation'), i18n.t('u6.write_only_missing_translations_to_the', target_name=i18n.t("lang." + target_lang)), icon="warning"):
                return False,i18n.t("p0.reason.cancelled")

        existing_key_file = {}
        for fp in _generated_language_files(ext_loc, target_lang):
            try:
                _, entries, _ = core.parse_localization_file(fp)
                for key in entries:
                    existing_key_file.setdefault(key, fp)
            except Exception:
                continue
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root, backup_meta = self._create_full_localization_snapshot(
            ext_root, i18n.t('u6.translation_mod_difference_overwrite', target_name=i18n.t("lang." + target_lang)), category="上書き", source_mod_name=src_name,
            state_label=i18n.t('u6.source_text_before_difference_overwrite_to', target_name=i18n.t("lang." + target_lang)), stamp=stamp, target_lang=target_lang
        )
        _record_written_target(backup_root, backup_meta, target_lang)
        backed=set(); updated=0; added=0
        patch_file = ext_loc / core.remap_rel_dir(Path(), target_lang) / core.rename_for_target(Path("paradox_localization_translator_missing_l_japanese.yml"), target_lang, "japanese")
        try:
            for key, value in patch_values.items():
                target = existing_key_file.get(key)
                if not target or target_lang != core.DEFAULT_TARGET_LANG:
                    continue
                if target not in backed and target.exists():
                    rel=target.relative_to(ext_root)
                    bdst=backup_root / rel; bdst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(target,bdst); backed.add(target)
                if core.update_localization_value(target, key, value):
                    updated += 1
            missing = [(k,v) for k,v in patch_values.items() if k not in existing_key_file]
            if missing:
                if patch_file.exists() and patch_file not in backed:
                    rel=patch_file.relative_to(ext_root)
                    bdst=backup_root / rel; bdst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(patch_file,bdst); backed.add(patch_file)
                patch_file.parent.mkdir(parents=True,exist_ok=True)
                if patch_file.exists():
                    text=core.read_localization_text(patch_file)
                    if not text.endswith("\n"): text += "\n"
                else:
                    text=f"l_{target_lang}:\n"
                for key,value in missing:
                    escaped_value = core.escape_localization_value(value)
                    text += f' {key}: "{escaped_value}"\n'
                    added += 1
                patch_file.write_text("\ufeff"+text.lstrip("\ufeff"),encoding="utf-8")
            _, source_mod_root = self._infer_mod_target_for_item(item)
            validation_text = i18n.t('u6.post_overwrite_check_cannot_identify_assessment')
            validation_warning = False
            if source_mod_root and Path(source_mod_root).is_dir():
                coverage = core.analyze_external_translation_coverage(source_mod_root, ext_root, target_lang=target_lang)
                if coverage.get("complete"):
                    validation_text = i18n.t('u6.post_overwrite_check_no_gaps')
                else:
                    validation_warning = True
                    validation_text = i18n.t('u6.the_text_itself_has_gaps', gap_reason=coverage.get('gap_reason', i18n.t('u6.translations_are_missing')))
            if notify:
                messagebox.showinfo(APP_NAME,
                    i18n.t('u6.applied_differences_to_translation_mod_existing', updated=updated, added=added, backed_count=len(backed), value=backup_root if backed else i18n.t('u6.no_pre_change_files'), validation_text=validation_text, target_name=i18n.t("lang." + target_lang)))
            reason=i18n.t('u6.existing_keys_updated_new_keys_added', updated=updated, added=added, validation_text=validation_text)
            return True,reason
        except Exception as e:
            record_error(i18n.t('u6.translation_mod_difference_overwrite', target_name=i18n.t("lang." + target_lang)), e, str(ext_root))
            if notify:
                messagebox.showerror(APP_NAME, i18n.t('u6.error_overwriting_differences_to_translation_mod', value=e, backup_root=backup_root, target_name=i18n.t("lang." + target_lang)))
            return False,str(e)

    def _merge_translation_gaps_into_external_mod(self, item):
        ok,_=self._perform_external_gap_overwrite(item,confirm=True,notify=True)
        if ok:
            self._set_overwritten_status(item)
            self._invalidate_status_cache_for_item(item)
            self._refresh_queue_tree()
            self._refresh_chinese_queue_tree()
            self._save_workspace_state("overwrite_completed")
        return ok

    def _perform_source_mod_overwrite(self, item, confirm=True, notify=True):
        target_lang = _overwrite_target_lang(self, item)
        problem = _overwrite_language_problem(self, item, external=False)
        if problem:
            return False, problem
        loc_root, mod_root, mappings = self._source_overwrite_layout(item)
        problem = _overwrite_language_problem(self, item, destination=mod_root)
        if problem:
            return False, problem
        if not loc_root:
            return False,i18n.t('u6.cannot_identify_the_source_mod_s')
        if not mappings:
            return False,i18n.t('u6.no_completed_yaml_files_in_the', target_name=i18n.t("lang." + _overwrite_target_lang(self, item)))

        existing=sum(1 for _,dst,_ in mappings if dst.exists())
        mod_name=item.get("mod_name") or Path(mod_root).name
        if confirm:
            warning=(
                i18n.t('u6.write_translated_files_directly_to_the', mod_name=mod_name, mod_root=mod_root, mappings_count=len(mappings), existing=existing, target_name=i18n.t("lang." + _overwrite_target_lang(self, item))))
            if target_lang != core.DEFAULT_TARGET_LANG:
                warning += "\n\n" + i18n.t('u6.preserve_target_values', target_name=i18n.t('lang.' + target_lang))
            if not messagebox.askyesno(i18n.t('u6.warning_overwrite_mod_directly'), warning, icon="warning"):
                return False,i18n.t("p0.reason.cancelled")
            if not messagebox.askyesno(i18n.t('u6.final_confirmation'), i18n.t('u6.write_to_the_source_mod_this'), icon="warning"):
                return False,i18n.t("p0.reason.cancelled")

        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        backup_root, backup_meta = self._create_full_localization_snapshot(
            mod_root, i18n.t('u6.source_mod_overwrite'), category="上書き", source_mod_name=mod_name,
            state_label=i18n.t('u6.source_text_before_direct_source_mod'), stamp=stamp, target_lang=_overwrite_target_lang(self, item)
        )
        _record_written_target(backup_root, backup_meta, target_lang)
        existing_keys = _existing_target_keys(loc_root, target_lang) if target_lang != core.DEFAULT_TARGET_LANG else set()
        copied=0; backed=0
        try:
            for src,dst,rel in mappings:
                if dst.exists():
                    bdst=backup_root / rel
                    bdst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(dst,bdst); backed += 1
                dst.parent.mkdir(parents=True,exist_ok=True)
                copied += int(_copy_target_output(src, dst, target_lang, existing_keys))
            if (post := core.analyze_mod_translation_status(mod_root, target_lang=target_lang)).get("gap_count", 0):
                validation_text = i18n.t('u6.the_text_itself_has_gaps_2', value=post.get('gap_reason') or core.gap_reason_text(post.get('candidates', [])))
            else:
                validation_text = i18n.t('u6.post_overwrite_check_no_gaps')
            reason = i18n.t('u6.files_written_backups', copied=copied, backed=backed, validation_text=validation_text)
            if target_lang != core.DEFAULT_TARGET_LANG:
                reason = i18n.t('u6.target_overwrite_preserved', copied=copied, backup_root=backup_root,
                                validation=validation_text, target_name=i18n.t('lang.' + target_lang))
            if notify:
                text = (i18n.t('u6.overwrote_mod_with_translated_files_files', copied=copied, backed=backed, value=backup_root if backed else i18n.t('u6.no_existing_files'), validation_text=validation_text, target_name=i18n.t("lang." + _overwrite_target_lang(self, item)))
                        if target_lang == core.DEFAULT_TARGET_LANG else reason)
                messagebox.showinfo(APP_NAME, text)
            return True, reason
        except Exception as e:
            record_error(i18n.t('u6.direct_mod_overwrite'), e, str(mod_root))
            if notify:
                messagebox.showerror(APP_NAME, i18n.t('u6.error_overwriting_files_backup_location', value=e, backup_root=backup_root))
            return False,str(e)

    def _overwrite_single_item_interactive(self, item, prefer_external=True):
        problem = _overwrite_language_problem(self, item)
        if problem:
            messagebox.showinfo(APP_NAME, problem); return False
        if self.single_overwrite_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u6.an_overwrite_is_already_running_in')); return False
        if not self._queue_item_is_completed(item):
            messagebox.showinfo(APP_NAME,i18n.t('u6.only_completed_translation_items_can_be')); return False
        use_external=False; conflict_target=None
        if prefer_external and item.get('external_translation_path') and _overwrite_target_lang(self, item) == "english":
            messagebox.showinfo(APP_NAME, i18n.t('u6.english_external_overwrite_unavailable'))
        if prefer_external and _overwrite_target_lang(self, item) != "english":
            preferred,conflicts=self._preferred_later_translation_conflict(item)
            if preferred:
                ext_name=preferred.get('mod') or Path(preferred.get('path','')).name
                paths='\n'.join(i18n.t('u6.detail_6', value=p) for p in preferred.get('relative_paths',[])[:6])
                choice=messagebox.askyesnocancel(
                    i18n.t('u6.same_name_localization_file_conflict'),
                    i18n.t('u6.saving_to_the_source_mod_will', ext_name=ext_name, paths=paths, shared_keys=preferred.get('shared_keys', 0), source_only_keys=preferred.get('source_only_keys', 0), target_name=i18n.t("lang." + _overwrite_target_lang(self, item))),icon='warning')
                if choice is None: return False
                if choice: conflict_target=preferred
            elif item.get('external_translation_path') and _overwrite_target_lang(self, item) != "english":
                ext_name=item.get('external_translation_mod','') or Path(item.get('external_translation_path','')).name
                choice=messagebox.askyesnocancel(i18n.t('u6.confirm_overwrite_destination'),i18n.t('u6.translation_mod_found_yes_overwrite_differences', ext_name=ext_name, target_name=i18n.t("lang." + _overwrite_target_lang(self, item))),icon='question')
                if choice is None: return False
                use_external=bool(choice)
            elif conflicts:
                effective=next((row for row in conflicts if row.get('effective')),conflicts[-1])
                if not messagebox.askyesno(
                    i18n.t('u6.warning_same_name_file_conflict'),
                    i18n.t('u6.later_mod_has_the_same_localization', value=effective.get('mod') or Path(effective.get('path', '')).name),
                    icon='warning'):
                    return False
        target_label=((conflict_target.get('mod') or Path(conflict_target.get('path','')).name) if conflict_target
                      else (item.get('external_translation_mod') or i18n.t('u6.translation_mod', target_name=i18n.t("lang." + _overwrite_target_lang(self, item)))) if use_external
                      else (item.get('mod_name') or i18n.t('u6.source_mod_4')))
        if not messagebox.askyesno(i18n.t('u6.warning_overwrite_mod'),i18n.t('u6.target_existing_localization_is_backed_up', target_label=target_label),icon='warning'):
            return False
        if not messagebox.askyesno(i18n.t('u6.final_confirmation'),i18n.t('u6.write_these_files_this_changes_localization', value=i18n.t('lang.' + _overwrite_target_lang(self, item))),icon='warning'):
            return False
        self.progress_text.set(i18n.t('u6.overwriting_in_the_background', target_label=target_label))
        def work():
            try:
                if item.get('missing_only'):
                    if conflict_target:
                        target_root=Path(conflict_target.get('path','')); target_loc=Path(conflict_target.get('localization',''))
                    elif use_external:
                        target_root=Path(item.get('external_translation_path','')); target_loc=Path(item.get('external_translation_localization',''))
                    else:
                        target_loc,target_root=self._infer_mod_target_for_item(item)
                    if not target_loc or not target_root: ok,reason=False,i18n.t('u6.cannot_identify_the_destination_for_missing')
                    else: ok,reason=self._merge_missing_only_output(item,Path(target_loc),Path(target_root),confirm=False,notify=False)
                elif conflict_target:
                    ok,reason=self._perform_full_translation_mod_overwrite(item,conflict_target,confirm=False,notify=False)
                elif use_external:
                    ok,reason=self._perform_external_gap_overwrite(item,confirm=False,notify=False)
                else:
                    ok,reason=self._perform_source_mod_overwrite(item,confirm=False,notify=False)
                self.events.put(('single_overwrite_done',(item,ok,reason,target_label)))
            except Exception as exc:
                record_error(i18n.t('u6.background_single_overwrite'),exc,target_label); self.events.put(('single_overwrite_done',(item,False,str(exc),target_label)))
        self.single_overwrite_thread=threading.Thread(target=work,daemon=True,name='single-overwrite'); self.single_overwrite_thread.start()
        self._refresh_operation_states()
        return True

    def _apply_single_overwrite_done(self, item, ok, reason, target_label):
        self.single_overwrite_thread=None
        if ok:
            self._set_overwritten_status(item); self._invalidate_status_cache_for_item(item)
            self._refresh_queue_tree(); self._refresh_chinese_queue_tree(); self._save_workspace_state('overwrite_completed')
            self.progress_text.set(i18n.t('u6.overwrite_complete', target_label=target_label))
            self._refresh_backup_restore_entries()
            if not self._closing: messagebox.showinfo(APP_NAME,i18n.t('u6.overwrite_complete_target', target_label=target_label, reason=reason))
        else:
            self.progress_text.set(i18n.t('u6.could_not_overwrite'))
            if reason != i18n.t("p0.reason.cancelled") and not self._closing: messagebox.showinfo(APP_NAME,i18n.t('u6.could_not_overwrite_2', reason=reason))

    def _bulk_overwrite_queue_entries(self, entries, queue_kind="normal"):
        if self.bulk_overwrite_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u6.a_bulk_overwrite_is_already_running')); return
        eligible=[]; skipped_unfinished=0
        for idx,item in entries:
            if self._queue_item_is_completed(item): eligible.append((idx,item))
            else: skipped_unfinished+=1
        if not eligible:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_completed_translation_items_selected')); return
        conflict_targets={}
        for _idx,item in eligible:
            try:
                preferred,_conflicts=self._preferred_later_translation_conflict(item)
                if preferred and _overwrite_target_lang(self, item) != "english": conflict_targets[id(item)]=preferred
            except Exception as exc:
                record_error(i18n.t('u6.same_name_file_conflict_check_before'),exc,item.get('mod_name',''))
        target_name = ", ".join(dict.fromkeys(i18n.t("lang." + _overwrite_target_lang(self, item))
                                             for _, item in eligible if _overwrite_target_lang(self, item) != "english"))
        has_external=any((item.get('external_translation_path') and _overwrite_target_lang(self, item) != "english")
                         or id(item) in conflict_targets for _,item in eligible); policy='source'
        if has_external:
            choice=messagebox.askyesnocancel(i18n.t('u6.bulk_overwrite_destination_policy'),
                i18n.t('u6.bulk_overwrite_completed_items_yes_prefer', eligible_count=len(eligible), target_name=target_name),icon='question')
            if choice is None: return
            policy='external' if choice else 'source'
        policy_text=i18n.t('u6.prefer_existing_translation_mods', target_name=target_name) if policy=='external' else i18n.t('u6.write_everything_to_source_mods')
        relationship_warning=i18n.t('u6.for_items_written_to_translation_mods', target_name=target_name) if policy=='external' else ''
        if any(item.get('external_translation_path') and _overwrite_target_lang(self, item) == "english" for _, item in eligible):
            relationship_warning += "\n" + i18n.t('u6.english_external_overwrite_unavailable')
        if conflict_targets:
            relationship_warning += i18n.t('u6.items_hidden_by_later_mods_same', conflict_targets_count=len(conflict_targets))
        if not messagebox.askyesno(i18n.t('u6.confirm_bulk_overwrite'),
            i18n.t('u6.targets_policy_skipped_as_unfinished_each', eligible_count=len(eligible), policy_text=policy_text, skipped_unfinished=skipped_unfinished, relationship_warning=relationship_warning),icon='warning'):
            return
        self.progress_text.set(i18n.t('u6.bulk_overwrite_in_the_background_0', eligible_count=len(eligible)))
        def work():
            success=0; skipped=skipped_unfinished; failed=0; details=[]
            for pos,(_,item) in enumerate(eligible,1):
                name=item.get('mod_name') or Path(item.get('input','')).name or i18n.t('u6.item')
                self.events.put(('bulk_overwrite_progress',(pos,len(eligible),name)))
                try:
                    problem = _overwrite_language_problem(self, item)
                    if problem:
                        skipped += 1; details.append(i18n.t("u6.skipped", name=name, reason=problem)); continue
                    conflict_target=conflict_targets.get(id(item)) if policy=='external' else None
                    if item.get('missing_only'):
                        if conflict_target:
                            target_root=Path(conflict_target.get('path','')); target_loc=Path(conflict_target.get('localization',''))
                        elif policy=='external' and item.get('external_translation_path') and _overwrite_target_lang(self, item) != 'english':
                            target_root=Path(item.get('external_translation_path','')); target_loc=Path(item.get('external_translation_localization',''))
                        else:
                            target_loc,target_root=self._infer_mod_target_for_item(item)
                        if not target_loc or not target_root: ok,reason=False,i18n.t('u6.cannot_identify_the_destination_for_missing')
                        else: ok,reason=self._merge_missing_only_output(item,Path(target_loc),Path(target_root),confirm=False,notify=False)
                    elif conflict_target:
                        ok,reason=self._perform_full_translation_mod_overwrite(item,conflict_target,confirm=False,notify=False)
                    elif policy=='external' and item.get('external_translation_path') and _overwrite_target_lang(self, item) != "english":
                        ok,reason=self._perform_external_gap_overwrite(item,confirm=False,notify=False)
                        if not ok and reason in {i18n.t("p0.reason.no_gap_info"),i18n.t("p0.reason.no_gap_translation")}:
                            skipped+=1; details.append(i18n.t('u6.skipped', name=name, reason=reason)); continue
                    else:
                        ok,reason=self._perform_source_mod_overwrite(item,confirm=False,notify=False)
                    if ok:
                        self._set_overwritten_status(item); self._invalidate_status_cache_for_item(item); success+=1
                        if '⚠' in str(reason): details.append(f'{name}: {reason}')
                    else:
                        failed+=1; details.append(i18n.t('u6.failed', name=name, reason=reason))
                except Exception as exc:
                    failed+=1; details.append(i18n.t('u6.failed_2', name=name, exc=exc)); record_error(i18n.t('u6.bulk_overwrite'),exc,name)
            self.events.put(('bulk_overwrite_done',(success,skipped,failed,details,queue_kind)))
        self._bulk_overwrite_queue_kind=queue_kind
        self.bulk_overwrite_thread=threading.Thread(target=work,daemon=True,name='bulk-overwrite'); self.bulk_overwrite_thread.start()
        self._refresh_operation_states()

    def _apply_bulk_overwrite_done(self, success, skipped, failed, details, queue_kind):
        self.bulk_overwrite_thread=None
        self._bulk_overwrite_queue_kind=None
        self._refresh_queue_tree(); self._refresh_chinese_queue_tree(); self._save_workspace_state('bulk_overwrite_completed')
        if self.queue_items and all(self._queue_item_is_completed(x) for x in self.queue_items): self._delete_session()
        self.progress_text.set(i18n.t('u6.bulk_overwrite_complete_succeeded_skipped_failed', success=success, skipped=skipped, failed=failed))
        summary=i18n.t('u6.bulk_overwrite_complete_succeeded_skipped_failed_2', success=success, skipped=skipped, failed=failed)
        if details:
            summary+=i18n.t('u6.details', value='\n'.join(details[:12]))
            if len(details)>12: summary+=i18n.t('u6.and_more', value=len(details) - 12)
        if not self._closing: messagebox.showinfo(APP_NAME,summary)
        self._refresh_backup_restore_entries()

    def overwrite_selected_translation_to_mod(self, item_override=None, prefer_external=True):
        if item_override is not None:
            return self._overwrite_single_item_interactive(item_override,prefer_external=prefer_external)
        entries=self._selected_normal_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,i18n.t('u6.select_items_to_overwrite_in_the'))
            return
        self._bulk_overwrite_queue_entries(entries,queue_kind="normal")

    def overwrite_selected_status_mod(self):
        result=self._selected_mod_status_result()
        if not result:
            return
        loc=str(Path(result.get("localization", "")))
        candidates=[]
        for idx,item in enumerate(self.queue_items):
            if item.get("mod_localization") == loc or item.get("input") == loc:
                candidates.append((idx,item))
        if not candidates:
            messagebox.showinfo(APP_NAME, i18n.t('u6.no_completed_translation_for_this_mod'))
            return
        idx,item=candidates[-1]
        self.overwrite_selected_translation_to_mod(item_override=item)

    def clear_mod_status_results(self):
        if not messagebox.askyesno(APP_NAME, i18n.t('u6.clear_translation_status_results_and_saved')):
            return
        self.mod_research_results=[]
        self.mod_status_search_var.set("")
        self.mod_status_search_result_var.set("")
        self._populate_mod_status_tree()
        with self.mod_status_cache_lock:
            _relation_language_items(self.mod_status_cache, "items", _current_target_lang(self), create=True).clear()
            self.mod_status_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_STATUS_CACHE_PATH,self.mod_status_cache)
        self.mod_status_summary_var.set(i18n.t('u6.research_results_0'))

    def export_mod_status_csv(self):
        if not self.mod_research_results:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_research_results_to_save'))
            return
        p=filedialog.asksaveasfilename(title=i18n.t('u6.save_translation_status_as_csv'),defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="mod_translation_status.csv")
        if not p: return
        import csv
        with open(p,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow([i18n.t('u6.status'),"Mod",i18n.t('u6.gap_count'),i18n.t('u6.result'),i18n.t('u6.location_3')])
            for r in self.mod_research_results:
                w.writerow([display_status(r),r.get("mod",""),r.get("gap_count",0),ui_status.display_message(r),r.get("path","")])
        messagebox.showinfo(APP_NAME,i18n.t('u6.csv_saved'))

    def clear_monitor_results(self):
        self.monitor_candidates=[]
        if hasattr(self,"monitor_tree"):
            for x in self.monitor_tree.get_children(): self.monitor_tree.delete(x)
        self.monitor_summary_var.set(i18n.t('u6.untranslated_candidates_0'))

    def export_monitor_csv(self):
        if not self.monitor_candidates:
            messagebox.showinfo(APP_NAME,i18n.t('u6.no_candidates_to_save'))
            return
        p=filedialog.asksaveasfilename(title=i18n.t('u6.save_untranslated_candidates_as_csv'),defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="untranslated_candidates.csv")
        if not p: return
        import csv
        with open(p,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow([i18n.t('u6.type'),i18n.t('u6.assessment'),i18n.t('u6.file'),i18n.t('u6.key'),i18n.t('u6.source_text'),i18n.t('u6.current_japanese', target_name=i18n.t("lang." + _current_target_lang(self)))])
            for c in self.monitor_candidates:
                w.writerow([c.get("kind",""),c.get("confidence",""),c.get("target_file") or c.get("source_file",""),c.get("key",""),c.get("source",""),c.get("target","")])
        messagebox.showinfo(APP_NAME,i18n.t('u6.csv_saved'))

    def _build_models_tab(self):
        t=self.tab_models

        body=ttk.Panedwindow(t, orient="horizontal")
        body.pack(fill="both", expand=True)
        left_outer=ttk.Frame(body)
        right=ttk.Frame(body)
        body.add(left_outer, weight=2)
        body.add(right, weight=3)

        # 左側は共通設定が増えたためスクロール可能にする。
        canvas=tk.Canvas(left_outer,highlightthickness=0,borderwidth=0)
        scroll=ttk.Scrollbar(left_outer,orient="vertical",command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left",fill="both",expand=True); scroll.pack(side="right",fill="y")
        left=ttk.Frame(canvas,padding=(0,0,5,0))
        win=canvas.create_window((0,0),window=left,anchor="nw")
        left.bind("<Configure>",lambda e:canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>",lambda e:canvas.itemconfigure(win,width=e.width))

        conn=ttk.LabelFrame(left,text=i18n.t('u5.llm_connection'),padding=8); conn.pack(fill="x")
        conn.columnconfigure(1,weight=1)
        ttk.Label(conn,text=i18n.t('u5.provider')).grid(row=0,column=0,sticky="w")
        pc=ttk.Combobox(conn,textvariable=self.provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=14)
        pc.grid(row=0,column=1,padx=6,sticky="ew"); pc.bind("<<ComboboxSelected>>",lambda e:self.on_provider_change())
        ttk.Label(conn,text="API URL").grid(row=1,column=0,sticky="w",pady=(6,0))
        ttk.Entry(conn,textvariable=self.url_var).grid(row=1,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Button(conn,text=i18n.t('u5.refresh_connection'),command=self.refresh_models).grid(row=2,column=0,columnspan=2,sticky="ew",pady=(6,0))
        ttk.Label(conn,textvariable=self.connection_var).grid(row=3,column=0,columnspan=2,sticky="w",pady=(7,0))
        ttk.Label(conn,text=i18n.t('u5.model')).grid(row=4,column=0,sticky="w",pady=(6,0))
        self.model_combo=ttk.Combobox(conn,textvariable=self.model_var,state="normal")
        self.model_combo.grid(row=4,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Label(conn,text=i18n.t('u5.api_key')).grid(row=5,column=0,sticky="w",pady=(6,0))
        ttk.Entry(conn,textvariable=self.api_key_var,show="•").grid(row=5,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Label(conn,text=i18n.t('u5.api_key_note'),foreground="#666",wraplength=430,justify="left").grid(row=6,column=0,columnspan=2,sticky="w",pady=(4,0))

        common=ttk.LabelFrame(left,text=i18n.t('u5.common_settings'),padding=8); common.pack(fill="x",pady=(10,0))
        common.columnconfigure(1,weight=1)
        ttk.Label(common,text=i18n.t('u5.game_preset')).grid(row=0,column=0,sticky="w")
        ttk.Combobox(common,textvariable=self.preset_var,values=list(core.GAME_PRESETS),state="readonly",width=15).grid(row=0,column=1,sticky="ew",padx=(6,0))
        ttk.Checkbutton(common,text=i18n.t('u5.repair_existing', target_name=i18n.t('lang.' + _current_target_lang(self))),variable=self.repair_var,command=self._save_llm_preferences).grid(row=1,column=0,columnspan=2,sticky="w",pady=(6,0))
        ttk.Checkbutton(common,text=i18n.t('u5.auto_qa'),variable=self.autoqa_var,command=self._save_llm_preferences).grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Checkbutton(common,text=i18n.t('u5.chinese_auto_qa'),variable=self.chinese_autoqa_var,command=self._save_llm_preferences).grid(row=3,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Checkbutton(common,text=i18n.t('u5.normalize_spacing'),variable=self.normalize_spacing_var,command=self._save_llm_preferences).grid(row=11,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Label(common,text=i18n.t('u5.batch')).grid(row=4,column=0,sticky="w",pady=(7,0))
        ttk.Spinbox(common,from_=1,to=500,textvariable=self.batch_var,width=8,command=self._save_llm_preferences).grid(row=4,column=1,sticky="w",padx=(6,0),pady=(7,0))
        ttk.Label(common,text=i18n.t('u5.workers')).grid(row=5,column=0,sticky="w",pady=(5,0))
        ttk.Spinbox(common,from_=1,to=8,textvariable=self.workers_var,width=8,command=self._save_llm_preferences).grid(row=5,column=1,sticky="w",padx=(6,0),pady=(5,0))
        ttk.Label(common,text=i18n.t('u5.recommended')).grid(row=6,column=0,sticky="w",pady=(5,0))
        perf_combo=ttk.Combobox(common,textvariable=self.performance_preset_var,values=[ui_status.performance_preset_label(x) for x in ui_status.PERFORMANCE_PRESETS],state="readonly",width=18)
        perf_combo.grid(row=6,column=1,sticky="ew",padx=(6,0),pady=(5,0))
        ttk.Button(common,text=i18n.t('u5.apply_preset'),command=self.apply_performance_preset).grid(row=7,column=0,columnspan=2,sticky="ew",pady=(5,0))
        ttk.Label(common,text=i18n.t('u5.glossary')).grid(row=8,column=0,sticky="w",pady=(7,0))
        ttk.Entry(common,textvariable=self.glossary_path_var).grid(row=8,column=1,sticky="ew",padx=(6,0),pady=(7,0))
        ttk.Button(common,text=i18n.t('u5.choose_glossary'),command=self.pick_glossary).grid(row=9,column=0,columnspan=2,sticky="ew",pady=(5,0))
        ttk.Label(common,text=i18n.t('u5.batch_recommendation'),foreground="#8a5a00").grid(row=10,column=0,columnspan=2,sticky="w",pady=(5,0))
        self.apply_current_translation_btn=ttk.Button(common,text=i18n.t('u5.apply_current_settings'),command=self.apply_settings_to_current_translation)
        self.apply_current_translation_btn.grid(row=11,column=0,columnspan=2,sticky="ew",pady=(7,0))

        profsel=ttk.LabelFrame(left,text=i18n.t('u5.profile_selection'),padding=8); profsel.pack(fill="x",pady=(10,0))
        profsel.columnconfigure(0,weight=1)
        self.profile_combo=ttk.Combobox(profsel,textvariable=self.profile_var,state="readonly")
        self.profile_combo.grid(row=0,column=0,sticky="ew")
        pbar=ttk.Frame(profsel); pbar.grid(row=1,column=0,sticky="ew",pady=(6,0))
        ttk.Button(pbar,text=i18n.t('u5.apply'),command=self.apply_selected_profile).pack(side="left")
        ttk.Button(pbar,text=i18n.t('u5.delete'),command=self.delete_selected_profile_combo).pack(side="left",padx=(5,0))
        ttk.Button(pbar,text=i18n.t('u5.save_current_settings'),command=self.save_current_profile).pack(side="left",padx=(5,0))

        pf=ttk.LabelFrame(left,text=i18n.t('u5.saved_profiles'),padding=8); pf.pack(fill="both",expand=True,pady=(10,0))
        pb=ttk.Frame(pf); pb.pack(fill="x",pady=(0,6))
        ttk.Button(pb,text=i18n.t('u5.save_profile'),command=self.save_current_profile).pack(side="left")
        ttk.Button(pb,text=i18n.t('u5.apply_selected'),command=self.apply_profile_from_tree).pack(side="left",padx=(6,0))
        ttk.Button(pb,text=i18n.t('u5.delete_selected'),command=self.delete_profile).pack(side="left",padx=(6,0))
        self.profile_tree=ttk.Treeview(pf,columns=("name","label","provider","model","batch","workers"),show="headings",height=7)
        # 列幅は表示領域に合わせて縮ませず固定する。必要幅を超えた分は
        # 下部の横スクロールバーで確認する。
        for c,txt,w in (("name",i18n.t('u5.name'),140),("label",i18n.t('u5.purpose'),160),("provider",i18n.t('u5.method'),150),("model",i18n.t('u5.model'),420),("batch",i18n.t('u5.batch'),80),("workers",i18n.t('u5.workers'),80)):
            self.profile_tree.heading(c,text=txt)
            self.profile_tree.column(c,width=w,minwidth=w,stretch=False)
        self._enable_tree_sort(self.profile_tree)
        pscroll_x=ttk.Scrollbar(pf,orient="horizontal",command=self.profile_tree.xview)
        self.profile_tree.configure(xscrollcommand=pscroll_x.set)
        self.profile_tree.pack(fill="both",expand=True); pscroll_x.pack(fill="x")
        self.profile_tree.bind("<Double-1>",lambda e:self.apply_profile_from_tree())

        bench=ttk.LabelFrame(right,text=i18n.t('u5.speed_comparison'),padding=8); bench.pack(fill="both",expand=True)
        bar=ttk.Frame(bench); bar.pack(fill="x",pady=(0,6))
        ttk.Button(bar,text=i18n.t('u5.benchmark_current'),command=self.benchmark_selected_model).pack(side="left")
        ttk.Button(bar,text=i18n.t('u5.benchmark_selected'),command=self.benchmark_selected_models).pack(side="left",padx=(6,0))
        self.benchmark_stop_btn=ttk.Button(bar,text=i18n.t('u5.stop_benchmark'),command=self.stop_benchmark,state="disabled"); self.benchmark_stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(bar,text=i18n.t('u5.clear_stats'),command=self.clear_model_stats).pack(side="left",padx=(6,0))
        self.benchmark_status_var=tk.StringVar(value=""); ttk.Label(bar,textvariable=self.benchmark_status_var).pack(side="right")

        select_box=ttk.LabelFrame(bench,text=i18n.t('u5.choose_models'),padding=6); select_box.pack(fill="x",pady=(0,8))
        ttk.Label(select_box,text=i18n.t('u5.multiselect_note'),foreground="#666").pack(anchor="w",pady=(0,4))
        self.benchmark_model_list=tk.Listbox(select_box,selectmode=tk.EXTENDED,exportselection=False,height=6)
        self._enable_ctrl_multiselect(self.benchmark_model_list,max_items=5); self.benchmark_model_list.pack(fill="x"); self.benchmark_model_list.bind("<<ListboxSelect>>",self._limit_benchmark_selection)

        cols=("provider","model","requests","avg","tps","fail")
        self.stats_tree=ttk.Treeview(bench,columns=cols,show="headings",height=16)
        for c,txt,w in (("provider",i18n.t('u5.provider'),100),("model",i18n.t('u5.model'),330),("requests",i18n.t('u5.requests'),70),("avg",i18n.t('u5.average_seconds'),90),("tps","tokens/s",100),("fail",i18n.t('u5.failure_rate'),90)):
            self.stats_tree.heading(c,text=txt); self.stats_tree.column(c,width=w,anchor="center" if c not in ("model",) else "w")
        self._enable_tree_sort(self.stats_tree)
        sscroll_x=ttk.Scrollbar(bench,orient="horizontal",command=self.stats_tree.xview)
        self.stats_tree.configure(xscrollcommand=sscroll_x.set); self.stats_tree.pack(fill="both",expand=True); sscroll_x.pack(fill="x")

        self.refresh_model_stats_ui(); self.refresh_profiles_ui()

    def _swap_api_key_for_provider(self):
        """プロバイダを切り替えたら、前のプロバイダのキーを別の相手へ送らないよう入れ替える。

        キーはこの起動中だけ覚え、ディスクには保存しない。
        """
        if not hasattr(self, "_api_keys_by_provider"): self._api_keys_by_provider={}
        old=getattr(self, "_api_key_provider", None)
        new=self.provider_var.get()
        if old == new: return
        if old is not None:
            self._api_keys_by_provider[old]=self.api_key_var.get().strip()
        self.api_key_var.set(self._api_keys_by_provider.get(new, ""))
        self._api_key_provider=new

    def on_provider_change(self):
        self._swap_api_key_for_provider()
        self.url_var.set(core.default_url_for_provider(self.provider_var.get()))
        self.model_var.set("")
        self.refresh_models()

    def refresh_model_stats_ui(self):
        if not hasattr(self,"stats_tree"): return
        for x in self.stats_tree.get_children(): self.stats_tree.delete(x)
        for key,st in sorted(self.model_stats.items(),key=lambda kv:(kv[1].get("provider",""),kv[1].get("model",""))):
            req=int(st.get("requests",0)); fail=int(st.get("failures",0)); succ=max(0,req-fail)
            avg=(float(st.get("total_seconds",0))/succ) if succ else 0
            toks=float(st.get("total_tokens",0)); toksec=float(st.get("token_seconds",0)); tps=(toks/toksec) if toksec else float(st.get("last_tps",0) or 0)
            fr=(fail/req*100) if req else 0
            self.stats_tree.insert("","end",iid=key,values=(st.get("provider",""),st.get("model",""),req,f"{avg:.2f}",f"{tps:.1f}" if tps else "--",f"{fr:.1f}%"))

    def _record_metric(self,metric):
        if not metric: return
        key=f"{metric.get('provider','')}::{metric.get('model','')}"
        st=self.model_stats.setdefault(key,{"provider":metric.get("provider",""),"model":metric.get("model",""),"requests":0,"failures":0,"total_seconds":0.0,"total_tokens":0,"token_seconds":0.0,"last_tps":0.0})
        st["requests"]=int(st.get("requests",0))+1
        if not metric.get("success"):
            st["failures"]=int(st.get("failures",0))+1
        else:
            elapsed=float(metric.get("elapsed",0) or 0); st["total_seconds"]=float(st.get("total_seconds",0))+elapsed
            tokens=int(metric.get("completion_tokens",0) or 0)
            if tokens>0 and elapsed>0:
                st["total_tokens"]=int(st.get("total_tokens",0))+tokens; st["token_seconds"]=float(st.get("token_seconds",0))+elapsed
            st["last_tps"]=float(metric.get("tokens_per_second",0) or st.get("last_tps",0) or 0)
        core.save_json(STATS_PATH,self.model_stats); self.refresh_model_stats_ui()

    def benchmark_selected_model(self):
        model=self.model_var.get().strip()
        if not model: messagebox.showinfo(APP_NAME,i18n.t('u5.select_model')); return
        self._start_benchmark([model])

    def _limit_benchmark_selection(self,event=None):
        if not hasattr(self,"benchmark_model_list"): return
        selected=list(self.benchmark_model_list.curselection())
        if len(selected)<=5: return
        # Tkの選択順は取得できないため、先頭5件を残して6件目以降を解除する。
        for idx in selected[5:]:
            self.benchmark_model_list.selection_clear(idx)
        self.benchmark_status_var.set(i18n.t('u5.benchmark_limit_status'))

    def benchmark_selected_models(self):
        if not hasattr(self,"benchmark_model_list"):
            return
        selected=list(self.benchmark_model_list.curselection())
        if not selected:
            messagebox.showinfo(APP_NAME,i18n.t('u5.select_comparison_models'))
            return
        if len(selected)>5:
            messagebox.showinfo(APP_NAME,i18n.t('u5.benchmark_limit'))
            return
        models=[self.benchmark_model_list.get(i) for i in selected]
        self._start_benchmark(models)

    def _start_benchmark(self,models):
        if getattr(self,"benchmark_worker",None) and self.benchmark_worker.is_alive(): return
        self.benchmark_status_var.set(i18n.t('u5.benchmark_starting', count=len(models)))
        self.llm_operation = i18n.t('u5.model_benchmark')
        self.benchmark_stop_btn.config(state="normal")
        provider=self.provider_var.get(); url=self.url_var.get().strip(); api_key=self.api_key_var.get().strip()
        self.benchmark_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("benchmark_progress",p)))
        def work():
            stopped=False
            for i,m in enumerate(models,1):
                if self.benchmark_controller.stop_event.is_set():
                    stopped=True; break
                self.events.put(("benchmark_model_start",(i,len(models),m)))
                try:
                    captured=[]
                    original_cb=self.benchmark_controller.progress_callback
                    def cb(payload):
                        if payload.get("kind")=="llm_metric": captured.append(payload.get("metric"))
                        if original_cb: original_cb(payload)
                    self.benchmark_controller.progress_callback=cb
                    core.benchmark_model(provider,url,m,self.benchmark_controller,api_key)
                    metric=next((x for x in reversed(captured) if x),None)
                    self.events.put(("benchmark_metric",(i,len(models),metric)))
                except core.StopRequested:
                    stopped=True; break
                except Exception as e:
                    if self.benchmark_controller.stop_event.is_set():
                        stopped=True; break
                    self.events.put(("benchmark_error",(i,len(models),m,str(e))))
            self.events.put(("benchmark_stopped" if stopped else "benchmark_done",None))
        self.benchmark_worker=threading.Thread(target=work,daemon=True); self.benchmark_worker.start()

    def stop_benchmark(self):
        if self.benchmark_controller and not self.benchmark_controller.stop_event.is_set():
            self.benchmark_controller.request_stop(save=False)
            self.benchmark_status_var.set(i18n.t('u5.benchmark_stop_requested'))
            self.benchmark_stop_btn.config(state="disabled")
            self.llm_detail_var.set(i18n.t('u5.api_stop_requested'))

    def clear_model_stats(self):
        if messagebox.askyesno(APP_NAME,i18n.t('u5.confirm_clear_stats')):
            self.model_stats={}; core.save_json(STATS_PATH,self.model_stats); self.refresh_model_stats_ui()

    def refresh_profiles_ui(self):
        names=sorted(self.model_profiles)
        if hasattr(self,"profile_combo"): self.profile_combo["values"]=names
        if hasattr(self,"profile_tree"):
            for x in self.profile_tree.get_children(): self.profile_tree.delete(x)
            for name in names:
                p=self.model_profiles[name]
                self.profile_tree.insert("","end",iid=name,values=(name,p.get("label",""),p.get("provider",""),p.get("model",""),p.get("batch",40),p.get("workers",1)))

    def save_current_profile(self):
        name=simpledialog.askstring(i18n.t('u5.model_profiles'),i18n.t('u5.profile_name'))
        if not name: return
        label=simpledialog.askstring(i18n.t('u5.model_profiles'),i18n.t('u5.profile_purpose'),initialvalue=self.model_profiles.get(name,{}).get("label","")) or ""
        self.model_profiles[name]={"label":label,"provider":self.provider_var.get(),"url":self.url_var.get(),"model":self.model_var.get(),"batch":self.batch_var.get(),"workers":self.workers_var.get(),"preset":self.preset_var.get()}
        core.save_json(PROFILES_PATH,self.model_profiles); self.profile_var.set(name); self.refresh_profiles_ui()

    def _apply_profile(self,name):
        p=self.model_profiles.get(name)
        if not p: return
        self.provider_var.set(p.get("provider","Ollama")); self.url_var.set(p.get("url",core.default_url_for_provider(self.provider_var.get())))
        self.model_var.set(p.get("model","")); self.batch_var.set(p.get("batch",40)); self.workers_var.set(p.get("workers",1)); self.preset_var.set(p.get("preset","CK3")); self.profile_var.set(name)
        self._swap_api_key_for_provider()
        self.refresh_models()

    def apply_selected_profile(self): self._apply_profile(self.profile_var.get())

    def apply_profile_from_tree(self):
        sel=self.profile_tree.selection()
        if sel: self._apply_profile(sel[0])

    def delete_profile(self):
        sel=self.profile_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, i18n.t('u5.select_profile_delete'))
            return
        names=list(sel)
        if not messagebox.askyesno(APP_NAME, i18n.t('u5.confirm_delete_profiles', names="\n".join(names))):
            return
        for name in names: self.model_profiles.pop(name,None)
        if self.profile_var.get() in names: self.profile_var.set("")
        core.save_json(PROFILES_PATH,self.model_profiles); self.refresh_profiles_ui()

    def delete_selected_profile_combo(self):
        name=self.profile_var.get().strip()
        if not name:
            messagebox.showinfo(APP_NAME,i18n.t('u5.select_profile_delete'))
            return
        if not messagebox.askyesno(APP_NAME,i18n.t('u5.confirm_delete_profile', name=name)):
            return
        self.model_profiles.pop(name,None)
        self.profile_var.set("")
        core.save_json(PROFILES_PATH,self.model_profiles)
        self.refresh_profiles_ui()

    # ---------------- queue ----------------
    def _output_identity_source(self, p: Path) -> Path:
        p = Path(p)
        if p.is_dir() and core.is_localization_dir_name(p.name):
            return p.parent
        if p.is_dir() and core.mod_localization_root(p) is not None:
            return p
        return p

    def _isolated_output_path(self, p: Path, root: Path, mod_name: str = "",
                              target_lang: str = core.DEFAULT_TARGET_LANG) -> Path:
        """Return a stable Mod/job-specific output directory.

        ``localization`` is the basename of almost every Mod localization folder,
        so using it directly caused unrelated Mods to share one output tree.
        Include the source identity hash to keep parent/child and same-name Mods
        completely isolated even before a Japanese file exists.
        """
        identity = self._output_identity_source(Path(p))
        try:
            source_id = str(identity.expanduser().resolve())
        except Exception:
            source_id = str(identity.expanduser())
        label = mod_name or (identity.stem if identity.is_file() else identity.name) or "translation"
        safe = re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+', '_', label).strip('_')[:64] or "translation"
        digest = hashlib.sha256(source_id.encode("utf-8", "ignore")).hexdigest()[:10]
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        # 末尾は翻訳先の言語。日本語は v0.12.0 までと同じ「_japanese」なので、今までの出力をそのまま引き継ぐ。
        # （v0.12.0 は言語によらず _japanese にしていたため、同じ Mod の日本語とほかの言語が出力先を共有していた）
        lang = target_lang if target_lang in core.TARGET_LANGUAGES else core.DEFAULT_TARGET_LANG
        return root / f"{safe}_{digest}_{lang}"

    def _default_output(self,p:Path,target_lang:str|None=None):
        raw = self.normal_output_var.get().strip() if hasattr(self, "normal_output_var") else ""
        root = Path(raw) if raw else _automatic_output_root()
        return self._isolated_output_path(Path(p), root, target_lang=target_lang or core.DEFAULT_TARGET_LANG)

    def _set_target_lang(self, lang, save=True):
        lang=_target_lang_from_choice(lang)
        previous = _current_target_lang(self)
        if previous != lang and getattr(self, "mod_research_results", None):
            self._save_translation_status_state("target_language_changed")
        self.target_lang_var.set(lang)
        self.target_lang_choice_var.set(_target_lang_choice(lang))
        self._refresh_glossary_import_language_labels()
        if previous != lang and hasattr(self, "mod_status_tree"):
            self.mod_research_stop_event.set()
            self.mod_research_results = []
            self._restore_status_snapshot_cache = None
            self._restore_status_rows_cache = None
            self._populate_mod_status_tree()
            self._refresh_relation_target_labels(previous, lang)
            self._restore_cached_mod_status()
        if save:
            self._save_llm_preferences()

    def _refresh_relation_target_labels(self, previous, target_lang):
        keys = (
            'u6.japanese_translation_status_by_mod', 'u6.mod_research_translation_mod_assessment_and',
            'u6.set_translation_mod_source_mod_exceptions', 'u6.check_source_mods_and_separate_translation',
            'u6.also_search_other_mods_for_japanese',
        )
        replacements = {i18n.t(key, target_name=i18n.t("lang." + previous)):
                        i18n.t(key, target_name=i18n.t("lang." + target_lang)) for key in keys}
        replacements[_relation_scope_text(previous)] = _relation_scope_text(target_lang)
        pending = [self.tab_status, self.tab_monitor] if hasattr(self, "tab_monitor") else [self.tab_status]
        while pending:
            widget = pending.pop()
            pending.extend(widget.winfo_children())
            try:
                text = widget.cget("text")
                if text in replacements:
                    widget.configure(text=replacements[text])
            except tk.TclError:
                pass
        for column, key in (("jpmod", 'u6.translation_mod'), ("jpmod_gaps", 'u6.translation_mod_gaps')):
            self.mod_status_tree.heading(column, text=i18n.t(key, target_name=i18n.t("lang." + target_lang)))
        self._set_mod_status_detail_text(i18n.t('u6.select_a_mod_to_see_research', target_name=i18n.t("lang." + target_lang)))

    def _refresh_glossary_import_language_labels(self):
        target_name=i18n.t("lang." + _current_target_lang(self))
        menu=getattr(self,"glossary_import_menu",None)
        if menu is not None:
            menu.entryconfigure(0,label=i18n.t('u4.target_import_yaml',target_name=target_name))
            menu.entryconfigure(1,label=i18n.t('u4.target_import_mod',target_name=target_name))
        for name,key in (("glossary_jp_import_btn","u4.target_import_files"),
                         ("glossary_base_help_label","u4.target_base_help"),
                         ("glossary_generated_help_label","u4.target_generated_help")):
            widget=getattr(self,name,None)
            if widget is not None:
                widget.config(text=i18n.t(key,target_name=target_name))
        hint=getattr(self,"auto_glossary_drop_hint",None)
        if hint is not None:
            hint.config(text=i18n.t('u4.target_drop_help',target_name=target_name) if DND_AVAILABLE else i18n.t('u4.drop_unavailable'))

    def _ensure_isolated_item_output(self, item: dict, mode: str = "normal"):
        if item.get("custom_output"):
            return
        inp = Path(item.get("input", ""))
        if not inp:
            return
        if mode == "chinese":
            raw = self.chinese_output_var.get().strip() if hasattr(self, "chinese_output_var") else ""
            root = Path(raw) if raw else OUTPUT_ROOT / "中国語基準翻訳"
        else:
            raw = self.normal_output_var.get().strip() if hasattr(self, "normal_output_var") else ""
            root = Path(raw) if raw else OUTPUT_ROOT
        target_lang = _item_target_lang(item)
        expected = self._isolated_output_path(inp, root, item.get("mod_name", ""), target_lang=target_lang)
        # v0.12.0 で日本語以外を訳した項目（出力先が日本語と共有の「…_japanese」）も、ここで「…_<言語>」へ向け直す。
        # 古い出力のファイルは動かさない（「…_japanese」の中に残る）。キャッシュは CACHE_ROOT にあるので訳し直しにはならない。
        if item.get("output") != str(expected) or not item.get("output_isolated_v2"):
            item["output"] = str(expected)
            item["output_isolated_v2"] = True

    def pick_normal_output(self):
        raw=filedialog.askdirectory(title=i18n.t('u1.choose_output_root'))
        if raw:
            self.normal_output_var.set(raw)

    def add_folder(self):
        p=filedialog.askdirectory(title=i18n.t('u1.choose_mod_folder'))
        if p:
            path=Path(p)
            self.normal_input_var.set(str(path))
            self.normal_status_var.set(i18n.t('u1.folder_added', name=path.name))
            self._append_queue(path)

    def add_files(self):
        paths=filedialog.askopenfilenames(title=i18n.t('u1.choose_yaml'),filetypes=[("Paradox YAML","*.yml"),("All","*")])
        added=0
        for raw in paths:
            path=Path(raw)
            self._append_queue(path)
            added += 1
        if paths:
            self.normal_input_var.set(str(Path(paths[-1])))
            self.normal_status_var.set(i18n.t('u1.yaml_added', count=added))

    def _safe_job_name(self, p: Path) -> str:
        base = p.stem if p.is_file() else p.name
        base = re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+', '_', base).strip('_')
        return base[:48] or "translation"

    def _source_id(self, p: Path) -> str:
        try:
            return str(Path(p).resolve())
        except Exception:
            return str(Path(p).absolute())

    def _load_cache_registry(self) -> dict:
        data = load_persistent_json(CACHE_REGISTRY_PATH, {}, i18n.t('u5.cache_registry'))
        return data if isinstance(data, dict) else {}

    def _save_cache_registry(self, data: dict):
        core.save_json(CACHE_REGISTRY_PATH, data)

    def _register_cache_job(self, item: dict, mode: str = "normal"):
        cache = Path(item.get("cache", ""))
        if not cache.exists() or not (cache.parent / core.SOURCE_MANIFEST_NAME).exists():
            return
        sid = self._source_id(Path(item["input"]))
        reg = self._load_cache_registry()
        rows = [r for r in reg.get(sid, []) if Path(r.get("cache", "")).exists()]
        rows = [r for r in rows if r.get("cache") != str(cache)]
        rows.append({"cache": str(cache), "input": item["input"], "output": item.get("output", ""),
                     "mode": mode, "updated_at": datetime.now().isoformat(timespec="seconds")})
        reg[sid] = rows[-20:]
        self._save_cache_registry(reg)

    def _find_previous_cache(self, p: Path, exclude: Path | None = None, mode: str = "normal") -> Path | None:
        sid = self._source_id(p)
        candidates = []
        reg = self._load_cache_registry()
        for row in reg.get(sid, []):
            row_mode = row.get("mode")
            if mode == "chinese" and row_mode != "chinese":
                continue
            if mode == "normal" and row_mode not in (None, "normal"):
                continue
            cp = Path(row.get("cache", ""))
            if cp.exists() and (cp.parent / core.SOURCE_MANIFEST_NAME).exists():
                candidates.append(cp)
        # Registryが失われても、キャッシュフォルダ内のmanifestから復旧できる。
        if mode == "normal":
            for mf in CACHE_ROOT.glob(f"*/{core.SOURCE_MANIFEST_NAME}"):
                try:
                    manifest = core.load_json(mf, {})
                    if manifest.get("input") == sid and not manifest.get("language_filter"):
                        cp = mf.parent / core.CACHE_FILE_NAME
                        if cp.exists(): candidates.append(cp)
                except Exception:
                    pass
        if exclude:
            try: ex = Path(exclude).resolve()
            except Exception: ex = Path(exclude)
            candidates = [c for c in candidates if c.resolve() != ex]
        if not candidates:
            return None
        # manifestの更新時刻を優先。
        unique = {str(c.resolve()): c for c in candidates}
        return max(unique.values(), key=lambda c: (c.parent / core.SOURCE_MANIFEST_NAME).stat().st_mtime)

    def _new_cache_path(self, p: Path) -> Path:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        job_id = uuid.uuid4().hex[:8]
        folder = CACHE_ROOT / f"{stamp}_{self._safe_job_name(p)}_{job_id}"
        folder.mkdir(parents=True, exist_ok=True)
        return folder / core.CACHE_FILE_NAME

    def _ensure_item_cache(self, item: dict) -> str:
        existing = item.get("cache")
        if existing:
            existing = _remap_legacy_data_path(existing)
            item["cache"] = existing
            path = Path(existing)
            path.parent.mkdir(parents=True, exist_ok=True)
            return str(path)
        p = Path(item["input"])
        cache_path = self._new_cache_path(p)
        old_cache = Path(item.get("output", "")) / ".cache" / core.CACHE_FILE_NAME
        if old_cache.exists() and not cache_path.exists():
            try:
                shutil.copy2(old_cache, cache_path)
            except Exception:
                pass
        item["cache"] = str(cache_path)
        return item["cache"]

    def _translation_status_missing_for_item(self, item: dict, source_language: str) -> dict:
        """Return differential targets from the same gap logic used by Translation Status.

        The Translation Status view judges Japanese coverage against the English +
        Simplified-Chinese union. Differential translation reuses that judgement, then
        selects only keys that the current queue language can actually translate.
        """
        p = Path(item.get("input", ""))
        loc, mod_root = self._infer_mod_target_for_item(item)
        if not loc or not Path(loc).is_dir():
            if p.is_dir() and core.is_localization_dir_name(p.name):
                loc, mod_root = p, p
            elif p.is_dir() and core.mod_localization_root(p) is not None:
                loc, mod_root = core.mod_localization_root(p), p
            else:
                loc, mod_root = p, p

        candidates = []
        status_label = ""
        target_lang = _overwrite_target_lang(self, item)
        try:
            ext_root = Path(item.get("external_translation_path", "")) if item.get("external_translation_path") else None
            if target_lang == "english":
                ext_root = None
            if ext_root and ext_root.is_dir() and Path(mod_root).exists():
                result = core.analyze_external_translation_coverage(Path(mod_root), ext_root, target_lang=target_lang)
                candidates = list(result.get("gaps", []))
                status_label = "別Mod翻訳・欠損" if candidates else "別Modで完全翻訳"
            elif Path(mod_root).exists():
                result = core.analyze_mod_translation_status(Path(mod_root), preferred_source=source_language, target_lang=target_lang)
                candidates = list(result.get("candidates", []))
                status_label = result.get("status", "")
            if target_lang != core.DEFAULT_TARGET_LANG:
                target_root = ext_root if ext_root and ext_root.is_dir() else loc
                existing_keys = _existing_target_keys(target_root, target_lang)
                candidates = [candidate for candidate in candidates if candidate.get("key") not in existing_keys]
        except Exception as exc:
            record_error(i18n.t('u6.difference_translation_translation_status_gap_assessment'), exc, str(mod_root))
            candidates = list(item.get("status_gap_candidates", [])) if target_lang == core.DEFAULT_TARGET_LANG else []
            status_label = i18n.t('u6.saved_translation_status')

        wanted = {str(c.get("key")) for c in candidates if c.get("key")}
        files = core.gather_yml_files(p) if p.exists() else []
        base_dir = p if p.is_dir() else p.parent
        details = []
        selected = set()
        for source_file in files:
            try:
                lang, entries, _ = core.parse_localization_file(source_file)
            except Exception:
                continue
            if lang != source_language:
                continue
            keys = [k for k in entries if k in wanted and entries.get(k) and not core.looks_untranslatable(entries.get(k, ""))]
            if not keys:
                continue
            selected.update(keys)
            rel_dir = source_file.parent.relative_to(base_dir) if p.is_dir() else Path('.')
            details.append({
                "source_file": str(source_file),
                "target_file": str(Path(item.get("output", "")) / core.remap_rel_dir(rel_dir, target_lang) / core.rename_for_target(source_file, target_lang, source_language)),
                "keys": keys,
            })
        opposite_origin = "english_only" if source_language == "simp_chinese" else "chinese_only"
        opposite_language = "english" if source_language == "simp_chinese" else "simp_chinese"
        opposite_only_keys = sorted({
            str(c.get("key")) for c in candidates
            if c.get("key") and c.get("source_origin") == opposite_origin
        })
        unavailable_keys = sorted(wanted - selected)
        opposite_only_unavailable = sorted(set(unavailable_keys) & set(opposite_only_keys))
        other_unavailable = sorted(set(unavailable_keys) - set(opposite_only_unavailable))
        return {
            "count": len(selected),
            "details": details,
            "source_language": source_language,
            "status_gap_total": len(candidates),
            "status": status_label,
            "candidate_keys": sorted(wanted),
            "selected_keys": sorted(selected),
            "unavailable_keys": unavailable_keys,
            "opposite_language": opposite_language,
            "opposite_only_keys": opposite_only_unavailable,
            "opposite_only_count": len(opposite_only_unavailable),
            "other_unavailable_keys": other_unavailable,
            "other_unavailable_count": len(other_unavailable),
        }

    def _prepare_differential_cache(self, item: dict, silent: bool = True, mode: str = "normal", repair_enabled=None) -> dict | None:
        p = Path(item["input"])
        output_root = Path(item.get("output", ""))
        current_cache = Path(self._ensure_item_cache(item))
        source_language = "simp_chinese" if mode == "chinese" or _overwrite_target_lang(self, item) == "english" else "english"

        # 欠損は独自計算せず、翻訳状況タブと同じ判定ロジックから取得する。
        # スナップショットがなくても、翻訳状況で欠損と判断されたキーを差分対象にできる。
        try:
            missing = self._translation_status_missing_for_item(item, source_language)
        except Exception as exc:
            record_error(i18n.t('u3.diff_status_error'), exc, str(p))
            missing = {"count": 0, "details": [], "source_language": source_language, "status_gap_total": 0}

        previous = (self._find_previous_cache(p, exclude=current_cache, mode=mode)
                    if _overwrite_target_lang(self, item) == core.DEFAULT_TARGET_LANG else None)
        old_manifest = core.load_source_manifest(previous) if previous else {}
        try:
            if mode == "chinese":
                new_manifest = core.build_source_manifest_for_language(p, "simp_chinese")
            else:
                use_repair = self.repair_var.get() if repair_enabled is None else bool(repair_enabled)
                new_manifest = core.build_source_manifest(p, None if use_repair else core.DEFAULT_TARGET_LANG)
        except Exception:
            return None

        if old_manifest:
            diff = core.compare_source_manifests(old_manifest, new_manifest)
            diff["snapshot_available"] = True
        else:
            diff = {
                "counts": {"added": 0, "changed": 0, "removed": 0, "unchanged": 0,
                           "added_files": 0, "removed_files": 0},
                "details": [],
                "snapshot_available": False,
            }
        diff["missing"] = missing
        diff["counts"]["missing"] = int(missing.get("count", 0) or 0)
        c = diff["counts"]
        changed_total = c["added"] + c["changed"] + c["removed"]
        source_changed = changed_total > 0 or c["added_files"] > 0 or c["removed_files"] > 0
        missing_total = c["missing"]

        status_gap_total = int(missing.get("status_gap_total", 0) or 0)
        opposite_only_count = int(missing.get("opposite_only_count", 0) or 0)
        other_unavailable_count = int(missing.get("other_unavailable_count", 0) or 0)
        language_complete = (
            missing_total == 0
            and status_gap_total > 0
            and opposite_only_count == status_gap_total
            and other_unavailable_count == 0
        )
        diff["language_complete"] = language_complete
        diff["opposite_only_count"] = opposite_only_count
        diff["opposite_language"] = missing.get("opposite_language", "")

        # スナップショットがなくても、翻訳状況に残る欠損がすべて反対側言語固有なら、
        # 現在の言語では翻訳が完了していると判定できる。
        if not old_manifest and missing_total == 0:
            if language_complete:
                item["diff"] = diff
                item["diff_mode"] = True
                return diff
            # 欠損そのものがない場合は、同一キー本文の更新有無を判定する材料がない。
            return None

        if not source_changed and missing_total == 0:
            item["diff"] = diff
            if previous:
                item["previous_cache"] = str(previous)
            if item.get("status") == status_value("waiting") and not language_complete:
                item["status"] = status_value("no_diff")
            return diff

        # 過去キャッシュがある場合は複製し、既訳を再利用しつつ
        # 原文差分と現在の欠損だけを補完する。
        if previous:
            try:
                shutil.copy2(previous, current_cache)
            except Exception:
                pass
            item["previous_cache"] = str(previous)
        else:
            item.pop("previous_cache", None)
        item["diff"] = diff
        item["diff_mode"] = True
        if source_changed and missing_total:
            item["status"] = status_value("diff_added_changed_missing", added=c['added'], changed=c['changed'], missing=missing_total)
        elif missing_total:
            item["status"] = status_value("gap_fill", missing=missing_total)
        else:
            item["status"] = status_value("diff_added_changed", added=c['added'], changed=c['changed'])
        core.save_json(current_cache.parent / "diff_report.json", {
            "previous_cache": str(previous) if previous else "", "current_input": str(p),
            "detected_at": datetime.now().isoformat(timespec="seconds"), "diff": diff
        })
        if not silent:
            snapshot_note = i18n.t('u3.snapshot_present') if old_manifest else i18n.t('u3.snapshot_absent')
            messagebox.showinfo(APP_NAME,
                i18n.t('u3.diff_confirmation', snapshot_note=snapshot_note, added=c['added'], changed=c['changed'], removed=c['removed'], missing_total=missing_total, added_files=c['added_files'], removed_files=c['removed_files']))
        return diff

    def _append_queue(self,p:Path,out:Path|None=None,status=None,cache:Path|None=None,target_lang:str|None=None):
        if self._normal_queue_locked():
            return None
        p = Path(p)
        if not p.exists():
            return
        target_lang=target_lang or self.target_lang_var.get()
        out=out or self._default_output(p, target_lang)
        cache_path = cache or self._new_cache_path(p)
        item={"input":str(p),"output":str(out),"status":status or status_value("waiting"),"cache":str(cache_path),"output_isolated_v2":True,
              "target_lang":target_lang}
        app_state.ensure_queue_item_id(item)
        self.queue_items.append(item)
        self._refresh_queue_tree(); self._save_workspace_state("normal_queue_changed")

    def detect_diff_for_selected(self):
        item = self._selected_queue_item()
        if not item: return
        diff = self._prepare_differential_cache(item, silent=False)
        if diff is None:
            messagebox.showinfo(APP_NAME, i18n.t('u3.snapshot_not_found'))
        elif sum(diff["counts"][k] for k in ("added","changed","removed")) == 0:
            messagebox.showinfo(APP_NAME, i18n.t('u3.no_source_changes'))
        self._refresh_queue_tree()

    def _register_dnd_widgets(self, widgets, handler):
        """Register widgets as native file-drop targets and surface failures."""
        if not DND_AVAILABLE:
            return False
        ok = False
        last_error = None
        for widget in widgets:
            try:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", handler)
                ok = True
            except Exception as e:
                last_error = e
        if not ok and last_error is not None:
            raise last_error
        return ok

    def _normalize_drop_path(self, raw):
        """Normalize TkDND paths, including macOS file:// URLs and Tcl braces."""
        text = str(raw).strip().strip('\x00')
        if len(text) >= 2 and text[0] == '{' and text[-1] == '}':
            text = text[1:-1]
        if text.lower().startswith('file://'):
            parsed = urlparse(text)
            text = unquote(parsed.path or '')
            # Windows file URLs look like /C:/path.
            if os.name == 'nt' and re.match(r'^/[A-Za-z]:/', text):
                text = text[1:]
        return Path(text).expanduser()

    def _raw_drop_paths(self, event):
        try:
            raw_paths = list(self.tk.splitlist(event.data))
        except Exception:
            raw_paths = [getattr(event, 'data', '')]
        out=[]
        for raw in raw_paths:
            if not str(raw).strip():
                continue
            p=self._normalize_drop_path(raw)
            out.append(p)
        return out

    def _extract_drop_paths(self, event):
        files=[]
        for p in self._raw_drop_paths(event):
            if p.is_dir():
                try:
                    files.extend(core.gather_yml_files(p)[:2000])
                except Exception as e:
                    self._record_error(i18n.t('u1.dnd_parse'), e)
            elif p.is_file() and p.suffix.lower() in {".yml",".yaml"}:
                files.append(p)
        # Preserve order while removing duplicates.
        seen=set(); out=[]
        for f in files:
            try:
                k=str(f.resolve())
            except Exception:
                k=str(f)
            if k not in seen:
                seen.add(k); out.append(f)
        return out

    def _classify_drop_pair(self, files):
        src=None; dst=None
        for f in files:
            try:
                lang,_,_=core.parse_localization_file(f)
            except Exception:
                lang=""
            if lang == "japanese" and dst is None:
                dst=f
            elif lang != "japanese" and src is None:
                src=f
        if len(files) == 1 and src is None and dst is None:
            src=files[0]
        return src,dst

    def on_review_drop_paths(self,event):
        files=self._extract_drop_paths(event)
        src,dst=self._classify_drop_pair(files)
        if src: self.review_src_var.set(str(src))
        if dst: self.review_dst_var.set(str(dst))
        if src and dst:
            self.load_review()
        elif files:
            side = i18n.t('u3.japanese_yaml') if src else i18n.t('u3.source_yaml_languages')
            self.qa_summary_var.set(i18n.t('u3.drop_other_side', side=side))
        else:
            messagebox.showinfo(APP_NAME,i18n.t('u3.review_drop_files'))
        return event.action if hasattr(event,"action") else None

    def on_diff_drop_paths(self,event):
        files=self._extract_drop_paths(event)
        src,dst=self._classify_drop_pair(files)
        if src: self.diff_src_var.set(str(src))
        if dst: self.diff_dst_var.set(str(dst))
        if src and dst:
            self.load_diff_inspector()
        elif files:
            self.diff_summary_var.set(i18n.t('u3.diff_drop_both'))
        else:
            messagebox.showinfo(APP_NAME,i18n.t('u3.diff_drop_files'))
        return event.action if hasattr(event,"action") else None

    def on_drop_paths(self, event):
        if self._normal_queue_locked():
            return "break"
        added = 0
        ignored = []
        for p in self._raw_drop_paths(event):
            if p.is_dir():
                self._append_queue(p); added += 1
            elif p.is_file() and p.suffix.lower() in {".yml", ".yaml"}:
                self._append_queue(p); added += 1
            else:
                ignored.append(p.name or str(p))
        if added:
            self.progress_text.set(i18n.t('u1.dnd_added', count=added))
            self.save_session(active=False)
        if ignored:
            messagebox.showinfo(APP_NAME, i18n.t("u1.dnd_rejected_items", items="\n".join(ignored[:10])))
        return event.action if hasattr(event, "action") else None

    def _refresh_queue_tree(self):
        app_state.ensure_queue_item_ids(self.queue_items)
        for x in self.queue_tree.get_children(): self.queue_tree.delete(x)
        for i,item in enumerate(self.queue_items):
            inp=Path(item.get("input", ""))
            label=item.get("mod_name") or (inp.stem if inp.is_file() else inp.name) or i18n.t('u1.unnamed_item')
            if _item_target_lang(item) != core.DEFAULT_TARGET_LANG:
                label=f"［{core.target_language_label(_item_target_lang(item))}］{label}"
            self.queue_tree.insert("", "end", iid=str(i), values=(
                label,
                self._queue_display_path(item.get("input", "")),
                self._queue_display_path(item.get("output", "")),
                display_status(item.get("status", ""))
            ))

    def remove_queue(self):
        if self._normal_queue_locked(): return
        sels=sorted((int(x) for x in self.queue_tree.selection()),reverse=True)
        for i in sels:
            if 0<=i<len(self.queue_items): self.queue_items.pop(i)
        self._refresh_queue_tree()
        if not self.queue_items and not (self.worker and self.worker.is_alive()):
            self._delete_session()
        elif not (self.worker and self.worker.is_alive()):
            self._write_session_file(active=False,restore_on_launch=False)
        self._save_workspace_state("normal_queue_changed")

    def clear_queue(self):
        if self._normal_queue_locked(): return
        self.queue_items.clear(); self._refresh_queue_tree(); self._delete_session(); self._save_workspace_state("normal_queue_cleared")

    def _selected_queue_item(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, i18n.t('u1.select_queue_item'))
            return None
        idx = int(sel[0])
        if not (0 <= idx < len(self.queue_items)):
            return None
        item = self.queue_items[idx]
        self._ensure_item_cache(item)
        return item

    def view_selected_cache(self):
        item = self._selected_queue_item()
        if not item:
            return
        cache_path = Path(item["cache"])
        cache = core.load_cache(cache_path) if cache_path.exists() else {}
        win = tk.Toplevel(self)
        win.title(i18n.t('u5.cache_title', filename=Path(item['input']).name))
        win.geometry("900x600")
        top = ttk.Frame(win, padding=8); top.pack(fill="x")
        ttk.Label(top, text=i18n.t('u5.cache_path', cache_path=cache_path), wraplength=700).pack(side="left", fill="x", expand=True)
        ttk.Label(top, text=i18n.t('u5.entry_count', count=len(cache))).pack(side="right", padx=(8,0))
        bar = ttk.Frame(win, padding=(8,0,8,6)); bar.pack(fill="x")
        ttk.Button(bar, text=i18n.t('u5.open_storage'), command=lambda:self._open_path(cache_path.parent)).pack(side="left")
        ttk.Button(bar, text=i18n.t('u5.reload_json'), command=lambda:self._reload_cache_view(text, cache_path)).pack(side="left", padx=(6,0))
        text = tk.Text(win, wrap="none")
        y = ttk.Scrollbar(win, orient="vertical", command=text.yview); text.configure(yscrollcommand=y.set)
        text.pack(side="left", fill="both", expand=True, padx=(8,0), pady=(0,8)); y.pack(side="right", fill="y", pady=(0,8), padx=(0,8))
        self._reload_cache_view(text, cache_path)

    def _reload_cache_view(self, text_widget, cache_path: Path):
        cache = core.load_cache(cache_path) if cache_path.exists() else {}
        text_widget.config(state="normal")
        text_widget.delete("1.0", "end")
        text_widget.insert("1.0", json.dumps(cache, ensure_ascii=False, indent=2))
        text_widget.config(state="disabled")

    def import_cache_to_selected(self):
        if self._normal_queue_locked(): return
        item = self._selected_queue_item()
        if not item:
            return
        src = filedialog.askopenfilename(title=i18n.t('u5.choose_cache'), filetypes=[("JSON cache", "*.json"), ("All", "*")])
        if not src:
            return
        try:
            imported = core.load_cache(Path(src))
            if not isinstance(imported, dict):
                raise ValueError(i18n.t('u5.cache_not_dictionary'))
            dst_path = Path(item["cache"]); dst = core.load_cache(dst_path) if dst_path.exists() else {}
            overwrite = messagebox.askyesno(APP_NAME, i18n.t('u5.confirm_import_cache', count=len(imported)))
            if overwrite:
                dst.update(imported)
            else:
                for k,v in imported.items():
                    dst.setdefault(k,v)
            core.save_cache(dst_path, dst)
            self.save_session(active=bool(self.worker and self.worker.is_alive()))
            messagebox.showinfo(APP_NAME, i18n.t('u5.cache_imported', count=len(dst), dst_path=dst_path))
        except Exception as e:
            messagebox.showerror(APP_NAME, i18n.t('u5.cache_import_failed', e=e))

    def _start_manual_qa_repair(self, pairs, origin, _llm_ready=False):
        if self.qa_repair_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u3.qa_repair_running')); return
        conflicting=any(self._operation_pending(thread) for thread in (
            self.worker,self.chinese_worker,getattr(self,"benchmark_worker",None),
            self.diff_translate_thread,self.proofread_thread,self.auto_glossary_thread))
        if conflicting or self.llm_busy_count>0:
            messagebox.showinfo(APP_NAME,i18n.t('u3.qa_llm_busy')); return
        pairs=[dict(pair) for pair in (pairs or []) if pair.get("source_file") and pair.get("target_file")]
        if not pairs:
            messagebox.showinfo(APP_NAME,i18n.t('u3.qa_pair_missing', target_name=i18n.t("lang." + _current_target_lang(self)))); return
        label={"normal":i18n.t('u3.normal_queue'),"chinese":i18n.t('u3.chinese_queue'),"review":i18n.t('u3.qa_review')}.get(origin,"QA")
        if not _llm_ready:
            saved_pairs=tuple(dict(pair) for pair in pairs)
            self._begin_llm_preflight(i18n.t('u3.qa_repair_label', label=label),
                lambda:self._start_manual_qa_repair(saved_pairs,origin,_llm_ready=True))
            return
        if not messagebox.askyesno(APP_NAME,
            i18n.t('u3.qa_repair_confirm', label=label, count=len(pairs))):
            return
        settings={
            "normalize_spacing":_normalize_spacing_enabled(self),
            "provider":self.provider_var.get(), "url":self.url_var.get().strip(),
            "model":self.model_var.get().strip(), "api_key":self.api_key_var.get().strip(),
            "preset":self.preset_var.get(), "glossary":self.glossary_path_var.get().strip() or None,
        }
        if origin=="review": self.qa_summary_var.set(i18n.t('u3.qa_repair_working', count=len(pairs)))
        elif origin=="chinese": self._append_chinese_log(i18n.t('u3.qa_repair_start', count=len(pairs)))
        else: self._append_log(i18n.t('u3.qa_repair_start', count=len(pairs)))
        self._qa_repair_origin=origin
        self.qa_repair_controller=core.TranslationController(
            progress_callback=lambda payload:self.events.put(("qa_repair_event",payload)))
        def work():
            try:
                result=core.auto_repair_qa_pairs(
                    pairs,backup_root=BACKUP_ROOT/"QA自動修復",model=settings["model"],url=settings["url"],
                    provider=settings["provider"],api_key=settings["api_key"],preset=settings["preset"],
                    glossary_path=settings["glossary"],controller=self.qa_repair_controller,
                    max_passes=2,label=f"{origin}_manual_qa",
                    normalize_spacing=settings["normalize_spacing"])
                report_path=QA_LOG_ROOT/f'qa_auto_repair_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.json'
                core.save_json(report_path,result)
                contexts=[]
                if origin=="review":
                    for row in result.get("files") or []:
                        source_path=Path(row.get("source_file") or ""); target_path=Path(row.get("target_file") or "")
                        if not source_path.exists() or not target_path.exists(): continue
                        lang,source_entries,_=core.parse_localization_file(source_path)
                        _,target_entries,_=core.parse_localization_file(target_path)
                        contexts.append({"source_path":source_path,"target_path":target_path,"lang":lang,
                                         "source_entries":source_entries,"target_entries":target_entries,
                                         "issues":list(row.get("issues") or [])})
                self.events.put(("qa_auto_repair_done",(origin,result,report_path,contexts)))
            except Exception as exc:
                self.events.put(("qa_auto_repair_error",(origin,type(exc).__name__,str(exc))))
        self.qa_repair_thread=threading.Thread(target=work,daemon=True,name=f"qa-auto-repair-{origin}")
        self.qa_repair_thread.start(); self._refresh_operation_states()

    def _apply_qa_auto_repair_done(self, origin, result, report_path, contexts):
        self.qa_repair_thread=None; self.qa_repair_controller=None; self._qa_repair_origin=None
        summary=result.get("summary") or {}; failures=list(result.get("failures") or [])
        text=(i18n.t('u3.qa_repair_summary', initial_errors=summary.get('initial_errors',0), final_errors=summary.get('final_errors',0), resolved_errors=summary.get('resolved_errors',0), repaired_keys=summary.get('repaired_keys',0), warnings=summary.get('warnings',0), notices=summary.get('notices',0), failed_files=summary.get('failed_files',0), spaces_removed=summary.get('spaces_removed',0)))
        if origin=="review":
            self.review_last_qa_repair_result=result
            self._apply_review_qa_batch_loaded(contexts,failures)
            self.review_last_qa_repair_result=result
            self.qa_summary_var.set(i18n.t('u3.qa_repair_complete_log', text=text))
        elif origin=="chinese":
            self._append_chinese_log(i18n.t('u3.qa_repair_complete_log', text=text))
            self._append_chinese_log(i18n.t('u3.repair_log', report_path=report_path))
        else:
            self._append_log(i18n.t('u3.qa_repair_complete_log', text=text))
            self._append_log(i18n.t('u3.repair_log', report_path=report_path))
        self._refresh_operation_states()
        self._set_llm_idle(i18n.t('u3.llm_idle'),i18n.t('u3.qa_repair_complete'))
        message=(i18n.t('u3.qa_repair_complete_message', text=text, backup_dir=result.get('backup_dir',''), report_path=report_path))
        if result.get("interrupted"):
            messagebox.showinfo(APP_NAME,i18n.t('u3.qa_repair_stopped', text=text, report_path=report_path))
        elif failures: messagebox.showwarning(APP_NAME,message)
        else: messagebox.showinfo(APP_NAME,message)

    def _apply_qa_repair_progress(self, payload):
        stage=str(payload.get("stage") or "")
        file_no=int(payload.get("file_no",0) or 0); file_total=int(payload.get("file_total",0) or 0)
        filename=Path(payload.get("target_file") or payload.get("source_file") or "").name
        labels={
            "file_start":i18n.t('u3.file_start'), "initial_qa":i18n.t('u3.initial_qa'), "backup":i18n.t('u3.backup'),
            "repair_pass":i18n.t('u3.repair_pass'), "mechanical_repair":i18n.t('u3.mechanical_repair'),
            "llm_retranslate":i18n.t('u3.llm_retranslate'), "recheck":i18n.t('u3.recheck'),
            "final_qa":i18n.t('u3.final_qa'), "rollback":i18n.t('u3.rollback'), "file_done":i18n.t('u3.file_done'),
        }
        stage_label=labels.get(stage,stage or i18n.t('u3.processing'))
        progress=f"{file_no}/{file_total}" if file_total else ""
        self.llm_operation=i18n.t('u3.qa_auto_repair')
        self.llm_banner.config(bg="#4f46e5")
        self.llm_status_label.config(bg="#4f46e5",fg="white")
        self.llm_detail_label.config(bg="#4f46e5",fg="white")
        self.llm_status_var.set(i18n.t('u3.qa_repair_stage', stage_label=stage_label))
        detail=" / ".join(x for x in (progress,filename) if x)
        if payload.get("repairable_errors") is not None: detail = i18n.t('u3.repairable_detail', repairable_errors=payload.get('repairable_errors'), detail=detail)
        if payload.get("repair_keys") is not None: detail = i18n.t('u3.repair_keys_detail', repair_keys=payload.get('repair_keys'), detail=detail)
        self.llm_detail_var.set(detail or i18n.t('u3.checking_progress'))
        self.llm_stop_btn.config(state="normal")
        origin=getattr(self,"_qa_repair_origin",None)
        if origin=="review":
            self.qa_summary_var.set(i18n.t('u3.qa_repair_progress', progress=progress, filename=filename, stage_label=stage_label))
        if stage=="file_done":
            summary=(i18n.t('u3.qa_file_summary', progress=progress, filename=filename, initial_errors=payload.get('initial_errors',0), final_errors=payload.get('final_errors',0), repaired=payload.get('repaired',0)))
            if origin=="chinese": self._append_chinese_log(i18n.t('u3.qa_repair_file_log', summary=summary))
            elif origin=="normal": self._append_log(i18n.t('u3.qa_repair_file_log', summary=summary))

    def _apply_qa_auto_repair_error(self, origin, error_type, message):
        self.qa_repair_thread=None; self.qa_repair_controller=None; self._qa_repair_origin=None
        self._refresh_operation_states(); self._set_llm_idle(i18n.t('u3.llm_idle'),i18n.t('u3.qa_repair_failed'))
        if origin=="review": self.qa_summary_var.set(i18n.t('u3.qa_repair_error_context'))
        record_error(i18n.t('u3.qa_repair'),detail=f"{error_type}: {message}")
        messagebox.showerror(APP_NAME,i18n.t('u3.qa_repair_error', error_type=error_type, message=message))

    def run_selected_translation_qa(self):
        """Back up, QA, and automatically repair selected normal queue items."""
        entries=self._selected_normal_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,i18n.t('u3.select_qa_items')); return
        pairs=[]
        for _idx,item in entries:
            inp=Path(item.get("input", "")); out=Path(item.get("output", ""))
            if not inp.exists(): continue
            target_lang=_item_target_lang(item)
            if target_lang == core.DEFAULT_TARGET_LANG:
                pairs.extend(core.collect_translation_qa_pairs(inp,out,("english","simp_chinese")))
            else:
                pairs.extend(core.collect_translation_qa_pairs(inp,out,None,target_lang=target_lang))
        self._start_manual_qa_repair(pairs,"normal")

    def change_output(self):
        if self._normal_queue_locked(): return
        sel=self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, i18n.t('u1.output_help'))
            return
        current = self.queue_items[int(sel[0])].get("output", "")
        initial = str(Path(current).parent) if current else str(_automatic_output_root())
        p=filedialog.askdirectory(title=i18n.t('u1.selected_output'), initialdir=initial)
        if p:
            self.queue_items[int(sel[0])]["output"]=p
            self.queue_items[int(sel[0])]["custom_output"]=True
            self._refresh_queue_tree()
            self.save_session(active=bool(self.worker and self.worker.is_alive()))

    def apply_settings_to_current_translation(self):
        """Compatibility button: apply current UI settings everywhere and to active translation."""
        return self.apply_translation_settings_everywhere(silent=False)

    def _item_has_remaining_translation_gap(self, item: dict) -> bool:
        """Return True when the produced Japanese output still misses translatable source keys."""
        try:
            _loc, mod_root = self._infer_mod_target_for_item(item)
            source_root = Path(mod_root) if mod_root else None
            output_root = Path(item.get("output", ""))
            if source_root and source_root.is_dir() and output_root.is_dir():
                return not core.analyze_external_translation_coverage(source_root, output_root).get("complete", True)
        except Exception:
            pass
        return False

    def _differential_language_completion(self, item: dict, source_language: str) -> dict:
        """Describe whether the current source language is complete while the opposite language still has gaps."""
        try:
            missing = self._translation_status_missing_for_item(item, source_language)
        except Exception as exc:
            record_error(i18n.t('u3.diff_completion_error'), exc, str(item.get("input", "")))
            return {"language_complete": False, "status_gap_total": 0, "current_missing": 0}
        total = int(missing.get("status_gap_total", 0) or 0)
        current = int(missing.get("count", 0) or 0)
        opposite = int(missing.get("opposite_only_count", 0) or 0)
        other = int(missing.get("other_unavailable_count", 0) or 0)
        complete = current == 0 and total > 0 and opposite == total and other == 0
        return {
            "language_complete": complete,
            "status_gap_total": total,
            "current_missing": current,
            "opposite_only_count": opposite,
            "opposite_language": missing.get("opposite_language", ""),
            "opposite_only_keys": list(missing.get("opposite_only_keys", [])),
        }

    def _language_complete_status_text(self, source_language: str, count: int) -> str:
        if source_language == "simp_chinese":
            return status_value("done_lang_chinese", count=count)
        return status_value("done_lang_normal", count=count)

    def _language_complete_notice_text(self, source_language: str, count: int) -> str:
        if source_language == "simp_chinese":
            return i18n.t('p0.chinese_based_translation_is_complete', count=count)
        return i18n.t('p0.standard_translation_is_complete_the', count=count)

    def _reset_item_for_full_translation(self, item: dict):
        was_diff = bool(item.get("diff_mode") or item.get("previous_cache") or item.get("diff"))
        item.pop("diff", None)
        item.pop("previous_cache", None)
        item.pop("diff_mode", None)
        # A differential run may have copied the previous cache into this job.
        # Ordinary translation must not silently reuse that copied cache.
        if was_diff:
            item["cache"] = str(self._new_cache_path(Path(item["input"])))
        if str(item.get("status", "")).startswith("差分"):
            item["status"] = status_value("waiting")

    def start_differential_queue(self, entries=None):
        entries=entries if entries is not None else self._selected_normal_queue_entries()
        self._start_differential_prepare(entries, mode='normal')

    def _start_differential_prepare(self, entries, mode='normal'):
        active_worker=self.chinese_worker if mode=='chinese' else self.worker
        if active_worker is not None: return
        if self.differential_prepare_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u3.diff_preparing')); return
        entries=list(entries or [])
        if not entries:
            messagebox.showinfo(APP_NAME,i18n.t('u3.select_diff_items')); return
        if mode!='chinese':
            stop,_warnings=_target_language_problems([item for _idx,item in entries], diff_requested=True)
            if stop:
                messagebox.showinfo(APP_NAME, stop); return
        repair_enabled=bool(self.repair_var.get())
        if mode=='chinese': self.chinese_progress_var.set(i18n.t('u3.diff_prepare_progress', count=len(entries)))
        else: self.progress_text.set(i18n.t('u3.diff_prepare_progress', count=len(entries)))
        def prepare_work():
            unavailable=[]; notices=[]; prepared=[]
            for pos,(idx,item) in enumerate(entries,1):
                target_lang = _overwrite_target_lang(self, item)
                source_language = 'simp_chinese' if mode == 'chinese' or target_lang == 'english' else 'english'
                self.events.put(('differential_prepare_progress',(mode,pos,len(entries),item.get('mod_name') or Path(item.get('input','')).name)))
                problem = _overwrite_language_problem(self, item) if target_lang != core.DEFAULT_TARGET_LANG else ""
                if problem:
                    name = item.get('mod_name') or Path(item.get('input','')).name
                    unavailable.append(f"{name}: {problem}"); continue
                if mode=='chinese': self._ensure_item_cache(item)
                diff=self._prepare_differential_cache(item,silent=True,mode=mode,repair_enabled=repair_enabled)
                if diff is None:
                    unavailable.append(item.get('mod_name') or Path(item.get('input','')).name); continue
                if target_lang != core.DEFAULT_TARGET_LANG:
                    missing_keys = diff.get('missing', {}).get('selected_keys', [])
                    if missing_keys:
                        loc, mod_root = self._infer_mod_target_for_item(item)
                        sparse = self._write_missing_source_subset(Path(loc), source_language, missing_keys,
                                                                   item.get('mod_name') or Path(mod_root).name) if loc and mod_root else None
                        if not sparse:
                            unavailable.append(item.get('mod_name') or Path(item.get('input','')).name); continue
                        item['mod_localization'] = str(loc)
                        item['mod_root'] = str(mod_root)
                        item['input'] = str(sparse)
                        item['target_lang'] = target_lang
                        item['missing_only'] = True
                        item['missing_keys'] = list(missing_keys)
                item['diff_mode']=True
                counts=diff.get('counts',{})
                changed_total=sum(int(counts.get(k,0) or 0) for k in ('added','changed','removed','added_files','removed_files','missing'))
                if changed_total==0 and diff.get('language_complete'):
                    n=int(diff.get('opposite_only_count',0) or 0); item['status']=self._language_complete_status_text(source_language,n)
                    notices.append(f"{item.get('mod_name') or Path(item.get('input','')).name}: "+self._language_complete_notice_text(source_language,n))
                elif changed_total==0:
                    item['status']=status_value("done_no_diff")
                else:
                    item['status']=status_value("waiting"); prepared.append(idx)
            self.events.put(('differential_prepare_done',(mode,prepared,unavailable,notices)))
        def work():
            try:
                prepare_work()
            except Exception as exc:
                self.events.put(('differential_prepare_error',(mode,str(exc))))
        self._differential_prepare_mode=mode
        self.differential_prepare_thread=threading.Thread(target=work,daemon=True,name=f'differential-prepare-{mode}'); self.differential_prepare_thread.start()
        self._refresh_operation_states()

    def _apply_differential_prepare_done(self, mode, prepared_indices, unavailable, language_complete_notices):
        self.differential_prepare_thread=None
        self._differential_prepare_mode=None
        if mode=='chinese': self._refresh_chinese_queue_tree()
        else: self._refresh_queue_tree()
        if self._closing:
            self._save_workspace_state("differential_prepare_stopped_for_exit")
            return
        if unavailable:
            msg=i18n.t('u3.diff_unavailable', value='\n'.join(unavailable[:10]))
            if language_complete_notices: msg = i18n.t('u3.language_completed_list', value='\n'.join(language_complete_notices[:10]), prefix=msg)
            messagebox.showinfo(APP_NAME,msg)
        if prepared_indices:
            if language_complete_notices: messagebox.showinfo(APP_NAME,i18n.t('u3.some_completed', value='\n'.join(language_complete_notices[:10])))
            if mode=='chinese': self._start_chinese_selected(prepared_indices,diff_requested=True)
            else: self._start_normal_selected(prepared_indices,diff_requested=True)
        elif language_complete_notices and not unavailable:
            messagebox.showinfo(APP_NAME,'\n'.join(language_complete_notices[:10]))
        elif not unavailable:
            messagebox.showinfo(APP_NAME,i18n.t('u3.no_diff_gaps'))

    def start_queue(self):
        if self._closing: return
        if self.worker is not None:
            return
        if not self.queue_items:
            messagebox.showinfo(APP_NAME,i18n.t('u1.empty_queue')); return
        entries = self._selected_normal_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME, i18n.t('u1.select_translation_items'))
            return
        mode = self._ask_translation_mode(i18n.t('u1.normal_method'))
        if mode is None:
            return
        if mode == "diff":
            self.start_differential_queue(entries)
            return
        self._prepare_selected_for_full_translation(entries)
        self._refresh_queue_tree()
        self._start_normal_selected([idx for idx, _item in entries], diff_requested=False)

    def _start_normal_selected(self, selected_indices, diff_requested=False, _llm_ready=False):
        if self._closing: return
        if self.worker is not None: return
        selected_indices = sorted(set(int(x) for x in selected_indices if 0 <= int(x) < len(self.queue_items)))
        if not selected_indices:
            messagebox.showinfo(APP_NAME, i18n.t('u1.select_translation_items_period')); return
        if not _llm_ready:
            preset_var=getattr(self,"preset_var",None)
            stop,warnings=_target_language_problems([self.queue_items[i] for i in selected_indices], diff_requested,
                                                    preset_var.get() if preset_var is not None else "")
            if stop:
                messagebox.showinfo(APP_NAME, stop); return
            if warnings and not messagebox.askyesno(i18n.t('u1.unsupported_language'), i18n.t("u1.language_warning", warnings="\n\n".join(warnings)), icon="warning"):
                return
            indices=tuple(selected_indices)
            self._begin_llm_preflight(i18n.t('u1.normal_translation'),
                lambda:self._start_normal_selected(indices,diff_requested=diff_requested,_llm_ready=True))
            return
        for idx in selected_indices:
            self._ensure_isolated_item_output(self.queue_items[idx], mode="normal")
            app_state.ensure_queue_item_id(self.queue_items[idx])
        self._refresh_queue_tree()
        self._clear_log(); self.progress["value"]=0
        self.llm_operation = i18n.t('u1.translation')
        self.controller=core.TranslationController(progress_callback=lambda x:self.events.put(("progress",x)), checkpoint_callback=self._checkpoint)
        self.controller.update_runtime_settings(
            provider=self.provider_var.get(), url=self.url_var.get().strip(), model=self.model_var.get().strip(),
            api_key=self.api_key_var.get().strip(), preset=self.preset_var.get(),
            batch_size=max(1,self.batch_var.get()), workers=max(1,self.workers_var.get()),
            glossary_path=self.glossary_path_var.get().strip() or None, dual_source=False)
        self.translation_start_settings={
            "provider":self.provider_var.get(), "url":self.url_var.get().strip(), "model":self.model_var.get().strip(),
            "api_key":self.api_key_var.get().strip(), "preset":self.preset_var.get(),
            "batch":max(1,self.batch_var.get()), "workers":max(1,self.workers_var.get()),
            "glossary":self.glossary_path_var.get().strip() or None, "dual":False,
            "repair":self.repair_var.get(), "autoqa":self.autoqa_var.get(),
            "normalize_spacing":_normalize_spacing_enabled(self)}
        self._active_normal_item_ids = [app_state.ensure_queue_item_id(self.queue_items[idx]) for idx in selected_indices]
        mode_label = i18n.t('u1.diff_only') if diff_requested else i18n.t('u1.full_translation')
        self._append_log(i18n.t('u1.translation_started', count=len(selected_indices), mode=mode_label))
        self._append_log(i18n.t('u1.connection', provider=self.provider_var.get(), model=self.model_var.get().strip() or i18n.t('u1.model_unspecified'), batch=max(1,self.batch_var.get()), workers=max(1,self.workers_var.get())))
        self.start_btn.config(state="disabled"); self.pause_btn.config(state="normal",text=i18n.t('u1.pause')); self.stop_btn.config(state="normal")
        self.worker=threading.Thread(target=self._queue_worker,daemon=True); self.worker.start()
        self._refresh_operation_states()
        self.save_session(active=True)

    def _queue_worker(self):
        interrupted = False
        completed_ids = set()
        recovered_ids = set()
        unresolved_ids = set()
        queue_error_records = []
        active = list(getattr(self, "_active_normal_item_ids", []))
        if not active:
            app_state.ensure_queue_item_ids(self.queue_items)
            active = [app_state.ensure_queue_item_id(item) for item in self.queue_items]

        def item_label(item):
            return item.get("mod_name") or Path(item.get("input", "")).name

        def run_item(item_id, pos, total, retry_pass=False):
            item=app_state.queue_item_by_id(self.queue_items,item_id)
            if item is None:
                raise RuntimeError(i18n.t('u1.queue_item_lost'))
            i=app_state.queue_index_by_id(self.queue_items,item_id)
            self.current_queue_index=i
            item["status"]=status_value("retrying_errors") if retry_pass else status_value("translating")
            self.events.put(("queue_refresh",None))
            phase = i18n.t("u1.queue_retry", mod=item_label(item), pos=pos+1, total=total) if retry_pass else i18n.t("u1.queue_start", mod=item_label(item), pos=pos+1, total=total)
            self.events.put(("normal_log", phase))
            self._checkpoint({"queue_index":i,"queue_item_id":item_id,"retry_pass":retry_pass})
            target_lang=_item_target_lang(item)
            cache_file=_cache_for_target(self._ensure_item_cache(item), target_lang)
            st=getattr(self,"translation_start_settings",{})
            glossary_path=(st.get("glossary") or None) if target_lang == core.DEFAULT_TARGET_LANG else _existing_language_glossary(st.get("glossary"),target_lang)
            if target_lang != core.DEFAULT_TARGET_LANG:
                glossary_note=i18n.t('u1.glossary_file', name=glossary_path.name) if glossary_path else i18n.t('u1.no_glossary')
                self.events.put(("normal_log", i18n.t('u1.translation_target', target_name=_target_lang_choice(target_lang), glossary=glossary_note)))
            result=core.run_translation(
                item["input"], item["output"], model=st.get("model", ""), url=st.get("url", ""),
                workers=max(1,int(st.get("workers",1) or 1)), batch_size=max(1,int(st.get("batch",40) or 40)), cache_path=cache_file,
                resume=True, verbose=True, include_target_files=bool(st.get("repair",True)), controller=self.controller,
                glossary_path=glossary_path,
                preset=st.get("preset","CK3"),
                dual_source=False, auto_qa=bool(st.get("autoqa",True)),
                provider=st.get("provider","Ollama"), api_key=st.get("api_key", ""),
                qa_backup_root=BACKUP_ROOT/"QA自動修復", target_lang=target_lang,
                normalize_spacing=bool(st.get("normalize_spacing", True)))
            self._register_cache_job(item)
            skipped=int(result.get("skipped",0) or 0)
            failed=int(result.get("failed",0) or 0)
            warnings=int(result.get("warnings",0) or 0)
            item["translation_error_summary"]={
                "skipped_files":skipped, "failed_jobs":failed,
                "warnings":warnings,
                "error_report":result.get("error_report", ""),
                "encoding_recoveries":len(result.get("encoding_recoveries") or []),
                "retry_pass_completed":bool(retry_pass),
            }
            item["translation_error_report"]=result.get("error_report", "")
            self.events.put(("normal_log", i18n.t('u1.processing_result', mod=item_label(item), processed=result.get('processed',0), jobs=result.get('jobs',0), failed=failed, skipped=skipped, warnings=warnings)))
            self.events.put(("normal_log", i18n.t('u1.spaces_removed', count=result.get('spaces_removed',0))))
            if bool(st.get("autoqa",True)):
                self.events.put(("normal_log", i18n.t('u1.auto_qa_result', errors=result.get('qa_errors',0), warnings=result.get('qa_warnings',0), notices=result.get('qa_notices',0), repaired=result.get('qa_repaired',0))))
                if result.get("qa_report"):
                    self.events.put(("normal_log", i18n.t('u1.qa_report', path=result.get('qa_report'))))
                if result.get("qa_backup"):
                    self.events.put(("normal_log", i18n.t('u1.qa_backup', path=result.get('qa_backup'))))
            if result.get("encoding_recoveries"):
                self.events.put(("normal_log", i18n.t('u1.encoding_repaired', mod=item_label(item), count=len(result.get('encoding_recoveries') or []))))
            if skipped or failed or warnings:
                self.events.put(("normal_log", i18n.t('u1.error_report', path=result.get('error_report',''))))
            return item, result

        def set_completed_status(item, result, retry_pass=False):
            item_id=app_state.ensure_queue_item_id(item)
            skipped=int(result.get("skipped",0) or 0)
            failed=int(result.get("failed",0) or 0)
            warnings=int(result.get("warnings",0) or 0)
            unresolved=bool(skipped or failed)
            if unresolved:
                unresolved_ids.add(item_id)
                item["status"]=(status_value("warn_retry", skipped=skipped, failed=failed) if not retry_pass
                                else status_value("done_unresolved", skipped=skipped, failed=failed))
                return
            if item_id in unresolved_ids:
                unresolved_ids.discard(item_id)
                recovered_ids.add(item_id)
            if warnings:
                item["status"]=status_value("done_warnings", count=warnings)
                return
            if item.get("diff_mode"):
                lang_done = self._differential_language_completion(item, "english")
                if lang_done.get("language_complete"):
                    item["status"] = self._language_complete_status_text("english", int(lang_done.get("opposite_only_count", 0) or 0))
                elif self._item_has_remaining_translation_gap(item):
                    item["status"] = status_value("done_partial_gap")
                else:
                    item["status"] = status_value("done_diff_updated")
            elif self._item_has_remaining_translation_gap(item):
                item["status"] = status_value("done_partial_gap")
            else:
                item["status"] = status_value("done")

        try:
            for pos,item_id in enumerate(active):
                try:
                    item,result=run_item(item_id,pos,len(active),retry_pass=False)
                    if result.get("interrupted"):
                        interrupted = True
                        item["status"]=status_value("interrupted_resumable")
                        self.events.put(("queue_refresh",None))
                        self._write_session_file(active=True,restore_on_launch=True)
                        break
                    completed_ids.add(item_id)
                    set_completed_status(item,result,retry_pass=False)
                except core.StopRequested:
                    interrupted=True
                    item=app_state.queue_item_by_id(self.queue_items,item_id)
                    if item: item["status"]=status_value("interrupted_resumable")
                    break
                except Exception as exc:
                    item=app_state.queue_item_by_id(self.queue_items,item_id)
                    record_error(i18n.t('u1.queue_item_error', mod=item_label(item or {})),exc)
                    queue_error_records.append({
                        "phase":"first_pass", "item_id":item_id,
                        "mod":item_label(item or {}), "error_type":type(exc).__name__,
                        "message":str(exc), "action":i18n.t('u1.defer_retry'),
                    })
                    unresolved_ids.add(item_id)
                    if item:
                        item["status"]=status_value("error_retry_later")
                        item["translation_error_summary"]={"queue_error":str(exc),"retry_pass_completed":False}
                    self.events.put(("normal_log",i18n.t('u1.retry_warning', mod=item_label(item or {}), error_type=type(exc).__name__, error=exc)))
                self.events.put(("queue_refresh",None))
                if pos < len(active)-1:
                    self._write_session_file(active=True,restore_on_launch=True)

            # Finish the healthy queue first. Then retry only unresolved items once,
            # using conservative concurrency so malformed responses are isolated.
            if not interrupted and unresolved_ids:
                retry_ids=[item_id for item_id in active if item_id in unresolved_ids]
                self.events.put(("normal_log",i18n.t('u1.retry_started', count=len(retry_ids))))
                previous_runtime=self.controller.get_runtime_settings() if self.controller else {}
                if self.controller:
                    self.controller.update_runtime_settings(batch_size=min(10,max(1,int(previous_runtime.get("batch_size",10) or 10))),workers=1)
                try:
                    for retry_pos,item_id in enumerate(retry_ids):
                        try:
                            item,result=run_item(item_id,retry_pos,len(retry_ids),retry_pass=True)
                            if result.get("interrupted"):
                                interrupted=True
                                item["status"]=status_value("interrupted_resumable")
                                break
                            completed_ids.add(item_id)
                            set_completed_status(item,result,retry_pass=True)
                        except core.StopRequested:
                            interrupted=True
                            break
                        except Exception as exc:
                            item=app_state.queue_item_by_id(self.queue_items,item_id)
                            record_error(i18n.t('u1.queue_retry_error', mod=item_label(item or {})),exc)
                            queue_error_records.append({
                                "phase":"retry_pass", "item_id":item_id,
                                "mod":item_label(item or {}), "error_type":type(exc).__name__,
                                "message":str(exc), "action":i18n.t('u1.record_unresolved'),
                            })
                            if item:
                                item["status"]=status_value("unresolved_error")
                                summary=dict(item.get("translation_error_summary") or {})
                                summary.update({"queue_error":str(exc),"retry_pass_completed":True})
                                item["translation_error_summary"]=summary
                            self.events.put(("normal_log",i18n.t('u1.unresolved', mod=item_label(item or {}), error_type=type(exc).__name__, error=exc)))
                        self.events.put(("queue_refresh",None))
                        self._write_session_file(active=True,restore_on_launch=True)
                finally:
                    if self.controller and previous_runtime:
                        self.controller.update_runtime_settings(**previous_runtime)
            if not interrupted:
                keep_for_review=bool(unresolved_ids)
                self._write_session_file(active=keep_for_review,restore_on_launch=keep_for_review)
            queue_report_path=UNATTENDED_LOG_ROOT / f"unattended_translation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            try:
                core.save_json(queue_report_path,{
                    "generated_at":datetime.now().isoformat(timespec="seconds"),
                    "app_version":APP_VERSION, "interrupted":interrupted,
                    "selected_total":len(active), "completed_items":len(completed_ids),
                    "recovered_items":len(recovered_ids), "unresolved_items":len(unresolved_ids),
                    "queue_errors":queue_error_records,
                    "items":[{
                        "item_id":item_id,
                        "mod":item_label(app_state.queue_item_by_id(self.queue_items,item_id) or {}),
                        "status":(app_state.queue_item_by_id(self.queue_items,item_id) or {}).get("status",""),
                        "summary":(app_state.queue_item_by_id(self.queue_items,item_id) or {}).get("translation_error_summary",{}),
                        "error_report":(app_state.queue_item_by_id(self.queue_items,item_id) or {}).get("translation_error_report",""),
                    } for item_id in active],
                })
                self.events.put(("normal_log",i18n.t('u1.unattended_report', path=queue_report_path)))
            except Exception as report_exc:
                record_error(i18n.t('u1.report_save'),report_exc)
                queue_report_path=Path("")
            self.events.put(("done", {
                "interrupted": interrupted,
                "processed_items": len(completed_ids),
                "selected_total": len(active),
                "unresolved_items": len(unresolved_ids),
                "recovered_items": len(recovered_ids),
                "queue_report": str(queue_report_path) if queue_report_path else "",
            }))
        except Exception as exc:
            record_error(i18n.t('u1.fatal_translation'), exc)
            self.events.put(("fatal",str(exc)))

    def toggle_pause(self):
        if not self.controller: return
        if self.controller.pause_event.is_set():
            self.controller.resume(); self.pause_btn.config(text=i18n.t('u1.pause')); self.progress_text.set(i18n.t('u1.resumed'))
        else:
            self.controller.pause(); self.pause_btn.config(text=i18n.t('u1.resume')); self.progress_text.set(i18n.t('u1.paused'))
        self.save_session(active=True)

    def save_and_stop(self):
        if self.controller:
            self.save_session(active=True); self.controller.request_stop(save=True)
            self.progress_text.set(i18n.t('p0.saving_and_stopping_waiting_for'))
            self.stop_btn.config(state="disabled")

    # ---------------- persistent Translation Status / Total Diagnosis state ----------------
    @staticmethod
    def _json_safe_state(value):
        """Convert runtime diagnostic structures (sets/Path/etc.) to JSON-safe data."""
        if isinstance(value, dict):
            return {str(k): App._json_safe_state(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [App._json_safe_state(v) for v in value]
        if isinstance(value, set):
            return [App._json_safe_state(v) for v in sorted(value, key=lambda x: str(x))]
        if isinstance(value, Path):
            return str(value)
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    def _save_shared_mod_state_cache(self, reason="update"):
        """Mirror classification/relation state into キャッシュ for cross-tab recovery."""
        try:
            payload = {
                "schema": 2,
                "mod_status_cache_version": MOD_STATUS_CACHE_VERSION,
                "relation_algorithm_version": core.TRANSLATION_RELATION_ALGORITHM_VERSION,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "saved_at_ns": time.time_ns(),
                "reason": reason,
                "classification": self._json_safe_state(getattr(self, "mod_classification_cache", {})),
                "relations": self._json_safe_state(getattr(self, "mod_relation_overrides", {})),
            }
            core.save_json(SHARED_MOD_STATE_CACHE_PATH, payload)
        except Exception as exc:
            record_error(i18n.t('u5.save_shared_state'), exc)

    def _restore_shared_mod_state_cache(self):
        """Use the shared cache as a safety fallback if the primary cache files are missing/incomplete."""
        try:
            data = load_persistent_json(SHARED_MOD_STATE_CACHE_PATH, {}, i18n.t('u7.shared_mod_state'))
            if not isinstance(data, dict):
                return
            cached_cls = data.get("classification") if isinstance(data.get("classification"), dict) else {}
            cached_rel = data.get("relations") if isinstance(data.get("relations"), dict) else {}
            changed = False
            if cached_cls:
                cur = getattr(self, "mod_classification_cache", {})
                cur_mods = dict((cur or {}).get("mods") or {})
                for key, row in dict(cached_cls.get("mods") or {}).items():
                    if key not in cur_mods:
                        cur_mods[key] = row
                        changed = True
                    elif isinstance(row, dict) and isinstance(cur_mods[key], dict):
                        for target_lang, value in (row.get("had_target_at_first_seen") or {}).items():
                            targets = cur_mods[key].setdefault("had_target_at_first_seen", {})
                            if target_lang not in targets:
                                targets[target_lang] = value
                                changed = True
                if changed:
                    self.mod_classification_cache["mods"] = cur_mods
                    self.mod_classification_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    core.save_json(MOD_CLASSIFICATION_CACHE_PATH, self.mod_classification_cache)
            rel_changed = False
            if cached_rel:
                cur_rel = getattr(self, "mod_relation_overrides", {})
                cur_mods = dict((cur_rel or {}).get("mods") or {})
                for key, row in dict(cached_rel.get("mods") or {}).items():
                    if key not in cur_mods:
                        cur_mods[key] = row
                        rel_changed = True
                for target_lang, language_data in (cached_rel.get("languages") or {}).items():
                    if target_lang not in core.TARGET_LANGUAGES or target_lang == "japanese":
                        continue
                    target_mods = _relation_language_items(self.mod_relation_overrides, "mods", target_lang, create=True)
                    for key, row in (language_data.get("mods") or {}).items():
                        if key not in target_mods:
                            target_mods[key] = row
                            rel_changed = True
                if rel_changed:
                    self.mod_relation_overrides["mods"] = cur_mods
                    self.mod_relation_overrides["updated_at"] = datetime.now().isoformat(timespec="seconds")
                    core.save_json(MOD_RELATION_OVERRIDES_PATH, self.mod_relation_overrides)
            if changed or rel_changed:
                self._save_shared_mod_state_cache("fallback_restore")
        except Exception as exc:
            record_error(i18n.t('u7.shared_mod_state_cache_restoration'), exc)

    def _save_translation_status_state(self, reason="update"):
        """Persist the visible Translation Status state independently from scan-signature cache."""
        if threading.current_thread() is not threading.main_thread():
            try:
                self.after(0, lambda r=reason: self._save_translation_status_state(r))
            except Exception:
                pass
            return
        try:
            pending = getattr(self, "_translation_status_save_after_id", None)
            if pending is not None:
                try:
                    self.after_cancel(pending)
                except Exception:
                    pass
                self._translation_status_save_after_id = None
            self._translation_status_pending_reason = ""
            selected_paths = []
            if hasattr(self, "mod_status_tree"):
                for row in self._selected_mod_status_results():
                    raw = row.get("path")
                    if raw and raw not in selected_paths:
                        selected_paths.append(str(raw))
            target_lang = _current_target_lang(self)
            payload = {
                "schema": TRANSLATION_STATUS_SNAPSHOT_SCHEMA,
                "target_lang": target_lang,
                "mod_status_cache_version": MOD_STATUS_CACHE_VERSION,
                "relation_algorithm_version": core.TRANSLATION_RELATION_ALGORITHM_VERSION,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "saved_at_ns": time.time_ns(),
                "reason": reason,
                "results": self._json_safe_state([
                    _compact_translation_status_result(row)
                    for row in list(getattr(self, "mod_research_results", []) or [])
                    if _status_matches_language(row, target_lang)
                ]),
                "selected_paths": selected_paths,
                "summary": self._workspace_scalar(getattr(self, "mod_status_summary_var", None), ""),
                # Search is a transient view filter. Persisting it made a valid
                # restored result set appear empty on the next launch.
                "search": "",
            }
            core.save_json(_translation_status_path(target_lang), payload)
            self._restore_status_snapshot_cache = payload
            self._restore_status_rows_cache = None
            self._save_shared_mod_state_cache("translation_status:" + str(reason))
        except Exception as exc:
            record_error(i18n.t('u6.save_translation_status_cache'), exc)

    def _schedule_translation_status_state_save(self, reason="update", delay_ms=750):
        """Coalesce rapid status-row events into one main-thread snapshot write."""
        self._translation_status_pending_reason = str(reason)
        pending = getattr(self, "_translation_status_save_after_id", None)
        if pending is not None:
            try:
                self.after_cancel(pending)
            except Exception:
                pass
        def flush():
            self._translation_status_save_after_id = None
            pending_reason = self._translation_status_pending_reason or reason
            self._translation_status_pending_reason = ""
            self._save_translation_status_state(pending_reason)
        self._translation_status_save_after_id = self.after(max(0, int(delay_ms)), flush)

    def _load_translation_status_snapshot(self, force_disk=False, *, target_lang=None):
        """Load the persisted Translation Status snapshot with a process-local cache.

        v0.11.56: this file can become large. Re-reading/re-decoding it repeatedly during
        application startup caused multi-second hangs and extreme transient memory use.
        """
        target_lang = target_lang or _current_target_lang(self)
        if not force_disk and self._restore_status_snapshot_cache is not None:
            if _status_matches_language(self._restore_status_snapshot_cache, target_lang):
                return self._restore_status_snapshot_cache
        try:
            data = load_persistent_json(_translation_status_path(target_lang), {}, i18n.t('u7.translation_status_state'))
            data = data if _status_matches_language(data, target_lang) else {}
            self._restore_status_snapshot_cache = data
            return data
        except Exception as exc:
            record_error(i18n.t('u7.loading_translation_status_state_cache'), exc)
            self._restore_status_snapshot_cache = {}
            return {}

    def _save_diagnostic_state(self, reason="update"):
        """Persist last Total Diagnosis results, selected targets, and per-key conflict decisions."""
        try:
            target_paths = []
            if hasattr(self, "diagnostic_target_tree"):
                for iid in self.diagnostic_target_tree.selection():
                    vals = self.diagnostic_target_tree.item(iid, "values")
                    if len(vals) >= 3 and vals[2]:
                        target_paths.append(str(vals[2]))
            payload = {
                "schema": 1,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "saved_at_ns": time.time_ns(),
                "reason": reason,
                "target_paths": target_paths,
                "summary": self._workspace_scalar(getattr(self, "diagnostic_summary_var", None), ""),
                "analyses": self._json_safe_state(list(getattr(self, "diagnostic_last_analyses", []) or [])),
                "conflict_choices": self._json_safe_state(dict(getattr(self, "diagnostic_conflict_choices", {}) or {})),
                "relation_choices": self._json_safe_state(dict(getattr(self, "diagnostic_relation_choices", {}) or {})),
            }
            core.save_json(DIAGNOSTIC_STATE_PATH, payload)
            self._save_shared_mod_state_cache("diagnostic:" + str(reason))
        except Exception as exc:
            record_error(i18n.t('u7.saving_diagnostic_state_cache'), exc)

    def _restore_diagnostic_state(self):
        if self.diagnostic_restore_thread and self.diagnostic_restore_thread.is_alive():
            return
        self.diagnostic_summary_var.set(i18n.t('u7.restoring_previous_diagnostics_in_the_background'))
        def work():
            try:
                data=load_persistent_json(DIAGNOSTIC_STATE_PATH,{},i18n.t('u7.diagnostic_state'))
                self.events.put(('diagnostic_state_restored',data if isinstance(data,dict) else {}))
            except Exception as exc:
                self.events.put(('diagnostic_state_restore_error',str(exc)))
        self.diagnostic_restore_thread=threading.Thread(target=work,daemon=True,name='diagnostic-state-restore')
        self.diagnostic_restore_thread.start()

    def _apply_restored_diagnostic_state(self, data):
        self.diagnostic_restore_thread=None
        try:
            self._restore_shared_mod_state_cache()
            if not isinstance(data,dict): return
            choices=data.get('conflict_choices') or {}
            if isinstance(choices,dict):
                self.diagnostic_conflict_choices={str(k):str(v) for k,v in choices.items() if v in {'source','translation','auto'}}
            relation_choices=data.get('relation_choices') or {}
            if isinstance(relation_choices,dict):
                self.diagnostic_relation_choices={str(k):str(v) for k,v in relation_choices.items() if v in {'source','translation'}}
            analyses=data.get('analyses') or []
            valid=[]
            if isinstance(analyses,list):
                for row in analyses:
                    if not isinstance(row,dict): continue
                    raw=row.get('path')
                    if raw and not Path(raw).exists(): continue
                    valid.append(row)
                if valid:
                    self.diagnostic_results=list(valid)
                    self._populate_diagnostic_results(valid)
            wanted={str(x) for x in (data.get('target_paths') or []) if x}
            if wanted and hasattr(self,'diagnostic_target_tree'):
                for iid in self.diagnostic_target_tree.get_children():
                    vals=self.diagnostic_target_tree.item(iid,'values')
                    if len(vals)>=3 and str(vals[2]) in wanted: self.diagnostic_target_tree.selection_add(iid)
            if valid:
                issues=sum(1 for a in valid for x in (a.get('issues') or []) if x.get('severity') in {'ERROR','WARN'})
                self.diagnostic_summary_var.set(i18n.t('u7.previous_diagnostics_restored_mods_items_to', count=len(valid), issues=issues))
                self._set_diagnostic_detail(i18n.t('u7.diagnostic_results_from_the_previous_session'))
            elif not analyses:
                self.diagnostic_summary_var.set(i18n.t('u7.waiting_for_diagnostics'))
        except Exception as exc:
            record_error(i18n.t('u7.diagnostic_state_cache_restoration'),exc)


    def _workspace_scalar(self, var, default=None):
        try:
            return var.get()
        except Exception:
            return default

    def _workspace_selected_paths(self):
        paths=[]
        try:
            for iid in self.discovered_mod_tree.selection():
                idx=int(str(iid).replace("loc_", ""))
                if 0 <= idx < len(self.detected_mod_locations):
                    raw=self.detected_mod_locations[idx].get("path")
                    if raw and raw not in paths: paths.append(str(raw))
        except Exception:
            pass
        if not paths:
            paths=[str(x) for x in (self.monitor_target_paths or []) if x]
        return paths

    def _collect_workspace_state(self, reason="autosave"):
        """Collect user-visible working state from all major tabs.

        Must be called on the Tk/main thread. API keys and transient controller/
        thread objects are deliberately excluded.
        """
        self.workspace_revision = max(0, int(getattr(self,"workspace_revision",0))) + 1
        try:
            tab_index=int(self.notebook.index(self.notebook.select()))
        except Exception:
            tab_index=0
        now_ns=time.time_ns()
        return {
            "schema_version":3,
            "app_version":APP_VERSION,
            "saved_at":datetime.now().isoformat(timespec="seconds"),
            "saved_at_ns":now_ns,
            "revision":self.workspace_revision,
            "reason":reason,
            "data_root":str(DATA_ROOT),
            "active_tab":tab_index,
            "active_tab_text":self.notebook.tab(self.notebook.select(), "text") if self.notebook.select() else "",
            "normal_translation":{
                "input":self._workspace_scalar(self.normal_input_var,""),
                "output":self._workspace_scalar(self.normal_output_var,str(OUTPUT_ROOT)),
                "queue":self.queue_items,
                "queue_index":self.current_queue_index,
            },
            "chinese_translation":{
                "target_lang":self._workspace_scalar(self.chinese_target_lang_var,core.DEFAULT_TARGET_LANG),
                "input":self._workspace_scalar(self.chinese_input_var,""),
                "output":self._workspace_scalar(self.chinese_output_var,str(OUTPUT_ROOT/"中国語基準翻訳")),
                "queue":self.chinese_queue_items,
                "queue_index":self.chinese_queue_index,
            },
            "qa_review":{
                "source":self._workspace_scalar(self.review_src_var,""),
                "target":self._workspace_scalar(self.review_dst_var,""),
            },
            "diff":{
                "source":self._workspace_scalar(self.diff_src_var,""),
                "target":self._workspace_scalar(self.diff_dst_var,""),
            },
            "glossary":{
                "path":self._workspace_scalar(self.glossary_path_var,str(DEFAULT_GLOSSARY)),
            },
            "models":{
                "provider":self._workspace_scalar(self.provider_var,"Ollama"),
                "url":self._workspace_scalar(self.url_var,""),
                "model":self._workspace_scalar(self.model_var,""),
                "preset":self._workspace_scalar(self.preset_var,"CK3"),
                "target_lang":self._workspace_scalar(self.target_lang_var,core.DEFAULT_TARGET_LANG),
                "batch":self._workspace_scalar(self.batch_var,40),
                "workers":self._workspace_scalar(self.workers_var,1),
                "performance_preset":ui_status.performance_preset_from_label(self._workspace_scalar(self.performance_preset_var,"standard")),
                "repair":bool(self._workspace_scalar(self.repair_var,True)),
                "normalize_spacing":_normalize_spacing_enabled(self),
                "dual":bool(self._workspace_scalar(self.dual_var,False)),
                "autoqa":bool(self._workspace_scalar(self.autoqa_var,True)),
                "chinese_autoqa":bool(self._workspace_scalar(self.chinese_autoqa_var,True)),
                "profile":self._workspace_scalar(self.profile_var,""),
            },
            "monitor":{
                "target_paths":[str(x) for x in (self.monitor_target_paths or [])],
                "interval":self._workspace_scalar(self.monitor_interval_var,15),
                "use_llm":bool(self._workspace_scalar(self.monitor_use_llm_var,True)),
                "check_translation_mods":bool(self._workspace_scalar(self.monitor_check_translation_mods_var,True)),
                "provider":self._workspace_scalar(self.monitor_provider_var,"Ollama"),
                "url":self._workspace_scalar(self.monitor_url_var,""),
                "model":self._workspace_scalar(self.monitor_model_var,""),
            },
            "translation_status":{
                "selected_location_paths":self._workspace_selected_paths(),
                "multi_select":bool(self._workspace_scalar(self.discovery_multi_select_var,False)),
                "search":"",
            },
            "translation_search":{
                "game":self._workspace_scalar(self.search_game_var,"Crusader Kings III"),
                "query":self._workspace_scalar(self.search_query_var,""),
                "selected_mod_paths":list(self.search_selected_mod_paths or []),
            },
        }

    def _save_workspace_state(self, reason="autosave"):
        if threading.current_thread() is not threading.main_thread():
            try: self.after(0, lambda r=reason:self._save_workspace_state(r))
            except Exception: pass
            return
        try:
            data=self._collect_workspace_state(reason)
            core.save_json(WORKSPACE_STATE_PATH,data)
        except Exception as e:
            record_error(i18n.t('u1.workspace_save'),e)

    def _workspace_autosave_tick(self):
        try:
            self._save_workspace_state("periodic")
        finally:
            try: self.after(15000,self._workspace_autosave_tick)
            except Exception: pass

    @staticmethod
    def _clear_stale_external_translation_relation(item):
        """Drop saved external-Japanese-Mod relationship metadata from older builds.

        Translation output/cache paths remain untouched.  A fresh Translation Status
        scan rebuilds relationships with the v0.11.33 weighted classifier.
        """
        if not isinstance(item, dict):
            return
        for key in (
            "external_translation_mod", "external_translation_path",
            "external_translation_localization", "external_translation_gap_count",
            "external_translation_complete", "external_translation_gaps",
            "external_translation_coverage", "external_translation_precision",
            "external_translation_score", "external_translation_confidence", "external_translation_reasons",
            "translation_candidate_mod", "translation_candidate_path", "translation_candidate_score",
            "translation_candidate_precision", "translation_candidate_coverage", "translation_candidate_reasons",
            "external_gap_keys",
        ):
            item.pop(key, None)

    def _restore_workspace_state(self):
        data=load_persistent_json(WORKSPACE_STATE_PATH,{},i18n.t('u7.workspace_state'))
        if not isinstance(data,dict) or not data:
            return
        self._workspace_restore_data=data
        stale_external_relations = str(data.get("app_version", "")) != APP_VERSION
        try: self.workspace_revision=max(0,int(data.get("revision",0) or 0))
        except Exception: self.workspace_revision=0
        saved_root=data.get("data_root")
        def remap(raw):
            return _remap_saved_data_path(raw,saved_root) if raw else raw
        try:
            n=data.get("normal_translation") or {}
            self.normal_input_var.set(remap(n.get("input","")) or "")
            self.normal_output_var.set(remap(n.get("output",str(OUTPUT_ROOT))) or str(OUTPUT_ROOT))
            self.queue_items=list(n.get("queue") or [])
            self.current_queue_index=int(n.get("queue_index",-1) or -1)
            for item in self.queue_items:
                if isinstance(item,dict):
                    if stale_external_relations:
                        self._clear_stale_external_translation_relation(item)
                    for k in ("input","output","cache","previous_cache"):
                        if item.get(k): item[k]=remap(item[k])
                    if item.get("status")==status_value("translating"): item["status"]=status_value("interrupted_resumable")
            self._refresh_queue_tree()

            z=data.get("chinese_translation") or {}
            chinese_target = z.get("target_lang", core.DEFAULT_TARGET_LANG)
            if chinese_target not in core.CHINESE_BASIS_TARGETS:
                chinese_target = core.DEFAULT_TARGET_LANG
            self.chinese_target_display_var.set(i18n.t("lang." + chinese_target))
            self._select_chinese_target_language()
            self.chinese_input_var.set(remap(z.get("input","")) or "")
            self.chinese_output_var.set(remap(z.get("output",str(OUTPUT_ROOT/"中国語基準翻訳"))) or str(OUTPUT_ROOT/"中国語基準翻訳"))
            self.chinese_queue_items=list(z.get("queue") or [])
            self.chinese_queue_index=int(z.get("queue_index",-1) or -1)
            for item in self.chinese_queue_items:
                if isinstance(item,dict):
                    if stale_external_relations:
                        self._clear_stale_external_translation_relation(item)
                    for k in ("input","output","cache","previous_cache"):
                        if item.get(k): item[k]=remap(item[k])
                    if item.get("status")==status_value("translating"): item["status"]=status_value("interrupted_resumable")
            self._refresh_chinese_queue_tree()

            q=data.get("qa_review") or {}; self.review_src_var.set(remap(q.get("source","")) or ""); self.review_dst_var.set(remap(q.get("target","")) or "")
            d=data.get("diff") or {}; self.diff_src_var.set(remap(d.get("source","")) or ""); self.diff_dst_var.set(remap(d.get("target","")) or "")
            g=data.get("glossary") or {}; self.glossary_path_var.set(remap(g.get("path",str(DEFAULT_GLOSSARY))) or str(DEFAULT_GLOSSARY))

            m=data.get("models") or {}
            self.provider_var.set(m.get("provider",self.provider_var.get())); self.url_var.set(m.get("url",self.url_var.get())); self.model_var.set(m.get("model",self.model_var.get()))
            self.preset_var.set(m.get("preset",self.preset_var.get())); self.batch_var.set(max(1,int(m.get("batch",self.batch_var.get()) or 40))); self.workers_var.set(max(1,int(m.get("workers",self.workers_var.get()) or 1)))
            self.normalize_spacing_var.set(bool(m.get("normalize_spacing",_normalize_spacing_enabled(self))))
            self.performance_preset_var.set(ui_status.performance_preset_label(ui_status.performance_preset_from_label(m.get("performance_preset",self.performance_preset_var.get())))); self.repair_var.set(bool(m.get("repair",self.repair_var.get()))); self.dual_var.set(bool(m.get("dual",self.dual_var.get())))
            self.autoqa_var.set(bool(m.get("autoqa",self.autoqa_var.get()))); self.chinese_autoqa_var.set(bool(m.get("chinese_autoqa",self.chinese_autoqa_var.get()))); self.profile_var.set(m.get("profile",self.profile_var.get()))
            self._set_target_lang(m.get("target_lang",self.target_lang_var.get()),save=False)

            mon=data.get("monitor") or {}
            self.monitor_target_paths=[str(x) for x in (mon.get("target_paths") or []) if x]
            self.monitor_path_var.set(self.monitor_target_paths[0] if self.monitor_target_paths else "")
            self.monitor_interval_var.set(max(3,int(mon.get("interval",self.monitor_interval_var.get()) or 15))); self.monitor_use_llm_var.set(bool(mon.get("use_llm",self.monitor_use_llm_var.get())))
            self.monitor_check_translation_mods_var.set(bool(mon.get("check_translation_mods",self.monitor_check_translation_mods_var.get()))); self.monitor_provider_var.set(mon.get("provider",self.monitor_provider_var.get())); self.monitor_url_var.set(mon.get("url",self.monitor_url_var.get())); self.monitor_model_var.set(mon.get("model",self.monitor_model_var.get()))
            if self.monitor_target_paths: self.monitor_target_summary_var.set(i18n.t('u7.monitored_locations_previous_state_restored', count=len(self.monitor_target_paths)))

            st=data.get("translation_status") or {}
            self._workspace_selected_location_paths=[str(x) for x in (st.get("selected_location_paths") or []) if x]
            self.discovery_multi_select_var.set(bool(st.get("multi_select",False))); self.mod_status_search_var.set("")
            sr=data.get("translation_search") or {}; self.search_game_var.set(sr.get("game",self.search_game_var.get())); self.search_query_var.set(sr.get("query","") or ""); self.search_selected_mod_paths=[str(x) for x in (sr.get("selected_mod_paths") or []) if x]
            try: self.after_idle(self.refresh_translation_search_mods)
            except Exception: pass
            try:
                wanted_text=str(data.get("active_tab_text") or "")
                selected=False
                if wanted_text:
                    for i in range(self.notebook.index("end")):
                        if self.notebook.tab(i,"text")==wanted_text:
                            self.notebook.select(i); selected=True; break
                if not selected:
                    idx=int(data.get("active_tab",0) or 0)
                    # v0.11.32 inserted 総合診断 before 設定. Preserve the old
                    # Settings/Help tab positions when restoring a pre-v0.11.32 workspace.
                    if str(data.get("app_version", "")) and str(data.get("app_version", "")) != APP_VERSION and idx >= 9:
                        idx += 1
                    if 0 <= idx < self.notebook.index("end"): self.notebook.select(idx)
            except Exception: pass
        except Exception as e:
            record_error(i18n.t('u7.workspace_state_restoration'),e)

    def _workspace_saved_at_ns(self):
        try:
            data=core.load_json(WORKSPACE_STATE_PATH,{})
            return int(data.get("saved_at_ns",0) or 0) if isinstance(data,dict) else 0
        except Exception:
            return 0

    # ---------------- session ----------------
    def _settings_dict(self):
        # Worker checkpoints must not read Tk variables directly.
        if threading.current_thread() is not threading.main_thread():
            st=dict(getattr(self,"translation_start_settings",{}) or {})
            return {"provider":st.get("provider",""),"url":st.get("url",""),"model":st.get("model",""),"preset":st.get("preset","CK3"),
                    "batch":st.get("batch",40),"workers":st.get("workers",1),"repair":st.get("repair",True),
                    "dual":st.get("dual",False),"autoqa":st.get("autoqa",True),"glossary":st.get("glossary") or str(DEFAULT_GLOSSARY)}
        return {"provider":self.provider_var.get(),"url":self.url_var.get(),"model":self.model_var.get(),"preset":self.preset_var.get(),
                "batch":self.batch_var.get(),"workers":self.workers_var.get(),"repair":self.repair_var.get(),
                "normalize_spacing":_normalize_spacing_enabled(self),
                "dual":self.dual_var.get(),"autoqa":self.autoqa_var.get(),"glossary":self.glossary_path_var.get()}

    def _append_resume_history(self, event: str, data: dict):
        """Append a compact, version-independent work history entry."""
        try:
            RESUME_HISTORY_PATH.parent.mkdir(parents=True,exist_ok=True)
            row={
                "timestamp":datetime.now().isoformat(timespec="seconds"),
                "event":event,
                "app_version":APP_VERSION,
                "schema_version":1,
                "active":bool(data.get("active")),
                "restore_on_launch":bool(data.get("restore_on_launch")),
                "queue_index":data.get("queue_index",0),
                "queue_count":len(data.get("queue",[]) or []),
            }
            with RESUME_HISTORY_PATH.open("a",encoding="utf-8") as fh:
                fh.write(json.dumps(row,ensure_ascii=False)+"\n")
        except Exception:
            pass

    def _write_session_file(self, active=False, restore_on_launch=False, checkpoint=None):
        """Persist the current work state independently of the application version.

        session.json is kept for backward compatibility. resume_state.json is the
        stable cross-version source used when a newly installed version cannot find
        or use the older transient session file.
        """
        data={
            "schema_version":1,
            "app_version":APP_VERSION,
            "version":APP_VERSION,
            "saved_at":datetime.now().isoformat(timespec="seconds"),
            "saved_at_ns":time.time_ns(),
            "state_revision":max(0,int(getattr(self,"workspace_revision",0))),
            "data_root":str(DATA_ROOT),
            "active":bool(active),
            "restore_on_launch":bool(restore_on_launch),
            "queue":self.queue_items,
            "queue_index":self.current_queue_index,
            "settings":self._settings_dict(),
        }
        if checkpoint is not None:
            data["checkpoint"]=checkpoint
        core.save_json(SESSION_PATH,data)
        core.save_json(RESUME_STATE_PATH,data)
        # Checkpoints may occur every batch; keep the human-readable history compact.
        if checkpoint is None:
            self._append_resume_history("state_saved",data)
            if threading.current_thread() is threading.main_thread():
                self._save_workspace_state("session_state_saved")

    def save_session(self,active=False,restore_on_launch=None):
        # 手動保存は次回起動時の強制復元対象にはしない。終了時保存だけ明示的にTrueを渡す。
        if restore_on_launch is None:
            restore_on_launch=bool(active)
        self._write_session_file(active=active,restore_on_launch=restore_on_launch)
        if not active:
            self.progress_text.set(i18n.t('p0.session_saved', RESUME_STATE_PATH=RESUME_STATE_PATH))

    def _checkpoint(self,payload):
        self._write_session_file(active=True,restore_on_launch=True,checkpoint=payload)

    def _load_resume_candidate(self):
        """Load only the newest restorable translation snapshot.

        A stale session file must never override a newer workspace state. Active
        checkpoints saved after the last workspace autosave remain eligible.
        """
        workspace_ns=self._workspace_saved_at_ns()
        candidates=[]
        for path in (SESSION_PATH,RESUME_STATE_PATH):
            try: data=core.load_json(path,{})
            except Exception: data={}
            if not isinstance(data,dict) or not data.get("queue"): continue
            if not (data.get("active") or data.get("restore_on_launch")): continue
            try: saved_ns=int(data.get("saved_at_ns",0) or 0)
            except Exception: saved_ns=0
            # New workspace snapshots are authoritative over older transient state.
            if workspace_ns and saved_ns and saved_ns < workspace_ns:
                continue
            candidates.append((saved_ns,path,data))
        if not candidates:
            return {},None
        _,path,data=max(candidates,key=lambda x:x[0])
        saved_root=data.get("data_root")
        stale_external_relations = str(data.get("app_version") or data.get("version") or "") != APP_VERSION
        for item in data.get("queue",[]) or []:
            if isinstance(item,dict):
                if stale_external_relations:
                    self._clear_stale_external_translation_relation(item)
                for key in ("input","cache","output","previous_cache"):
                    if item.get(key): item[key]=_remap_saved_data_path(item.get(key),saved_root)
        settings=data.get("settings") or {}
        if isinstance(settings,dict) and settings.get("glossary"):
            settings["glossary"]=_remap_saved_data_path(settings.get("glossary"),saved_root)
        return data,path

    def restore_session(self, data=None):
        if data is None:
            data,_=self._load_resume_candidate()
        if not data:
            messagebox.showinfo(APP_NAME,i18n.t('u7.no_saved_work')); return
        self.queue_items=data.get("queue",[])
        self.current_queue_index=max(0,int(data.get("queue_index",0) or 0))
        s=data.get("settings",{})
        self.provider_var.set(s.get("provider",self.provider_var.get())); self.url_var.set(s.get("url",self.url_var.get())); self.model_var.set(s.get("model",self.model_var.get())); self.preset_var.set(s.get("preset",self.preset_var.get()))
        self.normalize_spacing_var.set(bool(s.get("normalize_spacing", True)))
        self.batch_var.set(s.get("batch",40)); self.workers_var.set(s.get("workers",1)); self.repair_var.set(s.get("repair",True)); self.dual_var.set(s.get("dual",False)); self.autoqa_var.set(s.get("autoqa",True)); self.glossary_path_var.set(s.get("glossary",str(DEFAULT_GLOSSARY)))
        for item in self.queue_items:
            self._ensure_item_cache(item)
            if item.get("status") == "翻訳中": item["status"]=status_value("interrupted_resumable")
        previous_version=data.get("app_version") or data.get("version") or "不明"
        # 復元直後は古いactiveフラグを解除し、新バージョン形式へ移行して保存する。
        self._write_session_file(active=False,restore_on_launch=False)
        self._refresh_queue_tree()
        self._save_workspace_state("session_restored")
        self.progress_text.set(i18n.t('u7.work_restored_saved_by_v_start', previous_version=previous_version))

    def _offer_restore_session(self):
        data,path=self._load_resume_candidate()
        if not data:
            return
        previous_version=data.get("app_version") or data.get("version") or "不明"
        source_note=""
        if path==RESUME_STATE_PATH:
            source_note=i18n.t('u7.restoring_from_the_resume_log_shared')
        if messagebox.askyesno(APP_NAME,i18n.t('u7.unfinished_work_remains_from_your_last', previous_version=previous_version, source_note=source_note)):
            self.restore_session(data)
        else:
            self._disable_resume_offer()
            self._delete_session()

    def _disable_resume_offer(self):
        try:
            data=core.load_json(RESUME_STATE_PATH,{})
            if isinstance(data,dict) and data:
                data["active"]=False; data["restore_on_launch"]=False
                data["saved_at"]=datetime.now().isoformat(timespec="seconds")
                core.save_json(RESUME_STATE_PATH,data)
                self._append_resume_history("restore_declined",data)
        except Exception:
            pass

    def _delete_session(self):
        try: SESSION_PATH.unlink(missing_ok=True)
        except Exception: pass

    # ---------------- models ----------------
    def _set_llm_connection_error_status(self, provider, url, error=""):
        info=_llm_connection_alert_content(provider,url,self.model_var.get().strip(),error)
        self.llm_busy_count=0; self.llm_active_ids.clear(); self.llm_busy_since=None
        self.llm_banner.config(bg="#b91c1c")
        self.llm_status_label.config(bg="#b91c1c",fg="white")
        self.llm_detail_label.config(bg="#b91c1c",fg="white")
        self.llm_status_var.set(i18n.t('u5.llm_disconnected'))
        self.llm_detail_var.set(i18n.t('u5.connection_check_note', provider=info['provider'], endpoint=info['endpoint']))
        self.llm_stop_btn.config(state="disabled")

    def _close_llm_connection_alert(self, *, reset_key=False):
        win=getattr(self,"_llm_connection_alert_window",None)
        self._llm_connection_alert_window=None
        if reset_key: self._llm_connection_alert_key=""
        if win is not None:
            try: win.grab_release()
            except (tk.TclError,AttributeError): pass
            try: win.destroy()
            except (tk.TclError,AttributeError): pass

    def _show_llm_connection_alert(self, provider, url, model="", error="", *, context=None, retry_command=None, cancel_command=None, force=False):
        if self._closing: return
        if context is None: context=i18n.t("u5.llm_task")
        info=_llm_connection_alert_content(provider,url,model,error)
        key=f"{info['category']}|{info['provider']}|{info['endpoint']}"
        existing=getattr(self,"_llm_connection_alert_window",None)
        if existing is not None:
            try: existing.lift(); existing.focus_force(); return
            except (tk.TclError,AttributeError): self._llm_connection_alert_window=None
        if not force and self._llm_connection_alert_key==key:
            return
        self._llm_connection_alert_key=key
        self._set_llm_connection_error_status(provider,url,error)
        win=tk.Toplevel(self); self._llm_connection_alert_window=win
        win.title(info["title"]); win.geometry("720x440"); win.minsize(620,360)
        try: win.transient(self)
        except tk.TclError: pass
        header=tk.Frame(win,bg="#b91c1c",padx=20,pady=18); header.pack(fill="x")
        tk.Label(header,text="⚠  "+info["heading"],bg="#b91c1c",fg="white",font=("",20,"bold")).pack(anchor="w")
        body=ttk.Frame(win,padding=22); body.pack(fill="both",expand=True)
        ttk.Label(body,text=i18n.t('u5.cannot_start', context=context),font=("",13,"bold")).pack(anchor="w",pady=(0,12))
        ttk.Label(body,text=info["message"],justify="left",wraplength=660).pack(anchor="w",fill="x")
        buttons=ttk.Frame(body); buttons.pack(side="bottom",fill="x",pady=(18,0))
        def retry():
            self._close_llm_connection_alert(reset_key=True)
            (retry_command or self.refresh_models)()
        def settings():
            self._close_llm_connection_alert()
            self._llm_preflight_request=None
            self.notebook.select(self.tab_models)
        def cancel():
            self._close_llm_connection_alert()
            self._llm_preflight_request=None
            self.llm_preflight_thread=None
            self._refresh_operation_states()
            if cancel_command: cancel_command()
        ttk.Button(buttons,text=i18n.t('u5.retry_connection'),command=retry).pack(side="left")
        ttk.Button(buttons,text=i18n.t('u5.open_settings'),command=settings).pack(side="left",padx=(8,0))
        ttk.Button(buttons,text=i18n.t('u5.cancel_task'),command=cancel).pack(side="right")
        win.protocol("WM_DELETE_WINDOW",cancel)
        try: win.grab_set(); win.lift(); win.focus_force()
        except tk.TclError: pass

    def _launch_llm_preflight(self):
        request=self._llm_preflight_request
        if not request or self._closing: return
        token=uuid.uuid4().hex; request["token"]=token
        provider=request["provider"]; url=request["url"]; model=request["model"]; api_key=request["api_key"]
        self.connection_var.set(i18n.t('u5.checking_connection', provider=provider))
        self.llm_status_var.set(i18n.t('u5.llm_checking'))
        self.llm_detail_var.set(f"{provider} / {url}")
        def work():
            try:
                if not model:
                    raise RuntimeError(i18n.t('u5.no_translation_model'))
                models=core.list_models(provider,url,timeout=8,api_key=api_key)
                if core.normalize_provider(provider) in {"ollama","lmstudio"} and not models:
                    raise RuntimeError(i18n.t('u5.no_loaded_models'))
                warning=core.unusable_model_warning(provider,url,model) or core.reasoning_model_probe_warning(provider,url,model,api_key)
                if warning:
                    raise RuntimeError(warning)
                self.events.put(("llm_preflight_done",{"token":token,"models":models}))
            except Exception as exc:
                self.events.put(("llm_preflight_error",{"token":token,"error":str(exc)}))
        self.llm_preflight_thread=threading.Thread(target=work,daemon=True,name="llm-preflight")
        self.llm_preflight_thread.start(); self._refresh_operation_states()

    def _begin_llm_preflight(self, context, callback):
        if self.llm_preflight_thread is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u5.connection_check_busy')); return False
        provider=self.provider_var.get(); url=self.url_var.get().strip() or core.default_url_for_provider(provider)
        self._llm_preflight_request={"context":context,"callback":callback,"provider":provider,"url":url,
                                     "model":self.model_var.get().strip(),"api_key":self.api_key_var.get().strip()}
        self._launch_llm_preflight(); return True

    def _retry_llm_preflight(self):
        if not self._llm_preflight_request: return
        self._launch_llm_preflight()

    def _apply_llm_preflight_done(self, payload):
        request=self._llm_preflight_request
        if not request or payload.get("token")!=request.get("token"): return
        callback=request.get("callback"); models=list(payload.get("models") or [])
        self.llm_preflight_thread=None; self._llm_preflight_request=None; self._llm_connection_alert_key=""
        self._close_llm_connection_alert(reset_key=True)
        self.connection_var.set(i18n.t('u5.connected_models', provider=request['provider'], count=len(models)))
        self._set_llm_idle(i18n.t('u5.llm_idle'),i18n.t('u5.connection_checked'))
        self._refresh_operation_states()
        if callback and not self._closing: self.after_idle(callback)

    def _apply_llm_preflight_error(self, payload):
        request=self._llm_preflight_request
        if not request or payload.get("token")!=request.get("token"): return
        self.llm_preflight_thread=None; self._refresh_operation_states()
        error=str(payload.get("error") or i18n.t('u5.connection_failed'))
        record_error(i18n.t('u5.preflight_error'),detail=f"{request['context']}: {error}")
        self._show_llm_connection_alert(request["provider"],request["url"],request["model"],error,
                                        context=request["context"],retry_command=self._retry_llm_preflight,force=True)

    def refresh_models(self):
        label=self.provider_var.get()
        key = self.api_key_var.get().strip() or core.env_api_key_for_provider(label)
        if core.normalize_provider(label) in {"openai","anthropic","gemini","openai_compat"} and not key:
            self.connection_var.set(i18n.t('u5.missing_api_key', label=label))
        else:
            self.connection_var.set(i18n.t('u5.checking_connection', provider=label))
        provider = self.provider_var.get()
        url = self.url_var.get().strip()
        api_key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        threading.Thread(target=self._fetch_models,args=(provider,url,api_key,model),daemon=True).start()

    def _fetch_models(self, provider, url, api_key, model=""):
        try:
            models=core.list_models(provider,url,timeout=8,api_key=api_key)
            if core.normalize_provider(provider) in {"ollama","lmstudio"} and not models:
                raise RuntimeError(i18n.t('u5.no_loaded_models'))
            self.events.put(("models",models))
        except Exception as e:
            self.events.put(("model_error",{"provider":provider,"url":url,"model":model,"error":str(e)}))

    # ---------------- difference inspector / search ----------------
    def load_diff_inspector(self):
        src=Path(self.diff_src_var.get()); dst=Path(self.diff_dst_var.get())
        if not src.exists() or not dst.exists():
            messagebox.showerror(APP_NAME,i18n.t('u3.select_diff_files', target_name=i18n.t("lang." + _current_target_lang(self)))); return
        if self.diff_load_worker and self.diff_load_worker.is_alive():
            self.diff_summary_var.set(i18n.t('u3.diff_background')); return
        self.diff_batch_contexts=[]
        self.diff_summary_var.set(i18n.t('u3.diff_background_hint'))
        target_lang=_current_target_lang(self)
        def work():
            try:
                source_lang,source_entries,_=core.parse_localization_file(src)
                _,target_entries,_=core.parse_localization_file(dst)
                rows=core.compare_localization_entries(source_entries,target_entries,source_lang,target_lang)
                self.events.put(('diff_inspector_loaded',(source_lang,source_entries,target_entries,rows)))
            except Exception as exc:
                self.events.put(('diff_inspector_load_error',str(exc)))
        self.diff_load_worker=threading.Thread(target=work,daemon=True,name='diff-inspector-load'); self.diff_load_worker.start()

    def load_diff_pairs(self, pairs):
        pairs=[dict(pair) for pair in (pairs or []) if pair.get("source") and pair.get("target")]
        if not pairs:
            return
        if len(pairs)==1:
            self.diff_src_var.set(str(pairs[0]["source"])); self.diff_dst_var.set(str(pairs[0]["target"]))
            self.load_diff_inspector(); return
        if self.diff_load_worker and self.diff_load_worker.is_alive():
            self.diff_summary_var.set(i18n.t('u3.diff_background')); return
        self.diff_src_var.set(str(pairs[0]["source"])); self.diff_dst_var.set(str(pairs[0]["target"]))
        self.diff_summary_var.set(i18n.t('u3.diff_batch_background', count=len(pairs)))
        target_lang=_current_target_lang(self)
        def work():
            contexts=[]; errors=[]
            for pair in pairs:
                try:
                    lang,source,_=core.parse_localization_file(Path(pair["source"]))
                    _,target,_=core.parse_localization_file(Path(pair["target"]))
                    rows=core.compare_localization_entries(source,target,lang,target_lang)
                    contexts.append({"source_path":Path(pair["source"]),"target_path":Path(pair["target"]),"lang":lang,
                                     "source_entries":source,"target_entries":target,"rows":list(rows or [])})
                except Exception as exc:
                    errors.append(f'{Path(pair.get("source","")).name}: {exc}')
            self.events.put(('diff_inspector_batch_loaded',(contexts,errors)))
        self.diff_load_worker=threading.Thread(target=work,daemon=True,name='diff-inspector-batch'); self.diff_load_worker.start()

    def _apply_diff_inspector_loaded(self, source_lang, source_entries, target_entries, rows):
        self.diff_load_worker=None
        self.diff_batch_contexts=[]; self.diff_tree_record_map={}
        self.diff_source_lang=source_lang; self.diff_source_entries=source_entries; self.diff_target_entries=target_entries
        self.diff_rows=list(rows or []); self.diff_row_by_key={r['key']:r for r in self.diff_rows}
        for iid in self.diff_tree.get_children(): self.diff_tree.delete(iid)
        self.diff_tree_key_map={}
        labels={'missing':i18n.t('u3.missing'),'untranslated':i18n.t('u3.untranslated'),'extra':i18n.t('u3.target_only', target_name=i18n.t("lang." + _current_target_lang(self))),'ok':i18n.t('u3.matched')}
        counts={k:0 for k in labels}; parents={}
        for status in ('missing','untranslated','extra','ok'):
            parents[status]=self.diff_tree.insert('','end',iid=f'diff_group_{status}',text=labels[status],open=status!='ok',values=('',''),tags=(status,))
        for row in self.diff_rows: counts[row['status']]=counts.get(row['status'],0)+1
        self.diff_summary_var.set(i18n.t('u3.diff_summary_rendering', missing=counts['missing'], untranslated=counts['untranslated'], extra=counts['extra'], ok=counts['ok'], target_name=i18n.t("lang." + _current_target_lang(self))))
        self._populate_diff_rows_chunked(0,parents)

    def _populate_diff_rows_chunked(self, start, parents, chunk=400):
        end=min(len(self.diff_rows),start+chunk)
        for n in range(start,end):
            row=self.diff_rows[n]; status=row['status']; iid=f'diff_leaf_{n}'
            self.diff_tree.insert(parents[status],'end',iid=iid,text='',values=('',row['key']),tags=(status,)); self.diff_tree_key_map[iid]=row['key']
        if end < len(self.diff_rows):
            self.after(1,lambda:self._populate_diff_rows_chunked(end,parents,chunk))
        else:
            counts={k:0 for k in ('missing','untranslated','extra','ok')}
            for row in self.diff_rows: counts[row['status']]=counts.get(row['status'],0)+1
            self.diff_summary_var.set(i18n.t('u3.diff_summary', missing=counts['missing'], untranslated=counts['untranslated'], extra=counts['extra'], ok=counts['ok'], target_name=i18n.t("lang." + _current_target_lang(self))))

    def _activate_diff_context(self, index):
        if not (0 <= index < len(self.diff_batch_contexts)):
            return
        c=self.diff_batch_contexts[index]
        self.diff_src_var.set(str(c["source_path"])); self.diff_dst_var.set(str(c["target_path"]))
        self.diff_source_lang=c["lang"]; self.diff_source_entries=c["source_entries"]; self.diff_target_entries=c["target_entries"]
        self.diff_rows=c["rows"]; self.diff_row_by_key={r['key']:r for r in self.diff_rows}

    def _apply_diff_inspector_batch_loaded(self, contexts, errors):
        self.diff_load_worker=None; self.diff_batch_contexts=list(contexts or []); self.diff_tree_record_map={}; self.diff_tree_key_map={}
        for iid in self.diff_tree.get_children(): self.diff_tree.delete(iid)
        if not self.diff_batch_contexts:
            self.diff_summary_var.set(i18n.t('u3.diff_batch_failed', count=len(errors)))
            if errors: messagebox.showerror(APP_NAME,i18n.t('u3.diff_no_files', value='\n'.join(errors[:20])))
            return
        self._activate_diff_context(0)
        labels={'missing':i18n.t('u3.missing'),'untranslated':i18n.t('u3.untranslated'),'extra':i18n.t('u3.target_only', target_name=i18n.t("lang." + _current_target_lang(self))),'ok':i18n.t('u3.matched')}
        parents={status:self.diff_tree.insert('','end',iid=f'diff_batch_group_{status}',text=label,open=status!='ok',values=('',''),tags=(status,)) for status,label in labels.items()}
        counts={k:0 for k in labels}; n=0
        for ci,c in enumerate(self.diff_batch_contexts):
            file_label=f'{"English" if c["lang"]=="english" else i18n.t("u3.simplified_chinese")}: {Path(c["source_path"]).name}'
            for row in c["rows"]:
                status=row['status']; counts[status]=counts.get(status,0)+1; iid=f'diff_batch_leaf_{n}'; n+=1
                self.diff_tree.insert(parents[status],'end',iid=iid,values=(file_label,row['key']),tags=(status,))
                self.diff_tree_key_map[iid]=row['key']; self.diff_tree_record_map[iid]=(ci,row['key'])
        failed=len(errors or [])
        self.diff_summary_var.set((i18n.t('u3.diff_batch_summary_failed', count=len(self.diff_batch_contexts), missing=counts["missing"], untranslated=counts["untranslated"], extra=counts["extra"], ok=counts["ok"], target_name=i18n.t("lang." + _current_target_lang(self)), failed=failed) if failed else i18n.t('u3.diff_batch_summary', count=len(self.diff_batch_contexts), missing=counts["missing"], untranslated=counts["untranslated"], extra=counts["extra"], ok=counts["ok"], target_name=i18n.t("lang." + _current_target_lang(self)))))
        if failed:
            messagebox.showwarning(APP_NAME,i18n.t('u3.diff_batch_skipped', failed=failed, value='\n'.join((errors or [])[:20])))

    def _selected_diff_keys(self):
        out=[]
        for iid in self.diff_tree.selection():
            key=getattr(self,"diff_tree_key_map",{}).get(iid)
            if key: out.append(key)
        return out

    def on_diff_select(self, _=None):
        keys=self._selected_diff_keys()
        if not keys: return
        key=keys[0]
        sel=self.diff_tree.selection()
        if sel and sel[0] in self.diff_tree_record_map:
            ci,_key=self.diff_tree_record_map[sel[0]]; self._activate_diff_context(ci)
        row = self.diff_row_by_key.get(key, {})
        self.diff_src_text.delete("1.0", "end"); self.diff_src_text.insert("1.0", row.get("source", ""))
        self.diff_dst_text.delete("1.0", "end"); self.diff_dst_text.insert("1.0", row.get("target", ""))
        self.diff_message_var.set(row.get("message", ""))

    def save_diff_value(self):
        keys=self._selected_diff_keys()
        if not keys: return
        key=keys[0]
        value = self.diff_dst_text.get("1.0", "end-1c")
        try:
            target=Path(self.diff_dst_var.get())
            self._backup_before_diff_write([str(target)])
            core.upsert_localization_values(target, {key:value}, _current_target_lang(self))
            self._invalidate_status_after_diff_write([str(target), self.diff_src_var.get()])
            if len(self.diff_batch_contexts)>1:
                pairs=[{"source":c["source_path"],"target":c["target_path"],"lang":c["lang"]} for c in self.diff_batch_contexts]
                self.load_diff_pairs(pairs)
            else:
                self.load_diff_inspector()
            for iid,k in getattr(self,"diff_tree_key_map",{}).items():
                if k==key and self.diff_tree.exists(iid):
                    self.diff_tree.selection_set(iid); self.diff_tree.see(iid); break
        except Exception as e:
            record_error(i18n.t('u3.save_diff_error'), e); messagebox.showerror(APP_NAME, str(e))

    def _backup_before_diff_write(self, target_paths):
        """差分翻訳・差分訳の保存で書き込む前に、ほかの上書きと同じ方式でバックアップを取る。

        Mod の localization の中のファイルなら、その Mod の localization 全体を「上書き」として保存する。
        それ以外の場所のファイルは、ファイル単位で写しを取る（復元用の manifest.json 付き）。
        """
        backups=[]; done=set(); loose=[]
        for raw in target_paths:
            path=Path(raw)
            mod_root=_mod_root_of_localization_file(path)
            if mod_root is None:
                if path.exists(): loose.append(path)
                continue
            key=str(mod_root)
            if key in done: continue
            done.add(key)
            root,_manifest=self._create_full_localization_snapshot(
                mod_root,"差分翻訳",category="上書き",
                state_label=i18n.t('u3.diff_backup_label'))
            backups.append(root)
        if loose:
            backup_dir=core.create_qa_repair_backup_dir(BACKUP_ROOT/"差分翻訳","diff_translate")
            for path in loose:
                core._backup_qa_repair_target(path,backup_dir)
            backups.append(backup_dir)
        return backups

    def _invalidate_status_after_diff_write(self, paths):
        """書き込んだファイルの Mod と、原文の Mod の翻訳状況のキャッシュを捨てる（再調査で状態を変えるため）。

        翻訳状況の一覧のキャッシュは元Mod の localization だけを見て使い回すので、
        日本語化Mod など別の場所へ書いたときは、ここで捨てないと再調査しても状態が変わらない。
        """
        roots=[]
        for raw in paths:
            root=_mod_root_of_localization_file(raw)
            if root is not None and str(root) not in roots:
                roots.append(str(root))
        if roots:
            self._invalidate_mod_status_cache_paths(roots)

    def translate_diff_items(self, all_missing=False, _llm_ready=False):
        if self._closing:
            return
        if self.diff_controller is not None:
            messagebox.showinfo(APP_NAME, i18n.t('u3.diff_translation_running'))
            return
        if not self.diff_rows and not self.diff_batch_contexts:
            self.load_diff_inspector()
            if not self.diff_rows: return
        if not _llm_ready:
            self._begin_llm_preflight("差分翻訳",lambda:self.translate_diff_items(all_missing,_llm_ready=True))
            return
        tasks=[]
        if len(self.diff_batch_contexts)>1:
            if all_missing:
                contexts=sorted(enumerate(self.diff_batch_contexts),key=lambda item:(item[1].get("lang")!="english",item[0]))
                for ci,c in contexts:
                    for row in c["rows"]:
                        if row["status"] in ("missing","untranslated") and row.get("source"):
                            tasks.append((ci,row["key"]))
            else:
                for iid in self.diff_tree.selection():
                    record=self.diff_tree_record_map.get(iid)
                    if record:
                        ci,key=record; row=next((r for r in self.diff_batch_contexts[ci]["rows"] if r["key"]==key),{})
                        if row.get("source"): tasks.append((ci,key))
        else:
            keys = ([r["key"] for r in self.diff_rows if r["status"] in ("missing","untranslated") and r.get("source")]
                    if all_missing else [k for k in self._selected_diff_keys() if self.diff_row_by_key.get(k,{}).get("source")])
            single={"source_path":Path(self.diff_src_var.get()),"target_path":Path(self.diff_dst_var.get()),"lang":self.diff_source_lang or "english",
                    "source_entries":self.diff_source_entries,"target_entries":self.diff_target_entries,"rows":self.diff_rows}
            tasks=[(0,key) for key in keys]
        contexts=self.diff_batch_contexts if len(self.diff_batch_contexts)>1 else [single]
        tasks=_dedupe_diff_translation_tasks(contexts,tasks)
        if not tasks:
            messagebox.showinfo(APP_NAME, i18n.t('u3.select_missing_keys'))
            return
        self.diff_controller = core.TranslationController(progress_callback=lambda p:self.events.put(("diff_translate_progress", p)))
        self.llm_operation = "差分翻訳"
        self.diff_message_var.set(i18n.t('u3.diff_translating', count=len(tasks)))
        target_lang = _current_target_lang(self)
        glossary_path = _existing_language_glossary(self.glossary_path_var.get().strip(),target_lang)
        diff_settings = {
            "normalize_spacing": _normalize_spacing_enabled(self),
            "url": self.url_var.get().strip(), "model": self.model_var.get().strip(),
            "preset": self.preset_var.get(), "provider": self.provider_var.get(),
            "api_key": self.api_key_var.get().strip(),
        }
        def work():
            try:
                glossary = core.load_glossary(Path(glossary_path)) if glossary_path else {}
                outputs = {}
                spaces_removed = 0
                untranslated = []
                for i, (ci,key) in enumerate(tasks, 1):
                    if self.diff_controller.stop_event.is_set(): raise core.StopRequested()
                    context=contexts[ci]; source_lang=context["lang"]
                    self.events.put(("diff_translate_status", (i, len(tasks), f'{Path(context["source_path"]).name} / {key}')))
                    source_text=context["source_entries"][key]
                    problem=""
                    for _attempt in range(DIFF_TRANSLATE_ATTEMPTS):
                        if self.diff_controller.stop_event.is_set(): raise core.StopRequested()
                        try:
                            translated=core.translate_single_text(diff_settings["url"], diff_settings["model"], source_text, source_lang,
                                                                  glossary, diff_settings["preset"], diff_settings["provider"], diff_settings["api_key"], self.diff_controller,
                                                                  chinese_basis=(source_lang == "simp_chinese" and target_lang in core.CHINESE_BASIS_TARGETS),
                                                                  target_lang=target_lang)
                        except core.StopRequested:
                            raise
                        except Exception as exc:
                            translated=""; problem=i18n.t('u3.translation_failed', value=type(exc).__name__, exc=exc)
                            continue
                        problem=_diff_translation_problem(source_text, translated, source_lang, target_lang)
                        if not problem:
                            break
                    if problem:
                        # 原文のまま・使えない訳は訳文のファイルへ書き戻さず、「未翻訳のまま」として結果に出す。
                        untranslated.append({"file":Path(context["target_path"]).name,"key":key,"reason":problem})
                        continue
                    if diff_settings["normalize_spacing"]:
                        translated, removed = core.normalize_cjk_spacing(translated, target_lang)
                        spaces_removed += removed
                    outputs.setdefault(str(context["target_path"]),{})[key]=translated
                backups = self._backup_before_diff_write(list(outputs)) if outputs else []
                for target_path,values in outputs.items():
                    core.upsert_localization_values(Path(target_path),values,target_lang)
                if outputs:
                    self._invalidate_status_after_diff_write(
                        list(outputs) + [str(contexts[ci]["source_path"]) for ci,_key in tasks])
                self.events.put(("diff_translate_done", {
                    "written": sum(len(v) for v in outputs.values()), "untranslated": untranslated,
                    "spaces_removed": spaces_removed,
                    "backups": [str(x) for x in backups], "total": len(tasks)}))
            except core.StopRequested:
                self.events.put(("diff_translate_stopped", None))
            except Exception as e:
                self.events.put(("diff_translate_error", str(e)))
        self.diff_translate_thread=threading.Thread(target=work, daemon=True,name="diff-translate")
        self.diff_translate_thread.start()

    def pick_search_folder(self):
        # Legacy compatibility: translation search is now game-scoped.
        messagebox.showinfo(APP_NAME, i18n.t('u3.search_game_scope'))

    def pick_search_file(self):
        messagebox.showinfo(APP_NAME, i18n.t('u3.search_yaml_scope'))

    def clear_translation_search_results(self):
        if hasattr(self, "search_tree"):
            for iid in self.search_tree.get_children():
                self.search_tree.delete(iid)
        self.search_result_map = {}
        self.search_summary_var.set(i18n.t('u3.search_idle'))
        if hasattr(self, "search_edit_text"):
            self.search_edit_text.delete("1.0", "end")
        if hasattr(self, "search_selected_var"):
            self.search_selected_var.set(i18n.t('u3.select_result'))

    def _translation_search_location_rows_for_game(self, game):
        rows=[]
        seen=set()
        for row in self.detected_mod_locations:
            if row.get("game") != game:
                continue
            raw=str(row.get("path","")).strip()
            if raw and raw not in seen:
                seen.add(raw); rows.append(dict(row))
        for raw in self.monitor_target_paths:
            raw=str(raw or "").strip()
            if not raw or raw in seen:
                continue
            matched=next((r for r in self.detected_mod_locations if str(r.get("path", ""))==raw and r.get("game")==game), None)
            if matched:
                seen.add(raw); rows.append(dict(matched))
        return rows

    def _translation_search_mod_roots_for_game(self, game):
        roots=[]; seen=set()
        rows=self._translation_search_location_rows_for_game(game)
        for row in rows:
            location=Path(row.get("path", ""))
            if not location.exists():
                continue
            try: candidates=core.find_mod_roots(location)
            except Exception: candidates=[]
            for root in candidates:
                try: key=str(Path(root).resolve())
                except Exception: key=str(Path(root))
                if key not in seen:
                    seen.add(key); roots.append(Path(root))
        # 翻訳状況で既に個別Modが確定している場合も取り込む。
        allowed=[Path(r.get("path","")) for r in rows if r.get("path")]
        for result in self.mod_research_results:
            raw=str(result.get("path","")).strip()
            if not raw:
                continue
            rp=Path(raw)
            if not rp.exists():
                continue
            if allowed:
                try:
                    rr=rp.resolve()
                    if not any(rr == a.resolve() or a.resolve() in rr.parents for a in allowed if a.exists()):
                        continue
                except Exception:
                    pass
            try: key=str(rp.resolve())
            except Exception: key=str(rp)
            if key not in seen:
                seen.add(key); roots.append(rp)
        return roots

    def _remember_translation_search_mod_selection(self):
        if not hasattr(self,"search_mod_list"):
            return
        paths=[]
        for i in self.search_mod_list.curselection():
            path=self.search_mod_map.get(int(i))
            if path: paths.append(str(path))
        self.search_selected_mod_paths=paths
        self._save_workspace_state("translation_search_mod_selection")

    def _select_all_translation_search_mods(self):
        if hasattr(self,"search_mod_list"):
            self.search_mod_list.selection_set(0,"end")
            self._remember_translation_search_mod_selection()

    def _clear_translation_search_mod_selection(self):
        if hasattr(self,"search_mod_list"):
            self.search_mod_list.selection_clear(0,"end")
        self.search_selected_mod_paths=[]
        self._save_workspace_state("translation_search_mod_selection_clear")

    def refresh_translation_search_mods(self):
        if not hasattr(self,"search_mod_list"):
            return
        game=self.search_game_var.get().strip()
        self.search_mod_refresh_generation += 1
        generation=self.search_mod_refresh_generation
        wanted=set(self.search_selected_mod_paths or [])
        self.search_mod_status_var.set(i18n.t('u3.search_mods_background'))
        def work():
            try:
                roots=self._translation_search_mod_roots_for_game(game)
                rows=[]
                for root in roots:
                    try: name=core.detect_mod_name(Path(root))
                    except Exception: name=Path(root).name
                    rows.append((name,str(Path(root))))
                rows.sort(key=lambda x:x[0].casefold())
                self.events.put(("translation_search_mods_done", {"generation":generation,"game":game,"rows":rows,"wanted":list(wanted)}))
            except Exception as e:
                self.events.put(("translation_search_mods_error", {"generation":generation,"error":str(e)}))
        threading.Thread(target=work,daemon=True).start()

    def _search_expected_japanese_path(self, loc_root, source_file, source_lang):
        """Return the deterministic Japanese counterpart path for a source localization file."""
        loc_root = Path(loc_root)
        source_file = Path(source_file)
        try:
            rel_parent = source_file.parent.relative_to(loc_root)
        except Exception:
            rel_parent = Path(source_file.parent.name)
        return loc_root / core.remap_rel_dir(rel_parent, "japanese") / core.rename_for_target(source_file, "japanese", source_lang)

    def run_translation_search(self):
        game=self.search_game_var.get().strip()
        q_raw=self.search_query_var.get().strip()
        q=q_raw.casefold()
        if not game:
            messagebox.showerror(APP_NAME,i18n.t('u3.select_search_game')); return
        if not q:
            messagebox.showinfo(APP_NAME,i18n.t('u3.require_search_term')); return
        selected=[Path(p) for p in (self.search_selected_mod_paths or []) if Path(p).exists()]
        if not selected:
            selected=[Path(v) for v in self.search_mod_map.values() if Path(v).exists()]
        if not selected:
            # 一覧取得前でも検索ボタンからそのまま開始できるよう、Mod取得もバックグラウンド側で行う。
            rows=self._translation_search_location_rows_for_game(game)
        else:
            rows=[]
        self.search_generation += 1
        generation=self.search_generation
        self.search_summary_var.set(i18n.t('u3.search_background', game=game))
        def work():
            try:
                roots=selected or self._translation_search_mod_roots_for_game(game)
                results=[]; missing_count=0; scanned_mods=0
                for mod_no,mod_root in enumerate(roots,1):
                    loc=core.mod_localization_root(mod_root)
                    if not loc: continue
                    scanned_mods += 1
                    mod_name=core.detect_mod_name(mod_root)
                    self.events.put(("translation_search_progress", {"generation":generation,"game":game,"done":mod_no,"total":len(roots),"mod":mod_name}))
                    try: files=core.gather_yml_files(loc)
                    except Exception: continue
                    groups={}
                    for f in files:
                        try: lang,entries,_=core.parse_localization_file(f)
                        except Exception: continue
                        if lang not in ("english","simp_chinese","japanese"): continue
                        try: lid=core._logical_localization_id(f,loc,lang)
                        except Exception: lid=f.name
                        groups.setdefault(lid,{})[lang]={"path":Path(f),"entries":entries}
                    for _lid,langs in groups.items():
                        ja=langs.get("japanese")
                        src=langs.get("english") or langs.get("simp_chinese")
                        src_lang="english" if "english" in langs else ("simp_chinese" if "simp_chinese" in langs else "")
                        ja_entries=ja["entries"] if ja else {}
                        src_entries=src["entries"] if src else {}
                        for key in sorted(set(ja_entries)|set(src_entries)):
                            ja_value=ja_entries.get(key); source_value=src_entries.get(key,"")
                            source_file=src["path"] if src else None
                            target_file=ja["path"] if ja else (self._search_expected_japanese_path(loc,source_file,src_lang) if source_file else None)
                            missing=key in src_entries and key not in ja_entries
                            searchable=[key,mod_name,source_value]
                            if ja_value is not None: searchable.append(ja_value)
                            if source_file: searchable.append(source_file.name)
                            if target_file: searchable.append(Path(target_file).name)
                            if not any(q in str(v).casefold() for v in searchable if v is not None): continue
                            shown_file=source_file if missing and source_file else (ja["path"] if ja else target_file)
                            results.append({
                                "target_file":str(target_file) if target_file else "",
                                "source_file":str(source_file) if source_file else "",
                                "key":key,"value":"" if missing else (ja_value or ""),"source_value":source_value,
                                "source_lang":src_lang,"mod_name":mod_name,"missing":missing,
                                "shown_file":str(shown_file) if shown_file else "",
                            })
                            if missing: missing_count += 1
                self.events.put(("translation_search_done", {"generation":generation,"game":game,"rows":results,"missing":missing_count,"scanned_mods":scanned_mods}))
            except Exception as e:
                self.events.put(("translation_search_error", {"generation":generation,"error":str(e)}))
        self.search_thread=threading.Thread(target=work,daemon=True); self.search_thread.start()

    def on_search_select(self, _=None):
        sel = self.search_tree.selection()
        if not sel:
            return
        row = self.search_result_map.get(sel[0])
        if not row:
            return
        key = row["key"]
        mod_name = row["mod_name"]
        source_file = row.get("source_file")
        target_file = row.get("target_file")
        if row.get("missing"):
            src = self._localization_display_path(source_file) if source_file else ""
            dst = self._localization_display_path(target_file) if target_file else ""
            self.search_selected_var.set(i18n.t('u3.search_missing_path', mod_name=mod_name, localization_key=key, src=src, dst=dst))
        else:
            self.search_selected_var.set(f"{mod_name} / {self._localization_display_path(target_file)} / {key}")
        self.search_edit_text.delete("1.0", "end")
        self.search_edit_text.insert("1.0", row.get("value", ""))

    def save_search_value(self):
        sel = self.search_tree.selection()
        if not sel:
            return
        row = self.search_result_map.get(sel[0])
        if not row:
            return
        target_file = row.get("target_file")
        key = row.get("key", "")
        mod_name = row.get("mod_name", "")
        if not target_file:
            messagebox.showerror(APP_NAME, i18n.t('u3.search_target_missing'))
            return
        value = self.search_edit_text.get("1.0", "end-1c")
        try:
            if row.get("missing"):
                core.upsert_localization_values(Path(target_file), {key: value}, "japanese")
            elif not core.update_localization_value(Path(target_file), key, value):
                raise RuntimeError(i18n.t('u3.search_update_failed'))
            row["value"] = value
            row["missing"] = False
            self.search_result_map[sel[0]] = row
            self.search_tree.item(sel[0], values=(mod_name, self._localization_display_path(target_file), key, value[:180]))
            self.search_selected_var.set(f"{mod_name} / {self._localization_display_path(target_file)} / {key}")
            self.search_summary_var.set(i18n.t('u3.saved_key', localization_key=key))
        except Exception as e:
            record_error(i18n.t('u3.search_save_error'), e)
            messagebox.showerror(APP_NAME, str(e))

    # ---------------- QA/editor ----------------
    def pick_review_file(self,var):
        p=filedialog.askopenfilename(filetypes=[("Paradox YAML","*.yml"),("All","*")])
        if p: var.set(p)

    def load_review(self):
        dst=Path(self.review_dst_var.get())
        if not dst.exists(): messagebox.showerror(APP_NAME,i18n.t('u3.select_translation_file')); return
        self.review_batch_contexts=[]
        self._start_review_background(load_files=True)

    def _set_review_qa_log_enabled(self, enabled):
        if hasattr(self,"review_export_log_btn"):
            self.review_export_log_btn.configure(state="normal" if enabled else "disabled")

    def _set_review_auto_repair_enabled(self, enabled):
        if hasattr(self,"review_auto_repair_btn"):
            active=bool(enabled) and self.qa_repair_thread is None and not self._closing
            self.review_auto_repair_btn.configure(state="normal" if active else "disabled")

    def _clear_pending_review_qa_log(self):
        self.review_last_qa_contexts=[]; self.review_last_qa_errors=[]
        self.review_last_qa_repair_result=None
        self._set_review_qa_log_enabled(False)
        self._set_review_auto_repair_enabled(False)

    def export_review_qa_log(self):
        contexts=list(self.review_last_qa_contexts or []); failures=list(self.review_last_qa_errors or [])
        if not contexts and not failures:
            self._set_review_qa_log_enabled(False)
            return
        try:
            payload=_build_qa_log_payload(contexts,failures,repair_result=getattr(self,"review_last_qa_repair_result",None))
            path=QA_LOG_ROOT / f'qa_report_{datetime.now().strftime("%Y%m%d_%H%M%S_%f")}.json'
            core.save_json(path,payload)
            messagebox.showinfo(APP_NAME,i18n.t('u3.qa_log_exported', path=path))
        except Exception as exc:
            record_error(i18n.t('u3.qa_log_error_context'),exc)
            messagebox.showerror(APP_NAME,i18n.t('u3.qa_log_export_failed', exc=exc))

    def run_review_auto_repair(self):
        contexts=list(self.review_batch_contexts or self.review_last_qa_contexts or [])
        if not _qa_contexts_have_repairable_errors(contexts):
            self._set_review_auto_repair_enabled(False)
            messagebox.showinfo(APP_NAME,i18n.t('u3.no_repairable_errors')); return
        pairs=[{"source_file":str(c.get("source_path") or ""),"target_file":str(c.get("target_path") or ""),
                "source_language":str(c.get("lang") or "english"),
                "target_language":str(c.get("target_lang") or core.DEFAULT_TARGET_LANG)} for c in contexts]
        self._start_manual_qa_repair(pairs,"review")

    def load_review_pairs(self, pairs):
        pairs=[dict(pair) for pair in (pairs or []) if pair.get("source") and pair.get("target")]
        if not pairs:
            return
        first=pairs[0]
        self.review_src_var.set(str(first["source"])); self.review_dst_var.set(str(first["target"]))
        self._start_review_pairs_background(pairs)

    def run_review_qa(self):
        if len(self.review_batch_contexts)>1:
            pairs=[{"source":c["source_path"],"target":c["target_path"],"lang":c["lang"]} for c in self.review_batch_contexts]
            self._start_review_pairs_background(pairs)
            return
        self._start_review_background(load_files=not bool(self.review_target_entries))

    def _start_review_pairs_background(self, pairs):
        if self.review_worker and self.review_worker.is_alive():
            self.qa_summary_var.set(i18n.t('u3.qa_background')); return
        self._clear_pending_review_qa_log()
        target_lang=_current_target_lang(self)
        glossary_path=_existing_language_glossary(self.glossary_path_var.get(),target_lang)
        self.qa_summary_var.set(i18n.t('u3.qa_batch_background', count=len(pairs)))
        def work():
            contexts=[]; errors=[]
            try:
                glossary=core.load_glossary(glossary_path) if glossary_path else {}
            except Exception as exc:
                errors.append({"source_file":"","target_file":"","source_language":"","stage":"glossary_read","error_type":type(exc).__name__,"message":str(exc),"action":i18n.t('u3.cancel_qa')})
                self.events.put(('review_qa_batch_loaded',(contexts,errors))); return
            for pair in pairs:
                source_path=Path(pair["source"]); target_path=Path(pair["target"]); lang=str(pair.get("lang") or "")
                stage="source_read"
                try:
                    lang,source,_=core.parse_localization_file(source_path)
                    stage="target_read"
                    _,target,_=core.parse_localization_file(target_path)
                    stage="qa_analysis"
                    issues=core.qa_file(target_path,source_path,source_lang=lang,glossary=glossary,target_lang=target_lang)
                    contexts.append({"source_path":source_path,"target_path":target_path,"lang":lang,"target_lang":target_lang,
                                     "source_entries":source,"target_entries":target,"issues":list(issues or [])})
                except Exception as exc:
                    errors.append({"source_file":str(source_path),"target_file":str(target_path),"source_language":lang,"stage":stage,
                                   "error_type":type(exc).__name__,"message":str(exc),"action":i18n.t('u3.skip_continue')})
            self.events.put(('review_qa_batch_loaded',(contexts,errors)))
        self.review_worker=threading.Thread(target=work,daemon=True,name='review-qa-batch'); self.review_worker.start()

    def _start_review_background(self, load_files=False):
        if self.review_worker and self.review_worker.is_alive():
            self.qa_summary_var.set(i18n.t('u3.qa_background')); return
        self._clear_pending_review_qa_log()
        dst=Path(self.review_dst_var.get()) if self.review_dst_var.get() else None
        src=Path(self.review_src_var.get()) if self.review_src_var.get() else None
        target_lang=_current_target_lang(self)
        glossary_path=_existing_language_glossary(self.glossary_path_var.get(),target_lang)
        existing_target=dict(self.review_target_entries); existing_source=dict(self.review_source_entries); existing_lang=self.review_source_lang
        self.qa_summary_var.set(i18n.t('u3.qa_background_hint'))
        def work():
            stage="qa_analysis"
            try:
                target=existing_target; source=existing_source; source_lang=existing_lang
                if load_files or not target:
                    if not dst or not dst.exists(): raise RuntimeError(i18n.t('u3.select_translation_file'))
                    stage="target_read"
                    _,target,_=core.parse_localization_file(dst)
                    if src and src.exists():
                        stage="source_read"; source_lang,source,_=core.parse_localization_file(src)
                    else: source_lang='english'; source={}
                stage="glossary_read"
                glossary=core.load_glossary(glossary_path) if glossary_path else {}
                stage="qa_analysis"
                if dst and dst.exists():
                    issues=core.qa_file(dst,src if src and src.exists() else None,source_lang=source_lang,glossary=glossary,
                                        target_lang=target_lang)
                else:
                    issues=core.qa_entries(target,source or None,source_lang,glossary,source_path=src,target_lang=target_lang)
                self.events.put(('review_qa_loaded',(source_lang,source,target,issues)))
            except Exception as exc:
                self.events.put(('review_qa_error',{"source_file":str(src or ""),"target_file":str(dst or ""),"source_language":str(existing_lang or ""),
                                                    "stage":stage,"error_type":type(exc).__name__,"message":str(exc),"action":i18n.t('u3.cancel_qa')}))
        self.review_worker=threading.Thread(target=work,daemon=True,name='review-qa'); self.review_worker.start()

    def _apply_review_qa_loaded(self, source_lang, source_entries, target_entries, issues):
        self.review_worker=None; self.review_source_lang=source_lang; self.review_source_entries=source_entries; self.review_target_entries=target_entries
        self.review_batch_contexts=[]; self.review_batch_errors=[]; self.review_tree_record_map={}
        self.review_issues=list(issues or []); self.review_issue_by_key={}
        for issue in self.review_issues: self.review_issue_by_key.setdefault(issue['key'],[]).append(issue)
        errs=sum(x['severity']=='error' for x in self.review_issues); warns=sum(x['severity']=='warning' for x in self.review_issues)
        notices=sum(x['severity']=='notice' for x in self.review_issues)
        self.review_last_qa_contexts=[{"source_path":Path(self.review_src_var.get()) if self.review_src_var.get() else "",
                                      "target_path":Path(self.review_dst_var.get()) if self.review_dst_var.get() else "",
                                      "lang":source_lang,"target_lang":_current_target_lang(self),
                                      "source_entries":source_entries,"target_entries":target_entries,"issues":self.review_issues}]
        self.review_last_qa_errors=[]; self._set_review_qa_log_enabled(True)
        self._set_review_auto_repair_enabled(_qa_contexts_have_repairable_errors(self.review_last_qa_contexts))
        self.qa_summary_var.set(i18n.t('u3.qa_summary', errs=errs, warns=warns, notices=notices, count=len(self.review_target_entries)))
        self.populate_review(True)

    def _activate_review_context(self, index):
        if not (0 <= index < len(self.review_batch_contexts)):
            return
        c=self.review_batch_contexts[index]
        self.review_src_var.set(str(c["source_path"])); self.review_dst_var.set(str(c["target_path"]))
        self.review_source_lang=c["lang"]; self.review_source_entries=c["source_entries"]; self.review_target_entries=c["target_entries"]
        self.review_issues=c["issues"]; self.review_issue_by_key={}
        for issue in self.review_issues: self.review_issue_by_key.setdefault(issue['key'],[]).append(issue)

    def _apply_review_qa_batch_loaded(self, contexts, errors):
        self.review_worker=None; self.review_batch_contexts=list(contexts or []); self.review_batch_errors=list(errors or []); self.review_tree_record_map={}
        self.review_last_qa_contexts=list(self.review_batch_contexts); self.review_last_qa_errors=list(self.review_batch_errors)
        self._set_review_qa_log_enabled(bool(self.review_last_qa_contexts or self.review_last_qa_errors))
        self._set_review_auto_repair_enabled(_qa_contexts_have_repairable_errors(self.review_last_qa_contexts))
        if not self.review_batch_contexts:
            self.qa_summary_var.set(i18n.t('u3.qa_batch_failed', count=len(errors)))
            if errors: messagebox.showerror(APP_NAME,i18n.t('u3.qa_no_files', value='\n'.join(_qa_failure_display(x) for x in errors[:20])))
            return
        self._activate_review_context(0)
        self.populate_review_batch(True,errors)

    def populate_review_batch(self, warnings_only, errors=None):
        for x in self.review_tree.get_children(): self.review_tree.delete(x)
        self.review_tree_key_map={}; self.review_tree_record_map={}; parents={}; type_parents={}; n=0
        counts={"error":0,"warning":0,"notice":0}; total_keys=0
        for ci,c in enumerate(self.review_batch_contexts):
            issue_by_key={}
            for issue in c["issues"]:
                issue_by_key.setdefault(issue['key'],[]).append(issue); counts[issue['severity']]=counts.get(issue['severity'],0)+1
            keys=sorted(set(c["target_entries"]) | set(c["source_entries"]))
            total_keys += len(keys)
            file_label=f'{"English" if c["lang"]=="english" else i18n.t("u3.simplified_chinese")}: {Path(c["source_path"]).name}'
            for key in keys:
                issues=issue_by_key.get(key,[])
                if warnings_only and not issues: continue
                group=_qa_severity_group(issues)
                types=sorted(set(i['type'] for i in issues)) or ['']
                for typ in types:
                    if group not in parents:
                        parents[group]=self.review_tree.insert('', 'end', iid=f'qa_batch_group_{group}', text={'error':i18n.t('u3.error'),'warning':i18n.t('u3.warning'),'notice':i18n.t('u3.notice'),'ok':i18n.t('u3.no_issues')}[group], open=group!='ok', values=('','',''))
                    parent=parents[group]
                    if group!='ok':
                        token=(group,typ)
                        if token not in type_parents:
                            type_parents[token]=self.review_tree.insert(parent,'end',text=typ,open=True,values=(typ,'',''))
                        parent=type_parents[token]
                    iid=f'qa_batch_leaf_{n}'; n+=1
                    self.review_tree.insert(parent,'end',iid=iid,values=(typ,file_label,key))
                    self.review_tree_key_map[iid]=key; self.review_tree_record_map[iid]=(ci,key)
        failed=len(errors or [])
        self.qa_summary_var.set((i18n.t('u3.qa_batch_summary_failed', count=len(self.review_batch_contexts), error=counts["error"], warning=counts["warning"], notice=counts["notice"], total_keys=total_keys, failed=failed) if failed else i18n.t('u3.qa_batch_summary', count=len(self.review_batch_contexts), error=counts["error"], warning=counts["warning"], notice=counts["notice"], total_keys=total_keys)))
        if failed:
            messagebox.showwarning(APP_NAME,i18n.t('u3.qa_batch_skipped', failed=failed, value='\n'.join(_qa_failure_display(x) for x in (errors or [])[:20])))

    def populate_review(self,warnings_only):
        if self.review_batch_contexts:
            self.populate_review_batch(warnings_only,self.review_batch_errors)
            return
        for x in self.review_tree.get_children(): self.review_tree.delete(x)
        self.review_tree_key_map={}
        keys=sorted(set(self.review_target_entries) | set(self.review_source_entries or {}))
        rows=[]
        for key in keys:
            issues=self.review_issue_by_key.get(key,[])
            if warnings_only and not issues: continue
            if issues:
                group=_qa_severity_group(issues)
                for typ in (sorted(set(i['type'] for i in issues)) or [i18n.t('u3.other')]): rows.append((group,typ,key))
            else:
                rows.append(('ok','',key))
        parents={}; type_parents={}
        self.qa_summary_var.set(i18n.t('u3.review_rendering', value=self.qa_summary_var.get(), count=len(rows)))
        self._populate_review_rows_chunked(rows,0,parents,type_parents)

    def _populate_review_rows_chunked(self, rows, start, parents, type_parents, chunk=350):
        def ensure_parent(group,label):
            if group not in parents:
                parents[group]=self.review_tree.insert('','end',iid=f'qa_group_{group}',text=label,open=True,values=('',''))
            return parents[group]
        def ensure_type(group,typ):
            k=(group,typ)
            if k not in type_parents:
                parent=ensure_parent(group,{'error':i18n.t('u3.error'),'warning':i18n.t('u3.warning'),'notice':i18n.t('u3.notice'),'ok':i18n.t('u3.no_issues')}[group])
                type_parents[k]=self.review_tree.insert(parent,'end',text=typ,open=True,values=(typ,'',''))
            return type_parents[k]
        end=min(len(rows),start+chunk)
        for n in range(start,end):
            group,typ,key=rows[n]
            if group=='ok': parent=ensure_parent('ok',i18n.t('u3.no_issues'))
            else: parent=ensure_type(group,typ)
            iid=f'qa_leaf_{n}'; self.review_tree.insert(parent,'end',iid=iid,text='',values=(typ,'',key)); self.review_tree_key_map[iid]=key
        if end < len(rows):
            self.after(1,lambda:self._populate_review_rows_chunked(rows,end,parents,type_parents,chunk))
        else:
            errs=sum(x['severity']=='error' for x in self.review_issues); warns=sum(x['severity']=='warning' for x in self.review_issues)
            notices=sum(x['severity']=='notice' for x in self.review_issues)
            self.qa_summary_var.set(i18n.t('u3.qa_summary', errs=errs, warns=warns, notices=notices, count=len(self.review_target_entries)))

    def _selected_review_key(self):
        for iid in self.review_tree.selection():
            key=getattr(self,"review_tree_key_map",{}).get(iid)
            if key:
                return key
        return None

    def on_review_select(self,_=None):
        key=self._selected_review_key()
        if not key: return
        sel=self.review_tree.selection()
        if sel and sel[0] in self.review_tree_record_map:
            ci,_key=self.review_tree_record_map[sel[0]]; self._activate_review_context(ci)
        self.src_text.delete("1.0","end"); self.src_text.insert("1.0",self.review_source_entries.get(key,""))
        self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",self.review_target_entries.get(key,""))
        self.issue_text.set(" / ".join(i["message"] for i in self.review_issue_by_key.get(key,[])))

    def save_review_value(self):
        key=self._selected_review_key()
        if not key: return
        value=self.dst_text.get("1.0","end-1c")
        if core.update_localization_value(Path(self.review_dst_var.get()),key,value):
            self.review_target_entries[key]=value; self.run_review_qa();
            for iid,k in getattr(self,"review_tree_key_map",{}).items():
                if k==key and self.review_tree.exists(iid):
                    self.review_tree.selection_set(iid); self.review_tree.see(iid); break

    def save_review_glossary_term(self):
        target_lang=_current_target_lang(self)
        key=self._selected_review_key()
        if not key:
            messagebox.showinfo(APP_NAME, i18n.t('u4.review_selection'))
            return
        src=(self.review_source_entries.get(key,"") or "").strip()
        dst=self.dst_text.get("1.0","end-1c").strip()
        if not src:
            messagebox.showinfo(APP_NAME, i18n.t('u4.missing_source'))
            return
        if not dst:
            messagebox.showinfo(APP_NAME, i18n.t('u4.enter_translation', target_name=i18n.t("lang." + target_lang)))
            return
        p=core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,target_lang)
        gl=core.load_glossary(p)
        old=gl.get(src)
        if old is not None and old != dst:
            if not messagebox.askyesno(
                APP_NAME,
                i18n.t('u4.overwrite_manual', source=src, old=old, target=dst),
            ):
                return
        gl[src]=dst
        core.save_glossary(p,gl)
        if target_lang == core.DEFAULT_TARGET_LANG: self.glossary_path_var.set(str(p))
        # QA / 比較編集から明示的に保存した語は「手動用語」として扱う。
        variants=core.load_json(core.glossary_variants_path(p),{})
        if not isinstance(variants,dict): variants={}
        variants.pop(src,None)
        core.save_json(core.glossary_variants_path(p),variants)
        self.load_glossary_ui(silent=True)
        self.progress_text.set(i18n.t('u4.manual_saved_status', source=src, target=dst))
        messagebox.showinfo(APP_NAME, i18n.t('u4.manual_saved', source=src, target=dst))

    def restore_source_to_target(self):
        key=self._selected_review_key()
        if key:
            self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",self.review_source_entries.get(key,""))

    def ai_proofread_selected(self):
        if self._closing:
            return
        key=self._selected_review_key()
        if not key: return
        text=self.dst_text.get("1.0","end-1c"); src=self.review_source_entries.get(key,"")
        self.issue_text.set(i18n.t('u3.ai_proofreading'))
        self.llm_operation = i18n.t('u3.ai_typo_check')
        self.proofread_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("proofread_progress",p)))
        target_lang = _current_target_lang(self)
        glossary_path = _existing_language_glossary(self.glossary_path_var.get().strip(),target_lang)
        proofread_settings = {
            "url": self.url_var.get().strip(), "model": self.model_var.get().strip(),
            "preset": self.preset_var.get(), "provider": self.provider_var.get(),
            "api_key": self.api_key_var.get().strip(),
        }
        def work():
            try:
                glossary=core.load_glossary(Path(glossary_path)) if glossary_path else {}
                out=core.proofread_text(proofread_settings["url"],proofread_settings["model"],text,src,glossary,proofread_settings["preset"],proofread_settings["provider"],proofread_settings["api_key"],controller=self.proofread_controller,target_lang=target_lang)
                self.events.put(("proofread",out))
            except core.StopRequested:
                self.events.put(("proofread_stopped",None))
            except Exception as e: self.events.put(("proofread_error",str(e)))
        self.proofread_thread=threading.Thread(target=work,daemon=True,name="proofread")
        self.proofread_thread.start()

    def bulk_unify_review_terms(self):
        if not _japanese_glossary_only(self): return
        src = Path(self.review_src_var.get()) if self.review_src_var.get() else None
        dst = Path(self.review_dst_var.get()) if self.review_dst_var.get() else None
        if not src or not src.exists() or not dst or not dst.exists():
            messagebox.showinfo(APP_NAME, i18n.t('u3.load_before_unify', target_name=i18n.t("lang." + _current_target_lang(self))))
            return
        term_issues=[x for x in self.review_issues if x.get("type")=="term_mismatch"]
        if not term_issues:
            messagebox.showinfo(APP_NAME, i18n.t('u3.no_term_issues'))
            return
        if not messagebox.askyesno(APP_NAME, i18n.t('u3.unify_confirm', count=len(term_issues))):
            return
        try:
            result=core.bulk_unify_qa_terms(dst, src, Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY))
            self.load_review()
            messagebox.showinfo(APP_NAME, i18n.t('u3.unify_complete', changed=result.get('changed',0), skipped=result.get('skipped',0)))
        except Exception as exc:
            record_error(i18n.t('u3.unify_error_context'), exc)
            messagebox.showerror(APP_NAME, str(exc))

    def _auto_glossary_pairs_from_origin(self, origin):
        target_lang=_current_target_lang(self)
        pairs=[]
        if origin == "review":
            src=Path(self.review_src_var.get()) if self.review_src_var.get() else None
            dst=Path(self.review_dst_var.get()) if self.review_dst_var.get() else None
            if src and dst and src.exists() and dst.exists():
                try:
                    lang=core.parse_localization_file(src)[0]
                except Exception:
                    lang="english"
                return [{"source":src,"target":dst,"lang":lang}]
            return []
        if origin == "diff":
            src=Path(self.diff_src_var.get()) if self.diff_src_var.get() else None
            dst=Path(self.diff_dst_var.get()) if self.diff_dst_var.get() else None
            if src and dst and src.exists() and dst.exists():
                try:
                    lang=core.parse_localization_file(src)[0]
                except Exception:
                    lang="english"
                return [{"source":src,"target":dst,"lang":lang}]
            return []
        if origin == "normal":
            sels=list(self.queue_tree.selection()) if hasattr(self,"queue_tree") else []
            if not sels:
                return []
            for iid in sels:
                try: item=self.queue_items[int(iid)]
                except Exception: continue
                pairs.extend(self._collect_qa_diff_pairs(Path(item.get("input","")), Path(item.get("output","")),source_langs=core.glossary_source_languages(target_lang),target_lang=target_lang))
            return pairs
        if origin == "chinese":
            sels=list(self.chinese_queue_tree.selection()) if hasattr(self,"chinese_queue_tree") else []
            if not sels:
                return []
            for iid in sels:
                try: item=self.chinese_queue_items[int(str(iid).replace("zh_",""))]
                except Exception: continue
                pairs.extend(self._collect_qa_diff_pairs(Path(item.get("input","")), Path(item.get("output","")), source_langs=("simp_chinese",), target_lang=_item_target_lang(item)))
            return pairs
        return []

    def start_auto_glossary_generation(self, origin, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        if origin == "chinese":
            # 中国語基準キューは項目ごとに翻訳先を持つ（日本語・韓国語）。選んだ項目の翻訳先の用語集に作る
            item_targets={_item_target_lang(item) for _index, item in self._selected_chinese_queue_entries()}
            if len(item_targets) > 1:
                messagebox.showinfo(APP_NAME, i18n.t("u2.mixed_targets_auto_glossary")); return
            if item_targets:
                target_lang=next(iter(item_targets))
        if self._closing:
            return
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME, i18n.t('u4.import_busy_generate'))
            return
        if self.auto_glossary_controller is not None:
            messagebox.showinfo(APP_NAME, i18n.t('u4.generation_busy'))
            return
        pairs=self._auto_glossary_pairs_from_origin(origin)
        if not pairs:
            if origin == "review":
                msg=i18n.t('u4.review_load', target_name=i18n.t("lang." + _current_target_lang(self)))
            elif origin == "diff":
                msg=i18n.t('u4.diff_load', target_name=i18n.t("lang." + _current_target_lang(self)))
            else:
                msg=i18n.t('u4.queue_selection')
            messagebox.showinfo(APP_NAME,msg); return
        self.auto_glossary_status_var.set(i18n.t('u4.generating', count=len(pairs)))
        self.llm_operation=i18n.t('u4.generation')
        self.auto_glossary_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("auto_glossary_progress",p)))
        settings={"provider":self.provider_var.get(),"url":self.url_var.get().strip(),"model":self.model_var.get().strip(),"preset":self.preset_var.get(),"api_key":self.api_key_var.get().strip()}
        glossary_path=core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,target_lang)
        include_phrases_var=getattr(self,"auto_glossary_include_phrases_var",None)
        include_phrases=bool(include_phrases_var.get()) if include_phrases_var is not None else False
        def work():
            try:
                candidates=core.build_auto_glossary_candidates(pairs,target_lang=target_lang)
                if candidates and target_lang == "japanese":
                    candidates=core.resolve_auto_glossary_conflicts(settings["provider"],settings["url"],settings["model"],candidates,settings["preset"],settings["api_key"],self.auto_glossary_controller)
                result=core.save_auto_glossary_candidates(glossary_path,candidates,preserve_existing=True,include_phrases=include_phrases)
                self.events.put(("auto_glossary_done",result))
            except core.StopRequested:
                self.events.put(("auto_glossary_error",i18n.t("p0.event.stopped")))
            except Exception as exc:
                self.events.put(("auto_glossary_error",str(exc)))
        self.auto_glossary_thread=threading.Thread(target=work,daemon=True,name="auto-glossary")
        self.auto_glossary_thread.start()

    # ---------------- glossary ----------------
    def _refresh_auto_glossary_tree(self, display_only=True):
        if not hasattr(self,"auto_glossary_tree"):
            return
        path=_selected_glossary_path(self)  # 用語集タブで選んでいる言語の用語集
        if core.glossary_file_problem(path):
            return
        glossary=core.load_glossary(path)
        metadata=self._glossary_variant_metadata()
        rows={source:(target,metadata[source]) for source,target in glossary.items() if isinstance(metadata.get(source),dict) and metadata[source]}
        if display_only:
            for source,meta in metadata.items():
                if isinstance(meta,dict) and meta.get("term_kind")=="phrase" and source not in glossary and meta.get("preferred"):
                    rows[source]=(meta["preferred"],meta)
        for row_id in self.auto_glossary_tree.get_children():
            self.auto_glossary_tree.delete(row_id)
        labels={"proper":i18n.t('u4.proper'),"term":i18n.t('u4.term'),"phrase":i18n.t('u4.phrase')}
        filters=getattr(self,"auto_glossary_kind_filter_vars",{})
        for source,(target,meta) in sorted(rows.items()):
            term_kind=meta.get("term_kind","")
            variable=filters.get(term_kind)
            if display_only and variable is not None and not variable.get():
                continue
            self.auto_glossary_tree.insert("","end",values=(source,target,self._glossary_kind_label(meta),labels.get(term_kind,"")))

    def _run_glossary_action(self, action):
        self._refresh_auto_glossary_tree(display_only=False)
        try:
            return action()
        finally:
            self._refresh_auto_glossary_tree()

    @staticmethod
    def _auto_glossary_kind_summary(result):
        counts=result.get("term_kind_counts",{})
        return i18n.t("u4.kind_summary" if result.get("include_phrases") else "u4.kind_summary_no_phrases",
                      proper=counts.get('proper',0), term_count=counts.get('term',0), phrase=counts.get('phrase',0))

    def _glossary_variant_metadata(self):
        p=_selected_glossary_path(self)
        data=core.load_json(core.glossary_variants_path(p), {})
        return data if isinstance(data,dict) else {}

    def _glossary_kind_label(self, meta):
        kind=str((meta or {}).get("source_kind", "auto"))
        if kind == "import:paratranz":
            return "ParaTranz"
        if kind.startswith("base:"):
            return i18n.t('u4.base_origin', game=kind.split(":",1)[1])
        if kind.startswith("import:file"):
            return i18n.t('u4.target_yaml', target_name=i18n.t("lang." + _glossary_language(self)))
        if kind.startswith("import:mod"):
            return i18n.t('u4.target_mod', target_name=i18n.t("lang." + _glossary_language(self)))
        return i18n.t('u4.generated')

    def _choose_game_for_glossary_import(self):
        result={"game":None}
        win=tk.Toplevel(self); win.title(i18n.t('u4.choose_game_title')); win.transient(self); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=12); frm.pack(fill="both",expand=True)
        ttk.Label(frm,text=i18n.t('u4.choose_game')).pack(anchor="w")
        var=tk.StringVar(value=next(iter(core.PARADOX_STEAM_GAMES)))
        combo=ttk.Combobox(frm,textvariable=var,values=list(core.PARADOX_STEAM_GAMES),state="readonly",width=32); combo.pack(fill="x",pady=(8,10))
        row=ttk.Frame(frm); row.pack(fill="x")
        def ok(): result["game"]=var.get(); win.destroy()
        ttk.Button(row,text=i18n.t('u4.cancel'),command=win.destroy).pack(side="right")
        ttk.Button(row,text=i18n.t('u4.select'),command=ok).pack(side="right",padx=(0,6))
        win.wait_window()
        return result["game"]

    def _find_base_game_localization_root(self, game):
        install_name=game
        candidates=[]
        try:
            libs=core.discover_steam_libraries(Path.home(), sys.platform)
        except Exception:
            libs=[]
        for lib in libs:
            base=Path(lib)/"steamapps"/"common"/install_name
            for rel in ("game/localization","game/localisation","localization","localisation"):
                p=base/rel
                if p.is_dir(): candidates.append(p)
        if candidates:
            return candidates[0]
        chosen=filedialog.askdirectory(title=i18n.t('p0.select_the_base_game_localization', game=game))
        return Path(chosen) if chosen else None

    def _choose_glossary_import_mode(self):
        result={"mode":None}
        win=tk.Toplevel(self); win.title(i18n.t('u4.import_mode')); win.transient(self); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=12); frm.pack(fill="both",expand=True)
        ttk.Label(frm,text=i18n.t('u4.choose_scope'),font=("TkDefaultFont",10,"bold")).pack(anchor="w")
        var=tk.StringVar(value="common")
        ttk.Radiobutton(frm,text=i18n.t('u4.common_only'),variable=var,value="common").pack(anchor="w",pady=(10,0))
        ttk.Label(frm,text=i18n.t('u4.common_help'),wraplength=560,justify="left",foreground="#555").pack(anchor="w",padx=(22,0),pady=(2,6))
        ttk.Radiobutton(frm,text=i18n.t('u4.import_all'),variable=var,value="all").pack(anchor="w")
        ttk.Label(frm,text=i18n.t('u4.all_help'),wraplength=560,justify="left",foreground="#555").pack(anchor="w",padx=(22,0),pady=(2,8))
        ttk.Label(frm,text=i18n.t('u4.target_import_help', target_name=i18n.t("lang." + _current_target_lang(self))),wraplength=560,justify="left",foreground="#8a5a00").pack(anchor="w",pady=(4,8))
        row=ttk.Frame(frm); row.pack(fill="x",pady=(4,0))
        def ok(): result["mode"]=var.get(); win.destroy()
        ttk.Button(row,text=i18n.t('u4.cancel'),command=win.destroy).pack(side="right")
        ttk.Button(row,text=i18n.t('u4.import'),command=ok).pack(side="right",padx=(0,6))
        win.wait_window()
        return result["mode"]

    def _set_glossary_import_busy(self, busy: bool, status: str | None = None):
        """Update only Tk-side state for glossary imports."""
        self.glossary_import_busy=bool(busy)
        state="disabled" if busy else "normal"
        for name in ("glossary_base_import_btn","glossary_jp_import_btn"):
            widget=getattr(self,name,None)
            if widget is not None:
                try: widget.config(state=state)
                except Exception: pass
        if status:
            self.auto_glossary_status_var.set(status)

    def _start_glossary_import_thread(self, worker, status=None, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        if self.auto_glossary_controller is not None:
            messagebox.showinfo(APP_NAME,i18n.t('u4.generation_busy_import'))
            return False
        if self.glossary_import_busy or (self.glossary_import_thread and self.glossary_import_thread.is_alive()):
            messagebox.showinfo(APP_NAME,i18n.t('u4.import_busy'))
            return False
        self._set_glossary_import_busy(True,i18n.t("u4.import_started") if status is None else status)
        self.glossary_import_target_lang=target_lang
        self.glossary_import_target_path=str(core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,target_lang))
        def run():
            try:
                worker()
            except Exception as exc:
                record_error(i18n.t('u4.background_context'),exc)
                self.events.put(("glossary_import_error",str(exc)))
        self.glossary_import_thread=threading.Thread(target=run,daemon=True)
        self.glossary_import_thread.start()
        return True

    def _finish_import_candidates_in_worker(self, candidates, label, stats=None):
        if not candidates:
            self.events.put(("glossary_import_done",{"label":label,"empty":True,"stats":stats or {}}))
            return
        glossary_path=Path(getattr(self,"glossary_import_target_path",str(DEFAULT_GLOSSARY)))
        result=core.save_auto_glossary_candidates(glossary_path,candidates,preserve_existing=True)
        self.events.put(("glossary_import_done",{"label":label,"result":result,"stats":stats or {}}))

    def _align_japanese_with_base_root(self, japanese_targets, root: Path, target_lang="japanese"):
        source_maps, source_files=self._collect_base_source_maps(Path(root),target_lang=target_lang)
        jp_entries={}; jp_files=0
        for target in japanese_targets:
            data,count=self._collect_japanese_entries_from_target(Path(target),target_lang=target_lang)
            jp_entries.update(data); jp_files += count
        records=[]; counts={lang:0 for lang in source_maps}; unmatched=0
        for key,dst in jp_entries.items():
            for source_lang,entries in source_maps.items():
                if key in entries:
                    records.append({"key":key,"source_text":entries[key],"target_text":dst,"source_lang":source_lang})
                    counts[source_lang] += 1
                    break
            else:
                unmatched += 1
        return {"records":records,"japanese_keys":len(jp_entries),"japanese_files":jp_files,"english":counts.get("english",0),"chinese":counts.get("simp_chinese",0),"unmatched":unmatched,"source_files":source_files,"root":Path(root)}

    def _start_japanese_glossary_import(self, targets, source_kind, label, mode, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        targets=[Path(x) for x in targets if Path(x).exists()]
        if not targets:
            return
        def worker():
            self.events.put(("glossary_import_status",i18n.t('u4.target_checking', target_name=i18n.t("lang." + target_lang))))
            valid=[]
            for target in targets:
                if target.is_file():
                    if target.suffix.lower() not in {".yml",".yaml"}: continue
                    try: lang,_,_=core.parse_localization_file(target)
                    except Exception: continue
                    if lang != target_lang: continue
                elif not target.is_dir():
                    continue
                valid.append(target)
            if not valid:
                self.events.put(("glossary_import_done",{"label":label,"invalid":True,"target_lang":target_lang}))
                return
            all_pairs=[]; seen=set()
            total=len(valid)
            for idx,target in enumerate(valid,1):
                self.events.put(("glossary_import_status",i18n.t('u4.import_progress', index=idx, total=total, name=target.name)))
                pairs=self._collect_glossary_import_pairs_from_path(target,target_lang=target_lang)
                for pair in pairs:
                    ident=(str(pair.get("source","")),str(pair.get("target","")))
                    if ident not in seen:
                        seen.add(ident); all_pairs.append(pair)
            if all_pairs:
                self.events.put(("glossary_import_status",i18n.t('u4.creating_candidates', count=len(all_pairs))))
                candidates=core.build_import_glossary_candidates(all_pairs,source_kind=source_kind,mode=mode,target_lang=target_lang)
                self._finish_import_candidates_in_worker(candidates,label)
                return
            self.events.put(("glossary_import_needs_fallback",{"targets":[str(x) for x in valid],"source_kind":source_kind,"label":label,"mode":mode,"target_lang":target_lang}))
        self._start_glossary_import_thread(worker,target_lang=target_lang)

    def _start_japanese_base_fallback(self, targets, root, game, source_kind, label, mode, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        def worker():
            self.events.put(("glossary_import_status",i18n.t('u4.target_key_alignment', game=game, target_name=i18n.t("lang." + target_lang))))
            aligned=self._align_japanese_with_base_root(targets,Path(root),target_lang=target_lang)
            stats={k:aligned[k] for k in ("japanese_keys","english","chinese","unmatched")}
            if not aligned["records"]:
                self.events.put(("glossary_import_done",{"label":label,"empty":True,"stats":stats,"all_unmatched":True}))
                return
            candidates=core.build_import_glossary_candidates_from_records(aligned["records"],source_kind=source_kind,mode=mode,target_lang=target_lang)
            suffix=i18n.t('u1.common_names') if mode=="common" else i18n.t('u1.all_names')
            self._finish_import_candidates_in_worker(candidates,f"{label}（{game} / {suffix}）",stats=stats)
        self._start_glossary_import_thread(worker,target_lang=target_lang,status=i18n.t('u1.base_glossary_started', game=game))

    def _collect_japanese_entries_from_target(self, target: Path, target_lang="japanese"):
        target=Path(target)
        files=[target] if target.is_file() else core.gather_yml_files(target)
        entries={}
        used_files=0
        for f in files:
            try:
                lang, data, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang != target_lang:
                continue
            used_files += 1
            entries.update(data)
        return entries, used_files

    def _collect_base_source_maps(self, root: Path, target_lang="japanese"):
        maps={lang:{} for lang in core.glossary_source_languages(target_lang)}
        files={lang:0 for lang in maps}
        for f in core.gather_yml_files(Path(root)):
            try:
                lang, data, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang in maps:
                maps[lang].update(data)
                files[lang] += 1
        return maps, files

    def _align_japanese_with_base_game(self, japanese_targets, game, target_lang="japanese"):
        root=self._find_base_game_localization_root(game)
        if not root or not Path(root).exists():
            return None
        return self._align_japanese_with_base_root(japanese_targets,Path(root),target_lang=target_lang)

    def _save_imported_glossary_candidates(self, candidates, label, stats=None):
        if not candidates:
            msg=i18n.t('u4.no_candidates')
            if stats:
                msg = i18n.t("u4.target_no_candidates_stats", target_name=i18n.t("lang." + _current_target_lang(self)), japanese=stats.get('japanese_keys',0),
                             english=stats.get('english',0), chinese=stats.get('chinese',0), unmatched=stats.get('unmatched',0))
            messagebox.showinfo(APP_NAME,msg)
            return
        result=core.save_auto_glossary_candidates(core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,_current_target_lang(self)),candidates,preserve_existing=True)
        self.load_glossary_ui(silent=True)
        if hasattr(self,"_refresh_auto_glossary_tree"): self._refresh_auto_glossary_tree()
        self.auto_glossary_status_var.set(i18n.t('u4.import_result', label=label, added=result.get('added',0), total=result.get('total',0)))
        lines=[i18n.t('u4.import_complete', label=label),i18n.t('u4.candidates', count=result.get('total',0)),i18n.t('u4.added', count=result.get('added',0))]
        if stats:
            lines += ["",i18n.t('u4.target_keys', target_name=i18n.t("lang." + _current_target_lang(self)), count=stats.get('japanese_keys',0)),i18n.t('u4.english_matches', count=stats.get('english',0)),i18n.t('u4.chinese_matches', count=stats.get('chinese',0)),i18n.t('u4.unmatched', count=stats.get('unmatched',0))]
            if stats.get('unmatched',0):
                lines.append(i18n.t('u4.skipped_unmatched', count=stats.get('unmatched',0)))
        messagebox.showinfo(APP_NAME,"\n".join(lines))

    def _save_imported_glossary_pairs(self, pairs, source_kind, label, mode="common"):
        if not pairs:
            messagebox.showinfo(APP_NAME,i18n.t('u4.target_no_pairs', target_name=i18n.t("lang." + _current_target_lang(self))))
            return
        try:
            candidates=core.build_import_glossary_candidates(pairs,source_kind=source_kind,mode=mode,target_lang=_current_target_lang(self))
            self._save_imported_glossary_candidates(candidates,label)
        except Exception as exc:
            record_error(i18n.t('u4.import_context'),exc)
            messagebox.showerror(APP_NAME,str(exc))

    def _import_japanese_targets_with_fallback(self, targets, source_kind, label, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        targets=[Path(x) for x in targets if Path(x).exists()]
        if not targets:
            return
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,i18n.t('p0.glossary_import_is_already_running'))
            return
        mode=self._choose_glossary_import_mode()
        if not mode:
            return
        self._start_japanese_glossary_import(targets,source_kind,label,mode,target_lang=target_lang)

    def import_glossary_from_base_game(self, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,i18n.t('u4.import_busy'))
            return
        game=self._choose_game_for_glossary_import()
        if not game: return
        mode=self._choose_glossary_import_mode()
        if not mode: return
        root=self._find_base_game_localization_root(game)
        if not root or not Path(root).exists(): return
        source_kind=f"base:{game}"
        label=i18n.t('u4.base_import', game=game)
        def worker():
            self.events.put(("glossary_import_status",i18n.t('u4.base_scan', game=game)))
            if target_lang == "japanese":
                pairs=self._collect_qa_diff_pairs(Path(root),Path(root),source_langs=("english","simp_chinese"))
                self.events.put(("glossary_import_status",i18n.t('u4.creating_candidates', count=len(pairs))))
                candidates=core.build_import_glossary_candidates(pairs,source_kind=source_kind,mode=mode) if pairs else []
            else:
                aligned=self._align_japanese_with_base_root([Path(root)/target_lang],Path(root),target_lang=target_lang)
                candidates=core.build_import_glossary_candidates_from_records(aligned["records"],source_kind=source_kind,mode=mode,target_lang=target_lang)
            self._finish_import_candidates_in_worker(candidates,label)
        self._start_glossary_import_thread(worker,target_lang=target_lang,status=i18n.t('u4.base_started', game=game))

    def import_glossary_from_japanese_source(self, kind, target_lang=None):
        target_lang=target_lang or _current_target_lang(self)
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,i18n.t('u4.import_busy'))
            return
        if kind=="file":
            raw=filedialog.askopenfilename(title=i18n.t('u4.target_choose_yaml', target_name=i18n.t("lang." + target_lang)),filetypes=[("YAML","*.yml *.yaml"),("All files","*")])
        else:
            raw=filedialog.askdirectory(title=i18n.t('u4.target_choose_mod', target_name=i18n.t("lang." + target_lang)))
        if not raw: return
        source_kind="import:file" if kind=="file" else "import:mod"
        label=i18n.t('u4.target_yaml_import', target_name=i18n.t("lang." + target_lang)) if kind=="file" else i18n.t('u4.target_mod_import', target_name=i18n.t("lang." + target_lang))
        self._import_japanese_targets_with_fallback([Path(raw)],source_kind,label,target_lang=target_lang)

    def _collect_glossary_import_pairs_from_path(self, target: Path, target_lang="japanese"):
        """Backward-compatible local pairing helper used by older workflows."""
        target=Path(target)
        if not target.exists(): return []
        if target.is_file():
            if target.suffix.lower() not in {".yml",".yaml"}: return []
            try: lang,_,_=core.parse_localization_file(target)
            except Exception: return []
            if lang != target_lang: return []
            source_root=target.parent; cur=target.parent
            for _ in range(8):
                if cur.name.lower()==target_lang: source_root=cur.parent; break
                if cur.parent==cur: break
                cur=cur.parent
            return self._collect_qa_diff_pairs(source_root,target,source_langs=core.glossary_source_languages(target_lang),target_lang=target_lang)
        loc=core.mod_localization_root(target) or target
        return self._collect_qa_diff_pairs(loc,loc,source_langs=core.glossary_source_languages(target_lang),target_lang=target_lang)

    def on_glossary_import_drop_paths(self,event):
        if self.glossary_import_busy:
            self.auto_glossary_status_var.set(i18n.t('u4.import_busy'))
            return event.action if hasattr(event,"action") else None
        raw_paths=self._raw_drop_paths(event)
        targets=[]; ignored=[]
        for target in raw_paths:
            target=Path(target)
            if target.is_file():
                if target.suffix.lower() not in {".yml",".yaml"}:
                    ignored.append(target.name or str(target)); continue
            elif not target.is_dir():
                ignored.append(target.name or str(target)); continue
            targets.append(target)
        if targets:
            self._import_japanese_targets_with_fallback(targets,"import:dnd",i18n.t('u4.drop_import', count=len(targets)))
        else:
            messagebox.showinfo(APP_NAME,i18n.t('u4.target_drop_no_targets', target_name=i18n.t("lang." + _current_target_lang(self))))
        if ignored and targets:
            self.auto_glossary_status_var.set(i18n.t('u4.drop_result', targets=len(targets), ignored=len(ignored)))
        return event.action if hasattr(event,"action") else None

    def pick_glossary(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json"),("All","*")])
        if p: self.glossary_path_var.set(p); self.load_glossary_ui(silent=True)

    def show_selected_glossary_note(self, tree):
        selected=tree.selection()
        if not selected:
            self.glossary_note_var.set(i18n.t('u4.note_hint'))
            return
        source=tree.item(selected[0],"values")[0]
        metadata=self._glossary_variant_metadata().get(source,{})
        note=metadata.get("note","") if isinstance(metadata,dict) else ""
        self.glossary_note_var.set(i18n.t('u4.selected_note', source=source, note=note or i18n.t('u4.none')))

    def _show_glossary_import_text(self, parent, text):
        frame=ttk.Frame(parent); frame.pack(fill="both",expand=True,padx=8,pady=8)
        view=tk.Text(frame,wrap="word",height=20)
        scroll=ttk.Scrollbar(frame,orient="vertical",command=view.yview)
        view.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right",fill="y"); view.pack(side="left",fill="both",expand=True)
        view.insert("1.0",text); view.configure(state="disabled")
        def copy_selection(event=None):
            try:
                selected=view.get("sel.first","sel.last")
            except tk.TclError:
                return "break"
            view.clipboard_clear(); view.clipboard_append(selected)
            return "break"
        view.bind("<Control-c>",copy_selection); view.bind("<Command-c>",copy_selection)
        ttk.Button(parent,text=i18n.t('u4.copy_selection'),command=copy_selection).pack(anchor="w",padx=8)
        return view

    def import_paratranz_glossary(self):
        filename=filedialog.askopenfilename(title=i18n.t('u4.paratranz_import'),filetypes=[("JSON","*.json")])
        if not filename: return
        try:
            text,_encoding=core.decode_text_bytes(Path(filename).read_bytes())
            data=json.loads(text)
            if not core.is_paratranz_glossary(data):
                raise ValueError(i18n.t('u4.invalid_paratranz'))
            classified=core.classify_paratranz_glossary(data)
        except (OSError,UnicodeError,ValueError) as exc:
            messagebox.showerror(i18n.t('u4.paratranz_error'),str(exc)); return
        self.confirm_paratranz_import(classified)

    def confirm_paratranz_import(self, classified):
        dialog=tk.Toplevel(self); dialog.title(i18n.t('u4.paratranz_confirm')); dialog.geometry("850x700")
        dialog.transient(self); dialog.grab_set()
        labels={"items":i18n.t('u4.original_items'), "terms":i18n.t('u4.imported_terms'), "from_variants":i18n.t('u4.from_variants'),
                "rules":i18n.t('u4.rules_count'), "affixes":i18n.t('u4.affixes'), "symbols":i18n.t('u4.symbols'), "short_terms":i18n.t('u4.short_terms'),
                "spaces_fixed":i18n.t('u4.spaces_fixed'), "duplicates":i18n.t('u4.duplicates'), "note_rules":i18n.t('u4.note_rules_count')}
        summary="\n".join(f"{label}: {classified['counts'][key]}" for key,label in labels.items())
        for title,key in ((i18n.t('u4.short_warning'),"short_terms"),
                          (i18n.t('u4.rules_section'),"rules"),
                          (i18n.t('u4.note_rules_section'),"note_rules")):
            summary+="\n\n"+title+"\n"
            summary+="\n".join(f"{entry['term']} → {entry['translation']}\n  note: {entry['note']}  {entry.get('reason','')}" for entry in classified[key]) or i18n.t('u4.none')
        self._show_glossary_import_text(dialog,summary)
        options=ttk.Frame(dialog); options.pack(fill="x",padx=8,pady=8)
        language=tk.StringVar(value=_target_lang_choice(_glossary_language(self)))
        mode=tk.StringVar(value="merge")
        ttk.Label(options,text=i18n.t('u4.destination_language')).pack(side="left")
        ttk.Combobox(options,textvariable=language,values=[_target_lang_choice(lang) for lang in core.TARGET_LANGUAGES],state="readonly").pack(side="left",padx=6)
        ttk.Radiobutton(options,text=i18n.t('u4.merge'),variable=mode,value="merge").pack(side="left")
        ttk.Radiobutton(options,text=i18n.t('u4.replace'),variable=mode,value="replace").pack(side="left")
        destination=tk.StringVar()
        def update_destination(*args):
            path=core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,_target_lang_from_choice(language.get()))
            destination.set(i18n.t('u4.destination', path=path))
        language.trace_add("write",update_destination); update_destination()
        ttk.Label(dialog,textvariable=destination,wraplength=820).pack(fill="x",padx=8)
        ttk.Label(dialog,text=i18n.t('u4.replace_help'),wraplength=820).pack(fill="x",padx=8)
        def import_selected():
            path=core.glossary_path_for_language(self.glossary_path_var.get() or DEFAULT_GLOSSARY,_target_lang_from_choice(language.get()))
            try:
                result=core.save_paratranz_import(path,classified,mode.get())
            except (OSError,ValueError) as exc:
                messagebox.showerror(i18n.t('u4.paratranz_error'),str(exc),parent=dialog); return
            self.glossary_lang_var.set(language.get())
            self.load_glossary_ui(silent=True)
            self.progress_text.set(i18n.t('u4.paratranz_result', added=result['counts']['added'], updated=result['counts']['updated'], conflicts=result['counts']['conflicts']))
            dialog.destroy()
            if result["conflicts"]:
                conflicts=tk.Toplevel(self); conflicts.title(i18n.t('u4.conflicts_title')); conflicts.geometry("750x500")
                self._show_glossary_import_text(conflicts,"\n\n".join(i18n.t('u4.conflict_entry', term=entry['term'], existing=entry['existing'], incoming=entry['incoming']) for entry in result["conflicts"]))
                ttk.Button(conflicts,text=i18n.t('u4.close'),command=conflicts.destroy).pack(pady=8)
        buttons=ttk.Frame(dialog); buttons.pack(fill="x",padx=8,pady=8)
        ttk.Button(buttons,text=i18n.t('u4.import_selected'),command=import_selected).pack(side="right")
        ttk.Button(buttons,text=i18n.t('u4.abort'),command=dialog.destroy).pack(side="right",padx=6)

    def show_glossary_notation_rules(self):
        path=core.glossary_notation_rules_path(_selected_glossary_path(self))
        try:
            data=json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"rules":[],"note_rules":[]}
            if not isinstance(data,dict) or any(not isinstance(data.get(key,[]),list) or any(not isinstance(entry,dict) for entry in data.get(key,[])) for key in ("rules","note_rules")):
                raise ValueError(i18n.t('u4.invalid_rules'))
        except (OSError,ValueError) as exc:
            messagebox.showerror(i18n.t('u4.rules'),str(exc)); return
        dialog=tk.Toplevel(self); dialog.title(i18n.t('u4.rules_read_only')); dialog.geometry("850x600")
        text=i18n.t('u4.rules_help', path=path)
        for title,key in ((i18n.t('u4.rules'),"rules"),(i18n.t('u4.note_rules'),"note_rules")):
            text+="\n\n"+title+"\n"
            text+="\n\n".join(i18n.t('u4.rule_entry', term=entry.get('term',''), translation=entry.get('translation',''), note=entry.get('note',''), reason=entry.get('reason','')) for entry in data.get(key,[])) or i18n.t('u4.none')
        self._show_glossary_import_text(dialog,text)
        ttk.Button(dialog,text=i18n.t('u4.close'),command=dialog.destroy).pack(pady=8)

    def load_glossary_ui(self,silent=False):
        p=_selected_glossary_path(self)
        label=i18n.t("lang." + _glossary_language(self))
        if hasattr(self,"glossary_actual_path_var"):
            self.glossary_actual_path_var.set(i18n.t('u4.language_file', path=p))
        for tree_name in ("glossary_tree","auto_glossary_tree"):
            tree=getattr(self,tree_name,None)
            if tree is not None and hasattr(tree,"heading"): tree.heading("dst",text=label)
        problem=core.glossary_file_problem(p)
        if problem:
            self._glossary_unsafe_path=p.resolve()
            if silent:
                self.progress_text.set(problem)
                record_error(i18n.t('u4.load_context'),detail=f"{p}: {problem}")
            else:
                messagebox.showerror(i18n.t('u4.load_error'),problem)
            return
        gl=core.load_glossary(p)
        self._glossary_unsafe_path=None
        if hasattr(self,"glossary_note_var"):
            self.glossary_note_var.set(i18n.t('u4.note_hint'))
        variants=self._glossary_variant_metadata()
        if hasattr(self,"glossary_tree"):
            for x in self.glossary_tree.get_children(): self.glossary_tree.delete(x)
        if hasattr(self,"auto_glossary_tree"):
            for x in self.auto_glossary_tree.get_children(): self.auto_glossary_tree.delete(x)
        for src,dst in sorted(gl.items()):
            meta=variants.get(src)
            if meta and hasattr(self,"auto_glossary_tree"):
                self.auto_glossary_tree.insert("","end",values=(src,dst,self._glossary_kind_label(meta)))
            elif hasattr(self,"glossary_tree"):
                self.glossary_tree.insert("","end",values=(src,dst))
        if not silent: self.progress_text.set(i18n.t('u4.loaded', count=len(gl)))

    def save_glossary_ui(self):
        p=_selected_glossary_path(self)
        if p.resolve()==getattr(self,"_glossary_unsafe_path",None) or core.glossary_file_problem(p):
            messagebox.showerror(i18n.t('u4.save_error'),i18n.t('u4.unsupported_save'))
            return
        gl={}
        if hasattr(self,"glossary_tree"):
            for iid in self.glossary_tree.get_children():
                vals=self.glossary_tree.item(iid,"values")
                if len(vals)>=2: gl[str(vals[0])]=str(vals[1])
        if hasattr(self,"auto_glossary_tree"):
            for iid in self.auto_glossary_tree.get_children():
                vals=self.auto_glossary_tree.item(iid,"values")
                if len(vals)>=2: gl[str(vals[0])]=str(vals[1])
        core.save_glossary(p,gl)
        if _glossary_language(self) == core.DEFAULT_TARGET_LANG: self.glossary_path_var.set(str(p))
        self.progress_text.set(i18n.t('u4.saved', path=p))

    def add_glossary_term(self):
        src=simpledialog.askstring(i18n.t('u4.add_term'),i18n.t('u4.source_languages'))
        if not src: return
        dst=simpledialog.askstring(i18n.t('u4.add_term'),i18n.t('u4.fixed_translation', source=src, target_name=i18n.t("lang." + _glossary_language(self))))
        if dst:
            # 手動追加した語は自動分類メタデータから外し、左側へ表示する。
            p=_selected_glossary_path(self)
            variants=self._glossary_variant_metadata(); variants.pop(src,None); core.save_json(core.glossary_variants_path(p),variants)
            self.glossary_tree.insert("","end",values=(src,dst)); self.save_glossary_ui(); self.load_glossary_ui(silent=True)

    def edit_glossary_term(self):
        sel=self.glossary_tree.selection()
        if not sel: return
        src,dst=self.glossary_tree.item(sel[0],"values")
        nsrc=simpledialog.askstring(i18n.t('u4.edit_term'),i18n.t('u4.source'),initialvalue=src)
        if not nsrc: return
        ndst=simpledialog.askstring(i18n.t('u4.edit_term'),i18n.t("lang." + _glossary_language(self)),initialvalue=dst)
        if ndst is not None: self.glossary_tree.item(sel[0],values=(nsrc,ndst)); self.save_glossary_ui()

    def delete_glossary_term(self):
        for x in self.glossary_tree.selection(): self.glossary_tree.delete(x)
        self.save_glossary_ui()

    # ---------------- global LLM activity ----------------
    def _show_llm_response(self, payload, monitor=False):
        content = str(payload.get("content") or "")
        if not content:
            return
        provider = payload.get("provider", "")
        model = payload.get("model", "")
        received = datetime.now().strftime("%H:%M:%S")
        meta = i18n.t('u5.response_meta', received=received, provider=provider, model=model, count=len(content))
        if monitor:
            self.monitor_llm_last_response = content
            self.monitor_llm_response_meta = meta
            self.monitor_response_meta_var.set(meta)
            widget = self.monitor_response_text
        else:
            self.translation_llm_last_response = content
            self.translation_llm_response_meta = meta
            self.translation_response_meta_var.set(meta)
            widget = self.translation_response_text
        widget.config(state="normal")
        widget.delete("1.0", "end")
        # 常設欄は巨大応答で画面を重くしないよう末尾8,000文字を表示。全文は別窓で確認可能。
        preview = content if len(content) <= 8000 else i18n.t('u5.response_truncated', content=content[-8000:])
        widget.insert("1.0", preview)
        widget.see("end")
        widget.config(state="disabled")

    def _clear_llm_response(self, monitor=False):
        if monitor:
            self.monitor_llm_last_response = ""
            self.monitor_llm_response_meta = i18n.t('u5.waiting_response')
            self.monitor_response_meta_var.set(i18n.t('u5.waiting_response'))
            widget = self.monitor_response_text
        else:
            self.translation_llm_last_response = ""
            self.translation_llm_response_meta = i18n.t('u5.waiting_response')
            self.translation_response_meta_var.set(i18n.t('u5.waiting_response'))
            widget = self.translation_response_text
        widget.config(state="normal"); widget.delete("1.0", "end"); widget.config(state="disabled")

    def _open_llm_response_window(self, monitor=False):
        content = self.monitor_llm_last_response if monitor else self.translation_llm_last_response
        meta = self.monitor_llm_response_meta if monitor else self.translation_llm_response_meta
        if not content:
            messagebox.showinfo(APP_NAME, i18n.t('u5.no_response'))
            return
        win = tk.Toplevel(self)
        win.title(i18n.t('u5.discovery_response_title') if monitor else i18n.t('u5.translation_response_title'))
        win.geometry("900x650")
        ttk.Label(win, text=meta, padding=(10,8)).pack(fill="x")
        frame=ttk.Frame(win, padding=(10,0,10,10)); frame.pack(fill="both", expand=True)
        text=tk.Text(frame, wrap="word", font=("TkFixedFont",10))
        sy=ttk.Scrollbar(frame,orient="vertical",command=text.yview); text.configure(yscrollcommand=sy.set)
        sy.pack(side="right",fill="y"); text.pack(side="left",fill="both",expand=True)
        text.insert("1.0",content); text.config(state="disabled")

    def _handle_llm_activity(self, payload, operation=None):
        state=payload.get("state")
        provider=payload.get("provider",self.provider_var.get())
        model=payload.get("model",self.model_var.get())
        if operation:
            self.llm_operation=operation
        activity_id=payload.get("activity_id") or f"legacy-{provider}-{model}"
        if state=="start":
            self.llm_active_ids.add(activity_id)
            self.llm_busy_count = len(self.llm_active_ids)
            if self.llm_busy_since is None:
                import time
                self.llm_busy_since=time.time()
            self.llm_banner.config(bg="#d97706")
            self.llm_status_label.config(bg="#d97706",fg="white")
            self.llm_detail_label.config(bg="#d97706",fg="white")
            op=self.llm_operation or i18n.t('u5.llm_task')
            self.llm_status_var.set(i18n.t('u5.llm_running', op=op))
            self.llm_detail_var.set(i18n.t('u5.llm_waiting', provider=provider, model=model))
            self.llm_stop_btn.config(state="normal")
            self.after(250,self._update_llm_elapsed)
        elif state=="retry":
            self.llm_status_var.set(i18n.t('u5.llm_retrying', operation=self.llm_operation or i18n.t('u5.llm_task')))
            self.llm_detail_var.set(i18n.t('u5.llm_retry_detail', provider=provider, model=model, attempt=payload.get('attempt', 0), retries=payload.get('retries', 0)))
        elif state=="end":
            self.llm_active_ids.discard(activity_id)
            self.llm_busy_count=len(self.llm_active_ids)
            if self.llm_busy_count==0:
                self._set_llm_idle(i18n.t('u5.llm_idle'), i18n.t('u5.llm_finished'))
            error=str(payload.get("error") or "")
            if payload.get("success") is False and _is_llm_connection_alert_error(error):
                self._show_llm_connection_alert(self.provider_var.get(),self.url_var.get().strip(),
                                                self.model_var.get().strip(),error,
                                                context=self.llm_operation or i18n.t('u5.llm_task'),cancel_command=self.stop_current_llm)
            elif payload.get("success") is True:
                self._llm_connection_alert_key=""

    def _update_llm_elapsed(self):
        if self.llm_busy_count<=0 or self.llm_busy_since is None: return
        import time
        secs=max(0,int(time.time()-self.llm_busy_since))
        base=self.llm_detail_var.get().split(i18n.lookup("u5.elapsed").split("{base}", 1)[1].split("{seconds}", 1)[0])[0]
        self.llm_detail_var.set(i18n.t('u5.elapsed', base=base, seconds=secs))
        self.after(1000,self._update_llm_elapsed)

    def _set_llm_idle(self,status=None,detail=None):
        if status is None: status=i18n.t("u5.llm_idle")
        if detail is None: detail=i18n.t("u5.llm_not_running")
        self.llm_busy_count=0; self.llm_active_ids.clear(); self.llm_busy_since=None
        self.llm_status_var.set(status); self.llm_detail_var.set(detail)
        self.llm_banner.config(bg="#e5e7eb")
        self.llm_status_label.config(bg="#e5e7eb",fg="#222222")
        self.llm_detail_label.config(bg="#e5e7eb",fg="#444444")
        self.llm_stop_btn.config(state="disabled")

    def stop_current_llm(self):
        # 翻訳中は既存の安全な「セーブして中断」と同じ動作
        if self.controller and self.worker and self.worker.is_alive():
            self.save_and_stop(); return
        if self.chinese_controller and self.chinese_worker and self.chinese_worker.is_alive():
            self.stop_chinese_basis_translation(); return
        if getattr(self,"qa_repair_controller",None) and self.qa_repair_thread and self.qa_repair_thread.is_alive():
            self.qa_repair_controller.request_stop(save=False)
            self.llm_status_var.set(i18n.t('u5.qa_stop_requested'))
            self.llm_detail_var.set(i18n.t('u5.safe_stop_note'))
            self.llm_stop_btn.config(state="disabled")
            return
        if self.benchmark_controller and getattr(self,"benchmark_worker",None) and self.benchmark_worker.is_alive():
            self.stop_benchmark(); return
        if self.diff_controller:
            self.diff_controller.request_stop(save=False)
            self.diff_message_var.set(i18n.t('u5.diff_stop_requested'))
            self.llm_detail_var.set(i18n.t('u5.waiting_stop'))
            return
        if self.proofread_controller:
            self.proofread_controller.request_stop(save=False)
            self.issue_text.set(i18n.t('u5.proofread_stop_requested'))
            self.llm_detail_var.set(i18n.t('u5.waiting_stop'))

    # ---------------- monitor/research LLM activity ----------------
    def _handle_monitor_llm_activity(self, payload, operation=i18n.t('u6.untranslated_mod_research')):
        state = payload.get("state")
        provider = payload.get("provider", self.monitor_provider_var.get())
        model = payload.get("model", self.monitor_model_var.get())
        activity_id = payload.get("activity_id") or f"monitor-{provider}-{model}"
        if state == "start":
            self.monitor_llm_active_ids.add(activity_id)
            if self.monitor_llm_busy_since is None:
                import time
                self.monitor_llm_busy_since = time.time()
            self.monitor_llm_banner.config(bg="#2563eb")
            self.monitor_llm_status_label.config(bg="#2563eb", fg="white")
            self.monitor_llm_detail_label.config(bg="#2563eb", fg="white")
            self.monitor_llm_status_var.set(i18n.t('u6.research_llm_active', operation=operation))
            modtxt = f" / {self.monitor_current_mod}" if self.monitor_current_mod else ""
            self.monitor_llm_detail_var.set(i18n.t('u6.waiting_for_response', provider=provider, model=model, modtxt=modtxt))
            self.monitor_llm_stop_btn.config(state="normal")
            self.after(500, self._update_monitor_llm_elapsed)
        elif state == "retry":
            self.monitor_llm_status_var.set(i18n.t('u6.research_llm_retrying', operation=operation))
            self.monitor_llm_detail_var.set(i18n.t('u6.retry', provider=provider, model=model, attempt=payload.get('attempt', 0), retries=payload.get('retries', 0)))
        elif state == "end":
            self.monitor_llm_active_ids.discard(activity_id)
            if not self.monitor_llm_active_ids:
                self._set_monitor_llm_idle(i18n.t('u6.research_llm_idle'), i18n.t('u6.llm_review_ended_mod_research_may'))

    def _update_monitor_llm_elapsed(self):
        if not self.monitor_llm_active_ids or self.monitor_llm_busy_since is None:
            return
        import time
        secs=max(0,int(time.time()-self.monitor_llm_busy_since))
        base=self.monitor_llm_detail_var.get().split(i18n.t('u6.elapsed'))[0]
        self.monitor_llm_detail_var.set(i18n.t('u6.elapsed_seconds', base=base, secs=secs))
        self.after(1000,self._update_monitor_llm_elapsed)

    def _set_monitor_scan_status(self, text, detail=""):
        if self.monitor_llm_active_ids:
            return
        self.monitor_llm_banner.config(bg="#dbeafe")
        self.monitor_llm_status_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_detail_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_status_var.set(text)
        self.monitor_llm_detail_var.set(detail or i18n.t('u6.checking_untranslated_mods_automatically'))
        self.monitor_llm_stop_btn.config(state="normal" if (self.mod_research_thread and self.mod_research_thread.is_alive()) or (self.monitor_thread and self.monitor_thread.is_alive()) else "disabled")

    def _set_monitor_llm_idle(self, status=i18n.t('u6.research_llm_idle'), detail=i18n.t('u6.no_untranslated_mod_research_review_is')):
        self.monitor_llm_active_ids.clear(); self.monitor_llm_busy_since=None
        self.monitor_llm_status_var.set(status); self.monitor_llm_detail_var.set(detail)
        self.monitor_llm_banner.config(bg="#dbeafe")
        self.monitor_llm_status_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_detail_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_stop_btn.config(state="disabled")

    def stop_monitor_llm(self):
        self.mod_research_stop_event.set()
        self.monitor_stop_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.monitor_llm_status_var.set(i18n.t('u6.stop_requested'))
        self.monitor_llm_detail_var.set(i18n.t('u6.stops_safely_after_the_current_research'))

    # ---------------- misc ----------------
    def _open_path(self, path: Path):
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            elif os.name == "nt":
                os.startfile(str(path))
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))

    def open_selected_output(self):
        sel=self.queue_tree.selection(); path=None
        if sel: path=Path(self.queue_items[int(sel[0])]["output"])
        elif self.queue_items: path=Path(self.queue_items[-1]["output"])
        if not path: return
        self._open_path(path)

    def _append_log(self,text):
        self.log.config(state="normal"); self.log.insert("end",text+"\n"); self.log.see("end"); self.log.config(state="disabled")
        low=str(text).lower()
        if any(token in low for token in ("エラー", "失敗", "error", "exception", "traceback")):
            record_error("GUI log", detail=str(text))

    def _clear_log(self):
        self.log.config(state="normal"); self.log.delete("1.0","end"); self.log.config(state="disabled")

    def _poll_events(self):
        budget=app_state.EventBudget(max_items=200,max_seconds=0.012)
        try:
            while budget.allow_next():
                kind,payload=self.events.get_nowait()
                budget.record()
                if kind=="models":
                    self.model_combo["values"]=payload
                    if payload and self.model_var.get() not in payload: self.model_var.set(payload[0])
                    if hasattr(self,"benchmark_model_list"):
                        previous={self.benchmark_model_list.get(i) for i in self.benchmark_model_list.curselection()}
                        self.benchmark_model_list.delete(0,"end")
                        for model in payload:
                            self.benchmark_model_list.insert("end",model)
                        for i,model in enumerate(payload):
                            if model in previous:
                                self.benchmark_model_list.selection_set(i)
                    self.connection_var.set(i18n.t('p0.connected_models', value=self.provider_var.get(), count=len(payload)))
                    if self._llm_preflight_request is None:
                        self._llm_connection_alert_key=""
                        self._close_llm_connection_alert(reset_key=True)
                elif kind=="model_error":
                    failure=payload if isinstance(payload,dict) else {"error":str(payload)}
                    p=failure.get("provider") or self.provider_var.get()
                    failure_url=failure.get("url") or self.url_var.get().strip()
                    failure_model=failure.get("model") or self.model_var.get().strip()
                    failure_error=str(failure.get("error") or "")
                    if p=="Ollama": self.connection_var.set(i18n.t('p0.ollama_is_not_running_cannot'))
                    elif p=="LM Studio": self.connection_var.set(i18n.t('p0.cannot_connect_to_lm_studio'))
                    elif p in {"OpenAI","Anthropic","Gemini"}: self.connection_var.set(i18n.t('p0.cannot_connect_to_the_api', p=p))
                    else: self.connection_var.set(i18n.t('p0.cannot_connect_to_the_openai'))
                    if self._llm_preflight_request is None:
                        self._show_llm_connection_alert(p,failure_url,failure_model,failure_error,context=i18n.t('p0.llm_connection_check'))
                elif kind=="llm_preflight_done":
                    self._apply_llm_preflight_done(payload)
                elif kind=="llm_preflight_error":
                    self._apply_llm_preflight_error(payload)
                elif kind=="monitor_models":
                    for combo_name in ("monitor_model_combo", "status_monitor_model_combo"):
                        combo=getattr(self,combo_name,None)
                        if combo is not None:
                            combo["values"]=payload
                    if payload and self.monitor_model_var.get() not in payload:
                        self.monitor_model_var.set(payload[0])
                    self.monitor_connection_var.set(i18n.t('p0.monitor_llm_connected_models', value=self.monitor_provider_var.get(), count=len(payload)))
                    self._save_llm_preferences()
                elif kind=="monitor_model_error":
                    p=self.monitor_provider_var.get()
                    if p=="Ollama": msg=i18n.t('p0.ollama_is_not_running')
                    elif p=="LM Studio": msg=i18n.t('p0.cannot_connect_to_lm_studio')
                    else: msg=i18n.t('p0.cannot_connect_to', p=p)
                    self.monitor_connection_var.set(i18n.t('p0.monitor_llm', msg=msg))
                elif kind=="backup_restore_loaded":
                    generation,entries=payload
                    self._apply_backup_restore_loaded(generation,entries)
                elif kind=="backup_restore_load_error":
                    generation,msg=payload
                    if generation==self.backup_restore_refresh_generation:
                        self.backup_restore_refresh_thread=None
                        self.backup_restore_summary_var.set(i18n.t('p0.backup_loading_error'))
                        if hasattr(self,'backup_restore_reload_btn'): self.backup_restore_reload_btn.config(state='normal')
                        record_error(i18n.t('p0.background_loading_of_the_backup'),detail=str(msg))
                elif kind=="status_cache_restored":
                    data,rows,selected_paths=payload
                    self._apply_restored_mod_status(data,rows,selected_paths)
                elif kind=="status_cache_restore_error":
                    self.status_restore_thread=None
                    self.mod_status_summary_var.set(i18n.t('p0.could_not_restore_previous_translation'))
                    record_error(i18n.t('p0.background_restore_of_the_translation'),detail=str(payload))
                elif kind=="diagnostic_state_restored":
                    self._apply_restored_diagnostic_state(payload)
                elif kind=="diagnostic_state_restore_error":
                    self.diagnostic_restore_thread=None
                    self.diagnostic_summary_var.set(i18n.t('p0.diagnostics_idle'))
                    record_error(i18n.t('p0.background_restore_of_the_full'),detail=str(payload))
                elif kind=="judgement_log_ready":
                    token,text=payload
                    self._apply_judgement_log_ready(token,text)
                elif kind=="judgement_log_error":
                    token,msg=payload
                    self.judgement_log_thread=None
                    state=self._judgement_log_window
                    if state and state[0]==token and state[1].winfo_exists():
                        state[3].set(i18n.t('p0.detection_log_generation_error'))
                        state[2].delete('1.0','end'); state[2].insert('1.0',str(msg))
                    record_error(i18n.t('p0.generate_translation_mod_detection_log'),detail=str(msg))
                elif kind=="judgement_log_exported":
                    self.judgement_log_thread=None
                    self.mod_status_summary_var.set(i18n.t('p0.detection_log_exported'))
                    messagebox.showinfo(APP_NAME,i18n.t('p0.translation_mod_detection_log_exported', payload=payload))
                elif kind=="judgement_log_export_error":
                    self.judgement_log_thread=None
                    self.mod_status_summary_var.set(i18n.t('p0.detection_log_export_error'))
                    record_error(i18n.t('p0.export_translation_mod_detection_log'),detail=str(payload))
                    messagebox.showerror(APP_NAME,i18n.t('p0.could_not_export_the_detection', payload=payload))
                elif kind=="diff_inspector_loaded":
                    self._apply_diff_inspector_loaded(*payload)
                elif kind=="diff_inspector_batch_loaded":
                    self._apply_diff_inspector_batch_loaded(*payload)
                elif kind=="diff_inspector_load_error":
                    self.diff_load_worker=None
                    self.diff_summary_var.set(i18n.t('p0.difference_analysis_error'))
                    record_error(i18n.t('p0.background_difference_scan'),detail=str(payload))
                    messagebox.showerror(APP_NAME,str(payload))
                elif kind=="review_qa_loaded":
                    self._apply_review_qa_loaded(*payload)
                elif kind=="review_qa_batch_loaded":
                    self._apply_review_qa_batch_loaded(*payload)
                elif kind=="review_qa_error":
                    self.review_worker=None
                    self.qa_summary_var.set(i18n.t('p0.qa_analysis_error'))
                    self.review_last_qa_contexts=[]; self.review_last_qa_errors=[payload]
                    self._set_review_qa_log_enabled(True)
                    self._set_review_auto_repair_enabled(False)
                    detail=_qa_failure_display(payload)
                    record_error(i18n.t('p0.background_qa_analysis'),detail=detail)
                    messagebox.showerror(APP_NAME,detail)
                elif kind=="qa_auto_repair_done":
                    self._apply_qa_auto_repair_done(*payload)
                elif kind=="qa_auto_repair_error":
                    self._apply_qa_auto_repair_error(*payload)
                elif kind=="qa_repair_event":
                    event_kind=payload.get("kind")
                    if event_kind=="llm_activity": self._handle_llm_activity(payload,i18n.t('p0.qa_auto_fix'))
                    elif event_kind=="llm_response": self._show_llm_response(payload,monitor=False)
                    elif event_kind=="llm_metric": self._record_metric(payload.get("metric"))
                    elif event_kind=="qa_repair_progress": self._apply_qa_repair_progress(payload)
                elif kind=="single_overwrite_done":
                    self._apply_single_overwrite_done(*payload)
                elif kind=="bulk_overwrite_progress":
                    pos,total,name=payload
                    self.progress_text.set(i18n.t('p0.bulk_overwrite_2', pos=pos, total=total, name=name))
                elif kind=="bulk_overwrite_done":
                    self._apply_bulk_overwrite_done(*payload)
                elif kind=="backup_restore_done":
                    self.backup_restore_operation_thread=None
                    target,safety_root=payload
                    self._refresh_diagnostic_targets()
                    self._refresh_backup_restore_entries()
                    if not self._closing: messagebox.showinfo(APP_NAME,i18n.t('p0.restored_target_pre_restore_backup', target=target, safety_root=safety_root))
                elif kind=="backup_restore_error":
                    self.backup_restore_operation_thread=None
                    self.backup_restore_summary_var.set(i18n.t('p0.backup_restore_error'))
                    if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.could_not_restore_the_backup', payload=payload))
                elif kind=="differential_prepare_progress":
                    mode,pos,total,name=payload
                    if mode=='chinese': self.chinese_progress_var.set(i18n.t('p0.analyzing_differences', pos=pos, total=total, name=name))
                    else: self.progress_text.set(i18n.t('p0.analyzing_differences', pos=pos, total=total, name=name))
                elif kind=="differential_prepare_done":
                    self._apply_differential_prepare_done(*payload)
                elif kind=="differential_prepare_error":
                    mode,msg=payload
                    self.differential_prepare_thread=None
                    self._differential_prepare_mode=None
                    if mode=='chinese': self.chinese_progress_var.set(i18n.t('p0.difference_analysis_error'))
                    else: self.progress_text.set(i18n.t('p0.difference_analysis_error'))
                    record_error(i18n.t('p0.preparing_missing_only_translation'),detail=str(msg))
                    messagebox.showerror(APP_NAME,i18n.t('p0.could_not_analyze_differences', value=str(msg)))
                elif kind=="data_root_copy_done":
                    self._apply_data_root_change(*payload)
                elif kind=="data_root_copy_error":
                    self.data_root_move_thread=None
                    self.progress_text.set(i18n.t('p0.storage_location_change_error'))
                    record_error(i18n.t('p0.background_storage_location_copy'),detail=str(payload))
                    if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.could_not_change_the_storage', payload=payload))
                elif kind=="progress":
                    if payload.get("kind")=="llm_activity":
                        self._handle_llm_activity(payload,i18n.t('p0.translation'))
                    elif payload.get("kind")=="llm_response":
                        self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric":
                        self._record_metric(payload.get("metric"))
                    elif payload.get("kind")=="batch":
                        done,total=payload.get("done",0),max(1,payload.get("total",1)); self.progress["value"]=done/total*100
                        self.progress_text.set(i18n.t('p0.queue_file_lines', value=self.current_queue_index+1, count=len(self.queue_items), file_no=payload.get('file_no',0), file_total=payload.get('file_total',0), done=done, total=total))
                        self._append_log(i18n.t('p0.translating_lines', name=Path(payload.get('file','')).name, done=done, total=total))
                    elif payload.get("kind")=="file_done":
                        self.progress["value"]=100
                        self._append_log(i18n.t('p0.completed', name=Path(payload.get('file','')).name))
                    elif payload.get("kind")=="encoding_recovered":
                        self._append_log(i18n.t('p0.auto_repair_utf_8_bom', name=Path(payload.get('file','')).name, detected_encoding=payload.get('detected_encoding','')))
                    elif payload.get("kind")=="file_error":
                        self._append_log(i18n.t('p0.file_error', name=Path(payload.get('file','')).name, stage=payload.get('stage',''), error_type=payload.get('error_type',''), action=payload.get('action','')))
                elif kind=="chinese_queue_status":
                    item_id,status=payload
                    item=app_state.queue_item_by_id(self.chinese_queue_items,item_id)
                    if item is not None:
                        item["status"]=status
                        self._refresh_chinese_queue_tree()
                        self._save_workspace_state("chinese_progress")
                elif kind=="chinese_queue_current":
                    i,total,name=payload
                    self.chinese_queue_index=i-1
                    self.chinese_progress_var.set(i18n.t('p0.queue', i=i, total=total, name=name))
                    self._append_chinese_log(i18n.t('p0.started', name=name, i=i, total=total))
                elif kind=="chinese_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"中国語基準翻訳")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                    elif payload.get("kind")=="batch":
                        done,total=payload.get("done",0),max(1,payload.get("total",1)); self.chinese_progress["value"]=done/total*100
                        self.chinese_progress_var.set(i18n.t('p0.queue_file_lines', value=self.chinese_queue_index+1, count=len(self.chinese_queue_items), file_no=payload.get('file_no',0), file_total=payload.get('file_total',0), done=done, total=total))
                        self._append_chinese_log(i18n.t('p0.translating_lines', name=Path(payload.get('file','')).name, done=done, total=total))
                    elif payload.get("kind")=="file_done":
                        self._append_chinese_log(i18n.t('p0.completed', name=Path(payload.get('file','')).name))
                elif kind=="chinese_done":
                    self.chinese_worker=None; self.chinese_controller=None
                    self.chinese_start_btn.config(state="normal"); self.chinese_pause_btn.config(state="disabled", text=i18n.t('p0.pause')); self.chinese_stop_btn.config(state="disabled")
                    if payload.get("interrupted"):
                        self.chinese_progress_var.set(i18n.t('p0.stopped_cache_saved'))
                        self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.chinese_based_translation_stopped'))
                    else:
                        self.chinese_progress["value"]=100
                        qa_e=payload.get('qa_errors',0); qa_w=payload.get('qa_warnings',0); qa_n=payload.get('qa_notices',0); qa_r=payload.get('qa_repaired',0)
                        self.chinese_progress_var.set(i18n.t('p0.completed_items_qa_errors_warnings', processed_files=payload.get('processed_files',0), queue_total=payload.get('queue_total',len(self.chinese_queue_items)), qa_e=qa_e, qa_w=qa_w, qa_n=qa_n, qa_r=qa_r))
                        self._append_chinese_log(i18n.t('p0.auto_qa_and_fixes_for', qa_e=qa_e, qa_w=qa_w, qa_n=qa_n, qa_r=qa_r))
                        for report in payload.get('qa_reports') or []: self._append_chinese_log(i18n.t('p0.qa_repair_log', report=report))
                        for backup in payload.get('qa_backups') or []: self._append_chinese_log(i18n.t('p0.pre_qa_repair_backup', backup=backup))
                        self._append_chinese_log(i18n.t('p0.output', output=payload.get('output',self.chinese_output_var.get())))
                        self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.chinese_based_translation_completed'))
                        source_notice=self._source_gap_notice_for_items(self.chinese_queue_items)
                        msg=i18n.t('p0.chinese_based_translation_completed_auto', qa_e=qa_e, qa_w=qa_w, qa_n=qa_n, qa_r=qa_r)
                        if source_notice:
                            msg += "\n\n" + source_notice
                        if not self._closing: messagebox.showinfo(APP_NAME,msg)
                elif kind=="chinese_error":
                    record_error("中国語基準翻訳", detail=str(payload)); self.chinese_worker=None; self.chinese_controller=None
                    self.chinese_start_btn.config(state="normal"); self.chinese_pause_btn.config(state="disabled", text=i18n.t('p0.pause')); self.chinese_stop_btn.config(state="disabled")
                    self.chinese_progress_var.set(i18n.t('u3.error'))
                    self._append_chinese_log(i18n.t('p0.error', value=str(payload))); self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.an_error_occurred_in_chinese'))
                    if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.chinese_based_translation_error', value=str(payload)))
                elif kind=="benchmark_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,i18n.t('p0.model_speed_test'))
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="benchmark_model_start":
                    i,total,model=payload
                    self.benchmark_status_var.set(i18n.t('p0.speed_test', i=i, total=total, model=model))
                    self.llm_operation=i18n.t('p0.model_speed_test_2', i=i, total=total)
                elif kind=="benchmark_metric":
                    i,total,metric=payload
                    self.benchmark_status_var.set(i18n.t('p0.speed_test_completed_preparing_the', i=i, total=total))
                elif kind=="benchmark_error":
                    i,total,model,err=payload; self.benchmark_status_var.set(i18n.t('p0.failed', model=model, i=i, total=total))
                    self._append_log(i18n.t('p0.speed_test_failed', model=model, err=err))
                elif kind=="benchmark_done":
                    self.benchmark_status_var.set(i18n.t('p0.speed_test_complete')); self.benchmark_stop_btn.config(state="disabled"); self.benchmark_controller=None; self.benchmark_worker=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.speed_test_completed'))
                elif kind=="benchmark_stopped":
                    self.benchmark_status_var.set(i18n.t('p0.speed_test_stopped')); self.benchmark_stop_btn.config(state="disabled"); self.benchmark_controller=None; self.benchmark_worker=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.speed_test_stopped'))
                elif kind=="mod_locations_discovered":
                    self.detected_mod_locations=list(payload or [])
                    # Remember Steam library roots so a custom/secondary drive does not
                    # have to be rediscovered from scratch on every launch.
                    remembered=[]
                    for row in self.detected_mod_locations:
                        if row.get("kind") != "Steam Workshop":
                            continue
                        try:
                            wp=Path(row.get("path",""))
                            lib=wp.parents[3]  # <library>/steamapps/workshop/content/<appid>
                            val=str(lib)
                            if val not in remembered: remembered.append(val)
                        except Exception:
                            pass
                    old_roots=core.load_json(SAVED_STEAM_ROOTS_PATH, [])
                    if isinstance(old_roots,list):
                        for val in old_roots:
                            try:
                                if Path(val).exists() and val not in remembered: remembered.append(val)
                            except Exception: pass
                    core.save_json(SAVED_STEAM_ROOTS_PATH, remembered)
                    for x in self.discovered_mod_tree.get_children(): self.discovered_mod_tree.delete(x)
                    for i,row in enumerate(self.detected_mod_locations):
                        self.discovered_mod_tree.insert("","end",iid=f"loc_{i}",values=(row.get("game",""),row.get("kind",""),row.get("mod_count",0),row.get("path","")))
                    if self.detected_mod_locations:
                        try: self.refresh_translation_search_mods()
                        except Exception: pass
                        self.mod_discovery_status_var.set(i18n.t('p0.locations_detected', count=len(self.detected_mod_locations)))
                        restored=[]
                        wanted=set(getattr(self,"_workspace_selected_location_paths",[]) or [])
                        for i,row in enumerate(self.detected_mod_locations):
                            if str(row.get("path","")) in wanted:
                                restored.append(f"loc_{i}")
                        if restored:
                            self.discovered_mod_tree.selection_set(restored)
                            self.discovered_mod_tree.focus(restored[0]); self.discovered_mod_tree.see(restored[0])
                        else:
                            preferred_idx=next((i for i,row in enumerate(self.detected_mod_locations) if int(row.get("mod_count",0) or 0)>0),0)
                            first=f"loc_{preferred_idx}"
                            if self.discovered_mod_tree.exists(first):
                                self.discovered_mod_tree.selection_set(first); self.discovered_mod_tree.focus(first); self.discovered_mod_tree.see(first)
                        self._sync_monitor_targets_from_discovery_selection()
                    else:
                        self.mod_discovery_status_var.set(i18n.t('p0.auto_detection_failed_select_a'))
                elif kind=="mod_locations_error":
                    self.mod_discovery_status_var.set(i18n.t('p0.auto_detection_error'))
                    self._append_log(i18n.t('p0.mod_location_auto_detection', value=str(payload)))
                elif kind=="monitor_progress":
                    if payload.get("kind")=="llm_activity": self._handle_monitor_llm_activity(payload,i18n.t('p0.untranslated_monitor'))
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=True)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="monitor_status":
                    self.monitor_status_var.set(payload)
                elif kind=="monitor_log":
                    self._append_log(i18n.t('p0.untranslated_monitor_2', value=str(payload)))
                elif kind=="monitor_results":
                    for x in self.monitor_tree.get_children(): self.monitor_tree.delete(x)
                    counts={}
                    for i,c in enumerate(payload):
                        counts[c.get("kind","")]=counts.get(c.get("kind",""),0)+1
                        text=(c.get("target") or c.get("source") or "").replace("\n"," ")
                        fp=c.get("target_file") or c.get("source_file") or c.get("logical_file","")
                        self.monitor_tree.insert("","end",iid=str(i),values=(c.get("kind",""),c.get("confidence",""),Path(fp).name if fp else "",c.get("key",""),text[:500]))
                    summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                    self.monitor_summary_var.set(i18n.t('p0.untranslated_candidates_2', count=len(payload), value=f"　({summary})" if summary else ""))
                    self.monitor_status_var.set(i18n.t('p0.continuous_monitoring_last_checked', value=datetime.now().strftime('%H:%M:%S')))
                elif kind=="monitor_stopped":
                    self.monitor_status_var.set(i18n.t('p0.monitor_stopped_2'))
                    if hasattr(self,"monitor_toggle_btn"):
                        self.monitor_toggle_btn.config(text=i18n.t('p0.continuous_monitoring_started'), state="normal")
                    self.monitor_thread=None
                    self._set_monitor_llm_idle(i18n.t('p0.discovery_llm_idle'),i18n.t('p0.untranslated_monitor_stopped'))
                elif kind=="monitor_error":
                    record_error(i18n.t('p0.untranslated_monitor'), detail=str(payload))
                    self.monitor_status_var.set(i18n.t('p0.monitoring_error'))
                    if hasattr(self,"monitor_toggle_btn"):
                        self.monitor_toggle_btn.config(text=i18n.t('p0.continuous_monitoring_started'), state="normal")
                    self.monitor_thread=None
                    messagebox.showerror(APP_NAME,i18n.t('p0.untranslated_monitor_error', payload=payload))
                elif kind=="mod_status_results":
                    self.mod_research_results=[row for row in (payload or []) if _status_matches_language(row, _current_target_lang(self))]
                    self._populate_mod_status_tree()
                    self.mod_status_summary_var.set(i18n.t('p0.scan_results_entries', count=len(self.mod_research_results)))
                elif kind=="mod_status_append":
                    if not _status_matches_language(payload, _current_target_lang(self)):
                        continue
                    self.mod_research_results.append(payload)
                    self._populate_mod_status_tree()
                    self._schedule_translation_status_state_save("status_append")
                    counts={}
                    for r in self.mod_research_results: counts[r.get("status","")]=counts.get(r.get("status",""),0)+1
                    summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                    self.mod_status_summary_var.set(i18n.t('p0.scan_results_entries_2', count=len(self.mod_research_results), value=f"　{summary}" if summary else ""))
                elif kind=="mod_research_progress":
                    i,total,name=payload
                    self.monitor_current_mod=name
                    self.mod_status_summary_var.set(i18n.t('p0.scanning_in_background', i=i, total=total, name=name))
                    self._set_monitor_scan_status(i18n.t('p0.discovering_untranslated_mods', i=i, total=total), i18n.t('p0.currently_scanning', name=name))
                elif kind=="mod_research_done":
                    self.mod_research_stop_btn.config(state="disabled"); self.mod_research_thread=None
                    try: self.refresh_translation_search_mods()
                    except Exception: pass
                    if self.mod_research_stop_event.is_set():
                        self.mod_status_summary_var.set(i18n.t('p0.scan_stopped_entries_checked', count=len(self.mod_research_results)))
                    else:
                        counts={}
                        for r in self.mod_research_results: counts[r.get("status","")]=counts.get(r.get("status",""),0)+1
                        summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                        self.mod_status_summary_var.set(i18n.t('p0.scan_complete_entries', count=len(self.mod_research_results), value=f"　{summary}" if summary else ""))
                    self._set_monitor_llm_idle(i18n.t('p0.discovery_llm_idle'),i18n.t('p0.mod_translation_status_scan_completed'))
                    self._save_translation_status_state("status_research_done")
                    # A newly completed Translation Status scan can resolve restore targets
                    # that were previously shown as unknown. Refresh the rollback inventory.
                    try:
                        if hasattr(self, 'backup_restore_tree'):
                            self._refresh_backup_restore_entries()
                    except Exception as refresh_exc:
                        record_error(i18n.t('p0.resolve_backup_restore_destinations_again'), refresh_exc)
                elif kind=="mod_research_error":
                    record_error(i18n.t('p0.mod_translation_status_scan'), detail=str(payload))
                    self.mod_research_stop_btn.config(state="disabled"); self.mod_research_thread=None
                    self.mod_status_summary_var.set(i18n.t('p0.scan_error'))
                    self._set_monitor_llm_idle(i18n.t('p0.discovery_llm_idle'),i18n.t('p0.an_error_occurred_during_the'))
                    messagebox.showerror(APP_NAME,i18n.t('p0.mod_translation_status_scan_error', payload=payload))
                elif kind=="diagnostic_progress":
                    if int(payload.get("generation",-1))==self.diagnostic_generation:
                        self.diagnostic_summary_var.set(i18n.t('p0.diagnostic_progress', phase=payload.get('phase',i18n.t('u7.diagnostic_phase')), done=payload.get('done',0), total=payload.get('total',0), mod=payload.get('mod','')))
                elif kind=="diagnostic_choices_required":
                    if int(payload.get("generation",-1))==self.diagnostic_generation:
                        self.diagnostic_thread=None
                        self._set_diagnostic_repair_busy(False)
                        self.diagnostic_running_repair=False
                        shown=payload.get("before") or []
                        self.diagnostic_results=list(shown)
                        self._populate_diagnostic_results(shown)
                        self.diagnostic_summary_var.set(i18n.t('p0.choose_which_conflicting_version_to'))
                        self._save_diagnostic_state("choices_required")
                        if not self._closing: messagebox.showwarning(APP_NAME,
                            i18n.t('p0.before_repair_choose_which_version', value=str(payload.get("message", ""))))
                elif kind=="diagnostic_done":
                    if int(payload.get("generation",-1))==self.diagnostic_generation:
                        self.diagnostic_thread=None
                        if payload.get("repair"):
                            self._set_diagnostic_repair_busy(False)
                        else:
                            self.diagnostic_scan_btn.config(state="normal"); self.diagnostic_repair_btn.config(state="normal")
                        self.diagnostic_running_repair=False
                        shown=payload.get("after") if payload.get("repair") else payload.get("before")
                        count=self._populate_diagnostic_results(shown or []) or 0
                        self._refresh_diagnostic_action_state(shown or [], payload.get("integration_summary") if not payload.get("repair") else None)
                        issues=sum(1 for a in (shown or []) for x in (a.get("issues") or []) if x.get("severity") in {"ERROR","WARN"})
                        self.diagnostic_results=list(shown or [])
                        self.diagnostic_summary_var.set(i18n.t('p0.repair_complete_summary' if payload.get("repair") else 'p0.diagnostics_complete_summary', count=len(shown or []), issues=issues))
                        logs=payload.get("logs") or []
                        if logs: self._set_diagnostic_detail(i18n.t('p0.post_repair_diagnostics_are_shown', value="\n".join(logs)))
                        elif count: self._set_diagnostic_detail(i18n.t('p0.diagnostics_completed_select_an_item'))
                        self._save_diagnostic_state("repair_done" if payload.get("repair") else "diagnostic_done")
                        try:
                            if payload.get("repair"):
                                # Discard stale status summaries and re-check repaired Mods on the next status scan.
                                with self.mod_status_cache_lock:
                                    self.mod_status_cache={"version":MOD_STATUS_CACHE_VERSION,"items":{},"reset_for_version":APP_VERSION,"reset_at":datetime.now().isoformat(timespec="seconds")}
                                    core.save_json(MOD_STATUS_CACHE_PATH,self.mod_status_cache)
                        except Exception as exc:
                            record_error(i18n.t('p0.refresh_full_diagnostics_cache_after'),exc)
                elif kind=="diagnostic_error":
                    if int(payload.get("generation",-1))==self.diagnostic_generation:
                        self.diagnostic_thread=None
                        if getattr(self,"diagnostic_running_repair",False):
                            self._set_diagnostic_repair_busy(False)
                        else:
                            self.diagnostic_scan_btn.config(state="normal"); self.diagnostic_repair_btn.config(state="normal")
                        self.diagnostic_running_repair=False
                        self.diagnostic_summary_var.set(i18n.t('p0.diagnostics_error'))
                        record_error("総合診断",detail=str(payload.get("error","")))
                        if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.full_diagnostics_error', value=str(payload.get("error",""))))
                elif kind=="translation_search_mods_done":
                    if int(payload.get("generation",-1)) == self.search_mod_refresh_generation:
                        rows=list(payload.get("rows") or [])
                        wanted=set(payload.get("wanted") or self.search_selected_mod_paths or [])
                        self.search_mod_list.delete(0,"end"); self.search_mod_map={}
                        for i,(name,path) in enumerate(rows):
                            self.search_mod_list.insert("end",name); self.search_mod_map[i]=path
                            if path in wanted: self.search_mod_list.selection_set(i)
                        self._remember_translation_search_mod_selection()
                        self.search_mod_status_var.set(i18n.t('p0.target_mods', count=len(rows)))
                elif kind=="translation_search_mods_error":
                    if int(payload.get("generation",-1)) == self.search_mod_refresh_generation:
                        self.search_mod_status_var.set(i18n.t('p0.could_not_load_target_mods'))
                        record_error(i18n.t('p0.load_target_mods_for_translation'), detail=str(payload.get("error","")))
                elif kind=="translation_search_progress":
                    if int(payload.get("generation",-1)) == self.search_generation:
                        self.search_summary_var.set(i18n.t('p0.searching_in_background', game=payload.get('game',''), done=payload.get('done',0), total=payload.get('total',0), mod=payload.get('mod','')))
                elif kind=="translation_search_done":
                    if int(payload.get("generation",-1)) == self.search_generation:
                        for iid in self.search_tree.get_children(): self.search_tree.delete(iid)
                        self.search_result_map={}
                        for n,row in enumerate(payload.get("rows") or []):
                            iid=f"r{n}"
                            converted=dict(row)
                            for k in ("target_file","source_file","shown_file"):
                                if converted.get(k): converted[k]=Path(converted[k])
                            self.search_result_map[iid]=converted
                            shown_file=converted.get("shown_file")
                            shown_value=i18n.t('p0.untranslated') if converted.get("missing") else converted.get("value","")
                            self.search_tree.insert("","end",iid=iid,values=(converted.get("mod_name",""),self._localization_display_path(shown_file) if shown_file else "",converted.get("key",""),shown_value[:180]))
                        self.search_summary_var.set(i18n.t('p0.searched_mods_matches_untranslated', game=payload.get('game',''), scanned_mods=payload.get('scanned_mods',0), count=len(payload.get('rows') or []), missing=payload.get('missing',0)))
                        self.search_thread=None
                        self._save_workspace_state("translation_search_done")
                elif kind=="translation_search_error":
                    if int(payload.get("generation",-1)) == self.search_generation:
                        self.search_thread=None
                        self.search_summary_var.set(i18n.t('p0.search_error'))
                        record_error(i18n.t('p0.translation_search'), detail=str(payload.get("error","")))
                        messagebox.showerror(APP_NAME,i18n.t('p0.translation_search_error', value=str(payload.get("error",""))))
                elif kind=="normal_log":
                    self._append_log(str(payload))
                elif kind=="chinese_log":
                    self._append_chinese_log(str(payload))
                elif kind=="queue_refresh": self._refresh_queue_tree()
                elif kind=="done":
                    self.worker=None
                    info = payload if isinstance(payload, dict) else {}
                    interrupted = bool(info.get("interrupted", False))
                    unresolved = int(info.get("unresolved_items", 0) or 0)
                    recovered = int(info.get("recovered_items", 0) or 0)
                    if not interrupted and not unresolved:
                        self._delete_session()
                    self._finish_controls()
                    self._refresh_queue_tree()
                    if interrupted:
                        self._append_log(i18n.t('p0.translation_stopped_cache_saved'))
                        self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.translation_stopped'))
                        self.progress_text.set(i18n.t('p0.stopped_cache_saved'))
                    else:
                        self._append_log(i18n.t('p0.translation_complete_items_recovered_by', processed_items=info.get('processed_items',0), selected_total=info.get('selected_total',0), recovered=recovered, unresolved=unresolved))
                        idle_detail = i18n.t('p0.translation_complete_unresolved_items', unresolved=unresolved) if unresolved else i18n.t('p0.translation_completed')
                        self._set_llm_idle(i18n.t('p0.llm_idle'),idle_detail)
                        self.progress["value"]=100
                        self.progress_text.set(i18n.t('p0.translation_complete_unresolved_items_2', unresolved=unresolved) if unresolved else i18n.t('p0.selected_translations_completed'))
                        source_notice=self._source_gap_notice_for_items(self.queue_items)
                        msg=i18n.t('p0.selected_translations_completed_completed_items', processed_items=info.get('processed_items', 0), selected_total=info.get('selected_total', 0), recovered=recovered, unresolved=unresolved)
                        if info.get("queue_report"):
                            msg += i18n.t('p0.unattended_run_report', queue_report=info.get('queue_report'))
                        if unresolved:
                            msg += i18n.t('p0.unresolved_items_remain_in_the')
                        if source_notice:
                            msg += "\n\n" + source_notice
                        if not self._closing: messagebox.showinfo(APP_NAME,msg)
                elif kind=="fatal":
                    self.worker=None
                    self._append_log(i18n.t('p0.error', value=str(payload)))
                    record_error(i18n.t('p0.fatal_translation_error'), detail=str(payload)); self._finish_controls(); self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.an_error_occurred_during_translation'))
                    if not self._closing: messagebox.showerror(APP_NAME,payload)
                elif kind=="diff_translate_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"差分翻訳")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="diff_translate_status":
                    i,total,key=payload; self.diff_message_var.set(i18n.t('p0.translating_missing_entries', i=i, total=total, entry_key=key))
                elif kind=="diff_translate_done":
                    result=payload if isinstance(payload,dict) else {"written":payload,"untranslated":[],"backups":[],"total":payload}
                    left=list(result.get("untranslated") or [])
                    self.diff_controller=None; self.diff_translate_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.missing_only_translation_completed_entries', written=result.get('written',0)))
                    if not self._closing:
                        if len(self.diff_batch_contexts)>1:
                            pairs=[{"source":c["source_path"],"target":c["target_path"],"lang":c["lang"]} for c in self.diff_batch_contexts]
                            self.load_diff_pairs(pairs)
                        else:
                            self.load_diff_inspector()
                    message=i18n.t("p0.diff_complete_untranslated" if left else "p0.diff_complete",
                              written=result.get('written',0), spaces_removed=result.get('spaces_removed',0), count=len(left))
                    self.diff_message_var.set(message)
                    if left and not self._closing:
                        lines="\n".join(i18n.t('p0.untranslated_entry', file=row['file'], entry_key=row['key'], reason=row['reason']) for row in left[:15])
                        more=i18n.t('p0.more_entries', value=len(left)-15) if len(left)>15 else ""
                        messagebox.showwarning(APP_NAME,i18n.t('p0.these_keys_could_not_be', lines=lines, more=more))
                elif kind=="diff_translate_stopped":
                    self.diff_controller=None; self.diff_translate_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.missing_only_translation_stopped')); self.diff_message_var.set(i18n.t('p0.missing_only_translation_stopped'))
                elif kind=="diff_translate_error":
                    record_error("差分翻訳", detail=str(payload)); self.diff_controller=None; self.diff_translate_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.an_error_occurred_in_missing')); self.diff_message_var.set(i18n.t('p0.missing_only_translation_error', value=str(payload)))
                    if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.missing_only_translation_error', value=str(payload)))
                elif kind=="auto_glossary_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,i18n.t('p0.auto_glossary'))
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="auto_glossary_done":
                    self.auto_glossary_controller=None; self.auto_glossary_thread=None
                    self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.auto_glossary_completed'))
                    self.load_glossary_ui(silent=True)
                    if hasattr(self,"_refresh_auto_glossary_tree"): self._refresh_auto_glossary_tree()
                    kind_summary=App._auto_glossary_kind_summary(payload)
                    self.auto_glossary_status_var.set(i18n.t('p0.added_candidates_variants', added=payload.get('added',0), total=payload.get('total',0), conflicts=payload.get('conflicts',0), kind_summary=kind_summary))
                    if not self._closing: messagebox.showinfo(APP_NAME, i18n.t('p0.auto_glossary_completed_candidates_new', total=payload.get('total',0), added=payload.get('added',0), conflicts=payload.get('conflicts',0), kind_summary=kind_summary))
                elif kind=="auto_glossary_error":
                    self.auto_glossary_controller=None; self.auto_glossary_thread=None
                    self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.auto_glossary_stopped'))
                    self.auto_glossary_status_var.set(i18n.t('p0.auto_glossary_2', value=str(payload)))
                    if str(payload)!=i18n.t("p0.event.stopped") and not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.auto_glossary_error', value=str(payload)))
                elif kind=="glossary_import_status":
                    self.auto_glossary_status_var.set(str(payload))
                elif kind=="glossary_import_needs_fallback":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,i18n.t('p0.find_matching_source_text_in'))
                    if self._closing:
                        continue
                    messagebox.showinfo(APP_NAME,
                        i18n.t('u4.target_fallback_help', target_name=i18n.t("lang." + payload.get("target_lang","japanese"))))
                    game=self._choose_game_for_glossary_import()
                    if game:
                        root=self._find_base_game_localization_root(game)
                        if root and Path(root).exists():
                            self._start_japanese_base_fallback(
                                [Path(x) for x in payload.get("targets",[])],root,game,
                                payload.get("source_kind","import:mod"),payload.get("label",i18n.t('u4.target_localization_import', target_name=i18n.t("lang." + payload.get("target_lang","japanese")))),payload.get("mode","common"),target_lang=payload.get("target_lang","japanese"))
                elif kind=="glossary_import_done":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,i18n.t('p0.glossary_import_complete'))
                    if payload.get("invalid"):
                        if not self._closing: messagebox.showinfo(APP_NAME,i18n.t('u4.target_invalid', target_name=i18n.t("lang." + payload.get("target_lang","japanese"))))
                    else:
                        label=payload.get("label",i18n.t('p0.import_glossary'))
                        result=payload.get("result") or {}
                        stats=payload.get("stats") or {}
                        if not result:
                            lines=[i18n.t('p0.completed_2', label=label),i18n.t('p0.no_glossary_candidates_were_available')]
                        else:
                            self.load_glossary_ui(silent=True)
                            if hasattr(self,"_refresh_auto_glossary_tree"): self._refresh_auto_glossary_tree()
                            self.auto_glossary_status_var.set(i18n.t('p0.added_candidates', label=label, added=result.get('added',0), total=result.get('total',0)))
                            lines=[i18n.t('p0.completed_2', label=label),i18n.t('p0.candidates', total=result.get('total',0)),i18n.t('p0.new_entries', added=result.get('added',0))]
                        if stats:
                            lines += ["",i18n.t('u4.target_keys', target_name=i18n.t("lang." + getattr(self,"glossary_import_target_lang","japanese")), count=stats.get('japanese_keys',0)),i18n.t('p0.english_matches', english=stats.get('english',0)),i18n.t('p0.chinese_matches', chinese=stats.get('chinese',0)),i18n.t('p0.unmatched', unmatched=stats.get('unmatched',0))]
                            if stats.get("unmatched",0): lines.append(i18n.t('p0.skipped_entries_with_no_matching', unmatched=stats.get('unmatched',0)))
                        if not self._closing: messagebox.showinfo(APP_NAME,"\n".join(lines))
                elif kind=="glossary_import_error":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,i18n.t('p0.glossary_import_error'))
                    if not self._closing: messagebox.showerror(APP_NAME,i18n.t('p0.glossary_import_error_2', value=str(payload)))
                elif kind=="proofread_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,i18n.t('p0.ai_spelling_and_typo_check'))
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="proofread":
                    self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",payload); self.issue_text.set(i18n.t('p0.ai_proofreading_results_are_shown')); self.proofread_controller=None; self.proofread_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.ai_proofreading_completed'))
                elif kind=="proofread_stopped":
                    self.issue_text.set(i18n.t('p0.ai_proofreading_stopped')); self.proofread_controller=None; self.proofread_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.ai_proofreading_stopped_2'))
                elif kind=="proofread_error":
                    record_error(i18n.t('p0.ai_proofreading'), detail=str(payload))
                    self.issue_text.set(i18n.t('p0.ai_proofreading_error', payload=payload)); self.proofread_controller=None; self.proofread_thread=None; self._set_llm_idle(i18n.t('p0.llm_idle'),i18n.t('p0.an_error_occurred_during_ai'))
        except queue.Empty:
            pass
        self._refresh_operation_states()
        delay=1 if not self.events.empty() else 100
        self.after(delay,self._poll_events)

    def _finish_controls(self):
        self.start_btn.config(state="normal"); self.pause_btn.config(state="disabled",text=i18n.t('p0.pause')); self.stop_btn.config(state="disabled"); self.controller=None

    def on_close(self):
        """Handle the window × button according to the user's preference."""
        self._save_llm_preferences()
        setting = ui_status.close_action_from_label(self.close_action_var.get())

        if setting == "confirm":
            action = self._show_close_choice_dialog()
        elif setting == "minimize":
            action = "minimize"
        else:
            action = "quit"

        if action == "cancel":
            return
        if action == "minimize":
            self.iconify()
            return
        self._begin_graceful_exit()



if __name__ == "__main__":
    app=App(); app.mainloop()
