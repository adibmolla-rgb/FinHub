import { useEffect, useState } from 'react'
import { ApiError, compact, formatValue, fundamentalsApi, timeAgo, type Fundamentals, type Receipt } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'

const RATIOS: [string, string][] = [
  ['revenue', 'Revenue'], ['revenue_growth', 'Revenue growth'], ['gross_margin', 'Gross margin'], ['operating_margin', 'Operating margin'],
  ['net_margin', 'Net margin'], ['net_income', 'Net income'], ['roe', 'ROE'], ['roa', 'ROA'], ['debt_to_equity', 'Debt / equity'],
  ['free_cash_flow', 'Free cash flow'], ['fcf_margin', 'FCF margin'], ['cash', 'Cash'],
]
const TABS = [['income', 'Income statement'], ['balance', 'Balance sheet'], ['cash', 'Cash flow']] as const

const label = (field: string) => field.replace(/_/g, ' ').replace(/([a-z])([A-Z])/g, '$1 $2').replace(/^./, (c) => c.toUpperCase())

export function FundamentalsWorkspace({ symbol, onReceipt }: { symbol: string; onReceipt: (r: Receipt) => void }) {
  const [period, setPeriod] = useState<'annual' | 'quarter'>('annual')
  const [tab, setTab] = useState<(typeof TABS)[number][0]>('income')
  const [data, setData] = useState<Fundamentals | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    fundamentalsApi.get(symbol, period).then(
      (d) => live && (setData(d), setLoading(false)),
      (e) => live && (setError(e), setData(null), setLoading(false)),
    )
    return () => { live = false }
  }, [symbol, period])

  const st = data?.statements[tab]
  const stErr = data?.errors[tab]
  return (
    <main className="grid grid--fa">
      <Panel code="FA" title={`${symbol} · key figures (${period === 'annual' ? 'latest fiscal year' : 'latest quarter'})`} className="grid__faratios">
        <div className="stack">
          <div className="ticket">
            {(['annual', 'quarter'] as const).map((p) => <button key={p} className={`chip ${period === p ? 'chip--on' : ''}`} onClick={() => setPeriod(p)}>{p === 'annual' ? 'Annual' : 'Quarterly'}</button>)}
          </div>
          {loading && <p className="muted">Loading statements… (three in parallel)</p>}
          {error && (
            <div className="data-error">
              <p><span className="bad">Couldn’t load fundamentals.</span> <span className="muted">{error.message}</span></p>
              {error instanceof ApiError && error.attempts.length > 0 && <ul className="small muted">{error.attempts.map((a, i) => <li key={i}>✗ {a.provider}: {a.error}</li>)}</ul>}
            </div>
          )}
          {data && (
            <dl className="ratios">
              {RATIOS.filter(([k]) => data.ratios[k]).map(([k, l]) => (
                <div key={k}>
                  <dt>{l}</dt>
                  <dd><button className="val" onClick={() => onReceipt(data.ratios[k])}>{formatValue(data.ratios[k])}</button></dd>
                </div>
              ))}
            </dl>
          )}
          {data && <p className="muted small">Click a figure for its receipt: the formula and the exact provider fields and periods behind it. Ratios are left out when an input is missing.</p>}
        </div>
      </Panel>
      <Panel code="STMT" title="Statements" className="grid__fastmt">
        <div className="stack">
          <div className="ticket">
            {TABS.map(([k, l]) => <button key={k} className={`chip ${tab === k ? 'chip--on' : ''}`} onClick={() => setTab(k)}>{l}</button>)}
            {st && <CopyCsvButton rows={() => [['line_item', ...st.periods], ...st.rows.map((r) => [r.field, ...r.values])]} />}
            {st && <span className="badge" style={{ marginLeft: 'auto' }}>via {st.provider_name} · {timeAgo(st.fetched_at)}{st.currency ? ` · ${st.currency}` : ''}</span>}
          </div>
          {stErr && <p className="bad small">{stErr.error}</p>}
          {st && (
            <div className="stmt-scroll">
              <table className="table stmt">
                <thead><tr><th>Line item</th>{st.periods.map((p) => <th key={p} className="num">{p}</th>)}</tr></thead>
                <tbody>
                  {st.rows.map((r) => (
                    <tr key={r.field}>
                      <td title={`provider field: ${r.field}`}>{label(r.field)}</td>
                      {r.values.map((v, i) => <td key={i} className={`num ${v != null && v < 0 ? 'bad' : ''}`}>{v == null ? '—' : Math.abs(v) >= 1e4 ? compact(v) : v.toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </Panel>
    </main>
  )
}
