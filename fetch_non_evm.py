import csv
import json
import urllib.request
import ssl

def make_request(url):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
        return json.loads(response.read())

def fetch_cosmos_chains():
    print("Fetching Cosmos chains from cosmos.directory...")
    chains = []
    try:
        # cosmos.directory aggregates registry data
        data = make_request("https://chains.cosmos.directory/")
        # data is usually a dict with "chains" list or just a list
        # detailed structure check needed usually, but let's assume standard
        
        chain_list = data.get('chains', [])
        for c in chain_list:
            name = c.get('pretty_name') or c.get('name')
            chain_id = c.get('chain_id')
            network_type = c.get('network_type')
            
            if network_type != 'mainnet':
                continue
                
            # Get best RPC
            # best_apis can be found in 'best_apis' -> 'rpc'
            rpcs = c.get('best_apis', {}).get('rpc', [])
            selected_rpc = None
            if rpcs:
                selected_rpc = rpcs[0].get('address')
            
            if name and chain_id and selected_rpc:
                chains.append({
                    "Chain Name": name,
                    "Chain ID": chain_id,
                    "Main RPC Option": selected_rpc,
                    "Type": "cosmos"
                })
    except Exception as e:
        print(f"Error fetching Cosmos chains: {e}")
        
    print(f"Found {len(chains)} active Cosmos chains.")
    return chains

def get_major_non_evms():
    # Hardcoded majors
    return [
        {"Chain Name": "Near Protocol", "Chain ID": "near-mainnet", "Main RPC Option": "https://rpc.mainnet.near.org", "Type": "near"},
        {"Chain Name": "Aptos Mainnet", "Chain ID": "aptos-mainnet", "Main RPC Option": "https://fullnode.mainnet.aptoslabs.com/v1", "Type": "aptos"},
        {"Chain Name": "Sui Mainnet", "Chain ID": "sui-mainnet", "Main RPC Option": "https://fullnode.mainnet.sui.io:443", "Type": "sui"},
        {"Chain Name": "Algorand Mainnet", "Chain ID": "algorand-mainnet", "Main RPC Option": "https://mainnet-api.algonode.cloud", "Type": "algorand"},
        # Solana, Bitcoin, Tron are already in DB but we can add them here for completeness if we re-run
    ]

def main():
    all_chains = []
    all_chains.extend(get_major_non_evms())
    all_chains.extend(fetch_cosmos_chains())
    
    filename = "non_evm_chains.csv"
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Chain Name", "Chain ID", "Main RPC Option", "Type"])
        writer.writeheader()
        writer.writerows(all_chains)
        
    print(f"Saved {len(all_chains)} non-EVM chains to {filename}")

if __name__ == "__main__":
    main()
