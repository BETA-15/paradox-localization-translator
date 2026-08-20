#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core engine for Paradox Localization Translator v0.6.0.

Features:
- Batch translation via Ollama, LM Studio, OpenAI, Anthropic, Gemini, or OpenAI-compatible APIs
- Resume cache and persistent session checkpoints
- Pause / save-and-stop controller
- Repair untranslated English in Japanese files
- Paradox token protection and QA
- Glossary-aware prompts
- English + Simplified Chinese dual-source translation
- Multi-project queue support through GUI callbacks
"""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import math
import re
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

DEFAULT_MODEL = "qwen3.6:latest"
DEFAULT_OLLAMA_URL = "http://localhost:11434"
DEFAULT_LMSTUDIO_URL = "http://localhost:1234/v1"
DEFAULT_OPENAI_URL = "https://api.openai.com/v1"
DEFAULT_ANTHROPIC_URL = "https://api.anthropic.com/v1"
DEFAULT_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_OPENAI_COMPAT_URL = ""
DEFAULT_TARGET_LANG = "japanese"
CACHE_FILE_NAME = "translate_cache.json"
SESSION_FILE_NAME = ".plt_session.json"

SOURCE_MANIFEST_NAME = "source_manifest.json"
JOB_META_NAME = "job_meta.json"

BATCH_LINE_SEP = "|||"
DUAL_SEP = " ⟪ZH_REF⟫ "

KNOWN_SOURCE_LANGS = [
    "english", "simp_chinese", "german", "french", "spanish",
    "russian", "polish", "braz_por", "japanese", "korean",
]

LINE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-\'&][A-Za-z0-9_.\-\'& ]*)\s*:\s*'
    r'(?P<version>\d+\s+)?'
    r'"(?P<value>(?:[^"\\]|\\.)*)"'
    r'(?P<trailing>.*)$'
)
LOOSE_LINE_PATTERN = re.compile(
    r'^(?P<indent>\s*)(?P<key>[A-Za-z0-9_.\-\'&][A-Za-z0-9_.\-\'& ]*)\s*:\s*'
    r'(?P<version>\d+\s+)?'
    r'"(?P<value>.*)"\s*(?P<trailing>#.*)?$'
)
HEADER_PATTERN = re.compile(r'^\s*l_(?P<lang>[a-z_]+)\s*:\s*$')

PROTECT_PATTERNS = [
    r'\[[^\[\]]*\]', r'\$[^\$]+\$', r'£[^£]+£', r'@[A-Za-z_]+!',
    r'§[A-Za-z!]', r'#[A-Za-z_]+(?:;[^#]*)?', r'#!', r'\\n', r'\\"',
]
PROTECT_RE = re.compile('(' + '|'.join(PROTECT_PATTERNS) + ')')
PLACEHOLDER_PREFIX = "@@"
PLACEHOLDER_SUFFIX = "@@"
PLACEHOLDER_RE = re.compile(re.escape(PLACEHOLDER_PREFIX) + r'(\d+)' + re.escape(PLACEHOLDER_SUFFIX))
PLACEHOLDER_FALLBACK_RE = re.compile(re.escape(PLACEHOLDER_PREFIX) + r'(\d+)\D{0,2}')

GAME_PRESETS = {
    "General": "Paradox Interactiveゲーム全般。簡潔で自然なUI日本語を優先する。",
    "CK3": "Crusader Kings III。中世の称号・封建制・宮廷・宗教・制度の歴史語彙を重視する。",
    "Victoria 3": "Victoria 3。19世紀の政治・経済・産業・外交用語を重視する。",
    "HOI4": "Hearts of Iron IV。20世紀前半の軍事・政治・外交・装備用語を重視する。",
    "Stellaris": "Stellaris。SF、宇宙政治、技術、艦船、異星文明の用語を自然に訳す。",
}


class StopRequested(Exception):
    pass


@dataclass
class TranslationController:
    pause_event: threading.Event = field(default_factory=threading.Event)
    stop_event: threading.Event = field(default_factory=threading.Event)
    save_stop_event: threading.Event = field(default_factory=threading.Event)
    progress_callback: Optional[Callable[[dict], None]] = None
    checkpoint_callback: Optional[Callable[[dict], None]] = None

    def pause(self):
        self.pause_event.set()

    def resume(self):
        self.pause_event.clear()

    def request_stop(self, save: bool = True):
        if save:
            self.save_stop_event.set()
        self.stop_event.set()

    def wait_if_paused(self):
        while self.pause_event.is_set() and not self.stop_event.is_set():
            time.sleep(0.15)
        if self.stop_event.is_set():
            raise StopRequested()

    def notify(self, **payload):
        if self.progress_callback:
            self.progress_callback(payload)

    def checkpoint(self, payload: dict):
        if self.checkpoint_callback:
            self.checkpoint_callback(payload)


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def load_cache(path: Path) -> dict:
    return load_json(path, {})


def save_cache(path: Path, cache: dict):
    save_json(path, cache)


def load_glossary(path: Optional[Path]) -> dict:
    if not path:
        return {}
    data = load_json(path, {})
    if isinstance(data, dict):
        return {str(k): str(v) for k, v in data.items() if str(k).strip()}
    return {}


def save_glossary(path: Path, glossary: dict):
    save_json(path, glossary)


def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def protect_text(value: str):
    tokens = []
    def repl(m):
        tokens.append(m.group(0))
        return f"{PLACEHOLDER_PREFIX}{len(tokens)-1}{PLACEHOLDER_SUFFIX}"
    return PROTECT_RE.sub(repl, value), tokens


def restore_text(translated: str, tokens: list) -> str:
    def repl(m):
        idx = int(m.group(1))
        return tokens[idx] if 0 <= idx < len(tokens) else m.group(0)
    result = PLACEHOLDER_RE.sub(repl, translated)
    if PLACEHOLDER_PREFIX in result:
        result = PLACEHOLDER_FALLBACK_RE.sub(repl, result)
    return result


def extract_protected_tokens(value: str) -> List[str]:
    return PROTECT_RE.findall(value)


def looks_untranslatable(value: str) -> bool:
    stripped = PROTECT_RE.sub('', value).strip()
    return not bool(re.search(r'[A-Za-z0-9\u3040-\u30ff\u4e00-\u9fff]', stripped))


def looks_foreign_in_target(value: str, target_lang: str) -> bool:
    if target_lang != "japanese":
        return False
    plain = PROTECT_RE.sub('', value).strip()
    if not plain or re.search(r'[\u3040-\u30ff\u4e00-\u9fff]', plain):
        return False
    words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", plain)
    letters = ''.join(words)
    if not words or len(letters) < 4:
        return False
    if len(words) == 1 and words[0].isupper() and len(words[0]) <= 6:
        return False
    return len(words) >= 2 or (len(words[0]) >= 4 and any(c.islower() for c in words[0]))


def looks_untranslated(original: str, translated: str, source_lang: str) -> bool:
    if not original or not translated:
        return False
    orig = original.strip()
    trans = translated.strip()
    orig_plain = PROTECT_RE.sub('', orig).strip()
    trans_plain = PROTECT_RE.sub('', trans).strip()
    if not orig_plain:
        return False
    if orig == trans:
        if source_lang == "english":
            words = re.findall(r"[A-Za-z]+(?:'[A-Za-z]+)?", orig_plain)
            if sum(len(w) for w in words) >= 4 and any(len(w) >= 4 for w in words):
                return True
        if source_lang == "simp_chinese" and re.search(r'[\u4e00-\u9fff]', orig_plain):
            return True
    if source_lang == "english":
        english_chars = len(re.findall(r'[A-Za-z]', trans_plain))
        kana = len(re.findall(r'[\u3040-\u30ff]', trans_plain))
        if english_chars >= 12 and kana == 0 and re.search(r'[A-Za-z]{3,}\s+[A-Za-z]{2,}', trans_plain):
            return True
    return False


def cache_entry_is_valid(original: str, cached: str, source_lang: str) -> bool:
    return not looks_untranslated(original, cached, source_lang)


def glossary_for_prompt(glossary: dict, values: Iterable[str], max_items: int = 80) -> List[Tuple[str, str]]:
    joined = "\n".join(values).lower()
    matched = []
    for src, dst in glossary.items():
        if src.lower() in joined:
            matched.append((src, dst))
            if len(matched) >= max_items:
                break
    return matched


def normalize_provider(provider: str) -> str:
    p = (provider or "Ollama").strip().lower()
    aliases = {
        "ollama": "ollama",
        "lm studio": "lmstudio", "lmstudio": "lmstudio", "lm_studio": "lmstudio",
        "openai": "openai", "openai api": "openai",
        "anthropic": "anthropic", "claude": "anthropic",
        "gemini": "gemini", "google gemini": "gemini",
        "openai compatible": "openai_compat", "openai互換": "openai_compat",
        "openai_compatible": "openai_compat", "custom": "openai_compat",
    }
    return aliases.get(p, "ollama")


def provider_display_name(provider: str) -> str:
    return {
        "ollama": "Ollama", "lmstudio": "LM Studio", "openai": "OpenAI",
        "anthropic": "Anthropic", "gemini": "Gemini",
        "openai_compat": "OpenAI Compatible",
    }[normalize_provider(provider)]


def default_url_for_provider(provider: str) -> str:
    return {
        "ollama": DEFAULT_OLLAMA_URL,
        "lmstudio": DEFAULT_LMSTUDIO_URL,
        "openai": DEFAULT_OPENAI_URL,
        "anthropic": DEFAULT_ANTHROPIC_URL,
        "gemini": DEFAULT_GEMINI_URL,
        "openai_compat": DEFAULT_OPENAI_COMPAT_URL,
    }[normalize_provider(provider)]


def env_api_key_for_provider(provider: str) -> str:
    p = normalize_provider(provider)
    names = {
        "openai": ["OPENAI_API_KEY"],
        "anthropic": ["ANTHROPIC_API_KEY"],
        "gemini": ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
        "openai_compat": ["PLT_API_KEY", "OPENAI_API_KEY"],
    }.get(p, [])
    import os
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _headers_for_provider(provider: str, api_key: str = "") -> dict:
    p = normalize_provider(provider)
    key = (api_key or env_api_key_for_provider(provider)).strip()
    headers = {"Content-Type": "application/json"}
    if p in {"openai", "openai_compat"} and key:
        headers["Authorization"] = f"Bearer {key}"
    elif p == "anthropic":
        if key:
            headers["x-api-key"] = key
        headers["anthropic-version"] = "2023-06-01"
    elif p == "gemini" and key:
        headers["x-goog-api-key"] = key
    return headers


def list_models(provider: str, url: str, timeout: int = 5, api_key: str = "") -> List[str]:
    p = normalize_provider(provider)
    base = (url or default_url_for_provider(provider)).rstrip('/')
    if p == "ollama":
        endpoint = base + "/api/tags"
        req = urllib.request.Request(endpoint)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("name") for m in data.get("models", []) if m.get("name")]
    if p in {"lmstudio", "openai", "openai_compat"}:
        if not base.endswith('/v1') and p != "openai_compat":
            base += '/v1'
        endpoint = base + "/models"
        req = urllib.request.Request(endpoint, headers=_headers_for_provider(provider, api_key))
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("id") for m in data.get("data", []) if m.get("id")]
    if p == "anthropic":
        endpoint = base + "/models"
        req = urllib.request.Request(endpoint, headers=_headers_for_provider(provider, api_key))
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [m.get("id") for m in data.get("data", []) if m.get("id")]
    if p == "gemini":
        endpoint = base + "/models"
        req = urllib.request.Request(endpoint, headers=_headers_for_provider(provider, api_key))
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        out = []
        for m in data.get("models", []):
            name = m.get("name", "")
            methods = m.get("supportedGenerationMethods") or []
            if name and (not methods or "generateContent" in methods):
                out.append(name.split("models/", 1)[-1])
        return out
    return []

def _metric(provider: str, model: str, elapsed: float, success: bool,
            completion_tokens: Optional[int] = None,
            provider_tps: Optional[float] = None, error: str = "") -> dict:
    tps = provider_tps
    if (not tps) and completion_tokens and elapsed > 0:
        tps = completion_tokens / elapsed
    return {
        "provider": provider_display_name(provider),
        "model": model,
        "elapsed": float(elapsed),
        "success": bool(success),
        "completion_tokens": int(completion_tokens or 0),
        "tokens_per_second": float(tps or 0.0),
        "error": error,
        "timestamp": time.time(),
    }


def call_llm_raw(provider: str, url: str, model: str, user_content: str, system_prompt: str,
                 timeout: int = 300, retries: int = 5,
                 controller: Optional[TranslationController] = None,
                 temperature: float = 0.2, api_key: str = "") -> str:
    """Call local or cloud LLM APIs and emit per-request performance metrics."""
    p = normalize_provider(provider)
    base = (url or default_url_for_provider(provider)).rstrip('/')
    last_err = None
    overall_start = time.perf_counter()
    activity_id = f"{threading.get_ident()}-{time.time_ns()}"
    for attempt in range(retries):
        if controller:
            controller.wait_if_paused()
            controller.notify(kind="llm_activity", state="start", activity_id=activity_id, provider=provider_display_name(provider), model=model, attempt=attempt + 1, retries=retries)
        try:
            started = time.perf_counter()
            headers = _headers_for_provider(provider, api_key)
            if p == "ollama":
                endpoint = base + "/api/chat"
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt},
                                 {"role": "user", "content": user_content}],
                    "stream": False, "options": {"temperature": temperature},
                }
            elif p in {"lmstudio", "openai_compat"}:
                if p == "lmstudio" and not base.endswith('/v1'):
                    base += '/v1'
                endpoint = base + "/chat/completions"
                payload = {
                    "model": model,
                    "messages": [{"role": "system", "content": system_prompt},
                                 {"role": "user", "content": user_content}],
                    "stream": False, "temperature": temperature,
                }
            elif p == "openai":
                if not base.endswith('/v1'):
                    base += '/v1'
                endpoint = base + "/responses"
                payload = {"model": model, "instructions": system_prompt, "input": user_content}
            elif p == "anthropic":
                endpoint = base + "/messages"
                payload = {
                    "model": model, "max_tokens": 8192, "system": system_prompt,
                    "messages": [{"role": "user", "content": user_content}],
                    "temperature": temperature,
                }
            elif p == "gemini":
                endpoint = base + f"/models/{model}:generateContent"
                payload = {
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "contents": [{"role": "user", "parts": [{"text": user_content}]}],
                }
            else:
                raise RuntimeError(f"未対応のプロバイダです: {provider}")
            req = urllib.request.Request(endpoint, data=json.dumps(payload).encode("utf-8"), headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            elapsed = max(time.perf_counter() - started, 1e-6)
            completion_tokens = 0
            provider_tps = 0.0
            if p == "ollama":
                content = body.get("message", {}).get("content", "")
                completion_tokens = int(body.get("eval_count") or 0)
                eval_duration = float(body.get("eval_duration") or 0)
                if completion_tokens and eval_duration > 0:
                    provider_tps = completion_tokens / (eval_duration / 1_000_000_000)
            elif p in {"lmstudio", "openai_compat"}:
                choices = body.get("choices") or []
                content = (((choices[0] if choices else {}).get("message") or {}).get("content") or "")
                completion_tokens = int((body.get("usage") or {}).get("completion_tokens") or 0)
            elif p == "openai":
                content = body.get("output_text") or ""
                if not content:
                    parts = []
                    for item in body.get("output") or []:
                        for c in item.get("content") or []:
                            if c.get("type") in {"output_text", "text"} and c.get("text"):
                                parts.append(c.get("text"))
                    content = "".join(parts)
                completion_tokens = int((body.get("usage") or {}).get("output_tokens") or 0)
            elif p == "anthropic":
                content = "".join(x.get("text", "") for x in (body.get("content") or []) if x.get("type") == "text")
                completion_tokens = int((body.get("usage") or {}).get("output_tokens") or 0)
            else:  # Gemini
                candidates = body.get("candidates") or []
                parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
                content = "".join(x.get("text", "") for x in parts if x.get("text"))
                usage = body.get("usageMetadata") or {}
                completion_tokens = int(usage.get("candidatesTokenCount") or 0)
            content = (content or "").strip().strip('`').strip()
            if not content:
                raise RuntimeError("LLMから空の応答が返されました")
            if controller:
                controller.notify(kind="llm_metric", metric=_metric(provider, model, elapsed, True, completion_tokens, provider_tps))
                controller.notify(kind="llm_activity", state="end", activity_id=activity_id, provider=provider_display_name(provider), model=model, success=True)
            return content
        except StopRequested:
            raise
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError,
                json.JSONDecodeError, ConnectionError, OSError, RuntimeError, KeyError, IndexError) as e:
            last_err = e
            if controller:
                controller.notify(kind="llm_activity", state="retry" if attempt + 1 < retries else "end", activity_id=activity_id, provider=provider_display_name(provider), model=model, success=False, error=str(e), attempt=attempt + 1, retries=retries)
            if attempt + 1 < retries:
                for _ in range(min(5 * (attempt + 1), 30) * 5):
                    if controller and controller.stop_event.is_set():
                        raise StopRequested()
                    time.sleep(0.2)
    elapsed = max(time.perf_counter() - overall_start, 1e-6)
    if controller:
        controller.notify(kind="llm_metric", metric=_metric(provider, model, elapsed, False, error=str(last_err)))
    raise RuntimeError(f"LLM呼び出しに{retries}回失敗しました: {last_err}")

def benchmark_model(provider: str, url: str, model: str,
                    controller: Optional[TranslationController] = None, api_key: str = "") -> dict:
    """Run a short deterministic translation benchmark and return the observed metric."""
    captured = []
    proxy = controller
    if controller is None:
        proxy = TranslationController(progress_callback=lambda p: captured.append(p.get("metric")) if p.get("kind") == "llm_metric" else None)
    prompt = "日本語翻訳だけを返してください。説明は不要です。"
    sample = "Translate this into concise natural Japanese: The council approved the new law after a long debate."
    result = call_llm_raw(provider, url, model, sample, prompt, timeout=180, retries=1, controller=proxy, temperature=0.0, api_key=api_key)
    metric = next((x for x in reversed(captured) if x), None) if captured else None
    return {"text": result, "metric": metric or {}}


def build_system_prompt(source_lang: str, glossary: Optional[dict] = None,
                        preset: str = "General", dual_source: bool = False) -> str:
    lang_label = {"english": "英語", "simp_chinese": "簡体字中国語"}.get(source_lang, source_lang)
    preset_text = GAME_PRESETS.get(preset, GAME_PRESETS["General"])
    glossary_text = ""
    if glossary:
        pairs = [f"- {k} => {v}" for k, v in glossary.items()]
        glossary_text = "\n用語集（該当する場合はこの訳を優先）:\n" + "\n".join(pairs)
    dual_text = ""
    if dual_source:
        dual_text = f"\n各入力には英語本文の後ろに `{DUAL_SEP.strip()}` で簡体字中国語の参考訳が付く場合があります。日本語訳の意味判断には両方を参照し、英語をゲーム上の意味、中国語を制度語・固有語の参考として使ってください。参考訳中の [VAR] は出力しないでください。"
    return f"""あなたはParadox Interactive社のゲームのローカライズ翻訳者です。
{lang_label}のゲームテキストを自然で読みやすい日本語に翻訳してください。
対象プリセット: {preset_text}

入力は複数行で、各行の先頭に `N|||` が付きます。出力も同じ番号で `N|||翻訳後のテキスト` のみを返してください。
厳守事項:
1. @@0@@ @@1@@ などのプレースホルダは絶対に変更・削除・移動しない。
2. 行数・番号を変えない。説明、注釈、Markdown、余計な空行を出さない。
3. UIラベルは簡潔に、歴史制度語・軍事語・政治語は文脈に適した日本語にする。
4. 原文のテンプレート構造や改行表現を維持する。
5. 簡体字中国語をそのまま日本語として流用せず、日本語の字体・語法に直す。
6. 原文をそのまま返さず、翻訳可能な自然言語は必ず日本語化する。{dual_text}{glossary_text}
"""


def call_ollama_raw(url: str, model: str, user_content: str, system_prompt: str,
                    timeout: int = 300, retries: int = 5,
                    controller: Optional[TranslationController] = None) -> str:
    """Backward-compatible Ollama wrapper."""
    return call_llm_raw("Ollama", url, model, user_content, system_prompt, timeout, retries, controller)

def translate_batch(url: str, model: str, jobs: list, source_lang: str,
                    glossary: Optional[dict] = None, preset: str = "General",
                    dual_source: bool = False,
                    controller: Optional[TranslationController] = None,
                    provider: str = "Ollama", api_key: str = "") -> List[str]:
    if not jobs:
        return []
    selected_glossary = dict(glossary_for_prompt(glossary or {}, [j["value"] for j in jobs]))
    prompt = build_system_prompt(source_lang, selected_glossary, preset, dual_source)
    lines = []
    for i, j in enumerate(jobs):
        text = j["protected"]
        if dual_source and j.get("zh_ref"):
            ref = PROTECT_RE.sub('[VAR]', j["zh_ref"]).replace("\n", " ")
            text += DUAL_SEP + ref
        lines.append(f"{i}{BATCH_LINE_SEP}{text}")
    raw = call_llm_raw(provider, url, model, "\n".join(lines), prompt, controller=controller, api_key=api_key)
    result = [None] * len(jobs)
    for line in raw.splitlines():
        if BATCH_LINE_SEP not in line:
            continue
        idx_str, _, translated = line.partition(BATCH_LINE_SEP)
        if idx_str.strip().isdigit():
            idx = int(idx_str.strip())
            if 0 <= idx < len(result):
                result[idx] = translated
    return [result[i] if result[i] is not None else jobs[i]["protected"] for i in range(len(jobs))]


def detect_source_lang(path: Path, first_lines: list) -> str:
    name = path.name.lower()
    for lang in KNOWN_SOURCE_LANGS:
        if f"_l_{lang}" in name or name == f"l_{lang}.yml":
            return lang
    for line in first_lines[:5]:
        m = HEADER_PATTERN.match(line)
        if m:
            return m.group("lang")
    return "english"


def parse_line(line: str):
    m = LINE_PATTERN.match(line)
    if m:
        trailing = m.group("trailing") or ""
        if re.search(r'^[^#\n]*"[^"]*"', trailing):
            loose = LOOSE_LINE_PATTERN.match(line)
            if loose and len(loose.group("value")) > len(m.group("value")):
                return loose
        return m
    return LOOSE_LINE_PATTERN.match(line)


def parse_localization_file(path: Path) -> Tuple[str, Dict[str, str], List[str]]:
    raw = path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    lang = detect_source_lang(path, lines)
    entries = {}
    for line in lines:
        m = parse_line(line)
        if m:
            entries[m.group("key").strip()] = m.group("value")
    return lang, entries, lines


def gather_yml_files(input_path: Path, exclude_lang_dir: Optional[str] = None):
    if input_path.is_file():
        return [input_path]
    files = []
    for p in sorted(input_path.rglob("*.yml")):
        if "__MACOSX" in p.parts or p.name.startswith("._"):
            continue
        if exclude_lang_dir and exclude_lang_dir.lower() in [x.lower() for x in p.parts]:
            continue
        files.append(p)
    return files




# ---------------------------------------------------------------------------
# Lightweight live localization monitoring
# ---------------------------------------------------------------------------

def localization_file_stats(root: Path) -> dict:
    """Return a cheap snapshot (mtime_ns, size) for YAML files under root.

    This intentionally does not parse file contents, so an idle live monitor only
    performs directory/stat checks. Full parsing is done only when this snapshot
    changes.
    """
    root = Path(root)
    files = gather_yml_files(root) if root.exists() else []
    base = root if root.is_dir() else root.parent
    out = {}
    for f in files:
        try:
            st = f.stat()
            rel = str(f.relative_to(base)) if root.is_dir() else f.name
            out[rel] = (int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            continue
    return out


def _logical_localization_id(path: Path, root: Path, lang: str) -> str:
    """Normalize english/japanese/simp_chinese variants to one logical file id."""
    base = root if root.is_dir() else root.parent
    try:
        rel = path.relative_to(base)
    except ValueError:
        rel = Path(path.name)
    parts = [x for x in rel.parts[:-1] if x.lower() not in KNOWN_SOURCE_LANGS]
    name = rel.name
    for known in KNOWN_SOURCE_LANGS:
        name = re.sub(rf'_l_{re.escape(known)}(?=\.yml$)', '_l_LANG', name, flags=re.I)
    if re.fullmatch(r'l_[a-z_]+\.yml', name, flags=re.I):
        name = 'l_LANG.yml'
    return '/'.join(parts + [name])

def scan_translation_gaps(root: Path, preferred_source: str = "english") -> List[dict]:
    """Scan a localization tree and list missing/likely-untranslated Japanese entries.

    The scan is deterministic and does not call an LLM. Missing Japanese files/keys
    are treated as definite candidates. Existing Japanese values that are identical
    to English/Chinese source text, or look like foreign prose, are marked as
    candidates; short ambiguous foreign labels may optionally be refined by a small
    LLM in ``classify_monitor_candidates``.
    """
    root = Path(root)
    groups: Dict[str, dict] = {}
    for f in gather_yml_files(root):
        try:
            lang, entries, _ = parse_localization_file(f)
        except Exception:
            continue
        lid = _logical_localization_id(f, root, lang)
        groups.setdefault(lid, {})[lang] = {"path": str(f), "entries": entries}

    candidates: List[dict] = []
    for lid, langs in sorted(groups.items()):
        src_lang = preferred_source if preferred_source in langs else ("simp_chinese" if "simp_chinese" in langs else None)
        src = langs.get(src_lang) if src_lang else None
        ja = langs.get("japanese")

        if src and not ja:
            for key, value in src["entries"].items():
                if looks_untranslatable(value):
                    continue
                candidates.append({
                    "kind": "日本語ファイルなし", "logical_file": lid,
                    "source_file": src["path"], "target_file": "",
                    "source_lang": src_lang, "key": key, "source": value,
                    "target": "", "needs_llm": False, "confidence": "確定",
                })
            continue

        if src and ja:
            src_entries = src["entries"]
            ja_entries = ja["entries"]
            for key, value in src_entries.items():
                if key not in ja_entries and not looks_untranslatable(value):
                    candidates.append({
                        "kind": "日本語キーなし", "logical_file": lid,
                        "source_file": src["path"], "target_file": ja["path"],
                        "source_lang": src_lang, "key": key, "source": value,
                        "target": "", "needs_llm": False, "confidence": "確定",
                    })

            # Existing Japanese entries: exact source copies are highly suspicious.
            for key, target in ja_entries.items():
                if not target or looks_untranslatable(target):
                    continue
                source = src_entries.get(key, "")
                exact = bool(source and target.strip() == source.strip())
                foreign = looks_foreign_in_target(target, "japanese")
                if exact or foreign:
                    ambiguous = not exact and len(PROTECT_RE.sub('', target).strip()) <= 80
                    candidates.append({
                        "kind": "英語/外国語残り", "logical_file": lid,
                        "source_file": src["path"], "target_file": ja["path"],
                        "source_lang": src_lang, "key": key, "source": source,
                        "target": target, "needs_llm": ambiguous,
                        "confidence": "要確認" if ambiguous else "高",
                    })
        elif ja:
            # Japanese-only tree: still detect obvious foreign-only values.
            for key, target in ja["entries"].items():
                if looks_foreign_in_target(target, "japanese"):
                    candidates.append({
                        "kind": "英語/外国語残り", "logical_file": lid,
                        "source_file": "", "target_file": ja["path"],
                        "source_lang": "", "key": key, "source": "",
                        "target": target, "needs_llm": True, "confidence": "要確認",
                    })
    return candidates

def classify_monitor_candidates(provider: str, url: str, model: str, candidates: List[dict],
                                controller: Optional[TranslationController] = None,
                                api_key: str = "", batch_size: int = 40) -> Dict[int, bool]:
    """Use a small LLM only for ambiguous monitor candidates.

    Returns ``{candidate_index: True}`` for entries that should be translated to
    Japanese. Definite missing-file/key candidates should not be passed here.
    """
    decisions: Dict[int, bool] = {}
    if not candidates:
        return decisions
    system = """あなたは日本語ゲームローカライズの軽量QA判定器です。
各行が『日本語版に残った未翻訳テキストで、日本語へ翻訳すべきか』だけを判定してください。
固有の商品名・人名・一般的な略語・コード・型番など、通常そのまま表示してよいものは NO。
英語などの説明文、UI語、文章、翻訳されるべき一般語は YES。
出力は入力と同じ番号を使い、必ず `N|||YES` または `N|||NO` の1行だけ。説明は禁止。"""
    for start in range(0, len(candidates), max(1, batch_size)):
        if controller:
            controller.wait_if_paused()
        chunk = candidates[start:start + max(1, batch_size)]
        lines = []
        for i, c in enumerate(chunk):
            text = c.get("target") or c.get("source") or ""
            lines.append(f"{i}{BATCH_LINE_SEP}{text}")
        raw = call_llm_raw(provider, url, model, "\n".join(lines), system,
                           timeout=180, retries=2, controller=controller,
                           temperature=0.0, api_key=api_key)
        parsed = {}
        for line in raw.splitlines():
            if BATCH_LINE_SEP not in line:
                continue
            n, _, ans = line.partition(BATCH_LINE_SEP)
            n = n.strip()
            if n.isdigit():
                parsed[int(n)] = ans.strip().upper().startswith("YES")
        for i in range(len(chunk)):
            # Conservative fallback: keep the candidate if the model omitted it.
            decisions[start + i] = parsed.get(i, True)
    return decisions


def remap_rel_dir(rel_dir: Path, target_lang: str) -> Path:
    parts = [target_lang if p.lower() in KNOWN_SOURCE_LANGS else p for p in rel_dir.parts]
    return Path(*parts) if parts else rel_dir


def rename_for_target(path: Path, target_lang: str, source_lang: str) -> str:
    marker = f"_l_{source_lang}"
    if marker in path.name:
        return path.name.replace(marker, f"_l_{target_lang}")
    if path.name.endswith(".yml"):
        return path.name[:-4] + f"_l_{target_lang}.yml"
    return path.name


def build_source_manifest(input_path: Path, exclude_lang_dir: Optional[str] = None) -> dict:
    """Build a stable source snapshot used for differential updates."""
    input_path = Path(input_path)
    files = gather_yml_files(input_path, exclude_lang_dir)
    base = input_path if input_path.is_dir() else input_path.parent
    manifest = {
        "schema": 1,
        "input": str(input_path.resolve()),
        "created_at": time.time(),
        "files": {},
    }
    for f in files:
        try:
            lang, entries, _ = parse_localization_file(f)
        except Exception:
            continue
        rel = str(f.relative_to(base)) if input_path.is_dir() else f.name
        manifest["files"][rel] = {
            "language": lang,
            "keys": {k: text_hash(v) for k, v in entries.items()},
        }
    return manifest


def compare_source_manifests(old: dict, new: dict) -> dict:
    """Return added/changed/removed keys and files between two manifests."""
    old_files = (old or {}).get("files", {})
    new_files = (new or {}).get("files", {})
    details = []
    counts = {"added": 0, "changed": 0, "removed": 0, "unchanged": 0,
              "added_files": 0, "removed_files": 0}
    for rel in sorted(set(old_files) | set(new_files)):
        if rel not in old_files:
            keys = new_files[rel].get("keys", {})
            counts["added_files"] += 1
            counts["added"] += len(keys)
            details.append({"file": rel, "kind": "added_file", "keys": sorted(keys)})
            continue
        if rel not in new_files:
            keys = old_files[rel].get("keys", {})
            counts["removed_files"] += 1
            counts["removed"] += len(keys)
            details.append({"file": rel, "kind": "removed_file", "keys": sorted(keys)})
            continue
        ok = old_files[rel].get("keys", {})
        nk = new_files[rel].get("keys", {})
        added = sorted(set(nk) - set(ok))
        removed = sorted(set(ok) - set(nk))
        changed = sorted(k for k in set(ok) & set(nk) if ok[k] != nk[k])
        unchanged = len(set(ok) & set(nk)) - len(changed)
        counts["added"] += len(added); counts["removed"] += len(removed)
        counts["changed"] += len(changed); counts["unchanged"] += unchanged
        if added or removed or changed:
            details.append({"file": rel, "kind": "modified",
                            "added": added, "changed": changed, "removed": removed})
    return {"counts": counts, "details": details}


def save_source_manifest(cache_file: Path, manifest: dict):
    save_json(Path(cache_file).parent / SOURCE_MANIFEST_NAME, manifest)


def load_source_manifest(cache_file: Path) -> dict:
    return load_json(Path(cache_file).parent / SOURCE_MANIFEST_NAME, {})


def build_chinese_reference_map(input_path: Path) -> Dict[str, str]:
    refs = {}
    for p in gather_yml_files(input_path):
        try:
            lang, entries, _ = parse_localization_file(p)
        except Exception:
            continue
        if lang == "simp_chinese":
            refs.update(entries)
    return refs


def _apply_batch_result(batch, translated_list, results, cache, source_lang, failed):
    if translated_list is None:
        for j in batch:
            results[j["line_idx"]] = j["value"]
            failed.add(j["line_idx"])
        return
    for j, protected_translation in zip(batch, translated_list):
        restored = restore_text(protected_translation, j["tokens"])
        if looks_untranslated(j["value"], restored, source_lang):
            results[j["line_idx"]] = j["value"]
            failed.add(j["line_idx"])
            cache.pop(j["hash"], None)
        else:
            results[j["line_idx"]] = restored
            cache[j["hash"]] = restored
            failed.discard(j["line_idx"])


def process_file(in_path: Path, out_path: Path, url: str, model: str,
                 target_lang: str, cache: dict, workers: int, verbose: bool,
                 batch_size: int = 40, controller: Optional[TranslationController] = None,
                 glossary: Optional[dict] = None, preset: str = "General",
                 zh_refs: Optional[dict] = None, dual_source: bool = False,
                 cache_file: Optional[Path] = None, file_no: int = 0, file_total: int = 0,
                 provider: str = "Ollama", api_key: str = ""):
    raw = in_path.read_text(encoding="utf-8-sig")
    lines = raw.splitlines(keepends=False)
    source_lang = detect_source_lang(in_path, lines)
    repair_target_file = source_lang == target_lang
    translation_source_lang = "english" if repair_target_file and target_lang == "japanese" else source_lang
    if repair_target_file and verbose:
        print(f"  原文は既に{target_lang}です。未翻訳の外国語部分だけを修復します")

    parsed_lines = []
    jobs = []
    for line in lines:
        if HEADER_PATTERN.match(line):
            parsed_lines.append(("header", re.sub(r'l_[a-z_]+', f'l_{target_lang}', line)))
            continue
        m = parse_line(line)
        if not m:
            parsed_lines.append(("raw", line)); continue
        value = m.group("value")
        parsed_lines.append(("line", m))
        idx = len(parsed_lines) - 1
        if not value or looks_untranslatable(value):
            continue
        if repair_target_file and not looks_foreign_in_target(value, target_lang):
            continue
        h = f"v5:{normalize_provider(provider)}:{model}:{preset}:{translation_source_lang}:{text_hash(value)}"
        if h in cache and cache_entry_is_valid(value, cache[h], translation_source_lang):
            continue
        if h in cache:
            cache.pop(h, None)
        protected, tokens = protect_text(value)
        jobs.append({
            "line_idx": idx, "key": m.group("key").strip(), "value": value,
            "protected": protected, "tokens": tokens, "hash": h,
            "zh_ref": (zh_refs or {}).get(m.group("key").strip()) if translation_source_lang == "english" else None,
        })

    total_keys = sum(1 for k, _ in parsed_lines if k == "line")
    if verbose:
        print(f"  原文言語: {source_lang}{'（修復）' if repair_target_file else ''} / 全キー: {total_keys} / 翻訳対象: {len(jobs)}")

    results = {}
    failed = set()
    batches = [jobs[i:i+batch_size] for i in range(0, len(jobs), batch_size)]
    completed_jobs = 0

    # GUIでは安全な一時停止のため、バッチ単位で制御する。workers>1 は同一ウィンドウ内で並列。
    window = max(1, workers)
    for start in range(0, len(batches), window):
        if controller:
            controller.wait_if_paused()
        group = batches[start:start+window]
        if len(group) == 1:
            work_results = []
            try:
                tr = translate_batch(url, model, group[0], translation_source_lang,
                                     glossary, preset, dual_source, controller, provider, api_key)
                work_results.append((group[0], tr, None))
            except StopRequested:
                raise
            except Exception as e:
                work_results.append((group[0], None, str(e)))
        else:
            def run_one(b):
                try:
                    return b, translate_batch(url, model, b, translation_source_lang,
                                              glossary, preset, dual_source, controller, provider, api_key), None
                except StopRequested:
                    return b, None, "__STOP__"
                except Exception as e:
                    return b, None, str(e)
            with concurrent.futures.ThreadPoolExecutor(max_workers=window) as ex:
                work_results = [f.result() for f in [ex.submit(run_one, b) for b in group]]

        for b, translated, err in work_results:
            if err == "__STOP__":
                raise StopRequested()
            _apply_batch_result(b, translated, results, cache, translation_source_lang, failed)
            completed_jobs += len(b)
            if err and verbose:
                print(f"  [警告] バッチ失敗: {err}")
            if cache_file:
                save_cache(cache_file, cache)
            if controller:
                controller.notify(kind="batch", file=str(in_path), file_no=file_no, file_total=file_total,
                                  done=completed_jobs, total=max(len(jobs), 1), key_count=len(b))
                controller.checkpoint({"current_file": str(in_path), "completed_in_file": completed_jobs,
                                       "total_in_file": len(jobs), "timestamp": time.time()})
            if controller and controller.stop_event.is_set():
                raise StopRequested()

    if failed:
        if verbose:
            print(f"  {len(failed)}件を単発再試行します…")
        retry_jobs = [j for j in jobs if j["line_idx"] in failed]
        for j in retry_jobs:
            if controller:
                controller.wait_if_paused()
            try:
                tr = translate_batch(url, model, [j], translation_source_lang,
                                     glossary, preset, dual_source, controller, provider, api_key)
                restored = restore_text(tr[0], j["tokens"])
                if looks_untranslated(j["value"], restored, translation_source_lang):
                    cache.pop(j["hash"], None)
                else:
                    results[j["line_idx"]] = restored
                    cache[j["hash"]] = restored
                    failed.discard(j["line_idx"])
            except StopRequested:
                raise
            except Exception:
                pass
            if cache_file:
                save_cache(cache_file, cache)

    out_lines = []
    for idx, (kind, data) in enumerate(parsed_lines):
        if kind == "header": out_lines.append(data); continue
        if kind == "raw": out_lines.append(data); continue
        m = data
        orig = m.group("value")
        if idx in results:
            translated = results[idx]
        elif orig and not looks_untranslatable(orig):
            h = f"v5:{normalize_provider(provider)}:{model}:{preset}:{translation_source_lang}:{text_hash(orig)}"
            translated = cache.get(h, orig)
        else:
            translated = orig
        out_lines.append(f'{m.group("indent")}{m.group("key")}: {m.group("version") or ""}"{translated}"{m.group("trailing") or ""}')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\ufeff" + "\n".join(out_lines) + "\n", encoding="utf-8")
    return {"jobs": len(jobs), "failed": len(failed), "keys": total_keys}


def run_translation(input_path, output_path, model=DEFAULT_MODEL, url=DEFAULT_OLLAMA_URL,
                    target_lang=DEFAULT_TARGET_LANG, workers=1, batch_size=40,
                    cache_path=None, cache_dir=None, resume=True, verbose=True,
                    include_target_files=True, controller: Optional[TranslationController] = None,
                    glossary_path=None, preset="General", dual_source=False,
                    auto_qa=True, provider="Ollama", api_key=""):
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    if cache_path:
        cache_file = Path(cache_path); cache_file.parent.mkdir(parents=True, exist_ok=True)
    elif cache_dir:
        cdir = Path(cache_dir); cdir.mkdir(parents=True, exist_ok=True); cache_file = cdir / CACHE_FILE_NAME
    else:
        cache_file = output_path / CACHE_FILE_NAME
    cache = load_cache(cache_file) if (resume or cache_file.exists()) else {}
    current_manifest = build_source_manifest(input_path, None if include_target_files else target_lang)
    glossary = load_glossary(Path(glossary_path)) if glossary_path else {}
    zh_refs = build_chinese_reference_map(input_path) if dual_source and input_path.is_dir() else {}
    exclude = None if include_target_files else target_lang
    files = gather_yml_files(input_path, exclude)
    if not files:
        raise RuntimeError("翻訳対象のYAMLファイルが見つかりませんでした。")

    def sort_key(p):
        parts = [x.lower() for x in p.parts]; name = p.name.lower()
        is_en = "english" in parts or "_l_english" in name
        is_target = target_lang in parts or f"_l_{target_lang}" in name
        is_zh = "simp_chinese" in parts or "_l_simp_chinese" in name
        # Dual source時は中国語ファイル自体を別途出力しない（英語の参考として使用）
        return (0 if is_en else 3 if is_target else 2 if is_zh else 1, str(p))
    files = sorted(files, key=sort_key)
    if dual_source:
        english_exists = any(detect_source_lang(p, p.read_text(encoding="utf-8-sig").splitlines()[:5]) == "english" for p in files)
        if english_exists:
            files = [p for p in files if detect_source_lang(p, p.read_text(encoding="utf-8-sig").splitlines()[:5]) != "simp_chinese"]

    print(f"プロバイダ: {provider} / モデル: {model} / 対象ファイル: {len(files)} / プリセット: {preset} / 英中併用: {'ON' if dual_source else 'OFF'}")
    base_dir = input_path if input_path.is_dir() else input_path.parent
    planned = {}
    processed = 0
    total_jobs = total_failed = 0
    try:
        for i, f in enumerate(files, 1):
            if controller:
                controller.wait_if_paused()
            rel = f.parent.relative_to(base_dir) if input_path.is_dir() else Path(".")
            source_lang = detect_source_lang(f, f.read_text(encoding="utf-8-sig").splitlines()[:5])
            out = output_path / remap_rel_dir(rel, target_lang) / rename_for_target(f, target_lang, source_lang)
            key = str(out.resolve())
            if key in planned:
                print(f"[{i}/{len(files)}] 出力先重複のためスキップ: {f.name}")
                continue
            planned[key] = str(f)
            print(f"[{i}/{len(files)}] {f.relative_to(base_dir) if input_path.is_dir() else f.name} -> {out}")
            stats = process_file(f, out, url, model, target_lang, cache, workers, verbose,
                                 batch_size, controller, glossary, preset, zh_refs, dual_source,
                                 cache_file, i, len(files), provider, api_key)
            processed += 1; total_jobs += stats["jobs"]; total_failed += stats["failed"]
            save_cache(cache_file, cache)
            if auto_qa and out.exists():
                issues = qa_file(out, f if source_lang != target_lang else None)
                severe = sum(1 for x in issues if x["severity"] == "error")
                warn = sum(1 for x in issues if x["severity"] == "warning")
                print(f"  QA: error {severe} / warning {warn}")
            if controller:
                controller.notify(kind="file_done", file=str(f), file_no=i, file_total=len(files))
                if controller.stop_event.is_set():
                    raise StopRequested()
    except StopRequested:
        save_cache(cache_file, cache)
        save_source_manifest(cache_file, current_manifest)
        print("保存して中断しました。次回はキャッシュから再開できます。")
        return {"processed": processed, "interrupted": True, "jobs": total_jobs, "failed": total_failed,
                "cache": str(cache_file)}
    save_source_manifest(cache_file, current_manifest)
    print("完了しました。")
    return {"processed": processed, "interrupted": False, "jobs": total_jobs, "failed": total_failed,
            "cache": str(cache_file), "manifest": str(cache_file.parent / SOURCE_MANIFEST_NAME)}


# ------------------------- QA / proofreading -------------------------

def typo_checks(text: str) -> List[dict]:
    issues = []
    rules = [
        (r'([、。！？])\1+', "句読点が重複しています"),
        (r'(です|ます|する|した)\1', "語句が重複している可能性があります"),
        (r'([ぁ-んァ-ヶ一-龯]{1,4})\1\1', "同じ語が連続している可能性があります"),
        (r'\s+[、。！？]', "句読点の直前に不要な空白があります"),
        (r'[、。！？]\s+[ぁ-んァ-ヶ一-龯]', "日本語文中に不要な半角空白があります"),
        (r'\?\?|！！|？？', "記号が重複しています"),
    ]
    for pattern, msg in rules:
        if re.search(pattern, text):
            issues.append({"severity": "warning", "type": "typo", "message": msg})
    pairs = [('（','）'), ('「','」'), ('『','』'), ('【','】')]
    for a,b in pairs:
        if text.count(a) != text.count(b):
            issues.append({"severity": "warning", "type": "typo", "message": f"括弧 {a}{b} の数が一致しません"})
    return issues


def qa_entries(target_entries: Dict[str,str], source_entries: Optional[Dict[str,str]] = None) -> List[dict]:
    issues = []
    for key, value in target_entries.items():
        if looks_foreign_in_target(value, "japanese"):
            issues.append({"key": key, "severity": "error", "type": "untranslated", "message": "英語の未翻訳候補", "value": value})
        for item in typo_checks(value):
            issues.append({"key": key, "value": value, **item})
        if '@@' in value:
            issues.append({"key": key, "severity": "error", "type": "placeholder", "message": "内部プレースホルダ @@N@@ が残っています", "value": value})
        if source_entries and key in source_entries:
            src_tokens = extract_protected_tokens(source_entries[key])
            dst_tokens = extract_protected_tokens(value)
            if src_tokens != dst_tokens:
                issues.append({"key": key, "severity": "error", "type": "syntax", "message": "ゲーム変数/タグが原文と一致しません", "value": value})
    if source_entries:
        missing = set(source_entries) - set(target_entries)
        extra = set(target_entries) - set(source_entries)
        for key in sorted(missing):
            issues.append({"key": key, "severity": "error", "type": "missing_key", "message": "訳文側にキーがありません", "value": ""})
        for key in sorted(extra):
            issues.append({"key": key, "severity": "warning", "type": "extra_key", "message": "原文側に存在しないキーです", "value": target_entries[key]})
    return issues


def qa_file(target_path: Path, source_path: Optional[Path] = None) -> List[dict]:
    _, target_entries, _ = parse_localization_file(Path(target_path))
    source_entries = None
    if source_path and Path(source_path).exists():
        _, source_entries, _ = parse_localization_file(Path(source_path))
    return qa_entries(target_entries, source_entries)


def proofread_text(url: str, model: str, text: str, source_text: str = "",
                   glossary: Optional[dict] = None, preset: str = "General",
                   provider: str = "Ollama", api_key: str = "",
                   controller: Optional[TranslationController] = None) -> str:
    protected, tokens = protect_text(text)
    glossary_text = "\n".join(f"{k}=>{v}" for k,v in (glossary or {}).items())
    system = f"""あなたはParadoxゲーム日本語ローカライズの校正者です。誤字、脱字、助詞、重複、不自然な日本語だけを修正してください。
意味を勝手に変えず、@@0@@ 等のプレースホルダは絶対に変更しないでください。回答は修正後本文だけ。
プリセット: {GAME_PRESETS.get(preset, GAME_PRESETS['General'])}
用語集:\n{glossary_text}"""
    user = f"原文参考: {PROTECT_RE.sub('[VAR]', source_text)}\n日本語: {protected}" if source_text else protected
    raw = call_llm_raw(provider, url, model, user, system, api_key=api_key, controller=controller)
    return restore_text(raw.strip().strip('`').strip(), tokens)


def update_localization_value(path: Path, key: str, new_value: str) -> bool:
    raw = Path(path).read_text(encoding="utf-8-sig")
    lines = raw.splitlines()
    changed = False
    out = []
    for line in lines:
        m = parse_line(line)
        if m and m.group("key").strip() == key and not changed:
            escaped = new_value.replace('"', '\\"') if '\\"' not in new_value else new_value
            out.append(f'{m.group("indent")}{m.group("key")}: {m.group("version") or ""}"{escaped}"{m.group("trailing") or ""}')
            changed = True
        else:
            out.append(line)
    if changed:
        Path(path).write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")
    return changed

# ---------------------------------------------------------------------------
# Mod-level translation availability research
# ---------------------------------------------------------------------------

def detect_mod_name(mod_root: Path) -> str:
    """Best-effort display name for a Paradox mod directory."""
    mod_root = Path(mod_root)
    candidates = []
    if mod_root.is_dir():
        descriptor = mod_root / "descriptor.mod"
        if descriptor.exists():
            candidates.append(descriptor)
        candidates.extend(sorted(mod_root.glob("*.mod"))[:5])
    for p in candidates:
        try:
            text = p.read_text(encoding="utf-8-sig", errors="ignore")
        except Exception:
            continue
        m = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', text, flags=re.I | re.M)
        if m:
            return m.group(1).strip()
    return mod_root.name or str(mod_root)


def find_mod_roots(root: Path) -> List[Path]:
    """Find likely mod roots below *root* without crawling arbitrary deep trees.

    - If root itself is a localization directory, its parent is treated as one mod.
    - If root contains localization/, root itself is treated as one mod.
    - Otherwise immediate child directories containing localization/ are returned.
    - As a fallback, localization directories up to two levels below root are used.
    """
    root = Path(root)
    if not root.exists():
        return []
    if root.is_file():
        return []
    if root.name.lower() == "localization":
        return [root.parent]
    if (root / "localization").is_dir():
        return [root]

    found: List[Path] = []
    try:
        for child in sorted(p for p in root.iterdir() if p.is_dir()):
            if (child / "localization").is_dir():
                found.append(child)
    except OSError:
        pass
    if found:
        return found

    # Fallback for layouts such as <root>/<category>/<mod>/localization.
    seen = set()
    try:
        for loc in root.glob("*/*/localization"):
            if loc.is_dir():
                mod = loc.parent
                key = str(mod.resolve())
                if key not in seen:
                    seen.add(key); found.append(mod)
    except OSError:
        pass
    return sorted(found)


def mod_localization_root(mod_root: Path) -> Optional[Path]:
    mod_root = Path(mod_root)
    if mod_root.name.lower() == "localization" and mod_root.is_dir():
        return mod_root
    loc = mod_root / "localization"
    if loc.is_dir():
        return loc
    return None


def analyze_mod_translation_status(mod_root: Path, preferred_source: str = "english") -> dict:
    """Return a mod-level Japanese translation status without invoking an LLM."""
    mod_root = Path(mod_root)
    loc = mod_localization_root(mod_root)
    name = detect_mod_name(mod_root)
    result = {
        "mod": name,
        "path": str(mod_root),
        "localization": str(loc) if loc else "",
        "status": "不明",
        "message": f"{name}のlocalizationフォルダを確認できませんでした。",
        "source_files": 0,
        "japanese_files": 0,
        "source_keys": 0,
        "japanese_keys": 0,
        "gap_count": 0,
        "candidates": [],
    }
    if not loc:
        return result

    source_keys = set()
    japanese_keys = set()
    source_files = 0
    japanese_files = 0
    for f in gather_yml_files(loc):
        try:
            lang, entries, _ = parse_localization_file(f)
        except Exception:
            continue
        if lang == "japanese":
            japanese_files += 1
            japanese_keys.update(entries.keys())
        elif lang in {preferred_source, "simp_chinese"}:
            source_files += 1
            source_keys.update(entries.keys())

    candidates = scan_translation_gaps(loc, preferred_source=preferred_source)
    result.update({
        "source_files": source_files,
        "japanese_files": japanese_files,
        "source_keys": len(source_keys),
        "japanese_keys": len(japanese_keys),
        "gap_count": len(candidates),
        "candidates": candidates,
    })

    if not source_keys:
        result["status"] = "対象なし"
        result["message"] = f"{name}には判定対象となる英語/中国語ローカライズが見つかりませんでした。"
    elif japanese_files == 0 or not japanese_keys:
        result["status"] = "翻訳なし"
        result["message"] = f"{name}というModは日本語翻訳がありません。"
    elif candidates:
        result["status"] = "欠損あり"
        result["message"] = f"{name}のModに翻訳の欠損箇所があります（{len(candidates)}件）。"
    else:
        result["status"] = "翻訳あり"
        result["message"] = f"{name}のModは日本語翻訳が確認できました。"
    return result
