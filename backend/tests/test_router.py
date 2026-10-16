from chokepoint.agent.router import route


def test_routes():
    assert route("debug@4.4.2 is malicious. Am I affected?") == ("explain_path", {"key": "debug@4.4.2"})
    assert route("would a fresh npm install have pulled debug@4.4.2?") == ("lockfile_saved_you", {"key": "debug@4.4.2"})
    assert route("what should I pin @babel/core@7.25.2 to? fix it") == ("safe_version", {"key": "@babel/core@7.25.2"})
    assert route("how many packages depend on ms@2.1.3") == ("blast_radius", {"key": "ms@2.1.3"})
    assert route("Who could poison my app?") == ("chokepoints", {})
    assert route("what if qix gets phished tomorrow?") == ("chokepoints", {"maintainer": "qix"})
    assert route("any known malware?") == ("known_advisories", {})
    assert route("how big is this?") == ("graph_stats", {})


def test_malware_only_from_osv_malicious_packages_dataset():
    from chokepoint.ingest.osv import _kind
    assert _kind({"id": "MAL-2025-46974"}) == "malware"
    assert _kind({"id": "GHSA-4x49-vf9v-38px", "aliases": ["CVE-2025-59144", "MAL-2025-46974"]}) == "malware"
    # "malicious" describing the attacker is not malware in the package
    assert _kind({"id": "GHSA-rpmf-866q-6p89", "summary": "basic-ftp allows a malicious FTP server to cause DoS"}) == "vuln"


def test_router_incident_and_installed_versions():
    from chokepoint.agent.router import route
    assert route("what happened to my project on sept 8 2025?") == ("incident", {})
    assert route("which versions of chalk do I have?") == ("installed_versions", {"name": "chalk"})
    assert route("what if @qix gets phished?")[0] == "chokepoints"


def test_investigate_and_recall():
    assert route("investigate chalk@5.6.1") == ("investigate", {"key": "chalk@5.6.1"})
    assert route("tell me everything about debug@4.4.2") == ("investigate", {"key": "debug@4.4.2"})
    assert route("What did Nightjar flag while I was away?") == ("recall", {})
    assert route("any alerts?") == ("recall", {})
    assert route("what happened on Sept 8?") == ("incident", {})
    assert route("who could poison my app?") == ("chokepoints", {})



def test_follow_up_only_fixes_what_is_there():
    from chokepoint.agent.router import follow_up, stop_reason
    q = "is debug@4.4.1 in my app and what do I pin?"
    assert route(q) == ("explain_path", {"key": "debug@4.4.1"})  # check first
    assert follow_up(q, "explain_path", {"key": "debug@4.4.1", "affected": True})[:2] == ("safe_version", {"key": "debug@4.4.1"})
    assert follow_up(q, "explain_path", {"key": "debug@4.4.2", "affected": False}) is None  # not installed: stop
    assert "nothing to pin" in stop_reason(q, "explain_path", {"key": "debug@4.4.2", "affected": False})
    saved = {"name": "chalk", "bad": "5.6.1", "verdict": "saved_by_lockfile"}
    assert follow_up("would a fresh install take chalk@5.6.1? what do I pin?", "lockfile_saved_you", saved)[:2] == ("safe_version", {"key": "chalk@5.6.1"})
    assert follow_up("is debug@4.4.1 in my app?", "explain_path", {"key": "debug@4.4.1", "affected": True}) is None  # no fix asked



def test_llm_latex_arrows_become_plain_arrows():
    from chokepoint.agent.mcp_agent import _plain
    assert _plain("app $\\rightarrow$ spdy@4.0.2 \\to debug") == "app → spdy@4.0.2 → debug"


def test_rate_limits_per_visitor_and_new_pr_cap(monkeypatch):
    import pytest
    from fastapi import HTTPException
    from starlette.requests import Request

    from chokepoint.api import limits

    limits.reset()
    monkeypatch.setitem(limits.LIMITS, "ask", (2, 60))
    monkeypatch.setattr(limits, "TRUSTED_PROXIES", 1)  # as on Render: one proxy appends the real address
    def req(ip):
        return Request({"type": "http", "headers": [(b"x-forwarded-for", ip.encode())], "client": ("10.0.0.1", 1)})
    limits.check(req("1.1.1.1"), "ask")
    limits.check(req("1.1.1.1"), "ask")
    with pytest.raises(HTTPException) as e:
        limits.check(req("1.1.1.1"), "ask")
    assert e.value.status_code == 429
    limits.check(req("2.2.2.2"), "ask")  # another visitor has their own budget

    monkeypatch.setattr(limits, "NEW_PRS_PER_DAY", 1)
    limits.reserve_new_pr()
    limits.release_new_pr()  # the click found an existing PR: the slot comes back
    limits.reserve_new_pr()
    with pytest.raises(HTTPException):
        limits.reserve_new_pr()
    limits.reset()


def test_hosted_prs_only_for_the_replay(monkeypatch):
    from chokepoint.api import app as A
    monkeypatch.setattr(A, "LOCAL", False)
    monkeypatch.setattr(A.github_pr, "_demo_repo", lambda: ("me/webpack-dev-server", "token"))
    assert A._why_no_pr("webpack/webpack-dev-server@fa9195c") is None
    assert "only for the Sept 8 replay" in A._why_no_pr("socketio/socket.io")


def test_hosted_armour(monkeypatch):
    """Attacks on the hosted site: a faked address, a giant body, junk tool args, memory for any name."""
    from fastapi.testclient import TestClient
    from starlette.requests import Request

    from chokepoint.api import app as A
    from chokepoint.api import limits

    monkeypatch.setattr(A, "LOCAL", False)
    monkeypatch.setattr(limits, "TRUSTED_PROXIES", 1)  # as on Render
    # a visitor can't pick their own address: the proxy's entry (last) counts, not the typed one (first)
    req = Request({"type": "http", "client": ("10.0.0.9", 1), "headers": [(b"x-forwarded-for", b"6.6.6.6, 203.0.113.7")]})
    assert limits.visitor(req) == "203.0.113.7"
    client = TestClient(A.app)
    huge = client.post("/api/ask", content=b'{"project":"x","question":"' + b"a" * 100_000 + b'"}',
                       headers={"content-type": "application/json"})
    assert huge.status_code == 413
    junk = client.post("/api/tool/explain_path", json={"project": "x", "args": {"key": "a" * 5000}})
    assert junk.status_code == 422
    assert client.get("/api/memory", params={"project": "anything-at-all"}).status_code == 404  # would create a graph
    assert client.get("/api/health").headers["x-frame-options"] == "DENY"
    assert client.get("/docs").status_code == 404  # no public API explorer on the hosted site


def test_heavy_work_is_capped(monkeypatch):
    import threading

    import pytest
    from fastapi import HTTPException

    from chokepoint.api import limits
    monkeypatch.setattr(limits, "_heavy", threading.BoundedSemaphore(1))
    with limits.heavy():
        monkeypatch.setattr(limits._heavy, "acquire", lambda timeout: False)  # still busy after waiting
        with pytest.raises(HTTPException) as e:
            limits.heavy().__enter__()
        assert e.value.status_code == 503


def test_no_proxy_ignores_forwarded_for(monkeypatch):
    """Without a proxy in front, X-Forwarded-For is the visitor's own words: a fresh value per request
    must not buy a fresh rate-limit budget."""
    from starlette.requests import Request

    from chokepoint.api import limits
    monkeypatch.setattr(limits, "TRUSTED_PROXIES", 0)
    fake = Request({"type": "http", "headers": [(b"x-forwarded-for", b"6.6.6.6")], "client": ("10.0.0.9", 1)})
    assert limits.visitor(fake) == "10.0.0.9"


def test_behind_a_cdn_the_cdn_header_names_the_visitor(monkeypatch):
    """Render: Cloudflare -> Render's proxy -> app. The last X-Forwarded-For entry is a Cloudflare server
    (a new one per request); CF-Connecting-IP is the visitor."""
    from starlette.requests import Request

    from chokepoint.api import limits
    monkeypatch.setattr(limits, "TRUSTED_PROXIES", 1)
    monkeypatch.setattr(limits, "CLIENT_IP_HEADER", "cf-connecting-ip")
    req = Request({"type": "http", "client": ("10.0.0.9", 1), "headers": [
        (b"x-forwarded-for", b"6.6.6.6, 203.0.113.7, 172.70.1.1"), (b"cf-connecting-ip", b"203.0.113.7")]})
    assert limits.visitor(req) == "203.0.113.7"
