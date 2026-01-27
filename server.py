from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import sqlite3
import uvicorn
import os

# Conditional import for local dev compatibility
try:
    import psycopg2
    from psycopg2.extras import RealDictCursor
except ImportError:
    psycopg2 = None
    RealDictCursor = None

app = FastAPI()

# Enable CORS for frontend
origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allow_origins = [o.strip() for o in origins_env.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "blockchain_data.db"
POSTGRES_URL = os.environ.get("POSTGRES_URL")

def get_db_connection():
    if POSTGRES_URL:
        conn = psycopg2.connect(POSTGRES_URL)
        return conn, "postgres"
    else:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        return conn, "sqlite"

def is_evm(cid):
    return cid.isdigit()

@app.get("/api/chains")
def get_chains():
    conn, db_type = get_db_connection()
    
    if db_type == "postgres":
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM chain_metrics")
        rows = cursor.fetchall()
    else:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM chain_metrics")
        rows = cursor.fetchall()
        
    conn.close()
    
    data = []
    for r in rows:
        item = dict(r)
        # Determine type
        item['type'] = 'EVM' if is_evm(str(item['chain_id'])) else 'Non-EVM'
        data.append(item)
        
    return data

@app.get("/api/summary")
def get_summary():
    conn, db_type = get_db_connection()
    
    if db_type == "postgres":
        cursor = conn.cursor(cursor_factory=RealDictCursor)
    else:
        cursor = conn.cursor()
        
    cursor.execute("SELECT chain_id, tps_10min, total_tx_count FROM chain_metrics")
    rows = cursor.fetchall()
    conn.close()
    
    metrics = {
        "evm": {"tps": 0, "history": 0, "count": 0},
        "non_evm": {"tps": 0, "history": 0, "count": 0}
    }
    
    for r in rows:
        if db_type == "postgres":
            cid = r.get("chain_id")
            tps = r.get("tps_10min") or 0
            hist = r.get("total_tx_count") or 0
        else:
            cid, tps, hist = r
            tps = tps or 0
            hist = hist or 0
        
        if is_evm(str(cid)):
            metrics["evm"]["tps"] += tps
            metrics["evm"]["history"] += hist
            metrics["evm"]["count"] += 1
        else:
            metrics["non_evm"]["tps"] += tps
            metrics["non_evm"]["history"] += hist
            metrics["non_evm"]["count"] += 1
            
    return metrics



from fastapi.staticfiles import StaticFiles
# Mount static files (must be last to allow API routes to match first)
app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
