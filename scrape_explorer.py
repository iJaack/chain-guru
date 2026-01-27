import sqlite3
import urllib.request
import ssl
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

DB_FILE = "blockchain_data.db"
TIMEOUT_SECONDS = 15
MAX_WORKERS = 20

# Regex patterns for common explorers (Blockscout, Etherscan clones)
TPS_PATTERNS = [
    r'TPS:?\s*([\d,]+\.?\d*)',
    r'Transactions per second:?\s*([\d,]+\.?\d*)',
    r'(\d+\.?\d*)\s*TPS',
]

TX_COUNT_PATTERNS = [
    r'Total Transactions:?\s*([\d,]+)',
    r'Transactions:?\s*([\d,]+)',
    r'Total Txs:?\s*([\d,]+)',
]

def clean_num(s):
    try:
        return float(s.replace(',', '').strip())
    except:
        return 0

def get_ssl_context():
    if os.environ.get("INSECURE_SSL", "").lower() in ("1", "true", "yes"):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx
    return None


def scrape_chain(chain_item):
    chain_id, name, explorer_url = chain_item
    
    if not explorer_url:
        return chain_id, None, None, "no_url"
        
    ctx = get_ssl_context()
    
    # Normalize URL
    if not explorer_url.startswith('http'):
        explorer_url = 'https://' + explorer_url
        
    try:
        req = urllib.request.Request(
            explorer_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)'}
        )
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS, context=ctx) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Scrape TPS
            tps = 0
            for p in TPS_PATTERNS:
                match = re.search(p, html, re.IGNORECASE)
                if match:
                    tps = clean_num(match.group(1))
                    break
            
            # Scrape History
            tx_count = 0
            for p in TX_COUNT_PATTERNS:
                match = re.search(p, html, re.IGNORECASE)
                if match:
                    tx_count = clean_num(match.group(1))
                    break
                    
            if tps > 0 or tx_count > 0:
                print(f"Scraped {name}: TPS={tps}, Tx={tx_count}")
                return chain_id, tps, tx_count, "success"
                
    except Exception as e:
        return chain_id, None, None, str(e)
        
    return chain_id, 0, 0, "no_matches"

def main():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # Select failed chains with explorer URLs
    print("Selecting failed chains...")
    cursor.execute("SELECT chain_id, chain_name, explorer_url FROM chain_metrics WHERE status != 'success' AND explorer_url IS NOT NULL")
    targets = cursor.fetchall()
    
    print(f"Targeting {len(targets)} chains for scraping...")
    
    updated = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_chain = {executor.submit(scrape_chain, c): c for c in targets}
        
        for future in as_completed(future_to_chain):
            cid, tps, tx, status = future.result()
            
            if status == 'success':
                # Update DB
                # Note: We keep status != 'success' mostly, or maybe mark as 'scraped'?
                # Let's keep status as is (rpc failed), but update health_status to "Scraped" + update metrics
                
                # Check if we have values
                updates = []
                params = []
                
                if tps:
                    updates.append("tps_10min = ?")
                    params.append(tps)
                if tx:
                    updates.append("total_tx_count = ?")
                    params.append(tx)
                    
                if updates:
                    updates.append("health_status = 'Live (Scraped)'")
                    updates.append("last_updated_at = ?")
                    params.append(time.time())
                    params.append(cid)
                    
                    sql = f"UPDATE chain_metrics SET {', '.join(updates)} WHERE chain_id = ?"
                    cursor.execute(sql, tuple(params))
                    updated += 1
                    
            if updated % 10 == 0:
                conn.commit()
                
    conn.commit()
    conn.close()
    print(f"Scraping complete. Updated {updated} chains.")

if __name__ == "__main__":
    main()
