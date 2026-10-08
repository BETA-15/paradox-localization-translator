"""v0.11.79：API キーの送り先と、待機中の CPU 使用の修正。"""
from __future__ import annotations

import importlib
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
import urllib.request

os.environ.setdefault("PARADOX_TRANSLATOR_DATA_ROOT", tempfile.mkdtemp(prefix="plt-v0-11-79-"))
main = importlib.import_module("main")
core = main.core


# ---------- 「https://」の無い URL ----------

def test_scheme_less_cloud_url_gets_https():
    assert core._base_url_for_provider("OpenAI", "api.openai.com/v1") == "https://api.openai.com/v1"
    assert core._base_url_for_provider("OpenAI Compatible", "openrouter.ai/api/v1").startswith("https://")


def test_scheme_less_local_url_keeps_http():
    assert core._base_url_for_provider("Ollama", "localhost:11434") == "http://localhost:11434"
    assert core._base_url_for_provider("LM Studio", "127.0.0.1:1234") == "http://127.0.0.1:1234"
    assert core._base_url_for_provider("LM Studio", "192.168.1.5:1234") == "http://192.168.1.5:1234"


def test_explicit_scheme_is_kept():
    assert core._base_url_for_provider("OpenAI Compatible", "http://example.com/v1") == "http://example.com/v1"


# ---------- 環境変数のキー ----------

def test_openai_compatible_does_not_borrow_openai_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.delenv("PLT_API_KEY", raising=False)
    assert core.env_api_key_for_provider("OpenAI Compatible") == ""
    monkeypatch.setenv("PLT_API_KEY", "compat-secret")
    assert core.env_api_key_for_provider("OpenAI Compatible") == "compat-secret"
    assert core.env_api_key_for_provider("OpenAI") == "openai-secret"


# ---------- リダイレクトでキーを別の相手へ送らない ----------

class _Recorder(BaseHTTPRequestHandler):
    seen: list = []
    target = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/redirect" and self.target:
            self.send_response(302); self.send_header("Location", self.target); self.end_headers(); return
        type(self).seen.append({k.lower(): v for k, v in self.headers.items()})
        body = b"{}"
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)


def _server(handler):
    s = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def test_cross_origin_redirect_drops_api_key_headers():
    class B(_Recorder):
        seen = []
    class A(_Recorder):
        seen = []
    b = _server(B); a = _server(A)
    A.target = f"http://127.0.0.1:{b.server_address[1]}/landing"
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{a.server_address[1]}/redirect",
                                     headers={"Authorization": "Bearer secret", "x-api-key": "secret",
                                              "x-goog-api-key": "secret", "X-Other": "keep"})
        with core._urlopen(req, timeout=5) as r:
            r.read()
        got = B.seen[-1]
        assert "authorization" not in got and "x-api-key" not in got and "x-goog-api-key" not in got
        assert got.get("x-other") == "keep"
    finally:
        a.shutdown(); b.shutdown()


def test_same_origin_redirect_keeps_api_key():
    class A(_Recorder):
        seen = []
    a = _server(A)
    A.target = f"http://127.0.0.1:{a.server_address[1]}/landing"
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{a.server_address[1]}/redirect",
                                     headers={"Authorization": "Bearer secret"})
        with core._urlopen(req, timeout=5) as r:
            r.read()
        assert A.seen[-1].get("authorization") == "Bearer secret"
    finally:
        a.shutdown()


# ---------- プロバイダを切り替えたときのキー ----------

class _Var:
    def __init__(self, v=""): self.v = v
    def get(self): return self.v
    def set(self, v): self.v = v


def _provider_state(provider, key):
    s = SimpleNamespace(provider_var=_Var(provider), url_var=_Var(""), model_var=_Var("m"),
                        api_key_var=_Var(key), _api_keys_by_provider={}, _api_key_provider=provider,
                        refresh_models=lambda: None)
    s._swap_api_key_for_provider = lambda: main.App._swap_api_key_for_provider(s)
    return s


def test_provider_change_does_not_carry_key_to_other_provider():
    s = _provider_state("OpenAI", "openai-secret")
    s.provider_var.set("Anthropic")
    main.App.on_provider_change(s)
    assert s.api_key_var.get() == ""
    s.api_key_var.set("anthropic-secret")
    s.provider_var.set("OpenAI")
    main.App.on_provider_change(s)
    assert s.api_key_var.get() == "openai-secret"  # 同じプロバイダに戻ればその鍵を戻す（保存はしない）
    s.provider_var.set("Anthropic")
    main.App.on_provider_change(s)
    assert s.api_key_var.get() == "anthropic-secret"


# ---------- 待機中の画面の状態の設定し直し ----------

def test_refresh_operation_states_skips_when_nothing_changed(monkeypatch):
    calls = []
    s = SimpleNamespace(
        _normal_queue_locked=lambda: False, _chinese_queue_locked=lambda: False,
        _normal_queue_controls=[], _chinese_queue_controls=[], _cross_queue_controls=[], _data_root_controls=[],
        _set_control_group_state=lambda group, locked: calls.append("group"),
        _thread_is_active=lambda t: False, worker=None, controller=None,
        chinese_worker=None, chinese_controller=None, _closing=False,
        _active_file_operation_names=lambda: [],
        review_batch_contexts=None, review_last_qa_contexts=None,
        _operation_state_signature=None, _operation_state_refreshed_at=0.0,
    )
    clock = [1000.0]
    monkeypatch.setattr(main.time, "monotonic", lambda: clock[0])
    main.App._refresh_operation_states(s)
    first = len(calls)
    assert first > 0
    clock[0] += 0.1
    main.App._refresh_operation_states(s)
    assert len(calls) == first  # 変わっていなければ設定し直さない
    clock[0] += 1.5
    main.App._refresh_operation_states(s)
    assert len(calls) == first * 2  # 1秒に1回は念のため設定し直す
    s._normal_queue_locked = lambda: True
    clock[0] += 0.1
    main.App._refresh_operation_states(s)
    assert len(calls) == first * 3  # 状態が変われば、すぐ設定し直す
