"""考える過程を出すモデル（reasoning）の見分けと止め方（v0.12.0）。LLM は偽のサーバーで差し替える。"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import translator_core as core


class _Fake(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.server.bodies.append((self.path, body))
        mode = self.server.mode
        if mode == "reject_effort" and "reasoning_effort" in body:
            self.send_response(400); self.end_headers(); self.wfile.write(b'{"error":"unknown reasoning_effort"}'); return
        if self.path == "/api/chat":
            message = {"content": "", "thinking": "Let me think..."} if mode == "thinking" else {"content": "0|||訳"}
            payload = {"message": message}
        elif mode == "thinking":
            payload = {"choices": [{"message": {"content": "", "reasoning_content": "We need to translate..."},
                                    "finish_reason": "length"}]}
        else:
            payload = {"choices": [{"message": {"content": "0|||Traduction"}}]}
        data = json.dumps(payload).encode()
        self.send_response(200); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)


@pytest.fixture
def server():
    srv = HTTPServer(("127.0.0.1", 0), _Fake)
    srv.bodies, srv.mode = [], "ok"
    thread = threading.Thread(target=srv.serve_forever, daemon=True); thread.start()
    yield srv
    srv.shutdown(); srv.server_close()
    core._LMSTUDIO_NO_REASONING_EFFORT.clear()


def _url(srv):
    return f"http://localhost:{srv.server_address[1]}"


def test_lm_studio_requests_ask_to_turn_reasoning_off(server):
    assert core.call_llm_raw("LM Studio", _url(server), "m", "0|||Hello", "sys", retries=1) == "0|||Traduction"
    assert server.bodies[0][1]["reasoning_effort"] == "none"


def test_reasoning_effort_is_dropped_when_the_server_rejects_it(server):
    server.mode = "reject_effort"
    assert core.call_llm_raw("LM Studio", _url(server), "m", "0|||Hello", "sys", retries=1) == "0|||Traduction"
    assert "reasoning_effort" not in server.bodies[-1][1]
    core.call_llm_raw("LM Studio", _url(server), "m", "0|||Hello", "sys", retries=1)
    assert "reasoning_effort" not in server.bodies[-1][1]  # 2回目からは最初から送らない


@pytest.mark.parametrize("provider", ["LM Studio", "OpenAI互換", "Ollama"])
def test_reasoning_only_answers_stop_at_once_without_retrying(server, provider):
    server.mode = "thinking"
    with pytest.raises(core.ReasoningModelError, match=core.REASONING_MODEL_MARKER):
        core.call_llm_raw(provider, _url(server), "think-model", "0|||Hello", "sys", retries=5)
    assert len([path for path, _body in server.bodies if path != "/api/show"]) == 1  # 翻訳の依頼は1回だけ


def test_probe_before_start_warns_about_reasoning_models_only(server):
    server.mode = "thinking"
    warning = core.reasoning_model_probe_warning("LM Studio", _url(server), "think-model")
    assert core.REASONING_MODEL_MARKER in warning and "instruct" in warning
    assert server.bodies[-1][1]["max_tokens"] == 64
    server.mode = "ok"
    assert core.reasoning_model_probe_warning("LM Studio", _url(server), "plain-model") == ""
    # 確かめられない（つながらない）ときは止めない。クラウドには送らない
    assert core.reasoning_model_probe_warning("LM Studio", "http://localhost:9", "m") == ""
    count = len(server.bodies)
    assert core.reasoning_model_probe_warning("OpenAI", _url(server), "gpt") == "" and len(server.bodies) == count
