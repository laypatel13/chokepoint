import { useEffect, useState } from "react";
import { post } from "../../lib/api";
import type { FixPreview as Preview, Project, PullRequest } from "../../lib/types";
import { CopyCommand } from "./CopyCommand";
import { Arrow } from "../../components/Arrow";

type Load = { kind: "loading" } | { kind: "error"; text: string } | { kind: "ready"; preview: Preview };

/** The fix for one version. On the website: a pull request on our demo fork, opened only after
 * two explicit clicks. In `chokepoint map`: the commands to apply it on your machine. */
export function FixPreview({ fixKey, project, local }: { fixKey: string; project: Project | undefined; local: boolean }) {
  // Rendered with key={fixKey}: a different fix is a fresh component, so it starts loading.
  const [load, setLoad] = useState<Load>({ kind: "loading" });
  useEffect(() => {
    let current = true;
    post<Preview>("/api/fix/preview", { project: project?.repo, key: fixKey })
      .then((preview) => { if (current) setLoad({ kind: "ready", preview }); })
      .catch((e: Error) => { if (current) setLoad({ kind: "error", text: e.message }); });
    return () => { current = false; };
  }, [fixKey, project?.repo]);

  if (load.kind === "loading") return <p className="muted"><span className="spin" />Building the fix…</p>;
  if (load.kind === "error") return <p className="err">{load.text}</p>;
  const p = load.preview;
  const overrides = <pre className="code">{JSON.stringify({ overrides: p.overrides }, null, 2)}</pre>;

  if (local) {
    return (
      <div className="pr">
        <div className="title">{p.title}</div>
        <div className="muted">package.json gets:</div>
        {overrides}
        {project?.folder ? (
          <>
            <div className="muted">Apply it on this machine:</div>
            <div className="row">
              <CopyCommand command={`cd "${project.folder_short}" && chokepoint fix ${fixKey} --write`} />
              <CopyCommand command="npm install" />
            </div>
          </>
        ) : <div className="muted">This project has no local folder (the replay, or a GitHub scan): copy the override into your package.json.</div>}
      </div>
    );
  }
  return (
    <div className="pr">
      <div className="title">{p.title}</div>
      <div className="muted">branch <code>{p.branch}</code> · package.json gets:</div>
      {overrides}
      <details><summary className="muted">PR body</summary><pre className="code">{p.body}</pre></details>
      <OpenPr preview={p} project={project?.repo} fixKey={fixKey} />
    </div>
  );
}

/** First click arms, second click opens the PR (never one click). */
function OpenPr({ preview, project, fixKey }: { preview: Preview; project?: string; fixKey: string }) {
  const [armed, setArmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ pr?: PullRequest; error?: string }>({});
  const open = async () => {
    if (!armed) { setArmed(true); return; }
    setBusy(true);
    try {
      setResult({ pr: await post<PullRequest>("/api/fix/open", { project, key: fixKey, confirm: true }) });
    } catch (e) { setResult({ error: (e as Error).message }); }
  };
  return (
    <>
      <div className="pr-actions">
        {preview.target_repo && preview.can_open && (
          <div className="pr-target muted">on <code>{preview.target_repo}</code>, our sandbox fork</div>
        )}
        <div className="pr-buttons">
          <button className="btn danger" id="open-pr" disabled={!preview.can_open || busy} onClick={open}>
            {busy ? "Opening…" : armed ? "Confirm: open the PR" : "Open PR"}
          </button>
          {armed && !busy && !result.pr && <button className="btn" onClick={() => setArmed(false)}>Cancel</button>}
        </div>
        {!preview.can_open && <p className="muted pr-why">{preview.why_not ?? "Opening PRs is switched off on this server."}</p>}
      </div>
      <div id="pr-result">
        {result.pr && <a href={result.pr.url} target="_blank" rel="noopener">PR #{result.pr.number} {result.pr.existing ? "(already open)" : "opened"} <Arrow /></a>}
        {result.error && <p className="err">{result.error}</p>}
      </div>
    </>
  );
}
