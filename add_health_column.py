import sqlite3

def main():
    print("Migrating local database...")
    conn = sqlite3.connect('blockchain_data.db')
    cursor = conn.cursor()
    
    # Add column if not exists
    try:
        cursor.execute("ALTER TABLE chain_metrics ADD COLUMN health_status TEXT")
        print("Column 'health_status' added.")
    except sqlite3.OperationalError:
        print("Column 'health_status' already exists.")

    # Backfill
    print("Backfilling data...")
    cursor.execute("UPDATE chain_metrics SET health_status = 'Live' WHERE status = 'success'")
    cursor.execute("UPDATE chain_metrics SET health_status = error_message WHERE status != 'success'")
    
    conn.commit()
    conn.close()
    print("Migration complete.")

if __name__ == '__main__':
    main()
