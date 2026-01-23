# Blockchain TPS Measurement Walkthrough

## Overview
We successfully created a comprehensive list of active blockchains and measured their Transactions Per Second (TPS) over a 10-minute window.

## Artifacts
- **CSV List**: `active_blockchains.csv` (2490 chains)
- **Database**: `blockchain_data.db` (SQLite)
- **Scripts**:
  - `process_chains.py`: Fetches and cleans chain data.
  - `measure_tps.py`: Estimates TPS using a sampling strategy.

## Methodology
1. **Data Collection**: Fetched chain metadata from `chainid.network`.
2. **TPS Estimation**:
   - For each chain, we determined the block range corresponding to the last 10 minutes.
   - We used a **sampling strategy** (sampling ~5 blocks) to calculate the average transaction count per block to avoid rate limits.
   - Calculated TPS = (Total Est. Transactions) / (Time Window).

## Results
- **Total Chains**: 2490 + 159 (Non-EVM)
- **Successful TPS Measurements**: 819 (EVM) + ~50 (Non-EVM)
- **Total Chains**: 2490 + 165 (Non-EVM + Gaps)
- **Successful TPS Measurements**: 819 (EVM) + ~55 (Non-EVM)
- **Top Non-EVM Chains by TPS**:
  1. Solana (~3629 TPS)
  2. Tron (~129 TPS)
  3. Sui (~85 TPS)
  4. Near (~61 TPS)
  5. Stellar (~40 TPS)
  6. Bitcoin (~7 TPS)
  7. Polkadot (~0.33 TPS)

## Non-EVM Integration
We implemented expanded coverage:
- **Cosmos Ecosystem**: Auto-discovery via Cosmos Chain Registry.
- **Major L1s**: Specific adapters for Near, Aptos, Sui, Algorand.
- **Gap Analysis**: Added Polkadot, Kusama, Dogecoin, Stellar after CoinGecko audit.

## Usage
To query the data:
```bash
sqlite3 blockchain_data.db
```
```sql
SELECT chain_name, tps_10min FROM chain_metrics WHERE status='success' ORDER BY tps_10min DESC LIMIT 10;
```

## Interactive Dashboard
A revenue simulation dashboard has been built to explore these metrics dynamically.

### Features
- **Live Revenue Calculator**: Adjust pricing for EVM vs Non-EVM and see impact on total revenue.
- **Data Explorer**: Sortable table of all 950+ chains with type-based filtering.
- **Visuals**: Real-time bar charts comparing ecosystem revenue.

### Access
**Live URL**: [https://distant-crab.vercel.app](https://distant-crab.vercel.app)
*(Backend API at `/api/chains`)*

### Source Code
- **GitHub Repo**: [https://github.com/iJaack/chain-guru](https://github.com/iJaack/chain-guru)

### Deployment Architecture
- **Frontend**: Vite + React (Served as Static Assets)
- **Backend**: FastAPI (Serverless Function at `/api`)
- **Database**: Vercel Postgres

---

