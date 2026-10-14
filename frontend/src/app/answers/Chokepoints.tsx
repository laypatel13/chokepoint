import type { Chokepoints, RankRow } from "../../lib/types";
import { useActions } from "./actions";
import { Arrow } from "../../components/Arrow";
import { Segmented } from "../../components/Segmented";

const pkg = (key: string) => key.slice(0, key.lastIndexOf("@") > 0 ? key.lastIndexOf("@") : undefined);

/** "@babel/cli +38 more": the dependencies that give an account its reach. */
function via(x: RankRow) {
  if (!x.via.length) return null;
  return <>{pkg(x.via[0])}{x.via.length > 1 && <span className="muted"> +{x.via.length - 1}</span>}</>;
}

/** Q2: who could poison this project, ranked by how many direct dependencies they reach. */
export function ChokepointsCard({ r }: { r: Chokepoints }) {
  const { run } = useActions();
  if (!r.ranking.length) return null;
  const focus = r.focus_row;
  const total = r.direct.direct;
  const by = r.by ?? "reach";
  const list = r.ranking.some((x) => x.maintainer === r.focus) ? r.ranking : [...r.ranking, focus];
  const value = (x: RankRow) => (by === "prod" ? x.prod_reach : x.reach);
  const of = by === "prod" ? r.direct.prod : total;
  return (
    <>
      <div>
        <div className="big">{focus.reach}<small> of your {total} direct dependencies</small></div>
        <div className="muted" style={{ marginTop: 4 }}>
          pull in a package <b>@{r.focus}</b> can publish ({focus.prod_reach} of {r.direct.prod} prod) · {r.controlled.length} versions in amber
        </div>
      </div>
      {r.top3 && r.top3.accounts.length > 1 && (
        <p className="top3" id="top3">
          Together, {r.top3.accounts.map((a, i) => <span key={a}>{i ? ", " : ""}<b>@{a}</b></span>)} reach{" "}
          <b>{r.top3.reach} of {total}</b> direct dependencies.
        </p>
      )}
      <div className="meta rank-meta">
        <span className={`pill ${r.when === "now" ? "blue" : "amber"}`}>{r.when === "now" ? "TODAY'S MAINTAINER LISTS" : "MAINTAINERS AT INSTALL TIME"}</span>
        <Segmented label="Rank by" value={by}
          onChange={(v) => run("chokepoints", { by: v })}
          options={[
            { value: "reach", label: "All deps", id: "rank-reach", title: "Every direct dependency: install-time malware hits dev tools and CI too" },
            { value: "prod", label: "Prod first", id: "rank-prod", title: "Production dependencies first: what ships to your users" },
          ]} />
      </div>
      <table className="rank">
        <tbody>
          {list.map((x) => (
            <tr key={x.maintainer} className={x.maintainer === r.focus ? "on" : ""} data-maintainer={x.maintainer}
              onClick={() => run("chokepoints", { maintainer: x.maintainer, by })}>
              <td className="num">{x.rank}</td>
              <td className="who" title={`@${x.maintainer}`}>
                <span className="line"><button className="handle" aria-pressed={x.maintainer === r.focus}
                  aria-label={`Focus on @${x.maintainer}: reaches ${x.reach} of ${total} direct dependencies`}
                  onClick={(e) => { e.stopPropagation(); run("chokepoints", { maintainer: x.maintainer, by }); }}>@{x.maintainer}</button>
                {x.bot && <span className="tag bot" title="An automated or organisation account">bot</span>}
                {x.dormant && x.last_published && (
                  <span className="tag quiet" title={`Still able to publish, but hasn't released any package in this project since ${x.last_published.slice(0, 10)}. A login from a quiet account is less likely to be noticed.`}>
                    quiet since {x.last_published.slice(0, 4)}
                  </span>
                )}
</span>
                <span className="via">{x.tied_with?.length ? (
                  <span className="tag tied" title={`Can publish exactly the same packages: ${x.tied_with.map((t) => "@" + t).join(", ")}`}>
                    +{x.tied_with.length} tied
                  </span>
                ) : null}via {via(x)}</span>
              </td>
              <td style={{ width: "24%" }}><div className="bar"><i style={{ width: `${(100 * value(x) / Math.max(1, of)).toFixed(1)}%` }} /></div></td>
              <td className="num" title={`${x.reach}/${total} direct · ${x.prod_reach}/${r.direct.prod} prod`}>{value(x)}/{of}</td>
              <td className="why" title="betweenness (bridge score) · PageRank (influence): tie-breakers"><span>b {x.betweenness}</span><span>pr {x.pagerank}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="muted small">
        ranked by {by === "prod" ? <>prod reach <Arrow /> reach</> : "reach"} <Arrow /> betweenness <Arrow /> PageRank
        {list.some((x) => x.tied_with?.length) && <> · “tied”: a team that can publish the same packages, grouped into one row</>}
      </div>
    </>
  );
}
