import { useState, useEffect } from 'react'
import { useParams } from 'react-router-dom'
import api from '../api'

const STATUS_COLOR = {
  up:      { dot: '#22c55e', label: 'Operational',     bg: 'rgba(34,197,94,0.1)' },
  down:    { dot: '#ef4444', label: 'Down',            bg: 'rgba(239,68,68,0.1)' },
  unknown: { dot: '#94a3b8', label: 'Unknown',         bg: 'rgba(148,163,184,0.1)' },
}

const OVERALL_LABEL = {
  operational:   { text: '✅ All systems operational', color: '#22c55e' },
  partial_outage:{ text: '⚠️ Partial outage',          color: '#f59e0b' },
  unknown:       { text: '⏳ Checking…',               color: '#94a3b8' },
}

function MiniChart({ history }) {
  if (!history?.length) return null
  const bars = history.slice(-30)
  return (
    <div style={{ display: 'flex', gap: 2, alignItems: 'flex-end', height: 32 }}>
      {bars.map((h, i) => (
        <div
          key={i}
          title={`${h.time.slice(11, 16)} — ${h.is_up ? `${h.response_ms}ms` : 'DOWN'}`}
          style={{
            width: 6,
            flex: '0 0 6px',
            height: h.is_up ? Math.min(32, Math.max(8, (h.response_ms || 200) / 20)) : 32,
            borderRadius: 2,
            background: h.is_up ? '#6366f1' : '#ef4444',
            opacity: 0.85,
          }}
        />
      ))}
    </div>
  )
}

function SiteRow({ site }) {
  const s = STATUS_COLOR[site.status] || STATUS_COLOR.unknown
  return (
    <div style={styles.siteRow}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
        <span style={{ color: s.dot, fontSize: 10 }}>●</span>
        <div style={{ minWidth: 0 }}>
          <p style={styles.siteName}>{site.name}</p>
          <p style={styles.siteUrl}>{site.url}</p>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <MiniChart history={site.history} />

        <div style={{ textAlign: 'right', minWidth: 90 }}>
          <p style={{ color: s.dot, fontSize: 12, fontWeight: 600 }}>{s.label}</p>
          <p style={styles.uptime}>
            {site.uptime_30d}% uptime
          </p>
          <p style={styles.uptime}>{site.uptime_7d}% (7d)</p>
          <p style={styles.uptime}>Incidents 7d: {site.incidents_7d || 0}</p>
          <p style={styles.uptime}>MTTR 7d: {site.mttr_minutes_7d || 0}m</p>
          {site.last_response_time && (
            <p style={styles.uptime}>{Math.round(site.last_response_time * 1000)}ms</p>
          )}
        </div>
      </div>
    </div>
  )
}

export default function StatusPage() {
  const { username } = useParams()
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState('')

  useEffect(() => {
    api.get(`/status/${username}`)
      .then(r => setData(r.data))
      .catch(() => setError('Status page not found'))
      .finally(() => setLoading(false))
  }, [username])

  if (loading) return (
    <div style={styles.center}>
      <p style={{ color: '#64748b' }}>Loading…</p>
    </div>
  )

  if (error) return (
    <div style={styles.center}>
      <p style={{ color: '#ef4444' }}>{error}</p>
    </div>
  )

  const overall = OVERALL_LABEL[data.overall] || OVERALL_LABEL.unknown

  return (
    <div style={styles.wrap}>
      <div style={styles.container}>
        {/* Header */}
        <div style={styles.header}>
          <h1 style={styles.title}>📡 {username}</h1>
          <p style={styles.subtitle}>System Status</p>
        </div>

        {/* Overall status */}
        <div style={{ ...styles.overallCard, borderColor: overall.color + '44' }}>
          <p style={{ color: overall.color, fontWeight: 700, fontSize: 16 }}>
            {overall.text}
          </p>
          <p style={{ color: '#64748b', fontSize: 12, marginTop: 4 }}>
            Last updated: {new Date(data.generated_at).toLocaleString()}
          </p>
        </div>

        {data.overall_metrics && (
          <div style={styles.metricsGrid}>
            <div style={styles.metricCard}>
              <p style={styles.metricValue}>{data.overall_metrics.uptime_24h}%</p>
              <p style={styles.metricLabel}>Uptime 24h</p>
            </div>
            <div style={styles.metricCard}>
              <p style={styles.metricValue}>{data.overall_metrics.uptime_7d}%</p>
              <p style={styles.metricLabel}>Uptime 7d</p>
            </div>
            <div style={styles.metricCard}>
              <p style={styles.metricValue}>{data.overall_metrics.mttr_minutes_7d || 0}m</p>
              <p style={styles.metricLabel}>MTTR 7d</p>
            </div>
            <div style={styles.metricCard}>
              <p style={styles.metricValue}>{data.overall_metrics.incidents_7d || 0}</p>
              <p style={styles.metricLabel}>Incidents 7d</p>
            </div>
          </div>
        )}

        {/* Sites */}
        <div style={styles.card}>
          <h2 style={styles.sectionTitle}>Monitored Services</h2>
          {data.sites.length === 0 ? (
            <p style={{ color: '#64748b', fontSize: 14 }}>No public sites configured.</p>
          ) : (
            data.sites.map((site, i) => (
              <div key={i}>
                <SiteRow site={site} />
                {i < data.sites.length - 1 && <div style={styles.divider} />}
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <p style={styles.footer}>
          Powered by{' '}
          <a href="https://sitewatcher-six.vercel.app" style={{ color: '#6366f1' }}>
            SiteWatcher
          </a>
        </p>
      </div>
    </div>
  )
}

const styles = {
  wrap:        { minHeight: '100vh', background: '#020617', fontFamily: 'Inter, sans-serif', padding: '40px 16px' },
  container:   { maxWidth: 680, margin: '0 auto' },
  center:      { minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#020617' },
  header:      { textAlign: 'center', marginBottom: 32 },
  title:       { color: '#f1f5f9', fontSize: 28, fontWeight: 700, margin: 0 },
  subtitle:    { color: '#64748b', fontSize: 14, marginTop: 4 },
  overallCard: { background: '#0f172a', border: '1px solid', borderRadius: 12, padding: '16px 20px', marginBottom: 16 },
  metricsGrid: { display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: 10, marginBottom: 16 },
  metricCard: { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 10, padding: '12px 14px' },
  metricValue: { color: '#e2e8f0', fontSize: 20, fontWeight: 700, margin: 0 },
  metricLabel: { color: '#64748b', fontSize: 11, margin: '4px 0 0' },
  card:        { background: '#0f172a', border: '1px solid #1e293b', borderRadius: 12, padding: '16px 20px', marginBottom: 16 },
  sectionTitle:{ color: '#94a3b8', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16, margin: '0 0 16px' },
  siteRow:     { display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, padding: '10px 0' },
  siteName:    { color: '#e2e8f0', fontSize: 14, fontWeight: 500, margin: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  siteUrl:     { color: '#475569', fontSize: 11, margin: '2px 0 0', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  uptime:      { color: '#64748b', fontSize: 11, margin: '2px 0 0' },
  divider:     { height: 1, background: '#1e293b' },
  footer:      { textAlign: 'center', color: '#334155', fontSize: 12, marginTop: 24 },
}
