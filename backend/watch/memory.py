"""The agent's memory, kept in FalkorDB (graph memory:<project>): what it flagged and what it did.
Every query lives in backend/graph/queries.py."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from chokepoint.graph import queries as Q
from chokepoint.graph.db import memory_graph
from chokepoint.watch.signals import Release


class Memory:
    def __init__(self, project: str):
        self.g = memory_graph(project)
        for idx in Q.MEM_INDEXES:
            try:
                self.g.query(idx)
            except Exception:  # index already exists
                pass

    def save_alert(self, r: Release, level: str, points: int, reasons: list[str], replay: bool = False) -> str:
        alert_id = hashlib.sha1(f"{r.key}|{replay}".encode()).hexdigest()[:16]
        self.g.query(Q.MEM_SAVE_ALERT, {
            "id": alert_id, "key": r.key, "name": r.name, "at": r.at, "level": level, "score": points,
            "signals": reasons, "replay": replay, "summary": reasons[0] if reasons else "", "publisher": r.publisher})
        return alert_id

    def decide(self, alert_id: str, action: str, reason: str, replay: bool = False, at: str | None = None) -> None:
        self.g.query(Q.MEM_SAVE_DECISION, {"alert": alert_id, "action": action, "reason": reason, "replay": replay,
                                           "at": at or datetime.now(timezone.utc).isoformat(timespec="seconds")})

    def set_brief(self, alert_id: str, brief: str, by: str) -> None:
        self.g.query(Q.MEM_SET_BRIEF, {"id": alert_id, "brief": brief, "by": by})

    def set_level(self, alert_id: str, level: str) -> None:
        self.g.query(Q.MEM_SET_LEVEL, {"id": alert_id, "level": level})

    def prior_alerts(self, publisher: str, replay: bool = False) -> int:
        rows = self.g.query(Q.MEM_ACCOUNT_HISTORY, {"publisher": publisher, "replay": replay}).result_set
        return rows[0][0] if rows else 0

    def open_alerts(self) -> list[dict]:
        res = self.g.query(Q.MEM_OPEN_ALERTS)
        cols = [c[1] for c in res.header]
        return [dict(zip(cols, row)) for row in res.result_set]

    def recall(self, limit: int = 20, include_replay: bool = True) -> list[dict]:
        res = self.g.query(Q.MEM_RECALL, {"limit": limit, "include_replay": include_replay})
        cols = [c[1] for c in res.header]
        rows = [dict(zip(cols, row)) for row in res.result_set]
        for r in rows:
            r["decisions"] = [d for d in r["decisions"] if d]
        return rows

    def clear_replay(self) -> None:
        self.g.query(Q.MEM_CLEAR_REPLAY)
