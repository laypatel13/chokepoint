import type { ReactNode } from "react";
import { Icon, type IconName } from "../../components/Icon";
import { withArrows } from "../../components/Arrow";

/** The square icon tile used on cards (tone: danger, warn, gold, ok, brand, or none). */
export function ITile({ icon, tone = "" }: { icon: IconName; tone?: string }) {
  return <span className={`itile ${tone}`.trim()}><Icon name={icon} /></span>;
}

/** A section's label, headline and intro. The headline spans the full width; with an `aside`
 * (a terminal, a code card) the intro and the aside sit side by side underneath it.
 * Labels share one quiet style; a tone is only for status (e.g. "ok live" on the live-data section). */
export function SecHead({ badge, badgeTone, title, children, aside }: {
  badge: string; badgeTone?: string; title: string; children?: ReactNode; aside?: ReactNode;
}) {
  const head = (
    <>
      <span className={`badge ${badgeTone ?? ""}`.trim()}>{badge}</span>
      <h2>{title}</h2>
    </>
  );
  if (!aside) return <div className="sec-head reveal">{head}{children}</div>;
  return (
    <>
      <div className="sec-head reveal">{head}</div>
      <div className="split">
        <div className="split-text reveal">{children}</div>
        {aside}
      </div>
    </>
  );
}

/** A small feature card: icon, title, text, optional example line. */
export function Feat({ icon, tone, title, small, children, example }: {
  icon: IconName; tone?: string; title: string; small?: boolean; children: ReactNode; example?: string;
}) {
  return (
    <article className={`card feat ${small ? "small " : ""}reveal`}>
      <ITile icon={icon} tone={tone} />
      <h3>{title}</h3>
      <p>{children}</p>
      {example && <code className="ex">{withArrows(example)}</code>}
    </article>
  );
}

export const REPLAY_URL = "/app?project=webpack/webpack-dev-server@fa9195c";
