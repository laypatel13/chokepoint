import { useEffect, useRef, useState } from "react";

/** A shell command you click to copy (local mode: things the browser shouldn't do for you,
 * like editing your files). */
export function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  const timer = useRef<number>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const copy = () => {
    navigator.clipboard?.writeText(command).then(() => {
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 900);
    }).catch(() => {});
  };
  return <code className="cmd" data-copy={command} title="Click to copy" onClick={copy}>{copied ? "copied" : command}</code>;
}
