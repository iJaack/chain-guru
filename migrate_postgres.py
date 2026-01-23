import sqlite3
import psycopg2
import os
import sys
from dotenv import load_dotenv

load_dotenv(".env.local")

# Usage: POSTGRES_URL=... python3 migrate_postgres.py

DB_FILE = "blockchain_data.db"
POSTGRES_URL = os.environ.get("POSTGRES_URL")

def migrate():
    if not POSTGRES_URL:
        print("Error: POSTGRES_URL environment variable not set.")
        sys.exit(1)
        
    print("Connecting to SQLite...")
    sqlite_conn = sqlite3.connect(DB_FILE)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_curr = sqlite_conn.cursor()
    
    print("Connecting to Postgres...")
    pg_conn = psycopg2.connect(POSTGRES_URL)
    pg_curr = pg_conn.cursor()
    
    # Create Table
    print("Creating table in Postgres...")
    pg_curr.execute('''
        CREATE TABLE IF NOT EXISTS chain_metrics (
            chain_id TEXT PRIMARY KEY,
            chain_name TEXT,
            rpc_url TEXT,
            tps_10min REAL,
            last_updated_at REAL,
            status TEXT,
            error_message TEXT,
            total_tx_count REAL
        )
    ''')
    pg_conn.commit()
    
    # Fetch Data
    sqlite_curr.execute("SELECT * FROM chain_metrics")
    rows = sqlite_curr.fetchall()
    print(f"Found {len(rows)} rows in SQLite.")
    
    # Insert Data
    count = 0
    for row in rows:
        item = dict(row)
        # Ensure total_tx_count exists (might be missing in older sqlite schema versions/rows if not strictly handled, but we added it)
        # SQLite Row returns keys
        
        pg_curr.execute('''
            INSERT INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (chain_id) DO UPDATE SET
                tps_10min = EXCLUDED.tps_10min,
                total_tx_count = EXCLUDED.total_tx_count,
                status = EXCLUDED.status,
                last_updated_at = EXCLUDED.last_updated_at
        ''', (
            item['chain_id'], 
            item['chain_name'], 
            item['rpc_url'], 
            item['tps_10min'], 
            item['last_updated_at'], 
            item['status'], 
            item['error_message'],
            item.get('total_tx_count', 0)
        ))
        count += 1
        
    pg_conn.commit()
    print(f"Successfully migrated {count} rows to Postgres.")
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
