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
APP_VERSION = "0.7.6"


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
    global SAVED_STEAM_ROOTS_PATH, LOG_ROOT, MOD_STATUS_CACHE_PATH
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
    for d in (DATA_ROOT, APP_HOME, OUTPUT_ROOT, CACHE_ROOT, BACKUP_ROOT, LOG_ROOT):
        d.mkdir(parents=True, exist_ok=True)


DATA_ROOT = _automatic_data_root()
_configure_data_root(DATA_ROOT)


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
        initial_w = min(1540, max(1220, int(screen_w * 0.96)))
        initial_h = min(1120, max(900, int(screen_h * 0.96)))
        initial_w = min(initial_w, max(960, screen_w - 24))
        initial_h = min(initial_h, max(760, screen_h - 48))
        self.geometry(f"{initial_w}x{initial_h}")
        self.minsize(min(1080, max(920, screen_w - 80)),
                     min(780, max(700, screen_h - 120)))
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
        self.translation_llm_last_response = ""
        self.monitor_llm_last_response = ""
        self.translation_llm_response_meta = "応答待機中"
        self.monitor_llm_response_meta = "応答待機中"

        self.provider_var = tk.StringVar(value="Ollama")
        self.api_key_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value=core.DEFAULT_OLLAMA_URL)
        self.model_var = tk.StringVar(value=core.DEFAULT_MODEL)
        self.preset_var = tk.StringVar(value="CK3")
        self.batch_var = tk.IntVar(value=40)
        self.workers_var = tk.IntVar(value=1)
        self.performance_preset_var = tk.StringVar(value="標準（40 / 1）")
        self.repair_var = tk.BooleanVar(value=True)
        self.dual_var = tk.BooleanVar(value=False)
        self.autoqa_var = tk.BooleanVar(value=True)
        self.glossary_path_var = tk.StringVar(value=str(DEFAULT_GLOSSARY))
        self.connection_var = tk.StringVar(value="LLM接続確認中…")
        self.profile_var = tk.StringVar(value="")
        self.data_root_var = tk.StringVar(value=str(DATA_ROOT))
        self.progress_text = tk.StringVar(value="待機中")
        self.review_src_var = tk.StringVar()
        self.review_dst_var = tk.StringVar()
        self.qa_summary_var = tk.StringVar(value="QA未実行")

        # Difference inspector / translation search
        self.diff_src_var = tk.StringVar(value="")
        self.diff_dst_var = tk.StringVar(value="")
        self.diff_summary_var = tk.StringVar(value="差分未調査")
        self.diff_source_entries = {}
        self.diff_target_entries = {}
        self.diff_rows = []
        self.diff_row_by_key = {}
        self.diff_controller: core.TranslationController | None = None
        self.search_path_var = tk.StringVar(value="")
        self.search_query_var = tk.StringVar(value="")
        self.search_summary_var = tk.StringVar(value="検索待機中")
        self.search_result_map = {}

        # Live untranslated-localization monitor
        self.monitor_path_var = tk.StringVar(value="")
        self.monitor_interval_var = tk.IntVar(value=15)
        self.monitor_use_llm_var = tk.BooleanVar(value=True)
        self.monitor_check_translation_mods_var = tk.BooleanVar(value=True)
        self.monitor_provider_var = tk.StringVar(value="Ollama")
        self.monitor_url_var = tk.StringVar(value=core.DEFAULT_OLLAMA_URL)
        self.monitor_api_key_var = tk.StringVar(value="")
        self.monitor_model_var = tk.StringVar(value="")
        self.monitor_connection_var = tk.StringVar(value="監視用LLM: 未確認")
        self.monitor_status_var = tk.StringVar(value="監視停止中")
        self.monitor_summary_var = tk.StringVar(value="未翻訳候補: --")
        self.mod_status_summary_var = tk.StringVar(value="調査結果: --")
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
        self.mod_status_cache_lock = threading.Lock()
        self.mod_status_cache = core.load_json(MOD_STATUS_CACHE_PATH, {"version": 1, "items": {}})
        if not isinstance(self.mod_status_cache, dict):
            self.mod_status_cache = {"version": 1, "items": {}}
        self.report_callback_exception = self._tk_callback_exception
        sys.excepthook = self._sys_excepthook
        if hasattr(threading, "excepthook"):
            threading.excepthook = self._thread_excepthook

        self._build_ui()
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

        self.llm_banner = tk.Frame(self, bg="#e5e7eb", padx=12, pady=7)
        self.llm_banner.pack(fill="x", padx=10, pady=(2, 2))
        self.llm_status_label = tk.Label(self.llm_banner, textvariable=self.llm_status_var, bg="#e5e7eb", fg="#222222", font=("", 12, "bold"))
        self.llm_status_label.pack(side="left")
        self.llm_detail_label = tk.Label(self.llm_banner, textvariable=self.llm_detail_var, bg="#e5e7eb", fg="#444444")
        self.llm_detail_label.pack(side="left", padx=(14, 0))
        self.llm_stop_btn = ttk.Button(self.llm_banner, text="現在のLLM処理を停止", command=self.stop_current_llm, state="disabled")
        self.llm_stop_btn.pack(side="right")

        self.monitor_llm_banner = tk.Frame(self, bg="#dbeafe", padx=12, pady=7)
        self.monitor_llm_banner.pack(fill="x", padx=10, pady=(0, 2))
        self.monitor_llm_status_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_status_var, bg="#dbeafe", fg="#1e3a8a", font=("", 11, "bold"))
        self.monitor_llm_status_label.pack(side="left")
        self.monitor_llm_detail_label = tk.Label(self.monitor_llm_banner, textvariable=self.monitor_llm_detail_var, bg="#dbeafe", fg="#1e3a8a")
        self.monitor_llm_detail_label.pack(side="left", padx=(14, 0))
        self.monitor_llm_stop_btn = ttk.Button(self.monitor_llm_banner, text="探索用LLM/調査を停止", command=self.stop_monitor_llm, state="disabled")
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
        self.translation_response_text = tk.Text(tr_frame, height=4, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.translation_response_text.pack(fill="x", pady=(4,0))

        mon_frame = ttk.LabelFrame(response_row, text="探索用LLM 最新応答（読み取り専用）", padding=5)
        mon_frame.pack(side="left", fill="both", expand=True, padx=(5, 0))
        mon_head = ttk.Frame(mon_frame); mon_head.pack(fill="x")
        self.monitor_response_meta_var = tk.StringVar(value="応答待機中")
        ttk.Label(mon_head, textvariable=self.monitor_response_meta_var, foreground="#555").pack(side="left")
        ttk.Button(mon_head, text="全文を開く", command=lambda:self._open_llm_response_window(True)).pack(side="right")
        ttk.Button(mon_head, text="クリア", command=lambda:self._clear_llm_response(True)).pack(side="right", padx=(0,5))
        self.monitor_response_text = tk.Text(mon_frame, height=4, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.monitor_response_text.pack(fill="x", pady=(4,0))

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=8)
        self.notebook = nb
        self.tab_translate = ttk.Frame(nb, padding=10)
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
        self._build_review_tab()
        self._build_diff_tab()
        self._build_search_tab()
        self._build_glossary_tab()
        self._build_models_tab()
        self._build_monitor_tab()
        self._build_status_tab()
        self._build_settings_tab()
        self._build_help_tab()

    def _build_translate_tab(self):
        t = self.tab_translate
        settings = ttk.LabelFrame(t, text="LLM / 翻訳設定", padding=8); settings.pack(fill="x")
        for c in (1,3,5): settings.columnconfigure(c, weight=1)
        ttk.Label(settings, text="プロバイダ").grid(row=0,column=0,sticky="w")
        provider_combo=ttk.Combobox(settings,textvariable=self.provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=12)
        provider_combo.grid(row=0,column=1,sticky="w",padx=(5,10)); provider_combo.bind("<<ComboboxSelected>>",lambda e:self.on_provider_change())
        ttk.Label(settings, text="URL").grid(row=0,column=2,sticky="e")
        ttk.Entry(settings,textvariable=self.url_var).grid(row=0,column=3,sticky="ew",padx=(5,10))
        ttk.Button(settings,text="接続確認",command=self.refresh_models).grid(row=0,column=4,padx=(0,12))
        ttk.Label(settings,text="モデル").grid(row=0,column=5,sticky="e")
        self.model_combo=ttk.Combobox(settings,textvariable=self.model_var,state="normal")
        self.model_combo.grid(row=0,column=6,sticky="ew",padx=(5,0))

        ttk.Label(settings,text="プリセット").grid(row=1,column=0,sticky="w",pady=(8,0))
        ttk.Combobox(settings,textvariable=self.preset_var,values=list(core.GAME_PRESETS),state="readonly",width=14).grid(row=1,column=1,sticky="w",padx=(5,10),pady=(8,0))
        ttk.Label(settings,text="モデルプロファイル").grid(row=1,column=2,sticky="e",pady=(8,0))
        self.profile_combo=ttk.Combobox(settings,textvariable=self.profile_var,state="readonly")
        self.profile_combo.grid(row=1,column=3,sticky="ew",padx=(5,5),pady=(8,0))
        ttk.Button(settings,text="適用",command=self.apply_selected_profile).grid(row=1,column=4,pady=(8,0))
        ttk.Button(settings,text="現在設定を保存",command=self.save_current_profile).grid(row=1,column=5,columnspan=2,sticky="e",pady=(8,0))

        ttk.Checkbutton(settings,text="既存日本語の未翻訳を修復",variable=self.repair_var).grid(row=2,column=0,columnspan=2,sticky="w",pady=(8,0))
        ttk.Checkbutton(settings,text="英語＋簡体字中国語を併用",variable=self.dual_var).grid(row=2,column=2,columnspan=2,sticky="w",pady=(8,0))
        ttk.Checkbutton(settings,text="翻訳後に自動QA",variable=self.autoqa_var).grid(row=2,column=4,columnspan=2,sticky="w",pady=(8,0))
        ttk.Label(settings,text="APIキー").grid(row=3,column=0,sticky="w",pady=(8,0))
        ttk.Entry(settings,textvariable=self.api_key_var,show="•").grid(row=3,column=1,columnspan=3,sticky="ew",padx=(5,10),pady=(8,0))
        ttk.Label(settings,text="クラウドAPIのみ。保存されません / 環境変数も利用可",foreground="#666").grid(row=3,column=4,columnspan=3,sticky="w",pady=(8,0))
        ttk.Label(settings,text="バッチ").grid(row=4,column=0,sticky="w",pady=(8,0))
        ttk.Spinbox(settings,from_=1,to=500,textvariable=self.batch_var,width=7).grid(row=4,column=1,sticky="w",pady=(8,0))
        ttk.Label(settings,text="並列").grid(row=4,column=2,sticky="w",pady=(8,0))
        ttk.Spinbox(settings,from_=1,to=8,textvariable=self.workers_var,width=7).grid(row=4,column=3,sticky="w",pady=(8,0))
        ttk.Label(settings,text="おすすめ設定").grid(row=4,column=4,sticky="e",pady=(8,0))
        perf_combo = ttk.Combobox(settings,textvariable=self.performance_preset_var,
                                  values=["安定重視（20 / 1）","標準（40 / 1）","高速（60 / 2）"],
                                  state="readonly",width=18)
        perf_combo.grid(row=4,column=5,sticky="w",padx=(5,4),pady=(8,0))
        ttk.Button(settings,text="適用",command=self.apply_performance_preset).grid(row=4,column=6,pady=(8,0))

        ttk.Label(settings,text="用語集").grid(row=5,column=0,sticky="w",pady=(8,0))
        ttk.Entry(settings,textvariable=self.glossary_path_var).grid(row=5,column=1,columnspan=3,sticky="ew",padx=(5,10),pady=(8,0))
        ttk.Button(settings,text="選択",command=self.pick_glossary).grid(row=5,column=4,sticky="w",pady=(8,0))
        ttk.Label(settings,
                  text="目安: バッチ20–60 / 並列1–2を推奨。バッチ80超は注意、120超は非推奨。ローカルLLMの並列3以上は不安定になりやすいです。",
                  foreground="#8a5a00").grid(row=5,column=5,columnspan=2,sticky="w",pady=(8,0))
        self.apply_current_translation_btn = ttk.Button(settings, text="現在の翻訳へ設定を適用", command=self.apply_settings_to_current_translation)
        self.apply_current_translation_btn.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8,0))
        ttk.Label(settings, text="翻訳中は次の安全なバッチ境界から反映します。モデル変更時も以降のキャッシュを分離します。", foreground="#555").grid(row=6, column=2, columnspan=5, sticky="w", pady=(8,0))
        qf = ttk.LabelFrame(t,text="複数翻訳キュー（上から順番に処理）",padding=8); qf.pack(fill="both",expand=True,pady=(10,0))
        toolbar=ttk.Frame(qf); toolbar.pack(fill="x",pady=(0,6))
        add_menu = tk.Menu(toolbar, tearoff=False)
        add_menu.add_command(label="YAMLファイルを追加", command=self.add_files)
        add_menu.add_command(label="Mod / localizationフォルダを追加", command=self.add_folder)
        self.add_menu_button = ttk.Menubutton(toolbar, text="追加", menu=add_menu)
        self.add_menu_button.pack(side="left")
        ttk.Button(toolbar,text="選択削除",command=self.remove_queue).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="全消去",command=self.clear_queue).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="完成した日本語化をModへ上書き",command=self.overwrite_selected_translation_to_mod).pack(side="left",padx=(12,0))
        ttk.Button(toolbar,text="選択項目の出力先変更",command=self.change_output).pack(side="left",padx=(14,0))
        ttk.Button(toolbar,text="キャッシュを見る",command=self.view_selected_cache).pack(side="left",padx=(14,0))
        ttk.Button(toolbar,text="キャッシュを追加",command=self.import_cache_to_selected).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="差分更新を再検出",command=self.detect_diff_for_selected).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="セッション読込",command=self.restore_session).pack(side="right")
        ttk.Button(toolbar,text="セッション保存",command=self.save_session).pack(side="right",padx=(0,6))

        self.drop_hint = ttk.Label(qf, text="ここへYAMLファイル / localizationフォルダをドラッグ＆ドロップできます" if DND_AVAILABLE else "ドラッグ＆ドロップ機能を利用できません（tkinterdnd2未読込）", foreground="#666")
        self.drop_hint.pack(fill="x", pady=(0,6))

        cols=("input","output","status")
        self.queue_tree=ttk.Treeview(qf,columns=cols,show="headings",height=12)
        self.queue_tree.heading("input",text="入力")
        self.queue_tree.heading("output",text="出力")
        self.queue_tree.heading("status",text="状態")
        self.queue_tree.column("input",width=430); self.queue_tree.column("output",width=430); self.queue_tree.column("status",width=130,anchor="center")
        ys=ttk.Scrollbar(qf,orient="vertical",command=self.queue_tree.yview); self.queue_tree.configure(yscrollcommand=ys.set)
        self.queue_tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y")
        if DND_AVAILABLE:
            try:
                self.queue_tree.drop_target_register(DND_FILES)
                self.queue_tree.dnd_bind("<<Drop>>", self.on_drop_paths)
                self.drop_hint.drop_target_register(DND_FILES)
                self.drop_hint.dnd_bind("<<Drop>>", self.on_drop_paths)
            except Exception as e:
                self.drop_hint.config(text=f"ドラッグ＆ドロップ初期化失敗: {e}")

        actions=ttk.Frame(t); actions.pack(fill="x",pady=(10,0))
        self.start_btn=ttk.Button(actions,text="翻訳開始",command=self.start_queue); self.start_btn.pack(side="left")
        self.pause_btn=ttk.Button(actions,text="一時停止",command=self.toggle_pause,state="disabled"); self.pause_btn.pack(side="left",padx=(7,0))
        self.stop_btn=ttk.Button(actions,text="セーブして中断",command=self.save_and_stop,state="disabled"); self.stop_btn.pack(side="left",padx=(7,0))
        ttk.Button(actions,text="出力を開く",command=self.open_selected_output).pack(side="left",padx=(7,0))
        ttk.Label(actions,textvariable=self.progress_text).pack(side="right")
        self.progress=ttk.Progressbar(t,mode="determinate",maximum=100); self.progress.pack(fill="x",pady=(7,7))

        lf=ttk.LabelFrame(t,text="ログ",padding=6); lf.pack(fill="both",expand=False)
        lbar=ttk.Frame(lf); lbar.pack(fill="x", pady=(0,4))
        ttk.Button(lbar,text="エラーログを開く",command=lambda:self._open_path(LOG_ROOT)).pack(side="left")
        ttk.Button(lbar,text="診断ログを収集",command=self.collect_error_logs).pack(side="left",padx=(6,0))
        self.log=tk.Text(lf,height=10,wrap="word",state="disabled")
        lsy=ttk.Scrollbar(lf,command=self.log.yview); self.log.configure(yscrollcommand=lsy.set)
        self.log.pack(side="left",fill="both",expand=True); lsy.pack(side="right",fill="y")

    def _build_review_tab(self):
        t=self.tab_review
        pf=ttk.LabelFrame(t,text="原文 / 訳文",padding=8); pf.pack(fill="x")
        pf.columnconfigure(1,weight=1)
        ttk.Label(pf,text="原文").grid(row=0,column=0,sticky="w")
        ttk.Entry(pf,textvariable=self.review_src_var).grid(row=0,column=1,sticky="ew",padx=6)
        ttk.Button(pf,text="選択",command=lambda:self.pick_review_file(self.review_src_var)).grid(row=0,column=2)
        ttk.Label(pf,text="訳文").grid(row=1,column=0,sticky="w",pady=(5,0))
        ttk.Entry(pf,textvariable=self.review_dst_var).grid(row=1,column=1,sticky="ew",padx=6,pady=(5,0))
        ttk.Button(pf,text="選択",command=lambda:self.pick_review_file(self.review_dst_var)).grid(row=1,column=2,pady=(5,0))
        ttk.Button(pf,text="比較を読み込む",command=self.load_review).grid(row=0,column=3,rowspan=2,padx=(8,0))

        qa=ttk.Frame(t); qa.pack(fill="x",pady=(8,5))
        ttk.Button(qa,text="QA再実行",command=self.run_review_qa).pack(side="left")
        ttk.Button(qa,text="警告だけ表示",command=lambda:self.populate_review(True)).pack(side="left",padx=(6,0))
        ttk.Button(qa,text="全キー表示",command=lambda:self.populate_review(False)).pack(side="left",padx=(6,0))
        ttk.Label(qa,textvariable=self.qa_summary_var).pack(side="right")

        paned=ttk.Panedwindow(t,orient="horizontal"); paned.pack(fill="both",expand=True)
        left=ttk.Frame(paned); right=ttk.Frame(paned); paned.add(left,weight=2); paned.add(right,weight=3)
        self.review_tree=ttk.Treeview(left,columns=("level","type","key"),show="headings")
        for c,txt,w in (("level","重要度",65),("type","種別",100),("key","キー",330)):
            self.review_tree.heading(c,text=txt); self.review_tree.column(c,width=w)
        self.review_tree.bind("<<TreeviewSelect>>",self.on_review_select)
        rys=ttk.Scrollbar(left,command=self.review_tree.yview); self.review_tree.configure(yscrollcommand=rys.set)
        self.review_tree.pack(side="left",fill="both",expand=True); rys.pack(side="right",fill="y")

        ttk.Label(right,text="原文").pack(anchor="w")
        self.src_text=tk.Text(right,height=7,wrap="word"); self.src_text.pack(fill="x",pady=(2,8))
        ttk.Label(right,text="訳文（編集可）").pack(anchor="w")
        self.dst_text=tk.Text(right,height=10,wrap="word"); self.dst_text.pack(fill="both",expand=True,pady=(2,6))
        self.issue_text=tk.StringVar(value="")
        ttk.Label(right,textvariable=self.issue_text,wraplength=550).pack(fill="x",pady=(0,6))
        eb=ttk.Frame(right); eb.pack(fill="x")
        ttk.Button(eb,text="この訳を保存",command=self.save_review_value).pack(side="left")
        ttk.Button(eb,text="AIで誤字脱字校正",command=self.ai_proofread_selected).pack(side="left",padx=(6,0))
        ttk.Button(eb,text="原文に戻す",command=self.restore_source_to_target).pack(side="left",padx=(6,0))

    def _build_diff_tab(self):
        t = self.tab_diff
        pf = ttk.LabelFrame(t, text="英語 / 日本語ファイル", padding=8); pf.pack(fill="x")
        pf.columnconfigure(1, weight=1)
        ttk.Label(pf, text="英語・原文").grid(row=0, column=0, sticky="w")
        ttk.Entry(pf, textvariable=self.diff_src_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(pf, text="選択", command=lambda:self.pick_review_file(self.diff_src_var)).grid(row=0, column=2)
        ttk.Label(pf, text="日本語").grid(row=1, column=0, sticky="w", pady=(5,0))
        ttk.Entry(pf, textvariable=self.diff_dst_var).grid(row=1, column=1, sticky="ew", padx=6, pady=(5,0))
        ttk.Button(pf, text="選択", command=lambda:self.pick_review_file(self.diff_dst_var)).grid(row=1, column=2, pady=(5,0))
        ttk.Button(pf, text="差分を調査", command=self.load_diff_inspector).grid(row=0, column=3, rowspan=2, padx=(8,0))

        bar = ttk.Frame(t); bar.pack(fill="x", pady=(8,5))
        ttk.Button(bar, text="選択項目を翻訳", command=lambda:self.translate_diff_items(False)).pack(side="left")
        ttk.Button(bar, text="欠落・未翻訳をまとめて翻訳", command=lambda:self.translate_diff_items(True)).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="選択訳を保存", command=self.save_diff_value).pack(side="left", padx=(6,0))
        ttk.Label(bar, textvariable=self.diff_summary_var).pack(side="right")

        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=2); paned.add(right, weight=3)
        self.diff_tree = ttk.Treeview(left, columns=("status","key"), show="headings", selectmode="extended")
        self.diff_tree.heading("status", text="状態"); self.diff_tree.column("status", width=110)
        self.diff_tree.heading("key", text="キー"); self.diff_tree.column("key", width=360)
        self.diff_tree.tag_configure("missing", background="#fee2e2")
        self.diff_tree.tag_configure("untranslated", background="#fef3c7")
        self.diff_tree.tag_configure("extra", background="#e0e7ff")
        self.diff_tree.bind("<<TreeviewSelect>>", self.on_diff_select)
        ys = ttk.Scrollbar(left, command=self.diff_tree.yview); self.diff_tree.configure(yscrollcommand=ys.set)
        self.diff_tree.pack(side="left", fill="both", expand=True); ys.pack(side="right", fill="y")

        compare = ttk.Panedwindow(right, orient="horizontal"); compare.pack(fill="both", expand=True)
        srcf = ttk.Frame(compare); dstf = ttk.Frame(compare); compare.add(srcf, weight=1); compare.add(dstf, weight=1)
        ttk.Label(srcf, text="英語 / 原文").pack(anchor="w")
        self.diff_src_text = tk.Text(srcf, wrap="word"); self.diff_src_text.pack(fill="both", expand=True, padx=(0,4), pady=(2,0))
        ttk.Label(dstf, text="日本語（直接編集可）").pack(anchor="w")
        self.diff_dst_text = tk.Text(dstf, wrap="word"); self.diff_dst_text.pack(fill="both", expand=True, padx=(4,0), pady=(2,0))
        self.diff_message_var = tk.StringVar(value="")
        ttk.Label(right, textvariable=self.diff_message_var, wraplength=650).pack(fill="x", pady=(6,0))

    def _build_search_tab(self):
        t = self.tab_search
        top = ttk.LabelFrame(t, text="翻訳ファイル検索", padding=8); top.pack(fill="x")
        top.columnconfigure(1, weight=1)
        ttk.Label(top, text="検索場所").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.search_path_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="フォルダ", command=self.pick_search_folder).grid(row=0, column=2)
        ttk.Button(top, text="YAML", command=self.pick_search_file).grid(row=0, column=3, padx=(5,0))
        ttk.Label(top, text="検索語").grid(row=1, column=0, sticky="w", pady=(6,0))
        ent = ttk.Entry(top, textvariable=self.search_query_var); ent.grid(row=1, column=1, sticky="ew", padx=6, pady=(6,0)); ent.bind("<Return>", lambda e:self.run_translation_search())
        ttk.Button(top, text="検索", command=self.run_translation_search).grid(row=1, column=2, columnspan=2, sticky="ew", pady=(6,0))

        ttk.Label(t, textvariable=self.search_summary_var).pack(anchor="w", pady=(7,4))
        paned = ttk.Panedwindow(t, orient="horizontal"); paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned); right = ttk.Frame(paned); paned.add(left, weight=3); paned.add(right, weight=2)
        self.search_tree = ttk.Treeview(left, columns=("file","key","value"), show="headings")
        for c, txt, w in (("file","ファイル",190),("key","キー",260),("value","日本語訳",350)):
            self.search_tree.heading(c, text=txt); self.search_tree.column(c, width=w)
        self.search_tree.bind("<<TreeviewSelect>>", self.on_search_select)
        ys = ttk.Scrollbar(left, command=self.search_tree.yview); self.search_tree.configure(yscrollcommand=ys.set)
        self.search_tree.pack(side="left", fill="both", expand=True); ys.pack(side="right", fill="y")
        self.search_selected_var = tk.StringVar(value="検索結果を選択してください")
        ttk.Label(right, textvariable=self.search_selected_var, wraplength=420).pack(fill="x", anchor="w")
        self.search_edit_text = tk.Text(right, wrap="word"); self.search_edit_text.pack(fill="both", expand=True, pady=(6,6))
        ttk.Button(right, text="この日本語訳を保存", command=self.save_search_value).pack(anchor="w")

    def _build_glossary_tab(self):
        t=self.tab_glossary
        top=ttk.Frame(t); top.pack(fill="x")
        ttk.Label(top,text="用語集ファイル").pack(side="left")
        ttk.Entry(top,textvariable=self.glossary_path_var).pack(side="left",fill="x",expand=True,padx=6)
        ttk.Button(top,text="読込",command=self.load_glossary_ui).pack(side="left")
        ttk.Button(top,text="保存",command=self.save_glossary_ui).pack(side="left",padx=(6,0))
        bar=ttk.Frame(t); bar.pack(fill="x",pady=8)
        ttk.Button(bar,text="用語追加",command=self.add_glossary_term).pack(side="left")
        ttk.Button(bar,text="選択削除",command=self.delete_glossary_term).pack(side="left",padx=(6,0))
        ttk.Label(bar,text="英語/中国語の語句 → 固定したい日本語訳。該当バッチのプロンプトへ自動挿入します。",foreground="#666").pack(side="left",padx=12)
        self.glossary_tree=ttk.Treeview(t,columns=("src","dst"),show="headings")
        self.glossary_tree.heading("src",text="原語"); self.glossary_tree.heading("dst",text="日本語")
        self.glossary_tree.column("src",width=400); self.glossary_tree.column("dst",width=500)
        self.glossary_tree.pack(fill="both",expand=True)
        self.glossary_tree.bind("<Double-1>",lambda e:self.edit_glossary_term())
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
            "│   └── ParadoxLocalizationTranslator_diagnostics_*.zip\n"
            "└── 設定/\n"
            "    ├── session.json\n"
            "    ├── glossary.json\n"
            "    ├── model_stats.json\n"
            "    ├── model_profiles.json\n"
            "    ├── mod_translation_status_cache.json\n"
            "    └── steam_library_roots.json\n\n"
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
            self.data_root_var.set(str(DATA_ROOT))
            self.glossary_path_var.set(str(DEFAULT_GLOSSARY))
            self.model_stats = core.load_json(STATS_PATH, {})
            self.model_profiles = core.load_json(PROFILES_PATH, {})
            self.mod_status_cache = core.load_json(MOD_STATUS_CACHE_PATH, {"version":1,"items":{}})
            if not isinstance(self.mod_status_cache, dict): self.mod_status_cache={"version":1,"items":{}}
            self.refresh_profiles_ui()
            self._restore_cached_mod_status()
            messagebox.showinfo(APP_NAME,
                "保存場所を変更しました。\n\n"
                f"{DATA_ROOT}\n\n"
                + ("既存データもコピーしました。" if ans else "今後作成するデータから新しい場所を使用します。"))
        except Exception as e:
            messagebox.showerror(APP_NAME, f"保存場所の変更に失敗しました。\n{e}")

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
        guide = """【基本的な使い方】

1. Ollama / LM Studio / クラウドAPIのいずれかを準備します。
2. 「翻訳 / キュー」タブへYAML/フォルダをドラッグ＆ドロップするか、［追加］からファイルまたはフォルダを選びます。
3. 必要ならモデル・バッチサイズ・用語集などを設定します。
4. ［翻訳開始］を押します。

【バッチ / 並列のおすすめ設定】

翻訳 / キュー画面の「おすすめ設定」から3種類を選択して［適用］できます。

・安定重視: バッチ20 / 並列1
  長文が多いMod、初回利用、メモリに余裕がない環境向け。

・標準: バッチ40 / 並列1
  通常はこちらを推奨。速度と安定性のバランスが良い設定です。

・高速: バッチ60 / 並列2
  Ollama / LM Studio側が同時2リクエストを処理でき、十分なRAM/VRAMがある場合向け。

安定性の目安:
・バッチ1～60: 通常範囲
・バッチ80超: 長文が多いファイルでは応答欠落・タイムアウトが増えやすい
・バッチ120超: 非推奨
・並列1: 最も安定
・並列2: サーバー側の並列処理が有効な場合のみ推奨
・並列3以上: ローカルLLMではVRAM/RAM圧迫、待ち行列、タイムアウトが増えやすいため非推奨

※これは固定上限ではありません。モデルの大きさ、コンテキスト長、1行の長さ、RAM/VRAM、Ollama/LM Studio側の設定で変わります。
※クラウドAPIはサービス側のレート制限を優先してください。

【出力先】

出力先は自動で決まります。
・アプリ/実行ファイルの隣に書き込める場合:
・アプリの隣へ書き込めない場合（例: macOSの /Applications）:

セッション、用語集、モデル統計などは「設定」、翻訳キャッシュは「キャッシュ」に分けて保存します。
各翻訳項目は「翻訳結果」の中に「元ファイル名_japanese」または「元フォルダ名_japanese」で作成されます。

出力先を個別に変更したい場合は、キューの対象行をクリックして選択してから［出力先変更］を押してください。
未選択の場合は案内が表示されます。

【キャッシュ管理】

各翻訳キューは、それぞれ独立したキャッシュを持ちます。
Dataフォルダ内の「キャッシュ」に翻訳ごとの専用フォルダを作成します。
［キャッシュを見る］で選択中の翻訳キャッシュを確認できます。
［キャッシュを追加］では別の translate_cache.json を選択中の翻訳へ統合できます。

【Mod更新時の差分追加翻訳】
一度翻訳したModを更新後にもう一度ドラッグ＆ドロップすると、同じ入力パスの過去キャッシュと原文スナップショットを自動検索します。
新規キー・文章が変更されたキー・削除キーを判定し、前回キャッシュを新しい専用キャッシュへ複製します。
そのため、変更されていない文章は再翻訳せず、新規・変更箇所だけLLMへ送信します。
必要なら［差分更新を再検出］で手動再判定できます。

【ドラッグ＆ドロップ】

YAMLファイルまたはlocalization/Modフォルダを翻訳キューへ直接ドロップできます。
複数ファイルの同時ドロップにも対応します。

【LLM動作表示と停止】

アプリ上部には常にLLM状態バーがあります。翻訳・速度テスト・AI校正などでLLMが推論中になると、
「● LLM 動作中」とプロバイダ、モデル、経過時間を表示します。
上部の［現在のLLM処理を停止］から、その時実行中の処理を安全に停止できます。
速度テストには専用の［速度テスト停止］ボタンもあります。
通信中のAPIリクエストそのものは途中で破棄せず、応答が返った安全な地点で停止します。

【中断と再開】

・［一時停止］: 現在のリクエスト/バッチが終わった安全な地点で停止します。
・［セーブして中断］: 状態とキャッシュを保存して終了します。次回起動時に復元できます。

【QA / 比較編集】

原文と訳文を読み込み、未翻訳、Paradox構文の破損、誤字脱字候補などを確認できます。
警告行を選択すると、原文と訳文を並べて編集できます。

【用語集】

Grand Campaign → 開辺 のような固定訳を登録できます。翻訳時に該当する語があればLLMへ自動提示されます。

【LLM接続】

・Ollama: 通常 http://localhost:11434
・LM Studio: 通常 http://localhost:1234/v1
・OpenAI / Anthropic / Gemini: APIキーを入力（キーは保存されません）
・OpenAI Compatible: OpenAI互換APIのURLとキーを指定

【既存日本語の修復】

「既存日本語の未翻訳を修復」をONにすると、l_japanese の中に残った英語なども検出して再翻訳します。

【未翻訳調査 / 常時監視】

「未翻訳監視」タブでは、通常翻訳とは別のプロバイダ・URL・モデルを監視専用LLMとして指定できます。
曖昧候補の判定だけに使うため、3B～8B級など小さなモデルを推奨します。監視機能から自動翻訳やファイル書換えは行いません。

［ゲーム/Mod場所を自動検出］: Steam WorkshopやParadoxのローカルMod保存場所を自動で探します。
［選択場所を調査対象に設定］: 自動検出一覧で選んだ場所を監視・調査対象に設定します。
［選択ゲームの全Modを調べる］: 選んだSteam Workshop/ローカルMod場所をまとめて調査します。
［指定したModをバックグラウンド調査］: 選択した1つのModをバックグラウンドで調べます。
［全部のModを調べる］: 選択した親フォルダ直下のModをまとめて調べます。
結果は新しい「翻訳状況」タブに、
「〇〇というModは日本語翻訳がありません。」
「〇〇のModに翻訳の欠損箇所があります。」
という形で一覧表示されます。

常時監視では待機中はファイルの更新時刻とサイズだけを見るため、LLMは常時動きません。更新を検知した時だけ再解析し、曖昧候補だけ監視専用LLMで精査します。

【困ったとき】

・Ollama/LM Studioが起動しているか確認
・モデルがロード/インストール済みか確認
・エラーは「ログ」フォルダへ自動収集されます。［診断ログを収集］で共有用ZIPを作成できます。
・翻訳状況一覧はキャッシュされ、次回起動時に復元されます。変更のないModは再調査せずキャッシュを使います。
・自動生成データはすべて「Paradox Localization Translator」フォルダにまとまり、［設定］から保存場所を自由に変更できます
"""
        box.insert("1.0", guide)
        box.config(state="disabled")

    def _build_monitor_tab(self):
        t = self.tab_monitor

        discovery = ttk.LabelFrame(t, text="ゲーム / Mod場所の自動検出", padding=8)
        discovery.pack(fill="x", pady=(0,8))
        dbar = ttk.Frame(discovery); dbar.pack(fill="x", pady=(0,5))
        ttk.Button(dbar, text="ゲーム/Mod場所を自動検出", command=self.discover_mod_locations).pack(side="left")
        ttk.Button(dbar, text="選択場所を調査対象に設定", command=self.use_selected_discovered_location).pack(side="left", padx=(6,0))
        ttk.Button(dbar, text="選択ゲームの全Modを調べる", command=self.research_selected_discovered_location).pack(side="left", padx=(6,0))
        ttk.Label(dbar, textvariable=self.mod_discovery_status_var).pack(side="right")
        cols=("game","kind","mods","path")
        self.discovered_mod_tree=ttk.Treeview(discovery, columns=cols, show="headings", height=4, selectmode="browse")
        for c,txt,w in (("game","ゲーム",210),("kind","種類",130),("mods","Mod数",70),("path","検出場所",650)):
            self.discovered_mod_tree.heading(c,text=txt); self.discovered_mod_tree.column(c,width=w,anchor="w")
        self.discovered_mod_tree.pack(fill="x")
        ttk.Label(discovery, text="Steamの追加ライブラリ、別ドライブ・外付けSSD、Documents/Paradox Interactive のローカルModを自動探索します。見つかったSteamライブラリは次回の探索にも再利用します。見つからない場合は下の［選択］から手動指定できます。", foreground="#555").pack(anchor="w", pady=(5,0))

        cfg = ttk.LabelFrame(t, text="ゲーム本体 / Mod の未翻訳調査・監視", padding=8)
        cfg.pack(fill="x")
        cfg.columnconfigure(1, weight=1)
        cfg.columnconfigure(4, weight=1)

        ttk.Label(cfg, text="調査対象").grid(row=0, column=0, sticky="w")
        ttk.Entry(cfg, textvariable=self.monitor_path_var).grid(row=0, column=1, columnspan=3, sticky="ew", padx=6)
        ttk.Button(cfg, text="選択", command=self.pick_monitor_path).grid(row=0, column=4, sticky="e")
        ttk.Label(cfg, text="間隔(秒)").grid(row=0, column=5, padx=(12, 4))
        ttk.Spinbox(cfg, from_=3, to=600, textvariable=self.monitor_interval_var, width=7).grid(row=0, column=6)

        ttk.Separator(cfg, orient="horizontal").grid(row=1, column=0, columnspan=7, sticky="ew", pady=8)
        ttk.Label(cfg, text="監視専用LLM", font=("", 10, "bold")).grid(row=2, column=0, sticky="w")
        ttk.Label(cfg, text="プロバイダ").grid(row=2, column=1, sticky="e")
        self.monitor_provider_combo = ttk.Combobox(
            cfg, textvariable=self.monitor_provider_var,
            values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],
            state="readonly", width=16)
        self.monitor_provider_combo.grid(row=2, column=2, sticky="w", padx=(6,10))
        self.monitor_provider_combo.bind("<<ComboboxSelected>>", lambda e:self.on_monitor_provider_change())
        ttk.Label(cfg, text="URL").grid(row=2, column=3, sticky="e")
        ttk.Entry(cfg, textvariable=self.monitor_url_var).grid(row=2, column=4, sticky="ew", padx=(6,10))
        ttk.Button(cfg, text="監視用モデル再読込", command=self.refresh_monitor_models).grid(row=2, column=5, columnspan=2, sticky="e")

        ttk.Checkbutton(cfg, text="軽量LLMで曖昧候補だけ精査", variable=self.monitor_use_llm_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8,0))
        ttk.Checkbutton(cfg, text="別Modの日本語化も検索する", variable=self.monitor_check_translation_mods_var).grid(row=3, column=5, columnspan=2, sticky="w", pady=(8,0))
        ttk.Label(cfg, text="モデル").grid(row=3, column=2, sticky="e", pady=(8,0))
        self.monitor_model_combo = ttk.Combobox(cfg, textvariable=self.monitor_model_var, state="normal")
        self.monitor_model_combo.grid(row=3, column=3, columnspan=2, sticky="ew", padx=(6,10), pady=(8,0))
        ttk.Label(cfg, text="APIキー").grid(row=4, column=0, sticky="w", pady=(6,0))
        ttk.Entry(cfg, textvariable=self.monitor_api_key_var, show="•").grid(row=4, column=1, columnspan=4, sticky="ew", padx=(6,10), pady=(6,0))
        ttk.Label(cfg, textvariable=self.monitor_connection_var).grid(row=4, column=5, columnspan=2, sticky="e", pady=(6,0))

        warning = tk.Label(
            cfg,
            text="⚠ 未翻訳調査のLLMは判定専用です。常時監視の負荷を抑えるため、3B～8B級など小さなモデルを使用してください。自動翻訳は行いません。",
            fg="#8a4b00", anchor="w", justify="left", wraplength=1050)
        warning.grid(row=5, column=0, columnspan=7, sticky="ew", pady=(8,0))

        research = ttk.LabelFrame(t, text="バックグラウンド調査", padding=8)
        research.pack(fill="x", pady=(10,6))
        ttk.Button(research, text="指定したModをバックグラウンド調査", command=self.research_selected_mod_background).pack(side="left")
        ttk.Button(research, text="全部のModを調べる", command=self.research_all_mods_background).pack(side="left", padx=(6,0))
        self.mod_research_stop_btn = ttk.Button(research, text="調査停止", command=self.stop_mod_research, state="disabled")
        self.mod_research_stop_btn.pack(side="left", padx=(6,0))
        ttk.Label(research, text="結果は『翻訳状況』タブに表示します。翻訳処理は一切実行しません。", foreground="#555").pack(side="left", padx=(12,0))

        bar = ttk.Frame(t); bar.pack(fill="x", pady=(6,6))
        self.monitor_start_btn = ttk.Button(bar, text="常時監視開始", command=self.start_monitor)
        self.monitor_start_btn.pack(side="left")
        self.monitor_stop_btn = ttk.Button(bar, text="常時監視停止", command=self.stop_monitor, state="disabled")
        self.monitor_stop_btn.pack(side="left", padx=(6,0))
        ttk.Button(bar, text="今すぐ再スキャン", command=self.monitor_scan_now).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="候補一覧を消去", command=self.clear_monitor_results).pack(side="left", padx=(6,0))
        ttk.Button(bar, text="CSV保存", command=self.export_monitor_csv).pack(side="left", padx=(6,0))
        ttk.Label(bar, textvariable=self.monitor_status_var).pack(side="right")

        ttk.Label(t, textvariable=self.monitor_summary_var, font=("", 11, "bold")).pack(anchor="w", pady=(0,6))
        cols=("kind","confidence","file","key","text")
        self.monitor_tree=ttk.Treeview(t, columns=cols, show="headings", height=12)
        for c,txt,w in (("kind","種類",130),("confidence","判定",75),("file","ファイル",260),("key","キー",260),("text","内容",430)):
            self.monitor_tree.heading(c,text=txt); self.monitor_tree.column(c,width=w,anchor="w")
        sy=ttk.Scrollbar(t,orient="vertical",command=self.monitor_tree.yview)
        sx=ttk.Scrollbar(t,orient="horizontal",command=self.monitor_tree.xview)
        self.monitor_tree.configure(yscrollcommand=sy.set,xscrollcommand=sx.set)
        self.monitor_tree.pack(fill="both",expand=True,side="top")
        sx.pack(fill="x")

        note = ttk.LabelFrame(t, text="仕組み", padding=6); note.pack(fill="x", pady=(8,0))
        ttk.Label(note, text="待機中はYAMLの更新時刻とサイズだけを確認します。変更があった時だけ解析し、曖昧候補だけ監視専用LLMへ送ります。自動翻訳・ファイル書換えは行いません。", wraplength=1050).pack(anchor="w")

    def _build_status_tab(self):
        t = self.tab_status
        top = ttk.Frame(t); top.pack(fill="x", pady=(0,8))
        ttk.Label(top, text="Modごとの日本語翻訳状況", font=("", 13, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.mod_status_summary_var).pack(side="right")

        info = ttk.LabelFrame(t, text="判定内容", padding=8); info.pack(fill="x", pady=(0,8))
        ttk.Label(
            info,
            text=(
                "元Mod内の日本語だけでなく、別の日本語化Modも確認します。\n"
                "完全翻訳か、欠落があるかを判定します。調査だけでは自動翻訳しません。\n"
                "一覧で行を選択すると、下の『選択項目の詳細』に結果と保存場所を段落表示します。"
            ),
            justify="left", wraplength=1200
        ).pack(anchor="w")

        cols=("status","mod","gaps","jpmod","jpmod_gaps")
        self.mod_status_tree=ttk.Treeview(t, columns=cols, show="headings", height=13, selectmode="extended")
        for c,txt,w in (("status","状態",145),("mod","Mod",300),("gaps","欠損",75),("jpmod","日本語化Mod",300),("jpmod_gaps","日本語化Mod欠損",125)):
            self.mod_status_tree.heading(c,text=txt); self.mod_status_tree.column(c,width=w,anchor="w")
        sy=ttk.Scrollbar(t,orient="vertical",command=self.mod_status_tree.yview)
        self.mod_status_tree.configure(yscrollcommand=sy.set)
        tree_frame=ttk.Frame(t); tree_frame.pack(fill="both",expand=True)
        self.mod_status_tree.pack(in_=tree_frame,side="left",fill="both",expand=True)
        sy.pack(in_=tree_frame,side="right",fill="y")
        self.mod_status_tree.bind("<<TreeviewSelect>>", self._on_mod_status_selection_changed)

        detail = ttk.LabelFrame(t, text="選択項目の詳細", padding=8); detail.pack(fill="x", pady=(8,0))
        self.mod_status_detail = tk.Text(detail, height=6, wrap="word", relief="flat", background=self.cget("background"))
        self.mod_status_detail.pack(fill="x", expand=False)
        self.mod_status_detail.insert("1.0", "一覧からModを選択すると、ここに調査結果・日本語化Mod・上書き先・場所を段落で表示します。")
        self.mod_status_detail.configure(state="disabled")

        bottom=ttk.Frame(t); bottom.pack(fill="x", pady=(8,0))
        ttk.Button(bottom,text="選択したModを翻訳",command=self.translate_selected_mod_from_status).pack(side="left")
        ttk.Button(bottom,text="選択Modを除外して翻訳",command=self.translate_all_except_selected_mods).pack(side="left",padx=(6,0))
        ttk.Button(bottom,text="選択Modを翻訳キューへ追加",command=lambda:self.queue_selected_mod_from_status(start_now=False)).pack(side="left",padx=(6,0))
        self.status_overwrite_btn = ttk.Button(bottom,text="完成した日本語化をModへ上書き",command=self.overwrite_selected_status_mod)
        self.status_overwrite_btn.pack(side="left",padx=(6,0))
        ttk.Separator(bottom,orient="vertical").pack(side="left",fill="y",padx=10)
        ttk.Button(bottom,text="結果を消去",command=self.clear_mod_status_results).pack(side="left")
        ttk.Button(bottom,text="キャッシュ再読込",command=self._restore_cached_mod_status).pack(side="left",padx=(6,0))
        ttk.Button(bottom,text="CSV保存",command=self.export_mod_status_csv).pack(side="left",padx=(6,0))
        ttk.Label(bottom,text="※ 上書き前に対象先を明示し、バックアップ＋二重確認します。",foreground="#a35a00").pack(side="right")

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
            return
        r = selected[0]
        mod_name = r.get("mod", "Mod")
        jpmod = r.get("external_translation_mod", "")
        jp_path = r.get("external_translation_path", "")
        lines = [f"Mod: {mod_name}", f"状態: {r.get('status','')}　欠損: {r.get('gap_count',0)}件", "", r.get("message", "")]
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

    def _selected_discovered_location(self):
        if not hasattr(self, "discovered_mod_tree"):
            return None
        sel=self.discovered_mod_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME,"自動検出されたゲーム/Mod場所を1つ選択してください。")
            return None
        try:
            idx=int(sel[0].split("_",1)[1])
            return self.detected_mod_locations[idx]
        except Exception:
            return None

    def use_selected_discovered_location(self):
        row=self._selected_discovered_location()
        if not row: return
        self.monitor_path_var.set(row.get("path",""))
        self.mod_discovery_status_var.set(f"調査対象: {row.get('game','')} / {row.get('kind','')}")

    def research_selected_discovered_location(self):
        row=self._selected_discovered_location()
        if not row: return
        path=Path(row.get("path",""))
        if not path.exists():
            messagebox.showerror(APP_NAME,"検出したMod場所が現在存在しません。再検出してください。")
            return
        self.monitor_path_var.set(str(path))
        roots=core.find_mod_roots(path)
        if not roots:
            messagebox.showinfo(APP_NAME,"この場所からlocalizationを持つModを確認できませんでした。")
            return
        self._start_mod_research(roots, replace=True)
        try: self.notebook.select(self.tab_status)
        except Exception: pass

    def on_monitor_provider_change(self):
        provider=self.monitor_provider_var.get()
        self.monitor_url_var.set(core.default_url_for_provider(provider))
        self.monitor_model_var.set("")
        self.monitor_connection_var.set("監視用LLM: 未確認")
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

    def start_monitor(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            return
        root=Path(self.monitor_path_var.get().strip())
        if not root.exists():
            messagebox.showinfo(APP_NAME,"監視するフォルダを選択してください。")
            return
        self.monitor_stop_event.clear(); self.monitor_force_event.set(); self.monitor_snapshot={}
        self.monitor_start_btn.config(state="disabled"); self.monitor_stop_btn.config(state="normal")
        self.monitor_status_var.set("監視開始中…")
        self._set_monitor_scan_status("● 未翻訳Mod監視中", "変更されたYAMLがないか確認しています")
        self.monitor_thread=threading.Thread(target=self._monitor_worker,daemon=True)
        self.monitor_thread.start()

    def stop_monitor(self):
        self.monitor_stop_event.set(); self.monitor_force_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.monitor_status_var.set("監視停止要求済み…")

    def monitor_scan_now(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_force_event.set(); self.monitor_status_var.set("再スキャン要求済み")
            return
        root=Path(self.monitor_path_var.get().strip())
        if not root.exists():
            messagebox.showinfo(APP_NAME,"監視するフォルダを選択してください。")
            return
        self.monitor_stop_event.clear(); self.monitor_force_event.set(); self.monitor_snapshot={}
        self.monitor_thread=threading.Thread(target=self._monitor_worker,args=(True,),daemon=True)
        self.monitor_thread.start()

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
        root=Path(self.monitor_path_var.get().strip())
        try:
            first=True
            while not self.monitor_stop_event.is_set():
                forced=self.monitor_force_event.is_set(); self.monitor_force_event.clear()
                stats=core.localization_file_stats(root)
                changed = first or forced or stats != self.monitor_snapshot
                if changed:
                    self.events.put(("monitor_status","解析中…"))
                    candidates=core.scan_translation_gaps(root)
                    try:
                        candidates=self._refine_candidates_with_monitor_llm(candidates)
                    except core.StopRequested:
                        if self.monitor_stop_event.is_set(): break
                    except Exception as e:
                        self.events.put(("monitor_log",f"軽量LLM精査をスキップ: {e}"))
                    self.monitor_candidates=candidates; self.monitor_snapshot=stats
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
            self.mod_status_cache["version"] = 1
            self.mod_status_cache["updated_at"] = datetime.now().isoformat(timespec="seconds")
            core.save_json(MOD_STATUS_CACHE_PATH, self.mod_status_cache)

    def _restore_cached_mod_status(self):
        try:
            data = core.load_json(MOD_STATUS_CACHE_PATH, {"items": {}})
            items = data.get("items", {}) if isinstance(data, dict) else {}
            rows = []
            for row in items.values():
                result = row.get("result") if isinstance(row, dict) else None
                if isinstance(result, dict) and result.get("path"):
                    r = dict(result); r["cached"] = True; rows.append(r)
            rows.sort(key=lambda r: str(r.get("mod", "")).lower())
            if not hasattr(self, "mod_status_tree"):
                return
            for x in self.mod_status_tree.get_children(): self.mod_status_tree.delete(x)
            self.mod_research_results = rows
            for i,r in enumerate(rows):
                msg = r.get("message", "")
                if msg and not msg.endswith("（キャッシュ）"):
                    msg += "（キャッシュ）"
                self.mod_status_tree.insert("", "end", iid=f"mod_{i}", values=(r.get("status",""),r.get("mod",""),r.get("gap_count",0),r.get("external_translation_mod",""),r.get("external_translation_gap_count",0) if r.get("external_translation_mod") else ""))
            counts={}
            for r in rows: counts[r.get("status","")] = counts.get(r.get("status",""),0)+1
            summary=" / ".join(f"{k}: {v}" for k,v in counts.items())
            self.mod_status_summary_var.set(f"キャッシュ復元: {len(rows)}件" + (f"　{summary}" if summary else ""))
        except Exception as e:
            record_error("翻訳状況キャッシュ復元", e)

    def research_selected_mod_background(self):
        root=Path(self.monitor_path_var.get().strip())
        if not root.exists():
            messagebox.showinfo(APP_NAME,"調査するModフォルダを選択してください。")
            return
        if self.mod_research_thread and self.mod_research_thread.is_alive():
            messagebox.showinfo(APP_NAME,"すでに調査中です。")
            return
        # A localization directory itself is accepted; otherwise the selected folder is one mod.
        mod_root = root.parent if root.name.lower()=="localization" else root
        if not core.mod_localization_root(mod_root):
            roots=core.find_mod_roots(root)
            if len(roots)==1:
                mod_root=roots[0]
            elif len(roots)>1:
                messagebox.showinfo(APP_NAME,"複数のModが見つかりました。全部を調べる場合は『全部のModを調べる』を使用してください。")
                return
        self._start_mod_research([mod_root], replace=True)

    def research_all_mods_background(self):
        root=Path(self.monitor_path_var.get().strip())
        if not root.exists():
            messagebox.showinfo(APP_NAME,"Modが入っている親フォルダを選択してください。")
            return
        roots=core.find_mod_roots(root)
        if not roots:
            messagebox.showinfo(APP_NAME,"調査できるModのlocalizationフォルダが見つかりませんでした。")
            return
        self._start_mod_research(roots, replace=True)

    def _start_mod_research(self, roots, replace=True):
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
        self.mod_research_thread=threading.Thread(target=self._mod_research_worker,args=(roots,),daemon=True)
        self.mod_research_thread.start()

    def stop_mod_research(self):
        self.mod_research_stop_event.set()
        if self.monitor_llm_controller:
            self.monitor_llm_controller.request_stop(save=False)
        self.mod_status_summary_var.set("調査停止要求済み…")

    def _mod_research_worker(self, roots):
        try:
            total=len(roots)
            results=[]
            check_external = bool(self.monitor_check_translation_mods_var.get())
            translation_index = core.build_translation_mod_index(roots) if check_external else None
            pool_signature = ""
            if check_external:
                h = hashlib.sha256()
                for root in sorted((Path(r) for r in roots), key=lambda x: str(x)):
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
                        # For a separate Japanese translation mod, refined candidates are that mod's missing/foreign entries.
                        if result.get("external_translation_mod") and not result.get("external_translation_complete"):
                            result["external_translation_gaps"] = refined
                            result["external_translation_gap_count"] = len(refined)
                            result["gap_count"] = len(refined)
                            if refined:
                                result["status"]="別Mod翻訳・欠損"
                                result["message"]=f"{result['mod']}には日本語化Mod『{result['external_translation_mod']}』がありますが、翻訳に欠損があります（{len(refined)}件）。"
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
                            result["message"]=f"{result['mod']}のModに翻訳の欠損箇所があります（{len(refined)}件）。"
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

    def queue_selected_mod_from_status(self, start_now=False):
        result = self._selected_mod_status_result()
        if not result:
            return None
        loc = Path(result.get("localization", ""))
        mod_root = Path(result.get("path", ""))
        if not loc.is_dir():
            messagebox.showerror(APP_NAME, "このModのlocalizationフォルダを確認できません。")
            return None
        if result.get("status") in {"翻訳あり", "別Modで完全翻訳"} and not result.get("gap_count"):
            if not messagebox.askyesno(APP_NAME, f"{result.get('mod','このMod')} は日本語翻訳済みと判定されています。\nそれでも翻訳しますか？"):
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
        self._refresh_queue_tree()
        self.save_session(active=False)
        try:
            self.notebook.select(self.tab_translate)
        except Exception:
            pass
        if start_now:
            if self.worker and self.worker.is_alive():
                messagebox.showinfo(APP_NAME, "現在ほかの翻訳を実行中のため、選択Modをキュー末尾へ追加しました。")
            else:
                self.start_queue()
        return item

    def translate_selected_mod_from_status(self):
        """Translate the selected researched mod without requiring the user to move files."""
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

    def translate_all_except_selected_mods(self):
        """Translate all researched mods that need work except the selected mods."""
        if not self.mod_research_results:
            messagebox.showinfo(APP_NAME, "先にModの翻訳状況を調査してください。")
            return
        selected = self._selected_mod_status_results()
        if not selected:
            messagebox.showinfo(APP_NAME, "除外するModを1つ以上選択してください。\nCtrlキーを押しながら複数選択できます。")
            return
        excluded = {str(Path(r.get("path", ""))) for r in selected}
        targets = []
        skipped_complete = 0
        for result in self.mod_research_results:
            path = str(Path(result.get("path", "")))
            if path in excluded:
                continue
            # Fully translated mods do not need another translation pass.
            if result.get("status") in {"翻訳あり", "別Modで完全翻訳"} and not result.get("gap_count"):
                skipped_complete += 1
                continue
            loc = Path(result.get("localization", ""))
            if loc.is_dir():
                targets.append(result)
        if not targets:
            messagebox.showinfo(APP_NAME, "選択したModを除外すると、翻訳が必要なModは残っていません。")
            return
        excluded_names = "、".join(r.get("mod", Path(r.get("path", "")).name) for r in selected[:8])
        if len(selected) > 8:
            excluded_names += f" ほか{len(selected)-8}件"
        detail = (
            f"選択した {len(selected)} Modを除外し、残りの翻訳対象 {len(targets)} Modをキューへ追加します。\n\n"
            f"除外: {excluded_names}"
        )
        if skipped_complete:
            detail += f"\n\n翻訳済み判定の {skipped_complete} Modは自動的に対象外です。"
        detail += "\n\nこのまま翻訳を開始しますか？"
        if not messagebox.askyesno(APP_NAME, detail):
            return
        added = 0
        for result in targets:
            if self._queue_mod_status_result(result) is not None:
                added += 1
        self._refresh_queue_tree()
        self.save_session(active=False)
        try:
            self.notebook.select(self.tab_translate)
        except Exception:
            pass
        if not added:
            messagebox.showinfo(APP_NAME, "翻訳キューへ追加できるModがありませんでした。")
            return
        if self.worker and self.worker.is_alive():
            messagebox.showinfo(APP_NAME, f"{added} Modをキュー末尾へ追加しました。現在の翻訳完了後に続けて処理します。")
        else:
            self.start_queue()

    def _infer_mod_target_for_item(self, item):
        loc = Path(item.get("mod_localization", "")) if item.get("mod_localization") else None
        root = Path(item.get("mod_root", "")) if item.get("mod_root") else None
        inp = Path(item.get("input", ""))
        if loc and loc.is_dir():
            return loc, loc
        if inp.is_dir() and inp.name.lower() == "localization":
            return inp, inp
        if inp.is_dir() and (inp / "localization").is_dir():
            return inp / "localization", inp
        return None, None

    def _generated_japanese_files(self, output_root: Path):
        files=[]
        if not output_root.exists():
            return files
        for p in sorted(output_root.rglob("*.yml")):
            try:
                head=p.read_text(encoding="utf-8-sig",errors="ignore").splitlines()[:5]
                lang=core.detect_source_lang(p,head)
            except Exception:
                lang=""
            if lang == "japanese" or "_l_japanese" in p.name.lower():
                files.append(p)
        return files

    def _merge_translation_gaps_into_external_mod(self, item):
        """Merge only missing/foreign keys into an existing separate Japanese translation mod."""
        ext_root = Path(item.get("external_translation_path", ""))
        ext_loc = Path(item.get("external_translation_localization", ""))
        gap_keys = {k for k in item.get("external_gap_keys", []) if k}
        out_root = Path(item.get("output", ""))
        if not ext_root.is_dir() or not ext_loc.is_dir() or not gap_keys:
            return False
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
            messagebox.showinfo(APP_NAME, "日本語化Modへ追加できる差分訳が完成済み出力から見つかりませんでした。")
            return True

        ext_name = item.get("external_translation_mod") or ext_root.name
        src_name = item.get("mod_name") or Path(item.get("mod_root", "")).name
        warning=(
            f"⚠ 別の日本語化Modへ不足分だけを書き込みます。\n\n"
            f"元Mod: {src_name}\n"
            f"日本語化Mod: {ext_name}\n"
            f"★ 今回の上書き先: 日本語化Mod『{ext_name}』\n"
            f"対象: {ext_root}\n"
            f"差分キー: {len(patch_values)}件\n\n"
            "既存の日本語訳は維持し、欠損・未翻訳と判定されたキーだけ更新/追加します。\n"
            "変更対象ファイルは実行前にバックアップします。\n"
            "Steam Workshop更新時には変更が失われる可能性があります。\n\n続行しますか？"
        )
        if not messagebox.askyesno("警告 — 日本語化Modへ差分上書き", warning, icon="warning"):
            return True
        if not messagebox.askyesno("最終確認", "日本語化Modへ不足分だけを書き込みます。本当に続行しますか？", icon="warning"):
            return True

        existing_key_file = {}
        for fp in self._generated_japanese_files(ext_loc):
            try:
                _, entries, _ = core.parse_localization_file(fp)
                for key in entries:
                    existing_key_file.setdefault(key, fp)
            except Exception:
                continue
        stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
        safe=re.sub(r'[^0-9A-Za-zぁ-んァ-ヶ一-龯_\-]+','_',ext_name).strip('_')[:60] or "JapaneseMod"
        backup_root=BACKUP_ROOT / f"{stamp}_{safe}_差分上書き"
        backed=set(); updated=0; added=0
        patch_file = ext_loc / "japanese" / "paradox_localization_translator_missing_l_japanese.yml"
        try:
            # Existing keys are updated in-place so duplicate localization keys are avoided.
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
                    text=patch_file.read_text(encoding="utf-8-sig")
                    if not text.endswith("\n"): text += "\n"
                else:
                    text="l_japanese:\n"
                for key,value in missing:
                    text += f' {key}: "{value}"\n'
                    added += 1
                patch_file.write_text("\ufeff"+text.lstrip("\ufeff"),encoding="utf-8")
            messagebox.showinfo(APP_NAME,
                f"日本語化Modへ差分を反映しました。\n\n既存キー更新: {updated}件\n新規キー追加: {added}件\nバックアップ: {len(backed)}ファイル\nバックアップ先: {backup_root if backed else '変更前ファイルなし'}")
            return True
        except Exception as e:
            record_error("日本語化Mod差分上書き", e, str(ext_root))
            messagebox.showerror(APP_NAME, f"日本語化Modへの差分上書き中にエラーが発生しました。\n{e}\n\nバックアップ先: {backup_root}")
            return True

    def overwrite_selected_translation_to_mod(self, item_override=None):
        item = item_override or self._selected_queue_item()
        if not item:
            return
        if item.get("status", "").startswith("翻訳中"):
            messagebox.showinfo(APP_NAME, "翻訳中の項目は上書きできません。翻訳完了後に実行してください。")
            return
        if item.get("external_translation_path") and item.get("external_gap_keys"):
            if self._merge_translation_gaps_into_external_mod(item):
                return
        loc_root, mod_root = self._infer_mod_target_for_item(item)
        if not loc_root:
            messagebox.showerror(APP_NAME, "元のModのlocalizationフォルダを特定できません。\n翻訳状況タブからModを追加した場合は自動特定できます。")
            return
        out_root = Path(item.get("output", ""))
        generated = self._generated_japanese_files(out_root)
        if not generated:
            messagebox.showinfo(APP_NAME, "上書きできる完成済み日本語YAMLが出力先に見つかりません。")
            return

        input_path = Path(item.get("input", ""))
        # Status-tab direct jobs use localization as input, so output paths are relative to localization.
        if input_path.is_dir() and input_path.name.lower() == "localization":
            target_base = loc_root
        else:
            # For a mod-root job, generated files keep localization/... in their relative path.
            target_base = mod_root

        mappings=[]
        for src in generated:
            try:
                rel=src.relative_to(out_root)
            except ValueError:
                continue
            dst=target_base / rel
            mappings.append((src,dst,rel))
        if not mappings:
            messagebox.showinfo(APP_NAME, "上書き対象を特定できませんでした。")
            return

        existing=sum(1 for _,dst,_ in mappings if dst.exists())
        mod_name=item.get("mod_name") or Path(mod_root).name
        warning=(
            f"⚠ 元のModへ日本語化ファイルを直接書き込みます。\n\n"
            f"Mod: {mod_name}\n"
            f"対象: {mod_root}\n"
            f"日本語YAML: {len(mappings)}件\n"
            f"既存ファイルの上書き: {existing}件\n\n"
            "既存ファイルは実行前にバックアップされます。\n"
            "Mod更新・Steam Workshop更新時には上書き内容が失われる可能性があります。\n\n"
            "続行しますか？"
        )
        if not messagebox.askyesno("警告 — Modへ直接上書き", warning, icon="warning"):
            return
        if not messagebox.askyesno("最終確認", "本当に元のModへ書き込みますか？\nこの操作は対象ファイルを置き換えます。", icon="warning"):
            return

        stamp=datetime.now().strftime("%Y%m%d_%H%M%S")
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
            messagebox.showinfo(APP_NAME,
                f"Modへ日本語化ファイルを上書きしました。\n\n書き込み: {copied}件\nバックアップ: {backed}件\nバックアップ先: {backup_root if backed else '既存ファイルなし'}")
        except Exception as e:
            messagebox.showerror(APP_NAME, f"上書き中にエラーが発生しました。\n{e}\n\nバックアップ先: {backup_root}")

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
            messagebox.showinfo(APP_NAME, "このModの完成済み翻訳がキューに見つかりません。\n先に『選択したModを翻訳』を実行してください。")
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
            self.mod_status_cache={"version":1,"items":{},"updated_at":datetime.now().isoformat(timespec="seconds")}
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
        conn=ttk.LabelFrame(t,text="接続",padding=8); conn.pack(fill="x")
        ttk.Label(conn,text="プロバイダ").grid(row=0,column=0,sticky="w")
        pc=ttk.Combobox(conn,textvariable=self.provider_var,values=["Ollama","LM Studio","OpenAI","Anthropic","Gemini","OpenAI Compatible"],state="readonly",width=14)
        pc.grid(row=0,column=1,padx=6); pc.bind("<<ComboboxSelected>>",lambda e:self.on_provider_change())
        ttk.Label(conn,text="API URL").grid(row=0,column=2,sticky="e")
        conn.columnconfigure(3,weight=1)
        ttk.Entry(conn,textvariable=self.url_var).grid(row=0,column=3,sticky="ew",padx=6)
        ttk.Button(conn,text="接続確認 / モデル再読込",command=self.refresh_models).grid(row=0,column=4)
        ttk.Label(conn,textvariable=self.connection_var).grid(row=1,column=0,columnspan=5,sticky="w",pady=(7,0))
        ttk.Label(conn,text="APIキー").grid(row=2,column=0,sticky="w",pady=(6,0))
        ttk.Entry(conn,textvariable=self.api_key_var,show="•").grid(row=2,column=1,columnspan=3,sticky="ew",padx=6,pady=(6,0))
        ttk.Label(conn,text="キーは保存しません",foreground="#666").grid(row=2,column=4,sticky="w",pady=(6,0))
        ttk.Label(conn,text="ローカル: Ollama / LM Studio　クラウド: OpenAI / Anthropic / Gemini / OpenAI互換API",foreground="#666").grid(row=3,column=0,columnspan=5,sticky="w",pady=(4,0))

        bench=ttk.LabelFrame(t,text="モデル速度比較（実翻訳時の統計も自動記録）",padding=8); bench.pack(fill="both",expand=True,pady=(10,0))
        bar=ttk.Frame(bench); bar.pack(fill="x",pady=(0,6))
        ttk.Button(bar,text="現在のLLMを速度テスト",command=self.benchmark_selected_model).pack(side="left")
        ttk.Button(bar,text="選択したモデルを比較テスト",command=self.benchmark_selected_models).pack(side="left",padx=(6,0))
        self.benchmark_stop_btn=ttk.Button(bar,text="速度テスト停止",command=self.stop_benchmark,state="disabled")
        self.benchmark_stop_btn.pack(side="left",padx=(6,0))
        ttk.Button(bar,text="統計を消去",command=self.clear_model_stats).pack(side="left",padx=(6,0))
        self.benchmark_status_var=tk.StringVar(value="")
        ttk.Label(bar,textvariable=self.benchmark_status_var).pack(side="right")

        select_box=ttk.LabelFrame(bench,text="比較するモデルを選択（最大5モデル）",padding=6)
        select_box.pack(fill="x",pady=(0,8))
        ttk.Label(select_box,text="Ctrlキーを押しながら複数選択できます。最大5モデルまで選択できます。",foreground="#666").pack(anchor="w",pady=(0,4))
        self.benchmark_model_list=tk.Listbox(select_box,selectmode=tk.EXTENDED,exportselection=False,height=5)
        self.benchmark_model_list.pack(fill="x")
        self.benchmark_model_list.bind("<<ListboxSelect>>",self._limit_benchmark_selection)
        cols=("provider","model","requests","avg","tps","fail")
        self.stats_tree=ttk.Treeview(bench,columns=cols,show="headings",height=9)
        for c,txt,w in (("provider","プロバイダ",100),("model","モデル",330),("requests","回数",70),("avg","平均秒",90),("tps","tokens/s",100),("fail","失敗率",90)):
            self.stats_tree.heading(c,text=txt); self.stats_tree.column(c,width=w,anchor="center" if c not in ("model",) else "w")
        self.stats_tree.pack(fill="both",expand=True)

        pf=ttk.LabelFrame(t,text="モデルプロファイル",padding=8); pf.pack(fill="both",expand=True,pady=(10,0))
        pb=ttk.Frame(pf); pb.pack(fill="x",pady=(0,6))
        ttk.Button(pb,text="現在設定をプロファイル保存",command=self.save_current_profile).pack(side="left")
        ttk.Button(pb,text="選択を適用",command=self.apply_profile_from_tree).pack(side="left",padx=(6,0))
        ttk.Button(pb,text="選択を削除",command=self.delete_profile).pack(side="left",padx=(6,0))
        self.profile_tree=ttk.Treeview(pf,columns=("name","label","provider","model","batch","workers"),show="headings",height=7)
        for c,txt,w in (("name","名前",180),("label","用途",160),("provider","方式",90),("model","モデル",300),("batch","バッチ",70),("workers","並列",60)):
            self.profile_tree.heading(c,text=txt); self.profile_tree.column(c,width=w)
        self.profile_tree.pack(fill="both",expand=True)
        self.profile_tree.bind("<Double-1>",lambda e:self.apply_profile_from_tree())
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

    # ---------------- queue ----------------
    def _default_output(self,p:Path):
        root = _automatic_output_root()
        name = p.stem + "_japanese" if p.is_file() else p.name + "_japanese"
        return root / name

    def add_folder(self):
        p=filedialog.askdirectory(title="翻訳するMod/localizationフォルダを選択")
        if p: self._append_queue(Path(p))

    def add_files(self):
        paths=filedialog.askopenfilenames(title="翻訳するYAMLを複数選択",filetypes=[("Paradox YAML","*.yml"),("All","*")])
        for p in paths: self._append_queue(Path(p))

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

    def _register_cache_job(self, item: dict):
        cache = Path(item.get("cache", ""))
        if not cache.exists() or not (cache.parent / core.SOURCE_MANIFEST_NAME).exists():
            return
        sid = self._source_id(Path(item["input"]))
        reg = self._load_cache_registry()
        rows = [r for r in reg.get(sid, []) if Path(r.get("cache", "")).exists()]
        rows = [r for r in rows if r.get("cache") != str(cache)]
        rows.append({"cache": str(cache), "input": item["input"], "output": item.get("output", ""),
                     "updated_at": datetime.now().isoformat(timespec="seconds")})
        reg[sid] = rows[-20:]
        self._save_cache_registry(reg)

    def _find_previous_cache(self, p: Path, exclude: Path | None = None) -> Path | None:
        sid = self._source_id(p)
        candidates = []
        reg = self._load_cache_registry()
        for row in reg.get(sid, []):
            cp = Path(row.get("cache", ""))
            if cp.exists() and (cp.parent / core.SOURCE_MANIFEST_NAME).exists():
                candidates.append(cp)
        # Registryが失われても、キャッシュフォルダ内のmanifestから復旧できる。
        for mf in CACHE_ROOT.glob(f"*/{core.SOURCE_MANIFEST_NAME}"):
            try:
                manifest = core.load_json(mf, {})
                if manifest.get("input") == sid:
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

    def _prepare_differential_cache(self, item: dict, silent: bool = True) -> dict | None:
        p = Path(item["input"])
        current_cache = Path(self._ensure_item_cache(item))
        previous = self._find_previous_cache(p, exclude=current_cache)
        if not previous:
            return None
        old_manifest = core.load_source_manifest(previous)
        if not old_manifest:
            return None
        try:
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
        self._prepare_differential_cache(item, silent=True)
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

    def on_drop_paths(self, event):
        try:
            raw_paths = list(self.tk.splitlist(event.data))
        except Exception:
            raw_paths = [event.data]
        added = 0
        ignored = []
        for raw in raw_paths:
            p = Path(raw)
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
            self.queue_tree.insert("", "end", iid=str(i), values=(item["input"],item["output"],item["status"]))

    def remove_queue(self):
        sels=sorted((int(x) for x in self.queue_tree.selection()),reverse=True)
        for i in sels:
            if 0<=i<len(self.queue_items): self.queue_items.pop(i)
        self._refresh_queue_tree()

    def clear_queue(self):
        if self.worker and self.worker.is_alive(): return
        self.queue_items.clear(); self._refresh_queue_tree()

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
        """Apply current GUI translation settings to the active job at the next batch boundary."""
        if not self.controller or not self.worker or not self.worker.is_alive():
            messagebox.showinfo(APP_NAME, "現在実行中の翻訳はありません。\n変更した設定は次回の翻訳開始時に使用されます。")
            return
        try:
            glossary_path = self.glossary_path_var.get().strip()
            glossary = core.load_glossary(Path(glossary_path)) if glossary_path else {}
            self.controller.update_runtime_settings(
                provider=self.provider_var.get(),
                url=self.url_var.get().strip(),
                model=self.model_var.get().strip(),
                api_key=self.api_key_var.get().strip(),
                preset=self.preset_var.get(),
                batch_size=max(1, self.batch_var.get()),
                workers=max(1, self.workers_var.get()),
                glossary_path=glossary_path,
                dual_source=self.dual_var.get(),
            )
            self.progress_text.set(
                f"設定変更を予約しました。次のバッチから適用: {self.provider_var.get()} / {self.model_var.get()} / "
                f"バッチ{self.batch_var.get()} / 並列{self.workers_var.get()}"
            )
            self.save_session(active=True)
            messagebox.showinfo(
                APP_NAME,
                "現在の翻訳へ設定変更を予約しました。\n\n"
                "現在処理中のLLM応答はそのまま完了させ、次のバッチ境界から新設定を使用します。\n"
                "モデル・プロバイダを変えた場合、以降の翻訳キャッシュも新設定用のキーとして保存されます。"
            )
        except Exception as e:
            record_error("現在翻訳への設定適用", e)
            messagebox.showerror(APP_NAME, f"設定の適用に失敗しました。\n{e}")

    def start_queue(self):
        if self.worker and self.worker.is_alive(): return
        if not self.queue_items:
            messagebox.showinfo(APP_NAME,"翻訳キューにフォルダまたはファイルを追加してください。"); return
        self._clear_log(); self.progress["value"]=0
        self.llm_operation = "翻訳"
        self.controller=core.TranslationController(progress_callback=lambda x:self.events.put(("progress",x)), checkpoint_callback=self._checkpoint)
        self.start_btn.config(state="disabled"); self.pause_btn.config(state="normal",text="一時停止"); self.stop_btn.config(state="normal")
        self.worker=threading.Thread(target=self._queue_worker,daemon=True); self.worker.start()
        self.save_session(active=True)

    def _queue_worker(self):
        try:
            for i,item in enumerate(self.queue_items):
                self.current_queue_index=i
                if item.get("status") == "完了": continue
                item["status"]="翻訳中"; self.events.put(("queue_refresh",None))
                self._checkpoint({"queue_index":i})
                out=Path(item["output"]); cache_file=Path(self._ensure_item_cache(item))
                result=core.run_translation(
                    item["input"], item["output"], model=self.model_var.get().strip(), url=self.url_var.get().strip(),
                    workers=max(1,self.workers_var.get()), batch_size=max(1,self.batch_var.get()), cache_path=cache_file,
                    resume=True, verbose=True, include_target_files=self.repair_var.get(), controller=self.controller,
                    glossary_path=self.glossary_path_var.get().strip() or None, preset=self.preset_var.get(),
                    dual_source=self.dual_var.get(), auto_qa=self.autoqa_var.get(), provider=self.provider_var.get(), api_key=self.api_key_var.get().strip())
                self._register_cache_job(item)
                if result.get("interrupted"):
                    item["status"]="中断（再開可）"; self.events.put(("queue_refresh",None)); self.save_session(active=True); break
                item["status"]="完了（差分更新）" if item.get("diff_mode") else "完了"; self.events.put(("queue_refresh",None)); self.save_session(active=True)
            else:
                self.events.put(("done",None)); self._delete_session()
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
        return {"provider":self.provider_var.get(),"url":self.url_var.get(),"model":self.model_var.get(),"preset":self.preset_var.get(),
                "batch":self.batch_var.get(),"workers":self.workers_var.get(),"repair":self.repair_var.get(),
                "dual":self.dual_var.get(),"autoqa":self.autoqa_var.get(),"glossary":self.glossary_path_var.get()}

    def save_session(self,active=False):
        data={"version":APP_VERSION,"active":active,"queue":self.queue_items,"queue_index":self.current_queue_index,"settings":self._settings_dict()}
        core.save_json(SESSION_PATH,data)
        if not active: self.progress_text.set(f"セッション保存: {SESSION_PATH}")

    def _checkpoint(self,payload):
        data=core.load_json(SESSION_PATH,{})
        data.update({"version":APP_VERSION,"active":True,"queue":self.queue_items,"queue_index":self.current_queue_index,"settings":self._settings_dict(),"checkpoint":payload})
        core.save_json(SESSION_PATH,data)

    def restore_session(self):
        data=core.load_json(SESSION_PATH,{})
        if not data:
            messagebox.showinfo(APP_NAME,"保存されたセッションはありません。"); return
        self.queue_items=data.get("queue",[])
        s=data.get("settings",{})
        self.provider_var.set(s.get("provider",self.provider_var.get())); self.url_var.set(s.get("url",self.url_var.get())); self.model_var.set(s.get("model",self.model_var.get())); self.preset_var.set(s.get("preset",self.preset_var.get()))
        self.batch_var.set(s.get("batch",40)); self.workers_var.set(s.get("workers",1)); self.repair_var.set(s.get("repair",True)); self.dual_var.set(s.get("dual",False)); self.autoqa_var.set(s.get("autoqa",True)); self.glossary_path_var.set(s.get("glossary",str(DEFAULT_GLOSSARY)))
        for item in self.queue_items:
            self._ensure_item_cache(item)
            if item.get("status") == "翻訳中": item["status"]="中断（再開可）"
        self._refresh_queue_tree(); self.progress_text.set("セッションを復元しました。翻訳開始で続きから再開します。")

    def _offer_restore_session(self):
        data=core.load_json(SESSION_PATH,{})
        if data.get("active") and data.get("queue"):
            if messagebox.askyesno(APP_NAME,"前回の翻訳セッションが残っています。復元しますか？"):
                self.restore_session()

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
            messagebox.showerror(APP_NAME, "英語/原文ファイルと日本語ファイルの両方を選択してください。")
            return
        try:
            source_lang, self.diff_source_entries, _ = core.parse_localization_file(src)
            _, self.diff_target_entries, _ = core.parse_localization_file(dst)
            self.diff_rows = core.compare_localization_entries(self.diff_source_entries, self.diff_target_entries, source_lang)
            self.diff_row_by_key = {r["key"]: r for r in self.diff_rows}
            for iid in self.diff_tree.get_children(): self.diff_tree.delete(iid)
            labels = {"missing":"欠落", "untranslated":"未翻訳", "extra":"日本語のみ", "ok":"対応あり"}
            counts = {k:0 for k in labels}
            for row in self.diff_rows:
                counts[row["status"]] = counts.get(row["status"], 0) + 1
                self.diff_tree.insert("", "end", iid=row["key"], values=(labels.get(row["status"],row["status"]), row["key"]), tags=(row["status"],))
            self.diff_summary_var.set(f"欠落 {counts['missing']} / 未翻訳 {counts['untranslated']} / 日本語のみ {counts['extra']} / 対応あり {counts['ok']}")
        except Exception as e:
            record_error("差分調査", e)
            messagebox.showerror(APP_NAME, str(e))

    def on_diff_select(self, _=None):
        sel = self.diff_tree.selection()
        if not sel: return
        key = sel[0]
        row = self.diff_row_by_key.get(key, {})
        self.diff_src_text.delete("1.0", "end"); self.diff_src_text.insert("1.0", row.get("source", ""))
        self.diff_dst_text.delete("1.0", "end"); self.diff_dst_text.insert("1.0", row.get("target", ""))
        self.diff_message_var.set(row.get("message", ""))

    def save_diff_value(self):
        sel = self.diff_tree.selection()
        if not sel: return
        key = sel[0]
        value = self.diff_dst_text.get("1.0", "end-1c")
        try:
            core.upsert_localization_values(Path(self.diff_dst_var.get()), {key:value})
            self.load_diff_inspector()
            if self.diff_tree.exists(key): self.diff_tree.selection_set(key); self.diff_tree.see(key)
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
            keys = [k for k in self.diff_tree.selection() if self.diff_row_by_key.get(k,{}).get("source")]
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
                                                          glossary, self.preset_var.get(), self.provider_var.get(), self.api_key_var.get().strip(), self.diff_controller)
                core.upsert_localization_values(dst_path, out)
                self.events.put(("diff_translate_done", len(out)))
            except core.StopRequested:
                self.events.put(("diff_translate_stopped", None))
            except Exception as e:
                self.events.put(("diff_translate_error", str(e)))
        threading.Thread(target=work, daemon=True).start()

    def pick_search_folder(self):
        p = filedialog.askdirectory()
        if p: self.search_path_var.set(p)

    def pick_search_file(self):
        p = filedialog.askopenfilename(filetypes=[("Paradox YAML","*.yml"),("All","*")])
        if p: self.search_path_var.set(p)

    def run_translation_search(self):
        root = Path(self.search_path_var.get())
        if not root.exists():
            messagebox.showerror(APP_NAME, "検索するファイルまたはフォルダを選択してください。")
            return
        q = self.search_query_var.get().strip().lower()
        files = [root] if root.is_file() else core.gather_yml_files(root)
        for iid in self.search_tree.get_children(): self.search_tree.delete(iid)
        self.search_result_map = {}
        count = 0
        for f in files:
            try:
                lang, entries, _ = core.parse_localization_file(f)
            except Exception:
                continue
            if lang != "japanese": continue
            for key, value in entries.items():
                if q and q not in key.lower() and q not in value.lower() and q not in f.name.lower():
                    continue
                iid = f"r{count}"
                self.search_result_map[iid] = (f, key, value)
                self.search_tree.insert("", "end", iid=iid, values=(f.name, key, value[:180]))
                count += 1
        self.search_summary_var.set(f"検索結果: {count}件")

    def on_search_select(self, _=None):
        sel = self.search_tree.selection()
        if not sel: return
        f, key, value = self.search_result_map.get(sel[0], (None,"",""))
        if not f: return
        self.search_selected_var.set(f"{f} / {key}")
        self.search_edit_text.delete("1.0", "end"); self.search_edit_text.insert("1.0", value)

    def save_search_value(self):
        sel = self.search_tree.selection()
        if not sel: return
        f, key, _ = self.search_result_map.get(sel[0], (None,"",""))
        if not f: return
        value = self.search_edit_text.get("1.0", "end-1c")
        try:
            if not core.update_localization_value(Path(f), key, value):
                raise RuntimeError("対象キーをファイル内で更新できませんでした")
            self.search_result_map[sel[0]] = (f, key, value)
            self.search_tree.item(sel[0], values=(Path(f).name, key, value[:180]))
            self.search_summary_var.set(f"保存しました: {key}")
        except Exception as e:
            record_error("翻訳検索から直接訂正", e); messagebox.showerror(APP_NAME, str(e))

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
            self.review_source_entries=core.parse_localization_file(src)[1] if src and src.exists() else {}
            self.run_review_qa()
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def run_review_qa(self):
        if not self.review_target_entries and self.review_dst_var.get():
            try: _,self.review_target_entries,_=core.parse_localization_file(Path(self.review_dst_var.get()))
            except Exception as e: messagebox.showerror(APP_NAME,str(e)); return
        self.review_issues=core.qa_entries(self.review_target_entries,self.review_source_entries or None)
        self.review_issue_by_key={}
        for issue in self.review_issues: self.review_issue_by_key.setdefault(issue["key"],[]).append(issue)
        errs=sum(x["severity"]=="error" for x in self.review_issues); warns=sum(x["severity"]=="warning" for x in self.review_issues)
        self.qa_summary_var.set(f"QA: エラー {errs} / 警告 {warns} / キー {len(self.review_target_entries)}")
        self.populate_review(True)

    def populate_review(self,warnings_only):
        for x in self.review_tree.get_children(): self.review_tree.delete(x)
        keys=sorted(self.review_target_entries)
        if self.review_source_entries:
            keys=sorted(set(keys)|set(self.review_source_entries))
        for key in keys:
            issues=self.review_issue_by_key.get(key,[])
            if warnings_only and not issues: continue
            level=""; typ=""
            if issues:
                level="ERROR" if any(i["severity"]=="error" for i in issues) else "WARN"
                typ=",".join(sorted(set(i["type"] for i in issues)))
            self.review_tree.insert("","end",iid=key,values=(level,typ,key))

    def on_review_select(self,_=None):
        sel=self.review_tree.selection()
        if not sel: return
        key=sel[0]
        self.src_text.delete("1.0","end"); self.src_text.insert("1.0",self.review_source_entries.get(key,""))
        self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",self.review_target_entries.get(key,""))
        self.issue_text.set(" / ".join(i["message"] for i in self.review_issue_by_key.get(key,[])))

    def save_review_value(self):
        sel=self.review_tree.selection()
        if not sel: return
        key=sel[0]; value=self.dst_text.get("1.0","end-1c")
        if core.update_localization_value(Path(self.review_dst_var.get()),key,value):
            self.review_target_entries[key]=value; self.run_review_qa();
            if self.review_tree.exists(key): self.review_tree.selection_set(key)

    def restore_source_to_target(self):
        sel=self.review_tree.selection()
        if sel:
            self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",self.review_source_entries.get(sel[0],""))

    def ai_proofread_selected(self):
        sel=self.review_tree.selection()
        if not sel: return
        key=sel[0]; text=self.dst_text.get("1.0","end-1c"); src=self.review_source_entries.get(key,"")
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

    # ---------------- glossary ----------------
    def pick_glossary(self):
        p=filedialog.askopenfilename(filetypes=[("JSON","*.json"),("All","*")])
        if p: self.glossary_path_var.set(p); self.load_glossary_ui(silent=True)

    def load_glossary_ui(self,silent=False):
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        gl=core.load_glossary(p)
        for x in getattr(self,"glossary_tree",ttk.Treeview()).get_children(): self.glossary_tree.delete(x)
        if hasattr(self,"glossary_tree"):
            for src,dst in sorted(gl.items()): self.glossary_tree.insert("","end",values=(src,dst))
        if not silent: self.progress_text.set(f"用語集 {len(gl)}件を読み込みました")

    def save_glossary_ui(self):
        p=Path(self.glossary_path_var.get() or DEFAULT_GLOSSARY)
        gl={}
        for iid in self.glossary_tree.get_children():
            src,dst=self.glossary_tree.item(iid,"values"); gl[src]=dst
        core.save_glossary(p,gl); self.glossary_path_var.set(str(p)); self.progress_text.set(f"用語集保存: {p}")

    def add_glossary_term(self):
        src=simpledialog.askstring("用語追加","原語（英語/中国語）")
        if not src: return
        dst=simpledialog.askstring("用語追加",f"「{src}」の固定日本語訳")
        if dst: self.glossary_tree.insert("","end",values=(src,dst)); self.save_glossary_ui()

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
                    if hasattr(self,"monitor_model_combo"):
                        self.monitor_model_combo["values"]=payload
                        if payload and self.monitor_model_var.get() not in payload:
                            self.monitor_model_var.set(payload[0])
                    self.monitor_connection_var.set(f"監視用LLM: {self.monitor_provider_var.get()} 接続済み / {len(payload)}モデル")
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
                        first=self.discovered_mod_tree.get_children()[0]
                        self.discovered_mod_tree.selection_set(first); self.discovered_mod_tree.focus(first)
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
                    self.monitor_status_var.set(f"監視中 — 最終確認 {datetime.now().strftime('%H:%M:%S')}")
                elif kind=="monitor_stopped":
                    self.monitor_status_var.set("監視停止中")
                    self.monitor_start_btn.config(state="normal"); self.monitor_stop_btn.config(state="disabled")
                    self.monitor_thread=None
                    self._set_monitor_llm_idle("探索用LLM 待機中","未翻訳監視を終了しました")
                elif kind=="monitor_error":
                    record_error("未翻訳監視", detail=str(payload))
                    self.monitor_status_var.set("監視エラー")
                    self.monitor_start_btn.config(state="normal"); self.monitor_stop_btn.config(state="disabled")
                    self.monitor_thread=None
                    messagebox.showerror(APP_NAME,"未翻訳監視エラー: "+payload)
                elif kind=="mod_status_results":
                    for x in self.mod_status_tree.get_children(): self.mod_status_tree.delete(x)
                    self.mod_research_results=[]
                    self.mod_status_summary_var.set("調査結果: 0件")
                elif kind=="mod_status_append":
                    self.mod_research_results.append(payload)
                    i=len(self.mod_research_results)-1
                    self.mod_status_tree.insert("","end",iid=f"mod_{i}",values=(payload.get("status",""),payload.get("mod",""),payload.get("gap_count",0),payload.get("external_translation_mod",""),payload.get("external_translation_gap_count",0) if payload.get("external_translation_mod") else ""))
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
                    self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳が完了しました"); self.progress["value"]=100; self.progress_text.set("すべての翻訳が完了しました"); self._refresh_queue_tree(); messagebox.showinfo(APP_NAME,"翻訳キューが完了しました。")
                elif kind=="fatal": record_error("翻訳処理 fatal", detail=str(payload)); self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳処理でエラーが発生しました"); messagebox.showerror(APP_NAME,payload)
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
        self.start_btn.config(state="normal"); self.pause_btn.config(state="disabled",text="一時停止"); self.stop_btn.config(state="disabled"); self.controller=None

    def on_close(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_stop_event.set()
            if self.monitor_llm_controller: self.monitor_llm_controller.request_stop(save=False)
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME,"翻訳中です。セッションを保存して終了しますか？\n完了済みバッチはキャッシュされ、次回再開できます。"):
                return
            self.save_session(active=True)
            if self.controller: self.controller.request_stop(save=True)
        self.destroy()


if __name__ == "__main__":
    app=App(); app.mainloop()
