"""Fix PR: pin a bad package with an npm `overrides` entry in package.json.

Two users of the same code:
- the website opens PRs only on GITHUB_DEMO_REPO (our sandbox fork), after an explicit confirm click;
- on your machine, `chokepoint fix --pr` and `chokepoint nightjar --pr` open them on YOUR repo, with your own
  fine-grained token from the OS keychain (`chokepoint config github`).
Without a token everything still works as a preview. Nothing here ever merges a PR.
"""

from __future__ import annotations

import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from chokepoint import tools as T

ROOT = Path(__file__).resolve().parents[2]
API = "https://api.github.com"


class PRError(RuntimeError):
    pass


def _demo_repo() -> tuple[str | None, str | None]:
    return os.getenv("GITHUB_DEMO_REPO") or None, os.getenv("GITHUB_TOKEN") or None


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


def _package_json(project: str, folder: str | None = None) -> dict:
    """package.json from the project's folder on this machine (`chokepoint map`), or from GitHub for
    `owner/repo` (main/master) and `owner/repo@commit` (that exact commit)."""
    if folder:
        try:
            return json.loads((Path(folder) / "package.json").read_text())
        except (OSError, ValueError) as e:
            raise PRError(f"couldn't read package.json in {folder}") from e
    repo, _, ref = project.partition("@")
    for branch in ([ref] if ref else ["main", "master"]):
        r = httpx.get(f"https://raw.githubusercontent.com/{repo}/{branch}/package.json", timeout=30)
        if r.status_code == 200:
            return r.json()
    raise PRError(f"couldn't fetch package.json for {project}")


def _with_override(pkg: dict, name: str, bad: str, version: str) -> dict:
    out = dict(pkg)
    out["overrides"] = {**(pkg.get("overrides") or {}), T.override_key(name, bad): version}
    return out


def preview(project: str, key: str, folder: str | None = None) -> dict:
    """Everything the PR would contain, without touching GitHub. `folder`: a project on this machine."""
    explain = T.explain_path(project, key)
    safe = T.safe_version(project, key)
    name, bad, pin = safe["name"], safe["bad"], safe["safe"]
    adv_ids = [a["id"] for a in explain.get("advisories", [])]
    title = f"fix(deps): pin {name} to {pin}" + (f" ({adv_ids[0]})" if adv_ids else "")
    chains = "\n".join(f"- `{' → '.join(p['chain'])}`{'' if p['prod'] else ' (dev only)'}"
                       for p in explain.get("paths", []))
    advisories = "\n".join(
        f"- [{a['id']}](https://osv.dev/vulnerability/{a['id']}) {a['summary']}"
        + (f" (aliases: {', '.join(a['aliases'])})" if a["aliases"] else "")
        for a in explain.get("advisories", [])
    )
    body = (
        f"Chokepoint found **{name}@{bad}** in this project.\n\n"
        f"### How it gets in\n{chains or '- (not currently installed)'}\n\n"
        + (f"### Advisories\n{advisories}\n\n" if advisories else "")
        + f"### Fix\nAdds an npm `overrides` entry `\"{name}@{bad}\": \"{pin}\"`: wherever npm would install "
        f"`{name}@{bad}`, it installs `{pin}` instead, the newest version with no known advisory"
        f"{' that satisfies every declared range' if safe['satisfies_ranges'] else ''}. Other installed versions of "
        f"`{name}` are left alone.\n\n"
        "### After merging: refresh the lockfile\n"
        "This PR changes `package.json` only. `package-lock.json` still lists the old version until npm "
        "re-resolves it, so run this once and commit the result:\n\n"
        "```sh\nnpm install --package-lock-only --ignore-scripts\ngit commit -am \"chore(deps): refresh lockfile\"\n```\n\n"
        f"(`--package-lock-only` rewrites the lockfile without installing anything; `--ignore-scripts` runs no "
        f"package scripts.) Afterwards the lockfile has `{name}@{pin}` wherever it had `{name}@{bad}`.\n\n"
        "_Opened by Chokepoint after an explicit click. The graph decided the fix; no LLM wrote this diff._"
    )
    before = _package_json(project, folder)
    after = _with_override(before, name, bad, pin)
    demo_repo, token = _demo_repo()
    return {
        "project": project, "key": f"{name}@{bad}", "safe": pin, "title": title, "body": body,
        "branch": f"chokepoint/pin-{name.replace('/', '-').lstrip('@')}-{pin}",
        "package_json_before": before, "package_json_after": after,
        "overrides": after["overrides"],
        "can_open": bool(demo_repo and token), "target_repo": demo_repo,
        "summary": f"{title}. {safe['summary']}",
    }


def open_pr(project: str, key: str, visit_note: bool = False) -> dict:
    """The website's button: a fix PR on GITHUB_DEMO_REPO (our sandbox fork). Only after a confirm click."""
    demo_repo, token = _demo_repo()
    if not (demo_repo and token):
        raise PRError("GITHUB_TOKEN and GITHUB_DEMO_REPO must be set in .env to open a PR")
    p = preview(project, key)
    name, bad = p["key"].rsplit("@", 1)
    out = open_override_pr(demo_repo, token, name=name, bad=bad, pin=p["safe"], title=p["title"], body=p["body"],
                           branch=p["branch"])
    if visit_note:
        try:
            out["visit"] = visit_comment(demo_repo, token, out["number"], name=name, bad=bad, pin=p["safe"],
                                         again=out["existing"])
        except (httpx.HTTPError, KeyError, ValueError):  # the PR itself is done; the note is a bonus
            out["visit"] = None
    return out


def visit_comment(repo: str, token: str, number: int, *, name: str, bad: str, pin: str, again: bool,
                  now: datetime | None = None) -> int:
    """Nightjar's note on the website's sandbox PR, one per click: which fix it checked, the visit number and
    the time. Every word is written here, from the graph's answer: nothing a visitor types reaches GitHub."""
    now = now or datetime.now(timezone.utc)
    with httpx.Client(base_url=API, headers=_headers(token), timeout=30) as gh:
        issue = gh.get(f"/repos/{repo}/issues/{number}")
        issue.raise_for_status()
        visit = int(issue.json()["comments"]) + 1
        text = (f"🐦 Nightjar {'re-checked' if again else 'checked'} this fix: {'still ' if again else ''}"
                f"`{name}@{bad}` → `{pin}`, graph unchanged. Opened from the live site · visit {visit} · "
                f"{now:%Y-%m-%d %H:%M} UTC\n\nAnother visitor learned what happened on Sept 8, 2025.")
        gh.post(f"/repos/{repo}/issues/{number}/comments", json={"body": text}).raise_for_status()
    return visit


def open_override_pr(repo: str, token: str, *, name: str, bad: str, pin: str, title: str, body: str, branch: str,
                     path: str = "") -> dict:
    """Branch + one commit (the override in package.json) + PR on `repo`, with the caller's token.
    Used by the website (our sandbox fork), `chokepoint fix --pr` and Nightjar (your own repo).

    The change is always made against the base branch's package.json, so running it again for the same
    fix updates the existing PR (code, title and description) instead of stacking edits or opening a new one.
    It never merges anything. `path`: the folder of package.json inside the repo ("" = the root)."""
    pkg = f"{path.strip('/')}/package.json" if path.strip("/") else "package.json"
    with httpx.Client(base_url=API, headers=_headers(token), timeout=30) as gh:
        info = gh.get(f"/repos/{repo}")
        if info.status_code in (401, 403, 404):
            raise PRError(f"GitHub says {info.status_code} for {repo}: check the repo name and that the token can see it.")
        info.raise_for_status()
        base = info.json()["default_branch"]
        sha = gh.get(f"/repos/{repo}/git/ref/heads/{base}").json()["object"]["sha"]
        r = gh.post(f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": sha})
        if r.status_code not in (201, 422):  # 422 = branch already exists
            r.raise_for_status()
        current = gh.get(f"/repos/{repo}/contents/{pkg}", params={"ref": branch})
        original = gh.get(f"/repos/{repo}/contents/{pkg}", params={"ref": base})
        if original.status_code == 404:
            raise PRError(f"No {pkg} on {repo}'s {base} branch.")
        current.raise_for_status()
        original.raise_for_status()
        doc = json.loads(base64.b64decode(original.json()["content"]))
        new = json.dumps(_with_override(doc, name, bad, pin), indent=2) + "\n"
        gh.put(f"/repos/{repo}/contents/{pkg}", json={
            "message": title, "branch": branch, "sha": current.json()["sha"],
            "content": base64.b64encode(new.encode()).decode(),
        }).raise_for_status()
        pr = gh.post(f"/repos/{repo}/pulls", json={"title": title, "head": branch, "base": base, "body": body})
        if pr.status_code == 422:
            existing = gh.get(f"/repos/{repo}/pulls", params={"head": f"{repo.split('/')[0]}:{branch}", "state": "open"}).json()
            if existing:  # the same fix again: bring its title and description up to date too
                number = existing[0]["number"]
                gh.patch(f"/repos/{repo}/pulls/{number}", json={"title": title, "body": body}).raise_for_status()
                return {"url": existing[0]["html_url"], "number": number, "existing": True}
            msg = "; ".join(e.get("message", "") for e in pr.json().get("errors") or []) or pr.json().get("message", "")
            raise PRError(f"GitHub wouldn't open the PR on {repo}: {msg or 'unprocessable'}.")
        pr.raise_for_status()
        return {"url": pr.json()["html_url"], "number": pr.json()["number"], "existing": False}


def check_access(repo: str, token: str) -> str:
    """Before saving a user's token: it must be a fine-grained token that can write to `repo`.
    A classic token (ghp_…) can reach every repo you own, which is far more than Nightjar needs."""
    if token.startswith(("ghp_", "gho_", "ghu_", "ghs_")):
        raise PRError("That's a classic token, which can reach every repo you own. Create a fine-grained token "
                      "for just this repo instead (it starts with github_pat_).")
    with httpx.Client(base_url=API, headers=_headers(token), timeout=30) as gh:
        info = gh.get(f"/repos/{repo}")
        if info.status_code in (401, 403, 404):
            raise PRError(f"GitHub says {info.status_code} for {repo}: wrong repo name, or the token can't see it.")
        info.raise_for_status()
        if not (info.json().get("permissions") or {}).get("push"):
            raise PRError(f"The token can read {repo} but not write to it: give it Contents and Pull requests "
                          "(read and write).")
        return info.json()["default_branch"]


def nightjar_pr(project: str, name: str, bad: str, pin: str, level: str, publisher: str, at: str,
                reasons: list[str], brief: str | None) -> dict:
    """Title, body and branch for the PR Nightjar opens when it raises an ALERT on your repo."""
    why = "\n".join(f"- {r}" for r in reasons)
    body = (
        f"**Nightjar {level}**: `{name}@{bad}` was published by @{publisher} at {at[11:19]} UTC on {at[:10]}, and "
        f"a fresh install of this project would take it.\n\n"
        f"### Why it raised the alarm\n{why}\n\n"
        + (f"### Nightjar's brief\n{brief}\n\n" if brief else "")
        + f"### The fix\nAdds `\"{name}@{bad}\": \"{pin}\"` to npm `overrides` in package.json: wherever npm would "
        f"install `{name}@{bad}`, it keeps `{pin}`, the version your lockfile already has. Other versions of `{name}` "
        "are left alone. Remove the override once the release is cleared (Nightjar re-checks it against OSV).\n\n"
        "### After merging: refresh the lockfile\n"
        "```sh\nnpm install --package-lock-only --ignore-scripts\ngit commit -am \"chore(deps): refresh lockfile\"\n```\n\n"
        f"_Opened by Nightjar, Chokepoint's watcher agent, for `{project}`. Plain rules decided; nothing was merged._"
    )
    return {"title": f"fix(deps): hold {name} at {pin} ({name}@{bad} flagged by Nightjar)", "body": body,
            "branch": f"nightjar/hold-{name.replace('/', '-').lstrip('@')}-{bad}"}
