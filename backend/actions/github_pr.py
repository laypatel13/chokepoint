"""Fix PR: pin a bad package with an npm `overrides` entry in package.json.

Safety: PRs are only ever opened on GITHUB_DEMO_REPO (our own fork), with a
fine-grained token scoped to that repo, and only after an explicit confirm click.
Without a token everything still works as a preview.
"""

from __future__ import annotations

import base64
import json
import os
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


def open_pr(project: str, key: str) -> dict:
    """Create branch + commit + PR on GITHUB_DEMO_REPO. Call only after user confirmation."""
    demo_repo, token = _demo_repo()
    if not (demo_repo and token):
        raise PRError("GITHUB_TOKEN and GITHUB_DEMO_REPO must be set in .env to open a PR")
    p = preview(project, key)
    name, bad, pin = *p["key"].rsplit("@", 1), p["safe"]
    with httpx.Client(base_url=API, headers=_headers(token), timeout=30) as gh:
        repo = gh.get(f"/repos/{demo_repo}")
        repo.raise_for_status()
        base = repo.json()["default_branch"]
        sha = gh.get(f"/repos/{demo_repo}/git/ref/heads/{base}").json()["object"]["sha"]
        r = gh.post(f"/repos/{demo_repo}/git/refs", json={"ref": f"refs/heads/{p['branch']}", "sha": sha})
        if r.status_code not in (201, 422):  # 422 = branch already exists
            r.raise_for_status()
        current = gh.get(f"/repos/{demo_repo}/contents/package.json", params={"ref": p["branch"]})
        current.raise_for_status()
        # The change is always made against the base branch's package.json, so clicking again updates
        # an existing PR to the current fix instead of stacking edits on top of an older one.
        original = gh.get(f"/repos/{demo_repo}/contents/package.json", params={"ref": base})
        original.raise_for_status()
        doc = json.loads(base64.b64decode(original.json()["content"]))
        new = json.dumps(_with_override(doc, name, bad, pin), indent=2) + "\n"
        gh.put(f"/repos/{demo_repo}/contents/package.json", json={
            "message": p["title"], "branch": p["branch"], "sha": current.json()["sha"],
            "content": base64.b64encode(new.encode()).decode(),
        }).raise_for_status()
        pr = gh.post(f"/repos/{demo_repo}/pulls",
                     json={"title": p["title"], "head": p["branch"], "base": base, "body": p["body"]})
        if pr.status_code == 422:
            existing = gh.get(f"/repos/{demo_repo}/pulls",
                              params={"head": f"{demo_repo.split('/')[0]}:{p['branch']}", "state": "open"}).json()
            if existing:  # same fix clicked again: bring its title and description up to date too
                number = existing[0]["number"]
                gh.patch(f"/repos/{demo_repo}/pulls/{number}", json={"title": p["title"], "body": p["body"]}).raise_for_status()
                return {"url": existing[0]["html_url"], "number": number, "existing": True}
        pr.raise_for_status()
        return {"url": pr.json()["html_url"], "number": pr.json()["number"], "existing": False}
