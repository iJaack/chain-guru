import urllib.request
import csv
import json
import ssl

def main():
    url = "https://chainid.network/chains.json"
    print(f"Fetching data from {url}...")
    
    # Create a context that doesn't verify SSL certificates specifically for this
    # simple data fetching script to avoid potential local SSL issues, though 
    # normally we'd want verification.
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        with urllib.request.urlopen(url, context=ctx) as response:
            data = response.read()
            chains = json.loads(data)
    except Exception as e:
        print(f"Error fetching data: {e}")
        return

    print(f"Processing {len(chains)} chains...")
    
    csv_file = "active_blockchains.csv"
    
    with open(csv_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(["Chain Name", "Chain ID", "Main RPC Option"])
        
        count = 0
        for chain in chains:
            name = chain.get("name", "Unknown")
            chain_id = chain.get("chainId", "Unknown")
            rpcs = chain.get("rpc", [])
            
            selected_rpc = "N/A"
            if rpcs:
                # Try to find a "clean" RPC first (no placeholders like ${API_KEY})
                clean_rpcs = [r for r in rpcs if "${" not in r]
                if clean_rpcs:
                    selected_rpc = clean_rpcs[0]
                else:
                    selected_rpc = rpcs[0]
            
            writer.writerow([name, chain_id, selected_rpc])
            count += 1
            
    print(f"Successfully wrote {count} chains to {csv_file}")

if __name__ == "__main__":
    main()
