import { useEffect, useState } from 'react'
import { alertsApi, timeAgo, type Alert, type AlertEvent } from './api'
import { Panel } from './components'
import { notify } from './notify'

export function AlertsWorkspace({ version }: { version: number }) {
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [events, setEvents] = useState<AlertEvent[]>([])
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)

  const load = () => alertsApi.list().then((d) => { setAlerts(d.alerts); setEvents(d.events) }, (e) => setError(String(e.message ?? e)))
  useEffect(() => { load() }, [version])

  const active = alerts.filter((a) => a.active)
  const done = alerts.filter((a) => !a.active)
  return (
    <main className="grid grid--alerts">
      <Panel code="ALERT" title={`Active alerts · ${active.length}`} className="grid__alertsactive">
        <div className="stack">
          <p className="muted small">
            Add with <code>ALERT AAPL &gt; 200</code>, <code>ALERT AAPL &lt; 150</code>, <code>ALERT NVDA +5%</code> (day’s move) or <code>ALERT NVDA -5%</code>.
            Checked every 2 minutes while FinHub is open; each alert fires once.
          </p>
          <div className="ticket">
            <button className="chip" disabled={checking} onClick={() => { setChecking(true); alertsApi.checkNow().then(load, (e) => setError(String(e.message ?? e))).finally(() => setChecking(false)) }}>
              {checking ? 'Checking…' : 'Check now'}
            </button>
            <button className="chip" onClick={() => notify('FinHub', 'Test notification: alerts will look like this.')}>Test notification</button>
          </div>
          {error && <p className="bad small">{error}</p>}
          <table className="table">
            <tbody>
              {active.map((a) => (
                <tr key={a.id}>
                  <td>{a.description}</td>
                  <td className="muted small">{timeAgo(a.created_at)}</td>
                  <td><button className="chip" onClick={() => alertsApi.remove(a.id).then(load)}>✕</button></td>
                </tr>
              ))}
              {!active.length && <tr><td className="muted">No active alerts.</td></tr>}
            </tbody>
          </table>
          {done.length > 0 && (
            <>
              <h3 className="subhead">Triggered</h3>
              <table className="table">
                <tbody>
                  {done.map((a) => (
                    <tr key={a.id}>
                      <td>{a.description}</td>
                      <td className="muted small">{a.triggered_at ? `${timeAgo(a.triggered_at)} at ${a.triggered_price}` : ''}</td>
                      <td><button className="chip" onClick={() => alertsApi.remove(a.id).then(load)}>✕</button></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </div>
      </Panel>
      <Panel code="EVENTS" title="Alert history" className="grid__alertsevents">
        {!events.length && <p className="muted">Nothing has fired yet.</p>}
        <ol className="log">
          {[...events].reverse().map((e) => (
            <li key={e.id}><time>{new Date(e.at).toLocaleString([], { hour12: false })}</time><span>{e.text}</span><span className="muted small">{e.provider}</span></li>
          ))}
        </ol>
      </Panel>
    </main>
  )
}
