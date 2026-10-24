"""試験の共通の準備。

app/main.py は import したときにデータの置き場所を決め、古い場所からのファイルの写し（移行）と記録を書く。
試験が利用者の本物の置き場所（~/Documents/Paradox Localization Translator）に書かないよう、
どの試験より先に、置き場所を一時フォルダに向ける（2026-10-12、試験の実行で storage_migration.json が書かれていた）。
"""
import os
import tempfile

if not os.environ.get("PARADOX_TRANSLATOR_DATA_ROOT"):
    os.environ["PARADOX_TRANSLATOR_DATA_ROOT"] = tempfile.mkdtemp(prefix="plt-test-data-")
