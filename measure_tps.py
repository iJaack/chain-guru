import csv
import sqlite3
import time
import json
import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import math
import random

# Configuration
DB_FILE = 'blockchain_data.db'
CSV_FILE = 'active_blockchains.csv'
MAX_WORKERS = 50
TIMEOUT_SECONDS = 15
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

def make_rpc_request(url, payload):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(
        url, 
        data=json.dumps(payload).encode('utf-8'), 
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as response:
        return json.loads(response.read())

def get_block_evm(rpc_url, block_identifier='latest', request_id=1):
    payload = {
        "jsonrpc": "2.0",
        "method": "eth_getBlockByNumber",
        "params": [block_identifier, False],
        "id": request_id
    }
    result = make_rpc_request(rpc_url, payload)
    return result.get('result')

def measure_evm(chain_id, chain_name, rpc_url):
    try:
        latest_block = get_block_evm(rpc_url, 'latest')
        if not latest_block:
             return None, "error", "Could not fetch latest block"
        
        latest_num = int(latest_block['number'], 16)
        latest_timestamp = int(latest_block['timestamp'], 16)
        
        # Estimate 10 mins ago
        lookback = 100
        start_num_estimate = max(0, latest_num - lookback)
        start_block = get_block_evm(rpc_url, hex(start_num_estimate))
        
        if not start_block:
             start_num_estimate = max(0, latest_num - 1)
             start_block = get_block_evm(rpc_url, hex(start_num_estimate))
             if not start_block:
                 return None, "error", "Could not fetch start block"

        start_timestamp = int(start_block['timestamp'], 16)
        time_diff = latest_timestamp - start_timestamp
        if time_diff == 0: time_diff = 1

        avg_block_time = time_diff / (latest_num - start_num_estimate) if (latest_num - start_num_estimate) > 0 else 1
        target_time_window = 600
        blocks_needed = int(target_time_window / avg_block_time) if avg_block_time > 0 else 1
        actual_start_num = max(0, latest_num - blocks_needed)
        
        actual_start_block = get_block_evm(rpc_url, hex(actual_start_num))
        if not actual_start_block:
             return None, "error", "Could not fetch calculated start block"
             
        actual_start_timestamp = int(actual_start_block['timestamp'], 16)
        actual_time_diff = latest_timestamp - actual_start_timestamp
        if actual_time_diff <= 0: actual_time_diff = 1

        total_blocks_in_range = latest_num - actual_start_num
        if total_blocks_in_range <= SAMPLE_SIZE:
            sample_blocks = range(actual_start_num + 1, latest_num + 1)
        else:
            step = total_blocks_in_range // SAMPLE_SIZE
            sample_blocks = [actual_start_num + 1 + i*step for i in range(SAMPLE_SIZE)]
            sample_blocks = [b for b in sample_blocks if b <= latest_num]

        total_tx_in_sample = 0
        valid_samples = 0
        
        for blk_num in sample_blocks:
            blk = get_block_evm(rpc_url, hex(blk_num))
            if blk:
                txs = blk.get('transactions', [])
                total_tx_in_sample += len(txs)
                valid_samples += 1
        
        if valid_samples == 0:
             return None, "error", "Could not sample any blocks"

        avg_tx_per_block = total_tx_in_sample / valid_samples
        estimated_total_tx = avg_tx_per_block * total_blocks_in_range
        tps = estimated_total_tx / actual_time_diff
        return tps, "success", None
        
    except Exception as e:
        return None, "error", str(e)

def measure_solana(chain_id, chain_name, rpc_url):
    try:
        # Solana getRecentPerformanceSamples
        payload = {
            "jsonrpc": "2.0", 
            "id": 1, 
            "method": "getRecentPerformanceSamples", 
            "params": [4] # Get last 4 samples (usually 60s each)
        }
        result = make_rpc_request(rpc_url, payload)
        samples = result.get('result', [])
        
        if not samples:
            return None, "error", "No performance samples found"
            
        total_tx = sum(s['numTransactions'] for s in samples)
        total_time = sum(s['samplePeriodSecs'] for s in samples)
        
        if total_time == 0:
            return None, "error", "Zero sample time"
            
        tps = total_tx / total_time
        return tps, "success", None
    except Exception as e:
        return None, "error", str(e)

def measure_bitcoin(chain_id, chain_name, rpc_url):
    # Bitcoin is hard without a full indexer via RPC.
    # Public RPCs often block 'getblock' with verbosity 2 (txs).
    # We will try 'getblockchaininfo' to get height, then 'getblockhash' -> 'getblock'
    try:
        # 1. Get info
        info = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblockchaininfo", "params": []})
        latest_height = info['result']['blocks']
        
        # 2. Get latest block
        latest_hash_res = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblockhash", "params": [latest_height]})
        latest_hash = latest_hash_res['result']
        
        latest_block_res = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblock", "params": [latest_hash, 1]}) # 1 for verbose info (header + txids)
        latest_block = latest_block_res['result']
        
        latest_time = latest_block['time']
        
        # Go back ~2 blocks (Bitcoin is slow, 10 mins is ~1 block)
        # We'll fetch 3 blocks to average.
        
        total_tx = 0
        total_time = 0
        
        # Sample last 3 blocks
        for i in range(3):
            height = latest_height - i
            if height < 0: break
            
            h_res = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblockhash", "params": [height]})
            b_res = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblock", "params": [h_res['result'], 1]})
            blk = b_res['result']
            
            total_tx += len(blk['tx'])
        
        # Time window estimate: Time of latest - Time of (latest-3)
        # Wait, TPS = sum(tx) / (time_latest - time_oldest)
        
        oldest_height = max(0, latest_height - 3)
        h_res_old = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblockhash", "params": [oldest_height]})
        b_res_old = make_rpc_request(rpc_url, {"jsonrpc": "1.0", "id":"curltest", "method": "getblock", "params": [h_res_old['result'], 1]})
        oldest_time = b_res_old['result']['time']
        
        time_diff = latest_time - oldest_time
        if time_diff == 0: time_diff = 1 # Avoid div zero
        
        # We counted txs for 3 blocks. The time diff is roughly time for 3 blocks.
        tps = total_tx / time_diff
        return tps, "success", None
        
    except Exception as e:
        return None, "error", str(e)


def measure_chain_dispatcher(chain_info):
    chain_name, chain_id, rpc_url = chain_info
    
    if not rpc_url or rpc_url == 'N/A':
        return chain_id, chain_name, rpc_url, None, "skipped_no_rpc", "No RPC URL"
    
    # Simple heuristic dispatcher
    if "solana" in chain_name.lower():
        tps, status, error = measure_solana(chain_id, chain_name, rpc_url)
    elif "bitcoin" == chain_name.lower():
        tps, status, error = measure_bitcoin(chain_id, chain_name, rpc_url)
    else:
        # Default to EVM
        tps, status, error = measure_evm(chain_id, chain_name, rpc_url)
        
    return chain_id, chain_name, rpc_url, tps, status, error

def main():
    init_db()
    
    chains = []
    
    # 1. EVM Chains from CSV
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                chains.append((row['Chain Name'], row['Chain ID'], row['Main RPC Option']))
    except FileNotFoundError:
        print(f"{CSV_FILE} not found. Proceeding with hardcoded non-EVMs only.")

    # 2. Add Non-EVM Chains (Hardcoded for this task)
    non_evm_chains = [
        ("Solana Mainnet", "solana-mainnet", "https://api.mainnet-beta.solana.com"),
        ("Bitcoin", "bitcoin-mainnet", "https://bitcoin-mainnet-archive.allthatnode.com"), # Public Bitcoin RPC
        ("Tron Mainnet", "tron-mainnet", "https://api.trongrid.io/jsonrpc"), # Tron supports eth-like RPC on some endpoints or custom
    ]
    # For Tron, the URL above supports standard JSON-RPC but methods might differ. 
    # Actually Tron Grid exposes `eth_` compatible methods on a different URL or needs specific one.
    # Let's start with Solana and Bitcoin which are high priority.
    
    # Add non-EVMs to the list
    for name, cid, rpc in non_evm_chains:
        # Check if already exists to avoid duplicates if re-running
        exists = False
        for c in chains:
            if c[1] == cid: exists = True
        if not exists:
            chains.append((name, cid, rpc))

    print(f"Starting TPS measurement for {len(chains)} chains with {MAX_WORKERS} workers...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_chain = {executor.submit(measure_chain_dispatcher, chain): chain for chain in chains}
        
        for future in as_completed(future_to_chain):
            chain_id, chain_name, rpc_url, tps, status, error = future.result()
            
            health = "Live" if status == 'success' else error
            
            cursor.execute('''
                INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, health_status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chain_id, chain_name, rpc_url, tps, time.time(), status, error, health))
            
            if completed % 10 == 0:
                conn.commit()
                print(f"Progress: {completed}/{len(chains)} chains processed.", end='\r')
            
            completed += 1

    conn.commit()
    conn.close()
    print(f"\nCompleted. Processed {completed} chains.")

if __name__ == "__main__":
    main()
