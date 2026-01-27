import argparse
import json
import sqlite3
import time
import urllib.request
import ssl
import os
from pathlib import Path

DB_FILE = "blockchain_data.db"
COINGECKO_LIST_URL = "https://api.coingecko.com/api/v3/coins/list"
COINGECKO_COIN_URL = "https://api.coingecko.com/api/v3/coins/{id}?localization=false&tickers=false&market_data=false&community_data=true&developer_data=false&sparkline=false"


def get_ssl_context():
    if os.environ.get("INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def make_request(url, retries=5, backoff=10):
    ctx = get_ssl_context()
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as response:
                return json.loads(response.read())
        except Exception as e:
            # Backoff for rate limits / transient errors
            msg = str(e)
            if "HTTP Error 429" in msg:
                wait = 60 * (i + 1)
            else:
                wait = backoff * (i + 1)
            print(f"Request failed ({e}). Retrying in {wait}s...")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch after {retries} retries: {url}")


def normalize(name: str) -> str:
    if not name:
        return ""
    n = name.lower().strip()
    for suffix in [" mainnet", " network", " chain", " blockchain"]:
        if n.endswith(suffix):
            n = n[: -len(suffix)].strip()
    return n


def get_chains(conn):
    cur = conn.cursor()
    cur.execute("SELECT chain_id, chain_name, x_handle FROM chain_metrics")
    return cur.fetchall()


def ensure_column(conn):
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE chain_metrics ADD COLUMN x_handle TEXT")
        conn.commit()
        print("Added x_handle column to chain_metrics.")
    except Exception:
        conn.rollback()


def main():
    p = argparse.ArgumentParser(description="Scout X (Twitter) accounts for chains")
    p.add_argument("--db", default=DB_FILE)
    p.add_argument("--sleep", type=float, default=1.0, help="sleep between CoinGecko calls")
    p.add_argument("--force", action="store_true", help="re-scan even if x_handle is already set")
    p.add_argument("--max", type=int, default=0, help="limit number of chain lookups (0=all)")
    p.add_argument("--refresh-list", action="store_true", help="refresh CoinGecko list cache")
    p.add_argument("--list-cache", default="data/coingecko_coins_list.json")
    args = p.parse_args()

    conn = sqlite3.connect(args.db)
    ensure_column(conn)

    cache_path = Path(args.list_cache)
    if cache_path.exists() and not args.refresh_list:
        print(f"Loading CoinGecko coin list cache: {cache_path}")
        coins = json.loads(cache_path.read_text())
    else:
        print("Fetching CoinGecko coin list...")
        coins = make_request(COINGECKO_LIST_URL)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(coins))

    # Build lookup map by normalized name
    by_name = {}
    for c in coins:
        name = normalize(c.get("name", ""))
        if name and name not in by_name:
            by_name[name] = c.get("id")

    rows = get_chains(conn)
    updates = 0
    checked = 0

    for chain_id, chain_name, x_handle in rows:
        if not args.force and x_handle:
            continue

        if not chain_name:
            continue

        n = normalize(chain_name)
        if not n or "testnet" in n:
            continue

        coin_id = by_name.get(n)
        if not coin_id:
            # Try shorter normalization if name has parenthetical
            if "(" in n:
                base = n.split("(")[0].strip()
                coin_id = by_name.get(base)

        if not coin_id:
            continue

        checked += 1
        if args.max and checked > args.max:
            break

        try:
            data = make_request(COINGECKO_COIN_URL.format(id=coin_id))
            handle = data.get("links", {}).get("twitter_screen_name")
            if handle:
                cur = conn.cursor()
                cur.execute("UPDATE chain_metrics SET x_handle = ? WHERE chain_id = ?", (handle, chain_id))
                conn.commit()
                updates += 1
                print(f"{chain_name}: @{handle}")
        except Exception as e:
            print(f"Error for {chain_name}: {e}")

        time.sleep(args.sleep)

    conn.close()
    print(f"Done. Updated {updates} chains with X handles.")


if __name__ == "__main__":
    main()
