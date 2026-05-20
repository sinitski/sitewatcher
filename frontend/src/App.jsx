import { HashRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './store/auth'
import AuthPage from './pages/AuthPage'
import Dashboard from './pages/Dashboard'
import SettingsPage from './pages/SettingsPage'
import UpgradePage from './pages/UpgradePage'
import StatusPage from './pages/StatusPage'
import LandingPage from './pages/LandingPage'

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="min-h-screen bg-surface flex items-center justify-center text-gray-500">Loading…</div>
  if (!user) return <Navigate to="/login" replace />
  return children
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return null
  if (user) return <Navigate to="/dashboard" replace />
  return children
}

export default function App() {
  return (
    <AuthProvider>
      <HashRouter>
        <Routes>
          {/* Landing page at root */}
          <Route path="/" element={<PublicRoute><LandingPage /></PublicRoute>} />
          <Route path="/login" element={<PublicRoute><AuthPage mode="login" /></PublicRoute>} />
          <Route path="/register" element={<PublicRoute><AuthPage mode="register" /></PublicRoute>} />
          <Route path="/dashboard" element={<PrivateRoute><Dashboard /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
          <Route path="/upgrade" element={<PrivateRoute><UpgradePage /></PrivateRoute>} />
          <Route path="/status/:username" element={<StatusPage />} />
        </Routes>
      </HashRouter>
    </AuthProvider>
  )
}
