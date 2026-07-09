import React from "react";

// Tiny dependency-free inline-SVG charts (K1). Colours come from CSS vars so they
// follow the light/dark theme.

// Grouped horizontal bars: one row per person, comparing a few metrics.
export function EquityBars({ rows, metrics }) {
  if (!rows.length) return null;
  const max = Math.max(1, ...rows.flatMap((r) => metrics.map((m) => r[m.key] || 0)));
  const rowH = 18;
  const barH = rowH / metrics.length - 1;
  return (
    <div className="chart">
      <div className="chart-legend">
        {metrics.map((m) => (
          <span key={m.key} className="legend-item">
            <span className="legend-swatch" style={{ background: m.color }} /> {m.label}
          </span>
        ))}
      </div>
      <svg width="100%" height={rows.length * (rowH + 8)} role="img"
        aria-label="Equity distribution by person">
        {rows.map((r, i) => {
          const y0 = i * (rowH + 8);
          return (
            <g key={r.name}>
              <text x="0" y={y0 + rowH / 2 + 3} className="chart-label">{r.name}</text>
              {metrics.map((m, j) => {
                const v = r[m.key] || 0;
                const w = `${(v / max) * 70}%`;
                return (
                  <g key={m.key}>
                    <rect x="30%" y={y0 + j * (barH + 1)} width={w} height={barH}
                      fill={m.color} rx="2">
                      <title>{`${r.name} · ${m.label}: ${v}`}</title>
                    </rect>
                    {v > 0 && (
                      <text x={`calc(30% + ${v / max * 70}% + 4px)`}
                        y={y0 + j * (barH + 1) + barH - 1} className="chart-num">{v}</text>
                    )}
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}

// Trend line of a single series across periods.
export function Sparkline({ points, label }) {
  if (!points || points.length < 2) return null;
  const w = 320, h = 60, pad = 6;
  const max = Math.max(1, ...points.map((p) => p.shifts));
  const step = (w - pad * 2) / (points.length - 1);
  const coords = points.map((p, i) => [
    pad + i * step,
    h - pad - (p.shifts / max) * (h - pad * 2),
  ]);
  const path = coords.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`).join(" ");
  return (
    <div className="chart">
      {label && <div className="chart-legend"><span className="muted">{label}</span></div>}
      <svg width={w} height={h} role="img" aria-label={label || "trend"}>
        <path d={path} fill="none" stroke="var(--accent)" strokeWidth="2" />
        {coords.map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r="2.5" fill="var(--accent)">
            <title>{`${points[i].period}: ${points[i].shifts} shifts`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}
