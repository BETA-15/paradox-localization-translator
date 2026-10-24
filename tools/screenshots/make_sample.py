"""Create a made-up Victoria 3 mod and a partial Japanese translation mod under <home>.

Usage: python3 make_sample.py /Users/Shared/PLT_Demo [target_language]
target_language is a translator_core.TARGET_LANGUAGES key (default japanese); the translation
mod is written in that language.
"""
import pathlib
import sys

H = pathlib.Path(sys.argv[1])
LANG = sys.argv[2] if len(sys.argv) > 2 else "japanese"
NATIVE = {"japanese": "Japanese", "english": "English", "french": "Français", "german": "Deutsch",
          "spanish": "Español", "korean": "한국어", "polish": "Polski", "braz_por": "Português (Brasil)",
          "russian": "Русский", "simp_chinese": "简体中文", "turkish": "Türkçe"}
# A made-up item name and description for each language (the sample only needs plausible text).
TEXT = {
    "french": ("Accord commercial", "Augmente la capacité des routes commerciales en [SCOPE.sState('state').GetName] de §Y+{n}§!."),
    "german": ("Handelsabkommen", "Erhöht die Kapazität der Handelsrouten in [SCOPE.sState('state').GetName] um §Y+{n}§!."),
    "spanish": ("Acuerdo comercial", "Aumenta la capacidad de las rutas comerciales en [SCOPE.sState('state').GetName] en §Y+{n}§!."),
    "korean": ("무역 협정", "[SCOPE.sState('state').GetName]의 무역로 용량이 §Y+{n}§! 증가합니다."),
    "polish": ("Umowa handlowa", "Zwiększa przepustowość szlaków handlowych w [SCOPE.sState('state').GetName] o §Y+{n}§!."),
    "braz_por": ("Acordo comercial", "Aumenta a capacidade das rotas comerciais em [SCOPE.sState('state').GetName] em §Y+{n}§!."),
    "russian": ("Торговое соглашение", "Увеличивает пропускную способность торговых путей в [SCOPE.sState('state').GetName] на §Y+{n}§!."),
    "simp_chinese": ("贸易协定", "[SCOPE.sState('state').GetName]的贸易路线容量增加§Y+{n}§!。"),
    "turkish": ("Ticaret anlaşması", "[SCOPE.sState('state').GetName] bölgesindeki ticaret yollarının kapasitesini §Y+{n}§! artırır."),
    "english": ("Trade accord", "Raises trade route capacity in [SCOPE.sState('state').GetName] by §Y+{n}§!."),
}
base = H / "Documents/Paradox Interactive/Victoria 3/mod"
mod = base / "Example Trade Reforms"
tr = base / f"Example Trade Reforms - {NATIVE[LANG]}"
for m, name, mid, desc, tags in (
    (mod, "Example Trade Reforms", "example.trade.reforms", "Sample mod for screenshots", "[]"),
    (tr, f"Example Trade Reforms - {NATIVE[LANG]}", f"example.trade.reforms.{LANG}", "Translation", '["Translation"]'),
):
    (m / ".metadata").mkdir(parents=True, exist_ok=True)
    (m / ".metadata/metadata.json").write_text(
        f'{{"name":"{name}","id":"{mid}","version":"1.0","supported_game_version":"1.8.*",'
        f'"short_description":"{desc}","tags":{tags},"relationships":[],'
        '"game_custom_data":{"multiplayer_synchronized":true}}',
        encoding="utf-8",
    )
words = ["Free Trade Accord", "Customs Union", "Harbor Authority", "Merchant Guild", "Tariff Board",
         "Grain Exchange", "Silk Route Charter", "Coastal Convoy", "Bonded Warehouse", "Trade Envoy"]
ja = ["自由貿易協定", "関税同盟", "港湾局", "商人ギルド", "関税委員会", "穀物取引所", "絹の道の特許状",
      "沿岸護送船団", "保税倉庫", "通商使節"]
en, jp = [], []
for i in range(140):
    k = f"etr_item_{i:03d}"
    en += [f' {k}:0 "{words[i % 10]} {i // 10 + 1}"',
           f' {k}_desc:0 "Increases trade route capacity in [SCOPE.sState(\'state\').GetName] by §Y+{i % 5 + 1}§!."']
    if i < 118:  # leave the last 22 items (44 keys) untranslated
        if LANG == "japanese":
            jp += [f' {k}:0 "{ja[i % 10]}（{i // 10 + 1}）"',
                   f' {k}_desc:0 "[SCOPE.sState(\'state\').GetName]の交易路の容量が§Y+{i % 5 + 1}§!増える。"']
        else:
            name, desc = TEXT[LANG]
            jp += [f' {k}:0 "{name} {i + 1}"', f' {k}_desc:0 "{desc.format(n=i % 5 + 1)}"']


def write(path, head, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("﻿" + head + ":\n" + "\n".join(lines) + "\n", encoding="utf-8")


write(mod / "localization/english/etr_l_english.yml", "l_english", en)
write(tr / f"localization/{LANG}/etr_l_{LANG}.yml", f"l_{LANG}", jp)
