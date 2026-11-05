// Small SVG line chart with a numeric x-axis (payoff diagrams, equity curves, distributions).
// lightweight-charts only supports time on the x-axis, so this covers the other cases.

export type Series = { label: string; color: string; points: [number, number][]; dashed?: boolean; fill?: boolean }

type Props = {
  series: Series[]
  height?: number
  xLabel?: (x: number) => string
  yLabel?: (y: number) => string
  markers?: { x: number; label: string; color?: string }[]
  zeroLine?: boolean
}

function niceTicks(min: number, max: number, count = 5): number[] {
  if (!(max > min)) return [min]
  const raw = (max - min) / count
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(Number(v.toPrecision(12)))
  return out
}

export function XYChart({ series, height = 240, xLabel = (x) => x.toFixed(0), yLabel = (y) => y.toFixed(2), markers = [], zeroLine = true }: Props) {
  const all = series.flatMap((s) => s.points)
  if (!all.length) return <p className="muted">No data.</p>
  const W = 640
  const H = height
  const pad = { l: 56, r: 12, t: 10, b: 26 }
  const xs = all.map((p) => p[0])
  const ys = all.map((p) => p[1])
  const x0 = Math.min(...xs)
  let x1 = Math.max(...xs)
  let [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  if (zeroLine) {
    y0 = Math.min(y0, 0)
    y1 = Math.max(y1, 0)
  }
  if (x1 === x0) x1 = x0 + 1
  if (y1 === y0) {
    y1 += 1
    y0 -= 1
  }
  const yPad = (y1 - y0) * 0.06
  y0 -= yPad
  y1 += yPad
  const sx = (x: number) => pad.l + ((x - x0) / (x1 - x0)) * (W - pad.l - pad.r)
  const sy = (y: number) => H - pad.b - ((y - y0) / (y1 - y0)) * (H - pad.t - pad.b)
  const path = (pts: [number, number][]) => pts.map((p, i) => `${i ? 'L' : 'M'}${sx(p[0]).toFixed(1)},${sy(p[1]).toFixed(1)}`).join('')

  return (
    <div className="xychart">
      <svg viewBox={`0 0 ${W} ${H}`} role="img">
        {niceTicks(y0, y1).map((t) => (
          <g key={`y${t}`}>
            <line x1={pad.l} x2={W - pad.r} y1={sy(t)} y2={sy(t)} className="xychart__grid" />
            <text x={pad.l - 6} y={sy(t) + 3} textAnchor="end" className="xychart__tick">{yLabel(t)}</text>
          </g>
        ))}
        {niceTicks(x0, x1, 6).map((t) => (
          <text key={`x${t}`} x={sx(t)} y={H - 8} textAnchor="middle" className="xychart__tick">{xLabel(t)}</text>
        ))}
        {zeroLine && y0 < 0 && y1 > 0 && <line x1={pad.l} x2={W - pad.r} y1={sy(0)} y2={sy(0)} className="xychart__zero" />}
        {markers.map((m, i) => (
          <g key={i}>
            <line x1={sx(m.x)} x2={sx(m.x)} y1={pad.t} y2={H - pad.b} stroke={m.color ?? '#7d8794'} strokeDasharray="3 3" strokeWidth={1} />
            <text x={sx(m.x) + 3} y={pad.t + 10 + (i % 3) * 11} className="xychart__tick" fill={m.color ?? '#7d8794'}>{m.label}</text>
          </g>
        ))}
        {series.map((s) =>
          s.fill ? (
            <path key={`f${s.label}`} d={`${path(s.points)}L${sx(s.points[s.points.length - 1][0])},${sy(Math.max(y0, 0))}L${sx(s.points[0][0])},${sy(Math.max(y0, 0))}Z`} fill={s.color} opacity={0.12} />
          ) : null,
        )}
        {series.map((s) => (
          <path key={s.label} d={path(s.points)} fill="none" stroke={s.color} strokeWidth={s.dashed ? 1.2 : 2} strokeDasharray={s.dashed ? '5 4' : undefined} vectorEffect="non-scaling-stroke" />
        ))}
      </svg>
      <div className="xychart__legend">
        {series.map((s) => (
          <span key={s.label}><i style={{ background: s.color }} />{s.label}</span>
        ))}
      </div>
    </div>
  )
}
