import os
import shlex
import subprocess
import sys
import time

def run_command(command, description):
    print(f"\n--- Starting: {description} ---")
    start_time = time.time()
    try:
        if isinstance(command, str):
            command = shlex.split(command)

        # Run command and stream output
        process = subprocess.Popen(
            command,
            shell=False,
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT,
            text=True
        )
        
        for line in process.stdout:
            print(line, end='')
            
        process.wait()
        
        if process.returncode != 0:
            print(f"!!! Error in {description} (Exit Code: {process.returncode}) !!!")
            # We don't exit here because we might want to try to push partial data or continue
            return False
    except Exception as e:
        print(f"!!! Exception in {description}: {e} !!!")
        return False
        
    elapsed = time.time() - start_time
    print(f"--- Finished: {description} (Took {elapsed:.2f}s) ---\n")
    return True

def main():
    # 1. Fetch latest chain list
    # This finds new chains and updates RPCs from source
    run_command("python3 process_chains.py", "Update Chain List")

    # 2. Run Standard Measurement
    # Measures default EVM + specialized Non-EVM adapters
    run_command("python3 measure_tps.py", "Standard TPS Measurement")
    
    # 3. Run Forced/Retry Measurement
    # Retries failed EVM chains with aggressive timeouts/failovers
    # This fulfills the "retry finding other RPCs" requirement
    run_command("python3 measure_force_evm.py", "Forced EVM Retry")

    # 4. Run Headless Browser Scraping (for chains with failed RPC)
    # Uses Playwright to scrape block explorer pages
    run_command("python3 scrape_explorer_headless.py", "Headless Explorer Scraping")

    # 5. Scout X (Twitter) accounts for chains
    run_command("python3 scout_x_accounts.py --sleep 6", "Scout X Accounts")

    # 6. Sync to Cloud Database
    # Pushes the updated local SQLite DB to Vercel Postgres
    if os.environ.get("POSTGRES_URL"):
        run_command("python3 migrate_postgres.py", "Sync to Vercel Postgres")
    else:
        print("Skipping Database Sync: POSTGRES_URL not set in environment.")

if __name__ == "__main__":
    main()
