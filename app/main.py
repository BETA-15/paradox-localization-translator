#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import contextlib
import io
import json
import os
import queue
import re
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import translator_core

APP_NAME = "Paradox Localization Translator"
APP_VERSION = "0.2.0"
DEFAULT_URL = "http://localhost:11434"
DEFAULT_MODEL = "qwen3.6:latest"


class QueueWriter(io.TextIOBase):
    def __init__(self, q: queue.Queue, kind: str = "log"):
        self.q = q
        self.kind = kind
        self._buf = ""

    def write(self, s):
        if not s:
            return 0
        self._buf += str(s)
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put((self.kind, line))
        return len(s)

    def flush(self):
        if self._buf:
            self.q.put((self.kind, self._buf))
            self._buf = ""


class TranslatorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("930x720")
        self.minsize(820, 620)

        self.events = queue.Queue()
        self.worker = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.cache_var = tk.StringVar()
        self.url_var = tk.StringVar(value=DEFAULT_URL)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.batch_var = tk.IntVar(value=40)
        self.workers_var = tk.IntVar(value=1)
        self.repair_var = tk.BooleanVar(value=True)
        self.resume_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Ollama接続を確認してください")
        self.progress_text_var = tk.StringVar(value="待機中")

        self._build_ui()
        self.after(100, self._poll_events)
        self.after(250, self.refresh_models)

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        title = ttk.Label(root, text="Paradox Localization Translator", font=("", 20, "bold"))
        title.pack(anchor="w")
        ttk.Label(root, text="Paradox系ゲームのローカライズYAMLを、OllamaのローカルLLMで日本語化・修復します。")\
            .pack(anchor="w", pady=(2, 14))

        paths = ttk.LabelFrame(root, text="ファイル / フォルダ", padding=10)
        paths.pack(fill="x")
        paths.columnconfigure(1, weight=1)

        ttk.Label(paths, text="入力").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(paths, textvariable=self.input_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(paths, text="フォルダ選択", command=self.pick_input_dir).grid(row=0, column=2, padx=(8, 0), pady=4)
        ttk.Button(paths, text="ファイル選択", command=self.pick_input_file).grid(row=0, column=3, padx=(6, 0), pady=4)

        ttk.Label(paths, text="出力").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(paths, textvariable=self.output_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(paths, text="選択", command=self.pick_output_dir).grid(row=1, column=2, padx=(8, 0), pady=4)

        ttk.Label(paths, text="キャッシュ").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(paths, textvariable=self.cache_var).grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Button(paths, text="選択", command=self.pick_cache_dir).grid(row=2, column=2, padx=(8, 0), pady=4)

        ollama = ttk.LabelFrame(root, text="Ollama", padding=10)
        ollama.pack(fill="x", pady=(10, 0))
        ollama.columnconfigure(1, weight=1)

        ttk.Label(ollama, text="URL").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(ollama, textvariable=self.url_var).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(ollama, text="接続確認", command=self.refresh_models).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(ollama, text="モデル").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.model_combo = ttk.Combobox(ollama, textvariable=self.model_var, state="normal")
        self.model_combo.grid(row=1, column=1, sticky="ew", pady=4)
        self.connection_label = ttk.Label(ollama, textvariable=self.status_var)
        self.connection_label.grid(row=1, column=2, padx=(8, 0), sticky="e")

        opts = ttk.LabelFrame(root, text="翻訳設定", padding=10)
        opts.pack(fill="x", pady=(10, 0))

        ttk.Checkbutton(opts, text="既存の日本語ファイルも走査し、英語の未翻訳箇所だけ修復する",
                        variable=self.repair_var).grid(row=0, column=0, columnspan=4, sticky="w", pady=3)
        ttk.Checkbutton(opts, text="キャッシュを使用して差分翻訳 / 再開する",
                        variable=self.resume_var).grid(row=1, column=0, columnspan=4, sticky="w", pady=3)

        ttk.Label(opts, text="バッチサイズ").grid(row=2, column=0, sticky="w", pady=(8, 3))
        ttk.Spinbox(opts, from_=1, to=500, textvariable=self.batch_var, width=8).grid(row=2, column=1, sticky="w", padx=(6, 20), pady=(8, 3))
        ttk.Label(opts, text="並列数").grid(row=2, column=2, sticky="w", pady=(8, 3))
        ttk.Spinbox(opts, from_=1, to=16, textvariable=self.workers_var, width=8).grid(row=2, column=3, sticky="w", padx=(6, 0), pady=(8, 3))
        ttk.Label(opts, text="※ Ollama既定設定では並列数1を推奨").grid(row=2, column=4, sticky="w", padx=(12, 0), pady=(8, 3))

        action = ttk.Frame(root)
        action.pack(fill="x", pady=(12, 0))
        self.start_btn = ttk.Button(action, text="翻訳開始", command=self.start_translation)
        self.start_btn.pack(side="left")
        ttk.Button(action, text="出力フォルダを開く", command=self.open_output).pack(side="left", padx=(8, 0))
        ttk.Label(action, textvariable=self.progress_text_var).pack(side="right")

        self.progress = ttk.Progressbar(root, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(8, 10))

        logframe = ttk.LabelFrame(root, text="ログ", padding=8)
        logframe.pack(fill="both", expand=True)
        self.log = tk.Text(logframe, wrap="word", height=16, state="disabled")
        scroll = ttk.Scrollbar(logframe, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def pick_input_dir(self):
        p = filedialog.askdirectory(title="入力フォルダを選択")
        if p:
            self.input_var.set(p)
            if not self.output_var.get():
                self.output_var.set(str(Path(p).parent / "翻訳後"))
            if not self.cache_var.get():
                self.cache_var.set(str(Path(p).parent / "キャッシュ"))

    def pick_input_file(self):
        p = filedialog.askopenfilename(title="YAMLファイルを選択", filetypes=[("YAML", "*.yml"), ("すべて", "*")])
        if p:
            self.input_var.set(p)
            if not self.output_var.get():
                self.output_var.set(str(Path(p).parent / "翻訳後"))
            if not self.cache_var.get():
                self.cache_var.set(str(Path(p).parent / "キャッシュ"))

    def pick_output_dir(self):
        p = filedialog.askdirectory(title="出力フォルダを選択")
        if p:
            self.output_var.set(p)

    def pick_cache_dir(self):
        p = filedialog.askdirectory(title="キャッシュフォルダを選択")
        if p:
            self.cache_var.set(p)

    def refresh_models(self):
        self.status_var.set("確認中…")
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def _fetch_models(self):
        url = self.url_var.get().strip().rstrip("/") + "/api/tags"
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            self.events.put(("models", models))
        except Exception as e:
            self.events.put(("model_error", str(e)))

    def start_translation(self):
        if self.worker and self.worker.is_alive():
            return

        in_path = Path(self.input_var.get().strip())
        if not in_path.exists():
            messagebox.showerror(APP_NAME, "入力ファイルまたはフォルダが見つかりません。")
            return
        if not self.output_var.get().strip():
            messagebox.showerror(APP_NAME, "出力フォルダを指定してください。")
            return
        if not self.model_var.get().strip():
            messagebox.showerror(APP_NAME, "Ollamaモデルを指定してください。")
            return

        out = Path(self.output_var.get().strip())
        cache = Path(self.cache_var.get().strip()) if self.cache_var.get().strip() else (out / "キャッシュ")
        out.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)

        self._clear_log()
        self.start_btn.configure(state="disabled")
        self.progress.configure(value=0, mode="indeterminate")
        self.progress.start(10)
        self.progress_text_var.set("翻訳中…")

        args = {
            "input_path": str(in_path),
            "output_path": str(out),
            "model": self.model_var.get().strip(),
            "url": self.url_var.get().strip(),
            "target_lang": "japanese",
            "workers": max(1, int(self.workers_var.get())),
            "batch_size": max(1, int(self.batch_var.get())),
            "cache_dir": str(cache),
            "resume": bool(self.resume_var.get()),
            "verbose": True,
            "include_target_files": bool(self.repair_var.get()),
        }
        self.worker = threading.Thread(target=self._run_worker, args=(args,), daemon=True)
        self.worker.start()

    def _run_worker(self, args):
        out_writer = QueueWriter(self.events, "log")
        err_writer = QueueWriter(self.events, "log")
        try:
            with contextlib.redirect_stdout(out_writer), contextlib.redirect_stderr(err_writer):
                processed = translator_core.run_translation(**args)
            out_writer.flush(); err_writer.flush()
            self.events.put(("done", processed))
        except Exception as e:
            out_writer.flush(); err_writer.flush()
            self.events.put(("fatal", str(e)))

    def _poll_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                    self._update_progress_from_log(payload)
                elif kind == "models":
                    self.model_combo["values"] = payload
                    if payload and self.model_var.get() not in payload:
                        preferred = next((m for m in payload if m.startswith("qwen3.6")), payload[0])
                        self.model_var.set(preferred)
                    self.status_var.set(f"● 接続済み ({len(payload)}モデル)")
                elif kind == "model_error":
                    self.status_var.set("● 未接続")
                    self._append_log(f"[Ollama] 接続確認失敗: {payload}")
                elif kind == "done":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=100)
                    self.progress_text_var.set("完了")
                    self.start_btn.configure(state="normal")
                    self._append_log(f"GUI: {payload}ファイルの処理を完了しました。")
                    messagebox.showinfo(APP_NAME, "翻訳処理が完了しました。")
                elif kind == "fatal":
                    self.progress.stop()
                    self.progress.configure(mode="determinate", value=0)
                    self.progress_text_var.set("エラー")
                    self.start_btn.configure(state="normal")
                    self._append_log(f"[致命的エラー] {payload}")
                    messagebox.showerror(APP_NAME, payload)
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _update_progress_from_log(self, line: str):
        m = re.search(r"バッチ\s+(\d+)/(\d+)\s+完了", line)
        if m:
            done, total = map(int, m.groups())
            if total:
                self.progress.stop()
                self.progress.configure(mode="determinate", value=done / total * 100)
                self.progress_text_var.set(f"バッチ {done}/{total}")

    def _append_log(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def open_output(self):
        p = self.output_var.get().strip()
        if not p:
            return
        Path(p).mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "darwin":
                os.system(f'open "{p}"')
            elif os.name == "nt":
                os.startfile(p)  # type: ignore[attr-defined]
            else:
                os.system(f'xdg-open "{p}" >/dev/null 2>&1 &')
        except Exception as e:
            messagebox.showerror(APP_NAME, str(e))


if __name__ == "__main__":
    TranslatorApp().mainloop()
