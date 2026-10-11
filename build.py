#!/usr/bin/env python3
"""Build the static site: template.html + i18n/<code>.json + site.json -> index.html, <slug>/index.html.

Only the Python standard library is used. Run:  python3 build.py
Languages are built only when i18n/<code>.json exists. Missing strings fall back to English
and are listed at the end so translators can fill them.
"""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = json.loads((ROOT / "site.json").read_text(encoding="utf-8"))
TEMPLATE = (ROOT / "template.html").read_text(encoding="utf-8")
LANGS = SITE["languages"]
ALL_GAME_LANGS = [lang["game"] for lang in LANGS]
SHORT = {
    "l_english": "EN", "l_french": "FR", "l_german": "DE", "l_spanish": "ES", "l_japanese": "JA",
    "l_korean": "KO", "l_polish": "PL", "l_braz_por": "PT", "l_russian": "RU",
    "l_simp_chinese": "ZH", "l_turkish": "TR",
}
TOKEN = re.compile(r"(\[[^\]]*\]|\$[^$]*\$|£[^£]*£|§[A-Za-z]|§!)")

missing: dict[str, list[str]] = {}
warnings: list[str] = []


def inline(text: str) -> str:
    """Escape, then allow `code` and **emphasis**."""
    out = html.escape(text, quote=True)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<em>\1</em>", out)
    return out


def highlight(line: str) -> str:
    parts = TOKEN.split(line)
    return "".join(
        f'<span class="tok">{html.escape(p)}</span>' if i % 2 else html.escape(p)
        for i, p in enumerate(parts)
    )


def lookup(data: dict, path: str):
    node = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def get(texts: dict, en: dict, code: str, path: str):
    value = lookup(texts, path)
    if value is None:
        missing.setdefault(code, []).append(path)
        value = lookup(en, path)
    if value is None:
        raise KeyError(f"{path} is missing in en.json too")
    return value


def page_url(lang: dict) -> str:
    return SITE["base_url"] + (lang["slug"] + "/" if lang["slug"] else "")


def build_matrix(t, page_game: str) -> str:
    head = "".join(
        f'<th scope="col" title="{html.escape(l["name"])}"'
        f'{" class=here" if l["game"] == page_game else ""}>{SHORT[l["game"]]}</th>'
        for l in LANGS
    )
    rows = []
    for game in SITE["games"]:
        langs = game["langs"]
        cells = []
        if langs == "pending":
            count = f'{t("games.count").replace("{n}", str(game["count"]))} · {t("games.pending")}'
            cells = [f'<td class="pending{" here" if g == page_game else ""}">·</td>' for g in ALL_GAME_LANGS]
            warnings.append(f'{game["name"]}: language list is still pending')
        else:
            have = ALL_GAME_LANGS if langs == "all" else langs
            count = t("games.all") if langs == "all" else t("games.count").replace("{n}", str(len(have)))
            for g in ALL_GAME_LANGS:
                cls = ["yes" if g in have else "no"] + (["here"] if g == page_game else [])
                cells.append(f'<td class="{" ".join(cls)}">{"✓" if g in have else "–"}</td>')
        rows.append(
            f'<tr><th scope="row">{html.escape(game["name"])}<span class="count">{inline(count)}</span></th>'
            + "".join(cells) + "</tr>"
        )
    return (
        f'<table class="matrix"><thead><tr><th scope="col">{inline(t("games.game"))}</th>{head}</tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table>'
    )


def shot_src(name: str, code: str) -> tuple[str, bool] | None:
    """Return (path, borrowed). borrowed = the picture shows another language's UI (site.json shots_fallback)."""
    fallback = SITE.get("shots_fallback")
    folders = [(f"assets/shots/{code}", False), ("assets/shots", False)]
    if fallback and fallback != code:
        folders.append((f"assets/shots/{fallback}", True))
    for folder, borrowed in folders:
        for ext in ("webp", "png"):
            if (ROOT / folder / f"{name}.{ext}").exists():
                return f"{folder}/{name}.{ext}", borrowed
    return None


def build_page(lang: dict, built: list[dict], en: dict) -> str:
    code = lang["code"]
    texts = json.loads((ROOT / "i18n" / f"{code}.json").read_text(encoding="utf-8"))
    t = lambda path: get(texts, en, code, path)  # noqa: E731
    root = "../" if lang["slug"] else ""

    ctx: dict[str, str] = {}
    for key in ("base_url", "repo_url", "release_url", "author_url"):
        ctx[key] = html.escape(SITE[key])
    for os_name, url in SITE["downloads"].items():
        ctx[f"downloads.{os_name}"] = html.escape(url)

    ctx.update({
        "lang": html.escape(lang["hreflang"]),
        "lang_name": html.escape(lang["name"]),
        "root": root,
        "slug_path": lang["slug"] + "/" if lang["slug"] else "",
        "canonical": html.escape(page_url(lang)),
    })

    alternates = [
        f'<link rel="alternate" hreflang="{l["hreflang"]}" href="{html.escape(page_url(l))}">' for l in built
    ]
    alternates.append(f'<link rel="alternate" hreflang="x-default" href="{html.escape(SITE["base_url"])}">')
    ctx["hreflang"] = "\n".join(alternates)
    ctx["langmenu"] = "".join(
        f'<li><a href="{root}{l["slug"] + "/" if l["slug"] else ""}" hreflang="{l["hreflang"]}" lang="{l["hreflang"]}"'
        f'{" aria-current=page" if l is lang else ""}>{html.escape(l["name"])}</a></li>'
        for l in built
    )

    ctx["badges"] = "".join(f"<li>{inline(b)}</li>" for b in t("hero.badges"))
    ctx["features_html"] = "".join(
        f'<article class="card"><span class="num">{i:02d}</span><h3>{inline(f["title"])}</h3><p>{inline(f["text"])}</p></article>'
        for i, f in enumerate(t("features.items"), 1)
    )

    shots = []
    borrowed_any = False
    for shot in SITE["shots"]:
        caption = inline(t(f'shots.items.{shot["file"]}'))
        found = shot_src(shot["file"], code)
        src, borrowed = found if found else (None, False)
        borrowed_any = borrowed_any or borrowed
        if src:
            shots.append(
                f'<figure class="shot"><button type="button" class="zoom" data-full="{root}{src}">'
                f'<img src="{root}{src}" alt="{caption}" width="{shot["w"]}" height="{shot["h"]}" loading="lazy"></button>'
                f"<figcaption>{caption}</figcaption></figure>"
            )
        else:
            warnings.append(f'{code}: screenshot "{shot["file"]}" not found')
            shots.append(
                f'<figure class="shot empty"><div class="ph">{inline(t("shots.pending"))}</div><figcaption>{caption}</figcaption></figure>'
            )
    ctx["shots_html"] = "".join(shots)
    # Shown while a page borrows another language's UI pictures; disappears once its own pictures exist.
    ctx["shots_note"] = f'<p class="intro">{inline(t("shots.ui_note"))}</p>' if borrowed_any else ""

    page_game = lang["game"]
    ctx["matrix"] = build_matrix(t, page_game)
    ctx["steps"] = "".join(
        f'<li><h3>{inline(s["title"])}</h3><p>{inline(s["text"])}</p></li>' for s in t("howto.steps")
    )
    ctx["publish_items"] = "".join(
        f'<li><strong>{inline(i["title"])}</strong> {inline(i["text"])}</li>' for i in t("publish.items")
    )
    ctx["faq_html"] = "".join(
        f'<details><summary>{inline(i["q"])}</summary><p>{inline(i["a"])}</p></details>' for i in t("faq.items")
    )

    if SITE["donate"]:
        if not SITE["sponsor_url"]:
            sys.exit("site.json: donate is true but sponsor_url is empty")
        ctx["donate_html"] = (
            f'<section id="donate" class="band donate"><h2>{inline(t("donate.title"))}</h2>'
            f'<p>{inline(t("donate.text"))}</p>'
            f'<a class="btn" href="{html.escape(SITE["sponsor_url"])}">{inline(t("donate.button"))} ♥</a></section>'
        )
    else:
        ctx["donate_html"] = ""

    demo = SITE["demo"]
    order = [g for g in ALL_GAME_LANGS if g != "l_english"]
    first = page_game if page_game in demo["lines"] else "l_japanese"
    order = order[order.index(first):] + order[: order.index(first)]
    ctx["demo.key"] = html.escape(demo["key"])
    ctx["demo.source"] = highlight(demo["source"])
    ctx["demo.first_lang"] = first
    ctx["demo.first_line"] = highlight(demo["lines"][first])
    ctx["suggest_close"] = html.escape(t("suggest_close"))

    js = {
        "here": lang["hreflang"],
        "langs": [
            {"tag": l["hreflang"], "href": root + (l["slug"] + "/" if l["slug"] else ""),
             "text": json.loads((ROOT / "i18n" / f'{l["code"]}.json').read_text(encoding="utf-8")).get("suggest", "")}
            for l in built
        ],
        "demo": [[g, highlight(demo["lines"][g])] for g in order],
    }
    ctx["js_data"] = json.dumps(js, ensure_ascii=False).replace("</", "<\\/")

    def fill(match: re.Match) -> str:
        key = match.group(1)
        if key in ctx:
            return ctx[key]
        value = t(key)
        if not isinstance(value, str):
            raise TypeError(f"{key} is not a string")
        return inline(value)

    return re.sub(r"\{\{([a-zA-Z0-9_.]+)\}\}", fill, TEMPLATE)


def main() -> None:
    en = json.loads((ROOT / "i18n" / "en.json").read_text(encoding="utf-8"))
    built = [l for l in LANGS if (ROOT / "i18n" / f'{l["code"]}.json').exists()]
    for lang in built:
        out = ROOT / lang["slug"] / "index.html" if lang["slug"] else ROOT / "index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build_page(lang, built, en), encoding="utf-8")
        print(f"built {out.relative_to(ROOT)}")

    sitemap = ['<?xml version="1.0" encoding="UTF-8"?>',
               '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    sitemap += [f"  <url><loc>{html.escape(page_url(l))}</loc></url>" for l in built]
    sitemap.append("</urlset>")
    (ROOT / "sitemap.xml").write_text("\n".join(sitemap) + "\n", encoding="utf-8")

    for code, paths in missing.items():
        print(f"[{code}] {len(paths)} string(s) fell back to English: {', '.join(paths)}")
    for w in dict.fromkeys(warnings):
        print(f"warning: {w}")


if __name__ == "__main__":
    main()
