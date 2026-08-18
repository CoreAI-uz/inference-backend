// The dome / concentric-arc signature mark. Three arcs radiating from a center dot,
// opacities stepping down — "local infrastructure broadcasting compute".

export function ArcLogo({ size = 34, className, color = "var(--ca-logo)" }: { size?: number; className?: string; color?: string }) {
  // Cropped viewBox drops the dead space in the 56×56 grid so the mark reads at full
  // size. `size` = width; height follows the ~50:32 content aspect. `color` overrides the
  // Default terracotta; callers can override it for other branded surfaces.
  return (
    <svg
      viewBox="3 12 50 32"
      width={size}
      height={Math.round((size * 32) / 50)}
      className={className}
      aria-hidden
    >
      <path d="M 6,38 A 22,22 0 0,1 50,38" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" />
      <path d="M 13,38 A 15,15 0 0,1 43,38" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" opacity="0.5" />
      <path d="M 20,38 A 8,8 0 0,1 36,38" fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" opacity="0.28" />
      <circle cx="28" cy="38" r="4" fill={color} />
    </svg>
  );
}

// Compact 2-arc mark used as the assistant avatar / model-picker glyph.
export function ArcMark({ size = 26, className }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 56 56" width={size} height={size} className={className} aria-hidden>
      <path d="M 6,38 A 22,22 0 0,1 50,38" fill="none" stroke="var(--ca-logo)" strokeWidth="5" strokeLinecap="round" />
      <path d="M 15,38 A 13,13 0 0,1 41,38" fill="none" stroke="var(--ca-logo)" strokeWidth="5" strokeLinecap="round" opacity="0.45" />
      <circle cx="28" cy="38" r="4.5" fill="var(--ca-logo)" />
    </svg>
  );
}

// "Sequential beam" thinking/generating mark: the center dot ignites, then the
// concentric arcs illuminate inner → outer (radiating outward), hold, fade, and loop.
// Opacity + hue only (no transform). Keyframes + reduced-motion fallback in globals.css.
// Matches ArcMark exactly (2 arcs: r=22 outer, r=13 inner + dot, strokeWidth 5) so
// the streaming beam settles seamlessly into the static avatar when the reply ends.
export function ArcThinking({ size = 26, label = "Generating", className }: { size?: number; label?: string; className?: string }) {
  return (
    <svg className={["beam-root", className].filter(Boolean).join(" ")} width={size} height={size} viewBox="0 0 56 56" role="img" aria-label={label} fill="none">
      <path className="beam-arc beam-arc--outer" d="M 6,38 A 22,22 0 0,1 50,38" strokeWidth="5" strokeLinecap="round" />
      <path className="beam-arc beam-arc--inner" d="M 15,38 A 13,13 0 0,1 41,38" strokeWidth="5" strokeLinecap="round" />
      <circle className="beam-dot" cx="28" cy="38" r="4.5" />
    </svg>
  );
}

export function Wordmark({ size = 18, className, accent = "var(--ca-logo)", weight = 500 }: { size?: number; className?: string; accent?: string; weight?: number }) {
  return (
    <span style={{ fontSize: size, letterSpacing: "-0.02em", fontWeight: weight }} className={className}>
      Core<span style={{ color: accent }}>AI</span>
    </span>
  );
}
