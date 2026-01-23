import sqlite3
import time
import json
import urllib.request
import ssl

DB_FILE = 'blockchain_data.db'

def make_request(url, payload=None, method='GET'):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {'Content-Type': 'application/json', 'User-Agent': 'Mozilla/5.0'}
    try:
        if payload:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers=headers, method=method)
        else:
            req = urllib.request.Request(url, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Request error: {e}")
        return None

def main():
    chain_id = "solana-mainnet"
    name = "Solana Mainnet"
    rpc_url = "https://api.mainnet-beta.solana.com"
    
    print(f"Measuring {name}...")
    
    try:
        # getRecentPerformanceSamples
        payload = {"jsonrpc": "2.0", "id": 1, "method": "getRecentPerformanceSamples", "params": [4]}
        res = make_request(rpc_url, payload, 'POST')
        
        tps = 0
        if res and 'result' in res:
            samples = res['result']
            if samples:
                total_tx_sample = sum(s['numTransactions'] for s in samples)
                total_time = sum(s['samplePeriodSecs'] for s in samples)
                if total_time > 0:
                    tps = total_tx_sample / total_time
        
        print(f"TPS: {tps}")
        
        # Total Tx Count
        total_history = 0
        try:
             res_total = make_request(rpc_url, {"jsonrpc":"2.0", "id":1, "method":"getTransactionCount", "params":[]}, 'POST')
             if res_total and 'result' in res_total:
                 total_history = int(res_total['result'])
        except Exception as e:
             print(f"History error: {e}")
             
        print(f"Total Transactions: {total_history}")
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (chain_id, name, rpc_url, tps, time.time(), "success", None, float(total_history)))
        conn.commit()
        conn.close()
        print("Updated DB.")
        
    except Exception as e:
        print(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
