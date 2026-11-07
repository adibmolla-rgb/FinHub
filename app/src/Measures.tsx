// VOL (arch), BOND (QuantLib) and MOOD (finBERT). These measure one thing each, and none of them uses an AI provider.

import { useEffect, useState } from 'react'
import { labApi, type BondResult, type MoodResult, type Receipt, type VolResult } from './api'
import { Panel } from './components'
import { CopyCsvButton } from './CopyCsv'
import { XYChart } from './quant/XYChart'
import { DataError, Val } from './Ticker'

type Common = { onReceipt: (r: Receipt) => void }
const pct = (v: number | null | undefined, digits = 1) => (v == null ? '—' : `${(v * 100).toFixed(digits)}%`)
const points = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)} points`)
const num = (v: number | null | undefined, digits = 2) => (v == null ? '—' : v.toFixed(digits))

function verdict(check: VolResult['check']): string {
  const { months, model_error: model, naive_error: naive, average_miss: miss } = check
  if (model == null || naive == null || !months) return 'There wasn’t enough history to check its forecasts.'
  const lead = model < naive ? 'The model did better than simply assuming the last month carries on' : 'The model did no better than simply assuming the last month carries on'
  const lean = miss == null ? '' : ` It ran ${points(Math.abs(miss))} too ${miss > 0 ? 'high' : 'low'} on average.`
  return `${lead}: over ${months} months its typical error was ${points(model)}, against ${points(naive)}.${lean}`
}

export function VolWorkspace({ symbol, onReceipt }: { symbol: string } & Common) {
  const [data, setData] = useState<VolResult | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let live = true
    labApi.volatility(symbol).then((d) => { if (live) setData(d) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [symbol])

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="VOL" title={`How much might ${symbol} move?`} className="research-wide">
        <div className="stack">
          <p className="muted small">A GARCH model: big moves tend to follow big moves, then calm returns. Volatility here is a year’s typical move, so 20% means about ±1.3% on a normal day.</p>
          {error && <DataError error={error} what="this forecast" />}
          {!data && !error && <p className="muted">Fitting… (usually under a minute)</p>}
          {data && (
            <>
              <p className="muted small">{data.start} to {data.end} · {data.days.toLocaleString()} days of returns.</p>
              {data.warnings.map((w) => <p key={w} className="warn small">{w}</p>)}
              <table className="table">
                <thead><tr><th>Volatility</th><th className="num">A year</th></tr></thead>
                <tbody>
                  <tr><td>The model’s reading today</td><td className="num"><Val r={data.current ?? undefined} onReceipt={onReceipt} /></td></tr>
                  {data.forecasts.map((f) => <tr key={f.days}><td>Forecast, next {f.days === 1 ? 'day' : `${f.days} days`}</td><td className="num"><Val r={f.receipt} onReceipt={onReceipt} /></td></tr>)}
                  <tr><td>What the last month actually did</td><td className="num"><Val r={data.last_month ?? undefined} onReceipt={onReceipt} /></td></tr>
                  <tr><td>All of this history</td><td className="num"><Val r={data.sample ?? undefined} onReceipt={onReceipt} /></td></tr>
                  {data.long_run && <tr><td>Where the model expects it to settle</td><td className="num"><Val r={data.long_run} onReceipt={onReceipt} /></td></tr>}
                </tbody>
              </table>
              <p className="small">
                A shock fades by half in about {num(data.half_life_days, 0)} trading days (persistence {num(data.persistence, 3)}).
                {!data.long_run && ' That’s so slow that the model can’t pin down a long-run level, so it isn’t shown.'}
              </p>
              <h3 className="subhead">Did it work?</h3>
              <p>{verdict(data.check)}</p>
              <p className="muted small">Each month it was refitted using only the past, forecast the next 21 days, and was then compared with what happened.</p>
              {data.series.length > 1 && (
                <XYChart
                  height={200}
                  series={[{ label: 'Volatility', color: 'var(--accent)', points: data.series.flatMap(([, v], i): [number, number][] => (v == null ? [] : [[i, v * 100]])) }]}
                  xLabel={(x) => data.series[Math.round(x)]?.[0] ?? ''}
                  yLabel={(y) => `${y.toFixed(0)}%`}
                  zeroLine={false}
                />
              )}
              <div className="ticket">
                <CopyCsvButton rows={() => [['date', 'forecast', 'last_month', 'what_happened'], ...data.check.rows.map((r) => [r.date, r.forecast, r.naive, r.realised])]} />
              </div>
              <table className="table">
                <thead><tr><th>Made on</th><th className="num">Forecast</th><th className="num">Last month</th><th className="num">What happened</th></tr></thead>
                <tbody>
                  {data.check.rows.slice(-12).reverse().map((r) => <tr key={r.date}><td>{r.date}</td><td className="num">{pct(r.forecast)}</td><td className="num">{pct(r.naive)}</td><td className="num">{pct(r.realised)}</td></tr>)}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}

export function BondWorkspace({ coupon: firstCoupon, years: firstYears, price: firstPrice, onReceipt }: { coupon: number; years: number; price?: number } & Common) {
  const [coupon, setCoupon] = useState(String(+(firstCoupon * 100).toFixed(4)))
  const [years, setYears] = useState(String(firstYears))
  const [price, setPrice] = useState(firstPrice == null ? '' : String(firstPrice))
  const [data, setData] = useState<BondResult | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  const value = async (c: number, y: number, p?: number) => {
    setBusy(true)
    setError(null)
    try {
      setData(await labApi.bond(c, y, p))
    } catch (e) {
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    void value(firstCoupon, firstYears, firstPrice)
    // The form's own button handles later changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const submit = () => {
    const c = parseFloat(coupon), y = parseFloat(years), p = price.trim() === '' ? undefined : parseFloat(price)
    if (!Number.isFinite(c) || !Number.isFinite(y) || (p !== undefined && !Number.isFinite(p))) {
      setError(new Error('the coupon, years and price need to be numbers'))
      return
    }
    void value(c / 100, y, p) // typed as percent, stored as a fraction, converted once here
  }

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="BOND" title="What is this bond worth?" className="research-wide">
        <div className="stack">
          <p className="muted small">A fixed-rate bond paying twice a year, valued with QuantLib. Without a price, it’s valued on today’s Treasury curve, so this is the bond’s value if it were as safe as a Treasury.</p>
          <form className="ticket" onSubmit={(e) => { e.preventDefault(); submit() }}>
            <label className="numfield"><span>Coupon %</span><input value={coupon} onChange={(e) => setCoupon(e.target.value)} inputMode="decimal" /></label>
            <label className="numfield"><span>Years</span><input value={years} onChange={(e) => setYears(e.target.value)} inputMode="decimal" /></label>
            <label className="numfield"><span>Price per 100</span><input value={price} onChange={(e) => setPrice(e.target.value)} placeholder="optional" inputMode="decimal" /></label>
            <button className="chip chip--on" disabled={busy}>{busy ? 'Valuing…' : 'Value it'}</button>
          </form>
          {error && <DataError error={error} what="this bond" />}
          {data && (
            <>
              <p className="muted small">{data.label}, settling {data.settlement}, maturing {data.maturity}.</p>
              <table className="table">
                <tbody>
                  <tr><td>Yield to maturity</td><td className="num"><Val r={data.yield_receipt} onReceipt={onReceipt} /></td><td className="muted small">The return a year if you hold it to the end and reinvest each coupon at this same rate</td></tr>
                  {data.fair_receipt && <tr><td>Value on the Treasury curve</td><td className="num"><Val r={data.fair_receipt} onReceipt={onReceipt} /></td><td className="muted small">{data.price_given ? (data.clean_price > (data.fair_price ?? 0) ? 'Your price is above this' : 'Your price is below this, so it pays more than a Treasury') : 'Used as the price below, as you didn’t give one'}</td></tr>}
                  <tr><td>Clean price</td><td className="num">{num(data.clean_price, 3)}</td><td className="muted small">Per 100 of face value, the way bonds are quoted</td></tr>
                  <tr><td>Modified duration</td><td className="num"><Val r={data.modified_receipt} onReceipt={onReceipt} /></td><td className="muted small">If yields rise 1 point, the price falls about {num(data.modified_duration, 1)}%</td></tr>
                  <tr><td>Macaulay duration</td><td className="num">{num(data.macaulay_duration)} years</td><td className="muted small">The average wait for your money, weighted by present value</td></tr>
                  <tr><td>Convexity</td><td className="num"><Val r={data.convexity_receipt} onReceipt={onReceipt} /></td><td className="muted small">Why big falls in yield help more than big rises hurt</td></tr>
                  <tr><td>DV01</td><td className="num">{num(data.dv01, 4)}</td><td className="muted small">The price change for a 0.01 point move in yield, per 100 of face value</td></tr>
                </tbody>
              </table>
              <h3 className="subhead">Next payments{data.cashflow_count > data.cashflows.length ? ` (first ${data.cashflows.length} of ${data.cashflow_count})` : ''}</h3>
              <table className="table">
                <thead><tr><th>Date</th><th className="num">Per 100</th></tr></thead>
                <tbody>{data.cashflows.map((c, i) => <tr key={`${c.date}-${i}`}><td>{c.date}</td><td className="num">{num(c.amount, 3)}</td></tr>)}</tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}

export function MoodWorkspace({ symbol, onReceipt }: { symbol: string } & Common) {
  const [data, setData] = useState<MoodResult | null>(null)
  const [error, setError] = useState<Error | null>(null)

  useEffect(() => {
    let live = true
    labApi.mood(symbol).then((d) => { if (live) setData(d) }, (e) => { if (live) setError(e) })
    return () => { live = false }
  }, [symbol])

  return (
    <main className="grid grid--research grid--stacked">
      <Panel code="MOOD" title={`The tone of ${symbol}’s headlines`} className="research-wide">
        <div className="stack">
          <p className="muted small">finBERT, a language model trained on financial news, reads each headline on this computer. It reads tone only: it doesn’t check whether a headline is true or even about this company, and this isn’t a trading signal. Its model is licensed for non-commercial use.</p>
          {error && <DataError error={error} what="the headlines’ tone" />}
          {!data && !error && <p className="muted">Reading… The first time, this also downloads the model (about 420 MB), which can take several minutes.</p>}
          {data && (
            <>
              <p>{data.counts.positive} positive, {data.counts.neutral} neutral and {data.counts.negative} negative, of {data.rows.length} headlines.</p>
              <p className="muted small">Headlines from {data.news_provider ?? 'the news feed'}, {data.fetched_at?.slice(0, 16).replace('T', ' ')} UTC. Tone by {data.model}.</p>
              <div className="ticket">
                <CopyCsvButton rows={() => [['headline', 'tone', 'positive', 'neutral', 'negative', 'source', 'url'], ...data.rows.map((r) => [r.headline, r.label, r.positive, r.neutral, r.negative, r.source, r.url])]} />
              </div>
              <table className="table">
                <thead><tr><th>Headline</th><th>Tone</th><th className="num">Sure</th><th>Source</th></tr></thead>
                <tbody>
                  {data.rows.map((r, i) => (
                    <tr key={`${r.headline}-${i}`}>
                      <td>{r.url ? <a href={r.url} target="_blank" rel="noreferrer">{r.headline}</a> : r.headline}</td>
                      <td className={r.label === 'positive' ? 'ok' : r.label === 'negative' ? 'bad' : 'muted'}>{r.label}</td>
                      <td className="num"><Val r={r.confidence} onReceipt={onReceipt} /></td>
                      <td className="muted">{r.source ?? '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
    </main>
  )
}
