// The mark: the Pinch. Packages on one side and your app on the other, every road squeezed through
// one yellow diamond in the middle: the maintainer account they all depend on. A chokepoint.
//
// The bowtie (.logo-turn) half-turns on every navigation (src/lib/ring.ts), so the two sides swap
// with a small click, like Mahoraga's wheel turning a notch. The diamond never moves.

const HOLE = "#1C1C1F";  // the dot in the diamond's middle
const DIAMOND = "#FFDE59";
const ROWS = [13, 24, 35];

export function Logo() {
  return (
    // No background tile: just the mark (viewBox cropped to it, so it fills its space).
    <svg className="logo-mark" viewBox="4 4 40 40" fill="none" aria-hidden="true" focusable="false">
      <g className="logo-turn">
        {/* each road leaves its node level, then bends into the diamond: a funnel, not an X */}
        <g stroke="#FFFFFF" strokeOpacity=".55" strokeWidth="2.2" strokeLinecap="round">
          {ROWS.map((y) => <path key={`l${y}`} d={`M10 ${y} C18 ${y} 19 24 24 24`} />)}
          {ROWS.map((y) => <path key={`r${y}`} d={`M38 ${y} C30 ${y} 29 24 24 24`} />)}
        </g>
        {/* packages (tinted, the color changes each turn) on one side, your app's side in white */}
        {ROWS.map((y) => <circle key={`p${y}`} className="tint-fill" cx="10" cy={y} r="3.6" />)}
        {ROWS.map((y) => <circle key={`a${y}`} cx="38" cy={y} r="3" fill="#FFFFFF" fillOpacity=".9" />)}
      </g>
      <rect x="18.7" y="18.7" width="10.6" height="10.6" rx="2.2" fill={DIAMOND} transform="rotate(45 24 24)" />
      <circle cx="24" cy="24" r="2" fill={HOLE} />
    </svg>
  );
}
