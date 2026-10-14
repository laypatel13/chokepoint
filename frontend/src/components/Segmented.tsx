// A segmented switch whose highlight slides to the chosen option (like the replay's glider),
// instead of jumping. The highlight is one element moved with a CSS transition on transform and
// width, so it stays smooth and respects reduced motion (base.css turns transitions off).
import { useLayoutEffect, useRef, useState } from "react";

export interface Option<T extends string> {
  value: T;
  label: string;
  id?: string;
  disabled?: boolean;
  title?: string;
}

export function Segmented<T extends string>({ options, value, onChange, label }: {
  options: Option<T>[]; value: T; onChange: (v: T) => void; label: string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [thumb, setThumb] = useState<{ x: number; width: number; ready: boolean } | null>(null);

  useLayoutEffect(() => {
    const measure = (animate: boolean) => {
      const btn = box.current?.querySelector<HTMLElement>(`[data-value="${value}"]`);
      if (!btn) return;
      // The first placement doesn't slide in from nowhere; later ones animate.
      setThumb((t) => ({ x: btn.offsetLeft, width: btn.offsetWidth, ready: animate && !!t }));
    };
    measure(true);
    const observer = new ResizeObserver(() => measure(false));  // fonts load, labels change width
    if (box.current) observer.observe(box.current);
    return () => observer.disconnect();
  }, [value, options.length]);

  return (
    <div className="seg" role="group" aria-label={label} ref={box}>
      <span className={`seg-thumb ${thumb?.ready ? "ready" : ""}`} aria-hidden="true"
        style={thumb ? { width: thumb.width, transform: `translateX(${thumb.x - 3}px)` } : { opacity: 0 }} />
      {options.map((o) => (
        <button key={o.value} id={o.id} data-value={o.value} className={o.value === value ? "on" : ""}
          aria-pressed={o.value === value} disabled={o.disabled} title={o.title} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}
