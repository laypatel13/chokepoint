"""CLI tests: an embedded FalkorDB in a temp dir, the small example lockfile, no network (enrich=False)."""

import importlib.util
import json
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(importlib.util.find_spec("redislite") is None,
                                reason="embedded FalkorDB (falkordblite, Python 3.12+) not installed")

LOCK = Path(__file__).resolve().parents[2] / "backend" / "tests" / "fixtures" / "example-app" / "package-lock.json"


@pytest.fixture(scope="module")
def cli(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("cli")
    keys = ("CHOKEPOINT_BACKEND", "CHOKEPOINT_DB", "CHOKEPOINT_CACHE")
    saved = {k: os.environ.get(k) for k in keys}
    os.environ.update(CHOKEPOINT_BACKEND="embedded", CHOKEPOINT_DB=str(tmp / "graph.db"),
                      CHOKEPOINT_CACHE=str(tmp / "cache"))
    from typer.testing import CliRunner

    from chokepoint import projects as P
    from chokepoint.cli import state
    from chokepoint.cli.app import app
    from chokepoint.graph.load import load_project

    state.STATE = tmp / "state.json"
    project, lock, folder = P.local_project(LOCK.parent)
    load_project(project, lock, enrich=False)
    state.remember_project(project, str(folder), state.fingerprint(LOCK))
    runner = CliRunner()
    yield lambda *args: runner.invoke(app, list(args))
    for k, v in saved.items():  # don't leak the embedded backend into the other test modules
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_local_project_id():
    from chokepoint import projects as P
    project, lock, _ = P.local_project(LOCK)
    assert project == "local:example-app" and len(lock.packages) == 9


def test_check_installed_exits_1_with_prod_chain(cli):
    r = cli("--json", "check", "debug@4.4.2")
    assert r.exit_code == 1
    data = json.loads(r.stdout)
    assert data["affected"] and data["ships_to_prod"]
    assert data["paths"][0]["chain"] == ["local:example-app", "@babel/core@7.25.2", "debug@4.4.2"]


def test_check_not_installed_exits_0(cli):
    r = cli("--json", "check", "debug@4.4.1")
    assert r.exit_code == 0 and json.loads(r.stdout)["installed_versions"] == ["4.4.2"]


def test_why_lists_every_installed_version(cli):
    data = json.loads(cli("--json", "why", "semver").stdout)
    assert {v["key"] for v in data["versions"]} == {"semver@7.6.3", "semver@6.3.1"}


def test_human_output_shortens_project_and_hints(cli):
    r = cli("check", "debug@4.4.2")
    assert "example-app ─▶ @babel/core@7.25.2 ─▶ debug@4.4.2" in r.stdout  # the CLI draws a bolder arrow
    assert "chokepoint fix debug@4.4.2" in r.stdout


def test_bad_version_is_a_usage_error(cli):
    r = cli("check", "debug")
    assert r.exit_code == 2


def test_unknown_project_is_a_usage_error(cli):
    assert cli("--project", "nope", "who").exit_code == 2


# ---- your projects vs the Sept 8 replay: never mixed --------------------------------------


def test_outside_a_project_never_falls_back_to_the_replay(cli, tmp_path, monkeypatch):
    from chokepoint import incident
    from chokepoint.cli import state

    before = state.load().get("last_project")
    state.save(last_project=incident.REPLAY_PROJECT)  # e.g. an old state file
    monkeypatch.chdir(tmp_path)
    try:
        r = cli("who")
        assert r.exit_code == 2 and "chokepoint replay" in r.stderr
    finally:
        state.save(last_project=before)


def test_inside_the_app_folder_uses_it_without_a_flag(cli, monkeypatch):
    monkeypatch.chdir(LOCK.parent)
    r = cli("--json", "check", "debug@4.4.2")
    assert r.exit_code == 1 and json.loads(r.stdout)["paths"][0]["chain"][0] == "local:example-app"


def test_nightjar_refuses_the_replay(cli):
    from chokepoint import incident
    r = cli("--project", incident.REPLAY_PROJECT, "nightjar", "--once")
    assert r.exit_code == 2 and "chokepoint replay nightjar" in r.stderr


def test_nightjar_needs_a_project_folder(cli, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = cli("nightjar", "--once")
    assert r.exit_code == 2 and "package-lock.json" in r.stderr


def test_same_package_name_in_two_folders_gets_two_ids(cli, tmp_path):
    from chokepoint.cli import state
    assert state.unique_id("local:example-app", LOCK.parent) == "local:example-app"
    other = state.unique_id("local:example-app", tmp_path)
    assert other.startswith("local:example-app-") and other != "local:example-app"


def test_use_refuses_the_replay(cli):
    from chokepoint import incident
    assert cli("use", incident.REPLAY_PROJECT).exit_code == 2


def test_home_screen_without_a_command(cli):
    r = cli()
    assert r.exit_code == 0
    assert "who can poison your app?" in r.stdout and "chokepoint diff" in r.stdout and "chokepoint nightjar" in r.stdout


def test_check_fail_on(cli):
    assert cli("check", "debug@4.4.2", "--fail-on", "never").exit_code == 0
    assert cli("check", "debug@4.4.2", "--fail-on", "prod").exit_code == 1  # it ships to production
    assert cli("check", "debug@4.4.2", "--fail-on", "sometimes").exit_code == 2


def test_diff_compares_rankings_including_teams(monkeypatch):
    from chokepoint import tools as T
    from chokepoint.cli import app as A

    def ranking(rows):
        return {"ranking": rows, "direct": {"direct": 10, "prod": 4}, "cypher": []}
    rankings = {
        "new": ranking([{"maintainer": "qix", "reach": 6, "via": ["a@1"]},
                        {"maintainer": "team1", "reach": 3, "via": ["b@1"], "tied_with": ["team2"]}]),
        "old": ranking([{"maintainer": "qix", "reach": 4, "via": ["a@1"]}, {"maintainer": "gone", "reach": 1, "via": ["c@1"]}]),
    }
    monkeypatch.setattr(T, "chokepoints", lambda project, **_: rankings[project])
    d = A._diff("new", "old")
    assert [a["maintainer"] for a in d["added"]] == ["team1", "team2"]  # a team counts account by account
    assert d["removed"] == ["gone"]
    assert [(a["maintainer"], a["before"], a["reach"]) for a in d["grew"]] == [("qix", 4, 6)]


def test_cypher_is_coloured_by_token():
    from chokepoint.cli.render import HIGHLIGHT, VIOLET, cypher_text
    t = cypher_text("MATCH (p:Project) RETURN p")
    styles = {t.plain[s.start:s.end]: str(s.style) for s in t.spans}
    assert styles["MATCH"] == f"bold {VIOLET}" and styles[":Project"] == HIGHLIGHT


def test_every_command_the_home_screen_lists_exists(cli):
    from chokepoint.cli.app import HOME_COMMANDS
    for cmd, _ in HOME_COMMANDS:
        name = cmd.split()[1]
        r = cli(name, "--help")
        assert r.exit_code == 0, f"`chokepoint {name}` is listed on the home screen but doesn't exist"


def test_fix_prs_only_for_the_app_the_repo_belongs_to(monkeypatch):
    """A repo set up for one app never gets PRs about another app, and the replay never opens or writes anything."""
    import typer

    from chokepoint import incident
    from chokepoint.cli import app as A
    from chokepoint.cli import config as C

    monkeypatch.setattr(C, "github", lambda: {"repo": "me/app-a", "path": "", "project": "local:app-a", "token": "t"})
    assert A.github_for("local:app-a") == ("me/app-a", "t", "")
    for other in ("local:app-b", incident.REPLAY_PROJECT):
        with pytest.raises(typer.Exit):
            A.github_for(other)


def test_github_token_is_never_the_llm_key(monkeypatch):
    from chokepoint.cli import config as C

    monkeypatch.setenv("CHOKEPOINT_LLM_API_KEY", "sk-llm-secret")
    monkeypatch.delenv("CHOKEPOINT_GITHUB_TOKEN", raising=False)
    monkeypatch.setattr(C, "_keychain", lambda name: None)
    assert C.github()["token"] is None


def test_replay_fix_never_writes_or_opens(cli):
    from chokepoint import incident
    for flag in ("--write", "--pr"):  # refused before anything is fetched, built or written
        r = cli("-p", incident.REPLAY_PROJECT, "fix", "debug@4.4.2", flag)
        assert r.exit_code != 0 and "example on webpack-dev-server's history" in r.output
