"""Create a made-up Victoria 3 mod and a partial Japanese translation mod under <home>.

Usage: python3 make_sample.py /Users/Shared/PLT_Demo
"""
import pathlib
import sys

H = pathlib.Path(sys.argv[1])
base = H / "Documents/Paradox Interactive/Victoria 3/mod"
mod = base / "Example Trade Reforms"
tr = base / "Example Trade Reforms - Japanese"
for m, name, mid, desc, tags in (
    (mod, "Example Trade Reforms", "example.trade.reforms", "Sample mod for screenshots", "[]"),
    (tr, "Example Trade Reforms - Japanese", "example.trade.reforms.ja", "Japanese translation", '["Translation"]'),
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
        jp += [f' {k}:0 "{ja[i % 10]} {i // 10 + 1}"',
               f' {k}_desc:0 "[SCOPE.sState(\'state\').GetName]の交易路の容量が§Y+{i % 5 + 1}§!増える。"']


def write(path, head, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("﻿" + head + ":\n" + "\n".join(lines) + "\n", encoding="utf-8")


write(mod / "localization/english/etr_l_english.yml", "l_english", en)
write(tr / "localization/japanese/etr_l_japanese.yml", "l_japanese", jp)
