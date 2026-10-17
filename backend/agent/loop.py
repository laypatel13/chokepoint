"""Question -> one graph tool -> plain-English answer.

The LLM only translates: it picks a tool (function calling) and rephrases the tool's
JSON. The graph decides the answer. Any LLM failure (no key, 429, timeout, bad tool
call) falls back to the deterministic router + the tool's own templated summary.
Budget: at most 2 LLM calls per question.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from chokepoint import tools as T
from chokepoint.agent import llm, prompts
from chokepoint.agent.router import route

log = logging.getLogger(__name__)

_KEY = {"type": "string", "description": "exact package version, name@version, e.g. debug@4.4.2"}
TOOL_SCHEMAS: dict[str, dict] = {
    "explain_path": {"description": "Is this exact version installed, through which dependency chain, and does it ship to production?",
                     "properties": {"key": _KEY}, "required": ["key"]},
    "blast_radius": {"description": "Which direct dependencies pull in this version and how many packages depend on it.",
                     "properties": {"key": _KEY}, "required": ["key"]},
    "lockfile_saved_you": {"description": "Would a fresh npm install have pulled this (bad) version, or did the lockfile protect the project?",
                           "properties": {"key": _KEY}, "required": ["key"]},
    "safe_version": {"description": "Nearest version with no known advisory that satisfies the declared ranges.",
                     "properties": {"key": _KEY}, "required": ["key"]},
    "chokepoints": {"description": "Rank npm maintainer accounts by how much of the project they could poison if phished.",
                    "properties": {"maintainer": {"type": "string", "description": "optional npm username to focus on"},
                                   "by": {"type": "string", "enum": ["reach", "prod"],
                                          "description": "rank by all direct dependencies (reach, default) or production ones first (prod)"}},
                    "required": []},
    "known_advisories": {"description": "All known OSV advisories (vulnerabilities and malware) hitting the project.",
                         "properties": {}, "required": []},
    "graph_stats": {"description": "Size of the project's dependency graph.", "properties": {}, "required": []},
    "incident": {"description": "History only: what happened in this project during the npm attack of Sept 8, 2025.",
                 "properties": {}, "required": []},
    "investigate": {"description": "Everything about one version in one call: path, fresh-install risk, fix and publishers.",
                    "properties": {"key": {"type": "string", "description": "name@version, e.g. debug@4.4.2"}},
                    "required": ["key"]},
    "recall": {"description": "What Nightjar, the watcher agent, flagged in this project and what it decided.",
               "properties": {}, "required": []},
    "installed_versions": {"description": "Every installed version of a package, by name.",
                           "properties": {"name": {"type": "string", "description": "package name, e.g. debug"}},
                           "required": ["name"]},
}
OPENAI_TOOLS = [
    {"type": "function", "function": {"name": n, "description": s["description"],
     "parameters": {"type": "object", "properties": s["properties"], "required": s["required"]}}}
    for n, s in TOOL_SCHEMAS.items()
]

_cache: dict[tuple[str, str], dict] = {}


def run_tool(project: str, name: str, args: dict) -> dict:
    allowed = set(TOOL_SCHEMAS[name]["properties"])
    return T.TOOLS[name](project, **{k: v for k, v in args.items() if k in allowed and v not in (None, "")})


def _for_llm(result: dict) -> str:
    slim = {k: v for k, v in result.items() if k not in ("highlight", "cypher", "controlled")}
    for k in ("ranking", "requirements", "advisories", "paths"):
        if isinstance(slim.get(k), list):
            slim[k] = slim[k][:5]
    if isinstance(slim.get("ranking"), list):  # no package lists; a team of tied accounts becomes a count
        slim["ranking"] = [{**{k: v for k, v in r.items() if k not in ("via", "tied_with")},
                            **({"tied_accounts": len(r["tied_with"])} if r.get("tied_with") else {})} for r in slim["ranking"]]
    if isinstance(slim.get("alerts"), list):  # Nightjar's memory: the facts per release, so every one fits
        slim["alerts"] = [{k: a.get(k) for k in ("key", "level", "at", "publisher")} for a in slim["alerts"]]
    return json.dumps(slim, default=str)[:4000]


def ask(project: str, question: str) -> dict[str, Any]:
    cache_key = (project, question.strip().lower())
    if cache_key in _cache:
        return {**_cache[cache_key], "cached": True}

    started = time.perf_counter()
    out: dict[str, Any] = {"question": question, "mode": "template", "llm_error": None}
    client = llm.client()
    tool, args, answer = None, {}, None

    if client:
        try:
            r = client.chat.completions.create(
                model=llm.model(),
                messages=[{"role": "system", "content": prompts.SYSTEM_PICK.format(project=project)},
                          {"role": "user", "content": question}],
                tools=OPENAI_TOOLS, tool_choice="auto", temperature=0, **llm.extra(),
            )
            calls = r.choices[0].message.tool_calls or []
            if calls and calls[0].function.name in TOOL_SCHEMAS:
                tool = calls[0].function.name
                args = json.loads(calls[0].function.arguments or "{}")
        except Exception as e:  # 429, timeout, provider down: degrade, never error
            out["llm_error"] = llm.error_text(e)
            log.warning("LLM tool pick failed: %s", e)

    if tool is None:
        tool, args = route(question)
        out["routed_by"] = "rules"
    else:
        out["routed_by"] = "llm"

    try:
        result = run_tool(project, tool, args)
    except (T.ToolError, TypeError) as e:
        if out["routed_by"] == "llm":  # LLM gave bad args; retry with the rules router
            tool, args = route(question)
            out["routed_by"] = "rules"
            result = run_tool(project, tool, args)
        else:
            raise e

    if client and out["llm_error"] is None:
        try:
            r = client.chat.completions.create(
                model=llm.model(),
                messages=[{"role": "system", "content": prompts.SYSTEM_EXPLAIN},
                          {"role": "user", "content": f"Question: {question}\nTool: {tool}\nTool result JSON: {_for_llm(result)}"}],
                temperature=0, max_tokens=900, **llm.extra(),
            )
            # Cut off by the token limit (thinking counts too): the graph's own summary instead of half a sentence.
            answer = None if r.choices[0].finish_reason == "length" else (r.choices[0].message.content or "").strip() or None
            if answer:
                out["mode"] = "llm"
        except Exception as e:
            out["llm_error"] = llm.error_text(e)
            log.warning("LLM explain failed: %s", e)

    out.update(tool=tool, args=args, answer=answer or result["summary"], result=result,
               ms=round((time.perf_counter() - started) * 1000))
    _cache[cache_key] = out
    return out
