"""Users give the CLI their LLM key and GitHub token. These tests pin down that neither leaves their machine
except to the one service it belongs to, and never shows up in output."""


def test_keys_only_travel_encrypted_or_stay_on_your_network():
    from chokepoint.agent.llm import insecure

    for ok in ("https://api.groq.com/openai/v1", "http://localhost:11434/v1", "http://127.0.0.1:1234/v1",
               "http://192.168.1.20:11434/v1", "http://host.docker.internal:11434/v1", "http://gpu-box.local/v1"):
        assert insecure(ok) is None, ok
    for bad in ("http://api.example.com/v1", "http://8.8.8.8/v1", "ftp://example.com", "api.groq.com/v1"):
        assert insecure(bad), bad


def test_no_llm_client_for_an_unencrypted_remote_url(monkeypatch):
    from chokepoint.agent import llm

    monkeypatch.setenv("LLM_BASE_URL", "http://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "m")
    monkeypatch.setenv("LLM_API_KEY", "sk-live-1234567890abcdef")
    assert llm.client() is None


def test_errors_never_carry_a_key(monkeypatch):
    from chokepoint.agent import llm

    monkeypatch.setenv("LLM_API_KEY", "my-very-own-key-123456")
    text = llm.error_text(RuntimeError("Incorrect API key provided: my-very-own-key-123456 (also gsk_abcdefghijkl, "
                                       "github_pat_ABCDEFGH12345678, sk-proj-abcdefghijklmnop, AIzaSyA1234567890abcdefghij)"))
    for secret in ("my-very-own-key", "gsk_abc", "github_pat_", "sk-proj", "AIzaSy"):
        assert secret not in text, secret


def test_the_mcp_server_process_gets_no_secrets_and_never_imports_from_your_folder(monkeypatch):
    from chokepoint.agent import mcp_agent

    for k in mcp_agent.SECRET_ENV:
        monkeypatch.setenv(k, "secret-value")
    params = mcp_agent._server_params()
    assert not (set(params.env) & mcp_agent.SECRET_ENV)
    assert params.args[:2] == ["-P", "-m"]


def test_background_nightjar_never_imports_from_your_folder():
    from chokepoint.cli import service

    assert service._argv("local:app")[1] == "-P"


def test_local_map_answers_only_on_localhost(monkeypatch):
    from fastapi.testclient import TestClient

    from chokepoint.api import app as A

    monkeypatch.setattr(A, "LOCAL", True)
    c = TestClient(A.app)
    assert c.get("/api/config", headers={"host": "evil.example.com"}).status_code == 403
    assert c.get("/api/config", headers={"host": "127.0.0.1:8899"}).status_code == 200

