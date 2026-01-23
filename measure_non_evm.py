import csv
import sqlite3
import time
import json
import urllib.request
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed
import random

# Configuration
DB_FILE = 'blockchain_data.db'
NON_EVM_CSV = 'non_evm_chains.csv'
MAX_WORKERS = 50
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
            error_message TEXT
        )
    ''')
    conn.commit()
    conn.close()

def make_request(url, payload=None, method='GET'):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    
    if payload:
        data = json.dumps(payload).encode('utf-8')
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
    else:
        req = urllib.request.Request(url, headers=headers, method=method)
        
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as response:
        return json.loads(response.read())

# --- Adapters ---

def measure_cosmos(chain_id, chain_name, rpc_url):
    # Cosmos REST API: /cosmos/base/tendermint/v1beta1/blocks/latest
    # Transactions in /cosmos/tx/v1beta1/txs?events=... is hard.
    # Better: /cosmos/base/tendermint/v1beta1/blocks/{height}
    # It contains "block" -> "data" -> "txs" (list of base64 strings)
    try:
        # 1. Latest Block
        base_url = rpc_url.rstrip('/')
        latest_url = f"{base_url}/cosmos/base/tendermint/v1beta1/blocks/latest"
        latest_res = make_request(latest_url)
        latest_block = latest_res.get('block')
        if not latest_block:
             # Try /blocks/latest (older standard)
             latest_url = f"{base_url}/blocks/latest"
             latest_res = make_request(latest_url)
             latest_block = latest_res.get('block')
             if not latest_block: return None, "error", "Could not fetch latest block"

        header = latest_block['header']
        latest_height = int(header['height'])
        latest_time_str = header['time'] # ISO format "2023-10-...Z"
        # Parse simple ISO
        # Python 3.7+ can use fromisoformat but let's be robust
        latest_time = time.mktime(time.strptime(latest_time_str.split('.')[0], "%Y-%m-%dT%H:%M:%S"))

        # 2. Go back ~50 blocks. Cosmos is 6s usually, so 50 blocks is ~5 mins.
        lookback = 50
        start_height = max(1, latest_height - lookback)
        
        start_url = f"{base_url}/cosmos/base/tendermint/v1beta1/blocks/{start_height}"
        try:
             start_res = make_request(start_url)
        except:
             # fallback older api
             start_url = f"{base_url}/blocks/{start_height}"
             start_res = make_request(start_url)
             
        start_block = start_res.get('block')
        if not start_block: return None, "error", "Could not fetch start block"

        start_time_str = start_block['header']['time']
        start_time = time.mktime(time.strptime(start_time_str.split('.')[0], "%Y-%m-%dT%H:%M:%S"))
        
        time_diff = latest_time - start_time
        if time_diff <= 0: time_diff = 1 # Avoid div zero
        
        # 3. Count TXs in this range
        # We can just sum them up if we sampled, but here we can iterate all 50 if fast enough
        # Or sample 10.
        
        sample_size = 10
        step = max(1, (latest_height - start_height) // sample_size)
        sample_heights = range(start_height, latest_height + 1, step)[:sample_size]
        
        total_tx = 0
        valid_samples = 0
        
        for h in sample_heights:
            try:
                if 'cosmos/base' in latest_url:
                     u = f"{base_url}/cosmos/base/tendermint/v1beta1/blocks/{h}"
                else:
                     u = f"{base_url}/blocks/{h}"
                
                res = make_request(u)
                txs = res.get('block', {}).get('data', {}).get('txs', [])
                total_tx += len(txs)
                valid_samples += 1
            except: pass
            
        if valid_samples == 0: return None, "error", "No valid samples"
        
        avg_tx = total_tx / valid_samples
        total_range = latest_height - start_height
        
        tps = (avg_tx * total_range) / time_diff
        
        # Estimate total: height * avg
        total_count = float(latest_height) * avg_tx
        
        return tps, "success", None, total_count
        
    except Exception as e:
        return None, "error", str(e)

def measure_aptos(chain_id, chain_name, rpc_url):
    # Aptos REST: /v1/blocks/by_height/{height}?with_transactions=true
    # Or /v1/ledger gives latest height
    try:
        base_url = rpc_url.rstrip('/')
        ledger_res = make_request(f"{base_url}/v1")
        latest_height = int(ledger_res['block_height'])
        latest_time = int(ledger_res['ledger_timestamp']) / 1_000_000 # microseconds to seconds
        
        # Go back 1000 blocks (Aptos is fast)
        start_height = max(1, latest_height - 1000)
        
        # Get start usage
        # We can't efficiently get random blocks without fetching txs which is heavy?
        # Actually /v1/blocks/by_height/{height} returns "transactions" list
        
        # Sample 5 blocks
        sample_indices = [latest_height - i*200 for i in range(5)]
        total_tx = 0
        valid = 0
        
        # We need time of start block too
        start_blk_res = make_request(f"{base_url}/v1/blocks/by_height/{start_height}?with_transactions=false")
        start_time = int(start_blk_res['block_timestamp']) / 1_000_000
        
        time_diff = latest_time - start_time
        if time_diff <= 0: time_diff = 1
        
        for h in sample_indices:
            try:
                res = make_request(f"{base_url}/v1/blocks/by_height/{h}?with_transactions=true")
                txs = res.get('transactions', [])
                # Exclude state checkpoint txs? Aptos usually counts all interactions.
                # User txs have type 'user_transaction'
                user_txs = [t for t in txs if t.get('type') == 'user_transaction']
                total_tx += len(user_txs)
                valid += 1
            except: pass
            
        if valid == 0: return None, "error", "No valid samples"
        
        avg_tx = total_tx / valid
        tps = (avg_tx * (latest_height - start_height)) / time_diff
        
        # Estimate
        total_count = float(latest_height) * avg_tx
        return tps, "success", None, total_count
    except Exception as e:
        return None, "error", str(e)

def measure_sui(chain_id, chain_name, rpc_url):
    # JSON-RPC sui_getTotalTransactionBlocks
    try:
        # Get total txs
        res_now = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"sui_getTotalTransactionBlocks", "params":[]}, 'POST')
        tx_now = int(res_now['result'])
        time_now = time.time()
        
        # We need a delta. Wait 5 seconds?
        # This is a bit blocking but safest for total counters.
        # Or check active checkpoints.
        
        # Better: getCheckpoint(latest) -> timestamp + tx_count? 
        # sui_getLatestCheckpointSequenceNumber
        
        res_seq = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"sui_getLatestCheckpointSequenceNumber", "params":[]}, 'POST')
        seq_now = int(res_seq['result'])
        
        # Get checkpoint details
        res_cp = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"sui_getCheckpoint", "params":[str(seq_now)]}, 'POST')
        cp_now = res_cp['result']
        ts_now = int(cp_now['timestampMs']) / 1000.0
        
        # Go back 20 checkpoints
        seq_old = max(0, seq_now - 20)
        res_cp_old = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"sui_getCheckpoint", "params":[str(seq_old)]}, 'POST')
        cp_old = res_cp_old['result']
        ts_old = int(cp_old['timestampMs']) / 1000.0
        
        time_diff = ts_now - ts_old
        if time_diff <= 0: time_diff = 1
        
        # Sum transactions in between? 
        # Checkpoints have 'transactions' array (digests) or rolling summary?
        # cp has "networkTotalTransactions" ? No.
        # But we can assume linearly accumulating or just sum lengths of sampled checkpoints.
        
        # It's better to fetch sample checkpoints and sum their tx count.
        sample_size = 5
        step = max(1, (seq_now - seq_old) // sample_size)
        samples = range(seq_old, seq_now + 1, step)[:sample_size]
        
        total_tx = 0
        valid = 0
        for s in samples:
             res = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"sui_getCheckpoint", "params":[str(s)]}, 'POST')
             txs = res['result'].get('transactions', [])
             total_tx += len(txs)
             valid += 1
             
        avg_tx = total_tx / valid
        total_range = seq_now - seq_old
        tps = (avg_tx * total_range) / time_diff
        
        # Exact count for Sui?
        # seq_now is checkpoint sequence. 
        # But `sui_getTotalTransactionBlocks` (measured earlier as tx_now) is exact!
        return tps, "success", None, float(tx_now)
    except Exception as e:
        return None, "error", str(e)

def measure_near(chain_id, chain_name, rpc_url):
    try:
        # block method
        # { "jsonrpc": "2.0", "id": "dontcare", "method": "block", "params": { "finality": "final" } }
        payload = {"jsonrpc": "2.0", "id": "1", "method": "block", "params": {"finality": "final"}}
        res_now = make_request(rpc_url, payload, 'POST')
        
        header_now = res_now['result']['header']
        height_now = header_now['height']
        ts_now = header_now['timestamp'] # nanoseconds?
        # Near timestamp is usually nanoseconds
        ts_now_sec = ts_now / 1_000_000_000
        
        # Go back 100 blocks
        height_old = height_now - 100
        payload_old = {"jsonrpc": "2.0", "id": "1", "method": "block", "params": {"block_id": height_old}}
        res_old = make_request(rpc_url, payload_old, 'POST')
        
        header_old = res_old['result']['header']
        ts_old_sec = header_old['timestamp'] / 1_000_000_000
        
        time_diff = ts_now_sec - ts_old_sec
        if time_diff <= 0: time_diff = 1
        
        # Sample chunks? Near blocks have chunks.
        # Simplifying: Just count txs in blocks if available directly.
        # result->chunks is list. Need to fetch chunks? 
        # Actually standard Near measurement often involves `chunk` details.
        
        # Alternative: use `validators` or `gas_used`? 
        # Standard block header has no tx count.
        # But `chunks` in block result has `chunk_hash`.
        # We need to call `chunk` method. This is heavy for many blocks.
        
        # Let's rely on average conservative estimate if chunks are populated.
        # Or better: Try to get just 3 blocks fully.
        
        sample_count = 3
        total_tx = 0
        
        for i in range(sample_count):
            h = height_now - i * 30
            p = {"jsonrpc": "2.0", "id": "1", "method": "block", "params": {"block_id": h}}
            r = make_request(rpc_url, p, 'POST')
            chunks = r['result']['chunks']
            
            # Fetch each chunk
            for c in chunks:
                if c['height_included'] == h:
                    c_hash = c['chunk_hash']
                    cp = {"jsonrpc": "2.0", "id": "1", "method": "chunk", "params": {"chunk_id": c_hash}}
                    cr = make_request(rpc_url, cp, 'POST')
                    txs = cr['result'].get('transactions', [])
                    total_tx += len(txs)
        
        # Time for these samples?
        # We sampled 3 blocks spread over range.
        # Just TPS = total_tx_in_sample / (avg_block_time * sample_count) ?
        # No, simpler: 
        # TPS = (Total Sampled TXs) / (Time Duration of Sampled Blocks * (Total Range / Sample Count))?
        # Let's just do: TPS of the sampled blocks.
        # Near block time is ~1.3s. 
        # We examined 1 block at i=0, i=1, i=2.
        # Each block represents ~1.3s of time.
        # So TPS = Total TXs / (Sample Count * 1.3s)
        # We can calculate block time from diff above.
        
        avg_block_time = time_diff / (height_now - height_old)
        tps = total_tx / (sample_count * avg_block_time)
        
        # Estimate: height * (avg tx per block from sample / 1.3s?)
        # total_tx in sample count (3 blocks)
        avg_per_blk = total_tx / sample_count
        total_count = float(height_now) * avg_per_blk
        
        return tps, "success", None, total_count
    except Exception as e:
        return None, "error", str(e)
        
def measure_algorand(chain_id, chain_name, rpc_url):
    # /v2/status -> lastRound
    try:
        status = make_request(f"{rpc_url}/v2/status")
        last_round = status['last-round']
        
        # /v2/blocks/{round} -> transactions (list)
        # Sample 5 blocks
        total_tx = 0
        valid = 0
        
        # Algos are fast (3.5s?)
        samples = range(last_round, max(0, last_round - 20), -1)[:5]
        
        timestamps = []
        
        for r in samples:
            blk = make_request(f"{rpc_url}/v2/blocks/{r}")
            timestamps.append(blk['timestamp'])
            txs = blk.get('transactions', [])
            total_tx += len(txs)
            valid += 1
            
        if valid < 2: return None, "error", "Not enough samples"
        
        # Avg time per block from samples
        time_span = max(timestamps) - min(timestamps)
        if time_span <= 0: time_span = 1
        
        # This time_span covers (len(samples)-1) gaps
        tps = total_tx / time_span if time_span > 1 else total_tx
        
        # Algorand exact?
        # /v2/blocks/{round} has txn-counter? No.
        # Estimate: round * (total_tx / 5)
        avg_per = total_tx / 5
        total_count = float(last_round) * avg_per
        
        return tps, "success", None, total_count
    except Exception as e:
        return None, "error", str(e)


def process_chain(chain):
    name = chain['Chain Name']
    cid = chain['Chain ID']
    rpc = chain['Main RPC Option']
    ctype = chain.get('Type', 'unknown')
    
    if ctype == 'cosmos':
        return cid, name, rpc, *measure_cosmos(cid, name, rpc)
    elif ctype == 'near':
        return cid, name, rpc, *measure_near(cid, name, rpc)
    elif ctype == 'aptos':
        return cid, name, rpc, *measure_aptos(cid, name, rpc)
    elif ctype == 'sui':
        return cid, name, rpc, *measure_sui(cid, name, rpc)
    elif ctype == 'algorand':
        return cid, name, rpc, *measure_algorand(cid, name, rpc)
    else:
        return cid, name, rpc, None, "skipped", "Unknown type", 0

def main():
    init_db()
    
    chains = []
    with open(NON_EVM_CSV, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            chains.append(row)
            
    print(f"Measuring TPS for {len(chains)} non-EVM chains...")
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_chain = {executor.submit(process_chain, c): c for c in chains}
        
        for future in as_completed(future_to_chain):
            result = future.result()
            # Unpack 7 values now
            if len(result) == 7:
                 chain_id, chain_name, rpc_url, tps, status, error, total_cnt = result
            else:
                 # fallback
                 chain_id, chain_name, rpc_url, tps, status, error = result
                 total_cnt = 0
            
            cursor.execute('''
                INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chain_id, chain_name, rpc_url, tps, time.time(), status, error, total_cnt))
            
            completed += 1
            if completed % 10 == 0:
                conn.commit()
                print(f"Progress: {completed}/{len(chains)} chains.", end='\r')
                
    conn.commit()
    conn.close()
    print("\nNon-EVM Measurement Complete.")

if __name__ == "__main__":
    main()
