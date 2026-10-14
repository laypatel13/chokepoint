// A macOS-style window for the story page's terminal and code samples: traffic-light controls,
// a centred title, a darker body. Purely decorative chrome; the content is real output or code.
import type { ReactNode } from "react";

export function Window({ title, children, className = "" }: { title: string; children: ReactNode; className?: string }) {
  return (
    <div className={`window reveal ${className}`.trim()}>
      <div className="window-bar">
        <span className="traffic" aria-hidden="true"><i /><i /><i /></span>
        <span className="window-title">{title}</span>
      </div>
      <pre className="window-body">{children}</pre>
    </div>
  );
}
