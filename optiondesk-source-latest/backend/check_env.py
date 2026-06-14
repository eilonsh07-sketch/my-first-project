"""
Quick connectivity check — run once to verify .env is correct.
Usage: python check_env.py
"""
import os, sys, ssl
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # parse manually
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(env_path):
        for line in open(env_path):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

results = {}

# 1. ACCESS_CODE
code = os.environ.get("ACCESS_CODE", "")
results["ACCESS_CODE"] = ("[OK] set", True) if code and code != "your-strong-access-code-here" else ("[!!] missing or default", False)

# 2. Polygon
polygon_key = os.environ.get("POLYGON_API_KEY", "")
if not polygon_key:
    results["POLYGON_API_KEY"] = ("[!!] missing", False)
else:
    try:
        import urllib.request, json
        url = f"https://api.polygon.io/v1/marketstatus/now?apiKey={polygon_key}"
        with urllib.request.urlopen(url, timeout=10, context=_ctx) as r:
            data = json.loads(r.read())
        if "market" in data or data.get("status") in ("OK", "ok"):
            results["POLYGON_API_KEY"] = ("[OK] connected (market status OK)", True)
        elif data.get("status") == "ERROR":
            results["POLYGON_API_KEY"] = (f"[!!] {data.get('error','key invalid or plan too low')}", False)
        else:
            results["POLYGON_API_KEY"] = (f"[??] unexpected response: {str(data)[:60]}", False)
    except Exception as e:
        results["POLYGON_API_KEY"] = (f"[!!] error: {e}", False)

# 3. Anthropic
anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
if not anthropic_key:
    results["ANTHROPIC_API_KEY"] = ("[--] missing (agents won't work)", False)
else:
    try:
        import urllib.request, json
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=json.dumps({
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "ping"}]
            }).encode(),
            headers={
                "x-api-key": anthropic_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=15, context=_ctx) as r:
            results["ANTHROPIC_API_KEY"] = ("[OK] connected (Claude OK)", True)
    except Exception as e:
        msg = str(e)
        if "401" in msg:
            results["ANTHROPIC_API_KEY"] = ("[!!] key invalid (401)", False)
        elif "403" in msg:
            results["ANTHROPIC_API_KEY"] = ("[!!] no billing / plan issue (403)", False)
        else:
            results["ANTHROPIC_API_KEY"] = (f"[!!] error: {msg}", False)

# Print
print("\n=== OptionDesk ENV Check ===\n")
all_ok = True
for key, (status, ok) in results.items():
    print(f"  {key:25s}  {status}")
    if not ok:
        all_ok = False

print()
if all_ok:
    print("[OK] All good - ready to run.")
else:
    print("[!!] Fix the items marked [!!] above, then re-run.")
print()
