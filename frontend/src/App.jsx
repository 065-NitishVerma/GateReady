import { useEffect, useMemo, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

const storageKeys = {
  access: 'aba_access_token',
  refresh: 'aba_refresh_token',
}

function readTokens() {
  return {
    accessToken: localStorage.getItem(storageKeys.access) || '',
    refreshToken: localStorage.getItem(storageKeys.refresh) || '',
  }
}

function writeTokens(tokens) {
  localStorage.setItem(storageKeys.access, tokens.accessToken || '')
  localStorage.setItem(storageKeys.refresh, tokens.refreshToken || '')
}

function clearTokens() {
  localStorage.removeItem(storageKeys.access)
  localStorage.removeItem(storageKeys.refresh)
}

function App() {
  const [tokens, setTokens] = useState(readTokens)
  const [username, setUsername] = useState('user_123')
  const [password, setPassword] = useState('demo-pass')
  const [message, setMessage] = useState('')
  const [messages, setMessages] = useState([])
  const [bookings, setBookings] = useState([])
  const [allBookings, setAllBookings] = useState([])
  const [filterOrigin, setFilterOrigin] = useState('')
  const [filterDestination, setFilterDestination] = useState('')
  const [filterStatus, setFilterStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const isAuthed = useMemo(() => Boolean(tokens.accessToken), [tokens.accessToken])
  const filterOptions = useMemo(() => {
    const origins = new Set()
    const destinations = new Set()
    const statuses = new Set()
    allBookings.forEach((booking) => {
      if (booking.origin) origins.add(booking.origin)
      if (booking.destination) destinations.add(booking.destination)
      if (booking.status) statuses.add(booking.status)
    })
    return {
      origins: Array.from(origins).sort(),
      destinations: Array.from(destinations).sort(),
      statuses: Array.from(statuses).sort(),
    }
  }, [bookings])
  const filteredBookings = useMemo(() => bookings, [bookings])

  useEffect(() => {
    writeTokens(tokens)
  }, [tokens])

  const fetchBookings = async (filters = {}, updateAll = false) => {
    if (!tokens.accessToken) {
      setBookings([])
      setAllBookings([])
      return
    }
    const params = new URLSearchParams()
    if (filters.origin) params.set('origin', filters.origin)
    if (filters.destination) params.set('destination', filters.destination)
    if (filters.status) params.set('status', filters.status)
    const url = params.toString() ? `${API_BASE}/bookings?${params}` : `${API_BASE}/bookings`
    try {
      const res = await fetch(url, {
        headers: { Authorization: `Bearer ${tokens.accessToken}` },
      })
      if (!res.ok) {
        return
      }
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      setBookings(list)
      if (updateAll) {
        setAllBookings(list)
      }
    } catch {
      // Ignore fetch errors for the panel; chat errors are surfaced elsewhere.
    }
  }

  useEffect(() => {
    fetchBookings({}, true)
  }, [tokens.accessToken])

  const setTokenState = (accessToken, refreshToken) => {
    setTokens({ accessToken: accessToken || '', refreshToken: refreshToken || '' })
  }

  const handleLogin = async (event) => {
    event.preventDefault()
    setError('')
    setBusy(true)
    try {
      const res = await fetch(`${API_BASE}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      if (!res.ok) {
        throw new Error('Login failed. Check your credentials.')
      }
      const data = await res.json()
      setTokenState(data.access_token, data.refresh_token)
    } catch (err) {
      setError(err.message)
      setTokenState('', '')
    } finally {
      setBusy(false)
    }
  }

  const refreshAccess = async () => {
    if (!tokens.refreshToken) return false
    const res = await fetch(`${API_BASE}/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: tokens.refreshToken }),
    })
    if (!res.ok) {
      return false
    }
    const data = await res.json()
    setTokenState(data.access_token, data.refresh_token || tokens.refreshToken)
    return true
  }

  const sendMessage = async (event) => {
    event.preventDefault()
    const trimmed = message.trim()
    if (!trimmed || busy) return
    setError('')
    setBusy(true)
    setMessages((prev) => [...prev, { role: 'user', content: trimmed }])
    setMessage('')

    const attemptSend = async (accessToken) => {
      const res = await fetch(`${API_BASE}/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ message: trimmed }),
      })
      return res
    }

    try {
      let res = await attemptSend(tokens.accessToken)
      if (res.status === 401) {
        const refreshed = await refreshAccess()
        if (refreshed) {
          res = await attemptSend(localStorage.getItem(storageKeys.access) || '')
        }
      }
      if (!res.ok) {
        throw new Error('Request failed. Are you logged in?')
      }
      const data = await res.json()
      setMessages((prev) => [...prev, { role: 'assistant', content: data.reply }])
      if (isAuthed) {
        await fetchBookings({
          origin: filterOrigin,
          destination: filterDestination,
          status: filterStatus,
        })
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  const handleLogout = async () => {
    setError('')
    if (tokens.refreshToken) {
      try {
        await fetch(`${API_BASE}/logout`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: tokens.refreshToken }),
        })
      } catch {
        // Ignore network errors on logout.
      }
    }
    clearTokens()
    setTokenState('', '')
    setMessages([])
    setBookings([])
  }

  return (
    <div className="page">
      <header className="topbar">
        <div>
          <p className="eyebrow">GateReady</p>
          <h1>Secure flight answers, fast.</h1>
          <p className="subtle">
            Login, then ask about your next trip.
          </p>
        </div>
        <div className="status-chip">
          <span className={isAuthed ? 'dot ok' : 'dot idle'} />
          {isAuthed ? 'Authenticated' : 'Not logged in'}
        </div>
      </header>

      <main className="grid">
        <section className="card">
          <h2>Login</h2>
          <form onSubmit={handleLogin} className="stack">
            <label>
              Username
              <input
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="user_123"
                autoComplete="username"
              />
            </label>
            <label>
              Password
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="demo-pass"
                autoComplete="current-password"
              />
            </label>
            <button type="submit" disabled={busy}>
              {busy ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <div className="actions">
            <button type="button" className="ghost" onClick={handleLogout}>
              Logout
            </button>
          </div>
        </section>

        <section className="card bookings">
          <div className="chat-header">
            <h2>Bookings</h2>
            <span className="pill">MongoDB</span>
          </div>
          <div className="filters row">
            <select
              value={filterOrigin}
              onChange={(event) => setFilterOrigin(event.target.value)}
              disabled={!isAuthed}
            >
              <option value="">All origins</option>
              {filterOptions.origins.map((origin) => (
                <option key={origin} value={origin}>
                  {origin}
                </option>
              ))}
            </select>
            <select
              value={filterDestination}
              onChange={(event) => setFilterDestination(event.target.value)}
              disabled={!isAuthed}
            >
              <option value="">All destinations</option>
              {filterOptions.destinations.map((destination) => (
                <option key={destination} value={destination}>
                  {destination}
                </option>
              ))}
            </select>
            <select
              value={filterStatus}
              onChange={(event) => setFilterStatus(event.target.value)}
              disabled={!isAuthed}
            >
              <option value="">All statuses</option>
              {filterOptions.statuses.map((statusOption) => (
                <option key={statusOption} value={statusOption}>
                  {statusOption}
                </option>
              ))}
            </select>
            <button
              type="button"
              className="ghost"
              onClick={() => {
                setFilterOrigin('')
                setFilterDestination('')
                setFilterStatus('')
                fetchBookings({}, true)
              }}
              disabled={!isAuthed}
            >
              Clear
            </button>
            <button
              type="button"
              onClick={() =>
                fetchBookings({
                  origin: filterOrigin,
                  destination: filterDestination,
                  status: filterStatus,
                })
              }
              disabled={!isAuthed}
            >
              Apply
            </button>
          </div>
          {bookings.length === 0 ? (
            <p className="empty">
              {isAuthed ? 'No bookings yet. Create one via the API.' : 'Login to see your bookings.'}
            </p>
          ) : (
            <div className="booking-list">
              {filteredBookings.map((booking) => (
                <article key={booking.booking_id} className="booking-card">
                  <div>
                    <p className="flight">{booking.flight_number}</p>
                    <p className="route">
                      {booking.origin} → {booking.destination}
                    </p>
                  </div>
                  <div className="meta">
                    <span>{booking.date}</span>
                    <span className="status">{booking.status}</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>

        <section className="card chat">
          <div className="chat-header">
            <h2>Chat</h2>
            <span className="pill">JWT + Refresh</span>
          </div>
          <div className="messages">
            {messages.length === 0 ? (
              <p className="empty">
                Try: “Where am I flying next?”
              </p>
            ) : (
              messages.map((item, index) => (
                <div key={`${item.role}-${index}`} className={`msg ${item.role}`}>
                  <span className="role">{item.role === 'user' ? 'You' : 'Assistant'}</span>
                  <p>{item.content}</p>
                </div>
              ))
            )}
          </div>
          <form onSubmit={sendMessage} className="composer">
            <input
              type="text"
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              placeholder="Ask about your booking..."
              disabled={!isAuthed || busy}
            />
            <button type="submit" disabled={!isAuthed || busy}>
              {busy ? 'Sending...' : 'Send'}
            </button>
          </form>
        </section>
      </main>

      {error ? <div className="toast">{error}</div> : null}
    </div>
  )
}

export default App
