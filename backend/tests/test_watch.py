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


def test_act_pins_only_the_bad_version_within_its_major():
    from chokepoint import tools as T
    from chokepoint.watch.signals import Release, action_for, pin_for
    r = Release(name="chalk", version="5.6.1", publisher="qix", at="2025-09-08T13:13:05Z", pinned=["2.4.2", "4.1.2", "5.4.1"])
    assert pin_for(r) == "5.4.1"  # not 2.4.2 or 4.1.2: those serve other majors and stay as they are
    assert "pin chalk to 5.4.1" in action_for("ALERT", r)
    assert T.override_key("chalk", "5.6.1") == "chalk@5.6.1"  # overrides only that version, never every chalk
    assert pin_for(Release(name="x", version="2.0.0", publisher="p", at="", pinned=["1.9.0"])) is None  # no same-major pin
