#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Core engine for Paradox Localization Translator v0.7.8.

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
    "EU5": "Europa Universalis V。中世後期から近世・近代初期の政治・外交・宗教・交易・軍事・制度語彙を重視する。",
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
    runtime_settings: dict = field(default_factory=dict)
    settings_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

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

    def update_runtime_settings(self, **settings):
        """Update settings used from the next safe batch boundary."""
        with self.settings_lock:
            self.runtime_settings.update({k: v for k, v in settings.items() if v is not None})

    def get_runtime_settings(self) -> dict:
        with self.settings_lock:
            return dict(self.runtime_settings)


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


def read_localization_text(path: Path) -> str:
    """Read a Paradox localization text file with BOM-aware encoding detection.

    Paradox/community mods are normally UTF-8 with BOM, but some mods contain
    UTF-16 LE/BE files. Detect the BOM first and fall back conservatively so a
    single differently encoded YAML does not abort an entire translation queue.
    """
    path = Path(path)
    data = path.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    if data.startswith(b"\xff\xfe"):
        return data.decode("utf-16-le").lstrip("\ufeff")
    if data.startswith(b"\xfe\xff"):
        return data.decode("utf-16-be").lstrip("\ufeff")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        # UTF-16 without a BOM is uncommon, but this gives legacy/community
        # files a safe fallback while still raising if neither variant is valid.
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                text = data.decode(enc)
                # A plausible localization file should not be dominated by NULs.
                if text.count("\x00") <= max(1, len(text) // 20):
                    return text.lstrip("\ufeff")
            except UnicodeDecodeError:
                pass
        raise


def text_hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def escape_localization_value(value: str) -> str:
    """Escape literal quotes for a quoted Paradox localization value."""
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            out.extend((ch, value[i + 1]))
            i += 2
            continue
        out.append('\\"' if ch == '"' else ch)
        i += 1
    return "".join(out)


def translation_cache_key(provider: str, model: str, preset: str, source_lang: str,
                          original: str, glossary: Optional[dict] = None,
                          dual_source: bool = False, zh_ref: str = "",
                          translation_mode: str = "standard") -> str:
    """Cache key including settings that materially change translation output."""
    glossary_blob = json.dumps(glossary or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cfg_blob = "\n".join([
        normalize_provider(provider), model or "", preset or "", source_lang or "",
        "dual=1" if dual_source else "dual=0", f"mode={translation_mode}", text_hash(glossary_blob),
        text_hash(zh_ref or "") if dual_source else "no-zh",
    ])
    return f"v6:{text_hash(cfg_blob)}:{text_hash(original)}"


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
                # GUIへ、モデルが実際に返した生のテキストを通知する。
                # 読み取り専用のライブ確認欄で利用し、翻訳結果そのものの処理ロジックは変更しない。
                controller.notify(kind="llm_response", activity_id=activity_id, provider=provider_display_name(provider), model=model, content=content, received_at=time.time())
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
                        preset: str = "General", dual_source: bool = False,
                        chinese_basis: bool = False) -> str:
    lang_label = {"english": "英語", "simp_chinese": "簡体字中国語"}.get(source_lang, source_lang)
    preset_text = GAME_PRESETS.get(preset, GAME_PRESETS["General"])
    glossary_text = ""
    if glossary:
        pairs = [f"- {k} => {v}" for k, v in glossary.items()]
        glossary_text = "\n用語集（該当する場合はこの訳を優先）:\n" + "\n".join(pairs)
    dual_text = ""
    if dual_source:
        dual_text = f"\n各入力には英語本文の後ろに `{DUAL_SEP.strip()}` で簡体字中国語の参考訳が付く場合があります。日本語訳の意味判断には両方を参照し、英語をゲーム上の意味、中国語を制度語・固有語の参考として使ってください。参考訳中の [VAR] は出力しないでください。"
    chinese_basis_text = ""
    if chinese_basis:
        chinese_basis_text = """
この翻訳は「中国語基準翻訳」です。簡体字中国語原文の漢字語彙を訳語選定の第一基準にしてください。
- 制度名・官職名・地名・文化語・軍事語・歴史用語は、中国語原文にある漢字の意味と語構成を優先する。
- 中国語の漢字語が日本語でも自然に成立する場合は、その語を日本語の字体・表記へ整えて活用する。
- 不必要な英語風カタカナ化や音写、原文の意味から離れた意訳を避ける。
- ただし中国語の語順・助詞・文法をそのまま移さず、文章全体は自然な日本語にする。
- 簡体字は必要に応じて日本語で一般的な字体へ直す。
"""
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
6. 原文をそのまま返さず、翻訳可能な自然言語は必ず日本語化する。{dual_text}{chinese_basis_text}{glossary_text}
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
                    provider: str = "Ollama", api_key: str = "",
                    chinese_basis: bool = False) -> List[str]:
    if not jobs:
        return []
    selected_glossary = dict(glossary_for_prompt(glossary or {}, [j["value"] for j in jobs]))
    prompt = build_system_prompt(source_lang, selected_glossary, preset, dual_source, chinese_basis)
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
    raw = read_localization_text(path)
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
                 provider: str = "Ollama", api_key: str = "", chinese_basis: bool = False):
    raw = read_localization_text(in_path)
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
        h = translation_cache_key(provider, model, preset, translation_source_lang, value,
                                  glossary=glossary, dual_source=dual_source,
                                  zh_ref=(zh_refs or {}).get(m.group("key").strip(), ""),
                                  translation_mode="chinese_basis" if chinese_basis else "standard")
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
    completed_jobs = 0
    cursor = 0

    def runtime_cfg():
        cfg = controller.get_runtime_settings() if controller else {}
        current_provider = cfg.get("provider", provider)
        current_model = cfg.get("model", model)
        current_url = cfg.get("url", url)
        current_preset = cfg.get("preset", preset)
        current_dual = bool(cfg.get("dual_source", dual_source))
        current_api_key = cfg.get("api_key", api_key)
        current_batch = max(1, int(cfg.get("batch_size", batch_size) or batch_size))
        current_workers = max(1, int(cfg.get("workers", workers) or workers))
        current_glossary = glossary
        gp = cfg.get("glossary_path")
        if gp:
            try:
                current_glossary = load_glossary(Path(gp))
            except Exception:
                current_glossary = glossary
        return {
            "provider": current_provider, "model": current_model, "url": current_url,
            "preset": current_preset, "dual_source": current_dual, "api_key": current_api_key,
            "batch_size": current_batch, "workers": current_workers, "glossary": current_glossary,
        }

    # v0.7.6: バッチ境界ごとにGUI側の最新設定を読み直す。
    # モデル・URL・プロバイダ・バッチ・並列・プリセット等を翻訳途中でも安全に切り替えられる。
    while cursor < len(jobs):
        if controller:
            controller.wait_if_paused()
        cfg = runtime_cfg()
        group = []
        for _ in range(cfg["workers"]):
            if cursor >= len(jobs):
                break
            b = jobs[cursor:cursor + cfg["batch_size"]]
            cursor += len(b)
            for j in b:
                j["hash"] = translation_cache_key(
                    cfg["provider"], cfg["model"], cfg["preset"], translation_source_lang, j["value"],
                    glossary=cfg["glossary"], dual_source=cfg["dual_source"], zh_ref=j.get("zh_ref") or "",
                    translation_mode="chinese_basis" if chinese_basis else "standard")
            group.append(b)

        def run_one(b):
            try:
                return b, translate_batch(cfg["url"], cfg["model"], b, translation_source_lang,
                                          cfg["glossary"], cfg["preset"], cfg["dual_source"],
                                          controller, cfg["provider"], cfg["api_key"], chinese_basis), None
            except StopRequested:
                return b, None, "__STOP__"
            except Exception as e:
                return b, None, str(e)

        if len(group) == 1:
            work_results = [run_one(group[0])]
        else:
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(group)) as ex:
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
                                  done=completed_jobs, total=max(len(jobs), 1), key_count=len(b),
                                  active_model=cfg["model"], active_provider=provider_display_name(cfg["provider"]),
                                  active_batch=cfg["batch_size"], active_workers=cfg["workers"])
                controller.checkpoint({"current_file": str(in_path), "completed_in_file": completed_jobs,
                                       "total_in_file": len(jobs), "timestamp": time.time(),
                                       "runtime_settings": {k:v for k,v in cfg.items() if k != "glossary"}})
            if controller and controller.stop_event.is_set():
                raise StopRequested()

    if failed:
        if verbose:
            print(f"  {len(failed)}件を単発再試行します…")
        retry_jobs = [j for j in jobs if j["line_idx"] in failed]
        for j in retry_jobs:
            if controller:
                controller.wait_if_paused()
            cfg = runtime_cfg()
            j["hash"] = translation_cache_key(
                cfg["provider"], cfg["model"], cfg["preset"], translation_source_lang, j["value"],
                glossary=cfg["glossary"], dual_source=cfg["dual_source"], zh_ref=j.get("zh_ref") or "",
                translation_mode="chinese_basis" if chinese_basis else "standard")
            try:
                tr = translate_batch(cfg["url"], cfg["model"], [j], translation_source_lang,
                                     cfg["glossary"], cfg["preset"], cfg["dual_source"],
                                     controller, cfg["provider"], cfg["api_key"], chinese_basis)
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
            zh_ref = (zh_refs or {}).get(m.group("key").strip(), "") if translation_source_lang == "english" else ""
            h = translation_cache_key(provider, model, preset, translation_source_lang, orig,
                                      glossary=glossary, dual_source=dual_source, zh_ref=zh_ref,
                                      translation_mode="chinese_basis" if chinese_basis else "standard")
            translated = cache.get(h, orig)
        else:
            translated = orig
        escaped_translated = escape_localization_value(translated)
        out_lines.append(f'{m.group("indent")}{m.group("key")}: {m.group("version") or ""}"{escaped_translated}"{m.group("trailing") or ""}')
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
    zh_refs = build_chinese_reference_map(input_path) if input_path.is_dir() else {}
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
        english_exists = any(detect_source_lang(p, read_localization_text(p).splitlines()[:5]) == "english" for p in files)
        if english_exists:
            files = [p for p in files if detect_source_lang(p, read_localization_text(p).splitlines()[:5]) != "simp_chinese"]

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
            source_lang = detect_source_lang(f, read_localization_text(f).splitlines()[:5])
            out = output_path / remap_rel_dir(rel, target_lang) / rename_for_target(f, target_lang, source_lang)
            key = str(out.resolve())
            if key in planned:
                print(f"[{i}/{len(files)}] 出力先重複のためスキップ: {f.name}")
                continue
            planned[key] = str(f)
            print(f"[{i}/{len(files)}] {f.relative_to(base_dir) if input_path.is_dir() else f.name} -> {out}")
            stats = process_file(f, out, url, model, target_lang, cache, workers, verbose,
                                 batch_size, controller, glossary, preset, zh_refs, dual_source,
                                 cache_file, i, len(files), provider, api_key, False)
            processed += 1; total_jobs += stats["jobs"]; total_failed += stats["failed"]
            save_cache(cache_file, cache)
            if auto_qa and out.exists():
                issues = qa_file(out, f if source_lang != target_lang else None, source_lang=source_lang, glossary=glossary)
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


def qa_entries(target_entries: Dict[str,str], source_entries: Optional[Dict[str,str]] = None,
               source_lang: str = "english", glossary: Optional[dict] = None) -> List[dict]:
    """QA Japanese localization against an optional source localization.

    ``source_lang`` may be ``english`` or ``simp_chinese``.  Chinese-source QA is
    deliberately conservative: it flags an exact unchanged Chinese source string,
    missing keys, protected-token mismatches and glossary terminology mismatches.
    It does not treat all Han characters as untranslated because normal Japanese
    localization also contains kanji.
    """
    issues = []
    glossary = glossary or {}
    for key, value in target_entries.items():
        # English residues can be detected without a source file.  When a source
        # entry is present, looks_untranslated() below performs the source-aware
        # check so the same issue is not reported twice.
        if (not source_entries or key not in source_entries) and looks_foreign_in_target(value, "japanese"):
            issues.append({"key": key, "severity": "error", "type": "untranslated", "message": "英語の未翻訳候補", "value": value})
        for item in typo_checks(value):
            issues.append({"key": key, "value": value, **item})
        if '@@' in value:
            issues.append({"key": key, "severity": "error", "type": "placeholder", "message": "内部プレースホルダ @@N@@ が残っています", "value": value})
        if source_entries and key in source_entries:
            src = source_entries[key]
            if looks_untranslated(src, value, source_lang):
                msg = "簡体字中国語の原文が未翻訳のままです" if source_lang == "simp_chinese" else "原文が未翻訳のままです"
                issues.append({"key": key, "severity": "error", "type": "untranslated", "message": msg, "value": value})
            src_tokens = extract_protected_tokens(src)
            dst_tokens = extract_protected_tokens(value)
            if src_tokens != dst_tokens:
                issues.append({"key": key, "severity": "error", "type": "syntax", "message": "ゲーム変数/タグが原文と一致しません", "value": value})
            # Translation-term QA: if a registered source term is present, require
            # its fixed Japanese term in the target.  This is especially useful for
            # Chinese historical/institutional terminology.
            for src_term, dst_term in glossary.items():
                if src_term and dst_term and src_term in src and dst_term not in value:
                    issues.append({
                        "key": key, "severity": "warning", "type": "term_mismatch",
                        "message": f"用語集指定『{src_term} → {dst_term}』が訳文に反映されていません",
                        "value": value, "source_term": src_term, "expected_term": dst_term,
                    })
    if source_entries:
        missing = set(source_entries) - set(target_entries)
        extra = set(target_entries) - set(source_entries)
        for key in sorted(missing):
            issues.append({"key": key, "severity": "error", "type": "missing_key", "message": "訳文側にキーがありません", "value": ""})
        for key in sorted(extra):
            issues.append({"key": key, "severity": "warning", "type": "extra_key", "message": "原文側に存在しないキーです", "value": target_entries[key]})
    return issues


def qa_file(target_path: Path, source_path: Optional[Path] = None, source_lang: Optional[str] = None,
            glossary: Optional[dict] = None) -> List[dict]:
    _, target_entries, _ = parse_localization_file(Path(target_path))
    source_entries = None
    detected_lang = source_lang or "english"
    if source_path and Path(source_path).exists():
        detected_lang, source_entries, _ = parse_localization_file(Path(source_path))
        if source_lang:
            detected_lang = source_lang
    return qa_entries(target_entries, source_entries, detected_lang, glossary)




def _is_auto_glossary_source_candidate(text: str, source_lang: str) -> bool:
    plain = PROTECT_RE.sub('', text or '').strip()
    if not plain or len(plain) > 80:
        return False
    if source_lang == "english":
        words = re.findall(r"[A-Za-z][A-Za-z'\-]*", plain)
        return 1 <= len(words) <= 8 and not re.search(r"[.!?]\s", plain)
    if source_lang == "simp_chinese":
        han = re.findall(r"[\u4e00-\u9fff]", plain)
        return 1 <= len(han) <= 28 and plain.count('。') == 0 and plain.count('！') == 0 and plain.count('？') == 0
    return len(plain) <= 60


def build_auto_glossary_candidates(pairs: Iterable[dict]) -> List[dict]:
    """Build terminology candidates from aligned source/Japanese localization files.

    Repeated short source labels/terms are grouped by their exact source wording.
    If existing Japanese localization uses more than one wording, all variants and
    occurrence counts are retained so the UI can unify them later.
    """
    from collections import Counter, defaultdict
    grouped = defaultdict(Counter)
    langs = {}
    keys_by_source = defaultdict(list)
    for pair in pairs:
        source = Path(pair.get("source", ""))
        target = Path(pair.get("target", ""))
        if not source.exists() or not target.exists():
            continue
        try:
            source_lang, source_entries, _ = parse_localization_file(source)
            _, target_entries, _ = parse_localization_file(target)
        except Exception:
            continue
        if source_lang not in {"english", "simp_chinese"}:
            continue
        for key, src in source_entries.items():
            dst = target_entries.get(key, "").strip()
            src = (src or "").strip()
            if not dst or not src or looks_untranslated(src, dst, source_lang):
                continue
            if not _is_auto_glossary_source_candidate(src, source_lang):
                continue
            grouped[src][dst] += 1
            langs[src] = source_lang
            keys_by_source[src].append(key)
    out = []
    for src, counts in grouped.items():
        total = sum(counts.values())
        if total < 2:
            continue
        variants = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        preferred = variants[0][0]
        out.append({
            "source": src, "source_lang": langs.get(src, "english"),
            "preferred": preferred, "occurrences": total,
            "variants": [{"text": v, "count": c} for v, c in variants],
            "conflict": len(variants) > 1,
            "keys": keys_by_source[src][:30],
            "source_kind": "auto",
        })
    out.sort(key=lambda x: (not x["conflict"], -x["occurrences"], x["source"]))
    return out


def build_import_glossary_candidates(pairs: Iterable[dict], source_kind: str = "import") -> List[dict]:
    """Build glossary candidates from aligned localization pairs, including one-off terms.

    This is intended for importing terminology from official/base-game Japanese
    localization or a specific Japanese localization file/Mod. Short source labels
    are aligned by localization key and every usable pair is retained.
    """
    from collections import Counter, defaultdict
    grouped = defaultdict(Counter)
    langs = {}
    keys_by_source = defaultdict(list)
    for pair in pairs:
        source = Path(pair.get("source", ""))
        target = Path(pair.get("target", ""))
        if not source.exists() or not target.exists():
            continue
        try:
            source_lang, source_entries, _ = parse_localization_file(source)
            _, target_entries, _ = parse_localization_file(target)
        except Exception:
            continue
        if source_lang not in {"english", "simp_chinese"}:
            continue
        for key, src in source_entries.items():
            dst = target_entries.get(key, "").strip()
            src = (src or "").strip()
            if not dst or not src or looks_untranslated(src, dst, source_lang):
                continue
            if not _is_auto_glossary_source_candidate(src, source_lang):
                continue
            grouped[src][dst] += 1
            langs[src] = source_lang
            keys_by_source[src].append(key)
    out = []
    for src, counts in grouped.items():
        variants = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        if not variants:
            continue
        out.append({
            "source": src, "source_lang": langs.get(src, "english"),
            "preferred": variants[0][0], "occurrences": sum(counts.values()),
            "variants": [{"text": v, "count": c} for v, c in variants],
            "conflict": len(variants) > 1,
            "keys": keys_by_source[src][:30],
            "source_kind": source_kind,
        })
    out.sort(key=lambda x: (not x["conflict"], -x["occurrences"], x["source"]))
    return out


def resolve_auto_glossary_conflicts(provider: str, url: str, model: str, candidates: List[dict],
                                      preset: str = "General", api_key: str = "",
                                      controller: Optional[TranslationController] = None) -> List[dict]:
    """Ask the configured LLM for one preferred Japanese wording per conflicting term.

    Failure is non-fatal: the frequency-based preferred wording remains in place.
    """
    conflicts = [c for c in candidates if c.get("conflict")][:80]
    if not conflicts or not model:
        return candidates
    payload = [{
        "source": c["source"], "source_lang": c.get("source_lang", "english"),
        "variants": c.get("variants", [])
    } for c in conflicts]
    system = """あなたはParadoxゲーム日本語ローカライズの用語統一担当です。
同じ原語に複数の日本語訳が使われています。各原語について、既存候補から最も自然で一貫した訳語を1つ選ぶか、明らかに改善できる場合だけ短い新しい訳語を提案してください。
文全体ではなく用語・短いラベルとして扱い、ゲーム変数や記号は変更しません。
出力はJSON配列のみ。各要素は {"source":"...","preferred":"..."} としてください。"""
    user = json.dumps({"preset": preset, "items": payload}, ensure_ascii=False)
    try:
        raw = call_llm_raw(provider, url, model, user, system, controller=controller, temperature=0.1, api_key=api_key)
        m = re.search(r'\[.*\]', raw, re.S)
        data = json.loads(m.group(0) if m else raw)
        resolved = {str(x.get("source")): str(x.get("preferred", "")).strip() for x in data if isinstance(x, dict)}
        for c in candidates:
            val = resolved.get(c.get("source", ""))
            if val:
                c["preferred"] = val
                c["llm_resolved"] = True
    except Exception:
        pass
    return candidates


def glossary_variants_path(glossary_path: Path) -> Path:
    glossary_path = Path(glossary_path)
    return glossary_path.with_name(glossary_path.stem + "_variants.json")


def save_auto_glossary_candidates(glossary_path: Path, candidates: List[dict], preserve_existing: bool = True) -> dict:
    """Merge generated terminology into the normal glossary and save variant metadata."""
    glossary_path = Path(glossary_path)
    glossary = load_glossary(glossary_path) if preserve_existing else {}
    variants = load_json(glossary_variants_path(glossary_path), {})
    if not isinstance(variants, dict):
        variants = {}
    added = 0
    conflicts = 0
    for c in candidates:
        src = str(c.get("source", "")).strip()
        preferred = str(c.get("preferred", "")).strip()
        if not src or not preferred:
            continue
        existed = src in glossary
        was_generated = src in variants
        if not existed:
            glossary[src] = preferred
            added += 1
        else:
            preferred = glossary[src]
        # A manually registered term must remain a manual term. Automatic generation
        # and imports may use it as the preferred wording, but must not move it to
        # the generated/imported group merely by creating variant metadata.
        if preserve_existing and existed and not was_generated:
            continue
        if c.get("conflict"):
            conflicts += 1
        variants[src] = {
            "preferred": preferred,
            "variants": [x.get("text", "") for x in c.get("variants", []) if x.get("text")],
            "counts": {x.get("text", ""): int(x.get("count", 0)) for x in c.get("variants", []) if x.get("text")},
            "source_lang": c.get("source_lang", ""),
            "occurrences": int(c.get("occurrences", 0)),
            "source_kind": c.get("source_kind", "auto"),
        }
    save_glossary(glossary_path, glossary)
    save_json(glossary_variants_path(glossary_path), variants)
    return {"added": added, "total": len(candidates), "conflicts": conflicts, "glossary_size": len(glossary)}


def bulk_unify_qa_terms(target_path: Path, source_path: Path, glossary_path: Path) -> dict:
    """Replace known inconsistent Japanese variants with glossary-preferred wording.

    Exact-source candidates are replaced as a whole value. For ordinary glossary
    substring rules, known variant substrings are replaced conservatively.
    """
    target_path = Path(target_path); source_path = Path(source_path); glossary_path = Path(glossary_path)
    source_lang, source_entries, _ = parse_localization_file(source_path)
    _, target_entries, _ = parse_localization_file(target_path)
    glossary = load_glossary(glossary_path)
    meta = load_json(glossary_variants_path(glossary_path), {})
    if not isinstance(meta, dict): meta = {}
    changed = {}
    skipped = 0
    for key, src in source_entries.items():
        if key not in target_entries:
            continue
        value = target_entries[key]
        new_value = value
        for src_term, preferred in glossary.items():
            if not src_term or not preferred or src_term not in src:
                continue
            if preferred in new_value:
                continue
            info = meta.get(src_term, {}) if isinstance(meta.get(src_term, {}), dict) else {}
            variants = [v for v in info.get("variants", []) if v and v != preferred]
            if src.strip() == src_term.strip() and variants and new_value in variants:
                new_value = preferred
                continue
            replaced = False
            for variant in sorted(variants, key=len, reverse=True):
                if variant in new_value:
                    new_value = new_value.replace(variant, preferred)
                    replaced = True
            if not replaced and preferred not in new_value:
                skipped += 1
        if new_value != value:
            changed[key] = new_value
    if changed:
        upsert_localization_values(target_path, changed)
    return {"changed": len(changed), "skipped": skipped, "source_lang": source_lang}

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
    raw = read_localization_text(Path(path))
    lines = raw.splitlines()
    changed = False
    out = []
    for line in lines:
        m = parse_line(line)
        if m and m.group("key").strip() == key and not changed:
            escaped = escape_localization_value(new_value)
            out.append(f'{m.group("indent")}{m.group("key")}: {m.group("version") or ""}"{escaped}"{m.group("trailing") or ""}')
            changed = True
        else:
            out.append(line)
    if changed:
        Path(path).write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")
    return changed


def compare_localization_entries(source_entries: Dict[str, str], target_entries: Dict[str, str], source_lang: str = "english") -> List[dict]:
    """Compare source/target localization dictionaries key-by-key."""
    rows = []
    for key in sorted(set(source_entries) | set(target_entries)):
        src = source_entries.get(key, "")
        dst = target_entries.get(key, "")
        if key not in target_entries:
            status = "missing"
            message = "日本語側にキーがありません"
        elif key not in source_entries:
            status = "extra"
            message = "日本語側だけに存在するキーです"
        elif looks_untranslated(src, dst, source_lang) or (src.strip() and src.strip() == dst.strip()):
            status = "untranslated"
            message = "原文のまま残っている可能性があります"
        else:
            status = "ok"
            message = "対応あり"
        rows.append({"key": key, "status": status, "message": message, "source": src, "target": dst})
    return rows



def run_chinese_basis_translation(input_path, output_path, model=DEFAULT_MODEL, url=DEFAULT_OLLAMA_URL,
                                  target_lang=DEFAULT_TARGET_LANG, workers=1, batch_size=40,
                                  cache_path=None, controller: Optional[TranslationController] = None,
                                  glossary_path=None, preset="General", auto_qa=True,
                                  provider="Ollama", api_key=""):
    """Translate only Simplified Chinese localization using Chinese wording as the terminology basis."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    output_path.mkdir(parents=True, exist_ok=True)
    cache_file = Path(cache_path) if cache_path else output_path / "chinese_basis_translate_cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(cache_file) if cache_file.exists() else {}
    glossary = load_glossary(Path(glossary_path)) if glossary_path else {}

    if input_path.is_file():
        files = [input_path]
        base_dir = input_path.parent
    else:
        base_dir = input_path
        files = gather_yml_files(input_path)
    chinese_files = []
    for f in files:
        try:
            lang = detect_source_lang(f, read_localization_text(f).splitlines()[:5])
        except Exception:
            continue
        if lang == "simp_chinese":
            chinese_files.append(f)
    if not chinese_files:
        raise RuntimeError("簡体字中国語（l_simp_chinese）のYAMLファイルが見つかりませんでした。")

    total_jobs = total_failed = processed = 0
    qa_errors = qa_warnings = 0
    qa_report = []
    planned = set()
    try:
        for i, f in enumerate(chinese_files, 1):
            if controller:
                controller.wait_if_paused()
            rel = f.parent.relative_to(base_dir) if input_path.is_dir() else Path(".")
            out = output_path / remap_rel_dir(rel, target_lang) / rename_for_target(f, target_lang, "simp_chinese")
            out_key = str(out.resolve())
            if out_key in planned:
                continue
            planned.add(out_key)
            stats = process_file(
                f, out, url, model, target_lang, cache, workers, True,
                batch_size, controller, glossary, preset, None, False,
                cache_file, i, len(chinese_files), provider, api_key, True,
            )
            processed += 1
            total_jobs += stats["jobs"]
            total_failed += stats["failed"]
            save_cache(cache_file, cache)
            if auto_qa and out.exists():
                issues = qa_file(out, f, source_lang="simp_chinese", glossary=glossary)
                severe = sum(1 for x in issues if x["severity"] == "error")
                warn = sum(1 for x in issues if x["severity"] == "warning")
                qa_errors += severe
                qa_warnings += warn
                for issue in issues:
                    qa_report.append({"source_file": str(f), "target_file": str(out), **issue})
                print(f"  中国語翻訳語QA: error {severe} / warning {warn}")
            if controller:
                controller.notify(kind="file_done", file=str(f), file_no=i, file_total=len(chinese_files))
                if controller.stop_event.is_set():
                    raise StopRequested()
    except StopRequested:
        save_cache(cache_file, cache)
        return {"interrupted": True, "processed_files": processed, "jobs": total_jobs, "failed": total_failed, "cache": str(cache_file),
                "qa_errors": qa_errors, "qa_warnings": qa_warnings}
    qa_report_path = output_path / "chinese_basis_qa_report.json"
    if auto_qa:
        save_json(qa_report_path, {"source_language": "simp_chinese", "errors": qa_errors, "warnings": qa_warnings, "issues": qa_report})
    return {"interrupted": False, "processed_files": processed, "jobs": total_jobs, "failed": total_failed, "cache": str(cache_file), "output": str(output_path),
            "qa_errors": qa_errors, "qa_warnings": qa_warnings, "qa_report": str(qa_report_path) if auto_qa else ""}


def qa_translation_output(input_path: Path, output_path: Path, glossary_path=None, target_lang: str = DEFAULT_TARGET_LANG) -> dict:
    """Run QA against an existing normal translation output tree.

    The file mapping intentionally mirrors ``run_translation`` so a queue item can
    be checked again after translation without loading files manually in the QA tab.
    English and Simplified Chinese sources are compared source-aware; Japanese
    repair inputs are checked as Japanese output without treating the original
    Japanese text as an untranslated source.
    """
    input_path = Path(input_path)
    output_path = Path(output_path)
    glossary = load_glossary(Path(glossary_path)) if glossary_path else {}
    if input_path.is_file():
        files = [input_path]
        base_dir = input_path.parent
    else:
        files = gather_yml_files(input_path)
        base_dir = input_path
    issues_all = []
    checked = 0
    missing_outputs = 0
    planned = set()
    for f in files:
        try:
            source_lang = detect_source_lang(f, read_localization_text(f).splitlines()[:5])
        except Exception:
            continue
        rel = f.parent.relative_to(base_dir) if input_path.is_dir() else Path(".")
        out = output_path / remap_rel_dir(rel, target_lang) / rename_for_target(f, target_lang, source_lang)
        out_key = str(out.resolve())
        if out_key in planned:
            continue
        planned.add(out_key)
        if not out.exists():
            missing_outputs += 1
            try:
                _, src_entries, _ = parse_localization_file(f)
            except Exception:
                src_entries = {}
            for key in src_entries:
                issues_all.append({"source_file": str(f), "target_file": str(out), "key": key, "severity": "error", "type": "missing_output", "message": "対応する日本語出力ファイルがありません", "value": ""})
            continue
        checked += 1
        source_ref = None if source_lang == target_lang else f
        for issue in qa_file(out, source_ref, source_lang=source_lang, glossary=glossary):
            issues_all.append({"source_file": str(f), "target_file": str(out), **issue})
    errors = sum(1 for x in issues_all if x.get("severity") == "error")
    warnings = sum(1 for x in issues_all if x.get("severity") == "warning")
    return {"checked_files": checked, "missing_outputs": missing_outputs, "errors": errors, "warnings": warnings, "issues": issues_all}


def qa_chinese_basis_translation(input_path: Path, output_path: Path, glossary_path=None) -> dict:
    """Run Chinese-source-aware QA against an existing Chinese-basis translation output."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    glossary = load_glossary(Path(glossary_path)) if glossary_path else {}
    if input_path.is_file():
        files = [input_path]
        base_dir = input_path.parent
    else:
        files = gather_yml_files(input_path)
        base_dir = input_path
    issues_all = []
    checked = 0
    missing_outputs = 0
    for f in files:
        try:
            lang = detect_source_lang(f, read_localization_text(f).splitlines()[:5])
        except Exception:
            continue
        if lang != "simp_chinese":
            continue
        rel = f.parent.relative_to(base_dir) if input_path.is_dir() else Path(".")
        out = output_path / remap_rel_dir(rel, DEFAULT_TARGET_LANG) / rename_for_target(f, DEFAULT_TARGET_LANG, "simp_chinese")
        if not out.exists():
            missing_outputs += 1
            try:
                _, src_entries, _ = parse_localization_file(f)
            except Exception:
                src_entries = {}
            for key in src_entries:
                issues_all.append({"source_file": str(f), "target_file": str(out), "key": key, "severity": "error", "type": "missing_output", "message": "対応する日本語出力ファイルがありません", "value": ""})
            continue
        checked += 1
        for issue in qa_file(out, f, source_lang="simp_chinese", glossary=glossary):
            issues_all.append({"source_file": str(f), "target_file": str(out), **issue})
    errors = sum(1 for x in issues_all if x.get("severity") == "error")
    warnings = sum(1 for x in issues_all if x.get("severity") == "warning")
    return {"checked_files": checked, "missing_outputs": missing_outputs, "errors": errors, "warnings": warnings, "issues": issues_all}


def translate_single_text(url: str, model: str, text: str, source_lang: str = "english",
                          glossary: Optional[dict] = None, preset: str = "General",
                          provider: str = "Ollama", api_key: str = "",
                          controller: Optional[TranslationController] = None,
                          chinese_basis: bool = False) -> str:
    """Translate one localization value while preserving Paradox tokens."""
    protected, tokens = protect_text(text)
    job = {"value": text, "protected": protected, "tokens": tokens}
    out = translate_batch(url, model, [job], source_lang, glossary=glossary, preset=preset,
                          dual_source=False, controller=controller, provider=provider, api_key=api_key,
                          chinese_basis=chinese_basis)[0]
    return restore_text(out, tokens)


def upsert_localization_values(path: Path, values: Dict[str, str], target_lang: str = "japanese") -> int:
    """Update existing keys and append missing keys to a Paradox localization YAML file."""
    path = Path(path)
    if not values:
        return 0
    if path.exists():
        raw = read_localization_text(path)
        lines = raw.splitlines()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"l_{target_lang}:"]
    pending = dict(values)
    out = []
    changed = 0
    for line in lines:
        m = parse_line(line)
        if m:
            key = m.group("key").strip()
            if key in pending:
                val = pending.pop(key)
                escaped = escape_localization_value(val)
                out.append(f'{m.group("indent")}{m.group("key")}: {m.group("version") or ""}"{escaped}"{m.group("trailing") or ""}')
                changed += 1
                continue
        out.append(line)
    if pending:
        if not out:
            out.append(f"l_{target_lang}:")
        for key, val in pending.items():
            escaped = escape_localization_value(val)
            out.append(f' {key}: "{escaped}"')
            changed += 1
    path.write_text("\ufeff" + "\n".join(out) + "\n", encoding="utf-8")
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
            text = read_localization_text(p)
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



def _collect_mod_language_entries(mod_root: Path) -> dict:
    """Collect source/Japanese localization entries for one mod."""
    loc = mod_localization_root(mod_root)
    result = {"localization": str(loc) if loc else "", "source": {}, "japanese": {}, "japanese_files": []}
    if not loc:
        return result
    for f in gather_yml_files(loc):
        try:
            lang, entries, _ = parse_localization_file(f)
        except Exception:
            continue
        if lang == "japanese":
            result["japanese"].update(entries)
            result["japanese_files"].append(str(f))
        elif lang in {"english", "simp_chinese"}:
            # Prefer English wording if both exist for the same key.
            if lang == "english":
                result["source"].update(entries)
            else:
                for k, v in entries.items():
                    result["source"].setdefault(k, v)
    return result


def build_translation_mod_index(mod_roots: Iterable[Path]) -> List[dict]:
    """Build a reusable index of mods that contain Japanese localization.

    The index is intentionally key-based rather than filename-based because Japanese
    translation mods frequently mirror another Workshop mod with a different folder
    and descriptor name.
    """
    rows = []
    for root in mod_roots:
        root = Path(root)
        data = _collect_mod_language_entries(root)
        ja = data.get("japanese", {})
        if not ja:
            continue
        rows.append({
            "path": str(root),
            "mod": detect_mod_name(root),
            "localization": data.get("localization", ""),
            "japanese": ja,
            "japanese_keys": set(ja),
        })
    return rows


def _normalize_mod_name_for_match(name: str) -> str:
    text = (name or "").lower()
    for token in ["japanese", "日本語化", "日本語", "translation", "localization", "localisation", "jp", "ja"]:
        text = text.replace(token, " ")
    return re.sub(r'[^0-9a-z\u3040-\u30ff\u4e00-\u9fff]+', '', text)


def _external_gap_candidates(source_entries: Dict[str, str], japanese_entries: Dict[str, str]) -> List[dict]:
    candidates = []
    for key, source_text in source_entries.items():
        target = japanese_entries.get(key)
        if target is None:
            candidates.append({"kind": "missing_key", "key": key, "source_text": source_text, "target_text": "", "confidence": "確定"})
            continue
        if source_text.strip() == target.strip() and source_text.strip():
            candidates.append({"kind": "source_copy", "key": key, "source_text": source_text, "target_text": target, "confidence": "確定"})
            continue
        if looks_foreign_in_target(target, "japanese"):
            candidates.append({"kind": "foreign_text", "key": key, "source_text": source_text, "target_text": target, "confidence": "要確認"})
    return candidates


def find_external_japanese_translation(mod_root: Path, translation_index: Optional[List[dict]]) -> Optional[dict]:
    """Find the most plausible separate Japanese translation mod for *mod_root*.

    Matching uses localization-key overlap, with descriptor/name similarity as a
    secondary signal. This avoids relying on Workshop IDs or exact file names.
    """
    if not translation_index:
        return None
    mod_root = Path(mod_root)
    src_data = _collect_mod_language_entries(mod_root)
    source_entries = src_data.get("source", {})
    if not source_entries:
        return None
    source_keys = set(source_entries)
    source_name = detect_mod_name(mod_root)
    source_norm = _normalize_mod_name_for_match(source_name)
    best = None
    best_score = -1.0
    for row in translation_index:
        try:
            cand_path = Path(row.get("path", ""))
            if cand_path.resolve() == mod_root.resolve():
                continue
        except Exception:
            continue
        ja = row.get("japanese", {}) or {}
        ja_keys = set(ja)
        overlap = source_keys & ja_keys
        overlap_n = len(overlap)
        if not overlap_n:
            continue
        coverage = overlap_n / max(1, len(source_keys))
        precision = overlap_n / max(1, len(ja_keys))
        cand_norm = _normalize_mod_name_for_match(row.get("mod", ""))
        name_match = bool(source_norm and cand_norm and (source_norm in cand_norm or cand_norm in source_norm))
        # Conservative acceptance to avoid mistaking generic shared game keys for a translation mod.
        accept = coverage >= 0.55 or (coverage >= 0.25 and overlap_n >= 20) or (name_match and overlap_n >= 3 and coverage >= 0.10)
        if not accept:
            continue
        score = coverage * 100 + min(precision, 1.0) * 12 + (18 if name_match else 0) + min(overlap_n, 100) / 100
        if score <= best_score:
            continue
        gaps = _external_gap_candidates(source_entries, ja)
        best_score = score
        best = {
            "mod": row.get("mod", cand_path.name),
            "path": str(cand_path),
            "localization": row.get("localization", ""),
            "coverage": coverage,
            "overlap_keys": overlap_n,
            "source_keys": len(source_keys),
            "gap_count": len(gaps),
            "gaps": gaps,
            "complete": len(gaps) == 0,
        }
    return best


def analyze_mod_translation_status(mod_root: Path, preferred_source: str = "english", translation_index: Optional[List[dict]] = None) -> dict:
    """Return a mod-level Japanese translation status without invoking an LLM.

    If ``translation_index`` is supplied, a separate Japanese translation mod is also
    detected and classified as complete/incomplete.
    """
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
        "simp_chinese_files": 0,
        "simp_chinese_keys": 0,
        "japanese_files": 0,
        "source_keys": 0,
        "japanese_keys": 0,
        "gap_count": 0,
        "candidates": [],
        "external_translation_mod": "",
        "external_translation_path": "",
        "external_translation_localization": "",
        "external_translation_gap_count": 0,
        "external_translation_complete": False,
        "external_translation_gaps": [],
    }
    if not loc:
        return result

    source_keys = set()
    japanese_keys = set()
    source_files = 0
    simp_chinese_files = 0
    simp_chinese_keys = set()
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
            if lang == "simp_chinese":
                simp_chinese_files += 1
                simp_chinese_keys.update(entries.keys())

    candidates = scan_translation_gaps(loc, preferred_source=preferred_source)
    result.update({
        "source_files": source_files,
        "simp_chinese_files": simp_chinese_files,
        "simp_chinese_keys": len(simp_chinese_keys),
        "japanese_files": japanese_files,
        "source_keys": len(source_keys),
        "japanese_keys": len(japanese_keys),
        "gap_count": len(candidates),
        "candidates": candidates,
    })

    external = find_external_japanese_translation(mod_root, translation_index)
    if external:
        result.update({
            "external_translation_mod": external.get("mod", ""),
            "external_translation_path": external.get("path", ""),
            "external_translation_localization": external.get("localization", ""),
            "external_translation_gap_count": external.get("gap_count", 0),
            "external_translation_complete": bool(external.get("complete")),
            "external_translation_gaps": external.get("gaps", []),
            "external_translation_coverage": external.get("coverage", 0.0),
        })

    if not source_keys:
        result["status"] = "対象なし"
        result["message"] = f"{name}には判定対象となる英語/中国語ローカライズが見つかりませんでした。"
    elif japanese_files > 0 and japanese_keys and not candidates:
        result["status"] = "翻訳あり"
        result["message"] = f"{name}のModは日本語翻訳が確認できました。"
        if external:
            result["message"] += f" 別Mod『{external['mod']}』にも日本語化があります。"
    elif external and external.get("complete"):
        result["status"] = "別Modで完全翻訳"
        result["gap_count"] = 0
        result["message"] = f"{name}には日本語化Mod『{external['mod']}』があり、完全な日本語化を確認できました。"
    elif external:
        result["status"] = "別Mod翻訳・欠損"
        result["gap_count"] = int(external.get("gap_count", 0))
        result["candidates"] = list(external.get("gaps", []))
        result["message"] = f"{name}には日本語化Mod『{external['mod']}』がありますが、翻訳に欠損があります（{result['gap_count']}件）。"
    elif japanese_files == 0 or not japanese_keys:
        result["status"] = "翻訳なし"
        result["message"] = f"{name}というModは日本語翻訳がありません。日本語化Modも確認できませんでした。"
    elif candidates:
        result["status"] = "欠損あり"
        result["message"] = f"{name}のModに翻訳の欠損箇所があります（{len(candidates)}件）。"
    else:
        result["status"] = "翻訳あり"
        result["message"] = f"{name}のModは日本語翻訳が確認できました。"
    return result

# ---------------------------------------------------------------------------
# Automatic Paradox / Steam mod-location discovery
# ---------------------------------------------------------------------------

PARADOX_STEAM_GAMES = {
    "Crusader Kings III": {"appid": "1158310", "docs": ["Crusader Kings III"]},
    "Victoria 3": {"appid": "529340", "docs": ["Victoria 3"]},
    "Hearts of Iron IV": {"appid": "394360", "docs": ["Hearts of Iron IV"]},
    "Stellaris": {"appid": "281990", "docs": ["Stellaris"]},
    "Europa Universalis V": {"appid": "3450310", "docs": ["Europa Universalis V"]},
}


def _windows_drive_roots() -> List[Path]:
    """Return currently mounted Windows drive roots (C:\\, D:\\, ...)."""
    roots: List[Path] = []
    if not sys.platform.startswith("win"):
        return roots
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if mask & (1 << i):
                roots.append(Path(f"{chr(65+i)}:\\\\"))
    except Exception:
        for i in range(26):
            p = Path(f"{chr(65+i)}:\\\\")
            try:
                if p.exists():
                    roots.append(p)
            except Exception:
                pass
    return roots


def _mounted_volume_roots(home: Optional[Path] = None, platform: Optional[str] = None) -> List[Path]:
    """Return likely roots of secondary/internal/external volumes without deep scanning."""
    home = Path(home or Path.home())
    platform = platform or sys.platform
    roots: List[Path] = []
    if platform.startswith("win"):
        roots.extend(_windows_drive_roots())
    elif platform == "darwin":
        volumes = Path("/Volumes")
        if volumes.is_dir():
            try:
                roots.extend(p for p in volumes.iterdir() if p.is_dir())
            except OSError:
                pass
    else:
        candidates = [Path("/mnt"), Path("/media"), Path("/run/media")]
        for base in candidates:
            if not base.is_dir():
                continue
            try:
                for p in base.iterdir():
                    if not p.is_dir():
                        continue
                    roots.append(p)
                    # Linux desktop mounts are often /media/$USER/<volume>.
                    try:
                        if p.name == home.name or base.name in {"media"}:
                            roots.extend(c for c in p.iterdir() if c.is_dir())
                    except OSError:
                        pass
            except OSError:
                pass
    # Deduplicate while keeping order.
    seen = set(); out = []
    for p in roots:
        key = str(p).lower()
        if key not in seen:
            seen.add(key); out.append(p)
    return out


def _shallow_steam_library_candidates(volume_root: Path) -> List[Path]:
    """Find Steam library roots on a volume using only a shallow, bounded scan.

    This deliberately avoids recursive whole-drive searching. It checks common names and
    first-level directories that already contain a steamapps folder.
    """
    volume_root = Path(volume_root)
    candidates: List[Path] = []
    common_names = (
        "Steam", "SteamLibrary", "steam", "steamlibrary",
        "Games/Steam", "Games/SteamLibrary",
        "Program Files (x86)/Steam", "Program Files/Steam",
    )
    for rel in common_names:
        p = volume_root / rel
        if (p / "steamapps").is_dir():
            candidates.append(p)
    if (volume_root / "steamapps").is_dir():
        candidates.append(volume_root)
    # Also inspect first-level folders only. This catches custom names such as D:\\GameSSD.
    try:
        children = list(volume_root.iterdir())[:256]
    except Exception:
        children = []
    for child in children:
        try:
            if child.is_dir() and (child / "steamapps").is_dir():
                candidates.append(child)
        except OSError:
            continue
    seen = set(); out = []
    for p in candidates:
        try:
            key = str(p.resolve()).lower()
        except Exception:
            key = str(p).lower()
        if key not in seen:
            seen.add(key); out.append(p)
    return out


def _steam_root_candidates(home: Optional[Path] = None, platform: Optional[str] = None,
                           scan_other_volumes: bool = True) -> List[Path]:
    """Return likely Steam installation/library roots for the current OS.

    Besides standard locations this can discover Steam libraries on other drives/SSDs.
    The extra scan is intentionally shallow so it remains practical on large disks.
    """
    home = Path(home or Path.home())
    platform = platform or sys.platform
    out: List[Path] = []
    if platform == "darwin":
        out += [home / "Library/Application Support/Steam"]
    elif platform.startswith("win"):
        import os
        for env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            base = os.environ.get(env)
            if base:
                out.append(Path(base) / "Steam")
        out += [home / "AppData/Local/Steam"]
    else:
        out += [home / ".local/share/Steam", home / ".steam/steam", home / ".steam/root"]

    if scan_other_volumes:
        for volume in _mounted_volume_roots(home, platform):
            out.extend(_shallow_steam_library_candidates(volume))

    seen = set(); result = []
    for p in out:
        key = str(p).lower()
        if key not in seen:
            seen.add(key); result.append(p)
    return result

def _parse_steam_libraryfolders(vdf_path: Path) -> List[Path]:
    """Best-effort parser for Steam libraryfolders.vdf across old/new formats."""
    try:
        text = Path(vdf_path).read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
    libs: List[Path] = []
    # New format: "path" "D:\\SteamLibrary". Old format: "1" "D:\\SteamLibrary".
    patterns = [
        r'"path"\s+"([^"]+)"',
        r'^\s*"\d+"\s+"([^"]+)"\s*$',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, flags=re.I | re.M):
            raw = m.group(1).replace('\\\\', '\\')
            p = Path(raw)
            if p not in libs:
                libs.append(p)
    return libs


def discover_steam_libraries(home: Optional[Path] = None, platform: Optional[str] = None,
                             extra_roots: Optional[Iterable[Path]] = None) -> List[Path]:
    """Discover Steam library roots, including libraries registered in libraryfolders.vdf."""
    roots = list(extra_roots or []) + _steam_root_candidates(home, platform)
    libs: List[Path] = []
    for root in roots:
        root = Path(root)
        if root.exists() and root not in libs:
            libs.append(root)
        vdf = root / "steamapps/libraryfolders.vdf"
        for lib in _parse_steam_libraryfolders(vdf):
            if lib.exists() and lib not in libs:
                libs.append(lib)
    return libs


def _count_mod_roots_fast(parent: Path) -> int:
    """Count likely mods without recursively parsing localization files."""
    parent = Path(parent)
    if not parent.is_dir():
        return 0
    count = 0
    try:
        for child in parent.iterdir():
            if not child.is_dir():
                continue
            if (child / "localization").is_dir() or (child / "descriptor.mod").exists():
                count += 1
    except OSError:
        pass
    return count


def _paradox_documents_root(home: Path) -> Path:
    return home / "Documents" / "Paradox Interactive"


def discover_paradox_mod_locations(home: Optional[Path] = None, platform: Optional[str] = None,
                                   extra_steam_roots: Optional[Iterable[Path]] = None) -> List[dict]:
    """Discover selectable Paradox mod locations on macOS, Windows and Linux.

    Returned rows contain: game, kind, path, appid, mod_count.
    Sources include Steam Workshop libraries and Paradox user-mod folders.
    """
    home = Path(home or Path.home())
    results: List[dict] = []
    seen = set()

    def add(game: str, kind: str, path: Path, appid: str = ""):
        path = Path(path)
        if not path.is_dir():
            return
        try:
            resolved = str(path.resolve())
        except Exception:
            resolved = str(path)
        key = (game, kind, resolved)
        if key in seen:
            return
        seen.add(key)
        results.append({
            "game": game,
            "kind": kind,
            "path": resolved,
            "appid": appid,
            "mod_count": _count_mod_roots_fast(path),
        })

    # Steam Workshop locations in every registered library.
    for lib in discover_steam_libraries(home, platform, extra_roots=extra_steam_roots):
        steamapps = lib / "steamapps"
        for game, meta in PARADOX_STEAM_GAMES.items():
            appid = meta["appid"]
            workshop = steamapps / "workshop" / "content" / appid
            if workshop.is_dir():
                add(game, "Steam Workshop", workshop, appid)

    # Paradox launcher / manually installed user mods.
    docs_root = _paradox_documents_root(home)
    for game, meta in PARADOX_STEAM_GAMES.items():
        for docs_name in meta.get("docs", []):
            mod_dir = docs_root / docs_name / "mod"
            if mod_dir.is_dir():
                add(game, "ローカルMod", mod_dir, meta["appid"])

    return sorted(results, key=lambda x: (x["game"].lower(), x["kind"], x["path"].lower()))
