import csv
import sqlite3
import time
import json
import urllib.request
import ssl
import os
from datetime import datetime

DB_FILE = 'blockchain_data.db'
TIMEOUT_SECONDS = 15

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


def make_request(url, payload=None, method='GET'):
    ctx = get_ssl_context()
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    
    try:
        if payload:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
        else:
            req = urllib.request.Request(url, headers=headers, method=method)
            
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as response:
            return json.loads(response.read())
    except Exception as e:
        return None

def parse_iso_time(t_str):
    # Handle both Z and +00:00 and .microseconds
    # Example: 2026-01-22T17:12:13Z
    t_str = t_str.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(t_str).timestamp()
    except:
        # Fallback for older python or weird formats
        # 2026-01-22T17:12:13.123Z
        try:
             # Manual split
             main, _ = t_str.split('+')
             return datetime.strptime(main, "%Y-%m-%dT%H:%M:%S").timestamp()
        except:
             return time.time() # Fail safe

def measure_polkadot(chain_id, chain_name, rpc_url):
    # Try generic Substrate RPC for block HEAD
    # chain_getHeader
    try:
        # Get head
        res = make_request(rpc_url, {"jsonrpc":"2.0", "method":"chain_getHeader", "params":[], "id":1}, 'POST')
        head_num = int(res['result']['number'], 16)
        
        # Get a previous block hash (10 blocks back)
        # chain_getBlockHash
        old_num = head_num - 10
        res_hash = make_request(rpc_url, {"jsonrpc":"2.0", "method":"chain_getBlockHash", "params":[old_num], "id":1}, 'POST')
        old_hash = res_hash['result']
        
        # We need extrinsics count.
        # chain_getBlock
        # Fetching full block via RPC returns opaque "extrinsics" (hex list).
        # We can just count the list length! We don't need to decode them to know there's a TX.
        # Some are system logs, but mostly extrinsics are txs. This is a good proxy.
        
        total_ext = 0
        valid = 0
        
        # Sample 3 blocks (Head, Head-5, Head-10)
        samples = [head_num, old_num]
        
        for n in samples:
            h_res = make_request(rpc_url, {"jsonrpc":"2.0", "method":"chain_getBlockHash", "params":[n], "id":1}, 'POST')
            h_hash = h_res['result']
            blk_res = make_request(rpc_url, {"jsonrpc":"2.0", "method":"chain_getBlock", "params":[h_hash], "id":1}, 'POST')
            blk = blk_res['result']['block']
            exts = blk['extrinsics']
            total_ext += len(exts)
            valid += 1
            
        if valid == 0: return None, "error", "No valid samples"
        
        # Estimate time. Polkadot is strictly 6s.
        time_diff = (head_num - old_num) * 6.0
        
        avg_tx = total_ext / valid
        tps = total_ext / (valid * 6.0) # TPS = Avg TX per block / Block Time (6s)
        
        # Estimate Total: Height * Avg
        total_count = float(head_num) * avg_tx
        
        return tps, "success", None, total_count
        
    except Exception as e:
        return None, "error", str(e)

def measure_starknet(chain_id, chain_name, rpc_url):
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "starknet_blockNumber",
            "params": [],
            "id": 1
        }
        res = make_request(rpc_url, payload, 'POST')
        if not res or 'result' not in res: return None, "error", "Starknet RPC fail"
        latest_num = res['result']
        
        # Get block details
        # starknet_getBlockWithTxHashes
        payload = {
            "jsonrpc": "2.0",
            "method": "starknet_getBlockWithTxHashes",
            "params": [{"block_number": latest_num}],
            "id": 1
        }
        r = make_request(rpc_url, payload, 'POST')
        if not r or 'result' not in r: return None, "error", "Block fetch fail"
        
        txs = r['result']['transactions']
        count = len(txs)
        ts_now = r['result']['timestamp']
        
        # Go back 10 blocks
        old_num = latest_num - 10
        payload['params'] = [{"block_number": old_num}]
        r_old = make_request(rpc_url, payload, 'POST')
        ts_old = r_old['result']['timestamp']
        
        diff = ts_now - ts_old
        if diff <= 0: diff = 1
        
        # Just use these 2 points for avg TPS over 10 blocks?
        # Ideally sample in between.
        # But let's just use the count from latest block as proxy for instantaneous capacity?
        # No, let's avg 2 blocks.
        
        txs_old = len(r_old['result']['transactions'])
        
        avg_tx = (count + txs_old) / 2
        tps = avg_tx / ((ts_now - ts_old) / 10.0) # Avg TX / Avg Block Time
        
        # Estimate
        total_count = float(latest_num) * avg_tx
        
        return tps, "success", None, total_count
    except Exception as e:
        return None, "error", str(e)

def measure_bitcoin_fork(chain_id, chain_name, rpc_url):
    try:
        # BlockCypher
        coin = "doge" if "doge" in chain_id else "ltc"
        base_url = f"https://api.blockcypher.com/v1/{coin}/main"
        
        info = make_request(base_url)
        height = info['height']
        
        total_tx = 0
        timestamps = []
        
        for i in range(3):
            h = height - i
            b = make_request(f"{base_url}/blocks/{h}")
            # Robust parsing
            t_str = b['time']
            # Example: 2026-01-22T17:12:13.123Z or without .123
            t_str = t_str.split('.')[0].replace('Z', '')
            ts = datetime.strptime(t_str, "%Y-%m-%dT%H:%M:%S").timestamp()
            timestamps.append(ts)
            total_tx += b['n_tx']
            
        time_diff = max(timestamps) - min(timestamps)
        
        # BlockCypher might give blocks in weird or out of order arrival?
        # If time diff is small, assume standard block time? (Doge 1m, LTC 2.5m)
        if time_diff < 10:
             time_diff = 60 * 2 if coin=='doge' else 150 * 2
             
        tps = total_tx / time_diff
        
        # Estimate
        avg_tx_per_block = total_tx / 3.0
        total_count = float(height) * avg_tx_per_block
        
        return tps, "success", None, total_count
        
    except Exception as e:
        return None, "error", str(e)


def main():
    # Use alternative RPCs
    targets = [
        ("polkadot", "Polkadot", "https://rpc.polkadot.io"), # Official RPC
        ("kusama", "Kusama", "https://kusama-rpc.polkadot.io"),
        ("starknet-mainnet", "Starknet", "https://starknet-mainnet.public.blastapi.io"), # Retry
        ("dogecoin", "Dogecoin", "https://api.blockcypher.com/v1/doge/main"),
        ("litecoin", "Litecoin", "https://api.blockcypher.com/v1/ltc/main"),
    ]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("Measuring Gap Chains (Attempts 2)...")
    
    for cid, name, url in targets:
        try:
            res = None
            if "polkadot" in cid or "kusama" in cid:
                res = measure_polkadot(cid, name, url)
            elif "starknet" in cid:
                res = measure_starknet(cid, name, url)
            elif "doge" in cid or "litecoin" in cid:
                res = measure_bitcoin_fork(cid, name, url)
            elif "solana" in cid:
                res = measure_solana(cid, name, url)
            
            if res and res[1] == "success":
                tps = res[0]
                status = res[1]
                err = res[2]
                total_cnt = res[3]
                print(f"{name}: {tps:.2f} TPS")
                cursor.execute('''
                    INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (cid, name, url, tps, time.time(), status, err, total_cnt))
            else:
                print(f"{name}: Failed ({res[2] if res else 'Unknown'})")
                
        except Exception as e:
            print(f"{name}: Failed ({e})")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
