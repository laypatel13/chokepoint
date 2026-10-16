"""The fix-PR flow against a fake GitHub: a new PR, the same fix again (updates, no duplicate), and the
token checks. No network."""

import base64
import json

import httpx
import pytest

from chokepoint.actions import github_pr as G


class FakeGitHub:
    def __init__(self, push=True):
        self.files = {"main": {"name": "app", "dependencies": {"chalk": "^5.3.0"}}}
        self.prs, self.push, self.calls, self.comments = [], push, [], []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path, m = request.url.path, request.method
        self.calls.append((m, path))
        body = json.loads(request.content) if request.content else {}
        if m == "GET" and path == "/repos/me/app":
            return httpx.Response(200, json={"default_branch": "main", "permissions": {"push": self.push}})
        if path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "abc"}})
        if path.endswith("/git/refs"):
            branch = body["ref"].removeprefix("refs/heads/")
            if branch in self.files:
                return httpx.Response(422, json={})
            self.files[branch] = dict(self.files["main"])
            return httpx.Response(201, json={})
        if path.endswith("/contents/package.json"):
            ref = request.url.params.get("ref") or body.get("branch")
            if m == "GET":
                return httpx.Response(200, json={"sha": "s", "content": base64.b64encode(json.dumps(self.files[ref]).encode()).decode()})
            self.files[body["branch"]] = json.loads(base64.b64decode(body["content"]))
            return httpx.Response(200, json={})
        if path.endswith("/pulls") and m == "POST":
            if any(p["head"] == body["head"] for p in self.prs):
                return httpx.Response(422, json={})
            self.prs.append({**body, "number": len(self.prs) + 1, "html_url": f"https://github.com/me/app/pull/{len(self.prs) + 1}"})
            return httpx.Response(201, json=self.prs[-1])
        if path.endswith("/pulls") and m == "GET":
            return httpx.Response(200, json=[p for p in self.prs if f"me:{p['head']}" == request.url.params["head"]
                                             and not p.get("closed")])
        if "/issues/" in path and path.endswith("/comments") and m == "POST":
            self.comments.append(body["body"])
            return httpx.Response(201, json={})
        if "/issues/" in path and m == "GET":
            return httpx.Response(200, json={"comments": len(self.comments)})
        if m == "PATCH":
            pr = self.prs[int(path.rsplit("/", 1)[1]) - 1]
            pr.update(body)
            return httpx.Response(200, json=pr)
        return httpx.Response(404, json={})


@pytest.fixture
def github(monkeypatch):
    fake = FakeGitHub()
    real = httpx.Client
    monkeypatch.setattr(G.httpx, "Client", lambda **kw: real(transport=httpx.MockTransport(fake), **kw))
    return fake


def test_opens_one_pr_with_a_precise_override_and_updates_it_on_repeat(github):
    text = G.nightjar_pr("local:app", "chalk", "5.6.1", "5.4.1", "ALERT", "qix", "2025-09-08T13:13:05Z",
                         ["burst: 3 releases from @qix in 54s"], "brief")
    first = G.open_override_pr("me/app", "github_pat_x", name="chalk", bad="5.6.1", pin="5.4.1", **text)
    assert first == {"url": "https://github.com/me/app/pull/1", "number": 1, "existing": False}
    assert github.files[text["branch"]]["overrides"] == {"chalk@5.6.1": "5.4.1"}  # only the poisoned version
    assert github.files["main"].get("overrides") is None  # nothing touches the base branch
    again = G.open_override_pr("me/app", "github_pat_x", name="chalk", bad="5.6.1", pin="5.4.1",
                               **{**text, "body": "updated"})
    assert again["existing"] and again["number"] == 1 and len(github.prs) == 1 and github.prs[0]["body"] == "updated"
    assert not any(m == "PUT" and "merge" in p for m, p in github.calls)  # never merges


def test_token_checks(github):
    assert G.check_access("me/app", "github_pat_x") == "main"
    with pytest.raises(G.PRError, match="classic token"):
        G.check_access("me/app", "ghp_everything")
    github.push = False
    with pytest.raises(G.PRError, match="not write"):
        G.check_access("me/app", "github_pat_x")


def test_a_closed_pr_gives_a_clear_error_not_a_crash(github):
    """GitHub refuses (422) and no open PR exists to update: a PRError the CLI and API can show."""
    args = dict(name="chalk", bad="5.6.1", pin="5.3.0", title="t", body="b", branch="fix/chalk")
    G.open_override_pr("me/app", "token", **args)
    github.prs[0]["closed"] = True
    with pytest.raises(G.PRError):
        G.open_override_pr("me/app", "token", **args)


def test_nightjar_notes_each_visit_with_only_its_own_words(github):
    from datetime import datetime, timezone
    at = datetime(2026, 10, 19, 11, 2, tzinfo=timezone.utc)
    assert G.visit_comment("me/app", "t", 1, name="debug", bad="4.4.2", pin="4.4.3", again=False, now=at) == 1
    assert G.visit_comment("me/app", "t", 1, name="debug", bad="4.4.2", pin="4.4.3", again=True, now=at) == 2
    first, second = github.comments
    assert first.startswith("🐦 Nightjar checked this fix: `debug@4.4.2` → `4.4.3`")
    assert second.startswith("🐦 Nightjar re-checked this fix: still `debug@4.4.2` → `4.4.3`, graph unchanged.")
    assert "visit 2 · 2026-10-19 11:02 UTC" in second and "#" not in second  # GitHub would link "#2"
    assert second.endswith("Another visitor learned what happened on Sept 8, 2025.")


def test_visit_notes_have_a_daily_cap(monkeypatch):
    from chokepoint.api import limits
    limits.reset()
    monkeypatch.setattr(limits, "VISIT_NOTES_PER_DAY", 2)
    assert [limits.allow_visit_note() for _ in range(3)] == [True, True, False]
    limits.reset()
