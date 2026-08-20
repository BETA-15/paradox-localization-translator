#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import translator_core as core

APP_NAME = "Paradox Localization Translator"
APP_VERSION = "0.5.3"


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


def _automatic_data_root() -> Path:
    beside = _app_container_dir() / "ParadoxLocalizationTranslator_Data"
    if _is_writable_dir(beside):
        return beside
    docs = Path.home() / "Documents" / "Paradox Localization Translator"
    docs.mkdir(parents=True, exist_ok=True)
    return docs


DATA_ROOT = _automatic_data_root()
APP_HOME = DATA_ROOT / "設定"
OUTPUT_ROOT = DATA_ROOT / "翻訳結果"
SESSION_PATH = APP_HOME / "session.json"
DEFAULT_GLOSSARY = APP_HOME / "glossary.json"
STATS_PATH = APP_HOME / "model_stats.json"
PROFILES_PATH = APP_HOME / "model_profiles.json"


def _automatic_output_root() -> Path:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    return OUTPUT_ROOT


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        APP_HOME.mkdir(parents=True, exist_ok=True)
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1180x820")
        self.minsize(980, 700)
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
        self.request_durations = []
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

        self.provider_var = tk.StringVar(value="Ollama")
        self.api_key_var = tk.StringVar(value="")
        self.url_var = tk.StringVar(value=core.DEFAULT_OLLAMA_URL)
        self.model_var = tk.StringVar(value=core.DEFAULT_MODEL)
        self.preset_var = tk.StringVar(value="CK3")
        self.batch_var = tk.IntVar(value=40)
        self.workers_var = tk.IntVar(value=1)
        self.repair_var = tk.BooleanVar(value=True)
        self.dual_var = tk.BooleanVar(value=False)
        self.autoqa_var = tk.BooleanVar(value=True)
        self.glossary_path_var = tk.StringVar(value=str(DEFAULT_GLOSSARY))
        self.connection_var = tk.StringVar(value="LLM接続確認中…")
        self.eta_var = tk.StringVar(value="残り時間: --")
        self.profile_var = tk.StringVar(value="")
        self.progress_text = tk.StringVar(value="待機中")
        self.review_src_var = tk.StringVar()
        self.review_dst_var = tk.StringVar()
        self.qa_summary_var = tk.StringVar(value="QA未実行")

        self._build_ui()
        self.after(100, self._poll_events)
        self.after(300, self.refresh_models)
        self.after(500, self._offer_restore_session)

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

        nb = ttk.Notebook(self); nb.pack(fill="both", expand=True, padx=10, pady=8)
        self.tab_translate = ttk.Frame(nb, padding=10)
        self.tab_review = ttk.Frame(nb, padding=10)
        self.tab_glossary = ttk.Frame(nb, padding=10)
        self.tab_models = ttk.Frame(nb, padding=10)
        self.tab_help = ttk.Frame(nb, padding=10)
        nb.add(self.tab_translate, text="翻訳 / キュー")
        nb.add(self.tab_review, text="QA / 比較編集")
        nb.add(self.tab_glossary, text="用語集")
        nb.add(self.tab_models, text="モデル / 接続")
        nb.add(self.tab_help, text="使い方")
        self._build_translate_tab()
        self._build_review_tab()
        self._build_glossary_tab()
        self._build_models_tab()
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
        ttk.Label(settings,text="用語集").grid(row=4,column=4,sticky="e",pady=(8,0))
        ttk.Entry(settings,textvariable=self.glossary_path_var).grid(row=4,column=5,sticky="ew",padx=(5,4),pady=(8,0))
        ttk.Button(settings,text="選択",command=self.pick_glossary).grid(row=4,column=6,pady=(8,0))
        qf = ttk.LabelFrame(t,text="複数翻訳キュー（上から順番に処理）",padding=8); qf.pack(fill="both",expand=True,pady=(10,0))
        toolbar=ttk.Frame(qf); toolbar.pack(fill="x",pady=(0,6))
        ttk.Button(toolbar,text="フォルダ追加",command=self.add_folder).pack(side="left")
        ttk.Button(toolbar,text="ファイル追加",command=self.add_files).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="選択削除",command=self.remove_queue).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="全消去",command=self.clear_queue).pack(side="left",padx=(6,0))
        ttk.Button(toolbar,text="選択項目の出力先変更",command=self.change_output).pack(side="left",padx=(14,0))
        ttk.Button(toolbar,text="セッション読込",command=self.restore_session).pack(side="right")
        ttk.Button(toolbar,text="セッション保存",command=self.save_session).pack(side="right",padx=(0,6))

        cols=("input","output","status")
        self.queue_tree=ttk.Treeview(qf,columns=cols,show="headings",height=12)
        self.queue_tree.heading("input",text="入力")
        self.queue_tree.heading("output",text="出力")
        self.queue_tree.heading("status",text="状態")
        self.queue_tree.column("input",width=430); self.queue_tree.column("output",width=430); self.queue_tree.column("status",width=130,anchor="center")
        ys=ttk.Scrollbar(qf,orient="vertical",command=self.queue_tree.yview); self.queue_tree.configure(yscrollcommand=ys.set)
        self.queue_tree.pack(side="left",fill="both",expand=True); ys.pack(side="right",fill="y")

        actions=ttk.Frame(t); actions.pack(fill="x",pady=(10,0))
        self.start_btn=ttk.Button(actions,text="翻訳開始",command=self.start_queue); self.start_btn.pack(side="left")
        self.pause_btn=ttk.Button(actions,text="一時停止",command=self.toggle_pause,state="disabled"); self.pause_btn.pack(side="left",padx=(7,0))
        self.stop_btn=ttk.Button(actions,text="セーブして中断",command=self.save_and_stop,state="disabled"); self.stop_btn.pack(side="left",padx=(7,0))
        ttk.Button(actions,text="出力を開く",command=self.open_selected_output).pack(side="left",padx=(7,0))
        ttk.Label(actions,textvariable=self.eta_var).pack(side="right",padx=(12,0))
        ttk.Label(actions,textvariable=self.progress_text).pack(side="right")
        self.progress=ttk.Progressbar(t,mode="determinate",maximum=100); self.progress.pack(fill="x",pady=(7,7))

        lf=ttk.LabelFrame(t,text="ログ",padding=6); lf.pack(fill="both",expand=False)
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

    def _build_help_tab(self):
        t = self.tab_help
        title = ttk.Label(t, text="Paradox Localization Translator 使い方", font=("", 18, "bold"))
        title.pack(anchor="w", pady=(0, 10))
        box = tk.Text(t, wrap="word", padx=12, pady=12)
        box.pack(fill="both", expand=True)
        guide = """【基本的な使い方】

1. Ollama / LM Studio / クラウドAPIのいずれかを準備します。
2. 「翻訳 / キュー」タブで［フォルダ追加］または［ファイル追加］を押します。
3. 必要ならモデル・バッチサイズ・用語集などを設定します。
4. ［翻訳開始］を押します。

【出力先】

出力先は自動で決まります。
・アプリ/実行ファイルの隣に書き込める場合:
  ParadoxLocalizationTranslator_Data/翻訳結果 フォルダ
・アプリの隣へ書き込めない場合（例: macOSの /Applications）:
  書類/Documents/Paradox Localization Translator/翻訳結果 フォルダ

セッション、用語集、モデル統計などの自動生成ファイルも同じDataフォルダ内の「設定」にまとめます。
各翻訳項目は「翻訳結果」の中に「元ファイル名_japanese」または「元フォルダ名_japanese」で作成されます。

出力先を個別に変更したい場合は、キューの対象行をクリックして選択してから［出力先変更］を押してください。
未選択の場合は案内が表示されます。

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

【困ったとき】

・Ollama/LM Studioが起動しているか確認
・モデルがロード/インストール済みか確認
・ログ欄の最後のエラーを確認
・出力先へ書き込めない場合はDocuments側が自動利用されます
"""
        box.insert("1.0", guide)
        box.config(state="disabled")

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
        ttk.Label(select_box,text="Ctrl / ⌘ を押しながら複数選択できます。5モデルを超える選択は自動的に5件へ制限されます。",foreground="#666").pack(anchor="w",pady=(0,4))
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
            if elapsed>0:
                self.request_durations.append(elapsed); self.request_durations=self.request_durations[-30:]
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
        if not sel: return
        for name in sel: self.model_profiles.pop(name,None)
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

    def _append_queue(self,p:Path,out:Path|None=None,status="待機"):
        out=out or self._default_output(p)
        item={"input":str(p),"output":str(out),"status":status}
        self.queue_items.append(item); self._refresh_queue_tree()

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

    def change_output(self):
        sel=self.queue_tree.selection()
        if not sel:
            messagebox.showinfo(APP_NAME, "出力先を変更する項目を、キュー一覧から先に選択してください。\n\n通常は変更不要です。出力先は自動で『アプリの隣』、書き込めない場合は『書類/Documents』になります。")
            return
        current = self.queue_items[int(sel[0])].get("output", "")
        initial = str(Path(current).parent) if current else str(_automatic_output_root())
        p=filedialog.askdirectory(title="選択項目の出力先", initialdir=initial)
        if p:
            self.queue_items[int(sel[0])]["output"]=p
            self._refresh_queue_tree()
            self.save_session(active=bool(self.worker and self.worker.is_alive()))

    def start_queue(self):
        if self.worker and self.worker.is_alive(): return
        if not self.queue_items:
            messagebox.showinfo(APP_NAME,"翻訳キューにフォルダまたはファイルを追加してください。"); return
        self._clear_log(); self.progress["value"]=0; self.request_durations=[]; self.eta_var.set("残り時間: 計測中…")
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
                out=Path(item["output"]); cache=out/".cache"
                result=core.run_translation(
                    item["input"], item["output"], model=self.model_var.get().strip(), url=self.url_var.get().strip(),
                    workers=max(1,self.workers_var.get()), batch_size=max(1,self.batch_var.get()), cache_dir=cache,
                    resume=True, verbose=True, include_target_files=self.repair_var.get(), controller=self.controller,
                    glossary_path=self.glossary_path_var.get().strip() or None, preset=self.preset_var.get(),
                    dual_source=self.dual_var.get(), auto_qa=self.autoqa_var.get(), provider=self.provider_var.get(), api_key=self.api_key_var.get().strip())
                if result.get("interrupted"):
                    item["status"]="中断（再開可）"; self.events.put(("queue_refresh",None)); self.save_session(active=True); break
                item["status"]="完了"; self.events.put(("queue_refresh",None)); self.save_session(active=True)
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
        if self.proofread_controller:
            self.proofread_controller.request_stop(save=False)
            self.issue_text.set("AI校正の停止を要求しました。現在のLLM応答完了後に停止します。")
            self.llm_detail_var.set("停止要求済み — 現在のAPI/LLM応答完了を待っています")

    # ---------------- misc ----------------
    def open_selected_output(self):
        sel=self.queue_tree.selection(); path=None
        if sel: path=Path(self.queue_items[int(sel[0])]["output"])
        elif self.queue_items: path=Path(self.queue_items[-1]["output"])
        if not path: return
        path.mkdir(parents=True,exist_ok=True)
        try:
            if sys.platform=="darwin": subprocess.Popen(["open",str(path)])
            elif os.name=="nt": os.startfile(str(path))
            else: subprocess.Popen(["xdg-open",str(path)])
        except Exception as e: messagebox.showerror(APP_NAME,str(e))

    def _append_log(self,text):
        self.log.config(state="normal"); self.log.insert("end",text+"\n"); self.log.see("end"); self.log.config(state="disabled")

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
                elif kind=="progress":
                    if payload.get("kind")=="llm_activity":
                        self._handle_llm_activity(payload,"翻訳")
                    elif payload.get("kind")=="llm_metric":
                        self._record_metric(payload.get("metric"))
                    elif payload.get("kind")=="batch":
                        done,total=payload.get("done",0),max(1,payload.get("total",1)); self.progress["value"]=done/total*100
                        self.progress_text.set(f"キュー {self.current_queue_index+1}/{len(self.queue_items)} / ファイル {payload.get('file_no',0)}/{payload.get('file_total',0)} / {done}/{total}行")
                        if self.request_durations and done < total:
                            import math
                            avg=sum(self.request_durations)/len(self.request_durations); remaining=max(0,total-done)
                            batches=math.ceil(remaining/max(1,self.batch_var.get())); waves=math.ceil(batches/max(1,self.workers_var.get())); secs=max(0,int(avg*waves))
                            if secs<60: eta=f"約{secs}秒"
                            elif secs<3600: eta=f"約{math.ceil(secs/60)}分"
                            else: eta=f"約{secs//3600}時間{math.ceil((secs%3600)/60)}分"
                            self.eta_var.set(f"現在ファイル残り: {eta}")
                        elif done>=total: self.eta_var.set("現在ファイル残り: ほぼ完了")
                    elif payload.get("kind")=="file_done": self.progress["value"]=100
                elif kind=="benchmark_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"モデル速度テスト")
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
                elif kind=="queue_refresh": self._refresh_queue_tree()
                elif kind=="done":
                    self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳が完了しました"); self.progress["value"]=100; self.progress_text.set("すべての翻訳が完了しました"); self.eta_var.set("残り時間: 0分"); self._refresh_queue_tree(); messagebox.showinfo(APP_NAME,"翻訳キューが完了しました。")
                elif kind=="fatal": self._finish_controls(); self._set_llm_idle("LLM 待機中","翻訳処理でエラーが発生しました"); messagebox.showerror(APP_NAME,payload)
                elif kind=="proofread_progress":
                    if payload.get("kind")=="llm_activity": self._handle_llm_activity(payload,"AI誤字脱字校正")
                    elif payload.get("kind")=="llm_metric": self._record_metric(payload.get("metric"))
                elif kind=="proofread":
                    self.dst_text.delete("1.0","end"); self.dst_text.insert("1.0",payload); self.issue_text.set("AI校正結果を表示しました。内容を確認して保存してください。"); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正が完了しました")
                elif kind=="proofread_stopped":
                    self.issue_text.set("AI校正を停止しました。"); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正を停止しました")
                elif kind=="proofread_error":
                    self.issue_text.set("AI校正エラー: "+payload); self.proofread_controller=None; self._set_llm_idle("LLM 待機中","AI校正でエラーが発生しました")
        except queue.Empty: pass
        self.after(100,self._poll_events)

    def _finish_controls(self):
        self.start_btn.config(state="normal"); self.pause_btn.config(state="disabled",text="一時停止"); self.stop_btn.config(state="disabled"); self.controller=None

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno(APP_NAME,"翻訳中です。セッションを保存して終了しますか？\n完了済みバッチはキャッシュされ、次回再開できます。"):
                return
            self.save_session(active=True)
            if self.controller: self.controller.request_stop(save=True)
        self.destroy()


if __name__ == "__main__":
    app=App(); app.mainloop()
