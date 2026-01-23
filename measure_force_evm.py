import json
import sqlite3
import time
import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# Configuration
DB_FILE = 'blockchain_data.db'
CHAINS_JSON_URL = "https://chainid.network/chains.json"
MAX_WORKERS = 100 # Aggressive parallelism
TIMEOUT_SECONDS = 10
SAMPLE_SIZE = 5

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
            health_status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def make_request(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            return json.loads(response.read())
    except:
        return []

def get_block_evm(rpc_url, block_identifier='latest', request_id=1):
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getBlockByNumber",
        "params": [block_identifier, False],
        "id": request_id
    }
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    try:
        req = urllib.request.Request(
            rpc_url, 
            data=json.dumps(payload).encode('utf-8'), 
            headers={'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as response:
            result = json.loads(response.read())
            return result.get('result')
    except:
        return None

def measure_evm(chain_id, chain_name, rpc_url):
    # Same logic as before
    try:
        latest_block = get_block_evm(rpc_url, 'latest')
        if not latest_block: return None, "error", "No latest block"
        
        latest_num = int(latest_block['number'], 16)
        latest_timestamp = int(latest_block['timestamp'], 16)
        
        # Estimate 10 mins ago
        # Attempt to get block 100 ago
        lookback = 100
        start_num_estimate = max(0, latest_num - lookback)
        start_block = get_block_evm(rpc_url, hex(start_num_estimate))
        
        if not start_block:
             # Fast failover
             start_num_estimate = max(0, latest_num - 10)
             start_block = get_block_evm(rpc_url, hex(start_num_estimate))
             if not start_block: return None, "error", "No start block"
             
        start_timestamp = int(start_block['timestamp'], 16)
        time_diff = latest_timestamp - start_timestamp
        if time_diff == 0: time_diff = 1
        
        avg_block_time = time_diff / (latest_num - start_num_estimate)
        
        # Target 600s
        blocks_needed = int(600 / avg_block_time) if avg_block_time > 0 else 1
        actual_start_num = max(0, latest_num - blocks_needed)
        
        # Fetch actual start
        actual_start_block = get_block_evm(rpc_url, hex(actual_start_num))
        if not actual_start_block:
             # Just use what we have if we can't go back far enough?
             # Let's be strict for accuracy, or relax for coverage?
             # Relax: Use start_block we found if it's > 60s ago?
             if time_diff > 60:
                 actual_start_num = start_num_estimate
                 actual_start_block = start_block
             else:
                 return None, "error", "Cannot seek start block"
                 
        actual_start_timestamp = int(actual_start_block['timestamp'], 16)
        total_time = latest_timestamp - actual_start_timestamp
        if total_time <= 0: total_time = 1
        
        # Sample
        total_range = latest_num - actual_start_num
        if total_range <= SAMPLE_SIZE:
             samples = range(actual_start_num + 1, latest_num + 1)
        else:
             step = total_range // SAMPLE_SIZE
             samples = [actual_start_num + 1 + i*step for i in range(SAMPLE_SIZE)]
             samples = [x for x in samples if x <= latest_num]
             
        total_tx = 0
        valid = 0
        for n in samples:
            blk = get_block_evm(rpc_url, hex(n))
            if blk:
                total_tx += len(blk.get('transactions', []))
                valid += 1
        
        if valid == 0: return None, "error", "No valid samples"
        
        avg_tx = total_tx / valid
        tps = (avg_tx * total_range) / total_time
        
        # Estimate Total Tx Count
        # Total = Height * Avg_Tx_Per_Block
        total_tx_count = float(latest_num) * avg_tx
        
        return tps, "success", None, total_tx_count
        
    except Exception as e:
        return None, "error", str(e)


def process_chain_failover(chain_item):
    name = chain_item.get('name')
    chain_id = str(chain_item.get('chainId'))
    rpcs = chain_item.get('rpc', [])
    
    # Filter bad RPCs
    candidate_rpcs = [r for r in rpcs if '${' not in r and 'wss://' not in r]
    
    if not candidate_rpcs:
        return chain_id, name, None, None, "skipped_no_rpc", "No valid RPCs", 0
    
    # Randomize to distribute load if running massively?
    # Or strict order? Strict order usually puts best first.
    
    for rpc in candidate_rpcs:
        result = measure_evm(chain_id, name, rpc)
        if result and result[1] == 'success':
            # result is (tps, status, err, total_tx_count)
            return chain_id, name, rpc, result[0], "success", None, result[3]
    
    return chain_id, name, candidate_rpcs[0], None, "error", "All RPCs failed", 0

def main():
    init_db()
    
    print("Downloading full chain list...")
    full_data = make_request(CHAINS_JSON_URL)
    if not full_data:
        print("Failed to download chains.json")
        return
        
    print(f"Loaded {len(full_data)} chains.")
    
    # Force re-run for everyone to get total_tx_count
    # cursor.execute("SELECT chain_id FROM chain_metrics WHERE status='success'")
    # existing = {r[0] for r in cursor.fetchall()}
    existing = set()
    
    # We want to retry EVERYTHING that isn't already success? 
    # OR retry everything period?
    # User said "force counting for all chains". 
    # Let's filter out Non-EVMs (strings) from this specific EVM script to avoid overwriting them with failures.
    # The full_data is all EVM (ChainID list).
    
    targets = []
    for c in full_data:
        cid = str(c['chainId'])
        if cid not in existing:
            targets.append(c)
            
    print(f"Targeting {len(targets)} chains for Force Measurement (excluding {len(existing)} already successful)...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_chain = {executor.submit(process_chain_failover, c): c for c in targets}
        
        for future in as_completed(future_to_chain):
            cid, name, rpc, tps, status, err, total_cnt = future.result()
            
            if status == 'success':
                health = "Live"
                cursor.execute('''
                    INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count, health_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (cid, name, rpc, tps, time.time(), status, err, total_cnt, health))
            
            completed += 1
            if completed % 10 == 0:
                conn.commit()
                print(f"Progress: {completed}/{len(targets)} chains.", end='\r')
                
    conn.commit()
    conn.close()
    print("\nForce Measurement Complete.")

if __name__ == "__main__":
    main()
