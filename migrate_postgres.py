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
    
    # Fetch Data
    sqlite_curr.execute("SELECT * FROM chain_metrics")
    rows = sqlite_curr.fetchall()
    print(f"Found {len(rows)} rows in SQLite.")
    
    # Write to Postgres
    try:
        pg_cursor = pg_conn.cursor()
        
        # Ensure schema has new column (idempotent)
        try:
            pg_cursor.execute("ALTER TABLE chain_metrics ADD COLUMN health_status TEXT")
            pg_conn.commit()
            print("Added health_status column to Postgres.")
        except psycopg2.errors.DuplicateColumn:
            pg_conn.rollback()
        except Exception:
            pg_conn.rollback()

        # Create Table if not exists
        pg_cursor.execute('''
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
        pg_conn.commit()
        
        count = 0
        for row in rows:
            item = dict(row)
            health = item.get('health_status')
            if not health:
                 health = "Live" if item.get('status') == 'success' else item.get('error_message')

            pg_cursor.execute('''
                INSERT INTO chain_metrics (chain_id, chain_name, rpc_url, tps_10min, last_updated_at, status, error_message, total_tx_count, health_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (chain_id) DO UPDATE SET
                    tps_10min = EXCLUDED.tps_10min,
                    total_tx_count = EXCLUDED.total_tx_count,
                    status = EXCLUDED.status,
                    last_updated_at = EXCLUDED.last_updated_at,
                    health_status = EXCLUDED.health_status
            ''', (
                item['chain_id'], 
                item['chain_name'], 
                item['rpc_url'], 
                item['tps_10min'], 
                item['last_updated_at'], 
                item['status'], 
                item['error_message'],
                item.get('total_tx_count', 0),
                health
            ))
            count += 1
        
        pg_conn.commit()
        print(f"Successfully migrated {count} rows to Postgres.")
        
    except Exception as e:
        print(f"Migration error: {str(e)}")
        pg_conn.rollback()
    
    sqlite_conn.close()
    pg_conn.close()

if __name__ == "__main__":
    migrate()
