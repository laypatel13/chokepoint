import { niceDate, shown } from "../../lib/format";
import { advanceRing } from "../../lib/ring";
import type { Project } from "../../lib/types";

interface Group { label: string; projects: Project[]; name: (p: Project) => string }

const replayName = (p: Project) => `${p.repo.split("@")[0]} · lockfile of ${niceDate(p.as_of)}`;

function groups(projects: Project[], local: boolean): Group[] {
  const of = (o: Project["origin"]) => projects.filter((p) => p.origin === o);
  return local
    ? [{ label: "Your projects", projects: of("yours"), name: (p) => shown(p.repo) },
       { label: "Replay: Sept 8, 2025 (example)", projects: of("replay"), name: replayName }]
    : [{ label: "Sept 8 replay", projects: of("replay"), name: replayName },
       { label: "Today (latest lockfile)", projects: of("demo"), name: (p) => p.repo },
       { label: "Scanned by visitors", projects: of("scan"), name: (p) => p.repo }];
}

/** One line under the picker: what this project is and which maintainer lists Q2 uses. */
function ProjectNote({ p }: { p?: Project }) {
  if (!p) return null;
  if (p.replay) {
    const [repo, ref] = p.repo.split("@");
    return (
      <>Real lockfile from <a href={`https://github.com/${repo}/blob/${ref}/package-lock.json`} target="_blank" rel="noopener">commit {ref}</a>{" "}
        ({niceDate(p.as_of)}), before the attack. Q2 uses maintainer lists from that time.</>
    );
  }
  const scanned = niceDate((p.scanned_at ?? "").slice(0, 10));
  if (p.folder) {
    return <>Your lockfile in <code title={p.folder}>{p.folder_short}</code>, scanned {scanned}. Q2 uses today's maintainer lists.</>;
  }
  return (
    <>Latest lockfile from <a href={`https://github.com/${p.repo}`} target="_blank" rel="noopener">github.com/{p.repo}</a>
      {["scan", "yours"].includes(p.origin) ? `, scanned ${scanned}` : ""}. Q2 uses today's maintainer lists.</>
  );
}

export function ProjectPicker({ projects, value, local, onSelect }: {
  projects: Project[]; value: string | null; local: boolean; onSelect: (repo: string) => void;
}) {
  return (
    <>
      <label className="field">
        <span className="label">Project</span>
        <select id="project" value={value ?? ""} onChange={(e) => {
          advanceRing();  // switching project is a navigation: the logo's wheel turns a notch
          onSelect(e.target.value);
        }}>
          {groups(projects, local).filter((g) => g.projects.length).map((g) => (
            <optgroup key={g.label} label={g.label}>
              {g.projects.map((p) => <option key={p.repo} value={p.repo}>{g.name(p)}</option>)}
            </optgroup>
          ))}
        </select>
      </label>
      <p id="project-note" className="hint"><ProjectNote p={projects.find((p) => p.repo === value)} /></p>
    </>
  );
}
