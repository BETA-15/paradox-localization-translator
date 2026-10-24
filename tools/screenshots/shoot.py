import sys, os, pathlib, subprocess, time
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); tools = pathlib.Path(__file__).parent
sys.path.insert(0, str(src))
UI_LANG = os.environ.get("SHOT_UI_LANG", "japanese")      # language of the app's interface
TARGET = os.environ.get("SHOT_TARGET", "japanese")        # translation target (and the sample translation mod's language)
NATIVE = {"japanese": "Japanese", "english": "English", "french": "Français", "german": "Deutsch",
          "spanish": "Español", "korean": "한국어", "polish": "Polski", "braz_por": "Português (Brasil)",
          "russian": "Русский", "simp_chinese": "简体中文", "turkish": "Türkçe"}
try:
    import i18n
    i18n.initial_ui_language = lambda *a, **k: UI_LANG
    label = i18n.t
except ImportError:  # versions before the multilingual interface
    i18n = None
    label = None
import translator_core
translator_core._mounted_volume_roots = lambda *a, **k: []
# Never show the real local LLM setup: answer every model list with made-up names.
FAKE_MODELS = ["local-model-8b", "local-model-14b", "local-model-32b"]
translator_core.list_models = lambda *a, **k: list(FAKE_MODELS)
translator_core.unusable_model_warning = lambda *a, **k: ""
import tkinter as tk
from tkinter import ttk
_orig_mainloop = tk.Misc.mainloop
MOD = pathlib.Path.home() / "Documents/Paradox Interactive/Victoria 3/mod/Example Trade Reforms"

def winid():
    # The main window is the one on layer 0; the list can be empty for a moment, so retry.
    for _ in range(10):
        rows = subprocess.run([str(tools / "win"), str(os.getpid())], capture_output=True, text=True).stdout.splitlines()
        best = None
        for row in rows:
            parts = row.split(maxsplit=4)  # id layer width height title
            if len(parts) == 5 and parts[1] == "0" and parts[4].startswith("Paradox Localization Translator"):
                area = float(parts[2]) * float(parts[3])
                if best is None or area > best[0]:
                    best = (area, parts[0])
        if best:
            return best[1]
        time.sleep(0.5)
    raise RuntimeError("app window not found")

def cap(app, name):
    app.update(); time.sleep(0.4); app.update()
    subprocess.run(["screencapture", "-x", "-o", "-l", winid(), str(out / f"{name}.png")])
    print("captured", name, flush=True)

def walk(w):
    yield w
    for c in w.winfo_children():
        yield from walk(c)

def buttons(frame):
    res = []
    for w in walk(frame):
        try:
            if w.winfo_class() in ("TButton", "Button"):
                res.append((w.cget("text"), w))
        except Exception:
            pass
    return res

def hide_version(app):
    """Keep version numbers off the pictures (the site does not show versions)."""
    import re
    app.title("Paradox Localization Translator")
    for w in walk(app):
        try:
            if w.winfo_class() in ("TLabel", "Label") and re.fullmatch(r"v?\d+\.\d+\.\d+", str(w.cget("text"))):
                w.configure(text="")
        except Exception:
            pass

def run(app):
    nb = app.notebook
    app.after(500, lambda: hide_version(app))
    def click(tab, key, fallback):
        text = label(key) if label else fallback
        for t, w in buttons(getattr(app, tab)):
            if t == text:
                w.invoke(); print("clicked", text, flush=True); return
        print("NOT FOUND", text, flush=True)
    def entries(tab):
        return [w for w in walk(getattr(app, tab)) if w.winfo_class() in ("TEntry", "Entry")]
    def s0():
        if hasattr(app, "_set_target_lang"):
            app._set_target_lang(TARGET)
        app._append_queue(MOD)
    app.after(1500, s0)
    def s0b(): nb.select(app.tab_models); app.after(1500, lambda: cap(app, "model"))
    app.after(4000, s0b)
    def s1():
        nb.select(app.tab_status); click("tab_status", "u6.detect_game_mod_locations", "ゲーム/Mod場所を自動検出")
    app.after(7000, s1)
    def s2(): click("tab_status", "u6.research_mods_in_selected_locations", "選択した場所のModを調査")
    app.after(9000, s2)
    def s3():
        nb.select(app.tab_status)
        for w in walk(app.tab_status):
            if w.winfo_class() == "Treeview" and len(w.get_children()) == 2 and "Example" in str(w.item(w.get_children()[0], "values")):
                first = w.get_children()[0]; w.selection_set(first); w.focus(first); w.event_generate("<<TreeviewSelect>>")
        app.after(1500, lambda: cap(app, "survey"))
    app.after(19000, s3)
    def s4():
        nb.select(app.tab_review)
        es = entries("tab_review"); print("entries", len(es), flush=True)
        src_f = MOD / "localization/english/etr_l_english.yml"
        ja_f = MOD.parent / f"Example Trade Reforms - {NATIVE[TARGET]}/localization/{TARGET}/etr_l_{TARGET}.yml"
        app.review_src_var.set(str(src_f)); app.review_dst_var.set(str(ja_f))
        try:
            app.review_src_display_var.set(str(src_f)); app.review_dst_display_var.set(str(ja_f))
        except Exception: pass
        click("tab_review", "u3.load_comparison", "比較を読み込む")
    app.after(22000, s4)
    def s5(): nb.select(app.tab_review); cap(app, "qa")
    app.after(28000, s5)
    # The window can still be settling right after start-up, so the queue picture is taken last.
    def s6(): nb.select(app.tab_translate); app.after(1500, lambda: cap(app, "translate"))
    app.after(30000, s6)

def mainloop(self, n=0):
    if not getattr(mainloop, "done", False):
        mainloop.done = True; run(self)
    return _orig_mainloop(self, n)
tk.Misc.mainloop = mainloop
sys.argv = [str(src / "main.py")]
import runpy
runpy.run_path(str(src / "main.py"), run_name="__main__")
