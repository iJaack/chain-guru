import sqlite3
import time
import json
import urllib.request
import ssl
import os

DB_FILE = 'blockchain_data.db'

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS chain_metrics (
            chain_id TEXT PRIMARY KEY,
            chain_name TEXT,
            rpc_url TEXT,
            tps_10min REAL,
            last_updated_at REAL,
            status TEXT,
            error_message TEXT,
            total_tx_count REAL,
            health_status TEXT,
            is_dead INTEGER DEFAULT 0,
            explorer_url TEXT,
            x_handle TEXT
        )
    ''')
    for stmt in [
        "ALTER TABLE chain_metrics ADD COLUMN total_tx_count REAL",
        "ALTER TABLE chain_metrics ADD COLUMN health_status TEXT",
        "ALTER TABLE chain_metrics ADD COLUMN is_dead INTEGER DEFAULT 0",
        "ALTER TABLE chain_metrics ADD COLUMN explorer_url TEXT",
        "ALTER TABLE chain_metrics ADD COLUMN x_handle TEXT",
    ]:
        try:
            cursor.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()

def get_ssl_context():
    if os.environ.get("INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def make_request(url, payload=None):
    ctx = get_ssl_context()
    
    if payload:
        req = urllib.request.Request(
            url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
    else:
        req = urllib.request.Request(
            url,
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        
    with urllib.request.urlopen(req, timeout=10, context=ctx) as response:
        return response.read()

def measure_bitcoin_mempool():
    # Use mempool.space API
    try:
        # Get last 10 blocks
        data = make_request("https://mempool.space/api/v1/blocks")
        blocks = json.loads(data)
        
        # Take last 3-4 blocks
        # blocks is a list of objects with 'tx_count' and 'timestamp'
        
        if len(blocks) < 2:
             return None, "error", "Not enough blocks"
             
        # Sum tx count
        sample = blocks[:3]
        total_tx = sum(b['tx_count'] for b in sample)
        
        # Time diff
        latest_time = sample[0]['timestamp']
        oldest_time = sample[-1]['timestamp']
        
        diff = latest_time - oldest_time
        if diff == 0: diff = 1
        
        tps = total_tx / diff
        return tps, "success", None
    except Exception as e:
        return None, "error", str(e)

def measure_tron_trongrid():
    try:
        # TronGrid API
        # getnowblock
        url = "https://api.trongrid.io/wallet/getnowblock"
        data = make_request(url, payload={"id": 1}) # Payload might be empty or specific
        # Actually standard REST call for Tron is POST
        
        now_blk = json.loads(data)
        now_num = now_blk['block_header']['raw_data']['number']
        now_ts = now_blk['block_header']['raw_data']['timestamp']
        
        # Go back 200 blocks (Tron is fast, 3s blocks) -> 600s = 200 blocks
        # getblockbynum
        
        old_num = now_num - 200
        url_old = "https://api.trongrid.io/wallet/getblockbynum"
        data_old = make_request(url_old, payload={"num": old_num})
        old_blk = json.loads(data_old)
        
        if not old_blk:
             return None, "error", "Could not fetch old block"
             
        old_ts = old_blk['block_header']['raw_data']['timestamp']
        
        # Time diff (ms to s)
        time_diff = (now_ts - old_ts) / 1000.0
        if time_diff <= 0: time_diff = 1
        
        # For Tx count, Tron blocks have "transactions" list
        # Since we can't fetch ALL 200 blocks easily without rate limits, we Sample.
        # Sample 5 blocks
        sample_indices = [now_num - i*40 for i in range(5)]
        total_tx = 0
        valid = 0
        
        for idx in sample_indices:
            try:
                d = make_request(url_old, payload={"num": idx})
                b = json.loads(d)
                txs = b.get('transactions', [])
                total_tx += len(txs)
                valid += 1
                time.sleep(0.5) # Rate limit backoff
            except:
                pass
        
        if valid == 0:
             return None, "error", "No valid samples"
             
        avg_tx = total_tx / valid
        total_est = avg_tx * 200
        
        tps = total_est / time_diff
        return tps, "success", None
        
    except Exception as e:
        return None, "error", str(e)

def main():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Bitcoin
    print("Measuring Bitcoin...")
    tps, status, error = measure_bitcoin_mempool()
    print(f"BTC: {tps} ({status})")
    cursor.execute('''
        INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', ("bitcoin-mainnet", "Bitcoin", "https://mempool.space/api", tps, time.time(), status, error))
    
    # 2. Tron
    print("Measuring Tron...")
    tps, status, error = measure_tron_trongrid()
    print(f"Tron: {tps} ({status})")
    cursor.execute('''
        INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', ("tron-mainnet", "Tron Mainnet", "https://api.trongrid.io", tps, time.time(), status, error))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
