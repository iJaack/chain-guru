"""
Headless Browser Scraper for Block Explorers

Uses Playwright to render JavaScript-heavy pages and bypass Cloudflare.
Targets chains with failed RPC connections that have explorer URLs.
"""

import sqlite3
import asyncio
import re
import time
from playwright.async_api import async_playwright

DB_FILE = "blockchain_data.db"
TIMEOUT_MS = 30000  # 30 seconds
MAX_CONCURRENT = 5  # Lower to avoid rate limits

# Regex patterns for common explorers
TPS_PATTERNS = [
    r'TPS[:\s]*([\d,]+\.?\d*)',
    r'Transactions per second[:\s]*([\d,]+\.?\d*)',
    r'([\d,]+\.?\d*)\s*TPS',
    r'tps[:\s]*([\d,]+\.?\d*)',
]

TX_COUNT_PATTERNS = [
    r'Total Transactions[:\s]*([\d,]+)',
    r'Transactions[:\s]*([\d,]+)',
    r'Total Txs[:\s]*([\d,]+)',
    r'(\d[\d,]*)\s*transactions',
    r'Total blocks[:\s]*([\d,]+)',  # Sometimes useful proxy
]


def clean_num(s):
    """Convert string with commas to float"""
    try:
        return float(s.replace(',', '').strip())
    except:
        return 0


def get_failed_chains():
    """Get chains that failed RPC and have explorer URLs"""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT chain_id, chain_name, explorer_url 
        FROM chain_metrics 
        WHERE status != 'success' 
        AND explorer_url IS NOT NULL 
        AND health_status != 'Live (Scraped)'
        AND (is_dead IS NULL OR is_dead = 0)
        LIMIT 100
    """)
    
    rows = cursor.fetchall()
    conn.close()
    return rows


async def scrape_chain(browser, chain_id, name, explorer_url):
    """Scrape a single chain's explorer using Playwright"""
    if not explorer_url:
        return chain_id, 0, 0, "no_url"
    
    # Normalize URL
    if not explorer_url.startswith('http'):
        explorer_url = 'https://' + explorer_url
    
    try:
        context = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        await page.goto(explorer_url, timeout=TIMEOUT_MS, wait_until='domcontentloaded')
        
        # Wait a bit for JS to render
        await page.wait_for_timeout(3000)
        
        # Get page text content
        content = await page.content()
        text = await page.inner_text('body')
        
        await context.close()
        
        # Scrape TPS
        tps = 0
        for p in TPS_PATTERNS:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                tps = clean_num(match.group(1))
                if tps > 0:
                    break
        
        # Scrape Transaction Count
        tx_count = 0
        for p in TX_COUNT_PATTERNS:
            match = re.search(p, text, re.IGNORECASE)
            if match:
                tx_count = clean_num(match.group(1))
                if tx_count > 0:
                    break
        
        if tps > 0 or tx_count > 0:
            print(f"✓ Scraped {name}: TPS={tps}, Tx={tx_count}")
            return chain_id, tps, tx_count, "success"
        else:
            return chain_id, 0, 0, "no_matches"
            
    except Exception as e:
        error_msg = str(e)[:100]
        print(f"✗ Failed {name}: {error_msg}")
        return chain_id, 0, 0, error_msg


async def process_batch(browser, chains):
    """Process a batch of chains concurrently"""
    tasks = [scrape_chain(browser, cid, name, url) for cid, name, url in chains]
    return await asyncio.gather(*tasks)


async def main():
    print("Starting Headless Browser Scraper...")
    
    chains = get_failed_chains()
    print(f"Found {len(chains)} chains to scrape")
    
    if not chains:
        print("No chains to scrape. Exiting.")
        return
    
    async with async_playwright() as p:
        # Launch browser in headless mode
        browser = await p.chromium.launch(headless=True)
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        
        updated = 0
        dead_count = 0
        
        # Process in batches
        for i in range(0, len(chains), MAX_CONCURRENT):
            batch = chains[i:i + MAX_CONCURRENT]
            results = await process_batch(browser, batch)
            
            for cid, tps, tx, status in results:
                if status == "success":
                    updates = []
                    params = []
                    
                    if tps > 0:
                        updates.append("tps_10min = ?")
                        params.append(tps)
                    if tx > 0:
                        updates.append("total_tx_count = ?")
                        params.append(tx)
                    
                    if updates:
                        updates.append("health_status = 'Live (Scraped)'")
                        updates.append("is_dead = 0")
                        updates.append("last_updated_at = ?")
                        params.append(time.time())
                        params.append(cid)
                        
                        sql = f"UPDATE chain_metrics SET {', '.join(updates)} WHERE chain_id = ?"
                        cursor.execute(sql, tuple(params))
                        updated += 1
                
                # Mark as dead if DNS resolution failed
                elif "ERR_NAME_NOT_RESOLVED" in status:
                    cursor.execute(
                        "UPDATE chain_metrics SET is_dead = 1, health_status = 'Dead (Domain Gone)' WHERE chain_id = ?",
                        (cid,)
                    )
                    dead_count += 1
            
            conn.commit()
            print(f"Processed batch {i // MAX_CONCURRENT + 1}/{(len(chains) + MAX_CONCURRENT - 1) // MAX_CONCURRENT}")
        
        await browser.close()
        conn.close()
        
        print(f"\nScraping complete. Updated {updated} chains, marked {dead_count} as dead.")


if __name__ == "__main__":
    asyncio.run(main())
