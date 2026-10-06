from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

import translator_core as core


class _FakeLocalLLM(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _send(self, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.server.paths.append(self.path)
        if self.path == "/api/tags":
            self._send({"models": [{"name": "qwen3:8b"}]})
        elif self.path == "/v1/models":
            self._send({"data": [{"id": "lm-model"}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        self.server.paths.append(self.path)
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path == "/api/chat":
            self._send({"message": {"content": "1|||訳"}})
        else:
            self._send({"choices": [{"message": {"content": "1|||訳"}}]})


@pytest.fixture
def local_server():
    server = HTTPServer(("127.0.0.1", 0), _FakeLocalLLM)
    server.paths = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def broken_system_proxy(monkeypatch):
    # Windows/macOSのシステムプロキシや環境変数のプロキシが、localhostの除外なしで設定されている状態。
    for name in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("http_proxy", "http://127.0.0.1:9")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:9")


def test_local_model_list_bypasses_system_proxy(local_server, broken_system_proxy):
    port = local_server.server_address[1]

    assert core.list_models("Ollama", f"http://localhost:{port}") == ["qwen3:8b"]
    assert core.list_models("LM Studio", f"http://127.0.0.1:{port}/v1") == ["lm-model"]


def test_local_llm_call_bypasses_system_proxy(local_server, broken_system_proxy):
    port = local_server.server_address[1]

    out = core.call_llm_raw("Ollama", f"http://localhost:{port}", "qwen3:8b", "1|||text", "sys", retries=1)

    assert out == "1|||訳"


def test_local_url_without_scheme_or_with_openai_suffix_is_normalized(local_server):
    port = local_server.server_address[1]

    assert core.list_models("Ollama", f"localhost:{port}") == ["qwen3:8b"]
    assert core.list_models("Ollama", f"http://localhost:{port}/v1/") == ["qwen3:8b"]
    assert core.list_models("LM Studio", f"127.0.0.1:{port}") == ["lm-model"]
    assert local_server.paths == ["/api/tags", "/api/tags", "/v1/models"]


def test_remote_hosts_keep_using_configured_proxy():
    assert core._is_local_llm_host("localhost") is True
    assert core._is_local_llm_host("127.0.0.1") is True
    assert core._is_local_llm_host("::1") is True
    assert core._is_local_llm_host("192.168.1.20") is True
    assert core._is_local_llm_host("api.openai.com") is False
    assert core._is_local_llm_host("8.8.8.8") is False


def test_reasoning_is_stripped_from_thinking_model_output():
    assert core.strip_reasoning("<think>考え中</think>\n1|||訳") == "\n1|||訳"
    # Qwen3-Thinking系はテンプレートが<think>を書くため、本文には閉じタグだけが残る。
    assert core.strip_reasoning("Okay, let me think...\n</think>\n\n1|||訳") == "\n\n1|||訳"
    # 思考の途中で打ち切られた応答は空として扱い、再試行させる。
    assert core.strip_reasoning("<think>Okay, so I need") == ""
    assert core.strip_reasoning("1|||訳") == "1|||訳"


class _FakeThinkingOllama(_FakeLocalLLM):
    def do_POST(self):
        self.server.paths.append(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.server.bodies.append(body)
        if self.path == "/api/show":
            self._send({"model_info": {"general.finetune": "Thinking"}})
        elif self.path == "/api/chat":
            self._send({"message": {"content": "Okay, so I need to translate"}})


def test_ollama_disables_thinking_and_explains_thinking_only_models():
    server = HTTPServer(("127.0.0.1", 0), _FakeThinkingOllama)
    server.paths, server.bodies = [], []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        port = server.server_address[1]
        with pytest.raises(RuntimeError, match="Thinking専用モデル"):
            core.call_llm_raw("Ollama", f"http://localhost:{port}", "qwen3:4b", "1|||text", "sys", retries=1)
        chat = [b for p, b in zip(server.paths, server.bodies) if p == "/api/chat"]
        assert chat and chat[0]["think"] is False
    finally:
        server.shutdown()
        server.server_close()


def test_thinking_only_warning_by_model_name_for_openai_compatible_servers():
    assert core.thinking_only_model_warning("LM Studio", "http://localhost:1234/v1", "deepseek/deepseek-r1-0528-qwen3-8b")
    assert core.thinking_only_model_warning("LM Studio", "http://localhost:1234/v1", "qwen3-4b-thinking-2507")
    assert core.thinking_only_model_warning("LM Studio", "http://localhost:1234/v1", "qwen/qwen3.8-27b") == ""
    assert core.thinking_only_model_warning("LM Studio", "http://localhost:1234/v1", "google/gemma-4-31b") == ""
    assert core.thinking_only_model_warning("OpenAI", "", "o1-thinking") == ""


class _FakeModelKinds(_FakeLocalLLM):
    """Ollama の /api/show の capabilities と、LM Studio の /api/v0/models の type を返す偽サーバー。"""

    def do_GET(self):
        self.server.paths.append(self.path)
        if self.path == "/api/v0/models":
            self._send({"data": [{"id": "acme/retriever-v2", "type": "embeddings"},
                                 {"id": "qwen/qwen3-8b", "type": "llm"}]})
        elif self.path == "/v1/models":
            self._send({"data": [{"id": "acme/retriever-v2"}, {"id": "qwen/qwen3-8b"}]})
        else:
            super().do_GET()

    def do_POST(self):
        self.server.paths.append(self.path)
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        self.server.bodies.append(body)
        if self.path == "/api/show":
            caps = ["embedding"] if body.get("model") == "bge-m3" else ["completion", "tools"]
            self._send({"capabilities": caps, "model_info": {}})
        elif self.path == "/api/chat":
            self._send({"message": {"content": "0|||訳"}})


@pytest.fixture
def kinds_server():
    server = HTTPServer(("127.0.0.1", 0), _FakeModelKinds)
    server.paths, server.bodies = [], []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


def test_embedding_only_models_are_blocked_before_translation(kinds_server):
    url = f"http://localhost:{kinds_server.server_address[1]}"
    # 名前に embed を含むモデル
    assert core.EMBEDDING_ONLY_MARKER in core.unusable_model_warning("Ollama", url, "nomic-embed-text:latest")
    assert core.unusable_model_warning("OpenAI互換", url, "text-embedding-nomic-embed-text-v1.5")
    # 名前で分からなくても、Ollama の capabilities が embedding だけなら止める
    assert core.EMBEDDING_ONLY_MARKER in core.unusable_model_warning("Ollama", url, "bge-m3")
    # LM Studio は /api/v0/models の type で見分ける（/v1 付きの URL でも）
    assert core.EMBEDDING_ONLY_MARKER in core.unusable_model_warning("LM Studio", url + "/v1", "acme/retriever-v2")
    # 文章を生成するモデルは止めない
    assert core.unusable_model_warning("Ollama", url, "qwen3:8b") == ""
    assert core.unusable_model_warning("LM Studio", url + "/v1", "qwen/qwen3-8b") == ""
    # クラウドのプロバイダには問い合わせない
    assert core.embedding_only_model_warning("OpenAI", "", "text-embedding-3-small") == ""


def test_ollama_request_sets_num_ctx_from_batch_size(kinds_server):
    url = f"http://localhost:{kinds_server.server_address[1]}"
    core.call_llm_raw("Ollama", url, "qwen3:8b", "0|||Hello", "sys", retries=1)
    core.call_llm_raw("Ollama", url, "qwen3:8b", "0|||" + "長い文章。" * 3000, "sys", retries=1)
    chats = [b for p, b in zip(kinds_server.paths, kinds_server.bodies) if p == "/api/chat"]

    assert [c["options"]["num_ctx"] for c in chats] == [8192, 32768]
    assert chats[0]["options"]["temperature"] == 0.2


def test_ollama_num_ctx_uses_fixed_steps_to_avoid_reloads():
    assert core.ollama_num_ctx("sys", "0|||short") == 8192
    # 日本語 2,000 文字（入力と同量の出力を見込む）は 8192 に収まらない
    assert core.ollama_num_ctx("sys", "あ" * 4000) == 16384
    # 上限を超える量でも段階の最大値で止める（サーバー既定の 256K などに任せない）
    assert core.ollama_num_ctx("sys", "あ" * 100000) == 32768
    assert set(core.OLLAMA_NUM_CTX_STEPS) >= {8192, 16384, 32768}
