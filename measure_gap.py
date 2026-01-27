import csv
import sqlite3
import time
import json
import urllib.request
import ssl
import os
from concurrent.futures import ThreadPoolExecutor

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
    except urllib.error.HTTPError as e:
        # Read body for error msg
        return None
    except Exception as e:
        return None

# --- Adapters ---

def measure_polkadot(chain_id, chain_name, rpc_url):
    # Use Subscan API (public endpoints, rate limited but mostly working for low volume)
    # https://polkadot.api.subscan.io/api/scan/transfers is one way, but better:
    # /api/scan/metadata gives block time?
    # Actually, we need TPS.
    # Subscan: POST /api/scan/blocks
    # payload: {"row": 10, "page": 0}
    try:
        domain = "polkadot" if "polkadot" in chain_id else "kusama"
        url = f"https://{domain}.api.subscan.io/api/scan/blocks"
        res = make_request(url, {"row": 10, "page": 0}, 'POST')
        
        if not res or res.get('message') != 'Success':
             return None, "error", "Subscan API error"
             
        blocks = res['data']['blocks']
        if len(blocks) < 2: return None, "error", "Not enough blocks"
        
        # Calculate TPS from last 10 blocks (Substrate blocks are ~6s)
        total_tx = sum(b['extrinsics_count'] for b in blocks)
        
        # Time diff
        # block_timestamp is unix timestamp
        latest_ts = blocks[0]['block_timestamp']
        oldest_ts = blocks[-1]['block_timestamp']
        
        time_diff = latest_ts - oldest_ts
        if time_diff <= 0: time_diff = 1
        
        tps = total_tx / time_diff
        return tps, "success", None
    except Exception as e:
        return None, "error", str(e)

def measure_starknet(chain_id, chain_name, rpc_url):
    # Starknet JSON RPC
    # starknet_getBlockWithTxHashes
    try:
        payload = {
            "jsonrpc": "2.0",
            "method": "starknet_getBlockWithTxHashes",
            "params": ["latest"],
            "id": 1
        }
        res = make_request(rpc_url, payload, 'POST')
        latest_block = res['result']
        latest_num = latest_block['block_number']
        latest_ts = latest_block['timestamp']
        
        # Go back 20 blocks
        old_num = max(0, latest_num - 20)
        payload['params'] = [{"block_number": old_num}]
        res_old = make_request(rpc_url, payload, 'POST')
        old_block = res_old['result']
        old_ts = old_block['timestamp']
        
        time_diff = latest_ts - old_ts
        if time_diff <= 0: time_diff = 1
        
        # Sample tx count?
        # We can iterate samples
        sample_nums = range(old_num, latest_num, 5)[:5]
        total_tx = 0
        valid = 0
        for n in sample_nums:
            payload['params'] = [{"block_number": n}]
            r = make_request(rpc_url, payload, 'POST')
            if r and 'result' in r:
                total_tx += len(r['result']['transactions'])
                valid += 1
                
        if valid == 0: return None, "error", "No valid samples"
        
        avg_tx = total_tx / valid
        tps = (avg_tx * (latest_num - old_num)) / time_diff
        return tps, "success", None
    except Exception as e:
        return None, "error", str(e)

def measure_bitcoin_fork(chain_id, chain_name, rpc_url):
    # For Doge/Litecoin using Blockcypher or similar public APIs if RPC failed?
    # Or try standard RPC we found?
    # Assuming we use a block explorer API here for robustness as raw RPCs for Doge are rare publicly.
    # Blockchair? SoChain?
    
    # Let's try SoChain API (free)
    # https://sochain.com/api/v2/get_info/{NETWORK}
    try:
        network = "DOGE" if "doge" in chain_id else "LTC"
        # SoChain v3?
        # https://chain.so/api/v3/block/{network}/{block_id}
        # https://chain.so/api/v2/get_info/{network} deprecated?
        
        # Let's try BlockCypher (free tier limits?)
        # https://api.blockcypher.com/v1/{coin}/main
        coin = "doge" if "doge" in chain_id else "ltc"
        base_url = f"https://api.blockcypher.com/v1/{coin}/main"
        
        info = make_request(base_url)
        height = info['height']
        
        # Get last block
        # https://api.blockcypher.com/v1/doge/main/blocks/{height}
        # Limit?
        
        # Sample 3 blocks
        total_tx = 0
        timestamps = []
        
        for i in range(3):
            h = height - i
            b = make_request(f"{base_url}/blocks/{h}")
            timestamps.append(time.mktime(time.strptime(b['time'], "%Y-%m-%dT%H:%M:%S.%fZ")))
            total_tx += b['n_tx'] # BlockCypher uses n_tx
            
        time_diff = max(timestamps) - min(timestamps)
        if time_diff <= 0: time_diff = 1
        
        tps = total_tx / time_diff if time_diff > 0 else 0
        return tps, "success", None
        
    except Exception as e:
        return None, "error", str(e)
    
def measure_stellar(chain_id, chain_name, rpc_url):
    # Horizon API: https://horizon.stellar.org
    # /ledgers?order=desc&limit=5
    try:
        url = f"{rpc_url}/ledgers?order=desc&limit=10"
        res = make_request(url)
        ledgers = res['_embedded']['records']
        
        total_tx = sum(l['successful_transaction_count'] + l['failed_transaction_count']  for l in ledgers)
        
        # Time diff
        # closed_at ISO strings
        latest_ts = ledgers[0]['closed_at']
        oldest_ts = ledgers[-1]['closed_at']
        
        # Parse ISO
        # 2024-01-...Z
        # Assume Python 3.7+
        import datetime
        t1 = datetime.datetime.strptime(latest_ts, "%Y-%m-%dT%H:%M:%SZ").timestamp()
        t2 = datetime.datetime.strptime(oldest_ts, "%Y-%m-%dT%H:%M:%SZ").timestamp()
        
        diff = t1 - t2
        if diff <= 0: diff = 1
        
        tps = total_tx / diff
        return tps, "success", None
    except Exception as e:
        return None, "error", str(e)
    
def measure_ton(chain_id, chain_name, rpc_url):
    # Toncenter API
    # getMasterchainInfo
    try:
        # Toncenter V2
        url = f"{rpc_url}/getMasterchainInfo"
        res = make_request(url)
        last = res['result']['last']
        seqno = last['seqno']
        
        # Get blocks (shards + master) is complex in TON.
        # But master blocks ("blocks") contain count of transactions in whole system?
        # Actually usually looked up via "getConsensusBlock" or simple statistics API.
        # Tonapi.io is better: /v2/blockchain/blocks?limit=10
        # But let's try reading `r.result` carefully.
        
        # Fallback to simplistic "TPS" if just masterchain? 
        # No, TON is sharded. Masterchain blocks don't hold all txs.
        # Using public indexer API like tonapi.io (public endpoint?)
        # https://tonapi.io/v2/blockchain/blocks?limit=10
        
        url_idx = "https://tonapi.io/v2/blockchain/blocks?limit=10"
        res_idx = make_request(url_idx)
        if not res_idx: return None, "error", "TonApi blocked"
        
        blocks = res_idx['blocks']
        total_tx = sum(b['tx_count'] for b in blocks)
        
        t1 = blocks[0]['timestamp']
        t2 = blocks[-1]['timestamp']
        
        diff = t1 - t2
        if diff <= 0: diff = 1
        tps = total_tx / diff
        return tps, "success", None
        
    except Exception as e:
        return None, "error", str(e)


def main():
    targets = [
        ("polkadot", "Polkadot", "https://polkadot.api.subscan.io"),
        ("kusama", "Kusama", "https://kusama.api.subscan.io"),
        ("starknet-mainnet", "Starknet", "https://starknet-mainnet.public.blastapi.io"),
        ("dogecoin", "Dogecoin", "https://api.blockcypher.com/v1/doge/main"),
        ("litecoin", "Litecoin", "https://api.blockcypher.com/v1/ltc/main"),
        ("stellar", "Stellar", "https://horizon.stellar.org"),
        ("ton", "Toncoin", "https://toncenter.com/api/v2/jsonRPC"), # We override logic to use tonapi inside
    ]
    
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    print("Measuring Gap Chains...")
    
    for cid, name, url in targets:
        try:
            res = None
            if "polkadot" in cid or "kusama" in cid:
                res = measure_polkadot(cid, name, url)
            elif "starknet" in cid:
                res = measure_starknet(cid, name, url)
            elif "doge" in cid or "litecoin" in cid:
                res = measure_bitcoin_fork(cid, name, url)
            elif "stellar" in cid:
                res = measure_stellar(cid, name, url)
            elif "ton" in cid:
                res = measure_ton(cid, name, url)
            
            if res and res[1] == "success":
                tps = res[0]
                status = res[1]
                err = res[2]
                print(f"{name}: {tps:.2f} TPS")
                cursor.execute('''
                    INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (cid, name, url, tps, time.time(), status, err))
            else:
                print(f"{name}: Failed ({res[2] if res else 'Unknown'})")
                
        except Exception as e:
            print(f"{name}: Failed ({e})")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    main()
