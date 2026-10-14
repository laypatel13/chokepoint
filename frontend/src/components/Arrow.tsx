// The flow arrow ("this pulls in that"), drawn as the same Lucide arrow the buttons use. The "→"
// character isn't in our bundled fonts (Latin only), so browsers drew it in a fallback font:
// thin, small and off the baseline. This one is sized to the text around it (1em).
import { Fragment, type ReactNode } from "react";

export function Arrow({ className = "" }: { className?: string }) {
  return (
    <svg className={`flow ${className}`.trim()} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path d="M5 12h14" /><path d="m13 6 6 6-6 6" />
    </svg>
  );
}

function arrows(text: string, key: string): ReactNode {
  if (!text.includes("→")) return text;
  return text.split("→").map((part, i) => <Fragment key={`${key}-${i}`}>{i > 0 && <Arrow />}{part}</Fragment>);
}

/** Text from the API, readable: every "→" drawn as the Arrow ("via a → b → c"), and `backticks`
 * as code ("install with `npm ci`"). Screen readers get the words; the arrow is decorative. */
export function withArrows(text: string): ReactNode {
  if (!text.includes("`")) return arrows(text, "t");
  return text.split("`").map((part, i) => (i % 2 ? <code key={i}>{part}</code> : <Fragment key={i}>{arrows(part, String(i))}</Fragment>));
}
