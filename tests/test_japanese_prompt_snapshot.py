"""翻訳以外の日本語の指示文（校正・用語統一・軽量QA・ベンチマーク）を v0.11.80 と一字一句同じに保つ。

値は tests/fixtures/japanese_prompt_snapshot.json に固定してある。LLM は呼ばず、
call_llm_raw を差し替えて送られる指示文と本文だけを記録する。
"""
from __future__ import annotations

import json
from pathlib import Path

import translator_core as core

SNAP = json.loads((Path(__file__).parent / "fixtures" / "japanese_prompt_snapshot.json").read_text(encoding="utf-8"))


def capture_prompts(monkeypatch) -> dict:
    sent = {}

    def fake(provider, url, model, user_content, system_prompt, *args, **kwargs):
        sent.setdefault("calls", []).append({"system": system_prompt, "user": user_content})
        return "0|||NO" if "YES" in system_prompt else '[{"source":"Duke","preferred":"公爵"}]'

    monkeypatch.setattr(core, "call_llm_raw", fake)
    core.proofread_text("u", "m", "公爵が来た $NAME$", "The Duke arrives $NAME$", {"Duke": "公爵"}, "CK3")
    core.proofread_text("u", "m", "公爵が来た", "", None, "General")
    core.resolve_auto_glossary_conflicts("Ollama", "u", "m",
                                         [{"source": "Duke", "variants": ["公爵", "大公"], "conflict": True}], "HOI4")
    core.classify_monitor_candidates("Ollama", "u", "m", [{"target": "Open the gate"}])
    core.benchmark_model("Ollama", "u", "m", controller=core.TranslationController())
    names = ["proofread_with_source", "proofread_plain", "glossary_conflicts", "monitor_classify", "benchmark"]
    return dict(zip(names, sent["calls"]))


def test_japanese_secondary_prompts_unchanged(monkeypatch):
    assert capture_prompts(monkeypatch) == SNAP
