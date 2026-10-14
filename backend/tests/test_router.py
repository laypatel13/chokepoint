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
