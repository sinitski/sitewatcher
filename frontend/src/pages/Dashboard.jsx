import { useEffect, useState } from 'react'
import { Plus, Radio, Settings, LogOut, Zap } from 'lucide-react'
import { useNavigate, Link } from 'react-router-dom'
import { useAuth } from '../store/auth'
import api from '../api'
import SiteCard from '../components/SiteCard'
import AddSiteModal from '../components/AddSiteModal'

export default function Dashboard() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [sites, setSites] = useState([])
  const [loading, setLoading] = useState(true)
  const [showAdd, setShowAdd] = useState(false)

  const fetchSites = async () => {
    try {
      const { data } = await api.get('/sites/')
      setSites(data)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchSites() }, [])

  // Auto-refresh every 30s
  useEffect(() => {
    const id = setInterval(fetchSites, 30_000)
    return () => clearInterval(id)
  }, [])

  const canAddMore = sites.length < (user?.limits?.max_sites || 1)

  const upCount = sites.filter((s) => s.last_status === 'up').length
  const downCount = sites.filter((s) => s.last_status === 'down').length

  return (
    <div className="min-h-screen bg-surface">
      {/* Nav */}
      <nav className="border-b border-border bg-panel/80 backdrop-blur sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Radio className="text-brand-500" size={20} />
            <span className="font-bold tracking-tight">SiteWatcher</span>
          </div>
          <div className="flex items-center gap-2">
            {!user?.is_paid && (
              <Link
                to="/upgrade"
                className="flex items-center gap-1 text-xs bg-amber-500/15 text-amber-400 hover:bg-amber-500/25 px-3 py-1.5 rounded-full transition-colors"
              >
                <Zap size={12} /> Upgrade to Pro
              </Link>
            )}
            {user?.is_paid && (
              <span className="flex items-center gap-1 text-xs bg-brand-500/15 text-brand-500 px-3 py-1.5 rounded-full">
                ⭐ Pro
              </span>
            )}
            <Link to="/settings" className="btn-ghost p-2">
              <Settings size={18} />
            </Link>
            <button onClick={() => { logout(); navigate('/login') }} className="btn-ghost p-2">
              <LogOut size={18} />
            </button>
          </div>
        </div>
      </nav>

      <div className="max-w-4xl mx-auto px-4 py-6">
        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="card text-center">
            <p className="text-2xl font-bold">{sites.length}</p>
            <p className="text-xs text-gray-500 mt-0.5">Total sites</p>
          </div>
          <div className="card text-center">
            <p className="text-2xl font-bold text-green-400">{upCount}</p>
            <p className="text-xs text-gray-500 mt-0.5">Online</p>
          </div>
          <div className="card text-center">
            <p className={`text-2xl font-bold ${downCount > 0 ? 'text-red-400' : 'text-gray-600'}`}>
              {downCount}
            </p>
            <p className="text-xs text-gray-500 mt-0.5">Down</p>
          </div>
        </div>

        {/* Header + Add */}
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-gray-200">Monitored Sites</h2>
          <button
            className="btn-primary flex items-center gap-1 text-sm"
            onClick={() => setShowAdd(true)}
            disabled={!canAddMore}
            title={!canAddMore ? `Free tier: max ${user?.limits?.max_sites} site(s)` : ''}
          >
            <Plus size={16} />
            Add Site
          </button>
        </div>

        {!user?.is_paid && (
          <div className="text-xs text-gray-500 bg-amber-500/5 border border-amber-500/20 rounded-lg px-3 py-2 mb-4">
            Free tier: <strong className="text-amber-400">{sites.length}/{user?.limits?.max_sites}</strong> sites,
            checks every <strong className="text-amber-400">{user?.limits?.min_interval} min</strong>.{' '}
            <Link to="/upgrade" className="text-brand-500 hover:underline">Upgrade for more →</Link>
          </div>
        )}

        {/* Sites list */}
        {loading ? (
          <div className="text-center text-gray-500 py-16">Loading…</div>
        ) : sites.length === 0 ? (
          <div className="card text-center py-16">
            <Radio size={40} className="text-gray-700 mx-auto mb-3" />
            <p className="text-gray-400 font-medium">No sites yet</p>
            <p className="text-sm text-gray-600 mt-1">Add your first site to start monitoring</p>
            <button
              className="btn-primary mt-4 inline-flex items-center gap-1"
              onClick={() => setShowAdd(true)}
            >
              <Plus size={16} /> Add Site
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            {sites.map((site) => (
              <SiteCard
                key={site.id}
                site={site}
                minInterval={user?.limits?.min_interval || 60}
                isPaid={Boolean(user?.is_paid)}
                onRefresh={fetchSites}
                onDelete={(id) => setSites((s) => s.filter((x) => x.id !== id))}
              />
            ))}
          </div>
        )}
      </div>

      {showAdd && (
        <AddSiteModal
          user={user}
          onClose={() => setShowAdd(false)}
          onAdded={(site) => setSites((s) => [...s, site])}
        />
      )}
    </div>
  )
}
