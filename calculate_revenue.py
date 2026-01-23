import sqlite3

def is_evm(cid):
    return cid.isdigit()

def calculate():
    conn = sqlite3.connect('blockchain_data.db')
    cursor = conn.cursor()
    cursor.execute("SELECT chain_id, tps_10min, total_tx_count FROM chain_metrics WHERE status='success'")
    rows = cursor.fetchall()
    conn.close()

    evm_tps = 0
    non_evm_tps = 0
    evm_tx = 0
    non_evm_tx = 0

    for r in rows:
        cid, tps, tx = r
        if tps is None: tps = 0
        if tx is None: tx = 0
        
        if is_evm(str(cid)):
            evm_tps += tps
            evm_tx += tx
        else:
            non_evm_tps += tps
            non_evm_tx += tx

    # Pricing
    # EVM
    evm_arr = evm_tps * 4000
    evm_setup = (evm_tx / 1_000_000) * 200
    evm_total = evm_arr + evm_setup

    # Non-EVM
    non_evm_arr = non_evm_tps * 16000
    non_evm_setup = (non_evm_tx / 1_000_000) * 800
    non_evm_total = non_evm_arr + non_evm_setup

    non_evm_total = non_evm_arr + non_evm_setup

    grand_total = evm_total + non_evm_total

    # Scenario B: Parity Pricing (Non-EVM at EVM rates)
    # Non-EVM @ $4k / $200
    non_evm_parity_arr = non_evm_tps * 4000
    non_evm_parity_setup = (non_evm_tx / 1_000_000) * 200
    non_evm_parity_total = non_evm_parity_arr + non_evm_parity_setup
    
    grand_total_parity = evm_total + non_evm_parity_total

    print(f"--- Revenue Projection ---")
    print(f"EVM Ecosystem:")
    print(f"  TPS Sum: {evm_tps:,.2f}")
    print(f"  Tx History: {evm_tx:,.0f}")
    print(f"  ARR (TPS * $4k): ${evm_arr:,.2f}")
    print(f"  Setup (Tx/1M * $200): ${evm_setup:,.2f}")
    print(f"  Subtotal: ${evm_total:,.2f}")
    print(f"")
    print(f"Non-EVM Ecosystem (Standard Pricing):")
    print(f"  TPS Sum: {non_evm_tps:,.2f}")
    print(f"  Tx History: {non_evm_tx:,.0f}")
    print(f"  ARR (TPS * $16k): ${non_evm_arr:,.2f}")
    print(f"  Setup (Tx/1M * $800): ${non_evm_setup:,.2f}")
    print(f"  Subtotal: ${non_evm_total:,.2f}")
    print(f"")
    print(f"Grand Total (Standard): ${grand_total:,.2f}")
    print(f"")
    print(f"--- Scenario B: Parity Pricing ---")
    print(f"Non-EVM Ecosystem (Parity - EVM Rates):")
    print(f"  ARR (TPS * $4k): ${non_evm_parity_arr:,.2f}")
    print(f"  Setup (Tx/1M * $200): ${non_evm_parity_setup:,.2f}")
    print(f"  Subtotal: ${non_evm_parity_total:,.2f}")
    print(f"")
    print(f"Grand Total (Parity): ${grand_total_parity:,.2f}")

if __name__ == "__main__":
    calculate()
