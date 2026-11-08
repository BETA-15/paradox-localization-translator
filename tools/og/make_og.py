#!/usr/bin/env python3
"""Build 1200x630 Open Graph cards: assets/og/<code>.png (Pillow only).
Usage: python3 tools/og/make_og.py [code ...]   (no args = all languages in site.json)"""
import json, os, sys
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BG, INK, MUTED, ACCENT = "#0e1620", "#e6e0d2", "#9aa6b4", "#e3c06d"  # --ink/--text/--muted/--brass-2
W, H, SPLIT = 1200, 630, 660
S = "/System/Library/Fonts/"
LATIN = [("/System/Library/Fonts/Supplemental/Arial Bold.ttf", 0)]
FONTS = {  # code -> candidate (path, ttc index); first existing wins
    "ja": [(S + "ヒラギノ角ゴシック W6.ttc", 0)],
    "zh-Hans": [("/System/Library/AssetsV2/com_apple_MobileAsset_Font8/86ba2c91f017a3749571a82f2c6d890ac7ffb2fb.asset/AssetData/PingFang.ttc", 11),
                (S + "Hiragino Sans GB.ttc", 0)],
    "ko": [(S + "AppleSDGothicNeo.ttc", 6)],
}
CJK = {"ja", "zh-Hans", "ko"}

def font(code, size):
    for path, idx in FONTS.get(code, LATIN):
        if os.path.exists(path):
            f = ImageFont.truetype(path, size, index=idx)
            try: f.set_variation_by_name("Bold")
            except Exception: pass
            return f
    raise SystemExit("no font for " + code)

def runs_of(chars):  # [(ch, flag)] -> [(text, flag)]
    out = []
    for ch, fl in chars:
        if out and out[-1][1] == fl: out[-1][0] += ch
        else: out.append([ch, fl])
    return out

def parse(title):  # strip ** markers, remember accent flag per char
    chars, on = [], False
    for part in title.split("**"):
        chars += [(c, on) for c in part]
        on = not on
    return chars

NO_START = set("、。，．,.！？!?：；:;）」』）”%")

def tokens(chars, cjk):  # unbreakable units: words (latin, trailing space kept) / CJK chars (ASCII runs whole)
    toks = []
    for c in chars:
        prev = toks[-1][-1][0] if toks else ""
        if not toks: toks.append([c])
        elif not cjk:
            if prev == " " and c[0] != " ": toks.append([c])
            else: toks[-1].append(c)
        elif c[0] in NO_START or c[0] == " " or (c[0].isascii() and prev.isascii() and prev != " "):
            toks[-1].append(c)
        else: toks.append([c])
    return toks

def wrap(chars, f, width, cjk):
    lines, line = [], []
    for t in tokens(chars, cjk):
        trial = line + t
        if line and f.getlength("".join(c for c, _ in trial).rstrip()) > width:
            lines.append(line); line = t
        else: line = trial
    if line: lines.append(line)
    return [l[:-1] if l and l[-1][0] == " " else l for l in lines]

def headline(code, chars, width, maxh):
    for size in range(54, 28, -2):
        f = font(code, size)
        lines = wrap(chars, f, width, code in CJK)
        lh = int(size * 1.28)
        if len(lines) <= 3 and len(lines) * lh <= maxh and all(f.getlength("".join(c for c, _ in l)) <= width for l in lines):
            return f, lines, lh
    return f, lines[:3], lh

SHORT = {"Crusader Kings III (CK3)": "CK3", "Hearts of Iron IV (HOI4)": "HOI4", "Europa Universalis IV (EU4)": "EU4",
         "Europa Universalis V (EU5)": "EU5", "Imperator: Rome": "Imperator"}
ORDER = ["CK3", "Victoria 3", "HOI4", "Stellaris", "EU4", "EU5", "Imperator"]

def games_for(code):  # only the games that can display this page's language (site.json games)
    site = json.load(open(f"{ROOT}/site.json", encoding="utf-8"))
    tag = next(l["game"] for l in site["languages"] if l["code"] == code)
    names = [SHORT.get(g["name"], g["name"]) for g in site["games"] if g["langs"] == "all" or tag in g["langs"]]
    return sorted(names, key=ORDER.index)

def build(code):
    t = json.load(open(f"{ROOT}/i18n/{code}.json", encoding="utf-8"))["hero"]["title"]
    im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
    # screenshot (right)
    shot = Image.open(f"{ROOT}/assets/shots/{code}/translate.webp").convert("RGB").crop((0, 0, 900, 760))
    shot = shot.resize((560, 473), Image.LANCZOS)
    sx, sy = 700, 100
    mask = Image.new("L", shot.size, 0); ImageDraw.Draw(mask).rounded_rectangle((0, 0, *shot.size), 16, fill=255)
    d.rounded_rectangle((sx - 1, sy - 1, sx + shot.width, sy + shot.height), 17, outline="#3a4a5c")
    im.paste(shot, (sx, sy), mask)
    # brand row
    x0 = 64
    icon = Image.open(f"{ROOT}/assets/icon.png").convert("RGBA").resize((64, 64), Image.LANCZOS)
    im.paste(icon, (x0, 56), icon)
    fb = font("en", 32)
    d.text((x0 + 84, 88), "Paradox Localization Translator", font=fb, fill=INK, anchor="lm")
    # headline
    f, lines, lh = headline(code, parse(t), SPLIT - x0 - 20, 300)
    y = 190
    for line in lines:
        x = x0
        for txt, acc in runs_of(line):
            d.text((x, y), txt, font=f, fill=ACCENT if acc else INK)
            x += f.getlength(txt)
        y += lh
    # footer
    d.text((x0, 506), " · ".join(games_for(code)), font=font("en", 22), fill=MUTED)
    d.text((x0, 548), "Free · MIT · Windows / macOS / Linux", font=font("en", 20), fill=MUTED)
    out = f"{ROOT}/assets/og/{code}.png"
    im.save(out, optimize=True)
    if os.path.getsize(out) > 300_000:
        im.quantize(256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)
    print(code, os.path.getsize(out) // 1024, "KB")

if __name__ == "__main__":
    os.makedirs(f"{ROOT}/assets/og", exist_ok=True)
    codes = sys.argv[1:] or [l["code"] for l in json.load(open(f"{ROOT}/site.json", encoding="utf-8"))["languages"]]
    for c in codes: build(c)
