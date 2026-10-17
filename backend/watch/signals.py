"""Signals and scoring for a new npm release. Pure functions, shared by the live watcher, the
Sept 8 replay and (later) the web app, so every front end reaches the same verdict.

The watcher does NOT detect malware. It flags risky moments: a new release that a fresh install
would take (inside a declared range), from an account that reaches a lot of the project, with
warning signs around it. Confirmation only ever comes from an advisory (OSV).

Levels:
  INFO       outside every declared range, or nothing notable
  WATCH      inside a range and notable: quarantine it (don't take it on fresh installs yet)
  ALERT      inside a range with strong warning signs: notify, prepare the pin
  CONFIRMED  an OSV malware advisory exists for this exact version
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

BURST_WINDOW_S = 600   # releases from one account within 10 minutes count as a burst
BURST_MIN = 3
HABIT_DAYS = 365       # an account that already burst on these packages this past year: that's its rhythm


@dataclass
class Release:
    name: str
    version: str
    publisher: str
    at: str                                   # ISO time (publish time, or when we saw it)
    ranges_accepting: int = 0                 # declared ranges in the lockfile that accept this version
    ranges_example: str | None = None         # e.g. "^4.1.0 from @babel/core@7.28.3"
    pinned: list[str] = field(default_factory=list)   # what the lockfile pins today (safe to keep)
    reach: int | None = None                  # direct deps the publisher reaches
    reach_rank: int | None = None
    direct_total: int | None = None
    burst: int = 1                            # releases by this publisher inside the burst window
    burst_seconds: int | None = None
    usual_burst: str | None = None            # date of this account's last earlier burst on these packages:
                                              # bursts are its normal rhythm (bots, monorepos), so this one scores 0
    new_install_script: str | None = None     # e.g. "postinstall" (None = no new script / unknown)
    outside_maintainers: bool | None = None   # publisher isn't in the package's maintainer list
    provenance_dropped: bool | None = None    # previous version had provenance, this one hasn't
    trusted_publisher: bool = False           # built and published by the package's own CI (npm trusted publishing)
    prior_alerts: int = 0                     # alerts this account already triggered (agent memory)
    advisory: str | None = None               # OSV malware id, when one exists

    @property
    def key(self) -> str:
        return f"{self.name}@{self.version}"


def score(r: Release) -> tuple[str, int, list[str]]:
    """Returns (level, points, reasons). Each reason is one plain sentence a person can check."""
    pts, why = 0, []
    in_range = r.ranges_accepting > 0
    if in_range:
        pts += 3
        why.append(f"a fresh install would take it: inside {r.ranges_accepting} of your declared ranges"
                   + (f" (e.g. {r.ranges_example})" if r.ranges_example else ""))
    else:
        why.append("outside every declared range in your lockfile")
    if r.reach and r.direct_total:
        big = (r.reach_rank or 99) <= 10 or r.reach / r.direct_total >= 0.2
        if big:
            pts += 1
        why.append(f"@{r.publisher} reaches {r.reach}/{r.direct_total} of your direct dependencies"
                   + (f" (#{r.reach_rank})" if r.reach_rank else ""))
    if r.burst >= BURST_MIN and r.usual_burst:
        why.append(f"burst: {r.burst} releases from @{r.publisher} in {r.burst_seconds}s, its usual rhythm"
                   f" (last burst on these packages: {r.usual_burst})")
    elif r.burst >= BURST_MIN:
        pts += 3
        why.append(f"burst: {r.burst} releases from @{r.publisher} in {r.burst_seconds}s"
                   + (", a first for this account on these packages" if r.usual_burst == "" else ""))
    if r.new_install_script:
        pts += 3
        why.append(f"new install script: {r.new_install_script}")
    if r.outside_maintainers:
        pts += 3
        why.append(f"@{r.publisher} isn't in this package's maintainer list")
    if r.provenance_dropped:
        pts += 2
        why.append("no provenance attestation, though the previous version had one")
    if r.trusted_publisher:
        why.append("published by the package's own CI through npm trusted publishing")
    if r.prior_alerts:
        pts += 1
        why.append(f"@{r.publisher} already triggered {r.prior_alerts} alert(s)")

    if r.advisory:
        return "CONFIRMED", pts, [f"confirmed by {r.advisory}"] + why
    if in_range and pts >= 6:
        return "ALERT", pts, why
    if in_range and pts >= 3:
        return "WATCH", pts, why
    return "INFO", pts, why


def last_burst(times: list[datetime], before: datetime) -> datetime | None:
    """The start of this account's most recent earlier burst (BURST_MIN releases within the window) in the
    HABIT_DAYS before `before`, or None. `times`: when the account published the packages in question."""
    t = sorted(x for x in times if before - timedelta(days=HABIT_DAYS) <= x < before)
    starts = [t[i] for i in range(len(t) - BURST_MIN + 1) if (t[i + BURST_MIN - 1] - t[i]).total_seconds() <= BURST_WINDOW_S]
    return starts[-1] if starts else None


def _ver(v: str) -> list[int]:
    return [int(x) if x.isdigit() else 0 for x in v.split("-")[0].split(".")]


def pin_for(r: Release) -> str | None:
    """The version to stay on instead of r.version: what your lockfile already has in the same major
    (the one a fresh install would replace), never newer than the release itself."""
    same = [v for v in r.pinned or [] if _ver(v)[:1] == _ver(r.version)[:1] and _ver(v) <= _ver(r.version)]
    return max(same, key=_ver) if same else None


def action_for(level: str, r: Release) -> str:
    """The recommended action, in one line (what --act would do)."""
    pins = pin_for(r) or "the version you have"
    return {
        "CONFIRMED": f"pin {r.name} to {pins} (npm overrides) and check whether any install took {r.key}",
        "ALERT": f"quarantine {r.key}: pin {r.name} to {pins} and install only with `npm ci` until it's verified",
        "WATCH": f"hold {r.key} for a few days: install with `npm ci` (lockfile) so it isn't picked up",
        "INFO": "no action needed",
    }[level]
