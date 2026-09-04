interface Props {
  min: number;
  max: number;
  step: number;
  value: [number, number];
  onChange: (value: [number, number]) => void;
  /** Accessible names for the lower and upper thumbs. */
  labels: [string, string];
  className?: string;
}

/**
 * Two-handle range slider built from two overlaid native range inputs.
 * The inputs are transparent and ignore pointer events except on their
 * thumbs (see `.range-thumb` in index.css), so each thumb drags on its own.
 * The lower value can never pass the upper one.
 */
export function RangeSlider({
  min,
  max,
  step,
  value: [lo, hi],
  onChange,
  labels,
  className = "",
}: Props) {
  const pct = (v: number) => ((v - min) / (max - min)) * 100;
  // With both thumbs on the same spot the later input wins the pointer.
  // Put the lower thumb on top in the upper half of the track so a pair
  // parked at the maximum can still be pulled apart.
  const lowerOnTop = lo === hi && lo >= (min + max) / 2;

  return (
    <div className={`relative h-4 ${className}`}>
      <div className="absolute top-1/2 right-0 left-0 h-1 -translate-y-1/2 rounded bg-gray-700" />
      <div
        className="absolute top-1/2 h-1 -translate-y-1/2 rounded bg-blue-500"
        style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
      />
      <input
        type="range"
        className="range-thumb"
        style={lowerOnTop ? { zIndex: 1 } : undefined}
        min={min}
        max={max}
        step={step}
        value={lo}
        aria-label={labels[0]}
        onChange={(e) => onChange([Math.min(Number(e.target.value), hi), hi])}
      />
      <input
        type="range"
        className="range-thumb"
        min={min}
        max={max}
        step={step}
        value={hi}
        aria-label={labels[1]}
        onChange={(e) => onChange([lo, Math.max(Number(e.target.value), lo)])}
      />
    </div>
  );
}
