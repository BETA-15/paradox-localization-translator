#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import queue
import hashlib
import platform
import traceback
import zipfile
import subprocess
import sys
import threading
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

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DND_AVAILABLE = True
    BaseTk = TkinterDnD.Tk
except Exception:
    DND_FILES = None
    DND_AVAILABLE = False
    BaseTk = tk.Tk

APP_NAME = "Paradox Localization Translator"
APP_VERSION = "0.11.21"
MOD_STATUS_CACHE_VERSION = 3


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
    saved = _load_saved_data_root()
    if saved is not None and _is_writable_dir(saved):
        return saved
    root = _default_data_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _configure_data_root(root: Path):
    """Update all generated-file locations after the user changes the storage root."""
    global DATA_ROOT, APP_HOME, OUTPUT_ROOT, SESSION_PATH, DEFAULT_GLOSSARY
    global STATS_PATH, PROFILES_PATH, CACHE_ROOT, CACHE_REGISTRY_PATH, BACKUP_ROOT
    global SAVED_STEAM_ROOTS_PATH, LOG_ROOT, MOD_STATUS_CACHE_PATH, APP_PREFS_PATH
    global RESUME_STATE_PATH, RESUME_HISTORY_PATH, WORK_STATE_ROOT, MIGRATION_STATE_PATH
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
    SAVED_STEAM_ROOTS_PATH = APP_HOME / "steam_library_roots.json"
    MOD_STATUS_CACHE_PATH = APP_HOME / "mod_translation_status_cache.json"
    APP_PREFS_PATH = APP_HOME / "app_preferences.json"
    # Stable, version-independent resume files. APP_VERSION is metadata only.
    RESUME_STATE_PATH = APP_HOME / "resume_state.json"
    RESUME_HISTORY_PATH = LOG_ROOT / "resume_history.jsonl"
    # Version-independent runtime/work state belongs under the user data root,
    # never beside the executable/app bundle.
    WORK_STATE_ROOT = DATA_ROOT / "作業データ"
    MIGRATION_STATE_PATH = APP_HOME / "storage_migration.json"
    for d in (DATA_ROOT, APP_HOME, OUTPUT_ROOT, CACHE_ROOT, BACKUP_ROOT, LOG_ROOT, WORK_STATE_ROOT):
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
        "app_preferences.json": APP_PREFS_PATH,
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
    try:
        previous = core.load_json(MIGRATION_STATE_PATH, {})
        result["previous_run"] = previous.get("timestamp") if isinstance(previous, dict) else None
        core.save_json(MIGRATION_STATE_PATH, result)
        if result["copied"]:
            LOG_ROOT.mkdir(parents=True, exist_ok=True)
            with (LOG_ROOT / "storage_migration.log").open("a", encoding="utf-8") as fh:
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


def _error_log_path() -> Path:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    return LOG_ROOT / f"errors_{datetime.now().strftime('%Y%m%d')}.log"


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


def _automatic_output_root() -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    return OUTPUT_ROOT


class App(BaseTk):
    def __init__(self):
        super().__init__()
        APP_HOME.mkdir(parents=True, exist_ok=True)
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        BACKUP_ROOT.mkdir(parents=True, exist_ok=True)
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
        self.model_stats = core.load_json(STATS_PATH, {})
        self.model_profiles = core.load_json(PROFILES_PATH, {})
        self.benchmark_controller: core.TranslationController | None = None
        self.proofread_controller: core.TranslationController | None = None
        self.llm_busy_count = 0
        self.llm_active_ids = set()
        self.llm_busy_since = None
        self.llm_operation = ""
        self.llm_status_var = tk.StringVar(value="LLM 待機中")
        self.llm_detail_var = tk.StringVar(value="LLM処理が始まるとここに常時表示されます")
        self.monitor_llm_status_var = tk.StringVar(value="探索用LLM 待機中")
        self.monitor_llm_detail_var = tk.StringVar(value="未翻訳Modの探索・精査状況をここに表示します")
        self.monitor_llm_busy_since = None
        self.monitor_llm_active_ids = set()
        self.monitor_current_mod = ""
        self.dnd_status_var = tk.StringVar(value="ドラッグ＆ドロップ: 初期化確認中")
        self.translation_llm_last_response = ""
        self.monitor_llm_last_response = ""
        self.translation_llm_response_meta = "応答待機中"
        self.monitor_llm_response_meta = "応答待機中"

        # 前回使用したLLM設定は通常セッションとは別に常時保存する。
        # APIキーだけは保存しない。
        self.app_preferences = core.load_json(APP_PREFS_PATH, {})
        if not isinstance(self.app_preferences, dict):
            self.app_preferences = {}
        last_translation = self.app_preferences.get("translation_llm", {})
        last_monitor = self.app_preferences.get("monitor_llm", {})
        close_prefs = self.app_preferences.get("window_close", {}) if isinstance(self.app_preferences.get("window_close", {}), dict) else {}
        # ×ボタン時の既定動作。confirm / minimize / quit の3種類。
        self.close_action_var = tk.StringVar(value={"confirm":"毎回確認","minimize":"最小化","quit":"終了"}.get(close_prefs.get("action"), close_prefs.get("action", "毎回確認")))

        self.provider_var = tk.StringVar(value=last_translation.get("provider", "Ollama"))
        self.api_key_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value=last_translation.get("url") or core.default_url_for_provider(last_translation.get("provider", "Ollama")))
        self.model_var = tk.StringVar(value=last_translation.get("model") or core.DEFAULT_MODEL)
        self.preset_var = tk.StringVar(value="CK3")
        self.batch_var = tk.IntVar(value=max(1, int(last_translation.get("batch", 40) or 40)))
        self.workers_var = tk.IntVar(value=max(1, int(last_translation.get("workers", 1) or 1)))
        self.performance_preset_var = tk.StringVar(value="標準（40 / 1）")
        self.repair_var = tk.BooleanVar(value=True)
        self.dual_var = tk.BooleanVar(value=False)
        self.autoqa_var = tk.BooleanVar(value=True)
        self.chinese_autoqa_var = tk.BooleanVar(value=bool(last_translation.get("chinese_autoqa", True)))
        self.glossary_path_var = tk.StringVar(value=str(DEFAULT_GLOSSARY))
        self.auto_glossary_status_var = tk.StringVar(value="自動用語作成: 待機中")
        self.auto_glossary_controller = None
        self.glossary_import_thread = None
        self.glossary_import_busy = False
        self.connection_var = tk.StringVar(value="LLM接続確認中…")
        self.profile_var = tk.StringVar(value="")
        self.data_root_var = tk.StringVar(value=str(DATA_ROOT))
        self.progress_text = tk.StringVar(value="待機中")
        self.review_src_var = tk.StringVar()
        self.review_dst_var = tk.StringVar()
        self.review_src_display_var = tk.StringVar()
        self.review_dst_display_var = tk.StringVar()
        self.qa_summary_var = tk.StringVar(value="QA未実行")
        self.review_source_lang = "english"

        # Normal translation input/output display
        self.normal_input_var = tk.StringVar(value="")
        self.normal_output_var = tk.StringVar(value=str(OUTPUT_ROOT))
        self.normal_status_var = tk.StringVar(value="YAML / localizationフォルダを追加してください")

        # Simplified Chinese basis translation
        self.chinese_input_var = tk.StringVar(value="")
        self.chinese_output_var = tk.StringVar(value=str(OUTPUT_ROOT / "中国語基準翻訳"))
        self.chinese_status_var = tk.StringVar(value="簡体字中国語YAMLを選択してください")
        self.chinese_progress_var = tk.StringVar(value="待機中")
        self.chinese_controller: core.TranslationController | None = None
        self.chinese_worker = None
        self.chinese_queue_items = []
        self.chinese_queue_index = -1

        # Difference inspector / translation search
        self.diff_src_var = tk.StringVar(value="")
        self.diff_dst_var = tk.StringVar(value="")
        self.diff_src_display_var = tk.StringVar(value="")
        self.diff_dst_display_var = tk.StringVar(value="")
        self.diff_summary_var = tk.StringVar(value="差分未調査")
        self.diff_source_entries = {}
        self.diff_target_entries = {}
        self.diff_rows = []
        self.diff_row_by_key = {}
        self.diff_controller: core.TranslationController | None = None
        self.diff_source_lang = "english"
        self.search_path_var = tk.StringVar(value="")  # legacy/internal compatibility; search is now game-scoped
        self.search_game_var = tk.StringVar(value="Crusader Kings III")
        self.search_query_var = tk.StringVar(value="")
        self.search_summary_var = tk.StringVar(value="検索待機中")
        self.search_result_map = {}

        # Live untranslated-localization monitor
        self.monitor_path_var = tk.StringVar(value="")  # legacy / first monitor target
        self.monitor_target_paths = []
        self.monitor_target_summary_var = tk.StringVar(value="監視対象: 翻訳状況タブでゲーム / Mod場所を選択してください")
        self.monitor_interval_var = tk.IntVar(value=15)
        self.monitor_use_llm_var = tk.BooleanVar(value=True)
        self.monitor_check_translation_mods_var = tk.BooleanVar(value=True)
        self.monitor_provider_var = tk.StringVar(value=last_monitor.get("provider", "Ollama"))
        self.monitor_url_var = tk.StringVar(value=last_monitor.get("url") or core.default_url_for_provider(last_monitor.get("provider", "Ollama")))
        self.monitor_api_key_var = tk.StringVar(value="")
        self.monitor_model_var = tk.StringVar(value=last_monitor.get("model", ""))
        self.monitor_connection_var = tk.StringVar(value="監視用LLM: 未確認")
        self.monitor_status_var = tk.StringVar(value="監視停止中")
        self.monitor_summary_var = tk.StringVar(value="未翻訳候補: --")
        self.mod_status_summary_var = tk.StringVar(value="調査結果: --")
        self.mod_status_search_var = tk.StringVar(value="")
        self.mod_status_search_result_var = tk.StringVar(value="")
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
        self.mod_discovery_status_var = tk.StringVar(value="ゲーム/Mod場所: 未検出")
        self.discovery_multi_select_var = tk.BooleanVar(value=False)
        self.mod_status_cache_lock = threading.Lock()
        self.mod_status_cache = core.load_json(MOD_STATUS_CACHE_PATH, {"version": MOD_STATUS_CACHE_VERSION, "items": {}})
        if not isinstance(self.mod_status_cache, dict) or self.mod_status_cache.get("version") != MOD_STATUS_CACHE_VERSION:
            self.mod_status_cache = {"version": MOD_STATUS_CACHE_VERSION, "items": {}}
        self.report_callback_exception = self._tk_callback_exception
        sys.excepthook = self._sys_excepthook
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._thread_excepthook

        self._build_ui()
        for actual, display in ((self.review_src_var,self.review_src_display_var),(self.review_dst_var,self.review_dst_display_var),(self.diff_src_var,self.diff_src_display_var),(self.diff_dst_var,self.diff_dst_display_var)):
            actual.trace_add("write", lambda *_args, a=actual, d=display: d.set(self._localization_display_path(a.get())))
            display.set(self._localization_display_path(actual.get()))
        self.after(100, self._poll_events)
        self.after(300, self.refresh_models)
        self.after(450, self.refresh_monitor_models)
        self.after(500, self._offer_restore_session)
        self.after(600, self._restore_cached_mod_status)
        self.after(700, self.discover_mod_locations)

    # ---------------- UI ----------------
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
        self.llm_stop_btn = ttk.Button(self.llm_banner, text="翻訳LLM停止", command=self.stop_current_llm, state="disabled")
        self.llm_stop_btn.pack(side="right")

        self.monitor_llm_banner = tk.Frame(llm_row, bg="#dbeafe", padx=9, pady=5)
        self.monitor_llm_banner.pack(side="left", fill="x", expand=True, padx=(4,0))
        self.monitor_llm_status_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_status_var, bg="#dbeafe", fg="#1e3a8a", font=("", 10, "bold"))
        self.monitor_llm_status_label.pack(side="left")
        self.monitor_llm_detail_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_detail_var, bg="#dbeafe", fg="#1e3a8a")
        self.monitor_llm_detail_label.pack(side="left", padx=(8,0))
        self.monitor_llm_stop_btn = ttk.Button(self.monitor_llm_banner, text="探索LLM停止", command=self.stop_monitor_llm, state="disabled")
        self.monitor_llm_stop_btn.pack(side="right")

        # 実際にLLMから返ってきた最新応答を、そのまま確認するための読み取り専用欄。
        # 翻訳用と探索用を分離し、処理が本当に進んでいるか目視できるようにする。
        response_row = ttk.Frame(self, padding=(10, 0, 10, 2))
        response_row.pack(fill="x")
        tr_frame = ttk.LabelFrame(response_row, text="翻訳用LLM 最新応答（読み取り専用）", padding=5)
        tr_frame.pack(side="left", fill="both", expand=True, padx=(0, 5))
        tr_head = ttk.Frame(tr_frame); tr_head.pack(fill="x")
        self.translation_response_meta_var = tk.StringVar(value="応答待機中")
        ttk.Label(tr_head, textvariable=self.translation_response_meta_var, foreground="#555").pack(side="left")
        ttk.Button(tr_head, text="全文を開く", command=lambda:self._open_llm_response_window(False)).pack(side="right")
        ttk.Button(tr_head, text="クリア", command=lambda:self._clear_llm_response(False)).pack(side="right", padx=(0,5))
        self.translation_response_text = tk.Text(tr_frame, height=2, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.translation_response_text.pack(fill="x", pady=(4,0))

        mon_frame = ttk.LabelFrame(response_row, text="探索用LLM 最新応答（読み取り専用）", padding=5)
        mon_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        mon_head = ttk.Frame(mon_frame); mon_head.pack(fill="x")
        self.monitor_response_meta_var = tk.StringVar(value="応答待機中")
        ttk.Label(mon_head, textvariable=self.monitor_response_meta_var, foreground="#555").pack(side="left")
        ttk.Button(mon_head, text="全文を開く", command=lambda:self._open_llm_response_window(True)).pack(side="right")
        ttk.Button(mon_head, text="クリア", command=lambda:self._clear_llm_response(True)).pack(side="right", padx=(0,5))
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
        self.tab_settings = ttk.Frame(nb, padding=10)
        self.tab_help = ttk.Frame(nb, padding=10)
        nb.add(self.tab_translate, text="翻訳 / キュー")
        nb.add(self.tab_chinese, text="中国語基準翻訳")
        nb.add(self.tab_review, text="QA / 比較編集")
        nb.add(self.tab_diff, text="差分調査")
        nb.add(self.tab_search, text="翻訳検索")
        nb.add(self.tab_glossary, text="用語集")
        nb.add(self.tab_models, text="モデル / 接続")
        nb.add(self.tab_monitor, text="未翻訳監視")
        nb.add(self.tab_status, text="翻訳状況")
        nb.add(self.tab_settings, text="設定")
        nb.add(self.tab_help, text="使い方")
        self._build_translate_tab()
        self._build_chinese_tab()
        self._build_review_tab()
        self._build_diff_tab()
        self._build_search_tab()
        self._build_glossary_tab()
        self._build_models_tab()
        self._build_monitor_tab()
        self._build_status_tab()
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
                record_error("Ctrl複数選択", exc)
            return None

        widget.bind("<Control-Button-1>", on_ctrl_click, add="+")

    def _build_translate_tab(self):
        t = self.tab_translate

        # 通常翻訳も中国語基準翻訳と同じ左右2ブロック構成に統一する。
        main=ttk.Panedwindow(t,orient="horizontal"); main.pack(fill="both",expand=True)
        left=ttk.Frame(main,padding=(0,0,6,0)); right=ttk.Frame(main,padding=(6,0,0,0))
        main.add(left,weight=2); main.add(right,weight=3)

        intro=ttk.LabelFrame(left,text="通常翻訳",padding=9); intro.pack(fill="x")
        ttk.Label(intro,text=("英語などのParadox localizationを日本語化します。YAMLまたはMod / localizationフォルダを追加すると、直接翻訳キューへ登録します。\n"
                              "LLM・バッチ・並列・プリセット・用語集などは［モデル / 接続］タブの共通設定を使用します。"),
                  wraplength=430,foreground="#333",justify="left").pack(fill="x")

        src=ttk.LabelFrame(left,text="入力 / 出力",padding=9); src.pack(fill="x",pady=(5,0)); src.columnconfigure(0,weight=1)
        ttk.Label(src,text="YAML / Mod / localizationフォルダ").grid(row=0,column=0,sticky="w")
        self.normal_input_entry=ttk.Entry(src,textvariable=self.normal_input_var,state="readonly")
        self.normal_input_entry.grid(row=1,column=0,sticky="ew",pady=(3,0))
        pickbar=ttk.Frame(src); pickbar.grid(row=2,column=0,sticky="ew",pady=(5,0))
        normal_add_menu=tk.Menu(pickbar,tearoff=False)
        normal_add_menu.add_command(label="YAMLファイルを追加",command=self.add_files)
        normal_add_menu.add_command(label="Mod / localizationフォルダを追加",command=self.add_folder)
        self.add_menu_button=ttk.Menubutton(pickbar,text="追加",menu=normal_add_menu)
        self.add_menu_button.pack(side="left")
        ttk.Label(pickbar,text="選択するとそのまま翻訳キューへ追加します",foreground="#666").pack(side="left",padx=(8,0))
        ttk.Label(src,textvariable=self.normal_status_var,foreground="#555",wraplength=430,justify="left").grid(row=3,column=0,sticky="w",pady=(4,0))
        ttk.Separator(src,orient="horizontal").grid(row=4,column=0,sticky="ew",pady=5)
        ttk.Label(src,text="出力先ルート").grid(row=5,column=0,sticky="w")
        ttk.Entry(src,textvariable=self.normal_output_var).grid(row=6,column=0,sticky="ew",pady=(3,0))
        outbar=ttk.Frame(src); outbar.grid(row=7,column=0,sticky="ew",pady=(5,0))
        ttk.Button(outbar,text="選択",command=self.pick_normal_output).pack(side="left")
        ttk.Button(outbar,text="開く",command=lambda:self._open_path(Path(self.normal_output_var.get()))).pack(side="left",padx=(5,0))

        settings=ttk.LabelFrame(left,text="モデル / 接続（共通設定）",padding=9); settings.pack(fill="x",pady=(5,0))
        ttk.Label(settings,text="プロバイダ / URL / モデル / APIキー / バッチ / 並列 / プリセット / 用語集は［モデル / 接続］タブの共通設定を使用します。",wraplength=430,justify="left").pack(anchor="w")
        ttk.Button(settings,text="モデル / 接続を開く",command=lambda:self.notebook.select(self.tab_models)).pack(anchor="w",pady=(6,0))
        ttk.Checkbutton(settings,text="翻訳後に自動QA",variable=self.autoqa_var,command=self._save_llm_preferences).pack(anchor="w",pady=(7,0))
        ttk.Label(settings,text="QAでは未翻訳原文、キー欠落、ゲーム変数/タグ、誤字脱字、用語集の固定訳を確認します。",foreground="#555",wraplength=430,justify="left").pack(anchor="w",pady=(5,0))

        qbox=ttk.LabelFrame(right,text="通常翻訳キュー",padding=8); qbox.pack(fill="both",expand=True)
        qbar=ttk.Frame(qbox); qbar.pack(fill="x",pady=(0,5))
        ttk.Button(qbar,text="選択削除",command=self.remove_queue).pack(side="left")
        ttk.Button(qbar,text="全消去",command=self.clear_queue).pack(side="left",padx=(5,0))
        ttk.Button(qbar,text="出力先変更",command=self.change_output).pack(side="left",padx=(10,0))
        ttk.Button(qbar,text="キャッシュを見る",command=self.view_selected_cache).pack(side="left",padx=(5,0))
        ttk.Button(qbar,text="キャッシュを追加",command=self.import_cache_to_selected).pack(side="left",padx=(5,0))

        qbar2=ttk.Frame(qbox); qbar2.pack(fill="x",pady=(0,5))
        ttk.Button(qbar2,text="選択項目を一括上書き",command=self.overwrite_selected_translation_to_mod).pack(side="left")
        ttk.Button(qbar2,text="選択項目の翻訳語QAを実行",command=self.run_selected_translation_qa).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="用語集を自動作成",command=lambda:self.start_auto_glossary_generation("normal")).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="QA / 比較編集へ",command=lambda:self._send_pair_to_qa_or_diff("normal","review")).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="差分調査へ",command=lambda:self._send_pair_to_qa_or_diff("normal","diff")).pack(side="left",padx=(6,0))
        ttk.Button(qbar,text="中国語基準キューへ渡す",command=lambda:self.transfer_selected_queue_to_opposite("normal",False)).pack(side="left",padx=(10,0))
        ttk.Button(qbar2,text="中国語不足分だけをキューへ追加",command=lambda:self.transfer_selected_queue_to_opposite("normal",True)).pack(side="left",padx=(6,0))
        ttk.Label(qbox,text="上書き: 複数選択に対応。最初に上書き方針を1回だけ選び、完了済み項目をまとめて処理します。成功した項目は「上書き済み」と表示します。",foreground="#8a5a00",wraplength=900,justify="left").pack(fill="x",anchor="w",pady=(0,5))

        self.drop_hint=ttk.Label(qbox,textvariable=self.dnd_status_var,foreground="#666")
        self.drop_hint.pack(fill="x",pady=(0,5))
        cols=("mod","input","output","status")
        queue_table=ttk.Frame(qbox)
        queue_table.pack(fill="both",expand=True)
        self.queue_tree=ttk.Treeview(queue_table,columns=cols,show="headings",height=10,selectmode="extended")
        for c,txt,w in (("mod","Mod / 項目",240),("input","原文localization",430),("output","出力",390),("status","状態",230)):
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

        if DND_AVAILABLE:
            try:
                self._register_dnd_widgets([t,src,self.normal_input_entry,qbox,self.queue_tree],self.on_drop_paths)
                self.dnd_status_var.set("ドラッグ＆ドロップ有効 — YAML / localizationフォルダ")
            except Exception as e:
                self.dnd_status_var.set(f"ドラッグ＆ドロップ初期化失敗: {e}")
                self._record_error("DnD初期化",e)
        else:
            self.dnd_status_var.set("ドラッグ＆ドロップ無効 — 『追加』ボタンは利用できます")

        actions=ttk.Frame(right); actions.pack(fill="x",pady=(7,0))
        self.start_btn=ttk.Button(actions,text="翻訳開始",command=self.start_queue); self.start_btn.pack(side="left")
        self.diff_start_btn=ttk.Button(actions,text="差分翻訳",command=self.start_differential_queue); self.diff_start_btn.pack(side="left",padx=(6,0))
        self.pause_btn=ttk.Button(actions,text="一時停止",command=self.toggle_pause,state="disabled"); self.pause_btn.pack(side="left",padx=(6,0))
        self.stop_btn=ttk.Button(actions,text="セーブして中断",command=self.save_and_stop,state="disabled"); self.stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(actions,text="出力を開く",command=self.open_selected_output).pack(side="left",padx=(6,0))
        ttk.Label(actions,textvariable=self.progress_text).pack(side="right")
        self.progress=ttk.Progressbar(right,mode="determinate",maximum=100); self.progress.pack(fill="x",pady=(6,7))

        logbox=ttk.LabelFrame(right,text="通常翻訳ログ",padding=6); logbox.pack(fill="both",expand=True)
        lbar=ttk.Frame(logbox); lbar.pack(fill="x",pady=(0,4))
        ttk.Button(lbar,text="エラーログを開く",command=lambda:self._open_path(LOG_ROOT)).pack(side="left")
        ttk.Button(lbar,text="診断ログを収集",command=self.collect_error_logs).pack(side="left",padx=(5,0))
        self.log=tk.Text(logbox,height=6,wrap="word",state="disabled")
        lsy=ttk.Scrollbar(logbox,command=self.log.yview); self.log.configure(yscrollcommand=lsy.set)
        self.log.pack(side="left",fill="both",expand=True); lsy.pack(side="right",fill="y")

    def _build_chinese_tab(self):
        t = self.tab_chinese

        # 中国語基準翻訳は基準デザインとして維持し、入力追加だけ単純化する。
        main=ttk.Panedwindow(t,orient="horizontal"); main.pack(fill="both",expand=True)
        left=ttk.Frame(main,padding=(0,0,6,0)); right=ttk.Frame(main,padding=(6,0,0,0))
        main.add(left,weight=2); main.add(right,weight=3)

        intro=ttk.LabelFrame(left,text="中国語の漢字を基準に日本語化",padding=9); intro.pack(fill="x")
        ttk.Label(intro,text=("簡体字中国語のlocalizationを直接読み込み、中国語原文の漢字語彙・制度名・官職名・歴史用語を第一基準として日本語化します。\n"
                              "英語ファイルは不要です。簡体字は日本語で一般的な字体へ整え、文章は自然な日本語にします。"),
                  wraplength=430,foreground="#333",justify="left").pack(fill="x")

        src=ttk.LabelFrame(left,text="入力 / 出力",padding=9); src.pack(fill="x",pady=(5,0)); src.columnconfigure(0,weight=1)
        ttk.Label(src,text="中国語YAML / フォルダ").grid(row=0,column=0,sticky="w")
        self.chinese_input_entry=ttk.Entry(src,textvariable=self.chinese_input_var,state="readonly"); self.chinese_input_entry.grid(row=1,column=0,sticky="ew",pady=(3,0))
        pickbar=ttk.Frame(src); pickbar.grid(row=2,column=0,sticky="ew",pady=(5,0))
        chinese_add_menu=tk.Menu(pickbar,tearoff=False)
        chinese_add_menu.add_command(label="中国語YAMLファイルを追加",command=self.pick_chinese_file)
        chinese_add_menu.add_command(label="中国語localizationフォルダを追加",command=self.pick_chinese_folder)
        self.chinese_add_menu_button=ttk.Menubutton(pickbar,text="追加",menu=chinese_add_menu)
        self.chinese_add_menu_button.pack(side="left")
        ttk.Label(pickbar,text="選択するとそのまま中国語基準翻訳キューへ追加します",foreground="#666").pack(side="left",padx=(8,0))
        ttk.Label(src,textvariable=self.chinese_status_var,foreground="#555",wraplength=430,justify="left").grid(row=3,column=0,sticky="w",pady=(4,0))
        ttk.Separator(src,orient="horizontal").grid(row=4,column=0,sticky="ew",pady=5)
        ttk.Label(src,text="出力先ルート").grid(row=5,column=0,sticky="w")
        ttk.Entry(src,textvariable=self.chinese_output_var).grid(row=6,column=0,sticky="ew",pady=(3,0))
        outbar=ttk.Frame(src); outbar.grid(row=7,column=0,sticky="ew",pady=(5,0))
        ttk.Button(outbar,text="選択",command=self.pick_chinese_output).pack(side="left")
        ttk.Button(outbar,text="開く",command=lambda:self._open_path(Path(self.chinese_output_var.get()))).pack(side="left",padx=(5,0))

        settings=ttk.LabelFrame(left,text="モデル / 接続（共通設定）",padding=9); settings.pack(fill="x",pady=(5,0))
        ttk.Label(settings,text="中国語基準翻訳でも、プロバイダ / URL / モデル / APIキー / バッチ / 並列 / プリセット / 用語集は［モデル / 接続］タブの共通設定を使用します。",wraplength=430,justify="left").pack(anchor="w")
        ttk.Button(settings,text="モデル / 接続を開く",command=lambda:self.notebook.select(self.tab_models)).pack(anchor="w",pady=(6,0))
        ttk.Label(settings,text="中国語の漢字語彙を優先し、不要な英語風カタカナ化を避けます。",foreground="#7a4b00",wraplength=430).pack(anchor="w",pady=(6,0))
        ttk.Checkbutton(settings,text="翻訳後に中国語翻訳語自動QA",variable=self.chinese_autoqa_var,command=self._save_llm_preferences).pack(anchor="w",pady=(7,0))
        ttk.Label(settings,text="QAでは未翻訳の中国語原文、キー欠落、ゲーム変数/タグ、誤字脱字、用語集の固定訳を確認します。",foreground="#555",wraplength=430,justify="left").pack(anchor="w",pady=(5,0))

        qbox=ttk.LabelFrame(right,text="中国語基準翻訳キュー",padding=8); qbox.pack(fill="both",expand=True)
        qbar=ttk.Frame(qbox); qbar.pack(fill="x",pady=(0,5))
        ttk.Button(qbar,text="選択削除",command=self.remove_chinese_queue_selected).pack(side="left")
        ttk.Button(qbar,text="全消去",command=self.clear_chinese_queue).pack(side="left",padx=(5,0))
        ttk.Button(qbar,text="出力先変更",command=self.change_chinese_output_for_selected).pack(side="left",padx=(10,0))
        ttk.Button(qbar,text="キャッシュを見る",command=self.view_selected_chinese_cache).pack(side="left",padx=(5,0))
        ttk.Button(qbar,text="キャッシュを追加",command=self.import_cache_to_selected_chinese).pack(side="left",padx=(5,0))

        qbar2=ttk.Frame(qbox); qbar2.pack(fill="x",pady=(0,5))
        ttk.Button(qbar2,text="選択項目を一括上書き",command=self.overwrite_selected_chinese_translation).pack(side="left")
        ttk.Button(qbar2,text="選択項目の翻訳語QAを実行",command=self.run_selected_chinese_qa).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="用語集を自動作成",command=lambda:self.start_auto_glossary_generation("chinese")).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="QA / 比較編集へ",command=lambda:self._send_pair_to_qa_or_diff("chinese","review")).pack(side="left",padx=(6,0))
        ttk.Button(qbar2,text="差分調査へ",command=lambda:self._send_pair_to_qa_or_diff("chinese","diff")).pack(side="left",padx=(6,0))
        ttk.Button(qbar,text="通常翻訳キューへ渡す",command=lambda:self.transfer_selected_queue_to_opposite("chinese",False)).pack(side="left",padx=(10,0))
        ttk.Button(qbar2,text="英語不足分だけをキューへ追加",command=lambda:self.transfer_selected_queue_to_opposite("chinese",True)).pack(side="left",padx=(6,0))
        ttk.Label(qbox,text="上書き: 複数選択に対応。最初に上書き方針を1回だけ選び、完了済み項目をまとめて処理します。成功した項目は「上書き済み」と表示します。",foreground="#8a5a00",wraplength=900,justify="left").pack(fill="x",anchor="w",pady=(0,5))
        cols=("mod","input","output","status")
        chinese_queue_table=ttk.Frame(qbox)
        chinese_queue_table.pack(fill="both",expand=True)
        self.chinese_queue_tree=ttk.Treeview(chinese_queue_table,columns=cols,show="headings",height=10,selectmode="extended")
        for c,txt,w in (("mod","Mod / 項目",240),("input","中国語localization",430),("output","出力",390),("status","状態",230)):
            self.chinese_queue_tree.heading(c,text=txt)
            self.chinese_queue_tree.column(c,width=w,minwidth=120,stretch=False,anchor="center" if c=="status" else "w")
        self._enable_ctrl_multiselect(self.chinese_queue_tree)
        self._enable_tree_sort(self.chinese_queue_tree)
        sy=ttk.Scrollbar(chinese_queue_table,orient="vertical",command=self.chinese_queue_tree.yview)
        sx=ttk.Scrollbar(chinese_queue_table,orient="horizontal",command=self.chinese_queue_tree.xview)
        self.chinese_queue_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        sx.pack(side="bottom",fill="x")
        sy.pack(side="right",fill="y")
        self.chinese_queue_tree.pack(side="left",fill="both",expand=True)

        actions=ttk.Frame(right); actions.pack(fill="x",pady=(7,0))
        self.chinese_start_btn=ttk.Button(actions,text="翻訳開始",command=self.start_chinese_basis_translation); self.chinese_start_btn.pack(side="left")
        self.chinese_diff_start_btn=ttk.Button(actions,text="差分翻訳",command=self.start_chinese_differential_translation); self.chinese_diff_start_btn.pack(side="left",padx=(6,0))
        self.chinese_pause_btn=ttk.Button(actions,text="一時停止",command=self.toggle_chinese_pause,state="disabled"); self.chinese_pause_btn.pack(side="left",padx=(6,0))
        self.chinese_stop_btn=ttk.Button(actions,text="セーブして中断",command=self.save_and_stop_chinese_translation,state="disabled"); self.chinese_stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(actions,text="出力を開く",command=self.open_selected_chinese_output).pack(side="left",padx=(6,0))
        ttk.Label(actions,textvariable=self.chinese_progress_var).pack(side="right")
        self.chinese_progress=ttk.Progressbar(right,mode="determinate",maximum=100); self.chinese_progress.pack(fill="x",pady=(6,7))

        logbox=ttk.LabelFrame(right,text="中国語基準翻訳ログ",padding=6); logbox.pack(fill="both",expand=True)
        lbar=ttk.Frame(logbox); lbar.pack(fill="x",pady=(0,4))
        ttk.Button(lbar,text="エラーログを開く",command=lambda:self._open_path(LOG_ROOT)).pack(side="left")
        ttk.Button(lbar,text="診断ログを収集",command=self.collect_error_logs).pack(side="left",padx=(5,0))
        self.chinese_log=tk.Text(logbox,height=6,wrap="word",state="disabled")
        y=ttk.Scrollbar(logbox,command=self.chinese_log.yview); self.chinese_log.configure(yscrollcommand=y.set)
        self.chinese_log.pack(side="left",fill="both",expand=True); y.pack(side="right",fill="y")
        self._register_dnd_widgets([t,intro,src,self.chinese_input_entry,qbox,self.chinese_queue_tree],self.on_chinese_drop_paths)

    def _append_chinese_log(self, text):
        if not hasattr(self, "chinese_log"):
            return
        self.chinese_log.config(state="normal")
        self.chinese_log.insert("end",str(text)+"\n")
        self.chinese_log.see("end")
        self.chinese_log.config(state="disabled")

    def _validate_chinese_input(self, path: Path):
        if not path.exists():
            return False,"選択したパスが存在しません。"
        if path.is_file():
            try: lang,_,_=core.parse_localization_file(path)
            except Exception as exc: return False,f"YAMLを読み込めません: {exc}"
            if lang!="simp_chinese": return False,f"このファイルは l_simp_chinese ではありません（検出: {lang}）。"
            return True,f"簡体字中国語YAMLを確認しました: {path.name}"
        count=0
        for f in core.gather_yml_files(path):
            try:
                lang,_,_=core.parse_localization_file(f)
                if lang=="simp_chinese": count+=1
            except Exception: pass
        if not count: return False,"フォルダ内に l_simp_chinese のYAMLが見つかりませんでした。"
        return True,f"簡体字中国語YAMLを {count} ファイル検出しました。"

    def _refresh_chinese_queue_tree(self):
        if not hasattr(self,"chinese_queue_tree"): return
        for x in self.chinese_queue_tree.get_children(): self.chinese_queue_tree.delete(x)
        for i,item in enumerate(self.chinese_queue_items):
            self.chinese_queue_tree.insert("","end",iid=f"zh_{i}",values=(
                item.get("mod_name",Path(item.get("input","")).name),
                self._queue_display_path(item.get("input","")),
                self._queue_display_path(item.get("output","")),
                item.get("status","待機")
            ))

    def _append_chinese_queue(self, path, mod_name=""):
        path=Path(path); ok,msg=self._validate_chinese_input(path)
        if not ok: return None,msg
        key=str(path.resolve())
        for item in self.chinese_queue_items:
            try:
                if str(Path(item.get("input","")).resolve())==key: return item,"すでに中国語基準キューに追加されています。"
            except Exception: pass
        safe=re.sub(r'[^0-9A-Za-z_\-\u3040-\u30ff\u4e00-\u9fff]+','_',mod_name or path.name).strip("_") or "ChineseBasis"
        item={"input":str(path),"mod_name":mod_name or path.name,"status":"待機","output":str(Path(self.chinese_output_var.get().strip() or str(OUTPUT_ROOT/"中国語基準翻訳"))/safe)}
        if path.is_dir() and path.name.lower()=="localization":
            item["mod_localization"]=str(path); item["mod_root"]=str(path.parent)
        elif path.is_dir() and (path/"localization").is_dir():
            item["mod_root"]=str(path); item["mod_localization"]=str(path/"localization")
        self.chinese_queue_items.append(item); self._refresh_chinese_queue_tree()
        return item,msg

    def remove_chinese_queue_selected(self):
        if not hasattr(self,"chinese_queue_tree"): return
        idx=[]
        for iid in self.chinese_queue_tree.selection():
            try: idx.append(int(iid.split("_",1)[1]))
            except Exception: pass
        for i in sorted(set(idx),reverse=True):
            if 0<=i<len(self.chinese_queue_items): self.chinese_queue_items.pop(i)
        self._refresh_chinese_queue_tree()

    def clear_chinese_queue(self):
        self.chinese_queue_items.clear(); self._refresh_chinese_queue_tree()

    def _selected_chinese_queue_item(self):
        if not hasattr(self,"chinese_queue_tree"):
            return None
        sel=self.chinese_queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME,"中国語基準翻訳キューから項目を1つ選択してください。")
            return None
        try:
            idx=int(sel[0].split("_",1)[1])
        except Exception:
            return None
        return self.chinese_queue_items[idx] if 0 <= idx < len(self.chinese_queue_items) else None

    def change_chinese_output_for_selected(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=filedialog.askdirectory(title="選択した中国語基準翻訳の出力先を変更")
        if not raw: return
        item["output"]=str(Path(raw))
        self._append_chinese_log(f"出力先変更: {item.get('mod_name','項目')} → {raw}")

    def open_selected_chinese_output(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=item.get("output","")
        if not raw:
            messagebox.showinfo(APP_NAME,"この項目の出力先が設定されていません。")
            return
        self._open_path(Path(raw))

    def view_selected_chinese_cache(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=item.get("cache","")
        if not raw:
            messagebox.showinfo(APP_NAME,"この項目にはまだキャッシュがありません。翻訳を開始すると作成されます。")
            return
        cache=Path(raw)
        self._open_path(cache.parent if cache.parent.exists() else cache)

    def import_cache_to_selected_chinese(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        raw=filedialog.askopenfilename(title="中国語基準翻訳キャッシュを追加",filetypes=[("JSON","*.json"),("All files","*")])
        if not raw: return
        src=Path(raw)
        try:
            core.load_json(src,{})
            cache=Path(item.get("cache", "")) if item.get("cache") else self._new_cache_path(Path(item["input"]))
            cache.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(src,cache)
            item["cache"]=str(cache)
            self._append_chinese_log(f"キャッシュ追加: {item.get('mod_name','項目')} ← {src.name}")
        except Exception as exc:
            record_error("中国語基準キャッシュ追加",exc,str(src))
            messagebox.showerror(APP_NAME,f"キャッシュを追加できませんでした。\n{exc}")

    def overwrite_selected_chinese_translation(self):
        """Overwrite all selected completed Chinese-basis jobs in one batch."""
        entries=self._selected_chinese_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,"中国語基準翻訳キューから上書きする項目を選択してください。")
            return
        self._bulk_overwrite_queue_entries(entries, queue_kind="chinese")

    def run_selected_chinese_qa(self):
        item=self._selected_chinese_queue_item()
        if not item: return
        inp=Path(item.get("input", "")); out=Path(item.get("output", ""))
        if not inp.exists():
            messagebox.showerror(APP_NAME,"中国語原文が見つかりません。"); return
        if not out.exists():
            messagebox.showinfo(APP_NAME,"まだ翻訳出力がありません。先に中国語基準翻訳を実行してください。"); return
        try:
            result=core.qa_chinese_basis_translation(inp,out,self.glossary_path_var.get().strip() or None)
            report_path=out / "chinese_basis_qa_report.json"
            core.save_json(report_path,{"source_language":"simp_chinese",**result})
            self._append_chinese_log(f"翻訳語QA: error {result['errors']} / warning {result['warnings']} / syntax自動修正 {result['syntax_repaired']} / 未修正 {result['syntax_unresolved']} / 確認 {result['checked_files']}ファイル")
            if result.get("missing_outputs"):
                self._append_chinese_log(f"翻訳語QA: 対応する日本語出力がないファイル {result['missing_outputs']}件")
            messagebox.showinfo(APP_NAME,f"中国語翻訳語QAが完了しました。\n\nエラー: {result['errors']}\n警告: {result['warnings']}\nsyntax検出: {result['syntax_detected']}\n自動修正: {result['syntax_repaired']}\n未修正: {result['syntax_unresolved']}\n確認ファイル: {result['checked_files']}\n\nレポート: {report_path}")
        except Exception as exc:
            record_error("中国語翻訳語QA",exc)
            messagebox.showerror(APP_NAME,str(exc))

    def pick_chinese_file(self):
        raw=filedialog.askopenfilename(title="簡体字中国語YAMLを追加",filetypes=[("Paradox YAML","*.yml *.yaml"),("All files","*")])
        if not raw:return
        path=Path(raw)
        self.chinese_input_var.set(str(path))
        item,msg=self._append_chinese_queue(path)
        self.chinese_status_var.set(msg)
        if not item: messagebox.showwarning(APP_NAME,msg)

    def pick_chinese_folder(self):
        raw=filedialog.askdirectory(title="簡体字中国語localizationを含むフォルダを追加")
        if not raw:return
        path=Path(raw)
        self.chinese_input_var.set(str(path))
        item,msg=self._append_chinese_queue(path)
        self.chinese_status_var.set(msg)
        if not item: messagebox.showwarning(APP_NAME,msg)

    def pick_chinese_output(self):
        raw=filedialog.askdirectory(title="中国語基準翻訳の出力先")
        if raw:self.chinese_output_var.set(raw)

    def on_chinese_drop_paths(self,event):
        paths=self._raw_drop_paths(event)
        added=0
        for path in paths:
            if path.is_file() and path.suffix.lower() not in {".yml",".yaml"}: continue
            item,msg=self._append_chinese_queue(path)
            if item: added+=1
        if paths:
            self.chinese_input_var.set(str(paths[0])); ok,msg=self._validate_chinese_input(paths[0]); self.chinese_status_var.set(msg)
        if not added and paths: messagebox.showinfo(APP_NAME,"ドロップした項目に l_simp_chinese のYAMLが見つかりませんでした。")
        return event.action if hasattr(event,"action") else None

    def start_chinese_differential_translation(self):
        if self.chinese_worker and self.chinese_worker.is_alive():
            return
        targets = [x for x in self.chinese_queue_items if not self._queue_item_is_completed(x)]
        if not targets:
            messagebox.showinfo(APP_NAME, "差分翻訳できる待機中の中国語基準項目がありません。")
            return
        unavailable = []
        for item in targets:
            self._ensure_item_cache(item)
            diff = self._prepare_differential_cache(item, silent=True, mode="chinese")
            if diff is None:
                unavailable.append(item.get("mod_name") or Path(item.get("input", "")).name)
            else:
                item["diff_mode"] = True
                counts = diff.get("counts", {})
                changed_total = sum(int(counts.get(k, 0) or 0) for k in ("added", "changed", "removed", "added_files", "removed_files"))
                if changed_total == 0:
                    item["status"] = "完了（差分更新）"
        self._refresh_chinese_queue_tree()
        if unavailable:
            for item in targets:
                if item.get("diff_mode"):
                    self._reset_item_for_full_translation(item)
            self._refresh_queue_tree()
            messagebox.showinfo(APP_NAME, "前回の差分スナップショットがないため差分翻訳できない項目があります。\n\n" + "\n".join(unavailable[:10]))
            return
        if any(not self._queue_item_is_completed(x) for x in targets):
            self.start_chinese_basis_translation(_diff_requested=True)
        else:
            messagebox.showinfo(APP_NAME, "前回翻訳時から翻訳対象の差分はありません。")

    def start_chinese_basis_translation(self, _diff_requested=False):
        if self.chinese_worker and self.chinese_worker.is_alive(): return
        if not _diff_requested:
            for item in self.chinese_queue_items:
                if not self._queue_item_is_completed(item):
                    self._reset_item_for_full_translation(item)
            self._refresh_chinese_queue_tree()
        if not self.chinese_queue_items:
            raw=self.chinese_input_var.get().strip()
            if raw: self._append_chinese_queue(Path(raw))
        if not self.chinese_queue_items:
            messagebox.showinfo(APP_NAME,"中国語基準翻訳キューが空です。中国語YAML/フォルダを追加してください。"); return
        out_root=Path(self.chinese_output_var.get().strip() or str(OUTPUT_ROOT/"中国語基準翻訳")); out_root.mkdir(parents=True,exist_ok=True)
        self.chinese_log.config(state="normal"); self.chinese_log.delete("1.0","end"); self.chinese_log.config(state="disabled")
        self.chinese_progress["value"]=0; self.chinese_progress_var.set("キュー翻訳準備中…"); self.llm_operation="中国語基準翻訳"
        self.chinese_controller=core.TranslationController(progress_callback=lambda x:self.events.put(("chinese_progress",x)))
        self.chinese_start_btn.config(state="disabled"); self.chinese_diff_start_btn.config(state="disabled"); self.chinese_pause_btn.config(state="normal", text="一時停止"); self.chinese_stop_btn.config(state="normal")
        settings={"provider":self.provider_var.get(),"url":self.url_var.get().strip(),"model":self.model_var.get().strip(),"api_key":self.api_key_var.get().strip(),"preset":self.preset_var.get(),"batch":max(1,self.batch_var.get()),"workers":max(1,self.workers_var.get()),"glossary":self.glossary_path_var.get().strip() or None,"autoqa":self.chinese_autoqa_var.get()}
        snapshot=[dict(x) for x in self.chinese_queue_items]
        def worker():
            try:
                total=len(snapshot); completed=0; qa_errors=0; qa_warnings=0
                for i,item in enumerate(snapshot):
                    if self.chinese_controller.stop_event.is_set(): break
                    if self._queue_item_is_completed(item):
                        completed += 1
                        continue
                    self.events.put(("chinese_queue_status",(i,"翻訳中")))
                    self.events.put(("chinese_queue_current",(i+1,total,item.get("mod_name",""))))
                    inp=Path(item["input"]); safe=re.sub(r'[^0-9A-Za-z_\-\u3040-\u30ff\u4e00-\u9fff]+','_',item.get("mod_name") or inp.name).strip("_") or f"item_{i+1}"
                    out=Path(item.get("output") or (out_root/safe)); out.mkdir(parents=True,exist_ok=True)
                    cache=Path(item.get("cache", "")) if item.get("cache") else self._new_cache_path(inp)
                    item["output"]=str(out); item["cache"]=str(cache)
                    if 0 <= i < len(self.chinese_queue_items):
                        self.chinese_queue_items[i]["output"]=str(out); self.chinese_queue_items[i]["cache"]=str(cache)
                    result=core.run_chinese_basis_translation(inp,out,model=settings["model"],url=settings["url"],workers=settings["workers"],batch_size=settings["batch"],cache_path=cache,controller=self.chinese_controller,glossary_path=settings["glossary"],preset=settings["preset"],auto_qa=settings["autoqa"],provider=settings["provider"],api_key=settings["api_key"])
                    qa_errors += int(result.get("qa_errors",0) or 0)
                    qa_warnings += int(result.get("qa_warnings",0) or 0)
                    self._register_cache_job(item, mode="chinese")
                    if result.get("interrupted"):
                        self.events.put(("chinese_queue_status",(i,"中断"))); break
                    completed += 1
                    if self._item_has_remaining_translation_gap(item):
                        final_status = "完了（一部差分欠落あり）"
                    else:
                        final_status = "完了（差分更新）" if item.get("diff_mode") else "完了"
                    self.events.put(("chinese_queue_status",(i,final_status)))
                self.events.put(("chinese_done",{"interrupted":self.chinese_controller.stop_event.is_set(),"processed_files":completed,"jobs":0,"output":str(out_root),"queue_total":total,"qa_errors":qa_errors,"qa_warnings":qa_warnings}))
            except Exception as exc: self.events.put(("chinese_error",str(exc)))
        self.chinese_worker=threading.Thread(target=worker,daemon=True); self.chinese_worker.start()

    def toggle_chinese_pause(self):
        if not self.chinese_controller:
            return
        if self.chinese_controller.pause_event.is_set():
            self.chinese_controller.resume()
            self.chinese_pause_btn.config(text="一時停止")
            self.chinese_progress_var.set("再開しました")
        else:
            self.chinese_controller.pause()
            self.chinese_pause_btn.config(text="再開")
            self.chinese_progress_var.set("一時停止中 — 現在のLLM応答完了後に停止します")

    def save_and_stop_chinese_translation(self):
        if self.chinese_controller:
            self.chinese_controller.request_stop(save=True)
            self.chinese_progress_var.set("セーブして中断中 — 現在のLLM応答完了を待っています")
            self.chinese_stop_btn.config(state="disabled")
            self.chinese_pause_btn.config(state="disabled", text="一時停止")

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
            if p.name.lower() == "localization" and p.parent.name:
                return str(Path(p.parent.name) / p.name)
            if p.is_dir():
                return p.name or str(p)
            return p.name
        except Exception:
            return str(value)

    def _collect_qa_diff_pairs(self, source_root, target_root, source_langs=("english", "simp_chinese")):
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
            if lang == "japanese":
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
            if lang not in source_langs:
                continue

            chosen = None
            # First prefer the deterministic path produced by the translator.
            if target_root.is_dir():
                try:
                    rel = sf.parent.relative_to(source_base) if source_root.is_dir() else Path(".")
                    expected = target_root / core.remap_rel_dir(rel, "japanese") / core.rename_for_target(sf, "japanese", lang)
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
                            if core._logical_localization_id(tf, target_root, "japanese") == src_id:
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
            pairs.append({"source": sf, "target": chosen, "lang": lang})
        return pairs

    def _choose_qa_diff_pair(self, pairs, title):
        if not pairs:
            return None
        if len(pairs) == 1:
            return pairs[0]

        result = {"value": None}
        win = tk.Toplevel(self)
        win.title(title)
        win.geometry("980x520")
        win.transient(self)
        win.grab_set()
        ttk.Label(win, text="使用する原文と日本語訳の組み合わせを選択してください。", padding=(10,10,10,4)).pack(anchor="w")
        frame = ttk.Frame(win, padding=(10,0,10,8)); frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, columns=("lang","src","dst"), show="headings", selectmode="browse")
        for c, label, width in (("lang","原文言語",120),("src","原文YAML",390),("dst","日本語YAML",390)):
            tree.heading(c, text=label); tree.column(c, width=width, anchor="w")
        sy = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        sx = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        tree.pack(side="top", fill="both", expand=True)
        sx.pack(side="bottom", fill="x")
        sy.pack(side="right", fill="y")
        labels = {"english":"英語", "simp_chinese":"簡体字中国語"}
        for i, pair in enumerate(pairs):
            tree.insert("", "end", iid=str(i), values=(labels.get(pair["lang"], pair["lang"]), self._localization_display_path(pair["source"]), self._localization_display_path(pair["target"])))
        tree.selection_set("0"); tree.focus("0")

        buttons = ttk.Frame(win, padding=(10,0,10,10)); buttons.pack(fill="x")
        def accept(_=None):
            sel = tree.selection()
            if not sel:
                return
            result["value"] = pairs[int(sel[0])]
            win.destroy()
        ttk.Button(buttons, text="選択", command=accept).pack(side="right")
        ttk.Button(buttons, text="キャンセル", command=win.destroy).pack(side="right", padx=(0,6))
        tree.bind("<Double-1>", accept)
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
            label = "通常翻訳"
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
                messagebox.showinfo(APP_NAME, "翻訳状況一覧からModを1件選択してください。")
                return
            if len(results) != 1:
                messagebox.showinfo(APP_NAME, "QA / 差分調査へ送る場合は、翻訳状況一覧からModを1件だけ選択してください。")
                return
            r = results[0]
            source_root = Path(r.get("localization") or (Path(r.get("path", "")) / "localization"))
            external = r.get("external_translation_localization", "")
            target_root = Path(external) if external and Path(external).exists() else source_root
            source_langs = ("english", "simp_chinese")
            label = r.get("mod", "翻訳状況")
        else:
            return

        pairs = self._collect_qa_diff_pairs(source_root, target_root, source_langs)
        if not pairs:
            messagebox.showinfo(APP_NAME, f"{label}から、原文（英語/簡体字中国語）と対応する日本語YAMLの組み合わせを見つけられませんでした。\n翻訳完了後、または日本語化Modが存在する状態で実行してください。")
            return
        pair = self._choose_qa_diff_pair(pairs, f"{label}からQA / 差分用ファイルを選択")
        if not pair:
            return
        if destination == "review":
            self.review_src_var.set(str(pair["source"]))
            self.review_dst_var.set(str(pair["target"]))
            self.notebook.select(self.tab_review)
            self.load_review()
        else:
            self.diff_src_var.set(str(pair["source"]))
            self.diff_dst_var.set(str(pair["target"]))
            self.notebook.select(self.tab_diff)
            self.load_diff_inspector()

    def _build_review_tab(self):
        t=self.tab_review
        pf=ttk.LabelFrame(t,text="原文 / 訳文",padding=8); pf.pack(fill="x")
        pf.columnconfigure(1,weight=1)
        ttk.Label(pf,text="原文").grid(row=0,column=0,sticky="w")
        self.review_src_entry=ttk.Entry(pf,textvariable=self.review_src_display_var,state="readonly")
        self.review_src_entry.grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Button(pf,text="選択",command=lambda:self.pick_review_file(self.review_src_var)).grid(row=0,column=2)
        ttk.Label(pf,text="訳文").grid(row=1,column=0,sticky="w",pady=(5,0))
        self.review_dst_entry=ttk.Entry(pf,textvariable=self.review_dst_display_var,state="readonly")
        self.review_dst_entry.grid(row=1,column=1,sticky="ew",padx=6,pady=(5,0))
        ttk.Button(pf,text="選択",command=lambda:self.pick_review_file(self.review_dst_var)).grid(row=1,column=2,pady=(5,0))
        ttk.Button(pf,text="比較を読み込む",command=self.load_review).grid(row=0,column=3,rowspan=2,padx=(8,0))
        self.review_drop_hint=ttk.Label(pf,text="英語または簡体字中国語の原文YAMLと日本語YAMLをここへドラッグ＆ドロップできます" if DND_AVAILABLE else "ドラッグ＆ドロップはこのビルドでは利用できません",foreground="#555")
        self.review_drop_hint.grid(row=2,column=0,columnspan=4,sticky="ew",pady=(7,0))
        qa=ttk.Frame(t); qa.pack(fill="x",pady=(8,5))
        ttk.Button(qa,text="QA再実行",command=self.run_review_qa).pack(side="left")
        ttk.Button(qa,text="警告だけ表示",command=lambda:self.populate_review(True)).pack(side="left",padx=(6,0))
        ttk.Button(qa,text="全キー表示",command=lambda:self.populate_review(False)).pack(side="left",padx=(6,0))
        ttk.Button(qa,text="用語不一致を一括統一",command=self.bulk_unify_review_terms).pack(side="left",padx=(8,0))
        ttk.Button(qa,text="用語集を自動作成",command=lambda:self.start_auto_glossary_generation("review")).pack(side="left",padx=(8,0))
        ttk.Button(qa,text="現在の翻訳設定を適用",command=self.apply_translation_settings_everywhere).pack(side="left",padx=(10,0))
        ttk.Label(qa,text="AI校正は現在の翻訳モデル設定を使用 / 一覧は重要度→問題種別→キーで整理",foreground="#666").pack(side="left",padx=(12,0))
        ttk.Label(qa,textvariable=self.qa_summary_var).pack(side="right")

        paned=ttk.Panedwindow(t,orient="horizontal"); paned.pack(fill="both",expand=True)
        left=ttk.Frame(paned); right=ttk.Frame(paned); paned.add(left,weight=2); paned.add(right,weight=3)
        self.review_tree=ttk.Treeview(left,columns=("type","key"),show="tree headings")
        self.review_tree.heading("#0",text="重要度 / 分類"); self.review_tree.column("#0",width=150)
        self.review_tree.heading("type",text="種別"); self.review_tree.column("type",width=130)
        self.review_tree.heading("key",text="キー"); self.review_tree.column("key",width=300)
        self.review_tree.bind("<<TreeviewSelect>>",self.on_review_select)
        self._enable_tree_sort(self.review_tree, recursive=True)
        rys=ttk.Scrollbar(left,command=self.review_tree.yview); self.review_tree.configure(yscrollcommand=rys.set)
        self.review_tree.pack(side="left",fill="both",expand=True); rys.pack(side="right",fill="y")

        ttk.Label(right,text="原文（英語 / 簡体字中国語）").pack(anchor="w")
        self.src_text=tk.Text(right,height=7,wrap="word"); self.src_text.pack(fill="x",pady=(2,8))
        ttk.Label(right,text="訳文（編集可）").pack(anchor="w")
        self.dst_text=tk.Text(right,height=10,wrap="word"); self.dst_text.pack(fill="both",expand=True,pady=(2,6))
        self.issue_text=tk.StringVar(value="")
        ttk.Label(right,textvariable=self.issue_text,wraplength=550).pack(fill="x",pady=(0,6))
        eb=ttk.Frame(right); eb.pack(fill="x")
        ttk.Button(eb,text="この訳を日本語ファイルへ保存",command=self.save_review_value).pack(side="left")
        ttk.Button(eb,text="この訳を用語集へ保存",command=self.save_review_glossary_term).pack(side="left",padx=(6,0))
        ttk.Button(eb,text="AIで誤字脱字校正",command=self.ai_proofread_selected).pack(side="left",padx=(6,0))
        ttk.Button(eb,text="原文に戻す",command=self.restore_source_to_target).pack(side="left",padx=(6,0))
        self._register_dnd_widgets([pf,self.review_src_entry,self.review_dst_entry,self.review_drop_hint,self.review_tree,self.src_text,self.dst_text],self.on_review_drop_paths)

    def _build_diff_tab(self):
        t = self.tab_diff
        pf = ttk.LabelFrame(t, text="原文（英語 / 簡体字中国語） / 日本語ファイル", padding=8); pf.pack(fill="x")
        pf.columnconfigure(1, weight=1)
        ttk.Label(pf, text="原文（英語 / 中国語）").grid(row=0, column=0, sticky="w")
        self.diff_src_entry=ttk.Entry(pf, textvariable=self.diff_src_display_var, state="readonly")
        self.diff_src_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(pf, text="選択", command=lambda:self.pick_review_file(self.diff_src_var)).grid(row=0, column=2)
        ttk.Label(pf, text="日本語").grid(row=1, column=0, sticky="w", pady=(5,0))
        self.diff_dst_entry=ttk.Entry(pf, textvariable=self.diff_dst_display_var, state="readonly")
        self.diff_dst_entry.grid(row=1, column=1, sticky="ew", padx=6, pady=(5,0))
        ttk.Button(pf, text="選択", command=lambda:self.pick_review_file(self.diff_dst_var)).grid(row=1, column=2, pady=(5,0))
        ttk.Button(pf, text="差分を調査", command=self.load_diff_inspector).grid(row=0, column=3, rowspan=2, padx=(8,0))
        self.diff_drop_hint=ttk.Label(pf,text="英語または簡体字中国語の原文YAMLと日本語YAMLをここへドラッグ＆ドロップできます" if DND_AVAILABLE else "ドラッグ＆ドロップはこのビルドでは利用できません",foreground="#555")
        self.diff_drop_hint.grid(row=2,column=0,columnspan=4,sticky="ew",pady=(7,0))

        bar = ttk.Frame(t); bar.pack(fill="x", pady=(8,5))
        ttk.Button(bar, text="選択項目を翻訳", command=lambda:self.translate_diff_items(False)).pack(side="left")
        ttk.Button(bar, text="欠落・未翻訳をまとめて翻訳", command=lambda:self.translate_diff_items(True)).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="選択訳を保存", command=self.save_diff_value).pack(side="left", padx=(6,0))
        ttk.Button(bar,text="用語集を自動作成",command=lambda:self.start_auto_glossary_generation("diff")).pack(side="left",padx=(8,0))
        ttk.Button(bar,text="現在の翻訳設定を適用",command=self.apply_translation_settings_everywhere).pack(side="left",padx=(10,0))
        ttk.Label(bar,text="差分翻訳は現在の翻訳モデル設定を使用 / 一覧は状態→キーで整理",foreground="#666").pack(side="left",padx=(12,0))
        ttk.Label(bar, textvariable=self.diff_summary_var).pack(side="right")

        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=2); paned.add(right, weight=3)
        self.diff_tree = ttk.Treeview(left, columns=("key",), show="tree headings", selectmode="extended")
        self._enable_ctrl_multiselect(self.diff_tree)
        self.diff_tree.heading("#0", text="状態"); self.diff_tree.column("#0", width=150)
        self.diff_tree.heading("key", text="キー"); self.diff_tree.column("key", width=360)
        self.diff_tree.tag_configure("missing", background="#fee2e2")
        self.diff_tree.tag_configure("untranslated", background="#fef3c7")
        self.diff_tree.tag_configure("extra", background="#e0e7ff")
        self.diff_tree.bind("<<TreeviewSelect>>", self.on_diff_select)
        self._enable_tree_sort(self.diff_tree, recursive=True)
        ys = ttk.Scrollbar(left, command=self.diff_tree.yview); self.diff_tree.configure(yscrollcommand=ys.set)
        hint = ttk.Label(left, text="Ctrlキーを押しながらクリックすると複数選択できます。", foreground="#666")
        hint.pack(side="bottom", fill="x", pady=(3,0))
        self.diff_tree.pack(side="left", fill="both", expand=True); ys.pack(side="right", fill="y")

        compare = ttk.Panedwindow(right, orient="horizontal"); compare.pack(fill="both", expand=True)
        srcf = ttk.Frame(compare); dstf = ttk.Frame(compare); compare.add(srcf, weight=1); compare.add(dstf, weight=1)
        ttk.Label(srcf, text="原文（英語 / 簡体字中国語）").pack(anchor="w")
        self.diff_src_text = tk.Text(srcf, wrap="word"); self.diff_src_text.pack(fill="both", expand=True, padx=(0,4), pady=(2,0))
        ttk.Label(dstf, text="日本語（直接編集可）").pack(anchor="w")
        self.diff_dst_text = tk.Text(dstf, wrap="word"); self.diff_dst_text.pack(fill="both", expand=True, padx=(4,0), pady=(2,0))
        self.diff_message_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.diff_message_var, wraplength=650).pack(fill="x", pady=(4,0))
        self._register_dnd_widgets([pf,self.diff_src_entry,self.diff_dst_entry,self.diff_drop_hint,self.diff_tree,self.diff_src_text,self.diff_dst_text],self.on_diff_drop_paths)

    def _build_search_tab(self):
        t = self.tab_search
        top = ttk.LabelFrame(t, text="ゲーム内の日本語翻訳を検索", padding=8); top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="対象ゲーム").grid(row=0, column=0, sticky="w")
        self.search_game_combo = ttk.Combobox(top, textvariable=self.search_game_var, values=list(core.PARADOX_STEAM_GAMES), state="readonly", width=28)
        self.search_game_combo.grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(top, text="ゲーム / Mod場所を再検出", command=self.discover_mod_locations).grid(row=0, column=2, columnspan=2, sticky="e")
        ttk.Label(top, text="検索語").grid(row=1, column=0, sticky="w", pady=(6,0))
        ent = ttk.Entry(top, textvariable=self.search_query_var); ent.grid(row=1, column=1, sticky="ew", padx=6, pady=(6,0)); ent.bind("<Return>", lambda e:self.run_translation_search())
        ttk.Button(top, text="検索", command=self.run_translation_search).grid(row=1, column=2, sticky="ew", pady=(6,0))
        ttk.Button(top, text="結果を消去", command=self.clear_translation_search_results).grid(row=1, column=3, sticky="ew", padx=(6,0), pady=(6,0))
        ttk.Label(top, text="検索語は必須です。ローカライズキー・日本語本文・原文を検索し、原文にあるのに日本語側にないキーは「未訳」として表示します。", foreground="#666").grid(row=2, column=0, columnspan=4, sticky="w", pady=(6,0))

        ttk.Label(t, textvariable=self.search_summary_var).pack(anchor="w", pady=(7,4))
        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=3); paned.add(right, weight=2)
        search_table = ttk.Frame(left)
        search_table.pack(fill="both", expand=True)
        search_table.rowconfigure(0, weight=1)
        search_table.columnconfigure(0, weight=1)
        self.search_tree = ttk.Treeview(search_table, columns=("mod","file","key","value"), show="headings")
        for c, txt, w in (("mod","Mod",260),("file","ファイル",260),("key","キー",360),("value","日本語訳",520)):
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
        self.search_selected_var = tk.StringVar(value="検索結果を選択してください")
        ttk.Label(right, textvariable=self.search_selected_var, wraplength=420).pack(fill="x", anchor="w")
        self.search_edit_text = tk.Text(right, wrap="word"); self.search_edit_text.pack(fill="both", expand=True, pady=(6,6))
        ttk.Button(right, text="この日本語訳を保存", command=self.save_search_value).pack(anchor="w")

    def _build_glossary_tab(self):
        t=self.tab_glossary
        top=ttk.LabelFrame(t,text="用語集設定",padding=8); top.pack(fill="x",pady=(0,6))
        ttk.Label(top,text="用語集ファイル").pack(side="left")
        ttk.Entry(top,textvariable=self.glossary_path_var).pack(side="left",fill="x",expand=True,padx=6)
        ttk.Button(top,text="読込",command=self.load_glossary_ui).pack(side="left")
        ttk.Button(top,text="保存",command=self.save_glossary_ui).pack(side="left",padx=(6,0))
        ttk.Label(top,textvariable=self.auto_glossary_status_var,foreground="#555").pack(side="right",padx=(8,0))

        panes=ttk.Panedwindow(t,orient="horizontal"); panes.pack(fill="both",expand=True)
        manual=ttk.LabelFrame(panes,text="自分で作った用語",padding=8)
        generated=ttk.LabelFrame(panes,text="自動生成 / 取り込み用語",padding=8)
        panes.add(manual,weight=1); panes.add(generated,weight=1)

        mbar=ttk.Frame(manual); mbar.pack(fill="x",pady=(0,6))
        ttk.Button(mbar,text="用語追加",command=self.add_glossary_term).pack(side="left")
        ttk.Button(mbar,text="選択編集",command=self.edit_glossary_term).pack(side="left",padx=(6,0))
        ttk.Button(mbar,text="選択削除",command=self.delete_glossary_term).pack(side="left",padx=(6,0))
        ttk.Label(manual,text="手動で固定した原語 → 日本語訳です。手動用語は自動生成で上書きされません。",foreground="#666",wraplength=520,justify="left").pack(fill="x",anchor="w",pady=(0,6))
        self.glossary_tree=ttk.Treeview(manual,columns=("src","dst"),show="headings")
        self.glossary_tree.heading("src",text="原語"); self.glossary_tree.heading("dst",text="日本語")
        self.glossary_tree.column("src",width=260,stretch=True); self.glossary_tree.column("dst",width=300,stretch=True)
        self._enable_tree_sort(self.glossary_tree)
        my=ttk.Scrollbar(manual,orient="vertical",command=self.glossary_tree.yview); mx=ttk.Scrollbar(manual,orient="horizontal",command=self.glossary_tree.xview)
        self.glossary_tree.configure(yscrollcommand=my.set,xscrollcommand=mx.set)
        self.glossary_tree.pack(fill="both",expand=True); mx.pack(fill="x")
        self.glossary_tree.bind("<Double-1>",lambda e:self.edit_glossary_term())

        gbar=ttk.Frame(generated); gbar.pack(fill="x",pady=(0,6))
        self.glossary_base_import_btn=ttk.Button(gbar,text="ゲーム本体から取り込む",command=self.import_glossary_from_base_game)
        self.glossary_base_import_btn.pack(side="left")
        self.glossary_import_menu=tk.Menu(gbar,tearoff=False)
        self.glossary_import_menu.add_command(label="日本語YAMLファイルから取り込む",command=lambda:self.import_glossary_from_japanese_source("file"))
        self.glossary_import_menu.add_command(label="日本語化Mod / localizationフォルダから取り込む",command=lambda:self.import_glossary_from_japanese_source("folder"))
        self.glossary_jp_import_btn=ttk.Menubutton(gbar,text="日本語化ファイル / Modから取り込む",menu=self.glossary_import_menu)
        self.glossary_jp_import_btn.pack(side="left",padx=(6,0))
        ttk.Label(generated,text="※ ゲーム本体の日本語訳は［ゲーム本体から取り込む］を使うと、英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。",foreground="#8a5a00",wraplength=560,justify="left").pack(fill="x",anchor="w",pady=(0,4))
        ttk.Label(generated,text="通常翻訳・中国語基準翻訳・QA・差分調査で作成した用語と、ゲーム本体や既存日本語化から取り込んだ用語を表示します。自動生成は各作業タブから実行します。",foreground="#666",wraplength=560,justify="left").pack(fill="x",anchor="w",pady=(0,4))
        self.auto_glossary_drop_hint=ttk.Label(generated,text=("ドラッグ＆ドロップ対応 — 日本語YAML / 日本語化Mod / localizationフォルダ" if DND_AVAILABLE else "ドラッグ＆ドロップはこのビルドでは利用できません"),foreground="#555")
        self.auto_glossary_drop_hint.pack(fill="x",anchor="w",pady=(0,6))
        self.auto_glossary_tree=ttk.Treeview(generated,columns=("src","dst","kind"),show="headings")
        for c,label,w in (("src","原語",250),("dst","日本語",280),("kind","由来",140)):
            self.auto_glossary_tree.heading(c,text=label); self.auto_glossary_tree.column(c,width=w,stretch=True)
        self._enable_tree_sort(self.auto_glossary_tree)
        gy=ttk.Scrollbar(generated,orient="vertical",command=self.auto_glossary_tree.yview); gx=ttk.Scrollbar(generated,orient="horizontal",command=self.auto_glossary_tree.xview)
        self.auto_glossary_tree.configure(yscrollcommand=gy.set,xscrollcommand=gx.set)
        self.auto_glossary_tree.pack(fill="both",expand=True); gx.pack(fill="x")
        if DND_AVAILABLE:
            try:
                self._register_dnd_widgets([generated,self.auto_glossary_drop_hint,self.auto_glossary_tree],self.on_glossary_import_drop_paths)
            except Exception as exc:
                self.auto_glossary_drop_hint.configure(text=f"ドラッグ＆ドロップ初期化失敗: {exc}")
                record_error("用語集DnD初期化",exc)
        self.load_glossary_ui(silent=True)

    def _build_settings_tab(self):
        t = self.tab_settings
        box = ttk.LabelFrame(t, text="自動生成ファイルの保存場所", padding=12)
        box.pack(fill="x")
        box.columnconfigure(1, weight=1)
        ttk.Label(box, text="保存フォルダ").grid(row=0, column=0, sticky="w")
        ttk.Entry(box, textvariable=self.data_root_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=(8,8))
        ttk.Button(box, text="保存場所を変更", command=self.change_data_root).grid(row=0, column=2)
        ttk.Button(box, text="フォルダを開く", command=lambda:self._open_path(DATA_ROOT)).grid(row=0, column=3, padx=(6,0))
        ttk.Button(box, text="エラーログを開く", command=lambda:self._open_path(LOG_ROOT)).grid(row=2, column=2, pady=(10,0))
        ttk.Button(box, text="診断ログを収集", command=self.collect_error_logs).grid(row=2, column=3, padx=(6,0), pady=(10,0))
        ttk.Label(box, text="翻訳結果・キャッシュ・バックアップ・設定・セッション・モデル統計など、アプリが自動生成するデータはすべてこの『Paradox Localization Translator』フォルダ内にまとめます。", wraplength=920, foreground="#555").grid(row=1, column=0, columnspan=4, sticky="w", pady=(10,0))

        close_box = ttk.LabelFrame(t, text="ウィンドウの×ボタンを押したときの動作", padding=12)
        close_box.pack(fill="x", pady=(12,0))
        ttk.Label(close_box, text="既定動作").grid(row=0, column=0, sticky="w")
        close_combo = ttk.Combobox(close_box, textvariable=self.close_action_var, state="readonly", width=20,
                                   values=("毎回確認", "最小化", "終了"))
        close_combo.grid(row=0, column=1, sticky="w", padx=(8,12))
        ttk.Label(close_box, text="通常は『毎回確認』を推奨します。", foreground="#555").grid(row=0,column=2,sticky="w")
        ttk.Button(close_box, text="この設定を保存", command=self.save_close_behavior_settings).grid(row=0,column=3,padx=(12,0))
        ttk.Label(close_box, text=(
            "毎回確認: ×ボタンを押すたびに『最小化 / 終了 / キャンセル』を選びます。\n"
            "最小化: 確認せずウィンドウだけを最小化し、翻訳・探索・LLM処理は続行します。\n"
            "終了: 確認せず、翻訳中ならセッションとキャッシュを保存して停止要求を出してから終了します。"
        ), foreground="#555", wraplength=1100, justify="left").grid(row=1,column=0,columnspan=4,sticky="w",pady=(5,0))

        structure = ttk.LabelFrame(t, text="フォルダ構成", padding=12)
        structure.pack(fill="both", expand=True, pady=(12,0))
        text = tk.Text(structure, height=16, wrap="none")
        text.pack(fill="both", expand=True)
        text.insert("1.0",
            "Paradox Localization Translator/\n"
            "├── 翻訳結果/\n"
            "├── キャッシュ/\n"
            "├── バックアップ/\n"
            "├── ログ/\n"
            "│   ├── errors_YYYYMMDD.log\n"
            "│   ├── resume_history.jsonl\n"
            "│   ├── storage_migration.log\n"
            "│   └── ParadoxLocalizationTranslator_diagnostics_*.zip\n"
            "├── 作業データ/  ← バージョン非依存の一時・作業状態用\n"
            "└── 設定/\n"
            "    ├── session.json\n"
            "    ├── resume_state.json\n"
            "    ├── storage_migration.json\n"
            "    ├── glossary.json\n"
            "    ├── model_stats.json\n"
            "    ├── model_profiles.json\n"
            "    ├── mod_translation_status_cache.json\n"
            "    ├── steam_library_roots.json\n"
            "    └── app_preferences.json  ← 前回LLM設定・×ボタン動作\n\n"
            "既定位置: 書類/Documents/Paradox Localization Translator\n"
            "［保存場所を変更］から、別ドライブ・外付けSSD・任意のフォルダへ移動できます。")
        text.config(state="disabled")

    def change_data_root(self):
        old_root = DATA_ROOT
        chosen = filedialog.askdirectory(title="Paradox Localization Translator フォルダの保存先を選択", initialdir=str(old_root.parent if old_root.exists() else Path.home()))
        if not chosen:
            return
        selected = Path(chosen).expanduser()
        new_root = selected if selected.name == DATA_FOLDER_NAME else selected / DATA_FOLDER_NAME
        try:
            if new_root.resolve() == old_root.resolve():
                messagebox.showinfo(APP_NAME, "現在と同じ保存場所です。")
                return
        except Exception:
            pass
        if not _is_writable_dir(new_root):
            messagebox.showerror(APP_NAME, f"選択した場所へ書き込めません。\n{new_root}")
            return
        ans = messagebox.askyesnocancel(
            APP_NAME,
            "自動生成ファイルの保存場所を変更します。\n\n"
            f"現在: {old_root}\n"
            f"変更後: {new_root}\n\n"
            "［はい］: 現在のデータを新しい場所へコピーしてから切り替える\n"
            "［いいえ］: データは移動せず、今後の生成先だけ変更する\n"
            "［キャンセル］: 変更しない")
        if ans is None:
            return
        try:
            if ans and old_root.exists():
                shutil.copytree(old_root, new_root, dirs_exist_ok=True)
            _save_data_root_preference(new_root)
            _configure_data_root(new_root)
            # Active queue/state must follow the data-root move as well; otherwise
            # a running session could keep writing cache/output paths under old_root.
            for item in self.queue_items:
                if not isinstance(item, dict):
                    continue
                for key in ("cache", "output", "previous_cache"):
                    raw = item.get(key)
                    if not raw:
                        continue
                    try:
                        rel = Path(raw).expanduser().resolve().relative_to(old_root.resolve())
                        item[key] = str(DATA_ROOT / rel)
                    except Exception:
                        pass
            self.data_root_var.set(str(DATA_ROOT))
            current_glossary = self.glossary_path_var.get().strip()
            try:
                rel = Path(current_glossary).expanduser().resolve().relative_to(old_root.resolve()) if current_glossary else None
                self.glossary_path_var.set(str(DATA_ROOT / rel) if rel is not None else str(DEFAULT_GLOSSARY))
            except Exception:
                # External user-selected glossaries remain external; only the old
                # default location is replaced by the new default.
                if not current_glossary or current_glossary == str(old_root / "設定" / "glossary.json"):
                    self.glossary_path_var.set(str(DEFAULT_GLOSSARY))
            self.model_stats = core.load_json(STATS_PATH, {})
            self.model_profiles = core.load_json(PROFILES_PATH, {})
            self.mod_status_cache = core.load_json(MOD_STATUS_CACHE_PATH, {"version":MOD_STATUS_CACHE_VERSION,"items":{}})
            if not isinstance(self.mod_status_cache, dict) or self.mod_status_cache.get("version") != MOD_STATUS_CACHE_VERSION:
                self.mod_status_cache={"version":MOD_STATUS_CACHE_VERSION,"items":{}}
            self.refresh_profiles_ui()
            self._restore_cached_mod_status()
            messagebox.showinfo(APP_NAME,
                "保存場所を変更しました。\n\n"
                f"{DATA_ROOT}\n\n"
                + ("既存データもコピーしました。" if ans else "今後作成するデータから新しい場所を使用します。"))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"保存場所の変更に失敗しました。\n{e}")

    def save_close_behavior_settings(self, silent=False):
        """Save the single × button behavior setting."""
        self._save_llm_preferences()
        if not silent:
            messagebox.showinfo(
                APP_NAME,
                "×ボタンの動作設定を保存しました。\n\n"
                f"動作: {self.close_action_var.get()}"
            )
        return True

    def _show_close_choice_dialog(self):
        """Return 'minimize', 'quit' or 'cancel'."""
        dlg = tk.Toplevel(self)
        dlg.title("アプリを閉じますか？")
        dlg.transient(self)
        dlg.grab_set()
        dlg.resizable(False, False)
        result = {"action": "cancel"}
        active_translation = bool(self.worker and self.worker.is_alive())
        active_monitor = bool(self.monitor_thread and self.monitor_thread.is_alive())

        frame = ttk.Frame(dlg, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="×ボタンが押されました", font=("", 14, "bold")).pack(anchor="w")
        ttk.Label(
            frame,
            text=(
                "最小化しますか？ それともアプリを終了しますか？\n\n"
                "・最小化: ウィンドウだけを最小化します。翻訳・探索・LLM処理は続行します。\n"
                "・終了: 翻訳中ならセッションとキャッシュを保存し、安全停止を要求してから終了します。"
            ),
            justify="left", wraplength=560
        ).pack(anchor="w", pady=(10, 10))
        if active_translation or active_monitor:
            running = []
            if active_translation: running.append("翻訳")
            if active_monitor: running.append("Mod探索/監視")
            ttk.Label(frame, text="現在動作中: " + " / ".join(running), foreground="#a35a00").pack(anchor="w", pady=(0,8))
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        def choose(action):
            result["action"] = action
            dlg.destroy()
        ttk.Button(buttons, text="最小化", command=lambda: choose("minimize")).pack(side="left")
        ttk.Button(buttons, text="終了", command=lambda: choose("quit")).pack(side="left", padx=(8,0))
        ttk.Button(buttons, text="キャンセル", command=lambda: choose("cancel")).pack(side="right")
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

    def _perform_app_exit(self):
        """終了時の保存規則を一箇所に固定してからUIを閉じる。"""
        self._save_llm_preferences()
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_stop_event.set()
            if self.monitor_llm_controller:
                self.monitor_llm_controller.request_stop(save=False)

        running=bool(self.worker and self.worker.is_alive())
        unfinished=any(not self._queue_item_is_completed(item) for item in self.queue_items)
        if running:
            # 翻訳中の終了は必ず復元可能状態として保存する。
            self._write_session_file(active=True,restore_on_launch=True)
            if self.controller:
                self.controller.request_stop(save=True)
        elif self.queue_items and unfinished:
            # 待機中/中断済みの未完了キューだけを終了時保存する。
            self._write_session_file(active=False,restore_on_launch=True)
        else:
            # 空キュー、または全項目完了済みなら古いセッションを残さない。
            self._delete_session()

        if self.chinese_worker and self.chinese_worker.is_alive() and self.chinese_controller:
            self.chinese_controller.request_stop(save=True)
        self.destroy()

    def apply_performance_preset(self):
        """バッチサイズと並列数の安全側プリセットを適用する。

        Paradox localization は1行の長さが一定ではないため、数値は絶対的な
        上限ではなく実用上の目安。特にローカルLLMではサーバー側の並列設定と
        メモリ容量に左右される。
        """
        name = self.performance_preset_var.get()
        presets = {
            "安定重視（20 / 1）": (20, 1),
            "標準（40 / 1）": (40, 1),
            "高速（60 / 2）": (60, 2),
        }
        batch, workers = presets.get(name, (40, 1))
        self.batch_var.set(batch)
        self.workers_var.set(workers)
        note = {
            "安定重視（20 / 1）": "長文が多いMod、初回利用、メモリに余裕がない環境向けです。",
            "標準（40 / 1）": "通常はこちらを推奨します。速度と安定性のバランスを優先します。",
            "高速（60 / 2）": "同時2リクエストを処理できる環境向けです。Ollama/LM Studio側の並列処理と十分なメモリが必要です。",
        }.get(name, "")
        messagebox.showinfo(
            "おすすめ設定",
            f"{name} を適用しました。\n\nバッチ: {batch}\n並列: {workers}\n\n{note}\n\n"
            "安定性の目安\n"
            "・バッチ 1–60: 通常範囲\n"
            "・バッチ 80超: 長文では応答欠落・タイムアウトに注意\n"
            "・バッチ 120超: 非推奨\n"
            "・並列 1: 最も安定\n"
            "・並列 2: サーバー側が同時処理できる場合のみ推奨\n"
            "・並列 3以上: ローカルLLMではVRAM/RAM圧迫、待ち行列、タイムアウトが増えやすい\n\n"
            "クラウドAPIでは並列数を上げられる場合がありますが、API側のレート制限を優先してください。"
        )

    def _build_help_tab(self):
        t = self.tab_help
        title = ttk.Label(t, text="Paradox Localization Translator 使い方", font=("", 18, "bold"))
        title.pack(anchor="w", pady=(0, 10))
        box = tk.Text(t, wrap="word", padx=12, pady=12)
        box.pack(fill="both", expand=True)
        guide = """Paradox Localization Translator 詳細ガイド

【0. このアプリでできること】
Paradox Interactive系ゲームのlocalization YAMLを、ローカルLLMまたはクラウドAPIで日本語化するための統合ツールです。
単純な一括翻訳だけでなく、未翻訳修復、差分更新、QA、検索修正、Mod翻訳状況調査、既存日本語化Modへの差分反映、キャッシュ管理まで行えます。

主な対応タイトル:
・Crusader Kings III
・Victoria 3
・Hearts of Iron IV
・Stellaris
・Europa Universalis V

【1. 最初に必要なもの】
ローカルLLMを使う場合:
・Ollama または LM Studio
・翻訳に使うLLMモデル

クラウドAPIを使う場合:
・OpenAI / Anthropic / Gemini / OpenAI互換APIのAPIキー

配布版アプリにはPython、Tk/Tcl、必要なGUI部品が内蔵されるため、利用者がPythonを別途入れる必要はありません。

【2. 起動したら最初に確認する場所】
画面上部にはLLM状態が2系統あります。

翻訳用LLM:
通常翻訳、差分翻訳、QAのAI校正、モデル速度テストなどに使います。

探索用LLM:
未翻訳Mod探索や、翻訳状況の曖昧候補判定に使います。
探索用には3B～8B程度の軽量モデルを推奨します。

それぞれ「最新応答」欄には、実際にLLMから返ってきた応答を読み取り専用で表示します。
「全文を開く」で完全な応答を確認できます。

【3. 翻訳 / キュー タブ】
ここが通常翻訳の中心です。

［追加］:
YAMLファイルまたはlocalization/Modフォルダを追加します。ドラッグ＆ドロップも利用できます。

［選択削除］:
選択中のキュー項目だけを削除します。原本ファイルは削除しません。

［全消去］:
翻訳キューを空にします。原本やキャッシュは削除しません。

［翻訳開始］:
上から順番に翻訳します。

［一時停止］:
現在のAPI/LLM応答が終わった安全な地点で一時停止します。

［セーブして中断］:
現在までのキャッシュとセッションを保存して停止します。次回起動時に再開できます。

［現在の翻訳へ設定を適用］:
翻訳途中でモデル、プロバイダ、URL、バッチ、並列、用語集、英中併用設定などを変更した後、このボタンを押すと次のバッチから新設定を使います。

［上書き］:
完成した翻訳を元Modまたは検出済み日本語化Modへ反映します。
既存日本語化Modがある場合は、押した時に「日本語化Modへ差分上書き / 元Modへ上書き / キャンセル」を選べます。上書き前に対象を明示し、バックアップを作成します。

【4. バッチ / 並列のおすすめ設定】
おすすめ設定から3種類を選べます。

安定重視: バッチ20 / 並列1
・長文が多いMod
・初回利用
・メモリ余裕が少ない環境
・動作確認を優先したい場合

標準: バッチ40 / 並列1
・通常はこちらを推奨
・速度と安定性のバランス重視

高速: バッチ60 / 並列2
・Ollama / LM Studio側が同時2リクエストを処理できる場合
・十分なRAM/VRAMがある場合

目安:
・バッチ1～60: 通常範囲
・バッチ80超: 長文で欠落、タイムアウトが増えやすい
・バッチ120超: 非推奨
・並列1: 最も安定
・並列2: サーバー側並列処理を有効にしている場合に推奨
・並列3以上: ローカルLLMではメモリ圧迫、待ち行列、タイムアウトが増えやすい

クラウドAPIではサービス側のレート制限を優先してください。

【5. LLM / 翻訳設定】
プロバイダ:
Ollama / LM Studio / OpenAI / Anthropic / Gemini / OpenAI Compatible から選択できます。

URL:
Ollama既定: http://localhost:11434
LM Studio既定: http://localhost:1234/v1
クラウドは通常自動設定されます。

モデル:
接続確認後、利用可能なモデル一覧から選択します。

APIキー:
クラウドAPI用です。アプリの設定ファイルには保存しません。

プリセット:
CK3などゲームごとの翻訳プロンプト方針に使います。

中国語基準翻訳:
専用タブへ簡体字中国語YAMLを入れると、中国語の漢字語彙・制度語・固有語を第一基準として日本語化します。英語ファイルは不要です。

既存日本語の未翻訳を修復:
l_japanese内に英語などが残っている場合、その部分だけ修復対象にします。

翻訳後に自動QA:
翻訳後、未翻訳やParadox構文破損を検査します。

【6. キャッシュ】
翻訳ごとに独立したキャッシュを持ちます。
同じMod更新時も過去キャッシュを特定し、変更のない文章を再翻訳しません。

［キャッシュを見る］:
選択キューのキャッシュ内容、件数、保存場所を確認します。

［キャッシュを追加］:
別のtranslate_cache.jsonを現在の翻訳へ統合します。

差分更新:
前回原文のsource_manifest.jsonと現在の原文を比較し、新規・変更箇所だけ再翻訳します。

【7. QA / 比較編集 タブ】
原文と日本語を比較し、問題を階層表示します。
YAMLをドラッグ＆ドロップして読み込めます。

主な検査:
・未翻訳
・キー欠落
・プレースホルダ不一致
・[Character...] / $VALUE$ / §色コード等の破損
・誤字脱字候補
・括弧や句読点の不整合

問題行を選ぶと原文と日本語を並べて確認できます。
日本語欄を直接編集して保存できます。
AI校正は現在の翻訳用LLM設定を使用します。設定変更後は［現在の翻訳設定を適用］を押してください。

【8. 差分調査 タブ】
英語/原文と日本語をキー単位で向かい合わせに比較します。
ドラッグ＆ドロップにも対応します。

判定例:
・欠落: 原文にはあるが日本語にない
・未翻訳: 日本語値が英語原文のまま
・日本語のみ: 日本語側だけにキーがある
・対応あり: 正常に対応している

［選択項目を翻訳］:
選択した1キーだけ翻訳します。

［欠落・未翻訳をまとめて翻訳］:
問題箇所だけまとめてLLMへ送ります。

差分翻訳も現在の翻訳用LLM設定を使用します。

【9. 翻訳検索 タブ】
日本語YAML/フォルダを横断検索し、検索結果から直接翻訳を訂正できます。

検索対象:
・ファイル名
・localizationキー
・日本語本文

結果を選ぶと現在の訳文を編集でき、［この日本語訳を保存］で元YAMLへ反映します。

【10. 用語集 タブ】
固定訳を登録できます。
例: Grand Campaign → 開辺

該当する原文が翻訳バッチに含まれる場合、その用語だけLLMプロンプトへ提示します。
用語集を途中変更した場合も、現在の翻訳へ設定を適用すれば次のバッチから反映できます。

【11. モデル / 接続 タブ】
接続確認、モデル一覧、速度テスト、プロファイル管理を行います。

現在モデルを速度テスト:
現在選択中の1モデルを測定します。

選択モデルを比較テスト:
最大5モデルまで選び、平均処理時間、tokens/s、失敗率を比較します。

モデルプロファイル:
プロバイダ、URL、モデル、バッチ、並列、ゲームプリセットなどをまとめて保存できます。
追加だけでなく削除もできます。

前回使用した翻訳用/探索用のプロバイダ・URL・モデルは次回起動時に自動復元します。APIキーは保存しません。

【12. 未翻訳監視 タブ】
翻訳状況タブで登録したMod場所を読み取り専用で常時監視します。自動翻訳はしません。

監視対象:
［翻訳状況］タブでゲーム/Mod場所を選択し、［選択した場所のModを調査］を実行すると、その場所が監視対象にも登録されます。

探索専用LLM:
通常翻訳とは別モデルを指定できます。3B～8B程度の軽量モデルを推奨します。

［常時監視を開始］:
監視開始後は同じボタンが［常時監視を停止］に変わり、状態欄に「● 常時監視中」と表示します。

［再調査］:
登録済みの監視対象について、Mod翻訳状況をもう一度調査します。

監視中はYAMLの更新時刻・サイズを確認し、変更があった対象だけ解析します。曖昧な候補だけ軽量LLMへ送ります。

【13. 翻訳状況 タブ】
ゲーム/Mod場所の自動検出、調査対象の選択、Mod翻訳状況の調査をここへ集約しています。
複数の場所を選択して［選択した場所のModを調査］を実行できます。結果はキャッシュされ、変更があったModだけ再調査します。

表示例:
・翻訳なし
・欠損あり
・別Mod翻訳・欠損
・別Modで完全翻訳
・翻訳あり

日本語化Mod検出:
元Modに日本語がなくても、同じゲーム内の別Modが原文キーに対応する日本語キーを持っていれば、日本語化Mod候補として判定します。
完全か欠損ありかも表示します。

検索:
Mod名や状態を入力して、判定済み一覧を絞り込めます。

キューへ追加:
複数選択したModは、選択した全件を通常翻訳キューへ追加できます。中国語基準キューでは、中国語localizationがある選択Modを全件追加します。

選択Modを除外してキューへ追加:
選択したModだけ除外し、残りを通常翻訳キュー、または中国語localizationがあるModだけ中国語基準キューへまとめて追加できます。

日本語化Modへの上書き:
既存日本語化Modがある場合は元Modではなく日本語化Mod側へ不足分を差分反映します。
既存訳を維持し、欠落キーや未翻訳キーだけ追加・更新します。
実行前には上書き先Mod名とパスを表示し、バックアップ＋二重確認を行います。

【14. 自動生成ファイルと保存場所】
自動生成物はすべて1つのフォルダにまとめます。

既定:
書類/Documents/Paradox Localization Translator/

構成:
Paradox Localization Translator/
├── 翻訳結果/
├── キャッシュ/
├── バックアップ/
├── ログ/
├── 作業データ/
└── 設定/

旧バージョンの実行ファイル横にある ParadoxLocalizationTranslator_Data は起動時に検出し、必要なデータをこの保存先へ非破壊で引き継ぎます。再開セッション内の旧絶対パスも現在の保存先へ読み替えます。

［設定］タブの［保存場所を変更］から別SSDや任意フォルダへ変更できます。既存データをコピーして移行することもできます。

【15. エラーログ / 診断】
アプリ例外、LLM接続失敗、YAML解析失敗、書込失敗などを日別ログへ保存します。

［エラーログを開く］:
ログフォルダを開きます。

［診断ログを収集］:
OS、アプリバージョン、モデル情報、エラーログなどを診断ZIPへまとめます。APIキーや翻訳本文は含めません。

【16. ×ボタンを押したとき】
右上/左上の×ボタンを押すと、既定では次の確認が出ます。

「最小化しますか？ それともアプリを終了しますか？」

最小化:
・ウィンドウだけ最小化します
・翻訳、探索、LLM処理は止まりません

終了:
・未完了の翻訳キューがあればセッションを保存します
・正常完了済みのキューは復元セッションとして残しません
・次回起動時に復元を拒否したセッションは破棄され、再表示されません
・LLM/翻訳処理へ安全停止要求を出してからアプリを終了します

後から変更したい場合:
［設定］→［ウィンドウの×ボタンを押したときの動作］で、
・毎回確認
・最小化
・終了
を選択できます。

【17. 安全に使うための注意】
・元Modへ直接上書きする前に必ず警告内容を確認してください。
・Steam Workshop更新で手動変更が上書きされる場合があります。
・直接上書き時は自動バックアップを作ります。
・大規模翻訳ではまず標準設定（40 / 1）を推奨します。
・探索用LLMは小型モデルを使うと負荷を抑えられます。
・クラウドAPIキーは保存されません。
・不具合時は診断ログZIPを作成すると原因調査が容易です。

【18. よくある使い方】
新規Modを日本語化:
1. Modをドラッグ
2. 翻訳モデル確認
3. 翻訳開始
4. QA
5. 必要なら検索修正
6. 完成版をModへ差分上書き

既存日本語化Modの欠損を直す:
1. 全Mod調査
2. 翻訳状況で「別Mod翻訳・欠損」を確認
3. 対象Modを翻訳
4. 翻訳中は［一時停止］または［セーブして中断］を利用可能
5. ［出力を開く］で完成ファイルを確認
6. ［上書き］を押し、日本語化Modが見つかっている場合は確認画面から上書き先を選択

Mod更新後だけ追加翻訳:
1. 更新済みModを再度追加
2. 過去キャッシュ/原文スナップショットを自動特定
3. 差分更新を確認
4. 新規・変更キーだけ翻訳

手動で訳語を直す:
1. 翻訳検索タブ
2. キーまたは日本語本文を検索
3. 結果を選択
4. 訳文を編集して保存

この使い方タブはアプリ内蔵説明書です。配布版だけを受け取った利用者でも、外部READMEを開かず基本操作から高度機能まで確認できます。
"""
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

        target = ttk.LabelFrame(left, text="監視対象", padding=8)
        target.pack(fill="x", pady=(0,8))
        ttk.Label(target, textvariable=self.monitor_target_summary_var, wraplength=470, justify="left").pack(anchor="w")
        ttk.Label(target, text="対象の追加・変更とMod調査は［翻訳状況］タブで行います。", foreground="#666", wraplength=470, justify="left").pack(anchor="w", pady=(5,0))
        ttk.Button(target, text="翻訳状況を開く", command=lambda:self.notebook.select(self.tab_status)).pack(anchor="w", pady=(7,0))

        cfg = ttk.LabelFrame(left, text="未翻訳監視設定", padding=8)
        cfg.pack(fill="x", pady=(0,8))
        cfg.columnconfigure(1, weight=1)
        ttk.Label(cfg, text="間隔(秒)").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(cfg, from_=3, to=600, textvariable=self.monitor_interval_var, width=7).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Separator(cfg, orient="horizontal").grid(row=1, column=0, columnspan=3, sticky="ew", pady=7)
        ttk.Label(cfg, text="監視専用LLM", font=("", 10, "bold")).grid(row=2, column=0, columnspan=3, sticky="w")
        ttk.Label(cfg, text="プロバイダ").grid(row=3, column=0, sticky="w", pady=(5,0))
        self.monitor_provider_combo = ttk.Combobox(
            cfg, textvariable=self.monitor_provider_var,
            values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],
            state="readonly", width=15)
        self.monitor_provider_combo.grid(row=3, column=1, sticky="ew", padx=6, pady=(5,0))
        self.monitor_provider_combo.bind("<<ComboboxSelected>>", lambda e:self.on_monitor_provider_change())
        ttk.Button(cfg, text="モデル再読込", command=self.refresh_monitor_models).grid(row=3, column=2, pady=(5,0))
        ttk.Label(cfg, text="URL").grid(row=4, column=0, sticky="w", pady=(5,0))
        ttk.Entry(cfg, textvariable=self.monitor_url_var).grid(row=4, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, text="モデル").grid(row=5, column=0, sticky="w", pady=(5,0))
        self.monitor_model_combo = ttk.Combobox(cfg, textvariable=self.monitor_model_var, state="normal")
        self.monitor_model_combo.grid(row=5, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, text="APIキー").grid(row=6, column=0, sticky="w", pady=(5,0))
        ttk.Entry(cfg, textvariable=self.monitor_api_key_var, show="•").grid(row=6, column=1, columnspan=2, sticky="ew", padx=6, pady=(5,0))
        ttk.Label(cfg, textvariable=self.monitor_connection_var, foreground="#555", wraplength=460, justify="left").grid(row=7, column=0, columnspan=3, sticky="w", pady=(5,0))
        ttk.Checkbutton(cfg, text="軽量LLMで曖昧候補だけ精査", variable=self.monitor_use_llm_var).grid(row=8, column=0, columnspan=3, sticky="w", pady=(5,0))
        ttk.Checkbutton(cfg, text="別Modの日本語化も検索する", variable=self.monitor_check_translation_mods_var).grid(row=9, column=0, columnspan=3, sticky="w", pady=(3,0))
        ttk.Label(cfg, text="判定専用なので3B〜8B級など小さなモデルを推奨します。自動翻訳は行いません。", foreground="#8a4b00", wraplength=460, justify="left").grid(row=10, column=0, columnspan=3, sticky="w", pady=(5,0))

        controls = ttk.LabelFrame(left, text="監視操作", padding=8)
        controls.pack(fill="x")
        r1=ttk.Frame(controls); r1.pack(fill="x")
        self.monitor_toggle_btn = ttk.Button(r1, text="常時監視を開始", command=self.toggle_monitor)
        self.monitor_toggle_btn.pack(side="left")
        ttk.Button(r1, text="再調査", command=self.research_monitor_targets).pack(side="left", padx=(6,0))
        self.mod_research_stop_btn = ttk.Button(r1, text="調査停止", command=self.stop_mod_research, state="disabled")
        self.mod_research_stop_btn.pack(side="left", padx=(6,0))
        ttk.Label(controls, textvariable=self.monitor_status_var, wraplength=460, justify="left").pack(anchor="w", pady=(6,0))

        result_top = ttk.Frame(right); result_top.pack(fill="x", pady=(0,6))
        ttk.Label(result_top, text="未翻訳候補", font=("", 12, "bold")).pack(side="left")
        ttk.Label(result_top, textvariable=self.monitor_summary_var, font=("", 11, "bold")).pack(side="left", padx=(12,0))
        ttk.Button(result_top, text="候補一覧を消去", command=self.clear_monitor_results).pack(side="right")
        ttk.Button(result_top, text="CSV保存", command=self.export_monitor_csv).pack(side="right", padx=(0,6))

        result_frame = ttk.Frame(right); result_frame.pack(fill="both", expand=True)
        cols=("kind","confidence","file","key","text")
        self.monitor_tree=ttk.Treeview(result_frame, columns=cols, show="headings", height=18)
        for c,txt,w in (("kind","種類",130),("confidence","判定",75),("file","ファイル",280),("key","キー",280),("text","内容",450)):
            self.monitor_tree.heading(c,text=txt); self.monitor_tree.column(c,width=w,anchor="w")
        sy=ttk.Scrollbar(result_frame,orient="vertical",command=self.monitor_tree.yview)
        sx=ttk.Scrollbar(result_frame,orient="horizontal",command=self.monitor_tree.xview)
        self._enable_tree_sort(self.monitor_tree)
        self.monitor_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.monitor_tree.grid(row=0,column=0,sticky="nsew")
        sy.grid(row=0,column=1,sticky="ns")
        sx.grid(row=1,column=0,sticky="ew")
        result_frame.rowconfigure(0,weight=1); result_frame.columnconfigure(0,weight=1)

        note = ttk.LabelFrame(right, text="仕組み", padding=6); note.pack(fill="x", pady=(6,0))
        ttk.Label(note, text="待機中は監視対象のYAML更新時刻とサイズだけを確認します。変更があった対象だけ解析し、曖昧候補だけ監視専用LLMへ送ります。自動翻訳・ファイル書換えは行いません。", wraplength=650, justify="left").pack(anchor="w")

    def _build_status_tab(self):
        t = self.tab_status
        top = ttk.Frame(t); top.pack(fill="x", pady=(0,6))
        ttk.Label(top, text="Modごとの日本語翻訳状況", font=("", 13, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.mod_status_summary_var).pack(side="right")

        # フルHDでも縦方向が苦しくなりにくいよう、左に設定系、右に結果系を置く。
        body = ttk.Panedwindow(t, orient="horizontal")
        body.pack(fill="both", expand=True)
        left_outer, left, self.status_left_canvas, self.status_left_scrollbar = self._make_vertical_scroll_area(body)
        right_outer, right, self.status_right_canvas, self.status_right_scrollbar = self._make_vertical_scroll_area(body)
        body.add(left_outer, weight=2)
        body.add(right_outer, weight=5)

        discovery = ttk.LabelFrame(left, text="ゲーム / Mod場所", padding=6); discovery.pack(fill="x", pady=(0,6))
        dbar1 = ttk.Frame(discovery); dbar1.pack(fill="x", pady=(0,5))
        ttk.Button(dbar1, text="ゲーム/Mod場所を自動検出", command=self.discover_mod_locations).pack(side="left")
        ttk.Button(dbar1, text="選択した場所のModを調査", command=self.research_selected_discovered_location).pack(side="left", padx=(6,0))
        ttk.Label(dbar1, textvariable=self.mod_discovery_status_var).pack(side="right")
        dbar2 = ttk.Frame(discovery); dbar2.pack(fill="x", pady=(0,5))
        ttk.Checkbutton(dbar2, text="複数選択モード", variable=self.discovery_multi_select_var).pack(side="left")
        ttk.Button(dbar2, text="すべて選択", command=self.select_all_discovered_locations).pack(side="left", padx=(6,0))
        ttk.Button(dbar2, text="選択解除", command=lambda:self.discovered_mod_tree.selection_remove(self.discovered_mod_tree.selection())).pack(side="left", padx=(6,0))
        cols=("game","kind","mods","path")
        treewrap = ttk.Frame(discovery); treewrap.pack(fill="both", expand=True)
        self.discovered_mod_tree=ttk.Treeview(treewrap, columns=cols, show="headings", height=6, selectmode="extended")
        self._enable_ctrl_multiselect(self.discovered_mod_tree)
        self.discovered_mod_tree.bind("<Button-1>", self._on_discovery_tree_click, add="+")
        self.discovered_mod_tree.bind("<<TreeviewSelect>>", lambda e:self._sync_monitor_targets_from_discovery_selection(), add="+")
        for c,txt,w in (("game","ゲーム",180),("kind","種類",125),("mods","Mod数",70),("path","検出場所",650)):
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
        ttk.Label(discovery, text="Ctrl+クリックで複数場所を選択できます。［選択した場所のModを調査］を実行すると、その場所が未翻訳監視の対象にも登録されます。", foreground="#666", wraplength=330, justify="left").pack(anchor="w", pady=(4,0))

        search = ttk.LabelFrame(left, text="判定済みModを検索", padding=6); search.pack(fill="x", pady=(0,6))
        ttk.Label(search, text="Mod名").grid(row=0, column=0, sticky="w")
        search_entry = ttk.Entry(search, textvariable=self.mod_status_search_var, width=28)
        search_entry.grid(row=0, column=1, sticky="ew", padx=(6,6))
        search_entry.bind("<Return>", lambda e:self.search_mod_status())
        search_entry.bind("<KeyRelease>", lambda e:self.search_mod_status(live=True))
        ttk.Button(search, text="検索", command=self.search_mod_status).grid(row=0, column=2)
        ttk.Button(search, text="解除", command=self.clear_mod_status_search).grid(row=0, column=3, padx=(6,0))
        ttk.Label(search, textvariable=self.mod_status_search_result_var, foreground="#555", wraplength=300, justify="left").grid(row=1, column=0, columnspan=4, sticky="w", pady=(6,0))
        search.columnconfigure(1, weight=1)

        # 翻訳状況タブから探索専用LLMをそのまま変更・適用できる。
        moncfg = ttk.LabelFrame(left, text="探索用LLM設定", padding=6); moncfg.pack(fill="x", pady=(0,6))
        ttk.Label(moncfg, text="プロバイダ").grid(row=0,column=0,sticky="w")
        cmb=ttk.Combobox(moncfg,textvariable=self.monitor_provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=12)
        cmb.grid(row=0,column=1,padx=(5,8),sticky="ew"); cmb.bind("<<ComboboxSelected>>",lambda e:self.on_monitor_provider_change())
        ttk.Label(moncfg,text="URL").grid(row=1,column=0,sticky="w", pady=(6,0))
        ttk.Entry(moncfg,textvariable=self.monitor_url_var,width=26).grid(row=1,column=1,columnspan=2,sticky="ew",padx=(5,8), pady=(6,0))
        ttk.Label(moncfg,text="モデル").grid(row=2,column=0,sticky="w", pady=(6,0))
        self.status_monitor_model_combo=ttk.Combobox(moncfg,textvariable=self.monitor_model_var,state="normal",width=24)
        self.status_monitor_model_combo.grid(row=2,column=1,columnspan=2,sticky="ew",padx=(5,8), pady=(6,0))
        btnrow = ttk.Frame(moncfg); btnrow.grid(row=3,column=0,columnspan=3,sticky="ew", pady=(8,0))
        ttk.Button(btnrow,text="モデル一覧を再読込",command=self.refresh_monitor_models).pack(side="left")
        ttk.Button(btnrow,text="探索設定を適用",command=self.apply_monitor_settings).pack(side="left", padx=(6,0))
        moncfg.columnconfigure(1,weight=1); moncfg.columnconfigure(2,weight=1)
        ttk.Label(moncfg,text="再読込はモデル一覧の取得だけです。変更を確定するには［探索設定を適用］を押してください。小型3B〜8B級を推奨。",foreground="#a35a00",wraplength=320,justify="left").grid(row=4,column=0,columnspan=3,sticky="w",pady=(6,0))

        info = ttk.LabelFrame(left, text="判定内容", padding=6); info.pack(fill="x", pady=(0,6))
        ttk.Label(info,text="元Modと別日本語化Modを確認し、完全翻訳・欠落を判定します。調査だけでは自動翻訳しません。行を選ぶと右下に詳細を表示します。",justify="left",wraplength=320).pack(anchor="w")

        guide = ttk.LabelFrame(left, text="選択と操作", padding=6); guide.pack(fill="both", expand=True)
        ttk.Label(guide, text="小さく：Ctrlキーを押しながら複数選択できます。\n\n一覧では、選択したModだけの再調査、翻訳、除外翻訳、翻訳キュー追加、中国語基準キュー追加、上書きができます。", foreground="#666", justify="left", wraplength=320).pack(anchor="w")

        content = ttk.Panedwindow(right, orient="vertical"); content.pack(fill="x", expand=False)
        tree_frame=ttk.Frame(content); detail_frame=ttk.Frame(content)
        content.add(tree_frame, weight=6); content.add(detail_frame, weight=2)
        cols=("status","mod","gaps","chinese","jpmod","jpmod_gaps")
        self.mod_status_tree=ttk.Treeview(tree_frame, columns=cols, show="headings", height=16, selectmode="extended")
        self._enable_ctrl_multiselect(self.mod_status_tree)
        # v0.11.2: 翻訳状況一覧は列幅を固定し、表示領域に合わせて潰さない。
        # 長いMod名・日本語化Mod名は下部の横スクロールバーで確認する。
        for c,txt,w in (("status","状態",165),("mod","Mod",430),("gaps","欠損",80),("chinese","中国語",90),("jpmod","日本語化Mod",430),("jpmod_gaps","日本語化Mod欠損",150)):
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
        self._enable_tree_sort(self.mod_status_tree)

        detail = ttk.LabelFrame(detail_frame, text="選択項目の詳細", padding=6); detail.pack(fill="both",expand=True,pady=(4,0))
        self.mod_status_detail = tk.Text(detail, height=7, wrap="word", relief="flat", background=self.cget("background"))
        self.mod_status_detail.pack(fill="both", expand=True)
        self.mod_status_detail.insert("1.0", "一覧からModを選択すると、ここに調査結果・日本語化Mod・上書き先・場所を段落で表示します。")
        self.mod_status_detail.configure(state="disabled")

        bottom=ttk.Frame(right); bottom.pack(fill="x", pady=(4,0))
        bottom1=ttk.Frame(bottom); bottom1.pack(fill="x")
        bottom2=ttk.Frame(bottom); bottom2.pack(fill="x", pady=(4,0))
        ttk.Button(bottom1,text="選択Modだけ再調査",command=self.research_selected_status_mods).pack(side="left")
        ttk.Button(bottom1,text="通常翻訳キューへ追加",command=lambda:self.queue_selected_mod_from_status(start_now=False)).pack(side="left",padx=(6,0))
        self.status_chinese_queue_btn = ttk.Button(bottom1,text="中国語基準キューへ追加",command=self.queue_selected_mods_to_chinese_basis,state="disabled")
        self.status_chinese_queue_btn.pack(side="left",padx=(6,0))
        ttk.Button(bottom1,text="選択Modを除外して通常翻訳キューへ追加",command=self.queue_all_except_selected_mods).pack(side="left",padx=(6,0))
        ttk.Button(bottom2,text="選択Modを除外して中国語基準キューへ追加",command=self.queue_all_except_selected_mods_chinese).pack(side="left")

        ttk.Button(bottom2,text="QA / 比較編集へ",command=lambda:self._send_pair_to_qa_or_diff("status","review")).pack(side="left")
        ttk.Button(bottom2,text="差分調査へ",command=lambda:self._send_pair_to_qa_or_diff("status","diff")).pack(side="left",padx=(6,0))
        self.status_overwrite_btn = ttk.Button(bottom2,text="完成した日本語化をModへ上書き",command=self.overwrite_selected_status_mod)
        self.status_overwrite_btn.pack(side="left",padx=(6,0))
        ttk.Separator(bottom2,orient="vertical").pack(side="left",fill="y",padx=8)
        ttk.Button(bottom2,text="結果を消去",command=self.clear_mod_status_results).pack(side="left")
        ttk.Button(bottom2,text="キャッシュ再読込",command=self._restore_cached_mod_status).pack(side="left",padx=(6,0))
        ttk.Button(bottom2,text="CSV保存",command=self.export_mod_status_csv).pack(side="left",padx=(6,0))

    def _mod_status_matches_query(self, result, query):
        q = (query or "").strip().casefold()
        if not q:
            return True
        fields = [
            result.get("mod", ""),
            result.get("status", ""),
            result.get("external_translation_mod", ""),
            result.get("message", ""),
            result.get("path", ""),
        ]
        return any(q in str(v).casefold() for v in fields)

    def _populate_mod_status_tree(self, results=None):
        if not hasattr(self, "mod_status_tree"):
            return
        query = self.mod_status_search_var.get().strip() if hasattr(self, "mod_status_search_var") else ""
        source = list(self.mod_research_results if results is None else results)
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
                r.get("status", ""), r.get("mod", ""), r.get("gap_count", 0),
                "あり" if r.get("simp_chinese_files", 0) else "なし",
                r.get("external_translation_mod", ""),
                r.get("external_translation_gap_count", 0) if r.get("external_translation_mod") else ""
            ))
        if query:
            self.mod_status_search_result_var.set(f"{len(visible)}件 / 全{len(source)}件")
        else:
            self.mod_status_search_result_var.set("")
        if not visible and query:
            self._set_mod_status_detail_text(f"『{query}』に一致する判定済みModはありません。")

    def search_mod_status(self, live=False):
        query = self.mod_status_search_var.get().strip()
        self._populate_mod_status_tree()
        if not query:
            return
        matches = [r for r in self.mod_research_results if self._mod_status_matches_query(r, query)]
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
            self.mod_status_search_result_var.set(f"『{query}』は見つかりませんでした")

    def clear_mod_status_search(self):
        self.mod_status_search_var.set("")
        self.mod_status_search_result_var.set("")
        self._populate_mod_status_tree()
        self._set_mod_status_detail_text("一覧からModを選択すると、ここに調査結果・日本語化Mod・上書き先・場所を段落で表示します。")

    def _set_mod_status_detail_text(self, text):
        if not hasattr(self, "mod_status_detail"):
            return
        self.mod_status_detail.configure(state="normal")
        self.mod_status_detail.delete("1.0", "end")
        self.mod_status_detail.insert("1.0", text)
        self.mod_status_detail.configure(state="disabled")

    def _on_mod_status_selection_changed(self, _event=None):
        selected = self._selected_mod_status_results() if hasattr(self, "mod_status_tree") else []
        if not selected:
            self._set_mod_status_detail_text("一覧からModを選択すると、ここに調査結果・日本語化Mod・上書き先・場所を段落で表示します。")
            if hasattr(self, "status_overwrite_btn"):
                self.status_overwrite_btn.config(text="完成した日本語化をModへ上書き")
            if hasattr(self, "status_chinese_queue_btn"):
                self.status_chinese_queue_btn.config(state="disabled")
            return
        r = selected[0]
        mod_name = r.get("mod", "Mod")
        jpmod = r.get("external_translation_mod", "")
        jp_path = r.get("external_translation_path", "")
        zh_count = r.get("simp_chinese_files", 0)
        lines = [f"Mod: {mod_name}", f"状態: {r.get('status','')}　欠損: {r.get('gap_count',0)}件", f"英語キー: {r.get('english_keys',0)}　簡体字中国語キー: {r.get('simp_chinese_keys',0)}　日本語キー: {r.get('japanese_keys',0)}", f"言語固有キー: 英語のみ {r.get('english_only_keys',0)} / 中国語のみ {r.get('chinese_only_keys',0)}", f"簡体字中国語: {'あり（' + str(zh_count) + 'ファイル）' if zh_count else 'なし'}", "", r.get("message", "")]
        if hasattr(self, "status_chinese_queue_btn"):
            # 複数選択時は、中国語localizationを持つModが1件でもあれば利用可。
            has_zh = any(x.get("simp_chinese_files", 0) for x in selected)
            self.status_chinese_queue_btn.config(state="normal" if has_zh else "disabled")
        if jpmod:
            lines += ["", f"日本語化Mod: {jpmod}", f"日本語化Mod側の欠損: {r.get('external_translation_gap_count',0)}件", f"上書き先: 日本語化Mod『{jpmod}』", f"日本語化Mod場所: {jp_path}"]
            if hasattr(self, "status_overwrite_btn"):
                label = f"日本語化Mod『{jpmod}』へ差分上書き"
                if len(label) > 34:
                    label = "日本語化Modへ差分上書き"
                self.status_overwrite_btn.config(text=label)
        else:
            lines += ["", "上書き先: 元Mod内の日本語localization"]
            if hasattr(self, "status_overwrite_btn"):
                self.status_overwrite_btn.config(text="完成した日本語化を元Modへ上書き")
        lines += ["", f"元Mod場所: {r.get('path','')}"]
        self._set_mod_status_detail_text("\n".join(lines))

    def pick_monitor_path(self):
        p=filedialog.askdirectory(title="調査するMod、localization、またはMod親フォルダを選択")
        if p: self.monitor_path_var.set(p)

    def discover_mod_locations(self):
        """Find Steam Workshop / Paradox user-mod folders without blocking the GUI.

        Previously discovered Steam library roots are reused, and the core also performs
        a shallow scan of other mounted drives/volumes so installations on another SSD
        or external drive can be found without a whole-disk recursive search.
        """
        if not hasattr(self, "discovered_mod_tree"):
            return
        self.mod_discovery_status_var.set("自動検出中…（別ドライブ・外付けSSDも確認）")
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
            self.mod_discovery_status_var.set(f"{len(items)}か所を選択中 / 監視対象へ反映済み")

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
        if rows:
            self.mod_discovery_status_var.set(f"{len(rows)}か所を選択中 / 監視対象へ反映済み")
        return rows

    def _selected_discovered_locations(self):
        if not hasattr(self, "discovered_mod_tree"):
            return []
        sel = self.discovered_mod_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "自動検出されたゲーム/Mod場所を選択してください。Ctrlキーを押しながらクリックすると複数選択できます。")
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
                label += f" ほか{len(labels)-3}か所"
            self.monitor_target_summary_var.set(f"監視対象: {len(paths)}か所 — {label}")
        else:
            self.monitor_target_summary_var.set("監視対象: 翻訳状況タブでゲーム / Mod場所を選択してください")

    def use_selected_discovered_location(self):
        # 旧UI/内部呼び出しとの互換。選択場所を監視対象として登録する。
        rows = self._selected_discovered_locations()
        if not rows:
            return
        self._set_monitor_targets(rows)
        self.mod_discovery_status_var.set(f"監視対象に{len(self.monitor_target_paths)}か所登録")

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
                record_error("Mod場所調査", exc, str(path)); roots=[]
            for root in roots:
                rp=Path(root)
                if rp not in all_roots:
                    all_roots.append(rp)
        return all_roots, missing

    def research_selected_discovered_location(self):
        rows = self._selected_discovered_locations()
        if not rows:
            return
        all_roots, missing = self._collect_mod_roots_from_location_rows(rows)
        if not all_roots:
            counts = ", ".join(f"{r.get('game','')} {r.get('kind','')}: {r.get('mod_count',0)}" for r in rows)
            messagebox.showinfo(APP_NAME, "選択した場所からlocalizationを持つModを確認できませんでした。\n\n" + counts)
            self.mod_discovery_status_var.set("調査対象のlocalizationを確認できませんでした")
            return
        self.mod_discovery_status_var.set(f"{len(rows)}か所 / {len(all_roots)} Modを調査中")
        self._start_mod_research(all_roots, replace=True, translation_pool=all_roots)
        if missing:
            record_error("Mod場所一括調査", detail="存在しない検出場所: " + " | ".join(missing))

    def research_monitor_targets(self):
        paths=[Path(p) for p in self.monitor_target_paths if Path(p).exists()]
        if not paths:
            messagebox.showinfo(APP_NAME, "監視対象がありません。［翻訳状況］タブでゲーム / Mod場所を1件以上選択してください。")
            return
        rows=[]
        for p in paths:
            matched=next((r for r in self.detected_mod_locations if str(Path(r.get("path", "")))==str(p)), None)
            rows.append(matched or {"path":str(p),"game":"","kind":""})
        roots,_=self._collect_mod_roots_from_location_rows(rows)
        if not roots:
            messagebox.showinfo(APP_NAME, "監視対象からlocalizationを持つModを確認できませんでした。")
            return
        self._start_mod_research(roots, replace=True, translation_pool=roots)
        self.monitor_status_var.set(f"再調査中 — {len(roots)} Mod")

    def on_monitor_provider_change(self):
        provider=self.monitor_provider_var.get()
        self.monitor_url_var.set(core.default_url_for_provider(provider))
        self.monitor_model_var.set("")
        self.monitor_connection_var.set("監視用LLM: 未確認")
        self._save_llm_preferences()
        self.refresh_monitor_models()

    def refresh_monitor_models(self):
        provider=self.monitor_provider_var.get()
        url=self.monitor_url_var.get().strip() or core.default_url_for_provider(provider)
        api_key=self.monitor_api_key_var.get().strip()
        self.monitor_connection_var.set(f"{provider}: 接続確認中…")
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
                },
                "monitor_llm": {
                    "provider": self.monitor_provider_var.get(),
                    "url": self.monitor_url_var.get().strip(),
                    "model": self.monitor_model_var.get().strip(),
                },
                "window_close": {
                    "action": {"毎回確認":"confirm","最小化":"minimize","終了":"quit"}.get(self.close_action_var.get(), "confirm"),
                },
            })
            core.save_json(APP_PREFS_PATH, data)
            self.app_preferences = data
        except Exception as e:
            record_error("LLM設定保存", e)

    def apply_monitor_settings(self, silent=False):
        """Apply monitor/research LLM settings. Current in-flight request is not interrupted."""
        provider=self.monitor_provider_var.get()
        url=self.monitor_url_var.get().strip() or core.default_url_for_provider(provider)
        model=self.monitor_model_var.get().strip()
        self.monitor_url_var.set(url)
        if not model:
            if not silent:
                messagebox.showinfo(APP_NAME,"探索用LLMのモデルを選択してください。")
            return False
        self._save_llm_preferences()
        self.monitor_connection_var.set(f"監視用LLM設定: {provider} / {model}")
        self.monitor_llm_detail_var.set(f"次の探索LLM呼び出しから適用: {provider} / {model}")
        if not silent:
            messagebox.showinfo(APP_NAME,"探索用LLM設定を適用しました。\n\n現在応答待ちの呼び出しはそのまま完了し、次の探索LLM呼び出しから新設定を使用します。")
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
                record_error("翻訳設定全体適用", e)
                if not silent: messagebox.showerror(APP_NAME,f"設定の適用に失敗しました。\n{e}")
                return False
        if not silent:
            messagebox.showinfo(APP_NAME,
                "現在の翻訳設定を適用しました。\n\nQAのAI校正と差分翻訳は、この画面で現在選択されているプロバイダ・URL・モデル・用語集を使用します。"
                + ("\n実行中の通常翻訳は次のバッチから切り替わります。" if self.controller and self.worker and self.worker.is_alive() else ""))
        return True

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
            messagebox.showinfo(APP_NAME,"監視対象がありません。［翻訳状況］タブでゲーム / Mod場所を1件以上選択してください。")
            return
        self.monitor_stop_event.clear(); self.monitor_force_event.set(); self.monitor_snapshot={}
        self.monitor_toggle_btn.config(text="常時監視を停止")
        self.monitor_status_var.set(f"● 常時監視中 — {len(roots)}か所 / 初回確認中…")
        self._set_monitor_scan_status("● 未翻訳Mod監視中", f"{len(roots)}か所の変更されたYAMLを確認しています")
        self.monitor_thread=threading.Thread(target=self._monitor_worker,daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self):
        if not (self.monitor_thread and self.monitor_thread.is_alive()):
            self.monitor_status_var.set("○ 監視停止中")
            self.monitor_toggle_btn.config(text="常時監視を開始")
            return
        self.monitor_stop_event.set(); self.monitor_force_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.monitor_status_var.set("監視停止処理中…")
        self.monitor_toggle_btn.config(text="停止処理中…", state="disabled")

    def monitor_scan_now(self):
        # 旧内部呼び出しとの互換。現在は「再調査」に統合。
        self.research_monitor_targets()

    def _refine_candidates_with_monitor_llm(self, candidates):
        ambiguous=[(i,c) for i,c in enumerate(candidates) if c.get("needs_llm")]
        if not (self.monitor_use_llm_var.get() and ambiguous):
            return candidates
        provider,url,model,api_key=self._monitor_llm_config()
        if not model:
            self.events.put(("monitor_log","監視専用LLMが未選択のため曖昧候補の精査をスキップしました。"))
            return candidates
        self.monitor_llm_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("monitor_progress",p)))
        try:
            decisions=core.classify_monitor_candidates(
                provider,url,model,[c for _,c in ambiguous],self.monitor_llm_controller,
                api_key,batch_size=40)
            keep=set()
            for pos,(original_idx,c) in enumerate(ambiguous):
                if decisions.get(pos,True):
                    c["confidence"]="LLM確認"; keep.add(original_idx)
            return [c for i,c in enumerate(candidates) if not c.get("needs_llm") or i in keep]
        finally:
            self.monitor_llm_controller=None

    def _monitor_worker(self, one_shot=False):
        roots=self._current_monitor_roots()
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
                    self.events.put(("monitor_status",f"● 常時監視中 — 解析中… ({len(roots)}か所)"))
                    candidates=[]
                    for root in roots:
                        try:
                            candidates.extend(core.scan_translation_gaps(root))
                        except Exception as exc:
                            self.events.put(("monitor_log",f"{root}: 解析をスキップ: {exc}"))
                    try:
                        candidates=self._refine_candidates_with_monitor_llm(candidates)
                    except core.StopRequested:
                        if self.monitor_stop_event.is_set(): break
                    except Exception as e:
                        self.events.put(("monitor_log",f"軽量LLM精査をスキップ: {e}"))
                    self.monitor_candidates=candidates; self.monitor_snapshot=combined_stats
                    self.events.put(("monitor_results",candidates))
                    first=False
                if one_shot:
                    break
                interval=max(3,int(self.monitor_interval_var.get() or 15))
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
        messagebox.showerror(APP_NAME, f"予期しないエラーが発生しました。\n\n{exc_value}\n\nエラーログに記録しました。")

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
            LOG_ROOT.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            target = LOG_ROOT / f"ParadoxLocalizationTranslator_diagnostics_{stamp}.zip"
            info = {
                "app": APP_NAME, "version": APP_VERSION,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "platform": platform.platform(), "python": sys.version,
                "data_root": str(DATA_ROOT),
                "provider": self.provider_var.get(), "model": self.model_var.get(),
                "monitor_provider": self.monitor_provider_var.get(), "monitor_model": self.monitor_model_var.get(),
            }
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr("diagnostics.json", json.dumps(info, ensure_ascii=False, indent=2))
                for lp in sorted(LOG_ROOT.glob("*.log")):
                    zf.write(lp, f"logs/{lp.name}")
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
                if RESUME_HISTORY_PATH.exists():
                    try: zf.write(RESUME_HISTORY_PATH,"logs/resume_history.jsonl")
                    except Exception: pass
            messagebox.showinfo(APP_NAME, f"診断ログを収集しました。\n\n{target}\n\nAPIキーや翻訳本文は収集しません。")
        except Exception as e:
            record_error("診断ログ収集", e)
            messagebox.showerror(APP_NAME, f"診断ログの収集に失敗しました。\n{e}")

    def _mod_source_signature(self, mod_root: Path) -> str:
        """Cheap signature used to decide whether a cached status result is still current."""
        try:
            loc = core.mod_localization_root(Path(mod_root))
            if not loc:
                return "missing"
            h = hashlib.sha256()
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
            return "error"

    def _cached_status_for_mod(self, mod_root: Path, signature: str):
        key = str(Path(mod_root).expanduser().resolve())
        with self.mod_status_cache_lock:
            if self.mod_status_cache.get("version") != MOD_STATUS_CACHE_VERSION:
                return None
            row = (self.mod_status_cache.get("items") or {}).get(key)
        if row and row.get("signature") == signature and isinstance(row.get("result"), dict):
            result = dict(row["result"])
            result["cached"] = True
            return result
        return None

    def _cache_mod_status_result(self, mod_root: Path, signature: str, result: dict):
        key = str(Path(mod_root).expanduser().resolve())
        summary = {k:v for k,v in result.items() if k != "candidates"}
        summary["path"] = str(result.get("path") or mod_root)
        row = {"signature": signature, "checked_at": datetime.now().isoformat(timespec="seconds"), "result": summary}
        with self.mod_status_cache_lock:
            self.mod_status_cache.setdefault("items", {})[key] = row
            self.mod_status_cache["version"] = MOD_STATUS_CACHE_VERSION
            self.mod_status_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_STATUS_CACHE_PATH, self.mod_status_cache)

    def _restore_cached_mod_status(self):
        try:
            data = core.load_json(MOD_STATUS_CACHE_PATH, {"version": MOD_STATUS_CACHE_VERSION, "items": {}})
            if not isinstance(data, dict) or data.get("version") != MOD_STATUS_CACHE_VERSION:
                self.mod_status_cache = {"version": MOD_STATUS_CACHE_VERSION, "items": {}}
                return
            items = data.get("items", {})
            rows = []
            for row in items.values():
                result = row.get("result") if isinstance(row, dict) else None
                if isinstance(result, dict) and result.get("path"):
                    r = dict(result); r["cached"] = True; rows.append(r)
            rows.sort(key=lambda r: str(r.get("mod", "")).lower())
            if not hasattr(self, "mod_status_tree"):
                return
            self.mod_research_results = rows
            self._populate_mod_status_tree()
            counts={}
            for r in rows: counts[r.get("status","")] = counts.get(r.get("status",""),0)+1
            summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
            self.mod_status_summary_var.set(f"キャッシュ復元: {len(rows)}件" + (f"　{summary}" if summary else ""))
        except Exception as e:
            record_error("翻訳状況キャッシュ復元", e)

    def research_selected_mod_background(self):
        # 旧UI互換。調査機能は翻訳状況タブの選択場所調査へ統合済み。
        self.research_monitor_targets()

    def research_all_mods_background(self):
        # 旧UI互換。調査機能は翻訳状況タブの選択場所調査へ統合済み。
        self.research_monitor_targets()

    def _start_mod_research(self, roots, replace=True, translation_pool=None):
        if self.mod_research_thread and self.mod_research_thread.is_alive():
            messagebox.showinfo(APP_NAME,"すでに調査中です。")
            return
        self.mod_research_stop_event.clear()
        self.mod_research_stop_btn.config(state="normal")
        self.mod_status_summary_var.set(f"バックグラウンド調査中: 0/{len(roots)}")
        self._set_monitor_scan_status(f"● 未翻訳Mod探索開始 — 0/{len(roots)}", "Mod一覧と別日本語化Modを確認しています")
        if replace:
            self.mod_research_results=[]
            self.events.put(("mod_status_results",[]))
        self.mod_research_thread=threading.Thread(target=self._mod_research_worker,args=(roots,translation_pool),daemon=True)
        self.mod_research_thread.start()

    def stop_mod_research(self):
        self.mod_research_stop_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.mod_status_summary_var.set("調査停止要求済み…")

    def _mod_research_worker(self, roots, translation_pool=None):
        try:
            total=len(roots)
            results=[]
            check_external = bool(self.monitor_check_translation_mods_var.get())
            pool_roots = list(translation_pool or roots)
            translation_index = core.build_translation_mod_index(pool_roots) if check_external else None
            pool_signature = ""
            if check_external:
                h = hashlib.sha256()
                for root in sorted((Path(r) for r in pool_roots), key=lambda x: str(x)):
                    h.update(str(root).encode("utf-8", "ignore"))
                    h.update(self._mod_source_signature(root).encode())
                pool_signature = h.hexdigest()
            for i,mod_root in enumerate(roots,1):
                if self.mod_research_stop_event.is_set(): break
                mod_name = core.detect_mod_name(Path(mod_root))
                self.events.put(("mod_research_progress",(i,total,mod_name)))
                signature = self._mod_source_signature(Path(mod_root))
                if pool_signature:
                    signature = hashlib.sha256((signature + ":" + pool_signature).encode()).hexdigest()
                result = self._cached_status_for_mod(Path(mod_root), signature)
                if result is None:
                    result=core.analyze_mod_translation_status(mod_root, translation_index=translation_index)
                    candidates=result.get("candidates",[])
                    try:
                        refined=self._refine_candidates_with_monitor_llm(candidates)
                        result["candidates"]=refined
                        result["gap_count"]=len(refined)
                        result["gap_origin_counts"]=core.gap_origin_counts(refined)
                        result["gap_reason"]=core.gap_reason_text(refined)
                        # For a separate Japanese translation mod, refined candidates are that mod's missing/foreign entries.
                        if result.get("external_translation_mod") and not result.get("external_translation_complete"):
                            result["external_translation_gaps"] = refined
                            result["external_translation_gap_count"] = len(refined)
                            result["gap_count"] = len(refined)
                            if refined:
                                result["status"]="別Mod翻訳・欠損"
                                result["message"]=f"{result['mod']}には日本語化Mod『{result['external_translation_mod']}』がありますが、翻訳に欠損があります（{len(refined)}件）。 {core.gap_reason_text(refined)}。"
                            else:
                                result["status"]="別Modで完全翻訳"
                                result["external_translation_complete"] = True
                                result["message"]=f"{result['mod']}には日本語化Mod『{result['external_translation_mod']}』があり、完全な日本語化を確認できました。"
                        elif result.get("japanese_files",0)==0 or result.get("japanese_keys",0)==0:
                            if result.get("external_translation_complete"):
                                result["status"]="別Modで完全翻訳"
                            elif result.get("external_translation_mod"):
                                result["status"]="別Mod翻訳・欠損"
                            else:
                                result["status"]="翻訳なし"
                                result["message"]=f"{result['mod']}というModは日本語翻訳がありません。日本語化Modも確認できませんでした。"
                        elif refined:
                            result["status"]="欠損あり"
                            result["gap_count"] = len(refined)
                            result["message"]=f"{result['mod']}のModに翻訳の欠損箇所があります（{len(refined)}件）。 {core.gap_reason_text(refined)}。"
                        elif not result.get("external_translation_mod"):
                            result["status"]="翻訳あり"
                            result["gap_count"] = 0
                            result["message"]=f"{result['mod']}のModは日本語翻訳が確認できました。"
                    except core.StopRequested:
                        if self.mod_research_stop_event.is_set(): break
                    except Exception as e:
                        record_error("Mod翻訳状況 LLM精査", e, str(mod_root))
                        self.events.put(("monitor_log",f"{result.get('mod','Mod')} のLLM精査をスキップ: {e}"))
                    self._cache_mod_status_result(Path(mod_root), signature, result)
                else:
                    self.events.put(("monitor_log", f"{result.get('mod', Path(mod_root).name)}: 前回調査結果をキャッシュから再利用"))
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
            messagebox.showinfo(APP_NAME, "翻訳状況の一覧からModを1つ選択してください。")
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
            messagebox.showinfo(APP_NAME,"翻訳状況の一覧から再調査するModを選択してください。Ctrlキーを押しながらクリックすると複数選択できます。")
            return
        if self.mod_research_thread and self.mod_research_thread.is_alive():
            messagebox.showinfo(APP_NAME,"すでに調査中です。")
            return
        roots=[]; selected_paths=set()
        for result in selected:
            root=Path(result.get("path", ""))
            if root.exists() and core.mod_localization_root(root):
                roots.append(root)
                try:selected_paths.add(str(root.resolve()))
                except Exception:selected_paths.add(str(root))
        if not roots:
            messagebox.showinfo(APP_NAME,"選択した項目から調査可能なModフォルダを確認できませんでした。")
            return
        kept=[]
        for r in self.mod_research_results:
            try:key=str(Path(r.get("path","")).resolve())
            except Exception:key=str(Path(r.get("path","")))
            if key not in selected_paths:
                kept.append(r)
        self.mod_research_results=kept
        with self.mod_status_cache_lock:
            items=self.mod_status_cache.setdefault("items",{})
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
        self._start_mod_research(roots, replace=False, translation_pool=pool or roots)

    def queue_selected_mods_to_chinese_basis(self):
        """翻訳状況で選択したうち、簡体字中国語localizationを持つModだけ中国語基準キューへ追加する。"""
        selected=self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME,"翻訳状況の一覧からModを選択してください。")
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
                item["external_gap_keys"]=[c.get("key") for c in result.get("external_translation_gaps",[]) if c.get("key")]
                added+=1
        self._refresh_chinese_queue_tree()
        if added:
            try:self.notebook.select(self.tab_chinese)
            except Exception:pass
            self.chinese_status_var.set(f"翻訳状況から中国語localizationを持つ {added} Modをキューへ追加しました。")
        if skipped:
            self._append_chinese_log("中国語なしのため除外: "+"、".join(skipped[:10])+(f" ほか{len(skipped)-10}件" if len(skipped)>10 else ""))
        if not added:
            messagebox.showinfo(APP_NAME,"選択したModには簡体字中国語（l_simp_chinese）が見つかりませんでした。")

    def queue_selected_mod_from_status(self, start_now=False):
        """翻訳状況で選択したModをすべて通常翻訳キューへ追加する。"""
        selected = self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME, "翻訳状況の一覧からModを1件以上選択してください。")
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
                messagebox.showinfo(APP_NAME, f"{len(added)} Modをキュー末尾へ追加しました。現在の翻訳完了後に続けて処理します。")
            else:
                self.start_queue()
        elif added:
            msg=f"選択した {len(added)} Modを通常翻訳キューへ追加しました。"
            if skipped: msg += f"\nlocalizationを確認できずスキップ: {len(skipped)}件"
            messagebox.showinfo(APP_NAME,msg)
        elif skipped:
            messagebox.showinfo(APP_NAME,"選択したModから調査可能なlocalizationフォルダを確認できませんでした。")
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
        self._append_queue(loc)
        item = self.queue_items[-1]
        item["mod_root"] = str(mod_root)
        item["mod_localization"] = str(loc)
        item["mod_name"] = result.get("mod", mod_root.name)
        item["direct_from_status"] = True
        item["external_translation_mod"] = result.get("external_translation_mod", "")
        item["external_translation_path"] = result.get("external_translation_path", "")
        item["external_translation_localization"] = result.get("external_translation_localization", "")
        item["external_gap_keys"] = [c.get("key") for c in result.get("external_translation_gaps", []) if c.get("key")]
        return item

    def _status_results_except_selected(self):
        if not self.mod_research_results:
            messagebox.showinfo(APP_NAME, "先にModの翻訳状況を調査してください。")
            return None, None
        selected=self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME, "除外するModを1つ以上選択してください。\nCtrlキーを押しながらクリックすると複数選択できます。")
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
            messagebox.showinfo(APP_NAME,"選択したModを除外すると、通常翻訳キューへ追加できるModは残っていません。")
            return
        added=sum(1 for r in targets if self._queue_mod_status_result(r) is not None)
        self._refresh_queue_tree(); self.save_session(active=False)
        if added:
            try:self.notebook.select(self.tab_translate)
            except Exception:pass
        messagebox.showinfo(APP_NAME, f"選択した {len(selected)} Modを除外し、{added} Modを通常翻訳キューへ追加しました。\n翻訳済みで対象外: {skipped_complete}件\nlocalizationなし: {skipped_invalid}件")

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
                item["external_gap_keys"]=[c.get("key") for c in result.get("external_translation_gaps",[]) if c.get("key")]
                added += 1
        self._refresh_chinese_queue_tree()
        if added:
            try:self.notebook.select(self.tab_chinese)
            except Exception:pass
        messagebox.showinfo(APP_NAME, f"選択した {len(selected)} Modを除外し、中国語localizationがある {added} Modを中国語基準キューへ追加しました。\n中国語なし: {no_chinese}件\nlocalizationなし: {invalid}件")

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
        if inp.is_dir() and inp.name.lower() == "localization":
            return inp, inp
        if inp.is_dir() and (inp / "localization").is_dir():
            return inp / "localization", inp
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
        items = self._selected_queue_items_for_kind(queue_kind)
        if not items:
            label = "中国語基準" if queue_kind == "chinese" else "通常"
            messagebox.showinfo(APP_NAME, f"{label}翻訳キューから項目を選択してください。")
            return
        added = 0
        skipped = 0
        details = []
        for item in items:
            loc, mod_root = self._infer_mod_target_for_item(item)
            if not loc or not Path(loc).is_dir():
                skipped += 1; details.append(f"{item.get('mod_name','項目')}: localizationを特定できません")
                continue
            mod_name = item.get("mod_name") or (Path(mod_root).name if mod_root else Path(loc).name)
            source_lang = "english" if queue_kind == "chinese" else "simp_chinese"
            target_kind = "normal" if queue_kind == "chinese" else "chinese"
            input_path = Path(loc)
            missing_keys = []
            if missing_only:
                preferred = "simp_chinese" if queue_kind == "chinese" else "english"
                gaps = core.scan_translation_gaps(Path(loc), preferred_source=preferred)
                origin = "english_only" if source_lang == "english" else "chinese_only"
                missing_keys = [g.get("key") for g in gaps if g.get("source_origin") == origin and g.get("key")]
                if not missing_keys:
                    skipped += 1; details.append(f"{mod_name}: {source_lang}固有の不足翻訳なし")
                    continue
                sparse = self._write_missing_source_subset(Path(loc), source_lang, missing_keys, mod_name)
                if not sparse:
                    skipped += 1; details.append(f"{mod_name}: 不足原文を作成できません")
                    continue
                input_path = sparse
            if target_kind == "chinese":
                new_item, msg = self._append_chinese_queue(input_path, mod_name + ("（不足分）" if missing_only else ""))
            else:
                before = len(self.queue_items)
                self._append_queue(input_path)
                new_item = self.queue_items[-1] if len(self.queue_items) > before else None
                msg = ""
            if not new_item:
                skipped += 1; details.append(f"{mod_name}: {msg or 'キュー追加できませんでした'}")
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
            target_label = "通常翻訳" if queue_kind == "chinese" else "中国語基準翻訳"
            mode = "不足している翻訳だけを" if missing_only else "選択項目を"
            text = f"{mode}{target_label}キューへ追加しました。\n追加: {added}件 / スキップ: {skipped}件"
        else:
            text = f"キューへ追加できる項目がありませんでした。\nスキップ: {skipped}件"
        if details:
            text += "\n\n" + "\n".join(details[:8])
        messagebox.showinfo(APP_NAME, text)

    def _merge_missing_only_output(self, item, target_loc: Path, target_root: Path, confirm=True, notify=True):
        """Merge sparse missing-only translation output without replacing unrelated Japanese text."""
        out_root = Path(item.get("output", ""))
        generated = self._generated_japanese_files(out_root)
        if not generated:
            return False, "不足分の完成済み日本語YAMLが見つかりません"
        translations = {}
        for fp in generated:
            try:
                lang, entries, _ = core.parse_localization_file(fp)
                if lang == "japanese":
                    translations.update(entries)
            except Exception:
                continue
        wanted = {k for k in item.get("missing_keys", []) if k}
        patch_values = {k: v for k, v in translations.items() if not wanted or k in wanted}
        if not patch_values:
            return False, "不足分の翻訳結果が見つかりません"
        target_loc = Path(target_loc); target_root = Path(target_root)
        patch_file = target_loc / "japanese" / "paradox_localization_translator_missing_l_japanese.yml"
        if confirm:
            if not messagebox.askyesno("不足翻訳の上書き", f"不足していた翻訳 {len(patch_values)}件だけを既存日本語本文へ追加します。\n\n対象: {target_root}\n\n既存の他キーは置き換えません。続行しますか？", icon="warning"):
                return False, "キャンセル"
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe = re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+','_', item.get("mod_name", "Mod")).strip('_')[:60] or "Mod"
        backup_root = BACKUP_ROOT / f"{stamp}_{safe}_不足分上書き"
        try:
            # Existing Japanese keys are updated in place. Truly absent keys are
            # collected in the dedicated patch file, so unrelated files are never replaced.
            existing_key_file = {}
            for fp in self._generated_japanese_files(target_loc):
                try:
                    _, entries, _ = core.parse_localization_file(fp)
                    for key in entries:
                        existing_key_file.setdefault(key, fp)
                except Exception:
                    continue
            backed = set(); updated = 0; added_values = {}
            for key, value in patch_values.items():
                target = existing_key_file.get(key)
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
                lines = ["l_japanese:"]
                for key in sorted(patch_entries):
                    lines.append(f' {key}: "{core.escape_localization_value(patch_entries[key])}"')
                patch_file.write_text("\ufeff" + "\n".join(lines) + "\n", encoding="utf-8")
            source_mod_root = Path(item.get("mod_root", ""))
            validation_text = "上書き後確認: 判定対象を特定できません"
            if source_mod_root.is_dir():
                if target_root.resolve() == source_mod_root.resolve():
                    post = core.analyze_mod_translation_status(source_mod_root)
                    validation_text = "上書き後確認: 欠損なし" if not post.get("gap_count") else f"⚠ 本文自体に欠落があります。\n{post.get('gap_reason') or core.gap_reason_text(post.get('candidates', []))}"
                else:
                    post = core.analyze_external_translation_coverage(source_mod_root, target_root)
                    validation_text = "上書き後確認: 欠損なし" if post.get("complete") else f"⚠ 本文自体に欠落があります。\n{post.get('gap_reason','翻訳不足があります')}"
            if notify:
                messagebox.showinfo(APP_NAME, f"不足していた翻訳だけを反映しました。\n\n既存キー更新: {updated}件\n新規キー追加: {len(added_values)}件\nバックアップ: {len(backed)}ファイル\n\n{validation_text}")
            return True, f"既存キー更新 {updated} / 新規キー追加 {len(added_values)} / {validation_text}"
        except Exception as exc:
            record_error("不足翻訳上書き", exc, str(target_root))
            if notify:
                messagebox.showerror(APP_NAME, f"不足翻訳の上書きに失敗しました。\n{exc}")
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
                if candidate.name.lower() == "localization":
                    root = candidate
                    break
            if not root.exists():
                continue
            try:
                result = core.analyze_source_language_gaps(root)
            except Exception:
                continue
            if result.get("has_gaps"):
                name=item.get("mod_name") or Path(item.get("input", "")).name or "項目"
                notices.append(f"{name}: {core.source_language_gap_reason_text(result)}")
        if not notices:
            return ""
        text = "⚠ 原文に欠落あり\n英語・簡体字中国語の原文を比較したところ、片方にのみ存在する翻訳対象キーがあります。\n"
        text += "\n".join(notices[:10])
        if len(notices) > 10:
            text += f"\n…ほか {len(notices)-10}件"
        return text

    def _generated_japanese_files(self, output_root: Path):
        files=[]
        if not output_root.exists():
            return files
        for p in sorted(output_root.rglob("*.yml")):
            try:
                head=core.read_localization_text(p).splitlines()[:5]
                lang=core.detect_source_lang(p,head)
            except Exception:
                lang=""
            if lang == "japanese" or "_l_japanese" in p.name.lower():
                files.append(p)
        return files

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
        item["status"]="上書き済み"

    def _perform_external_gap_overwrite(self, item, confirm=True, notify=True):
        """Write only translated gap keys into a detected external Japanese mod."""
        ext_root = Path(item.get("external_translation_path", ""))
        ext_loc = Path(item.get("external_translation_localization", ""))
        gap_keys = {k for k in item.get("external_gap_keys", []) if k}
        out_root = Path(item.get("output", ""))
        if not ext_root.is_dir() or not ext_loc.is_dir():
            return False,"日本語化Modの場所を特定できません"
        if not gap_keys:
            return False,"日本語化Modへ反映する差分情報がありません"
        generated = self._generated_japanese_files(out_root)
        translations = {}
        for fp in generated:
            try:
                lang, entries, _ = core.parse_localization_file(fp)
                if lang == "japanese":
                    translations.update(entries)
            except Exception:
                continue
        patch_values = {k: translations[k] for k in gap_keys if k in translations}
        if not patch_values:
            return False,"完成済み出力に差分訳が見つかりません"

        ext_name = item.get("external_translation_mod") or ext_root.name
        src_name = item.get("mod_name") or Path(item.get("mod_root", "")).name
        if confirm:
            warning=(
                f"⚠ 別の日本語化Modへ不足分だけを書き込みます。\n\n"
                f"元Mod: {src_name}\n日本語化Mod: {ext_name}\n対象: {ext_root}\n"
                f"差分キー: {len(patch_values)}件\n\n"
                "既存の日本語訳は維持し、欠損・未翻訳と判定されたキーだけ更新/追加します。\n"
                "変更対象ファイルは実行前にバックアップします。\n続行しますか？")
            if not messagebox.askyesno("警告 — 日本語化Modへ差分上書き", warning, icon="warning"):
                return False,"キャンセル"
            if not messagebox.askyesno("最終確認", "日本語化Modへ不足分だけを書き込みます。本当に続行しますか？", icon="warning"):
                return False,"キャンセル"

        existing_key_file = {}
        for fp in self._generated_japanese_files(ext_loc):
            try:
                _, entries, _ = core.parse_localization_file(fp)
                for key in entries:
                    existing_key_file.setdefault(key, fp)
            except Exception:
                continue
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe=re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+','_',ext_name).strip('_')[:60] or "JapaneseMod"
        backup_root=BACKUP_ROOT / f"{stamp}_{safe}_差分上書き"
        backed=set(); updated=0; added=0
        patch_file = ext_loc / "japanese" / "paradox_localization_translator_missing_l_japanese.yml"
        try:
            for key, value in patch_values.items():
                target = existing_key_file.get(key)
                if not target:
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
                    text="l_japanese:\n"
                for key,value in missing:
                    escaped_value = core.escape_localization_value(value)
                    text += f' {key}: "{escaped_value}"\n'
                    added += 1
                patch_file.write_text("\ufeff"+text.lstrip("\ufeff"),encoding="utf-8")
            _, source_mod_root = self._infer_mod_target_for_item(item)
            validation_text = "上書き後確認: 判定対象を特定できません"
            validation_warning = False
            if source_mod_root and Path(source_mod_root).is_dir():
                coverage = core.analyze_external_translation_coverage(source_mod_root, ext_root)
                if coverage.get("complete"):
                    validation_text = "上書き後確認: 欠損なし"
                else:
                    validation_warning = True
                    validation_text = f"⚠ 本文自体に欠落があります。\n{coverage.get('gap_reason','翻訳不足があります')}"
            if notify:
                messagebox.showinfo(APP_NAME,
                    f"日本語化Modへ差分を反映しました。\n\n既存キー更新: {updated}件\n新規キー追加: {added}件\nバックアップ: {len(backed)}ファイル\nバックアップ先: {backup_root if backed else '変更前ファイルなし'}\n\n{validation_text}")
            reason=f"既存キー更新 {updated} / 新規キー追加 {added} / {validation_text}"
            return True,reason
        except Exception as e:
            record_error("日本語化Mod差分上書き", e, str(ext_root))
            if notify:
                messagebox.showerror(APP_NAME, f"日本語化Modへの差分上書き中にエラーが発生しました。\n{e}\n\nバックアップ先: {backup_root}")
            return False,str(e)

    def _merge_translation_gaps_into_external_mod(self, item):
        ok,_=self._perform_external_gap_overwrite(item,confirm=True,notify=True)
        if ok:
            self._set_overwritten_status(item)
            self._refresh_queue_tree()
            self._refresh_chinese_queue_tree()
        return ok

    def _perform_source_mod_overwrite(self, item, confirm=True, notify=True):
        loc_root, mod_root = self._infer_mod_target_for_item(item)
        if not loc_root:
            return False,"元のModのlocalizationフォルダを特定できません"
        out_root = Path(item.get("output", ""))
        generated = self._generated_japanese_files(out_root)
        if not generated:
            return False,"完成済み日本語YAMLが出力先に見つかりません"

        input_path = Path(item.get("input", ""))
        target_base = loc_root if input_path.is_dir() and input_path.name.lower() == "localization" else mod_root
        mappings=[]
        for src in generated:
            try:
                rel=src.relative_to(out_root)
            except ValueError:
                continue
            mappings.append((src,target_base / rel,rel))
        if not mappings:
            return False,"上書き対象を特定できません"

        existing=sum(1 for _,dst,_ in mappings if dst.exists())
        mod_name=item.get("mod_name") or Path(mod_root).name
        if confirm:
            warning=(
                f"⚠ 元のModへ日本語化ファイルを直接書き込みます。\n\n"
                f"Mod: {mod_name}\n対象: {mod_root}\n日本語YAML: {len(mappings)}件\n"
                f"既存ファイルの上書き: {existing}件\n\n"
                "既存ファイルは実行前にバックアップされます。\n"
                "Mod更新・Steam Workshop更新時には上書き内容が失われる可能性があります。\n\n続行しますか？")
            if not messagebox.askyesno("警告 — Modへ直接上書き", warning, icon="warning"):
                return False,"キャンセル"
            if not messagebox.askyesno("最終確認", "本当に元のModへ書き込みますか？\nこの操作は対象ファイルを置き換えます。", icon="warning"):
                return False,"キャンセル"

        stamp=datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        safe=re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+','_',mod_name).strip('_')[:60] or "Mod"
        backup_root=BACKUP_ROOT / f"{stamp}_{safe}"
        copied=0; backed=0
        try:
            for src,dst,rel in mappings:
                if dst.exists():
                    bdst=backup_root / rel
                    bdst.parent.mkdir(parents=True,exist_ok=True)
                    shutil.copy2(dst,bdst); backed += 1
                dst.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(src,dst); copied += 1
            post = core.analyze_mod_translation_status(mod_root)
            if post.get("gap_count", 0):
                validation_text = f"⚠ 本文自体に欠落があります。\n{post.get('gap_reason') or core.gap_reason_text(post.get('candidates', []))}"
            else:
                validation_text = "上書き後確認: 欠損なし"
            if notify:
                messagebox.showinfo(APP_NAME,
                    f"Modへ日本語化ファイルを上書きしました。\n\n書き込み: {copied}件\nバックアップ: {backed}件\nバックアップ先: {backup_root if backed else '既存ファイルなし'}\n\n{validation_text}")
            return True,f"書き込み {copied} / バックアップ {backed} / {validation_text}"
        except Exception as e:
            record_error("Mod直接上書き", e, str(mod_root))
            if notify:
                messagebox.showerror(APP_NAME, f"上書き中にエラーが発生しました。\n{e}\n\nバックアップ先: {backup_root}")
            return False,str(e)

    def _overwrite_single_item_interactive(self, item, prefer_external=True):
        if not self._queue_item_is_completed(item):
            messagebox.showinfo(APP_NAME,"上書きできるのは翻訳完了済みの項目です。")
            return False
        use_external=False
        if prefer_external and item.get("external_translation_path"):
            ext_name=item.get("external_translation_mod","") or Path(item.get("external_translation_path","")).name
            choice=messagebox.askyesnocancel(
                "上書き先の確認",
                f"日本語化Mod『{ext_name}』が見つかっています。\n\n"
                "はい: 日本語化Modへ差分上書き\nいいえ: 元Modへ上書き\nキャンセル: 何もしない",
                icon="question")
            if choice is None:
                return False
            use_external=bool(choice)
        if item.get("missing_only"):
            if use_external:
                target_root = Path(item.get("external_translation_path", ""))
                target_loc = Path(item.get("external_translation_localization", ""))
            else:
                target_loc, target_root = self._infer_mod_target_for_item(item)
            if not target_loc or not target_root:
                ok, reason = False, "不足翻訳の上書き先を特定できません"
            else:
                ok,reason=self._merge_missing_only_output(item, Path(target_loc), Path(target_root), confirm=True, notify=True)
        elif use_external:
            ok,reason=self._perform_external_gap_overwrite(item,confirm=True,notify=True)
        else:
            ok,reason=self._perform_source_mod_overwrite(item,confirm=True,notify=True)
        if ok:
            self._set_overwritten_status(item)
            self._refresh_queue_tree(); self._refresh_chinese_queue_tree()
        elif reason not in {"キャンセル"}:
            messagebox.showinfo(APP_NAME,f"上書きできませんでした。\n{reason}")
        return ok

    def _bulk_overwrite_queue_entries(self, entries, queue_kind="normal"):
        eligible=[]; skipped_unfinished=0
        for idx,item in entries:
            if self._queue_item_is_completed(item):
                eligible.append((idx,item))
            else:
                skipped_unfinished += 1
        if not eligible:
            messagebox.showinfo(APP_NAME,"選択項目に翻訳完了済みの項目がありません。")
            return

        has_external=any(item.get("external_translation_path") for _,item in eligible)
        policy="source"
        if has_external:
            choice=messagebox.askyesnocancel(
                "一括上書き先の方針",
                f"翻訳完了済み {len(eligible)}件を一括上書きします。\n\n"
                "はい: 既存日本語化Modがある項目は日本語化Modへ差分上書き\n"
                "      日本語化Modがない項目は元Modへ上書き\n"
                "いいえ: すべて元Modへ上書き\n"
                "キャンセル: 何もしない",
                icon="question")
            if choice is None:
                return
            policy="external" if choice else "source"

        policy_text="既存日本語化Modを優先" if policy=="external" else "すべて元Modへ上書き"
        if not messagebox.askyesno(
            "一括上書きの確認",
            f"対象: {len(eligible)}件\n方針: {policy_text}\n"
            f"未完了のためスキップ予定: {skipped_unfinished}件\n\n"
            "各Modについて既存ファイルのバックアップを作成してから書き込みます。\n続行しますか？",
            icon="warning"):
            return

        success=0; skipped=skipped_unfinished; failed=0; details=[]
        for _,item in eligible:
            name=item.get("mod_name") or Path(item.get("input","")).name or "項目"
            try:
                if item.get("missing_only"):
                    if policy=="external" and item.get("external_translation_path"):
                        target_root=Path(item.get("external_translation_path", "")); target_loc=Path(item.get("external_translation_localization", ""))
                    else:
                        target_loc,target_root=self._infer_mod_target_for_item(item)
                    if not target_loc or not target_root:
                        ok,reason=False,"不足翻訳の上書き先を特定できません"
                    else:
                        ok,reason=self._merge_missing_only_output(item,Path(target_loc),Path(target_root),confirm=False,notify=False)
                elif policy=="external" and item.get("external_translation_path"):
                    ok,reason=self._perform_external_gap_overwrite(item,confirm=False,notify=False)
                    if not ok and reason in {"日本語化Modへ反映する差分情報がありません","完成済み出力に差分訳が見つかりません"}:
                        skipped += 1; details.append(f"{name}: スキップ ({reason})"); continue
                else:
                    ok,reason=self._perform_source_mod_overwrite(item,confirm=False,notify=False)
                if ok:
                    self._set_overwritten_status(item); success += 1
                    if "⚠" in str(reason):
                        details.append(f"{name}: {reason}")
                else:
                    failed += 1; details.append(f"{name}: 失敗 ({reason})")
            except Exception as exc:
                failed += 1; details.append(f"{name}: 失敗 ({exc})")
                record_error("一括上書き",exc,name)

        self._refresh_queue_tree(); self._refresh_chinese_queue_tree()
        if self.queue_items and all(self._queue_item_is_completed(x) for x in self.queue_items):
            self._delete_session()
        summary=f"一括上書きが完了しました。\n\n上書き成功: {success}件\nスキップ: {skipped}件\n失敗: {failed}件"
        if details:
            summary += "\n\n詳細:\n" + "\n".join(details[:12])
            if len(details)>12:
                summary += f"\n…ほか {len(details)-12}件"
        messagebox.showinfo(APP_NAME,summary)

    def overwrite_selected_translation_to_mod(self, item_override=None, prefer_external=True):
        if item_override is not None:
            return self._overwrite_single_item_interactive(item_override,prefer_external=prefer_external)
        entries=self._selected_normal_queue_entries()
        if not entries:
            messagebox.showinfo(APP_NAME,"通常翻訳キューから上書きする項目を選択してください。")
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
            messagebox.showinfo(APP_NAME, "このModの完成済み翻訳がキューに見つかりません。\n先に『通常翻訳キューへ追加』で対象Modをキューへ追加し、翻訳を完了してください。")
            return
        idx,item=candidates[-1]
        self.overwrite_selected_translation_to_mod(item_override=item)

    def clear_mod_status_results(self):
        if not messagebox.askyesno(APP_NAME, "翻訳状況一覧と保存済みキャッシュを消去しますか？"):
            return
        self.mod_research_results=[]
        if hasattr(self,"mod_status_tree"):
            for x in self.mod_status_tree.get_children(): self.mod_status_tree.delete(x)
        with self.mod_status_cache_lock:
            self.mod_status_cache={"version":MOD_STATUS_CACHE_VERSION,"items":{},"updated_at":datetime.now().isoformat(timespec="seconds")}
            core.save_json(MOD_STATUS_CACHE_PATH,self.mod_status_cache)
        self.mod_status_summary_var.set("調査結果: 0件")

    def export_mod_status_csv(self):
        if not self.mod_research_results:
            messagebox.showinfo(APP_NAME,"保存する調査結果がありません。")
            return
        p=filedialog.asksaveasfilename(title="翻訳状況をCSV保存",defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="mod_translation_status.csv")
        if not p: return
        import csv
        with open(p,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow(["状態","Mod","欠損件数","結果","場所"])
            for r in self.mod_research_results:
                w.writerow([r.get("status",""),r.get("mod",""),r.get("gap_count",0),r.get("message",""),r.get("path","")])
        messagebox.showinfo(APP_NAME,"CSVを保存しました。")

    def clear_monitor_results(self):
        self.monitor_candidates=[]
        if hasattr(self,"monitor_tree"):
            for x in self.monitor_tree.get_children(): self.monitor_tree.delete(x)
        self.monitor_summary_var.set("未翻訳候補: 0")

    def export_monitor_csv(self):
        if not self.monitor_candidates:
            messagebox.showinfo(APP_NAME,"保存する候補がありません。")
            return
        p=filedialog.asksaveasfilename(title="未翻訳候補をCSV保存",defaultextension=".csv",filetypes=[("CSV","*.csv")],initialfile="untranslated_candidates.csv")
        if not p: return
        import csv
        with open(p,"w",encoding="utf-8-sig",newline="") as f:
            w=csv.writer(f); w.writerow(["種類","判定","ファイル","キー","原文","現在の日本語"])
            for c in self.monitor_candidates:
                w.writerow([c.get("kind",""),c.get("confidence",""),c.get("target_file") or c.get("source_file",""),c.get("key",""),c.get("source",""),c.get("target","")])
        messagebox.showinfo(APP_NAME,"CSVを保存しました。")

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

        conn=ttk.LabelFrame(left,text="LLM接続",padding=8); conn.pack(fill="x")
        conn.columnconfigure(1,weight=1)
        ttk.Label(conn,text="プロバイダ").grid(row=0,column=0,sticky="w")
        pc=ttk.Combobox(conn,textvariable=self.provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=14)
        pc.grid(row=0,column=1,padx=6,sticky="ew"); pc.bind("<<ComboboxSelected>>",lambda e:self.on_provider_change())
        ttk.Label(conn,text="API URL").grid(row=1,column=0,sticky="w",pady=(6,0))
        ttk.Entry(conn,textvariable=self.url_var).grid(row=1,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Button(conn,text="接続確認 / モデル再読込",command=self.refresh_models).grid(row=2,column=0,columnspan=2,sticky="ew",pady=(6,0))
        ttk.Label(conn,textvariable=self.connection_var).grid(row=3,column=0,columnspan=2,sticky="w",pady=(7,0))
        ttk.Label(conn,text="モデル").grid(row=4,column=0,sticky="w",pady=(6,0))
        self.model_combo=ttk.Combobox(conn,textvariable=self.model_var,state="normal")
        self.model_combo.grid(row=4,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Label(conn,text="APIキー").grid(row=5,column=0,sticky="w",pady=(6,0))
        ttk.Entry(conn,textvariable=self.api_key_var,show="•").grid(row=5,column=1,sticky="ew",padx=6,pady=(6,0))
        ttk.Label(conn,text="APIキーは保存しません。ローカル: Ollama / LM Studio　クラウド: OpenAI / Anthropic / Gemini / OpenAI互換API",foreground="#666",wraplength=430,justify="left").grid(row=6,column=0,columnspan=2,sticky="w",pady=(4,0))

        common=ttk.LabelFrame(left,text="翻訳共通設定",padding=8); common.pack(fill="x",pady=(10,0))
        common.columnconfigure(1,weight=1)
        ttk.Label(common,text="ゲームプリセット").grid(row=0,column=0,sticky="w")
        ttk.Combobox(common,textvariable=self.preset_var,values=list(core.GAME_PRESETS),state="readonly",width=15).grid(row=0,column=1,sticky="ew",padx=(6,0))
        ttk.Checkbutton(common,text="既存日本語の未翻訳を修復",variable=self.repair_var,command=self._save_llm_preferences).grid(row=1,column=0,columnspan=2,sticky="w",pady=(6,0))
        ttk.Checkbutton(common,text="通常翻訳後に自動QA",variable=self.autoqa_var,command=self._save_llm_preferences).grid(row=2,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Checkbutton(common,text="中国語基準翻訳後に自動QA",variable=self.chinese_autoqa_var,command=self._save_llm_preferences).grid(row=3,column=0,columnspan=2,sticky="w",pady=(4,0))
        ttk.Label(common,text="バッチ").grid(row=4,column=0,sticky="w",pady=(7,0))
        ttk.Spinbox(common,from_=1,to=500,textvariable=self.batch_var,width=8,command=self._save_llm_preferences).grid(row=4,column=1,sticky="w",padx=(6,0),pady=(7,0))
        ttk.Label(common,text="並列").grid(row=5,column=0,sticky="w",pady=(5,0))
        ttk.Spinbox(common,from_=1,to=8,textvariable=self.workers_var,width=8,command=self._save_llm_preferences).grid(row=5,column=1,sticky="w",padx=(6,0),pady=(5,0))
        ttk.Label(common,text="おすすめ").grid(row=6,column=0,sticky="w",pady=(5,0))
        perf_combo=ttk.Combobox(common,textvariable=self.performance_preset_var,values=["安定重視（20 / 1）","標準（40 / 1）","高速（60 / 2）"],state="readonly",width=18)
        perf_combo.grid(row=6,column=1,sticky="ew",padx=(6,0),pady=(5,0))
        ttk.Button(common,text="おすすめ設定を適用",command=self.apply_performance_preset).grid(row=7,column=0,columnspan=2,sticky="ew",pady=(5,0))
        ttk.Label(common,text="用語集").grid(row=8,column=0,sticky="w",pady=(7,0))
        ttk.Entry(common,textvariable=self.glossary_path_var).grid(row=8,column=1,sticky="ew",padx=(6,0),pady=(7,0))
        ttk.Button(common,text="用語集を選択",command=self.pick_glossary).grid(row=9,column=0,columnspan=2,sticky="ew",pady=(5,0))
        ttk.Label(common,text="推奨: バッチ20–60 / 並列1–2",foreground="#8a5a00").grid(row=10,column=0,columnspan=2,sticky="w",pady=(5,0))
        self.apply_current_translation_btn=ttk.Button(common,text="現在の翻訳へ設定を適用",command=self.apply_settings_to_current_translation)
        self.apply_current_translation_btn.grid(row=11,column=0,columnspan=2,sticky="ew",pady=(7,0))

        profsel=ttk.LabelFrame(left,text="モデルプロファイル選択",padding=8); profsel.pack(fill="x",pady=(10,0))
        profsel.columnconfigure(0,weight=1)
        self.profile_combo=ttk.Combobox(profsel,textvariable=self.profile_var,state="readonly")
        self.profile_combo.grid(row=0,column=0,sticky="ew")
        pbar=ttk.Frame(profsel); pbar.grid(row=1,column=0,sticky="ew",pady=(6,0))
        ttk.Button(pbar,text="適用",command=self.apply_selected_profile).pack(side="left")
        ttk.Button(pbar,text="削除",command=self.delete_selected_profile_combo).pack(side="left",padx=(5,0))
        ttk.Button(pbar,text="現在設定を保存",command=self.save_current_profile).pack(side="left",padx=(5,0))

        pf=ttk.LabelFrame(left,text="保存済みモデルプロファイル",padding=8); pf.pack(fill="both",expand=True,pady=(10,0))
        pb=ttk.Frame(pf); pb.pack(fill="x",pady=(0,6))
        ttk.Button(pb,text="現在設定をプロファイル保存",command=self.save_current_profile).pack(side="left")
        ttk.Button(pb,text="選択を適用",command=self.apply_profile_from_tree).pack(side="left",padx=(6,0))
        ttk.Button(pb,text="選択を削除",command=self.delete_profile).pack(side="left",padx=(6,0))
        self.profile_tree=ttk.Treeview(pf,columns=("name","label","provider","model","batch","workers"),show="headings",height=7)
        # 列幅は表示領域に合わせて縮ませず固定する。必要幅を超えた分は
        # 下部の横スクロールバーで確認する。
        for c,txt,w in (("name","名前",140),("label","用途",160),("provider","方式",150),("model","モデル",420),("batch","バッチ",80),("workers","並列",80)):
            self.profile_tree.heading(c,text=txt)
            self.profile_tree.column(c,width=w,minwidth=w,stretch=False)
        self._enable_tree_sort(self.profile_tree)
        pscroll_x=ttk.Scrollbar(pf,orient="horizontal",command=self.profile_tree.xview)
        self.profile_tree.configure(xscrollcommand=pscroll_x.set)
        self.profile_tree.pack(fill="both",expand=True); pscroll_x.pack(fill="x")
        self.profile_tree.bind("<Double-1>",lambda e:self.apply_profile_from_tree())

        bench=ttk.LabelFrame(right,text="モデル速度比較（実翻訳時の統計も自動記録）",padding=8); bench.pack(fill="both",expand=True)
        bar=ttk.Frame(bench); bar.pack(fill="x",pady=(0,6))
        ttk.Button(bar,text="現在のLLMを速度テスト",command=self.benchmark_selected_model).pack(side="left")
        ttk.Button(bar,text="選択したモデルを比較テスト",command=self.benchmark_selected_models).pack(side="left",padx=(6,0))
        self.benchmark_stop_btn=ttk.Button(bar,text="速度テスト停止",command=self.stop_benchmark,state="disabled"); self.benchmark_stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(bar,text="統計を消去",command=self.clear_model_stats).pack(side="left",padx=(6,0))
        self.benchmark_status_var=tk.StringVar(value=""); ttk.Label(bar,textvariable=self.benchmark_status_var).pack(side="right")

        select_box=ttk.LabelFrame(bench,text="比較するモデルを選択（最大5モデル）",padding=6); select_box.pack(fill="x",pady=(0,8))
        ttk.Label(select_box,text="Ctrlキーを押しながらクリックすると複数選択できます。最大5モデルまで選択できます。",foreground="#666").pack(anchor="w",pady=(0,4))
        self.benchmark_model_list=tk.Listbox(select_box,selectmode=tk.EXTENDED,exportselection=False,height=6)
        self._enable_ctrl_multiselect(self.benchmark_model_list,max_items=5); self.benchmark_model_list.pack(fill="x"); self.benchmark_model_list.bind("<<ListboxSelect>>",self._limit_benchmark_selection)

        cols=("provider","model","requests","avg","tps","fail")
        self.stats_tree=ttk.Treeview(bench,columns=cols,show="headings",height=16)
        for c,txt,w in (("provider","プロバイダ",100),("model","モデル",330),("requests","回数",70),("avg","平均秒",90),("tps","tokens/s",100),("fail","失敗率",90)):
            self.stats_tree.heading(c,text=txt); self.stats_tree.column(c,width=w,anchor="center" if c not in ("model",) else "w")
        self._enable_tree_sort(self.stats_tree)
        sscroll_x=ttk.Scrollbar(bench,orient="horizontal",command=self.stats_tree.xview)
        self.stats_tree.configure(xscrollcommand=sscroll_x.set); self.stats_tree.pack(fill="both",expand=True); sscroll_x.pack(fill="x")

        self.refresh_model_stats_ui(); self.refresh_profiles_ui()

    def on_provider_change(self):
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
        if not model: messagebox.showinfo(APP_NAME,"モデルを選択してください。"); return
        self._start_benchmark([model])

    def _limit_benchmark_selection(self,event=None):
        if not hasattr(self,"benchmark_model_list"): return
        selected=list(self.benchmark_model_list.curselection())
        if len(selected)<=5: return
        # Tkの選択順は取得できないため、先頭5件を残して6件目以降を解除する。
        for idx in selected[5:]:
            self.benchmark_model_list.selection_clear(idx)
        self.benchmark_status_var.set("比較テストは最大5モデルまで選択できます")

    def benchmark_selected_models(self):
        if not hasattr(self,"benchmark_model_list"):
            return
        selected=list(self.benchmark_model_list.curselection())
        if not selected:
            messagebox.showinfo(APP_NAME,"比較するモデルを1〜5個選択してください。")
            return
        if len(selected)>5:
            messagebox.showinfo(APP_NAME,"比較テストで選択できるのは最大5モデルです。")
            return
        models=[self.benchmark_model_list.get(i) for i in selected]
        self._start_benchmark(models)

    def _start_benchmark(self,models):
        if getattr(self,"benchmark_worker",None) and self.benchmark_worker.is_alive(): return
        self.benchmark_status_var.set(f"速度テスト中 0/{len(models)} — 開始準備")
        self.llm_operation = "モデル速度テスト"
        self.benchmark_stop_btn.config(state="normal")
        provider=self.provider_var.get(); url=self.url_var.get().strip()
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
                    core.benchmark_model(provider,url,m,self.benchmark_controller,self.api_key_var.get().strip())
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
            self.benchmark_status_var.set("速度テスト停止要求済み — 現在のLLM応答完了を待っています")
            self.benchmark_stop_btn.config(state="disabled")
            self.llm_detail_var.set("停止要求済み — 現在のAPI/LLM応答が返り次第停止します")

    def clear_model_stats(self):
        if messagebox.askyesno(APP_NAME,"モデル速度統計をすべて消去しますか？"):
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
        name=simpledialog.askstring("モデルプロファイル","プロファイル名（例: Qwen 30B 品質重視）")
        if not name: return
        label=simpledialog.askstring("モデルプロファイル","用途メモ（例: 品質重視 / 高速）",initialvalue=self.model_profiles.get(name,{}).get("label","")) or ""
        self.model_profiles[name]={"label":label,"provider":self.provider_var.get(),"url":self.url_var.get(),"model":self.model_var.get(),"batch":self.batch_var.get(),"workers":self.workers_var.get(),"preset":self.preset_var.get()}
        core.save_json(PROFILES_PATH,self.model_profiles); self.profile_var.set(name); self.refresh_profiles_ui()

    def _apply_profile(self,name):
        p=self.model_profiles.get(name)
        if not p: return
        self.provider_var.set(p.get("provider","Ollama")); self.url_var.set(p.get("url",core.default_url_for_provider(self.provider_var.get())))
        self.model_var.set(p.get("model","")); self.batch_var.set(p.get("batch",40)); self.workers_var.set(p.get("workers",1)); self.preset_var.set(p.get("preset","CK3")); self.profile_var.set(name)
        self.refresh_models()

    def apply_selected_profile(self): self._apply_profile(self.profile_var.get())

    def apply_profile_from_tree(self):
        sel=self.profile_tree.selection()
        if sel: self._apply_profile(sel[0])

    def delete_profile(self):
        sel=self.profile_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "削除するモデルプロファイルを選択してください。")
            return
        names=list(sel)
        if not messagebox.askyesno(APP_NAME, "次のモデルプロファイルを削除しますか？\n\n" + "\n".join(names)):
            return
        for name in names: self.model_profiles.pop(name,None)
        if self.profile_var.get() in names: self.profile_var.set("")
        core.save_json(PROFILES_PATH,self.model_profiles); self.refresh_profiles_ui()

    def delete_selected_profile_combo(self):
        name=self.profile_var.get().strip()
        if not name:
            messagebox.showinfo(APP_NAME,"削除するモデルプロファイルを選択してください。")
            return
        if not messagebox.askyesno(APP_NAME,f"モデルプロファイル『{name}』を削除しますか？"):
            return
        self.model_profiles.pop(name,None)
        self.profile_var.set("")
        core.save_json(PROFILES_PATH,self.model_profiles)
        self.refresh_profiles_ui()

    # ---------------- queue ----------------
    def _default_output(self,p:Path):
        raw = self.normal_output_var.get().strip() if hasattr(self, "normal_output_var") else ""
        root = Path(raw) if raw else _automatic_output_root()
        root.mkdir(parents=True, exist_ok=True)
        name = p.stem + "_japanese" if p.is_file() else p.name + "_japanese"
        return root / name

    def pick_normal_output(self):
        raw=filedialog.askdirectory(title="通常翻訳の出力先ルートを選択")
        if raw:
            self.normal_output_var.set(raw)

    def add_folder(self):
        p=filedialog.askdirectory(title="翻訳するMod/localizationフォルダを選択")
        if p:
            path=Path(p)
            self.normal_input_var.set(str(path))
            self.normal_status_var.set(f"キューへ追加しました: {path.name}")
            self._append_queue(path)

    def add_files(self):
        paths=filedialog.askopenfilenames(title="翻訳するYAMLを複数選択",filetypes=[("Paradox YAML","*.yml"),("All","*")])
        added=0
        for raw in paths:
            path=Path(raw)
            self._append_queue(path)
            added += 1
        if paths:
            self.normal_input_var.set(str(Path(paths[-1])))
            self.normal_status_var.set(f"YAMLを {added} 件キューへ追加しました。")

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
        data = core.load_json(CACHE_REGISTRY_PATH, {})
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

    def _prepare_differential_cache(self, item: dict, silent: bool = True, mode: str = "normal") -> dict | None:
        p = Path(item["input"])
        current_cache = Path(self._ensure_item_cache(item))
        previous = self._find_previous_cache(p, exclude=current_cache, mode=mode)
        if not previous:
            return None
        old_manifest = core.load_source_manifest(previous)
        if not old_manifest:
            return None
        try:
            if mode == "chinese":
                new_manifest = core.build_source_manifest_for_language(p, "simp_chinese")
            else:
                new_manifest = core.build_source_manifest(p, None if self.repair_var.get() else core.DEFAULT_TARGET_LANG)
        except Exception:
            return None
        diff = core.compare_source_manifests(old_manifest, new_manifest)
        c = diff["counts"]
        changed_total = c["added"] + c["changed"] + c["removed"]
        if changed_total == 0 and c["added_files"] == 0 and c["removed_files"] == 0:
            item["diff"] = diff
            item["previous_cache"] = str(previous)
            if item.get("status") == "待機": item["status"] = "差分なし"
            return diff
        # 翻訳ごとの独立キャッシュを維持したまま、前回キャッシュを複製して差分だけ追加する。
        try:
            shutil.copy2(previous, current_cache)
        except Exception:
            pass
        item["previous_cache"] = str(previous)
        item["diff"] = diff
        item["diff_mode"] = True
        item["status"] = f"差分 +{c['added']} / 変更{c['changed']}"
        core.save_json(current_cache.parent / "diff_report.json", {
            "previous_cache": str(previous), "current_input": str(p),
            "detected_at": datetime.now().isoformat(timespec="seconds"), "diff": diff
        })
        if not silent:
            messagebox.showinfo(APP_NAME,
                f"過去のキャッシュを自動特定しました。\n\n新規キー: {c['added']}\n変更キー: {c['changed']}\n削除キー: {c['removed']}\n新規ファイル: {c['added_files']}\n削除ファイル: {c['removed_files']}\n\n差分だけが追加翻訳されます。")
        return diff

    def _append_queue(self,p:Path,out:Path|None=None,status="待機",cache:Path|None=None):
        p = Path(p)
        if not p.exists():
            return
        out=out or self._default_output(p)
        cache_path = cache or self._new_cache_path(p)
        item={"input":str(p),"output":str(out),"status":status,"cache":str(cache_path)}
        self.queue_items.append(item)
        self._refresh_queue_tree()

    def detect_diff_for_selected(self):
        item = self._selected_queue_item()
        if not item: return
        diff = self._prepare_differential_cache(item, silent=False)
        if diff is None:
            messagebox.showinfo(APP_NAME, "同じ入力元に対応する過去の差分スナップショット付きキャッシュが見つかりません。\n一度v0.5.6以降で通常翻訳すると、次回更新から自動判定できます。")
        elif sum(diff["counts"][k] for k in ("added","changed","removed")) == 0:
            messagebox.showinfo(APP_NAME, "前回翻訳時から原文の差分はありません。")
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
                    self._record_error("DnDフォルダ解析", e)
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
            side = "日本語YAML" if src else "英語または簡体字中国語の原文YAML"
            self.qa_summary_var.set(f"片方を受け取りました。{side}もドロップしてください。")
        else:
            messagebox.showinfo(APP_NAME,"QAにはYAMLファイル、またはYAMLを含むフォルダをドロップしてください。")
        return event.action if hasattr(event,"action") else None

    def on_diff_drop_paths(self,event):
        files=self._extract_drop_paths(event)
        src,dst=self._classify_drop_pair(files)
        if src: self.diff_src_var.set(str(src))
        if dst: self.diff_dst_var.set(str(dst))
        if src and dst:
            self.load_diff_inspector()
        elif files:
            self.diff_summary_var.set("片方を受け取りました。英語または簡体字中国語の原文と日本語の両方をドロップしてください。")
        else:
            messagebox.showinfo(APP_NAME,"差分調査にはYAMLファイル、またはYAMLを含むフォルダをドロップしてください。")
        return event.action if hasattr(event,"action") else None

    def on_drop_paths(self, event):
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
            self.progress_text.set(f"ドラッグ＆ドロップで{added}件追加しました")
            self.save_session(active=False)
        if ignored:
            messagebox.showinfo(APP_NAME, "YAMLファイルまたはフォルダ以外は追加しませんでした。\n\n" + "\n".join(ignored[:10]))
        return event.action if hasattr(event, "action") else None

    def _refresh_queue_tree(self):
        for x in self.queue_tree.get_children(): self.queue_tree.delete(x)
        for i,item in enumerate(self.queue_items):
            inp=Path(item.get("input", ""))
            label=item.get("mod_name") or (inp.stem if inp.is_file() else inp.name) or "項目"
            self.queue_tree.insert("", "end", iid=str(i), values=(
                label,
                self._queue_display_path(item.get("input", "")),
                self._queue_display_path(item.get("output", "")),
                item.get("status", "")
            ))

    def remove_queue(self):
        sels=sorted((int(x) for x in self.queue_tree.selection()),reverse=True)
        for i in sels:
            if 0<=i<len(self.queue_items): self.queue_items.pop(i)
        self._refresh_queue_tree()
        if not self.queue_items and not (self.worker and self.worker.is_alive()):
            self._delete_session()
        elif not (self.worker and self.worker.is_alive()):
            self._write_session_file(active=False,restore_on_launch=False)

    def clear_queue(self):
        if self.worker and self.worker.is_alive(): return
        self.queue_items.clear(); self._refresh_queue_tree(); self._delete_session()

    def _selected_queue_item(self):
        sel = self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "先にキュー一覧から対象の翻訳を選択してください。")
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
        win.title(f"キャッシュを見る — {Path(item['input']).name}")
        win.geometry("900x600")
        top = ttk.Frame(win, padding=8); top.pack(fill="x")
        ttk.Label(top, text=f"キャッシュ: {cache_path}", wraplength=700).pack(side="left", fill="x", expand=True)
        ttk.Label(top, text=f"{len(cache)}件").pack(side="right", padx=(8,0))
        bar = ttk.Frame(win, padding=(8,0,8,6)); bar.pack(fill="x")
        ttk.Button(bar, text="保存場所を開く", command=lambda:self._open_path(cache_path.parent)).pack(side="left")
        ttk.Button(bar, text="JSONを再読込", command=lambda:self._reload_cache_view(text, cache_path)).pack(side="left", padx=(6,0))
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
        item = self._selected_queue_item()
        if not item:
            return
        src = filedialog.askopenfilename(title="追加するキャッシュを選択", filetypes=[("JSON cache", "*.json"), ("All", "*")])
        if not src:
            return
        try:
            imported = core.load_cache(Path(src))
            if not isinstance(imported, dict):
                raise ValueError("キャッシュJSONが辞書形式ではありません")
            dst_path = Path(item["cache"]); dst = core.load_cache(dst_path) if dst_path.exists() else {}
            overwrite = messagebox.askyesno(APP_NAME, f"{len(imported)}件のキャッシュを追加します。\n同じキーがある場合、追加するキャッシュで上書きしますか？")
            if overwrite:
                dst.update(imported)
            else:
                for k,v in imported.items():
                    dst.setdefault(k,v)
            core.save_cache(dst_path, dst)
            self.save_session(active=bool(self.worker and self.worker.is_alive()))
            messagebox.showinfo(APP_NAME, f"キャッシュを追加しました。\n現在: {len(dst)}件\n保存先: {dst_path}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"キャッシュの追加に失敗しました。\n{e}")

    def run_selected_translation_qa(self):
        """Run source-aware QA for the currently selected normal translation queue item."""
        sel = self.queue_tree.selection() if hasattr(self, "queue_tree") else ()
        if not sel:
            messagebox.showinfo(APP_NAME, "翻訳語QAを実行する項目を選択してください。")
            return
        try:
            item = self.queue_items[int(sel[0])]
        except Exception:
            messagebox.showerror(APP_NAME, "選択した翻訳項目を取得できませんでした。")
            return
        inp = Path(item.get("input", ""))
        out = Path(item.get("output", ""))
        if not inp.exists():
            messagebox.showerror(APP_NAME, "翻訳元が見つかりません。")
            return
        if not out.exists():
            messagebox.showinfo(APP_NAME, "まだ翻訳出力がありません。先に翻訳を実行してください。")
            return
        try:
            result = core.qa_translation_output(inp, out, self.glossary_path_var.get().strip() or None)
            report_path = out / "translation_qa_report.json"
            core.save_json(report_path, {"target_language": "japanese", **result})
            self._log(f"翻訳語QA: error {result['errors']} / warning {result['warnings']} / syntax自動修正 {result['syntax_repaired']} / 未修正 {result['syntax_unresolved']} / 確認 {result['checked_files']}ファイル")
            if result.get("missing_outputs"):
                self._log(f"翻訳語QA: 対応する日本語出力がないファイル {result['missing_outputs']}件")
            messagebox.showinfo(APP_NAME, f"翻訳語QAが完了しました。\n\nエラー: {result['errors']}\n警告: {result['warnings']}\nsyntax検出: {result['syntax_detected']}\n自動修正: {result['syntax_repaired']}\n未修正: {result['syntax_unresolved']}\n確認ファイル: {result['checked_files']}\n\nレポート: {report_path}")
        except Exception as exc:
            record_error("通常翻訳語QA", exc)
            messagebox.showerror(APP_NAME, str(exc))

    def change_output(self):
        sel=self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "出力先を変更する項目を、キュー一覧から先に選択してください。\n\n通常は変更不要です。既定では『Paradox Localization Translator/翻訳結果』へ出力されます。全体の保存場所は［設定］タブから変更できます。")
            return
        current = self.queue_items[int(sel[0])].get("output", "")
        initial = str(Path(current).parent) if current else str(_automatic_output_root())
        p=filedialog.askdirectory(title="選択項目の出力先", initialdir=initial)
        if p:
            self.queue_items[int(sel[0])]["output"]=p
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
            item["status"] = "待機"

    def start_differential_queue(self):
        if self.worker and self.worker.is_alive():
            return
        targets = [x for x in self.queue_items if not self._queue_item_is_completed(x)]
        if not targets:
            messagebox.showinfo(APP_NAME, "差分翻訳できる待機中の項目がありません。")
            return
        prepared = 0
        unavailable = []
        for item in targets:
            diff = self._prepare_differential_cache(item, silent=True)
            if diff is None:
                unavailable.append(item.get("mod_name") or Path(item.get("input", "")).name)
            else:
                item["diff_mode"] = True
                counts = diff.get("counts", {})
                changed_total = sum(int(counts.get(k, 0) or 0) for k in ("added", "changed", "removed", "added_files", "removed_files"))
                if changed_total == 0:
                    item["status"] = "完了（差分更新）"
                else:
                    prepared += 1
        self._refresh_queue_tree()
        if unavailable:
            for item in targets:
                if item.get("diff_mode"):
                    self._reset_item_for_full_translation(item)
            self._refresh_chinese_queue_tree()
            messagebox.showinfo(APP_NAME, "前回の差分スナップショットがないため差分翻訳できない項目があります。\n\n" + "\n".join(unavailable[:10]))
            return
        if prepared:
            self.start_queue(_diff_requested=True)
        else:
            messagebox.showinfo(APP_NAME, "前回翻訳時から翻訳対象の差分はありません。")

    def start_queue(self, _diff_requested=False):
        if self.worker and self.worker.is_alive(): return
        if not _diff_requested:
            for item in self.queue_items:
                if not self._queue_item_is_completed(item):
                    self._reset_item_for_full_translation(item)
            self._refresh_queue_tree()
        if not self.queue_items:
            messagebox.showinfo(APP_NAME,"翻訳キューにフォルダまたはファイルを追加してください。"); return
        self._clear_log(); self.progress["value"]=0
        self.llm_operation = "翻訳"
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
            "repair":self.repair_var.get(), "autoqa":self.autoqa_var.get()}
        self.start_btn.config(state="disabled"); self.diff_start_btn.config(state="disabled"); self.pause_btn.config(state="normal",text="一時停止"); self.stop_btn.config(state="normal")
        self.worker=threading.Thread(target=self._queue_worker,daemon=True); self.worker.start()
        self.save_session(active=True)

    def _queue_worker(self):
        try:
            for i,item in enumerate(self.queue_items):
                self.current_queue_index=i
                if self._queue_item_is_completed(item): continue
                item["status"]="翻訳中"; self.events.put(("queue_refresh",None))
                self._checkpoint({"queue_index":i})
                out=Path(item["output"]); cache_file=Path(self._ensure_item_cache(item))
                st=getattr(self,"translation_start_settings",{})
                result=core.run_translation(
                    item["input"], item["output"], model=st.get("model",self.model_var.get().strip()), url=st.get("url",self.url_var.get().strip()),
                    workers=max(1,st.get("workers",self.workers_var.get())), batch_size=max(1,st.get("batch",self.batch_var.get())), cache_path=cache_file,
                    resume=True, verbose=True, include_target_files=st.get("repair",self.repair_var.get()), controller=self.controller,
                    glossary_path=st.get("glossary") or None, preset=st.get("preset",self.preset_var.get()),
                    dual_source=False, auto_qa=st.get("autoqa",self.autoqa_var.get()),
                    provider=st.get("provider",self.provider_var.get()), api_key=st.get("api_key",self.api_key_var.get().strip()))
                self._register_cache_job(item)
                if result.get("interrupted"):
                    item["status"]="中断（再開可）"; self.events.put(("queue_refresh",None)); self.save_session(active=True); break
                if self._item_has_remaining_translation_gap(item):
                    item["status"] = "完了（一部差分欠落あり）"
                else:
                    item["status"] = "完了（差分更新）" if item.get("diff_mode") else "完了"
                self.events.put(("queue_refresh",None))
                # 次の項目がある間だけ復元可能な実行中セッションとして保存する。
                if i < len(self.queue_items)-1:
                    self._write_session_file(active=True,restore_on_launch=True)
            else:
                # 全項目正常完了。古いセッションが再び復活しないよう、完了状態を確定してから削除する。
                self._write_session_file(active=False,restore_on_launch=False)
                self._delete_session()
                self.events.put(("done",None))
        except Exception as e:
            self.events.put(("fatal",str(e))); self.save_session(active=True)

    def toggle_pause(self):
        if not self.controller: return
        if self.controller.pause_event.is_set():
            self.controller.resume(); self.pause_btn.config(text="一時停止"); self.progress_text.set("再開しました")
        else:
            self.controller.pause(); self.pause_btn.config(text="再開"); self.progress_text.set("一時停止中（現在のLLM応答完了後に停止）")
        self.save_session(active=True)

    def save_and_stop(self):
        if self.controller:
            self.save_session(active=True); self.controller.request_stop(save=True)
            self.progress_text.set("保存して中断中… 現在のリクエスト完了を待っています")
            self.stop_btn.config(state="disabled")

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

    def save_session(self,active=False,restore_on_launch=None):
        # 手動保存は次回起動時の強制復元対象にはしない。終了時保存だけ明示的にTrueを渡す。
        if restore_on_launch is None:
            restore_on_launch=bool(active)
        self._write_session_file(active=active,restore_on_launch=restore_on_launch)
        if not active:
            self.progress_text.set(f"セッション保存: {RESUME_STATE_PATH}")

    def _checkpoint(self,payload):
        self._write_session_file(active=True,restore_on_launch=True,checkpoint=payload)

    def _load_resume_candidate(self):
        """Load a restorable snapshot without requiring the same app version."""
        for path in (SESSION_PATH,RESUME_STATE_PATH):
            try:
                data=core.load_json(path,{})
            except Exception:
                data={}
            if not isinstance(data,dict) or not data.get("queue"):
                continue
            if data.get("active") or data.get("restore_on_launch"):
                # Saved queue paths from old app-adjacent data roots must follow
                # the migrated copy under Documents/Paradox Localization Translator.
                saved_root = data.get("data_root")
                for item in data.get("queue", []) or []:
                    if isinstance(item, dict):
                        for key in ("cache", "output", "previous_cache"):
                            if item.get(key):
                                item[key] = _remap_saved_data_path(item.get(key), saved_root)
                settings = data.get("settings") or {}
                if isinstance(settings, dict) and settings.get("glossary"):
                    settings["glossary"] = _remap_saved_data_path(settings.get("glossary"), saved_root)
                return data,path
        return {},None

    def restore_session(self, data=None):
        if data is None:
            data,_=self._load_resume_candidate()
        if not data:
            messagebox.showinfo(APP_NAME,"保存された再開可能な作業はありません。"); return
        self.queue_items=data.get("queue",[])
        self.current_queue_index=max(0,int(data.get("queue_index",0) or 0))
        s=data.get("settings",{})
        self.provider_var.set(s.get("provider",self.provider_var.get())); self.url_var.set(s.get("url",self.url_var.get())); self.model_var.set(s.get("model",self.model_var.get())); self.preset_var.set(s.get("preset",self.preset_var.get()))
        self.batch_var.set(s.get("batch",40)); self.workers_var.set(s.get("workers",1)); self.repair_var.set(s.get("repair",True)); self.dual_var.set(s.get("dual",False)); self.autoqa_var.set(s.get("autoqa",True)); self.glossary_path_var.set(s.get("glossary",str(DEFAULT_GLOSSARY)))
        for item in self.queue_items:
            self._ensure_item_cache(item)
            if item.get("status") == "翻訳中": item["status"]="中断（再開可）"
        previous_version=data.get("app_version") or data.get("version") or "不明"
        # 復元直後は古いactiveフラグを解除し、新バージョン形式へ移行して保存する。
        self._write_session_file(active=False,restore_on_launch=False)
        self._refresh_queue_tree()
        self.progress_text.set(f"作業を復元しました（保存元 v{previous_version}）。翻訳開始で続きから再開します。")

    def _offer_restore_session(self):
        data,path=self._load_resume_candidate()
        if not data:
            return
        previous_version=data.get("app_version") or data.get("version") or "不明"
        source_note=""
        if path==RESUME_STATE_PATH:
            source_note="\n\nバージョン共通の再開ログから復元します。"
        if messagebox.askyesno(APP_NAME,f"前回の未完了作業が残っています（保存元 v{previous_version}）。\n続きから復元しますか？{source_note}"):
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
    def refresh_models(self):
        label=self.provider_var.get()
        key = self.api_key_var.get().strip() or core.env_api_key_for_provider(label)
        if core.normalize_provider(label) in {"openai","anthropic","gemini","openai_compat"} and not key:
            self.connection_var.set(f"{label}: APIキーが未設定です")
        else:
            self.connection_var.set(f"{label} 接続確認中…")
        threading.Thread(target=self._fetch_models,daemon=True).start()

    def _fetch_models(self):
        try:
            models=core.list_models(self.provider_var.get(),self.url_var.get().strip(),timeout=8,api_key=self.api_key_var.get().strip())
            self.events.put(("models",models))
        except Exception as e:
            self.events.put(("model_error",str(e)))

    # ---------------- difference inspector / search ----------------
    def load_diff_inspector(self):
        src = Path(self.diff_src_var.get())
        dst = Path(self.diff_dst_var.get())
        if not src.exists() or not dst.exists():
            messagebox.showerror(APP_NAME, "英語または簡体字中国語の原文ファイルと日本語ファイルの両方を選択してください。")
            return
        try:
            source_lang, self.diff_source_entries, _ = core.parse_localization_file(src)
            self.diff_source_lang = source_lang
            _, self.diff_target_entries, _ = core.parse_localization_file(dst)
            self.diff_rows = core.compare_localization_entries(self.diff_source_entries, self.diff_target_entries, source_lang)
            self.diff_row_by_key = {r["key"]: r for r in self.diff_rows}
            for iid in self.diff_tree.get_children(): self.diff_tree.delete(iid)
            self.diff_tree_key_map={}
            labels = {"missing":"欠落", "untranslated":"未翻訳", "extra":"日本語のみ", "ok":"対応あり"}
            counts = {k:0 for k in labels}
            parents={}
            for status in ("missing","untranslated","extra","ok"):
                parents[status]=self.diff_tree.insert("","end",iid=f"diff_group_{status}",text=labels[status],open=status!="ok",values=("",),tags=(status,))
            n=0
            for row in self.diff_rows:
                status=row["status"]
                counts[status] = counts.get(status, 0) + 1
                iid=f"diff_leaf_{n}"; n+=1
                self.diff_tree.insert(parents[status], "end", iid=iid, text="", values=(row["key"],), tags=(status,))
                self.diff_tree_key_map[iid]=row["key"]
            self.diff_summary_var.set(f"欠落 {counts['missing']} / 未翻訳 {counts['untranslated']} / 日本語のみ {counts['extra']} / 対応あり {counts['ok']}")
        except Exception as e:
            record_error("差分調査", e)
            messagebox.showerror(APP_NAME, str(e))

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
            core.upsert_localization_values(Path(self.diff_dst_var.get()), {key:value})
            self.load_diff_inspector()
            for iid,k in getattr(self,"diff_tree_key_map",{}).items():
                if k==key and self.diff_tree.exists(iid):
                    self.diff_tree.selection_set(iid); self.diff_tree.see(iid); break
        except Exception as e:
            record_error("差分訳保存", e); messagebox.showerror(APP_NAME, str(e))

    def translate_diff_items(self, all_missing=False):
        if self.diff_controller is not None:
            messagebox.showinfo(APP_NAME, "差分翻訳はすでに実行中です。")
            return
        if not self.diff_rows:
            self.load_diff_inspector()
            if not self.diff_rows: return
        if all_missing:
            keys = [r["key"] for r in self.diff_rows if r["status"] in ("missing","untranslated") and r.get("source")]
        else:
            keys = [k for k in self._selected_diff_keys() if self.diff_row_by_key.get(k,{}).get("source")]
        if not keys:
            messagebox.showinfo(APP_NAME, "翻訳対象の欠落/未翻訳キーを選択してください。")
            return
        src_path = Path(self.diff_src_var.get()); dst_path = Path(self.diff_dst_var.get())
        source_lang = core.parse_localization_file(src_path)[0]
        self.diff_controller = core.TranslationController(progress_callback=lambda p:self.events.put(("diff_translate_progress", p)))
        self.llm_operation = "差分翻訳"
        self.diff_message_var.set(f"差分翻訳中… {len(keys)}件")
        def work():
            try:
                glossary = core.load_glossary(Path(self.glossary_path_var.get())) if self.glossary_path_var.get() else {}
                out = {}
                for i, key in enumerate(keys, 1):
                    if self.diff_controller.stop_event.is_set(): raise core.StopRequested()
                    self.events.put(("diff_translate_status", (i, len(keys), key)))
                    out[key] = core.translate_single_text(self.url_var.get(), self.model_var.get(), self.diff_source_entries[key], source_lang,
                                                          glossary, self.preset_var.get(), self.provider_var.get(), self.api_key_var.get().strip(), self.diff_controller,
                                                          chinese_basis=(source_lang == "simp_chinese"))
                core.upsert_localization_values(dst_path, out)
                self.events.put(("diff_translate_done", len(out)))
            except core.StopRequested:
                self.events.put(("diff_translate_stopped", None))
            except Exception as e:
                self.events.put(("diff_translate_error", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def pick_search_folder(self):
        # Legacy compatibility: translation search is now game-scoped.
        messagebox.showinfo(APP_NAME, "翻訳検索はゲーム単位の検索に変更されました。対象ゲームを選んで検索してください。")

    def pick_search_file(self):
        messagebox.showinfo(APP_NAME, "翻訳検索はゲーム単位の検索に変更されました。個別YAMLはQA / 比較編集または差分調査から選択できます。")

    def clear_translation_search_results(self):
        if hasattr(self, "search_tree"):
            for iid in self.search_tree.get_children():
                self.search_tree.delete(iid)
        self.search_result_map = {}
        self.search_summary_var.set("検索待機中")
        if hasattr(self, "search_edit_text"):
            self.search_edit_text.delete("1.0", "end")
        if hasattr(self, "search_selected_var"):
            self.search_selected_var.set("検索結果を選択してください")

    def _translation_search_mod_roots_for_game(self, game):
        roots = []
        seen = set()
        for row in self.detected_mod_locations:
            if row.get("game") != game:
                continue
            location = Path(row.get("path", ""))
            if not location.exists():
                continue
            try:
                candidates = core.find_mod_roots(location)
            except Exception:
                candidates = []
            for root in candidates:
                key = str(Path(root).resolve())
                if key not in seen:
                    seen.add(key); roots.append(Path(root))
        return roots

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
        game = self.search_game_var.get().strip()
        q = self.search_query_var.get().strip().casefold()
        if not game:
            messagebox.showerror(APP_NAME, "検索するゲームを選択してください。")
            return
        if not q:
            messagebox.showinfo(APP_NAME, "全件列挙を防ぐため、検索語を入力してください。")
            return
        roots = self._translation_search_mod_roots_for_game(game)
        if not roots:
            messagebox.showinfo(APP_NAME, f"{game} のMod場所がまだ検出されていません。［ゲーム / Mod場所を再検出］を実行してから再度検索してください。")
            return
        for iid in self.search_tree.get_children():
            self.search_tree.delete(iid)
        self.search_result_map = {}
        count = 0
        missing_count = 0
        scanned_mods = 0

        for mod_root in roots:
            loc = core.mod_localization_root(mod_root)
            if not loc:
                continue
            scanned_mods += 1
            mod_name = core.detect_mod_name(mod_root)
            try:
                files = core.gather_yml_files(loc)
            except Exception:
                continue

            groups = {}
            for f in files:
                try:
                    lang, entries, _ = core.parse_localization_file(f)
                except Exception:
                    continue
                if lang not in ("english", "simp_chinese", "japanese"):
                    continue
                try:
                    lid = core._logical_localization_id(f, loc, lang)
                except Exception:
                    lid = f.name
                groups.setdefault(lid, {})[lang] = {"path": Path(f), "entries": entries}

            for _lid, langs in groups.items():
                ja = langs.get("japanese")
                src = langs.get("english") or langs.get("simp_chinese")
                src_lang = "english" if "english" in langs else ("simp_chinese" if "simp_chinese" in langs else "")
                ja_entries = ja["entries"] if ja else {}
                src_entries = src["entries"] if src else {}
                all_keys = set(ja_entries) | set(src_entries)

                for key in sorted(all_keys):
                    ja_value = ja_entries.get(key)
                    source_value = src_entries.get(key, "")
                    source_file = src["path"] if src else None
                    target_file = ja["path"] if ja else (self._search_expected_japanese_path(loc, source_file, src_lang) if source_file else None)
                    missing = key in src_entries and key not in ja_entries

                    searchable = [key, mod_name, source_value]
                    if ja_value is not None:
                        searchable.append(ja_value)
                    if source_file:
                        searchable.append(source_file.name)
                    if target_file:
                        searchable.append(Path(target_file).name)
                    if not any(q in str(v).casefold() for v in searchable if v is not None):
                        continue

                    shown_file = source_file if missing and source_file else (ja["path"] if ja else target_file)
                    shown_value = "【未訳】" if missing else (ja_value or "")
                    iid = f"r{count}"
                    self.search_result_map[iid] = {
                        "target_file": Path(target_file) if target_file else None,
                        "source_file": Path(source_file) if source_file else None,
                        "key": key,
                        "value": "" if missing else (ja_value or ""),
                        "source_value": source_value,
                        "source_lang": src_lang,
                        "mod_name": mod_name,
                        "missing": missing,
                    }
                    self.search_tree.insert("", "end", iid=iid, values=(mod_name, self._localization_display_path(shown_file) if shown_file else "", key, shown_value[:180]))
                    count += 1
                    if missing:
                        missing_count += 1

        self.search_summary_var.set(f"{game}: {scanned_mods} Modを検索 / {count}件一致（未訳 {missing_count}件）")

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
            self.search_selected_var.set(f"{mod_name} / {key} / 未訳  原文: {src}  → 日本語: {dst}")
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
            messagebox.showerror(APP_NAME, "日本語ファイルの保存先を特定できませんでした。")
            return
        value = self.search_edit_text.get("1.0", "end-1c")
        try:
            if row.get("missing"):
                core.upsert_localization_values(Path(target_file), {key: value}, "japanese")
            elif not core.update_localization_value(Path(target_file), key, value):
                raise RuntimeError("対象キーをファイル内で更新できませんでした")
            row["value"] = value
            row["missing"] = False
            self.search_result_map[sel[0]] = row
            self.search_tree.item(sel[0], values=(mod_name, self._localization_display_path(target_file), key, value[:180]))
            self.search_selected_var.set(f"{mod_name} / {self._localization_display_path(target_file)} / {key}")
            self.search_summary_var.set(f"保存しました: {key}")
        except Exception as e:
            record_error("翻訳検索から直接訂正", e)
            messagebox.showerror(APP_NAME, str(e))

    # ---------------- QA/editor ----------------
    def pick_review_file(self,var):
        p=filedialog.askopenfilename(filetypes=[("Paradox YAML","*.yml"),("All","*")])
        if p: var.set(p)

    def load_review(self):
        dst=Path(self.review_dst_var.get())
        if not dst.exists(): messagebox.showerror(APP_NAME,"訳文ファイルを選択してください。"); return
        try:
            _,self.review_target_entries,_=core.parse_localization_file(dst)
            src=Path(self.review_src_var.get()) if self.review_src_var.get() else None
            if src and src.exists():
                self.review_source_lang,self.review_source_entries,_=core.parse_localization_file(src)
            else:
                self.review_source_lang="english"; self.review_source_entries={}
            self.run_review_qa()
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def run_review_qa(self):
        if not self.review_target_entries and self.review_dst_var.get():
            try: _,self.review_target_entries,_=core.parse_localization_file(Path(self.review_dst_var.get()))
            except Exception as e: messagebox.showerror(APP_NAME,str(e)); return
        self.review_issues=core.qa_entries(self.review_target_entries,self.review_source_entries or None,self.review_source_lang,core.load_glossary(Path(self.glossary_path_var.get())) if self.glossary_path_var.get() else {})
        self.review_issue_by_key={}
        for issue in self.review_issues: self.review_issue_by_key.setdefault(issue["key"],[]).append(issue)
        errs=sum(x["severity"]=="error" for x in self.review_issues); warns=sum(x["severity"]=="warning" for x in self.review_issues)
        self.qa_summary_var.set(f"QA: エラー {errs} / 警告 {warns} / キー {len(self.review_target_entries)}")
        self.populate_review(True)

    def populate_review(self,warnings_only):
        for x in self.review_tree.get_children(): self.review_tree.delete(x)
        self.review_tree_key_map={}
        keys=sorted(self.review_target_entries)
        if self.review_source_entries:
            keys=sorted(set(keys)|set(self.review_source_entries))

        parents={}
        type_parents={}
        def ensure_parent(group,label):
            if group not in parents:
                parents[group]=self.review_tree.insert("","end",iid=f"qa_group_{group}",text=label,open=True,values=("",""))
            return parents[group]
        def ensure_type(group,typ):
            k=(group,typ)
            if k not in type_parents:
                parent=ensure_parent(group,{"error":"エラー","warning":"警告","ok":"問題なし"}[group])
                type_parents[k]=self.review_tree.insert(parent,"end",text=typ,open=True,values=(typ,""))
            return type_parents[k]

        leaf_no=0
        for key in keys:
            issues=self.review_issue_by_key.get(key,[])
            if warnings_only and not issues:
                continue
            if issues:
                group="error" if any(i["severity"]=="error" for i in issues) else "warning"
                types=sorted(set(i["type"] for i in issues)) or ["その他"]
                for typ in types:
                    parent=ensure_type(group,typ)
                    iid=f"qa_leaf_{leaf_no}"; leaf_no+=1
                    self.review_tree.insert(parent,"end",iid=iid,text="",values=(typ,key))
                    self.review_tree_key_map[iid]=key
            else:
                parent=ensure_parent("ok","問題なし")
                iid=f"qa_leaf_{leaf_no}"; leaf_no+=1
                self.review_tree.insert(parent,"end",iid=iid,text="",values=("",key))
                self.review_tree_key_map[iid]=key

    def _selected_review_key(self):
        for iid in self.review_tree.selection():
            key=getattr(self,"review_tree_key_map",{}).get(iid)
            if key:
                return key
        return None

    def on_review_select(self,_=None):
        key=self._selected_review_key()
        if not key: return
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
        key=self._selected_review_key()
        if not key:
            messagebox.showinfo(APP_NAME, "用語集へ保存する項目をQA / 比較編集の一覧から選択してください。")
            return
        src=(self.review_source_entries.get(key,"") or "").strip()
        dst=self.dst_text.get("1.0","end-1c").strip()
        if not src:
            messagebox.showinfo(APP_NAME, "選択した項目に原文がありません。")
            return
        if not dst:
            messagebox.showinfo(APP_NAME, "日本語訳を入力してから用語集へ保存してください。")
            return
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        gl=core.load_glossary(p)
        old=gl.get(src)
        if old is not None and old != dst:
            if not messagebox.askyesno(
                APP_NAME,
                f"この原文はすでに用語集に登録されています。\n\n原文: {src}\n現在: {old}\n新規: {dst}\n\n手動用語として上書きしますか？",
            ):
                return
        gl[src]=dst
        core.save_glossary(p,gl)
        self.glossary_path_var.set(str(p))
        # QA / 比較編集から明示的に保存した語は「手動用語」として扱う。
        variants=self._glossary_variant_metadata()
        variants.pop(src,None)
        core.save_json(core.glossary_variants_path(p),variants)
        self.load_glossary_ui(silent=True)
        self.progress_text.set(f"手動用語を保存: {src} → {dst}")
        messagebox.showinfo(APP_NAME, f"手動用語として用語集へ保存しました。\n\n{src} → {dst}")

    def restore_source_to_target(self):
        key=self._selected_review_key()
        if key:
            self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",self.review_source_entries.get(key,""))

    def ai_proofread_selected(self):
        key=self._selected_review_key()
        if not key: return
        text=self.dst_text.get("1.0","end-1c"); src=self.review_source_entries.get(key,"")
        self.issue_text.set("AI校正中…（上部のLLM動作表示から停止できます）")
        self.llm_operation = "AI誤字脱字校正"
        self.proofread_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("proofread_progress",p)))
        def work():
            try:
                glossary=core.load_glossary(Path(self.glossary_path_var.get())) if self.glossary_path_var.get() else {}
                out=core.proofread_text(self.url_var.get(),self.model_var.get(),text,src,glossary,self.preset_var.get(),self.provider_var.get(),self.api_key_var.get().strip(),controller=self.proofread_controller)
                self.events.put(("proofread",out))
            except core.StopRequested:
                self.events.put(("proofread_stopped",None))
            except Exception as e: self.events.put(("proofread_error",str(e)))
        threading.Thread(target=work,daemon=True).start()

    def bulk_unify_review_terms(self):
        src = Path(self.review_src_var.get()) if self.review_src_var.get() else None
        dst = Path(self.review_dst_var.get()) if self.review_dst_var.get() else None
        if not src or not src.exists() or not dst or not dst.exists():
            messagebox.showinfo(APP_NAME, "先にQA / 比較編集で原文と日本語訳を読み込んでください。")
            return
        term_issues=[x for x in self.review_issues if x.get("type")=="term_mismatch"]
        if not term_issues:
            messagebox.showinfo(APP_NAME, "現在のQA結果に用語不一致はありません。")
            return
        if not messagebox.askyesno(APP_NAME, f"用語集の自動用語候補を使って、用語不一致 {len(term_issues)}件を一括統一しますか？\n\n既知の表記揺れだけを安全に置換します。判定できない箇所は変更しません。"):
            return
        try:
            result=core.bulk_unify_qa_terms(dst, src, Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY))
            self.load_review()
            messagebox.showinfo(APP_NAME, f"用語統一が完了しました。\n変更: {result.get('changed',0)}件\n自動置換できなかった候補: {result.get('skipped',0)}件")
        except Exception as exc:
            record_error("QA用語一括統一", exc)
            messagebox.showerror(APP_NAME, str(exc))

    def _auto_glossary_pairs_from_origin(self, origin):
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
                pairs.extend(self._collect_qa_diff_pairs(Path(item.get("input","")), Path(item.get("output",""))))
            return pairs
        if origin == "chinese":
            sels=list(self.chinese_queue_tree.selection()) if hasattr(self,"chinese_queue_tree") else []
            if not sels:
                return []
            for iid in sels:
                try: item=self.chinese_queue_items[int(str(iid).replace("zh_",""))]
                except Exception: continue
                pairs.extend(self._collect_qa_diff_pairs(Path(item.get("input","")), Path(item.get("output","")), source_langs=("simp_chinese",)))
            return pairs
        return []

    def start_auto_glossary_generation(self, origin):
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME, "用語取り込み中です。完了してから自動用語作成を実行してください。")
            return
        if self.auto_glossary_controller is not None:
            messagebox.showinfo(APP_NAME, "自動用語作成はすでに実行中です。")
            return
        pairs=self._auto_glossary_pairs_from_origin(origin)
        if not pairs:
            if origin == "review":
                msg="QA / 比較編集で原文と日本語訳を読み込んでください。"
            elif origin == "diff":
                msg="差分調査で原文と日本語訳を読み込んでください。"
            else:
                msg="対象キューから翻訳済み項目を選択してください。"
            messagebox.showinfo(APP_NAME,msg); return
        self.auto_glossary_status_var.set(f"自動用語作成中: {len(pairs)}ファイル組")
        self.llm_operation="自動用語作成"
        self.auto_glossary_controller=core.TranslationController(progress_callback=lambda p:self.events.put(("auto_glossary_progress",p)))
        settings={"provider":self.provider_var.get(),"url":self.url_var.get().strip(),"model":self.model_var.get().strip(),"preset":self.preset_var.get(),"api_key":self.api_key_var.get().strip()}
        glossary_path=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        def work():
            try:
                candidates=core.build_auto_glossary_candidates(pairs)
                if candidates:
                    candidates=core.resolve_auto_glossary_conflicts(settings["provider"],settings["url"],settings["model"],candidates,settings["preset"],settings["api_key"],self.auto_glossary_controller)
                result=core.save_auto_glossary_candidates(glossary_path,candidates,preserve_existing=True)
                self.events.put(("auto_glossary_done",result))
            except core.StopRequested:
                self.events.put(("auto_glossary_error","停止しました"))
            except Exception as exc:
                self.events.put(("auto_glossary_error",str(exc)))
        threading.Thread(target=work,daemon=True).start()

    # ---------------- glossary ----------------
    def _glossary_variant_metadata(self):
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        data=core.load_json(core.glossary_variants_path(p), {})
        return data if isinstance(data,dict) else {}

    def _glossary_kind_label(self, meta):
        kind=str((meta or {}).get("source_kind", "auto"))
        if kind.startswith("base:"):
            return "ゲーム本体: "+kind.split(":",1)[1]
        if kind.startswith("import:file"):
            return "日本語YAML"
        if kind.startswith("import:mod"):
            return "日本語化Mod"
        return "自動生成"

    def _choose_game_for_glossary_import(self):
        result={"game":None}
        win=tk.Toplevel(self); win.title("ゲーム本体から用語を取り込む"); win.transient(self); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=12); frm.pack(fill="both",expand=True)
        ttk.Label(frm,text="用語を取り込むゲームを選択してください。").pack(anchor="w")
        var=tk.StringVar(value=next(iter(core.PARADOX_STEAM_GAMES)))
        combo=ttk.Combobox(frm,textvariable=var,values=list(core.PARADOX_STEAM_GAMES),state="readonly",width=32); combo.pack(fill="x",pady=(8,10))
        row=ttk.Frame(frm); row.pack(fill="x")
        def ok(): result["game"]=var.get(); win.destroy()
        ttk.Button(row,text="キャンセル",command=win.destroy).pack(side="right")
        ttk.Button(row,text="選択",command=ok).pack(side="right",padx=(0,6))
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
        chosen=filedialog.askdirectory(title=f"{game} のゲーム本体 localization / localisation フォルダを選択")
        return Path(chosen) if chosen else None

    def _choose_glossary_import_mode(self):
        result={"mode":None}
        win=tk.Toplevel(self); win.title("用語取り込みモード"); win.transient(self); win.grab_set(); win.resizable(False,False)
        frm=ttk.Frame(win,padding=12); frm.pack(fill="both",expand=True)
        ttk.Label(frm,text="取り込む用語の範囲を選択してください。",font=("TkDefaultFont",10,"bold")).pack(anchor="w")
        var=tk.StringVar(value="common")
        ttk.Radiobutton(frm,text="共通名のみ取り込み",variable=var,value="common").pack(anchor="w",pady=(10,0))
        ttk.Label(frm,text="制度名・官職名・UI語など再利用しやすい短い用語を取り込み、人物名・地名・王朝名・「〇〇公爵」「〇〇軍管区長官」のような固有名詞付き候補を除外します。",wraplength=560,justify="left",foreground="#555").pack(anchor="w",padx=(22,0),pady=(2,6))
        ttk.Radiobutton(frm,text="すべて取り込み",variable=var,value="all").pack(anchor="w")
        ttk.Label(frm,text="英語または簡体字中国語と対応付けできた項目を、長い文や固有名詞を含め原則すべて候補にします。",wraplength=560,justify="left",foreground="#555").pack(anchor="w",padx=(22,0),pady=(2,8))
        ttk.Label(frm,text="※ ゲーム本体の日本語訳なら、［ゲーム本体から取り込む］で英語 / 簡体字中国語の対応原文を自動照合して用語集を作成できます。\n日本語化Mod単独の場合も、対応原文が近くになければゲーム本体との照合を案内します。",wraplength=560,justify="left",foreground="#8a5a00").pack(anchor="w",pady=(4,8))
        row=ttk.Frame(frm); row.pack(fill="x",pady=(4,0))
        def ok(): result["mode"]=var.get(); win.destroy()
        ttk.Button(row,text="キャンセル",command=win.destroy).pack(side="right")
        ttk.Button(row,text="取り込み",command=ok).pack(side="right",padx=(0,6))
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

    def _start_glossary_import_thread(self, worker, status="用語取り込みをバックグラウンドで開始しました…"):
        if self.auto_glossary_controller is not None:
            messagebox.showinfo(APP_NAME,"自動用語作成中です。完了してから用語取り込みを実行してください。")
            return False
        if self.glossary_import_busy or (self.glossary_import_thread and self.glossary_import_thread.is_alive()):
            messagebox.showinfo(APP_NAME,"用語取り込みはすでにバックグラウンドで実行中です。")
            return False
        self._set_glossary_import_busy(True,status)
        self.glossary_import_target_path=str(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        def run():
            try:
                worker()
            except Exception as exc:
                record_error("用語集バックグラウンド取り込み",exc)
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

    def _align_japanese_with_base_root(self, japanese_targets, root: Path):
        source_maps, source_files=self._collect_base_source_maps(Path(root))
        jp_entries={}; jp_files=0
        for target in japanese_targets:
            data,count=self._collect_japanese_entries_from_target(Path(target))
            jp_entries.update(data); jp_files += count
        records=[]; english_count=0; chinese_count=0; unmatched=0
        for key,dst in jp_entries.items():
            if key in source_maps["english"]:
                records.append({"key":key,"source_text":source_maps["english"][key],"target_text":dst,"source_lang":"english"}); english_count += 1
            elif key in source_maps["simp_chinese"]:
                records.append({"key":key,"source_text":source_maps["simp_chinese"][key],"target_text":dst,"source_lang":"simp_chinese"}); chinese_count += 1
            else:
                unmatched += 1
        return {"records":records,"japanese_keys":len(jp_entries),"japanese_files":jp_files,"english":english_count,"chinese":chinese_count,"unmatched":unmatched,"source_files":source_files,"root":Path(root)}

    def _start_japanese_glossary_import(self, targets, source_kind, label, mode):
        targets=[Path(x) for x in targets if Path(x).exists()]
        if not targets:
            return
        def worker():
            self.events.put(("glossary_import_status","用語取り込み中: 日本語localizationを確認しています…"))
            valid=[]
            for target in targets:
                if target.is_file():
                    if target.suffix.lower() not in {".yml",".yaml"}: continue
                    try: lang,_,_=core.parse_localization_file(target)
                    except Exception: continue
                    if lang != "japanese": continue
                elif not target.is_dir():
                    continue
                valid.append(target)
            if not valid:
                self.events.put(("glossary_import_done",{"label":label,"invalid":True}))
                return
            all_pairs=[]; seen=set()
            total=len(valid)
            for idx,target in enumerate(valid,1):
                self.events.put(("glossary_import_status",f"用語取り込み中: {idx}/{total} — {target.name}"))
                if target.is_file():
                    source_root=target.parent; cur=target.parent
                    for _ in range(8):
                        if cur.name.lower()=="japanese": source_root=cur.parent; break
                        if cur.parent==cur: break
                        cur=cur.parent
                    pairs=self._collect_qa_diff_pairs(source_root,target,source_langs=("english","simp_chinese"))
                else:
                    loc=core.mod_localization_root(target) or target
                    pairs=self._collect_qa_diff_pairs(loc,loc,source_langs=("english","simp_chinese"))
                for pair in pairs:
                    ident=(str(pair.get("source","")),str(pair.get("target","")))
                    if ident not in seen:
                        seen.add(ident); all_pairs.append(pair)
            if all_pairs:
                self.events.put(("glossary_import_status",f"用語候補を作成中: {len(all_pairs)}ファイル組"))
                candidates=core.build_import_glossary_candidates(all_pairs,source_kind=source_kind,mode=mode)
                self._finish_import_candidates_in_worker(candidates,label)
                return
            self.events.put(("glossary_import_needs_fallback",{"targets":[str(x) for x in valid],"source_kind":source_kind,"label":label,"mode":mode}))
        self._start_glossary_import_thread(worker)

    def _start_japanese_base_fallback(self, targets, root, game, source_kind, label, mode):
        def worker():
            self.events.put(("glossary_import_status",f"{game} 本体の原文と日本語キーを照合中…"))
            aligned=self._align_japanese_with_base_root(targets,Path(root))
            stats={k:aligned[k] for k in ("japanese_keys","english","chinese","unmatched")}
            if not aligned["records"]:
                self.events.put(("glossary_import_done",{"label":label,"empty":True,"stats":stats,"all_unmatched":True}))
                return
            candidates=core.build_import_glossary_candidates_from_records(aligned["records"],source_kind=source_kind,mode=mode)
            suffix="共通名のみ" if mode=="common" else "すべて"
            self._finish_import_candidates_in_worker(candidates,f"{label}（{game} / {suffix}）",stats=stats)
        self._start_glossary_import_thread(worker,status=f"{game} 本体と照合する用語取り込みを開始しました…")

    def _collect_japanese_entries_from_target(self, target: Path):
        target=Path(target)
        files=[target] if target.is_file() else core.gather_yml_files(target)
        entries={}
        used_files=0
        for f in files:
            try:
                lang, data, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang != "japanese":
                continue
            used_files += 1
            entries.update(data)
        return entries, used_files

    def _collect_base_source_maps(self, root: Path):
        maps={"english":{},"simp_chinese":{}}
        files={"english":0,"simp_chinese":0}
        for f in core.gather_yml_files(Path(root)):
            try:
                lang, data, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang in maps:
                maps[lang].update(data)
                files[lang] += 1
        return maps, files

    def _align_japanese_with_base_game(self, japanese_targets, game):
        root=self._find_base_game_localization_root(game)
        if not root or not Path(root).exists():
            return None
        source_maps, source_files=self._collect_base_source_maps(Path(root))
        jp_entries={}
        jp_files=0
        for target in japanese_targets:
            data, count=self._collect_japanese_entries_from_target(Path(target))
            jp_entries.update(data); jp_files += count

        records=[]; english_count=0; chinese_count=0; unmatched=0
        # Prefer English when both exist, then fall back to Simplified Chinese.
        for key, dst in jp_entries.items():
            if key in source_maps["english"]:
                records.append({"key":key,"source_text":source_maps["english"][key],"target_text":dst,"source_lang":"english"})
                english_count += 1
            elif key in source_maps["simp_chinese"]:
                records.append({"key":key,"source_text":source_maps["simp_chinese"][key],"target_text":dst,"source_lang":"simp_chinese"})
                chinese_count += 1
            else:
                unmatched += 1
        return {
            "records":records,"japanese_keys":len(jp_entries),"japanese_files":jp_files,
            "english":english_count,"chinese":chinese_count,"unmatched":unmatched,
            "source_files":source_files,"root":Path(root),
        }

    def _save_imported_glossary_candidates(self, candidates, label, stats=None):
        if not candidates:
            msg="取り込み可能な用語候補が見つかりませんでした。"
            if stats:
                msg += f"\n\n日本語キー: {stats.get('japanese_keys',0)}件\n英語対応: {stats.get('english',0)}件\n中国語対応: {stats.get('chinese',0)}件\n対応なし: {stats.get('unmatched',0)}件"
            messagebox.showinfo(APP_NAME,msg)
            return
        result=core.save_auto_glossary_candidates(Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY),candidates,preserve_existing=True)
        self.load_glossary_ui(silent=True)
        self.auto_glossary_status_var.set(f"{label}: {result.get('added',0)}件追加 / 候補 {result.get('total',0)}件")
        lines=[f"{label}が完了しました。",f"候補: {result.get('total',0)}件",f"新規追加: {result.get('added',0)}件"]
        if stats:
            lines += ["",f"日本語キー: {stats.get('japanese_keys',0)}件",f"英語対応: {stats.get('english',0)}件",f"中国語対応: {stats.get('chinese',0)}件",f"対応なし: {stats.get('unmatched',0)}件"]
            if stats.get('unmatched',0):
                lines.append(f"ゲーム本体に対応原文がないため {stats.get('unmatched',0)}件をスキップしました。")
        messagebox.showinfo(APP_NAME,"\n".join(lines))

    def _save_imported_glossary_pairs(self, pairs, source_kind, label, mode="common"):
        if not pairs:
            messagebox.showinfo(APP_NAME,"原文（英語/簡体字中国語）と日本語を対応付けられるlocalizationが見つかりませんでした。\n\n日本語だけでは原語→日本語の用語集を作れません。英語または簡体字中国語の対応原文が必要です。")
            return
        try:
            candidates=core.build_import_glossary_candidates(pairs,source_kind=source_kind,mode=mode)
            self._save_imported_glossary_candidates(candidates,label)
        except Exception as exc:
            record_error("用語集取り込み",exc)
            messagebox.showerror(APP_NAME,str(exc))

    def _import_japanese_targets_with_fallback(self, targets, source_kind, label):
        targets=[Path(x) for x in targets if Path(x).exists()]
        if not targets:
            return
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,"用語取り込みはすでにバックグラウンドで実行中です。")
            return
        mode=self._choose_glossary_import_mode()
        if not mode:
            return
        self._start_japanese_glossary_import(targets,source_kind,label,mode)

    def import_glossary_from_base_game(self):
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,"用語取り込みはすでにバックグラウンドで実行中です。")
            return
        game=self._choose_game_for_glossary_import()
        if not game: return
        mode=self._choose_glossary_import_mode()
        if not mode: return
        root=self._find_base_game_localization_root(game)
        if not root or not Path(root).exists(): return
        source_kind=f"base:{game}"
        label=f"{game} 本体からの用語取り込み"
        def worker():
            self.events.put(("glossary_import_status",f"{game} 本体localizationを走査中…"))
            pairs=self._collect_qa_diff_pairs(Path(root),Path(root),source_langs=("english","simp_chinese"))
            self.events.put(("glossary_import_status",f"用語候補を作成中: {len(pairs)}ファイル組"))
            candidates=core.build_import_glossary_candidates(pairs,source_kind=source_kind,mode=mode) if pairs else []
            self._finish_import_candidates_in_worker(candidates,label)
        self._start_glossary_import_thread(worker,status=f"{game} 本体からの用語取り込みを開始しました…")

    def import_glossary_from_japanese_source(self, kind):
        if self.glossary_import_busy:
            messagebox.showinfo(APP_NAME,"用語取り込みはすでにバックグラウンドで実行中です。")
            return
        if kind=="file":
            raw=filedialog.askopenfilename(title="日本語localization YAMLを選択",filetypes=[("YAML","*.yml *.yaml"),("All files","*")])
        else:
            raw=filedialog.askdirectory(title="日本語化Modまたは localization フォルダを選択")
        if not raw: return
        source_kind="import:file" if kind=="file" else "import:mod"
        label="日本語YAMLからの用語取り込み" if kind=="file" else "日本語化Modからの用語取り込み"
        self._import_japanese_targets_with_fallback([Path(raw)],source_kind,label)

    def _collect_glossary_import_pairs_from_path(self, target: Path):
        """Backward-compatible local pairing helper used by older workflows."""
        target=Path(target)
        if not target.exists(): return []
        if target.is_file():
            if target.suffix.lower() not in {".yml",".yaml"}: return []
            try: lang,_,_=core.parse_localization_file(target)
            except Exception: return []
            if lang != "japanese": return []
            source_root=target.parent; cur=target.parent
            for _ in range(8):
                if cur.name.lower()=="japanese": source_root=cur.parent; break
                if cur.parent==cur: break
                cur=cur.parent
            return self._collect_qa_diff_pairs(source_root,target,source_langs=("english","simp_chinese"))
        loc=core.mod_localization_root(target) or target
        return self._collect_qa_diff_pairs(loc,loc,source_langs=("english","simp_chinese"))

    def on_glossary_import_drop_paths(self,event):
        if self.glossary_import_busy:
            self.auto_glossary_status_var.set("用語取り込みはすでにバックグラウンドで実行中です。")
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
            self._import_japanese_targets_with_fallback(targets,"import:dnd",f"ドラッグ＆ドロップからの用語取り込み（{len(targets)}項目）")
        else:
            messagebox.showinfo(APP_NAME,"取り込み可能な日本語YAML / 日本語化Mod / localizationフォルダを確認できませんでした。")
        if ignored and targets:
            self.auto_glossary_status_var.set(f"DnD: 対象 {len(targets)}件 / 対象外 {len(ignored)}件")
        return event.action if hasattr(event,"action") else None

    def pick_glossary(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json"),("All","*")])
        if p: self.glossary_path_var.set(p); self.load_glossary_ui(silent=True)

    def load_glossary_ui(self,silent=False):
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        gl=core.load_glossary(p)
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
        if not silent: self.progress_text.set(f"用語集 {len(gl)}件を読み込みました")

    def save_glossary_ui(self):
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        gl={}
        if hasattr(self,"glossary_tree"):
            for iid in self.glossary_tree.get_children():
                vals=self.glossary_tree.item(iid,"values")
                if len(vals)>=2: gl[str(vals[0])]=str(vals[1])
        if hasattr(self,"auto_glossary_tree"):
            for iid in self.auto_glossary_tree.get_children():
                vals=self.auto_glossary_tree.item(iid,"values")
                if len(vals)>=2: gl[str(vals[0])]=str(vals[1])
        core.save_glossary(p,gl); self.glossary_path_var.set(str(p)); self.progress_text.set(f"用語集保存: {p}")

    def add_glossary_term(self):
        src=simpledialog.askstring("用語追加","原語（英語/中国語）")
        if not src: return
        dst=simpledialog.askstring("用語追加",f"「{src}」の固定日本語訳")
        if dst:
            # 手動追加した語は自動分類メタデータから外し、左側へ表示する。
            p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
            variants=self._glossary_variant_metadata(); variants.pop(src,None); core.save_json(core.glossary_variants_path(p),variants)
            self.glossary_tree.insert("","end",values=(src,dst)); self.save_glossary_ui(); self.load_glossary_ui(silent=True)

    def edit_glossary_term(self):
        sel=self.glossary_tree.selection()
        if not sel: return
        src,dst=self.glossary_tree.item(sel[0],"values")
        nsrc=simpledialog.askstring("用語編集","原語",initialvalue=src)
        if not nsrc: return
        ndst=simpledialog.askstring("用語編集","日本語",initialvalue=dst)
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
        meta = f"{received} / {provider} / {model} / {len(content):,}文字"
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
        preview = content if len(content) <= 8000 else "…（前半省略）…\n" + content[-8000:]
        widget.insert("1.0", preview)
        widget.see("end")
        widget.config(state="disabled")

    def _clear_llm_response(self, monitor=False):
        if monitor:
            self.monitor_llm_last_response = ""
            self.monitor_llm_response_meta = "応答待機中"
            self.monitor_response_meta_var.set("応答待機中")
            widget = self.monitor_response_text
        else:
            self.translation_llm_last_response = ""
            self.translation_llm_response_meta = "応答待機中"
            self.translation_response_meta_var.set("応答待機中")
            widget = self.translation_response_text
        widget.config(state="normal"); widget.delete("1.0", "end"); widget.config(state="disabled")

    def _open_llm_response_window(self, monitor=False):
        content = self.monitor_llm_last_response if monitor else self.translation_llm_last_response
        meta = self.monitor_llm_response_meta if monitor else self.translation_llm_response_meta
        if not content:
            messagebox.showinfo(APP_NAME, "まだLLM応答はありません。")
            return
        win = tk.Toplevel(self)
        win.title(("探索用" if monitor else "翻訳用") + "LLM 応答全文")
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
            op=self.llm_operation or "LLM処理"
            self.llm_status_var.set(f"● LLM 動作中 — {op}")
            self.llm_detail_var.set(f"{provider} / {model} — 応答を待っています")
            self.llm_stop_btn.config(state="normal")
            self.after(250,self._update_llm_elapsed)
        elif state=="retry":
            self.llm_status_var.set(f"● LLM 再試行中 — {self.llm_operation or 'LLM処理'}")
            self.llm_detail_var.set(f"{provider} / {model} — 再試行 {payload.get('attempt',0)}/{payload.get('retries',0)}")
        elif state=="end":
            self.llm_active_ids.discard(activity_id)
            self.llm_busy_count=len(self.llm_active_ids)
            if self.llm_busy_count==0:
                self._set_llm_idle("LLM 待機中", "直前のLLM処理が終了しました")

    def _update_llm_elapsed(self):
        if self.llm_busy_count<=0 or self.llm_busy_since is None: return
        import time
        secs=max(0,int(time.time()-self.llm_busy_since))
        base=self.llm_detail_var.get().split(" / 経過 ")[0]
        self.llm_detail_var.set(f"{base} / 経過 {secs}秒")
        self.after(1000,self._update_llm_elapsed)

    def _set_llm_idle(self,status="LLM 待機中",detail="LLM処理は実行されていません"):
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
        if self.benchmark_controller and getattr(self,"benchmark_worker",None) and self.benchmark_worker.is_alive():
            self.stop_benchmark(); return
        if self.diff_controller:
            self.diff_controller.request_stop(save=False)
            self.diff_message_var.set("差分翻訳の停止を要求しました。現在のLLM応答完了後に停止します。")
            self.llm_detail_var.set("停止要求済み — 現在のAPI/LLM応答完了を待っています")
            return
        if self.proofread_controller:
            self.proofread_controller.request_stop(save=False)
            self.issue_text.set("AI校正の停止を要求しました。現在のLLM応答完了後に停止します。")
            self.llm_detail_var.set("停止要求済み — 現在のAPI/LLM応答完了を待っています")

    # ---------------- monitor/research LLM activity ----------------
    def _handle_monitor_llm_activity(self, payload, operation="未翻訳Mod探索"):
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
            self.monitor_llm_status_var.set(f"● 探索用LLM 動作中 — {operation}")
            modtxt = f" / {self.monitor_current_mod}" if self.monitor_current_mod else ""
            self.monitor_llm_detail_var.set(f"{provider} / {model}{modtxt} — 応答待ち")
            self.monitor_llm_stop_btn.config(state="normal")
            self.after(500, self._update_monitor_llm_elapsed)
        elif state == "retry":
            self.monitor_llm_status_var.set(f"● 探索用LLM 再試行中 — {operation}")
            self.monitor_llm_detail_var.set(f"{provider} / {model} — 再試行 {payload.get('attempt',0)}/{payload.get('retries',0)}")
        elif state == "end":
            self.monitor_llm_active_ids.discard(activity_id)
            if not self.monitor_llm_active_ids:
                self._set_monitor_llm_idle("探索用LLM 待機中", "LLM精査は終了しました。Mod調査は継続する場合があります")

    def _update_monitor_llm_elapsed(self):
        if not self.monitor_llm_active_ids or self.monitor_llm_busy_since is None:
            return
        import time
        secs=max(0,int(time.time()-self.monitor_llm_busy_since))
        base=self.monitor_llm_detail_var.get().split(" / 経過 ")[0]
        self.monitor_llm_detail_var.set(f"{base} / 経過 {secs}秒")
        self.after(1000,self._update_monitor_llm_elapsed)

    def _set_monitor_scan_status(self, text, detail=""):
        if self.monitor_llm_active_ids:
            return
        self.monitor_llm_banner.config(bg="#dbeafe")
        self.monitor_llm_status_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_detail_label.config(bg="#dbeafe",fg="#1e3a8a")
        self.monitor_llm_status_var.set(text)
        self.monitor_llm_detail_var.set(detail or "未翻訳Modを機械的に調査しています")
        self.monitor_llm_stop_btn.config(state="normal" if (self.mod_research_thread and self.mod_research_thread.is_alive()) or (self.monitor_thread and self.monitor_thread.is_alive()) else "disabled")

    def _set_monitor_llm_idle(self, status="探索用LLM 待機中", detail="未翻訳Modの探索・精査は実行されていません"):
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
        self.monitor_llm_status_var.set("探索停止要求済み")
        self.monitor_llm_detail_var.set("現在の探索用LLM応答が終わり次第、安全に停止します")

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
        try:
            while True:
                kind,payload=self.events.get_nowait()
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
                    self.connection_var.set(f"{self.provider_var.get()} 接続済み / {len(payload)}モデル")
                elif kind=="model_error":
                    p=self.provider_var.get()
                    if p=="Ollama": self.connection_var.set("Ollamaが起動していません（接続できません）")
                    elif p=="LM Studio": self.connection_var.set("LM Studio Local Serverに接続できません")
                    elif p in {"OpenAI","Anthropic","Gemini"}: self.connection_var.set(f"{p} APIに接続できません。APIキー・モデル・利用権限を確認してください")
                    else: self.connection_var.set("OpenAI互換APIに接続できません。URL/APIキーを確認してください")
                elif kind=="monitor_models":
                    for combo_name in ("monitor_model_combo", "status_monitor_model_combo"):
                        combo=getattr(self,combo_name,None)
                        if combo is not None:
                            combo["values"]=payload
                    if payload and self.monitor_model_var.get() not in payload:
                        self.monitor_model_var.set(payload[0])
                    self.monitor_connection_var.set(f"監視用LLM: {self.monitor_provider_var.get()} 接続済み / {len(payload)}モデル")
                    self._save_llm_preferences()
                elif kind=="monitor_model_error":
                    p=self.monitor_provider_var.get()
                    if p=="Ollama": msg="Ollamaが起動していません"
                    elif p=="LM Studio": msg="LM Studio Local Serverに接続できません"
                    else: msg=f"{p}に接続できません"
                    self.monitor_connection_var.set("監視用LLM: "+msg)
                elif kind=="progress":
                    if payload.get("kind")=="llm_activity":
                        self._handle_llm_activity(payload,"翻訳")
                    elif payload.get("kind")=="llm_response":
                        self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric":
                        self._record_metric(payload.get("metric"))
                    elif payload.get("kind")=="batch":
                        done,total=payload.get("done",0),max(1,payload.get("total",1)); self.progress["value"]=done/total*100
                        self.progress_text.set(f"キュー {self.current_queue_index+1}/{len(self.queue_items)} / ファイル {payload.get('file_no',0)}/{payload.get('file_total',0)} / {done}/{total}行")
                    elif payload.get("kind")=="file_done": self.progress["value"]=100
                elif kind=="chinese_queue_status":
                    idx,status=payload
                    if 0 <= idx < len(self.chinese_queue_items):
                        self.chinese_queue_items[idx]["status"]=status
                        self._refresh_chinese_queue_tree()
                elif kind=="chinese_queue_current":
                    i,total,name=payload
                    self.chinese_queue_index=i-1
                    self.chinese_progress_var.set(f"キュー {i}/{total} — {name}")
                    self._append_chinese_log(f"開始: {name} ({i}/{total})")
                elif kind=="chinese_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"中国語基準翻訳")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                    elif payload.get("kind")=="batch":
                        done,total=payload.get("done",0),max(1,payload.get("total",1)); self.chinese_progress["value"]=done/total*100
                        self.chinese_progress_var.set(f"キュー {self.chinese_queue_index+1}/{len(self.chinese_queue_items)} / ファイル {payload.get('file_no',0)}/{payload.get('file_total',0)} / {done}/{total}行")
                        self._append_chinese_log(f"翻訳中: {Path(payload.get('file','')).name} — {done}/{total}行")
                    elif payload.get("kind")=="file_done":
                        self._append_chinese_log(f"完了: {Path(payload.get('file','')).name}")
                elif kind=="chinese_done":
                    self.chinese_worker=None; self.chinese_controller=None
                    self.chinese_start_btn.config(state="normal"); self.chinese_diff_start_btn.config(state="normal"); self.chinese_pause_btn.config(state="disabled", text="一時停止"); self.chinese_stop_btn.config(state="disabled")
                    if payload.get("interrupted"):
                        self.chinese_progress_var.set("中断しました（キャッシュ保存済み）")
                        self._set_llm_idle("LLM 待機中","中国語基準翻訳を中断しました")
                    else:
                        self.chinese_progress["value"]=100
                        qa_e=payload.get('qa_errors',0); qa_w=payload.get('qa_warnings',0)
                        self.chinese_progress_var.set(f"完了 — {payload.get('processed_files',0)}/{payload.get('queue_total',len(self.chinese_queue_items))}項目 / QA error {qa_e}・warning {qa_w}")
                        self._append_chinese_log(f"翻訳語QA: error {qa_e} / warning {qa_w}")
                        self._append_chinese_log(f"出力先: {payload.get('output',self.chinese_output_var.get())}")
                        self._set_llm_idle("LLM 待機中","中国語基準翻訳が完了しました")
                        source_notice=self._source_gap_notice_for_items(self.chinese_queue_items)
                        msg=f"中国語基準翻訳が完了しました。\n翻訳語QA: error {qa_e} / warning {qa_w}"
                        if source_notice:
                            msg += "\n\n" + source_notice
                        messagebox.showinfo(APP_NAME,msg)
                elif kind=="chinese_error":
                    record_error("中国語基準翻訳", detail=str(payload)); self.chinese_worker=None; self.chinese_controller=None
                    self.chinese_start_btn.config(state="normal"); self.chinese_diff_start_btn.config(state="normal"); self.chinese_pause_btn.config(state="disabled", text="一時停止"); self.chinese_stop_btn.config(state="disabled")
                    self.chinese_progress_var.set("エラー")
                    self._append_chinese_log("エラー: "+str(payload)); self._set_llm_idle("LLM 待機中","中国語基準翻訳でエラーが発生しました")
                    messagebox.showerror(APP_NAME,"中国語基準翻訳エラー: "+str(payload))
                elif kind=="benchmark_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"モデル速度テスト")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="benchmark_model_start":
                    i,total,model=payload
                    self.benchmark_status_var.set(f"速度テスト中 {i}/{total} — {model}")
                    self.llm_operation=f"モデル速度テスト {i}/{total}"
                elif kind=="benchmark_metric":
                    i,total,metric=payload
                    self.benchmark_status_var.set(f"速度テスト中 {i}/{total} 完了 — 次のモデルを準備")
                elif kind=="benchmark_error":
                    i,total,model,err=payload; self.benchmark_status_var.set(f"{model} 失敗 ({i}/{total})")
                    self._append_log(f"[速度テスト失敗] {model}: {err}")
                elif kind=="benchmark_done":
                    self.benchmark_status_var.set("速度テスト完了"); self.benchmark_stop_btn.config(state="disabled"); self.benchmark_controller=None; self._set_llm_idle("LLM 待機中","速度テストが完了しました")
                elif kind=="benchmark_stopped":
                    self.benchmark_status_var.set("速度テストを停止しました"); self.benchmark_stop_btn.config(state="disabled"); self.benchmark_controller=None; self._set_llm_idle("LLM 待機中","速度テストを停止しました")
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
                        self.mod_discovery_status_var.set(f"{len(self.detected_mod_locations)}か所検出")
                        preferred_idx=next((i for i,row in enumerate(self.detected_mod_locations) if int(row.get("mod_count",0) or 0)>0),0)
                        first=f"loc_{preferred_idx}"
                        if self.discovered_mod_tree.exists(first):
                            self.discovered_mod_tree.selection_set(first); self.discovered_mod_tree.focus(first); self.discovered_mod_tree.see(first)
                            self._sync_monitor_targets_from_discovery_selection()
                    else:
                        self.mod_discovery_status_var.set("自動検出できませんでした — 手動選択を使用してください")
                elif kind=="mod_locations_error":
                    self.mod_discovery_status_var.set("自動検出エラー")
                    self._append_log("[Mod場所自動検出] "+str(payload))
                elif kind=="monitor_progress":
                    if payload.get("kind")=="llm_activity": self._handle_monitor_llm_activity(payload,"未翻訳監視")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=True)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="monitor_status":
                    self.monitor_status_var.set(payload)
                elif kind=="monitor_log":
                    self._append_log("[未翻訳監視] "+str(payload))
                elif kind=="monitor_results":
                    for x in self.monitor_tree.get_children(): self.monitor_tree.delete(x)
                    counts={}
                    for i,c in enumerate(payload):
                        counts[c.get("kind","")]=counts.get(c.get("kind",""),0)+1
                        text=(c.get("target") or c.get("source") or "").replace("\n"," ")
                        fp=c.get("target_file") or c.get("source_file") or c.get("logical_file","")
                        self.monitor_tree.insert("","end",iid=str(i),values=(c.get("kind",""),c.get("confidence",""),Path(fp).name if fp else "",c.get("key",""),text[:500]))
                    summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                    self.monitor_summary_var.set(f"未翻訳候補: {len(payload)}"+(f"　({summary})" if summary else ""))
                    self.monitor_status_var.set(f"● 常時監視中 — 最終確認 {datetime.now().strftime('%H:%M:%S')}")
                elif kind=="monitor_stopped":
                    self.monitor_status_var.set("○ 監視停止中")
                    if hasattr(self,"monitor_toggle_btn"):
                        self.monitor_toggle_btn.config(text="常時監視を開始", state="normal")
                    self.monitor_thread=None
                    self._set_monitor_llm_idle("探索用LLM 待機中","未翻訳監視を終了しました")
                elif kind=="monitor_error":
                    record_error("未翻訳監視", detail=str(payload))
                    self.monitor_status_var.set("監視エラー")
                    if hasattr(self,"monitor_toggle_btn"):
                        self.monitor_toggle_btn.config(text="常時監視を開始", state="normal")
                    self.monitor_thread=None
                    messagebox.showerror(APP_NAME,"未翻訳監視エラー: "+payload)
                elif kind=="mod_status_results":
                    self.mod_research_results=[]
                    self._populate_mod_status_tree()
                    self.mod_status_summary_var.set("調査結果: 0件")
                elif kind=="mod_status_append":
                    self.mod_research_results.append(payload)
                    self._populate_mod_status_tree()
                    counts={}
                    for r in self.mod_research_results: counts[r.get("status","")]=counts.get(r.get("status",""),0)+1
                    summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                    self.mod_status_summary_var.set(f"調査結果: {len(self.mod_research_results)}件"+(f"　{summary}" if summary else ""))
                elif kind=="mod_research_progress":
                    i,total,name=payload
                    self.monitor_current_mod=name
                    self.mod_status_summary_var.set(f"バックグラウンド調査中: {i}/{total} — {name}")
                    self._set_monitor_scan_status(f"● 未翻訳Mod探索中 — {i}/{total}", f"現在調査中: {name}")
                elif kind=="mod_research_done":
                    self.mod_research_stop_btn.config(state="disabled"); self.mod_research_thread=None
                    if self.mod_research_stop_event.is_set():
                        self.mod_status_summary_var.set(f"調査を停止しました — {len(self.mod_research_results)}件確認")
                    else:
                        counts={}
                        for r in self.mod_research_results: counts[r.get("status","")]=counts.get(r.get("status",""),0)+1
                        summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
                        self.mod_status_summary_var.set(f"調査完了: {len(self.mod_research_results)}件"+(f"　{summary}" if summary else ""))
                    self._set_monitor_llm_idle("探索用LLM 待機中","Mod翻訳状況の調査が完了しました")
                elif kind=="mod_research_error":
                    record_error("Mod翻訳状況調査", detail=str(payload))
                    self.mod_research_stop_btn.config(state="disabled"); self.mod_research_thread=None
                    self.mod_status_summary_var.set("調査エラー")
                    self._set_monitor_llm_idle("探索用LLM 待機中","Mod調査でエラーが発生しました")
                    messagebox.showerror(APP_NAME,"Mod翻訳状況の調査エラー: "+payload)
                elif kind=="queue_refresh": self._refresh_queue_tree()
                elif kind=="done":
                    self.worker=None
                    self._delete_session()
                    self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳が完了しました"); self.progress["value"]=100; self.progress_text.set("すべての翻訳が完了しました"); self._refresh_queue_tree()
                    source_notice=self._source_gap_notice_for_items(self.queue_items)
                    msg="翻訳キューが完了しました。"
                    if source_notice:
                        msg += "\n\n" + source_notice
                    messagebox.showinfo(APP_NAME,msg)
                elif kind=="fatal":
                    self.worker=None
                    record_error("翻訳処理 fatal", detail=str(payload)); self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳処理でエラーが発生しました"); messagebox.showerror(APP_NAME,payload)
                elif kind=="diff_translate_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"差分翻訳")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="diff_translate_status":
                    i,total,key=payload; self.diff_message_var.set(f"差分翻訳中 {i}/{total} — {key}")
                elif kind=="diff_translate_done":
                    self.diff_controller=None; self._set_llm_idle("LLM 待機中",f"差分翻訳 {payload}件が完了しました"); self.load_diff_inspector(); self.diff_message_var.set(f"差分翻訳完了: {payload}件")
                elif kind=="diff_translate_stopped":
                    self.diff_controller=None; self._set_llm_idle("LLM 待機中","差分翻訳を停止しました"); self.diff_message_var.set("差分翻訳を停止しました")
                elif kind=="diff_translate_error":
                    record_error("差分翻訳", detail=str(payload)); self.diff_controller=None; self._set_llm_idle("LLM 待機中","差分翻訳でエラーが発生しました"); self.diff_message_var.set("差分翻訳エラー: "+str(payload)); messagebox.showerror(APP_NAME,"差分翻訳エラー: "+str(payload))
                elif kind=="auto_glossary_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"自動用語作成")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="auto_glossary_done":
                    self.auto_glossary_controller=None
                    self._set_llm_idle("LLM 待機中","自動用語作成が完了しました")
                    self.load_glossary_ui(silent=True)
                    self.auto_glossary_status_var.set(f"追加 {payload.get('added',0)} / 候補 {payload.get('total',0)} / 表記揺れ {payload.get('conflicts',0)}")
                    messagebox.showinfo(APP_NAME, f"自動用語作成が完了しました。\n候補: {payload.get('total',0)}件\n新規追加: {payload.get('added',0)}件\n複数訳を統一: {payload.get('conflicts',0)}件")
                elif kind=="auto_glossary_error":
                    self.auto_glossary_controller=None
                    self._set_llm_idle("LLM 待機中","自動用語作成を終了しました")
                    self.auto_glossary_status_var.set("自動用語作成: "+str(payload))
                    if str(payload)!="停止しました": messagebox.showerror(APP_NAME,"自動用語作成エラー: "+str(payload))
                elif kind=="glossary_import_status":
                    self.auto_glossary_status_var.set(str(payload))
                elif kind=="glossary_import_needs_fallback":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,"対応原文をゲーム本体から探せます")
                    messagebox.showinfo(APP_NAME,
                        "選択した日本語localizationの近くに、対応する英語 / 簡体字中国語原文が見つかりませんでした。\n\n"
                        "対象ゲーム本体のlocalizationを同じキーで自動照合できます。ゲーム本体に存在しないMod独自キーはスキップされます。")
                    game=self._choose_game_for_glossary_import()
                    if game:
                        root=self._find_base_game_localization_root(game)
                        if root and Path(root).exists():
                            self._start_japanese_base_fallback(
                                [Path(x) for x in payload.get("targets",[])],root,game,
                                payload.get("source_kind","import:mod"),payload.get("label","日本語localizationからの用語取り込み"),payload.get("mode","common"))
                elif kind=="glossary_import_done":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,"用語取り込み完了")
                    if payload.get("invalid"):
                        messagebox.showinfo(APP_NAME,"取り込み可能な日本語localizationを確認できませんでした。")
                    else:
                        label=payload.get("label","用語取り込み")
                        result=payload.get("result") or {}
                        stats=payload.get("stats") or {}
                        if not result:
                            lines=[f"{label}が完了しました。","取り込み可能な用語候補はありませんでした。"]
                        else:
                            self.load_glossary_ui(silent=True)
                            self.auto_glossary_status_var.set(f"{label}: {result.get('added',0)}件追加 / 候補 {result.get('total',0)}件")
                            lines=[f"{label}が完了しました。",f"候補: {result.get('total',0)}件",f"新規追加: {result.get('added',0)}件"]
                        if stats:
                            lines += ["",f"日本語キー: {stats.get('japanese_keys',0)}件",f"英語対応: {stats.get('english',0)}件",f"中国語対応: {stats.get('chinese',0)}件",f"対応なし: {stats.get('unmatched',0)}件"]
                            if stats.get("unmatched",0): lines.append(f"ゲーム本体に対応原文がないため {stats.get('unmatched',0)}件をスキップしました。")
                        messagebox.showinfo(APP_NAME,"\n".join(lines))
                elif kind=="glossary_import_error":
                    self.glossary_import_thread=None
                    self._set_glossary_import_busy(False,"用語取り込みエラー")
                    messagebox.showerror(APP_NAME,"用語取り込みエラー: "+str(payload))
                elif kind=="proofread_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"AI誤字脱字校正")
                    elif payload.get("kind")=="llm_response": self._show_llm_response(payload, monitor=False)
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="proofread":
                    self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",payload); self.issue_text.set("AI校正結果を表示しました。内容を確認して保存してください。"); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正が完了しました")
                elif kind=="proofread_stopped":
                    self.issue_text.set("AI校正を停止しました。"); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正を停止しました")
                elif kind=="proofread_error":
                    record_error("AI校正", detail=str(payload))
                    self.issue_text.set("AI校正エラー: "+payload); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正でエラーが発生しました")
        except queue.Empty: pass
        self.after(100,self._poll_events)

    def _finish_controls(self):
        self.start_btn.config(state="normal"); self.diff_start_btn.config(state="normal"); self.pause_btn.config(state="disabled",text="一時停止"); self.stop_btn.config(state="disabled"); self.controller=None

    def on_close(self):
        """Handle the window × button according to the user's preference."""
        self._save_llm_preferences()
        setting = self.close_action_var.get()

        if setting == "毎回確認":
            action = self._show_close_choice_dialog()
        elif setting == "最小化":
            action = "minimize"
        else:
            action = "quit"

        if action == "cancel":
            return
        if action == "minimize":
            self.iconify()
            return
        self._perform_app_exit()



if __name__ == "__main__":
    app=App(); app.mainloop()
