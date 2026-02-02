import urllib.request
import json
import sqlite3
import os
import csv
from utils import get_ssl_context

DB_FILE = 'blockchain_data.db'


def make_request(url):
    ctx = get_ssl_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
        return json.loads(response.read())

def get_existing_chains():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, chain_name FROM chain_metrics")
    rows = cursor.fetchall()
    conn.close()
    # Normalize names for comparison
    return {r[1].lower(): r[0] for r in rows}

def fetch_coingecko_chains():
    print("Fetching CoinGecko top chains...")
    # This endpoint returns all coins. Use markets to get top by mcap.
    # https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1
    url = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=100&page=1"
    try:
        data = make_request(url)
        return data
    except Exception as e:
        print(f"CoinGecko API Error: {e}")
        return []

def main():
    existing = get_existing_chains()
    cg_chains = fetch_coingecko_chains()
    
    missing_majors = []
    
    # Keyword overlap check
    # Many coins are tokens on other chains. verifying if they represent a unique chain.
    # Known L1 metrics usually have 'network', 'protocol', 'chain' in name or are well known identifiers.
    
    # Manual map or heuristic?
    # We look for "Layer 1" or independent chains. CoinGecko doesn't strictly label this in simple endpoint.
    # But we can check if the name is close to something we have.
    
    for c in cg_chains:
        name = c['name']
        cid = c['id']
        symbol = c['symbol']
        
        # Check if we have it
        found = False
        for ex_name in existing:
            if name.lower() in ex_name or ex_name in name.lower() or cid in ex_name:
                found = True
                break
        
        if not found:
            # Filter tokens (heuristic)
            # This is hard. But let's just list the top missing ones and decide.
            # Stablecoins (USDT, USDC) are tokens.
            # Staked ETH (stETH) is token.
            if symbol.lower() in ['usdt', 'usdc', 'steth', 'wbtc', 'dai']:
                continue
                
            missing_majors.append((name, cid))

    print(f"\n--- Gap Analysis (Top 100 on CG) ---")
    print(f"Found {len(missing_majors)} potential missing chains or naming mismatches:")
    
    # Write to a CSV for "to-do" list
    with open('missing_chains.csv', 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['Name', 'ID', 'Note'])
        for m in missing_majors:
            print(f"- {m[0]} ({m[1]})")
            writer.writerow([m[0], m[1], 'Check if L1'])

if __name__ == "__main__":
    main()
