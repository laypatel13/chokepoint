import { Fragment } from "react";
import { shown } from "../../lib/format";
import { Arrow } from "../../components/Arrow";

/** A dependency road: project → package → … → the version, with the bad one in red. */
export function Chain({ chain, bad }: { chain: string[]; bad?: string }) {
  return (
    <div className="chain">
      {chain.map((k, i) => (
        <Fragment key={`${i}-${k}`}>
          {i > 0 && <Arrow className="arr" />}
          <span className={`node ${k === bad ? "bad" : ""}`}>{i ? k : shown(k)}</span>
        </Fragment>
      ))}
    </div>
  );
}
