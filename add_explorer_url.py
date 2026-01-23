import sqlite3
import json
import urllib.request
import ssl

DB_FILE = "blockchain_data.db"
CHAINS_JSON_URL = "https://chainid.network/chains.json"

def main():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    # 1. Add Column
    try:
        cursor.execute("ALTER TABLE chain_metrics ADD COLUMN explorer_url TEXT")
        print("Column 'explorer_url' added.")
    except sqlite3.OperationalError:
        print("Column 'explorer_url' already exists.")
        
    # 2. Fetch Data
    print("Fetching chains.json...")
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    req = urllib.request.Request(CHAINS_JSON_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
        chains_data = json.loads(response.read())
        
    # 3. Create Map
    chain_explorers = {}
    for c in chains_data:
        explorers = c.get('explorers', [])
        if explorers:
            # Pick first
            url = explorers[0].get('url')
            if url:
                chain_explorers[str(c['chainId'])] = url
                
    # 4. Update DB
    print("Updating explorer URLs...")
    cursor.execute("SELECT chain_id FROM chain_metrics")
    rows = cursor.fetchall()
    
    count = 0
    for row in rows:
        cid = row[0]
        url = chain_explorers.get(cid)
        if url:
            cursor.execute("UPDATE chain_metrics SET explorer_url = ? WHERE chain_id = ?", (url, cid))
            count += 1
            
    conn.commit()
    conn.close()
    print(f"Updated explorer URLs for {count} chains.")

if __name__ == "__main__":
    main()
