"use client";

import { useState } from "react";

export type Bucket = { label: string; ok: number; bad: number };

const W = 640;
const H = 160;
const PAD = { top: 8, right: 4, bottom: 20, left: 30 };
const GAP = 2; // surface gap between stacked segments and adjacent bars

/** Bar with only its top (data end) rounded; bottom stays square on the baseline. */
function topRounded(x: number, y: number, w: number, h: number, r = 4) {
  if (h <= 0) return "";
  const rr = Math.min(r, w / 2, h);
  return `M${x},${y + h}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${y + h}Z`;
}

function niceMax(v: number) {
  if (v <= 4) return 4;
  const pow = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((m) => m * pow).find((m) => m >= v)!;
}

/** Stacked hourly bars: successes in series blue, failures in the critical status color on top. */
export function HourlyChart({
  buckets,
  okLabel,
  badLabel,
}: {
  buckets: Bucket[];
  okLabel: string;
  badLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = niceMax(Math.max(0, ...buckets.map((b) => b.ok + b.bad)));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const slot = innerW / buckets.length;
  const barW = Math.max(2, Math.min(18, slot - GAP));
  const y = (v: number) => (v / max) * innerH;
  const ticks = [0, max / 2, max];

  return (
    <div className="chart">
      <div className="legend">
        <span>
          <i style={{ background: "var(--series-1)" }} />
          {okLabel}
        </span>
        <span>
          <i style={{ background: "var(--critical)" }} />
          {badLabel}
        </span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`${okLabel} and ${badLabel} per hour`}>
        <g className="grid">
          {ticks.map((t) => (
            <line key={t} x1={PAD.left} x2={W - PAD.right} y1={PAD.top + innerH - y(t)} y2={PAD.top + innerH - y(t)} />
          ))}
        </g>
        <g className="axis">
          {ticks.map((t) => (
            <text key={t} x={PAD.left - 6} y={PAD.top + innerH - y(t) + 3} textAnchor="end">
              {Number.isInteger(t) ? t : t.toFixed(1)}
            </text>
          ))}
          {buckets.map((b, i) =>
            i % 6 === 0 || i === buckets.length - 1 ? (
              <text key={i} x={PAD.left + i * slot + slot / 2} y={H - 4} textAnchor="middle">
                {b.label}
              </text>
            ) : null,
          )}
        </g>
        {buckets.map((b, i) => {
          const x = PAD.left + i * slot + (slot - barW) / 2;
          const base = PAD.top + innerH;
          const okH = y(b.ok);
          const badH = y(b.bad);
          const okTop = base - okH;
          // Gap only when both segments are present; the top segment owns the rounded end.
          const badY = okTop - badH - (b.ok && b.bad ? GAP : 0);
          return (
            <g key={i}>
              {b.ok > 0 && (
                <path className="bar-ok" d={b.bad ? `M${x},${base}V${okTop}H${x + barW}V${base}Z` : topRounded(x, okTop, barW, okH)} />
              )}
              {b.bad > 0 && <path className="bar-bad" d={topRounded(x, badY, barW, badH)} />}
              <rect
                className="hit"
                x={PAD.left + i * slot}
                y={PAD.top}
                width={slot}
                height={innerH}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
              />
            </g>
          );
        })}
      </svg>
      {hover !== null && (
        <div
          className="tooltip"
          style={{ left: `${((PAD.left + hover * slot + slot / 2) / W) * 100}%`, top: 24 }}
          role="status"
        >
          <strong>{buckets[hover].label}</strong>
          <div>
            {okLabel}: {buckets[hover].ok}
          </div>
          <div>
            {badLabel}: {buckets[hover].bad}
          </div>
        </div>
      )}
    </div>
  );
}
