# Codebase Review: Chain Guru

**Date:** 2026-01-29
**Auditor:** Eva (via Codex)

## 🚨 Critical Security Risks

1.  **Arbitrary Command Execution (`refresh_data.py`)**
    *   **Issue:** Uses `subprocess.Popen(..., shell=True)`.
    *   **Risk:** If `command` input is ever tainted, this allows Remote Code Execution (RCE).
    *   **Fix:** Use `shlex.split()` and `shell=False`.

2.  **SSRF (Server-Side Request Forgery)**
    *   **Issue:** Scraper scripts (`scrape_explorer.py`, `scrape_explorer_headless.py`) fetch URLs from an external list (`chainid.network`) without validation.
    *   **Risk:** A malicious chain list entry could point to `localhost:80` or internal AWS metadata services, leaking secrets.
    *   **Fix:** Validate domains against an allowlist or block private IP ranges.

3.  **SSL Verification Disabled**
    *   **Issue:** `INSECURE_SSL` env var disables SSL verification globally in many scripts (`ssl.CERT_NONE`).
    *   **Risk:** Man-in-the-Middle (MitM) attacks if running on non-secure networks.

4.  **CORS Misconfiguration (`server.py`)**
    *   **Issue:** Reads `ALLOWED_ORIGINS` but default behavior might be too permissive if configured incorrectly.

## 🐛 Bugs & Stability Issues

1.  **Missing Timeouts (`app/api/news/route.ts`)**
    *   **Issue:** RSS fetches fetch data without a `signal` or `timeout`.
    *   **Risk:** If a feed provider hangs, your API hangs indefinitely (DoS).
    *   **Fix:** Add `AbortController` with timeout (Fixed in `avax-price`, needed here too).

2.  **Blocking Calls (`measure_non_evm.py`)**
    *   **Issue:** `measure_sui` has a `time.sleep(5)` *inside* the function.
    *   **Risk:** Blocks the worker thread, reducing parallelism efficiency.

3.  **Frontend Sorting (`App.jsx`)**
    *   **Issue:** Sorting logic compares numbers with potential `null` or string values, leading to `NaN` and erratic sorting.
    *   **Fix:** Add strict type guards in sort function.

4.  **Resource Leaks (`measure_tps.py`)**
    *   **Issue:** RPC requests fetched via `urllib` might not strictly close connections if exceptions occur (though Python GC usually handles this).

## 🛠 Improvement Opportunities

1.  **Database Strategy**
    *   **Current:** Ad-hoc migration scripts (`add_column_x.py`) + Dual support (`sqlite`/`postgres`).
    *   **Recommendation:** Use a real migration tool like **Alembic** to manage schema changes safely.

2.  **Scraping Fragility**
    *   **Current:** Regex scraping (`TPS: ...`) is brittle.
    *   **Recommendation:** Use structured API data where available, or move regex logic to a config file for easier updates.

3.  **Code Duplication**
    *   **Current:** `get_ssl_context()` is copy-pasted in almost every script.
    *   **Recommendation:** Move shared logic to a `utils.py` module.
