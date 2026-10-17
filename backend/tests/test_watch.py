"""Watcher: scoring rules (pure) and the Sept 8 replay on the real seeded project."""

import pytest

from chokepoint.watch.signals import Release, action_for, score


def rel(**kw):
    base = dict(name="debug", version="4.4.2", publisher="qix", at="2025-09-08T13:12:39Z")
    return Release(**{**base, **kw})


def test_outside_every_range_is_info():
    level, _, why = score(rel(ranges_accepting=0, reach=43, reach_rank=1, direct_total=90, burst=5))
    assert level == "INFO" and "outside every declared range" in why[0]


def test_in_range_from_big_account_is_watch():
    level, pts, _ = score(rel(ranges_accepting=29, reach=43, reach_rank=1, direct_total=90))
    assert (level, pts) == ("WATCH", 4)


def test_burst_inside_range_is_alert():
    level, _, why = score(rel(ranges_accepting=6, reach=43, reach_rank=1, direct_total=90, burst=3, burst_seconds=54))
    assert level == "ALERT" and any("burst: 3 releases" in w for w in why)


def test_new_install_script_or_foreign_publisher_alerts_alone():
    assert score(rel(ranges_accepting=1, new_install_script="postinstall"))[0] == "ALERT"
    assert score(rel(ranges_accepting=1, outside_maintainers=True))[0] == "ALERT"


def test_trusted_publishing_ci_is_not_a_foreign_publisher():
    # Real case: eslint-plugin-jsdoc@65.3.3, published as "GitHub Actions" via OIDC, maintainer gajus.
    level, pts, why = score(rel(name="eslint-plugin-jsdoc", version="65.3.3", publisher="GitHub Actions",
                                ranges_accepting=1, outside_maintainers=None, trusted_publisher=True))
    assert (level, pts) == ("WATCH", 3) and not any("maintainer list" in w for w in why)


def test_a_burst_that_is_the_accounts_usual_rhythm_scores_nothing_but_is_still_shown():
    # Real case: the @types bot releases @types/node 18 and 20 together every week.
    level, pts, why = score(rel(name="@types/node", version="20.19.11", publisher="types", ranges_accepting=3,
                                reach=43, reach_rank=1, direct_total=90, burst=3, burst_seconds=5,
                                usual_burst="2025-08-08"))
    assert (level, pts) == ("WATCH", 4)
    assert any("its usual rhythm (last burst on these packages: 2025-08-08)" in w for w in why)


def test_a_first_ever_burst_still_alerts_and_says_so():
    # Sept 8: @qix had never published three packages at once.
    level, _, why = score(rel(name="chalk", version="5.6.1", ranges_accepting=6, reach=43, reach_rank=1,
                              direct_total=90, burst=3, burst_seconds=54, usual_burst=""))
    assert level == "ALERT" and any("a first for this account on these packages" in w for w in why)


def test_last_burst_finds_only_real_bursts_in_the_past_year():
    from datetime import datetime, timedelta, timezone

    from chokepoint.watch.signals import last_burst
    t0 = datetime(2025, 9, 8, 13, 12, tzinfo=timezone.utc)
    spread = [t0 - timedelta(days=d) for d in (3, 40, 90)]                         # one release at a time
    old = [t0 - timedelta(days=400, seconds=s) for s in (0, 60, 120)]              # a burst, but over a year ago
    assert last_burst(spread + old, before=t0) is None
    weekly = [t0 - timedelta(days=7, seconds=s) for s in (0, 5, 30)]               # a bot's weekly burst
    assert last_burst(spread + weekly, before=t0) == t0 - timedelta(days=7, seconds=30)


def test_a_burst_never_counts_as_its_own_habit():
    """npm already lists the burst's own releases (some maybe not polled yet): only earlier bursts count."""
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace

    from chokepoint.watch.agent import Watcher
    t0 = datetime(2025, 9, 8, 13, 13, 5, tzinfo=timezone.utc)
    burst = [("qix", t0 - timedelta(seconds=26), "debug@4.4.2"), ("qix", t0, "chalk@5.6.1"),
             ("qix", t0 + timedelta(seconds=20), "ansi-styles@6.2.2")]
    now_on_npm = [(t0 - timedelta(seconds=55), "ansi-regex@6.2.1", "qix"),   # same burst, not polled yet
                  (t0 - timedelta(seconds=26), "debug@4.4.2", "qix"), (t0, "chalk@5.6.1", "qix"),
                  (t0 + timedelta(seconds=20), "ansi-styles@6.2.2", "qix"),
                  (t0 - timedelta(days=120), "debug@4.4.1", "qix")]
    me = SimpleNamespace(feed=SimpleNamespace(history=lambda names: now_on_npm))
    assert Watcher._usual_burst(me, "qix", burst) == ""
    weekly = [(t0 - timedelta(days=7, seconds=s), f"debug@4.3.{s}", "qix") for s in (0, 5, 30)]
    me.feed.history = lambda names: now_on_npm + weekly
    assert Watcher._usual_burst(me, "qix", burst) == (t0 - timedelta(days=7)).date().isoformat()


def test_trusted_publishing_counts_without_a_provenance_attestation():
    """Real case: Babel publishes through npm trusted publishing (OIDC) without provenance."""
    import asyncio
    import tempfile
    from pathlib import Path

    import httpx

    from chokepoint.watch.feed import Feed
    user = {"name": "GitHub Actions", "trustedPublisher": {"id": "github"}}
    docs = {"/@babel%2Ftypes/7.28.5": {"_npmUser": user, "dist": {}, "maintainers": [{"name": "nicolo-ribaudo"}]},
            "/@babel%2Ftypes/7.28.4": {"_npmUser": {"name": "nicolo-ribaudo"}, "dist": {}}}
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=docs[req.url.raw_path.decode()]))

    async def run():
        async with httpx.AsyncClient(transport=transport, base_url="https://registry.npmjs.org") as c:
            return await Feed(Path(tempfile.mkdtemp()) / "s.sqlite")._details(
                c, asyncio.Semaphore(1), "@babel/types", "7.28.5", "7.28.4")
    nv = asyncio.run(run())
    assert nv.trusted_publisher and not nv.provenance


def test_advisory_confirms_and_action_pins_what_you_have():
    r = rel(ranges_accepting=29, advisory="MAL-2025-46974", pinned=["4.4.1"])
    level, _, why = score(r)
    assert level == "CONFIRMED" and why[0] == "confirmed by MAL-2025-46974"
    assert "pin debug to 4.4.1" in action_for(level, r)


def test_rules_only_brief_states_the_facts_and_the_action():
    from chokepoint.watch.brief import template
    r = rel(name="chalk", version="5.6.1", ranges_accepting=6, ranges_example="^5.3.0 from x@1.0.0", pinned=["5.4.1"],
            reach=43, direct_total=90, burst=3, burst_seconds=54)
    text = template(r, "ALERT", action_for("ALERT", r))
    assert text.startswith("chalk@5.6.1 was just published by @qix.")
    assert "6 of your declared ranges" in text and "43 of your 90" in text and "3 releases" in text
    assert "pin chalk to 5.4.1" in text and "malware" not in text


def test_tool_calls_written_as_text_are_recognised_not_shown():
    from chokepoint.watch.brief import _looks_like_a_brief, text_calls
    written = 'blast_radius(key="chalk@5.6.1")\nchokepoints(maintainer="qix")'
    assert text_calls(written) == [("blast_radius", {"key": "chalk@5.6.1"}), ("chokepoints", {"maintainer": "qix"})]
    assert not _looks_like_a_brief(written)
    assert text_calls("Run rm(-rf)") == []  # only our read-only tools, only whole lines
    assert _looks_like_a_brief("@qix published chalk@5.6.1 in a burst. Pin chalk to 5.4.1.")


def _seeded(project):
    try:
        from chokepoint import tools as T
        return any(p["repo"] == project for p in T.list_projects())
    except Exception:
        return False


RP = "webpack/webpack-dev-server@fa9195c"


@pytest.mark.skipif(not _seeded(RP), reason="FalkorDB with the seeded replay project not available")
def test_replay_alerts_74_minutes_before_the_first_advisory():
    from chokepoint.watch import replay
    r = replay.run(RP, remember=False)
    assert r["first_alert"]["key"] == "chalk@5.6.1" and r["first_alert"]["at"].startswith("2025-09-08T13:13:05")
    assert r["first_advisory"]["advisory"] == "MAL-2025-46974"
    assert r["lead_minutes"] == 74
    releases = [x for x in r["timeline"] if x["kind"] == "release"]
    assert all(x["publisher"] == "qix" for x in releases)
    assert {x["key"]: x["level"] for x in releases}["supports-color@10.2.1"] == "INFO"  # outside every range


@pytest.mark.skipif(not _seeded(RP), reason="FalkorDB with the seeded replay project not available")
def test_website_replay_scores_like_the_cli_replay():
    """The website runs the replay without memory; it must still reach the CLI's verdicts."""
    from chokepoint.watch import replay
    web, cli = replay.run(RP, remember=False), replay.run(RP, remember=True)
    levels = lambda r: [(x["key"], x["level"], x["score"]) for x in r["timeline"] if x["kind"] == "release"]  # noqa: E731
    assert levels(web) == levels(cli) and web["lead_minutes"] == cli["lead_minutes"]


def test_cache_entries_expire(tmp_path, monkeypatch):
    import os
    import time

    from chokepoint.ingest import cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(cache, "FOREVER", False)
    cache.put("npm", "debug", {"latest": "4.4.1"})
    assert cache.get("npm", "debug", max_age=60) == {"latest": "4.4.1"}
    old = time.time() - 120
    os.utime(cache._path("npm", "debug"), (old, old))
    assert cache.get("npm", "debug", max_age=60) is None
    assert cache.get("npm", "debug") == {"latest": "4.4.1"}  # still there as a fallback when npm is down


def test_cache_survives_writers_racing_on_one_entry(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from chokepoint.ingest import cache
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    with ThreadPoolExecutor(8) as pool:
        list(pool.map(lambda i: cache.put("osv-q", "debug@4.4.1", [i]), range(200)))
    assert cache.get("osv-q", "debug@4.4.1") in ([i] for i in range(200))
    assert not list(tmp_path.rglob("*.tmp"))  # no temp files left behind


def test_act_pins_only_the_bad_version_within_its_major():
    from chokepoint import tools as T
    from chokepoint.watch.signals import Release, action_for, pin_for
    r = Release(name="chalk", version="5.6.1", publisher="qix", at="2025-09-08T13:13:05Z", pinned=["2.4.2", "4.1.2", "5.4.1"])
    assert pin_for(r) == "5.4.1"  # not 2.4.2 or 4.1.2: those serve other majors and stay as they are
    assert "pin chalk to 5.4.1" in action_for("ALERT", r)
    assert T.override_key("chalk", "5.6.1") == "chalk@5.6.1"  # overrides only that version, never every chalk
    assert pin_for(Release(name="x", version="2.0.0", publisher="p", at="", pinned=["1.9.0"])) is None  # no same-major pin
