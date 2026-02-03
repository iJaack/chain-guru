import { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts'

function App() {
  const [chains, setChains] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [currentView, setCurrentView] = useState('dashboard') // 'dashboard', 'graveyard', 'about'

  // Pricing State
  const [pricing, setPricing] = useState({
    evm: { tps: 4000, setup: 200 },
    nonEvm: { tps: 16000, setup: 800 }
  })

  // Table State
  const [envFilter, setEnvFilter] = useState('all') // 'all', 'Mainnet', 'Testnet'
  const [sort, setSort] = useState({ key: 'tps_10min', dir: 'desc' })

  useEffect(() => {
    const fetchChains = () => {
      fetch('/api/chains')
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`)
          return res.json()
        })
        .then(data => {
          // Process Names and Environment
          const processed = data.map(c => {
            let env = 'Mainnet'
            let name = c.chain_name

            if (name.toLowerCase().includes('testnet')) {
              env = 'Testnet'
              name = name.replace(/testnet/gi, '').trim()
            } else if (name.toLowerCase().includes('mainnet')) {
              name = name.replace(/mainnet/gi, '').trim()
            }
            // Remove trailing hyphens or spaces if any
            name = name.replace(/-$/, '').trim()

            return { ...c, clean_name: name, environment: env }
          })
          setChains(processed)
          setError(null)
          setLoading(false)
        })
        .catch(err => {
          console.error("API Error:", err)
          setError(err.message || 'Failed to load data')
          setLoading(false)
        })
    }

    fetchChains()
    const interval = setInterval(fetchChains, 5 * 60 * 1000)
    return () => clearInterval(interval)
  }, [])

  // Separate live and dead chains
  const liveChains = useMemo(() => chains.filter(c => !c.is_dead), [chains])
  const deadChains = useMemo(() => chains.filter(c => c.is_dead), [chains])

  // Calculations (only for live chains)
  const stats = useMemo(() => {
    let evmTps = 0, evmHist = 0
    let nonEvmTps = 0, nonEvmHist = 0
    let mainnetTps = 0, mainnetHist = 0
    let testnetTps = 0, testnetHist = 0

    let total = 0

    liveChains.forEach(c => {
      const tps = c.tps_10min || 0
      const hist = c.total_tx_count || 0

      // Type Stats
      if (c.type === 'EVM') {
        evmTps += tps
        evmHist += hist
      } else {
        nonEvmTps += tps
        nonEvmHist += hist
      }

      // Environment Stats
      if (c.environment === 'Mainnet') {
        mainnetTps += tps
        mainnetHist += hist
      } else {
        testnetTps += tps
        testnetHist += hist
      }

      total++
    })

    const evmRev = evmTps * pricing.evm.tps + (evmHist / 1000000) * pricing.evm.setup
    const nonEvmRev = nonEvmTps * pricing.nonEvm.tps + (nonEvmHist / 1000000) * pricing.nonEvm.setup

    return {
      evm: { tps: evmTps, hist: evmHist, rev: evmRev, arr: evmTps * pricing.evm.tps * 12, setup: (evmHist / 1000000) * pricing.evm.setup },
      nonEvm: { tps: nonEvmTps, hist: nonEvmHist, rev: nonEvmRev, arr: nonEvmTps * pricing.nonEvm.tps * 12, setup: (nonEvmHist / 1000000) * pricing.nonEvm.setup },
      mainnet: { tps: mainnetTps, hist: mainnetHist },
      testnet: { tps: testnetTps, hist: testnetHist },
      total: evmRev + nonEvmRev,
      count: total
    }
  }, [liveChains, pricing])

  // Table Data for dashboard
  const sortedLiveChains = useMemo(() => {
    let filtered = liveChains

    if (envFilter !== 'all') {
      filtered = filtered.filter(c => c.environment === envFilter)
    }

    const normalizeSortValue = (value) => {
      if (value === null || value === undefined) {
        return { kind: 'empty', value: null }
      }
      if (typeof value === 'number') {
        return Number.isFinite(value) ? { kind: 'number', value } : { kind: 'empty', value: null }
      }
      if (typeof value === 'string') {
        const trimmed = value.trim()
        if (!trimmed) return { kind: 'empty', value: null }
        const numeric = Number(trimmed.replace(/,/g, ''))
        if (Number.isFinite(numeric)) {
          return { kind: 'number', value: numeric }
        }
        return { kind: 'string', value: trimmed }
      }
      if (typeof value === 'boolean') {
        return { kind: 'number', value: value ? 1 : 0 }
      }
      return { kind: 'string', value: String(value) }
    }

    const compareValues = (a, b) => {
      const valA = normalizeSortValue(a)
      const valB = normalizeSortValue(b)

      if (valA.kind === 'empty' && valB.kind === 'empty') return 0
      if (valA.kind === 'empty') return 1
      if (valB.kind === 'empty') return -1

      if (valA.kind === valB.kind) {
        if (valA.kind === 'number') {
          return valA.value - valB.value
        }
        return valA.value.localeCompare(valB.value, undefined, { numeric: true, sensitivity: 'base' })
      }

      if (valA.kind === 'number' && valB.kind === 'string') return -1
      if (valA.kind === 'string' && valB.kind === 'number') return 1
      return 0
    }

    return [...filtered].sort((a, b) => {
      const result = compareValues(a[sort.key], b[sort.key])
      return sort.dir === 'desc' ? -result : result
    })
  }, [liveChains, envFilter, sort])

  // Table Data for graveyard
  const sortedDeadChains = useMemo(() => {
    return [...deadChains].sort((a, b) => {
      const valA = a.clean_name || ''
      const valB = b.clean_name || ''
      return valA.localeCompare(valB)
    })
  }, [deadChains])

  // Formatters
  const fmtMoney = (n) => widthCheck(n) ? `$${(n / 1000000).toFixed(1)}M` : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(n)
  const fmtNum = (n) => new Intl.NumberFormat('en-US').format(Math.round(n))
  const widthCheck = (n) => n > 1000000

  const handlePriceChange = (cat, field, val) => {
    setPricing(prev => ({
      ...prev,
      [cat]: { ...prev[cat], [field]: Number(val) }
    }))
  }

  const handleSort = (key) => {
    setSort(prev => ({
      key,
      dir: prev.key === key && prev.dir === 'desc' ? 'asc' : 'desc'
    }))
  }

  if (loading) {
    return <div className="loading">Loading blockchain data...</div>
  }

  if (error) {
    return (
      <div className="loading">
        <div>Failed to load data: {error}</div>
        <button style={{ marginTop: '1rem' }} onClick={() => window.location.reload()}>Retry</button>
      </div>
    )
  }

  return (
    <div className="app-container">
      <header>
        <h1>BLOCKCHAIN REVENUE SIMULATOR</h1>
        <nav className="main-nav">
          <button
            className={currentView === 'dashboard' ? 'active' : ''}
            onClick={() => setCurrentView('dashboard')}
          >
            📊 Dashboard ({liveChains.length})
          </button>
          <button
            className={currentView === 'graveyard' ? 'active graveyard-btn' : 'graveyard-btn'}
            onClick={() => setCurrentView('graveyard')}
          >
            💀 Graveyard ({deadChains.length})
          </button>
          <button
            className={currentView === 'about' ? 'active about-btn' : 'about-btn'}
            onClick={() => setCurrentView('about')}
          >
            ℹ️ About
          </button>
        </nav>
        <div className="status">
          <span className="dot"></span> Connected to Node
        </div>
      </header>

      {currentView === 'about' ? (
        <main className="about-view">
          <section className="about-content" style={{ maxWidth: '800px', margin: '0 auto' }}>
            <div className="card about-card">
              <h2>About Chain Guru</h2>
              
              <div className="about-section">
                <h3>🌍 The Mission</h3>
                <p>
                  This website tracks all chains, alive and dead, to calculate true global throughput across all VMs.
                </p>
              </div>

              <div className="about-section">
                <h3>💰 Cost Model</h3>
                <p>
                  Infrastructure needs to pay for this. At a glance you can see the cost to run everything.
                </p>
                <p>
                  Costs are variable, and we apply a premium for non-EVM chains to reflect different infrastructure overhead.
                </p>
              </div>

              <div className="about-section">
                <h3>⚡ Real-Time Data</h3>
                <p>
                  Data is updated daily, with a goal of real-time updates.
                </p>
              </div>

              <div className="about-section donation-section" style={{ marginTop: '2rem', padding: '1.5rem', background: 'rgba(10, 255, 10, 0.05)', borderRadius: '8px', border: '1px solid rgba(10, 255, 10, 0.2)' }}>
                <h3>☕ Support the Project</h3>
                <p>If you find this data useful, consider supporting the infrastructure costs.</p>
                <p>Donation address (EVM):</p>
                <div className="wallet-address" style={{ fontFamily: 'monospace', background: '#000', padding: '1rem', borderRadius: '4px', margin: '1rem 0', wordBreak: 'break-all' }}>
                  0x0fe61780bd5508b3C99e420662050e5560608cA4
                </div>
                <p style={{ fontSize: '0.9em', opacity: 0.8 }}>(EVM)</p>
              </div>
            </div>
          </section>
        </main>
      ) : currentView === 'graveyard' ? (
        <main className="graveyard-view">
          <section className="graveyard-header">
            <div className="card graveyard-intro">
              <h2>💀 Blockchain Graveyard</h2>
              <p>
                These {deadChains.length} chains appear to be defunct - their domains no longer resolve.
                This is the final resting place for abandoned blockchain projects.
              </p>
            </div>
          </section>

          <section className="data-section">
            <div className="table-wrapper graveyard-table">
              <table>
                <thead>
                  <tr>
                    <th>Chain Name</th>
                    <th>Environment</th>
                    <th>Type</th>
                    <th>Chain ID</th>
                    <th>Last Known RPC</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedDeadChains.map(c => (
                    <tr key={c.chain_id} className="dead-row">
                      <td className="dead-name">💀 {c.clean_name}</td>
                      <td><span className="badge dead">{c.environment}</span></td>
                      <td><span className="badge dead">{c.type}</span></td>
                      <td className="chain-id">{c.chain_id}</td>
                      <td className="rpc-url">{c.rpc_url || 'N/A'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-footer graveyard-footer">
              🪦 RIP to {deadChains.length} blockchain projects
            </div>
          </section>
        </main>
      ) : (
        <main>
          {/* Hero Section */}
          <section className="hero-section" style={{ textAlign: 'center', marginBottom: '2rem', padding: '2rem', background: 'linear-gradient(180deg, rgba(10, 11, 30, 0) 0%, rgba(10, 255, 10, 0.05) 100%)', borderRadius: '12px', border: '1px solid rgba(255, 255, 255, 0.05)' }}>
            <h2 style={{ fontSize: '1.5rem', marginBottom: '0.5rem', color: '#fff' }}>Global Blockchain Throughput & Cost Simulator</h2>
            <p style={{ color: '#94a3b8', maxWidth: '600px', margin: '0 auto', lineHeight: '1.6' }}>
              Tracking the pulse of the entire blockchain ecosystem. Real-time TPS and infrastructure cost simulation across all chains and VMs (EVM, SVM, Move, Cosmos).
            </p>
          </section>

          {/* Revenue Cards */}
          <section className="kpi-grid">
            <div className="card glow-evm">
              <h3>EVM Ecosystem</h3>
              <div className="big-num">{fmtMoney(stats.evm.rev)}</div>
              <div className="sub-stats">
                <div>ARR: {fmtMoney(stats.evm.arr)}</div>
                <div>Setup: {fmtMoney(stats.evm.setup)}</div>
              </div>
            </div>

            <div className="card glow-total">
              <h3>TOTAL POTENTIAL REVENUE</h3>
              <div className="mega-num">{fmtMoney(stats.total)}</div>
              <div className="bar-container">
                <div className="bar-fill evm" style={{ width: `${stats.total > 0 ? (stats.evm.rev / stats.total) * 100 : 0}%` }}></div>
                <div className="bar-fill nonevm" style={{ width: `${stats.total > 0 ? (stats.nonEvm.rev / stats.total) * 100 : 0}%` }}></div>
              </div>
              <div className="legend">
                <span className="evm-text">EVM</span> vs <span className="nonevm-text">Non-EVM</span>
              </div>
            </div>

            <div className="card glow-nonevm">
              <h3>Non-EVM Ecosystem</h3>
              <div className="big-num">{fmtMoney(stats.nonEvm.rev)}</div>
              <div className="sub-stats">
                <div>ARR: {fmtMoney(stats.nonEvm.arr)}</div>
                <div>Setup: {fmtMoney(stats.nonEvm.setup)}</div>
              </div>
            </div>
          </section>

          {/* Charts Section - Environment Based */}
          <section className="charts-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem', marginBottom: '2rem' }}>
            <div className="card">
              <h3>TPS Distribution by Environment</h3>
              <div style={{ height: '300px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={[
                      { name: 'Mainnet', value: stats.mainnet.tps, color: '#0aff0a' },
                      { name: 'Testnet', value: stats.testnet.tps, color: '#fbbf24' }
                    ]}
                    margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="name" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0a0b1e', border: '1px solid rgba(255,255,255,0.1)' }}
                      itemStyle={{ color: '#fff' }}
                      formatter={(value) => [value.toFixed(2), "TPS"]}
                    />
                    <Bar dataKey="value">
                      {
                        [{ color: '#0aff0a' }, { color: '#fbbf24' }].map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))
                      }
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="card">
              <h3>History (Tx) by Environment</h3>
              <div style={{ height: '300px' }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart
                    data={[
                      { name: 'Mainnet', value: stats.mainnet.hist, color: '#0aff0a' },
                      { name: 'Testnet', value: stats.testnet.hist, color: '#fbbf24' }
                    ]}
                    margin={{ top: 20, right: 30, left: 20, bottom: 5 }}
                  >
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.1)" />
                    <XAxis dataKey="name" stroke="#94a3b8" />
                    <YAxis stroke="#94a3b8" tickFormatter={(value) => (value / 1000000).toFixed(0) + 'M'} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0a0b1e', border: '1px solid rgba(255,255,255,0.1)' }}
                      itemStyle={{ color: '#fff' }}
                      formatter={(value) => [(value / 1000000000).toFixed(2) + 'B', "Tx Count"]}
                    />
                    <Bar dataKey="value">
                      {
                        [{ color: '#0aff0a' }, { color: '#fbbf24' }].map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.color} />
                        ))
                      }
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </section>

          {/* Controls */}
          <section className="controls-section">
            <div className="card control-group">
              <h4>EVM Pricing</h4>
              <div className="input-row">
                <label>Price/TPS ($)</label>
                <input type="number" value={pricing.evm.tps} onChange={e => handlePriceChange('evm', 'tps', e.target.value)} />
              </div>
              <div className="input-row">
                <label>Setup/1M Tx ($)</label>
                <input type="number" value={pricing.evm.setup} onChange={e => handlePriceChange('evm', 'setup', e.target.value)} />
              </div>
            </div>

            <div className="card control-group">
              <h4>Non-EVM Pricing</h4>
              <div className="input-row">
                <label>Price/TPS ($)</label>
                <input type="number" value={pricing.nonEvm.tps} onChange={e => handlePriceChange('nonEvm', 'tps', e.target.value)} />
              </div>
              <div className="input-row">
                <label>Setup/1M Tx ($)</label>
                <input type="number" value={pricing.nonEvm.setup} onChange={e => handlePriceChange('nonEvm', 'setup', e.target.value)} />
              </div>
            </div>

            <div className="card actions">
              <h4>Actions</h4>
              <button onClick={() => setPricing({ evm: { tps: 4000, setup: 200 }, nonEvm: { tps: 16000, setup: 800 } })}>Reset to Premium</button>
              <button onClick={() => setPricing({ evm: { tps: 4000, setup: 200 }, nonEvm: { tps: 4000, setup: 200 } })}>Set Parity</button>
            </div>
          </section>

          {/* Data Table */}
          <section className="data-section">
            <div className="table-header">
              <h3>Chain Metrics ({sortedLiveChains.length})</h3>
              <div className="filters">
                <button className={envFilter === 'all' ? 'active' : ''} onClick={() => setEnvFilter('all')}>All</button>
                <button className={envFilter === 'Mainnet' ? 'active' : ''} onClick={() => setEnvFilter('Mainnet')}>Mainnet</button>
                <button className={envFilter === 'Testnet' ? 'active' : ''} onClick={() => setEnvFilter('Testnet')}>Testnet</button>
              </div>
            </div>

            <div className="table-wrapper">
              <table>
                <thead>
                  <tr>
                    <th onClick={() => handleSort('clean_name')}>Name</th>
                    <th onClick={() => handleSort('environment')}>Env</th>
                    <th onClick={() => handleSort('type')}>Type</th>
                    <th onClick={() => handleSort('health_status')}>Status</th>
                    <th onClick={() => handleSort('tps_10min')} className="right">TPS (Live)</th>
                    <th onClick={() => handleSort('total_tx_count')} className="right">History (Total Tx)</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedLiveChains.map(c => (
                    <tr key={c.chain_id}>
                      <td>{c.clean_name}</td>
                      <td><span className={`badge ${c.environment === 'Mainnet' ? 'live' : 'type'}`} style={{ color: c.environment === 'Mainnet' ? '#0aff0a' : '#fbbf24', background: 'rgba(255,255,255,0.05)' }}>{c.environment}</span></td>
                      <td><span className={`badge ${c.type}`}>{c.type}</span></td>
                      <td><span className={`status-badge ${c.health_status === 'Live' || c.health_status?.includes('Scraped') ? 'live' : 'error'}`}>{c.health_status || 'Unknown'}</span></td>
                      <td className="right">{c.tps_10min?.toFixed(2)}</td>
                      <td className="right">{fmtNum(c.total_tx_count)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-footer">Showing {sortedLiveChains.length} active chains</div>
          </section>
        </main>
      )}
    </div>
  )
}

export default App
