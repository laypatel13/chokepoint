"""Nightjar's alert brief: what happened, why it matters for this project, what to do.

Two writers, same facts, same verdict:
  template     always available, no LLM: built from the Release the rules scored.
  investigate  with an LLM: Nightjar's analyst. It calls read-only tools through Chokepoint's MCP
               server (at most MAX_TOOL_CALLS) to look further, then writes the brief in plain words.

The rules decide the level and the action; the LLM never changes them, never acts and never writes
Cypher. Any LLM failure (not configured, offline, slow, out of credits) falls back to the template.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time

from chokepoint.watch.signals import Release

MAX_TOOL_CALLS = 3
# Tools the analyst may use: questions about this project only (no listing, no history lesson).
_ALLOWED = {"explain_path", "blast_radius", "chokepoints", "safe_version", "lockfile_saved_you", "investigate",
            "installed_versions", "known_advisories"}

# Small local models sometimes write calls as text, e.g. `explain_path(key="chalk@5.4.1")`.
_TEXT_CALL = re.compile(r"^\W*(\w+)\((.*)\)\W*$")
_TEXT_ARG = re.compile(r"(\w+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([\w.@/^~<>=-]+))")


def text_calls(content: str | None) -> list[tuple[str, dict]]:
    """Tool calls written as text, if every non-empty line is one (else [])."""
    lines = [ln.strip() for ln in (content or "").splitlines() if ln.strip().strip("`")]
    calls = []
    for ln in lines:
        m = _TEXT_CALL.match(ln.strip("`"))
        if not m or m.group(1) not in _ALLOWED:
            return []
        args = {k: next(v for v in vals if v) for k, *vals in _TEXT_ARG.findall(m.group(2))}
        calls.append((m.group(1), {k: int(v) if v.isdigit() else v for k, v in args.items()}))
    return calls


def _looks_like_a_brief(text: str) -> bool:
    return bool(text) and not text_calls(text) and len(re.findall(r"[.!?](\s|$)", text)) >= 2 \
        and not any(f"{t}(" in text for t in _ALLOWED)


SYSTEM = """You are Nightjar, the watch agent of Chokepoint, guarding the npm project "{project}".
A rules engine has already scored a new npm release. Its LEVEL and ACTION are final: you cannot change them.

Your job: investigate, then brief the developer.
1. Call at most {max_calls} tools, only ones that add something the alert doesn't already say. Good questions:
   - which of my direct dependencies pull this package in, and does it ship to production?
     (explain_path or blast_radius on a version the project HAS: see "pinned")
   - what else can this account publish into my project? (chokepoints with maintainer=<publisher>)
   - which version should I keep? (safe_version)
2. Then write the brief, like a colleague tapping the developer on the shoulder: 3 or 4 plain sentences.
   - Sentence 1: what just happened: who published which version, and the warning signs.
   - Then why it matters HERE, with specifics the tools found: which of the developer's direct dependencies
     pull this package in, whether it ships to production, what else this account can publish into the project.
   - Last: the action, as given.
Rules: use only facts from the alert and the tool results. Write npm usernames with @. Never mention the rules
engine, scores or levels. Never call it malware unless an advisory is listed: say "risky release" instead.
No markdown, no headings, no lists."""


def template(r: Release, level: str, action: str) -> str:
    """The brief without an LLM: every sentence comes straight from a scored fact."""
    who = "its own CI (npm trusted publishing)" if r.trusted_publisher else f"@{r.publisher}"
    out = [f"{r.key} was just published by {who}."]
    if r.advisory:
        out.append(f"OSV lists it as malware ({r.advisory}).")
    if r.ranges_accepting:
        eg = f", e.g. {r.ranges_example}" if r.ranges_example else ""
        out.append(f"A fresh `npm install` would take it: {r.ranges_accepting} of your declared ranges accept it{eg}.")
    else:
        out.append("None of your declared ranges accept it, so installs keep the version you have.")
    if r.reach and r.direct_total and not r.trusted_publisher:
        out.append(f"@{r.publisher} can publish into {r.reach} of your {r.direct_total} direct dependencies.")
    signs = []
    if r.burst >= 3:
        signs.append(f"{r.burst} releases from the same account in {r.burst_seconds}s")
    if r.new_install_script:
        signs.append(f"a new `{r.new_install_script}` script")
    if r.outside_maintainers:
        signs.append("a publisher who isn't one of the package's maintainers")
    if r.provenance_dropped:
        signs.append("no provenance, though the previous version had it")
    if r.prior_alerts:
        signs.append(f"{r.prior_alerts} earlier alert(s) on this account")
    if signs:
        out.append("Warning signs: " + "; ".join(signs) + ".")
    if level != "INFO":
        out.append(f"Do: {action}.")
    return " ".join(out)


def _facts(r: Release, level: str, action: str) -> dict:
    return {"release": r.key, "package": r.name, "publisher": r.publisher, "level": level, "action": action,
            "pinned": r.pinned, "ranges_accepting": r.ranges_accepting, "range_example": r.ranges_example,
            "publisher_reach": r.reach, "direct_dependencies": r.direct_total, "burst": r.burst,
            "new_install_script": r.new_install_script, "publisher_outside_maintainers": r.outside_maintainers,
            "provenance_dropped": r.provenance_dropped, "trusted_publishing": r.trusted_publisher,
            "prior_alerts": r.prior_alerts, "advisory": r.advisory}


async def _investigate(project: str, r: Release, level: str, action: str) -> dict:
    from mcp.client.client import Client

    from chokepoint.agent import llm
    from chokepoint.agent.loop import _for_llm
    from chokepoint.agent.mcp_agent import _openai_tools, _result_json
    from chokepoint.mcp_server import mcp as server

    for name in ("", "httpx", "mcp", "nodesemver"):
        logging.getLogger(name).setLevel(logging.WARNING)
    client = llm.client()
    used: list[str] = []
    async with Client(server) as mcp_client:
        tools = [t for t in _openai_tools((await mcp_client.list_tools()).tools) if t["function"]["name"] in _ALLOWED]
        messages = [{"role": "system", "content": SYSTEM.format(project=project, max_calls=MAX_TOOL_CALLS)},
                    {"role": "user", "content": "Alert: " + json.dumps(_facts(r, level, action))}]
        while len(used) < MAX_TOOL_CALLS:
            reply = client.chat.completions.create(model=llm.model(), messages=messages, tools=tools,
                                                   tool_choice="auto", temperature=0, **llm.extra())
            msg = reply.choices[0].message
            calls = (msg.tool_calls or [])[: MAX_TOOL_CALLS - len(used)]
            if not calls:
                written = text_calls(msg.content)[: MAX_TOOL_CALLS - len(used)]
                if not written:
                    if _looks_like_a_brief((msg.content or "").strip()):
                        return {"text": msg.content.strip(), "tools": used}
                    break
                # the model wrote its calls as text: run them for it, hand back the results
                results = []
                for name, args in written:
                    try:
                        results.append(f"{name}: " + _for_llm(_result_json(
                            await mcp_client.call_tool(name, {**args, "project": project}))))
                        used.append(name)
                    except Exception as e:
                        results.append(f"{name}: error {str(e)[:200]}")
                        used.append(f"{name} (failed)")
                messages += [{"role": "assistant", "content": msg.content},
                             {"role": "user", "content": "Tool results:\n" + "\n".join(results)}]
                continue
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [{"id": c.id, "type": "function",
                                             "function": {"name": c.function.name, "arguments": c.function.arguments}}
                                            for c in calls]})
            for c in calls:
                name = c.function.name
                try:
                    if name not in _ALLOWED:
                        raise ValueError(f"{name} isn't available")
                    args = json.loads(c.function.arguments or "{}")
                    result = _for_llm(_result_json(await mcp_client.call_tool(name, {**args, "project": project})))
                    used.append(name)
                except Exception as e:  # a bad argument is the model's problem: tell it, keep going
                    result = json.dumps({"error": str(e)[:200]})
                    used.append(f"{name} (failed)")
                messages.append({"role": "tool", "tool_call_id": c.id, "content": result})
        final = client.chat.completions.create(
            model=llm.model(), temperature=0, max_tokens=260, **llm.extra(),
            messages=messages + [{"role": "user", "content": "Now write the brief."}])
        text = (final.choices[0].message.content or "").strip()
        if not _looks_like_a_brief(text):
            raise ValueError("the model didn't write a usable brief")
        return {"text": text, "tools": used}


def write(project: str, r: Release, level: str, action: str, use_llm: bool = True) -> dict:
    """{'text', 'by' ('template' or the model name), 'tools', 'ms', 'error'}: never raises."""
    from chokepoint.agent import llm

    started = time.perf_counter()
    base = {"text": template(r, level, action), "by": "template", "tools": [], "error": None}
    if not (use_llm and llm.client()):
        return {**base, "ms": 0}
    try:
        got = asyncio.run(_investigate(project, r, level, action))
        return {**base, **got, "by": llm.model(), "ms": round((time.perf_counter() - started) * 1000)}
    except Exception as e:
        return {**base, "error": llm.error_text(e), "ms": round((time.perf_counter() - started) * 1000)}
