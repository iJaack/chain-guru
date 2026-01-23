import { useState, useEffect, useMemo } from 'react'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer, Cell } from 'recharts'

function App() {
  const [chains, setChains] = useState([])
  const [loading, setLoading] = useState(true)

  // Pricing State
  const [pricing, setPricing] = useState({
    evm: { tps: 4000, setup: 200 },
    nonEvm: { tps: 16000, setup: 800 }
  })

  // Table State
  const [filter, setFilter] = useState('all') // 'all', 'EVM', 'Non-EVM'
  const [sort, setSort] = useState({ key: 'tps_10min', dir: 'desc' })

  useEffect(() => {
    fetch('/api/chains')
      .then(res => res.json())
      .then(data => {
        setChains(data)
        setLoading(false)
      })
      .catch(err => console.error("API Error:", err))
  }, [])

  // Calculations
  const stats = useMemo(() => {
    let evmTps = 0, evmHist = 0, evmCount = 0
    let nonEvmTps = 0, nonEvmHist = 0, nonEvmCount = 0

    chains.forEach(c => {
      const tps = c.tps_10min || 0
      const hist = c.total_tx_count || 0

      if (c.type === 'EVM') {
        evmTps += tps
        evmHist += hist
        evmCount++
      } else {
        nonEvmTps += tps
        nonEvmHist += hist
        nonEvmCount++
      }
    })

    // Revenue
    const evmArr = evmTps * pricing.evm.tps
    const evmSetup = (evmHist / 1000000) * pricing.evm.setup
    const evmTotal = evmArr + evmSetup

    const nonEvmArr = nonEvmTps * pricing.nonEvm.tps
    const nonEvmSetup = (nonEvmHist / 1000000) * pricing.nonEvm.setup
    const nonEvmTotal = nonEvmArr + nonEvmSetup

    return {
      evm: { tps: evmTps, hist: evmHist, count: evmCount, rev: evmTotal, arr: evmArr, setup: evmSetup },
      nonEvm: { tps: nonEvmTps, hist: nonEvmHist, count: nonEvmCount, rev: nonEvmTotal, arr: nonEvmArr, setup: nonEvmSetup },
      total: evmTotal + nonEvmTotal
    }
  }, [chains, pricing])

  // Table Data
  const sortedChains = useMemo(() => {
    let filtered = chains
    if (filter !== 'all') {
      filtered = chains.filter(c => c.type === filter)
    }

    return [...filtered].sort((a, b) => {
      const valA = a[sort.key] || 0
      const valB = b[sort.key] || 0
      return sort.dir === 'desc' ? valB - valA : valA - valB
    })
  }, [chains, filter, sort])

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

  return (
    <div className="app-container">
      <header>
        <h1>BLOCKCHAIN REVENUE SIMULATOR</h1>
        <div className="status">
          <span className="dot"></span> Connected to Node
        </div>
      </header>

      <main>
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
              <div className="bar-fill evm" style={{ width: `${(stats.evm.rev / stats.total) * 100}%` }}></div>
              <div className="bar-fill nonevm" style={{ width: `${(stats.nonEvm.rev / stats.total) * 100}%` }}></div>
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



        {/* Charts Section */}
        <section className="charts-grid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px', marginBottom: '40px' }}>
          <div className="card">
            <h3>TPS Distribution</h3>
            <div style={{ height: '300px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[
                    { name: 'EVM', value: stats.evm.tps, color: '#00f3ff' },
                    { name: 'Non-EVM', value: stats.nonEvm.tps, color: '#bc13fe' }
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
                      [{ color: '#00f3ff' }, { color: '#bc13fe' }].map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.color} />
                      ))
                    }
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="card">
            <h3>Transaction History</h3>
            <div style={{ height: '300px' }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={[
                    { name: 'EVM', value: stats.evm.hist, color: '#00f3ff' },
                    { name: 'Non-EVM', value: stats.nonEvm.hist, color: '#bc13fe' }
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
                      [{ color: '#00f3ff' }, { color: '#bc13fe' }].map((entry, index) => (
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
            <h3>Chain Metrics ({sortedChains.length})</h3>
            <div className="filters">
              <button className={filter === 'all' ? 'active' : ''} onClick={() => setFilter('all')}>All</button>
              <button className={filter === 'EVM' ? 'active' : ''} onClick={() => setFilter('EVM')}>EVM</button>
              <button className={filter === 'Non-EVM' ? 'active' : ''} onClick={() => setFilter('Non-EVM')}>Non-EVM</button>
            </div>
          </div>

          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th onClick={() => handleSort('chain_name')}>Name</th>
                  <th onClick={() => handleSort('type')}>Type</th>
                  <th onClick={() => handleSort('health_status')}>Status</th>
                  <th onClick={() => handleSort('tps_10min')} className="right">TPS (Live)</th>
                  <th onClick={() => handleSort('total_tx_count')} className="right">History (Total Tx)</th>
                </tr>
              </thead>
              <tbody>
                {sortedChains.map(c => (
                  <tr key={c.chain_id}>
                    <td>{c.chain_name}</td>
                    <td><span className={`badge ${c.type}`}>{c.type}</span></td>
                    <td><span className={`status-badge ${c.health_status === 'Live' ? 'live' : 'error'}`}>{c.health_status || 'Unknown'}</span></td>
                    <td className="right">{c.tps_10min?.toFixed(2)}</td>
                    <td className="right">{fmtNum(c.total_tx_count)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-footer">Showing all {chains.length} chains</div>
        </section>
      </main>
    </div >
  )
}

export default App
