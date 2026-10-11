"""翻訳先が日本語のときの出力を、多言語化の前と一字一句同じに保つ。

- キャッシュのキーが変わると、利用者のこれまでの翻訳キャッシュが全部使えなくなる。
- 指示文が変わると、キャッシュに残った訳と新しい訳の調子がずれる。
値は tests/fixtures/japanese_snapshot.json（v0.11.80 の出力）に固定してある。
"""
import json
from pathlib import Path

from app import translator_core as core

SNAP = json.loads((Path(__file__).parent / "fixtures" / "japanese_snapshot.json").read_text(encoding="utf-8"))


def test_japanese_cache_keys_unchanged():
    assert core.translation_cache_key("Ollama", "qwen3:8b", "CK3", "english", "Hello [ROOT.GetName]") \
        == SNAP["cache_key_basic"]
    assert core.translation_cache_key("LM Studio", "m", "General", "english", "The king", {"king": "王"},
                                      True, "国王", "repair") == SNAP["cache_key_dual"]


def test_japanese_cache_keys_unchanged_with_explicit_target():
    assert core.translation_cache_key("Ollama", "qwen3:8b", "CK3", "english", "Hello [ROOT.GetName]",
                                      target_lang="japanese") == SNAP["cache_key_basic"]


def test_japanese_system_prompts_unchanged():
    cases = {"plain": {}, "glossary": {"glossary": {"Duke": "公爵"}}, "dual": {"dual_source": True},
             "chinese_basis": {"chinese_basis": True}, "zh_source": {}, "preset_hoi4": {"preset": "HOI4"}}
    for name, kw in cases.items():
        src = "simp_chinese" if name == "zh_source" else "english"
        assert core.build_system_prompt(src, **kw) == SNAP["prompt_" + name], name
        assert core.build_system_prompt(src, target_lang="japanese", **kw) == SNAP["prompt_" + name], name
