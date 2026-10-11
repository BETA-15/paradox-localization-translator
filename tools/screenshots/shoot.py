import sys, os, pathlib, subprocess, time
src = pathlib.Path(sys.argv[1]); out = pathlib.Path(sys.argv[2]); tools = pathlib.Path(__file__).parent
sys.path.insert(0, str(src))
import translator_core
translator_core._mounted_volume_roots = lambda *a, **k: []
import tkinter as tk
from tkinter import ttk
_orig_mainloop = tk.Misc.mainloop
MOD = pathlib.Path.home() / "Documents/Paradox Interactive/Victoria 3/mod/Example Trade Reforms"

def winid():
    r = subprocess.run([str(tools / "win"), str(os.getpid())], capture_output=True, text=True).stdout.split()
    return r[0] if r else None

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

def run(app):
    nb = app.notebook
    def click(tab, label):
        for t, w in buttons(getattr(app, tab)):
            if t == label:
                w.invoke(); print("clicked", label, flush=True); return
        print("NOT FOUND", label, flush=True)
    def entries(tab):
        return [w for w in walk(getattr(app, tab)) if w.winfo_class() in ("TEntry", "Entry")]
    def s1():
        nb.select(app.tab_status); click("tab_status", "ゲーム/Mod場所を自動検出")
    app.after(3000, s1)
    def s2(): click("tab_status", "選択した場所のModを調査")
    app.after(6000, s2)
    def s3():
        nb.select(app.tab_status)
        for w in walk(app.tab_status):
            if w.winfo_class() == "Treeview" and len(w.get_children()) == 2 and "Example" in str(w.item(w.get_children()[0], "values")):
                first = w.get_children()[0]; w.selection_set(first); w.focus(first); w.event_generate("<<TreeviewSelect>>")
        app.after(1500, lambda: cap(app, "survey"))
    app.after(16000, s3)
    def s4():
        nb.select(app.tab_review)
        es = entries("tab_review"); print("entries", len(es), flush=True)
        src_f = MOD / "localization/english/etr_l_english.yml"
        ja_f = MOD.parent / "Example Trade Reforms - Japanese/localization/japanese/etr_l_japanese.yml"
        app.review_src_var.set(str(src_f)); app.review_dst_var.set(str(ja_f))
        try:
            app.review_src_display_var.set(str(src_f)); app.review_dst_display_var.set(str(ja_f))
        except Exception: pass
        click("tab_review", "比較を読み込む")
    app.after(18000, s4)
    def s5(): nb.select(app.tab_review); cap(app, "qa")
    app.after(24000, s5)

def mainloop(self, n=0):
    if not getattr(mainloop, "done", False):
        mainloop.done = True; run(self)
    return _orig_mainloop(self, n)
tk.Misc.mainloop = mainloop
sys.argv = [str(src / "main.py")]
import runpy
runpy.run_path(str(src / "main.py"), run_name="__main__")
