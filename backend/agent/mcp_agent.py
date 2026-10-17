"""The agent, with tool selection through MCP (Track 01: "tool selection through MCP").

    question ─► MCP list_tools ─► LLM picks one ─► MCP call_tool ─► FalkorDB ─► LLM words the JSON

The agent never imports the tools directly: it is an MCP client of Chokepoint's own MCP server, so the
LLM chooses from exactly the tool list any other MCP client (Claude Desktop, Cursor) would see.
The transport is in-memory by default (same process, real MCP protocol); `stdio=True` spawns
`chokepoint mcp` as a separate process instead.

Rules unchanged from the web agent: the graph decides, the LLM only picks and words; at most 2 LLM calls;
no LLM (or any LLM failure) falls back to the keyword router and the tool's own summary.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from chokepoint.agent import llm, prompts

# Secrets a child process never needs.
SECRET_ENV = {"LLM_API_KEY", "CHOKEPOINT_LLM_API_KEY", "CHOKEPOINT_GITHUB_TOKEN", "GITHUB_TOKEN"}
from chokepoint.agent.loop import _for_llm
from chokepoint.agent.router import follow_up, route, stop_reason

log = logging.getLogger(__name__)

# Tools that need no question-specific input or aren't questions; the agent doesn't offer them.
_HIDDEN = {"list_projects"}


def _openai_tools(mcp_tools) -> list[dict]:
    """MCP tool list -> OpenAI function-calling list, with `project` removed (the agent fills it in)."""
    out = []
    for t in mcp_tools:
        if t.name in _HIDDEN:
            continue
        schema = dict(t.input_schema or {"type": "object", "properties": {}})
        props = {k: v for k, v in (schema.get("properties") or {}).items() if k != "project"}
        required = [r for r in schema.get("required", []) if r != "project"]
        out.append({"type": "function", "function": {
            "name": t.name, "description": (t.description or "").strip(),
            "parameters": {"type": "object", "properties": props, "required": required}}})
    return out


def _result_json(res) -> dict:
    if getattr(res, "is_error", False):
        text = " ".join(getattr(c, "text", "") for c in res.content)
        raise ValueError(text or "tool error")
    for c in res.content:
        text = getattr(c, "text", None)
        if text:
            return json.loads(text)
    raise ValueError("empty tool result")


# Small local models sometimes write arrows as LaTeX ($\rightarrow$, \to). The answer is plain text.
_LATEX_ARROW = re.compile(r"\$?\\(?:rightarrow|to|longrightarrow|Rightarrow)\$?")


def _plain(text: str) -> str:
    return _LATEX_ARROW.sub("→", text).strip()


def _server_params():
    import os
    import sys

    from mcp.client.stdio import StdioServerParameters

    # the server process must use the same graph backend and data as this one
    # The server only needs the graph settings: your LLM key and GitHub token stay out of its environment.
    # -P: don't put the current folder on the import path, or a file named httpx.py in a cloned repo would run.
    env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
    env["CHOKEPOINT_MCP_HIGHLIGHT"] = "1"  # this agent draws the answer on the graph: keep what to light up
    return StdioServerParameters(command=sys.executable, args=["-P", "-m", "chokepoint.mcp_server"], env=env)


async def ask_async(project: str, question: str, stdio: bool = False, use_llm: bool = True) -> dict[str, Any]:
    from mcp.client.client import Client

    from chokepoint import mcp_server
    from chokepoint.mcp_server import mcp as server

    mcp_server.KEEP_HIGHLIGHT = True  # in-process: this agent draws the answer on the graph

    for name in ("", "httpx", "mcp", "nodesemver"):  # the MCP server sets up chatty logging; keep the terminal clean
        logging.getLogger(name).setLevel(logging.WARNING)
    started = time.perf_counter()
    out: dict[str, Any] = {"question": question, "mode": "template", "llm_error": None,
                           "transport": "stdio" if stdio else "in-memory", "via": "mcp"}
    client = llm.client() if use_llm else None
    async with Client(_server_params() if stdio else server) as mcp_client:
        listed = await mcp_client.list_tools()
        tools = _openai_tools(listed.tools)
        out["tools_offered"] = [t["function"]["name"] for t in tools]
        names = set(out["tools_offered"])
        tool, args = None, {}

        if client:
            try:
                r = client.chat.completions.create(
                    model=llm.model(),
                    messages=[{"role": "system", "content": prompts.SYSTEM_PICK.format(project=project)},
                              {"role": "user", "content": question}],
                    tools=tools, tool_choice="auto", temperature=0, **llm.extra())
                calls = r.choices[0].message.tool_calls or []
                if calls and calls[0].function.name in names:
                    tool, args = calls[0].function.name, json.loads(calls[0].function.arguments or "{}")
            except Exception as e:  # 429, timeout, model without tool calling: degrade, never fail
                out["llm_error"] = llm.error_text(e)
                log.warning("LLM tool pick failed: %s", e)

        out["routed_by"] = "llm" if tool else "rules"
        if tool is None:
            tool, args = route(question)

        async def call(name: str, arguments: dict) -> dict:
            return _result_json(await mcp_client.call_tool(name, {"project": project, **arguments}))

        try:
            result = await call(tool, args)
        except Exception:
            if out["routed_by"] != "llm":
                raise
            tool, args = route(question)  # the LLM's arguments didn't work: use the rules router
            out["routed_by"] = "rules"
            result = await call(tool, args)

        # Look at what the graph returned, then decide whether one more step is needed (at most one).
        steps = [{"tool": tool, "args": args, "summary": result.get("summary", ""), "why": "answer the question"}]
        nxt = follow_up(question, tool, result)
        if nxt:
            tool2, args2, why = nxt
            try:
                second = await call(tool2, args2)
                steps.append({"tool": tool2, "args": args2, "summary": second.get("summary", ""), "why": why, "result": second})
            except Exception as e:  # the first answer still stands
                log.warning("follow-up %s failed: %s", tool2, e)
        out["steps"] = steps
        out["stopped"] = None if nxt else stop_reason(question, tool, result)

    answer = None
    if client and out["llm_error"] is None:
        try:
            r = client.chat.completions.create(
                model=llm.model(),
                messages=[{"role": "system", "content": prompts.SYSTEM_EXPLAIN},
                          {"role": "user", "content": f"Question: {question}\n" + "\n".join(
                              f"Step {i}: tool {s['tool']}\nTool result JSON: {_for_llm(s.get('result', result))}"
                              for i, s in enumerate(steps, 1))}],
                temperature=0, max_tokens=900, **llm.extra())
            # Cut off by the token limit (thinking counts too): the graph's own summary instead of half a sentence.
            answer = None if r.choices[0].finish_reason == "length" else _plain(r.choices[0].message.content or "") or None
            if answer:
                out["mode"] = "llm"
        except Exception as e:
            out["llm_error"] = llm.error_text(e)

    plain = " ".join(s["summary"] for s in steps) + (f" {out['stopped']}" if out.get("stopped") else "")
    out.update(tool=tool, args=args, answer=answer or plain, result=result,
               ms=round((time.perf_counter() - started) * 1000))
    return out


def ask(project: str, question: str, stdio: bool = False, use_llm: bool = True) -> dict[str, Any]:
    return asyncio.run(ask_async(project, question, stdio=stdio, use_llm=use_llm))
